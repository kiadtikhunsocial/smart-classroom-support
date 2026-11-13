"""dispatch.py — ระบบส่งงานแบบ Grab

ใบงานใหม่ → ระบบเลือกช่างที่ว่างที่สุด → เสนองานให้ (สถานะ assigned) + ส่ง LINE ส่วนตัว
ช่างกด "รับงาน" (in_progress) หรือ "ข้าม" → ระบบเสนอคนถัดไป
ไม่ตอบภายใน DISPATCH_OFFER_MINUTES นาที → เสนอคนถัดไปเหมือนกด "ข้าม"
เสนอครบทุกคนแล้วไม่มีใครรับ → กลับเป็น "new" ให้แอดมินเห็นในหน้าสรุป (ไม่วนส่ง LINE ซ้ำทั้งคืน)

กติกาเลือกช่าง (ตายตัว ไม่ต้องตั้งค่า):
  1) งานค้างน้อยที่สุด  2) วันนี้ปิดงานไปน้อยที่สุด  3) ว่างมานานที่สุด  4) id น้อยสุด
ช่างที่มีสิทธิ์: it_support, ใช้งานอยู่, เปิด "พร้อมรับงาน", และดูแลโรงเรียนนั้น (หรือดูแลทุกโรงเรียน)

ทุกการเลือก/ย้ายงานอยู่ใต้ advisory lock ตัวเดียวของ Postgres — สองใบงานที่เข้ามาพร้อมกัน
จะไม่เห็น "ภาระงาน" ชุดเดียวกันแล้วไปตกที่คนเดียว
"""
from __future__ import annotations

import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from typing import Iterable, Optional

from sqlalchemy import func, or_, select, text
from sqlalchemy.orm import Session

from app.models import Device, Organization, RepairTicket, SessionLocal, TicketUpdate, User

logger = logging.getLogger(__name__)

OPEN_STATUSES = ("assigned", "in_progress", "pending", "waiting_parts", "waiting_user")
BANGKOK = timezone(timedelta(hours=7))
_LOCK_KEY = 7_420_001  # advisory lock ของระบบส่งงาน
STAFF_APP_URL = os.environ.get("STAFF_APP_URL", "https://iwasmart-service.vercel.app").rstrip("/")


def enabled() -> bool:
    return os.environ.get("AUTO_ASSIGN_ENABLED", "1").strip() not in ("0", "false", "no", "")


def offer_minutes() -> int:
    try:
        return max(1, int(os.environ.get("DISPATCH_OFFER_MINUTES", "5")))
    except ValueError:
        return 5


def _now() -> datetime:
    return datetime.now(timezone.utc)


def day_start_utc(now: Optional[datetime] = None) -> datetime:
    local = (now or _now()).astimezone(BANGKOK)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _lock(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})


def _tried(ticket: RepairTicket) -> list[int]:
    try:
        return [int(x) for x in json.loads(ticket.offer_tried or "[]")]
    except (ValueError, TypeError):
        return []


# ─── ภาระงาน ─────────────────────────────────────────────────────────

def staff_load(db: Session, user_ids: Iterable[int], now: Optional[datetime] = None) -> dict[int, dict]:
    """{user_id: {open, done_today, last_assigned_at}} — ใช้ทั้งตอนเลือกช่างและหน้าสรุปแอดมิน"""
    ids = list(user_ids)
    out = {uid: {"open": 0, "done_today": 0, "last_assigned_at": None} for uid in ids}
    if not ids:
        return out
    for uid, n in db.execute(
        select(RepairTicket.assigned_user_id, func.count())
        .where(RepairTicket.assigned_user_id.in_(ids), RepairTicket.status.in_(OPEN_STATUSES))
        .group_by(RepairTicket.assigned_user_id)
    ):
        out[uid]["open"] = n
    for uid, n in db.execute(
        select(RepairTicket.assigned_user_id, func.count())
        .where(RepairTicket.assigned_user_id.in_(ids), RepairTicket.resolved_at >= day_start_utc(now))
        .group_by(RepairTicket.assigned_user_id)
    ):
        out[uid]["done_today"] = n
    for uid, last in db.execute(
        select(RepairTicket.assigned_user_id, func.max(RepairTicket.assigned_at))
        .where(RepairTicket.assigned_user_id.in_(ids))
        .group_by(RepairTicket.assigned_user_id)
    ):
        out[uid]["last_assigned_at"] = last
    return out


REACH_MINUTES = 10  # "เปิดแอปอยู่" = หน้าเว็บถามงานเข้ามาภายใน 10 นาทีที่ผ่านมา


def reachable_cond(now: Optional[datetime] = None):
    """ติดต่อได้จริง (แบบคนขับ Grab ที่ออนไลน์): ผูก LINE แล้ว หรือเปิดหน้าเว็บอยู่
    บัญชีเก่าที่ไม่มีใครใช้ จึงไม่ถูกเสนองานแล้วปล่อยให้รอ 5 นาทีต่อคน"""
    since = (now or _now()) - timedelta(minutes=REACH_MINUTES)
    return or_(User.line_push_id.is_not(None), User.last_seen_at >= since)


def is_reachable(u: User, now: Optional[datetime] = None) -> bool:
    if u.line_push_id:
        return True
    return bool(u.last_seen_at and u.last_seen_at >= (now or _now()) - timedelta(minutes=REACH_MINUTES))


def eligible_staff(db: Session, org_id: Optional[int]) -> list[User]:
    conds = [User.role == "it_support", User.is_active.is_(True), User.on_duty.is_(True), reachable_cond()]
    if org_id is not None:
        conds.append(or_(User.organization_id.is_(None), User.organization_id == org_id))
    return list(db.execute(select(User).where(*conds)).scalars())


def pick_staff(db: Session, org_id: Optional[int], exclude_ids: Iterable[int] = ()) -> Optional[User]:
    skip = set(exclude_ids)
    staff = [u for u in eligible_staff(db, org_id) if u.id not in skip]
    if not staff:
        return None
    load = staff_load(db, [u.id for u in staff])
    oldest = datetime.min.replace(tzinfo=timezone.utc)

    def rank(u: User):
        s = load[u.id]
        return (s["open"], s["done_today"], s["last_assigned_at"] or oldest, u.id)

    return min(staff, key=rank)


def ticket_org_id(db: Session, ticket: RepairTicket) -> Optional[int]:
    return ticket.organization_id or db.execute(
        select(Device.organization_id).where(Device.device_id == ticket.device_id)
    ).scalar_one_or_none()


# ─── เสนองาน ─────────────────────────────────────────────────────────

def _history(db: Session, ticket: RepairTicket, from_s: str, to_s: str, note: str) -> None:
    db.add(TicketUpdate(ticket=ticket, from_status=from_s, to_status=to_s, note=note,
                        author_name="ระบบส่งงาน", author_role="system"))


def offer_next(db: Session, ticket: RepairTicket, reason: str = "") -> Optional[User]:
    """เสนอใบงานให้ช่างคนถัดไปที่ยังไม่เคยได้รับข้อเสนอ — ผู้เรียกต้องถือ lock และ commit เอง
    ไม่มีใครเหลือ → ใบงานกลับเป็น new (ไม่มีผู้รับผิดชอบ) แอดมินเห็นเป็น "ไม่มีใครรับ"
    """
    tried = _tried(ticket)
    if ticket.assigned_user_id and ticket.assigned_user_id not in tried:
        tried.append(ticket.assigned_user_id)
    staff = pick_staff(db, ticket_org_id(db, ticket), exclude_ids=tried)
    prev = ticket.status
    if staff is None:
        if prev == "assigned" and ticket.auto_assigned:
            ticket.status = "new"
            ticket.assigned_user_id = None
            ticket.assigned_to = None
            ticket.auto_assigned = False
            _history(db, ticket, prev, "new", "ไม่มีช่างรับงาน — รอแอดมินมอบหมาย" + (f" ({reason})" if reason else ""))
        ticket.offer_tried = json.dumps(tried)
        return None
    tried.append(staff.id)
    ticket.offer_tried = json.dumps(tried)
    ticket.assigned_user_id = staff.id
    ticket.assigned_to = staff.line_display_name or staff.line_user_id
    ticket.assigned_at = _now()
    ticket.auto_assigned = True
    ticket.status = "assigned"
    note = f"ระบบเสนองานให้ {ticket.assigned_to}" + (f" ({reason})" if reason else "")
    _history(db, ticket, prev, "assigned", note)
    return staff


def _locked_ticket(db: Session, ticket_pk: int) -> Optional[RepairTicket]:
    return db.execute(
        select(RepairTicket).where(RepairTicket.id == ticket_pk).with_for_update()
        .execution_options(populate_existing=True)  # อ่านค่าหลังได้ lock แม้ session จะโหลดแถวนี้ไว้แล้ว
    ).scalar_one_or_none()


def dispatch_ticket(ticket_pk: int) -> Optional[int]:
    """เสนอใบงานใหม่ให้ช่าง — ทำงานบน _POOL (session ของตัวเอง) คืน user id ที่ได้งาน"""
    with SessionLocal() as db:
        _lock(db)
        t = _locked_ticket(db, ticket_pk)
        if t is None or t.status != "new" or t.assigned_user_id or t.assigned_to:
            db.rollback()
            return None
        staff = offer_next(db, t)
        db.commit()
        if staff:
            push_offer(db, t, staff)
            return staff.id
        return None


class NotOffered(Exception):
    """งานนี้ไม่ได้รอให้ช่างคนนี้ตอบแล้ว (คนอื่นรับไป / หมดเวลา / แอดมินมอบหมายใหม่)"""


def decline(db: Session, ticket: RepairTicket, user: User) -> Optional[User]:
    """ช่างกด "ข้าม" — ใช้ใน request (ผู้เรียก commit แล้วค่อย push_offer)
    ตรวจเงื่อนไขอีกครั้งหลังได้ lock — ระหว่างนั้นอาจมีคนกดรับหรือ sweep ส่งต่อไปแล้ว"""
    _lock(db)
    t = _locked_ticket(db, ticket.id)
    if t is None or t.status != "assigned" or not t.auto_assigned or t.assigned_user_id != user.id:
        raise NotOffered()
    return offer_next(db, t, reason=f"{user.line_display_name or 'ช่าง'} ข้าม")


def sweep(now: Optional[datetime] = None, only_ids: Optional[list[int]] = None) -> int:
    """เสนอต่อเมื่อหมดเวลา และลองเสนอใบงาน new ที่ยังไม่มีคนรับ — คืนจำนวนใบที่เปลี่ยน
    only_ids: จำกัดเฉพาะใบงานเหล่านี้ (ใช้ในเทสต์ ไม่ให้ไปแตะข้อมูลอื่นในฐานข้อมูล)"""
    if not enabled():
        return 0
    now = now or _now()
    cutoff = now - timedelta(minutes=offer_minutes())
    pushes: list[tuple[int, int]] = []
    changed = 0
    with SessionLocal() as db:
        _lock(db)
        stale = db.execute(
            select(RepairTicket).where(
                RepairTicket.status == "assigned", RepairTicket.auto_assigned.is_(True),
                RepairTicket.assigned_at < cutoff,
                *([RepairTicket.id.in_(only_ids)] if only_ids is not None else []),
            ).order_by(RepairTicket.assigned_at).limit(50).with_for_update()
        ).scalars().all()
        for t in stale:
            staff = offer_next(db, t, reason=f"ไม่ตอบรับภายใน {offer_minutes()} นาที")
            changed += 1
            if staff:
                pushes.append((t.id, staff.id))
        waiting = db.execute(
            select(RepairTicket).where(
                RepairTicket.status == "new", RepairTicket.assigned_user_id.is_(None),
                or_(RepairTicket.assigned_to.is_(None), RepairTicket.assigned_to == ""),
                RepairTicket.created_at >= now - timedelta(days=3),
                *([RepairTicket.id.in_(only_ids)] if only_ids is not None else []),
            ).order_by(RepairTicket.created_at).limit(50).with_for_update()
        ).scalars().all()
        for t in waiting:
            staff = offer_next(db, t)
            if staff:
                changed += 1
                pushes.append((t.id, staff.id))
        db.commit()
        for tid, uid in pushes:
            t, u = db.get(RepairTicket, tid), db.get(User, uid)
            if t and u:
                push_offer(db, t, u)
    return changed


# ─── LINE ส่วนตัว ────────────────────────────────────────────────────

def offer_message(db: Session, t: RepairTicket) -> str:
    org = db.get(Organization, ticket_org_id(db, t)) if ticket_org_id(db, t) else None
    place = (org.short_name or org.name) if org else ""
    # ไม่ใส่เบอร์โทรผู้แจ้ง — ข้อความ LINE ถูกส่งต่อ/แคปหน้าจอได้ง่าย
    return (
        f"🔔 มีงานซ่อมใหม่สำหรับคุณ\n"
        f"เลขที่ {t.ticket_id}\n{t.title}\n"
        + (f"{place} · " if place else "") + f"อุปกรณ์ {t.device_id}\n"
        f"กดรับงานภายใน {offer_minutes()} นาที ไม่งั้นระบบจะส่งให้คนถัดไป\n"
        # ?job= = แอปเจ้าหน้าที่ (ล็อกอินแล้วเปิดใบงาน + ปุ่มรับงาน); ?ticket= คือหน้าติดตามของลูกค้า
        f"{STAFF_APP_URL}/?job={t.ticket_id}"
    )


def push_offer(db: Session, t: RepairTicket, staff: User) -> bool:
    if not staff.line_push_id:
        return False
    try:
        from app.line_bot import send_line_push
        return bool(send_line_push(staff.line_push_id, offer_message(db, t)))
    except Exception:
        logger.exception("dispatch push failed for ticket %s", t.ticket_id)
        return False


def line_push_configured() -> bool:
    from app.line_bot import LINE_TOKEN
    return bool(LINE_TOKEN)


# ─── คิวพื้นหลัง ──────────────────────────────────────────────────────

_POOL = ThreadPoolExecutor(max_workers=1, thread_name_prefix="dispatch")


def _safe(fn, *args):
    try:
        return fn(*args)
    except Exception:
        logger.exception("dispatch job failed")
        return None


def enqueue_dispatch(ticket_pk: int) -> None:
    """เรียกหลัง commit ใบงานใหม่ — คืนค่าทันที ไม่หน่วงหน้าแจ้งซ่อม"""
    if not enabled() or not ticket_pk:
        return
    try:
        _POOL.submit(_safe, dispatch_ticket, ticket_pk)
    except RuntimeError:
        pass  # pool ปิดแล้ว (process กำลังจบ) — sweep รอบหน้าจะหยิบใบนี้เอง


def run_in_background(fn, *args) -> None:
    try:
        _POOL.submit(_safe, fn, *args)
    except RuntimeError:
        pass


def flush(timeout: float = 10.0) -> None:
    """รอคิวให้ว่าง — ใช้ในเทสต์"""
    _POOL.submit(lambda: None).result(timeout=timeout)


_sweeper_started = False


def start_sweeper(interval_seconds: int = 30) -> None:
    global _sweeper_started
    if _sweeper_started or not enabled() or os.environ.get("DISPATCH_SWEEP_DISABLED") == "1":
        return
    _sweeper_started = True
    stop = threading.Event()

    def loop():
        while not stop.wait(interval_seconds):
            # ให้ทำบน _POOL ตัวเดียวกับงานเสนอ — เรียงลำดับกันเอง ไม่แย่ง lock
            run_in_background(sweep)

    threading.Thread(target=loop, name="dispatch-sweeper", daemon=True).start()
