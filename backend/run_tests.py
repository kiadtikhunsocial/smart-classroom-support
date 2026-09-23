"""run_tests.py — ทดสอบระบบโดยใช้ TestClient (ไม่ต้องรัน server จริง)"""
import os
import sys

os.chdir(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, ".")

from sqlalchemy import text as sa_text

from app.main import OPEN_TICKET_STATUSES, app
from app.models import SessionLocal
from starlette.testclient import TestClient

client = TestClient(app, raise_server_exceptions=True)

# รหัสอุปกรณ์ไม่ฮาร์ดโค้ดแล้ว: รูปแบบใหม่ผูกกับโรงเรียน/อาคาร/ห้อง
# (เช่น SCHDEMO-B3-301-DISP-01) และ seed สร้างจาก generate_device_id ตอนรัน
# จึงต้องหยิบตัวจริงจากฐานข้อมูล ไม่ใช่เดารหัส
#
# ต้องเป็นเครื่องที่ "ไม่มีใบงานค้าง" ด้วย ไม่ใช่เครื่องแรกตามลำดับรหัส:
# TEST 3 สร้างใบงานใหม่ ถ้าเครื่องนั้นมีใบค้างอยู่ POST /api/tickets จะตอบ 409
# DUPLICATE_OPEN_TICKET ตามกันแจ้งซ้ำ (TOR 1.5.2) — ใช้ OPEN_TICKET_STATUSES
# ชุดเดียวกับที่ฝั่ง API ใช้ตรวจ เพื่อให้เงื่อนไขตรงกันเสมอ
_db = SessionLocal()
try:
    DEVICE_ID = _db.execute(
        sa_text(
            "SELECT d.device_id FROM devices d "
            "WHERE NOT EXISTS ("
            "  SELECT 1 FROM repair_tickets t "
            "  WHERE t.device_id = d.device_id AND t.status::text = ANY(:open)"
            ") ORDER BY d.device_id LIMIT 1"
        ),
        {"open": list(OPEN_TICKET_STATUSES)},
    ).scalar()
finally:
    _db.close()
if not DEVICE_ID:
    raise SystemExit(
        "✗ ไม่มีอุปกรณ์ที่ว่างจากใบงานค้างในฐานข้อมูล "
        "— รัน python scripts/seed_db.py ก่อน หรือปิดใบงานที่ค้างอยู่"
    )
print(f"อุปกรณ์ที่ใช้ทดสอบ: {DEVICE_ID}")

# /api/tickets, /api/tickets/{id}/status และ /api/tickets/{id}/history ต้องมี token แล้ว
# (get_current_user) เทสต์เดิมยิงแบบไม่ล็อกอินจึงได้ 401 — ล็อกอินด้วยบัญชี super_admin
# ที่ scripts/seed_admin.py สร้างไว้ ปรับได้ด้วย env TEST_ADMIN_USER / TEST_ADMIN_PASSWORD
ADMIN_USER = os.environ.get("TEST_ADMIN_USER", "iwasuperadmin")
ADMIN_PASSWORD = os.environ.get("TEST_ADMIN_PASSWORD", "")
if not ADMIN_PASSWORD:
    raise SystemExit("Set TEST_ADMIN_PASSWORD before running this manual smoke test")

_login = client.post(
    "/api/auth/login",
    json={"username": ADMIN_USER, "password": ADMIN_PASSWORD},
)
if _login.status_code != 200:
    raise SystemExit(
        f"✗ ล็อกอิน {ADMIN_USER} ไม่ผ่าน ({_login.status_code}): {_login.text[:200]}\n"
        "  รัน `python scripts/seed_admin.py --yes` หรือกำหนด "
        "TEST_ADMIN_USER / TEST_ADMIN_PASSWORD ให้ตรงกับบัญชีที่มีอยู่"
    )
AUTH = {"Authorization": f"Bearer {_login.json()['token']}"}
print(f"ล็อกอินเป็น: {ADMIN_USER} ({_login.json()['user']['role']})")

print("=" * 60)
print("TEST 1: Health check")
r = client.get("/health")
print(f"  Status: {r.status_code}")
print(f"  Response: {r.json()}")
assert r.status_code == 200, f"Expected 200, got {r.status_code}"

print()
print("=" * 60)
print(f"TEST 2: Get device {DEVICE_ID}")
r = client.get(f"/api/devices/{DEVICE_ID}")
print(f"  Status: {r.status_code}")
if r.status_code == 200:
    d = r.json()
    print(f"  Device ID: {d['device_id']}")
    print(f"  Type: {d['device_type']}")
    print(f"  Room: {d.get('room_name') or d.get('room_code')}")
    print(f"  Org: {d['organization_name']}")
else:
    print(f"  Error: {r.text[:200]}")
assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"

print()
print("=" * 60)
print("TEST 3: Create ticket")
payload = {
    "device_id": DEVICE_ID,
    "title": "จอภาพ flickering",
    "description": "หน้าจอกะพริบ ทุก 3 วินาที",
    "reporter_name": "ครูสมหญิง",
    "reporter_email": "som@example.com",
    "reporter_type": "teacher",
    "priority": "high",
}
r = client.post("/api/tickets", json=payload)
print(f"  Status: {r.status_code}")
CREATED_TICKET_ID = None
if r.status_code == 201:
    t = r.json()
    CREATED_TICKET_ID = t["ticket_id"]
    print(f"  Ticket ID: {t['ticket_id']}")
    print(f"  Status: {t['status']}")
    print(f"  Priority: {t['priority']}")
    print(f"  Created: {t['created_at']}")
else:
    print(f"  Error: {r.text[:200]}")
assert r.status_code == 201, f"Expected 201, got {r.status_code}: {r.text[:200]}"

print()
print("=" * 60)
print("TEST 4: List tickets")
r = client.get("/api/tickets", headers=AUTH)
print(f"  Status: {r.status_code}")
# ต้อง assert ก่อนวน: ตอน 401 body เป็น dict {"detail": ...} การวนจะได้ str
# แล้วพังเป็น TypeError: string indices must be integers แทนที่จะบอกว่า auth ตก
assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
tickets = r.json()
assert isinstance(tickets, list), f"คาดว่าเป็น list ของใบงาน แต่ได้: {str(tickets)[:200]}"
print(f"  Total tickets: {len(tickets)}")
for t in tickets[:10]:   # limit ฝั่ง API = 50 ใบ — พิมพ์แค่ 10 แถวแรกพอให้เห็นรูปแบบ
    print(f"  - {t['ticket_id']}: {t['title']} [{t['status']}]")
if len(tickets) > 10:
    print(f"  … และอีก {len(tickets) - 10} ใบ")

print()
print("=" * 60)
print("TEST 5: Update status")
# ใช้ใบที่ TEST 3 สร้างเอง ไม่ใช่ tickets[0] เพื่อไม่ไปเปลี่ยนสถานะใบงานจริงใน DB
ticket_id = CREATED_TICKET_ID or tickets[0]["ticket_id"]
r = client.patch(f"/api/tickets/{ticket_id}/status", headers=AUTH, json={
    "status": "assigned",
    "author_name": "เจ้าหน้าที่ IT",
    "author_role": "it_staff",
})
print(f"  Status: {r.status_code}")
print(f"  Response: {r.json()}")
assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"

print()
print("=" * 60)
print("TEST 6: Ticket history")
r = client.get(f"/api/tickets/{ticket_id}/history", headers=AUTH)
print(f"  Status: {r.status_code}")
assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
history = r.json()
assert isinstance(history, list), f"คาดว่าเป็น list ของประวัติ แต่ได้: {str(history)[:200]}"
for h in history:
    print(f"  {h['created_at']}: {h['from_status'] or '—'} → {h['to_status']} ({h['author_name']})")

print()
print("=" * 60)
print("TEST 7: Stats")
r = client.get("/api/stats", headers=AUTH)
print(f"  Status: {r.status_code}")
stats = r.json()
assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
print(f"  Total: {stats['total_tickets']}, Open: {stats['open']}, In Progress: {stats['in_progress']}, Resolved: {stats['resolved']}, Cancelled: {stats['cancelled']}")

print()
print("=" * 60)
# เก็บกวาด: ลบใบงานที่ TEST 3 สร้าง (ticket_updates ลบตาม cascade)
# ถ้าปล่อยค้างไว้ อุปกรณ์ตัวนี้จะมีใบงานค้าง แล้วรันรอบถัดไปจะเข้าทางกันแจ้งซ้ำ
# (TOR 1.5.2) คืนใบเดิมแทนการสร้างใหม่ ทำให้ TEST 3 ตก
if CREATED_TICKET_ID:
    _cleanup_db = SessionLocal()
    try:
        _cleanup_db.execute(
            sa_text("DELETE FROM repair_tickets WHERE ticket_id = :t"),
            {"t": CREATED_TICKET_ID},
        )
        _cleanup_db.commit()
        print(f"ลบใบงานที่ใช้ทดสอบแล้ว: {CREATED_TICKET_ID}")
    except Exception as exc:   # ลบไม่ได้ก็ไม่ควรทำให้เทสต์ที่ผ่านแล้วกลายเป็น fail
        _cleanup_db.rollback()
        print(f"⚠ ลบใบงาน {CREATED_TICKET_ID} ไม่สำเร็จ: {exc!r}")
    finally:
        _cleanup_db.close()

print("✅ ทุกการทดสอบผ่าน!")
