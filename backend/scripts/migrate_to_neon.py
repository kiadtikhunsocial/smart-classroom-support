# -*- coding: utf-8 -*-
"""
migrate_to_neon.py — ย้ายข้อมูลจาก Railway Postgres → Neon
วิธีใช้:
  python scripts/migrate_to_neon.py \
      --src "postgresql://user:pw@railway-host:5432/railway" \
      --dst "postgresql://user:pw@neon-host/neondb?sslmode=require"

- สร้าง schema (create_all) ฝั่ง Neon ก่อน
- COPY-csv เฉพาะคอลัมน์ร่วม (กัน schema drift) ตามลำดับ FK
- ข้ามตารางที่ฝั่ง Neon seed ไปแล้ว (kb_articles, settings, pm_plans) ถ้าซ้ำ key
"""
import argparse
import sys
import psycopg2
from psycopg2.extras import RealDictCursor

# ลำดับตาม FK dependency
TABLES = ["organizations", "buildings", "rooms", "users", "devices",
          "repair_tickets", "ticket_updates", "ticket_comments", "ticket_attachments",
          "scan_logs", "kb_articles", "kb_suggestions", "self_service_cases",
          "pm_plans", "pm_tasks", "settings", "chatbot_logs", "chatbot_profiles",
          "line_sessions", "sales_leads", "notification_logs"]


def common_cols(cur, table):
    """คอลัมน์ร่วมระหว่าง src/dst (เรียงตาม src)"""
    cur.execute("""
        SELECT column_name FROM information_schema.columns WHERE table_name=%s
        ORDER BY ordinal_position
    """, (table,))
    rows = cur.fetchall()
    if rows and isinstance(rows[0], dict):
        return [r["column_name"] for r in rows]
    return [r[0] for r in rows]


def copy_table(cur_src, cur_dst, table, truncate=True):
    cols_src = common_cols(cur_src, table)
    cols_dst = common_cols(cur_dst, table)
    cols = [c for c in cols_src if c in cols_dst]
    if not cols:
        print(f"  ! {table}: ไม่มีคอลัมน์ร่วม ข้าม")
        return 0
    cols_sql = ", ".join(f'"{c}"' for c in cols)
    cur_src.execute(f'SELECT {cols_sql} FROM "{table}"')
    raw_rows = cur_src.fetchall()
    if not raw_rows:
        print(f"  ~ {table}: ไม่มีข้อมูล")
        return 0
    # แปลง tuple/dict → list values ตามลำดับ cols (RealDictCursor คืน dict)
    if isinstance(raw_rows[0], dict):
        import json as _json
        rows = []
        for r in raw_rows:
            row = []
            for c in cols:
                v = r[c]
                if isinstance(v, (dict, list)):
                    v = _json.dumps(v, ensure_ascii=False)
                row.append(v)
            rows.append(row)
    else:
        rows = raw_rows
    if truncate:
        try:
            cur_dst.execute(f'TRUNCATE "{table}" RESTART IDENTITY CASCADE')
        except Exception:
            pass
    cur_dst.executemany(f'INSERT INTO "{table}" ({cols_sql}) VALUES ({" ,".join(["%s"]*len(cols))})', rows)
    print(f"  ✓ {table}: {len(rows)} แถว")
    return len(rows)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", required=True, help="Railway Postgres URL")
    ap.add_argument("--dst", required=True, help="Neon Postgres URL")
    ap.add_argument("--init-schema", action="store_true", help="สร้าง schema ฝั่ง dst ก่อน (ต้องมี create_all)")
    args = ap.parse_args()

    conn_src = psycopg2.connect(args.src)
    conn_dst = psycopg2.connect(args.dst)
    conn_src.autocommit = True
    conn_dst.autocommit = True
    cur_src = conn_src.cursor(cursor_factory=RealDictCursor)
    cur_dst = conn_dst.cursor(cursor_factory=RealDictCursor)

    if args.init_schema:
        print("สร้าง schema ฝั่ง Neon (ต้องรัน create_all จากโค้ดก่อน หรือใช้ init_db())...")

    total = 0
    for t in TABLES:
        try:
            total += copy_table(cur_src, cur_dst, t)
        except Exception as e:
            import traceback
            print(f"  ✗ {t}: {e}\n{traceback.format_exc()}")
            break  # หยุดที่ error แรก เพื่อดูสาเหตุจริง

    print(f"\nเสร็จสิ้น — ย้าย {total} แถว")
    cur_src.close(); cur_dst.close()
    conn_src.close(); conn_dst.close()


if __name__ == "__main__":
    main()
