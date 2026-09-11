"""ทดสอบครบ: flow แจ้งซ่อมของ chatbot + LINE webhook (postback/กันซ้ำ) + regression RBAC"""
import warnings, json
warnings.filterwarnings("ignore")

from fastapi.testclient import TestClient
import app.main as m
from app.chatbot_core import handle_message
from app.chat_session import clear_session, save_session
from app.models import SessionLocal
from sqlalchemy import text

c = TestClient(m.app)
UID = "smoke-flow-user"
clear_session(UID)

print("=== 1) flow แจ้งซ่อมของ chatbot ===")
# เข้า flow เก็บข้อมูลตรง ๆ (จำลอง state ที่บอทตั้งเองหลังไม่พบวิธีแก้ใน KB)
save_session(UID, {"phase": "collecting", "fields": {"device_id": "TEST1-00001",
                                                    "symptom": "มีปัญหาที่ไม่เคยเจอมาก่อน ช่วยดูให้หน่อยครับ"}})
steps = [
    "สมชาย ใจดี",           # ชื่อ
    "0812345678",          # เบอร์
    "ยืนยัน",               # ยืนยันสร้าง ticket
]
for t in steps:
    try:
        r = handle_message(user_id=UID, text=t, reply_token="")
        print(f"  > {t:14} -> {(r or '')[:88].replace(chr(10),' ')}")
    except Exception as e:
        print(f"  > {t:14} -> ❌ {type(e).__name__}: {e}")

# ล้าง ticket ทดสอบ (ถ้าถูกสร้าง)
db = SessionLocal()
row = db.execute(text("SELECT ticket_id FROM repair_tickets WHERE reporter_name='สมชาย ใจดี'")).fetchall()
print("  ticket ที่สร้างจากเทส:", [r[0] for r in row])
for r in row:
    db.execute(text("DELETE FROM ticket_updates WHERE ticket_id IN (SELECT id FROM repair_tickets WHERE ticket_id=:t)"), {"t": r[0]})
    db.execute(text("DELETE FROM repair_tickets WHERE ticket_id=:t"), {"t": r[0]})
db.commit(); db.close()
clear_session(UID)

print("\n=== 2) LINE webhook (postback + กัน event ซ้ำ) ===")
import uuid as _u
_eid = "evt-" + _u.uuid4().hex[:10]
ev = {"events": [{"type": "message", "webhookEventId": _eid,
                  "replyToken": "rt", "source": {"type": "user", "userId": "U-test"},
                  "message": {"type": "text", "text": "สวัสดี"}}]}
r1 = c.post("/api/line/webhook", json=ev)
r2 = c.post("/api/line/webhook", json=ev)  # ส่งซ้ำ event เดิม
print("  ยิงครั้งแรก:", r1.status_code, r1.json())
print("  ยิงซ้ำ event เดิม:", r2.status_code, r2.json(), "(ต้อง processed=0)")

pb = {"events": [{"type": "postback", "webhookEventId": "evt-" + _u.uuid4().hex[:10], "replyToken": "rt2",
                  "source": {"type": "user", "userId": "U-test"},
                  "postback": {"data": "action=contact"}}]}
r3 = c.post("/api/line/webhook", json=pb)
print("  postback:", r3.status_code, r3.json())

print("\n=== 3) regression RBAC ===")
print("  anon /api/tickets ->", c.get("/api/tickets").status_code, "(ต้อง 401)")
print("  anon /api/devices ->", c.get("/api/devices").status_code, "(ต้อง 401)")
tok = c.post("/api/auth/login", json={"username": "test03", "password": "test003"}).json()["token"]
H = {"Authorization": "Bearer " + tok}
s = c.get("/api/stats", headers=H)
print("  admin_school /api/stats ->", s.status_code, "tickets=", s.json().get("total_tickets"))
dev = c.get("/api/devices?limit=50", headers=H).json()
print("  admin_school เห็นอุปกรณ์:", [(d["device_id"], d.get("organization_name")) for d in dev])
kb = c.post("/api/kb/articles", json={"title": "TEST-merge-smoke", "device_type": "Router",
                                      "symptom_tags": [], "steps": [], "is_published": False}, headers=H)
print("  admin_school สร้างบทความ ->", kb.status_code)
if kb.status_code == 201:
    print("     ลบ:", c.delete(f"/api/kb/articles/{kb.json()['kb_id']}", headers=H).status_code)
print("  owner login ->", c.post("/api/auth/login", json={"username": "iwasuperadmin", "password": "IwaScr2026!admin"}).status_code)
