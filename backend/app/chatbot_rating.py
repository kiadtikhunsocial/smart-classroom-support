"""Persist explicit LINE ratings; no model inference and no cross-customer ticket rating."""
import re

from sqlalchemy import select

from app.models import LineServiceRating, RepairTicket, SessionLocal

_BOT = re.compile(r"^ประเมิน(?:บอท|แชทบอท)\s*([1-5])(?:\s+(แก้ได้|ยังไม่หาย))?$", re.IGNORECASE)
_STAFF = re.compile(r"^ประเมินเจ้าหน้าที่\s+(\S{5,32})\s+([1-5])$", re.IGNORECASE)


def is_rating_message(message: str) -> bool:
    return (message or "").strip().startswith(("ประเมินบอท", "ประเมินแชทบอท", "ประเมินเจ้าหน้าที่"))


def record_rating(user_id: str, message: str, phone: str | None, allowed_ticket_id: str | None = None) -> str:
    text = (message or "").strip()
    bot, staff = _BOT.fullmatch(text), _STAFF.fullmatch(text)
    if not user_id or not (bot or staff):
        return "รูปแบบคะแนน: ประเมินบอท 1–5 แก้ได้/ยังไม่หาย หรือ ประเมินเจ้าหน้าที่ <เลข Ticket> 1–5 ค่ะ"
    target = "bot" if bot else "staff"
    score = int((bot or staff).group(1 if bot else 2))
    resolved = (bot.group(2) == "แก้ได้") if bot and bot.group(2) else None
    ticket_no = staff.group(1).upper() if staff else None
    db = SessionLocal()
    try:
        if target == "staff":
            ticket = db.execute(select(RepairTicket).where(RepairTicket.ticket_id == ticket_no)).scalar_one_or_none()
            # Require both the LINE ticket recorded by our repair flow and the
            # reporter phone. A phone alone is not an identity proof.
            if (allowed_ticket_id != ticket_no or not phone or not ticket
                    or ticket.reporter_phone != phone or ticket.status not in {"resolved", "closed"}):
                return "ยังประเมินงานนี้ไม่ได้ค่ะ ตรวจเลข Ticket และเบอร์ที่ใช้แจ้งงาน หรือรอให้งานซ่อมเสร็จก่อนนะคะ"
        old = db.execute(select(LineServiceRating).where(
            LineServiceRating.line_user_id == user_id, LineServiceRating.target == target,
            LineServiceRating.ticket_id == ticket_no if ticket_no else LineServiceRating.ticket_id.is_(None),
        )).scalar_one_or_none()
        if old:
            old.score = score
            if bot:
                old.resolved = resolved
        else:
            db.add(LineServiceRating(line_user_id=user_id[:128], target=target,
                                     ticket_id=ticket_no, score=score, resolved=resolved))
        db.commit()
        return f"ขอบคุณที่ประเมิน{'แชทบอท' if target == 'bot' else 'เจ้าหน้าที่'} {score}/5 ค่ะ ทีมงานจะนำไปปรับปรุงบริการ"
    finally:
        db.close()
