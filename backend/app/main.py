"""
Smart Classroom Support — FastAPI Backend
Scope: Device lookup + Ticket CRUD + Workflow status + QR scan log

Run: uvicorn app.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone, timedelta
import base64
import csv
import hashlib
import hmac
import io
import logging
import os
import threading
from typing import Literal, Optional
from decimal import Decimal

from fastapi import Depends, FastAPI, File, Header, HTTPException, Query, Request, UploadFile
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from starlette.exceptions import HTTPException as StarletteHTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import DateTime as SQLDateTime, Numeric as SQLNumeric, bindparam, func, select, text
from sqlalchemy.orm import Session, selectinload

from app.kb_loader import invalidate_kb_cache
# Audit Log (§40) + Preventive Maintenance (§38) — โมเดลที่เพิ่มใหม่
from app import google_sheets, pm_rules
from app.models import (AuditLog, ChatbotKnowledgeEntry, ChatbotPromptSetting,
                        DeviceHealthFlag, LineServiceRating, PMPlan, PMTask)
from app.models import (
    Base,
    Building,
    CustomerSignupInvite,
    Device,
    DeviceType,
    KBArticle,
    KBSuggestion,
    MEMBERSHIP_APPROVED,
    MEMBERSHIP_PENDING,
    MEMBERSHIP_REJECTED,
    MembershipApplication,
    DeletedRecord,
    NotificationLog,
    Organization,
    Priority,
    RepairTicket,
    Room,
    SalesLead,
    SalesRecord,
    ScanLog,
    SelfServiceCase,
    SessionLocal,
    Setting,
    TicketAttachment,
    TicketComment,
    TicketStatus,
    TicketUpdate,
    User,
    init_db,
    get_db,
)


# ---------------------------------------------------------------------------
# Password hashing (PBKDF2 — ไม่ต้องพึ่ง dependency เพิ่ม)
# ---------------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = os.urandom(16).hex()
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000).hex()
    return f"{salt}${digest}"


def verify_password(password: str, stored: Optional[str]) -> bool:
    if not stored or "$" not in stored:
        return False
    salt, digest = stored.split("$", 1)
    check = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), 100_000).hex()
    return check == digest


def bootstrap_local_admin(db: Session) -> None:
    """Create a development login once, without deleting or resetting any data.

    This is intentionally opt-in and refuses production so a deployment can never
    acquire a predictable administrator account from its environment by accident.
    """
    enabled = os.environ.get("BOOTSTRAP_LOCAL_ADMIN", "").lower() in {"1", "true", "yes"}
    if not enabled:
        return
    if os.environ.get("ENVIRONMENT", "development").lower() in {"production", "prod"}:
        raise RuntimeError("BOOTSTRAP_LOCAL_ADMIN must not be enabled in production")
    username = os.environ.get("LOCAL_ADMIN_USERNAME", "admin").strip()
    password = os.environ.get("LOCAL_ADMIN_PASSWORD", "").strip()
    if not username or not password:
        raise RuntimeError("LOCAL_ADMIN_USERNAME and LOCAL_ADMIN_PASSWORD are required when bootstrapping")
    if len(password) < 8:
        raise RuntimeError("LOCAL_ADMIN_PASSWORD must be at least 8 characters")
    if db.execute(select(User).where(User.line_user_id == username)).scalar_one_or_none():
        return
    db.add(User(
        line_user_id=username,
        line_display_name="Local development administrator",
        role="super_admin",
        is_active=True,
        password_hash=hash_password(password),
    ))
    db.commit()
    print(f"Created local development administrator: {username}")


# ---------------------------------------------------------------------------
# Token (JWT-like) — HMAC-SHA256 ลงนาม, stdlib เท่านั้น
# (base64 / hmac / hashlib import ไว้ด้านบนของไฟล์แล้ว — ไม่ import ซ้ำ)
# ---------------------------------------------------------------------------
import json
import time

# เปลี่ยน secret นี้ใน production (env JWT_SECRET)
JWT_SECRET = os.environ.get("JWT_SECRET", "smart-classroom-dev-secret-change-me")
JWT_TTL_SECONDS = 60 * 60 * 12  # 12 ชั่วโมง

# Never let a deployment accidentally use the repository's development key.
# Local development remains convenient, while hosted environments must supply
# an unpredictable value through their secret manager.
# Shared credential for automation-to-backend calls.  Unlike a user JWT this
# is only for the n8n service, never for browsers or public webhooks.
N8N_SHARED_SECRET = os.environ.get("N8N_SHARED_SECRET", "")

if os.environ.get("ENVIRONMENT", "").lower() in {"production", "prod"}:
    if not JWT_SECRET.strip() or JWT_SECRET == "smart-classroom-dev-secret-change-me":
        raise RuntimeError("JWT_SECRET must be configured in production")
    if not N8N_SHARED_SECRET.strip() or N8N_SHARED_SECRET == "<N8N_SHARED_SECRET>":
        raise RuntimeError("N8N_SHARED_SECRET must be configured in production")


def require_n8n_secret(x_n8n_secret: Optional[str] = Header(None)) -> None:
    """Reject automation calls unless a configured n8n secret matches."""
    if not N8N_SHARED_SECRET:
        raise HTTPException(status_code=503, detail="n8n integration is not configured")
    if not x_n8n_secret or not hmac.compare_digest(N8N_SHARED_SECRET, x_n8n_secret):
        raise HTTPException(status_code=401, detail="unauthorized")


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    pad = "=" * (-len(s) % 4)
    return base64.urlsafe_b64decode(s + pad)


def create_token(user: User) -> str:
    """สร้าง token 12 ชม. เก็บ user_id + role + org"""
    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}).encode())
    payload = _b64url_encode(json.dumps({
        "sub": user.id,
        "role": user.role,
        "org": user.organization_id,
        "exp": int(time.time()) + JWT_TTL_SECONDS,
        "iat": int(time.time()),
    }).encode())
    signing_input = f"{header}.{payload}"
    sig = _b64url_encode(hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest())
    return f"{signing_input}.{sig}"


def decode_token(token: str) -> Optional[dict]:
    """ถอด token — คืน payload ถ้าถูกต้อง+ยังไม่หมดอายุ, คืน None ถ้าไม่ valid"""
    try:
        header, payload, sig = token.split(".")
        signing_input = f"{header}.{payload}"
        expected = _b64url_encode(hmac.new(JWT_SECRET.encode(), signing_input.encode(), hashlib.sha256).digest())
        if not hmac.compare_digest(expected, sig):
            return None
        data = json.loads(_b64url_decode(payload))
        if data.get("exp", 0) < time.time():
            return None
        return data
    except Exception:
        return None


def get_current_user(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> User:
    """FastAPI dependency — ตรวจ token จาก Authorization: Bearer xxx"""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="กรุณาเข้าสู่ระบบก่อน (ไม่พบ token)")
    token = authorization.split(" ", 1)[1].strip()
    data = decode_token(token)
    if not data:
        raise HTTPException(status_code=401, detail="token หมดอายุหรือไม่ถูกต้อง — กรุณาเข้าสู่ระบบใหม่")
    user = db.get(User, data.get("sub"))
    if not user or not user.is_active:
        raise HTTPException(status_code=401, detail="บัญชีไม่ถูกต้องหรือถูกปิดใช้งาน")
    if user.role in RETIRED_ROLES:
        # บทบาท ครู/นักเรียน ถูกยกเลิกแล้ว — บล็อก token ที่ออกไปก่อนหน้านี้ด้วย
        raise HTTPException(
            status_code=403,
            detail="บทบาทนี้ถูกยกเลิกแล้ว — ผู้แจ้งซ่อมใช้หน้าแจ้งซ่อม/สแกน QR ได้โดยไม่ต้องมีบัญชี",
        )
    return user


def require_roles(*roles: str):
    """สร้าง dependency ที่เช็คว่า user มีบทบาทในรายการที่ให้"""
    def checker(user: User = Depends(get_current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail="คุณไม่มีสิทธิ์ทำรายการนี้")
        return user
    return checker


# ─── Scope ตามบทบาท (RBAC แยกตามโรงเรียน) ──────────────────────────────────
# ผลลัพธ์: None = เห็นทุกโรงเรียน (global)  |  set[int] = เห็นเฉพาะ org ใน set
# admin_school / it_support(มีสังกัด) → เห็นเฉพาะรรตัวเอง
# (บัญชีเก่าที่ยังติดบทบาท teacher/student ก็ถูกจำกัดเป็นรรตัวเองเช่นกัน)
# super_admin / admin / it_support(ไม่มีสังกัด, สร้างโดย superadmin) → เห็นทุกรร
# ─── บทบาทที่กำหนดให้ผู้ใช้ได้ ─────────────────────────────────────────────
# teacher / student ถูกยกเลิก: ผู้แจ้งซ่อมใช้หน้าสาธารณะ/สแกน QR โดยไม่ต้องมีบัญชี
# ค่าเดิมยังอยู่ในฐานข้อมูล จึงต้องอ่านได้ แต่ห้ามกำหนดให้ผู้ใช้ใหม่
ASSIGNABLE_ROLES: tuple[str, ...] = ("owner", "super_admin", "admin", "admin_school", "it_support")
RETIRED_ROLES: tuple[str, ...] = ("teacher", "student")

#: บทบาทที่ admin_school กำหนดให้ผู้ใช้ในโรงเรียนตัวเองได้ (เดิมมี ครู/นักเรียน)
SCHOOL_ADMIN_ASSIGNABLE_ROLES: tuple[str, ...] = ("it_support",)

#: บทบาทที่แก้งาน PM ที่ปิดแล้ว (done/skipped) ย้อนหลังได้
#: super_admin ต้องจัดการ/แก้ไขได้ทั้งหมด — it_support ทำได้แค่งานที่ยังเปิดอยู่
PM_TASK_OVERRIDE_ROLES: tuple[str, ...] = ("owner", "super_admin", "admin")


def validate_assignable_role(role: Optional[str]) -> None:
    """โยน 400 ถ้าบทบาทถูกยกเลิกไปแล้วหรือไม่มีอยู่จริง"""
    if role is None:
        return
    if role in RETIRED_ROLES:
        raise HTTPException(
            status_code=400,
            detail="บทบาท ครู/นักเรียน ถูกยกเลิกแล้ว — ผู้แจ้งซ่อมใช้หน้าแจ้งซ่อมได้โดยไม่ต้องมีบัญชี",
        )
    if role not in ASSIGNABLE_ROLES:
        raise HTTPException(status_code=400, detail=f"บทบาทไม่ถูกต้อง: {role}")


def visible_org_ids(user: User) -> Optional[set[int]]:
    """คืนชุด organization_id ที่ user นี้เห็นได้; None = เห็นทุกโรงเรียน"""
    if user.role in ("owner", "super_admin", "admin"):
        return None
    if user.role == "it_support":
        # it_support ที่ไม่มีสังกัด = สร้างโดย owner/admin → เห็นทุกรร
        # it_support ที่มีสังกัด = สร้างโดย admin_school → เห็นเฉพาะรรนั้น
        return None if not user.organization_id else {user.organization_id}
    # admin_school + บัญชีเก่าบทบาท teacher/student → เห็นเฉพาะรรตัวเอง
    return {user.organization_id} if user.organization_id else set()


def check_org_access(user: User, org_id: Optional[int], raise_http: bool = True) -> bool:
    """ตรวจว่า user เห็น org_id ได้หรือไม่ (None org = อนุญาตถ้า global scope)"""
    scope = visible_org_ids(user)
    if scope is None:
        return True  # global
    if org_id is None:
        ok = True
    else:
        ok = org_id in scope
    if not ok and raise_http:
        raise HTTPException(status_code=403, detail="คุณไม่มีสิทธิ์เข้าถึงข้อมูลของโรงเรียนนี้")
    return ok


def check_ticket_access(db: Session, user: User, ticket) -> None:
    """ตรวจว่า user เห็น ticket นี้ได้หรือไม่ (ผ่าน device.organization_id) — 403 ถ้าไม่อยู่ใน scope"""
    scope = visible_org_ids(user)
    if scope is None:
        return
    if not ticket.device_id:
        return  # device ไม่อยู่แล้ว (deleted) — ปล่อยผ่าน ไม่ block
    org_id = db.execute(
        select(Device.organization_id).where(Device.device_id == ticket.device_id)
    ).scalar_one_or_none()
    if org_id is None:
        return
    if org_id not in scope:
        raise HTTPException(status_code=403, detail="คุณไม่มีสิทธิ์เข้าถึงข้อมูลของโรงเรียนนี้")



def get_current_user_optional(
    authorization: Optional[str] = Header(None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """เหมือน get_current_user แต่คืน None ถ้าไม่มี token (สำหรับ endpoint สาธารณะที่ filter ตามบทบาท)"""
    if not authorization or not authorization.startswith("Bearer "):
        return None
    token = authorization.split(" ", 1)[1].strip()
    data = decode_token(token)
    if not data:
        return None
    user = db.get(User, data.get("sub"))
    if not user or not user.is_active:
        return None
    if user.role in RETIRED_ROLES:
        # บัญชีบทบาทเก่า = ถือว่าไม่ได้ล็อกอิน (endpoint สาธารณะยังใช้งานได้ปกติ)
        return None
    return user

# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class DeviceInfo(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    device_id: str
    device_type: str
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    status: str
    qr_token: Optional[str] = None
    qr_url: Optional[str] = None
    room_code: Optional[str] = None
    room_name: Optional[str] = None
    building: Optional[str] = None
    floor: Optional[str] = None
    gps_lat: Optional[float] = None
    gps_lng: Optional[float] = None
    organization_code: str
    organization_name: str
    organization_id: Optional[int] = None
    # วันที่จัดซื้อ — ใช้คู่กับ warranty_until ในทะเบียนทรัพย์สิน/PM Rule 3 (§38)
    purchase_date: Optional[datetime] = None
    warranty_until: Optional[datetime] = None
    warranty_details: Optional[str] = None
    notes: Optional[str] = None
    # กันแจ้งซ้ำ: หน้าที่เปิดจากการสแกน QR ใช้ response นี้เป็นข้อมูลเครื่อง จึงต้อง
    # รู้ตั้งแต่ตอนเปิดหน้าว่ามีใบงานค้างอยู่แล้ว ไม่ใช่ไปรู้ตอนกดส่งฟอร์มแล้วโดน 409
    # ค่าเริ่มต้น False/None เพื่อให้ endpoint อื่นที่คืน DeviceInfo เดิมไม่พัง
    has_open_ticket: bool = False
    open_ticket: Optional[dict] = None


class TicketCreate(BaseModel):
    device_id: str
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=3000)
    reporter_name: Optional[str] = None
    reporter_email: Optional[str] = None
    reporter_phone: Optional[str] = None
    reporter_type: Optional[str] = None
    priority: str = "normal"
    channel: Optional[str] = "qr"
    symptom_code: Optional[str] = None
    ai_session_id: Optional[str] = None
    attachments: Optional[list[str]] = None
    scan_gps_lat: Optional[float] = Field(None, ge=-90, le=90)
    scan_gps_lng: Optional[float] = Field(None, ge=-180, le=180)
    scan_timestamp: Optional[datetime] = None
    scan_user_agent: Optional[str] = None


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: str
    device_id: str
    title: str
    # หมวดหมู่อุปกรณ์ (map จาก device_type) — ใช้จัดกลุ่ม/กรองงานซ่อมเป็นหมวด
    device_category: Optional[str] = None
    # ชื่ออุปกรณ์แบบอ่านรู้เรื่อง (ประเภท · ยี่ห้อรุ่น · ห้อง) ไม่ใช่รหัสเปล่า ๆ
    device_label: Optional[str] = None
    # ประเภทอุปกรณ์ (join จากตาราง devices) — หน้าเว็บใช้แสดงและใช้เป็นตัวกรอง
    device_type: Optional[str] = None
    # โรงเรียนเจ้าของอุปกรณ์ - ใช้จัดกลุ่ม/กรองงานเป็นหมวดโรงเรียน
    # และทำให้เลข Ticket ที่ขึ้นต้นด้วยรหัสโรงเรียนอ่านคู่กันได้
    organization_id: Optional[int] = None
    organization_code: Optional[str] = None
    organization_name: Optional[str] = None
    description: Optional[str] = None
    reporter_name: Optional[str] = None
    reporter_email: Optional[str] = None
    reporter_phone: Optional[str] = None
    reporter_type: Optional[str] = None
    priority: str
    status: str
    assigned_to: Optional[str] = None
    channel: Optional[str] = None
    symptom_code: Optional[str] = None
    ai_category: Optional[str] = None
    attachments: Optional[list[str]] = None
    root_cause: Optional[str] = None
    solution: Optional[str] = None
    sla_due_at: Optional[datetime] = None
    sla_met: Optional[bool] = None
    escalation_level: int = 0
    resolved_at: Optional[datetime] = None
    rating: Optional[int] = None
    feedback: Optional[str] = None
    scan_gps_lat: Optional[float] = None
    scan_gps_lng: Optional[float] = None
    scan_timestamp: Optional[datetime] = None
    resolution_notes: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    closed_at: Optional[datetime] = None
    # ข้อมูลอุปกรณ์ + ประวัติ (สำหรับหน้า public ติดตามสถานะ)
    device_info: Optional[dict] = None
    history: Optional[list] = None


class TicketUpdateOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    from_status: Optional[str] = None
    to_status: Optional[str] = None
    note: Optional[str] = None
    author_name: Optional[str] = None
    author_role: Optional[str] = None
    created_at: datetime


class DeviceCreate(BaseModel):
    device_id: Optional[str] = None
    organization_id: int
    room_id: Optional[int] = None
    room_code: Optional[str] = None
    device_type: str = "other"
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    status: str = "active"
    notes: Optional[str] = None
    purchase_date: Optional[datetime] = None
    warranty_until: Optional[datetime] = None
    warranty_details: Optional[str] = Field(None, max_length=500)


class DeviceUpdate(BaseModel):
    device_type: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    serial_number: Optional[str] = None
    firmware_version: Optional[str] = None
    status: Optional[str] = None
    room_id: Optional[int] = None
    room_code: Optional[str] = None
    notes: Optional[str] = None
    purchase_date: Optional[datetime] = None
    warranty_until: Optional[datetime] = None
    warranty_details: Optional[str] = Field(None, max_length=500)


class PublicReportIn(BaseModel):
    """แจ้งซ่อมสาธารณะ (คนไม่มีบัญชี) — resolve/สร้าง room+device เองถ้าไม่รู้ device code."""
    organization_code: Optional[str] = None  # ถ้าไม่ระบุ ใช้ TEST1 / org แรก
    device_id: Optional[str] = None          # ถ้ารู้ device code แล้ว (เลือกจาก dropdown)
    room_text: Optional[str] = None          # ห้อง/สถานที่อิสระ — resolve/สร้าง Room ถ้ายังไม่มี
    device_type: Optional[str] = None        # ประเภทอุปกรณ์ (เลือกจาก dropdown)
    device_detail: Optional[str] = None      # ชื่อ/รายละเอียดอุปกรณ์อิสระ (ถ้าไม่เลือก device)
    title: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = Field(None, max_length=3000)
    reporter_name: str = Field(..., min_length=1, max_length=128)
    reporter_phone: str = Field(..., min_length=1, max_length=32)
    reporter_type: Optional[str] = None
    priority: str = "normal"
    attachments: Optional[list[str]] = None
    line_report_token: Optional[str] = Field(None, min_length=20, max_length=128)
    scan_gps_lat: Optional[float] = Field(None, ge=-90, le=90)
    scan_gps_lng: Optional[float] = Field(None, ge=-180, le=180)
    scan_timestamp: Optional[datetime] = None
    scan_user_agent: Optional[str] = Field(None, max_length=512)


class PublicTicketNoteIn(BaseModel):
    """ผู้แจ้ง (ไม่มีบัญชี) เพิ่มอาการ/ข้อมูลเข้า Ticket ที่ยังไม่ปิด — ไม่สร้างใบใหม่"""

    note: str = Field(..., min_length=3, max_length=2000)
    reporter_name: str = Field(..., min_length=1, max_length=128)
    reporter_phone: Optional[str] = Field(None, max_length=32)
    attachments: Optional[list[str]] = None


class PublicDeviceInfo(BaseModel):
    """ข้อมูลอุปกรณ์เท่าที่ปลอดภัยจะส่งออก endpoint สาธารณะ (ไม่ต้อง auth)

    แยกจาก DeviceInfo โดยเจตนา: DeviceInfo มี qr_token/qr_url (ใช้สร้างลิงก์สแกนของ
    ทุกห้องได้), serial_number, firmware_version, warranty_until, notes และ gps_lat/lng
    ซึ่งเป็นข้อมูลทรัพย์สินภายใน โค้ดเดิมไม่ได้ใส่ค่าให้ฟิลด์เหล่านั้น แต่ key ยังติดไปกับ
    response ทุกครั้ง และถ้าวันหน้ามีใครเผลอใส่ค่าก็รั่วทันที — โมเดลนี้จึงไม่มีฟิลด์
    เหล่านั้นเลย ทำให้ปลอดภัยด้วยโครงสร้าง ไม่ใช่ด้วยวินัยของผู้แก้โค้ด
    """

    model_config = ConfigDict(from_attributes=True)

    device_id: str
    device_type: str
    # หมวดหมู่ + ชื่อที่คนอ่านรู้เรื่อง — ผู้แจ้งเลือกจาก "จอแสดงภาพ · ห้อง ป.1/2"
    # ได้โดยไม่ต้องจำรหัสอย่าง TEST1-B1-R101-DISP-01
    device_category: Optional[str] = None
    device_label: Optional[str] = None
    brand: Optional[str] = None
    model: Optional[str] = None
    status: str
    room_code: Optional[str] = None
    room_name: Optional[str] = None
    building: Optional[str] = None
    floor: Optional[str] = None
    organization_code: str
    organization_name: str
    organization_id: Optional[int] = None


class DeviceCategoryOut(BaseModel):
    """หมวดหมู่อุปกรณ์ 1 หมวด สำหรับจัดกลุ่ม dropdown/ตัวกรองของหน้าเว็บ

    device_count = จำนวนอุปกรณ์ของหน่วยงานนั้นที่อยู่ในหมวดนี้ (0 = หน้าเว็บซ่อนได้)
    """

    category: str
    device_types: list[str]
    device_count: int = 0


class PublicOptionsOut(BaseModel):
    """ตัวเลือกของหน้าแจ้งซ่อมสาธารณะ

    requires_organization=True หมายถึงยังไม่ได้ระบุรหัสหน่วยงาน จึงไม่ส่งรายการ
    อุปกรณ์ออกไป (เดิม endpoint นี้คืนอุปกรณ์ของทุกโรงเรียนถึง 500 รายการโดยไม่ต้อง
    ล็อกอิน) — ผู้แจ้งต้องระบุ organization_code หรือสแกน QR ที่ตัวอุปกรณ์
    """

    organization_code: Optional[str] = None
    organization_name: Optional[str] = None
    requires_organization: bool = False
    device_types: list[str]
    device_categories: list[DeviceCategoryOut] = []
    devices: list[PublicDeviceInfo]


class OrgCreate(BaseModel):
    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=2, max_length=255)
    short_name: Optional[str] = None
    timezone: str = "Asia/Bangkok"


class UserOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    line_user_id: str
    line_display_name: Optional[str] = None
    line_picture_url: Optional[str] = None
    line_email: Optional[str] = None
    organization_id: Optional[int] = None
    role: str
    is_active: bool
    created_at: datetime


class UserCreate(BaseModel):
    line_user_id: str = Field(..., min_length=2, max_length=64)
    line_display_name: Optional[str] = None
    line_picture_url: Optional[str] = None
    line_email: Optional[str] = None
    organization_id: Optional[int] = None
    role: str = "it_support"
    is_active: bool = True
    password: Optional[str] = Field(None, min_length=4, max_length=128)


class UserUpdate(BaseModel):
    # ชื่อผู้ใช้สำหรับเข้าสู่ระบบ (เก็บในคอลัมน์ line_user_id) — แยกจากอีเมล
    username: Optional[str] = Field(None, min_length=2, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    line_display_name: Optional[str] = None
    line_picture_url: Optional[str] = None
    line_email: Optional[str] = None
    organization_id: Optional[int] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=4, max_length=128)


class MembershipApplyIn(BaseModel):
    """ฟอร์มสมัครสมาชิกจากหน้าสาธารณะ (ไม่ต้อง login)"""
    username: str = Field(..., min_length=3, max_length=64, pattern=r"^[a-zA-Z0-9._-]+$")
    password: str = Field(..., min_length=8, max_length=128)
    full_name: str = Field(..., min_length=2, max_length=255)
    email: Optional[str] = Field(None, max_length=255)
    phone: Optional[str] = Field(None, max_length=32)
    organization_code: Optional[str] = Field(None, max_length=64)
    note: Optional[str] = Field(None, max_length=1000)


class MembershipDecisionIn(BaseModel):
    """ผู้ดูแลอนุมัติ/ปฏิเสธคำขอ — ระบุบทบาท/หน่วยงานทับค่าที่ผู้สมัครกรอกได้"""
    role: Optional[str] = None
    organization_id: Optional[int] = None
    reason: Optional[str] = Field(None, max_length=500)


class MembershipApplicationOut(BaseModel):
    """ข้อมูลคำขอที่ส่งออก — ตั้งใจไม่มี password_hash"""
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    full_name: str
    email: Optional[str] = None
    phone: Optional[str] = None
    organization_id: Optional[int] = None
    organization_code: Optional[str] = None
    requested_role: str
    status: str
    note: Optional[str] = None
    reject_reason: Optional[str] = None
    created_at: Optional[datetime] = None
    reviewed_at: Optional[datetime] = None
    sheet_synced_at: Optional[datetime] = None


class LoginRequest(BaseModel):
    username: str = Field(..., min_length=2, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class StatusUpdateRequest(BaseModel):
    status: str
    note: Optional[str] = None
    author_name: Optional[str] = None
    author_role: Optional[str] = "it_staff"
    force: bool = False


# ---------------------------------------------------------------------------
# Status transition rules — ย้ายไป app/ticket_state.py (source of truth เดียว)
# ---------------------------------------------------------------------------

from app.ticket_state import STATUS_TRANSITIONS, apply_transition


def write_audit(
    db: Session,
    *,
    action: str,
    user: Optional[User] = None,
    entity_type: Optional[str] = None,
    entity_id: Optional[str] = None,
    old_value=None,
    new_value=None,
    request: Optional[Request] = None,
) -> None:
    """บันทึก Audit Log (Blueprint §40) — ไม่ commit เอง ให้ caller commit พร้อม transaction เดิม

    เก็บเฉพาะเหตุการณ์สำคัญตาม §40: Login, เปลี่ยนสิทธิ์, สร้าง/แก้/ลบ Asset,
    Assign งาน, เปลี่ยน Status, ปิดงาน, แก้ KB และ System Settings
    """
    def _dump(v):
        if v is None:
            return None
        if isinstance(v, str):
            return v
        try:
            return json.dumps(v, ensure_ascii=False, default=str)
        except (TypeError, ValueError):
            return str(v)

    ip = None
    ua = None
    if request is not None:
        ip = request.headers.get("x-forwarded-for") or (
            request.client.host if request.client else None
        )
        if ip:
            ip = ip.split(",")[0].strip()[:64]
        ua = (request.headers.get("user-agent") or "")[:255] or None

    db.add(AuditLog(
        user_id=getattr(user, "id", None),
        # โมเดล User ของระบบนี้ไม่มี full_name/username — ใช้ชื่อที่แสดงจาก LINE เป็นหลัก
        user_name=getattr(user, "line_display_name", None) or getattr(user, "line_user_id", None),
        user_role=getattr(user, "role", None),
        action=action,
        entity_type=entity_type,
        entity_id=str(entity_id) if entity_id is not None else None,
        old_value=_dump(old_value),
        new_value=_dump(new_value),
        ip_address=ip,
        user_agent=ua,
    ))


def _org_code_token(code: Optional[str], org_id: Optional[int]) -> str:
    """รหัสโรงเรียนแบบปลอดภัยสำหรับใส่ใน device_id / ticket_id (A–Z0–9 ยาวไม่เกิน 8)

    เดิม generate_device_id ใช้ fallback "SCH" เมื่อโรงเรียนยังไม่กรอก code ทำให้
    หลายโรงเรียนใช้ prefix เดียวกัน ลำดับอุปกรณ์ปนกันข้ามโรงเรียน ที่นี่ fallback
    เป็น ORG<id> ซึ่งไม่ซ้ำข้ามโรงเรียนแน่นอน
    """
    import re as _re
    token = _re.sub(r"[^A-Za-z0-9]", "", (code or "")).upper()[:8]
    if token:
        return token
    return f"ORG{org_id}" if org_id is not None else "SCH"


#: ชุดอักขระของ ISO 7064 MOD 37,36 — 0-9 แล้วต่อด้วย A-Z
_CHECK_ALPHABET = "0123456789ABCDEFGHIJKLMNOPQRSTUVWXYZ"

#: คำนำหน้าเลข Ticket ทุกใบ — ตัวชี้ว่าสตริงที่กรอกมา "ตั้งใจจะเป็นเลข Ticket"
#: รหัสอุปกรณ์ : TEST1-B1-R101-DISP-01  (ขีดล้วน ยาว มีรหัสห้อง/ประเภท)
#: เลข Ticket  : TK.TEST1.26.0001-Q     (ขึ้นต้น TK. คั่นจุด สั้น ปิดท้ายตัวตรวจสอบ)
TICKET_NO_PREFIX = "TK"


def _mod37_36_check_char(payload: str) -> str:
    """ตัวตรวจสอบท้ายเลข Ticket (ISO 7064 MOD 37,36)

    จับได้ทั้งพิมพ์ผิดหนึ่งตัวและสลับอักขระที่อยู่ติดกัน ทำให้เลขที่กรอกเพี้ยน
    ไม่ไปตรงกับ Ticket ใบอื่น (หรือของโรงเรียนอื่น) โดยบังเอิญ
    อักขระคั่น (. - _ /) ถูกข้ามในการคำนวณ ค่าจึงไม่ขึ้นกับรูปแบบตัวคั่น
    """
    p = 36
    for ch in (payload or "").upper():
        value = _CHECK_ALPHABET.find(ch)
        if value < 0:          # ตัวคั่น — ไม่นับเข้าสูตร
            continue
        p = ((p + value) % 36 or 36) * 2 % 37
    return _CHECK_ALPHABET[(37 - p) % 36]


def ticket_no_of(school_token: str, year: int, seq: int, width: int = 4) -> str:
    """ประกอบเลข Ticket: TK.<รหัสโรงเรียน>.<ปี 2 หลัก>.<ลำดับ>-<ตัวตรวจสอบ>

    ยาวไม่เกิน 32 ตัวอักษรตามคอลัมน์ repair_tickets.ticket_id
    (TK. + รหัสโรงเรียน ≤8 + ปี 2 + ลำดับ ≤6 + ตัวตรวจสอบ = 22 ตัวอย่างมากสุด)
    """
    body = f"{TICKET_NO_PREFIX}.{school_token}.{year % 100:02d}.{seq:0{width}d}"
    return f"{body}-{_mod37_36_check_char(body)}"


#: ตัวอย่างเลข Ticket ที่ตัวตรวจสอบตรงจริง — ใช้ในข้อความแจ้งเตือน/placeholder
TICKET_NO_EXAMPLE = ticket_no_of("SCHM01", 2026, 1)


def _lock_generated_id_prefix(db: Session, prefix: str) -> None:
    """Serialize MAX()+1 allocation per prefix when using PostgreSQL.

    The transaction-scoped advisory lock is released automatically on commit or
    rollback. SQLite-backed unit tests keep their existing behavior.
    """
    if db.get_bind().dialect.name == "postgresql":
        db.execute(
            text("SELECT pg_advisory_xact_lock(hashtext(:lock_key)::bigint)"),
            {"lock_key": f"smart-classroom:id:{prefix}"},
        )


def generate_ticket_id(db: Session, organization_id: Optional[int] = None) -> str:
    """สร้างเลข Ticket — แยกลำดับตามโรงเรียนต่อปี + มีตัวตรวจสอบกันกรอกผิด

    รูปแบบ: TK.<รหัสโรงเรียน>.<ปี 2 หลัก>.<ลำดับ 4 หลัก>-<ตัวตรวจสอบ>
            เช่น TK.SCHM01.26.0001-Q

    ตั้งใจให้หน้าตาไม่เหมือนรหัสอุปกรณ์ (TEST1-B1-R101-DISP-01) เพราะเดิมทั้งสอง
    อย่างเป็นสตริงขีดคั่นคล้ายกัน ผู้แจ้งจึงเอารหัสอุปกรณ์ไปกรอกช่องติดตาม Ticket
    แล้วได้แต่ "ไม่พบข้อมูล" โดยไม่รู้ว่าผิดช่อง

    ยัง unique ทั้งตาราง repair_tickets เพราะ prefix มีรหัสโรงเรียนอยู่ในตัว
    แต่ละโรงเรียนจึงเริ่มนับ 0001 ใหม่ของตัวเองได้โดยไม่ชนกัน

    ถ้าไม่ทราบโรงเรียน (organization_id เป็น None) ใช้ token "ALL" กับลำดับ 6 หลัก

    Ticket เดิม (TK-YYYYMM-XXXX, SC-YYYY-NNNNNN, SC-<รร>-YYYY-NNNN) ยังค้นหา/
    เปิดดูได้ตามปกติ เพราะ lookup เทียบค่า ticket_id ตรงตัว ไม่ผูกกับ prefix
    """
    now = datetime.now(timezone.utc)
    if organization_id is not None:
        org = db.get(Organization, organization_id)
        token = _org_code_token(org.code if org else None, organization_id)
        width = 4
    else:
        token = "ALL"
        width = 6
    prefix = f"{TICKET_NO_PREFIX}.{token}.{now.year % 100:02d}."
    # เทียบ prefix ด้วย LEFT(...) ไม่ใช่ LIKE เพื่อไม่ให้จุด/อักขระพิเศษในรหัสโรงเรียน
    # กลายเป็น wildcard และใช้ MAX(ลำดับ)+1 เพื่อกันเลขซ้ำหลังลบ Ticket กลางลำดับ
    # ส่วนท้ายเป็น <ลำดับ>-<ตัวตรวจสอบ> จึงตัดเอาเฉพาะหน้าขีดมาคิดลำดับ
    _lock_generated_id_prefix(db, prefix)
    row = db.execute(
        text(
            "SELECT MAX(CAST(SPLIT_PART("
            "  SUBSTRING(ticket_id FROM CHAR_LENGTH(:prefix) + 1), '-', 1) AS INTEGER)) "
            "FROM repair_tickets "
            "WHERE LEFT(ticket_id, CHAR_LENGTH(:prefix)) = :prefix "
            "AND SUBSTRING(ticket_id FROM CHAR_LENGTH(:prefix) + 1) ~ '^[0-9]+-[0-9A-Z]$'"
        ),
        {"prefix": prefix},
    ).scalar_one()
    nxt = (row or 0) + 1
    return ticket_no_of(token, now.year, nxt, width)


def _ticket_no_candidates(raw: str) -> tuple[list[str], Optional[tuple[str, str]]]:
    """เลขที่ผู้ใช้พิมพ์/สแกนมา -> รายการค่าที่ควรลองค้นในฐานข้อมูล

    ยืดหยุ่นเรื่องตัวคั่นและตัวพิมพ์ (tk-schm01-26-0001-q หรือ TKSCHM01260001Q
    ก็หาเจอ) แต่ไม่ยืดหยุ่นเรื่องความถูกต้องเลย: ถ้าตัวตรวจสอบตัวท้ายที่กรอกมา
    ไม่ตรงกับตัวเลขข้างหน้า จะไม่ส่งค่าใดออกไปค้นฐานข้อมูลเลย เพราะเลขที่พิมพ์
    เพี้ยนไปหนึ่งตัวอาจเป็นเลขจริงของใบอื่น (หรือของโรงเรียนอื่น) พอดี แล้วผู้แจ้ง
    จะเห็นใบงานที่ไม่ใช่ของตัวเอง

    ด้วยเหตุผลเดียวกัน ระบบจะไม่ "เติม" ตัวตรวจสอบให้เมื่อผู้ใช้ไม่ได้กรอกมา
    (การเติมจะเปลี่ยนเลขที่พิมพ์เพี้ยนให้กลายเป็นเลขที่ถูกต้องของใบอื่น) แต่ยัง
    ค้นแบบตรงตัวให้ เผื่อเป็นเลขรูปแบบเก่าที่ไม่มีตัวตรวจสอบ

    เวลาไม่มีตัวคั่น การแบ่ง <รหัสโรงเรียน>/<ปี>/<ลำดับ> กำกวม เพราะรหัสโรงเรียน
    มีตัวเลขได้ (TEST1) — TKTEST1260001V แบ่งเป็น TEST1/26/0001 หรือ TEST12/60/001
    ก็เข้ารูปแบบทั้งคู่ จึงไล่ทุกการแบ่งแล้วเชื่อเฉพาะการแบ่งที่ตัวตรวจสอบตรง
    ถ้ามีตัวคั่นครบก็เชื่อตัวคั่นอย่างเดียว ไม่ต้องเดาการแบ่งอื่น

    คืน (candidates, problem) โดย problem เป็น None หรือ (kind, ค่าที่กรอกมา):
      "check_mismatch" = มีตัวตรวจสอบมาแต่ไม่ตรง (candidates ว่างเสมอ)
      "missing_check"  = ไม่ได้กรอกตัวตรวจสอบ (ค้นตรงตัวได้ แต่ไม่เติมให้)
      "unverified"     = ไม่มีตัวคั่น และไม่มีการแบ่งใดที่ตัวตรวจสอบตรง
    """
    import re as _re

    typed = (raw or "").strip()
    if not typed:
        return [], None
    compact = _re.sub(r"\s+", "", typed).upper()
    candidates = [typed]
    if compact not in candidates:
        candidates.append(compact)
    if not compact.startswith(TICKET_NO_PREFIX):
        return candidates, None

    # เลขรูปแบบเก่า TK-YYYYMM-NNNN ไม่มีตัวตรวจสอบ ห้ามเอาไปเดาเป็นรูปแบบใหม่
    # ไม่อย่างนั้นจะถูกตีว่า "กรอกผิด" ทั้งที่เป็น Ticket เดิมที่ยังเปิดดูได้
    if _re.fullmatch(r"TK[.\-_/]?\d{6}[.\-_/]?\d{4}", compact):
        return candidates, None

    parts = [p for p in _re.split(r"[.\-_/]+", compact[len(TICKET_NO_PREFIX):]) if p]
    if not parts:
        return candidates, None

    def _valid(token: str, yy: str, seq: str, check: Optional[str]) -> bool:
        return bool(
            _re.fullmatch(r"[A-Z0-9]{1,12}", token)
            and _re.fullmatch(r"\d{2}", yy)
            and _re.fullmatch(r"\d{3,6}", seq)
            and (check is None or _re.fullmatch(r"[0-9A-Z]", check))
        )

    def _verify(layout: tuple) -> tuple[str, Optional[str]]:
        """คืน (เลขรูปแบบมาตรฐานของการแบ่งนี้, ปัญหาที่พบ) — None = ตัวตรวจสอบตรง"""
        token, yy, seq, check = layout
        body = f"{TICKET_NO_PREFIX}.{token}.{yy}.{seq}"
        expected = _mod37_36_check_char(body)
        canonical = f"{body}-{expected}"
        if check is None:
            return canonical, "missing_check"
        return canonical, None if check == expected else "check_mismatch"

    # มีตัวคั่นครบ = รู้แน่ว่าผู้ใช้แบ่งช่วงไว้อย่างไร จึงตัดสินจากการแบ่งนั้นอย่างเดียว
    # ไม่ต้องเดาการแบ่งอื่น (ยิ่งเดามาก เลขที่เพี้ยนยิ่งมีโอกาสไปตรงกับใบของคนอื่น)
    if len(parts) in (3, 4):
        layout = (parts[0], parts[1], parts[2], parts[3] if len(parts) == 4 else None)
        if _valid(*layout):
            canonical, kind = _verify(layout)
            if kind == "check_mismatch":
                # พิสูจน์แล้วว่าเลขเพี้ยน — ไม่ส่ง candidate ใดออกไปค้น DB เลย
                return [], (kind, compact)
            if kind == "missing_check":
                # ตรวจไม่ได้ว่าเพี้ยนหรือไม่ → ค้นตรงตัวเท่านั้น ไม่เติมตัวตรวจสอบให้
                return candidates, (kind, compact)
            if canonical not in candidates:
                candidates.insert(0, canonical)
            return candidates, None

    # ตัวคั่นไม่ครบ/ไม่มีเลย — ไล่ทุกการแบ่ง โดยเรียงจากที่น่าจะเป็นที่สุด:
    # มีตัวตรวจสอบท้ายก่อน และลำดับกว้าง 4 หลัก (ค่ามาตรฐานของเลขรายโรงเรียน) ก่อน
    layouts: list[tuple] = []
    flat = "".join(parts)
    for tail_is_check in (True, False):
        if tail_is_check:
            if len(flat) < 2 or not _re.fullmatch(r"[0-9A-Z]", flat[-1]):
                continue
            core, check = flat[:-1], flat[-1]
        else:
            core, check = flat, None
        for seq_len in (4, 6, 5, 3):
            if len(core) < seq_len + 3:      # ต้องเหลือปี 2 หลัก + รหัสโรงเรียน >= 1
                continue
            layout = (
                core[: -seq_len - 2],
                core[-seq_len - 2 : -seq_len],
                core[-seq_len:],
                check,
            )
            if _valid(*layout) and layout not in layouts:
                layouts.append(layout)

    if not layouts:
        # ไม่เข้ารูปแบบใหม่เลย (เช่นเลขรูปแบบเก่าแบบอื่น) — ค้นตรงตัวตามปกติ
        return candidates, None

    verified: list[str] = []
    for layout in layouts:
        canonical, kind = _verify(layout)
        if kind is None and canonical not in verified:
            verified.append(canonical)
    if verified:
        # ตัวตรวจสอบตรงแล้ว ค่าที่กรอกมาจึงปลอดภัยพอจะใช้ค้นเผื่อ ticket_id รูปแบบเดิม
        return verified + [c for c in candidates if c not in verified], None
    # ไม่มีการแบ่งใดที่ตัวตรวจสอบตรง — ค้นตรงตัวได้ (เผื่อเลขเก่า) แต่ไม่เดาเติมตัวท้าย
    return candidates, ("unverified", compact)


def find_ticket_by_no(db: Session, raw: str) -> "RepairTicket":
    """ค้น Ticket จากเลขที่ผู้ใช้กรอก — 404 พร้อมข้อความที่บอกได้ว่าผิดอย่างไร

    เดิมทุกเส้นทางเทียบ ticket_id ตรงตัวแล้วตอบ "ไม่พบหมายเลข Ticket นี้" เหมือนกันหมด
    ผู้แจ้งที่เอารหัสอุปกรณ์มากรอกผิดช่องจึงไม่รู้ว่าต้องแก้อะไร
    """
    candidates, problem = _ticket_no_candidates(raw)
    for candidate in candidates:
        found = db.execute(
            select(RepairTicket).where(RepairTicket.ticket_id == candidate)
        ).scalar_one_or_none()
        if found:
            return found

    if problem:
        kind, value = problem
        if kind == "missing_check":
            raise HTTPException(
                status_code=404,
                detail=(
                    f"เลข Ticket '{value}' ยังไม่ครบ — ต้องมีตัวตรวจสอบตัวท้ายต่อจากขีดด้วย "
                    f"เช่น {TICKET_NO_EXAMPLE} กรุณากรอกให้ครบตามใบแจ้ง/ข้อความยืนยัน"
                ),
            )
        raise HTTPException(
            status_code=404,
            detail=(
                f"เลข Ticket '{value}' ไม่ผ่านการตรวจสอบ — ตัวตรวจสอบตัวท้ายไม่ตรงกับ"
                "ตัวเลขข้างหน้า (พิมพ์ผิดหรือสลับตำแหน่งไปหนึ่งตัว) "
                "กรุณาตรวจทานจากใบแจ้ง/ข้อความยืนยันอีกครั้ง"
            ),
        )

    # ดูเหมือนรหัสอุปกรณ์ (มีขีดหลายช่วง ไม่ขึ้นต้น TK) -> บอกตรง ๆ ว่าคนละช่อง
    looks_like_device = (
        not (raw or "").strip().upper().startswith(TICKET_NO_PREFIX)
        and (raw or "").count("-") >= 2
    )
    if looks_like_device:
        raise HTTPException(
            status_code=404,
            detail=(
                "ค่าที่กรอกดูเหมือน 'รหัสอุปกรณ์' บนสติกเกอร์ ไม่ใช่เลข Ticket — "
                f"เลข Ticket ขึ้นต้นด้วย {TICKET_NO_PREFIX}. เช่น {TICKET_NO_EXAMPLE}"
            ),
        )
    raise HTTPException(
        status_code=404,
        detail=f"ไม่พบหมายเลข Ticket นี้ (รูปแบบที่ถูกต้อง เช่น {TICKET_NO_EXAMPLE})",
    )

# ---------------------------------------------------------------------------
# SLA — นับเวลาทำการ 08:00–16:30 จันทร์–ศุกร์ (TOR 4.5)
# ---------------------------------------------------------------------------

BUSINESS_START = (8, 0)     # 08:00
BUSINESS_END = (16, 30)     # 16:30

# ระดับความเร่งด่วน → (เวลารับงาน, เวลาปิดงาน) นาทีทำงาน
SLA_TARGETS = {
    "critical": (15, 120),
    "high": (30, 480),
    "normal": (120, 1440),
    "low": (480, 4320),
}

def _is_business_hour(dt: datetime) -> bool:
    if dt.weekday() >= 5:  # เสาร์/อาทิตย์
        return False
    mins = dt.hour * 60 + dt.minute
    return BUSINESS_START[0] * 60 + BUSINESS_START[1] <= mins < BUSINESS_END[0] * 60 + BUSINESS_END[1]

def _next_business_start(dt: datetime) -> datetime:
    """เวลาเริ่มทำการ "ถัดไป" ที่ >= dt เสมอ (ห้ามคืนเวลาย้อนหลัง)

    เดิมฟังก์ชันนี้คืน 08:00 ของ "วันเดียวกัน" ทำให้เคสแจ้งซ่อมหลังเลิกงาน
    (เช่น พุธ 18:00) ได้ sla_due_at ย้อนหลังไปเป็นพุธ 10:00 → เกินกำหนดทันที
    """
    candidate = dt.replace(hour=BUSINESS_START[0], minute=BUSINESS_START[1], second=0, microsecond=0)
    if candidate <= dt:
        # dt อยู่ในเวลาทำการหรือเลยเวลาเลิกงานของวันนี้ไปแล้ว → ขยับไปเช้าวันถัดไป
        candidate += timedelta(days=1)
    while candidate.weekday() >= 5:  # ข้ามเสาร์/อาทิตย์
        candidate += timedelta(days=1)
    return candidate

def add_business_minutes(start: datetime, minutes: int) -> datetime:
    """บวกเวลาทำการ (นาที) เข้ากับ start — ข้ามนอกเวลา/วันหยุด

    _next_business_start เลื่อนไปข้างหน้าเองแล้ว จึงไม่ต้องบวก timedelta(days=1)
    ก่อนเรียก (ของเดิมทำให้ข้ามวันทำการทิ้งไป 1 วัน)
    """
    cur = start
    remaining = minutes
    while remaining > 0:
        if not _is_business_hour(cur):
            cur = _next_business_start(cur)
            continue
        # นาทีที่เหลือของวันทำงานนี้
        end_today = cur.replace(hour=BUSINESS_END[0], minute=BUSINESS_END[1], second=0, microsecond=0)
        avail = int((end_today - cur).total_seconds() // 60)
        if avail <= 0:
            cur = _next_business_start(cur)
            continue
        if remaining <= avail:
            return cur + timedelta(minutes=remaining)
        remaining -= avail
        cur = _next_business_start(cur)
    return cur

def calc_sla_due(created_at: datetime, priority: str) -> datetime:
    """คำนวณ sla_due_at (เวลาปิดงาน) จาก priority"""
    _, close_min = SLA_TARGETS.get(priority, SLA_TARGETS["normal"])
    return add_business_minutes(created_at, close_min)


# ---------------------------------------------------------------------------
# Device ID — รูปแบบ SCH01-B1-R101-DISP-01 (TOR 3.5)
# ---------------------------------------------------------------------------

DEVICE_TYPE_CODES = {
    "Interactive Display": "DISP",
    "Computer AIO": "COMP",
    "Computer Notebook": "COMP",
    "Computer Tablet": "COMP",
    "Computer Desktop": "COMP",
    "Router": "RTR",
    "Access Point": "AP",
    "Switch": "SW",
    "Speaker": "SPK",
    "Camera": "CAM",
    "Visualizer": "CAM",
    "Microphone": "MIC",
    "UPS": "UPS",
    "Printer": "PRN",
    "Projector": "PJT",
    "Software (Picaro)": "SW",
    "Software (Phonics Hero)": "SW",
    "Other": "DEV",
}

def _device_type_code(device_type: Optional[str]) -> str:
    return DEVICE_TYPE_CODES.get(device_type or "", "DEV")

def _building_code(raw: Optional[str], floor: Optional[str]) -> str:
    """สร้างรหัสอาคารสั้นแบบปลอดภัยสำหรับ device_id จากชื่อเต็ม เช่น
    'อาคาร 1' → 'B1', 'อาคาร B ชั้น 3' → 'BB3', 'ตึกวิทย์' → 'TWIT'
    fallback: floor ('2'→'F2'), สุดท้าย 'B0'
    """
    import re as _re
    if raw:
        s = _re.sub(r"[^\u0E00-\u0E7Fa-zA-Z0-9]", "", str(raw)).strip()
        if not s:
            return "B0"
        # ดึงตัวเลขตัวแรก (ถ้ามี) → ใช้ B + เลข
        num = _re.search(r"[0-9]+", str(raw))
        if num:
            return f"B{num.group()[:2]}"
        # ไม่มีเลข → ใช้ floor หรือตัวย่อของชื่อ
        if floor:
            fnum = _re.search(r"[0-9]+", str(floor))
            if fnum:
                return f"B{fnum.group()[:2]}"
        # เอาเฉพาะตัวอักษรละตินตัวแรกๆ เป็นตัวย่อ
        latin = _re.findall(r"[a-zA-Z]", str(raw))
        if latin:
            return "B" + "".join(latin[:2]).upper()
        # ไทยล้วน → เอา 2 ตัวแรกพยางค์ แล้ว B
        return "B" + s[:2].upper()
    if floor:
        fnum = _re.search(r"[0-9]+", str(floor))
        if fnum:
            return f"B{fnum.group()[:2]}"
    return "B0"


def generate_device_id(db: Session, org: Organization, room: Optional[Room], device_type: Optional[str]) -> str:
    """SCH01-B1-R101-DISP-01 — รร-อาคาร-ห้อง-ประเภท-ลำดับ (01–99)"""
    org_code = _org_code_token(org.code, org.id)
    # building code ย่อ (sanitize ให้ปลอด URL) + room code
    building = _building_code(room.building if room else None, room.floor if room else None) if room else "B0"
    room_code = (room.code or "R000") if room else "R000"
    type_code = _device_type_code(device_type)
    prefix = f"{org_code}-{building}-{room_code}-{type_code}-"
    # ใช้ MAX(ลำดับ)+1 ไม่ใช่ COUNT(*)+1 — ถ้าลบอุปกรณ์กลางลำดับไป COUNT จะคืนเลขที่
    # มีอยู่แล้วและชน unique constraint ของ device_id
    # เทียบ prefix ด้วย LEFT(...) แทน LIKE/regex เพื่อไม่ให้อักขระพิเศษในรหัสห้อง
    # (_ % . ( ) ) ถูกตีความเป็น wildcard หรือ regex
    _lock_generated_id_prefix(db, prefix)
    row = db.execute(
        text("""
            SELECT MAX(CAST(SUBSTRING(device_id FROM CHAR_LENGTH(:prefix) + 1) AS INTEGER))
            FROM devices
            WHERE LEFT(device_id, CHAR_LENGTH(:prefix)) = :prefix
              AND SUBSTRING(device_id FROM CHAR_LENGTH(:prefix) + 1) ~ '^[0-9]+$'
        """),
        {"prefix": prefix},
    ).scalar_one()
    return f"{prefix}{(row or 0) + 1:02d}"


def _normalize_manual_device_id(db: Session, org: Organization, raw: str) -> str:
    """จัดรูป/ตรวจ device_id ที่ผู้ใช้กรอกเอง ให้ผูกกับรหัสโรงเรียนเสมอ

    เดิมช่อง "รหัสอุปกรณ์" ใน POST /api/devices รับค่าอะไรก็ได้ สองโรงเรียนจึง
    ตั้งรหัสคล้ายกันได้ (เช่น R101-DISP-01 ทั้งคู่) แล้วคนแจ้งซ่อมที่พิมพ์รหัสเอง
    หรือค้นรหัสในระบบ อาจไปเปิด Ticket ให้เครื่องของโรงเรียนอื่น

    กติกาใหม่ — รหัสต้องขึ้นต้นด้วย <รหัสโรงเรียน>- เสมอ (token ตัวเดียวกับที่
    generate_device_id / generate_ticket_id ใช้):
      · กรอกมาโดยไม่มี prefix       → เติม prefix ของโรงเรียนที่เลือกให้อัตโนมัติ
      · กรอก prefix ของโรงเรียนอื่น → ปฏิเสธ 400 พร้อมบอกรหัสที่ถูกต้อง
      · อักขระนอก A-Z 0-9 - _       → ปฏิเสธ (กัน path/QR เพี้ยน)
    """
    import re as _re

    token = _org_code_token(org.code, org.id)
    cleaned = _re.sub(r"\s+", "", raw or "").upper().strip("-")
    if not cleaned:
        raise HTTPException(status_code=400, detail="รหัสอุปกรณ์ว่าง")
    if not _re.fullmatch(r"[A-Z0-9][A-Z0-9_-]*", cleaned):
        raise HTTPException(
            status_code=400,
            detail="รหัสอุปกรณ์ใช้ได้เฉพาะตัวอักษร A-Z ตัวเลข 0-9 และ - _ เท่านั้น",
        )

    if cleaned != token and not cleaned.startswith(f"{token}-"):
        # ส่วนหน้าเป็นรหัสของโรงเรียนอื่นหรือไม่ — ถ้าใช่ ห้ามเติม prefix ทับเงียบ ๆ
        head = cleaned.split("-", 1)[0]
        for other_id, other_code in db.execute(
            select(Organization.id, Organization.code).where(Organization.id != org.id)
        ).all():
            if _org_code_token(other_code, other_id) == head:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"รหัส '{cleaned}' ขึ้นต้นด้วยรหัสของอีกโรงเรียนหนึ่ง ({head}) "
                        f"อุปกรณ์ของ {org.name} ต้องขึ้นต้นด้วย {token}-"
                    ),
                )
        cleaned = f"{token}-{cleaned}"
    elif cleaned == token:
        raise HTTPException(
            status_code=400,
            detail=f"รหัสอุปกรณ์ต้องมีส่วนต่อจากรหัสโรงเรียน เช่น {token}-B1-R101-DISP-01",
        )

    # คอลัมน์ devices.device_id เป็น String(64) — ตัดก่อนลง DB จะ error ไม่สื่อความ
    if len(cleaned) > 64:
        raise HTTPException(status_code=400, detail="รหัสอุปกรณ์ยาวเกิน 64 ตัวอักษร")
    return cleaned


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Seed KB 30 หัวข้อ (ถ้าตารางว่าง) + สร้าง PM plans ตั้งต้น
    db = SessionLocal()
    try:
        bootstrap_local_admin(db)
        seeded = seed_kb_articles(db)
        # Seed แผน PM ตั้งต้น 4 แผน (§38) — ถ้าตาราง pm_plans ยังว่าง
        if db.execute(select(func.count()).select_from(PMPlan)).scalar_one() == 0:
            db.add_all([
                PMPlan(
                    name="บำรุงรักษาจอ Interactive รายไตรมาส",
                    device_type="Interactive Display", interval_days=90, is_active=True,
                    checklist=json.dumps([
                        {"order": 1, "item": "ทำความสะอาดหน้าจอและกรอบ", "type": "boolean"},
                        {"order": 2, "item": "ทดสอบระบบสัมผัสทุกมุมจอ", "type": "boolean"},
                        {"order": 3, "item": "ตรวจสอบสายสัญญาณและสายไฟ", "type": "boolean"},
                        {"order": 4, "item": "ทดสอบเสียงลำโพง", "type": "boolean"},
                        {"order": 5, "item": "อุณหภูมิเครื่อง (°C)", "type": "number"},
                    ], ensure_ascii=False),
                ),
                PMPlan(
                    name="บำรุงรักษาคอมพิวเตอร์ราย 6 เดือน",
                    device_type="Computer Desktop", interval_days=180, is_active=True,
                    checklist=json.dumps([
                        {"order": 1, "item": "ทำความสะอาดพัดลมและช่องระบายอากาศ", "type": "boolean"},
                        {"order": 2, "item": "อัปเดตระบบปฏิบัติการ", "type": "boolean"},
                        {"order": 3, "item": "ตรวจสอบพื้นที่ว่างดิสก์", "type": "boolean"},
                        {"order": 4, "item": "ตรวจสอบแบตเตอรี่ CMOS", "type": "boolean"},
                    ], ensure_ascii=False),
                ),
                PMPlan(
                    name="บำรุงรักษา Router/AP ราย 6 เดือน",
                    device_type="Router", interval_days=180, is_active=True,
                    checklist=json.dumps([
                        {"order": 1, "item": "ตรวจสัญญาณ Wi-Fi แต่ละจุด", "type": "boolean"},
                        {"order": 2, "item": "อัปเดต Firmware", "type": "boolean"},
                        {"order": 3, "item": "ทำความสะอาดฝุ่น", "type": "boolean"},
                        {"order": 4, "item": "ตรวจสอบสาย LAN และ PoE", "type": "boolean"},
                    ], ensure_ascii=False),
                ),
                PMPlan(
                    name="บำรุงรักษาระบบเสียงรายไตรมาส",
                    device_type="Speaker", interval_days=90, is_active=True,
                    checklist=json.dumps([
                        {"order": 1, "item": "ทดสอบเสียงลำโพงทุกตัว", "type": "boolean"},
                        {"order": 2, "item": "ตรวจสายและขั้วต่อ", "type": "boolean"},
                        {"order": 3, "item": "ตรวจไมโครโฟนไร้สาย", "type": "boolean"},
                    ], ensure_ascii=False),
                ),
            ])
        # Seed ค่า Settings เริ่มต้น (TOR 5.11) — ถ้ายังไม่มี key นั้น
        default_settings = {
            "sla_hours": {"critical": 2, "high": 8, "normal": 24, "low": 72},
            "working_hours": {"start": "08:00", "end": "16:30", "days": [1, 2, 3, 4, 5]},
            "auto_close_days": 3,
            "ai_confidence_threshold": 0.75,
        }
        for key, value in default_settings.items():
            exists = db.execute(select(Setting).where(Setting.key == key)).scalar_one_or_none()
            if not exists:
                db.add(Setting(key=key, value=json.dumps(value, ensure_ascii=False)))
        db.commit()
    finally:
        db.close()
    yield


app = FastAPI(
    title="Smart Classroom Support API",
    version="0.1.0",
    lifespan=lifespan,
)

# ─── Rate limiting (ป้องกัน brute-force login / spam) ───
limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter

# ─── Error contract §35: {success, data, error: {code, message}} ──────────────
# ยังคง key "detail" รูปแบบเดิมไว้ในทุก response เพราะฝั่งที่เรียกใช้อ่านจาก detail จริง:
#   - frontend/src/api/client.ts → parsed?.detail และ detail.code
#   - backend/test_line_create_ticket.py → res.json()["detail"]
#   - n8n workflow (ข้อความแจ้งกลับเข้า LINE)
# ถ้าตัด detail ออก ข้อความ error บน UI และใน LINE จะกลายเป็น "HTTP 4xx" ทั้งระบบ
_ERROR_CODE_BY_STATUS = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    503: "SERVICE_UNAVAILABLE",
}


def _error_envelope(status_code: int, detail, fallback_message: Optional[str] = None) -> dict:
    """แปลง detail ของ exception เป็น envelope §35 โดยไม่ทิ้ง detail เดิม

    - detail เป็น dict (เช่น DUPLICATE_OPEN_TICKET) → ใช้ code/message ที่มีอยู่
      และคงฟิลด์เสริม (existing_ticket_no, existing_status) ไว้ใน error
    - detail เป็น str → code มาจาก status code, message คือข้อความไทยเดิม
    - detail เป็น list (pydantic validation) → ใช้ fallback_message เป็น message
    """
    default_code = _ERROR_CODE_BY_STATUS.get(status_code, f"HTTP_{status_code}")
    if isinstance(detail, dict):
        error = dict(detail)
        error.setdefault("code", default_code)
        error.setdefault("message", fallback_message or default_code)
    elif isinstance(detail, str) and detail.strip():
        error = {"code": default_code, "message": detail}
    else:
        error = {"code": default_code, "message": fallback_message or default_code}
    return {"success": False, "data": None, "error": error, "detail": detail}


@app.exception_handler(StarletteHTTPException)
async def _http_exception_handler(request: Request, exc: StarletteHTTPException):
    """ครอบทั้ง fastapi.HTTPException (เป็น subclass) และ 404/405 ของ router"""
    body = _error_envelope(exc.status_code, exc.detail)
    return JSONResponse(
        status_code=exc.status_code,
        content=jsonable_encoder(body),
        headers=getattr(exc, "headers", None),
    )


@app.exception_handler(RequestValidationError)
async def _validation_exception_handler(request: Request, exc: RequestValidationError):
    """422 ของ pydantic — detail ยังเป็น list ของ errors เหมือน default ของ FastAPI"""
    body = _error_envelope(
        422,
        exc.errors(),
        "ข้อมูลที่ส่งมาไม่ถูกต้อง กรุณาตรวจสอบฟิลด์ที่จำเป็น",
    )
    return JSONResponse(status_code=422, content=jsonable_encoder(body))


@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(
        status_code=429,
        content=_error_envelope(429, "มีการร้องขอมากเกินไป กรุณารอสักครู่ก่อนลองใหม่"),
    )

_cors_origins = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5173",
).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─── Logging (ข้อ 7: logging เพียงพอ + ไม่ leak sensitive data) ───────────────
# (logging import ไว้ด้านบนของไฟล์แล้ว)
import time as _time

logging.basicConfig(
    level=os.environ.get("LOG_LEVEL", "INFO").upper(),
    format="%(asctime)s %(levelname)s [%(name)s] %(message)s",
)
logger = logging.getLogger("smart_classroom")

# path ที่ไม่ต้อง log (health check / docs — ลด noise)
_SILENT_PATHS = ("/health", "/api/health", "/docs", "/openapi.json", "/favicon.ico")


@app.middleware("http")
async def _access_log_middleware(request: Request, call_next):
    """log request แบบไม่เก็บ body/query ที่อาจมีข้อมูลอ่อนไหว (ไม่ log Authorization/รหัส)"""
    started = _time.perf_counter()
    try:
        response = await call_next(request)
    except Exception:
        # log stack trace ฝั่ง server เท่านั้น (ไม่ส่งกลับ client)
        logger.exception("UNHANDLED %s %s", request.method, request.url.path)
        raise
    elapsed_ms = (_time.perf_counter() - started) * 1000
    if request.url.path not in _SILENT_PATHS:
        # log เฉพาะ path (ไม่ใส่ query string — กัน leak token/ข้อมูลส่วนตัว)
        logger.info(
            "%s %s -> %s (%.0f ms) ip=%s",
            request.method, request.url.path, response.status_code, elapsed_ms,
            request.client.host if request.client else "-",
        )
    if response.status_code >= 500:
        logger.error("SERVER ERROR %s %s -> %s", request.method, request.url.path, response.status_code)
    return response


@app.exception_handler(Exception)
async def _unhandled_exception_handler(request: Request, exc: Exception):
    """คืนข้อความ generic — ไม่ leak stack trace / schema / path ให้ client"""
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return JSONResponse(
        status_code=500,
        content=_error_envelope(500, "เกิดข้อผิดพลาดภายในระบบ กรุณาลองใหม่หรือแจ้งผู้ดูแล"),
    )



# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health")
def health():
    return {"status": "ok", "service": "smart-classroom-support-api"}


# ---------------------------------------------------------------------------
# Device lookup (used by QR scan landing page)
# ---------------------------------------------------------------------------


@app.get("/api/devices/{device_id}", response_model=DeviceInfo)
def get_device(device_id: str, db: Session = Depends(get_db)):
    row = (
        db.execute(
            select(Device, Room, Organization)
            .outerjoin(Room, Room.id == Device.room_id)
            .join(Organization, Organization.id == Device.organization_id)
            .where(Device.device_id == device_id)
        )
    ).first()
    if not row:
        raise HTTPException(status_code=404, detail="Device not found")

    device, room, org = row
    return DeviceInfo(
        # กันแจ้งซ้ำ: ปลายทางของการสแกน QR/กรอกรหัสเอง ต้องรู้สถานะงานค้างทันที
        **open_ticket_fields(db, device.device_id),
        device_id=device.device_id,
        device_type=device.device_type,
        brand=device.brand,
        model=device.model,
        serial_number=device.serial_number,
        qr_token=device.qr_token,
        qr_url=(f"/scan?t={device.qr_token}" if device.qr_token else f"/scan?device={device.device_id}"),
        firmware_version=device.firmware_version,
        status=device.status,
        room_code=room.code if room else None,
        room_name=room.name if room else None,
        building=room.building if room else None,
        floor=room.floor if room else None,
        gps_lat=float(room.gps_lat) if room and room.gps_lat is not None else None,
        gps_lng=float(room.gps_lng) if room and room.gps_lng is not None else None,
        organization_code=org.code,
        organization_name=org.name,
        organization_id=device.organization_id,
        purchase_date=device.purchase_date,
        warranty_until=device.warranty_until,
        warranty_details=device.warranty_details,
        notes=device.notes,
    )


# ---------------------------------------------------------------------------
# Ticket CRUD
# ---------------------------------------------------------------------------


# สถานะที่ถือว่า "งานยังไม่ปิด" — ใช้ร่วมกันทุกเส้นทางที่กันแจ้งซ้ำ เดิมตกหล่น
# waiting_parts/waiting_user ทำให้อุปกรณ์ที่รออะไหล่ยังถูกแจ้งซ้ำได้
OPEN_TICKET_STATUSES = (
    "new", "assigned", "in_progress", "pending", "waiting_parts", "waiting_user",
)


def find_open_ticket(db: Session, device_id: str) -> Optional[RepairTicket]:
    """ticket ที่ยังไม่ปิดของอุปกรณ์นี้ (ล่าสุดก่อน) — None ถ้าไม่มี"""
    return db.execute(
        select(RepairTicket)
        .where(
            RepairTicket.device_id == device_id,
            RepairTicket.status.in_(OPEN_TICKET_STATUSES),
        )
        .order_by(RepairTicket.created_at.desc(), RepairTicket.ticket_id.desc())
    ).scalars().first()


# ป้ายสถานะภาษาไทยสำหรับทุกหน้าที่เปิดสาธารณะ — เดิมแต่ละที่มีตารางของตัวเองและ
# ตกหล่น waiting_parts/waiting_user ทำให้ผู้แจ้งเห็นรหัสภาษาอังกฤษดิบ
PUBLIC_STATUS_LABELS = {
    "new": "รอรับเรื่อง",
    "assigned": "มอบหมายแล้ว",
    "in_progress": "กำลังดำเนินการ",
    "pending": "รออะไหล่/รอภายนอก",
    "waiting_parts": "รออะไหล่",
    "waiting_user": "รอผู้ใช้ยืนยัน",
    "resolved": "ซ่อมเสร็จ รอผู้แจ้งยืนยัน",
    "closed": "ปิดงาน",
    "cancelled": "ยกเลิก",
}


def _ticket_device(t: RepairTicket):
    """Device ของ ticket ถ้า ORM โหลดมาให้ (getattr กันกรณีไม่มี relationship)"""
    return getattr(t, "device", None)


def compose_device_label(
    device_type: Optional[str],
    brand: Optional[str],
    model: Optional[str],
    room_label: Optional[str] = None,
) -> str:
    """ประกอบชื่ออุปกรณ์จากค่าดิบ: ประเภท · ยี่ห้อรุ่น · ห้อง

    แยกจาก device_display_label เพื่อให้ endpoint ที่ join Room มาแล้ว (เช่น
    /api/public/options) ใช้รูปแบบชื่อเดียวกันได้ โดยไม่ต้องให้ ORM lazy-load
    room ทีละแถว (N+1)
    """
    parts = [device_type or "อุปกรณ์"]
    brand_model = " ".join(p for p in (brand, model) if p)
    if brand_model:
        parts.append(brand_model)
    if room_label:
        parts.append(f"ห้อง {room_label}")
    return " · ".join(parts)


def device_display_label(device) -> str:
    """ชื่ออุปกรณ์ที่คนอ่านรู้เรื่อง: ประเภท · ยี่ห้อรุ่น · ห้อง

    ผู้แจ้งและเจ้าหน้าที่จำรหัสอย่าง TEST1-B1-R101-DISP-01 ไม่ได้ ทุกที่ที่เคยโชว์
    รหัสเปล่า ๆ จึงใช้ค่านี้คู่กับรหัสแทน
    """
    if device is None:
        return "-"
    room = getattr(device, "room", None)
    room_label = (room.name or room.code) if room is not None else None
    return compose_device_label(
        device.device_type, device.brand, device.model, room_label
    )


def open_ticket_summary(t: RepairTicket) -> dict:
    """สรุป ticket ที่ยังไม่ปิด สำหรับแสดงให้ผู้แจ้ง (ไม่มีข้อมูลส่วนบุคคลของผู้แจ้งเดิม)"""
    device = _ticket_device(t)
    device_type = device.device_type if device else None
    return {
        "ticket_no": t.ticket_id,
        "status": t.status,
        "status_label": PUBLIC_STATUS_LABELS.get(t.status, t.status),
        "title": t.title,
        "priority": t.priority,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "sla_due_at": t.sla_due_at.isoformat() if t.sla_due_at else None,
        "device_id": t.device_id,
        "device_type": device_type,
        "device_category": device_category_of(device_type),
        "device_label": device_display_label(device),
        # ผู้แจ้งเพิ่มอาการ/ข้อมูลเข้าใบเดิมได้ ไม่ต้องเปิดใบใหม่
        "can_add_note": True,
    }


def open_ticket_fields(db: Session, device_id: str) -> dict:
    """คู่คีย์ has_open_ticket/open_ticket สำหรับ response ที่ต้องบอกว่าอุปกรณ์มีงานค้าง

    รวมไว้ที่เดียวเพื่อไม่ให้แต่ละ endpoint ยิง query ซ้ำหรือใส่ชื่อคีย์ไม่ตรงกัน
    """
    open_ticket = find_open_ticket(db, device_id)
    return {
        "has_open_ticket": open_ticket is not None,
        "open_ticket": open_ticket_summary(open_ticket) if open_ticket else None,
    }


def open_tickets_by_device(db: Session, device_ids: list[str]) -> dict[str, dict]:
    """สรุปใบงานที่ยังไม่ปิดของหลายอุปกรณ์ในคราวเดียว -> {device_id: summary}

    รายการผลค้นหา/รายการอุปกรณ์ต้องบอกได้ว่าเครื่องไหนมีงานค้าง ถ้าเรียก
    find_open_ticket ทีละแถวจะยิง query เท่าจำนวนแถว จึงดึงรอบเดียว แล้วเรียง
    เก่า→ใหม่ ให้ใบล่าสุดของแต่ละอุปกรณ์ทับใบก่อนหน้า (ตรงกับ find_open_ticket
    ที่คืนใบล่าสุด)
    """
    ids = [d for d in dict.fromkeys(device_ids) if d]
    if not ids:
        return {}
    rows = db.execute(
        select(RepairTicket)
        .where(
            RepairTicket.device_id.in_(ids),
            RepairTicket.status.in_(OPEN_TICKET_STATUSES),
        )
        .order_by(RepairTicket.created_at.asc())
    ).scalars().all()
    return {t.device_id: open_ticket_summary(t) for t in rows}


def raise_duplicate_open_ticket(t: RepairTicket) -> None:
    """409 DUPLICATE_OPEN_TICKET พร้อมข้อมูลงานเดิมให้หน้าเว็บแสดงได้ครบ"""
    raise HTTPException(
        status_code=409,
        detail={
            "code": "DUPLICATE_OPEN_TICKET",
            "message": (
                f"อุปกรณ์นี้แจ้งซ่อมไว้แล้ว เลขที่ {t.ticket_id} "
                f"(สถานะ: {PUBLIC_STATUS_LABELS.get(t.status, t.status)}) — "
                "เพิ่มอาการหรือข้อมูลเข้าใบเดิมได้ ไม่ต้องแจ้งซ้ำ"
            ),
            "existing_status_label": PUBLIC_STATUS_LABELS.get(t.status, t.status),
            "existing_device_id": t.device_id,
            "existing_device_label": device_display_label(_ticket_device(t)),
            "can_add_note": True,
            "open_ticket": open_ticket_summary(t),
            "existing_ticket_no": t.ticket_id,
            "existing_status": t.status,
            "existing_title": t.title,
            "existing_created_at": t.created_at.isoformat() if t.created_at else None,
        },
    )


@app.post("/api/tickets", response_model=TicketOut, status_code=201)
@limiter.limit("10/minute")
def create_ticket(
    payload: TicketCreate,
    request: Request,
    db: Session = Depends(get_db),
):
    if (payload.scan_gps_lat is None) != (payload.scan_gps_lng is None):
        raise HTTPException(status_code=422, detail="ต้องส่งพิกัดละติจูดและลองจิจูดพร้อมกัน")
    device = db.execute(
        select(Device).where(Device.device_id == payload.device_id)
    ).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")

    priority = (
        payload.priority
        if payload.priority in ("low", "normal", "high", "critical")
        else "normal"
    )

    # ─── กันแจ้งซ้ำ (TOR 1.5.2 / 5.7): อุปกรณ์มี ticket ค้าง → 409 DUPLICATE_OPEN_TICKET
    open_ticket = find_open_ticket(db, payload.device_id)
    if open_ticket:
        raise_duplicate_open_ticket(open_ticket)

    now = datetime.now(timezone.utc)
    sla_due = calc_sla_due(now, priority)

    ticket = RepairTicket(
        ticket_id=generate_ticket_id(db, device.organization_id),
        organization_id=device.organization_id,
        device_id=payload.device_id,
        title=payload.title,
        description=payload.description,
        reporter_name=payload.reporter_name,
        reporter_email=payload.reporter_email,
        reporter_phone=payload.reporter_phone,
        reporter_type=payload.reporter_type,
        priority=priority,
        status=TicketStatus.NEW,
        channel=payload.channel or "qr",
        symptom_code=payload.symptom_code,
        ai_session_id=payload.ai_session_id,
        attachments=json.dumps(payload.attachments or [], ensure_ascii=False),
        sla_due_at=sla_due,
        scan_gps_lat=payload.scan_gps_lat,
        scan_gps_lng=payload.scan_gps_lng,
        scan_timestamp=payload.scan_timestamp or now,
    )
    db.add(ticket)

    scan_log = ScanLog(
        device_id=payload.device_id,
        scan_gps_lat=payload.scan_gps_lat,
        scan_gps_lng=payload.scan_gps_lng,
        scan_timestamp=ticket.scan_timestamp,
        user_agent=payload.scan_user_agent,
        ip_address=request.client.host if request.client else None,
        ticket_id=None,
    )
    db.add(scan_log)

    update = TicketUpdate(
        ticket=ticket,
        from_status=None,
        to_status=TicketStatus.NEW,
        note="Ticket created from QR scan",
        author_name=payload.reporter_name or "Anonymous",
        author_role="reporter",
    )
    db.add(update)

    db.commit()
    db.refresh(ticket)
    scan_log.ticket_id = ticket.ticket_id
    db.commit()

    # แจ้ง n8n (fire-and-forget) — มี Ticket ใหม่
    _notify_n8n("ticket.created", _ticket_event_payload(ticket))

    return TicketOut(
        id=ticket.id,
        ticket_id=ticket.ticket_id,
        device_id=ticket.device_id,
        title=ticket.title,
        description=ticket.description,
        reporter_name=ticket.reporter_name,
        reporter_email=ticket.reporter_email,
        reporter_phone=ticket.reporter_phone,
        reporter_type=ticket.reporter_type,
        priority=ticket.priority,
        status=ticket.status,
        assigned_to=ticket.assigned_to,
        channel=ticket.channel,
        symptom_code=ticket.symptom_code,
        ai_category=ticket.ai_category,
        attachments=json.loads(ticket.attachments) if ticket.attachments else None,
        sla_due_at=ticket.sla_due_at,
        escalation_level=ticket.escalation_level,
        scan_gps_lat=(
            float(ticket.scan_gps_lat) if ticket.scan_gps_lat is not None else None
        ),
        scan_gps_lng=(
            float(ticket.scan_gps_lng) if ticket.scan_gps_lng is not None else None
        ),
        scan_timestamp=ticket.scan_timestamp,
        resolution_notes=ticket.resolution_notes,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )


# ---------------------------------------------------------------------------
# Public report (คนไม่มีบัญชี) — แจ้งซ่อมสาธารณะ
# ---------------------------------------------------------------------------

# ─── หมวดหมู่อุปกรณ์ ───────────────────────────────────────────────────────
# ใช้จัดกลุ่มงานซ่อมเป็นหมวด (จอ / คอมพิวเตอร์ / เครือข่าย …) แทนการไล่ดูรหัสอุปกรณ์
# ทีละตัว — เป็นตารางเดียวที่ทั้ง Ticket, ตัวกรอง และหน้าสาธารณะใช้ร่วมกัน
DEVICE_CATEGORY_TYPES: dict[str, tuple[str, ...]] = {
    "จอแสดงภาพ": ("Interactive Display", "Projector", "Visualizer"),
    "คอมพิวเตอร์": (
        "Computer AIO", "Computer Notebook", "Computer Tablet", "Computer Desktop",
    ),
    "ระบบเครือข่าย": ("Router", "Access Point", "Switch"),
    "ภาพและเสียง": ("Speaker", "Microphone", "Camera"),
    "อุปกรณ์ต่อพ่วง": ("Printer",),
    "ไฟฟ้า/สำรองไฟ": ("UPS",),
    "ซอฟต์แวร์": ("Software (Picaro)", "Software (Phonics Hero)"),
    "อื่น ๆ": ("Other",),
}

DEVICE_TYPE_TO_CATEGORY: dict[str, str] = {
    device_type: category
    for category, types in DEVICE_CATEGORY_TYPES.items()
    for device_type in types
}


def device_category_of(device_type: Optional[str]) -> Optional[str]:
    """ประเภทอุปกรณ์ → หมวดหมู่ (ประเภทที่ไม่อยู่ในตารางถือเป็น "อื่น ๆ")"""
    if not device_type:
        return None
    return DEVICE_TYPE_TO_CATEGORY.get(device_type, "อื่น ๆ")


def device_categories_out(devices: Optional[list] = None) -> list[DeviceCategoryOut]:
    """รายการหมวดหมู่อุปกรณ์ทั้งหมด + จำนวนอุปกรณ์ที่พบในแต่ละหมวด

    ส่งทุกหมวดเสมอ (ลำดับตาม DEVICE_CATEGORY_TYPES) เพื่อให้หน้าเว็บมีตัวเลือกคงที่
    ส่วน device_count บอกว่าหมวดนั้นมีอุปกรณ์ของหน่วยงานนี้กี่ตัว — หน้าเว็บเลือก
    ซ่อนหมวดที่เป็น 0 ได้เอง
    """
    counts: dict[str, int] = {}
    for item in devices or []:
        category = getattr(item, "device_category", None) or device_category_of(
            getattr(item, "device_type", None)
        )
        if category:
            counts[category] = counts.get(category, 0) + 1
    return [
        DeviceCategoryOut(
            category=category,
            device_types=list(types),
            device_count=counts.get(category, 0),
        )
        for category, types in DEVICE_CATEGORY_TYPES.items()
    ]


def _resolve_device_by_code(db: Session, raw: str) -> Optional[Device]:
    """qr_token หรือรหัสอุปกรณ์ → Device (ใช้ร่วมกันทั้ง /qr/resolve และหน้าสาธารณะ)"""
    code = (raw or "").strip()
    if not code:
        return None
    device = db.execute(
        select(Device).where(Device.qr_token == code)
    ).scalar_one_or_none()
    if device:
        return device
    return db.execute(
        select(Device).where(Device.device_id == code)
    ).scalar_one_or_none() or db.execute(
        select(Device).where(Device.device_id == code.upper())
    ).scalar_one_or_none()


@app.get("/api/device-categories")
def list_device_categories():
    """หมวดหมู่อุปกรณ์ + ประเภทในแต่ละหมวด — หน้าเว็บใช้ทำตัวกรองหมวดหมู่"""
    return {
        "categories": [
            {"category": category, "device_types": list(types)}
            for category, types in DEVICE_CATEGORY_TYPES.items()
        ]
    }


DEVICE_TYPE_LABELS = [
    "Interactive Display", "Computer AIO", "Computer Notebook", "Computer Tablet",
    "Computer Desktop", "Router", "Access Point", "Switch", "Speaker", "Camera",
    "Visualizer", "Microphone", "UPS", "Printer", "Projector",
    "Software (Picaro)", "Software (Phonics Hero)", "Other",
]


@app.get("/api/public/options", response_model=PublicOptionsOut)
@limiter.limit("60/minute")
def public_options(
    request: Request,
    organization_code: Optional[str] = Query(None, min_length=2, max_length=64),
    db: Session = Depends(get_db),
):
    """ข้อมูลสำหรับ dropdown หน้าแจ้งซ่อมสาธารณะ (ไม่ต้อง auth):
    - device_types: ประเภทอุปกรณ์ที่เลือกได้
    - devices: รายการอุปกรณ์ของหน่วยงานนั้น — ส่งเฉพาะเมื่อระบุ organization_code ถูกต้อง
      (เดิมคืนอุปกรณ์ทั้งระบบทุกโรงเรียน 500 รายการแบบไม่ต้องล็อกอิน)
    """
    code = (organization_code or "").strip()
    if not code:
        # ไม่ระบุรหัสหน่วยงาน = ไม่เปิดรายการอุปกรณ์ให้ไล่ดู ให้ผู้แจ้งกรอกห้อง/อุปกรณ์เอง
        return PublicOptionsOut(
            device_types=DEVICE_TYPE_LABELS,
            device_categories=device_categories_out(),
            devices=[],
            requires_organization=True,
        )

    org = db.execute(
        select(Organization).where(Organization.code == code)
    ).scalar_one_or_none()
    if not org:
        raise HTTPException(
            status_code=404,
            detail={
                "code": "ORGANIZATION_NOT_FOUND",
                "message": "ไม่พบรหัสหน่วยงานนี้ — ตรวจสอบรหัสบนสติกเกอร์ QR หรือสอบถามเจ้าหน้าที่",
            },
        )

    rows = db.execute(
        select(Device, Room)
        .outerjoin(Room, Room.id == Device.room_id)
        .where(Device.organization_id == org.id)
        .order_by(Device.device_id)
        .limit(200)
    ).all()
    devices: list[PublicDeviceInfo] = []
    for device, room in rows:
        # endpoint นี้เปิดสาธารณะ (ไม่ต้อง auth) — ต้องไม่ส่งข้อมูลอ่อนไหวออกไป
        # ห้ามส่ง: qr_token / qr_url (ใช้สร้างลิงก์สแกนของทุกห้องได้),
        #          serial_number, firmware_version, warranty_until, notes (ข้อมูลทรัพย์สินภายใน)
        room_label = (room.name or room.code) if room else None
        devices.append(PublicDeviceInfo(
            device_id=device.device_id,
            device_type=device.device_type,
            device_category=device_category_of(device.device_type),
            device_label=compose_device_label(
                device.device_type, device.brand, device.model, room_label
            ),
            brand=device.brand,
            model=device.model,
            status=device.status,
            room_code=room.code if room else None,
            room_name=room.name if room else None,
            building=room.building if room else None,
            floor=room.floor if room else None,
            organization_code=org.code,
            organization_name=org.name,
            organization_id=device.organization_id,
        ))
    return PublicOptionsOut(
        device_types=DEVICE_TYPE_LABELS,
        device_categories=device_categories_out(devices),
        devices=devices,
        organization_code=org.code,
        organization_name=org.name,
        requires_organization=False,
    )


@app.post("/api/public/report", status_code=201)
@limiter.limit("10/minute")
def public_report(
    payload: PublicReportIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """แจ้งซ่อมสาธารณะ (ไม่ต้อง login) — resolve/สร้าง room+device แล้วสร้าง repair_ticket.
    บังคับ: reporter_name, reporter_phone, title. ถ้าไม่มีชื่อ/เบอร์ → 422.
    """
    # ── บังคับ ชื่อ + เบอร์ (422 ถ้าไม่ครบ) ──
    name = (payload.reporter_name or "").strip()
    phone = (payload.reporter_phone or "").strip()
    if not name or not phone:
        missing = []
        if not name:
            missing.append("reporter_name")
        if not phone:
            missing.append("reporter_phone")
        raise HTTPException(
            status_code=422,
            detail={
                "code": "MISSING_REPORTER",
                "message": "กรุณาระบุชื่อผู้แจ้งและเบอร์โทรติดต่อ (จำเป็น)",
                "missing": missing,
            },
        )
    if not payload.title.strip():
        raise HTTPException(status_code=422, detail="กรุณาระบุหัวข้อ/อาการ (จำเป็น)")
    if (payload.scan_gps_lat is None) != (payload.scan_gps_lng is None):
        raise HTTPException(status_code=422, detail="ต้องส่งพิกัดละติจูดและลองจิจูดพร้อมกัน")

    priority = payload.priority if payload.priority in ("low", "normal", "high", "critical") else "normal"

    # ── Resolve organization (ระบุ code หรือ default ตัวแรก เช่น TEST1) ──
    org = None
    if payload.organization_code:
        org = db.execute(
            select(Organization).where(Organization.code == payload.organization_code.strip())
        ).scalar_one_or_none()
    if not org:
        org = db.execute(
            select(Organization).order_by(Organization.id).limit(1)
        ).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    try:
        # LINE identity comes only from a one-time token issued inside the
        # verified conversation, never from a browser-supplied user ID/phone.
        from app.line_report_link import bind_report_link, lock_report_link
        try:
            report_link = lock_report_link(db, payload.line_report_token) if payload.line_report_token else None
        except ValueError:
            raise HTTPException(status_code=422, detail={
                "code": "LINE_REPORT_LINK_EXPIRED",
                "message": "ลิงก์เชื่อม LINE หมดอายุหรือใช้ไปแล้ว กรุณาขอลิงก์ใหม่ในแชต LINE",
            })
        # ── Resolve/สร้าง device ──
        device = None
        room_text = ""
        # กรณีรู้ device code แล้ว (เลือกจาก dropdown)
        if payload.device_id:
            device = db.execute(
                select(Device).where(
                    Device.device_id == payload.device_id.strip(),
                    Device.organization_id == org.id,
                )
            ).scalar_one_or_none()
            if not device:
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"ไม่พบรหัสอุปกรณ์นี้ใน {org.name} — "
                        "รหัสอุปกรณ์ของแต่ละโรงเรียนไม่เหมือนกัน "
                        "กรุณาตรวจรหัสบนสติกเกอร์/QR หรือเลือกโรงเรียนให้ตรงกับเครื่อง"
                    ),
                )
        else:
            # ── Resolve/สร้าง Room จาก room_text ──
            room = None
            room_text = (payload.room_text or "").strip()
            if room_text:
                room = db.execute(
                    select(Room).where(
                        Room.organization_id == org.id,
                        Room.name == room_text,
                    )
                ).scalar_one_or_none()
                if not room:
                    room = db.execute(
                        select(Room).where(
                            Room.organization_id == org.id,
                            Room.code == room_text,
                        )
                    ).scalar_one_or_none()
                if not room:
                    room = Room(
                        organization_id=org.id,
                        code=room_text,
                        name=room_text,
                        building=None,
                        floor=None,
                    )
                    db.add(room)
                    db.flush()

            device_type = payload.device_type or "Other"
            # กัน device_type ไม่อยู่ใน enum
            if device_type not in DEVICE_TYPE_LABELS:
                device_type = "Other"
            detail = (payload.device_detail or "").strip() or room_text
            # ── Reuse อุปกรณ์เดิม ถ้าข้อมูล (ห้อง+ประเภท+รายละเอียด) ตรงกัน → กันแจ้งซ้ำได้จริง ──
            existing = None
            if detail:
                existing = db.execute(
                    select(Device).where(
                        Device.organization_id == org.id,
                        Device.device_type == device_type,
                        Device.notes == detail,
                        Device.room_id == (room.id if room else None),
                    )
                ).scalars().first()
            if existing:
                device = existing
            else:
                new_device_id = generate_device_id(db, org, room, device_type)
                device = Device(
                    device_id=new_device_id,
                    organization_id=org.id,
                    room_id=room.id if room else None,
                    device_type=device_type,
                    brand=None,
                    model=None,
                    serial_number=None,
                    status="active",
                    notes=detail,
                )
                db.add(device)
                db.flush()

        # ── กันแจ้งซ้ำ: อุปกรณ์มี ticket ค้าง → 409 DUPLICATE_OPEN_TICKET ──
        open_ticket = find_open_ticket(db, device.device_id)
        if open_ticket:
            raise_duplicate_open_ticket(open_ticket)

        # ── สร้าง RepairTicket ──
        now = datetime.now(timezone.utc)
        sla_due = calc_sla_due(now, priority)
        ticket = RepairTicket(
            ticket_id=generate_ticket_id(db, org.id),
            organization_id=org.id,
            device_id=device.device_id,
            title=payload.title.strip(),
            description=payload.description,
            reporter_name=name,
            reporter_phone=phone,
            reporter_type=payload.reporter_type or "public",
            priority=priority,
            status=TicketStatus.NEW,
            channel="public",
            attachments=json.dumps(payload.attachments or [], ensure_ascii=False),
            sla_due_at=sla_due,
            scan_gps_lat=payload.scan_gps_lat,
            scan_gps_lng=payload.scan_gps_lng,
            scan_timestamp=payload.scan_timestamp or now,
        )
        db.add(ticket)
        db.flush()
        if report_link:
            bind_report_link(report_link, ticket)

        update = TicketUpdate(
            ticket=ticket,
            from_status=None,
            to_status=TicketStatus.NEW,
            note="Ticket created from public no-login form",
            author_name=name,
            author_role="reporter",
        )
        db.add(update)
        db.add(ScanLog(
            device_id=device.device_id,
            scan_gps_lat=payload.scan_gps_lat,
            scan_gps_lng=payload.scan_gps_lng,
            scan_timestamp=ticket.scan_timestamp,
            user_agent=payload.scan_user_agent,
            ip_address=request.client.host if request.client else None,
            ticket_id=ticket.ticket_id,
        ))

        db.commit()
        db.refresh(ticket)

        # The ticket is durable even if LINE is unavailable. The browser also
        # shows the number, so a delivery failure cannot hide the result.
        line_receipt_sent = False
        if report_link:
            from app.line_report_link import send_ticket_receipt
            line_receipt_sent = send_ticket_receipt(report_link.line_user_id, ticket.ticket_id)

        # แจ้ง n8n (fire-and-forget)
        _notify_n8n("ticket.created", _ticket_event_payload(ticket))

        return {
            "ticket_id": ticket.ticket_id,
            "device_id": device.device_id,
            "device_type": device.device_type,
            "room_name": room_text,
            "status": ticket.status,
            "organization_code": org.code,
            "line_receipt_sent": line_receipt_sent,
            "message": "ส่งคำร้องแจ้งซ่อมเรียบร้อยแล้ว",
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@app.get("/api/public/devices/{code}/open-ticket")
@limiter.limit("60/minute")
def public_device_open_ticket(request: Request, code: str, db: Session = Depends(get_db)):
    """อุปกรณ์นี้มีงานค้างอยู่ไหม — ใช้เตือนก่อนที่ผู้แจ้งจะกรอกฟอร์มทั้งใบ

    รับได้ทั้ง qr_token และรหัสอุปกรณ์ (เหมือน /api/qr/resolve) เพื่อให้การสแกน QR
    และการพิมพ์รหัสใต้สติกเกอร์ได้ผลเหมือนกัน
    """
    device = _resolve_device_by_code(db, code)
    if not device:
        raise HTTPException(status_code=404, detail="ไม่พบอุปกรณ์ที่ตรงกับรหัส/QR นี้")
    open_ticket = find_open_ticket(db, device.device_id)
    return {
        "device_id": device.device_id,
        "device_type": device.device_type,
        "device_category": device_category_of(device.device_type),
        "device_label": device_display_label(device),
        "has_open_ticket": open_ticket is not None,
        "open_ticket": open_ticket_summary(open_ticket) if open_ticket else None,
    }


def _resolve_device_for_warranty(db: Session, raw: str) -> Optional[Device]:
    """หมายเลขสินค้า (serial) -> Device, สำรองด้วยรหัสอุปกรณ์/QR token

    หน้าตรวจสอบประกันให้ผู้ใช้กรอก "หมายเลขสินค้า" บนสติกเกอร์ของผู้ผลิตเป็นหลัก
    จึงค้น serial_number ก่อน (ไม่สนตัวพิมพ์เล็ก-ใหญ่) แล้ว fallback ไป
    _resolve_device_by_code เพื่อให้คนที่ถือสติกเกอร์ของโรงเรียนใช้ช่องเดียวกันได้
    """
    code = (raw or "").strip()
    if not code:
        return None
    device = (
        db.execute(select(Device).where(func.upper(Device.serial_number) == code.upper()))
        .scalars()
        .first()
    )
    if device:
        return device
    return _resolve_device_by_code(db, code)


#: ป้ายสถานะประกันสำหรับหน้าสาธารณะ — คำเดียวกับที่ frontend ใช้
WARRANTY_STATUS_LABELS = {
    "active": "อยู่ในระยะประกัน",
    "expiring": "ใกล้หมดประกัน",
    "expired": "หมดประกันแล้ว",
    "unknown": "ไม่มีข้อมูลวันสิ้นสุดประกัน",
}


@app.get("/api/public/warranty/{code}")
@limiter.limit("30/minute")
def public_warranty_lookup(request: Request, code: str, db: Session = Depends(get_db)):
    """ตรวจสอบประกันด้วยหมายเลขสินค้า — เปิดสาธารณะ ไม่ต้องล็อกอิน

    คืนเฉพาะข้อมูลที่จำเป็นต่อคำถาม "ยังอยู่ในประกันไหม" ไม่คืนข้อมูลผู้แจ้ง
    ไม่คืน notes ภายใน และไม่คืน qr_token เพื่อไม่ให้ใช้กวาดข้อมูลอุปกรณ์
    เกณฑ์ "ใกล้หมด" ใช้ pm_rules.WARRANTY_WARN_DAYS ตัวเดียวกับ PM Rule 2
    """
    device = _resolve_device_for_warranty(db, code)
    if not device:
        raise HTTPException(
            status_code=404,
            detail="ไม่พบหมายเลขสินค้านี้ในระบบ — ตรวจสอบหมายเลขบนสติกเกอร์อีกครั้ง",
        )

    room = db.get(Room, device.room_id) if device.room_id else None
    org = db.get(Organization, device.organization_id) if device.organization_id else None

    warn_days = pm_rules.WARRANTY_WARN_DAYS
    until = device.warranty_until
    # ฐานข้อมูลบางชุดเก็บ datetime แบบไม่มี timezone -> เทียบกับ now(utc) ตรง ๆ จะ error
    if until is not None and until.tzinfo is None:
        until = until.replace(tzinfo=timezone.utc)

    if until is None:
        status = "unknown"
        days_left = None
    else:
        days_left = (until - datetime.now(timezone.utc)).days
        if days_left < 0:
            status = "expired"
        elif days_left <= warn_days:
            status = "expiring"
        else:
            status = "active"

    open_ticket = find_open_ticket(db, device.device_id)
    return {
        "device_id": device.device_id,
        "device_type": device.device_type,
        "device_category": device_category_of(device.device_type),
        "device_label": device_display_label(device),
        "brand": device.brand,
        "model": device.model,
        "serial_number": device.serial_number,
        "device_status": device.status,
        "purchase_date": device.purchase_date,
        "warranty_until": device.warranty_until,
        "warranty_status": status,
        "warranty_status_label": WARRANTY_STATUS_LABELS[status],
        "days_left": days_left,
        "warn_days": warn_days,
        "room_name": room.name if room else None,
        "room_code": room.code if room else None,
        "organization_name": org.name if org else None,
        "has_open_ticket": open_ticket is not None,
        "open_ticket": open_ticket_summary(open_ticket) if open_ticket else None,
    }


@app.post("/api/public/tickets/{ticket_no}/notes", status_code=201)
@limiter.limit("10/minute")
def public_add_ticket_note(
    ticket_no: str,
    payload: PublicTicketNoteIn,
    request: Request,
    db: Session = Depends(get_db),
):
    """เพิ่มอาการ/ข้อมูลเข้า Ticket ที่ยังไม่ปิด (ไม่ต้องล็อกอิน) — ใช้แทนการแจ้งซ้ำ

    ไม่เปลี่ยนสถานะงานและไม่ทับ description เดิม เก็บเป็น ticket_updates เพื่อให้ช่าง
    เห็นลำดับเวลา และผู้แจ้งคนหลังไม่ลบข้อมูลของคนก่อน
    """
    ticket = find_ticket_by_no(db, ticket_no)
    if ticket.status not in OPEN_TICKET_STATUSES:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "TICKET_NOT_OPEN",
                "message": (
                    f"Ticket {ticket.ticket_id} ปิดงานแล้ว (สถานะ: "
                    f"{PUBLIC_STATUS_LABELS.get(ticket.status, ticket.status)}) — "
                    "ถ้าอุปกรณ์ยังมีปัญหา กรุณาแจ้งซ่อมใหม่"
                ),
                "status": ticket.status,
                "status_label": PUBLIC_STATUS_LABELS.get(ticket.status, ticket.status),
            },
        )

    note = payload.note.strip()
    name = payload.reporter_name.strip()
    if not note or not name:
        raise HTTPException(
            status_code=422,
            detail="กรุณาระบุชื่อผู้แจ้งและรายละเอียดที่ต้องการแจ้งเพิ่ม",
        )
    phone = (payload.reporter_phone or "").strip()
    suffix = f" (แนบรูป {len(payload.attachments)} รูป)" if payload.attachments else ""

    db.add(TicketUpdate(
        ticket=ticket,
        from_status=ticket.status,
        to_status=ticket.status,
        note=f"[แจ้งเพิ่มจากผู้ใช้] {note}{suffix}",
        author_name=f"{name} ({phone})" if phone else name,
        author_role="reporter",
    ))

    # รูปที่แนบเพิ่ม ต่อท้ายรายการเดิม ไม่เขียนทับของที่ผู้แจ้งคนแรกส่งมา
    if payload.attachments:
        try:
            current = json.loads(ticket.attachments) if ticket.attachments else []
        except (ValueError, TypeError):
            current = []
        if not isinstance(current, list):
            current = []
        ticket.attachments = json.dumps(
            current + list(payload.attachments), ensure_ascii=False
        )

    db.commit()
    db.refresh(ticket)

    event = _ticket_event_payload(ticket)
    event["note"] = note
    event["author_name"] = name
    _notify_n8n("ticket.note_added", event)

    return {
        "ticket_no": ticket.ticket_id,
        "status": ticket.status,
        "status_label": PUBLIC_STATUS_LABELS.get(ticket.status, ticket.status),
        "message": f"บันทึกข้อมูลเพิ่มเข้า Ticket {ticket.ticket_id} เรียบร้อยแล้ว",
    }


@app.get("/api/devices", response_model=list[DeviceInfo])
def list_devices(
    status: Optional[str] = Query(None),
    device_type: Optional[str] = Query(None),
    organization_code: Optional[str] = Query(None),
    organization_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(Device, Room, Organization)
        .outerjoin(Room, Room.id == Device.room_id)
        .join(Organization, Organization.id == Device.organization_id)
        .order_by(Device.device_id)
    )
    # ── จำกัดตาม scope ของบทบาท ──
    if user is not None:
        scope = visible_org_ids(user)
        if scope is not None:
            if not scope:
                return []  # scope ว่าง → ไม่เห็นข้อมูล
            stmt = stmt.where(Device.organization_id.in_(scope))
    if status:
        stmt = stmt.where(Device.status == status)
    if device_type:
        stmt = stmt.where(Device.device_type == device_type)
    if organization_code:
        stmt = stmt.where(Organization.code == organization_code)
    if organization_id:
        stmt = stmt.where(Device.organization_id == organization_id)
    stmt = stmt.offset(offset).limit(limit)

    rows = db.execute(stmt).all()
    result: list[DeviceInfo] = []
    for device, room, org in rows:
        result.append(DeviceInfo(
            device_id=device.device_id,
            device_type=device.device_type,
            brand=device.brand,
            model=device.model,
            serial_number=device.serial_number,
        qr_token=device.qr_token,
        qr_url=(f"/scan?t={device.qr_token}" if device.qr_token else f"/scan?device={device.device_id}"),
            firmware_version=device.firmware_version,
            status=device.status,
            room_code=room.code if room else None,
            room_name=room.name if room else None,
            building=room.building if room else None,
            floor=room.floor if room else None,
            organization_code=org.code,
            organization_name=org.name,
            organization_id=device.organization_id,
            purchase_date=device.purchase_date,
            warranty_until=device.warranty_until,
            warranty_details=device.warranty_details,
            notes=device.notes,
        ))
    return result



_DEVICE_IMPORT_COLUMNS = {
    "organization_code": ("organization_code", "school_code", "รหัสโรงเรียน"),
    "device_id": ("device_id", "รหัสอุปกรณ์"),
    "room_code": ("room_code", "รหัสห้อง"),
    "device_type": ("device_type", "ประเภทอุปกรณ์"),
    "brand": ("brand", "ยี่ห้อ"),
    "model": ("model", "รุ่น"),
    "serial_number": ("serial_number", "serial", "หมายเลขซีเรียล"),
    "firmware_version": ("firmware_version", "เฟิร์มแวร์"),
    "status": ("status", "สถานะ"),
    "purchase_date": ("purchase_date", "วันที่จัดซื้อ"),
    "warranty_until": ("warranty_until", "วันสิ้นสุดประกัน"),
    "warranty_details": ("warranty_details", "รายละเอียดประกันสำหรับลูกค้า"),
    "notes": ("notes", "หมายเหตุ"),
}


@app.post("/api/devices/import-csv")
async def import_devices_csv(
    request: Request,
    file: UploadFile = File(...),
    commit: bool = Query(False),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support")),
):
    """Google Sheets → CSV: ตรวจทุกแถวก่อนบันทึกทั้งหมดแบบ atomic; ไม่แก้ข้อมูลเดิม."""
    if not (file.filename or "").lower().endswith(".csv"):
        raise HTTPException(status_code=400, detail="รองรับเฉพาะไฟล์ CSV ที่ส่งออกจาก Google Sheets")
    raw = await file.read(2_000_001)
    if len(raw) > 2_000_000:
        raise HTTPException(status_code=413, detail="ไฟล์ใหญ่เกิน 2 MB")
    try:
        content = raw.decode("utf-8-sig")
        reader = csv.DictReader(io.StringIO(content))
        if not reader.fieldnames:
            raise ValueError("ไฟล์ไม่มีหัวตาราง")
        headers = {h.strip().lower(): h for h in reader.fieldnames if h}
        mapping = {key: next((headers[a.lower()] for a in aliases if a.lower() in headers), None)
                   for key, aliases in _DEVICE_IMPORT_COLUMNS.items()}
        if not mapping["organization_code"] or not mapping["device_id"] or not mapping["device_type"]:
            raise ValueError("ต้องมีคอลัมน์ organization_code, device_id, device_type (หรือชื่อภาษาไทยตามตัวอย่าง)")
        source_rows = list(reader)
    except (UnicodeDecodeError, csv.Error, ValueError) as exc:
        raise HTTPException(status_code=400, detail=f"อ่าน CSV ไม่ได้: {exc}") from exc
    if not source_rows or len(source_rows) > 500:
        raise HTTPException(status_code=400, detail="ไฟล์ต้องมีข้อมูล 1–500 แถว")

    orgs = {o.code.upper(): o for o in db.execute(select(Organization)).scalars()}
    existing = set(db.execute(select(Device.device_id)).scalars())
    seen: set[str] = set()
    results: list[dict] = []
    pending: list[dict] = []
    for row_number, source in enumerate(source_rows, 2):
        row = {key: str(source.get(header) or "").strip() if header else ""
               for key, header in mapping.items()}
        errors: list[str] = []
        org = orgs.get(row["organization_code"].upper())
        if not org:
            errors.append("ไม่พบรหัสโรงเรียน")
        elif not check_org_access(user, org.id, raise_http=False):
            errors.append("ไม่มีสิทธิ์ในโรงเรียนนี้")
        if org and not errors:
            try:
                row["device_id"] = _normalize_manual_device_id(db, org, row["device_id"])
            except HTTPException as exc:
                errors.append(str(exc.detail))
        if row["device_id"] in existing or row["device_id"] in seen:
            errors.append("รหัสอุปกรณ์ซ้ำ")
        seen.add(row["device_id"])
        valid_types = {value for name, value in vars(DeviceType).items() if name.isupper()}
        if row["device_type"] not in valid_types:
            errors.append("ประเภทอุปกรณ์ไม่อยู่ในรายการที่รองรับ")
        if row["status"] and row["status"] not in {"active", "inactive", "decommissioned"}:
            errors.append("สถานะไม่ถูกต้อง")
        room = None
        if org and row["room_code"]:
            room = db.execute(select(Room).where(Room.organization_id == org.id,
                                                Room.code == row["room_code"])).scalar_one_or_none()
            if not room:
                errors.append("ไม่พบรหัสห้องในโรงเรียนนี้")
        for date_field in ("purchase_date", "warranty_until"):
            if row[date_field]:
                try:
                    parsed_date = datetime.strptime(row[date_field], "%Y-%m-%d")
                    row[date_field] = parsed_date.replace(tzinfo=timezone(timedelta(hours=7))).isoformat()
                except ValueError:
                    errors.append(f"{date_field} ต้องเป็น YYYY-MM-DD")
        for field_name, max_length in (("brand", 128), ("model", 128), ("serial_number", 128), ("firmware_version", 64), ("warranty_details", 500)):
            if len(row[field_name]) > max_length:
                errors.append(f"{field_name} ยาวเกิน {max_length} ตัวอักษร")
        results.append({"row": row_number, "device_id": row["device_id"], "organization_code": row["organization_code"],
                        "device_type": row["device_type"], "errors": errors})
        if not errors:
            pending.append({"row": row, "org": org, "room": room})
    error_count = sum(bool(r["errors"]) for r in results)
    if not commit:
        return {"total": len(results), "valid": len(pending), "invalid": error_count, "rows": results}
    if error_count:
        raise HTTPException(status_code=422, detail={"message": "มีแถวผิดพลาด ไม่ได้บันทึกอุปกรณ์ใด", "rows": results})
    import secrets
    for item in pending:
        row, org, room = item["row"], item["org"], item["room"]
        db.add(Device(device_id=row["device_id"], organization_id=org.id, room_id=room.id if room else None,
                      device_type=row["device_type"], brand=row["brand"] or None, model=row["model"] or None,
                      serial_number=row["serial_number"] or None, firmware_version=row["firmware_version"] or None,
                      status=row["status"] or "active", notes=row["notes"] or None,
                      warranty_details=row["warranty_details"] or None,
                      purchase_date=datetime.fromisoformat(row["purchase_date"]) if row["purchase_date"] else None,
                      warranty_until=datetime.fromisoformat(row["warranty_until"]) if row["warranty_until"] else None,
                      qr_token=secrets.token_urlsafe(24)))
    write_audit(db, action="device_import_csv", user=user, entity_type="device",
                new_value={"count": len(pending), "device_ids": [x["row"]["device_id"] for x in pending]}, request=request)
    db.commit()
    return {"imported": len(pending), "rows": results}


@app.post("/api/devices", response_model=DeviceInfo, status_code=201)
def create_device(payload: DeviceCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """เพิ่มอุปกรณ์ใหม่ — บังคับ org ตาม scope ของบทบาท"""
    check_org_access(user, payload.organization_id)
    org = db.execute(select(Organization).where(Organization.id == payload.organization_id)).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    # หา room (จาก room_id หรือ room_code)
    room_id = payload.room_id
    room = None
    if not room_id and payload.room_code:
        room = db.execute(
            select(Room).where(Room.organization_id == payload.organization_id, Room.code == payload.room_code)
        ).scalar_one_or_none()
        if room:
            room_id = room.id
    elif room_id:
        room = db.get(Room, room_id)

    # หา device_id อัตโนมัติถ้าไม่ระบุ — รูปแบบ SCH01-B1-R101-DISP-01 (TOR 3.5)
    device_id = payload.device_id
    if not device_id:
        device_id = generate_device_id(db, org, room, payload.device_type)
    else:
        device_id = _normalize_manual_device_id(db, org, device_id)
    exists = db.execute(select(Device).where(Device.device_id == device_id)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="device_id ซ้ำ")

    import secrets
    qr_token = secrets.token_urlsafe(24)

    device = Device(
        device_id=device_id,
        organization_id=payload.organization_id,
        room_id=room_id,
        device_type=payload.device_type,
        brand=payload.brand,
        model=payload.model,
        serial_number=payload.serial_number,
        firmware_version=payload.firmware_version,
        status=payload.status,
        qr_token=qr_token,
        notes=payload.notes,
        purchase_date=payload.purchase_date,
        warranty_until=payload.warranty_until,
        warranty_details=payload.warranty_details,
    )
    db.add(device)
    # §40: สร้าง Asset ต้องบันทึก Audit Log (commit พร้อม transaction เดียวกัน)
    write_audit(
        db, action="device_create", user=user, entity_type="device", entity_id=device_id,
        new_value={
            "device_id": device_id,
            "organization_id": payload.organization_id,
            "room_id": room_id,
            "device_type": payload.device_type,
            "brand": payload.brand,
            "model": payload.model,
            "serial_number": payload.serial_number,
            "status": payload.status,
        },
        request=request,
    )
    db.commit()
    db.refresh(device)

    room = db.get(Room, device.room_id) if device.room_id else None
    return DeviceInfo(
        device_id=device.device_id,
        device_type=device.device_type,
        brand=device.brand,
        model=device.model,
        serial_number=device.serial_number,
        qr_token=device.qr_token,
        qr_url=(f"/scan?t={device.qr_token}" if device.qr_token else f"/scan?device={device.device_id}"),
        firmware_version=device.firmware_version,
        status=device.status,
        room_code=room.code if room else None,
        room_name=room.name if room else None,
        building=room.building if room else None,
        floor=room.floor if room else None,
        gps_lat=float(room.gps_lat) if room and room.gps_lat is not None else None,
        gps_lng=float(room.gps_lng) if room and room.gps_lng is not None else None,
        organization_code=org.code,
        organization_name=org.name,
        organization_id=device.organization_id,
        purchase_date=device.purchase_date,
        warranty_until=device.warranty_until,
        warranty_details=device.warranty_details,
        notes=device.notes,
    )


@app.patch("/api/devices/{device_id}", response_model=DeviceInfo)
def update_device(device_id: str, payload: DeviceUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """แก้ไขข้อมูลอุปกรณ์ — ตรวจว่า device อยู่ใน scope"""
    device = db.execute(select(Device).where(Device.device_id == device_id)).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    check_org_access(user, device.organization_id)

    data = payload.model_dump(exclude_unset=True)
    # จัดการ room_code -> room_id
    if "room_code" in data and data["room_code"]:
        room = db.execute(
            select(Room).where(Room.organization_id == device.organization_id, Room.code == data["room_code"])
        ).scalar_one_or_none()
        if room:
            data["room_id"] = room.id
    data.pop("room_code", None)

    # §40: เก็บค่าก่อนแก้ เพื่อบันทึกทั้ง old_value และ new_value
    old_value = {k: getattr(device, k, None) for k in data}
    for k, v in data.items():
        setattr(device, k, v)
    if data:
        write_audit(
            db, action="device_update", user=user, entity_type="device",
            entity_id=device.device_id, old_value=old_value, new_value=data,
            request=request,
        )
    db.commit()
    db.refresh(device)

    org = db.get(Organization, device.organization_id)
    room = db.get(Room, device.room_id) if device.room_id else None
    return DeviceInfo(
        device_id=device.device_id,
        device_type=device.device_type,
        brand=device.brand,
        model=device.model,
        serial_number=device.serial_number,
        qr_token=device.qr_token,
        qr_url=(f"/scan?t={device.qr_token}" if device.qr_token else f"/scan?device={device.device_id}"),
        firmware_version=device.firmware_version,
        status=device.status,
        room_code=room.code if room else None,
        room_name=room.name if room else None,
        building=room.building if room else None,
        floor=room.floor if room else None,
        gps_lat=float(room.gps_lat) if room and room.gps_lat is not None else None,
        gps_lng=float(room.gps_lng) if room and room.gps_lng is not None else None,
        organization_code=org.code if org else "",
        organization_name=org.name if org else "",
        purchase_date=device.purchase_date,
        warranty_until=device.warranty_until,
        warranty_details=device.warranty_details,
        notes=device.notes,
    )


def _recovery_snapshot(row) -> dict:
    """Store every scalar column except the surrogate PK; do not rely on partial audit metadata."""
    return {column.name: getattr(row, column.name) for column in row.__table__.columns if column.name != "id"}


def _recovery_model(model, values: dict, **overrides):
    """Rehydrate a snapshot, preserving timestamps/coordinates after JSON serialization."""
    columns = {column.name: column for column in model.__table__.columns}
    data = {}
    for name, value in {**values, **overrides}.items():
        if name == "id" or name not in columns:
            continue
        if value is not None and isinstance(columns[name].type, SQLDateTime):
            value = datetime.fromisoformat(value) if isinstance(value, str) else value
        elif value is not None and isinstance(columns[name].type, SQLNumeric):
            value = Decimal(str(value))
        data[name] = value
    return model(**data)


@app.delete("/api/devices/{device_id}")
def delete_device(device_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """ลบอุปกรณ์ (ต้องไม่มี ticket ผูกอยู่) — ตรวจว่า device อยู่ใน scope"""
    device = db.execute(select(Device).where(Device.device_id == device_id)).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    check_org_access(user, device.organization_id)

    ticket_count = db.execute(
        text("SELECT COUNT(*) FROM repair_tickets WHERE device_id=:d"), {"d": device_id}
    ).scalar_one()
    if ticket_count > 0:
        raise HTTPException(status_code=400, detail=f"ไม่สามารถลบได้ — อุปกรณ์มี {ticket_count} ticket ผูกอยู่")

    linked_pm = db.execute(select(func.count(PMTask.id)).where(PMTask.device_id == device_id)).scalar_one()
    linked_flags = db.execute(select(func.count(DeviceHealthFlag.id)).where(DeviceHealthFlag.device_id == device_id)).scalar_one()
    if linked_pm or linked_flags:
        raise HTTPException(status_code=400, detail="อุปกรณ์มีประวัติ PM/สถานะสุขภาพที่ผูกอยู่ กรุณาเก็บไว้เพื่อไม่ให้ประวัติสูญหาย")
    scans = db.execute(select(ScanLog).where(ScanLog.device_id == device_id)).scalars().all()
    db.add(DeletedRecord(
        entity_type="device", entity_id=device_id, organization_id=device.organization_id,
        payload=json.dumps({"device": _recovery_snapshot(device), "scans": [_recovery_snapshot(row) for row in scans]}, ensure_ascii=False, default=str),
        deleted_by=user.id,
    ))


    db.execute(text("DELETE FROM scan_logs WHERE device_id=:d"), {"d": device_id})
    # §40: ลบ Asset — ต้องเก็บค่าเดิมก่อนลบ เพราะหลังลบอ่านย้อนไม่ได้
    write_audit(
        db, action="device_delete", user=user, entity_type="device", entity_id=device_id,
        old_value={
            "device_id": device.device_id,
            "organization_id": device.organization_id,
            "room_id": device.room_id,
            "device_type": device.device_type,
            "serial_number": device.serial_number,
            "status": device.status,
        },
        request=request,
    )
    db.delete(device)
    db.commit()
    return {"message": "Device moved to recoverable history", "device_id": device_id}


# ─── Users ─────────────────────────────────────────────────────────
@app.get("/api/users", response_model=list[UserOut])
def list_users(db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school"))):
    """รายชื่อผู้ใช้ — จำกัดตามบทบาท: admin_school เห็นเฉพาะ user ในรรตัวเอง"""
    scope = visible_org_ids(user)
    stmt = select(User).order_by(User.created_at.desc())
    if scope is not None:
        if not scope:
            return []  # scope ว่าง → ไม่เห็นข้อมูล
        stmt = stmt.where(User.organization_id.in_(scope))
    rows = db.execute(stmt).scalars().all()
    return [UserOut(
        id=u.id,
        line_user_id=u.line_user_id,
        line_display_name=u.line_display_name,
        line_picture_url=u.line_picture_url,
        line_email=u.line_email,
        organization_id=u.organization_id,
        role=u.role,
        is_active=u.is_active,
        created_at=u.created_at,
    ) for u in rows]


@app.post("/api/users", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school"))):
    validate_assignable_role(payload.role)
    exists = db.execute(select(User).where(User.line_user_id == payload.line_user_id)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="line_user_id ซ้ำ")

    # ── จำกัดสิทธิ์การสร้าง user ตามบทบาท ──
    if payload.role == "owner" and user.role != "owner":
        raise HTTPException(status_code=403, detail="มีเพียง Owner เท่านั้นที่กำหนดบทบาท Owner ได้")
    if user.role == "admin_school":
        # admin_school: สร้างได้เฉพาะเจ้าหน้าที่ IT และในรรตัวเองเท่านั้น
        if payload.role not in SCHOOL_ADMIN_ASSIGNABLE_ROLES:
            raise HTTPException(status_code=403, detail="ผู้ดูแลโรงเรียนไม่สามารถสร้างบทบาทนี้ได้ (ได้แค่ ครู/นักเรียน/เจ้าหน้าที่ IT)")
        if payload.organization_id != user.organization_id:
            raise HTTPException(status_code=403, detail="ผู้ดูแลโรงเรียนสร้างผู้ใช้ได้เฉพาะในโรงเรียนของตนเองเท่านั้น")
    else:
        # super_admin / admin — บังคับว่าอย่างน้อยคน global ควรกำหนด org ให้ user ทั่วไป
        pass

    new_user = User(
        line_user_id=payload.line_user_id,
        line_display_name=payload.line_display_name,
        line_email=payload.line_email,
        organization_id=payload.organization_id,
        role=payload.role,
        is_active=payload.is_active,
        password_hash=hash_password(payload.password) if payload.password else None,
    )
    db.add(new_user)
    db.flush()  # ต้องได้ id ก่อน จึงอ้างอิงใน Audit Log ได้
    # §40: สร้างผู้ใช้ = การให้สิทธิ์ (ห้ามบันทึกรหัสผ่านหรือแฮชลง log)
    write_audit(
        db, action="user_create", user=user, entity_type="user", entity_id=new_user.id,
        new_value={
            "line_user_id": new_user.line_user_id,
            "organization_id": new_user.organization_id,
            "role": new_user.role,
            "is_active": new_user.is_active,
        },
        request=request,
    )
    db.commit()
    db.refresh(new_user)
    return UserOut(
        id=new_user.id,
        line_user_id=new_user.line_user_id,
        line_display_name=new_user.line_display_name,
        line_picture_url=new_user.line_picture_url,
        line_email=new_user.line_email,
        organization_id=new_user.organization_id,
        role=new_user.role,
        is_active=new_user.is_active,
        created_at=new_user.created_at,
    )


@app.delete("/api/users/{user_id}")
def delete_user(user_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school"))):
    """ลบผู้ใช้ — admin_school ลบได้เฉพาะ user ในรรตัวเอง"""
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    check_org_access(user, target.organization_id)
    # owner ห้ามถูกลบโดยใครนอกจากตัวเอง (และไม่ควรลบตัวเอง)
    if target.role == "owner" and user.role != "owner":
        raise HTTPException(status_code=403, detail="ไม่สามารถลบผู้ใช้ Owner ได้")
    if target.role == "owner" and target.id == user.id:
        raise HTTPException(status_code=403, detail="ไม่สามารถลบบัญชี Owner เองได้")
    # §40: ลบผู้ใช้ = เพิกถอนสิทธิ์ ต้องบันทึกก่อนลบ
    write_audit(
        db, action="user_delete", user=user, entity_type="user", entity_id=user_id,
        old_value={
            "line_user_id": target.line_user_id,
            "organization_id": target.organization_id,
            "role": target.role,
            "is_active": target.is_active,
        },
        request=request,
    )
    db.delete(target)
    db.commit()
    return {"message": "User deleted", "user_id": user_id}


@app.patch("/api/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school"))):
    target = db.get(User, user_id)
    if not target:
        raise HTTPException(status_code=404, detail="User not found")
    check_org_access(user, target.organization_id)
    data = payload.model_dump(exclude_unset=True)

    # ── Owner protection: มีแค่ owner เท่านั้นที่แก้/เปลี่ยนบทบาทของ owner ได้ ──
    if target.role == "owner" and user.role != "owner":
        raise HTTPException(status_code=403, detail="ไม่สามารถแก้ไขบัญชีเจ้าของระบบ (Owner) ได้")
    if user.role != "owner" and data.get("role") == "owner":
        raise HTTPException(status_code=403, detail="ไม่สามารถกำหนดบทบาท Owner ให้ผู้อื่นได้")

    # admin_school ไม่สามารถเปลี่ยนบทบาทตัวเอง/ผู้อื่นเป็นบทบาทระดับบริษัท และไม่สามารถย้ายคนข้ามรร
    if user.role == "admin_school":
        new_role = data.get("role", target.role)
        if new_role not in SCHOOL_ADMIN_ASSIGNABLE_ROLES:
            raise HTTPException(status_code=403, detail="ผู้ดูแลโรงเรียนไม่สามารถกำหนดบทบาทนี้ได้ (ได้แค่ ครู/นักเรียน/เจ้าหน้าที่ IT)")
        if "organization_id" in data and data["organization_id"] not in (user.organization_id, None):
            raise HTTPException(status_code=403, detail="ผู้ดูแลโรงเรียนไม่สามารถย้ายผู้ใช้ข้ามโรงเรียนได้")

    if "role" in data:
        validate_assignable_role(data["role"])

    password = data.pop("password", None)
    # username → line_user_id (ต้องไม่ซ้ำกับบัญชีอื่น)
    new_username = data.pop("username", None)
    if new_username:
        new_username = new_username.strip()
        if new_username != target.line_user_id:
            dup = db.execute(
                select(User).where(User.line_user_id == new_username, User.id != target.id)
            ).scalar_one_or_none()
            if dup:
                raise HTTPException(status_code=409, detail="ชื่อผู้ใช้นี้ถูกใช้แล้ว")
            target.line_user_id = new_username

    # §40: เปลี่ยนบทบาท/สถานะ/สังกัด ต้องบันทึก — รหัสผ่านบันทึกเพียงว่ามีการเปลี่ยน
    audited_fields = {k: v for k, v in data.items()
                      if k in ("role", "is_active", "organization_id")}
    old_value = {k: getattr(target, k, None) for k in audited_fields}
    new_value = dict(audited_fields)
    if password:
        target.password_hash = hash_password(password)
        new_value["password"] = "changed"
    for k, v in data.items():
        setattr(target, k, v)
    if new_value:
        write_audit(
            db,
            action="user_role_change" if "role" in audited_fields else "user_update",
            user=user, entity_type="user", entity_id=user_id,
            old_value=old_value or None, new_value=new_value, request=request,
        )
    db.commit()
    db.refresh(target)
    return UserOut(
        id=target.id,
        line_user_id=target.line_user_id,
        line_display_name=target.line_display_name,
        line_picture_url=target.line_picture_url,
        line_email=target.line_email,
        organization_id=target.organization_id,
        role=target.role,
        is_active=target.is_active,
        created_at=target.created_at,
    )


# ─── Auth (Login จริง) ──────────────────────────────────────────────
# ─── สมัครสมาชิก (Membership) ───────────────────────────────────────────────
# ผู้สมัครกรอกฟอร์มสาธารณะ → บันทึกเป็นคำขอสถานะ pending (ยังเข้าระบบไม่ได้)
# ผู้ดูแลอนุมัติจึงสร้างแถวใน users — ทุกคำขอถูกส่งไปต่อท้าย Google Sheet ด้วย
MEMBERSHIP_REVIEW_ROLES: tuple[str, ...] = ("owner", "super_admin", "admin", "admin_school")

#: บทบาทที่ผู้สมัครทางหน้าสาธารณะได้รับได้ — ห้ามสมัครเป็นผู้ดูแลด้วยตัวเอง
PUBLIC_SIGNUP_ROLE = "it_support"


@app.post("/api/public/register", status_code=201)
@limiter.limit("5/hour")
def public_register(request: Request, payload: MembershipApplyIn, db: Session = Depends(get_db)):
    """รับคำขอสมัครสมาชิก (ไม่ต้อง login) — ยังไม่สร้างบัญชีจนกว่าจะได้รับอนุมัติ"""
    username = payload.username.strip()
    # ใช้ข้อความเดียวกันทั้งกรณีชื่อถูกใช้แล้วและกรณีมีคำขอค้าง เพื่อไม่บอกใบ้ว่ามีบัญชีนี้อยู่
    taken = db.execute(
        select(User.id).where(User.line_user_id == username)
    ).scalar_one_or_none()
    if taken is None:
        taken = db.execute(
            select(MembershipApplication.id).where(
                MembershipApplication.username == username,
                MembershipApplication.status == MEMBERSHIP_PENDING,
            )
        ).scalar_one_or_none()
    if taken is not None:
        raise HTTPException(status_code=409, detail="ชื่อผู้ใช้นี้ใช้ไม่ได้ กรุณาเลือกชื่ออื่น")

    org_code = (payload.organization_code or "").strip() or None
    org = None
    if org_code:
        org = db.execute(
            select(Organization).where(Organization.code == org_code)
        ).scalar_one_or_none()
        if not org:
            raise HTTPException(status_code=404, detail="ไม่พบรหัสหน่วยงาน: %s" % org_code)

    row = MembershipApplication(
        username=username,
        full_name=payload.full_name.strip(),
        email=(payload.email or "").strip() or None,
        phone=(payload.phone or "").strip() or None,
        organization_id=org.id if org else None,
        organization_code=org.code if org else org_code,
        requested_role=PUBLIC_SIGNUP_ROLE,
        password_hash=hash_password(payload.password),
        note=payload.note,
        status=MEMBERSHIP_PENDING,
    )
    db.add(row)
    db.flush()  # ต้องได้ id ก่อน เพื่อใช้ใน audit log และแถวของ Google Sheet
    write_audit(
        db, action="membership_apply", user=None,
        entity_type="membership_application", entity_id=str(row.id),
        new_value={"username": username, "organization_code": row.organization_code,
                   "requested_role": row.requested_role},
        request=request,
    )
    db.commit()
    db.refresh(row)

    # Sheet เป็นช่องทางรายงานสำรอง — ส่งไม่ผ่านต้องไม่ทำให้การสมัครล้มเหลว
    if google_sheets.append_membership_row(row):
        row.sheet_synced_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)

    return {
        "id": row.id,
        "status": row.status,
        "sheet_synced": row.sheet_synced_at is not None,
        "message": "ส่งคำขอสมัครสมาชิกแล้ว รอผู้ดูแลระบบอนุมัติ",
    }


@app.get("/api/registrations", response_model=list[MembershipApplicationOut])
def list_registrations(
    status: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*MEMBERSHIP_REVIEW_ROLES)),
):
    """รายการคำขอสมัครสมาชิก — admin_school เห็นเฉพาะคำขอของโรงเรียนตัวเอง"""
    stmt = select(MembershipApplication).order_by(MembershipApplication.created_at.desc())
    if status:
        stmt = stmt.where(MembershipApplication.status == status)
    scope = visible_org_ids(user)
    if scope is not None:
        stmt = stmt.where(MembershipApplication.organization_id.in_(sorted(scope)))
    rows = db.execute(stmt.offset(offset).limit(limit)).scalars().all()
    return [MembershipApplicationOut.model_validate(r) for r in rows]


@app.post("/api/registrations/{application_id}/approve", status_code=201)
def approve_registration(
    application_id: int,
    payload: MembershipDecisionIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*MEMBERSHIP_REVIEW_ROLES)),
):
    """อนุมัติคำขอ → สร้างบัญชีผู้ใช้จริงด้วยรหัสผ่านที่ผู้สมัครตั้งไว้"""
    row = db.get(MembershipApplication, application_id)
    if not row:
        raise HTTPException(status_code=404, detail="ไม่พบคำขอสมัครสมาชิก")
    if row.status != MEMBERSHIP_PENDING:
        raise HTTPException(status_code=409, detail="คำขอนี้ถูกดำเนินการแล้ว (สถานะ %s)" % row.status)
    check_org_access(user, row.organization_id)

    org_id = payload.organization_id or row.organization_id
    if org_id is None and user.role == "admin_school":
        org_id = user.organization_id
    if org_id is not None and not db.get(Organization, org_id):
        raise HTTPException(status_code=404, detail="ไม่พบหน่วยงานที่ระบุ")
    check_org_access(user, org_id)

    role = payload.role or row.requested_role or PUBLIC_SIGNUP_ROLE
    validate_assignable_role(role)
    if user.role == "admin_school" and role not in SCHOOL_ADMIN_ASSIGNABLE_ROLES:
        raise HTTPException(status_code=403, detail="ผู้ดูแลโรงเรียนกำหนดบทบาทนี้ให้ผู้ใช้ไม่ได้")

    if db.execute(select(User.id).where(User.line_user_id == row.username)).scalar_one_or_none():
        raise HTTPException(status_code=409, detail="มีผู้ใช้ชื่อนี้ในระบบแล้ว")

    new_user = User(
        line_user_id=row.username,
        line_display_name=row.full_name,
        line_email=row.email,
        organization_id=org_id,
        role=role,
        is_active=True,
        password_hash=row.password_hash,  # ย้าย hash เดิม ไม่เคยมีรหัสผ่านดิบให้ย้าย
    )
    db.add(new_user)
    db.flush()

    row.status = MEMBERSHIP_APPROVED
    row.reviewed_by = user.id
    row.reviewed_at = datetime.now(timezone.utc)
    row.created_user_id = new_user.id
    write_audit(
        db, action="membership_approve", user=user,
        entity_type="membership_application", entity_id=str(row.id),
        old_value={"status": MEMBERSHIP_PENDING},
        new_value={"status": row.status, "user_id": new_user.id, "username": row.username,
                   "role": role, "organization_id": org_id},
        request=request,
    )
    db.commit()
    return {
        "application_id": row.id,
        "status": row.status,
        "user": {
            "id": new_user.id,
            "username": new_user.line_user_id,
            "line_display_name": new_user.line_display_name,
            "role": new_user.role,
            "organization_id": new_user.organization_id,
            "is_active": new_user.is_active,
        },
    }


@app.post("/api/registrations/{application_id}/reject", response_model=MembershipApplicationOut)
def reject_registration(
    application_id: int,
    payload: MembershipDecisionIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*MEMBERSHIP_REVIEW_ROLES)),
):
    """ปฏิเสธคำขอ — เก็บเหตุผลไว้ตรวจย้อนหลัง ไม่ลบแถวคำขอ"""
    row = db.get(MembershipApplication, application_id)
    if not row:
        raise HTTPException(status_code=404, detail="ไม่พบคำขอสมัครสมาชิก")
    if row.status != MEMBERSHIP_PENDING:
        raise HTTPException(status_code=409, detail="คำขอนี้ถูกดำเนินการแล้ว (สถานะ %s)" % row.status)
    check_org_access(user, row.organization_id)

    row.status = MEMBERSHIP_REJECTED
    row.reject_reason = (payload.reason or "").strip() or None
    row.reviewed_by = user.id
    row.reviewed_at = datetime.now(timezone.utc)
    write_audit(
        db, action="membership_reject", user=user,
        entity_type="membership_application", entity_id=str(row.id),
        old_value={"status": MEMBERSHIP_PENDING},
        new_value={"status": row.status, "username": row.username,
                   "reason": row.reject_reason},
        request=request,
    )
    db.commit()
    db.refresh(row)
    return MembershipApplicationOut.model_validate(row)


@app.post("/api/auth/login")
@limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    """Login ด้วย username (line_user_id) + password"""
    user = db.execute(
        select(User).where(User.line_user_id == payload.username)
    ).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        # §40/§39: บันทึก login ที่ล้มเหลว ไว้ตรวจพฤติกรรมเดารหัสผ่าน
        write_audit(
            db, action="login_failed", user=user, entity_type="user",
            entity_id=getattr(user, "id", None),
            new_value={"username": payload.username[:128],
                       "reason": "user_not_found" if not user else "bad_password"},
            request=request,
        )
        db.commit()
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    if not user.is_active:
        # §40: บัญชีถูกปิดแล้วยังพยายามเข้า — ถือเป็นเหตุการณ์ที่ต้องตรวจสอบ
        write_audit(
            db, action="login_failed", user=user, entity_type="user", entity_id=user.id,
            new_value={"username": payload.username[:128], "reason": "inactive"},
            request=request,
        )
        db.commit()
        raise HTTPException(status_code=403, detail="บัญชีถูกปิดใช้งาน")

    if user.role in RETIRED_ROLES:
        # §40: บัญชีบทบาทที่ยกเลิกแล้วพยายามเข้าระบบ — บันทึกไว้ตรวจสอบ
        write_audit(
            db, action="login_failed", user=user, entity_type="user", entity_id=user.id,
            new_value={"username": payload.username[:128],
                       "reason": "retired_role", "role": user.role},
            request=request,
        )
        db.commit()
        raise HTTPException(
            status_code=403,
            detail=(
                "บทบาท ครู/นักเรียน ถูกยกเลิกแล้ว — บัญชีนี้เข้าระบบไม่ได้ "
                "กรุณาแจ้งซ่อมผ่านหน้าแจ้งซ่อม หรือสแกน QR ที่ตัวเครื่อง"
            ),
        )

    user.last_login_at = datetime.now(timezone.utc)
    write_audit(
        db, action="login", user=user, entity_type="user", entity_id=user.id,
        new_value={"role": user.role, "organization_id": user.organization_id},
        request=request,
    )
    db.commit()

    org = db.get(Organization, user.organization_id) if user.organization_id else None
    return {
        "token": create_token(user),
        "user": {
            "id": user.id,
            "line_user_id": user.line_user_id,
            "line_display_name": user.line_display_name,
            "line_picture_url": user.line_picture_url,
            "line_email": user.line_email,
            "organization_id": user.organization_id,
            "role": user.role,
            "is_active": user.is_active,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "created_at": user.created_at.isoformat(),
            "organization": {
                "id": org.id,
                "code": org.code,
                "name": org.name,
                "short_name": org.short_name,
                "timezone": org.timezone,
            } if org else None,
        }
    }


@app.get("/api/auth/me")
def auth_me(user: User = Depends(get_current_user), db: Session = Depends(get_db)):
    """ดูข้อมูลผู้ใช้ปัจจุบันจาก token (ใช้ตอนเปิดแอปเพื่อ validate + โหลด user)"""
    org = db.get(Organization, user.organization_id) if user.organization_id else None
    return {
        "user": {
            "id": user.id,
            "line_user_id": user.line_user_id,
            "line_display_name": user.line_display_name,
            "line_picture_url": user.line_picture_url,
            "line_email": user.line_email,
            "organization_id": user.organization_id,
            "role": user.role,
            "is_active": user.is_active,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "created_at": user.created_at.isoformat(),
            "organization": {
                "id": org.id,
                "code": org.code,
                "name": org.name,
                "short_name": org.short_name,
                "timezone": org.timezone,
            } if org else None,
        }
    }


@app.patch("/api/auth/profile")
def update_my_profile(
    payload: UserUpdate,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """ผู้ใช้แก้โปรไฟล์ตัวเอง: ชื่อ, อีเมล, รูปภาพ, รหัสผ่าน (ไม่เปลี่ยนบทบาท/โรงเรียน/สถานะ)"""
    data = payload.model_dump(exclude_unset=True)
    # ห้ามแก้สิทธิ์ผ่าน endpoint นี้
    data.pop("role", None)
    data.pop("is_active", None)
    data.pop("organization_id", None)

    # เปลี่ยนชื่อผู้ใช้ที่ใช้ login ได้ แต่ต้องไม่ซ้ำกับบัญชีอื่น
    new_username = data.pop("username", None)
    if new_username:
        new_username = new_username.strip()
        if new_username != user.line_user_id:
            dup = db.execute(
                select(User).where(User.line_user_id == new_username, User.id != user.id)
            ).scalar_one_or_none()
            if dup:
                raise HTTPException(status_code=409, detail="ชื่อผู้ใช้นี้ถูกใช้แล้ว")
            user.line_user_id = new_username
    password = data.pop("password", None)
    if password:
        user.password_hash = hash_password(password)
    for k, v in data.items():
        setattr(user, k, v)
    db.commit()
    db.refresh(user)

    org = db.get(Organization, user.organization_id) if user.organization_id else None
    return {
        "token": create_token(user),
        "user": {
            "id": user.id,
            "line_user_id": user.line_user_id,
            "line_display_name": user.line_display_name,
            "line_picture_url": user.line_picture_url,
            "line_email": user.line_email,
            "organization_id": user.organization_id,
            "role": user.role,
            "is_active": user.is_active,
            "last_login_at": user.last_login_at.isoformat() if user.last_login_at else None,
            "created_at": user.created_at.isoformat(),
            "organization": {
                "id": org.id,
                "code": org.code,
                "name": org.name,
                "short_name": org.short_name,
                "timezone": org.timezone,
            } if org else None,
        },
    }


@app.get("/api/stats/devices")
def get_device_stats(db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user_optional)):
    """Dashboard stats: นับ ticket ตามประเภทอุปกรณ์, สถานะ, ความเร่งด่วน"""
    scope = visible_org_ids(user) if user else None
    if scope is not None and not scope:
        return {"by_type": [], "by_status": [], "by_priority": [], "devices_by_status": []}
    params: dict = {}
    scope_where = ""
    dev_scope_where = ""
    _oids = bindparam("oids", expanding=True)
    if scope is not None:
        params["oids"] = tuple(scope)
        scope_where = " AND d.organization_id IN :oids"
        dev_scope_where = " AND d.organization_id IN :oids"

    def _q(sql: str):
        stmt = text(sql)
        return db.execute(stmt.bindparams(_oids), params) if scope is not None else db.execute(stmt)

    by_type = _q(f"""
        SELECT d.device_type, COUNT(rt.id) as count
        FROM repair_tickets rt
        JOIN devices d ON rt.device_id = d.device_id
        WHERE 1=1 {scope_where}
        GROUP BY d.device_type
        ORDER BY count DESC
    """).fetchall()

    by_status = _q(f"""
        SELECT rt.status, COUNT(*) as count
        FROM repair_tickets rt
        JOIN devices d ON d.device_id = rt.device_id
        WHERE 1=1 {scope_where}
        GROUP BY rt.status
        ORDER BY count DESC
    """).fetchall()

    by_priority = _q(f"""
        SELECT rt.priority, COUNT(*) as count
        FROM repair_tickets rt
        JOIN devices d ON d.device_id = rt.device_id
        WHERE 1=1 {scope_where}
        GROUP BY rt.priority
        ORDER BY count DESC
    """).fetchall()

    devices_by_status = _q(f"""
        SELECT d.status, COUNT(*) as count
        FROM devices d
        WHERE 1=1 {dev_scope_where}
        GROUP BY d.status
        ORDER BY count DESC
    """).fetchall()

    return {
        "by_type": [{"device_type": r.device_type, "count": r.count} for r in by_type],
        "by_status": [{"status": r.status, "count": r.count} for r in by_status],
        "by_priority": [{"priority": r.priority, "count": r.count} for r in by_priority],
        "devices_by_status": [{"status": r.status, "count": r.count} for r in devices_by_status],
    }

@app.get("/api/organizations")
def list_organizations(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """รายการโรงเรียน — admin_school เห็นเฉพาะรรตัวเอง"""
    scope = visible_org_ids(user)
    stmt = (
        select(
            Organization.id,
            Organization.code,
            Organization.name,
            Organization.short_name,
            Organization.timezone,
            func.count(func.distinct(Device.device_id)).label("device_count"),
            func.count(func.distinct(RepairTicket.ticket_id)).label("ticket_count"),
        )
        .outerjoin(Device, Device.organization_id == Organization.id)
        .outerjoin(RepairTicket, RepairTicket.device_id == Device.device_id)
        .group_by(Organization.id)
        .order_by(Organization.name)
    )
    if scope is not None:
        if not scope:
            return []  # scope ว่าง → ไม่เห็นข้อมูล
        stmt = stmt.where(Organization.id.in_(scope))
    rows = db.execute(stmt).fetchall()
    return [
        {
            "id": r.id,
            "code": r.code,
            "name": r.name,
            "short_name": r.short_name,
            "timezone": r.timezone,
            "device_count": r.device_count,
            "ticket_count": r.ticket_count,
        }
        for r in rows
    ]


@app.post("/api/organizations", status_code=201)
def create_organization(payload: OrgCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin"))):
    """เพิ่มโรงเรียนใหม่ (super_admin)"""
    exists = db.execute(
        select(Organization).where(
            (Organization.code == payload.code) | (Organization.name == payload.name)
        )
    ).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="รหัสหรือชื่อโรงเรียนซ้ำ")

    org = Organization(
        code=payload.code,
        name=payload.name,
        short_name=payload.short_name,
        timezone=payload.timezone,
    )
    db.add(org)
    db.commit()
    db.refresh(org)
    return {
        "id": org.id,
        "code": org.code,
        "name": org.name,
        "short_name": org.short_name,
        "timezone": org.timezone,
        "device_count": 0,
        "ticket_count": 0,
    }


@app.post("/api/organizations/{org_id}/rooms", status_code=201)
def create_room(org_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school"))):
    """เพิ่มห้องใหม่ในโรงเรียน"""
    check_org_access(user, org_id)
    org = db.execute(select(Organization).where(Organization.id == org_id)).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")
    room = Room(
        organization_id=org_id,
        code=payload.get("code", ""),
        name=payload.get("name", ""),
        building=payload.get("building"),
        floor=payload.get("floor"),
    )
    db.add(room)
    db.commit()
    db.refresh(room)
    return {"id": room.id, "code": room.code, "name": room.name, "building": room.building, "floor": room.floor}


@app.delete("/api/organizations/{org_id}")
def delete_organization(org_id: int, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin"))):
    """Delete only a truly empty school; never cascade away unrelated production history."""
    org = db.execute(select(Organization).where(Organization.id == org_id)).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    linked = []
    for table in Base.metadata.tables.values():
        for column in table.columns:
            if any(fk.target_fullname == "organizations.id" for fk in column.foreign_keys):
                if db.execute(select(func.count()).select_from(table).where(column == org_id)).scalar_one():
                    linked.append(table.name)
    if db.execute(select(func.count(DeletedRecord.id)).where(DeletedRecord.organization_id == org_id)).scalar_one():
        linked.append("deleted_records")
    if linked:
        raise HTTPException(status_code=409, detail="โรงเรียนนี้ยังมีข้อมูลผูกอยู่ จึงลบไม่ได้: " + ", ".join(linked))
    write_audit(db, action="organization_delete", user=user, entity_type="organization",
                entity_id=org_id, old_value={"code": org.code, "name": org.name}, request=request)
    db.delete(org)
    db.commit()
    return {"message": "Organization deleted", "organization_id": org_id, "code": org.code}


@app.get("/api/organizations/{org_id}/stats")
def get_org_stats(org_id: int, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user_optional)):
    """สถิติของโรงเรียนเดียว (สำหรับหน้า admin ดูรายโรงเรียน)"""
    if user:
        check_org_access(user, org_id)
    org = db.execute(select(Organization).where(Organization.id == org_id)).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    ticket_total = db.execute(
        text("SELECT COUNT(*) FROM repair_tickets t JOIN devices d ON d.device_id = t.device_id WHERE d.organization_id = :oid"),
        {"oid": org_id},
    ).scalar_one()
    device_total = db.execute(
        text("SELECT COUNT(*) FROM devices WHERE organization_id = :oid"),
        {"oid": org_id},
    ).scalar_one()
    open_tickets = db.execute(
        text("SELECT COUNT(*) FROM repair_tickets t JOIN devices d ON d.device_id = t.device_id WHERE d.organization_id = :oid AND t.status IN ('new','assigned','in_progress','pending')"),
        {"oid": org_id},
    ).scalar_one()
    by_status = {
        r[0]: r[1]
        for r in db.execute(
            text("SELECT t.status, COUNT(*) FROM repair_tickets t JOIN devices d ON d.device_id = t.device_id WHERE d.organization_id = :oid GROUP BY t.status"),
            {"oid": org_id},
        ).fetchall()
    }
    return {
        "organization_id": org.id,
        "name": org.name,
        "code": org.code,
        "total_tickets": ticket_total,
        "total_devices": device_total,
        "open_tickets": open_tickets,
        "by_status": by_status,
    }


@app.get("/api/tickets", response_model=list[TicketOut])
def list_tickets(
    device_type: Optional[str] = Query(None),
    device_category: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    organization_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    # ดึง device_type มาด้วย — หน้าเว็บใช้แสดงและใช้เป็นตัวกรองประเภทอุปกรณ์
    stmt = (
        select(RepairTicket, Device, Organization)
        .join(Device, Device.device_id == RepairTicket.device_id)
        .join(Organization, Organization.id == Device.organization_id)
        # room ถูกใช้ประกอบชื่ออุปกรณ์ (device_display_label) - preload กัน N+1
        .options(selectinload(Device.room))
        .order_by(RepairTicket.created_at.desc(), RepairTicket.ticket_id.desc())
    )
    if status:
        stmt = stmt.where(RepairTicket.status == status)
    if priority:
        stmt = stmt.where(RepairTicket.priority == priority)
    if device_id:
        stmt = stmt.where(RepairTicket.device_id == device_id)
    if device_type:
        stmt = stmt.where(Device.device_type == device_type)
    if device_category:
        types = DEVICE_CATEGORY_TYPES.get(device_category)
        if not types:
            return []  # หมวดที่ไม่รู้จัก → ไม่เดา คืนว่าง
        stmt = stmt.where(Device.device_type.in_(types))
    if organization_id:
        stmt = stmt.where(Device.organization_id == organization_id)
    # ─── Role-based visibility: admin_school/it_support(มีสังกัด)/teacher/student เห็นเฉพาะรรตัวเอง ──
    if user:
        scope = visible_org_ids(user)
        if scope is not None:
            if not scope:
                return []  # scope ว่าง → ไม่เห็นข้อมูล
            stmt = stmt.where(Device.organization_id.in_(scope))
    stmt = stmt.offset(offset).limit(limit)

    rows = db.execute(stmt).all()
    result: list[TicketOut] = []
    for t, device, org in rows:
        result.append(TicketOut(
            id=t.id,
            ticket_id=t.ticket_id,
            device_id=t.device_id,
            title=t.title,
            # เดิมใส่ device_type จากพารามิเตอร์ตัวกรอง - ถ้าไม่ได้กรอง ทุกใบจะเป็น None
            # หน้าเว็บจึงสร้างตัวกรองประเภท/หมวดหมู่จากข้อมูลจริงไม่ได้
            device_type=device.device_type if device else None,
            device_category=device_category_of(
                device.device_type if device else None
            ),
            device_label=device_display_label(device),
            organization_id=org.id if org else None,
            organization_code=org.code if org else None,
            organization_name=(org.short_name or org.name) if org else None,
            description=t.description,
            reporter_name=t.reporter_name,
            reporter_email=t.reporter_email,
            reporter_phone=t.reporter_phone,
            reporter_type=t.reporter_type,
            priority=t.priority,
            status=t.status,
            assigned_to=t.assigned_to,
            channel=t.channel,
            symptom_code=t.symptom_code,
            ai_category=t.ai_category,
            attachments=json.loads(t.attachments) if t.attachments else None,
            sla_due_at=t.sla_due_at,
            sla_met=t.sla_met,
            escalation_level=t.escalation_level,
            resolved_at=t.resolved_at,
            root_cause=t.root_cause,
            solution=t.solution,
            rating=t.rating,
            feedback=t.feedback,
            closed_at=t.closed_at,
            scan_gps_lat=(
                float(t.scan_gps_lat) if t.scan_gps_lat is not None else None
            ),
            scan_gps_lng=(
                float(t.scan_gps_lng) if t.scan_gps_lng is not None else None
            ),
            scan_timestamp=t.scan_timestamp,
            resolution_notes=t.resolution_notes,
            created_at=t.created_at,
            updated_at=t.updated_at,
        ))
    return result


@app.get("/api/tickets/{ticket_id}", response_model=TicketOut)
def get_ticket(ticket_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = db.execute(
        select(RepairTicket)
        .options(selectinload(RepairTicket.device), selectinload(RepairTicket.updates))
        .where(RepairTicket.ticket_id == ticket_id)
    ).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    check_ticket_access(db, user, ticket)

    out = TicketOut(
        # เดิม get_ticket ไม่ส่ง device_type ทั้งที่ list_tickets ส่ง — หน้ารายละเอียด
        # จึงแสดงหมวดหมู่/ชื่ออุปกรณ์ไม่ได้
        device_type=ticket.device.device_type if ticket.device else None,
        device_category=device_category_of(
            ticket.device.device_type if ticket.device else None
        ),
        device_label=device_display_label(ticket.device),
        organization_id=ticket.device.organization_id if ticket.device else None,
        organization_code=(
            ticket.device.organization.code
            if ticket.device and ticket.device.organization
            else None
        ),
        organization_name=(
            (ticket.device.organization.short_name or ticket.device.organization.name)
            if ticket.device and ticket.device.organization
            else None
        ),
        id=ticket.id,
        ticket_id=ticket.ticket_id,
        device_id=ticket.device_id,
        title=ticket.title,
        description=ticket.description,
        reporter_name=ticket.reporter_name,
        reporter_email=ticket.reporter_email,
        reporter_phone=ticket.reporter_phone,
        reporter_type=ticket.reporter_type,
        priority=ticket.priority,
        status=ticket.status,
        assigned_to=ticket.assigned_to,
        channel=ticket.channel,
        symptom_code=ticket.symptom_code,
        ai_category=ticket.ai_category,
        attachments=json.loads(ticket.attachments) if ticket.attachments else None,
        root_cause=ticket.root_cause,
        solution=ticket.solution,
        sla_due_at=ticket.sla_due_at,
        sla_met=ticket.sla_met,
        escalation_level=ticket.escalation_level,
        resolved_at=ticket.resolved_at,
        rating=ticket.rating,
        feedback=ticket.feedback,
        closed_at=ticket.closed_at,
        scan_gps_lat=(float(ticket.scan_gps_lat) if ticket.scan_gps_lat is not None else None),
        scan_gps_lng=(float(ticket.scan_gps_lng) if ticket.scan_gps_lng is not None else None),
        scan_timestamp=ticket.scan_timestamp,
        resolution_notes=ticket.resolution_notes,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )
    out_dict = out.model_dump()
    out_dict["device_info"] = {
        "device_category": device_category_of(
            ticket.device.device_type if ticket.device else None
        ),
        "device_label": device_display_label(ticket.device),
        "device_id": ticket.device.device_id if ticket.device else None,
        "device_type": ticket.device.device_type if ticket.device else None,
        "brand": ticket.device.brand if ticket.device else None,
        "model": ticket.device.model if ticket.device else None,
        "room_name": ticket.device.room.name if ticket.device and ticket.device.room else None,
        "organization_name": ticket.device.organization.name if ticket.device and ticket.device.organization else None,
    } if ticket.device else None
    out_dict["history"] = [
        {
            "id": u.id,
            "from_status": u.from_status,
            "to_status": u.to_status,
            "note": u.note,
            "author_name": u.author_name,
            "author_role": u.author_role,
            "created_at": u.created_at,
        }
        for u in ticket.updates
    ]
    return out_dict

@app.patch("/api/tickets/{ticket_id}/status")
def update_ticket_status(
    ticket_id: str,
    payload: StatusUpdateRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
    x_n8n_secret: Optional[str] = Header(None),
):
    # รับได้ 2 ทาง: ผู้ใช้ที่ login (ต้องมีบทบาทถูก) หรือ n8n automation (แนบ X-N8N-Secret)
    is_n8n = bool(N8N_SHARED_SECRET and x_n8n_secret
                  and hmac.compare_digest(N8N_SHARED_SECRET, x_n8n_secret))
    if not is_n8n:
        if user is None:
            raise HTTPException(status_code=401, detail="กรุณาเข้าสู่ระบบก่อน (ไม่พบ token)")
        if user.role not in ("owner", "super_admin", "admin", "admin_school", "it_support"):
            raise HTTPException(status_code=403, detail="คุณไม่มีสิทธิ์ทำรายการนี้")
    ticket = db.execute(
        select(RepairTicket).where(RepairTicket.ticket_id == ticket_id)
    ).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    if not is_n8n:
        check_ticket_access(db, user, ticket)

    current = ticket.status
    target = payload.status

    apply_transition(db, ticket, target, force=payload.force,
                     author_name=payload.author_name,
                     author_role=payload.author_role, note=payload.note)

    if target in (TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED):
        if ticket.closed_at is None:
            ticket.closed_at = datetime.now(timezone.utc)
        if target == TicketStatus.RESOLVED and ticket.resolved_at is None:
            ticket.resolved_at = datetime.now(timezone.utc)
    if target == TicketStatus.ASSIGNED and not ticket.assigned_to:
        ticket.assigned_to = payload.author_name or ("n8n automation" if is_n8n else "Unassigned")

    # §40: เปลี่ยน Status / ปิดงาน ต้องบันทึก (เรียกจาก n8n จะไม่มี user → user=None)
    write_audit(
        db,
        action=("ticket_close"
                if target in (TicketStatus.CLOSED, TicketStatus.CANCELLED)
                else "ticket_status_change"),
        user=user, entity_type="ticket", entity_id=ticket.ticket_id,
        old_value={"status": current},
        new_value={"status": target, "note": payload.note,
                   "via": "n8n" if is_n8n else "user"},
        request=request,
    )
    db.commit()
    db.refresh(ticket)

    # แจ้ง n8n (fire-and-forget) — เปลี่ยนสถานะ
    payload_data = _ticket_event_payload(ticket)
    payload_data["from_status"] = current
    payload_data["to_status"] = target
    _notify_n8n("ticket.status_changed", payload_data)
    if target in (TicketStatus.RESOLVED, TicketStatus.CLOSED):
        from app.ticket_rating_invite import invite_staff_rating
        invite_staff_rating(db, ticket)

    return {
        "ticket_id": ticket.ticket_id,
        "from_status": current,
        "to_status": target,
        "message": "Status updated",
    }


@app.delete("/api/tickets/{ticket_id}")
def delete_ticket(ticket_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """ลบ ticket + ประวัติทั้งหมด (admin / admin_school / IT support)"""
    ticket = db.execute(
        select(RepairTicket).where(RepairTicket.ticket_id == ticket_id)
    ).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    check_ticket_access(db, user, ticket)

    updates = db.execute(select(TicketUpdate).where(TicketUpdate.ticket_id == ticket.id)).scalars().all()
    comments = db.execute(select(TicketComment).where(TicketComment.ticket_id == ticket_id)).scalars().all()
    attachments = db.execute(select(TicketAttachment).where(TicketAttachment.ticket_id == ticket_id)).scalars().all()
    db.add(DeletedRecord(
        entity_type="ticket", entity_id=ticket_id, organization_id=ticket.organization_id,
        payload=json.dumps({"ticket": _recovery_snapshot(ticket),
                            "updates": [_recovery_snapshot(row) for row in updates],
                            "comments": [_recovery_snapshot(row) for row in comments],
                            "attachments": [_recovery_snapshot(row) for row in attachments]}, ensure_ascii=False, default=str),
        deleted_by=user.id,
    ))
    write_audit(db, action="ticket_delete", user=user, entity_type="ticket", entity_id=ticket_id,
                old_value={"ticket_id": ticket_id, "status": ticket.status}, request=request)
    # ลบ updates ก่อน (กัน FK constraint)
    db.execute(
        text("DELETE FROM ticket_updates WHERE ticket_id = :tid"),
        {"tid": ticket.id},
    )
    db.execute(text("DELETE FROM ticket_comments WHERE ticket_id = :tid"), {"tid": ticket_id})
    db.execute(text("DELETE FROM ticket_attachments WHERE ticket_id = :tid"), {"tid": ticket_id})
    db.delete(ticket)
    db.commit()
    return {"message": "Ticket moved to recoverable history", "ticket_id": ticket_id}


@app.get("/api/tickets/{ticket_id}/history", response_model=list[TicketUpdateOut])
def ticket_history(ticket_id: str, db: Session = Depends(get_db)):
    ticket = db.execute(
        select(RepairTicket).where(RepairTicket.ticket_id == ticket_id)
    ).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")

    updates = (
        db.execute(
            select(TicketUpdate)
            .where(TicketUpdate.ticket_id == ticket.id)
            .order_by(TicketUpdate.created_at.desc())
        )
        .scalars()
        .all()
    )
    return [
        TicketUpdateOut(
            id=u.id,
            from_status=u.from_status,
            to_status=u.to_status,
            note=u.note,
            author_name=u.author_name,
            author_role=u.author_role,
            created_at=u.created_at,
        )
        for u in updates
    ]


# ---------------------------------------------------------------------------
# Dashboard stats
# ---------------------------------------------------------------------------


@app.get("/api/stats")
def get_stats(db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user_optional)):
    scope = visible_org_ids(user) if user else None
    # scope ว่าง (เช่น admin_school ยังไม่มีสังกัด) → ไม่ให้เห็นข้อมูลบริษัท
    if scope is not None and not scope:
        return {
            "total_tickets": 0, "total_devices": 0, "open": 0, "assigned": 0, "in_progress": 0,
            "pending": 0, "waiting_parts": 0, "waiting_user": 0,
            "resolved": 0, "closed": 0, "cancelled": 0, "new": 0,
            "low": 0, "normal": 0, "high": 0, "critical": 0,
            "by_type": {}, "by_status": {}, "by_priority": {}, "devices_by_status": {},
            "self_service_total": 0, "recent_tickets": [],
        }
    params: dict = {}
    if scope is not None:
        params["oids"] = tuple(scope)
    # หมายเหตุ: ต้องใช้ bindparam(..., expanding=True) — ถ้าใส่ tuple ตรง ๆ
    # SQLAlchemy จะไม่ขยาย IN ให้ (ใช้ได้แค่กรณีมีค่าเดียว)
    oids_param = bindparam("oids", expanding=True)

    def _run(q: str):
        stmt = text(q)
        return db.execute(stmt.bindparams(oids_param), params) if scope is not None else db.execute(stmt)

    total = _run("SELECT COUNT(*) FROM repair_tickets t LEFT JOIN devices d ON d.device_id=t.device_id" + (" WHERE d.organization_id IN :oids" if scope is not None else "")).scalar_one()
    total_devices = _run("SELECT COUNT(*) FROM devices d" + (" WHERE d.organization_id IN :oids" if scope is not None else "")).scalar_one()

    def count_by(col, table, where=None):
        # ต้องอ้างชื่อคอลัมน์แบบมีชื่อตาราง — หลัง JOIN มีคอลัมน์ชื่อซ้ำ (status) จะกำกวม
        q = f"SELECT {table}.{col}, COUNT(*) FROM {table}"
        joins = ""
        if scope is not None:
            if table == "repair_tickets":
                joins = " LEFT JOIN devices d ON d.device_id = repair_tickets.device_id"
                w = " WHERE d.organization_id IN :oids"
            elif table == "devices":
                joins = ""
                w = " WHERE devices.organization_id IN :oids"
            else:
                joins = ""
                w = ""
        else:
            w = ""
        if where:
            w = (w + " AND " + where) if w else (" WHERE " + where)
        q += joins + w
        q += f" GROUP BY {table}.{col}"
        return {r[0]: r[1] for r in _run(q).fetchall()}

    by_status = count_by("status", "repair_tickets")
    by_priority = count_by("priority", "repair_tickets")
    by_type = count_by("device_type", "devices")
    devices_by_status = count_by("status", "devices")

    def st(s):
        return by_status.get(s, 0)

    # self_service_cases ไม่มี organization_id — นับผ่าน device
    if scope is not None:
        self_service_total = _run(
            "SELECT COUNT(*) FROM self_service_cases s JOIN devices d ON d.device_id = s.device_id "
            "WHERE d.organization_id IN :oids").scalar_one()
    else:
        self_service_total = db.execute(text("SELECT COUNT(*) FROM self_service_cases")).scalar_one()

    recent_where = (" WHERE d.organization_id IN :oids" if scope is not None else "")
    recent = _run("""
        SELECT t.ticket_id, t.title, t.status, t.priority, t.created_at,
               d.device_type, r.name AS room_name, o.name AS organization_name
        FROM repair_tickets t
        LEFT JOIN devices d ON d.device_id = t.device_id
        LEFT JOIN rooms r ON r.id = d.room_id
        LEFT JOIN organizations o ON o.id = d.organization_id
    """ + recent_where + """
        ORDER BY t.created_at DESC
        LIMIT 10
    """).fetchall()

    return {
        "total_tickets": total,
        "total_devices": total_devices,
        "open": st("new"),
        "assigned": st("assigned"),
        "in_progress": st("in_progress"),
        "pending": st("pending"),
        "waiting_parts": st("waiting_parts"),
        "waiting_user": st("waiting_user"),
        "resolved": st("resolved"),
        "closed": st("closed"),
        "cancelled": st("cancelled"),
        "new": st("new"),
        "low": by_priority.get("low", 0),
        "normal": by_priority.get("normal", 0),
        "high": by_priority.get("high", 0),
        "critical": by_priority.get("critical", 0),
        "by_type": by_type,
        "by_status": by_status,
        "by_priority": by_priority,
        "devices_by_status": devices_by_status,
        "self_service_total": self_service_total,
        "recent_tickets": [
            {
                "ticket_id": r.ticket_id,
                "title": r.title,
                "status": r.status,
                "priority": r.priority,
                "created_at": r.created_at,
                "device_type": r.device_type,
                "room_name": r.room_name,
                "organization_name": r.organization_name,
            }
            for r in recent
        ],
    }


# ─── Uploads / ไฟล์แนบ (TOR 1.5.2 + Blueprint §41 File Attachment Security) ──
# การตรวจไฟล์ (MIME + นามสกุล + ลายเซ็นเนื้อไฟล์ + ขนาด) และการตั้งชื่อเป็น UUID
# อยู่ใน app/storage.py ทั้งหมด — ที่นี่ทำแค่รับไฟล์และคุมสิทธิ์ตอนดาวน์โหลด
from fastapi import File, UploadFile
from fastapi.responses import FileResponse, Response

from app.storage import (
    MAX_UPLOAD_BYTES,
    UPLOAD_DIR,  # noqa: F401 — คงชื่อไว้ให้โค้ด/สคริปต์เดิมที่อ้าง main.UPLOAD_DIR
    is_inline_viewable,
    is_servable_upload_name,
    local_upload_path,
    mime_for_name,
    read_cloud_upload,
    save_upload,
    sniff_ext,
    verify_upload_signature,
)


async def _store_upload(file: UploadFile, *, public: bool = False) -> dict:
    """Read and validate an upload with a bounded request body."""
    public_limit = 5 * 1024 * 1024
    max_bytes = public_limit if public else MAX_UPLOAD_BYTES
    content = await file.read(max_bytes + 1)
    if len(content) > max_bytes:
        limit_mb = 5 if public else max(1, MAX_UPLOAD_BYTES // (1024 * 1024))
        raise HTTPException(status_code=413, detail=f"ไฟล์เกิน {limit_mb} MB")
    if public and sniff_ext(content) not in {".jpg", ".png", ".webp", ".gif", ".heic"}:
        raise HTTPException(status_code=415, detail="แบบฟอร์มสาธารณะรับเฉพาะไฟล์รูปภาพ")
    return save_upload(content, file.filename or "image.jpg", file.content_type)


@app.post("/api/uploads", status_code=201)
@limiter.limit("30/minute")
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    user: User = Depends(get_current_user),
):
    """อัปโหลดไฟล์แนบ (jpg/png/pdf/webp/gif/heic) — ใช้กับฟอร์มแจ้งซ่อม + PM

    ไฟล์ถูกเปลี่ยนชื่อเป็น UUID และ URL ที่คืนไปมีลายเซ็นกำกับ (§41 Access)
    โหมด local: เขียน disk แล้วเสิร์ฟผ่าน GET /uploads/{name}
    ต้องล็อกอินก่อนอัปโหลด เพื่อกันการใช้พื้นที่เก็บไฟล์เป็นช่องทาง public upload
    """
    return await _store_upload(file)


@app.post("/api/public/uploads", status_code=201)
@limiter.limit("5/hour")
async def upload_public_image(request: Request, file: UploadFile = File(...)):
    """รับรูปประกอบคำร้องสาธารณะโดยไม่ต้องมีบัญชี จำกัดขนาดและจำนวนตาม IP."""
    return await _store_upload(file, public=True)


@app.get("/uploads/{name}")
def download_upload(
    name: str,
    s: Optional[str] = Query(None),
):
    """ส่งไฟล์แนบ (โหมด local) — §41 Access: ตรวจสิทธิ์ก่อนดาวน์โหลด

    ต้องมีลายเซ็น ?s= ที่ถูกต้องจาก URL ที่ระบบออกให้ (ใช้ใน <img> และใน LINE ได้)
    """
    if not is_servable_upload_name(name):
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์")
    if not verify_upload_signature(name, s):
        raise HTTPException(status_code=403, detail="ไม่มีสิทธิ์เข้าถึงไฟล์นี้")
    disposition = "inline" if is_inline_viewable(name) else "attachment"
    if os.environ.get("STORAGE_BACKEND", "local").lower() == "cloud":
        content = read_cloud_upload(name)
        if content is None:
            raise HTTPException(status_code=404, detail="ไม่พบไฟล์")
        return Response(
            content=content,
            media_type=mime_for_name(name),
            headers={
                "Content-Disposition": f'{disposition}; filename="{name}"',
                "X-Content-Type-Options": "nosniff",
                "Cache-Control": "private, max-age=3600",
            },
        )
    path = local_upload_path(name)
    if not path or not os.path.isfile(path):
        raise HTTPException(status_code=404, detail="ไม่พบไฟล์")
    # pdf บังคับดาวน์โหลด ไม่ให้เปิดใน origin เดียวกับเว็บ; รูปแสดง inline ได้
    return FileResponse(
        path,
        media_type=mime_for_name(name),
        headers={
            "Content-Disposition": f'{disposition}; filename="{name}"',
            "X-Content-Type-Options": "nosniff",
            "Cache-Control": "private, max-age=3600",
        },
    )


# ─── Superadmin chatbot studio: reviewed Q&A, runtime guidance, ratings ──────

_CHATBOT_MANAGER = require_roles("owner", "super_admin")


def _is_ratings_viewer(user: User) -> bool:
    # Owner oversees service quality; the super_admin seat remains designated.
    if user.role == "owner":
        return True
    allowed_id = os.environ.get("RATINGS_VIEWER_USERNAME", "iwasuperadmin").strip().casefold()
    return bool(allowed_id and user.role == "super_admin"
                and (user.line_user_id or "").strip().casefold() == allowed_id)


def require_ratings_viewer(user: User = Depends(get_current_user)) -> User:
    if not _is_ratings_viewer(user):
        raise HTTPException(status_code=403, detail="ผลประเมินเปิดเฉพาะ owner และบัญชี superadmin ที่กำหนด")
    return user


@app.get("/api/chatbot/manage/access")
def chatbot_manage_access(user: User = Depends(_CHATBOT_MANAGER)):
    return {"can_view_ratings": _is_ratings_viewer(user)}


class ChatbotKnowledgeInput(BaseModel):
    question: str = Field(..., min_length=3, max_length=500)
    answer: str = Field(..., min_length=3, max_length=3000)
    aliases: list[str] = Field(default_factory=list, max_length=12)
    source_label: Optional[str] = Field(default=None, max_length=160)
    source_url: Optional[str] = Field(default=None, max_length=500)
    is_published: bool = False


def _knowledge_out(row: ChatbotKnowledgeEntry) -> dict:
    return {"id": row.id, "question": row.question, "answer": row.answer,
            "aliases": json.loads(row.aliases or "[]"), "is_published": row.is_published,
            "source_label": row.source_label, "source_url": row.source_url,
            "updated_at": row.updated_at}


def _validate_knowledge(payload: ChatbotKnowledgeInput, db: Session, exclude_id: int | None = None) -> list[str]:
    from app.chatbot_helpers import normalize_question
    import re
    question = payload.question.strip()
    aliases = [alias.strip() for alias in payload.aliases]
    if len(question) < 3 or len(payload.answer.strip()) < 3:
        raise HTTPException(status_code=422, detail="กรอกคำถามและคำตอบให้ครบอย่างน้อย 3 ตัวอักษร")
    if payload.source_url and not payload.source_url.strip().lower().startswith("https://"):
        raise HTTPException(status_code=422, detail="ลิงก์แหล่งข้อมูลต้องขึ้นต้นด้วย https://")
    if any(not alias or len(alias) > 500 for alias in aliases):
        raise HTTPException(status_code=422, detail="คำถามทางเลือกต้องไม่ว่างและยาวไม่เกิน 500 ตัวอักษร")
    variants = [question, *aliases]
    keys = [normalize_question(value) for value in variants]
    if not all(keys):
        raise HTTPException(status_code=422, detail="คำถามต้องมีข้อความที่ค้นหาได้")
    if len(set(keys)) != len(keys):
        raise HTTPException(status_code=422, detail="คำถามหลักและคำถามทางเลือกซ้ำกัน")
    # These facts must be computed from their live workflow, never edited Q&A.
    if payload.is_published and any(re.search(r"ราคา|ประกัน|ชำระ|จ่าย|ใบงาน|ticket|สถานะ|ซ่อม|ซื้อ|สินค้า", value, re.I) for value in variants):
        raise HTTPException(status_code=422, detail="คำถามราคา ประกัน การชำระเงิน และงานซ่อมต้องใช้ข้อมูลจริงจากระบบ")
    for row in db.execute(select(ChatbotKnowledgeEntry)).scalars():
        if row.id == exclude_id:
            continue
        existing = [row.question, *json.loads(row.aliases or "[]")]
        if set(keys) & {normalize_question(value) for value in existing}:
            raise HTTPException(status_code=409, detail="มีคำถามนี้อยู่ในคลังแล้ว")
    return aliases


@app.get("/api/chatbot/manage/knowledge")
def list_chatbot_knowledge(db: Session = Depends(get_db), user: User = Depends(_CHATBOT_MANAGER)):
    rows = db.execute(select(ChatbotKnowledgeEntry).order_by(ChatbotKnowledgeEntry.updated_at.desc())).scalars().all()
    return [_knowledge_out(row) for row in rows]


@app.post("/api/chatbot/manage/knowledge", status_code=201)
def create_chatbot_knowledge(payload: ChatbotKnowledgeInput, request: Request,
                             db: Session = Depends(get_db), user: User = Depends(_CHATBOT_MANAGER)):
    aliases = _validate_knowledge(payload, db)
    row = ChatbotKnowledgeEntry(question=payload.question.strip(), answer=payload.answer.strip(),
                                aliases=json.dumps(aliases, ensure_ascii=False),
                                source_label=(payload.source_label or "").strip() or None,
                                source_url=(payload.source_url or "").strip() or None,
                                is_published=payload.is_published, updated_by=user.id)
    db.add(row)
    db.flush()
    write_audit(db, action="chatbot_knowledge_create", user=user, entity_type="chatbot_knowledge",
                entity_id=str(row.id), new_value={"question": row.question, "is_published": row.is_published}, request=request)
    db.commit()
    db.refresh(row)
    return _knowledge_out(row)


@app.put("/api/chatbot/manage/knowledge/{entry_id}")
def update_chatbot_knowledge(entry_id: int, payload: ChatbotKnowledgeInput, request: Request,
                             db: Session = Depends(get_db), user: User = Depends(_CHATBOT_MANAGER)):
    row = db.get(ChatbotKnowledgeEntry, entry_id)
    if not row:
        raise HTTPException(status_code=404, detail="ไม่พบคำตอบนี้")
    aliases = _validate_knowledge(payload, db, entry_id)
    old = {"question": row.question, "is_published": row.is_published}
    row.question, row.answer = payload.question.strip(), payload.answer.strip()
    row.aliases, row.is_published, row.updated_by = json.dumps(aliases, ensure_ascii=False), payload.is_published, user.id
    row.source_label = (payload.source_label or "").strip() or None
    row.source_url = (payload.source_url or "").strip() or None
    write_audit(db, action="chatbot_knowledge_update", user=user, entity_type="chatbot_knowledge",
                entity_id=str(row.id), old_value=old,
                new_value={"question": row.question, "is_published": row.is_published}, request=request)
    db.commit()
    db.refresh(row)
    return _knowledge_out(row)


class ChatbotPromptInput(BaseModel):
    guidance: str = Field(default="", max_length=2000)
    enabled: bool = False


@app.get("/api/chatbot/manage/prompts")
def list_chatbot_prompts(db: Session = Depends(get_db), user: User = Depends(_CHATBOT_MANAGER)):
    from app.prompt_extensions import ALLOWED_PROMPT_TASKS, guidance_for_task
    rows = {row.task: row for row in db.execute(select(ChatbotPromptSetting)).scalars()}
    return [{"task": task, "guidance": rows[task].guidance if task in rows else guidance_for_task(task),
             "enabled": rows[task].enabled if task in rows else bool(guidance_for_task(task)),
             "source": "database" if task in rows else "file"} for task in ALLOWED_PROMPT_TASKS]


@app.put("/api/chatbot/manage/prompts/{task}")
def update_chatbot_prompt(task: str, payload: ChatbotPromptInput, request: Request,
                          db: Session = Depends(get_db), user: User = Depends(_CHATBOT_MANAGER)):
    from app.prompt_extensions import ALLOWED_PROMPT_TASKS
    if task not in ALLOWED_PROMPT_TASKS:
        raise HTTPException(status_code=404, detail="ไม่พบงาน AI นี้")
    row = db.get(ChatbotPromptSetting, task)
    if row is None:
        row = ChatbotPromptSetting(task=task)
        db.add(row)
    row.guidance, row.enabled, row.updated_by = payload.guidance.strip(), payload.enabled, user.id
    write_audit(db, action="chatbot_prompt_update", user=user, entity_type="chatbot_prompt",
                entity_id=task, new_value={"enabled": row.enabled, "length": len(row.guidance)}, request=request)
    db.commit()
    return {"task": task, "guidance": row.guidance, "enabled": row.enabled, "source": "database"}


@app.get("/api/chatbot/manage/ratings")
def list_line_ratings(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db),
                      user: User = Depends(require_ratings_viewer)):
    cutoff = datetime.now(timezone.utc) - timedelta(days=days)
    rows = db.execute(select(LineServiceRating).where(LineServiceRating.created_at >= cutoff)
                      .order_by(LineServiceRating.created_at.desc()).limit(200)).scalars().all()
    summary = {}
    for target in ("bot", "staff"):
        aggregate = db.execute(select(func.count(LineServiceRating.id), func.avg(LineServiceRating.score))
                               .where(LineServiceRating.target == target, LineServiceRating.created_at >= cutoff)).one()
        distribution = dict(db.execute(select(LineServiceRating.score, func.count(LineServiceRating.id))
                               .where(LineServiceRating.target == target, LineServiceRating.created_at >= cutoff)
                               .group_by(LineServiceRating.score)).all())
        summary[target] = {"count": aggregate[0], "average": round(float(aggregate[1] or 0), 1),
                           "scores": {str(score): distribution.get(score, 0) for score in range(1, 6)}}
        if target == "bot":
            summary[target]["solved"] = db.execute(select(func.count(LineServiceRating.id)).where(
                LineServiceRating.target == "bot", LineServiceRating.resolved.is_(True),
                LineServiceRating.created_at >= cutoff)).scalar_one()
            summary[target]["not_solved"] = db.execute(select(func.count(LineServiceRating.id)).where(
                LineServiceRating.target == "bot", LineServiceRating.resolved.is_(False),
                LineServiceRating.created_at >= cutoff)).scalar_one()
    return {"days": days, "summary": summary,
            "recent": [{"id": row.id, "target": row.target, "score": row.score,
                        "resolved": row.resolved, "ticket_id": row.ticket_id,
                        "created_at": row.created_at} for row in rows]}


@app.get("/api/chatbot/manage/runtime")
def chatbot_runtime(user: User = Depends(_CHATBOT_MANAGER)):
    """Configuration status only; never return keys, credentials, or endpoint IDs."""
    from app import ai_client, chatbot_core, gemini_service, line_bot
    return {"provider": "Gemini", "model": line_bot.GEMINI_MODEL,
            "base_key_configured": bool(ai_client.API_KEY),
            "tuned_endpoint_configured": bool(ai_client.TUNED_ENDPOINT),
            "classifier_enabled": chatbot_core.ENABLE_GEMINI_CLASSIFIER,
            "orchestration_enabled": chatbot_core.ENABLE_GEMINI_ORCHESTRATION,
            "natural_replies_enabled": gemini_service.ENABLE_NATURAL_REPLIES}


class ChatbotPreviewInput(BaseModel):
    message: str = Field(..., min_length=1, max_length=1000)


@app.post("/api/chatbot/manage/preview")
def chatbot_preview(payload: ChatbotPreviewInput, user: User = Depends(_CHATBOT_MANAGER)):
    """Read-only, rule-layer preview. No LINE, Gemini, ticket, profile or log writes."""
    import re
    from app import chatbot_nlu
    from app.chatbot_helpers import detect_intent
    from app.chatbot_knowledge import answer_for_question
    from app.chatbot_warranty import extract_code, is_warranty_question, is_claim_request, has_claim_symptom, warranty_answer
    from app.assistant_policy import contains_prompt_injection, classify_urgency, INJECTION_REPLY, SAFETY_REPLY
    message = payload.message.strip()
    if contains_prompt_injection(message):
        return {"route": "security", "intent": "security", "reply": INJECTION_REPLY, "note": "กฎความปลอดภัย"}
    if classify_urgency(message) == "safety_critical":
        return {"route": "safety", "intent": "repair", "reply": SAFETY_REPLY, "note": "เหตุฉุกเฉิน"}
    if is_claim_request(message):
        return {"route": "claim", "intent": "repair",
                "reply": ("อุปกรณ์มีอาการอะไรคะ เช่น เปิดไม่ติด ไม่มีภาพ หรือเสียงหาย? ขอทราบอาการก่อนเพื่อช่วยตรวจวิธีแก้เบื้องต้น แล้วค่อยตรวจประกัน/การเคลมต่อค่ะ"
                          if not has_claim_symptom(message) else
                          "รับทราบอาการค่ะ ข้อความจริงจะค้นขั้นตอนที่ตรวจแล้วในฐานความรู้ก่อน หากแก้ไม่ได้จึงพาแจ้งซ่อมและให้เจ้าหน้าที่ตรวจสิทธิ์เคลม"),
                "note": "พรีวิวไม่สร้างบทสนทนา; LINE จริงจะถามอาการและตรวจฐานความรู้"}
    if is_warranty_question(message):
        code = extract_code(message)
        return {"route": "warranty", "intent": "warranty",
                "reply": warranty_answer(code) if code else "ขอรหัสอุปกรณ์หรือหมายเลข Serial ก่อนนะคะ",
                "note": "อ่านทะเบียนอุปกรณ์จริงแบบระบุรหัส; ไม่ส่ง LINE"}
    intent = detect_intent(message)
    if not re.search(r"ราคา|ประกัน|ชำระ|จ่าย|ใบงาน|ticket|สถานะ|ซ่อม|ซื้อ|สินค้า", message, re.I):
        answer = answer_for_question(message)
        if answer:
            return {"route": "reviewed_knowledge", "intent": intent, "reply": answer,
                    "note": "คำตอบเผยแพร่จากฐานข้อมูล"}
    clarify = chatbot_nlu.clarify_prompt(message) if intent in ("other", "ambiguous") else None
    return {"route": "clarify" if clarify else "intent_only", "intent": intent,
            "reply": clarify["message"] if clarify else None,
            "note": "พรีวิวชั้นกฎเท่านั้น; คำตอบจริงอาจต่างตามประวัติแชตและ AI"}


# ─── Knowledge Base (KB — TOR 1.5.5 / 5.6) ────────────────────────────

class KBArticleCreate(BaseModel):
    device_type: Optional[str] = None
    title: str = Field(..., min_length=3, max_length=255)
    symptom_tags: Optional[list[str]] = None
    steps: Optional[list] = None
    is_published: bool = False

class KBArticleUpdate(BaseModel):
    device_type: Optional[str] = None
    title: Optional[str] = None
    symptom_tags: Optional[list[str]] = None
    steps: Optional[list] = None
    is_published: Optional[bool] = None

class KBArticleOut(BaseModel):
    id: int
    kb_id: str
    organization_id: Optional[int] = None  # None = บทความหลัก (ส่วนกลาง)
    device_type: Optional[str] = None
    title: str
    symptom_tags: Optional[list] = None
    steps: Optional[list] = None
    is_published: bool
    view_count: int = 0
    success_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None


def _kb_to_out(a: KBArticle) -> KBArticleOut:
    return KBArticleOut(
        id=a.id, kb_id=a.kb_id, device_type=a.device_type, title=a.title,
        organization_id=getattr(a, "organization_id", None),
        symptom_tags=json.loads(a.symptom_tags) if a.symptom_tags else [],
        steps=json.loads(a.steps) if a.steps else [],
        is_published=a.is_published, view_count=a.view_count, success_count=a.success_count,
        created_at=a.created_at, updated_at=a.updated_at,
    )


@app.get("/api/kb/articles", response_model=list[KBArticleOut])
def list_kb_articles(
    q: Optional[str] = Query(None),
    device_type: Optional[str] = Query(None),
    is_published: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: Optional[User] = Depends(get_current_user_optional),
):
    stmt = select(KBArticle).order_by(KBArticle.title)
    if user is None:
        stmt = stmt.where(KBArticle.is_published.is_(True), KBArticle.organization_id.is_(None))
    # เห็นบทความหลัก (org None) + บทความของรรตัวเอง (ถ้ามีสังกัด)
    scope = visible_org_ids(user) if user else None
    if scope is not None:
        stmt = stmt.where(
            (KBArticle.organization_id.is_(None)) | (KBArticle.organization_id.in_(scope))
        )
    if device_type:
        stmt = stmt.where(KBArticle.device_type == device_type)
    if is_published is not None:
        stmt = stmt.where(KBArticle.is_published == is_published)
    if q:
        stmt = stmt.where((KBArticle.title.ilike(f"%{q}%")) | (KBArticle.symptom_tags.ilike(f"%{q}%")))
    rows = db.execute(stmt.offset(offset).limit(limit)).scalars().all()
    return [_kb_to_out(a) for a in rows]


@app.get("/api/kb/articles/{kb_id}", response_model=KBArticleOut)
def get_kb_article(kb_id: str, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user_optional)):
    a = db.execute(select(KBArticle).where(KBArticle.kb_id == kb_id)).scalar_one_or_none()
    if not a or (user is None and (not a.is_published or a.organization_id is not None)):
        raise HTTPException(status_code=404, detail="KB article not found")
    if user is not None and a.organization_id is not None:
        check_org_access(user, a.organization_id)
    return _kb_to_out(a)


def _validate_kb_publish(title: str, tags: list, steps: list, published: bool) -> None:
    if not published:
        return
    if not isinstance(title, str) or len(title.strip()) < 3 or not tags or not steps:
        raise HTTPException(status_code=422, detail="เผยแพร่ได้เมื่อมีหัวข้อ คำค้น และขั้นตอนอย่างน้อย 1 ข้อ")
    for step in steps:
        text_value = step if isinstance(step, str) else step.get("text", "") if isinstance(step, dict) else ""
        if not str(text_value).strip():
            raise HTTPException(status_code=422, detail="ขั้นตอนต้องไม่ว่าง")


@app.post("/api/kb/articles", response_model=KBArticleOut, status_code=201)
def create_kb_article(payload: KBArticleCreate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school"))):
    _validate_kb_publish(payload.title, payload.symptom_tags or [], payload.steps or [], payload.is_published)
    # สร้าง kb_id ใหม่จากเลขสูงสุดที่มีอยู่ (count+1 ผิดเมื่อมีการลบบทความ)
    last = db.execute(
        select(func.max(KBArticle.kb_id))
    ).scalar_one_or_none()
    try:
        next_no = int(str(last).split("-")[-1]) + 1 if last else 1
    except (ValueError, AttributeError):
        next_no = 1
    # admin_school สร้างบทความเฉพาะรรตัวเอง; owner/admin/super_admin สร้างบทความส่วนกลาง (None)
    org_id = user.organization_id if user.role == "admin_school" else None
    a = KBArticle(
        kb_id=f"kb-{next_no:04d}",
        organization_id=org_id,
        device_type=payload.device_type,
        title=payload.title,
        symptom_tags=json.dumps(payload.symptom_tags or [], ensure_ascii=False),
        steps=json.dumps(payload.steps or [], ensure_ascii=False),
        is_published=payload.is_published,
    )
    db.add(a)
    db.flush()  # ต้องได้แถวจริงก่อน จึงอ้างอิงใน Audit Log ได้
    # §40: สร้างบทความ KB
    write_audit(
        db, action="kb_create", user=user, entity_type="kb_article", entity_id=a.kb_id,
        new_value={"kb_id": a.kb_id, "title": a.title, "device_type": a.device_type,
                   "organization_id": a.organization_id, "is_published": a.is_published},
        request=request,
    )
    db.commit()
    db.refresh(a)
    invalidate_kb_cache()
    return _kb_to_out(a)


@app.patch("/api/kb/articles/{kb_id}", response_model=KBArticleOut)
def update_kb_article(kb_id: str, payload: KBArticleUpdate, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school"))):
    a = db.execute(select(KBArticle).where(KBArticle.kb_id == kb_id)).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="KB article not found")
    # admin_school แก้ได้เฉพาะบทความของรรตัวเอง; owner/admin/super_admin แก้บทความส่วนกลาง
    if user.role == "admin_school":
        if a.organization_id != user.organization_id:
            raise HTTPException(status_code=403, detail="คุณแก้ไขได้เฉพาะบทความของโรงเรียนตนเองเท่านั้น")
    elif a.organization_id is not None:
        raise HTTPException(status_code=403, detail="บทความนี้เป็นของโรงเรียนเฉพาะ — ผู้ดูแลบริษัทแก้ไขเฉพาะบทความหลัก")
    data = payload.model_dump(exclude_unset=True)
    _validate_kb_publish(data.get("title", a.title), data.get("symptom_tags", json.loads(a.symptom_tags or "[]")) or [],
                         data.get("steps", json.loads(a.steps or "[]")) or [], data.get("is_published", a.is_published))
    if "symptom_tags" in data and data["symptom_tags"] is not None:
        data["symptom_tags"] = json.dumps(data["symptom_tags"], ensure_ascii=False)
    if "steps" in data and data["steps"] is not None:
        data["steps"] = json.dumps(data["steps"], ensure_ascii=False)
    # §40: เก็บค่าก่อนแก้ เพื่อบันทึกทั้ง old_value และ new_value
    old_value = {k: getattr(a, k, None) for k in data}
    for k, v in data.items():
        setattr(a, k, v)
    if data:
        write_audit(
            db, action="kb_update", user=user, entity_type="kb_article", entity_id=a.kb_id,
            old_value=old_value, new_value=data, request=request,
        )
    db.commit()
    db.refresh(a)
    invalidate_kb_cache()
    return _kb_to_out(a)


@app.delete("/api/kb/articles/{kb_id}")
def delete_kb_article(kb_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school"))):
    a = db.execute(select(KBArticle).where(KBArticle.kb_id == kb_id)).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="KB article not found")
    if user.role == "admin_school":
        if a.organization_id != user.organization_id:
            raise HTTPException(status_code=403, detail="คุณลบได้เฉพาะบทความของโรงเรียนตนเองเท่านั้น")
    elif a.organization_id is not None:
        raise HTTPException(status_code=403, detail="บทความนี้เป็นของโรงเรียนเฉพาะ — ผู้ดูแลบริษัทลบได้เฉพาะบทความหลัก")
    # §40: ลบบทความ KB — ต้องเก็บค่าเดิมก่อนลบ เพราะหลังลบอ่านย้อนไม่ได้
    write_audit(
        db, action="kb_delete", user=user, entity_type="kb_article", entity_id=a.kb_id,
        old_value={"kb_id": a.kb_id, "title": a.title, "device_type": a.device_type,
                   "organization_id": a.organization_id, "is_published": a.is_published},
        request=request,
    )
    db.delete(a)
    db.commit()
    invalidate_kb_cache()
    return {"message": "KB article deleted", "kb_id": kb_id}


# ─── Seed KB 30 หัวข้อ (TOR ภาคผนวก ง) ────────────────────────────────

def seed_kb_articles(db: Session):
    """ใส่บทความ KB ตั้งต้น 30 หัวข้อ — รันเมื่อตารางว่าง"""
    count = db.execute(select(func.count()).select_from(KBArticle)).scalar_one()
    if count > 0:
        return 0
    articles = [
        ("Interactive Display", "จอ Interactive ไม่มีภาพ (ไฟเปิดติด)", ["จอไม่ติด", "ไม่มีภาพ", "no signal", "จอดำ", "ไฟติด"], [
            "ตรวจสอบสาย HDMI ให้เสียบแน่นทั้งสองด้าน",
            "กดปุ่ม Source/Input ที่รีโมท เลือกช่องสัญญาณให้ตรงกับพอร์ต",
            "ปิดจอค้างไว้ 10 วินาที แล้วเปิดใหม่",
            "ตรวจสอบว่าคอมพิวเตอร์เปิดอยู่และไม่ได้อยู่ในโหมด Sleep",
            "หากมีสาย HDMI สำรอง ให้ลองสลับสาย",
        ]),
        ("Interactive Display", "จอ Interactive ระบบสัมผัสไม่ทำงาน", ["สัมผัส", "touch", "touchscreen", "กดไม่ได้", "เขียนไม่ได้"], [
            "เช็ดหน้าจอให้สะอาดด้วยผ้าแห้ง (ไม่ใช้แอลกอฮอล์)",
            "ตรวจสอบว่าโหมดสัมผัสเปิดอยู่ (Settings → Touch)",
            "ถอดปลั๊กจอ 30 วินาที แล้วเสียบกลับ",
            "ลองแตะที่มุมจอทั้ง 4 ด้านเพื่อ calibrate",
            "ถ้ายังไม่หาย ต้องส่งช่างตรวจแผงสัมผัส",
        ]),
        ("Interactive Display", "จอ Interactive ไม่มีเสียง", ["ไม่มีเสียง", "no sound", "เงียบ", "ลำโพงไม่ดัง"], [
            "กดปุ่มเพิ่มเสียงที่รีโมท/ตัวเครื่อง",
            "ตรวจสอบว่าไม่ได้ Mute (ปุ่มรูปกากบาทเสียง)",
            "ตรวจสอบการตั้งค่าเสียงในระบบปฏิบัติการ",
            "ลองเสียบหูฟังเพื่อตรวจว่าลำโพงในตัวเสียหรือไม่",
            "ถ้าหูฟังดังแต่ลำโพงไม่ดัง ให้แจ้งช่างเปลี่ยนลำโพง",
        ]),
        ("Computer Desktop", "คอมพิวเตอร์เปิดไม่ติด", ["เปิดไม่ติด", "boot ไม่ขึ้น", "ไฟไม่เข้า", "จอดำ", "คอมไม่ทำงาน"], [
            "ตรวจสอบปลั๊กไฟและสายไฟให้เสียบแน่น",
            "กดปุ่ม Power ค้าง 10 วินาที แล้วกดใหม่",
            "ตรวจสอบว่าเต้ารับมีไฟ (ลองเสียบอุปกรณ์อื่น)",
            "ฟังเสียงพัดลม — ถ้าเงียบสนิทอาจ PSU เสีย",
            "ถ้ายังไม่ติด ให้แจ้งช่าง (ห้ามแกะเครื่องเอง)",
        ]),
        ("Computer Desktop", "คอมพิวเตอร์ช้า ค้างบ่อย", ["ช้า", "ค้าง", "แฮงก์", "หน่วง", "ช้าลง"], [
            "รีสตาร์ทเครื่องก่อน (Restart ไม่ใช่ Shutdown)",
            "ปิดโปรแกรมที่ไม่ใช้ (Ctrl+Shift+Esc → Task Manager)",
            "ตรวจสอบพื้นที่ว่างดิสก์ (ต้องเหลืออย่างน้อย 10%)",
            "ตรวจสอบอุณหภูมิ CPU — ถ้าร้อนจัดพัดลมอาจตัน",
            "ถ้ายังช้า ให้แจ้งช่างตรวจพัดลม/เปลี่ยน SSD",
        ]),
        ("Computer Desktop", "คอมพิวเตอร์ต่ออินเทอร์เน็ตไม่ได้", ["เน็ตไม่เข้า", "อินเทอร์เน็ต", "wifi ไม่", "lan ไม่", "ออฟไลน์"], [
            "ตรวจสอบว่าสาย LAN เสียบแน่น หรือ Wi-Fi เปิดอยู่",
            "ลองคลิกไอคอนเน็ต → แก้ไขปัญหา (Troubleshoot)",
            "ตรวจสอบว่าเครื่องอื่นในห้องใช้เน็ตได้หรือไม่",
            "ลอง restart เราเตอร์/AP ในห้อง",
            "ถ้าเครื่องอื่นก็ใช้ไม่ได้ ให้แจ้งช่างตรวจเครือข่าย",
        ]),
        ("Computer Notebook", "โน้ตบุ๊กชาร์จไม่เข้า", ["ชาร์จไม่เข้า", "แบตไม่ชาร์จ", "adapter", "สายชาร์จ"], [
            "ตรวจสอบปลั๊กและหัวชาร์จให้เสียบแน่น",
            "ลองเปลี่ยนเต้ารับอื่น",
            "ตรวจสอบไฟที่ adapter (ถ้าไม่มีไฟ แสดงว่า adapter เสีย)",
            "ถอดแบต (ถ้าถอดได้) แล้วใส่ใหม่",
            "ถ้ายังไม่ชาร์จ ให้แจ้งช่างเปลี่ยน adapter/หัวชาร์จ",
        ]),
        ("Projector", "โปรเจกเตอร์ไม่ขึ้นภาพ", ["โปรเจกเตอร์", "projector", "ไม่ขึ้นภาพ", "จอไม่แสดง"], [
            "ตรวจสอบไฟที่ตัวเครื่อง — ถ้าติดแต่ไม่มีภาพ อาจโคมไฟ (lamp) เสื่อม",
            "ตรวจสอบสาย VGA/HDMI ให้เสียบแน่นทั้งสองด้าน",
            "กดปุ่ม Source เลือกช่องสัญญาณที่ถูกต้อง",
            "รอเครื่องอุ่นเครื่อง 2-3 นาที (โคมไฟต้องอุ่นก่อน)",
            "ถ้าไฟกระพริบสีแดง ให้แจ้งช่างเปลี่ยนโคมไฟ",
        ]),
        ("Router", "Wi-Fi ช้า หลุดบ่อย", ["wifi ช้า", "เน็ตช้า", "หลุด", "สัญญาณอ่อน", "wi-fi"], [
            "รีสตาร์ทเราเตอร์ (ถอดปลั๊ก 30 วินาที แล้วเสียบใหม่)",
            "ตรวจสอบตำแหน่งเราเตอร์ — ควรอยู่สูงและกลางห้อง",
            "จำกัดจำนวนเครื่องที่เชื่อมต่อพร้อมกัน",
            "ตรวจสอบว่าสายจาก ONT/โมเด็มเสียบแน่น",
            "ถ้ายังช้า ให้แจ้งช่างตรวจสัญญาณ/อัปเดต firmware",
        ]),
        ("Access Point", "Access Point ไม่มีสัญญาณ", ["ap ไม่", "access point", "สัญญาณหาย", "wifi หาย"], [
            "ตรวจสอบไฟที่ AP — ถ้าดับแสดงว่าไฟไม่เข้า",
            "รีสตาร์ท AP โดยถอดปลั๊ก 30 วินาที",
            "ตรวจสอบสาย LAN ที่ต่อเข้ากับ AP",
            "ตรวจสอบว่า PoE Switch ที่จ่ายไฟทำงานอยู่",
            "ถ้ายังไม่มีสัญญาณ ให้แจ้งช่างตรวจ AP/Switch",
        ]),
        ("Speaker", "ลำโพงห้องเรียนไม่มีเสียง", ["ลำโพง", "ไม่มีเสียง", "เครื่องเสียง", "ไมค์ไม่ดัง"], [
            "ตรวจสอบปุ่ม Volume ที่เครื่องขยายเสียง (Amplifier)",
            "ตรวจสอบสายสัญญาณ (RCA/XLR) ให้เสียบแน่น",
            "ตรวจสอบว่าไม่ได้กด Mute",
            "ลองเปิดเพลงจากโทรศัพท์ผ่านสาย AUX เพื่อทดสอบลำโพง",
            "ถ้าลำโพงหลักไม่ดัง ให้แจ้งช่างตรวจแอมป์",
        ]),
        ("Microphone", "ไมโครโฟนไม่ดัง", ["ไมค์", "microphone", "ไมโครโฟน", "พูดไม่ได้ยิน"], [
            "ตรวจสอบสวิตช์เปิด/ปิดไมค์",
            "ตรวจสอบแบตเตอรี่ (ถ้าเป็นไร้สาย)",
            "ตรวจสอบความถี่ช่องสัญญาณให้ตรงกับเครื่องรับ",
            "ลองเสียบไมค์สายเข้ากับแอมป์โดยตรง",
            "ถ้ายังไม่ดัง ให้แจ้งช่างตรวจเครื่องรับสัญญาณ",
        ]),
        ("Camera", "กล้องวงจรปิดไม่มีภาพ", ["กล้อง", "cctv", "วงจรปิด", "ไม่มีภาพ", "มืด"], [
            "ตรวจสอบไฟที่กล้อง (IR LED ควรติดตอนกลางคืน)",
            "ตรวจสอบสาย LAN/สายไฟให้เสียบแน่น",
            "รีสตาร์ทเครื่องบันทึก (DVR/NVR)",
            "ตรวจสอบว่าจอ monitor เปิดอยู่และเลือกช่องถูกต้อง",
            "ถ้ายังไม่มีภาพ ให้แจ้งช่างตรวจกล้อง/เครื่องบันทึก",
        ]),
        ("Visualizer", "Visualizer ไม่แสดงภาพ", ["visualizer", "เครื่องฉายภาพ", "doc cam", "ไม่แสดงภาพ"], [
            "ตรวจสอบว่าเปิดไฟที่ตัวเครื่อง",
            "ตรวจสอบสาย VGA/HDMI ให้เสียบแน่น",
            "กดปุ่ม Source ที่จอ/โปรเจกเตอร์ เลือกช่องที่ถูกต้อง",
            "ลองกดปุ่ม Freeze/Standby ที่รีโมท",
            "ถ้ายังไม่แสดง ให้แจ้งช่างตรวจเซนเซอร์กล้อง",
        ]),
        ("UPS", "UPS เสียงเตือนดัง", ["ups", "สำรองไฟ", "เสียงเตือน", "beep"], [
            "เสียงเตือนต่อเนื่อง = ไฟบ้านดับ กำลังใช้แบตสำรอง — ประหยัดการใช้ไฟ",
            "เสียงเตือนสั้น ๆ เป็นระยะ = แบตเสื่อมหรือโหลดเกิน",
            "ตรวจสอบไฟที่ผนังว่ามีจริงหรือไม่",
            "กดปุ่ม Test เพื่อตรวจสภาพแบตเตอรี่",
            "ถ้าแบตเสื่อม (เตือนถี่ขึ้น) ให้แจ้งช่างเปลี่ยนแบต",
        ]),
        ("Printer", "ปริ้นเตอร์ไม่ทำงาน", ["ปริ้น", "printer", "พิมพ์ไม่ได้", "กระดาษติด"], [
            "ตรวจสอบกระดาษในถาดและแกะกระดาษติด (ถ้ามี)",
            "ตรวจสอบหมึก/โทนเนอร์ — ถ้าเหลือน้อยจะปริ้นไม่ออก",
            "ตรวจสอบว่าเครื่องปริ้นเปิดอยู่และเชื่อมต่อ (USB/Wi-Fi)",
            "ลองยกเลิกงานค้างในคิวพิมพ์ (Printer queue)",
            "ถ้ายังไม่ทำงาน ให้แจ้งช่างตรวจหัวพิมพ์/เซนเซอร์",
        ]),
        ("Software (Picaro)", "โปรแกรม Picaro เปิดไม่ได้", ["picaro", "เปิดไม่ได้", "crash", "error"], [
            "ปิดโปรแกรมทั้งหมดแล้วเปิดใหม่",
            "รีสตาร์ทคอมพิวเตอร์ก่อนลองอีกครั้ง",
            "ตรวจสอบว่าโปรแกรมติดตั้งเวอร์ชันล่าสุด",
            "บันทึกข้อความ error แล้วส่งให้ช่างตรวจ",
            "ถ้ายังเปิดไม่ได้ ให้แจ้งช่างติดตั้งใหม่",
        ]),
        ("Software (Phonics Hero)", "โปรแกรม Phonics Hero เข้าไม่ได้", ["phonics", "login ไม่ได้", "เข้าไม่ได้", "password"], [
            "ตรวจสอบอินเทอร์เน็ตก่อน (โปรแกรมต้องออนไลน์)",
            "ลองรีเซ็ตรหัสผ่าน (ลืมรหัสผ่าน)",
            "ตรวจสอบว่าบัญชีนักเรียน/ครูยัง active",
            "ลองใช้เบราว์เซอร์อื่น/เคลียร์แคช",
            "ถ้ายังเข้าไม่ได้ ให้แจ้งผู้ดูแลบัญชี",
        ]),
        ("Other", "อุปกรณ์มีกลิ่นไหม้ / ควัน", ["กลิ่นไหม้", "ควัน", "ไฟช็อต", "อันตราย"], [
            "ปิดเครื่องทันทีและถอดปลั๊ก (สำคัญที่สุด)",
            "อย่าเปิดเครื่องอีกจนกว่าช่างจะตรวจ",
            "ตักเตือนนักเรียนไม่ให้เข้าใกล้",
            "แจ้งช่างทันที — ห้ามซ่อมเอง",
            "บันทึกตำแหน่งอุปกรณ์เพื่อให้ช่างหาเจอ",
        ]),
        ("Other", "ปลั๊ก/เต้ารับร้อนผิดปกติ", ["ปลั๊กร้อน", "เต้ารับ", "ช็อต", "ไฟดูด"], [
            "หยุดใช้อุปกรณ์ที่เสียบอยู่นั้นทันที",
            "ถอดปลั๊ก (ใช้ผ้าหนา/ถุงมือกันไฟ)",
            "ตรวจสอบว่ามีอุปกรณ์เกินกำลังหรือไม่",
            "แจ้งช่างตรวจสายไฟ/เบรกเกอร์",
            "ห้ามเสียบอุปกรณ์อื่นแทนจนกว่าจะตรวจเสร็จ",
        ]),
        ("Computer AIO", "จอ AIO ฟ้า (Blue Screen)", ["blue screen", "จอฟ้า", "bsod", "error จอ"], [
            "จดรหัส error ที่ขึ้นบนจอ",
            "รีสตาร์ทเครื่อง (กดปุ่มค้าง 10 วินาที)",
            "ถ้าเกิดซ้ำ ให้ลอง Safe Mode (กด F8/F4 ตอนบูต)",
            "ตรวจสอบพื้นที่ว่างดิสก์และอัปเดต Windows",
            "ถ้าเกิดบ่อย ให้แจ้งช่างตรวจ RAM/ฮาร์ดดิสก์",
        ]),
        ("Computer AIO", "คอมพิวเตอร์บูตช้า", ["บูตช้า", "startup ช้า", "windows ช้า"], [
            "ปิดโปรแกรม auto-start ที่ไม่จำเป็น (Task Manager → Startup)",
            "ตรวจสอบพื้นที่ว่างดิสก์",
            "ถอดอุปกรณ์ USB ที่ไม่จำเป็นออก",
            "สแกนไวรัส/โปรแกรมไม่พึงประสงค์",
            "ถ้ายังช้า ให้แจ้งช่างตรวจ/เปลี่ยน SSD",
        ]),
        ("Computer Tablet", "แท็บเล็ตค้าง/รีสตาร์ทเอง", ["แท็บเล็ต", "tablet", "ค้าง", "รีสตาร์ทเอง", "ปิดเอง"], [
            "กดปุ่ม Power ค้าง 10 วินาที เพื่อบังคับรีสตาร์ท",
            "ตรวจสอบแบตเตอรี่ (ชาร์จให้เกิน 30%)",
            "อัปเดตระบบปฏิบัติการให้เป็นเวอร์ชันล่าสุด",
            "ล้างแคชแอปที่ใช้งานบ่อย",
            "ถ้ายังรีสตาร์ทเอง ให้แจ้งช่างตรวจแบต/เมนบอร์ด",
        ]),
        ("Computer Tablet", "แท็บเล็ตชาร์จไม่เข้า", ["แท็บเล็ตชาร์จ", "ชาร์จไม่เข้า", "หัวชาร์จ"], [
            "ตรวจสอบสายและหัวชาร์จให้เสียบแน่น",
            "ลองเปลี่ยนสาย/หัวชาร์จตัวอื่น",
            "ตรวจสอบพอร์ตชาร์จว่ามีฝุ่นหรือไม่ (เป่าลมเบา ๆ)",
            "ลองชาร์จข้ามคืน (แบตอาจหมดสนิท)",
            "ถ้ายังไม่ชาร์จ ให้แจ้งช่างเปลี่ยนพอร์ต/แบต",
        ]),
        ("Interactive Display", "จอ Interactive ภาพเพี้ยน/มีเส้น", ["ภาพเพี้ยน", "เส้น", "จอแตก", "จุดด่าง"], [
            "ถ่ายรูปอาการเพื่อส่งช่าง (สำคัญ)",
            "ลองเปลี่ยนสาย HDMI",
            "ตรวจสอบว่าจอมีรอยแตก/รอยกระแทกหรือไม่",
            "รีสตาร์ทจอและแหล่งสัญญาณ",
            "ถ้าเป็นรอยแตกที่แผง ต้องแจ้งช่างเปลี่ยนจอ",
        ]),
        ("Interactive Display", "จอ Interactive ร้อนจัด/พัดลมดัง", ["ร้อน", "พัดลมดัง", "เสียงดัง", "จอร้อน"], [
            "ตรวจสอบช่องระบายอากาศว่ามีฝุ่นอุดตันหรือไม่",
            "ตรวจสอบตำแหน่งติดตั้ง — ควรมีที่ว่างรอบเครื่อง",
            "ปิดจอพัก 10 นาที ให้เย็นลง",
            "ถ้าพัดลมดังผิดปกติต่อเนื่อง ให้แจ้งช่าง",
            "ห้ามฉีดน้ำหรือของเหลวใส่เครื่อง",
        ]),
        ("Router", "Router ไฟกระพริบไม่หยุด", ["router ไฟ", "ไฟกระพริบ", "internet ไฟแดง"], [
            "ไฟ Power กระพริบ = ตัวเครื่องมีปัญหา → รีสตาร์ท",
            "ไฟ Internet/WAN สีแดง = สัญญาณจากโมเด็มขาด",
            "รีสตาร์ททั้งโมเด็มและเราเตอร์",
            "ตรวจสอบสายจากโมเด็มเข้า WAN ให้เสียบแน่น",
            "ถ้ายังแดง ให้แจ้งช่างตรวจกับผู้ให้บริการเน็ต",
        ]),
        ("Camera", "กล้องภาพเบลอ/ไม่ชัด", ["กล้องเบลอ", "ภาพไม่ชัด", "โฟกัส"], [
            "เช็ดเลนส์กล้องด้วยผ้าแห้งนุ่ม",
            "ตรวจสอบฟิล์มกันรอยที่เลนส์ (ถ้ามี) ลอกออก",
            "ปรับโฟกัสด้วยมือ (ถ้าเป็นกล้องปรับได้)",
            "ตรวจสอบความละเอียดการบันทึก (Resolution)",
            "ถ้ายังเบลอ ให้แจ้งช่างตรวจเลนส์/เซนเซอร์",
        ]),
        ("Speaker", "เครื่องขยายเสียงฮัม/มีเสียงรบกวน", ["เสียงฮัม", "hum", "เสียงรบกวน", "แอมป์"], [
            "ลดเกน (Gain) ของไมค์ลง",
            "ตรวจสอบสายสัญญาณว่าขาด/ชำรุดหรือไม่",
            "ย้ายสายสัญญาณให้ห่างจากสายไฟ",
            "ตรวจสอบการต่อ Ground (สายดิน)",
            "ถ้ายังฮัม ให้แจ้งช่างตรวจแอมป์",
        ]),
        ("UPS", "อุปกรณ์ต่อ UPS ดับทั้งที่ไฟเข้า", ["ups ดับ", "ไฟดับ", "เครื่องดับ"], [
            "ตรวจสอบว่า UPS เปิดสวิตช์อยู่",
            "ตรวจสอบว่าโหลดไม่เกินกำลัง (อย่าเสียบหลายเครื่อง)",
            "กดปุ่ม Test — ถ้าแบตหมดจะเตือน",
            "ตรวจสอบว่าปลั๊กผนังมีไฟจริง",
            "ถ้า UPS เก่าเกิน 3 ปี ให้แจ้งช่างเปลี่ยนแบต",
        ]),
        ("Other", "สอบถามเรื่องการใช้อุปกรณ์", ["วิธีใช้", "ใช้งานยังไง", "สอบถาม", "how to"], [
            "ระบุอุปกรณ์และรหัสห้องให้ชัดเจน",
            "แจ้งอาการ/สิ่งที่ต้องการทำ",
            "ช่างจะแนะนำหรือนัดสาธิตการใช้งาน",
            "ถ้าเป็นซอฟต์แวร์ ให้ระบุเวอร์ชัน",
            "กรณีเร่งด่วนระหว่างสอน ให้โทรหา IT โดยตรง",
        ]),
    ]
    for i, (dtype, title, tags, steps) in enumerate(articles, start=1):
        db.add(KBArticle(
            kb_id=f"kb-{i:04d}",
            device_type=dtype,
            title=title,
            symptom_tags=json.dumps(tags, ensure_ascii=False),
            steps=json.dumps([{"order": j + 1, "text": t} for j, t in enumerate(steps)], ensure_ascii=False),
            is_published=True,
        ))
    db.commit()
    return len(articles)


# ─── AI Diagnose (TOR 5.5) — ค้น KB ด้วยคำสำคัญ, score < 0.3 → ส่งต่อช่าง ──

class DiagnoseRequest(BaseModel):
    device_id: Optional[str] = None
    device_type: Optional[str] = None
    symptom_text: str = Field(..., min_length=2, max_length=500)

class DiagnoseResult(BaseModel):
    session_id: str
    found: bool
    confidence: Optional[float] = None
    category: Optional[str] = None
    kb_article_id: Optional[str] = None
    title: Optional[str] = None
    steps: list = []
    message: str = ""
    next_actions: list = []
    fallback_mode: bool = False


@app.post("/api/ai/diagnose", response_model=DiagnoseResult)
@limiter.limit("20/minute")
def ai_diagnose(request: Request, payload: DiagnoseRequest, db: Session = Depends(get_db)):
    """วิเคราะห์อาการ:
    1) keyword match คัดบทความ KB ที่เกี่ยวข้อง (top-N)
    2) ส่งให้ Gemini เลือกบทความที่ตรงที่สุด (ตอบจาก list ที่ให้เท่านั้น กัน hallucination ตาม R4)
    3) ถ้าไม่มี GEMINI_API_KEY / API ล่ม / Gemini เลือกไม่ได้ → fallback ใช้ keyword best (score≥0.3)
    ตาม TOR 1.5.5 / SD-05"""
    import uuid as _uuid
    import re
    from app.gemini_service import match_article, is_available as gemini_available

    session_id = f"ai-{_uuid.uuid4().hex[:12]}"
    articles = db.execute(
        select(KBArticle).where(KBArticle.is_published == True)
    ).scalars().all()

    text_l = (payload.symptom_text or "").lower()
    # ─── 1. keyword match: ตรวจว่า symptom_tag/title ของบทความ ปรากฏในข้อความ (รองรับไทยไม่เว้นวรรค) ───
    scored = []
    for a in articles:
        tags = json.loads(a.symptom_tags) if a.symptom_tags else []
        # แต่ละ tag ถ้าอยู่ในข้อความอาการ → นับ (เป็นชิ้นคำ ไม่ใช่ token)
        matched = [t for t in tags if t.lower() and t.lower() in text_l]
        # title ของบทความก็เป็น keyword ด้วย
        if a.title.lower() in text_l:
            matched.append(a.title)
        score = len(matched)
        if payload.device_type and a.device_type == payload.device_type:
            score += 0.5
        scored.append((score, a))
    scored.sort(key=lambda x: x[0], reverse=True)
    top_candidates = scored[:5]

    # ─── 2. ให้ Gemini วิเคราะห์คำโดยตรงจากทุกบทความ (semantic — ไม่พึ่ง keyword คัดก่อน) ───
    chosen = None
    if gemini_available() and articles:
        # ส่งบทความทั้งหมด (ย่อ: ชื่อ+type+tag) ให้ Gemini เลือกที่ตรงกับอาการ — เข้าใจคำไทย/พ้อง/บริบท
        all_cand = [
            {"kb_id": a.kb_id, "device_type": a.device_type, "title": a.title,
             "tags": json.loads(a.symptom_tags) if a.symptom_tags else []}
            for a in articles
        ]
        gemini_match = match_article(payload.symptom_text, payload.device_type, all_cand)
        if gemini_match and gemini_match.get("kb_id"):
            chosen = next(
                (a for a in articles if a.kb_id == gemini_match["kb_id"]), None
            )

    # ─── 3. Fallback ฉลาด: ไม่มี Gemini/keyword แม่น แต่รู้ประเภทอุปกรณ์ → แนะนำบทความหลักของประเภทนั้น ───
    if chosen is None:
        def _not_found(msg="ระบบไม่พบวิธีแก้ไขเบื้องต้นสำหรับอาการนี้ ขออนุญาตส่งต่อให้เจ้าหน้าที่ดำเนินการครับ"):
            return DiagnoseResult(
                session_id=session_id, found=False, confidence=0.0, category=None,
                message=msg, next_actions=[{"type": "create_ticket", "label": "แจ้งเจ้าหน้าที่"}],
            )
        # 1) keyword match ดี → ใช้
        if top_candidates and top_candidates[0][0] >= 1:
            chosen = top_candidates[0][1]
        # 2) keyword ไม่แม่น แต่รู้ device_type → เลือกบทความหลักของประเภทนั้น (แนะนำเบื้องต้น กรณียังไม่ระบุอาการชัด)
        elif payload.device_type:
            same_type = sorted(
                (a for a in articles if a.device_type == payload.device_type),
                key=lambda x: int(re.sub(r"\D", "", x.kb_id) or 0)
            )
            if same_type:
                chosen = same_type[0]
                return DiagnoseResult(
                    session_id=session_id, found=True, confidence=0.4,
                    category=chosen.device_type, kb_article_id=chosen.kb_id, title=chosen.title,
                    steps=[s["text"] for s in (json.loads(chosen.steps) if chosen.steps else [])],
                    message=(f"อาการที่ระบุ ('{payload.symptom_text}') ยังกว้าง/ไม่เจาะจง ขอแนะนำวิธีเช็คเบื้องต้นของ {chosen.device_type} "
                             "ก่อน หากไม่ตรงกับอาการ ขอรายละเอียดเพิ่มหรือแจ้งเจ้าหน้าที่ได้นะคะ"),
                    next_actions=[
                        {"type": "resolved", "label": "แก้ไขได้แล้ว ✅"},
                        {"type": "create_ticket", "label": "ไม่ตรงอาการ / ยังไม่หาย → แจ้งเจ้าหน้าที่"},
                    ],
                )
        # 3) ไม่มีอะไรเลย → not found
        return _not_found()

    # เจอบทความ (จาก Gemini หรือ keyword) → คืนขั้นตอนของบทความนั้น
    chosen.view_count = (chosen.view_count or 0) + 1
    steps = [s["text"] for s in (json.loads(chosen.steps) if chosen.steps else [])]
    db.commit()
    return DiagnoseResult(
        session_id=session_id,
        found=True,
        confidence=round(top_candidates[0][0] if top_candidates else 0.3, 2),
        category=chosen.device_type,
        kb_article_id=chosen.kb_id,
        title=chosen.title,
        steps=steps,
        message="พบวิธีแก้ไขเบื้องต้นจากฐานความรู้ ลองทำตามขั้นตอนด้านล่างก่อนนะคะ",
        next_actions=[
            {"type": "resolved", "label": "แก้ไขได้แล้ว ✅"},
            {"type": "create_ticket", "label": "ยังไม่หาย → แจ้งเจ้าหน้าที่"},
        ],
    )


# ─── Self-Service Case (TOR 5.8) ──────────────────────────────────────

class SelfServiceCreate(BaseModel):
    device_id: Optional[str] = None
    symptom: Optional[str] = None
    kb_article_id: Optional[int] = None
    ai_session_id: Optional[str] = None
    helpful_step: Optional[int] = None
    time_saved_minutes: Optional[int] = None


@app.post("/api/self-service", status_code=201)
def create_self_service(payload: SelfServiceCreate, db: Session = Depends(get_db)):
    """บันทึกกรณีผู้ใช้แก้ไขได้เองจากคำแนะนำ Chatbot/KB"""
    if payload.kb_article_id:
        kb = db.get(KBArticle, payload.kb_article_id)
        if kb:
            kb.success_count = (kb.success_count or 0) + 1
    case = SelfServiceCase(
        device_id=payload.device_id,
        symptom=payload.symptom,
        kb_article_id=payload.kb_article_id,
        ai_session_id=payload.ai_session_id,
        helpful_step=payload.helpful_step,
        time_saved_minutes=payload.time_saved_minutes,
        resolved=True,
    )
    db.add(case)
    db.commit()
    db.refresh(case)
    return {"id": case.id, "message": "บันทึกเรียบร้อย ขอบคุณครับ"}


@app.get("/api/self-service")
def list_self_service(
    device_id: Optional[str] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support")),
):
    """รายการ self-service — จำกัดตามบทบาท: admin_school/it_support(มีสังกัด) เห็นเฉพาะรรตัวเอง"""
    scope = visible_org_ids(user)
    stmt = select(SelfServiceCase).order_by(SelfServiceCase.created_at.desc())
    # self_service_cases ไม่มี organization_id — filter ผ่าน device
    if scope is not None:
        if not scope:
            return []  # scope ว่าง → ไม่เห็นข้อมูล
        stmt = stmt.where(
            SelfServiceCase.device_id.in_(
                select(Device.device_id).where(Device.organization_id.in_(scope))
            )
        )
    if device_id:
        stmt = stmt.where(SelfServiceCase.device_id == device_id)
    rows = db.execute(stmt.offset(offset).limit(limit)).scalars().all()
    # ดึง device_type + room เพื่อแสดงในตาราง
    dev_info = {}
    dev_ids = list({c.device_id for c in rows if c.device_id})
    if dev_ids:
        for d in db.execute(select(Device).where(Device.device_id.in_(dev_ids))).scalars():
            dev_info[d.device_id] = {"device_type": d.device_type, "room_name": d.room.name if d.room else None}
    return [
        {
            "id": c.id,
            "device_id": c.device_id,
            "device_type": dev_info.get(c.device_id, {}).get("device_type"),
            "room_name": dev_info.get(c.device_id, {}).get("room_name"),
            "symptom": c.symptom,
            "kb_article_id": c.kb_article_id,
            "ai_session_id": c.ai_session_id,
            "resolved": c.resolved,
            "helpful_step": c.helpful_step,
            "time_saved_minutes": c.time_saved_minutes,
            "created_at": c.created_at,
        }
        for c in rows
    ]


# ─── SLA Check + Escalation (TOR 4.5) — เรียกโดย n8n Cron ─────────────

@app.get("/api/internal/sla/check")
def sla_check(db: Session = Depends(get_db), _: None = Depends(require_n8n_secret)):
    """ตรวจงานเกินกำหนด SLA → ยกระดับ L1/L2/L3 (เรียกทุก 15 นาทีโดย n8n)"""
    now = datetime.now(timezone.utc)
    overdue = db.execute(
        select(RepairTicket).where(
            RepairTicket.status.in_(["new", "assigned", "in_progress"]),
            RepairTicket.sla_due_at.is_not(None),
            RepairTicket.sla_due_at < now,
        )
    ).scalars().all()

    escalated = []
    for t in overdue:
        old_level = t.escalation_level
        if t.escalation_level == 0:
            t.escalation_level = 1
            note = "งานเกินกำหนด SLA — ระดับ 1 (เตือนช่างผู้รับผิดชอบ)"
        elif t.escalation_level == 1:
            t.escalation_level = 2
            note = "งานเกินกำหนด SLA เกิน 30 นาที — ระดับ 2 (แจ้งหัวหน้าฝ่าย IT)"
        else:
            note = "งานเกินกำหนด SLA นาน — ระดับ 3 (แจ้งผู้บริหาร)"
        if t.escalation_level != old_level:
            db.add(TicketUpdate(
                ticket=t,
                from_status=t.status,
                to_status=t.status,
                note=note,
                author_name="SLA System",
                author_role="system",
            ))
            escalated.append({
                "ticket_id": t.ticket_id,
                "priority": t.priority,
                "sla_due_at": t.sla_due_at.isoformat() if t.sla_due_at else None,
                "escalation_level": t.escalation_level,
                "note": note,
            })
    db.commit()
    return {"checked_at": now.isoformat(), "overdue_count": len(overdue), "escalated": escalated}


# ─── Preventive Maintenance (Blueprint §38 / TOR 1.5.10, 5.9) ────────

class PMPlanCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=255)
    device_type: Optional[str] = None
    interval_days: int = Field(90, ge=1, le=3650)
    checklist: Optional[list] = None
    is_active: bool = True


class PMPlanUpdate(BaseModel):
    """แก้ไขแผน PM — ส่งมาเฉพาะฟิลด์ที่ต้องการเปลี่ยน (exclude_unset)"""

    name: Optional[str] = Field(None, min_length=3, max_length=255)
    device_type: Optional[str] = None
    interval_days: Optional[int] = Field(None, ge=1, le=3650)
    checklist: Optional[list] = None
    is_active: Optional[bool] = None


def _pm_plan_out(p: PMPlan) -> dict:
    return {
        "id": p.id,
        "name": p.name,
        "device_type": p.device_type,
        "interval_days": p.interval_days,
        "checklist": json.loads(p.checklist) if p.checklist else [],
        "is_active": p.is_active,
    }


@app.get("/api/pm/plans")
def list_pm_plans(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    """แผน PM ทั้งหมด (§38)"""
    rows = db.execute(select(PMPlan).order_by(PMPlan.name)).scalars().all()
    return [_pm_plan_out(p) for p in rows]


@app.post("/api/pm/plans", status_code=201)
def create_pm_plan(
    payload: PMPlanCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin")),
):
    """สร้างแผน PM ใหม่ — admin ขึ้นไป"""
    plan = PMPlan(
        name=payload.name,
        device_type=payload.device_type,
        interval_days=payload.interval_days,
        checklist=json.dumps(payload.checklist or [], ensure_ascii=False),
        is_active=payload.is_active,
    )
    db.add(plan)
    db.flush()
    write_audit(
        db, action="pm_plan_create", user=user, entity_type="pm_plan",
        entity_id=plan.id, new_value=_pm_plan_out(plan), request=request,
    )
    db.commit()
    db.refresh(plan)
    return _pm_plan_out(plan)


@app.put("/api/pm/plans/{plan_id}")
def update_pm_plan(
    plan_id: int,
    payload: PMPlanUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin")),
):
    """แก้ไขแผน PM — admin ขึ้นไป (เดิมมีแค่ GET/POST จึงแก้ไม่ได้เลย)"""
    plan = db.get(PMPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="ไม่พบแผน PM นี้")

    before = _pm_plan_out(plan)
    data = payload.model_dump(exclude_unset=True)
    if not data:
        return before

    if data.get("name") is not None:
        plan.name = data["name"].strip()
    if "device_type" in data:
        # ส่ง "" หรือ null = แผนนี้ใช้กับอุปกรณ์ทุกชนิด
        plan.device_type = (data["device_type"] or None)
    if data.get("interval_days") is not None:
        plan.interval_days = data["interval_days"]
    if "checklist" in data:
        plan.checklist = json.dumps(data["checklist"] or [], ensure_ascii=False)
    if data.get("is_active") is not None:
        plan.is_active = data["is_active"]

    db.flush()
    write_audit(
        db, action="pm_plan_update", user=user, entity_type="pm_plan",
        entity_id=plan.id, old_value=before, new_value=_pm_plan_out(plan), request=request,
    )
    db.commit()
    db.refresh(plan)
    return _pm_plan_out(plan)


@app.delete("/api/pm/plans/{plan_id}")
def delete_pm_plan(
    plan_id: int,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin")),
):
    """ลบแผน PM — admin ขึ้นไป

    ถ้ายังมีงาน PM ค้าง (pending/overdue) ตอบ 409 พร้อมจำนวน เพื่อไม่ให้งานที่
    เจ้าหน้าที่กำลังถืออยู่หลุดหายไปเงียบ ๆ — ให้ปิดใช้งานแผน (is_active=false) แทน
    ประวัติงานที่ทำเสร็จ/ข้ามแล้วยังเก็บไว้ (pm_tasks.plan_id เป็น SET NULL)
    """
    plan = db.get(PMPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="ไม่พบแผน PM นี้")

    open_tasks = (
        db.query(PMTask)
        .filter(PMTask.plan_id == plan_id, PMTask.status.in_(("pending", "overdue")))
        .count()
    )
    if open_tasks:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "PM_PLAN_HAS_OPEN_TASKS",
                "message": (
                    f"ลบไม่ได้ — แผนนี้ยังมีงานค้างอยู่ {open_tasks} งาน "
                    "กรุณาปิดงานให้เสร็จ หรือปิดใช้งานแผนแทนการลบ"
                ),
                "open_tasks": open_tasks,
            },
        )

    kept_history = db.query(PMTask).filter(PMTask.plan_id == plan_id).count()
    write_audit(
        db, action="pm_plan_delete", user=user, entity_type="pm_plan",
        entity_id=plan.id, old_value=_pm_plan_out(plan), request=request,
    )
    db.delete(plan)
    db.commit()
    return {"deleted": True, "id": plan_id, "history_tasks_kept": kept_history}


def _gen_pm_task_no(db: Session) -> str:
    """PM-YYYYMM-NNNN — ใช้ MAX(ลำดับ)+1 กันเลขซ้ำหลังลบงาน"""
    now = datetime.now(timezone.utc)
    prefix = f"PM-{now.year}{now.month:02d}-"
    _lock_generated_id_prefix(db, prefix)
    row = db.execute(
        text("SELECT MAX(CAST(SUBSTRING(task_no FROM 'PM-\\d{6}-(\\d{4})') AS INTEGER)) "
             "FROM pm_tasks WHERE task_no LIKE :p"),
        {"p": f"{prefix}%"},
    ).scalar_one()
    return f"{prefix}{(row or 0) + 1:04d}"


@app.post("/api/pm/generate")
def pm_generate(
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    """สร้างงาน PM ล่วงหน้าให้อุปกรณ์ที่ถึงรอบ + ปรับงานเลยกำหนดเป็น overdue"""
    now = datetime.now(timezone.utc)

    # งานค้างที่เลยกำหนดแล้ว → overdue (§38 ปฏิทิน PM)
    stale = db.execute(
        select(PMTask).where(
            PMTask.status == "pending",
            PMTask.due_date.is_not(None),
            PMTask.due_date < now,
        )
    ).scalars().all()
    for t in stale:
        t.status = "overdue"

    plans = db.execute(select(PMPlan).where(PMPlan.is_active.is_(True))).scalars().all()
    generated = 0
    skipped = 0
    tasks = []
    for plan in plans:
        stmt = select(Device).where(Device.status == "active")
        if plan.device_type:
            stmt = stmt.where(Device.device_type == plan.device_type)
        devices = db.execute(stmt).scalars().all()
        for d in devices:
            # ข้ามถ้ามีงานค้าง (pending/overdue) ของแผนเดียวกันอยู่แล้ว
            existing = db.execute(
                select(PMTask.id).where(
                    PMTask.plan_id == plan.id,
                    PMTask.device_id == d.device_id,
                    PMTask.status.in_(["pending", "overdue"]),
                ).limit(1)
            ).scalar_one_or_none()
            if existing:
                skipped += 1
                continue

            # รอบถัดไปนับจากงานที่ทำเสร็จล่าสุด ถ้าไม่มีให้ตั้ง due ใน 7 วัน
            last_done = db.execute(
                select(PMTask.done_at).where(
                    PMTask.plan_id == plan.id,
                    PMTask.device_id == d.device_id,
                    PMTask.status == "done",
                ).order_by(PMTask.done_at.desc()).limit(1)
            ).scalar_one_or_none()
            due = (
                last_done + timedelta(days=plan.interval_days)
                if last_done else now + timedelta(days=7)
            )

            task = PMTask(
                task_no=_gen_pm_task_no(db),
                plan_id=plan.id,
                device_id=d.device_id,
                organization_id=d.organization_id,
                due_date=due,
                status="pending",
            )
            db.add(task)
            db.flush()
            tasks.append({
                "task_no": task.task_no,
                "device_id": d.device_id,
                "plan_name": plan.name,
                "due_date": task.due_date.isoformat() if task.due_date else None,
            })
            generated += 1

    write_audit(
        db, action="pm_generate", user=user, entity_type="pm_task",
        new_value={"generated": generated, "skipped": skipped, "marked_overdue": len(stale)},
        request=request,
    )
    db.commit()
    return {
        "generated": generated,
        "skipped_duplicate": skipped,
        "marked_overdue": len(stale),
        "tasks": tasks,
    }


class PMTaskCreate(BaseModel):
    plan_id: int
    device_id: str = Field(..., min_length=1, max_length=64)
    due_date: datetime


@app.post("/api/pm/tasks", status_code=201)
def create_pm_task(
    payload: PMTaskCreate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    """สร้างงาน PM รายเครื่องจากแผน พร้อมวันกำหนดและ checklist ที่ตรวจได้ก่อนบันทึก."""
    plan = db.get(PMPlan, payload.plan_id)
    device = db.execute(select(Device).where(Device.device_id == payload.device_id)).scalar_one_or_none()
    if not plan or not device:
        raise HTTPException(status_code=404, detail="ไม่พบแผนหรืออุปกรณ์")
    check_org_access(user, device.organization_id)
    if plan.device_type and plan.device_type != device.device_type:
        raise HTTPException(status_code=422, detail="แผนนี้ใช้กับอุปกรณ์ประเภทอื่น")
    if not plan.is_active:
        raise HTTPException(status_code=422, detail="แผนนี้ปิดใช้งานอยู่")
    if not plan.checklist or not json.loads(plan.checklist):
        raise HTTPException(status_code=422, detail="แผนต้องมีรายการตรวจก่อนสร้างงาน")
    existing = db.execute(select(PMTask.id).where(
        PMTask.plan_id == plan.id, PMTask.device_id == device.device_id,
        PMTask.status.in_(["pending", "overdue"]),
    ).limit(1)).scalar_one_or_none()
    if existing:
        raise HTTPException(status_code=409, detail="อุปกรณ์นี้มีงาน PM ค้างของแผนนี้แล้ว")
    due = payload.due_date
    if due.tzinfo is None:
        raise HTTPException(status_code=422, detail="due_date ต้องระบุ timezone")
    task = PMTask(task_no=_gen_pm_task_no(db), plan_id=plan.id, device_id=device.device_id,
                  organization_id=device.organization_id, due_date=due,
                  status="overdue" if due < datetime.now(timezone.utc) else "pending")
    db.add(task)
    db.flush()
    write_audit(db, action="pm_task_create", user=user, entity_type="pm_task", entity_id=task.id,
                new_value={"task_no": task.task_no, "plan_id": plan.id,
                           "device_id": device.device_id, "due_date": due.isoformat()}, request=request)
    db.commit()
    return {"id": task.id, "task_no": task.task_no, "status": task.status}


@app.get("/api/pm/tasks")
def list_pm_tasks(
    status: Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    organization_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    """รายการงาน PM + checklist ของแผนที่ผูกไว้"""
    stmt = select(PMTask).order_by(PMTask.due_date)
    scope = visible_org_ids(user)
    if scope is not None:
        stmt = stmt.where(PMTask.organization_id.in_(scope))
    if status:
        stmt = stmt.where(PMTask.status == status)
    if device_id:
        stmt = stmt.where(PMTask.device_id == device_id)
    if organization_id:
        stmt = stmt.where(PMTask.organization_id == organization_id)
    rows = db.execute(stmt.offset(offset).limit(limit)).scalars().all()

    result = []
    for t in rows:
        plan = db.get(PMPlan, t.plan_id) if t.plan_id else None
        dev = (
            db.execute(select(Device).where(Device.device_id == t.device_id)).scalar_one_or_none()
            if t.device_id else None
        )
        result.append({
            "id": t.id,
            "task_no": t.task_no,
            "plan_id": t.plan_id,
            "plan_name": plan.name if plan else None,
            "device_id": t.device_id,
            "device_type": dev.device_type if dev else None,
            "organization_id": t.organization_id,
            "due_date": t.due_date,
            "status": t.status,
            "result": json.loads(t.result) if t.result else [],
            "photos": json.loads(t.photos) if t.photos else [],
            "done_by": t.done_by,
            "done_at": t.done_at,
            "next_due": t.next_due,
            "ticket_id": t.ticket_id,
            "skip_reason": t.skip_reason,
            "checklist": json.loads(plan.checklist) if plan and plan.checklist else [],
        })
    return result


class PMSubmitRequest(BaseModel):
    result: Optional[list] = None
    photos: Optional[list[str]] = None


class PMSkipRequest(BaseModel):
    reason: str = Field(..., min_length=3, max_length=500)


@app.post("/api/pm/tasks/{task_id}/submit")
def pm_submit(
    task_id: int,
    payload: PMSubmitRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    """ส่งผลตรวจ PM — รายการที่ไม่ผ่านจะเปิด Ticket ให้อัตโนมัติ (§38)"""
    task = db.get(PMTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"ไม่พบงาน PM รหัส {task_id}")
    # งานที่ปิดแล้ว (done/skipped) แก้ย้อนหลังได้เฉพาะผู้ดูแลระดับสูง
    # — บันทึก audit เป็น action "pm_task_edit" แยกจากการบันทึกครั้งแรก
    is_reopen = task.status in ("done", "skipped")
    if is_reopen and user.role not in PM_TASK_OVERRIDE_ROLES:
        raise HTTPException(status_code=409, detail=f"งาน PM นี้ปิดแล้ว (สถานะ {task.status})")

    now = datetime.now(timezone.utc)
    old_status = task.status
    plan = db.get(PMPlan, task.plan_id) if task.plan_id else None

    task.status = "done"
    task.result = json.dumps(payload.result or [], ensure_ascii=False)
    task.photos = json.dumps(payload.photos or [], ensure_ascii=False)
    task.done_by = getattr(user, "full_name", None) or getattr(user, "username", None)
    task.done_at = now
    task.next_due = now + timedelta(days=(plan.interval_days if plan else 90))

    # รายการ "ไม่ผ่าน" → เปิด Ticket อัตโนมัติ พร้อมคิด SLA ตามปกติ
    failed = [
        r for r in (payload.result or [])
        if isinstance(r, dict) and r.get("value") in (False, "false", "fail", "ไม่ผ่าน")
    ]
    auto_ticket = None
    auto_ticket_existing = False
    if failed and task.device_id and not task.ticket_id:
        dev = db.execute(
            select(Device).where(Device.device_id == task.device_id)
        ).scalar_one_or_none()
        if dev:
            notes = " | ".join(
                str(r.get("item") or r.get("note") or "") for r in failed
            ).strip(" |")
            # ─── กันแจ้งซ้ำ: อุปกรณ์มีใบงานค้างอยู่แล้ว → ไม่เปิดใบที่สองของเรื่องเดิม ──
            # บันทึกรายการที่ตรวจไม่ผ่านเข้าใบเดิมเป็น ticket_updates แล้วผูกงาน PM
            # กับใบนั้น ช่างจะเห็นทั้งเรื่องที่ผู้ใช้แจ้งและผลตรวจ PM ในใบเดียว
            existing_open = find_open_ticket(db, dev.device_id)
            if existing_open is not None:
                db.add(TicketUpdate(
                    ticket=existing_open,
                    from_status=existing_open.status,
                    to_status=existing_open.status,
                    note=f"[ผลตรวจ PM {task.task_no}] รายการไม่ผ่าน: {notes or '-'}",
                    author_name=(task.done_by or "ช่าง PM")[:128],
                    author_role="technician",
                ))
                task.ticket_id = existing_open.ticket_id
                auto_ticket = existing_open.ticket_id
                auto_ticket_existing = True
            else:
                ticket = RepairTicket(
                    ticket_id=generate_ticket_id(db, dev.organization_id),
                    organization_id=dev.organization_id,
                    device_id=dev.device_id,
                    title=f"PM พบปัญหา: {notes or task.task_no}"[:255],
                    description=f"งาน PM {task.task_no} ตรวจพบรายการไม่ผ่าน: {notes or '-'}",
                    priority=Priority.NORMAL,
                    status=TicketStatus.NEW,
                    channel="pm",
                    reporter_name=task.done_by,
                    reporter_type="technician",
                    sla_due_at=calc_sla_due(now, Priority.NORMAL),
                )
                db.add(ticket)
                db.flush()
                task.ticket_id = ticket.ticket_id
                auto_ticket = ticket.ticket_id

    write_audit(
        db, action="pm_task_edit" if is_reopen else "pm_task_submit", user=user,
        entity_type="pm_task",
        entity_id=task.task_no,
        old_value={"status": old_status},
        new_value={"status": "done", "failed_items": len(failed), "auto_ticket": auto_ticket},
        request=request,
    )
    db.commit()
    return {
        "id": task.id,
        "task_no": task.task_no,
        "status": task.status,
        "done_at": task.done_at,
        "next_due": task.next_due,
        "failed_items": len(failed),
        "auto_ticket_id": auto_ticket,
        # True = ผูกกับใบงานที่ค้างอยู่เดิม ไม่ได้เปิดใบใหม่ (กันแจ้งซ้ำ)
        "auto_ticket_is_existing": auto_ticket_existing,
    }


@app.post("/api/pm/tasks/{task_id}/skip")
def pm_skip(
    task_id: int,
    payload: PMSkipRequest,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    """ข้ามงาน PM พร้อมเหตุผล (§38 — ต้องบันทึกเหตุผลไว้ตรวจย้อนหลัง)"""
    task = db.get(PMTask, task_id)
    if not task:
        raise HTTPException(status_code=404, detail=f"ไม่พบงาน PM รหัส {task_id}")
    # งานที่ปิดแล้ว (done/skipped) แก้ย้อนหลังได้เฉพาะผู้ดูแลระดับสูง
    # — บันทึก audit เป็น action "pm_task_edit" แยกจากการบันทึกครั้งแรก
    is_reopen = task.status in ("done", "skipped")
    if is_reopen and user.role not in PM_TASK_OVERRIDE_ROLES:
        raise HTTPException(status_code=409, detail=f"งาน PM นี้ปิดแล้ว (สถานะ {task.status})")

    old_status = task.status
    task.status = "skipped"
    task.skip_reason = payload.reason
    task.done_by = getattr(user, "full_name", None) or getattr(user, "username", None)
    task.done_at = datetime.now(timezone.utc)
    write_audit(
        db, action="pm_task_edit" if is_reopen else "pm_task_skip", user=user,
        entity_type="pm_task",
        entity_id=task.task_no,
        old_value={"status": old_status},
        new_value={"status": "skipped", "reason": payload.reason},
        request=request,
    )
    db.commit()
    return {"id": task.id, "task_no": task.task_no, "status": task.status,
            "skip_reason": task.skip_reason}


# ─── PM Rule Engine (Blueprint §38) ───────────────────────────────────
# Rule 1 REPEATED_FAILURE | Rule 2 WARRANTY_EXPIRING | Rule 3 REPLACEMENT_CANDIDATE
# ตัวกฎอยู่ใน app/pm_rules.py — ที่นี่ทำหน้าที่เปิดให้เรียก/อ่านผล + RBAC

class HealthFlagUpdate(BaseModel):
    status: str = Field(..., pattern="^(acknowledged|resolved)$")


def _health_flag_out(f: DeviceHealthFlag) -> dict:
    return {
        "id": f.id,
        "device_id": f.device_id,
        "organization_id": f.organization_id,
        "rule_code": f.rule_code,
        "severity": f.severity,
        "message": f.message,
        "detail": f.detail,
        "status": f.status,
        "acknowledged_by": f.acknowledged_by,
        "resolved_at": f.resolved_at,
        "created_at": f.created_at,
    }


def _pm_rule_scope(user: User, organization_id: Optional[int]) -> Optional[int]:
    """แปลงคำขอเป็น organization_id ที่รันกฎได้จริงตามสิทธิ์ (None = ทุกโรงเรียน)"""
    scope = visible_org_ids(user)
    if organization_id is not None:
        check_org_access(user, organization_id)
        return organization_id
    if scope is None:
        return None  # global scope → รันทุกโรงเรียน
    if not scope:
        raise HTTPException(status_code=403, detail="บัญชีนี้ยังไม่ได้ผูกกับโรงเรียน")
    return next(iter(scope))


@app.post("/api/pm/rules/run")
def pm_rules_run(
    request: Request,
    organization_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    """รัน PM Rule Engine ทั้งสามกฎ (§38) — คืนจำนวน flag ที่สร้างใหม่

    กันแจ้งซ้ำในตัว: อุปกรณ์ที่มี flag ของกฎเดิมสถานะ open อยู่แล้วจะถูกข้าม
    """
    target = _pm_rule_scope(user, organization_id)
    result = pm_rules.run_all(db, organization_id=target)
    write_audit(
        db, action="pm_rules_run", user=user, entity_type="pm_rule",
        entity_id=str(target) if target is not None else "all",
        new_value={"created": result["created"], "by_rule": result["by_rule"]},
        request=request,
    )
    db.commit()
    return result


@app.get("/api/pm/flags")
def list_health_flags(
    status: Optional[str] = Query(None),
    rule_code: Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    organization_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    """รายการ flag จาก Rule Engine เรียงใหม่ก่อน — จำกัดตาม scope ของผู้ใช้"""
    stmt = select(DeviceHealthFlag).order_by(
        DeviceHealthFlag.created_at.desc(), DeviceHealthFlag.id.desc()
    )
    if status:
        stmt = stmt.where(DeviceHealthFlag.status == status)
    if rule_code:
        stmt = stmt.where(DeviceHealthFlag.rule_code == rule_code)
    if device_id:
        stmt = stmt.where(DeviceHealthFlag.device_id == device_id)
    if organization_id is not None:
        check_org_access(user, organization_id)
        stmt = stmt.where(DeviceHealthFlag.organization_id == organization_id)
    else:
        scope = visible_org_ids(user)
        if scope is not None:
            stmt = stmt.where(DeviceHealthFlag.organization_id.in_(scope or {-1}))
    rows = db.execute(stmt.offset(offset).limit(limit)).scalars().all()
    return [_health_flag_out(f) for f in rows]


@app.patch("/api/pm/flags/{flag_id}")
def update_health_flag(
    flag_id: int,
    payload: HealthFlagUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    """รับทราบ/ปิด flag — ปิดแล้วกฎเดิมจะสร้าง flag ใหม่ได้เมื่อเงื่อนไขเกิดอีก"""
    flag = db.get(DeviceHealthFlag, flag_id)
    if not flag:
        raise HTTPException(status_code=404, detail=f"ไม่พบรายการแจ้งเตือนรหัส {flag_id}")
    check_org_access(user, flag.organization_id)
    if flag.status == payload.status:
        return _health_flag_out(flag)

    old_status = flag.status
    flag.status = payload.status
    flag.acknowledged_by = (
        getattr(user, "full_name", None) or getattr(user, "username", None)
    )
    flag.resolved_at = datetime.now(timezone.utc) if payload.status == "resolved" else None
    write_audit(
        db, action="pm_flag_update", user=user, entity_type="device_health_flag",
        entity_id=str(flag.id),
        old_value={"status": old_status},
        new_value={"status": flag.status, "device_id": flag.device_id,
                   "rule_code": flag.rule_code},
        request=request,
    )
    db.commit()
    db.refresh(flag)
    return _health_flag_out(flag)


# ─── Audit Log (Blueprint §40) ────────────────────────────────────────

def _parse_audit_date(raw: Optional[str], field: str) -> Optional[datetime]:
    """แปลง "YYYY-MM-DD" (หรือ ISO เต็ม) เป็น datetime UTC; ค่าว่างได้ None

    รับ ISO ที่ลงท้าย "Z" ด้วย เพราะ <input type="date"> ส่งมาแค่วันที่ แต่การเรียก
    จากสคริปต์/Postman มักส่งเวลามาเต็ม — ถ้าไม่มี tzinfo ให้ถือเป็น UTC
    """
    value = (raw or "").strip()
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=422,
            detail=f"{field} ต้องเป็นวันที่รูปแบบ YYYY-MM-DD",
        )
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


@app.get("/api/deleted-records")
def list_deleted_records(
    limit: int = Query(30, ge=1, le=100), offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin")),
):
    """Only owners may inspect recoverable deletion metadata; payload stays server-side."""
    rows = db.execute(select(DeletedRecord).where(DeletedRecord.restored_at.is_(None))
                      .order_by(DeletedRecord.deleted_at.desc(), DeletedRecord.id.desc()).offset(offset).limit(limit)).scalars().all()
    return [{"id": row.id, "entity_type": row.entity_type, "entity_id": row.entity_id,
             "organization_id": row.organization_id, "deleted_at": row.deleted_at} for row in rows]


@app.post("/api/deleted-records/{record_id}/restore")
def restore_deleted_record(
    record_id: int, request: Request, db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin")),
):
    row = db.execute(select(DeletedRecord).where(DeletedRecord.id == record_id).with_for_update()).scalar_one_or_none()
    if row is None or row.restored_at is not None:
        raise HTTPException(status_code=404, detail="ไม่พบรายการที่กู้คืนได้")
    if db.get(Organization, row.organization_id) is None:
        raise HTTPException(status_code=409, detail="ต้องกู้คืนโรงเรียนต้นสังกัดก่อน")
    payload = json.loads(row.payload)
    if row.entity_type == "device":
        if db.execute(select(Device).where(Device.device_id == row.entity_id)).scalar_one_or_none():
            raise HTTPException(status_code=409, detail="มีรหัสอุปกรณ์นี้อยู่แล้ว")
        data = dict(payload["device"])
        if data.get("room_id"):
            room = db.get(Room, data["room_id"])
            if room is None:
                data["room_id"] = None
            elif room.organization_id != row.organization_id:
                raise HTTPException(status_code=409, detail="ห้องของอุปกรณ์เปลี่ยนโรงเรียนแล้ว")
        if data.get("qr_token") and db.execute(select(Device).where(Device.qr_token == data["qr_token"])).scalar_one_or_none():
            raise HTTPException(status_code=409, detail="QR token นี้ถูกใช้งานโดยอุปกรณ์อื่นแล้ว")
        db.add(_recovery_model(Device, data))
        db.flush()
        for scan in payload.get("scans", []):
            db.add(_recovery_model(ScanLog, scan))
    elif row.entity_type == "ticket":
        if db.execute(select(RepairTicket).where(RepairTicket.ticket_id == row.entity_id)).scalar_one_or_none():
            raise HTTPException(status_code=409, detail="มีเลขใบงานนี้อยู่แล้ว")
        data = payload["ticket"]
        device = db.execute(select(Device).where(Device.device_id == data["device_id"])).scalar_one_or_none()
        if device is None:
            raise HTTPException(status_code=409, detail="ต้องกู้คืนอุปกรณ์ของใบงานก่อน")
        if device.organization_id != row.organization_id:
            raise HTTPException(status_code=409, detail="อุปกรณ์นี้ย้ายไปโรงเรียนอื่นแล้ว")
        ticket = _recovery_model(RepairTicket, data)
        db.add(ticket)
        db.flush()
        for update in payload.get("updates", []):
            db.add(_recovery_model(TicketUpdate, update, ticket_id=ticket.id))
        for comment in payload.get("comments", []):
            db.add(_recovery_model(TicketComment, comment))
        for attachment in payload.get("attachments", []):
            db.add(_recovery_model(TicketAttachment, attachment))
    else:
        raise HTTPException(status_code=409, detail="ข้อมูลชนิดนี้ยังไม่รองรับการกู้คืน")
    row.restored_at = datetime.now(timezone.utc)
    write_audit(db, action=f"{row.entity_type}_restore", user=user, entity_type=row.entity_type,
                entity_id=row.entity_id, new_value={"deleted_record_id": row.id}, request=request)
    db.commit()
    return {"message": "restored", "entity_type": row.entity_type, "entity_id": row.entity_id}


@app.get("/api/audit-logs")
def list_audit_logs(
    action: Optional[str] = Query(None),
    include_logins: bool = Query(True, description="รวมเหตุการณ์เข้าสู่ระบบ"),
    entity_type: Optional[str] = Query(None),
    entity_id: Optional[str] = Query(None),
    user_id: Optional[int] = Query(None),
    date_from: Optional[str] = Query(None, description="YYYY-MM-DD (รวมวันนั้น)"),
    date_to: Optional[str] = Query(None, description="YYYY-MM-DD (รวมวันนั้นทั้งวัน)"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin")),
):
    """ประวัติการกระทำสำคัญ เรียงใหม่ก่อน — admin ขึ้นไปเท่านั้น (§40)"""
    stmt = select(AuditLog).order_by(AuditLog.created_at.desc(), AuditLog.id.desc())
    if action:
        stmt = stmt.where(AuditLog.action == action)
    elif not include_logins:
        stmt = stmt.where(AuditLog.action.notin_(["login", "login_failed"]))
    if entity_type:
        stmt = stmt.where(AuditLog.entity_type == entity_type)
    if entity_id:
        stmt = stmt.where(AuditLog.entity_id == str(entity_id))
    if user_id:
        stmt = stmt.where(AuditLog.user_id == user_id)
    dt_from = _parse_audit_date(date_from, "date_from")
    dt_to = _parse_audit_date(date_to, "date_to")
    if dt_from and dt_to and dt_to < dt_from:
        raise HTTPException(status_code=422, detail="date_to ต้องไม่น้อยกว่า date_from")
    if dt_from:
        stmt = stmt.where(AuditLog.created_at >= dt_from)
    if dt_to:
        # ถ้าส่งมาแค่วันที่ (เวลา 00:00) ให้ครอบทั้งวันโดยบวก 1 วันแล้วใช้ <
        # ไม่อย่างนั้น 'ถึงวันนี้' จะได้ 0 แถว เพราะทุก log มีเวลามากกว่า 00:00
        end = dt_to + timedelta(days=1) if dt_to.time() == datetime.min.time() else dt_to
        stmt = stmt.where(AuditLog.created_at < end)
    rows = db.execute(stmt.offset(offset).limit(limit)).scalars().all()
    return [
        {
            "id": r.id,
            "user_id": r.user_id,
            "user_name": r.user_name,
            "user_role": r.user_role,
            "action": r.action,
            "entity_type": r.entity_type,
            "entity_id": r.entity_id,
            "old_value": json.loads(r.old_value) if r.old_value and r.old_value.startswith(("{", "[")) else r.old_value,
            "new_value": json.loads(r.new_value) if r.new_value and r.new_value.startswith(("{", "[")) else r.new_value,
            "ip_address": r.ip_address,
            "created_at": r.created_at,
        }
        for r in rows
    ]



# ─── QR Service (TOR 1.5.4 / 5.3) ─────────────────────────────────────

@app.get("/api/qr/resolve/{token}")
@limiter.limit("30/minute")
def qr_resolve(request: Request, token: str, db: Session = Depends(get_db)):
    """แปลง QR token → ข้อมูลอุปกรณ์ (ไม่ต้อง login, มี rate limit ตาม spec)"""
    code = (token or "").strip()
    device = (
        db.execute(select(Device).where(Device.qr_token == code)).scalar_one_or_none()
        if code
        else None
    )
    if not device and code:
        device = db.execute(
            select(Device).where(Device.device_id == code)
        ).scalar_one_or_none() or db.execute(
            select(Device).where(Device.device_id == code.upper())
        ).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="ไม่พบอุปกรณ์ที่ตรงกับ QR Code นี้")
    room = db.get(Room, device.room_id) if device.room_id else None
    org = db.get(Organization, device.organization_id)
    return {
        "type": "device",
        "device": {
            "device_id": device.device_id,
            "device_type": device.device_type,
            "brand": device.brand,
            "model": device.model,
            "serial_number": device.serial_number,
            "status": device.status,
            "warranty_until": device.warranty_until,
        },
        "room": {"name": room.name if room else None, "code": room.code if room else None,
                 "building": room.building if room else None},
        "organization": {"code": org.code if org else None, "name": org.name if org else None},
        # สแกนแล้วรู้ทันทีว่าอุปกรณ์นี้ถูกแจ้งไว้แล้วหรือยัง — ผู้แจ้งไม่ต้องกรอกฟอร์มทิ้ง
        # ชื่อ/หมวดอุปกรณ์แบบอ่านรู้เรื่อง — หน้าแจ้งซ่อมและหน้าสแกนแสดงคู่กับรหัส
        "device_category": device_category_of(device.device_type),
        "device_label": device_display_label(device),
        **open_ticket_fields(db, device.device_id),
        "qr_url": (
            f"/scan?t={device.qr_token}"
            if device.qr_token
            else f"/scan?device={device.device_id}"
        ),
    }


@app.post("/api/qr/rotate/{device_id}")
def qr_rotate(device_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support"))):
    """ออก QR token ใหม่ (สติกเกอร์หาย/ถูกนำไปใช้ผิด) — device_id เดิม ไม่ต้องพิมพ์ใหม่ทั้งเครื่อง"""
    import secrets
    device = db.execute(select(Device).where(Device.device_id == device_id)).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    # it_support ที่มีสังกัดเห็น/จัดการได้เฉพาะอุปกรณ์ในรรตัวเอง
    check_org_access(user, device.organization_id)
    device.qr_token = secrets.token_urlsafe(24)
    db.commit()
    return {"device_id": device.device_id, "qr_token": device.qr_token,
            "qr_url": f"/scan?t={device.qr_token}"}


@app.get("/api/qr/lookup")
@limiter.limit("30/minute")
def qr_lookup(
    request: Request,
    q: str = Query(..., min_length=2),
    limit: int = Query(10, ge=1, le=50),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles(*ASSIGNABLE_ROLES, *RETIRED_ROLES)),
):
    """ช่องทางสำรอง QR ชำรุด — ค้นหาด้วยรหัสอุปกรณ์ (รองรับบางส่วน)

    ห้ามคืน qr_token: เดิม endpoint นี้ค้นแบบ partial (%q%) และส่ง token จริงกลับไป
    ทำให้ค้นด้วยคำสั้น ๆ เช่น "DEV" แล้วเก็บ token ไปสร้างลิงก์สแกนได้ทั้งระบบ
    """
    rows = db.execute(
        select(Device)
        .where(Device.device_id.ilike(f"%{q}%"))
        .order_by(Device.device_id)
        .limit(limit)
    ).scalars().all()
    # กันแจ้งซ้ำ: ช่องนี้คือทางเข้าแจ้งซ่อมเวลา QR ชำรุด ผลค้นจึงต้องบอกว่าเครื่องไหน
    # มีใบงานค้าง และแสดงชื่ออุปกรณ์ที่คนอ่านรู้เรื่อง ไม่ใช่รหัสเปล่า ๆ
    open_map = open_tickets_by_device(db, [d.device_id for d in rows])
    return [
        {
            "device_id": d.device_id,
            "device_type": d.device_type,
            "device_category": device_category_of(d.device_type),
            "device_label": device_display_label(d),
            "brand": d.brand,
            "model": d.model,
            "organization_id": d.organization_id,
            # อ้างด้วย device_id เท่านั้น — ผู้ที่ถือ qr_token สร้างลิงก์สแกนของห้องใดก็ได้
            "qr_url": f"/scan?device={d.device_id}",
            "has_open_ticket": d.device_id in open_map,
            "open_ticket": open_map.get(d.device_id),
        }
        for d in rows
    ]


@app.get("/api/rooms/{room_id}/devices")
def room_devices(room_id: int, db: Session = Depends(get_db)):
    """รายการอุปกรณ์ในห้อง (Room QR — TOR 1.5.4)"""
    room = db.get(Room, room_id)
    if not room:
        raise HTTPException(status_code=404, detail="Room not found")
    devices = db.execute(
        select(Device).where(Device.room_id == room_id).order_by(Device.device_id)
    ).scalars().all()
    return {
        "room": {"id": room.id, "code": room.code, "name": room.name,
                 "building": room.building, "floor": room.floor},
        "devices": [
            {
                "device_id": d.device_id,
                "device_type": d.device_type,
                "brand": d.brand,
                "model": d.model,
                "status": d.status,
                "qr_url": f"/scan?t={d.qr_token}" if d.qr_token else f"/scan?device={d.device_id}",
            }
            for d in devices
        ],
    }


@app.get("/api/qr/batch")
def qr_batch(organization_id: Optional[int] = Query(None), db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """รายการ QR ทั้งหมด (สำหรับหน้าพิมพ์ batch — TOR 1.5.4) — จำกัดตามบทบาท"""
    scope = visible_org_ids(user)
    stmt = select(Device).order_by(Device.device_id)
    if scope is not None:
        if not scope:
            return []  # scope ว่าง → ไม่เห็นข้อมูล
        stmt = stmt.where(Device.organization_id.in_(scope))
    if organization_id:
        if scope is not None and organization_id not in scope:
            raise HTTPException(status_code=403, detail="คุณไม่มีสิทธิ์เข้าถึงข้อมูลของโรงเรียนนี้")
        stmt = stmt.where(Device.organization_id == organization_id)
    rows = db.execute(stmt).scalars().all()
    return [
        {
            "device_id": d.device_id,
            "device_type": d.device_type,
            "brand": d.brand,
            "model": d.model,
            "qr_url": f"/scan?t={d.qr_token}" if d.qr_token else f"/scan?device={d.device_id}",
        }
        for d in rows
    ]


# ═══════════════════════════════════════════════════════════════════════
# Batch 1 additions — Ticket lifecycle / public track / rooms / settings /
# reports / line webhook
# ═══════════════════════════════════════════════════════════════════════

# ─── Request schemas ───────────────────────────────────────────────────
class TicketAssignReq(BaseModel):
    assignee: str = Field(..., min_length=2, max_length=128)
    note: Optional[str] = None

class TicketResolveReq(BaseModel):
    root_cause: Optional[str] = None
    solution: str = Field(..., min_length=3, max_length=2000)
    parts_used: Optional[list] = None
    after_photos: Optional[list[str]] = None
    suggest_to_kb: bool = False

class TicketCloseReq(BaseModel):
    rating: Optional[int] = Field(None, ge=1, le=5)
    feedback: Optional[str] = None

class TicketCommentReq(BaseModel):
    note: str = Field(..., min_length=1, max_length=2000)
    is_internal: bool = False
    author_name: Optional[str] = None

class TicketAttachmentReq(BaseModel):
    file_url: str = Field(..., min_length=3)
    file_size: Optional[int] = None
    mime_type: Optional[str] = None
    phase: Optional[str] = None  # before | after
    uploaded_by: Optional[str] = None

# ─── Public ติดตามสถานะด้วยหมายเลข Ticket (TOR 5.7) ───────────────────
@app.get("/api/devices/{device_id}/recent")
def device_recent_ticket(device_id: str, db: Session = Depends(get_db)):
    """คืน Ticket ล่าสุดของอุปกรณ์ (ไม่ว่าสถานะไหน) — ใช้ช่วยผู้ใช้หาเลข Ticket คืนเมื่อลืม"""
    device = db.execute(select(Device).where(Device.device_id == device_id)).scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    latest = db.execute(
        select(RepairTicket)
        .where(RepairTicket.device_id == device_id)
        .order_by(RepairTicket.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
    if not latest:
        return {"device_id": device_id, "recent_ticket": None}
    return {
        "device_id": device_id,
        "recent_ticket": {
            "ticket_id": latest.ticket_id,
            "status": latest.status,
            "priority": latest.priority,
            "title": latest.title,
            "created_at": latest.created_at,
            "closed_at": latest.closed_at,
        },
    }

@app.get("/api/tickets/track/{ticket_no}")
def ticket_track(ticket_no: str, db: Session = Depends(get_db)):
    """ติดตามสถานะด้วยหมายเลข Ticket — เปิดสาธารณะ คืนข้อมูลจำกัด (ไม่เปิดเผยข้อมูลส่วนบุคคล)"""
    t = find_ticket_by_no(db, ticket_no)
    device = db.execute(select(Device).where(Device.device_id == t.device_id)).scalar_one_or_none()
    room = db.get(Room, device.room_id) if device and device.room_id else None
    status_label = {
        "new": "รอรับเรื่อง", "assigned": "มอบหมายแล้ว", "in_progress": "กำลังดำเนินการ",
        "pending": "รออะไหล่/รอภายนอก", "resolved": "ซ่อมเสร็จ รอผู้แจ้งยืนยัน",
        "closed": "ปิดงาน", "cancelled": "ยกเลิก",
    }.get(t.status, t.status)
    order = ["new", "assigned", "in_progress", "pending", "resolved", "closed"]
    # ป้ายสถานะจากตารางกลาง — ตารางเดิมด้านบนตกหล่น waiting_parts/waiting_user
    status_label = PUBLIC_STATUS_LABELS.get(t.status, status_label)
    # waiting_parts/waiting_user คือการ "รอ" หลังเริ่มงานแล้ว นับความคืบหน้าเท่า pending
    # ไม่ใช่ idx = -1 ที่ทำให้แถบความคืบหน้าย้อนกลับไปขั้นแรก
    step_status = "pending" if t.status in ("waiting_parts", "waiting_user") else t.status
    idx = order.index(step_status) if step_status in order else -1
    return {
        "ticket_no": t.ticket_id,
        "status": t.status,
        "status_label": status_label,
        "device_code": device.device_id if device else None,
        "device_type": device.device_type if device else None,
        "device_category": device_category_of(device.device_type) if device else None,
        "device_label": device_display_label(device),
        "room_name": room.name if room else None,
        "title": t.title,
        "priority": t.priority,
        "created_at": t.created_at,
        "estimated_completion": t.sla_due_at,
        "closed_at": t.closed_at,
        # งานยังไม่ปิด → หน้าติดตามเปิดช่อง "แจ้งข้อมูลเพิ่ม" เข้าใบเดิมได้
        "can_add_note": t.status in OPEN_TICKET_STATUSES,
        "progress": [
            {"step": "รับเรื่อง", "done": True},
            {"step": "มอบหมายงาน", "done": idx >= 1},
            {"step": "กำลังดำเนินการ", "done": idx >= 2},
            {"step": "ซ่อมเสร็จ", "done": idx >= 4},
            {"step": "ปิดงาน", "done": t.status in ("closed", "cancelled")},
        ],
    }

# ─── Room / Building endpoints ─────────────────────────────────────────
@app.get("/api/organizations/{org_id}/buildings")
def list_buildings(org_id: int, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user_optional)):
    check_org_access(user, org_id) if user else None
    rows = db.execute(
        select(Building).where(Building.organization_id == org_id).order_by(Building.code)
    ).scalars().all()
    return [{"id": b.id, "code": b.code, "name": b.name} for b in rows]

@app.post("/api/organizations/{org_id}/buildings", status_code=201)
def create_building(org_id: int, payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school"))):
    check_org_access(user, org_id)
    b = Building(organization_id=org_id, code=payload.get("code", ""), name=payload.get("name", ""))
    db.add(b); db.commit(); db.refresh(b)
    return {"id": b.id, "code": b.code, "name": b.name}

@app.get("/api/organizations/{org_id}/rooms")
def list_rooms(org_id: int, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user_optional)):
    """รายการห้องในโรงเรียน (ใช้ในหน้าเพิ่มอุปกรณ์/จัดการห้อง)"""
    if user:
        check_org_access(user, org_id)
    rows = db.execute(
        select(Room).where(Room.organization_id == org_id).order_by(Room.code)
    ).scalars().all()
    return [
        {
            "id": r.id, "code": r.code, "name": r.name, "building": r.building,
            "floor": r.floor,
            "gps_lat": float(r.gps_lat) if r.gps_lat is not None else None,
            "gps_lng": float(r.gps_lng) if r.gps_lng is not None else None,
            "device_count": db.execute(text("SELECT COUNT(*) FROM devices WHERE room_id=:rid"), {"rid": r.id}).scalar_one(),
        }
        for r in rows
    ]

# ─── Ticket lifecycle actions (TOR 5.7) ────────────────────────────────
def _get_ticket_or_404(db: Session, ticket_id: str) -> RepairTicket:
    t = db.execute(select(RepairTicket).where(RepairTicket.ticket_id == ticket_id)).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return t

def _add_update(db: Session, t: RepairTicket, from_s: Optional[str], to_s: Optional[str], note: Optional[str], author: Optional[str], role: Optional[str]):
    db.add(TicketUpdate(ticket=t, from_status=from_s, to_status=to_s, note=note, author_name=author, author_role=role))

@app.post("/api/tickets/{ticket_id}/assign", status_code=200)
def ticket_assign(ticket_id: str, payload: TicketAssignReq, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin"))):
    """มอบหมายงานให้ช่าง (admin/super_admin)"""
    t = _get_ticket_or_404(db, ticket_id)
    old = t.status
    old_assignee = t.assigned_to  # §40: เก็บผู้รับผิดชอบเดิมก่อนถูกเขียนทับ
    t.assigned_to = payload.assignee
    if old == "new":
        apply_transition(db, t, "assigned", force=True,
                         author_name=user.line_display_name or "Admin",
                         author_role=user.role,
                         note=payload.note or f"มอบหมายให้ {payload.assignee}")
    else:
        _add_update(db, t, old, t.status, payload.note or f"มอบหมายให้ {payload.assignee}", user.line_display_name or "Admin", user.role)
    # §40: มอบหมายงานให้ช่าง
    write_audit(
        db, action="ticket_assign", user=user, entity_type="ticket", entity_id=t.ticket_id,
        old_value={"status": old, "assigned_to": old_assignee},
        new_value={"status": t.status, "assigned_to": payload.assignee,
                   "note": payload.note},
        request=request,
    )
    db.commit()
    return {"ticket_id": t.ticket_id, "status": t.status, "assigned_to": t.assigned_to}

@app.post("/api/tickets/{ticket_id}/accept", status_code=200)
def ticket_accept(ticket_id: str, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """ช่างรับงาน — assigned/new → in_progress"""
    t = _get_ticket_or_404(db, ticket_id)
    old_status = t.status  # §40: เก็บสถานะเดิมไว้บันทึก Audit Log
    check_ticket_access(db, user, t)
    if t.status not in ("assigned", "new"):
        raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": f"สถานะปัจจุบันคือ {t.status} — ไม่สามารถรับงานได้"})
    t.assigned_to = t.assigned_to or (user.line_display_name or "ช่าง")
    apply_transition(db, t, "in_progress", force=True,
                     author_name=user.line_display_name or "Technician",
                     author_role=user.role, note="รับงานแล้ว กำลังดำเนินการ")
    # §40: ช่างรับงาน = เปลี่ยน Status
    write_audit(
        db, action="ticket_accept", user=user, entity_type="ticket", entity_id=t.ticket_id,
        old_value={"status": old_status},
        new_value={"status": t.status, "assigned_to": t.assigned_to},
        request=request,
    )
    db.commit()
    return {"ticket_id": t.ticket_id, "status": t.status, "assigned_to": t.assigned_to}

@app.post("/api/tickets/{ticket_id}/resolve", status_code=200)
def ticket_resolve(ticket_id: str, payload: TicketResolveReq, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """บันทึกผลการซ่อม — resolved + บันทึกสาเหตุ/วิธีแก้/รูปหลังซ่อม"""
    t = _get_ticket_or_404(db, ticket_id)
    old_status = t.status  # §40: เก็บสถานะเดิมไว้บันทึก Audit Log
    check_ticket_access(db, user, t)
    if not payload.solution.strip():
        raise HTTPException(status_code=400, detail="ต้องกรอกวิธีแก้ไข (solution)")
    t.root_cause = payload.root_cause
    t.solution = payload.solution
    t.parts_used = json.dumps(payload.parts_used or [], ensure_ascii=False) if payload.parts_used else None
    t.resolution_notes = " ".join(payload.after_photos or []) or None
    t.resolved_at = datetime.now(timezone.utc)
    if payload.after_photos:
        for url in payload.after_photos:
            db.add(TicketAttachment(ticket_id=t.ticket_id, file_url=url, phase="after", uploaded_by=user.line_display_name))
    apply_transition(db, t, "resolved", force=True,
                     author_name=user.line_display_name or "Technician",
                     author_role=user.role, note="ซ่อมเสร็จ: " + payload.solution[:150])
    # §40: บันทึกผลการซ่อม = เปลี่ยน Status (เก็บสาเหตุ/วิธีแก้แบบย่อ)
    write_audit(
        db, action="ticket_resolve", user=user, entity_type="ticket", entity_id=t.ticket_id,
        old_value={"status": old_status},
        new_value={"status": t.status, "root_cause": payload.root_cause,
                   "solution": payload.solution[:500]},
        request=request,
    )
    db.commit()
    from app.ticket_rating_invite import invite_staff_rating
    invite_staff_rating(db, t)
    return {"ticket_id": t.ticket_id, "status": t.status, "resolved_at": t.resolved_at, "sla_met": t.sla_met}

@app.post("/api/tickets/{ticket_id}/close", status_code=200)
def ticket_close(ticket_id: str, payload: TicketCloseReq, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """ผู้แจ้ง/admin ปิดงาน + ให้คะแนน (resolved → closed)"""
    t = _get_ticket_or_404(db, ticket_id)
    old_status = t.status  # §40: เก็บสถานะเดิมไว้บันทึก Audit Log
    check_ticket_access(db, user, t)
    if t.status != "resolved":
        raise HTTPException(status_code=409, detail={"code": "INVALID_STATUS_TRANSITION", "message": f"ต้องเป็นสถานะ resolved ก่อนปิด (ปัจจุบัน: {t.status})"})
    t.closed_at = datetime.now(timezone.utc)
    if payload.rating is not None:
        t.rating = payload.rating
    if payload.feedback:
        t.feedback = payload.feedback
    apply_transition(db, t, "closed", force=True,
                     author_name=user.line_display_name or "User",
                     author_role=user.role, note=payload.feedback or "ผู้แจ้งยืนยันปิดงาน")
    # §40: ปิดงาน (พร้อมคะแนนความพึงพอใจ)
    write_audit(
        db, action="ticket_close", user=user, entity_type="ticket", entity_id=t.ticket_id,
        old_value={"status": old_status},
        new_value={"status": t.status, "rating": payload.rating,
                   "feedback": payload.feedback},
        request=request,
    )
    db.commit()
    from app.ticket_rating_invite import invite_staff_rating
    invite_staff_rating(db, t)
    return {"ticket_id": t.ticket_id, "status": t.status, "closed_at": t.closed_at, "rating": t.rating}

@app.post("/api/tickets/{ticket_id}/reopen", status_code=200)
def ticket_reopen(ticket_id: str, payload: TicketCommentReq, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """เปิดงานใหม่กรณีปัญหากลับมา (closed → in_progress)"""
    t = _get_ticket_or_404(db, ticket_id)
    old_status = t.status  # §40: เก็บสถานะเดิมไว้บันทึก Audit Log
    check_ticket_access(db, user, t)
    if t.status != "closed":
        raise HTTPException(status_code=409, detail={"code": "INVALID_STATUS_TRANSITION", "message": f"เฉพาะงานที่ปิดแล้วเท่านั้นที่เปิดใหม่ได้ (ปัจจุบัน: {t.status})"})
    t.closed_at = None
    t.resolved_at = None
    apply_transition(db, t, "in_progress", force=True,
                     author_name=user.line_display_name or "User",
                     author_role=user.role, note=payload.note or "เปิดงานใหม่ (ปัญหากลับมาเกิดซ้ำ)")
    # §40: เปิดงานใหม่ — ต้องตรวจย้อนได้ว่าใครเปิดงานที่ปิดแล้ว
    write_audit(
        db, action="ticket_reopen", user=user, entity_type="ticket", entity_id=t.ticket_id,
        old_value={"status": old_status},
        new_value={"status": t.status, "note": payload.note},
        request=request,
    )
    db.commit()
    return {"ticket_id": t.ticket_id, "status": t.status}

@app.post("/api/tickets/{ticket_id}/cancel", status_code=200)
def ticket_cancel(ticket_id: str, payload: TicketCommentReq, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """ยกเลิกงานพร้อมเหตุผล"""
    t = _get_ticket_or_404(db, ticket_id)
    old_status = t.status  # §40: เก็บสถานะเดิมไว้บันทึก Audit Log
    check_ticket_access(db, user, t)
    if t.status in ("closed", "cancelled"):
        raise HTTPException(status_code=409, detail={"code": "INVALID_STATUS_TRANSITION", "message": f"สถานะ {t.status} ไม่สามารถยกเลิกได้"})
    t.closed_at = datetime.now(timezone.utc)
    apply_transition(db, t, "cancelled", force=True,
                     author_name=user.line_display_name or "User",
                     author_role=user.role, note=payload.note or "ยกเลิก")
    # §40: ยกเลิกงาน — บันทึกเหตุผลไว้ตรวจสอบ
    write_audit(
        db, action="ticket_cancel", user=user, entity_type="ticket", entity_id=t.ticket_id,
        old_value={"status": old_status},
        new_value={"status": t.status, "note": payload.note},
        request=request,
    )
    db.commit()
    return {"ticket_id": t.ticket_id, "status": t.status}

# ─── Comments (TOR 5.7) ────────────────────────────────────────────────
@app.get("/api/tickets/{ticket_id}/comments")
def list_ticket_comments(ticket_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = _get_ticket_or_404(db, ticket_id)
    check_ticket_access(db, user, ticket)
    rows = db.execute(select(TicketComment).where(TicketComment.ticket_id == ticket_id).order_by(TicketComment.created_at)).scalars().all()
    if user.role not in ("owner", "super_admin", "admin", "admin_school", "it_support"):
        rows = [c for c in rows if not c.is_internal]
    return [{"id": c.id, "note": c.note, "author_name": c.author_name, "author_role": c.author_role,
             "is_internal": c.is_internal, "created_at": c.created_at} for c in rows]

@app.post("/api/tickets/{ticket_id}/comments", status_code=201)
def add_ticket_comment(ticket_id: str, payload: TicketCommentReq, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = _get_ticket_or_404(db, ticket_id)
    check_ticket_access(db, user, ticket)
    if payload.is_internal and user.role not in ("owner", "super_admin", "admin", "admin_school", "it_support"):
        raise HTTPException(status_code=403, detail="เฉพาะเจ้าหน้าที่เท่านั้นที่เพิ่มหมายเหตุภายในได้")
    c = TicketComment(ticket_id=ticket_id, note=payload.note, is_internal=payload.is_internal,
                      author_id=user.id,
                      author_name=user.line_display_name or "User",
                      author_role=user.role)
    db.add(c); db.commit(); db.refresh(c)
    return {"id": c.id, "note": c.note, "author_name": c.author_name, "created_at": c.created_at}

# ─── Attachments (TOR 5.7) ─────────────────────────────────────────────
@app.get("/api/tickets/{ticket_id}/attachments")
def list_ticket_attachments(ticket_id: str, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = _get_ticket_or_404(db, ticket_id)
    check_ticket_access(db, user, ticket)
    rows = db.execute(select(TicketAttachment).where(TicketAttachment.ticket_id == ticket_id).order_by(TicketAttachment.created_at)).scalars().all()
    return [{"id": a.id, "file_url": a.file_url, "phase": a.phase, "mime_type": a.mime_type,
             "file_size": a.file_size, "uploaded_by": a.uploaded_by, "created_at": a.created_at} for a in rows]

@app.post("/api/tickets/{ticket_id}/attachments", status_code=201)
def add_ticket_attachment(ticket_id: str, payload: TicketAttachmentReq, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    ticket = _get_ticket_or_404(db, ticket_id)
    check_ticket_access(db, user, ticket)
    a = TicketAttachment(ticket_id=ticket_id, file_url=payload.file_url, file_size=payload.file_size,
                         mime_type=payload.mime_type, phase=payload.phase,
                         uploaded_by=user.line_display_name or "User")
    db.add(a); db.commit(); db.refresh(a)
    return {"id": a.id, "file_url": a.file_url, "phase": a.phase, "created_at": a.created_at}

# ─── Settings (TOR 5.11) ───────────────────────────────────────────────
def _read_setting(db: Session, key: str, default):
    row = db.execute(select(Setting).where(Setting.key == key)).scalar_one_or_none()
    if not row:
        return default
    try:
        return json.loads(row.value)
    except Exception:
        return default

@app.get("/api/settings")
def get_settings(db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin"))):
    return {
        "sla_hours": _read_setting(db, "sla_hours", {"critical": 2, "high": 8, "normal": 24, "low": 72}),
        "working_hours": _read_setting(db, "working_hours", {"start": "08:00", "end": "16:30", "days": [1, 2, 3, 4, 5]}),
        "auto_close_days": _read_setting(db, "auto_close_days", 3),
        "ai_confidence_threshold": _read_setting(db, "ai_confidence_threshold", 0.75),
    }

@app.patch("/api/settings")
def update_settings(payload: dict, request: Request, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin"))):
    """ปรับค่า SLA / working hours / auto-close / AI threshold — ไม่ต้อง deploy ใหม่"""
    allowed = {"sla_hours", "working_hours", "auto_close_days", "ai_confidence_threshold"}
    updated = []
    old_values = {}  # §40: ค่าก่อนแก้ ใช้เทียบย้อนหลังว่าใครเปลี่ยน SLA/เวลาทำงาน
    new_values = {}
    for key, value in payload.items():
        if key not in allowed:
            continue
        row = db.execute(select(Setting).where(Setting.key == key)).scalar_one_or_none()
        if row:
            old_values[key] = row.value
            row.value = json.dumps(value)
        else:
            old_values[key] = None
            db.add(Setting(key=key, value=json.dumps(value)))
        new_values[key] = value
        updated.append(key)
    if updated:
        # §40: เปลี่ยนค่าระบบต้องบันทึก (entity_id จำกัด 64 ตัวอักษรตามคอลัมน์)
        write_audit(
            db, action="settings_update", user=user, entity_type="setting",
            entity_id=",".join(updated)[:64],
            old_value=old_values, new_value=new_values, request=request,
        )
    db.commit()
    return {"updated": updated, "message": "Settings updated"}

# ─── Reports (TOR 5.10) ────────────────────────────────────────────────
@app.get("/api/reports/summary")
def report_summary(organization_id: Optional[int] = Query(None), db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """สรุปสถิติภาพรวม — สำหรับ Dashboard / รายงาน"""
    scope = visible_org_ids(user)
    # admin_school/it_support(มีสังกัด): บังคับให้ดูเฉพาะรรตัวเอง (กันส่ง org คนอื่น)
    if scope is not None:
        if organization_id is not None and organization_id not in scope:
            raise HTTPException(status_code=403, detail="คุณไม่มีสิทธิ์เข้าถึงข้อมูลของโรงเรียนนี้")
        # ถ้า scope ว่าง (admin_school ไม่มีสังกัด) → ดูได้แค่ 0 รายการ ไม่ให้เห็นข้อมูลบริษัท
        if not scope:
            return {"total_tickets": 0, "total_devices": 0, "by_status": {}, "by_priority": {}, "open_total": 0}
        organization_id = organization_id or next(iter(scope))
    org_cond = ""
    params: dict = {}
    if organization_id:
        org_cond = " AND d.organization_id = :oid"
        params["oid"] = organization_id
    total = db.execute(text("SELECT COUNT(*) FROM repair_tickets t JOIN devices d ON d.device_id=t.device_id WHERE 1=1" + org_cond), params).scalar_one()
    by_status = {r[0]: r[1] for r in db.execute(text(
        "SELECT t.status, COUNT(*) FROM repair_tickets t JOIN devices d ON d.device_id=t.device_id WHERE 1=1" + org_cond + " GROUP BY t.status"), params).fetchall()}
    by_priority = {r[0]: r[1] for r in db.execute(text(
        "SELECT t.priority, COUNT(*) FROM repair_tickets t JOIN devices d ON d.device_id=t.device_id WHERE 1=1" + org_cond + " GROUP BY t.priority"), params).fetchall()}
    device_total = db.execute(text("SELECT COUNT(*) FROM devices d WHERE 1=1" + org_cond), params).scalar_one()
    def g(s): return by_status.get(s, 0)
    def p(s): return by_priority.get(s, 0)
    return {
        "total_tickets": total,
        "total_devices": device_total,
        "by_status": {"new": g("new"), "assigned": g("assigned"), "in_progress": g("in_progress"),
                      "pending": g("pending"), "resolved": g("resolved"), "closed": g("closed"), "cancelled": g("cancelled")},
        "by_priority": {"critical": p("critical"), "high": p("high"), "normal": p("normal"), "low": p("low")},
        "open_total": g("new") + g("assigned") + g("in_progress") + g("pending"),
    }

@app.get("/api/reports/top-issues")
def report_top_issues(organization_id: Optional[int] = Query(None), limit: int = Query(10, ge=1, le=50),
                      db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """10 อันดับปัญหาที่พบบ่อย (จัดกลุ่มด้วย device_type)"""
    scope = visible_org_ids(user)
    if scope is not None:
        if organization_id is not None and organization_id not in scope:
            raise HTTPException(status_code=403, detail="คุณไม่มีสิทธิ์เข้าถึงข้อมูลของโรงเรียนนี้")
        if not scope:
            return []  # admin_school ไม่มีสังกัด → ไม่เห็นข้อมูลบริษัท
        organization_id = organization_id or next(iter(scope))
    org_cond = ""
    params = {"lim": limit}
    if organization_id:
        org_cond = " AND d.organization_id = :oid"
        params["oid"] = organization_id
    rows = db.execute(text(
        "SELECT d.device_type AS cat, COUNT(*) AS c "
        "FROM repair_tickets t JOIN devices d ON d.device_id=t.device_id WHERE 1=1" + org_cond +
        " GROUP BY d.device_type ORDER BY c DESC LIMIT :lim"), params).fetchall()
    total = sum(x.c for x in rows) or 1
    return [{"rank": i + 1, "device_type": r.cat, "count": r.c, "percentage": round(r.c * 100.0 / total, 1)} for i, r in enumerate(rows)]

@app.get("/api/reports/top-devices")
def report_top_devices(organization_id: Optional[int] = Query(None), limit: int = Query(10, ge=1, le=50),
                       db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """อุปกรณ์ที่เสียบ่อย (Repeat failure — TOR 1.5.8)"""
    scope = visible_org_ids(user)
    if scope is not None:
        if organization_id is not None and organization_id not in scope:
            raise HTTPException(status_code=403, detail="คุณไม่มีสิทธิ์เข้าถึงข้อมูลของโรงเรียนนี้")
        if not scope:
            return []  # admin_school ไม่มีสังกัด → ไม่เห็นข้อมูลบริษัท
        organization_id = organization_id or next(iter(scope))
    org_cond = ""
    params = {"lim": limit}
    if organization_id:
        org_cond = " AND d.organization_id = :oid"
        params["oid"] = organization_id
    rows = db.execute(text(
        "SELECT d.device_id, d.device_type, COALESCE(r.name,'') AS room_name, COUNT(t.id) AS failure_count, MAX(t.created_at) AS last_fail "
        "FROM repair_tickets t JOIN devices d ON d.device_id=t.device_id LEFT JOIN rooms r ON r.id=d.room_id "
        "WHERE 1=1" + org_cond + " GROUP BY d.device_id, d.device_type, r.name ORDER BY failure_count DESC LIMIT :lim"), params).fetchall()
    return [{"device_id": r.device_id, "device_type": r.device_type, "room_name": r.room_name,
             "failure_count": r.failure_count, "last_failure_at": r.last_fail} for r in rows]


@app.get("/api/reports/chatbot-analytics")
def report_chatbot_analytics(days: int = Query(30, ge=1, le=365), db: Session = Depends(get_db),
                             user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """Analytics จาก chatbot_logs: self-service success rate, การกระจาย intent,
    คำถามที่บอทตอบไม่ได้/พลาด (intent=other + empty reply) เพื่อปรับปรุง"""
    # chatbot_logs has no organization_id.  Until that relationship exists,
    # only globally scoped operators may view aggregate conversations.
    if visible_org_ids(user) is not None:
        raise HTTPException(status_code=403, detail="ข้อมูล chatbot ยังไม่รองรับการกรองตามโรงเรียน")
    params = {"days": days}
    total = db.execute(text("SELECT COUNT(*) FROM chatbot_logs WHERE created_at >= now() - make_interval(days => :days)"), params).scalar_one()
    resolved = db.execute(text("SELECT COUNT(*) FROM chatbot_logs WHERE resolved=TRUE AND created_at >= now() - make_interval(days => :days)"), params).scalar_one()
    intents = {r[0]: r[1] for r in db.execute(text(
        "SELECT intent, COUNT(*) FROM chatbot_logs WHERE created_at >= now() - make_interval(days => :days) GROUP BY intent ORDER BY COUNT(*) DESC"), params).fetchall()}
    missed = db.execute(text(
        "SELECT message FROM chatbot_logs WHERE (intent='other' OR ai_response='' OR ai_response IS NULL) "
        "AND created_at >= now() - make_interval(days => :days) ORDER BY created_at DESC LIMIT 100"), params).fetchall()
    from app.chatbot_quality import curate_review_questions
    result = {
        "total_conversations": total,
        "self_service_resolved": resolved,
        "self_service_rate": round(resolved * 100.0 / total, 1) if total else 0.0,
        "intent_distribution": intents,
        "missed_queries": curate_review_questions((r[0] for r in missed)),
    }
    # Ratings are personnel feedback; only top-level administrators can see them.
    if _is_ratings_viewer(user):
        result["line_ratings"] = {
            target: {"count": db.execute(select(func.count(LineServiceRating.id)).where(LineServiceRating.target == target)).scalar_one(),
                     "average": round(float(db.execute(select(func.avg(LineServiceRating.score)).where(LineServiceRating.target == target)).scalar_one() or 0), 1)}
            for target in ("bot", "staff")
        }
    return result


@app.get("/api/reports/avg-resolution")
def report_avg_resolution(organization_id: Optional[int] = Query(None, description="กรองตามองค์กร"),
                          db: Session = Depends(get_db),
                          user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """เวลาเฉลี่ยในการแก้ไข ticket ที่ status=resolved/closed (ชั่วโมง)"""
    scope = visible_org_ids(user)
    if scope is not None:
        if organization_id is not None and organization_id not in scope:
            raise HTTPException(status_code=403, detail="คุณไม่มีสิทธิ์เข้าถึงข้อมูลของโรงเรียนนี้")
        if not scope:
            return {"total_resolved": 0, "avg_hours": None, "min_hours": None, "max_hours": None, "organization_id": organization_id}
        organization_id = organization_id or next(iter(scope))
    where = "WHERE t.status IN ('resolved', 'closed')"
    params: dict = {}
    if organization_id:
        where += " AND t.organization_id = :oid"
        params["oid"] = organization_id
    row = db.execute(text(
        "SELECT COUNT(*) AS total, "
        "ROUND(AVG(EXTRACT(EPOCH FROM (COALESCE(resolved_at, updated_at) - created_at))/3600.0), 1) AS avg_hours, "
        "MIN(EXTRACT(EPOCH FROM (COALESCE(resolved_at, updated_at) - created_at))/3600.0) AS min_hours, "
        "MAX(EXTRACT(EPOCH FROM (COALESCE(resolved_at, updated_at) - created_at))/3600.0) AS max_hours "
        "FROM repair_tickets t " + where), params).fetchone()
    total = row[0] if row else 0
    return {
        "total_resolved": total,
        "avg_hours": float(row[1]) if row and row[1] is not None else None,
        "min_hours": float(row[2]) if row and row[2] is not None else None,
        "max_hours": float(row[3]) if row and row[3] is not None else None,
        "organization_id": organization_id,
    }


# ─── LINE Webhook (TOR 5.11) — รับ event จริง แล้วส่งต่อ chatbot ───────
# ปรับจากเวอร์ชันทีมบอท: เพิ่ม postback (Rich Menu) + กัน event ซ้ำ (idempotency)
# ผ่านตาราง line_webhook_events + จำกัด worker thread (ไม่สร้าง thread ไม่จำกัด)
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")
# ค่าลับที่ n8n แนบมาใน header X-N8N-Secret (ตั้ง env นี้เมื่ออัปเดต n8n แล้วเท่านั้น)
# ทำไมต้องมี: n8n รับ body จาก LINE แล้วส่งต่อใหม่ (re-serialize) ทำให้ X-Line-Signature
# ของ LINE ใช้ไม่ได้อีก → ถ้าไม่ตั้ง env นี้ ระบบจะยอมรับคำขอที่ไม่มี signature
# (พฤติกรรมเดิม เพื่อไม่ให้ LINE ล่ม) แต่ถ้าตั้งแล้ว จะบังคับให้ต้องมี secret เท่านั้น


def _line_request_trusted(raw: bytes, x_line_signature: Optional[str],
                          x_n8n_secret: Optional[str], n8n_key: Optional[str] = None) -> bool:
    """true = คำขอนี้มาจาก LINE (signature ถูก) หรือจาก n8n (shared secret ถูก)
    รับ secret ได้ 2 ทาง: header X-N8N-Secret หรือ query ?k= (เผื่อ n8n/proxy ตัด header)"""
    if N8N_SHARED_SECRET:
        for candidate in (x_n8n_secret, n8n_key):
            if candidate and hmac.compare_digest(N8N_SHARED_SECRET, candidate):
                return True
    if LINE_CHANNEL_SECRET and x_line_signature:
        mac = hmac.new(LINE_CHANNEL_SECRET.encode(), raw, hashlib.sha256).digest()
        expected = base64.b64encode(mac).decode()
        if hmac.compare_digest(expected, x_line_signature):
            return True
    return False



try:
    _line_worker_count = max(2, min(16, int(os.environ.get("LINE_WORKERS", "8"))))
except (TypeError, ValueError):
    _line_worker_count = 8
_LINE_EXECUTOR = ThreadPoolExecutor(max_workers=_line_worker_count, thread_name_prefix="line-chatbot")
_LINE_USER_LOCKS = defaultdict(threading.Lock)


def _claim_line_event(event_id: str) -> bool:
    """Claim a LINE event once so webhook retries cannot answer twice."""
    if not event_id:
        return True
    db = SessionLocal()
    try:
        result = db.execute(
            text("INSERT INTO line_webhook_events (event_id) VALUES (:event_id) "
                 "ON CONFLICT (event_id) DO NOTHING"),
            {"event_id": event_id[:128]},
        )
        db.commit()
        return result.rowcount == 1
    except Exception:
        db.rollback()
        # If the idempotency table is temporarily unavailable, process the
        # message rather than silently dropping a user's request.
        logger.exception("Could not claim LINE event %s", event_id)
        return True
    finally:
        db.close()


def _line_postback_text(event: dict) -> str:
    """แปลง postback จาก Rich Menu ให้เป็นข้อความที่ chatbot เข้าใจได้"""
    postback = event.get("postback") or {}
    display_text = str(postback.get("displayText") or "").strip()
    data = str(postback.get("data") or "").strip()
    if display_text:
        return display_text
    data_lower = data.lower()
    if any(term in data_lower for term in ("contact", "admin", "human", "เจ้าหน้าที่", "แอดมิน", "ติดต่อ")):
        return "ติดต่อแอดมิน"
    return data


@app.post("/api/line/webhook")
@limiter.limit("120/minute")
async def line_webhook(request: Request, x_line_signature: Optional[str] = Header(None),
                x_n8n_secret: Optional[str] = Header(None)):
    """รับ event จาก LINE OA โดยตรง → ตรวจ signature → เรียก LINE chatbot (คุยหลายรอบ)

    LINE ส่ง {events:[{type:message, replyToken, source:{userId,groupId,type},
                       message:{type:text, text}}]}.
    ตอบ 200 เสมอ (เพื่อให้ LINE ไม่ retry); การ reply ข้อความทำผ่าน LINE API แยก.
    """
    raw = await request.body()
    # ── ตรวจสิทธิ์: LINE ส่ง X-Line-Signature / n8n ส่ง X-N8N-Secret ──
    # n8n รับ body แล้วส่งต่อใหม่ signature ของ LINE จึงไม่ตรง — ตั้ง N8N_SHARED_SECRET
    # เพื่อบังคับโหมดเข้ม (ต้องมี secret เท่านั้น) เมื่ออัปเดต workflow ฝั่ง n8n แล้ว
    if not _line_request_trusted(raw, x_line_signature, x_n8n_secret, request.query_params.get("k")):
        logger.warning("LINE webhook: rejected request without valid signature/secret")
        raise HTTPException(status_code=401, detail="unauthorized")
    try:
        payload = json.loads(raw or b"{}")
    except Exception:
        payload = {}
    events = payload.get("events", [])
    processed = 0
    for ev in events:
        etype = ev.get("type")
        if etype in ("message", "postback"):
            event_id = str(ev.get("webhookEventId") or "").strip()
            if event_id and not _claim_line_event(event_id):
                logger.info("Skipping duplicate LINE event %s", event_id)
                continue
        if etype == "postback":
            src = ev.get("source") or {}
            user_id = src.get("userId") or ""
            group_id = src.get("groupId") or ""
            reply_token = ev.get("replyToken") or ""
            is_group = src.get("type") == "group"
            postback_text = _line_postback_text(ev)
            if postback_text:
                _process_line_text(user_id, postback_text, reply_token, group_id, is_group)
                processed += 1
        elif etype == "message":
            msg = ev.get("message") or {}
            src = ev.get("source") or {}
            if msg.get("type") == "text" and msg.get("text"):
                user_id = src.get("userId") or ""
                group_id = src.get("groupId") or ""
                reply_token = ev.get("replyToken") or ""
                is_group = (src.get("type") == "group")
                text_msg = msg["text"]
                # เรียก chatbot (คุยหลายรอบ) — ตอบ LINE ผ่าน reply_token
                _process_line_text(user_id, text_msg, reply_token, group_id, is_group)
                processed += 1
            # (ภาพ/สติกเกอร์/etc. ข้ามไปก่อน)
    return {"status": "ok", "received": len(events), "processed": processed}


def _process_line_text(user_id: str, text: str, reply_token: str, group_id: str, is_group: bool):
    """ประมวลผลข้อความ LINE ผ่าน chatbot แล้วตอบกลับ (ไม่บล็อก webhook)
    กลุ่ม LINE ใช้สำหรับแจ้งเตือนเท่านั้น — ไม่ตอบกลับข้อความในกลุ่ม"""
    # กลุ่ม = แจ้งเตือนอย่างเดียว: ข้าม reply (การแจ้งเตือนใช้ push ไป group_id แยกต่างหาก)
    if is_group:
        return
    def _run():
        # LINE can deliver two messages from the same user close together.
        # Serialize that user's state transitions while allowing different
        # users to be processed concurrently.
        with _LINE_USER_LOCKS[user_id or "anonymous"]:
            qr = None
            try:
                from app.chatbot_core import handle_message
                from app.chat_session import get_session
                reply = handle_message(
                    user_id=user_id, text=text,
                    reply_token=reply_token, group=False,
                )
                # G: ดึง quick-reply suggestions ที่ chatbot ฝากไว้ แล้วล้าง
                try:
                    sess = get_session(user_id)
                    if sess.get("_pending_qr"):
                        qr = sess.get("_pending_qr")
                        s2 = dict(sess)
                        s2.pop("_pending_qr", None)
                        from app.chat_session import save_session as _ss
                        _ss(user_id, s2)
                except Exception:
                    logger.exception("Could not consume quick replies for LINE user %s", user_id)
                from app.chatbot_core import get_pending_product_image
                image = get_pending_product_image()
            except Exception:
                logger.exception("Chatbot processing failed for LINE user %s", user_id)
                reply = "ขออภัยค่ะ ระบบกำลังขัดข้องชั่วคราว กรุณาลองส่งข้อความอีกครั้งนะคะ 🙏"
                image = None
            # ตอบ LINE ด้วย reply_token (จาก LINE จริง)
            if reply_token and reply:
                from app.line_bot import send_line_reply
                send_line_reply(reply_token, reply, qr, image)
    # ใช้ bounded worker pool เพื่อไม่สร้าง thread ใหม่ไม่จำกัดเมื่อ LINE retry
    _LINE_EXECUTOR.submit(_run)


# ═══════════════════════════════════════════════════════════════════════
# n8n integration — ยิง event ไป n8n workflow (fire-and-forget, ไม่บล็อก)
# ═══════════════════════════════════════════════════════════════════════

LINE_GROUP_ID_ENV = os.environ.get("LINE_GROUP_ID", "")

_STATUS_LABEL_TH = {
    "new": "รอรับเรื่อง", "assigned": "มอบหมายแล้ว", "in_progress": "กำลังดำเนินการ",
    "pending": "รออะไหล่/รอภายนอก", "waiting_parts": "รออะไหล่",
    "waiting_user": "รอผู้ใช้ตอบกลับ", "resolved": "ซ่อมเสร็จ รอยืนยัน",
    "closed": "ปิดงานแล้ว", "cancelled": "ยกเลิก",
}


N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "http://n8n:5678/webhook/")


def _notify_n8n(event: str, payload: dict):
    """ส่ง event ไป n8n (fire-and-forget) — n8n ไม่พร้อมก็ข้าม ไม่ทำให้ request หลักล้ม"""
    try:
        import httpx
        url = f"{N8N_WEBHOOK_URL}notify"
        body = {"event": event, **payload}
        try:
            httpx.post(url, json=body, timeout=2.0)
        except Exception:
            pass
    except Exception:
        pass


def _ticket_event_payload(t: "RepairTicket") -> dict:
    return {
        "ticket_id": t.ticket_id,
        "title": t.title,
        "description": t.description or "",
        "status": t.status,
        "priority": t.priority,
        "device_id": t.device_id,
        "reporter_name": t.reporter_name,
        "reporter_phone": t.reporter_phone,
        "channel": t.channel or "web",
        "assigned_to": t.assigned_to,
    }


# ═══════════════════════════════════════════════════════════════════════
# LINE Chatbot — รับข้อความจาก n8n → จัดการบทสนทนา → ตอบ LINE
# n8n webhook (/line-webhook) รับ LINE event แล้ว POST มาที่ endpoint นี้
# ═══════════════════════════════════════════════════════════════════════

class LineBotIn(BaseModel):
    user_id: str = ""
    text: str = ""
    reply_token: str = ""
    group_id: str = ""
    is_group: bool = False

@app.post("/api/line/bot", status_code=200)
def line_bot_handle(payload: LineBotIn, _: None = Depends(require_n8n_secret)):
    """ประมวลผลข้อความ LINE chatbot — คืน {reply: text} (n8n จะเอาคำตอบไป reply)
    ถ้า reply_token มี → backend reply เองได้เลย
    ถ้าตั้ง N8N_SHARED_SECRET ไว้ ต้องแนบ header X-N8N-Secret ให้ตรง"""
    from app.chatbot_core import handle_message
    reply = handle_message(
        user_id=payload.user_id,
        text=payload.text,
        reply_token=payload.reply_token,
        group=payload.is_group,
    )
    # ตอบ LINE ถ้ามี reply_token (จาก LINE จริง)
    if payload.reply_token:
        from app.line_bot import send_line_reply
        from app.chatbot_core import get_pending_product_image
        send_line_reply(payload.reply_token, reply, None, get_pending_product_image())
    return {"reply": reply, "handled": True}


# ═══════════════════════════════════════════════════════════════════════
# Adapter: รับ payload จาก n8n All-in-One workflow → สร้าง repair_ticket
# ผ่าน FastAPI (option B — ไม่เขียนตาราง tickets แยก). payload รูปแบบ camelCase
# ของ workflow: reporterName, organization, room, contact, deviceId, deviceType,
# problemDetail, urgency, imageUrl, userId, intent, channel
# ═══════════════════════════════════════════════════════════════════════

class N8nTicketIn(BaseModel):
    reporterName: str = ""
    organization: str = ""
    room: str = ""
    contact: str = ""
    deviceId: str = ""
    deviceType: str = ""
    problemDetail: str = ""
    urgency: str = "Normal"
    imageUrl: str = ""
    userId: str = ""
    intent: str = ""
    channel: str = "LINE"
    replyToken: str = ""

@app.post("/api/line/create-ticket", status_code=201)
def line_create_ticket(payload: N8nTicketIn, db: Session = Depends(get_db), _: None = Depends(require_n8n_secret)):
    """รับ payload จาก n8n → resolve device (ต้องระบุได้แน่ชัด) → สร้าง repair_ticket.
    คืน {ticket_no, ticket_id, success} ให้ n8n นำไป notify ต่อ"""
    from datetime import datetime, timezone as _tz
    device_id = payload.deviceId.strip()
    # guardrail: ห้าม fallback ไป "อุปกรณ์ตัวแรกในระบบ" หรือ default TEST1 —
    # ticket จะผูก organization_id ขององค์กรอื่น (ข้อมูลข้ามองค์กร) และช่างถูกส่งผิดห้อง
    # ตรงหลายเครื่อง = กำกวม ต้องให้ผู้แจ้งระบุรหัสเอง (เหมือน chatbot_core._create_ticket_from_fields)
    from app.chatbot_core import _looks_like_device_code
    # resolve device: รหัสตรงตัว → ไม่สนตัวพิมพ์ → รหัสบางส่วน (เฉพาะที่ดูเป็นรหัสอุปกรณ์) → ห้อง
    dev = None
    if device_id:
        dev = db.execute(select(Device).where(Device.device_id == device_id)).scalar_one_or_none()
        if not dev:
            row = db.execute(text(
                "SELECT id FROM devices WHERE lower(device_id) = lower(:d) LIMIT 1"
            ), {"d": device_id}).mappings().first()
            if row:
                dev = db.get(Device, row["id"])
        if not dev and _looks_like_device_code(device_id):
            code_rows = db.execute(text(
                "SELECT id, device_id FROM devices WHERE device_id ILIKE '%' || :d || '%' LIMIT 3"
            ), {"d": device_id}).mappings().all()
            if len(code_rows) == 1:
                dev = db.get(Device, code_rows[0]["id"])
            elif len(code_rows) > 1:
                codes = ", ".join(str(r["device_id"]) for r in code_rows)
                raise HTTPException(
                    status_code=409,
                    detail=f"พบอุปกรณ์หลายเครื่องที่ตรงกับ '{device_id}' ({codes}) "
                           "กรุณาระบุรหัสอุปกรณ์บนสติกเกอร์ QR ให้ชัดเจน",
                )
    if not dev and payload.room:
        # ลอง match ห้อง
        dev = db.execute(text(
            "SELECT d.id, d.device_id FROM devices d JOIN rooms r ON r.id=d.room_id "
            "WHERE r.code ILIKE :rc OR r.name ILIKE :rc LIMIT 3"
        ), {"rc": f"%{payload.room}%"}).mappings().all()
        if dev:
            if len(dev) > 1:
                codes = ", ".join(str(r["device_id"]) for r in dev)
                raise HTTPException(
                    status_code=409,
                    detail=f"ห้อง '{payload.room}' มีอุปกรณ์หลายเครื่อง ({codes}) "
                           "กรุณาระบุรหัสอุปกรณ์บนสติกเกอร์ QR ให้ชัดเจน",
                )
            dev = db.get(Device, dev[0]["id"])
    if not dev:
        raise HTTPException(
            status_code=422,
            detail=f"ไม่พบอุปกรณ์ที่ตรงกับ deviceId='{device_id or '-'}' / ห้อง='{payload.room or '-'}' "
                   "กรุณาส่งรหัสอุปกรณ์บนสติกเกอร์ QR (ระบบไม่สร้างใบงานผูกอุปกรณ์ขององค์กรอื่น)",
        )
    org_id = dev.organization_id
    prio_map = {"low":"low","Low":"low","medium":"normal","Medium":"normal","normal":"normal","Normal":"normal",
                "high":"high","High":"high","critical":"critical","Critical":"critical"}
    priority = prio_map.get(payload.urgency, "normal")
    now = datetime.now(_tz.utc)
    title = (payload.problemDetail or "แจ้งซ่อมผ่าน LINE")[:120]

    # ─── กันแจ้งซ้ำ (TOR 1.5.2 / 5.7): อุปกรณ์มีใบงานค้าง → ไม่เปิดใบใหม่ ─────────
    # ทางเข้า LINE/n8n ไม่มีหน้าจอให้ผู้แจ้งเลือกเหมือนหน้าเว็บ จึงเลือกทางที่ข้อมูล
    # ไม่หาย: ต่อท้ายอาการที่ส่งมาเข้าใบเดิมเป็น ticket_updates (รูปแบบเดียวกับ
    # public_add_ticket_note) แล้วคืน duplicate=True พร้อมเลขใบเดิมและสถานะภาษาไทย
    # ให้ n8n ตอบผู้แจ้งว่าอุปกรณ์นี้แจ้งไปแล้ว
    existing = find_open_ticket(db, dev.device_id)
    if existing:
        reporter = (payload.reporterName or "").strip() or "ผู้ใช้ LINE"
        contact = (payload.contact or payload.userId or "").strip()
        note_text = (payload.problemDetail or "").strip() or "แจ้งอาการเพิ่มผ่าน LINE (ไม่ระบุรายละเอียด)"
        suffix = " (แนบรูป 1 รูป)" if payload.imageUrl else ""
        author = f"{reporter} ({contact})" if contact else reporter
        db.add(TicketUpdate(
            ticket=existing,
            from_status=existing.status,
            to_status=existing.status,
            note=f"[แจ้งเพิ่มจากผู้ใช้ LINE] {note_text}{suffix}",
            author_name=author[:128],
            author_role="reporter",
        ))
        # รูปที่แนบมาใหม่ ต่อท้ายรายการเดิม ไม่เขียนทับของผู้แจ้งคนก่อน
        if payload.imageUrl:
            try:
                current = json.loads(existing.attachments) if existing.attachments else []
            except (ValueError, TypeError):
                current = []
            if not isinstance(current, list):
                current = []
            existing.attachments = json.dumps(current + [payload.imageUrl], ensure_ascii=False)
        db.commit()
        db.refresh(existing)
        try:
            event = _ticket_event_payload(existing)
            event["note"] = note_text
            event["author_name"] = reporter
            _notify_n8n("ticket.note_added", event)
        except Exception:
            pass
        status_label = PUBLIC_STATUS_LABELS.get(existing.status, existing.status)
        device_label = device_display_label(dev)
        return {
            "success": True,
            "duplicate": True,
            "code": "DUPLICATE_OPEN_TICKET",
            "ticket_no": existing.ticket_id,
            "ticket_id": existing.ticket_id,
            "device_id": existing.device_id,
            "device_type": dev.device_type,
            "device_category": device_category_of(dev.device_type),
            "device_label": device_label,
            "status": existing.status,
            "status_label": status_label,
            "note_added": True,
            "message": (
                f"อุปกรณ์ {device_label} ({existing.device_id}) แจ้งซ่อมไว้แล้ว "
                f"เลขที่ {existing.ticket_id} (สถานะ: {status_label}) — "
                "บันทึกอาการที่แจ้งเพิ่มเข้าใบเดิมให้แล้ว ไม่ต้องแจ้งซ้ำ"
            ),
        }
    line_customer_id = (payload.userId or "").strip()[:128] if payload.channel.lower() == "line" else None
    ticket = RepairTicket(
        ticket_id=generate_ticket_id(db, org_id),
        organization_id=org_id,
        device_id=dev.device_id,
        title=title,
        description=payload.problemDetail,
        reporter_name=payload.reporterName or "ผู้ใช้ LINE",
        reporter_phone=payload.contact or payload.userId,
        priority=priority,
        status=TicketStatus.NEW,
        channel="line" if payload.channel.lower()=="line" else "web",
        line_user_id=line_customer_id or None,
        symptom_code=payload.intent or None,
        ai_category=payload.intent or None,
        attachments=json.dumps([payload.imageUrl]) if payload.imageUrl else None,
        sla_due_at=calc_sla_due(now, priority),
        scan_timestamp=now,
    )
    db.add(ticket)
    db.flush()
    db.add(TicketUpdate(ticket=ticket, from_status=None, to_status="new",
                        note=f"สร้างจาก n8n ({payload.channel})", author_name=payload.reporterName or "ผู้ใช้ LINE",
                        author_role="reporter"))
    db.commit()
    # แจ้ง n8n event
    try:
        _notify_n8n("ticket.created", _ticket_event_payload(ticket))
    except Exception:
        pass
    return {"success": True, "ticket_no": ticket.ticket_id, "ticket_id": ticket.ticket_id,
            "device_id": dev.device_id, "status": "new"}


# ─── Sales Leads + Chatbot Logs Dashboard (admin / it_support) ────────
# ตาราง sales_leads / chatbot_logs ไม่มี SQLAlchemy model — SELECT ตรงจากตาราง
def _row_to_iso(v):
    if v is None:
        return None
    if isinstance(v, (datetime,)):
        return v.isoformat()
    return v


@app.get("/api/sales/leads")
def list_sales_leads(
    limit: int = Query(200, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    """รายการ lead การขาย (จาก LINE) เรียงล่าสุดก่อน"""
    rows = db.execute(
        text("SELECT id, user_id, name, phone, interest, products, source, note, status, created_at "
             "FROM sales_leads ORDER BY created_at DESC, id DESC LIMIT :lim OFFSET :off"),
        {"lim": limit, "off": offset},
    ).mappings().all()
    return [
        {
            "id": r["id"],
            "user_id": r["user_id"],
            "name": r["name"] or "",
            "phone": r["phone"] or "",
            "interest": r["interest"] or "",
            "products": r["products"] or "",
            "source": r["source"] or "LINE",
            "note": r["note"] or "",
            "status": r["status"] or "new",
            "created_at": _row_to_iso(r["created_at"]),
        }
        for r in rows
    ]


class LeadStatusUpdate(BaseModel):
    status: str = Field(..., pattern="^(new|contacted|closed)$")


def _sync_sales_lead_async(lead: SalesLead) -> None:
    """Best-effort Sheet mirror; database is authoritative if the service is down."""
    if lead.source == "DEMO" or not google_sheets.is_configured():
        return
    snapshot = {
        "id": lead.id, "user_id": lead.user_id, "name": lead.name,
        "phone": lead.phone, "interest": lead.interest,
        "products": lead.products, "source": lead.source,
        "status": lead.status, "note": lead.note, "created_at": lead.created_at,
    }
    threading.Thread(
        target=google_sheets.sync_lead_row,
        args=(snapshot,), name=f"sheet-lead-{lead.id}", daemon=True,
    ).start()


@app.patch("/api/sales/leads/{lead_id}")
def update_sales_lead_status(
    lead_id: int,
    payload: LeadStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    """ทำเครื่องหมาย lead ว่าติดต่อแล้ว (status = contacted)"""
    lead = db.get(SalesLead, lead_id)
    if not lead:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} ไม่พบ")
    lead.status = payload.status
    db.commit()
    _sync_sales_lead_async(lead)
    return {"id": lead_id, "status": payload.status, "name": lead.name}


@app.post("/api/sales/leads/{lead_id}/sync-sheet")
def retry_sales_lead_sheet_sync(
    lead_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin")),
):
    lead = db.get(SalesLead, lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="ไม่พบลูกค้า")
    if lead.source == "DEMO":
        raise HTTPException(status_code=400, detail="ข้อมูลตัวอย่างไม่ส่งไป Google Sheet")
    if not google_sheets.is_configured():
        raise HTTPException(status_code=503, detail="ยังไม่ได้ตั้งค่า Google Sheet")
    _sync_sales_lead_async(lead)
    return {"queued": True, "lead_id": lead_id}


@app.delete("/api/sales/leads/{lead_id}")
def delete_sales_lead(
    lead_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin")),
):
    """ลบ lead การขาย (ข้อมูลเทส/ซ้ำ) — super_admin/admin เท่านั้น"""
    row = db.execute(
        text("SELECT id, name FROM sales_leads WHERE id = :lid"),
        {"lid": lead_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} ไม่พบ")
    if db.execute(select(SalesRecord.id).where(SalesRecord.lead_id == lead_id).limit(1)).first():
        raise HTTPException(status_code=409, detail="ลูกค้านี้มีประวัติการขาย/คำขอชำระเงิน จึงลบไม่ได้")
    db.execute(text("DELETE FROM sales_leads WHERE id = :lid"), {"lid": lead_id})
    db.commit()
    return {"deleted": True, "id": lead_id, "name": row["name"]}


SALES_RECORD_STATUSES = {
    "deal": {"interested", "quoted", "won", "lost"},
    "payment_request": {"requested", "reviewing", "resolved", "cancelled"},
}


class SalesRecordIn(BaseModel):
    lead_id: int = Field(..., ge=1)
    kind: Literal["deal", "payment_request"]
    product: str = Field(..., min_length=1, max_length=255)
    quantity: int = Field(1, ge=1, le=10000)
    amount_thb: Optional[Decimal] = Field(None, ge=0)
    note: Optional[str] = Field(None, max_length=2000)


class SalesRecordUpdate(BaseModel):
    status: str = Field(..., min_length=1, max_length=32)


def _sales_record_out(row: SalesRecord, lead_name: str = "") -> dict:
    return {
        "id": row.id,
        "lead_id": row.lead_id,
        "lead_name": lead_name,
        "kind": row.kind,
        "product": row.product,
        "quantity": row.quantity,
        "amount_thb": str(row.amount_thb) if row.amount_thb is not None else None,
        "status": row.status,
        "note": row.note or "",
        "created_by": row.created_by,
        "created_at": _row_to_iso(row.created_at),
        "updated_at": _row_to_iso(row.updated_at),
    }


def _sync_sales_record_async(record: SalesRecord, lead_name: str, lead_source: str = "") -> None:
    if lead_source == "DEMO" or not google_sheets.is_configured():
        return
    snapshot = _sales_record_out(record, lead_name)
    threading.Thread(
        target=google_sheets.sync_sales_record_row,
        args=(snapshot,), name=f"sheet-sale-{record.id}", daemon=True,
    ).start()


@app.get("/api/sales/records")
def list_sales_records(
    limit: int = Query(200, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    rows = db.execute(
        select(SalesRecord, SalesLead.name)
        .join(SalesLead, SalesLead.id == SalesRecord.lead_id)
        .order_by(SalesRecord.created_at.desc(), SalesRecord.id.desc())
        .offset(offset).limit(limit)
    ).all()
    return [_sales_record_out(record, name or "") for record, name in rows]


@app.post("/api/sales/records", status_code=201)
def create_sales_record(
    payload: SalesRecordIn,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    lead = db.get(SalesLead, payload.lead_id)
    if lead is None:
        raise HTTPException(status_code=404, detail="ไม่พบลูกค้าหรือผู้สนใจ")
    product = payload.product.strip()
    if not product:
        raise HTTPException(status_code=422, detail="กรุณาระบุสินค้า/บริการ")
    if payload.amount_thb is not None and (
        payload.amount_thb > Decimal("9999999999.99")
        or payload.amount_thb != payload.amount_thb.quantize(Decimal("0.01"))
    ):
        raise HTTPException(status_code=422, detail="มูลค่าต้องไม่เกิน 10 หลักและมีทศนิยมไม่เกิน 2 ตำแหน่ง")
    record = SalesRecord(
        lead_id=lead.id,
        kind=payload.kind,
        product=product,
        quantity=payload.quantity,
        amount_thb=payload.amount_thb,
        status="interested" if payload.kind == "deal" else "requested",
        note=(payload.note or "").strip() or None,
        created_by=user.id,
    )
    db.add(record)
    db.flush()
    write_audit(
        db, action="sales_record_create", user=user,
        entity_type="sales_record", entity_id=str(record.id),
        new_value={"kind": record.kind, "lead_id": lead.id, "status": record.status},
        request=request,
    )
    db.commit()
    db.refresh(record)
    _sync_sales_record_async(record, lead.name or "", lead.source)
    return _sales_record_out(record, lead.name or "")


@app.patch("/api/sales/records/{record_id}")
def update_sales_record(
    record_id: int,
    payload: SalesRecordUpdate,
    request: Request,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    record = db.get(SalesRecord, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="ไม่พบบันทึกการขาย")
    if payload.status not in SALES_RECORD_STATUSES.get(record.kind, set()):
        raise HTTPException(status_code=422, detail="สถานะไม่ตรงกับหมวดบันทึก")
    old_status = record.status
    record.status = payload.status
    write_audit(
        db, action="sales_record_status", user=user,
        entity_type="sales_record", entity_id=str(record.id),
        old_value={"status": old_status}, new_value={"status": record.status},
        request=request,
    )
    db.commit()
    db.refresh(record)
    lead = db.get(SalesLead, record.lead_id)
    _sync_sales_record_async(record, lead.name if lead else "", lead.source if lead else "")
    return _sales_record_out(record, lead.name if lead else "")


@app.post("/api/sales/records/{record_id}/sync-sheet")
def retry_sales_record_sheet_sync(
    record_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin")),
):
    record = db.get(SalesRecord, record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="ไม่พบบันทึกการขาย")
    if not google_sheets.is_configured():
        raise HTTPException(status_code=503, detail="ยังไม่ได้ตั้งค่า Google Sheet")
    lead = db.get(SalesLead, record.lead_id)
    if lead and lead.source == "DEMO":
        raise HTTPException(status_code=400, detail="ข้อมูลตัวอย่างไม่ส่งไป Google Sheet")
    _sync_sales_record_async(record, lead.name if lead else "", lead.source if lead else "")
    return {"queued": True, "record_id": record_id}


@app.get("/api/sales/summary")
def sales_summary(
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    rows = db.execute(
        text("SELECT sr.kind, sr.status, COUNT(*) AS count, "
             "COALESCE(SUM(sr.amount_thb), 0) AS amount FROM sales_records sr "
             "JOIN sales_leads sl ON sl.id = sr.lead_id "
             "WHERE sl.source <> 'DEMO' GROUP BY sr.kind, sr.status")
    ).mappings().all()
    return {
        "lead_count": db.execute(select(func.count(SalesLead.id)).where(SalesLead.source != "DEMO")).scalar_one(),
        "demo_lead_count": db.execute(select(func.count(SalesLead.id)).where(SalesLead.source == "DEMO")).scalar_one(),
        "open_deals": sum(r["count"] for r in rows if r["kind"] == "deal" and r["status"] in {"interested", "quoted"}),
        "won_deals": sum(r["count"] for r in rows if r["kind"] == "deal" and r["status"] == "won"),
        "won_amount_thb": str(sum((r["amount"] for r in rows if r["kind"] == "deal" and r["status"] == "won"), Decimal("0"))),
        "payment_requests": sum(r["count"] for r in rows if r["kind"] == "payment_request" and r["status"] in {"requested", "reviewing"}),
        "deal_status_counts": {status: sum(r["count"] for r in rows if r["kind"] == "deal" and r["status"] == status)
                               for status in ("interested", "quoted", "won", "lost")},
        "lead_by_source": {source: count for source, count in db.execute(
            select(SalesLead.source, func.count(SalesLead.id)).where(SalesLead.source != "DEMO").group_by(SalesLead.source)
        ).all()},
        "new_leads_7d": db.execute(select(func.count(SalesLead.id)).where(
            SalesLead.source != "DEMO", SalesLead.created_at >= datetime.now(timezone.utc) - timedelta(days=7)
        )).scalar_one(),
    }


@app.get("/api/sales/integrations")
def sales_integrations(
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    return {
        "google_sheet_configured": google_sheets.is_configured(),
        "line_group_configured": bool(os.environ.get("LINE_GROUP_ID") and os.environ.get("LINE_CHANNEL_TOKEN")),
    }


# ─── สมัครสมาชิกลูกค้า (หน้าเว็บสาธารณะ /?customer=1) ──────────────────
# ลูกค้าทั่วไปไม่ต้องมีบัญชีในระบบ — คำขอถูกบันทึกเป็น lead (source=WEB)
# ใช้ตาราง/ชีต/การแจ้งกลุ่มไลน์ชุดเดียวกับ lead ที่มาจาก LINE จึงเห็นรวมกันในหน้า "ยอดขาย"
class CustomerSignupIn(BaseModel):
    full_name: str = Field(..., min_length=2, max_length=128)
    phone: str = Field(..., min_length=9, max_length=20)
    email: Optional[str] = Field(None, max_length=128)
    organization: Optional[str] = Field(None, max_length=128)
    interest: Optional[str] = Field(None, max_length=200)
    products: Optional[str] = Field(None, max_length=500)
    note: Optional[str] = Field(None, max_length=500)
    ref: Optional[str] = Field(None, max_length=128)
    consent: bool = False


def _normalize_th_phone(raw: str) -> str:
    """เหลือแต่ตัวเลข และแปลง +66xxxxxxxxx → 0xxxxxxxxx เพื่อให้เทียบ lead ซ้ำได้ตรงกัน"""
    digits = "".join(ch for ch in str(raw or "") if ch.isdigit())
    if digits.startswith("66") and len(digits) in (11, 12):
        digits = "0" + digits[2:]
    return digits


@app.post("/api/public/customer-signup", status_code=201)
@limiter.limit("10/hour")
def public_customer_signup(
    request: Request,
    payload: CustomerSignupIn,
    db: Session = Depends(get_db),
):
    """รับสมัครสมาชิกลูกค้าจากหน้าเว็บ (ไม่ต้อง login) → บันทึกเป็น lead รอทีมขายติดต่อกลับ"""
    if not payload.consent:
        raise HTTPException(
            status_code=400,
            detail="กรุณายอมรับการให้ข้อมูลเพื่อให้ทีมงานติดต่อกลับ",
        )

    name = payload.full_name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=422, detail="กรุณากรอกชื่อ-นามสกุล")

    phone = _normalize_th_phone(payload.phone)
    if not phone.startswith("0") or not (9 <= len(phone) <= 10):
        raise HTTPException(status_code=422, detail="รูปแบบเบอร์โทรไม่ถูกต้อง (ตัวอย่าง 0812345678)")

    email = (payload.email or "").strip() or None
    if email and ("@" not in email or "." not in email.rsplit("@", 1)[-1]):
        raise HTTPException(status_code=422, detail="รูปแบบอีเมลไม่ถูกต้อง")

    invite = None
    if payload.ref:
        token = payload.ref.strip()
        if not (20 <= len(token) <= 128) or any(c not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for c in token):
            raise HTTPException(status_code=400, detail="ลิงก์สมัครสมาชิกไม่ถูกต้อง")
        invite = db.execute(
            select(CustomerSignupInvite)
            .where(CustomerSignupInvite.token_hash == hashlib.sha256(token.encode()).hexdigest())
            .with_for_update()
        ).scalar_one_or_none()
        if not invite or invite.consumed_at or invite.expires_at < datetime.now(timezone.utc):
            raise HTTPException(status_code=400, detail="ลิงก์สมัครสมาชิกหมดอายุหรือถูกใช้แล้ว")

    interest = (payload.interest or "").strip() or (invite.interest if invite else None) or "สมัครสมาชิกลูกค้า (เว็บ)"
    products = (payload.products or "").strip() or (invite.products if invite else None) or ""
    line_user_id = invite.line_user_id if invite else None
    organization = (payload.organization or "").strip()
    note_parts: list[str] = []
    if email:
        note_parts.append(f"อีเมล: {email}")
    if organization:
        note_parts.append(f"หน่วยงาน: {organization}")
    if (payload.note or "").strip():
        note_parts.append(payload.note.strip())
    note = " | ".join(note_parts)[:500]

    # กันสมัครซ้ำ (ชื่อ+เบอร์เดิม) — ตอบข้อความเดียวกับที่ chatbot ใช้ ไม่สร้างแถวใหม่
    dup = db.execute(
        select(SalesLead).where(SalesLead.phone == phone, SalesLead.name == name)
        .order_by(SalesLead.id.desc()).limit(1)
    ).scalar_one_or_none()
    if dup:
        if line_user_id and not dup.user_id:
            dup.user_id = line_user_id
        if invite:
            invite.consumed_at = datetime.now(timezone.utc)
        db.commit()
        _sync_sales_lead_async(dup)
        if line_user_id:
            from app.chatbot_helpers import save_profile
            from app.chat_session import clear_session
            save_profile(line_user_id, {"name": name, "phone": phone, "interested": interest, "lead_id": dup.id})
            clear_session(line_user_id)
        return {
            "id": dup.id,
            "duplicate": True,
            "message": "เราได้รับข้อมูลของคุณไว้แล้ว ทีมงานจะติดต่อกลับโดยเร็วที่สุด",
        }

    created_at = datetime.now(timezone.utc)
    inserted = db.execute(
        text("INSERT INTO sales_leads "
             "(user_id, name, phone, interest, products, note, source, status, created_at) "
             "VALUES (:u, :n, :p, :i, :pr, :note, 'WEB', 'new', :t) RETURNING id"),
        {"u": line_user_id, "n": name[:128], "p": phone[:32], "i": interest[:200],
         "pr": products[:500], "note": note, "t": created_at},
    ).mappings().first()
    if invite:
        invite.consumed_at = created_at
    db.commit()
    lead_id = inserted["id"] if inserted else None

    write_audit(
        db, action="customer_signup", user=None,
        entity_type="sales_lead", entity_id=str(lead_id) if lead_id else None,
        new_value={"name": name, "source": "WEB", "products": products or None},
        request=request,
    )
    db.commit()

    # ชีต + แจ้งกลุ่มไลน์ เป็นช่องทางรายงานสำรอง — ล้มเหลวต้องไม่ทำให้การสมัครล้มเหลว
    # และต้องไม่หน่วง response (Sheets API / LINE push มี timeout หลายวินาที)
    def _report_web_lead() -> None:
        try:
            google_sheets.sync_lead_row({
                "id": lead_id, "user_id": line_user_id or "", "name": name, "phone": phone,
                "interest": interest, "products": products, "source": "WEB",
                "status": "new", "note": note, "created_at": created_at,
            })
        except Exception:
            pass
        try:
            from app.chatbot_helpers import notify_sales_group
            notify_sales_group(lead_id, name, phone, interest, products, source="WEB")
        except Exception:
            pass

    try:
        import threading
        threading.Thread(target=_report_web_lead,
                         name=f"web-lead-report-{lead_id}", daemon=True).start()
    except Exception:
        pass

    if line_user_id:
        from app.chatbot_helpers import save_profile
        from app.chat_session import clear_session
        save_profile(line_user_id, {"name": name, "phone": phone, "interested": interest, "lead_id": lead_id})
        clear_session(line_user_id)

    return {
        "id": lead_id,
        "duplicate": False,
        "message": "สมัครสมาชิกเรียบร้อย ทีมงานจะติดต่อกลับภายในเวลาทำการ",
    }


@app.get("/api/system/status")
def system_status(db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """Live, scoped settings summary without exposing integration credentials."""
    scope = visible_org_ids(user)
    article_count = select(func.count(KBArticle.id))
    if scope is not None:
        article_count = article_count.where(
            (KBArticle.organization_id.is_(None)) | (KBArticle.organization_id.in_(scope))
        )
    from app import line_bot
    return {
        "knowledge_articles": db.execute(article_count).scalar_one(),
        "working_hours": _read_setting(db, "working_hours", {"start": "08:00", "end": "16:30", "days": [1, 2, 3, 4, 5]}),
        "line_oa_configured": bool(line_bot.LINE_TOKEN),
        "staff_group_configured": bool(line_bot.LINE_TOKEN and os.environ.get("LINE_GROUP_ID")),
    }


@app.get("/api/chatbot/logs")
def list_chatbot_logs(
    limit: int = Query(200, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    """บทสนทนา chatbot ล่าสุด (ข้อความ/คำตอบ/เจตนา)"""
    rows = db.execute(
        text("SELECT id, user_id, message, ai_response, intent, resolved, created_at "
             "FROM chatbot_logs ORDER BY created_at DESC, id DESC LIMIT :lim"),
        {"lim": limit},
    ).mappings().all()
    return [
        {
            "id": r["id"],
            "user_id": r["user_id"],
            "message": r["message"] or "",
            "ai_response": r["ai_response"] or "",
            "intent": r["intent"] or "",
            "resolved": bool(r["resolved"]),
            "created_at": _row_to_iso(r["created_at"]),
        }
        for r in rows
    ]





