"""backup_db.py — สำรองข้อมูลทั้งหมดจาก PostgreSQL (Neon) เป็นไฟล์ .sql + .json

ใช้งาน:
    DATABASE_URL='postgresql://...' python scripts/backup_db.py [outdir]

ได้ไฟล์ (ใน backups/):
    neondb_<YYYYmmdd_HHMM>.sql   — INSERT ทุกตาราง (กู้คืนได้)
    neondb_<YYYYmmdd_HHMM>.json  — สำเนาแบบ JSON (อ่าน/ตรวจง่าย)
    neondb_<YYYYmmdd_HHMM>.txt   — สรุปจำนวนแถวแต่ละตาราง
"""
import json
import os
import sys
from datetime import date, datetime

import psycopg2
from psycopg2.extras import Json

URL = os.environ.get("DATABASE_URL", "")
if not URL:
    sys.exit("ต้องตั้ง DATABASE_URL ก่อนรัน")


def _jsonable(v):
    if isinstance(v, (datetime, date)):
        return v.isoformat()
    if isinstance(v, (bytes, bytearray)):
        return v.decode("utf-8", "replace")
    if isinstance(v, dict):
        return {k: _jsonable(x) for k, x in v.items()}
    if isinstance(v, list):
        return [_jsonable(x) for x in v]
    return v


OUTDIR = sys.argv[1] if len(sys.argv) > 1 else os.path.join(
    os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "backups")
os.makedirs(OUTDIR, exist_ok=True)
stamp = datetime.now().strftime("%Y%m%d_%H%M")
sql_path = os.path.join(OUTDIR, f"neondb_{stamp}.sql")
json_path = os.path.join(OUTDIR, f"neondb_{stamp}.json")
sum_path = os.path.join(OUTDIR, f"neondb_{stamp}.txt")

conn = psycopg2.connect(URL)
conn.set_session(readonly=True)
cur = conn.cursor()

cur.execute("""SELECT table_name FROM information_schema.tables
               WHERE table_schema='public' AND table_type='BASE TABLE' ORDER BY table_name""")
tables = [r[0] for r in cur.fetchall()]

sql_lines = [
    f"-- สำรองข้อมูล Smart Classroom (Neon) {datetime.now().isoformat(timespec='seconds')}",
    "-- วิธีกู้คืน: ให้แอปสร้างสคีมาก่อน (รัน backend หนึ่งครั้ง) แล้วรัน psql < ไฟล์นี้",
    "BEGIN;",
]
dump, summary, total = {}, [], 0

for t in tables:
    cur.execute("""SELECT column_name, data_type FROM information_schema.columns
                   WHERE table_schema='public' AND table_name=%s ORDER BY ordinal_position""", (t,))
    meta = cur.fetchall()
    cols = [m[0] for m in meta]
    json_cols = {m[0] for m in meta if m[1] in ("json", "jsonb")}
    if not cols:
        continue
    cur.execute(f'SELECT * FROM "{t}"')
    rows = cur.fetchall()
    summary.append((t, len(rows)))
    total += len(rows)
    dump[t] = [{c: _jsonable(v) for c, v in zip(cols, r)} for r in rows]
    if rows:
        collist = ", ".join(f'"{c}"' for c in cols)
        sql_lines.append(f"\n-- ตาราง {t} ({len(rows)} แถว)")
        for r in rows:
            # คอลัมน์ json/jsonb ต้องห่อด้วย Json ไม่งั้น psycopg2 adapt ไม่ได้
            args = tuple(Json(v) if (c in json_cols and isinstance(v, (dict, list))) else v
                         for c, v in zip(cols, r))
            vals = cur.mogrify(", ".join(["%s"] * len(cols)), args).decode()
            sql_lines.append(f'INSERT INTO "{t}" ({collist}) VALUES ({vals});')

sql_lines.append("\nCOMMIT;")
sql_lines.append(f"-- รวม {total} แถว จาก {len(summary)} ตาราง")

open(sql_path, "w", encoding="utf-8").write("\n".join(sql_lines))
json.dump(dump, open(json_path, "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
open(sum_path, "w", encoding="utf-8").write(
    "สำรองข้อมูล " + datetime.now().isoformat(timespec="seconds") + "\n\n"
    + "\n".join(f"{t:28} {n:>6} แถว" for t, n in summary)
    + f"\n\nรวม {total} แถว\n")

conn.close()
print(f"✓ สำเร็จ: {total} แถว จาก {len(summary)} ตาราง")
for t, n in summary:
    print(f"   {t:28} {n:>6}")
print("\nไฟล์:")
for p in (sql_path, json_path, sum_path):
    print(f"   {p}  ({os.path.getsize(p):,} bytes)")
