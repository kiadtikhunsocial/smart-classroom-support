import json, urllib.request, urllib.error

KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI5NzNhNTE5Mi00NGQxLTQyMjctOGYzYS00MWQxMjAwYTk0ZTYiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiYzUxNGExOWEtNjgzOC00NjZlLTg0YzYtMzQzYTcxOTJkN2NkIiwiaWF0IjoxNzg4OTIxODkxfQ.L8Wki3aSAWmyD-c7owdVm6z50CXfjtNZ6q5-KEEM1Jw"
BASE = "https://n8n-production-b27c.up.railway.app/api/v1"

creds = [
    {
        "name": "line_bot",
        "type": "httpHeaderAuth",
        "data": {
            "name": "Authorization",
            "value": "Bearer NcoCcYU/FHi9rEjEf5ru2V+0ko3x+0uT9dk7IqozRPg2TxHDyxI0WFz8fIxi5+3NBmzVTWnw+zAjPOY2d/bmwr27hngm43cJoi5mqHXwObFTm2sIajxmG4/FDywdS1DKhR39L403FU8uIuMhNbtpggdB04t89/1O/w1cDnyilFU=",
        },
    },
    {
        "name": "smart_classroom_db",
        "type": "postgres",
        "data": {
            "host": "postgres.railway.internal",
            "port": 5432,
            "database": "railway",
            "user": "postgres",
            "password": "viWCnUeCwEpnOoskzcOWGTUKwidLZGfv",
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
