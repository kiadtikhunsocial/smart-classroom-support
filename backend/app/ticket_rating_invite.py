"""Invite the original LINE reporter to rate completed staff work once per ticket.

Never infer a recipient from a phone/name: only tickets created by the verified
LINE conversation have line_user_id. Delivery failure does not fail the repair.
"""
import logging
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.line_bot import send_line_push
from app.models import RepairTicket

logger = logging.getLogger(__name__)


def invite_staff_rating(db: Session, ticket: RepairTicket) -> bool:
    if ticket.status not in {"resolved", "closed"} or not ticket.line_user_id or ticket.rating_invited_at:
        return False
    message = (f"เจ้าหน้าที่แจ้งว่างานซ่อม {ticket.ticket_id} เสร็จแล้วค่ะ กรุณาตรวจสอบผลก่อน\n"
               "หากเรียบร้อย ช่วยประเมินการดูแลของเจ้าหน้าที่ 1–5 คะแนน โดยพิมพ์\n"
               f"ประเมินเจ้าหน้าที่ {ticket.ticket_id} 5\n"
               "(เปลี่ยนเลข 5 เป็นคะแนนที่ต้องการได้ค่ะ)\n"
               "ถ้าปัญหายังไม่เรียบร้อย พิมพ์ 'ติดต่อเจ้าหน้าที่' เพื่อดูช่องทางติดต่อให้ทีมตรวจต่อค่ะ")
    try:
        if not send_line_push(ticket.line_user_id, message):
            logger.warning("Could not deliver rating invitation for ticket %s", ticket.ticket_id)
            return False
        ticket.rating_invited_at = datetime.now(timezone.utc)
        db.commit()
        return True
    except Exception:
        db.rollback()
        logger.exception("Could not save rating invitation for ticket %s", ticket.ticket_id)
        return False
