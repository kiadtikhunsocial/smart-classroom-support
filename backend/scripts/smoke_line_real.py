"""ทดสอบรอบสุดท้าย: flow จริงที่ผู้ใช้ LINE ทำ (รวมเคสที่เคยพังใน logs จริง)"""
import warnings
warnings.filterwarnings("ignore")
from app.chatbot_core import handle_message
from app.chat_session import clear_session, get_session, save_session
from app.models import SessionLocal
from sqlalchemy import text

db = SessionLocal()


def run(uid, msgs, label):
    clear_session(uid)
    print(f"\n=== {label} ===")
    for m in msgs:
        try:
            r = handle_message(user_id=uid, text=m, reply_token="")
            print(f"  > {m[:40]:42} [{get_session(uid).get('phase')}] {(r or '')[:72].replace(chr(10),' ')}")
        except Exception as e:
            print(f"  > {m[:40]:42} ❌ {type(e).__name__}: {e}")


# 1) เคสจริงจาก log: ถามสินค้า
run("t1", ["สวัสดี", "สินค้า"], "เคสจริง: ถามสินค้า")

# 2) เคสจริงจาก log: ขอแจ้งซ่อม แล้วแจ้งอุปกรณ์
run("t2", ["ขอแจ้งซ่อม", "จอ Interactive Display ห้อง 2208"], "เคสจริง: ขอแจ้งซ่อม")

# 3) เคสจริง: อาการที่ไม่มี keyword เดิม
run("t3", ["หน้าจอห้อง 201 ค้าง กดอะไรไม่ได้เลย เปิดใหม่ก็ไม่หาย"], "เคสจริง: อาการไม่มี keyword")

# 4) flow เต็มจนได้ ticket
clear_session("t4")
print("\n=== flow เต็ม: แจ้งซ่อม → ได้เลข ticket ===")
for m in ["แจ้งซ่อม", "สมหญิง ใจดี", "0899998888", "TEST1-00001", "ยืนยัน"]:
    try:
        r = handle_message(user_id="t4", text=m, reply_token="")
        print(f"  > {m:16} [{get_session('t4').get('phase')}] {(r or '')[:90].replace(chr(10),' ')}")
    except Exception as e:
        print(f"  > {m:16} ❌ {type(e).__name__}: {e}")

rows = db.execute(text("SELECT ticket_id FROM repair_tickets WHERE reporter_name='สมหญิง ใจดี'")).fetchall()
print("  ticket:", [r[0] for r in rows])
for r in rows:
    db.execute(text("DELETE FROM ticket_updates WHERE ticket_id IN (SELECT id FROM repair_tickets WHERE ticket_id=:t)"), {"t": r[0]})
    db.execute(text("DELETE FROM repair_tickets WHERE ticket_id=:t"), {"t": r[0]})
db.commit()

# 5) เคสที่เคยพัง: ระหว่างวินิจฉัย แล้วถามสินค้า
run("t5", ["จอไม่มีภาพ", "สินค้า"], "เคสจริง: ระหว่างซ่อมเปลี่ยนไปถามสินค้า")

# 6) กันวังวน: ตอบอุปกรณ์ผิด 3 ครั้ง
run("t6", ["แจ้งซ่อม", "สมชาย", "0811112222", "ไม่รู้", "ไม่ทราบ", "ไม่มี"],
    "กันวังวน: ผู้ใช้ไม่รู้รหัสอุปกรณ์")

for u in ["t1", "t2", "t3", "t4", "t5", "t6"]:
    clear_session(u)
db.close()
