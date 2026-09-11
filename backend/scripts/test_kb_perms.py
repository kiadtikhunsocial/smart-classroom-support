"""ทดสอบ KB permissions กับ Neon จริง (admin_school / admin) — ลบข้อมูลที่สร้างเองตอนจบ"""
import os
from fastapi.testclient import TestClient

import app.main as m

c = TestClient(m.app)


def tok(u, p):
    return c.post("/api/auth/login", json={"username": u, "password": p}).json()["token"]


t3 = tok("test03", "test003")   # admin_school org 11
t6 = tok("test06", "test006")   # admin (ไม่มีสังกัด)
h3 = {"Authorization": "Bearer " + t3}
h6 = {"Authorization": "Bearer " + t6}

body = {"title": "TEST-admin_school-article", "device_type": "Projector",
        "symptom_tags": ["t"], "steps": [{"order": 1, "text": "s"}], "is_published": False}

r = c.post("/api/kb/articles", json=body, headers=h3)
print("admin_school create ->", r.status_code, r.json().get("kb_id"), "org=", r.json().get("organization_id") if r.status_code < 300 else r.text[:150])
kid = r.json().get("kb_id") if r.status_code < 300 else None

if kid:
    r2 = c.patch(f"/api/kb/articles/{kid}", json={"title": "TEST-edited"}, headers=h3)
    print("admin_school edit own ->", r2.status_code, r2.json().get("title") if r2.status_code < 300 else r2.text[:120])
    r3 = c.patch(f"/api/kb/articles/{kid}", json={"title": "x"}, headers=h6)
    print("admin edit school-article (ควร 403) ->", r3.status_code, str(r3.json())[:90])

r4 = c.post("/api/kb/articles", json={"title": "TEST-admin-global", "device_type": "Router",
                                      "symptom_tags": [], "steps": [], "is_published": False}, headers=h6)
print("admin create ->", r4.status_code, r4.json().get("kb_id") if r4.status_code < 300 else r4.text[:150])
gid = r4.json().get("kb_id") if r4.status_code < 300 else None

for k, h in ((kid, h3), (gid, h6)):
    if k:
        print("cleanup", k, c.delete(f"/api/kb/articles/{k}", headers=h).status_code)

# ตรวจว่า test03 เห็นเฉพาะบทความหลัก + ของรรตัวเอง
s, d = None, None
resp = c.get("/api/kb/articles?limit=200", headers=h3)
arts = resp.json()
own = [a for a in arts if a.get("organization_id") not in (None, 11)]
print("test03 sees", len(arts), "articles | ของรรอื่นที่หลุดมา:", len(own))
