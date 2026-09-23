# -*- coding: utf-8 -*-
"""ปิดใช้งานบัญชีบทบาทเก่า teacher/student (บทบาทถูกยกเลิกแล้ว)

ผู้แจ้งซ่อมไม่ต้องมีบัญชีอีกต่อไป — ใช้หน้าแจ้งซ่อมสาธารณะ/สแกน QR ได้เลย
สคริปต์นี้ไม่ลบข้อมูล เพียงตั้ง is_active = False เพื่อคงประวัติ ticket ไว้

การใช้งาน (จาก backend/):
    python scripts/retire_legacy_roles.py            # ดูรายการก่อน (dry-run, ไม่แก้อะไร)
    python scripts/retire_legacy_roles.py --apply    # ปิดใช้งานจริง
    python scripts/retire_legacy_roles.py --apply --org 3   # เฉพาะโรงเรียน id 3
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

# ให้ import app.models ได้ทั้งตอนรันจาก backend/ และจาก backend/scripts/
BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import select  # noqa: E402

from app.models import SessionLocal, User  # noqa: E402

#: บทบาทที่ถูกยกเลิก — ต้องตรงกับ RETIRED_ROLES ใน app/main.py
RETIRED_ROLES: tuple[str, ...] = ("teacher", "student")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="ปิดใช้งานบัญชีที่ยังมีบทบาท teacher/student (ค่าเริ่มต้นคือ dry-run)"
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="แก้ฐานข้อมูลจริง (ถ้าไม่ใส่ = แสดงรายการที่จะถูกปิดเท่านั้น)",
    )
    parser.add_argument(
        "--org",
        type=int,
        default=None,
        metavar="ORG_ID",
        help="จำกัดเฉพาะ organization_id ที่ระบุ",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    db = SessionLocal()
    try:
        stmt = select(User).where(User.role.in_(RETIRED_ROLES))
        if args.org is not None:
            stmt = stmt.where(User.organization_id == args.org)
        users = db.execute(stmt.order_by(User.organization_id, User.id)).scalars().all()

        if not users:
            print("ไม่พบบัญชีบทบาท teacher/student — ไม่มีอะไรต้องทำ")
            return 0

        to_close = [u for u in users if u.is_active]
        already = len(users) - len(to_close)

        print(f"พบบัญชีบทบาทเก่าทั้งหมด {len(users)} รายการ "
              f"(ปิดอยู่แล้ว {already} / รอปิด {len(to_close)})")
        for u in users:
            state = "active" if u.is_active else "inactive"
            print(f"  id={u.id:<5} role={u.role:<8} org={u.organization_id} "
                  f"[{state}] {u.line_user_id} ({u.line_display_name or '-'})")

        if not to_close:
            print("ทุกบัญชีถูกปิดใช้งานอยู่แล้ว")
            return 0

        if not args.apply:
            print(f"\n[dry-run] จะปิดใช้งาน {len(to_close)} บัญชี "
                  f"— รันซ้ำด้วย --apply เพื่อดำเนินการจริง")
            return 0

        for u in to_close:
            u.is_active = False
        db.commit()
        print(f"\nปิดใช้งานแล้ว {len(to_close)} บัญชี (ข้อมูลและประวัติ ticket ยังอยู่ครบ)")
        return 0
    except Exception as exc:  # noqa: BLE001 — ต้องการให้ rollback แล้วแจ้งสาเหตุชัด ๆ
        db.rollback()
        print(f"ผิดพลาด: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())