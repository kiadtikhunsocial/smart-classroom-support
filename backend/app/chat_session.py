"""
chat_session.py — เก็บ state การสนทนา chatbot (multi-turn) ลงตาราง line_sessions
ใช้ SQLite/Postgres ตาม engine เดิม (ไม่ต้อง Redis แยกให้ยุ่ง)
"""
import json
import logging
from datetime import datetime, timezone

from app.models import LineSession, SessionLocal


logger = logging.getLogger(__name__)


def get_session(user_id: str) -> dict:
    """ดึง session ของ user — คืน dict state (หรือ default ว่าง)"""
    db = SessionLocal()
    try:
        row = db.get(LineSession, user_id)
        if not row or not row.data:
            return {}
        val = row.data
        # JSONB (Postgres) คืนเป็น dict แล้ว; legacy SQLite/text อาจเป็น str
        if isinstance(val, dict):
            return dict(val)
        parsed = json.loads(val)
        return parsed if isinstance(parsed, dict) else {}
    except (TypeError, ValueError, json.JSONDecodeError) as exc:
        logger.warning("Invalid chatbot session for user %s: %s", user_id, exc)
    except Exception:
        logger.exception("Could not read chatbot session for user %s", user_id)
    finally:
        db.close()
    return {}


def save_session(user_id: str, data: dict) -> bool:
    """บันทึก/อัปเดต session ของ user"""
    db = SessionLocal()
    try:
        row = db.get(LineSession, user_id)
        if row:
            row.data = dict(data or {})
            row.updated_at = datetime.now(timezone.utc)
        else:
            db.add(LineSession(
                user_id=user_id,
                data=dict(data or {}),
                updated_at=datetime.now(timezone.utc),
            ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not save chatbot session for user %s", user_id)
        return False
    finally:
        db.close()
    return True


def clear_session(user_id: str) -> bool:
    """ล้าง session (จบการสนทนา)"""
    db = SessionLocal()
    try:
        row = db.get(LineSession, user_id)
        if row:
            db.delete(row)
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not clear chatbot session for user %s", user_id)
        return False
    finally:
        db.close()
    return True
