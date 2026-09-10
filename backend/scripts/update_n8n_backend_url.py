# -*- coding: utf-8 -*-
"""อัปเดต n8n workflow: เปลี่ยน backend URL จาก Railway เก่า → Render ใหม่"""
import json, sys, urllib.request

N8N_BASE = "https://n8n-production-3bcb9.up.railway.app"
N8N_KEY = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiI3ZmQwNTllYS1kYWFiLTRmYzYtOWRhMC05NWIxZWRlZWNlMjkiLCJpc3MiOiJuOG4iLCJhdWQiOiJwdWJsaWMtYXBpIiwianRpIjoiNjgxZWYzZTgtMjIyOC00NDUxLWE2OTMtM2Q5NjU3N2U0YTdmIiwiaWF0IjoxNzg5MDUxMTI5fQ.BahBiKBOZmJAlefIuW0M7kt-ooaXfJUvja6DZKuQOeQ"
OLD = "https://backend-production-728f.up.railway.app"
NEW = "https://smart-classroom-backend-3tv7.onrender.com"
WF_ID = "A2CgAiYko6ueBVaz"


def api(method, path, body=None):
    req = urllib.request.Request(
        N8N_BASE + path, method=method,
        headers={"X-N8N-API-KEY": N8N_KEY, "Content-Type": "application/json"},
        data=json.dumps(body).encode() if body else None)
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def main():
    wf = api("GET", f"/api/v1/workflows/{WF_ID}")
    changed = []
    for n in wf["nodes"]:
        u = n.get("parameters", {}).get("url", "")
        if OLD in u:
            n["parameters"]["url"] = u.replace(OLD, NEW)
            changed.append((n["name"], NEW + u.split(".app", 1)[1]))
    if not changed:
        print("ไม่พบ URL ที่ต้องเปลี่ยน (เรียบร้อยแล้ว)")
        return
    print("จะเปลี่ยน:")
    for name, newurl in changed:
        print(f"  {name}: {newurl}")
    # PUT update — n8n ต้องการ nodes + connections + settings
    upd = {
        "name": wf["name"],
        "nodes": wf["nodes"],
        "connections": wf["connections"],
        "settings": wf.get("settings", {}),
    }
    res = api("PUT", f"/api/v1/workflows/{WF_ID}", upd)
    print("OK อัปเดต workflow:", res.get("name"), "| nodes:", len(res.get("nodes", [])))
    # activate ถ้ายังไม่ active
    if not res.get("active"):
        api("POST", f"/api/v1/workflows/{WF_ID}/activate")
        print("activated")


if __name__ == "__main__":
    main()
