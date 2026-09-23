# -*- coding: utf-8 -*-
"""Migrate: ตารางคำขอสมัครสมาชิก + คอลัมน์วันที่จัดซื้อของอุปกรณ์

รันซ้ำได้ ไม่ลบและไม่แก้ข้อมูลเดิม (ใช้ init_db() ที่เป็น CREATE TABLE IF NOT EXISTS
และ ADD COLUMN IF NOT EXISTS เท่านั้น)

    ในคอนเทนเนอร์:  docker compose exec backend python scripts/migrate_membership.py
    ในเครื่อง:      python backend/scripts/migrate_membership.py
"""
import os
import sys

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
for _path in ("/app", BACKEND_DIR):
    if os.path.isdir(_path) and _path not in sys.path:
        sys.path.insert(0, _path)

from sqlalchemy import text  # noqa: E402

from app.models import SessionLocal, init_db  # noqa: E402


def main() -> None:
    # สร้างตารางใหม่ที่ยังไม่มี (membership_applications) — ไม่แตะตารางเดิม
    init_db()

    db = SessionLocal()
    try:
        # devices.purchase_date — มีในโมเดลแล้ว แต่ฐานข้อมูลที่ตั้งก่อน PM Rule 3 อาจยังไม่มี
        db.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS purchase_date TIMESTAMPTZ"))

        # membership_applications — เผื่อกรณีตารางถูกสร้างจากเวอร์ชันก่อนหน้า
        for col, ddl in [
            ("reject_reason", "TEXT"),
            ("reviewed_by", "INTEGER"),
            ("reviewed_at", "TIMESTAMPTZ"),
            ("created_user_id", "INTEGER"),
            ("sheet_synced_at", "TIMESTAMPTZ"),
        ]:
            db.execute(text(
                f"ALTER TABLE membership_applications ADD COLUMN IF NOT EXISTS {col} {ddl}"
            ))

        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_membership_applications_status "
            "ON membership_applications(status)"
        ))
        db.execute(text(
            "CREATE INDEX IF NOT EXISTS ix_membership_applications_username "
            "ON membership_applications(username)"
        ))

        db.commit()
        print("MIGRATION OK")
    finally:
        db.close()


if __name__ == "__main__":
    main()