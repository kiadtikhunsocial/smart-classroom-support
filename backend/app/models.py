"""app/models.py — Database models for Smart Classroom Support System
SQLite (dev) / PostgreSQL (prod) — switch via DATABASE_URL env
"""
import os
from datetime import datetime, timezone
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
)
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

# ใช้ path สัมบูรณ์จากตำแหน่งไฟล์ models.py
# models.py อยู่ที่ backend/app/models.py -> ขึ้นไป 3 level ได้ project root
_base_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_db_path = os.path.join(_base_dir, "data", "smart_classroom.db")
DATABASE_URL = os.getenv("DATABASE_URL", f"postgresql+psycopg2://postgres:postgres@localhost:5432/smart_classroom{_db_path}")

engine = create_engine(
    DATABASE_URL,
    echo=False,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
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
    os.makedirs("data", exist_ok=True)
    Base.metadata.create_all(bind=engine)


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


class DeviceStatus(str):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DECOMMISSIONED = "decommissioned"


class TicketStatus(str):
    NEW = "new"
    ASSIGNED = "assigned"
    IN_PROGRESS = "in_progress"
    PENDING = "pending"
    RESOLVED = "resolved"
    CLOSED = "closed"
    CANCELLED = "cancelled"


class Priority(str):
    LOW = "low"
    NORMAL = "normal"
    HIGH = "high"
    CRITICAL = "critical"


# SAEnum definitions — create_type=False สำหรับ SQLite compatibility
device_type_enum = SAEnum(
    "Interactive Display", "Computer AIO", "Computer Notebook", "Computer Tablet",
    "Computer Desktop", "Router", "Access Point", "Switch", "Speaker", "Camera",
    "Visualizer", "Microphone", "UPS", "Printer", "Projector",
    "Software (Picaro)", "Software (Phonics Hero)", "Other",
    name="device_type_enum",
    create_type=False,
)

device_status_enum = SAEnum(
    "active", "inactive", "decommissioned",
    name="device_status_enum",
    create_type=False,
)

ticket_status_enum = SAEnum(
    "new", "assigned", "in_progress", "pending",
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
    device_type: Mapped[str] = mapped_column(
        device_type_enum, nullable=False, default=DeviceType.OTHER
    )
    brand: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    model: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    serial_number: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    firmware_version: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(
        device_status_enum, default=DeviceStatus.ACTIVE, nullable=False
    )
    qr_code_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    qr_token: Mapped[Optional[str]] = mapped_column(String(64), unique=True, nullable=True, index=True)
    warranty_until: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
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
    ADMIN = "admin"           # ผู้ดูแลระบบโรงเรียน — เห็นทุกอย่างในโรงเรียนตัวเอง
    TEACHER = "teacher"       # ครู — เห็นเฉพาะ ticket ที่ตัวเองสร้าง + อุปกรณ์ในโรงเรียน
    IT_SUPPORT = "it_support" # เจ้าหน้าที่ IT — เห็น ticket ทั้งหมดในโรงเรียน + จัดการได้
    STUDENT = "student"       # นักเรียน — เห็นอุปกรณ์ + สร้าง ticket + ดู ticket ที่ตัวเองสร้าง
    SUPER_ADMIN = "super_admin"  # เจ้าของบริษัท — เห็นทุกโรงเรียน + จัดการทุกอย่างได้


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
        SAEnum("admin", "teacher", "it_support", "student", "super_admin",
               name="user_role_enum", create_type=False),
        default=UserRole.TEACHER, nullable=False, index=True
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
# Knowledge Base (KB) — บทความวิธีแก้ไขเบื้องต้น ตาม TOR 1.5.5 / 5.6
# ---------------------------------------------------------------------------

class KBArticle(Base):
    __tablename__ = "kb_articles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    kb_id: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
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


# ---------------------------------------------------------------------------
# Preventive Maintenance (PM) — ตาม TOR 1.5.10 / 5.9
# ---------------------------------------------------------------------------

class PMPlan(Base):
    __tablename__ = "pm_plans"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    device_type: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    interval_days: Mapped[int] = mapped_column(default=90, nullable=False)
    checklist: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list
    is_active: Mapped[bool] = mapped_column(default=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class PMTask(Base):
    __tablename__ = "pm_tasks"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    task_no: Mapped[str] = mapped_column(String(32), unique=True, nullable=False, index=True)
    plan_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("pm_plans.id", ondelete="SET NULL"), nullable=True
    )
    device_id: Mapped[Optional[str]] = mapped_column(String(64), nullable=True, index=True)
    organization_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("organizations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    due_date: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(
        String(32), default="pending", nullable=False, index=True
    )  # pending | done | skipped | overdue
    result: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON checklist result
    photos: Mapped[Optional[str]] = mapped_column(Text, nullable=True)  # JSON list of URLs
    done_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    next_due: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    ticket_id: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    skip_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
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


