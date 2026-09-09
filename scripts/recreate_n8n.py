import json, os, urllib.request, urllib.error, glob

KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI3ZmQwNTllYS1kYWFiLTRmYzYtOWRhMC05NWIxZWRlZWNlMjkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiY2MzNDIxM2UtMmUxNC00YmQyLWI0MTAtNWM1NDljMDE5ZTFmIiwiaWF0IjoxNzg4OTQwNDM4fQ.fWhQGD7dhq2lTRYQ6RRGgG3eQZbHvauj7GF1auuSwaY"
BASE = "https://n8n-production-3bcb9.up.railway.app/api/v1"
OUT = r"C:\Users\nonam\AppData\Local\Temp\n8n_real"
LINE_TOKEN = "uOh1wAqqfQD9nGxsrwmmtbtnUDmeOESBSDt4weVtMhaAybKy8mMK2KMl2aWwlfaPBmzVTWnw+zAjPOY2d/bmwr27hngm43cJoi5mqHXwObG5XY8eAjFHc8R6GffOGSBOyONcFDJnoYFj0K4QVUgkmwdB04t89/1O/w1cDnyilFU="

def call(path, method="GET", payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data,
        headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}, method=method)
    try:
        return json.loads(urllib.request.urlopen(req, timeout=40).read().decode())
    except urllib.error.HTTPError as e:
        raise RuntimeError(f"{method} {path}: {e.code} {e.read().decode()[:200]}")

# 1) import workflows
wf_ids = {}
for fn in sorted(glob.glob(os.path.join(OUT, "*.json"))):
    d = json.load(open(fn, encoding="utf-8"))
    r = call("/workflows", "POST", {"name": d["name"], "nodes": d["nodes"], "connections": d["connections"], "settings": d.get("settings", {})})
    wf_ids[d["name"]] = r["id"]
    print(f"WF: {d['name'][:45]} -> {r['id']}")

# 2) create credentials
line_cred = call("/credentials", "POST", {"name": "line_bot", "type": "httpHeaderAuth", "data": {"name": "Authorization", "value": f"Bearer {LINE_TOKEN}"}})
db_cred = call("/credentials", "POST", {"name": "smart_classroom_db", "type": "postgres", "data": {"host": "postgres.railway.internal", "port": 5432, "database": "railway", "user": "postgres", "password": "viWCnUeCwEpnOoskzcOWGTUKwidLZGfv", "ssl": "disable"}})
line_id, db_id = line_cred["id"], db_cred["id"]
print(f"CREDS: line_bot={line_id} db={db_id}")

# 3) link creds into All-in-One, then activate all
for name, wid in wf_ids.items():
    if "All-in-One" in name:
        r = call(f"/workflows/{wid}", "GET")
        for node in r.get("nodes", []):
            creds = node.get("credentials") or {}
            if "httpHeaderAuth" in creds: creds["httpHeaderAuth"]["id"] = line_id
            if "postgres" in creds: creds["postgres"]["id"] = db_id
        r2 = call("/workflows", "POST", {"name": r["name"], "nodes": r["nodes"], "connections": r["connections"], "settings": r.get("settings", {})})
        call(f"/workflows/{wid}", "DELETE")
        wid = r2["id"]
        print(f"REBUILT All-in-One with creds -> {wid}")
    try:
        a = call(f"/workflows/{wid}/activate", "POST")
        print(f"ACTIVATED: {name[:40]} -> {a.get('active')}")
    except RuntimeError as e:
        print(f"skip activate {name[:30]}: {str(e)[:50]}")

print("DONE")
