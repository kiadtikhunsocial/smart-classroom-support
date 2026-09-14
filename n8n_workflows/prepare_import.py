"""prepare_import.py — เตรียมไฟล์ workflow สำหรับ import เข้า n8n

ไฟล์ใน n8n_workflows/ ถูกแทนค่าลับด้วย `<N8N_SHARED_SECRET>` ก่อน commit (เพื่อไม่ให้ความลับขึ้น git)
สคริปต์นี้จะแทนค่าจริงกลับ แล้วสร้างไฟล์ `.ready.json` พร้อมคำสั่ง import/publish

หาค่าลับจาก (เรียงตามลำดับ):
  1) ตัวแปรแวดล้อม N8N_SHARED_SECRET
  2) ไฟล์ _n8n_secret.txt ที่ root โปรเจกต์
  3) ถามจากผู้ใช้

ใช้งาน:
    cd n8n_workflows
    python prepare_import.py
"""
import base64
import glob
import gzip
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
PLACEHOLDER = "<N8N_SHARED_SECRET>"


def find_secret():
    s = os.environ.get("N8N_SHARED_SECRET", "").strip()
    if s:
        return s, "env N8N_SHARED_SECRET"
    p = os.path.join(ROOT, "_n8n_secret.txt")
    if os.path.exists(p):
        s = open(p, encoding="utf-8").read().strip()
        if s:
            return s, "_n8n_secret.txt"
    if not sys.stdin.isatty():
        sys.exit("ไม่พบค่าลับ — ตั้ง env N8N_SHARED_SECRET หรือวางไฟล์ _n8n_secret.txt")
    s = input("วางค่า N8N_SHARED_SECRET (ดูได้จาก Render → Environment): ").strip()
    if not s:
        sys.exit("ไม่ได้ระบุค่าลับ")
    return s, "ผู้ใช้ป้อน"


secret, src = find_secret()
print(f"ใช้ค่าลับจาก: {src} (ยาว {len(secret)} ตัวอักษร)\n")

files = sorted(f for f in glob.glob(os.path.join(HERE, "wf_*.json"))
               if not f.endswith(".ready.json"))
if not files:
    sys.exit("ไม่พบไฟล์ wf_*.json")

ready = []
for fp in files:
    raw = open(fp, encoding="utf-8").read()
    n = raw.count(PLACEHOLDER)
    out = raw.replace(PLACEHOLDER, secret)
    d = json.loads(out)
    d["active"] = False                       # ให้ publish เองหลัง import
    ready_path = fp[:-len(".json")] + ".ready.json"
    json.dump(d, open(ready_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ready.append((os.path.basename(ready_path), d["id"], d["name"], n))
    print(f"  ✓ {os.path.basename(ready_path):34} แทน {n} จุด | id={d['id']}")

# ไฟล์ .gz.b64 สำหรับส่งเข้า container ทาง stdin (ไฟล์ใหญ่เกิน command line)
for name, _id, _nm, _n in ready:
    raw = open(os.path.join(HERE, name), "rb").read()
    open(os.path.join(HERE, name + ".b64"), "w").write(base64.b64encode(gzip.compress(raw, 9)).decode())

print("\n=== ขั้นตอน import + publish + restart ===")
for name, wid, _nm, _n in ready:
    base = name[:-len(".ready.json")]
    print(f'''
# {_nm}
cat {name}.b64 | railway ssh --service n8n -- "base64 -d | gunzip > /tmp/{base}.json && n8n import:workflow --input=/tmp/{base}.json"
railway ssh --service n8n -- "n8n publish:workflow --id={wid}"''')
print('\nrailway restart --service n8n --yes     # จำเป็น — ไม่งั้น webhook ยัง 404')
print("\n⚠ ห้าม commit ไฟล์ *.ready.json / *.b64 — มีค่าลับอยู่ (อยู่ใน .gitignore แล้ว)")
