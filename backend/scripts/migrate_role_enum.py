# -*- coding: utf-8 -*-
"""migrate_role_enum.py — เติมค่าที่ขาดใน enum user_role_enum ของ PostgreSQL

ทำไมต้องมี
----------
app/models.py ประกาศ role เป็น SAEnum(..., create_type=False) 7 ค่า
    owner, admin, admin_school, teacher, it_support, student, super_admin
แต่ฐานข้อมูลที่ตั้งก่อนหน้านี้อาจมีแค่ 5 ค่า (ไม่มี owner / admin_school) ทำให้
การสร้างหรือแก้ผู้ใช้บทบาทเหล่านั้นล้มด้วย
    DataError: invalid input value for enum user_role_enum: "admin_school"
scripts/migrate.py มีคำสั่งนี้อยู่แล้วแต่ hardcode /app (ใช้ได้แต่ในคอนเทนเนอร์)

ความปลอดภัย
-----------
* เพิ่มค่าเท่านั้น (ADD VALUE IF NOT EXISTS) — ไม่แก้ ไม่ลบ ไม่ย้ายข้อมูลใด ๆ
* รันซ้ำได้ ค่าที่มีอยู่แล้วจะถูกข้าม
* ค่าเริ่มต้นเป็น dry-run — ต้องใส่ --apply จึงจะเขียนจริง
* PostgreSQL ไม่รองรับการลบค่า enum ภายหลัง จึงถือเป็นการเปลี่ยนแบบย้อนกลับไม่ได้

การใช้งาน (จาก root ของโปรเจกต์)
    backend\\.venv\\Scripts\\python.exe backend/scripts/migrate_role_enum.py
    backend\\.venv\\Scripts\\python.exe backend/scripts/migrate_role_enum.py --apply
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))
# ให้อ่าน .env ของ backend เจอเหมือนสคริปต์อื่นในโฟลเดอร์นี้
os.chdir(BACKEND_DIR)

from sqlalchemy import create_engine, text  # noqa: E402

from app.models import ACTIVE_ROLES, DATABASE_URL, LEGACY_ROLES  # noqa: E402

ENUM_NAME = "user_role_enum"

#: ค่าที่ enum ต้องมีให้ครบ — ตรงกับ SAEnum ใน app/models.py (User.role)
#: LEGACY_ROLES ยังต้องอยู่ เพราะแถวเก่าในตาราง users ยังใช้ค่านี้
REQUIRED_ROLES: tuple[str, ...] = tuple(ACTIVE_ROLES) + tuple(LEGACY_ROLES)


def _safe_url(url: str) -> str:
    """ซ่อนรหัสผ่านก่อนพิมพ์สตริงเชื่อมต่อ"""
    if "//" not in url or "@" not in url:
        return url
    head, tail = url.split("//", 1)
    creds, host = tail.split("@", 1)
    user = creds.split(":", 1)[0]
    return f"{head}//{user}:***@{host}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=f"เติมค่าที่ขาดใน enum {ENUM_NAME} (ค่าเริ่มต้นคือ dry-run)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="เขียนฐานข้อมูลจริง (ถ้าไม่ใส่ = แสดงค่าที่จะเพิ่มเท่านั้น)",
    )
    return parser.parse_args()


def read_labels(conn) -> list[str]:
    return list(
        conn.execute(
            text(
                "SELECT e.enumlabel FROM pg_type t "
                "JOIN pg_enum e ON e.enumtypid = t.oid "
                "WHERE t.typname = :name ORDER BY e.enumsortorder"
            ),
            {"name": ENUM_NAME},
        ).scalars()
    )


def main() -> int:
    args = parse_args()
    print(f"DATABASE_URL = {_safe_url(DATABASE_URL)}")

    # ALTER TYPE ... ADD VALUE ต้องไม่อยู่ใน transaction ที่ยังไม่ commit → ใช้ AUTOCOMMIT
    engine = create_engine(DATABASE_URL, future=True)
    try:
        with engine.connect().execution_options(isolation_level="AUTOCOMMIT") as conn:
            existing = read_labels(conn)
            if not existing:
                print(f"ไม่พบ type {ENUM_NAME} ในฐานข้อมูล — ตรวจ DATABASE_URL ก่อน", file=sys.stderr)
                return 1

            print(f"ค่าปัจจุบัน ({len(existing)}): {existing}")
            missing = [r for r in REQUIRED_ROLES if r not in existing]
            if not missing:
                print("ครบทุกค่าที่โมเดลต้องการแล้ว — ไม่มีอะไรต้องทำ")
                return 0

            print(f"ค่าที่ขาด ({len(missing)}): {missing}")
            if not args.apply:
                print("\n[dry-run] ยังไม่เขียนอะไร — รันซ้ำด้วย --apply เพื่อเพิ่มค่าเหล่านี้")
                return 0

            for role in missing:
                # ค่าใน DDL ผูกเป็น parameter ไม่ได้ (PG ไม่รองรับ) จึงตรวจ allow-list ก่อน
                if role not in REQUIRED_ROLES or not role.replace("_", "").isalnum():
                    print(f"ข้ามค่าที่ไม่ปลอดภัย: {role!r}", file=sys.stderr)
                    continue
                conn.execute(
                    text(f"ALTER TYPE {ENUM_NAME} ADD VALUE IF NOT EXISTS '{role}'")
                )
                print(f"  + เพิ่ม {role}")

            print(f"\nค่าหลังแก้: {read_labels(conn)}")
            print("MIGRATION OK")
            return 0
    finally:
        engine.dispose()


if __name__ == "__main__":
    raise SystemExit(main())