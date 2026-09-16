"""run_tests.py — ทดสอบระบบโดยใช้ TestClient (ไม่ต้องรัน server จริง)"""
import os
import sys

os.chdir(os.path.join(os.path.dirname(__file__), "..", "backend"))
sys.path.insert(0, ".")

from app.main import app
from starlette.testclient import TestClient

client = TestClient(app, raise_server_exceptions=True)

print("=" * 60)
print("TEST 1: Health check")
r = client.get("/health")
print(f"  Status: {r.status_code}")
print(f"  Response: {r.json()}")
assert r.status_code == 200, f"Expected 200, got {r.status_code}"

print()
print("=" * 60)
print("TEST 2: Get device DEV-2024-00123")
r = client.get("/api/devices/DEV-2024-00123")
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
    "device_id": "DEV-2024-00123",
    "title": "จอภาพ flickering",
    "description": "หน้าจอกะพริบ ทุก 3 วินาที",
    "reporter_name": "ครูสมหญิง",
    "reporter_email": "som@example.com",
    "reporter_type": "teacher",
    "priority": "high",
}
r = client.post("/api/tickets", json=payload)
print(f"  Status: {r.status_code}")
if r.status_code == 201:
    t = r.json()
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
r = client.get("/api/tickets")
print(f"  Status: {r.status_code}")
tickets = r.json()
print(f"  Total tickets: {len(tickets)}")
for t in tickets:
    print(f"  - {t['ticket_id']}: {t['title']} [{t['status']}]")

print()
print("=" * 60)
print("TEST 5: Update status")
ticket_id = tickets[0]["ticket_id"]
r = client.patch(f"/api/tickets/{ticket_id}/status", json={
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
r = client.get(f"/api/tickets/{ticket_id}/history")
print(f"  Status: {r.status_code}")
history = r.json()
for h in history:
    print(f"  {h['created_at']}: {h['from_status'] or '—'} → {h['to_status']} ({h['author_name']})")

print()
print("=" * 60)
print("TEST 7: Stats")
r = client.get("/api/stats")
print(f"  Status: {r.status_code}")
stats = r.json()
assert r.status_code == 200, f"Expected 200, got {r.status_code}: {r.text[:200]}"
print(f"  Total: {stats['total_tickets']}, Open: {stats['open']}, In Progress: {stats['in_progress']}, Resolved: {stats['resolved']}, Cancelled: {stats['cancelled']}")

print()
print("=" * 60)
print("✅ ทุกการทดสอบผ่าน!")
