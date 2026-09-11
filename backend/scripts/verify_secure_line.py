"""ตรวจหลังเปิดโหมดเข้ม (N8N_SHARED_SECRET): สายจริงต้องยังทำงาน และคำขอปลอมต้องถูกปฏิเสธ"""
import json
import time
import urllib.request
import urllib.error

BACKEND = "https://smart-classroom-backend-3tv7.onrender.com"
N8N = "https://n8n-production-3bcb9.up.railway.app"
SECRET = open(r"C:\Users\nonam\smart-classroom-support\_n8n_secret.txt").read().strip()


def post(url, payload, headers=None):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), method="POST")
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, r.read().decode()[:120]
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:120]


ev = lambda uid: {"events": [{"type": "message", "webhookEventId": "e-" + uid, "replyToken": "faketoken",
                              "source": {"type": "user", "userId": uid},
                              "message": {"type": "text", "text": "จอไม่ติด"}}]}

print("1) ยิงตรง backend โดยไม่มี secret ->", post(f"{BACKEND}/api/line/webhook", ev("Uhack1")))
print("2) ยิงตรง /api/line/bot โดยไม่มี secret ->", post(f"{BACKEND}/api/line/bot", {"user_id": "Uhack2", "text": "hi"}))
print("3) ยิงตรง backend พร้อม secret ที่ถูก ->",
      post(f"{BACKEND}/api/line/webhook", ev("Uok1"), {"X-N8N-Secret": SECRET}))
uid = "Ue2e" + str(int(time.time()))
print("4) สายจริง n8n -> backend (user " + uid + ") ->", post(f"{N8N}/webhook/line-webhook", ev(uid)))

time.sleep(12)
from app.models import SessionLocal  # noqa: E402
from sqlalchemy import text  # noqa: E402
from app.models import SessionLocal  # noqa: F811

db = SessionLocal()
print("\n=== ผลใน DB ===")
for tag, uid_ in [("คำขอปลอม Uhack1", "Uhack1"), ("secret ถูก Uok1", "Uok1"), ("สายจริง " + uid, uid)]:
    row = db.execute(text("SELECT COUNT(*) FROM chatbot_logs WHERE user_id=:u"), {"u": uid_}).scalar()
    print(f"  {tag}: ประมวลผล {row} ครั้ง", "(ถูกต้อง: ไม่ควรถูกประมวลผล)" if uid_ == "Uhack1" else "")
db.close()
