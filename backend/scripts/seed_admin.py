#!/usr/bin/env python3
"""seed_admin.py — ลบข้อมูลเดิมทั้งหมด แล้วสร้าง super_admin + องค์กรเริ่มต้น
ใช้: python seed_admin.py  (รันใน container)
"""
import os
import sys
sys.path.insert(0, "/app")
os.chdir("/app")

from sqlalchemy import text
from app.models import Base, User, Organization, SessionLocal, engine
from app.main import hash_password


def reset_and_seed() -> None:
    db = SessionLocal()
    try:
        # ลบทุกอย่างตามลำดับ FK
        db.execute(text("DELETE FROM ticket_updates"))
        db.execute(text("DELETE FROM repair_tickets"))
        db.execute(text("DELETE FROM scan_logs"))
        db.execute(text("DELETE FROM devices"))
        db.execute(text("DELETE FROM rooms"))
        db.execute(text("DELETE FROM users"))
        db.execute(text("DELETE FROM organizations"))
        db.commit()
        print("✅ ลบข้อมูลทั้งหมดแล้ว")

        # สร้าง super_admin (ไม่มี org — เห็นทุกโรงเรียน)
        admin = User(
            line_user_id="iwasuperadmin",
            line_display_name="ผู้ดูแลระบบ IWA",
            role="super_admin",
            is_active=True,
            password_hash=hash_password("IwaScr2026!admin"),
        )
        db.add(admin)
        db.commit()
        print("✅ สร้าง super_admin แล้ว: username=iwasuperadmin / password=IwaScr2026!admin")
    finally:
        db.close()


if __name__ == "__main__":
    reset_and_seed()
