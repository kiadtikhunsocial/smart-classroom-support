# -*- coding: utf-8 -*-
"""scripts/migrate_pm.py — migration สำหรับ PM Rule Engine (Blueprint §38)

ทำให้ฐานข้อมูลตรงกับ ``app/models.py`` หลังเพิ่มของ §38:

* ``devices.purchase_date``      — ใช้คิดอายุอุปกรณ์ใน PM Rule 3
* ตาราง ``device_health_flags``  — ผลลัพธ์ของ Rule Engine (สร้างด้วย create_all)
* ตารางอื่นที่ยังไม่มีในฐานข้อมูล — create_all สร้างเฉพาะตารางที่หายไป

ต่างจาก ``scripts/migrate.py`` ที่ hardcode ``/app`` ไว้สำหรับรันในคอนเทนเนอร์
ไฟล์นี้รันจากเครื่องนักพัฒนาได้ตรง ๆ::

    backend/.venv/Scripts/python.exe backend/scripts/migrate_pm.py

ปลายทางคือ ``DATABASE_URL`` เดียวกับที่แอปใช้ (ไม่มีค่า → localhost:5432)
สคริปต์นี้ idempotent: รันซ้ำได้ ไม่ลบหรือแก้ข้อมูลเดิม
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import inspect, text  # noqa: E402

from app.models import DATABASE_URL, SessionLocal, engine, init_db  # noqa: E402


def _safe_url(url: str) -> str:
    """ซ่อนรหัสผ่านก่อน print — log ของ CI ไม่ควรมี credential"""
    return re.sub(r"://([^:/@]+):[^@]+@", r"://\1:***@", url)


# คอลัมน์ที่เพิ่มเข้ามาหลังฐานข้อมูลถูกสร้างครั้งแรก (idempotent ด้วย IF NOT EXISTS)
COLUMN_PATCHES: list[tuple[str, str, str]] = [
    ("devices", "purchase_date", "TIMESTAMPTZ"),
]

# index ที่ create_all ไม่ได้สร้างให้ (ตารางมีอยู่ก่อนแล้ว)
INDEX_PATCHES: list[tuple[str, str]] = [
    (
        "ix_device_health_flags_open",
        "CREATE INDEX IF NOT EXISTS ix_device_health_flags_open "
        "ON device_health_flags(device_id, rule_code) WHERE status = 'open'",
    ),
]


def main() -> int:
    print(f"DATABASE_URL = {_safe_url(DATABASE_URL)}")

    # 1) สร้างตารางที่ยังไม่มี (device_health_flags, pm_plans, pm_tasks, ...)
    before = set(inspect(engine).get_table_names())
    init_db()
    after = set(inspect(engine).get_table_names())
    created = sorted(after - before)
    print(f"tables created: {created if created else 'ไม่มี (ครบอยู่แล้ว)'}")

    # 2) เพิ่มคอลัมน์ที่ขาด
    db = SessionLocal()
    try:
        for table, column, ddl in COLUMN_PATCHES:
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

    # 3) ตรวจผลว่าตรงกับโมเดลจริง
    insp = inspect(engine)
    device_columns = {c["name"] for c in insp.get_columns("devices")}
    missing: list[str] = []
    if "purchase_date" not in device_columns:
        missing.append("devices.purchase_date")
    if "device_health_flags" not in insp.get_table_names():
        missing.append("table device_health_flags")

    if missing:
        print("MIGRATION FAILED — ยังขาด: " + ", ".join(missing))
        return 1

    flag_columns = sorted(c["name"] for c in insp.get_columns("device_health_flags"))
    print(f"device_health_flags columns: {flag_columns}")
    print("MIGRATION OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())