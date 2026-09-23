"""ทดสอบเส้นทางที่เรียก _notify_n8n ให้ครบ (ใช้ ticket จริง แล้วคืนสภาพเดิม)"""
import warnings
import os
warnings.filterwarnings("ignore")
from fastapi.testclient import TestClient
import app.main as m
from app.models import SessionLocal
from sqlalchemy import text

c = TestClient(m.app)
password = os.environ.get("TEST_ADMIN_PASSWORD", "")
if not password:
    raise SystemExit("Set TEST_ADMIN_PASSWORD before running this manual smoke test")
TOK = c.post("/api/auth/login", json={"username": "iwasuperadmin", "password": password}).json()["token"]
H = {"Authorization": "Bearer " + TOK}

db = SessionLocal()
row = db.execute(text("SELECT ticket_id, status FROM repair_tickets ORDER BY id LIMIT 1")).fetchone()
db.close()
tid, orig = row
print(f"ใช้ ticket {tid} (สถานะเดิม: {orig})")

print("\n1) PATCH สถานะ -> assigned (เรียก _notify_n8n)")
r = c.patch(f"/api/tickets/{tid}/status",
            json={"status": "assigned", "author_name": "ทดสอบระบบ", "author_role": "admin", "force": True},
            headers=H)
print("   ->", r.status_code, str(r.json())[:140])

print("2) คืนสถานะเดิม")
r2 = c.patch(f"/api/tickets/{tid}/status",
             json={"status": orig, "author_name": "ทดสอบระบบ", "author_role": "admin", "force": True},
             headers=H)
print("   ->", r2.status_code, str(r2.json())[:140])

print("3) POST /api/tickets — สร้างอุปกรณ์ชั่วคราวเพื่อทดสอบ notify ตอนสร้าง ticket")
db = SessionLocal()
org = db.execute(text("SELECT id, code FROM organizations ORDER BY id LIMIT 1")).fetchone()
db.execute(text("INSERT INTO devices (device_id, organization_id, device_type, status, created_at) "
                "VALUES ('TEST-NOTIFY-01', :o, 'Other', 'active', now())"), {"o": org[0]})
db.commit()
db.close()
r3 = c.post("/api/tickets", json={"device_id": "TEST-NOTIFY-01", "title": "ทดสอบ notify ตอนสร้าง",
                                  "description": "t", "reporter_name": "ทดสอบระบบ", "priority": "normal"},
            headers=H)
print("   ->", r3.status_code, str(r3.json())[:140])

print("4) เก็บกวาด")
db = SessionLocal()
db.execute(text("DELETE FROM ticket_updates WHERE ticket_id IN "
                "(SELECT id FROM repair_tickets WHERE device_id='TEST-NOTIFY-01')"))
db.execute(text("DELETE FROM repair_tickets WHERE device_id='TEST-NOTIFY-01'"))
db.execute(text("DELETE FROM scan_logs WHERE device_id='TEST-NOTIFY-01'"))
db.execute(text("DELETE FROM devices WHERE device_id='TEST-NOTIFY-01'"))
db.commit()
print("   ลบอุปกรณ์ชั่วคราวแล้ว | tickets เหลือ:",
      db.execute(text("SELECT COUNT(*) FROM repair_tickets")).scalar())
db.close()
