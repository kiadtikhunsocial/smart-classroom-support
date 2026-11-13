# -*- coding: utf-8 -*-
"""scripts/migrate_ticket_indexes.py — เพิ่ม index ให้รายการใบงานแบบแบ่งหน้า

``create_all()`` สร้าง index ให้เฉพาะตารางที่สร้างใหม่ ฐานข้อมูลที่มีอยู่แล้ว
(local, Neon) จึงต้องรันสคริปต์นี้หนึ่งครั้ง::

    python scripts/migrate_ticket_indexes.py

ปลายทางคือ ``DATABASE_URL`` เดียวกับที่แอปใช้ สคริปต์ idempotent: รันซ้ำได้
ไม่แก้หรือลบข้อมูล — ``CREATE INDEX IF NOT EXISTS`` อย่างเดียว
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

from sqlalchemy import text  # noqa: E402

from app.models import DATABASE_URL, engine  # noqa: E402

INDEXES: list[tuple[str, str]] = [
    # ตรงกับ ORDER BY ของ GET /api/tickets: created_at DESC, ticket_id DESC
    ("ix_repair_tickets_created_at_id",
     "CREATE INDEX IF NOT EXISTS ix_repair_tickets_created_at_id "
     "ON repair_tickets (created_at DESC, ticket_id DESC)"),
]


def _safe_url(url: str) -> str:
    """ซ่อนรหัสผ่านก่อน print"""
    return re.sub(r"://([^:/@]+):[^@]+@", r"://\1:***@", url)


def main() -> None:
    print(f"ปลายทาง: {_safe_url(DATABASE_URL)}")
    with engine.begin() as conn:
        for name, ddl in INDEXES:
            conn.execute(text(ddl))
            print(f"  ✓ {name}")
    print("เสร็จ")


if __name__ == "__main__":
    main()
