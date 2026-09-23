"""เติมข้อมูลประกัน/จัดซื้อแบบ mockup ให้อุปกรณ์ที่ยังว่าง

ปัญหาที่แก้: หน้า "ตรวจสอบประกันสินค้า" (GET /api/public/warranty/{code}) ค้นเจอ
เครื่องแล้ว แต่ตอบ warranty_status = "unknown" เพราะอุปกรณ์ชุดเดโมเก่า (seed_db.py)
ถูกสร้างก่อนที่จะมีฟิลด์ purchase_date / warranty_until จึงไม่มีวันสิ้นสุดประกัน
ผู้ใช้จึงเห็นว่า "ตรวจสอบประกันไม่ได้"

สคริปต์นี้:
  • แตะเฉพาะเครื่องที่ purchase_date หรือ warranty_until เป็น NULL — ไม่ทับข้อมูลเดิม
  • สุ่มด้วย seed จาก device_id จึงได้ผลเหมือนกันทุกครั้งที่รันซ้ำ (idempotent)
  • กระจายสถานะให้ครบทุกกรณีที่หน้าเว็บต้องรองรับ: อยู่ในประกัน / ใกล้หมด / หมดแล้ว
  • เติมหมายเหตุทะเบียนทรัพย์สิน (เลขครุภัณฑ์ งบประมาณ ผู้ขาย เงื่อนไขประกัน)
    ให้เครื่องที่ยังไม่มี เพื่อให้แผงรายละเอียดอุปกรณ์มีข้อมูลให้ดู

วิธีใช้ (จากรากโปรเจกต์ ใช้ .env เดียวกับแอปอัตโนมัติ):
    backend/.venv/Scripts/python.exe backend/scripts/backfill_warranty_mockup.py --dry-run
    backend/.venv/Scripts/python.exe backend/scripts/backfill_warranty_mockup.py --yes
"""

from __future__ import annotations

import argparse
import hashlib
import os
import pathlib
import random
import sys
from datetime import datetime, timedelta, timezone
from typing import Optional

ROOT = pathlib.Path(__file__).resolve().parents[2]


def load_dotenv() -> None:
    """อ่าน .env ที่รากโปรเจกต์ โดยไม่ทับ env ที่ตั้งมาแล้ว"""
    env_file = ROOT / ".env"
    if not env_file.exists():
        return
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


load_dotenv()
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import or_, select  # noqa: E402

from app.models import Device, Organization, Room, SessionLocal  # noqa: E402
from demo_safety import require_local_demo_database  # noqa: E402

try:  # เกณฑ์ "ใกล้หมดประกัน" ต้องเป็นตัวเดียวกับ PM Rule 2 และหน้าเว็บ
    from app import pm_rules

    WARN_DAYS = int(pm_rules.WARRANTY_WARN_DAYS)
except Exception:  # pragma: no cover - ใช้ค่าเดียวกับที่ frontend ตั้งไว้
    WARN_DAYS = 30

#: อายุประกันมาตรฐานตามสัญญาจัดซื้อครุภัณฑ์ (ปี -> วัน)
WARRANTY_SPANS = (1095, 1460, 1825)

BUDGET_SOURCES = (
    "งบอุดหนุนรายหัว",
    "งบลงทุน (ครุภัณฑ์การศึกษา)",
    "เงินรายได้สถานศึกษา",
    "งบอุดหนุน อบจ./เทศบาล",
    "เงินบริจาค/ผ้าป่าเพื่อการศึกษา",
)

VENDORS = (
    ("บจก. ทิปส์ เอ็ดดูเคชั่น ซัพพลาย", "02-123-4567"),
    ("บจก. สมาร์ทคลาส เทคโนโลยี", "02-234-5678"),
    ("หจก. ไอทีภูมิภาค เซอร์วิส", "043-345-678"),
    ("บจก. เน็ตเวิร์ค โซลูชั่น ไทย", "053-456-789"),
)

WARRANTY_TERMS = (
    "on-site 3 ปี (อะไหล่ + ค่าแรง)",
    "on-site 2 ปี ปีที่ 3 ส่งซ่อมที่ศูนย์",
    "carry-in 1 ปี",
    "on-site 5 ปี เฉพาะพาเนล/จอ",
)


def seed_of(device_id: str) -> int:
    return int(hashlib.sha1(device_id.encode("utf-8")).hexdigest()[:8], 16)


def thai_fiscal_year(d: datetime) -> int:
    """ปีงบประมาณไทย (พ.ศ.) — ปีงบเริ่ม 1 ตุลาคม"""
    year = d.year + 543
    return year + 1 if d.month >= 10 else year


def asset_notes(
    device: Device,
    purchased: datetime,
    warranty: datetime,
    room_label: Optional[str],
    org_name: Optional[str],
) -> str:
    """หมายเหตุทะเบียนทรัพย์สิน — รูปแบบเดียวกับ seed_mockup_5_schools.py"""
    seed = seed_of(f"notes|{device.device_id}")
    budget = BUDGET_SOURCES[seed % len(BUDGET_SOURCES)]
    vendor, tel = VENDORS[(seed // 7) % len(VENDORS)]
    term = WARRANTY_TERMS[(seed // 13) % len(WARRANTY_TERMS)]
    fiscal = thai_fiscal_year(purchased)
    asset_no = f"{7440 + (seed % 60):04d}-{(seed // 3) % 1000:03d}/{fiscal}"

    lines = [
        f"เลขครุภัณฑ์ {asset_no}",
        f"งบประมาณ: {budget} ปีงบ {fiscal}",
        f"ผู้ขาย/ผู้ติดตั้ง: {vendor} โทร {tel}",
        f"เงื่อนไขประกัน: {term}",
        f"ตรวจรับเมื่อ {purchased:%d/%m/%Y} · ประกันถึง {warranty:%d/%m/%Y}",
    ]
    if device.serial_number:
        lines.append(f"หมายเลขสินค้า (serial): {device.serial_number}")
    if room_label:
        lines.append(f"ติดตั้งที่ {room_label}" + (f" · {org_name}" if org_name else ""))
    lines.append("ข้อมูลตัวอย่างสำหรับเดโม (mockup)")
    return "\n".join(lines)


def plan_dates(device_id: str, now: datetime, purchased: Optional[datetime]) -> tuple[datetime, datetime, str]:
    """คืน (วันจัดซื้อ, วันสิ้นสุดประกัน, สถานะที่ตั้งใจให้เป็น)"""
    rnd = random.Random(seed_of(device_id))

    if purchased is None:
        purchased = now - timedelta(days=rnd.randint(200, 1800))
    elif purchased.tzinfo is None:
        purchased = purchased.replace(tzinfo=timezone.utc)

    bucket = rnd.randint(0, 9)
    if bucket == 0:  # 10% หมดประกันแล้ว — ให้หน้าเว็บมีเคสสีแดงให้เห็น
        warranty = now - timedelta(days=rnd.randint(40, 400))
        status = "expired"
    elif bucket in (1, 2):  # 20% ใกล้หมด — ต้องอยู่ในกรอบ WARN_DAYS
        warranty = now + timedelta(days=rnd.randint(3, max(3, WARN_DAYS - 2)))
        status = "expiring"
    else:  # ที่เหลืออยู่ในประกันตามอายุสัญญามาตรฐาน
        warranty = purchased + timedelta(days=rnd.choice(WARRANTY_SPANS))
        if (warranty - now).days <= WARN_DAYS:
            # ของเก่าเกินกว่าจะยังอยู่ในประกัน -> ต่อ MA ให้ เพื่อให้สถานะตรงกับที่ตั้งใจ
            warranty = now + timedelta(days=rnd.randint(WARN_DAYS + 30, 900))
        status = "active"

    # วันจัดซื้อต้องมาก่อนวันสิ้นสุดประกันเสมอ
    if purchased >= warranty:
        purchased = warranty - timedelta(days=rnd.choice(WARRANTY_SPANS))
    return purchased, warranty, status


def main() -> int:
    parser = argparse.ArgumentParser(description="เติมข้อมูลประกันแบบ mockup ให้อุปกรณ์ที่ยังว่าง")
    parser.add_argument("--dry-run", action="store_true", help="แสดงผลที่จะเปลี่ยน โดยไม่บันทึก")
    parser.add_argument("--yes", action="store_true", help="บันทึกทันทีโดยไม่ถามยืนยัน")
    parser.add_argument(
        "--force-notes",
        action="store_true",
        help="เขียนหมายเหตุทะเบียนทรัพย์สินทับของเดิมที่เป็นข้อความเดโมบรรทัดเดียว",
    )
    args = parser.parse_args()

    url = os.environ.get("DATABASE_URL", "")
    host = url.split("@", 1)[1].split("/", 1)[0] if "@" in url else "(ค่าเริ่มต้น localhost:5432)"
    print(f"ฐานข้อมูล: {host}")
    print(f"เกณฑ์ใกล้หมดประกัน: {WARN_DAYS} วัน")

    if not args.dry_run and not args.yes:
        print("ต้องใส่ --yes เพื่อยืนยันการเขียนข้อมูล หรือ --dry-run เพื่อดูผลก่อน")
        return 2

    if not args.dry_run:
        require_local_demo_database()

    now = datetime.now(timezone.utc)
    db = SessionLocal()
    changed = {"active": 0, "expiring": 0, "expired": 0}
    notes_filled = 0

    try:
        rows = db.execute(
            select(Device)
            .where(or_(Device.warranty_until.is_(None), Device.purchase_date.is_(None)))
            .order_by(Device.device_id)
        ).scalars().all()

        print(f"อุปกรณ์ที่ต้องเติมข้อมูล: {len(rows)} เครื่อง")

        for device in rows:
            purchased, warranty, status = plan_dates(device.device_id, now, device.purchase_date)
            device.purchase_date = purchased
            device.warranty_until = warranty
            changed[status] += 1

            current_notes = (device.notes or "").strip()
            if args.force_notes or "เลขครุภัณฑ์" not in current_notes:
                room = db.get(Room, device.room_id) if device.room_id else None
                org = db.get(Organization, device.organization_id) if device.organization_id else None
                room_label = None
                if room is not None:
                    room_label = f"{room.name} ({room.code})" if room.code else room.name
                device.notes = asset_notes(
                    device, purchased, warranty, room_label, org.name if org else None
                )
                notes_filled += 1

            print(
                f"  {device.device_id:<34} serial={device.serial_number or '-':<22}"
                f" ซื้อ {purchased:%d/%m/%Y} ประกันถึง {warranty:%d/%m/%Y} [{status}]"
            )

        if args.dry_run:
            db.rollback()
            print("\n--dry-run: ไม่ได้บันทึกอะไรลงฐานข้อมูล")
        else:
            db.commit()
            print("\nบันทึกแล้ว")

        print(
            f"สรุป: อยู่ในประกัน {changed['active']} · ใกล้หมด {changed['expiring']}"
            f" · หมดแล้ว {changed['expired']} · เติมหมายเหตุ {notes_filled} เครื่อง"
        )
    except Exception as exc:  # pragma: no cover - รายงานแล้วออกด้วย exit code
        db.rollback()
        print(f"ผิดพลาด: {exc}", file=sys.stderr)
        return 1
    finally:
        db.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
