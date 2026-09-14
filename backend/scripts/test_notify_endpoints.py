"""ทดสอบ endpoint ที่เรียก _notify_n8n ทุกตัว (กันบั๊ก NameError กลับมา)"""
import warnings
warnings.filterwarnings("ignore")
from fastapi.testclient import TestClient
import app.main as m
from app.models import SessionLocal
from sqlalchemy import text

c = TestClient(m.app)
TOK = c.post("/api/auth/login", json={"username": "iwasuperadmin", "password": "IwaScr2026!admin"}).json()["token"]
H = {"Authorization": "Bearer " + TOK}

db = SessionLocal()
dev = db.execute(text("SELECT device_id FROM devices ORDER BY id LIMIT 1")).scalar()
db.close()
print("อุปกรณ์ทดสอบ:", dev)

print("\n=== 1) POST /api/tickets (QR) ===")
r = c.post("/api/tickets", json={"device_id": dev, "title": "ทดสอบแก้บั๊ก notify",
                                 "description": "t", "reporter_name": "ทดสอบ", "priority": "normal"})
print("   ->", r.status_code, str(r.json())[:120])
tid = r.json().get("ticket_id") if r.status_code in (200, 201) else None

print("=== 2) PATCH สถานะ (เรียก _notify_n8n) ===")
if tid:
    r2 = c.patch(f"/api/tickets/{tid}/status", json={"status": "assigned", "author_name": "ทดสอบ",
                                                     "author_role": "admin", "force": True})
    print("   ->", r2.status_code, str(r2.json())[:120])

print("=== 3) POST /api/public/report ===")
r3 = c.post("/api/public/report", json={"organization_code": "TEST1", "device_id": dev,
                                        "title": "ทดสอบฟอร์มสาธารณะ", "description": "t",
                                        "reporter_name": "ทดสอบ", "reporter_phone": "0800000000"})
print("   ->", r3.status_code, str(r3.json())[:150])

print("\n=== เก็บกวาด ticket ทดสอบ ===")
db = SessionLocal()
rows = db.execute(text("SELECT ticket_id FROM repair_tickets WHERE reporter_name='ทดสอบ'")).fetchall()
for r4 in rows:
    db.execute(text("DELETE FROM ticket_updates WHERE ticket_id IN (SELECT id FROM repair_tickets WHERE ticket_id=:t)"), {"t": r4[0]})
    db.execute(text("DELETE FROM repair_tickets WHERE ticket_id=:t"), {"t": r4[0]})
db.commit()
print("   ลบ:", [x[0] for x in rows])
db.close()
