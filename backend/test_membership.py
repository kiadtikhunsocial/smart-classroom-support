# -*- coding: utf-8 -*-
"""test_membership.py — เทสต์ flow สมัครสมาชิก/อนุมัติ (POST /api/public/register,
GET /api/registrations, POST /api/registrations/{id}/approve|reject)

พฤติกรรมที่ต้องคงไว้
--------------------
1. สมัครผ่านหน้าสาธารณะ → ได้แถวคำขอสถานะ pending เท่านั้น **ยังเข้าระบบไม่ได้**
   และรหัสผ่านต้องถูก hash (ห้ามเก็บรหัสดิบ)
2. ห้ามยกบทบาทให้ตัวเอง: ส่ง field role/requested_role มาด้วยก็ต้องถูกเมิน
   คำขอจากหน้าสาธารณะได้ PUBLIC_SIGNUP_ROLE เสมอ
3. ชื่อผู้ใช้ซ้ำ (มีบัญชีแล้ว หรือมีคำขอค้าง) → 409 ด้วยข้อความเดียวกัน
   (ไม่บอกใบ้ว่ามีบัญชีนั้นอยู่จริง) / รหัสหน่วยงานไม่มีจริง → 404
4. รายการคำขอเปิดให้ MEMBERSHIP_REVIEW_ROLES เท่านั้น: ไม่มี token → 401,
   it_support → 403, admin_school เห็นเฉพาะคำขอของโรงเรียนตัวเอง
5. response ของรายการ/การปฏิเสธ ต้องไม่มี password_hash ติดออกไป
6. อนุมัติ → สร้างบัญชีจริงด้วย hash เดิม ผู้สมัครล็อกอินด้วยรหัสที่ตั้งไว้ได้ทันที
   อนุมัติ/ปฏิเสธซ้ำ → 409 และ admin_school ยกบทบาทเกิน
   SCHOOL_ADMIN_ASSIGNABLE_ROLES ไม่ได้ (403 และคำขอต้องยัง pending)

เทสต์ชุดนี้เขียนลง PostgreSQL จริง (DATABASE_URL) แบบเดียวกับ test_audit_log.py
สร้างข้อมูลของตัวเองด้วยรหัสสุ่ม (MEMTEST-<uuid>) แล้วลบทิ้งทั้งหมดใน fixture
ต่อฐานข้อมูลไม่ได้ / ยังไม่ได้ migrate ตาราง membership_applications → skip ไม่ใช่ fail
(migrate ด้วย `python scripts/migrate_membership.py`)

สองอย่างที่ถูกปิดไว้ระหว่างเทสต์:
* rate limit ของ /api/public/register (5/hour) — ไม่งั้นเคสหลัง ๆ จะได้ 429
* google_sheets.append_membership_row — เทสต์ต้องไม่ยิงเน็ตออกไปจริง
"""
from __future__ import annotations

import uuid
from typing import Optional

import pytest
from sqlalchemy import select
from sqlalchemy import text as sa_text
from starlette.testclient import TestClient

from app import google_sheets
from app.main import (
    MEMBERSHIP_REVIEW_ROLES,
    PUBLIC_SIGNUP_ROLE,
    SCHOOL_ADMIN_ASSIGNABLE_ROLES,
    app,
    create_token,
    hash_password,
    limiter,
)
from app.models import (
    MEMBERSHIP_APPROVED,
    MEMBERSHIP_PENDING,
    MEMBERSHIP_REJECTED,
    MembershipApplication,
    Organization,
    SessionLocal,
    User,
)

client = TestClient(app)

#: รหัสผ่านที่ผู้สมัครตั้ง — ยาวพอตาม MembershipApplyIn (min_length=8)
PASSWORD = "Test-Passw0rd"

#: ฟิลด์ที่ห้ามหลุดออกจาก response ของ endpoint คำขอสมัคร
SENSITIVE_FIELDS = ("password", "password_hash")


class _Sandbox:
    """สร้างข้อมูลทดสอบในฐานข้อมูลจริง แล้วลบทิ้งให้หมดเมื่อจบเทสต์

    ลำดับการลบ: audit_logs → membership_applications → users → organizations
    (membership_applications.reviewed_by/created_user_id เป็น FK ondelete SET NULL
    แต่ลบคำขอก่อนอยู่แล้วเพื่อไม่ต้องพึ่งพฤติกรรมนั้น)
    """

    def __init__(self, db) -> None:
        self.db = db
        self.suffix = uuid.uuid4().hex[:8].lower()
        self.org_ids: list[int] = []
        self.user_ids: list[int] = []
        self.app_ids: list[int] = []

    # ─── สร้างข้อมูล ─────────────────────────────────────────────────
    def org(self) -> Organization:
        code = f"MEMTEST-{self.suffix}-{len(self.org_ids) + 1}"
        org = Organization(code=code, name=f"โรงเรียนทดสอบสมัครสมาชิก {code}")
        self.db.add(org)
        self.db.commit()
        self.db.refresh(org)
        self.org_ids.append(org.id)
        return org

    def user(self, role: str, org: Optional[Organization] = None) -> User:
        u = User(
            line_user_id=f"memtest.{self.suffix}.{role}.{len(self.user_ids) + 1}",
            line_display_name=f"ผู้ดูแลทดสอบ {role}",
            organization_id=org.id if org else None,
            role=role,
            is_active=True,
        )
        self.db.add(u)
        self.db.commit()
        self.db.refresh(u)
        self.user_ids.append(u.id)
        return u

    def username(self, tag: str) -> str:
        """ชื่อผู้ใช้ที่ตรง pattern ^[a-zA-Z0-9._-]+$ และไม่ชนกับข้อมูลจริง"""
        return f"memtest.{self.suffix}.{tag}"

    def application(
        self,
        *,
        username: str,
        org: Optional[Organization] = None,
        status: str = MEMBERSHIP_PENDING,
        requested_role: str = PUBLIC_SIGNUP_ROLE,
    ) -> MembershipApplication:
        """สร้างคำขอตรงในฐานข้อมูล — ใช้เตรียมข้อมูลให้เคสที่ทดสอบฝั่งผู้ดูแล"""
        row = MembershipApplication(
            username=username,
            full_name=f"ผู้สมัครทดสอบ {username}",
            email=f"{username}@example.com",
            phone="02-000-0000",
            organization_id=org.id if org else None,
            organization_code=org.code if org else None,
            requested_role=requested_role,
            password_hash=hash_password(PASSWORD),
            note="สร้างโดย test_membership.py",
            status=status,
        )
        self.db.add(row)
        self.db.commit()
        self.db.refresh(row)
        self.app_ids.append(row.id)
        return row

    # ─── เรียก API ในนามผู้ใช้ ────────────────────────────────────────
    def headers(self, user: User) -> dict[str, str]:
        return {"Authorization": f"Bearer {create_token(user)}"}

    # ─── อ่านผล ─────────────────────────────────────────────────────
    def fetch_application(self, application_id: int) -> MembershipApplication:
        # rollback ก่อน เพื่อเริ่ม transaction ใหม่และเห็นแถวที่ API commit ไปแล้ว
        self.db.rollback()
        row = self.db.get(MembershipApplication, application_id)
        assert row is not None, f"ไม่พบคำขอ id={application_id} ในฐานข้อมูล"
        return row

    def find_user(self, username: str) -> Optional[User]:
        self.db.rollback()
        return self.db.execute(
            select(User).where(User.line_user_id == username)
        ).scalar_one_or_none()

    def track_created_user(self, username: str) -> User:
        """ผูกบัญชีที่เกิดจากการอนุมัติเข้ากับ cleanup"""
        u = self.find_user(username)
        assert u is not None, f"อนุมัติแล้วต้องมีบัญชี {username} ในตาราง users"
        if u.id not in self.user_ids:
            self.user_ids.append(u.id)
        return u

    def register(self, **overrides) -> "object":
        """POST /api/public/register ด้วยข้อมูลครบชุด แล้วผูก id เข้ากับ cleanup"""
        payload = {
            "username": overrides.pop("username"),
            "password": overrides.pop("password", PASSWORD),
            "full_name": overrides.pop("full_name", "ผู้สมัครทดสอบสมาชิก"),
            "email": overrides.pop("email", "memtest@example.com"),
            "phone": overrides.pop("phone", "02-000-0000"),
            "note": overrides.pop("note", "สร้างโดย test_membership.py"),
        }
        payload.update(overrides)
        res = client.post("/api/public/register", json=payload)
        if res.status_code == 201:
            self.app_ids.append(res.json()["id"])
        return res

    # ─── ล้างข้อมูล ─────────────────────────────────────────────────
    def cleanup(self) -> None:
        db = self.db
        db.rollback()
        # audit: แถวของผู้ดูแลที่สร้างไว้ + แถวของคำขอ (membership_apply บันทึกโดยไม่มี user)
        # + แถวที่อ้างชื่อผู้ใช้ทดสอบใน new_value (login_failed ที่ไม่มี user_id)
        db.execute(
            sa_text(
                "DELETE FROM audit_logs WHERE user_id = ANY(:uids) "
                "OR (entity_type = 'membership_application' AND entity_id = ANY(:eids)) "
                "OR new_value LIKE :pat"
            ),
            {
                "uids": self.user_ids or [-1],
                "eids": [str(i) for i in self.app_ids] or [""],
                "pat": f"%{self.suffix}%",
            },
        )
        if self.app_ids:
            db.execute(
                sa_text("DELETE FROM membership_applications WHERE id = ANY(:ids)"),
                {"ids": self.app_ids},
            )
        # กันคำขอที่ endpoint สร้างแล้วเทสต์ไม่ได้จด id (เช่นเคสที่ assert ล้มก่อน)
        db.execute(
            sa_text("DELETE FROM membership_applications WHERE username LIKE :pat"),
            {"pat": f"memtest.{self.suffix}.%"},
        )
        if self.user_ids:
            db.execute(
                sa_text("DELETE FROM users WHERE id = ANY(:ids)"),
                {"ids": self.user_ids},
            )
        db.execute(
            sa_text("DELETE FROM users WHERE line_user_id LIKE :pat"),
            {"pat": f"memtest.{self.suffix}.%"},
        )
        if self.org_ids:
            db.execute(
                sa_text("DELETE FROM organizations WHERE id = ANY(:ids)"),
                {"ids": self.org_ids},
            )
        db.commit()


@pytest.fixture(autouse=True)
def _isolate_side_effects(monkeypatch):
    """ปิด rate limit และ Google Sheet ระหว่างเทสต์

    /api/public/register จำกัด 5 ครั้ง/ชั่วโมงต่อ IP — ถ้าไม่ปิด เคสท้าย ๆ จะได้ 429
    แทนผลจริง และ append_membership_row จะพยายามต่อ API ภายนอกหากเครื่องนักพัฒนา
    ตั้ง GOOGLE_SHEET_ID ไว้
    """
    monkeypatch.setattr(limiter, "enabled", False, raising=False)
    monkeypatch.setattr(
        google_sheets, "append_membership_row", lambda application, *a, **kw: False
    )


@pytest.fixture
def sandbox():
    try:
        db = SessionLocal()
    except Exception as exc:  # pragma: no cover — ขึ้นกับ environment
        pytest.skip(f"ต่อฐานข้อมูลไม่ได้: {exc!r}")
    try:
        db.execute(sa_text("SELECT 1 FROM membership_applications LIMIT 1"))
    except Exception as exc:  # pragma: no cover — ยังไม่ได้ migrate
        db.rollback()
        db.close()
        pytest.skip(
            f"ยังไม่มีตาราง membership_applications — รัน scripts/migrate_membership.py ({exc!r})"
        )

    box = _Sandbox(db)
    try:
        yield box
    finally:
        try:
            box.cleanup()
        finally:
            db.close()


def _assert_no_secret_fields(payload) -> None:
    """คำขอที่ส่งออกต้องไม่มี hash รหัสผ่าน ไม่ว่าจะเป็น dict เดี่ยวหรือรายการ"""
    rows = payload if isinstance(payload, list) else [payload]
    for row in rows:
        leaked = set(row.keys()).intersection(SENSITIVE_FIELDS)
        assert not leaked, f"ฟิลด์ {sorted(leaked)} หลุดออกจาก API คำขอสมัคร: {row}"


def _login(username: str, password: str = PASSWORD):
    return client.post(
        "/api/auth/login", json={"username": username, "password": password}
    )


# ─── สมัครสมาชิก (สาธารณะ) ────────────────────────────────────────────
def test_register_creates_pending_application_without_account(sandbox):
    """ข้อ 1: สมัครแล้วได้คำขอ pending — ยังไม่มีบัญชีและล็อกอินไม่ได้"""
    org = sandbox.org()
    username = sandbox.username("apply")

    res = sandbox.register(username=username, organization_code=org.code)
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == MEMBERSHIP_PENDING
    assert isinstance(body["id"], int)
    assert body["message"].strip(), "ต้องมีข้อความยืนยันให้ผู้สมัครอ่าน"
    _assert_no_secret_fields(body)

    row = sandbox.fetch_application(body["id"])
    assert row.username == username
    assert row.status == MEMBERSHIP_PENDING
    assert row.organization_id == org.id
    assert row.organization_code == org.code
    assert row.created_user_id is None, "ยังไม่อนุมัติ ห้ามผูกบัญชี"
    assert row.password_hash and row.password_hash != PASSWORD, (
        "ต้องเก็บเฉพาะ hash ห้ามเก็บรหัสผ่านดิบ"
    )

    assert sandbox.find_user(username) is None, "คำขอ pending ห้ามสร้างแถวใน users"
    login = _login(username)
    assert login.status_code != 200, (
        f"ยังไม่ได้รับอนุมัติต้องล็อกอินไม่ได้ แต่ได้ {login.status_code}: {login.text}"
    )


def test_register_ignores_self_assigned_role(sandbox):
    """ข้อ 2: ส่ง role มาเองก็ต้องได้บทบาทสาธารณะเท่านั้น"""
    username = sandbox.username("noadmin")

    res = sandbox.register(username=username, role="owner", requested_role="super_admin")
    assert res.status_code == 201, res.text

    row = sandbox.fetch_application(res.json()["id"])
    assert row.requested_role == PUBLIC_SIGNUP_ROLE, (
        f"ห้ามให้ผู้สมัครกำหนดบทบาทเอง แต่ได้ {row.requested_role}"
    )


def test_duplicate_username_is_rejected(sandbox):
    """ข้อ 3: คำขอค้างชื่อเดิม และชื่อที่มีบัญชีอยู่แล้ว → 409 ข้อความเดียวกัน"""
    username = sandbox.username("dup")

    first = sandbox.register(username=username)
    assert first.status_code == 201, first.text

    again = sandbox.register(username=username)
    assert again.status_code == 409, again.text
    pending_message = again.json()["error"]["message"]

    existing = sandbox.user("it_support")
    taken = sandbox.register(username=existing.line_user_id)
    assert taken.status_code == 409, taken.text
    assert taken.json()["error"]["message"] == pending_message, (
        "ข้อความต้องเหมือนกัน ไม่งั้นใช้แยกได้ว่าชื่อนี้มีบัญชีอยู่จริง"
    )


def test_unknown_organization_code_returns_404(sandbox):
    """ข้อ 3: รหัสหน่วยงานไม่มีจริง → 404 และไม่บันทึกคำขอ"""
    username = sandbox.username("badorg")

    res = sandbox.register(
        username=username, organization_code="MEMTEST-no-such-org-9137"
    )
    assert res.status_code == 404, res.text
    assert res.json()["success"] is False

    sandbox.db.rollback()
    exists = sandbox.db.execute(
        select(MembershipApplication.id).where(MembershipApplication.username == username)
    ).scalar_one_or_none()
    assert exists is None, "คำขอที่ระบุหน่วยงานผิดต้องไม่ถูกบันทึก"


@pytest.mark.parametrize(
    "field, value",
    [
        ("password", "short1"),          # < 8 ตัว
        ("username", "ชื่อไทย"),          # ไม่ตรง pattern ^[a-zA-Z0-9._-]+$
        ("username", "ab"),              # สั้นกว่า 3
        ("full_name", "x"),              # สั้นกว่า 2
    ],
)
def test_invalid_payload_is_422(sandbox, field, value):
    """ฟอร์มไม่ผ่าน validation → 422 VALIDATION_ERROR (ไม่ใช่ 500)"""
    payload = {"username": sandbox.username("invalid"), field: value}
    res = sandbox.register(**payload)
    assert res.status_code == 422, res.text
    assert res.json()["error"]["code"] == "VALIDATION_ERROR", res.text


# ─── รายการคำขอ (ฝั่งผู้ดูแล) ──────────────────────────────────────────
def test_list_requires_review_role(sandbox):
    """ข้อ 4: ไม่มี token → 401, it_support → 403"""
    res = client.get("/api/registrations")
    assert res.status_code == 401, res.text
    assert res.json()["error"]["code"] == "UNAUTHORIZED"

    it_support = sandbox.user("it_support")
    res = client.get("/api/registrations", headers=sandbox.headers(it_support))
    assert res.status_code == 403, res.text
    assert "it_support" not in MEMBERSHIP_REVIEW_ROLES, (
        "ถ้าเปิดสิทธิ์ให้ it_support ต้องแก้เทสต์นี้อย่างตั้งใจ"
    )


def test_admin_school_sees_only_own_organization(sandbox):
    """ข้อ 4+5: admin_school เห็นเฉพาะคำขอของโรงเรียนตัวเอง และไม่มี password_hash"""
    mine = sandbox.org()
    other = sandbox.org()
    my_app = sandbox.application(username=sandbox.username("mine"), org=mine)
    other_app = sandbox.application(username=sandbox.username("other"), org=other)

    school_admin = sandbox.user("admin_school", mine)
    res = client.get(
        "/api/registrations",
        params={"status": MEMBERSHIP_PENDING, "limit": 200},
        headers=sandbox.headers(school_admin),
    )
    assert res.status_code == 200, res.text
    rows = res.json()
    _assert_no_secret_fields(rows)

    ids = {r["id"] for r in rows}
    assert my_app.id in ids, "ต้องเห็นคำขอของโรงเรียนตัวเอง"
    assert other_app.id not in ids, "ห้ามเห็นคำขอของโรงเรียนอื่น"
    assert all(r["status"] == MEMBERSHIP_PENDING for r in rows), "ตัวกรองสถานะไม่ทำงาน"

    # ผู้ดูแลระดับระบบเห็นทั้งสองรายการ
    admin = sandbox.user("admin")
    res = client.get(
        "/api/registrations",
        params={"status": MEMBERSHIP_PENDING, "limit": 200},
        headers=sandbox.headers(admin),
    )
    assert res.status_code == 200, res.text
    all_ids = {r["id"] for r in res.json()}
    assert {my_app.id, other_app.id} <= all_ids


# ─── อนุมัติ / ปฏิเสธ ─────────────────────────────────────────────────
def test_approve_creates_account_with_applicant_password(sandbox):
    """ข้อ 6: อนุมัติ → มีบัญชีจริง และล็อกอินด้วยรหัสที่ผู้สมัครตั้งไว้ได้ทันที"""
    org = sandbox.org()
    admin = sandbox.user("admin")
    username = sandbox.username("approve")

    created = sandbox.register(username=username, organization_code=org.code)
    assert created.status_code == 201, created.text
    application_id = created.json()["id"]

    res = client.post(
        f"/api/registrations/{application_id}/approve",
        json={},
        headers=sandbox.headers(admin),
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["status"] == MEMBERSHIP_APPROVED
    assert body["user"]["username"] == username
    assert body["user"]["role"] == PUBLIC_SIGNUP_ROLE
    assert body["user"]["organization_id"] == org.id
    assert body["user"]["is_active"] is True
    _assert_no_secret_fields(body["user"])

    new_user = sandbox.track_created_user(username)
    row = sandbox.fetch_application(application_id)
    assert row.status == MEMBERSHIP_APPROVED
    assert row.created_user_id == new_user.id
    assert row.reviewed_by == admin.id
    assert row.reviewed_at is not None

    login = _login(username)
    assert login.status_code == 200, (
        f"ผู้สมัครต้องล็อกอินด้วยรหัสเดิมได้หลังอนุมัติ: {login.text}"
    )


def test_approve_twice_conflicts(sandbox):
    """ข้อ 6: คำขอที่ดำเนินการแล้ว อนุมัติซ้ำไม่ได้ (กันสร้างบัญชีซ้ำ)"""
    admin = sandbox.user("admin")
    username = sandbox.username("twice")
    application = sandbox.application(username=username)

    first = client.post(
        f"/api/registrations/{application.id}/approve",
        json={},
        headers=sandbox.headers(admin),
    )
    assert first.status_code == 201, first.text
    sandbox.track_created_user(username)

    second = client.post(
        f"/api/registrations/{application.id}/approve",
        json={},
        headers=sandbox.headers(admin),
    )
    assert second.status_code == 409, second.text


def test_admin_school_cannot_grant_elevated_role(sandbox):
    """ข้อ 6: admin_school ยกบทบาทเกินสิทธิ์ไม่ได้ และคำขอต้องยัง pending"""
    assert "admin" not in SCHOOL_ADMIN_ASSIGNABLE_ROLES, (
        "เทสต์นี้อาศัยว่า admin_school กำหนดบทบาท admin ไม่ได้"
    )
    org = sandbox.org()
    school_admin = sandbox.user("admin_school", org)
    username = sandbox.username("elevate")
    application = sandbox.application(username=username, org=org)

    res = client.post(
        f"/api/registrations/{application.id}/approve",
        json={"role": "admin"},
        headers=sandbox.headers(school_admin),
    )
    assert res.status_code == 403, res.text
    assert sandbox.fetch_application(application.id).status == MEMBERSHIP_PENDING
    assert sandbox.find_user(username) is None, "คำขอที่ถูกปฏิเสธสิทธิ์ห้ามสร้างบัญชี"


def test_admin_school_cannot_touch_other_organization(sandbox):
    """ข้อ 4: คำขอของโรงเรียนอื่น — อนุมัติไม่ได้ (403)"""
    mine = sandbox.org()
    other = sandbox.org()
    school_admin = sandbox.user("admin_school", mine)
    username = sandbox.username("crossorg")
    application = sandbox.application(username=username, org=other)

    res = client.post(
        f"/api/registrations/{application.id}/approve",
        json={},
        headers=sandbox.headers(school_admin),
    )
    assert res.status_code == 403, res.text
    assert sandbox.fetch_application(application.id).status == MEMBERSHIP_PENDING
    assert sandbox.find_user(username) is None


def test_reject_keeps_reason_and_blocks_later_approval(sandbox):
    """ข้อ 6: ปฏิเสธ → เก็บเหตุผล ไม่สร้างบัญชี และอนุมัติทีหลังไม่ได้"""
    admin = sandbox.user("admin")
    username = sandbox.username("reject")
    application = sandbox.application(username=username)
    reason = "ข้อมูลไม่ครบ — เทสต์อัตโนมัติ"

    res = client.post(
        f"/api/registrations/{application.id}/reject",
        json={"reason": reason},
        headers=sandbox.headers(admin),
    )
    assert res.status_code == 200, res.text
    body = res.json()
    assert body["status"] == MEMBERSHIP_REJECTED
    assert body["reject_reason"] == reason
    _assert_no_secret_fields(body)

    row = sandbox.fetch_application(application.id)
    assert row.status == MEMBERSHIP_REJECTED
    assert row.reviewed_by == admin.id
    assert row.created_user_id is None
    assert sandbox.find_user(username) is None, "คำขอที่ถูกปฏิเสธห้ามมีบัญชี"

    late = client.post(
        f"/api/registrations/{application.id}/approve",
        json={},
        headers=sandbox.headers(admin),
    )
    assert late.status_code == 409, late.text


def test_decision_on_missing_application_returns_404(sandbox):
    """คำขอที่ไม่มีอยู่ → 404 ทั้งอนุมัติและปฏิเสธ"""
    admin = sandbox.user("admin")
    missing_id = 2_000_000_000

    for action in ("approve", "reject"):
        res = client.post(
            f"/api/registrations/{missing_id}/{action}",
            json={},
            headers=sandbox.headers(admin),
        )
        assert res.status_code == 404, f"{action}: {res.text}"