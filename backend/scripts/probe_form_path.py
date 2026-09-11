"""ทดสอบ: หลังบอทให้ลิงก์ฟอร์มแล้ว ผู้ใช้พิมพ์ 'แจ้งซ่อม' ต่อ บอทสร้าง ticket ให้ได้ไหม"""
import warnings
warnings.filterwarnings("ignore")
from app.chatbot_core import handle_message
from app.chat_session import clear_session, get_session, save_session
from app.models import SessionLocal
from sqlalchemy import text

UID = "smoke-formpath"
clear_session(UID)

print("=== เส้นทาง: บอทให้ลิงก์ฟอร์ม แล้วผู้ใช้พิมพ์ 'แจ้งซ่อม' ===")
save_session(UID, {"phase": "new", "fields": {}})
for t in ["หน้าจอห้อง 201 ค้าง กดอะไรไม่ได้เลย เปิดใหม่ก็ไม่หาย", "แจ้งซ่อม", "สมหญิง", "0899998888", "ยืนยัน"]:
    try:
        r = handle_message(user_id=UID, text=t, reply_token="")
        print(f"  > {t[:34]:36} [{get_session(UID).get('phase')}] -> {(r or '')[:80].replace(chr(10),' ')}")
    except Exception as e:
        print(f"  > {t[:34]:36} -> ❌ {type(e).__name__}: {e}")

db = SessionLocal()
rows = db.execute(text("SELECT ticket_id, reporter_name FROM repair_tickets WHERE reporter_name='สมหญิง'")).fetchall()
print("  ticket ที่สร้าง:", [r[0] for r in rows])
for r in rows:
    db.execute(text("DELETE FROM ticket_updates WHERE ticket_id IN (SELECT id FROM repair_tickets WHERE ticket_id=:t)"), {"t": r[0]})
    db.execute(text("DELETE FROM repair_tickets WHERE ticket_id=:t"), {"t": r[0]})
db.commit(); db.close()
clear_session(UID)
