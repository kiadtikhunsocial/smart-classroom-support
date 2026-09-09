import json, os, urllib.request, urllib.error

# อ่าน secrets จาก env (ไม่ hardcode) — ตั้ง N8N_API_KEY, LINE_CHANNEL_TOKEN, POSTGRES_URL ก่อนรัน
KEY = os.environ.get("N8N_API_KEY", "")
if not KEY:
    raise SystemExit("ต้องตั้ง env N8N_API_KEY ก่อนรัน")
BASE = os.environ.get("N8N_BASE_URL", "https://n8n-production-b27c.up.railway.app/api/v1")
LINE_TOKEN = os.environ.get("LINE_CHANNEL_TOKEN", "")
if not LINE_TOKEN:
    raise SystemExit("ต้องตั้ง env LINE_CHANNEL_TOKEN ก่อนรัน")
import re
# DATABASE_URL ตัวอย่าง: postgresql://user:pass@host:5432/db
_m = re.match(r"postgresql\+?\w*://([^:]+):([^@]+)@([^:/]+):(\d+)/([\w-]+)", os.environ.get("DATABASE_URL", ""))
if _m:
    _db_user, _db_pass, _db_host, _db_port, _db_name = _m.groups()
else:
    _db_user, _db_pass, _db_host, _db_port, _db_name = "postgres", "", "localhost", "5432", "railway"

creds = [
    {
        "name": "line_bot",
        "type": "httpHeaderAuth",
        "data": {
            "name": "Authorization",
            "value": f"Bearer {LINE_TOKEN}",
        },
    },
    {
        "name": "smart_classroom_db",
        "type": "postgres",
        "data": {
            "host": _db_host,
            "port": int(_db_port),
            "database": _db_name,
            "user": _db_user,
            "password": _db_pass,
            "ssl": "disable",
        },
    },
]

for cred in creds:
    body = json.dumps(cred).encode()
    req = urllib.request.Request(f"{BASE}/credentials", data=body,
        headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}, method="POST")
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
        print(f"OK created {cred['name']} -> id={r.get('id')}")
    except urllib.error.HTTPError as e:
        print(f"ERR {cred['name']}: {e.code} {e.read().decode()[:200]}")
