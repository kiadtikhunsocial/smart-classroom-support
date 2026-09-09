import json, urllib.request, urllib.error, glob, os

KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJmYmE4ZjU0NS1kYjRjLTQxNTktODBiNC04MWE2ZGJjYTYwODYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiZjhhMTBlZGUtNDAxYS00OTEzLWE4YzMtNGY4ODkxNDFhZjI1IiwiaWF0IjoxNzg4OTI0MjAzfQ.Md6u1rCtUG1o2QgLnr6S7Cu3G5woBXsMILCd0sOJfYc"
BASE = "https://n8n-production-b27c.up.railway.app/api/v1"
OUT = r"C:\Users\nonam\AppData\Local\Temp\n8n_real"

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
line_cred = call("/credentials", "POST", {
    "name": "line_bot", "type": "httpHeaderAuth",
    "data": {"name": "Authorization", "value": "Bearer NcoCcYU/FHi9rEjEf5ru2V+0ko3x+0uT9dk7IqozRPg2TxHDyxI0WFz8fIxi5+3NBmzVTWnw+zAjPOY2d/bmwr27hngm43cJoi5mqHXwObFTm2sIajxmG4/FDywdS1DKhR39L403FU8uIuMhNbtpggdB04t89/1O/w1cDnyilFU="}})
db_cred = call("/credentials", "POST", {
    "name": "smart_classroom_db", "type": "postgres",
    "data": {"host": "postgres.railway.internal", "port": 5432, "database": "railway", "user": "postgres", "password": "viWCnUeCwEpnOoskzcOWGTUKwidLZGfv", "ssl": "disable"}})
line_id, db_id = line_cred["id"], db_cred["id"]
print(f"CREDS: line_bot={line_id}  db={db_id}")

# 3) link creds into All-in-One workflow (the 68-node one)
allin = next(n for n, i in wf_ids.items() if "All-in-One" in n)
wid = wf_ids[allin]
r = call(f"/workflows/{wid}", "GET")
nodes = r["nodes"]
for node in nodes:
    creds = node.get("credentials") or {}
    if "httpHeaderAuth" in creds:
        creds["httpHeaderAuth"]["id"] = line_id
    if "postgres" in creds:
        creds["postgres"]["id"] = db_id
r2 = call("/workflows", "POST", {"name": r["name"], "nodes": nodes, "connections": r["connections"], "settings": r.get("settings", {})})
new_allin_id = r2["id"]
call(f"/workflows/{wid}", "DELETE")
print(f"LINKED creds in All-in-One -> new id {new_allin_id}")

# 4) activate everything
for name, wid in list(wf_ids.items()) + [("All-in-One(rebuilt)", new_allin_id)]:
    try:
        a = call(f"/workflows/{wid}/activate", "POST")
        print(f"ACTIVATED: {name[:45]} -> {a.get('active')}")
    except RuntimeError as e:
        print(f"skip activate {name[:30]}: {str(e)[:60]}")

print("DONE")
