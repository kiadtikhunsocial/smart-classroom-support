"""เก็บกวาด ticket ที่เกิดจากการทดสอบ + คืนสถานะ ticket เดิม"""
from app.models import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    rows = db.execute(text("SELECT ticket_id, reporter_name, title FROM repair_tickets "
                           "WHERE reporter_name ILIKE 'ทดสอบ%' OR reporter_name ILIKE 'x%' "
                           "OR title ILIKE '%ทดสอบ%'")).fetchall()
    for r in rows:
        db.execute(text("DELETE FROM ticket_updates WHERE ticket_id IN "
                        "(SELECT id FROM repair_tickets WHERE ticket_id=:t)"), {"t": r[0]})
        db.execute(text("DELETE FROM repair_tickets WHERE ticket_id=:t"), {"t": r[0]})
        print("  ลบ:", r[0], "|", r[1], "|", str(r[2])[:40])
    db.commit()

    # คืนสถานะ ticket เดิมที่ถูกใช้ทดสอบ
    db.execute(text("UPDATE repair_tickets SET status='new', assigned_to=NULL WHERE ticket_id='TK-202609-0003'"))
    db.commit()

    print("\nเหลือ tickets:", db.execute(text("SELECT COUNT(*) FROM repair_tickets")).scalar())
    for r in db.execute(text("SELECT ticket_id, status, reporter_name FROM repair_tickets ORDER BY id")).fetchall():
        print("   ", r[0], "|", r[1], "|", r[2])
finally:
    db.close()
