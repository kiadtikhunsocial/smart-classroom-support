# ── แผนที่ไฟล์ ──────────────────────────────────────────────
# หน้าที่      : ส่งงานซ่อมให้ช่าง (คนว่างได้ทันที, ทุกคนยุ่ง = รอคิว) + ตัวกวาดงานค้าง
# ถูกเรียกจาก  : main (สร้าง/อัปเดต Ticket, /api/dispatch/*), chatbot_core
# เชื่อมต่อไป  : Supabase (users, repair_tickets), line_bot (แจ้งช่างทาง LINE)
# env ที่อ่าน  : AUTO_ASSIGN_ENABLED, DISPATCH_OFFER_MINUTES, DISPATCH_FREE_MAX_ACTIVE, DISPATCH_SWEEP_DISABLED, DISPATCH_TIMEOUT_COOLDOWN_MINUTES, STAFF_APP_URL
# ภาพรวมระบบ  : docs/SYSTEM_MAP.md
# ─────────────────────────────────────────────────────────
"""dispatch.py — ระบบส่งงาน (v2: ส่งให้คนว่าง / คนยุ่งแค่แจ้งเตือน / งานค้างรอคนว่าง)

ใบงานใหม่:
  - มีช่างที่ "ว่าง" (ไม่มีงานที่กำลังทำ: assigned/in_progress) → มอบงานให้คนที่ว่างที่สุดทันที
    (สถานะ assigned) + แจ้ง LINE/ป๊อปอัป ช่างกด "รับงาน" หรือ "ส่งต่อ" ได้
    ไม่ตอบภายใน DISPATCH_OFFER_MINUTES นาที → ส่งให้คนว่างคนถัดไป
  - ทุกคนยุ่ง → ใบงานอยู่ในคิว "งานค้าง" (status new) + แจ้งเตือนช่างทุกคนแบบไม่บังคับ
    ใครสะดวกกดรับเองได้ ไม่รับก็ไม่เป็นไร
  - ช่างคนไหนเคลียร์งานจนว่าง → sweep หยิบงานค้างที่เก่าสุดมอบให้ทันที

"ว่าง" = งาน assigned/in_progress ไม่เกิน DISPATCH_FREE_MAX_ACTIVE (ค่าเริ่มต้น 0)
งานที่รออะไหล่/รอผู้ใช้ ไม่นับว่ายุ่ง เพราะช่างไม่ได้ลงมือทำอยู่

กติกาเลือกช่างในกลุ่มที่ว่าง:
  1) งานที่กำลังทำน้อยสุด  2) งานค้างทั้งหมดน้อยสุด  3) วันนี้ปิดงานน้อยสุด  4) ว่างมานานสุด  5) id น้อยสุด
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
# งานที่ช่าง "กำลังทำอยู่จริง" — ใช้ตัดสินว่าว่างหรือยุ่ง (รออะไหล่/รอผู้ใช้ ไม่นับ)
ACTIVE_STATUSES = ("assigned", "in_progress")
BACKLOG_DAYS = 30  # งานค้างเก่ากว่านี้ไม่ถูกมอบอัตโนมัติ ให้แอดมินตัดสินเอง
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


def free_max_active() -> int:
    try:
        return max(0, int(os.environ.get("DISPATCH_FREE_MAX_ACTIVE", "0")))
    except ValueError:
        return 0


def _now() -> datetime:
    return datetime.now(timezone.utc)


def day_start_utc(now: Optional[datetime] = None) -> datetime:
    local = (now or _now()).astimezone(BANGKOK)
    return local.replace(hour=0, minute=0, second=0, microsecond=0).astimezone(timezone.utc)


def _lock(db: Session) -> None:
    db.execute(text("SELECT pg_advisory_xact_lock(:k)"), {"k": _LOCK_KEY})


def _offer_state(ticket: RepairTicket) -> dict:
    """offer_tried เก็บได้ 2 แบบ: list เดิม (คนที่เคยถูกเสนอรอบนี้) หรือ
    {"tried": [...], "declined": [...]} — declined = คนที่กด "ส่งต่อ" เอง ระบบไม่ส่งใบนี้ให้อีก"""
    try:
        raw = json.loads(ticket.offer_tried or "[]")
    except (ValueError, TypeError):
        raw = []
    if isinstance(raw, dict):
        return {"tried": [int(x) for x in raw.get("tried", [])],
                "declined": [int(x) for x in raw.get("declined", [])],
                "timeouts": {str(k): str(v) for k, v in (raw.get("timeouts") or {}).items()}}
    return {"tried": [int(x) for x in raw], "declined": [], "timeouts": {}}


def _save_offer_state(ticket: RepairTicket, tried: list[int], declined: list[int],
                      timeouts: Optional[dict] = None) -> None:
    ticket.offer_tried = json.dumps({"tried": tried, "declined": declined, "timeouts": timeouts or {}})


def timeout_cooldown_minutes() -> int:
    """ช่างที่ไม่ตอบรับทันเวลา จะไม่ถูกเด้งงานซ้ำจนกว่าจะพ้นช่วงนี้ หรือกลับมาเปิดแอป
    (กัน LINE เด้งทุก 5 นาทีทั้งคืน ถ้าช่างลืมปิด "พร้อมรับงาน")"""
    try:
        return max(1, int(os.environ.get("DISPATCH_TIMEOUT_COOLDOWN_MINUTES", "60")))
    except ValueError:
        return 60


def _cooling_ids(db: Session, timeouts: dict, now: datetime) -> set[int]:
    """uid ที่หมดเวลาตอบไม่นานนี้ และยังไม่ได้เปิดแอปอีกเลยหลังจากนั้น"""
    recent: dict[int, datetime] = {}
    for k, v in (timeouts or {}).items():
        try:
            at = datetime.fromisoformat(v)
        except ValueError:
            continue
        if at.tzinfo is None:
            at = at.replace(tzinfo=timezone.utc)
        if at > now - timedelta(minutes=timeout_cooldown_minutes()):
            recent[int(k)] = max(at, recent.get(int(k), at))
    if not recent:
        return set()
    seen = dict(db.execute(select(User.id, User.last_seen_at).where(User.id.in_(list(recent)))).all())
    return {uid for uid, at in recent.items() if not (seen.get(uid) and seen[uid] > at)}


def _tried(ticket: RepairTicket) -> list[int]:
    s = _offer_state(ticket)
    return sorted(set(s["tried"]) | set(s["declined"]))


# ─── ภาระงาน ─────────────────────────────────────────────────────────

def staff_load(db: Session, user_ids: Iterable[int], now: Optional[datetime] = None) -> dict[int, dict]:
    """{user_id: {open, done_today, last_assigned_at}} — ใช้ทั้งตอนเลือกช่างและหน้าสรุปแอดมิน"""
    ids = list(user_ids)
    out = {uid: {"open": 0, "active": 0, "done_today": 0, "last_assigned_at": None} for uid in ids}
    if not ids:
        return out
    for uid, n in db.execute(
        select(RepairTicket.assigned_user_id, func.count())
        .where(RepairTicket.assigned_user_id.in_(ids), RepairTicket.status.in_(ACTIVE_STATUSES))
        .group_by(RepairTicket.assigned_user_id)
    ):
        out[uid]["active"] = n
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


def is_free(load: dict) -> bool:
    return load["active"] <= free_max_active()


def pick_staff(db: Session, org_id: Optional[int], exclude_ids: Iterable[int] = ()) -> Optional[User]:
    """ช่างที่ว่างที่สุด — คืน None ถ้าทุกคนยุ่ง (ไม่มอบงานให้คนที่กำลังทำงานอยู่)"""
    skip = set(exclude_ids)
    staff = [u for u in eligible_staff(db, org_id) if u.id not in skip]
    if not staff:
        return None
    load = staff_load(db, [u.id for u in staff])
    staff = [u for u in staff if is_free(load[u.id])]
    if not staff:
        return None
    oldest = datetime.min.replace(tzinfo=timezone.utc)

    def rank(u: User):
        s = load[u.id]
        return (s["active"], s["open"], s["done_today"], s["last_assigned_at"] or oldest, u.id)

    return min(staff, key=rank)


def ticket_org_id(db: Session, ticket: RepairTicket) -> Optional[int]:
    return ticket.organization_id or db.execute(
        select(Device.organization_id).where(Device.device_id == ticket.device_id)
    ).scalar_one_or_none()


# ─── เสนองาน ─────────────────────────────────────────────────────────

def _history(db: Session, ticket: RepairTicket, from_s: str, to_s: str, note: str) -> None:
    db.add(TicketUpdate(ticket=ticket, from_status=from_s, to_status=to_s, note=note,
                        author_name="ระบบส่งงาน", author_role="system"))


def offer_next(db: Session, ticket: RepairTicket, reason: str = "",
               declined_by: Optional[int] = None, timed_out_by: Optional[int] = None,
               now: Optional[datetime] = None, extra_exclude: Iterable[int] = ()) -> Optional[User]:
    """มอบใบงานให้ช่างที่ว่างคนถัดไป — ผู้เรียกต้องถือ lock และ commit เอง
    ไม่มีใครว่าง → ใบงานกลับเข้าคิว "งานค้าง" (new) รอ sweep มอบให้คนที่ว่างทีหลัง
    รอบที่กลับเข้าคิวจะล้างรายชื่อ "เคยเสนอแล้ว" (คนที่แค่ไม่ทันตอบได้ลุ้นใหม่)
    แต่จำคนที่กด "ส่งต่อ" เองไว้ ไม่ส่งใบเดิมให้ซ้ำ
    """
    now = now or _now()
    state = _offer_state(ticket)
    tried, declined, timeouts = state["tried"], state["declined"], state["timeouts"]
    if declined_by and declined_by not in declined:
        declined.append(declined_by)
    if timed_out_by:
        timeouts[str(timed_out_by)] = now.isoformat()
    if ticket.assigned_user_id and ticket.assigned_user_id not in tried:
        tried.append(ticket.assigned_user_id)
    exclude = set(tried) | set(declined) | set(extra_exclude) | _cooling_ids(db, timeouts, now)
    staff = pick_staff(db, ticket_org_id(db, ticket), exclude_ids=exclude)
    prev = ticket.status
    if staff is None:
        if prev == "assigned" and ticket.auto_assigned:
            ticket.status = "new"
            ticket.assigned_user_id = None
            ticket.assigned_to = None
            ticket.auto_assigned = False
            _history(db, ticket, prev, "new",
                     "ไม่มีช่างว่าง — เข้าคิวงานค้าง ระบบจะมอบให้คนที่ว่างก่อน" + (f" ({reason})" if reason else ""))
        _save_offer_state(ticket, [] if ticket.status == "new" else tried, declined, timeouts)
        return None
    tried.append(staff.id)
    _save_offer_state(ticket, tried, declined, timeouts)
    ticket.assigned_user_id = staff.id
    ticket.assigned_to = staff.line_display_name or staff.line_user_id
    ticket.assigned_at = _now()
    ticket.auto_assigned = True
    ticket.status = "assigned"
    note = f"ระบบมอบงานให้ {ticket.assigned_to} (ว่างอยู่)" + (f" ({reason})" if reason else "")
    _history(db, ticket, prev, "assigned", note)
    return staff


def _locked_ticket(db: Session, ticket_pk: int) -> Optional[RepairTicket]:
    return db.execute(
        select(RepairTicket).where(RepairTicket.id == ticket_pk).with_for_update()
        .execution_options(populate_existing=True)  # อ่านค่าหลังได้ lock แม้ session จะโหลดแถวนี้ไว้แล้ว
    ).scalar_one_or_none()


def dispatch_ticket(ticket_pk: int) -> Optional[int]:
    """ใบงานใหม่: มีคนว่าง → มอบให้ทันที / ทุกคนยุ่ง → เข้าคิวงานค้าง + แจ้งเตือนทั้งทีม
    ทำงานบน _POOL (session ของตัวเอง) คืน user id ที่ได้งาน"""
    with SessionLocal() as db:
        _lock(db)
        t = _locked_ticket(db, ticket_pk)
        if t is None or t.status != "new" or t.assigned_user_id or t.assigned_to:
            db.rollback()
            return None
        staff = offer_next(db, t)
        team: list[User] = []
        if staff is None:
            team = eligible_staff(db, ticket_org_id(db, t))
            _history(db, t, "new", "new",
                     "ทีมช่างไม่ว่างทั้งหมด — บันทึกเป็นงานค้าง และแจ้งเตือนช่างทุกคนแล้ว"
                     if team else "ไม่มีช่างที่พร้อมรับงาน — บันทึกเป็นงานค้าง รอแอดมินมอบหมาย")
        db.commit()
        if staff:
            push_offer(db, t, staff)
            return staff.id
        for u in team:
            push_backlog_alert(db, t, u)
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
    return offer_next(db, t, reason=f"{user.line_display_name or 'ช่าง'} ส่งต่อ", declined_by=user.id)


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
        timed_out: set[int] = set()
        for t in stale:
            if t.assigned_user_id:
                timed_out.add(t.assigned_user_id)
            staff = offer_next(db, t, reason=f"ไม่ตอบรับภายใน {offer_minutes()} นาที",
                               timed_out_by=t.assigned_user_id, now=now, extra_exclude=timed_out)
            changed += 1
            if staff:
                pushes.append((t.id, staff.id))
        waiting = db.execute(
            select(RepairTicket).where(
                RepairTicket.status == "new", RepairTicket.assigned_user_id.is_(None),
                or_(RepairTicket.assigned_to.is_(None), RepairTicket.assigned_to == ""),
                RepairTicket.created_at >= now - timedelta(days=BACKLOG_DAYS),
                *([RepairTicket.id.in_(only_ids)] if only_ids is not None else []),
            ).order_by(RepairTicket.created_at).limit(50).with_for_update()
        ).scalars().all()
        # คนที่เพิ่งไม่ตอบ (ใบไหนก็ตาม) ไม่ถูกเด้งงานค้างใบอื่นจนกว่าจะพ้นช่วงพัก/กลับมาเปิดแอป
        cooling = set(timed_out)
        for t in waiting:
            cooling |= _cooling_ids(db, _offer_state(t)["timeouts"], now)
        for t in waiting:
            staff = offer_next(db, t, now=now, extra_exclude=cooling)
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
        f"🔔 ระบบมอบงานซ่อมให้คุณ (คุณว่างอยู่)\n"
        f"เลขที่ {t.ticket_id}\n{t.title}\n"
        + (f"{place} · " if place else "") + f"อุปกรณ์ {t.device_id}\n"
        f"กดรับงานภายใน {offer_minutes()} นาที ถ้าไม่สะดวกกด \"ส่งต่อ\" ระบบจะส่งให้คนว่างคนถัดไป\n"
        # ?job= = แอปเจ้าหน้าที่ (ล็อกอินแล้วเปิดใบงาน + ปุ่มรับงาน); ?ticket= คือหน้าติดตามของลูกค้า
        f"{STAFF_APP_URL}/?job={t.ticket_id}"
    )


def backlog_message(db: Session, t: RepairTicket) -> str:
    org = db.get(Organization, ticket_org_id(db, t)) if ticket_org_id(db, t) else None
    place = (org.short_name or org.name) if org else ""
    return (
        f"📋 มีงานซ่อมใหม่เข้ามา (ทีมยังไม่ว่าง)\n"
        f"เลขที่ {t.ticket_id}\n{t.title}\n"
        + (f"{place} · " if place else "") + f"อุปกรณ์ {t.device_id}\n"
        f"ถ้าสะดวกกดรับได้เลย ไม่รับก็ไม่เป็นไร — ใครว่างก่อนระบบจะมอบงานให้อัตโนมัติ\n"
        f"{STAFF_APP_URL}/?job={t.ticket_id}"
    )


def push_backlog_alert(db: Session, t: RepairTicket, staff: User) -> bool:
    if not staff.line_push_id:
        return False
    try:
        from app.line_bot import send_line_push
        return bool(send_line_push(staff.line_push_id, backlog_message(db, t)))
    except Exception:
        logger.exception("dispatch backlog alert failed for ticket %s", t.ticket_id)
        return False


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


def kick() -> None:
    """มีช่างอาจว่างขึ้น (ปิดงาน/ยกเลิก/ส่งต่อ/เปิดรับงาน) → มอบงานค้างทันที ไม่ต้องรอรอบ 30 วินาที"""
    if enabled():
        run_in_background(sweep)


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
