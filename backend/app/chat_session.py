"""
chat_session.py — เก็บ state การสนทนา chatbot (multi-turn) ลงตาราง line_sessions
ใช้ SQLite/Postgres ตาม engine เดิม (ไม่ต้อง Redis แยกให้ยุ่ง)
"""
import json
from datetime import datetime

from app.models import SessionLocal


def get_session(user_id: str) -> dict:
    """ดึง session ของ user — คืน dict state (หรือ default ว่าง)"""
    db = SessionLocal()
    try:
        row = db.execute(
            __import__("sqlalchemy").text("SELECT data FROM line_sessions WHERE user_id=:u"),
            {"u": user_id},
        ).fetchone()
        if row and row[0]:
            val = row[0]
            # jsonb (Postgres) คืนเป็น dict แล้ว; SQLite/text เป็น str
            if isinstance(val, dict):
                return val
            return json.loads(val)
    except Exception:
        pass
    finally:
        db.close()
    return {}


def save_session(user_id: str, data: dict):
    """บันทึก/อัปเดต session ของ user"""
    db = SessionLocal()
    try:
        import sqlalchemy
        db.execute(
            sqlalchemy.text(
                "INSERT INTO line_sessions (user_id, data, updated_at) VALUES (:u, :d, :t) "
                "ON CONFLICT (user_id) DO UPDATE SET data=:d, updated_at=:t"
            ),
            {"u": user_id, "d": json.dumps(data, ensure_ascii=False), "t": datetime.now()},
        )
        db.commit()
    except Exception:
        pass
    finally:
        db.close()


def clear_session(user_id: str):
    """ล้าง session (จบการสนทนา)"""
    db = SessionLocal()
    try:
        import sqlalchemy
        db.execute(sqlalchemy.text("DELETE FROM line_sessions WHERE user_id=:u"), {"u": user_id})
        db.commit()
    except Exception:
        pass
    finally:
        db.close()
