"""เก็บกวาด ticket ที่เกิดจากการทดสอบ + คืนสถานะใบที่ระบุ

ใช้:
    python cleanup_tickets.py                       # ลบใบทดสอบเท่านั้น
    python cleanup_tickets.py TK.SCHM01.26.0003-P   # ลบใบทดสอบ + คืนสถานะใบนี้เป็น new

เลขใบที่จะคืนสถานะรับจาก argv ไม่ hardcode อีกต่อไป — เดิมฝังเลขรูปแบบเก่า
(TK-202609-0003) ไว้ ซึ่งตอนนี้ไม่มีอยู่จริงแล้ว คำสั่ง UPDATE จึงเงียบ ๆ ไม่โดนแถวใด
และถ้าเผลอมีใบเลขนั้น ก็จะถูกรีเซ็ตสถานะโดยที่ผู้รันไม่ได้สั่ง
"""
import sys

from app.models import SessionLocal
from sqlalchemy import text

# เลขใบที่ขอคืนสถานะ (ถ้ามี) — ทำให้เป็นตัวพิมพ์ใหญ่ให้ตรงกับที่เก็บใน DB
reset_ids = [arg.strip().upper() for arg in sys.argv[1:] if arg.strip()]

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

    # คืนสถานะใบที่ผู้รันระบุมาเท่านั้น
    for ticket_no in reset_ids:
        result = db.execute(
            text("UPDATE repair_tickets SET status='new', assigned_to=NULL "
                 "WHERE ticket_id=:t"),
            {"t": ticket_no},
        )
        if result.rowcount:
            print("  คืนสถานะเป็น new:", ticket_no)
        else:
            print("  ไม่พบใบงาน:", ticket_no)
    if reset_ids:
        db.commit()

    print("\nเหลือ tickets:", db.execute(text("SELECT COUNT(*) FROM repair_tickets")).scalar())
    for r in db.execute(text("SELECT ticket_id, status, reporter_name FROM repair_tickets ORDER BY id")).fetchall():
        print("   ", r[0], "|", r[1], "|", r[2])
finally:
    db.close()