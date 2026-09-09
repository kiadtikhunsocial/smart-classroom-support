import json, urllib.request, urllib.error, glob, os

KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5NzNhNTE5Mi00NGQxLTQyMjctOGYzYS00MWQxMjAwYTk0ZTYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiYzUxNGExOWEtNjgzOC00NjZlLTg0YzYtMzQzYTcxOTJkN2NkIiwiaWF0IjoxNzg4OTIxODkxfQ.L8Wki3aSAWmyD-c7owdVm6z50CXfjtNZ6q5-KEEM1Jw"
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
