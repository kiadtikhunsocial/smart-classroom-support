import json, os, urllib.request

BASE = "https://smart-classroom-backend-3tv7.onrender.com"


def call(path, token=None, method="GET", body=None):
    req = urllib.request.Request(BASE + path, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    data = json.dumps(body).encode() if body else None
    try:
        with urllib.request.urlopen(req, data, timeout=30) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:200]


def login(u, p):
    s, d = call("/api/auth/login", method="POST", body={"username": u, "password": p})
    if s != 200:
        return None, None
    return d["token"], d.get("user", {})


if __name__ == "__main__":
    admin_password = os.environ.get("TEST_ADMIN_PASSWORD", "")
    users = ([("iwasuperadmin", admin_password)] if admin_password else []) + [("test01", "test001"),
             ("test02", "test002"), ("test03", "test003"), ("test04", "test004"),
             ("test07", "test007")]

    for u, p in users:
        tok, info = login(u, p)
        if not tok:
            print(f"{u}: LOGIN FAIL")
            continue
        role = info.get("role")
        org = info.get("organization_id")
        s1, t = call("/api/tickets?limit=50", tok)
        s2, dv = call("/api/devices?limit=100", tok)
        s3, rp = call("/api/reports/summary", tok)
        tids = [x.get("ticket_id") or x.get("ticket_no") for x in t] if isinstance(t, list) else t
        dorgs = sorted({x.get("organization_id") for x in dv}) if isinstance(dv, list) else dv
        print(f"{u} role={role} org={org}")
        print(f"   tickets({s1}): {tids if isinstance(tids, list) else str(tids)[:80]}")
        print(f"   device-orgs({s2}): {dorgs if isinstance(dorgs, list) else str(dorgs)[:80]}")
        print(f"   report({s3}): {json.dumps(rp, ensure_ascii=False)[:150] if s3 == 200 else rp}")
