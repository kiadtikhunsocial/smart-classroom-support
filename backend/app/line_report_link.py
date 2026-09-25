"""Single-use LINE-to-QR links. The browser never receives a LINE user ID.

Only the signed LINE webhook (or authenticated n8n forwarder) can issue a link.
The public form submits the opaque bearer token; PostgreSQL atomically consumes
it with the new ticket. A copied/expired link must not bind another ticket.
"""
from datetime import datetime, timedelta, timezone
import hashlib
import logging
import os
import secrets
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.line_bot import send_line_push
from app.models import LineReportLink, RepairTicket, SessionLocal

LINK_TTL = timedelta(minutes=30)
logger = logging.getLogger(__name__)


def _token_hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def issue_report_link(line_user_id: str) -> str | None:
    """Return a form URL or None if the bridge cannot be safely created."""
    if not line_user_id or len(line_user_id) > 128:
        return None
    base = os.environ.get("REPORT_FORM_URL", "http://localhost:5173/?publicreport=1")
    parts = urlsplit(base)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return None
    if os.environ.get("ENVIRONMENT", "").lower() in {"prod", "production"} and parts.scheme != "https":
        return None
    token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        db.add(LineReportLink(token_hash=_token_hash(token), line_user_id=line_user_id,
                              expires_at=now + LINK_TTL))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not issue LINE report link")
        return None
    finally:
        db.close()
    query = [(key, value) for key, value in parse_qsl(parts.query, keep_blank_values=True)
             if key not in {"line_link", "publicreport"}]
    query.append(("publicreport", "1"))
    # URL fragments are not sent in HTTP requests/referrers to Vercel or Render.
    # The public form reads and removes this fragment before submitting it.
    return urlunsplit((parts.scheme, parts.netloc, parts.path or "/",
                       urlencode(query), f"line_link={token}"))


def lock_report_link(db: Session, token: str) -> LineReportLink:
    """Lock and validate the bearer token in the ticket creation transaction."""
    if not token or len(token) > 128:
        raise ValueError("invalid")
    row = db.execute(select(LineReportLink).where(
        LineReportLink.token_hash == _token_hash(token)
    ).with_for_update()).scalar_one_or_none()
    now = datetime.now(timezone.utc)
    if not row or row.consumed_at or row.expires_at <= now:
        raise ValueError("expired_or_used")
    return row


def bind_report_link(row: LineReportLink, ticket: RepairTicket) -> None:
    ticket.line_user_id = row.line_user_id
    row.ticket_id = ticket.ticket_id
    row.consumed_at = datetime.now(timezone.utc)


def send_ticket_receipt(line_user_id: str, ticket_id: str) -> bool:
    """Best-effort push after commit; failed LINE delivery never loses a ticket."""
    try:
        return bool(send_line_push(
            line_user_id,
            f"รับแจ้งซ่อมเรียบร้อยแล้วค่ะ เลขใบงาน {ticket_id}\n"
            "ถามความคืบหน้าได้ในแชตนี้โดยพิมพ์ 'ติดตาม' หรือ 'รายละเอียดใบงาน' ค่ะ\n"
            "เมื่อเจ้าหน้าที่แจ้งว่าซ่อมเสร็จ ระบบจะเชิญให้ประเมินการบริการค่ะ",
        ))
    except Exception:
        logger.exception("Could not send LINE receipt for ticket %s", ticket_id)
        return False
