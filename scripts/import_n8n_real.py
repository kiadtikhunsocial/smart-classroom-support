import json, os, urllib.request, urllib.error, glob, os

KEY = os.environ.get("N8N_API_KEY", "")
BASE = "https://n8n-production-b27c.up.railway.app/api/v1"
OUT = r"C:\Users\nonam\AppData\Local\Temp\n8n_real"

for fn in sorted(glob.glob(os.path.join(OUT, "*.json"))):
    d = json.load(open(fn, encoding="utf-8"))
    body = json.dumps(d).encode()
    req = urllib.request.Request(f"{BASE}/workflows", data=body,
        headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}, method="POST")
    try:
        r = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())
        print(f"OK  {os.path.basename(fn)[:40]} -> id={r.get('id')} active={r.get('active')}")
    except urllib.error.HTTPError as e:
        print(f"ERR {os.path.basename(fn)[:40]}: {e.code} {e.read().decode()[:150]}")
