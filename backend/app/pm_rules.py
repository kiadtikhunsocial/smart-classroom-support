# -*- coding: utf-8 -*-
"""app/pm_rules.py — PM Rule Engine (Blueprint §38)

สามกฎตาม Blueprint:

* **Rule 1 REPEATED_FAILURE**       — อุปกรณ์มี ticket ตั้งแต่ 3 ใบใน 90 วัน
* **Rule 2 WARRANTY_EXPIRING**     — ประกันหมดภายใน 30 วัน (รวมที่หมดแล้วแต่ยังไม่แจ้ง)
* **Rule 3 REPLACEMENT_CANDIDATE** — อายุเกิน 4 ปี และซ่อมสะสมตั้งแต่ 5 ครั้ง

ทุกกฎเขียนผลลง ``device_health_flags`` และกันแจ้งซ้ำด้วยการเช็คว่ามี flag
rule_code เดิมของอุปกรณ์นั้นที่ยัง ``status='open'`` อยู่หรือไม่

โมดูลนี้ไม่ส่ง LINE เอง — คืนรายการ flag ที่สร้างใหม่ให้ผู้เรียกไปแจ้งเตือนต่อ
เพื่อให้ทดสอบได้โดยไม่ยิง external API
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select

from app.models import Device, DeviceHealthFlag, RepairTicket

# ─── พารามิเตอร์ของกฎ (§38) ───────────────────────────────────────────
REPEAT_WINDOW_DAYS = 90
REPEAT_THRESHOLD = 3
WARRANTY_WARN_DAYS = 30
REPLACE_AGE_YEARS = 4
REPLACE_REPAIR_THRESHOLD = 5

RULE_REPEATED_FAILURE = "REPEATED_FAILURE"
RULE_WARRANTY_EXPIRING = "WARRANTY_EXPIRING"
RULE_REPLACEMENT_CANDIDATE = "REPLACEMENT_CANDIDATE"

# ไม่นับ ticket ที่ถูกยกเลิกเป็น "ของเสีย"
_COUNTED_STATUSES_EXCLUDED = ("cancelled",)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _aware(value: Optional[datetime]) -> Optional[datetime]:
    """ทำให้ datetime มี timezone เสมอ — ค่าจาก DB บางแถวอาจเป็น naive"""
    if value is None:
        return None
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value


def _has_open_flag(db, device_id: str, rule_code: str) -> bool:
    stmt = (
        select(DeviceHealthFlag.id)
        .where(
            DeviceHealthFlag.device_id == device_id,
            DeviceHealthFlag.rule_code == rule_code,
            DeviceHealthFlag.status == "open",
        )
        .limit(1)
    )
    return db.execute(stmt).first() is not None


def _add_flag(db, device, rule_code, severity, message, detail) -> Optional[DeviceHealthFlag]:
    """สร้าง flag ถ้ายังไม่มีใบที่เปิดอยู่ — คืน None เมื่อข้ามเพราะซ้ำ"""
    if _has_open_flag(db, device.device_id, rule_code):
        return None
    flag = DeviceHealthFlag(
        device_id=device.device_id,
        organization_id=device.organization_id,
        rule_code=rule_code,
        severity=severity,
        message=message,
        detail=detail,
        status="open",
    )
    db.add(flag)
    return flag


def _repair_counts(db, since: Optional[datetime] = None) -> dict[str, int]:
    """จำนวน ticket (ไม่รวม cancelled) ต่ออุปกรณ์ — ระบุ ``since`` เพื่อจำกัดช่วงเวลา"""
    stmt = select(RepairTicket.device_id, func.count(RepairTicket.id)).where(
        RepairTicket.status.notin_(_COUNTED_STATUSES_EXCLUDED)
    )
    if since is not None:
        stmt = stmt.where(RepairTicket.created_at >= since)
    stmt = stmt.group_by(RepairTicket.device_id)
    return {row[0]: row[1] for row in db.execute(stmt).all()}


def _devices(db, organization_id: Optional[int] = None) -> list[Device]:
    stmt = select(Device).where(Device.status != "decommissioned")
    if organization_id is not None:
        stmt = stmt.where(Device.organization_id == organization_id)
    return list(db.execute(stmt).scalars().all())


# ─── Rule 1 ───────────────────────────────────────────────────────────
def rule_repeated_failure(db, organization_id: Optional[int] = None) -> list[DeviceHealthFlag]:
    """อุปกรณ์ที่มี ticket ≥ 3 ใบใน 90 วัน → REPEATED_FAILURE"""
    since = _now() - timedelta(days=REPEAT_WINDOW_DAYS)
    counts = _repair_counts(db, since=since)
    created: list[DeviceHealthFlag] = []

    for device in _devices(db, organization_id):
        n = counts.get(device.device_id, 0)
        if n < REPEAT_THRESHOLD:
            continue
        flag = _add_flag(
            db, device,
            RULE_REPEATED_FAILURE,
            "critical" if n >= REPEAT_THRESHOLD * 2 else "warning",
            f"อุปกรณ์ {device.device_id} มีการแจ้งซ่อม {n} ครั้งใน {REPEAT_WINDOW_DAYS} วัน",
            {"ticket_count": n, "window_days": REPEAT_WINDOW_DAYS,
             "threshold": REPEAT_THRESHOLD},
        )
        if flag is not None:
            created.append(flag)
    return created


# ─── Rule 2 ───────────────────────────────────────────────────────────
def rule_warranty_expiring(db, organization_id: Optional[int] = None) -> list[DeviceHealthFlag]:
    """ประกันหมดภายใน 30 วัน (หรือหมดแล้ว) → WARRANTY_EXPIRING แจ้ง admin"""
    now = _now()
    deadline = now + timedelta(days=WARRANTY_WARN_DAYS)
    created: list[DeviceHealthFlag] = []

    for device in _devices(db, organization_id):
        until = _aware(device.warranty_until)
        if until is None or until > deadline:
            continue
        days_left = (until - now).days
        expired = until <= now
        flag = _add_flag(
            db, device,
            RULE_WARRANTY_EXPIRING,
            "critical" if expired else "warning",
            (f"ประกันอุปกรณ์ {device.device_id} หมดแล้วเมื่อ {until.date()}" if expired
             else f"ประกันอุปกรณ์ {device.device_id} จะหมดใน {days_left} วัน ({until.date()})"),
            {"warranty_until": until.isoformat(), "days_left": days_left,
             "expired": expired, "warn_days": WARRANTY_WARN_DAYS},
        )
        if flag is not None:
            created.append(flag)
    return created


# ─── Rule 3 ───────────────────────────────────────────────────────────
def rule_replacement_candidate(db, organization_id: Optional[int] = None) -> list[DeviceHealthFlag]:
    """อายุ > 4 ปี และซ่อมสะสม ≥ 5 ครั้ง → REPLACEMENT_CANDIDATE เสนอเปลี่ยนเครื่อง

    อายุนับจาก ``purchase_date`` ถ้ามี ไม่มีก็ใช้ ``created_at`` ของระเบียนอุปกรณ์
    """
    now = _now()
    age_cutoff = now - timedelta(days=int(REPLACE_AGE_YEARS * 365.25))
    counts = _repair_counts(db)
    created: list[DeviceHealthFlag] = []

    for device in _devices(db, organization_id):
        ref_date = _aware(device.purchase_date) or _aware(device.created_at)
        if ref_date is None or ref_date > age_cutoff:
            continue
        n = counts.get(device.device_id, 0)
        if n < REPLACE_REPAIR_THRESHOLD:
            continue
        age_years = round((now - ref_date).days / 365.25, 1)
        flag = _add_flag(
            db, device,
            RULE_REPLACEMENT_CANDIDATE,
            "warning",
            (f"อุปกรณ์ {device.device_id} อายุ {age_years} ปี และซ่อมมาแล้ว {n} ครั้ง "
             f"— เสนอพิจารณาเปลี่ยนเครื่อง"),
            {"age_years": age_years, "repair_count": n,
             "age_basis": "purchase_date" if device.purchase_date else "created_at",
             "age_threshold_years": REPLACE_AGE_YEARS,
             "repair_threshold": REPLACE_REPAIR_THRESHOLD},
        )
        if flag is not None:
            created.append(flag)
    return created


# ─── Runner ───────────────────────────────────────────────────────────
def run_all(db, organization_id: Optional[int] = None, commit: bool = True) -> dict:
    """รันทั้งสามกฎ — คืนสรุปจำนวนและรายละเอียด flag ที่สร้างใหม่

    ผู้เรียกนำ ``flags`` ไปส่ง LINE/สร้าง ticket ต่อได้ (โมดูลนี้ไม่ยิง external API)
    """
    flags: list[DeviceHealthFlag] = []
    flags += rule_repeated_failure(db, organization_id)
    flags += rule_warranty_expiring(db, organization_id)
    flags += rule_replacement_candidate(db, organization_id)

    if commit:
        db.commit()
        for f in flags:
            db.refresh(f)

    summary: dict[str, int] = {
        RULE_REPEATED_FAILURE: 0,
        RULE_WARRANTY_EXPIRING: 0,
        RULE_REPLACEMENT_CANDIDATE: 0,
    }
    for f in flags:
        summary[f.rule_code] = summary.get(f.rule_code, 0) + 1

    return {
        "created": len(flags),
        "by_rule": summary,
        "flags": [
            {
                "id": f.id,
                "device_id": f.device_id,
                "organization_id": f.organization_id,
                "rule_code": f.rule_code,
                "severity": f.severity,
                "message": f.message,
                "detail": f.detail,
            }
            for f in flags
        ],
    }