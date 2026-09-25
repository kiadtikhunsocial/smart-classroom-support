"""app/models.py — Database models for Smart Classroom Support System
PostgreSQL only — connection string มาจาก env DATABASE_URL
"""
import os
from datetime import datetime, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    DateTime,
    Enum as SAEnum,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    create_engine,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import (
    DeclarativeBase,
    Mapped,
    mapped_column,
    relationship,
    sessionmaker,
)

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

# โปรเจกต์นี้ผูกกับ PostgreSQL: models ใช้ JSONB และ query ใน main.py ใช้ ILIKE /
# SUBSTRING(... FROM 'regex') ซึ่ง SQLite ไม่รองรับ — จึงไม่มี fallback เป็นไฟล์ .db
# production (Render/Neon) ตั้งค่าผ่าน env DATABASE_URL เสมอ
DEFAULT_DATABASE_URL = "postgresql+psycopg2://postgres:postgres@localhost:5432/smart_classroom"
DATABASE_URL = os.getenv("DATABASE_URL") or DEFAULT_DATABASE_URL

engine = create_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)
SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """สร้างตารางทั้งหมด — เรียกตอนแอปสตาร์ท"""
    Base.metadata.create_all(bind=engine)
    # The former PostgreSQL enum prevented staff from adding equipment types.
    # Migrate existing rows losslessly; fresh databases already use VARCHAR.
    with engine.begin() as connection:
        column_type = connection.execute(
            text(
                "SELECT udt_name FROM information_schema.columns "
                "WHERE table_schema = current_schema() AND table_name = 'devices' AND column_name = 'device_type'"
            )
        ).scalar_one_or_none()
        if column_type == "device_type_enum":
            connection.execute(text(
                "ALTER TABLE devices ALTER COLUMN device_type TYPE VARCHAR(64) USING device_type::text"
            ))


# ---------------------------------------------------------------------------
# Base class (SQLAlchemy 2.0 style — inheritance, ไม่ใช่เรียก constructor)
# ---------------------------------------------------------------------------

class Base(DeclarativeBase):
    """ฐานสำหรับ ORM models ทั้งหมด"""
    pass


# ---------------------------------------------------------------------------
# Enums (Python str enum สำหรับใช้ใน model column)
# ---------------------------------------------------------------------------


class DeviceType(str):
    INTERACTIVE_DISPLAY = "Interactive Display"
    COMPUTER_AIO = "Computer AIO"
    COMPUTER_NOTEBOOK = "Computer Notebook"
    COMPUTER_TABLET = "Computer Tablet"
    COMPUTER_DESKTOP = "Computer Desktop"
    ROUTER = "Router"
    ACCESS_POINT = "Access Point"
    SWITCH = "Switch"
    SPEAKER = "Speaker"
    CAMERA = "Camera"
    VISUALIZER = "Visualizer"
    MICROPHONE = "Microphone"
    UPS = "UPS"
    PRINTER = "Printer"
    PROJECTOR = "Projector"
    SOFTWARE_PICARO = "Software (Picaro)"
    SOFTWARE_PHONICS_HERO = "Software (Phonics Hero)"
    OTHER = "Other"


class DeviceTypeOption(Base):
    __tablename__ = "device_type_options"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class DeviceStatus(str):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DECOMMISSIONED = "decommissioned"


class TicketStatus(str):
    NEW = "new"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    PENDING = "pending"
    WAITING_PARTS = "waiting_parts"
    WAITING_USER = "waiting_user"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class Priority(str):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


# SAEnum definitions — create_type=False สำหรับ SQLite compatibility
device_status_enum = SAEnum(
    "active", "inactive", "decommissioned",
    name="device_status_enum",
    create_type=False,
)

ticket_status_enum = SAEnum(
    "new", "assigned", "in_progress", "pending",
    "waiting_parts", "waiting_user",
    "resolved", "closed", "cancelled",
    name="ticket_status_enum",
    create_type=False,
)

priority_enum = SAEnum(
    "low", "normal", "high", "critical",
    name="priority_enum",
    create_type=False,
)


# ---------------------------------------------------------------------------
# ORM Models
# ---------------------------------------------------------------------------


class Organization(Base):
    __tablename__ = "organizations"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    code: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    short_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    timezone: Mapped[str] = mapped_column(String(64), default="Asia/Bangkok")

    rooms: Mapped[list["Room"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    devices: Mapped[list["Device"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )
    users: Mapped[list["User"]] = relationship(
        back_populates="organization", cascade="all, delete-orphan"
    )


class Room(Base):
    __tablename__ = "rooms"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    building: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    floor: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    gps_lat: Mapped[Optional[Numeric]] = mapped_column(Numeric(9, 6), nullable=True)
    gps_lng: Mapped[Optional[Numeric]] = mapped_column(Numeric(9, 6), nullable=True)

    organization: Mapped["Organization"] = relationship(back_populates="rooms")
    devices: Mapped[list["Device"]] = relationship(
        back_populates="room", cascade="all, delete-orphan"
    )


class Device(Base):
    __tablename__ = "devices"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    room_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("rooms.id", ondelete="SET NULL"), nullable=True, index=True
    )
    device_type: Mapped[str] = mapped_column(String(64), nullable=False, default=DeviceType.OTHER)
    brand: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    firmware_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        device_status_enum, default=DeviceStatus.ACTIVE, nullable=False
    )
    qr_code_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    qr_token: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True, index=True)
    # วันที่จัดซื้อ — ใช้คิดอายุอุปกรณ์ใน PM Rule 3 (§38); ไม่มีค่าจะ fallback ไป created_at
    purchase_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    warranty_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    warranty_details: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    organization: Mapped["Organization"] = relationship(back_populates="devices")
    room: Mapped[Optional["Room"]] = relationship(back_populates="devices")
    tickets: Mapped[list["RepairTicket"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )
    scan_logs: Mapped[list["ScanLog"]] = relationship(
        back_populates="device", cascade="all, delete-orphan"
    )


class RepairTicket(Base):
    __tablename__ = "repair_tickets"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.device_id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    reporter_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    reporter_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    reporter_phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    reporter_type: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    priority: Mapped[str] = mapped_column(
        priority_enum, default=Priority.NORMAL, nullable=False
    )
    status: Mapped[str] = mapped_column(
        ticket_status_enum, default=TicketStatus.NEW, nullable=False, index=True
    )
    assigned_to: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    channel: Mapped[Optional[str]] = mapped_column(String(32), default="qr", nullable=True)
    symptom_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    ai_category: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    ai_session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    line_user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    rating_invited_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    scan_gps_lat: Mapped[Optional[Numeric]] = mapped_column(Numeric(9, 6), nullable=True)
    scan_gps_lng: Mapped[Optional[Numeric]] = mapped_column(Numeric(9, 6), nullable=True)
    scan_timestamp: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    screenshot_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    attachments: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list of URLs
    root_cause: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    solution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    parts_used: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list
    resolution_notes: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    # SLA
    sla_due_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    sla_met: Mapped[Optional[bool]] = mapped_column(default=None, nullable=True)
    escalation_level: Mapped[int] = mapped_column(default=0, nullable=False)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    closed_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    rating: Mapped[Optional[int]] = mapped_column(nullable=True)
    feedback: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    device: Mapped["Device"] = relationship(back_populates="tickets")
    updates: Mapped[list["TicketUpdate"]] = relationship(
        back_populates="ticket",
        cascade="all, delete-orphan",
        order_by="TicketUpdate.created_at",
    )


class TicketUpdate(Base):
    __tablename__ = "ticket_updates"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[int] = mapped_column(
        ForeignKey("repair_tickets.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    from_status: Mapped[Optional[str]] = mapped_column(ticket_status_enum, nullable=True)
    to_status: Mapped[Optional[str]] = mapped_column(ticket_status_enum, nullable=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    author_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    author_role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    ticket: Mapped["RepairTicket"] = relationship(back_populates="updates")


class ScanLog(Base):
    __tablename__ = "scan_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(64),
        ForeignKey("devices.device_id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    scan_gps_lat: Mapped[Optional[Numeric]] = mapped_column(Numeric(9, 6), nullable=True)
    scan_gps_lng: Mapped[Optional[Numeric]] = mapped_column(Numeric(9, 6), nullable=True)
    scan_timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    user_agent: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    ip_address: Mapped[Optional[str]] = mapped_column(String(45), nullable=True)
    ticket_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)

    device: Mapped["Device"] = relationship(back_populates="scan_logs")


# ---------------------------------------------------------------------------
# User & Auth (LINE Login — สร้างตารางหลังจากการ OAuth เสร็จสิ้น)
# ---------------------------------------------------------------------------

class UserRole(str):
    """บทบาทผู้ใช้ในระบบ"""
    OWNER = "owner"           # เจ้าของบริษัทสูงสุด (iwasuperadmin) — เห็น/จัดการทุกอย่าง + ห้าม role อื่นแก้
    ADMIN_SCHOOL = "admin_school"  # ผู้ดูแลโรงเรียน — เห็นเฉพาะข้อมูลในโรงเรียนตัวเอง + จัดการ user ในรรตัวเอง
    ADMIN = "admin"           # ผู้ดูแลบริษัท — เห็นทุกโรงเรียน + จัดการทุกอย่างได้
    TEACHER = "teacher"       # [เลิกใช้ — ห้ามกำหนดใหม่] ครู — เห็นเฉพาะ ticket ที่ตัวเองสร้าง + อุปกรณ์ในโรงเรียน
    IT_SUPPORT = "it_support" # เจ้าหน้าที่ IT — สร้างโดย owner/admin=เห็นทุกรร, สร้างโดย admin_school=เห็นเฉพาะรร
    STUDENT = "student"       # [เลิกใช้ — ห้ามกำหนดใหม่] นักเรียน — เห็นอุปกรณ์ + สร้าง ticket + ดู ticket ที่ตัวเองสร้าง
    SUPER_ADMIN = "super_admin"  # ผู้ดูแลบริษัท — เห็นทุกโรงเรียน + จัดการทุกอย่างได้ (ยกเว้น owner)


#: บทบาทที่ยังใช้งานได้จริง (เรียงจากสิทธิ์มากไปน้อย)
ACTIVE_ROLES: tuple[str, ...] = (
    UserRole.OWNER,
    UserRole.SUPER_ADMIN,
    UserRole.ADMIN,
    UserRole.ADMIN_SCHOOL,
    UserRole.IT_SUPPORT,
)

#: บทบาทที่เลิกใช้แล้ว (teacher/student) — ยังต้องอ่านได้จากแถวเก่า แต่ห้ามกำหนดใหม่
#: ค่าเหล่านี้ยังอยู่ใน user_role_enum ของฐานข้อมูล จึงห้ามตัดออกจาก SAEnum ด้านล่าง
LEGACY_ROLES: tuple[str, ...] = ("teacher", "student")


class User(Base):
    """ผู้ใช้ระบบ — เชื่อมโยงกับ LINE OAuth"""
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # LINE OAuth — external provider identifiers
    line_user_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False, index=True)
    line_display_name: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    line_picture_url: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    line_email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)

    # ข้อมูลในระบบ
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    password_hash: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(
        SAEnum("owner", "admin", "admin_school", "teacher", "it_support", "student", "super_admin",
               name="user_role_enum", create_type=False),
        default=UserRole.IT_SUPPORT, nullable=False, index=True
    )
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    last_login_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )

    # Relationships
    organization: Mapped[Optional["Organization"]] = relationship(back_populates="users")


# ---------------------------------------------------------------------------
# สมัครสมาชิก (Membership) — คำขอเปิดบัญชีใช้งานระบบ
# ---------------------------------------------------------------------------

#: สถานะคำขอ เก็บเป็น VARCHAR ไม่ใช่ PG enum — เพิ่มค่าใหม่ได้โดยไม่ต้อง migrate type
MEMBERSHIP_PENDING = "pending"
MEMBERSHIP_APPROVED = "approved"
MEMBERSHIP_REJECTED = "rejected"
MEMBERSHIP_STATUSES: tuple[str, ...] = (
    MEMBERSHIP_PENDING,
    MEMBERSHIP_APPROVED,
    MEMBERSHIP_REJECTED,
)


class MembershipApplication(Base):
    """คำขอสมัครสมาชิกจากหน้าสาธารณะ — ยังไม่ใช่บัญชีที่เข้าระบบได้

    เก็บเฉพาะ password_hash (ไม่เคยเก็บรหัสผ่านดิบ) เพื่อให้ผู้สมัครใช้รหัสที่ตั้งไว้
    เข้าระบบได้ทันทีเมื่อผู้ดูแลอนุมัติ — ตอนอนุมัติจะย้าย hash ไปสร้างแถวใน users
    """
    __tablename__ = "membership_applications"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # ชื่อผู้ใช้ที่ขอไว้ — จะกลายเป็น users.line_user_id เมื่ออนุมัติ
    username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    full_name: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    organization_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id", ondelete="SET NULL"), nullable=True, index=True
    )
    # เก็บรหัสหน่วยงานที่กรอกมาด้วย เผื่อกรอกรหัสที่ยังไม่มีในระบบ
    organization_code: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    requested_role: Mapped[str] = mapped_column(String(32), default="it_support", nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(
        String(16), default=MEMBERSHIP_PENDING, nullable=False, index=True
    )
    reject_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_user_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    # เวลาที่ส่งแถวขึ้น Google Sheet สำเร็จ (None = ยังไม่ได้ส่ง/ส่งไม่ผ่าน)
    sheet_synced_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ---------------------------------------------------------------------------
# Knowledge Base (KB) — บทความวิธีแก้ไขเบื้องต้น ตาม TOR 1.5.5 / 5.6
# ---------------------------------------------------------------------------

class KBArticle(Base):
    __tablename__ = "kb_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kb_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    organization_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )  # None = บทความหลัก/ส่วนกลาง ทุกคนเห็น; มีค่า = เฉพาะรรนั้น
    device_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    symptom_tags: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list
    steps: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list of {order,text}
    is_published: Mapped[bool] = mapped_column(default=True, nullable=False)
    view_count: Mapped[int] = mapped_column(default=0, nullable=False)
    success_count: Mapped[int] = mapped_column(default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )


class KBSuggestion(Base):
    __tablename__ = "kb_suggestions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    source_ticket_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    device_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    symptom_text: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    solution: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    occurrence_count: Mapped[int] = mapped_column(default=1, nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="pending_review", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SelfServiceCase(Base):
    __tablename__ = "self_service_cases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    symptom: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    kb_article_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("kb_articles.id", ondelete="SET NULL"), nullable=True
    )
    ai_session_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resolved: Mapped[bool] = mapped_column(default=True, nullable=False)
    helpful_step: Mapped[Optional[int]] = mapped_column(nullable=True)
    time_saved_minutes: Mapped[Optional[int]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ─── Buildings (ระหว่าง organizations กับ rooms — TOR 3.1) ─────────────
class Building(Base):
    __tablename__ = "buildings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    organization_id: Mapped[int] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    code: Mapped[str] = mapped_column(String(10), nullable=False)
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    __table_args__ = (
        UniqueConstraint("organization_id", "code", name="uq_building_code"),
    )


# ─── Settings (key-value สำหรับระบบ — TOR 5.11) ────────────────────────
class Setting(Base):
    __tablename__ = "settings"

    key: Mapped[str] = mapped_column(String(50), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)  # JSON string
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    updated_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), onupdate=func.now(), nullable=True
    )


# ─── Notification Logs (ประวัติการแจ้งเตือน LINE — TOR 5.1) ────────────
class NotificationLog(Base):
    __tablename__ = "notification_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    pm_task_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    recipient_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    recipient_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    event_type: Mapped[str] = mapped_column(String(40), nullable=False)
    channel: Mapped[str] = mapped_column(String(10), default="line", nullable=False)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(10), default="sent", nullable=False)  # sent|failed|retrying
    retry_count: Mapped[int] = mapped_column(default=0, nullable=False)
    error_detail: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ─── Ticket Attachments (รูปแนบ ticket — TOR 5.1) ─────────────────────
class TicketAttachment(Base):
    __tablename__ = "ticket_attachments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    file_url: Mapped[str] = mapped_column(String(512), nullable=False)
    file_size: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    mime_type: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    phase: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)  # before | after
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ─── Ticket Comments (ความเห็นใน ticket — TOR 5.7) ────────────────────
class TicketComment(Base):
    __tablename__ = "ticket_comments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ticket_id: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    author_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    author_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    author_role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    note: Mapped[str] = mapped_column(Text, nullable=False)
    is_internal: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ── Chatbot runtime tables (สร้างผ่าน create_all ให้ตรงกับ raw SQL ใน chat_session/helpers) ──

class LineSession(Base):
    __tablename__ = "line_sessions"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    data: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class LineReportLink(Base):
    """Short-lived, single-use bridge from a verified LINE chat to the public QR form."""
    __tablename__ = "line_report_links"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ticket_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class ChatbotLog(Base):
    __tablename__ = "chatbot_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    ai_response: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    intent: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    resolved: Mapped[bool] = mapped_column(default=False, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class LineServiceRating(Base):
    """Customer ratings from LINE, separate bot quality from completed ticket service."""
    __tablename__ = "line_service_ratings"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    line_user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    target: Mapped[str] = mapped_column(String(16), nullable=False, index=True)  # bot | staff
    ticket_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    score: Mapped[int] = mapped_column(Integer, nullable=False)
    resolved: Mapped[Optional[bool]] = mapped_column(nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class ChatbotKnowledgeEntry(Base):
    """Reviewed, exact-match LINE answers managed by the top-level administrator."""
    __tablename__ = "chatbot_knowledge_entries"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    question: Mapped[str] = mapped_column(String(500), nullable=False)
    answer: Mapped[str] = mapped_column(Text, nullable=False)
    aliases: Mapped[str] = mapped_column(Text, nullable=False, default="[]")
    source_label: Mapped[Optional[str]] = mapped_column(String(160), nullable=True)
    source_url: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    is_published: Mapped[bool] = mapped_column(default=False, nullable=False)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class ChatbotPromptSetting(Base):
    """Optional runtime guidance; immutable safety policy remains in application code."""
    __tablename__ = "chatbot_prompt_settings"

    task: Mapped[str] = mapped_column(String(40), primary_key=True)
    guidance: Mapped[str] = mapped_column(Text, nullable=False, default="")
    enabled: Mapped[bool] = mapped_column(default=False, nullable=False)
    updated_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class SalesLead(Base):
    __tablename__ = "sales_leads"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    phone: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    interest: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    products: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    source: Mapped[str] = mapped_column(String(32), default="LINE", nullable=False)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="new", nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class CustomerSignupInvite(Base):
    """One-time opaque link from a LINE conversation to the customer form."""
    __tablename__ = "customer_signup_invites"

    token_hash: Mapped[str] = mapped_column(String(64), primary_key=True)
    line_user_id: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    interest: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    products: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    consumed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class DataImportMarker(Base):
    """Records a one-time production data import without relying on local secrets."""
    __tablename__ = "data_import_markers"

    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    applied_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SalesRecord(Base):
    """Staff-managed deal or payment enquiry; never stores card/payment credentials."""
    __tablename__ = "sales_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    lead_id: Mapped[int] = mapped_column(
        ForeignKey("sales_leads.id", ondelete="RESTRICT"), nullable=False, index=True
    )
    kind: Mapped[str] = mapped_column(String(24), nullable=False, index=True)
    product: Mapped[str] = mapped_column(String(255), nullable=False)
    quantity: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    amount_thb: Mapped[Optional[Decimal]] = mapped_column(Numeric(12, 2), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    note: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_by: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), onupdate=func.now())


class ChatbotProfile(Base):
    __tablename__ = "chatbot_profiles"

    user_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    profile: Mapped[dict] = mapped_column(JSONB, default=dict, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )


class ChatbotFAQ(Base):
    """คำถามที่เคยพบ เพื่อเก็บสถิติและยึดคำตอบมาตรฐานสำหรับคำถามซ้ำ"""

    __tablename__ = "chatbot_faqs"

    question_key: Mapped[str] = mapped_column(String(64), primary_key=True)
    normalized_question: Mapped[str] = mapped_column(Text, nullable=False)
    sample_question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    intent: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    hit_count: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_seen: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


# ─── Audit Log (Blueprint §32 / §40) ──────────────────────────────────
class AuditLog(Base):
    """ประวัติการกระทำสำคัญ — Login, เปลี่ยนสิทธิ์, สร้าง/แก้ Asset, Assign งาน,
    เปลี่ยน Status, ปิดงาน, แก้ KB และ System Settings (§40)
    """

    __tablename__ = "audit_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True, index=True)
    user_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    user_role: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    action: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    entity_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    entity_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    old_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    new_value: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON string
    ip_address: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    user_agent: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class DeletedRecord(Base):
    """Recoverable snapshot for explicitly deleted devices and tickets."""
    __tablename__ = "deleted_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entity_type: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    entity_id: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    organization_id: Mapped[int] = mapped_column(Integer, nullable=False, index=True)
    payload: Mapped[str] = mapped_column(Text, nullable=False)
    deleted_by: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    deleted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    restored_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


# ─── Preventive Maintenance (Blueprint §32 / §38) ─────────────────────
class PMPlan(Base):
    """แผนบำรุงรักษาเชิงป้องกัน — ประเภทอุปกรณ์ + รอบ (วัน) + checklist"""

    __tablename__ = "pm_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    device_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    interval_days: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    checklist: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PMTask(Base):
    """งาน PM รายครั้ง — ผูกอุปกรณ์ + ผลตรวจ + ticket ที่สร้างอัตโนมัติเมื่อไม่ผ่าน"""

    __tablename__ = "pm_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    plan_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pm_plans.id", ondelete="SET NULL"), nullable=True, index=True
    )
    device_id: Mapped[Optional[str]] = mapped_column(
        String(64), ForeignKey("devices.device_id", ondelete="CASCADE"), nullable=True, index=True
    )
    organization_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    due_date: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, index=True
    )
    # pending | overdue | done | skipped
    status: Mapped[str] = mapped_column(String(16), default="pending", nullable=False, index=True)
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list ผลแต่ละข้อ
    photos: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list URL
    done_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_due: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ticket_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True, index=True)
    skip_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


# ─── PM Rule Engine flags (Blueprint §38) ─────────────────────────────
class DeviceHealthFlag(Base):
    """ผลจาก PM Rule Engine (§38) — REPEATED_FAILURE / WARRANTY_EXPIRING /
    REPLACEMENT_CANDIDATE

    หนึ่งอุปกรณ์มี flag ของ rule เดียวกันที่ ``status='open'`` ได้ครั้งเดียว
    (pm_rules._has_open_flag ใช้เงื่อนไขนี้กันแจ้งซ้ำ)
    """

    __tablename__ = "device_health_flags"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    device_id: Mapped[str] = mapped_column(
        String(64), ForeignKey("devices.device_id", ondelete="CASCADE"),
        nullable=False, index=True
    )
    organization_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    # REPEATED_FAILURE | WARRANTY_EXPIRING | REPLACEMENT_CANDIDATE
    rule_code: Mapped[str] = mapped_column(String(32), nullable=False, index=True)
    # info | warning | critical
    severity: Mapped[str] = mapped_column(String(16), default="warning", nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    detail: Mapped[Optional[dict]] = mapped_column(JSONB, nullable=True)
    # open | acknowledged | resolved
    status: Mapped[str] = mapped_column(String(16), default="open", nullable=False, index=True)
    acknowledged_by: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    resolved_at: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False, index=True
    )


class LineWebhookEvent(Base):
    """Idempotency record for LINE webhook retries."""

    __tablename__ = "line_webhook_events"

    event_id: Mapped[str] = mapped_column(String(128), primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
