import json, os, urllib.request, urllib.error

KEY = os.environ.get("N8N_API_KEY", "")
BASE = "https://n8n-production-b27c.up.railway.app/api/v1"

# old -> new credential id map
MAP = {
    "z9Wst6gVCKgQiwW9": "jSI5uC7zdH55DpQe",  # smart_classroom_db (postgres)
    "YZeMXOVRdMP9FZlP": "HBNHyQIJXIIpe0Ut",  # line_bot (httpHeaderAuth)
}
WF_ID = "WjmLHQYv45up8PzI"  # All-in-One

# get current workflow
req = urllib.request.Request(f"{BASE}/workflows/{WF_ID}", headers={"X-N8N-API-KEY": KEY}, method="GET")
d = json.loads(urllib.request.urlopen(req, timeout=30).read().decode())

# rewrite credential refs in every node
changed = 0
for n in d.get("nodes", []):
    creds = n.get("credentials") or {}
    for typ, ref in list(creds.items()):
        old = ref.get("id")
        if old in MAP:
            creds[typ]["id"] = MAP[old]
            changed += 1
# Rewrite credential refs in every node
changed = 0
for n in d.get("nodes", []):
    creds = n.get("credentials") or {}
    for typ, ref in list(creds.items()):
        old = ref.get("id")
        if old in MAP:
            creds[typ]["id"] = MAP[old]
            changed += 1

# Recreate as NEW workflow (POST) with only the writable fields — avoids read-only validation
payload = {
    "name": d.get("name", "All-in-One"),
    "nodes": d.get("nodes", []),
    "connections": d.get("connections", {}),
    "settings": d.get("settings", {}),
}
body = json.dumps(payload).encode()
req2 = urllib.request.Request(f"{BASE}/workflows", data=body,
    headers={"X-N8N-API-KEY": KEY, "Content-Type": "application/json"}, method="POST")
try:
    r = json.loads(urllib.request.urlopen(req2, timeout=30).read().decode())
    new_id = r.get("id")
    print(f"OK recreated {r.get('name')} -> id={new_id} | rewrote {changed} cred refs")
    # delete old
    reqd = urllib.request.Request(f"{BASE}/workflows/{WF_ID}", headers={"X-N8N-API-KEY": KEY}, method="DELETE")
    urllib.request.urlopen(reqd, timeout=30)
    print(f"deleted old {WF_ID}")
    # activate new
    reqa = urllib.request.Request(f"{BASE}/workflows/{new_id}/activate", headers={"X-N8N-API-KEY": KEY}, method="POST")
    ra = json.loads(urllib.request.urlopen(reqa, timeout=30).read().decode())
    print(f"activated new {new_id} active={ra.get('active')}")
except urllib.error.HTTPError as e:
    print("ERR", e.code, e.read().decode()[:300])
