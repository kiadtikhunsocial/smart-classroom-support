# -*- coding: utf-8 -*-
"""test_audit_log.py — เทสต์ Audit Log (Blueprint §40)

§40 กำหนดว่าเหตุการณ์สำคัญต้องถูกบันทึกย้อนหลังได้: Login, เปลี่ยนสิทธิ์,
สร้าง/แก้/ลบ Asset, Assign งาน, เปลี่ยน Status, ปิดงาน, แก้ KB และ System Settings

ไฟล์นี้ครอบส่วนที่เพิ่งเดินสายไว้ในชั้น endpoint (assign / status / close / KB /
settings) รวมทั้งสัญญาของ ``GET /api/audit-logs``:

* ต้องมีแถว audit หนึ่งแถวต่อหนึ่งเหตุการณ์ พร้อม ``old_value``/``new_value``
* ต้องผูกตัวผู้กระทำ (user_id / user_name / user_role) และ IP ไว้ด้วย
* แถว audit ต้อง commit ไปพร้อม transaction เดิม — ถ้าคำสั่งล้มเหลว ต้องไม่มีแถวค้าง
* endpoint อ่าน log เปิดให้ admin ขึ้นไปเท่านั้น (teacher → 403, ไม่มี token → 401)

เทสต์ชุดนี้เขียนลง PostgreSQL จริง (DATABASE_URL) เหมือน test_pm_rules.py จึงสร้าง
ข้อมูลของตัวเองด้วยรหัสสุ่ม (AUDITTEST-<uuid>) แล้วลบทิ้งทั้งหมดใน fixture
ค่าใน ตาราง settings ที่ถูกแก้ระหว่างเทสต์จะถูกสำรองและคืนค่าเดิมให้เสมอ
ต่อฐานข้อมูลไม่ได้ / ยังไม่ได้ migrate ตาราง audit_logs → skip ไม่ใช่ fail
"""
from __future__ import annotations

import json
import uuid
from typing import Any, Optional

import pytest
from sqlalchemy import select
from sqlalchemy import text as sa_text
from starlette.testclient import TestClient

from app.main import app, create_token
from app.models import (
    AuditLog,
    Device,
    KBArticle,
    Organization,
    RepairTicket,
    SessionLocal,
    Setting,
    User,
)

client = TestClient(app)

# คีย์ที่ใช้ทดสอบ settings — ต้องอยู่ใน allowed ของ update_settings()
SETTING_KEY = "auto_close_days"

# starlette TestClient ไม่ตั้งค่า request.client (เป็น None) จึงพิสูจน์การบันทึก IP
# ผ่านทาง X-Forwarded-For ซึ่งเป็นทางที่ใช้จริงหลัง reverse proxy อยู่แล้ว
TEST_CLIENT_IP = "203.0.113.9"


class _Sandbox:
    """สร้างข้อมูลทดสอบในฐานข้อมูลจริง และลบทิ้งให้หมดเมื่อจบเทสต์

    ลำดับการลบสำคัญ: audit_logs → repair_tickets (ticket_updates ตาม cascade)
    → devices → users → organizations  เพราะ repair_tickets.device_id เป็น FK
    ondelete=RESTRICT (ลบ device ก่อน ticket ไม่ได้)
    """

    def __init__(self, db) -> None:
        self.db = db
        self.suffix = uuid.uuid4().hex[:8].upper()
        self.org_ids: list[int] = []
        self.user_ids: list[int] = []
        self.device_ids: list[str] = []
        self.ticket_ids: list[str] = []
        self.kb_ids: list[str] = []
        self._setting_backup: Optional[tuple[str, Optional[str]]] = None

    # ─── สร้างข้อมูล ─────────────────────────────────────────────────
    def org(self) -> Organization:
        code = f"AUDITTEST-{self.suffix}-{len(self.org_ids) + 1}"
        org = Organization(code=code, name=f"โรงเรียนทดสอบ Audit {code}")
        self.db.add(org)
        self.db.commit()
        self.db.refresh(org)
        self.org_ids.append(org.id)
        return org

    def user(self, role: str, org: Optional[Organization] = None) -> User:
        u = User(
            line_user_id=f"AUDITTEST-{self.suffix}-{len(self.user_ids) + 1:02d}",
            line_display_name=f"ผู้ใช้ทดสอบ {role}",
            organization_id=org.id if org else None,
            role=role,
            is_active=True,
        )
        self.db.add(u)
        self.db.commit()
        self.db.refresh(u)
        self.user_ids.append(u.id)
        return u

    def device(self, org: Organization) -> Device:
        device_id = f"AUDITTEST-{self.suffix}-{len(self.device_ids) + 1:03d}"
        d = Device(
            device_id=device_id,
            organization_id=org.id,
            device_type="Interactive Display",
            brand="TestBrand",
            model="Audit-40",
            status="active",
            notes="สร้างโดย test_audit_log.py",
        )
        self.db.add(d)
        self.db.commit()
        self.db.refresh(d)
        self.device_ids.append(device_id)
        return d

    def ticket(self, device: Device, status: str = "new") -> RepairTicket:
        ticket_id = f"TKAUDIT-{self.suffix}-{len(self.ticket_ids) + 1:04d}"
        t = RepairTicket(
            ticket_id=ticket_id,
            organization_id=device.organization_id,
            device_id=device.device_id,
            title="เทสต์ Audit Log",
            description="ข้อมูลทดสอบอัตโนมัติ §40",
            priority="normal",
            status=status,
            channel="qr",
        )
        self.db.add(t)
        self.db.commit()
        self.db.refresh(t)
        self.ticket_ids.append(ticket_id)
        return t

    # ─── เรียก API ในนามผู้ใช้ ────────────────────────────────────────
    def headers(self, user: User) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {create_token(user)}",
            "X-Forwarded-For": f"{TEST_CLIENT_IP}, 10.0.0.1",
        }

    # ─── อ่านผล ─────────────────────────────────────────────────────
    def logs(
        self,
        *,
        action: Optional[str] = None,
        entity_id: Optional[str] = None,
    ) -> list[AuditLog]:
        """อ่าน audit เฉพาะที่เกิดจากผู้ใช้ของ sandbox นี้ (ไม่ปนกับข้อมูลจริง)"""
        self.db.rollback()  # เริ่ม transaction ใหม่ เพื่อเห็นแถวที่ API commit ไปแล้ว
        stmt = select(AuditLog).where(AuditLog.user_id.in_(self.user_ids or [-1]))
        if action:
            stmt = stmt.where(AuditLog.action == action)
        if entity_id:
            stmt = stmt.where(AuditLog.entity_id == entity_id)
        return list(self.db.execute(stmt.order_by(AuditLog.id)).scalars().all())

    def one_log(self, *, action: str, entity_id: Optional[str] = None) -> AuditLog:
        rows = self.logs(action=action, entity_id=entity_id)
        assert len(rows) == 1, (
            f"ต้องมีแถว audit ของ {action} เพียงแถวเดียว แต่ได้ {len(rows)} แถว"
        )
        return rows[0]

    # ─── settings: สำรอง/คืนค่า ──────────────────────────────────────
    def backup_setting(self, key: str) -> Optional[str]:
        row = self.db.execute(select(Setting).where(Setting.key == key)).scalar_one_or_none()
        self._setting_backup = (key, row.value if row else None)
        return row.value if row else None

    def _restore_setting(self) -> None:
        if self._setting_backup is None:
            return
        key, value = self._setting_backup
        row = self.db.execute(select(Setting).where(Setting.key == key)).scalar_one_or_none()
        if value is None:
            if row is not None:
                self.db.delete(row)
        elif row is not None:
            row.value = value
        else:
            self.db.add(Setting(key=key, value=value))
        self.db.commit()

    # ─── ล้างข้อมูล ─────────────────────────────────────────────────
    def cleanup(self) -> None:
        db = self.db
        db.rollback()
        self._restore_setting()
        if self.user_ids:
            db.execute(
                sa_text("DELETE FROM audit_logs WHERE user_id = ANY(:ids)"),
                {"ids": self.user_ids},
            )
        if self.kb_ids:
            db.execute(
                sa_text("DELETE FROM kb_articles WHERE kb_id = ANY(:ids)"),
                {"ids": self.kb_ids},
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
        if self.user_ids:
            db.execute(
                sa_text("DELETE FROM users WHERE id = ANY(:ids)"),
                {"ids": self.user_ids},
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
        db.execute(sa_text("SELECT 1 FROM audit_logs LIMIT 1"))
    except Exception as exc:  # pragma: no cover — ยังไม่ได้ migrate
        db.rollback()
        db.close()
        pytest.skip(f"ยังไม่มีตาราง audit_logs — รัน migration ก่อน ({exc!r})")

    box = _Sandbox(db)
    try:
        yield box
    finally:
        try:
            box.cleanup()
        finally:
            db.close()


def _loads(value: Optional[str]) -> Any:
    """แปลง old_value/new_value ที่ write_audit เก็บเป็น JSON string"""
    assert value is not None, "ต้องบันทึกค่าไว้ ไม่ใช่ None"
    return json.loads(value)


def _assert_actor(row: AuditLog, user: User) -> None:
    """ทุกแถวต้องระบุได้ว่าใครทำ จาก IP ไหน — ไม่งั้นย้อนสอบไม่ได้ (§40)"""
    assert row.user_id == user.id
    assert row.user_name == user.line_display_name
    assert row.user_role == user.role
    # ต้องเก็บ IP ต้นทางตัวแรกของ X-Forwarded-For ไม่ใช่ IP ของ proxy ตัวกลาง
    assert row.ip_address == TEST_CLIENT_IP, "ต้องบันทึก IP ผู้เรียกจาก X-Forwarded-For"
    assert row.user_agent, "ต้องบันทึก user-agent ผู้เรียก"
    assert row.created_at is not None


# ─── Assign งาน ───────────────────────────────────────────────────────
def test_assign_writes_audit_with_old_and_new_assignee(sandbox):
    """§40: Assign งาน → บันทึกผู้รับผิดชอบเดิมและใหม่"""
    org = sandbox.org()
    admin = sandbox.user("admin")
    device = sandbox.device(org)
    ticket = sandbox.ticket(device)

    res = client.post(
        f"/api/tickets/{ticket.ticket_id}/assign",
        json={"assignee": "ช่างสมชาย", "note": "มอบหมายโดยเทสต์"},
        headers=sandbox.headers(admin),
    )
    assert res.status_code == 200, res.text

    row = sandbox.one_log(action="ticket_assign", entity_id=ticket.ticket_id)
    _assert_actor(row, admin)
    assert row.entity_type == "ticket"
    old, new = _loads(row.old_value), _loads(row.new_value)
    assert old["status"] == "new"
    assert old["assigned_to"] is None, "ยังไม่เคยมอบหมาย → ค่าเดิมต้องเป็น null"
    assert new["assigned_to"] == "ช่างสมชาย"
    assert new["status"] == "assigned"
    assert new["note"] == "มอบหมายโดยเทสต์"


def test_failed_assign_leaves_no_audit_row(sandbox):
    """คำสั่งที่ล้มเหลว (403) ต้องไม่ทิ้งแถว audit ค้างไว้"""
    org = sandbox.org()
    teacher = sandbox.user("teacher", org)
    device = sandbox.device(org)
    ticket = sandbox.ticket(device)

    res = client.post(
        f"/api/tickets/{ticket.ticket_id}/assign",
        json={"assignee": "ช่างที่ไม่ควรถูกบันทึก"},
        headers=sandbox.headers(teacher),
    )
    assert res.status_code == 403, res.text
    assert sandbox.logs() == [], "ครูไม่มีสิทธิ์ assign — ห้ามมีแถว audit"


# ─── เปลี่ยน Status / ปิดงาน ──────────────────────────────────────────
def test_status_change_and_close_are_separate_actions(sandbox):
    """§40: เปลี่ยน Status และปิดงาน ต้องแยก action กันเพื่อกรองรายงานได้"""
    org = sandbox.org()
    admin = sandbox.user("admin")
    device = sandbox.device(org)
    ticket = sandbox.ticket(device)
    headers = sandbox.headers(admin)

    res = client.patch(
        f"/api/tickets/{ticket.ticket_id}/status",
        json={"status": "in_progress", "force": True, "note": "เริ่มซ่อม"},
        headers=headers,
    )
    assert res.status_code == 200, res.text

    changed = sandbox.one_log(action="ticket_status_change", entity_id=ticket.ticket_id)
    _assert_actor(changed, admin)
    assert _loads(changed.old_value)["status"] == "new"
    new = _loads(changed.new_value)
    assert new["status"] == "in_progress"
    assert new["via"] == "user", "เรียกด้วย token ผู้ใช้ ไม่ใช่ n8n"

    res = client.patch(
        f"/api/tickets/{ticket.ticket_id}/status",
        json={"status": "closed", "force": True, "note": "ปิดงาน"},
        headers=headers,
    )
    assert res.status_code == 200, res.text

    closed = sandbox.one_log(action="ticket_close", entity_id=ticket.ticket_id)
    assert _loads(closed.old_value)["status"] == "in_progress"
    assert _loads(closed.new_value)["status"] == "closed"
    assert len(sandbox.logs(entity_id=ticket.ticket_id)) == 2, "ต้องได้ 2 แถว ไม่ทับกัน"


def test_resolve_records_root_cause_and_solution(sandbox):
    """§40: บันทึกผลการซ่อม → เก็บสาเหตุ/วิธีแก้ไว้ใน audit ด้วย"""
    org = sandbox.org()
    admin = sandbox.user("admin")
    device = sandbox.device(org)
    ticket = sandbox.ticket(device, status="in_progress")

    res = client.post(
        f"/api/tickets/{ticket.ticket_id}/resolve",
        json={"root_cause": "สาย HDMI หลวม", "solution": "เสียบสาย HDMI ใหม่และทดสอบภาพ"},
        headers=sandbox.headers(admin),
    )
    assert res.status_code == 200, res.text

    row = sandbox.one_log(action="ticket_resolve", entity_id=ticket.ticket_id)
    _assert_actor(row, admin)
    assert _loads(row.old_value)["status"] == "in_progress"
    new = _loads(row.new_value)
    assert new["status"] == "resolved"
    assert new["root_cause"] == "สาย HDMI หลวม"
    assert new["solution"].startswith("เสียบสาย HDMI ใหม่")


# ─── Knowledge Base ───────────────────────────────────────────────────
def test_kb_create_update_delete_are_audited(sandbox):
    """§40: แก้ KB ทุกแบบต้องถูกบันทึก และการลบต้องเก็บค่าเดิมไว้ก่อนหาย"""
    admin = sandbox.user("admin")
    headers = sandbox.headers(admin)

    created = client.post(
        "/api/kb/articles",
        json={
            "title": f"AUDITTEST-{sandbox.suffix} จอไม่มีภาพ",
            "device_type": "Interactive Display",
            "symptom_tags": ["ไม่มีภาพ"],
            "steps": [{"order": 1, "text": "ตรวจสาย HDMI"}],
        },
        headers=headers,
    )
    assert created.status_code == 201, created.text
    kb_id = created.json()["kb_id"]
    sandbox.kb_ids.append(kb_id)

    row = sandbox.one_log(action="kb_create", entity_id=kb_id)
    _assert_actor(row, admin)
    assert row.entity_type == "kb_article"
    assert _loads(row.new_value)["title"].startswith(f"AUDITTEST-{sandbox.suffix}")

    patched = client.patch(
        f"/api/kb/articles/{kb_id}",
        json={"title": f"AUDITTEST-{sandbox.suffix} แก้ชื่อแล้ว"},
        headers=headers,
    )
    assert patched.status_code == 200, patched.text

    row = sandbox.one_log(action="kb_update", entity_id=kb_id)
    assert _loads(row.old_value)["title"].endswith("จอไม่มีภาพ"), "ต้องเก็บชื่อก่อนแก้"
    assert _loads(row.new_value)["title"].endswith("แก้ชื่อแล้ว")

    deleted = client.delete(f"/api/kb/articles/{kb_id}", headers=headers)
    assert deleted.status_code == 200, deleted.text

    row = sandbox.one_log(action="kb_delete", entity_id=kb_id)
    old = _loads(row.old_value)
    assert old["kb_id"] == kb_id
    assert old["title"].endswith("แก้ชื่อแล้ว"), "ต้องเก็บค่าล่าสุดก่อนลบ"


def test_kb_update_without_changes_writes_nothing(sandbox):
    """PATCH ที่ไม่ส่งฟิลด์ใดเลย ไม่ใช่การแก้ไข — ห้ามสร้างแถว audit ขยะ"""
    admin = sandbox.user("admin")
    headers = sandbox.headers(admin)

    created = client.post(
        "/api/kb/articles",
        json={"title": f"AUDITTEST-{sandbox.suffix} ไม่มีการแก้", "device_type": "Router"},
        headers=headers,
    )
    assert created.status_code == 201, created.text
    kb_id = created.json()["kb_id"]
    sandbox.kb_ids.append(kb_id)

    res = client.patch(f"/api/kb/articles/{kb_id}", json={}, headers=headers)
    assert res.status_code == 200, res.text
    assert sandbox.logs(action="kb_update", entity_id=kb_id) == []


# ─── System Settings ──────────────────────────────────────────────────
def test_settings_update_records_before_and_after(sandbox):
    """§40: เปลี่ยนค่าระบบ (SLA/auto-close) ต้องรู้ว่าใครเปลี่ยนจากอะไรเป็นอะไร"""
    admin = sandbox.user("admin")
    before_raw = sandbox.backup_setting(SETTING_KEY)

    res = client.patch(
        "/api/settings",
        json={SETTING_KEY: 9},
        headers=sandbox.headers(admin),
    )
    assert res.status_code == 200, res.text
    assert res.json()["updated"] == [SETTING_KEY]

    row = sandbox.one_log(action="settings_update")
    _assert_actor(row, admin)
    assert row.entity_type == "setting"
    assert row.entity_id == SETTING_KEY
    assert len(row.entity_id) <= 64, "คอลัมน์ entity_id กว้าง 64 ตัวอักษร"
    assert _loads(row.old_value)[SETTING_KEY] == before_raw
    assert _loads(row.new_value)[SETTING_KEY] == 9


def test_settings_update_ignores_unknown_keys(sandbox):
    """คีย์ที่ไม่อยู่ใน allowed ถูกข้าม → ไม่มีอะไรเปลี่ยน จึงต้องไม่มีแถว audit"""
    admin = sandbox.user("admin")

    res = client.patch(
        "/api/settings",
        json={"not_a_real_setting": 123},
        headers=sandbox.headers(admin),
    )
    assert res.status_code == 200, res.text
    assert res.json()["updated"] == []
    assert sandbox.logs(action="settings_update") == []


# ─── endpoint อ่าน Audit Log ──────────────────────────────────────────
def test_audit_log_endpoint_filters_and_parses_json(sandbox):
    """GET /api/audit-logs: กรองตาม action/entity_id ได้ และคืน old/new เป็น object"""
    org = sandbox.org()
    admin = sandbox.user("admin")
    device = sandbox.device(org)
    ticket = sandbox.ticket(device)
    headers = sandbox.headers(admin)

    assert client.post(
        f"/api/tickets/{ticket.ticket_id}/assign",
        json={"assignee": "ช่างสมหญิง"},
        headers=headers,
    ).status_code == 200

    res = client.get(
        "/api/audit-logs",
        params={"action": "ticket_assign", "entity_id": ticket.ticket_id},
        headers=headers,
    )
    assert res.status_code == 200, res.text
    rows = res.json()
    assert len(rows) == 1, rows
    item = rows[0]
    assert item["action"] == "ticket_assign"
    assert item["entity_id"] == ticket.ticket_id
    assert item["user_id"] == admin.id
    # §40: ต้องอ่านค่าเป็น object ไม่ใช่ JSON string ดิบ
    assert isinstance(item["new_value"], dict), item["new_value"]
    assert item["new_value"]["assigned_to"] == "ช่างสมหญิง"
    assert isinstance(item["old_value"], dict), item["old_value"]


def test_audit_log_endpoint_requires_admin(sandbox):
    """log การกระทำเป็นข้อมูลอ่อนไหว — teacher ห้ามเห็น, ไม่มี token ห้ามเห็น"""
    org = sandbox.org()
    teacher = sandbox.user("teacher", org)

    assert client.get("/api/audit-logs").status_code == 401
    res = client.get("/api/audit-logs", headers=sandbox.headers(teacher))
    assert res.status_code == 403, res.text


def test_audit_log_can_hide_login_noise_without_losing_other_events(sandbox):
    admin = sandbox.user("admin")
    sandbox.db.add_all([
        AuditLog(user_id=admin.id, user_name="Audit test", action="login", entity_type="user", entity_id=str(admin.id)),
        AuditLog(user_id=admin.id, user_name="Audit test", action="device_update", entity_type="device", entity_id="AUDITTEST-SAMPLE"),
    ])
    sandbox.db.commit()
    params = {"user_id": admin.id, "include_logins": "false"}
    hidden = client.get("/api/audit-logs", params=params, headers=sandbox.headers(admin))
    assert hidden.status_code == 200, hidden.text
    assert [row["action"] for row in hidden.json()] == ["device_update"]
    shown = client.get("/api/audit-logs", params={"user_id": admin.id}, headers=sandbox.headers(admin))
    assert shown.status_code == 200, shown.text
    assert {row["action"] for row in shown.json()} == {"login", "device_update"}


def test_kb_draft_is_not_public_and_publish_needs_content(sandbox):
    admin = sandbox.user("admin")
    created = client.post("/api/kb/articles", headers=sandbox.headers(admin),
                          json={"title": f"AUDITTEST-{sandbox.suffix} draft"})
    assert created.status_code == 201, created.text
    kb_id = created.json()["kb_id"]
    sandbox.kb_ids.append(kb_id)
    assert created.json()["is_published"] is False
    assert client.get(f"/api/kb/articles/{kb_id}").status_code == 404
    assert all(row["kb_id"] != kb_id for row in client.get("/api/kb/articles").json())
    invalid = client.patch(f"/api/kb/articles/{kb_id}", headers=sandbox.headers(admin),
                           json={"is_published": True})
    assert invalid.status_code == 422
    valid = client.patch(f"/api/kb/articles/{kb_id}", headers=sandbox.headers(admin),
                         json={"symptom_tags": ["no signal"],
                               "steps": [{"order": 1, "text": "ตรวจสายสัญญาณ"}],
                               "is_published": True})
    assert valid.status_code == 200, valid.text
    assert client.get(f"/api/kb/articles/{kb_id}").status_code == 200
