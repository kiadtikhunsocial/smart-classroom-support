import json, urllib.request, urllib.error, os

KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5NzNhNTE5Mi00NGQxLTQyMjctOGYzYS00MWQxMjAwYTk0ZTYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiYzUxNGExOWEtNjgzOC00NjZlLTg0YzYtMzQzYTcxOTJkN2NkIiwiaWF0IjoxNzg4OTIxODkxfQ.L8Wki3aSAWmyD-c7owdVm6z50CXfjtNZ6q5-KEEM1Jw"
BASE = "https://n8n-production-b27c.up.railway.app/api/v1"
DIR = "/c/Users/nonam/smart-classroom-support"  # dir containing workflow jsons (staged in tmp via host)
# staged copies are in /tmp/n8n_import (MSYS /tmp) -> real path
import pathlib
stage = pathlib.Path(r"C:\Users\nonam\AppData\Local\Temp\n8n_import") if os.path.isdir(r"C:\Users\nonam\AppData\Local\Temp\n8n_import") else pathlib.Path("/tmp/n8n_import")
files = sorted(stage.glob("wf*.json"))
print("files:", [f.name for f in files])
for f in files:
    data = json.loads(f.read_text(encoding="utf-8"))
    body = json.dumps(data).encode()
    req = urllib.request.Request(f"{BASE}/workflows", data=body,
        headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}, method="POST")
    try:
        r = urllib.request.urlopen(req, timeout=30)
        resp = json.loads(r.read().decode())
        print(f"OK  {f.name} -> id={resp.get('id')} active={resp.get('active')}")
    except urllib.error.HTTPError as e:
        print(f"ERR {f.name}: {e.code} {e.read().decode()[:200]}")
