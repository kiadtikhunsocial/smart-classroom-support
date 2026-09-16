#!/usr/bin/env python3
"""seed_admin.py — ล้างข้อมูลทั้งหมด แล้วสร้างบัญชี super_admin เริ่มต้น

⚠ สคริปต์นี้ลบข้อมูล "ทุกตาราง" — สำรองฐานข้อมูลก่อนทุกครั้ง:
      DATABASE_URL='<neon>' PYTHONPATH=. python scripts/backup_db.py

ใช้:
    # ในเครื่อง (รันจากโฟลเดอร์ backend)
    DATABASE_URL='<neon>' JWT_SECRET=x PYTHONPATH=. python scripts/seed_admin.py --yes
    # ใน container
    python scripts/seed_admin.py --yes

กำหนดรหัสผ่านเองได้ด้วย env `SEED_ADMIN_PASSWORD`
(ถ้าไม่ตั้งจะใช้ค่าเริ่มต้นด้านล่าง — ต้องเปลี่ยนทันทีหลัง login ครั้งแรก)
"""
import os
import sys

# รองรับทั้งใน container (/app) และในเครื่อง (โฟลเดอร์ backend/)
BASE_DIR = "/app" if os.path.isdir("/app") else os.path.dirname(
    os.path.dirname(os.path.abspath(__file__))
)
sys.path.insert(0, BASE_DIR)
os.chdir(BASE_DIR)

from app.models import Base, SessionLocal, User  # noqa: E402
from app.main import hash_password  # noqa: E402

DEFAULT_USERNAME = "iwasuperadmin"
DEFAULT_PASSWORD = "IwaScr2026!admin"


def reset_and_seed(password: str) -> None:
    db = SessionLocal()
    try:
        # ลบตามลำดับ FK: sorted_tables เรียง "แม่ → ลูก" จึงต้องวนย้อนกลับ
        # (เดิมไล่ลบเป็นรายชื่อตารางแบบ hardcode ทำให้ตกตารางลูกที่เพิ่มมาภายหลัง
        #  เช่น ticket_comments / ticket_attachments แล้ว DELETE ติด FK error)
        tables = list(reversed(Base.metadata.sorted_tables))
        for table in tables:
            db.execute(table.delete())
        db.commit()
        print(f"✅ ลบข้อมูลแล้ว {len(tables)} ตาราง")

        # super_admin ไม่สังกัดโรงเรียน → เห็นข้อมูลทุกโรงเรียน
        admin = User(
            line_user_id=DEFAULT_USERNAME,
            line_display_name="ผู้ดูแลระบบ IWA",
            role="super_admin",
            is_active=True,
            password_hash=hash_password(password),
        )
        db.add(admin)
        db.commit()
        print(f"✅ สร้าง super_admin แล้ว: username={DEFAULT_USERNAME}")
        print("⚠ เปลี่ยนรหัสผ่านที่หน้า 'โปรไฟล์' ทันทีหลัง login ครั้งแรก")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    confirmed = "--yes" in sys.argv or os.environ.get("CONFIRM_RESET", "").lower() == "yes"
    if not confirmed:
        print("⚠ สคริปต์นี้จะลบข้อมูลทั้งหมดในฐานข้อมูลที่ DATABASE_URL ชี้ไป")
        print("   ยืนยันด้วย:  python scripts/seed_admin.py --yes   (หรือ CONFIRM_RESET=yes)")
        sys.exit(1)
    reset_and_seed(os.environ.get("SEED_ADMIN_PASSWORD") or DEFAULT_PASSWORD)