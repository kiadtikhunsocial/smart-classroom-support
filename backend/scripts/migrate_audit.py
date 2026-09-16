# -*- coding: utf-8 -*-
"""scripts/migrate_audit.py — migration สำหรับ Audit Log (§40) + KB แยกตามโรงเรียน

ทำให้ฐานข้อมูลตรงกับ ``app/models.py`` หลังงาน §40:

* ตาราง ``audit_logs``            — สร้างด้วย create_all ถ้ายังไม่มี
* ``kb_articles.organization_id`` — บทความ KB เฉพาะโรงเรียน (None = บทความส่วนกลาง)
* ตรวจ schema drift ทุกตารางในโมเดล แล้วรายงานคอลัมน์ที่ยังขาด

รันจากเครื่องนักพัฒนาได้ตรง ๆ::

    backend/.venv/Scripts/python.exe backend/scripts/migrate_audit.py

ปลายทางคือ ``DATABASE_URL`` เดียวกับที่แอปใช้ สคริปต์นี้ idempotent:
รันซ้ำได้ ไม่ลบและไม่แก้ข้อมูลเดิม (ใช้ ADD COLUMN IF NOT EXISTS เท่านั้น)

exit code 0 = ฐานข้อมูลตรงกับโมเดล, 1 = ยังมีคอลัมน์ที่ขาดและต้องเพิ่ม patch
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import inspect, text  # noqa: E402

from app.models import Base, DATABASE_URL, SessionLocal, engine, init_db  # noqa: E402


def _safe_url(url: str) -> str:
    """ซ่อนรหัสผ่านก่อน print — log ของ CI ไม่ควรมี credential"""
    return re.sub(r"://([^:/@]+):[^@]+@", r"://\1:***@", url)


# คอลัมน์ที่เพิ่มเข้ามาหลังฐานข้อมูลถูกสร้างครั้งแรก (idempotent ด้วย IF NOT EXISTS)
COLUMN_PATCHES: list[tuple[str, str, str]] = [
    (
        "kb_articles",
        "organization_id",
        "INTEGER REFERENCES organizations(id) ON DELETE CASCADE",
    ),
    # §38 ตกค้าง: ตาราง pm_tasks ถูกสร้างก่อนที่โมเดลจะเพิ่มชื่อผู้ทำ PM
    ("pm_tasks", "done_by", "VARCHAR(128)"),
]

# index ที่ create_all ไม่ได้สร้างให้ เพราะตารางมีอยู่ก่อนแล้ว
INDEX_PATCHES: list[tuple[str, str]] = [
    (
        "ix_kb_articles_organization_id",
        "CREATE INDEX IF NOT EXISTS ix_kb_articles_organization_id "
        "ON kb_articles(organization_id)",
    ),
]


def _missing_columns() -> dict[str, list[str]]:
    """คืน {ตาราง: [คอลัมน์ในโมเดลที่ยังไม่มีในฐานข้อมูล]} — ข้ามตารางที่ยังไม่ถูกสร้าง"""
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    drift: dict[str, list[str]] = {}
    for table_name, table in Base.metadata.tables.items():
        if table_name not in existing_tables:
            continue
        db_cols = {c["name"] for c in inspector.get_columns(table_name)}
        missing = [c.name for c in table.columns if c.name not in db_cols]
        if missing:
            drift[table_name] = missing
    return drift


def main() -> int:
    print(f"DATABASE_URL = {_safe_url(DATABASE_URL)}")

    # 1) สร้างตารางที่ยังไม่มี (audit_logs, ...) — create_all ไม่แก้ตารางเดิม
    before = set(inspect(engine).get_table_names())
    init_db()
    after = set(inspect(engine).get_table_names())
    created = sorted(after - before)
    print(f"tables created: {created if created else 'ไม่มี (ครบอยู่แล้ว)'}")

    # 2) เพิ่มคอลัมน์ที่ขาด + index
    db = SessionLocal()
    try:
        for table, column, ddl in COLUMN_PATCHES:
            if table not in after:
                print(f"ข้าม {table}.{column} — ยังไม่มีตาราง {table}")
                continue
            db.execute(
                text(f"ALTER TABLE {table} ADD COLUMN IF NOT EXISTS {column} {ddl}")
            )
            print(f"column ok: {table}.{column}")

        for name, ddl in INDEX_PATCHES:
            db.execute(text(ddl))
            print(f"index ok: {name}")

        db.commit()
    finally:
        db.close()

    # 3) ตรวจว่าฐานข้อมูลตรงกับโมเดลจริงหรือยัง
    drift = _missing_columns()
    if drift:
        print("\n⚠ ยังมีคอลัมน์ที่ขาด (ต้องเพิ่มใน COLUMN_PATCHES):")
        for table, cols in sorted(drift.items()):
            print(f"  - {table}: {', '.join(cols)}")
        return 1

    print("\n✓ schema ตรงกับ app/models.py แล้ว")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())