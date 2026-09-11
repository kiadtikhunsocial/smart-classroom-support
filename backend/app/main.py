"""
Smart Classroom Support — FastAPI Backend
Scope: Device lookup + Ticket CRUD + Workflow status + QR scan log

Run: uvicorn app.main:app --reload --port 8000
"""

from contextlib import asynccontextmanager
from datetime import datetime, timezone, timedelta
import hashlib
import os
from typing import Optional

from fastapi import Depends, FastAPI, Header, HTTPException, Query, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import func, select, text
from sqlalchemy.orm import Session, selectinload

from app.models import (
    Base,
    Building,
    Device,
    KBArticle,
    KBSuggestion,
    NotificationLog,
    Organization,
    Priority,
    RepairTicket,
    Room,
    ScanLog,
    SelfServiceCase,
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


# ---------------------------------------------------------------------------
# Token (JWT-like) — HMAC-SHA256 ลงนาม, stdlib เท่านั้น
# ---------------------------------------------------------------------------
import base64
import hmac
import json
import time

# เปลี่ยน secret นี้ใน production (env JWT_SECRET)
JWT_SECRET = os.environ.get("JWT_SECRET", "smart-classroom-dev-secret-change-me")
JWT_TTL_SECONDS = 60 * 60 * 12  # 12 ชั่วโมง


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
# admin_school / it_support(มีสังกัด) / teacher / student → เห็นเฉพาะรรตัวเอง
# super_admin / admin / it_support(ไม่มีสังกัด, สร้างโดย superadmin) → เห็นทุกรร
def visible_org_ids(user: User) -> Optional[set[int]]:
    """คืนชุด organization_id ที่ user นี้เห็นได้; None = เห็นทุกโรงเรียน"""
    if user.role in ("owner", "super_admin", "admin"):
        return None
    if user.role == "it_support":
        # it_support ที่ไม่มีสังกัด = สร้างโดย owner/admin → เห็นทุกรร
        # it_support ที่มีสังกัด = สร้างโดย admin_school → เห็นเฉพาะรรนั้น
        return None if not user.organization_id else {user.organization_id}
    # admin_school / teacher / student → เห็นเฉพาะรรตัวเอง
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
    warranty_until: Optional[datetime] = None
    notes: Optional[str] = None


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
    scan_gps_lat: Optional[float] = None
    scan_gps_lng: Optional[float] = None
    scan_timestamp: Optional[datetime] = None
    scan_user_agent: Optional[str] = None


class TicketOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    ticket_id: str
    device_id: str
    title: str
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
    warranty_until: Optional[datetime] = None


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
    warranty_until: Optional[datetime] = None


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


class PublicOptionsOut(BaseModel):
    device_types: list[str]
    devices: list[DeviceInfo]


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
    role: str = "teacher"
    is_active: bool = True
    password: Optional[str] = Field(None, min_length=4, max_length=128)


class UserUpdate(BaseModel):
    line_display_name: Optional[str] = None
    line_picture_url: Optional[str] = None
    line_email: Optional[str] = None
    organization_id: Optional[int] = None
    role: Optional[str] = None
    is_active: Optional[bool] = None
    password: Optional[str] = Field(None, min_length=4, max_length=128)


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
# Status transition rules
# ---------------------------------------------------------------------------

STATUS_TRANSITIONS: dict[str, set[str]] = {
    "new": {"assigned", "cancelled"},
    "assigned": {"in_progress", "new", "cancelled"},
    "in_progress": {"pending", "waiting_parts", "waiting_user", "resolved", "cancelled"},
    "pending": {"in_progress", "cancelled"},
    "waiting_parts": {"in_progress", "pending", "resolved", "cancelled"},
    "waiting_user": {"in_progress", "pending", "resolved", "cancelled"},
    "resolved": {"closed", "in_progress"},
    "closed": set(),
    "cancelled": set(),
}


def generate_ticket_id(db: Session, organization_id: int) -> str:
    """Generate TK-YYYYMM-XXXX style ticket ID (TOR 3.5). ใช้ MAX(ลำดับ)+1 (กันเลขซ้ำหลังลบ)"""
    now = datetime.now(timezone.utc)
    prefix = f"TK-{now.year}{now.month:02d}-"
    row = db.execute(
        text("SELECT MAX(CAST(SUBSTRING(ticket_id FROM 'TK-\\d{6}-(\\d{4})') AS INTEGER)) "
             "FROM repair_tickets WHERE ticket_id LIKE :p"),
        {"p": f"{prefix}%"},
    ).scalar_one()
    nxt = (row or 0) + 1
    return f"{prefix}{nxt:04d}"


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
    """ข้ามไปเวลาทำการถัดไป (ถ้าอยู่นอกเวลาทำการ/วันหยุด)"""
    candidate = dt.replace(hour=BUSINESS_START[0], minute=BUSINESS_START[1], second=0, microsecond=0)
    while candidate.weekday() >= 5:
        candidate += timedelta(days=1)
    return candidate

def add_business_minutes(start: datetime, minutes: int) -> datetime:
    """บวกเวลาทำการ (นาที) เข้ากับ start — ข้ามนอกเวลา/วันหยุด"""
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
            cur = _next_business_start(cur + timedelta(days=1))
            continue
        if remaining <= avail:
            return cur + timedelta(minutes=remaining)
        remaining -= avail
        cur = _next_business_start(cur + timedelta(days=1))
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
    org_code = (org.code or "SCH").upper()
    # building code ย่อ (sanitize ให้ปลอด URL) + room code
    building = _building_code(room.building if room else None, room.floor if room else None) if room else "B0"
    room_code = (room.code or "R000") if room else "R000"
    type_code = _device_type_code(device_type)
    prefix = f"{org_code}-{building}-{room_code}-{type_code}-"
    row = db.execute(
        text("""
            SELECT COUNT(*) + 1 FROM devices
            WHERE device_id LIKE :p
              AND device_id ~ ('^' || :p || '[0-9]+$')
        """),
        {"p": f"{prefix}"},
    ).scalar_one()
    return f"{prefix}{row:02d}"


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    # Seed KB 30 หัวข้อ (ถ้าตารางว่าง) + สร้าง PM plans ตั้งต้น
    from app.models import SessionLocal
    db = SessionLocal()
    try:
        seeded = seed_kb_articles(db)
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

@app.exception_handler(RateLimitExceeded)
async def _rate_limit_handler(request: Request, exc: RateLimitExceeded):
    return JSONResponse(status_code=429, content={"detail": "มีการร้องขอมากเกินไป กรุณารอสักครู่ก่อนลองใหม่"})

_cors_origins = [o.strip() for o in os.environ.get(
    "CORS_ORIGINS",
    "http://localhost:5173,https://unnoticed-simplify-disclose.ngrok-free.dev",
).split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
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
        warranty_until=device.warranty_until,
        notes=device.notes,
    )


# ---------------------------------------------------------------------------
# Ticket CRUD
# ---------------------------------------------------------------------------


@app.post("/api/tickets", response_model=TicketOut, status_code=201)
def create_ticket(
    payload: TicketCreate,
    request: Request,
    db: Session = Depends(get_db),
):
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
    open_ticket = db.execute(
        select(RepairTicket)
        .where(
            RepairTicket.device_id == payload.device_id,
            RepairTicket.status.in_(["new", "assigned", "in_progress", "pending"]),
        )
        .order_by(RepairTicket.created_at.desc())
    ).scalars().first()
    if open_ticket:
        raise HTTPException(
            status_code=409,
            detail={
                "code": "DUPLICATE_OPEN_TICKET",
                "message": "อุปกรณ์นี้มีการแจ้งซ่อมที่ยังไม่ปิดอยู่แล้ว",
                "existing_ticket_no": open_ticket.ticket_id,
                "existing_status": open_ticket.status,
            },
        )

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

DEVICE_TYPE_LABELS = [
    "Interactive Display", "Computer AIO", "Computer Notebook", "Computer Tablet",
    "Computer Desktop", "Router", "Access Point", "Switch", "Speaker", "Camera",
    "Visualizer", "Microphone", "UPS", "Printer", "Projector",
    "Software (Picaro)", "Software (Phonics Hero)", "Other",
]


@app.get("/api/public/options", response_model=PublicOptionsOut)
def public_options(db: Session = Depends(get_db)):
    """ข้อมูลสำหรับ dropdown หน้าแจ้งซ่อมสาธารณะ (ไม่ต้อง auth):
    - device_types: ประเภทอุปกรณ์ที่เลือกได้
    - devices: รายการอุปกรณ์ที่ลงทะเบียนไว้แล้ว (device_id, room, org...)
    """
    rows = db.execute(
        select(Device, Room, Organization)
        .outerjoin(Room, Room.id == Device.room_id)
        .join(Organization, Organization.id == Device.organization_id)
        .order_by(Device.device_id)
        .limit(500)
    ).all()
    devices: list[DeviceInfo] = []
    for device, room, org in rows:
        devices.append(DeviceInfo(
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
            warranty_until=device.warranty_until,
            notes=device.notes,
        ))
    return PublicOptionsOut(device_types=DEVICE_TYPE_LABELS, devices=devices)


@app.post("/api/public/report", status_code=201)
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
        # ── Resolve/สร้าง device ──
        device = None
        room_text = ""
        # กรณีรู้ device code แล้ว (เลือกจาก dropdown)
        if payload.device_id:
            device = db.execute(
                select(Device).where(Device.device_id == payload.device_id.strip())
            ).scalar_one_or_none()
            if not device:
                raise HTTPException(status_code=404, detail="Device not found")
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
        open_ticket = db.execute(
            select(RepairTicket)
            .where(
                RepairTicket.device_id == device.device_id,
                RepairTicket.status.in_(["new", "assigned", "in_progress", "pending"]),
            )
            .order_by(RepairTicket.created_at.desc())
        ).scalars().first()
        if open_ticket:
            raise HTTPException(
                status_code=409,
                detail={
                    "code": "DUPLICATE_OPEN_TICKET",
                    "message": "อุปกรณ์นี้มีการแจ้งซ่อมที่ยังไม่ปิดอยู่แล้ว",
                    "existing_ticket_no": open_ticket.ticket_id,
                    "existing_status": open_ticket.status,
                },
            )

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
        )
        db.add(ticket)
        db.flush()

        update = TicketUpdate(
            ticket=ticket,
            from_status=None,
            to_status=TicketStatus.NEW,
            note="Ticket created from public no-login form",
            author_name=name,
            author_role="reporter",
        )
        db.add(update)

        db.commit()
        db.refresh(ticket)

        # แจ้ง n8n (fire-and-forget)
        _notify_n8n("ticket.created", _ticket_event_payload(ticket))

        return {
            "ticket_id": ticket.ticket_id,
            "device_id": device.device_id,
            "device_type": device.device_type,
            "room_name": room_text,
            "status": ticket.status,
            "organization_code": org.code,
            "message": "ส่งคำร้องแจ้งซ่อมเรียบร้อยแล้ว",
        }
    except HTTPException:
        db.rollback()
        raise
    except Exception:
        db.rollback()
        raise


@app.get("/api/devices", response_model=list[DeviceInfo])
def list_devices(
    status: Optional[str] = Query(None),
    device_type: Optional[str] = Query(None),
    organization_code: Optional[str] = Query(None),
    organization_id: Optional[int] = Query(None),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user_optional),
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
            warranty_until=device.warranty_until,
            notes=device.notes,
        ))
    return result



@app.post("/api/devices", response_model=DeviceInfo, status_code=201)
def create_device(payload: DeviceCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
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
        warranty_until=payload.warranty_until,
    )
    db.add(device)
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
        warranty_until=device.warranty_until,
        notes=device.notes,
    )


@app.patch("/api/devices/{device_id}", response_model=DeviceInfo)
def update_device(device_id: str, payload: DeviceUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
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

    for k, v in data.items():
        setattr(device, k, v)
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
        warranty_until=device.warranty_until,
        notes=device.notes,
    )


@app.delete("/api/devices/{device_id}")
def delete_device(device_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
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

    db.execute(text("DELETE FROM scan_logs WHERE device_id=:d"), {"d": device_id})
    db.delete(device)
    db.commit()
    return {"message": "Device deleted", "device_id": device_id}


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
def create_user(payload: UserCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school"))):
    exists = db.execute(select(User).where(User.line_user_id == payload.line_user_id)).scalar_one_or_none()
    if exists:
        raise HTTPException(status_code=400, detail="line_user_id ซ้ำ")

    # ── จำกัดสิทธิ์การสร้าง user ตามบทบาท ──
    if payload.role == "owner" and user.role != "owner":
        raise HTTPException(status_code=403, detail="มีเพียง Owner เท่านั้นที่กำหนดบทบาท Owner ได้")
    if user.role == "admin_school":
        # admin_school: สร้างได้เฉพาะ teacher / student / it_support และในรรตัวเองเท่านั้น
        if payload.role not in ("teacher", "student", "it_support"):
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
def delete_user(user_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school"))):
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
    db.delete(target)
    db.commit()
    return {"message": "User deleted", "user_id": user_id}


@app.patch("/api/users/{user_id}", response_model=UserOut)
def update_user(user_id: int, payload: UserUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school"))):
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
        if new_role not in ("teacher", "student", "it_support"):
            raise HTTPException(status_code=403, detail="ผู้ดูแลโรงเรียนไม่สามารถกำหนดบทบาทนี้ได้ (ได้แค่ ครู/นักเรียน/เจ้าหน้าที่ IT)")
        if "organization_id" in data and data["organization_id"] not in (user.organization_id, None):
            raise HTTPException(status_code=403, detail="ผู้ดูแลโรงเรียนไม่สามารถย้ายผู้ใช้ข้ามโรงเรียนได้")

    password = data.pop("password", None)
    if password:
        target.password_hash = hash_password(password)
    for k, v in data.items():
        setattr(target, k, v)
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
@app.post("/api/auth/login")
@limiter.limit("10/minute")
def login(request: Request, payload: LoginRequest, db: Session = Depends(get_db)):
    """Login ด้วย username (line_user_id) + password"""
    user = db.execute(
        select(User).where(User.line_user_id == payload.username)
    ).scalar_one_or_none()
    if not user or not verify_password(payload.password, user.password_hash):
        raise HTTPException(status_code=401, detail="ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="บัญชีถูกปิดใช้งาน")

    user.last_login_at = datetime.now(timezone.utc)
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
    if scope is not None:
        params["oids"] = tuple(scope)
        scope_where = " AND d.organization_id IN :oids"
        dev_scope_where = " AND d.organization_id IN :oids"
    by_type = db.execute(text(f"""
        SELECT d.device_type, COUNT(rt.id) as count
        FROM repair_tickets rt
        JOIN devices d ON rt.device_id = d.device_id
        WHERE 1=1 {scope_where}
        GROUP BY d.device_type
        ORDER BY count DESC
    """), params).fetchall()

    by_status = db.execute(text(f"""
        SELECT rt.status, COUNT(*) as count
        FROM repair_tickets rt
        JOIN devices d ON d.device_id = rt.device_id
        WHERE 1=1 {scope_where}
        GROUP BY rt.status
        ORDER BY count DESC
    """), params).fetchall()

    by_priority = db.execute(text(f"""
        SELECT rt.priority, COUNT(*) as count
        FROM repair_tickets rt
        JOIN devices d ON d.device_id = rt.device_id
        WHERE 1=1 {scope_where}
        GROUP BY rt.priority
        ORDER BY count DESC
    """), params).fetchall()

    devices_by_status = db.execute(text(f"""
        SELECT d.status, COUNT(*) as count
        FROM devices d
        WHERE 1=1 {dev_scope_where}
        GROUP BY d.status
        ORDER BY count DESC
    """), params).fetchall()

    return {
        "by_type": [{"device_type": r.device_type, "count": r.count} for r in by_type],
        "by_status": [{"status": r.status, "count": r.count} for r in by_status],
        "by_priority": [{"priority": r.priority, "count": r.count} for r in by_priority],
        "devices_by_status": [{"status": r.status, "count": r.count} for r in devices_by_status],
    }

@app.get("/api/organizations")
def list_organizations(db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user_optional)):
    """รายการโรงเรียน — admin_school เห็นเฉพาะรรตัวเอง"""
    scope = visible_org_ids(user) if user else None
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
def delete_organization(org_id: int, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin"))):
    """ลบโรงเรียนทั้งหมด: tickets → updates → scanlogs → devices → rooms → org"""
    org = db.execute(select(Organization).where(Organization.id == org_id)).scalar_one_or_none()
    if not org:
        raise HTTPException(status_code=404, detail="Organization not found")

    db.execute(text("""
        DELETE FROM ticket_updates WHERE ticket_id IN (
            SELECT rt.id FROM repair_tickets rt
            JOIN devices d ON d.device_id = rt.device_id
            WHERE d.organization_id = :oid
        )
    """), {"oid": org_id})
    db.execute(text("""
        DELETE FROM repair_tickets WHERE device_id IN (
            SELECT device_id FROM devices WHERE organization_id = :oid
        )
    """), {"oid": org_id})
    db.execute(text("""
        DELETE FROM scan_logs WHERE device_id IN (
            SELECT device_id FROM devices WHERE organization_id = :oid
        )
    """), {"oid": org_id})
    db.execute(text("DELETE FROM devices WHERE organization_id=:oid"), {"oid": org_id})
    db.execute(text("DELETE FROM rooms WHERE organization_id=:oid"), {"oid": org_id})
    db.delete(org)  # users ที่ผูก (organization_id FK CASCADE) จะถูกลบตาม
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
    status: Optional[str] = Query(None),
    priority: Optional[str] = Query(None),
    device_id: Optional[str] = Query(None),
    organization_id: Optional[int] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
):
    stmt = (
        select(RepairTicket)
        .join(Device, Device.device_id == RepairTicket.device_id)
        .order_by(RepairTicket.created_at.desc())
    )
    if status:
        stmt = stmt.where(RepairTicket.status == status)
    if priority:
        stmt = stmt.where(RepairTicket.priority == priority)
    if device_id:
        stmt = stmt.where(RepairTicket.device_id == device_id)
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

    rows = db.execute(stmt).scalars().all()
    result: list[TicketOut] = []
    for t in rows:
        result.append(TicketOut(
            id=t.id,
            ticket_id=t.ticket_id,
            device_id=t.device_id,
            title=t.title,
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
        scan_gps_lat=(float(ticket.scan_gps_lat) if ticket.scan_gps_lat else None),
        scan_gps_lng=(float(ticket.scan_gps_lng) if ticket.scan_gps_lng else None),
        scan_timestamp=ticket.scan_timestamp,
        resolution_notes=ticket.resolution_notes,
        created_at=ticket.created_at,
        updated_at=ticket.updated_at,
    )
    out_dict = out.model_dump()
    out_dict["device_info"] = {
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
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support")),
):
    ticket = db.execute(
        select(RepairTicket).where(RepairTicket.ticket_id == ticket_id)
    ).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    check_ticket_access(db, user, ticket)

    current = ticket.status
    target = payload.status

    if not payload.force and target not in STATUS_TRANSITIONS.get(current, set()):
        raise HTTPException(
            status_code=400,
            detail=f"Invalid transition: {current} → {target}",
        )

    ticket.status = target
    if target in (TicketStatus.RESOLVED, TicketStatus.CLOSED, TicketStatus.CANCELLED):
        if ticket.closed_at is None:
            ticket.closed_at = datetime.now(timezone.utc)
        if target == TicketStatus.RESOLVED and ticket.resolved_at is None:
            ticket.resolved_at = datetime.now(timezone.utc)
    if target == TicketStatus.ASSIGNED and not ticket.assigned_to:
        ticket.assigned_to = payload.author_name or "Unassigned"

    update = TicketUpdate(
        ticket=ticket,
        from_status=current,
        to_status=target,
        note=payload.note,
        author_name=payload.author_name,
        author_role=payload.author_role,
    )
    db.add(update)
    db.commit()
    db.refresh(ticket)

    # แจ้ง n8n (fire-and-forget) — เปลี่ยนสถานะ
    payload_data = _ticket_event_payload(ticket)
    payload_data["from_status"] = current
    payload_data["to_status"] = target
    _notify_n8n("ticket.status_changed", payload_data)

    return {
        "ticket_id": ticket.ticket_id,
        "from_status": current,
        "to_status": target,
        "message": "Status updated",
    }


@app.delete("/api/tickets/{ticket_id}")
def delete_ticket(ticket_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """ลบ ticket + ประวัติทั้งหมด (admin / admin_school / IT support)"""
    ticket = db.execute(
        select(RepairTicket).where(RepairTicket.ticket_id == ticket_id)
    ).scalar_one_or_none()
    if not ticket:
        raise HTTPException(status_code=404, detail="Ticket not found")
    check_ticket_access(db, user, ticket)

    # ลบ updates ก่อน (กัน FK constraint)
    db.execute(
        text("DELETE FROM ticket_updates WHERE ticket_id = :tid"),
        {"tid": ticket.id},
    )
    db.delete(ticket)
    db.commit()
    return {"message": "Ticket deleted", "ticket_id": ticket_id}


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
            "pending": 0, "resolved": 0, "closed": 0, "cancelled": 0, "new": 0,
            "low": 0, "normal": 0, "medium": 0, "high": 0, "critical": 0,
            "by_type": {}, "by_status": {}, "by_priority": {}, "devices_by_status": {},
            "self_service_total": 0, "recent_tickets": [],
        }
    params: dict = {}
    if scope is not None:
        params["oids"] = tuple(scope)
    total = db.execute(text("SELECT COUNT(*) FROM repair_tickets t LEFT JOIN devices d ON d.device_id=t.device_id" + (" WHERE d.organization_id IN :oids" if scope is not None else "")), params).scalar_one()
    total_devices = db.execute(text("SELECT COUNT(*) FROM devices d" + (" WHERE d.organization_id IN :oids" if scope is not None else "")), params).scalar_one()

    def count_by(col, table, where=None):
        q = f"SELECT {col}, COUNT(*) FROM {table}"
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
        q += " GROUP BY " + col
        return {r[0]: r[1] for r in db.execute(text(q), params).fetchall()}

    by_status = count_by("status", "repair_tickets")
    by_priority = count_by("priority", "repair_tickets")
    by_type = count_by("device_type", "devices")
    devices_by_status = count_by("status", "devices")

    def st(s):
        return by_status.get(s, 0)

    # self_service_cases ไม่มี organization_id — นับผ่าน device
    if scope is not None:
        self_service_total = db.execute(text(
            "SELECT COUNT(*) FROM self_service_cases s JOIN devices d ON d.device_id = s.device_id "
            "WHERE d.organization_id IN :oids"), params).scalar_one()
    else:
        self_service_total = db.execute(text("SELECT COUNT(*) FROM self_service_cases")).scalar_one()

    recent_where = (" WHERE d.organization_id IN :oids" if scope is not None else "")
    recent = db.execute(text("""
        SELECT t.ticket_id, t.title, t.status, t.priority, t.created_at,
               d.device_type, r.name AS room_name, o.name AS organization_name
        FROM repair_tickets t
        LEFT JOIN devices d ON d.device_id = t.device_id
        LEFT JOIN rooms r ON r.id = d.room_id
        LEFT JOIN organizations o ON o.id = d.organization_id
    """ + recent_where + """
        ORDER BY t.created_at DESC
        LIMIT 10
    """), params).fetchall()

    return {
        "total_tickets": total,
        "total_devices": total_devices,
        "open": st("new"),
        "assigned": st("assigned"),
        "in_progress": st("in_progress"),
        "pending": st("pending"),
        "resolved": st("resolved"),
        "closed": st("closed"),
        "cancelled": st("cancelled"),
        "new": st("new"),
        "low": by_priority.get("low", 0),
        "normal": by_priority.get("normal", 0),
        "medium": by_priority.get("medium", 0),
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


# ─── Uploads (รูปภาพแนบ — TOR 1.5.2) ─────────────────────────────────
from fastapi import File, UploadFile
from fastapi.staticfiles import StaticFiles

UPLOAD_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "uploads")
os.makedirs(UPLOAD_DIR, exist_ok=True)
app.mount("/uploads", StaticFiles(directory=UPLOAD_DIR), name="uploads")

@app.post("/api/uploads", status_code=201)
async def upload_file(
    file: UploadFile = File(...),
    user: Optional[User] = Depends(get_current_user_optional),
):
    """อัปโหลดรูปภาพ (สูงสุด 10MB) — ใช้กับฟอร์มแจ้งซ่อม + PM
    โหมด local: เขียน disk + mount /uploads  |  โหมด cloud (S3): upload + คืน URL เต็ม"""
    from app.storage import save_upload
    content = await file.read()
    if len(content) > 10 * 1024 * 1024:
        raise HTTPException(status_code=413, detail="ไฟล์เกิน 10 MB")
    return save_upload(content, file.filename or "image.jpg")


# ─── Knowledge Base (KB — TOR 1.5.5 / 5.6) ────────────────────────────

class KBArticleCreate(BaseModel):
    device_type: Optional[str] = None
    title: str = Field(..., min_length=3, max_length=255)
    symptom_tags: Optional[list[str]] = None
    steps: Optional[list] = None
    is_published: bool = True

class KBArticleUpdate(BaseModel):
    device_type: Optional[str] = None
    title: Optional[str] = None
    symptom_tags: Optional[list[str]] = None
    steps: Optional[list] = None
    is_published: Optional[bool] = None

class KBArticleOut(BaseModel):
    id: int
    kb_id: str
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
        stmt = stmt.where(KBArticle.title.ilike(f"%{q}%"))
    rows = db.execute(stmt.offset(offset).limit(limit)).scalars().all()
    return [_kb_to_out(a) for a in rows]


@app.get("/api/kb/articles/{kb_id}", response_model=KBArticleOut)
def get_kb_article(kb_id: str, db: Session = Depends(get_db)):
    a = db.execute(select(KBArticle).where(KBArticle.kb_id == kb_id)).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="KB article not found")
    return _kb_to_out(a)


@app.post("/api/kb/articles", response_model=KBArticleOut, status_code=201)
def create_kb_article(payload: KBArticleCreate, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school"))):
    count = db.execute(select(func.count()).select_from(KBArticle)).scalar_one() + 1
    # admin_school สร้างบทความเฉพาะรรตัวเอง; owner/admin/super_admin สร้างบทความส่วนกลาง (None)
    org_id = user.organization_id if user.role == "admin_school" else None
    a = KBArticle(
        kb_id=f"kb-{count:04d}",
        organization_id=org_id,
        device_type=payload.device_type,
        title=payload.title,
        symptom_tags=json.dumps(payload.symptom_tags or [], ensure_ascii=False),
        steps=json.dumps(payload.steps or [], ensure_ascii=False),
        is_published=payload.is_published,
    )
    db.add(a); db.commit(); db.refresh(a)
    return _kb_to_out(a)


@app.patch("/api/kb/articles/{kb_id}", response_model=KBArticleOut)
def update_kb_article(kb_id: str, payload: KBArticleUpdate, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school"))):
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
    if "symptom_tags" in data and data["symptom_tags"] is not None:
        data["symptom_tags"] = json.dumps(data["symptom_tags"], ensure_ascii=False)
    if "steps" in data and data["steps"] is not None:
        data["steps"] = json.dumps(data["steps"], ensure_ascii=False)
    for k, v in data.items():
        setattr(a, k, v)
    db.commit(); db.refresh(a)
    return _kb_to_out(a)


@app.delete("/api/kb/articles/{kb_id}")
def delete_kb_article(kb_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school"))):
    a = db.execute(select(KBArticle).where(KBArticle.kb_id == kb_id)).scalar_one_or_none()
    if not a:
        raise HTTPException(status_code=404, detail="KB article not found")
    if user.role == "admin_school":
        if a.organization_id != user.organization_id:
            raise HTTPException(status_code=403, detail="คุณลบได้เฉพาะบทความของโรงเรียนตนเองเท่านั้น")
    elif a.organization_id is not None:
        raise HTTPException(status_code=403, detail="บทความนี้เป็นของโรงเรียนเฉพาะ — ผู้ดูแลบริษัทลบได้เฉพาะบทความหลัก")
    db.delete(a); db.commit()
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
def ai_diagnose(payload: DiagnoseRequest, db: Session = Depends(get_db)):
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
def sla_check(db: Session = Depends(get_db)):
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


# ─── Preventive Maintenance (TOR 1.5.10 / 5.9) ───────────────────────


# ─── QR Service (TOR 1.5.4 / 5.3) ─────────────────────────────────────

@app.get("/api/qr/resolve/{token}")
def qr_resolve(token: str, db: Session = Depends(get_db)):
    """แปลง QR token → ข้อมูลอุปกรณ์ (ไม่ต้อง login, มี rate limit ตาม spec)"""
    device = db.execute(select(Device).where(Device.qr_token == token)).scalar_one_or_none()
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
        "qr_url": f"/scan?t={token}",
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
def qr_lookup(q: str = Query(..., min_length=2), limit: int = Query(10, ge=1, le=50), db: Session = Depends(get_db)):
    """ช่องทางสำรอง QR ชำรุด — ค้นหาด้วยรหัสอุปกรณ์ (รองรับบางส่วน)"""
    rows = db.execute(
        select(Device)
        .where(Device.device_id.ilike(f"%{q}%"))
        .order_by(Device.device_id)
        .limit(limit)
    ).scalars().all()
    return [
        {
            "device_id": d.device_id,
            "device_type": d.device_type,
            "brand": d.brand,
            "model": d.model,
            "organization_id": d.organization_id,
            "qr_url": f"/scan?t={d.qr_token}" if d.qr_token else f"/scan?device={d.device_id}",
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
    t = db.execute(select(RepairTicket).where(RepairTicket.ticket_id == ticket_no)).scalar_one_or_none()
    if not t:
        raise HTTPException(status_code=404, detail="ไม่พบหมายเลข Ticket นี้")
    device = db.execute(select(Device).where(Device.device_id == t.device_id)).scalar_one_or_none()
    room = db.get(Room, device.room_id) if device and device.room_id else None
    status_label = {
        "new": "รอรับเรื่อง", "assigned": "มอบหมายแล้ว", "in_progress": "กำลังดำเนินการ",
        "pending": "รออะไหล่/รอภายนอก", "resolved": "ซ่อมเสร็จ รอผู้แจ้งยืนยัน",
        "closed": "ปิดงาน", "cancelled": "ยกเลิก",
    }.get(t.status, t.status)
    order = ["new", "assigned", "in_progress", "pending", "resolved", "closed"]
    idx = order.index(t.status) if t.status in order else -1
    return {
        "ticket_no": t.ticket_id,
        "status": t.status,
        "status_label": status_label,
        "device_code": device.device_id if device else None,
        "device_type": device.device_type if device else None,
        "room_name": room.name if room else None,
        "title": t.title,
        "priority": t.priority,
        "created_at": t.created_at,
        "estimated_completion": t.sla_due_at,
        "closed_at": t.closed_at,
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
def ticket_assign(ticket_id: str, payload: TicketAssignReq, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin"))):
    """มอบหมายงานให้ช่าง (admin/super_admin)"""
    t = _get_ticket_or_404(db, ticket_id)
    old = t.status
    t.assigned_to = payload.assignee
    if old == "new":
        t.status = "assigned"
    _add_update(db, t, old, t.status, payload.note or f"มอบหมายให้ {payload.assignee}", user.line_display_name or "Admin", user.role)
    db.commit()
    return {"ticket_id": t.ticket_id, "status": t.status, "assigned_to": t.assigned_to}

@app.post("/api/tickets/{ticket_id}/accept", status_code=200)
def ticket_accept(ticket_id: str, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """ช่างรับงาน — assigned/new → in_progress"""
    t = _get_ticket_or_404(db, ticket_id)
    check_ticket_access(db, user, t)
    if t.status not in ("assigned", "new"):
        raise HTTPException(status_code=409, detail={"code": "CONFLICT", "message": f"สถานะปัจจุบันคือ {t.status} — ไม่สามารถรับงานได้"})
    old = t.status
    t.status = "in_progress"
    t.assigned_to = t.assigned_to or (user.line_display_name or "ช่าง")
    _add_update(db, t, old, t.status, "รับงานแล้ว กำลังดำเนินการ", user.line_display_name or "Technician", user.role)
    db.commit()
    return {"ticket_id": t.ticket_id, "status": t.status, "assigned_to": t.assigned_to}

@app.post("/api/tickets/{ticket_id}/resolve", status_code=200)
def ticket_resolve(ticket_id: str, payload: TicketResolveReq, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """บันทึกผลการซ่อม — resolved + บันทึกสาเหตุ/วิธีแก้/รูปหลังซ่อม"""
    t = _get_ticket_or_404(db, ticket_id)
    check_ticket_access(db, user, t)
    if not payload.solution.strip():
        raise HTTPException(status_code=400, detail="ต้องกรอกวิธีแก้ไข (solution)")
    old = t.status
    t.status = "resolved"
    t.root_cause = payload.root_cause
    t.solution = payload.solution
    t.parts_used = json.dumps(payload.parts_used or [], ensure_ascii=False) if payload.parts_used else None
    t.resolution_notes = " ".join(payload.after_photos or []) or None
    t.resolved_at = datetime.now(timezone.utc)
    if payload.after_photos:
        for url in payload.after_photos:
            db.add(TicketAttachment(ticket_id=t.ticket_id, file_url=url, phase="after", uploaded_by=user.line_display_name))
    _add_update(db, t, old, "resolved", "ซ่อมเสร็จ: " + payload.solution[:150], user.line_display_name or "Technician", user.role)
    db.commit()
    return {"ticket_id": t.ticket_id, "status": t.status, "resolved_at": t.resolved_at, "sla_met": t.sla_met}

@app.post("/api/tickets/{ticket_id}/close", status_code=200)
def ticket_close(ticket_id: str, payload: TicketCloseReq, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """ผู้แจ้ง/admin ปิดงาน + ให้คะแนน (resolved → closed)"""
    t = _get_ticket_or_404(db, ticket_id)
    if t.status != "resolved":
        raise HTTPException(status_code=409, detail={"code": "INVALID_STATUS_TRANSITION", "message": f"ต้องเป็นสถานะ resolved ก่อนปิด (ปัจจุบัน: {t.status})"})
    old = t.status
    t.status = "closed"
    t.closed_at = datetime.now(timezone.utc)
    if payload.rating is not None:
        t.rating = payload.rating
    if payload.feedback:
        t.feedback = payload.feedback
    _add_update(db, t, old, "closed", payload.feedback or "ผู้แจ้งยืนยันปิดงาน", user.line_display_name or "User", user.role)
    db.commit()
    return {"ticket_id": t.ticket_id, "status": t.status, "closed_at": t.closed_at, "rating": t.rating}

@app.post("/api/tickets/{ticket_id}/reopen", status_code=200)
def ticket_reopen(ticket_id: str, payload: TicketCommentReq, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    """เปิดงานใหม่กรณีปัญหากลับมา (closed → in_progress)"""
    t = _get_ticket_or_404(db, ticket_id)
    if t.status != "closed":
        raise HTTPException(status_code=409, detail={"code": "INVALID_STATUS_TRANSITION", "message": f"เฉพาะงานที่ปิดแล้วเท่านั้นที่เปิดใหม่ได้ (ปัจจุบัน: {t.status})"})
    old = t.status
    t.status = "in_progress"
    t.closed_at = None
    t.resolved_at = None
    _add_update(db, t, old, "in_progress", payload.note or "เปิดงานใหม่ (ปัญหากลับมาเกิดซ้ำ)", user.line_display_name or "User", user.role)
    db.commit()
    return {"ticket_id": t.ticket_id, "status": t.status}

@app.post("/api/tickets/{ticket_id}/cancel", status_code=200)
def ticket_cancel(ticket_id: str, payload: TicketCommentReq, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin", "admin_school", "it_support"))):
    """ยกเลิกงานพร้อมเหตุผล"""
    t = _get_ticket_or_404(db, ticket_id)
    check_ticket_access(db, user, t)
    if t.status in ("closed", "cancelled"):
        raise HTTPException(status_code=409, detail={"code": "INVALID_STATUS_TRANSITION", "message": f"สถานะ {t.status} ไม่สามารถยกเลิกได้"})
    old = t.status
    t.status = "cancelled"
    t.closed_at = datetime.now(timezone.utc)
    _add_update(db, t, old, "cancelled", payload.note or "ยกเลิก", user.line_display_name or "User", user.role)
    db.commit()
    return {"ticket_id": t.ticket_id, "status": t.status}

# ─── Comments (TOR 5.7) ────────────────────────────────────────────────
@app.get("/api/tickets/{ticket_id}/comments")
def list_ticket_comments(ticket_id: str, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user_optional)):
    _get_ticket_or_404(db, ticket_id)
    rows = db.execute(select(TicketComment).where(TicketComment.ticket_id == ticket_id).order_by(TicketComment.created_at)).scalars().all()
    return [{"id": c.id, "note": c.note, "author_name": c.author_name, "author_role": c.author_role,
             "is_internal": c.is_internal, "created_at": c.created_at} for c in rows]

@app.post("/api/tickets/{ticket_id}/comments", status_code=201)
def add_ticket_comment(ticket_id: str, payload: TicketCommentReq, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user_optional)):
    _get_ticket_or_404(db, ticket_id)
    c = TicketComment(ticket_id=ticket_id, note=payload.note, is_internal=payload.is_internal,
                      author_id=user.id if user else None,
                      author_name=payload.author_name or (user.line_display_name if user else "Guest"),
                      author_role=user.role if user else "guest")
    db.add(c); db.commit(); db.refresh(c)
    return {"id": c.id, "note": c.note, "author_name": c.author_name, "created_at": c.created_at}

# ─── Attachments (TOR 5.7) ─────────────────────────────────────────────
@app.get("/api/tickets/{ticket_id}/attachments")
def list_ticket_attachments(ticket_id: str, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user_optional)):
    _get_ticket_or_404(db, ticket_id)
    rows = db.execute(select(TicketAttachment).where(TicketAttachment.ticket_id == ticket_id).order_by(TicketAttachment.created_at)).scalars().all()
    return [{"id": a.id, "file_url": a.file_url, "phase": a.phase, "mime_type": a.mime_type,
             "file_size": a.file_size, "uploaded_by": a.uploaded_by, "created_at": a.created_at} for a in rows]

@app.post("/api/tickets/{ticket_id}/attachments", status_code=201)
def add_ticket_attachment(ticket_id: str, payload: TicketAttachmentReq, db: Session = Depends(get_db), user: Optional[User] = Depends(get_current_user_optional)):
    _get_ticket_or_404(db, ticket_id)
    a = TicketAttachment(ticket_id=ticket_id, file_url=payload.file_url, file_size=payload.file_size,
                         mime_type=payload.mime_type, phase=payload.phase,
                         uploaded_by=payload.uploaded_by or (user.line_display_name if user else "Guest"))
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
def update_settings(payload: dict, db: Session = Depends(get_db), user: User = Depends(require_roles("owner", "super_admin", "admin"))):
    """ปรับค่า SLA / working hours / auto-close / AI threshold — ไม่ต้อง deploy ใหม่"""
    allowed = {"sla_hours", "working_hours", "auto_close_days", "ai_confidence_threshold"}
    updated = []
    for key, value in payload.items():
        if key not in allowed:
            continue
        row = db.execute(select(Setting).where(Setting.key == key)).scalar_one_or_none()
        if row:
            row.value = json.dumps(value)
        else:
            db.add(Setting(key=key, value=json.dumps(value)))
        updated.append(key)
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
    params = {"days": days}
    total = db.execute(text("SELECT COUNT(*) FROM chatbot_logs WHERE created_at >= now() - make_interval(days => :days)"), params).scalar_one()
    resolved = db.execute(text("SELECT COUNT(*) FROM chatbot_logs WHERE resolved=TRUE AND created_at >= now() - make_interval(days => :days)"), params).scalar_one()
    intents = {r[0]: r[1] for r in db.execute(text(
        "SELECT intent, COUNT(*) FROM chatbot_logs WHERE created_at >= now() - make_interval(days => :days) GROUP BY intent ORDER BY COUNT(*) DESC"), params).fetchall()}
    missed = db.execute(text(
        "SELECT message FROM chatbot_logs WHERE (intent='other' OR ai_response='' OR ai_response IS NULL) "
        "AND created_at >= now() - make_interval(days => :days) ORDER BY created_at DESC LIMIT 50"), params).fetchall()
    return {
        "total_conversations": total,
        "self_service_resolved": resolved,
        "self_service_rate": round(resolved * 100.0 / total, 1) if total else 0.0,
        "intent_distribution": intents,
        "missed_queries": [r[0] for r in missed],
    }


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
LINE_CHANNEL_SECRET = os.environ.get("LINE_CHANNEL_SECRET", "")

@app.post("/api/line/webhook")
async def line_webhook(request: Request, x_line_signature: Optional[str] = Header(None)):
    """รับ event จาก LINE OA โดยตรง → ตรวจ signature → เรียก LINE chatbot (คุยหลายรอบ)

    LINE ส่ง {events:[{type:message, replyToken, source:{userId,groupId,type},
                       message:{type:text, text}}]}.
    ตอบ 200 เสมอ (เพื่อให้ LINE ไม่ retry); การ reply ข้อความทำผ่าน LINE API แยก.
    """
    raw = await request.body()
    # ตรวจ signature (HMAC-SHA256 ของ channel secret กับ raw body) — ถ้ามี secret ตั้งไว้
    if LINE_CHANNEL_SECRET and x_line_signature:
        import hmac, hashlib, base64 as _b64
        mac = hmac.new(LINE_CHANNEL_SECRET.encode(), raw, hashlib.sha256).digest()
        expected = _b64.b64encode(mac).decode()
        if not hmac.compare_digest(expected, x_line_signature):
            # signature ไม่ตรง → ตอบ 200 เงียบ ๆ (ไม่ประมวลผล) ป้องกันของปลอม
            return {"status": "ignored"}
    try:
        payload = json.loads(raw or b"{}")
    except Exception:
        payload = {}
    events = payload.get("events", [])
    processed = 0
    for ev in events:
        etype = ev.get("type")
        if etype == "message":
            msg = ev.get("message") or {}
            src = ev.get("source") or {}
            if msg.get("type") == "text" and msg.get("text"):
                user_id = src.get("userId") or ""
                group_id = src.get("groupId") or ""
                reply_token = ev.get("replyToken") or ""
                is_group = (src.get("type") == "group")
                text = msg["text"]
                # เรียก chatbot (คุยหลายรอบ) — ตอบ LINE ผ่าน reply_token
                _process_line_text(user_id, text, reply_token, group_id, is_group)
                processed += 1
            # (ภาพ/สติกเกอร์/etc. ข้ามไปก่อน)
    return {"status": "ok", "received": len(events), "processed": processed}


def _process_line_text(user_id: str, text: str, reply_token: str, group_id: str, is_group: bool):
    """ประมวลผลข้อความ LINE ผ่าน chatbot แล้วตอบกลับ (ไม่บล็อก webhook)
    กลุ่ม LINE ใช้สำหรับแจ้งเตือนเท่านั้น — ไม่ตอบกลับข้อความในกลุ่ม"""
    import threading
    # กลุ่ม = แจ้งเตือนอย่างเดียว: ข้าม reply (การแจ้งเตือนใช้ push ไป group_id แยกต่างหาก)
    if is_group:
        return
    def _run():
        try:
            from app.chatbot_core import handle_message
            from app.line_bot import send_line_reply
            from app.chat_session import get_session
            reply = handle_message(
                user_id=user_id, text=text,
                reply_token=reply_token, group=False,
            )
            # G: ดึง quick-reply suggestions ที่ chatbot ฝากไว้ แล้วล้าง
            qr = None
            try:
                sess = get_session(user_id)
                if sess.get("_pending_qr"):
                    qr = sess.get("_pending_qr")
                    s2 = dict(sess); s2.pop("_pending_qr", None)
                    from app.chat_session import save_session as _ss
                    _ss(user_id, s2)
            except Exception:
                pass
            # ตอบ LINE ด้วย reply_token (จาก LINE จริง)
            if reply_token and reply:
                from app.chatbot_core import get_pending_product_image
                send_line_reply(reply_token, reply, qr, get_pending_product_image())
        except Exception:
            pass
    # ใช้ thread เพื่อไม่บล็อก event loop / ตอบ webhook 200 ได้ทันที
    t = threading.Thread(target=_run, daemon=True)
    t.start()


# ═══════════════════════════════════════════════════════════════════════
# n8n integration — ยิง event ไป n8n workflow (fire-and-forget, ไม่บล็อก)
# ═══════════════════════════════════════════════════════════════════════

N8N_WEBHOOK_URL = os.environ.get("N8N_WEBHOOK_URL", "http://n8n:5678/webhook/")

def _notify_n8n(event: str, payload: dict):
    """ส่ง event ไป n8n (async fire-and-forget) — ถ้า n8n ไม่พร้อมก็ข้าม ไม่ทำให้ request หลักล้ม"""
    try:
        import httpx
        url = f"{N8N_WEBHOOK_URL}notify"
        body = {"event": event, **payload}
        # background: ไม่รอ response เกิน 2 วิ
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
def line_bot_handle(payload: LineBotIn):
    """ประมวลผลข้อความ LINE chatbot — คืน {reply: text} (n8n จะเอาคำตอบไป reply)
    ถ้า reply_token มี → backend reply เองได้เลย"""
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
def line_create_ticket(payload: N8nTicketIn, db: Session = Depends(get_db)):
    """รับ payload จาก n8n → resolve device (หรือ default) → สร้าง repair_ticket.
    คืน {ticket_no, ticket_id, success} ให้ n8n นำไป notify ต่อ"""
    from datetime import datetime, timezone as _tz
    device_id = payload.deviceId.strip()
    # resolve device: ตรง device_id / ห้อง / ตัวแรกของ org ไหนก็ได้ → default TEST1-00001
    dev = None
    if device_id:
        dev = db.execute(select(Device).where(Device.device_id == device_id)).scalar_one_or_none()
    if not dev and payload.room:
        # ลอง match ห้อง
        dev = db.execute(text(
            "SELECT d.* FROM devices d JOIN rooms r ON r.id=d.room_id "
            "WHERE r.code ILIKE :rc OR r.name ILIKE :rc LIMIT 1"
        ), {"rc": f"%{payload.room}%"}).mappings().first()
        if dev:
            dev = db.get(Device, dev["id"])
    if not dev:
        # default: ตัวแรก หรือ TEST1
        dev = db.execute(select(Device).order_by(Device.id).limit(1)).scalar_one_or_none()
    if not dev:
        return {"success": False, "error": "ไม่มีอุปกรณ์ในระบบ — เพิ่มอุปกรณ์ก่อน"}
    org_id = dev.organization_id
    prio_map = {"low":"low","Low":"low","medium":"normal","Medium":"normal","normal":"normal","Normal":"normal",
                "high":"high","High":"high","critical":"critical","Critical":"critical"}
    priority = prio_map.get(payload.urgency, "normal")
    now = datetime.now(_tz.utc)
    title = (payload.problemDetail or "แจ้งซ่อมผ่าน LINE")[:120]
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
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    """รายการ lead การขาย (จาก LINE) เรียงล่าสุดก่อน"""
    rows = db.execute(
        text("SELECT id, user_id, name, phone, interest, products, source, note, status, created_at "
             "FROM sales_leads ORDER BY created_at DESC, id DESC LIMIT :lim"),
        {"lim": limit},
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


@app.patch("/api/sales/leads/{lead_id}")
def update_sales_lead_status(
    lead_id: int,
    payload: LeadStatusUpdate,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("owner", "super_admin", "admin", "it_support")),
):
    """ทำเครื่องหมาย lead ว่าติดต่อแล้ว (status = contacted)"""
    row = db.execute(
        text("SELECT id, name, status FROM sales_leads WHERE id = :lid"),
        {"lid": lead_id},
    ).mappings().first()
    if not row:
        raise HTTPException(status_code=404, detail=f"Lead {lead_id} ไม่พบ")
    db.execute(
        text("UPDATE sales_leads SET status = :s WHERE id = :lid"),
        {"s": payload.status, "lid": lead_id},
    )
    db.commit()
    return {"id": lead_id, "status": payload.status, "name": row["name"]}


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
    db.execute(text("DELETE FROM sales_leads WHERE id = :lid"), {"lid": lead_id})
    db.commit()
    return {"deleted": True, "id": lead_id, "name": row["name"]}


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





