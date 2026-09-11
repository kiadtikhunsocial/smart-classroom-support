"""ล้างข้อมูลทดสอบที่เกิดจากการทดสอบ (logs/sessions/profiles) — ไม่แตะ ticket จริง"""
from app.models import SessionLocal
from sqlalchemy import text

PAT = r'^(Ue2e|Ureal|Uend|Udiag|Uhack|Ugem|Uok|U-test|U-probe|smoke|t[0-9]|f[0-9])'
db = SessionLocal()
try:
    for tbl, col in [("chatbot_logs", "user_id"), ("line_sessions", "user_id"),
                     ("chatbot_profiles", "user_id")]:
        n = db.execute(text(f"SELECT COUNT(*) FROM {tbl} WHERE {col} ~ :p"), {"p": PAT}).scalar()
        db.execute(text(f"DELETE FROM {tbl} WHERE {col} ~ :p"), {"p": PAT})
        print(f"  ลบ {tbl}: {n} แถว")
    n = db.execute(text("SELECT COUNT(*) FROM line_webhook_events WHERE event_id LIKE 'evt-test%' "
                        "OR event_id LIKE 'e-h%' OR event_id LIKE 'ev-diag%' OR event_id LIKE 'e-%'")).scalar()
    db.execute(text("DELETE FROM line_webhook_events WHERE event_id LIKE 'evt-test%' "
                    "OR event_id LIKE 'e-h%' OR event_id LIKE 'ev-diag%' OR event_id LIKE 'e-%'"))
    print(f"  ลบ line_webhook_events: {n} แถว")
    db.commit()
    print("\nเหลือในระบบ:")
    print("  chatbot_logs:", db.execute(text("SELECT COUNT(*) FROM chatbot_logs")).scalar())
    print("  line_sessions:", db.execute(text("SELECT COUNT(*) FROM line_sessions")).scalar())
    print("  repair_tickets:", db.execute(text("SELECT COUNT(*) FROM repair_tickets")).scalar())
finally:
    db.close()
