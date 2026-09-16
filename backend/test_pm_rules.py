# -*- coding: utf-8 -*-
"""test_pm_rules.py — เทสต์ PM Rule Engine (Blueprint §38)

ครอบสามกฎตาม Blueprint:

* **Rule 1 REPEATED_FAILURE**       — Ticket ≥ 3 ใบใน 90 วัน
* **Rule 2 WARRANTY_EXPIRING**     — ประกันหมดภายใน 30 วัน (หรือหมดแล้ว)
* **Rule 3 REPLACEMENT_CANDIDATE** — อายุ > 4 ปี และซ่อมสะสม ≥ 5 ครั้ง

รวมพฤติกรรมที่ Blueprint บอกเป็นนัยและพลาดง่าย:

* ห้ามแจ้งซ้ำเมื่อยังมี flag ``status='open'`` ของกฎเดิมค้างอยู่
* Ticket ที่ ``cancelled`` ไม่นับเป็นของเสีย
* อุปกรณ์ ``decommissioned`` ต้องไม่ถูกตรวจ
* การรันแบบระบุ ``organization_id`` ต้องไม่ข้ามไปแตะโรงเรียนอื่น

เทสต์ชุดนี้เขียนลง PostgreSQL จริง (DATABASE_URL) เหมือน test_ticket_creation.py
จึงสร้างข้อมูลของตัวเองด้วยรหัสสุ่ม (PMTEST-<uuid>) แล้วลบทิ้งทั้งหมดใน fixture
ไม่พึ่งข้อมูล seed และไม่แตะแถวของระบบจริง ต่อฐานข้อมูลไม่ได้ → skip ไม่ใช่ fail
"""
from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from typing import Optional

import pytest
from sqlalchemy import select
from sqlalchemy import text as sa_text

from app import pm_rules
from app.models import (
    Device,
    DeviceHealthFlag,
    Organization,
    RepairTicket,
    SessionLocal,
)


def _now() -> datetime:
    return datetime.now(timezone.utc)


class _Sandbox:
    """สร้างข้อมูลทดสอบในฐานข้อมูลจริง และลบทิ้งให้หมดเมื่อจบเทสต์

    ลำดับการลบสำคัญ: device_health_flags → repair_tickets → devices → organizations
    เพราะ repair_tickets.device_id เป็น FK ondelete=RESTRICT (ลบ device ก่อนไม่ได้)
    """

    def __init__(self, db) -> None:
        self.db = db
        self.suffix = uuid.uuid4().hex[:8].upper()
        self.org_ids: list[int] = []
        self.device_ids: list[str] = []
        self.ticket_ids: list[str] = []

    # ─── สร้างข้อมูล ─────────────────────────────────────────────────
    def org(self) -> Organization:
        code = f"PMTEST-{self.suffix}-{len(self.org_ids) + 1}"
        org = Organization(code=code, name=f"โรงเรียนทดสอบ PM {code}")
        self.db.add(org)
        self.db.commit()
        self.db.refresh(org)
        self.org_ids.append(org.id)
        return org

    def device(
        self,
        org: Organization,
        *,
        purchase_date: Optional[datetime] = None,
        warranty_until: Optional[datetime] = None,
        status: str = "active",
    ) -> Device:
        device_id = f"PMTEST-{self.suffix}-{len(self.device_ids) + 1:03d}"
        device = Device(
            device_id=device_id,
            organization_id=org.id,
            device_type="Interactive Display",
            brand="TestBrand",
            model="PM-Rule",
            status=status,
            purchase_date=purchase_date,
            warranty_until=warranty_until,
            notes="สร้างโดย test_pm_rules.py",
        )
        self.db.add(device)
        self.db.commit()
        self.db.refresh(device)
        self.device_ids.append(device_id)
        return device

    def tickets(
        self,
        device: Device,
        count: int,
        *,
        days_ago: int = 10,
        status: str = "closed",
    ) -> None:
        """สร้าง ticket ย้อนหลัง ``days_ago`` วัน (ระบุ created_at เอง เพื่อคุมช่วงเวลาของกฎ)"""
        created_at = _now() - timedelta(days=days_ago)
        for i in range(count):
            ticket_id = f"TKPMTEST-{self.suffix}-{len(self.ticket_ids) + 1:04d}"
            self.db.add(
                RepairTicket(
                    ticket_id=ticket_id,
                    organization_id=device.organization_id,
                    device_id=device.device_id,
                    title=f"เทสต์ PM Rule ใบที่ {i + 1}",
                    description="ข้อมูลทดสอบอัตโนมัติ",
                    priority="normal",
                    status=status,
                    channel="qr",
                    created_at=created_at,
                )
            )
            self.ticket_ids.append(ticket_id)
        self.db.commit()

    # ─── อ่านผล ─────────────────────────────────────────────────────
    def flags_of(self, device: Device) -> list[DeviceHealthFlag]:
        stmt = (
            select(DeviceHealthFlag)
            .where(DeviceHealthFlag.device_id == device.device_id)
            .order_by(DeviceHealthFlag.id)
        )
        return list(self.db.execute(stmt).scalars().all())

    # ─── ล้างข้อมูล ─────────────────────────────────────────────────
    def cleanup(self) -> None:
        db = self.db
        db.rollback()
        if self.device_ids:
            db.execute(
                sa_text("DELETE FROM device_health_flags WHERE device_id = ANY(:ids)"),
                {"ids": self.device_ids},
            )
        if self.ticket_ids:
            db.execute(
                sa_text("DELETE FROM repair_tickets WHERE ticket_id = ANY(:ids)"),
                {"ids": self.ticket_ids},
            )
        if self.device_ids:
            db.execute(
                sa_text("DELETE FROM devices WHERE device_id = ANY(:ids)"),
                {"ids": self.device_ids},
            )
        if self.org_ids:
            db.execute(
                sa_text("DELETE FROM organizations WHERE id = ANY(:ids)"),
                {"ids": self.org_ids},
            )
        db.commit()


@pytest.fixture
def sandbox():
    try:
        db = SessionLocal()
    except Exception as exc:  # pragma: no cover — ขึ้นกับ environment
        pytest.skip(f"ต่อฐานข้อมูลไม่ได้: {exc!r}")
    try:
        db.execute(sa_text("SELECT 1 FROM device_health_flags LIMIT 1"))
    except Exception as exc:  # pragma: no cover — ยังไม่ได้ migrate
        db.rollback()
        db.close()
        pytest.skip(
            "ยังไม่มีตาราง device_health_flags "
            f"— รัน `python scripts/migrate_pm.py` ก่อน ({exc!r})"
        )

    box = _Sandbox(db)
    try:
        yield box
    finally:
        try:
            box.cleanup()
        finally:
            db.close()


# ─── Rule 1: REPEATED_FAILURE ─────────────────────────────────────────
def test_rule1_flags_device_with_three_tickets_in_window(sandbox):
    """§38 Rule 1: Ticket ≥ 3 ใบใน 90 วัน → REPEATED_FAILURE"""
    org = sandbox.org()
    device = sandbox.device(org)
    sandbox.tickets(device, pm_rules.REPEAT_THRESHOLD, days_ago=10)

    result = pm_rules.run_all(sandbox.db, organization_id=org.id)

    assert result["created"] == 1, result
    assert result["by_rule"][pm_rules.RULE_REPEATED_FAILURE] == 1

    flags = sandbox.flags_of(device)
    assert len(flags) == 1
    flag = flags[0]
    assert flag.rule_code == pm_rules.RULE_REPEATED_FAILURE
    assert flag.status == "open"
    assert flag.severity == "warning", "3 ใบยังไม่ถึงสองเท่าของเกณฑ์ ไม่ควรเป็น critical"
    assert flag.organization_id == org.id
    assert flag.detail["ticket_count"] == pm_rules.REPEAT_THRESHOLD
    assert flag.detail["window_days"] == pm_rules.REPEAT_WINDOW_DAYS


def test_rule1_ignores_tickets_older_than_window(sandbox):
    """Ticket เก่ากว่า 90 วัน ต้องไม่ทำให้เกิด flag"""
    org = sandbox.org()
    device = sandbox.device(org)
    sandbox.tickets(device, pm_rules.REPEAT_THRESHOLD + 2, days_ago=200)

    result = pm_rules.run_all(sandbox.db, organization_id=org.id)

    assert result["created"] == 0, result
    assert sandbox.flags_of(device) == []


def test_rule1_does_not_duplicate_open_flag(sandbox):
    """รันซ้ำแล้วยังมี flag เดิมเปิดอยู่ → ต้องไม่แจ้งซ้ำ"""
    org = sandbox.org()
    device = sandbox.device(org)
    sandbox.tickets(device, pm_rules.REPEAT_THRESHOLD, days_ago=5)

    first = pm_rules.run_all(sandbox.db, organization_id=org.id)
    second = pm_rules.run_all(sandbox.db, organization_id=org.id)

    assert first["created"] == 1
    assert second["created"] == 0, "flag เดิมยัง open อยู่ ห้ามสร้างใบใหม่"
    assert len(sandbox.flags_of(device)) == 1


def test_rule1_reflags_after_previous_flag_resolved(sandbox):
    """ปิดงานไปแล้ว (resolved) แต่ยังเสียซ้ำ → ต้องแจ้งได้อีกครั้ง"""
    org = sandbox.org()
    device = sandbox.device(org)
    sandbox.tickets(device, pm_rules.REPEAT_THRESHOLD, days_ago=5)

    pm_rules.run_all(sandbox.db, organization_id=org.id)
    flag = sandbox.flags_of(device)[0]
    flag.status = "resolved"
    flag.resolved_at = _now()
    sandbox.db.commit()

    again = pm_rules.run_all(sandbox.db, organization_id=org.id)

    assert again["created"] == 1, "flag เดิมถูกปิดแล้ว ควรแจ้งใหม่ได้"
    assert len(sandbox.flags_of(device)) == 2


def test_cancelled_tickets_are_not_counted(sandbox):
    """Ticket ที่ถูกยกเลิกไม่ใช่ของเสีย — ห้ามนับเข้าเกณฑ์"""
    org = sandbox.org()
    device = sandbox.device(org)
    sandbox.tickets(device, pm_rules.REPEAT_THRESHOLD + 1, days_ago=10, status="cancelled")

    result = pm_rules.run_all(sandbox.db, organization_id=org.id)

    assert result["created"] == 0, result
    assert sandbox.flags_of(device) == []


def test_decommissioned_device_is_skipped(sandbox):
    """อุปกรณ์ที่ปลดระวางแล้ว ไม่ต้องตรวจสุขภาพ"""
    org = sandbox.org()
    device = sandbox.device(org, status="decommissioned")
    sandbox.tickets(device, pm_rules.REPEAT_THRESHOLD + 3, days_ago=10)

    result = pm_rules.run_all(sandbox.db, organization_id=org.id)

    assert result["created"] == 0, result
    assert sandbox.flags_of(device) == []


# ─── Rule 2: WARRANTY_EXPIRING ────────────────────────────────────────
def test_rule2_warns_when_warranty_expires_soon(sandbox):
    """§38 Rule 2: ประกันจะหมดใน 30 วัน → WARRANTY_EXPIRING (warning)"""
    org = sandbox.org()
    until = _now() + timedelta(days=10)
    device = sandbox.device(org, warranty_until=until)

    result = pm_rules.run_all(sandbox.db, organization_id=org.id)

    assert result["by_rule"][pm_rules.RULE_WARRANTY_EXPIRING] == 1, result
    flag = sandbox.flags_of(device)[0]
    assert flag.rule_code == pm_rules.RULE_WARRANTY_EXPIRING
    assert flag.severity == "warning"
    assert flag.detail["expired"] is False
    assert 0 <= flag.detail["days_left"] <= pm_rules.WARRANTY_WARN_DAYS


def test_rule2_expired_warranty_is_critical(sandbox):
    """ประกันหมดไปแล้วและยังไม่เคยแจ้ง → critical"""
    org = sandbox.org()
    device = sandbox.device(org, warranty_until=_now() - timedelta(days=5))

    pm_rules.run_all(sandbox.db, organization_id=org.id)

    flag = sandbox.flags_of(device)[0]
    assert flag.rule_code == pm_rules.RULE_WARRANTY_EXPIRING
    assert flag.severity == "critical"
    assert flag.detail["expired"] is True


def test_rule2_ignores_warranty_far_in_future(sandbox):
    """ประกันยังเหลือเกิน 30 วัน → ไม่ต้องแจ้ง"""
    org = sandbox.org()
    device = sandbox.device(
        org, warranty_until=_now() + timedelta(days=pm_rules.WARRANTY_WARN_DAYS + 60)
    )

    result = pm_rules.run_all(sandbox.db, organization_id=org.id)

    assert result["created"] == 0, result
    assert sandbox.flags_of(device) == []


# ─── Rule 3: REPLACEMENT_CANDIDATE ────────────────────────────────────
def test_rule3_recommends_replacement_for_old_device(sandbox):
    """§38 Rule 3: อายุ > 4 ปี + ซ่อมสะสม ≥ 5 ครั้ง → REPLACEMENT_CANDIDATE

    ตั้ง ticket ไว้ 200 วันก่อน (นอกหน้าต่าง 90 วันของ Rule 1)
    เพื่อให้เหลือเฉพาะ Rule 3 ที่ต้องยิง
    """
    org = sandbox.org()
    device = sandbox.device(org, purchase_date=_now() - timedelta(days=365 * 6))
    sandbox.tickets(device, pm_rules.REPLACE_REPAIR_THRESHOLD, days_ago=200)

    result = pm_rules.run_all(sandbox.db, organization_id=org.id)

    assert result["by_rule"][pm_rules.RULE_REPLACEMENT_CANDIDATE] == 1, result
    assert result["by_rule"][pm_rules.RULE_REPEATED_FAILURE] == 0

    flag = sandbox.flags_of(device)[0]
    assert flag.rule_code == pm_rules.RULE_REPLACEMENT_CANDIDATE
    assert flag.detail["repair_count"] == pm_rules.REPLACE_REPAIR_THRESHOLD
    assert flag.detail["age_basis"] == "purchase_date"
    assert flag.detail["age_years"] >= pm_rules.REPLACE_AGE_YEARS


def test_rule3_ignores_young_device_with_many_repairs(sandbox):
    """ซ่อมบ่อยแต่เครื่องยังใหม่ → ยังไม่เสนอเปลี่ยน (ต้องเข้าเกณฑ์ทั้งสองข้อ)"""
    org = sandbox.org()
    device = sandbox.device(org, purchase_date=_now() - timedelta(days=365))
    sandbox.tickets(device, pm_rules.REPLACE_REPAIR_THRESHOLD + 2, days_ago=200)

    result = pm_rules.run_all(sandbox.db, organization_id=org.id)

    assert result["created"] == 0, result
    assert sandbox.flags_of(device) == []


def test_rule3_ignores_old_device_with_few_repairs(sandbox):
    """เครื่องเก่าแต่แทบไม่เคยเสีย → ไม่ต้องเสนอเปลี่ยน"""
    org = sandbox.org()
    device = sandbox.device(org, purchase_date=_now() - timedelta(days=365 * 8))
    sandbox.tickets(device, pm_rules.REPLACE_REPAIR_THRESHOLD - 3, days_ago=200)

    result = pm_rules.run_all(sandbox.db, organization_id=org.id)

    assert result["created"] == 0, result
    assert sandbox.flags_of(device) == []


# ─── Scope / runner ───────────────────────────────────────────────────
def test_run_all_respects_organization_scope(sandbox):
    """ระบุ organization_id → ต้องตรวจแค่โรงเรียนนั้น (RBAC ระดับข้อมูล §39)"""
    org_a = sandbox.org()
    org_b = sandbox.org()
    device_a = sandbox.device(org_a)
    device_b = sandbox.device(org_b)
    sandbox.tickets(device_a, pm_rules.REPEAT_THRESHOLD, days_ago=7)
    sandbox.tickets(device_b, pm_rules.REPEAT_THRESHOLD, days_ago=7)

    result = pm_rules.run_all(sandbox.db, organization_id=org_a.id)

    assert result["created"] == 1, result
    assert [f["device_id"] for f in result["flags"]] == [device_a.device_id]
    assert len(sandbox.flags_of(device_a)) == 1
    assert sandbox.flags_of(device_b) == [], "ห้ามข้ามไปแจ้งอุปกรณ์ของโรงเรียนอื่น"


def test_run_all_summary_counts_every_rule(sandbox):
    """สรุปผลต้องมีคีย์ครบทั้งสามกฎ และรวมยอดตรงกับรายการ flag"""
    org = sandbox.org()
    repeated = sandbox.device(org)
    sandbox.tickets(repeated, pm_rules.REPEAT_THRESHOLD, days_ago=3)
    warranty = sandbox.device(org, warranty_until=_now() + timedelta(days=7))

    result = pm_rules.run_all(sandbox.db, organization_id=org.id)

    assert set(result["by_rule"]) == {
        pm_rules.RULE_REPEATED_FAILURE,
        pm_rules.RULE_WARRANTY_EXPIRING,
        pm_rules.RULE_REPLACEMENT_CANDIDATE,
    }
    assert result["by_rule"][pm_rules.RULE_REPEATED_FAILURE] == 1
    assert result["by_rule"][pm_rules.RULE_WARRANTY_EXPIRING] == 1
    assert result["created"] == sum(result["by_rule"].values()) == len(result["flags"])
    assert {f["device_id"] for f in result["flags"]} == {
        repeated.device_id,
        warranty.device_id,
    }
    for f in result["flags"]:
        assert f["id"] is not None, "flag ต้องถูก commit และมี id จริง"
        assert f["message"]