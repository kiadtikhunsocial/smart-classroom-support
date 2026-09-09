import sqlite3, json, os, re

DB = r"C:\Users\nonam\smart-classroom-support\n8n_local.sqlite"
OUT = r"C:\Users\nonam\AppData\Local\Temp\n8n_real"
os.makedirs(OUT, exist_ok=True)

c = sqlite3.connect(DB)
cols = [r[1] for r in c.execute("PRAGMA table_info(workflow_entity)")]
rows = c.execute("SELECT * FROM workflow_entity").fetchall()
for r in rows:
    d = dict(zip(cols, r))
    obj = {
        "name": d["name"],
        "nodes": json.loads(d["nodes"]),
        "connections": json.loads(d["connections"]),
        "settings": json.loads(d["settings"]) if d["settings"] else {},
    }
    safe = re.sub(r"[^A-Za-z0-9]+", "_", d["name"])[:50]
    fn = os.path.join(OUT, f"{d['id']}_{safe}.json")
    with open(fn, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False)
    print("exported:", d["id"], "|", d["name"], "| nodes:", len(obj["nodes"]), "|", fn)
