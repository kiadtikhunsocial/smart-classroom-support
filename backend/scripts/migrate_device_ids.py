"""migrate_device_ids.py — ย้ายรหัสอุปกรณ์เก่าให้เป็นรูปแบบเดียวกับที่ API สร้างจริง

รูปแบบเป้าหมาย (ตรงกับ generate_device_id ใน backend/app/main.py):
    <รหัสโรงเรียน>-<อาคาร>-<ห้อง>-<ประเภท>-<ลำดับ 2 หลัก>
    เช่น SCHM01-B1-101-DISP-01

ทำไมต้องมีสคริปต์นี้
--------------------
ข้อมูล mockup ในฐานข้อมูลยังเป็น DEV-2026-0101 / DEV-2024-00301 ซึ่งเป็นรูปแบบเก่าที่
ไม่ผูกกับโรงเรียน อาคาร ห้อง หรือประเภทอุปกรณ์ ส่วน seed จะข้ามอุปกรณ์ที่มีรหัสอยู่แล้ว
จึงไม่เคยเขียนทับให้เอง

ข้อควรระวังที่สคริปต์นี้จัดการให้
---------------------------------
· devices.device_id ถูกอ้างเป็น "สตริง" จากหลายตาราง และ FK ทุกตัวเป็น
  ON UPDATE NO ACTION (ไม่ CASCADE, ไม่ DEFERRABLE) → แก้ค่าที่ตารางแม่ตรง ๆ จะติด FK
  ทันที สคริปต์จึงเก็บนิยาม FK เดิมไว้ DROP ทิ้ง อัปเดตแม่+ลูก แล้ว ADD กลับด้วย
  นิยามเดิมทุกตัว ทั้งหมดอยู่ในทรานแซกชันเดียว (ล้มเหลว = ย้อนกลับหมด)
· เขียนสองจังหวะ (เก่า → MIGD.n → ใหม่) กันชน unique index ของ devices.device_id
  ระหว่างทาง เพราะรหัสใหม่ของเครื่องหนึ่งอาจเท่ากับรหัสเก่าของอีกเครื่อง
· อัปเดตคอลัมน์ device_id ของทุกตารางที่มี (ค้นจาก information_schema ไม่ฮาร์ดโค้ด)
  รวมถึง audit_logs.entity_id ของ entity_type='device' และรหัสที่ฝังใน
  audit_logs.old_value / new_value (แทนเฉพาะค่าที่อยู่ในเครื่องหมายคำพูดเต็มตัว)
· ตรวจความยาวไม่เกินขนาดคอลัมน์ และข้ามเครื่องที่อยู่ในรูปแบบใหม่ถูกต้องแล้ว

ใช้
---
    python backend/scripts/migrate_device_ids.py           # ดูผลล่วงหน้า ไม่แก้อะไร
    python backend/scripts/migrate_device_ids.py --apply   # เขียนจริง
"""

from __future__ import annotations

import argparse
import os
import re
import sys
from collections import defaultdict
from typing import Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sqlalchemy import text  # noqa: E402

from app.models import SessionLocal  # noqa: E402

#: คำนำหน้าชั่วคราวระหว่างเขียนสองจังหวะ — ต้องไม่ชนรหัสจริงใด ๆ
TEMP_PREFIX = "MIGD."

#: ต้องตรงกับ DEVICE_TYPE_CODES ใน backend/app/main.py
DEVICE_TYPE_CODES = {
    "Interactive Display": "DISP",
    "Computer AIO": "COMP",
    "Computer Notebook": "COMP",
    "Computer Tablet": "COMP",
    "Computer Desktop": "COMP",
    "Router": "RTR",
    "Access Point": "AP",
    "Switch": "SW",
    "Speaker": "SPK",
    "Camera": "CAM",
    "Visualizer": "CAM",
    "Microphone": "MIC",
    "UPS": "UPS",
    "Printer": "PRN",
    "Projector": "PJT",
    "Software (Picaro)": "SW",
    "Software (Phonics Hero)": "SW",
    "Other": "DEV",
}


def device_type_code(device_type: Optional[str]) -> str:
    """mirror ของ _device_type_code ใน app/main.py"""
    return DEVICE_TYPE_CODES.get(device_type or "", "DEV")


def org_code_token(code: Optional[str], org_id: Optional[int]) -> str:
    """mirror ของ _org_code_token ใน app/main.py"""
    token = re.sub(r"[^A-Za-z0-9]", "", (code or "")).upper()[:8]
    if token:
        return token
    return f"ORG{org_id}" if org_id is not None else "SCH"


def building_code_token(raw: Optional[str], floor: Optional[str]) -> str:
    """mirror ของ _building_code ใน app/main.py"""
    if raw:
        s = re.sub(r"[^\u0E00-\u0E7Fa-zA-Z0-9]", "", str(raw)).strip()
        if not s:
            return "B0"
        num = re.search(r"[0-9]+", str(raw))
        if num:
            return f"B{num.group()[:2]}"
        if floor:
            fnum = re.search(r"[0-9]+", str(floor))
            if fnum:
                return f"B{fnum.group()[:2]}"
        latin = re.findall(r"[a-zA-Z]", str(raw))
        if latin:
            return "B" + "".join(latin[:2]).upper()
        return "B" + s[:2].upper()
    if floor:
        fnum = re.search(r"[0-9]+", str(floor))
        if fnum:
            return f"B{fnum.group()[:2]}"
    return "B0"


def device_id_prefix(org_code: Optional[str], org_id: Optional[int],
                     room_code: Optional[str], building: Optional[str],
                     floor: Optional[str], device_type: Optional[str]) -> str:
    """prefix ของรหัสอุปกรณ์ — ตรงกับ generate_device_id ของ API

    ไม่มีห้อง → อาคาร B0 และห้อง R000 เหมือนฝั่ง API
    """
    if room_code is None and building is None and floor is None:
        building_token, room_token = "B0", "R000"
    else:
        building_token = building_code_token(building, floor)
        room_token = room_code or "R000"
    return (f"{org_code_token(org_code, org_id)}-{building_token}-{room_token}-"
            f"{device_type_code(device_type)}-")


# ---------------------------------------------------------------------------
# สำรวจสคีมา
# ---------------------------------------------------------------------------


def device_id_columns(db) -> list[tuple[str, str]]:
    """ทุกตาราง (ยกเว้น devices) ที่มีคอลัมน์ชื่อ device_id เก็บรหัสอุปกรณ์เป็นสตริง"""
    rows = db.execute(text(
        "SELECT table_name, column_name FROM information_schema.columns "
        "WHERE table_schema = 'public' AND column_name = 'device_id' "
        "  AND table_name <> 'devices' AND data_type IN ('character varying', 'text') "
        "ORDER BY table_name"
    )).all()
    return [(r[0], r[1]) for r in rows]


def device_fks(db) -> list[dict]:
    """FK ที่ชี้มา devices.device_id พร้อมนิยามเดิม (ใช้ ADD กลับให้เหมือนเดิม)"""
    rows = db.execute(text(
        "SELECT c.conname AS name, rel.relname AS table_name, "
        "       pg_get_constraintdef(c.oid) AS definition "
        "FROM pg_constraint c "
        "JOIN pg_class rel ON rel.oid = c.conrelid "
        "JOIN pg_class ref ON ref.oid = c.confrelid "
        "WHERE c.contype = 'f' AND ref.relname = 'devices' "
        "  AND pg_get_constraintdef(c.oid) LIKE '%%devices%%(device_id)%%' "
        "ORDER BY rel.relname"
    )).mappings().all()
    return [dict(r) for r in rows]


def column_type(db, table: str, column: str) -> Optional[str]:
    return db.execute(text(
        "SELECT data_type FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
    ), {"t": table, "c": column}).scalar()


def device_id_maxlen(db) -> int:
    return db.execute(text(
        "SELECT character_maximum_length FROM information_schema.columns "
        "WHERE table_schema = 'public' AND table_name = 'devices' "
        "  AND column_name = 'device_id'"
    )).scalar() or 64


def orphan_counts(db, child_columns: list[tuple[str, str]]) -> dict[str, int]:
    """จำนวนแถวของแต่ละคอลัมน์ลูกที่ชี้ไปรหัสอุปกรณ์ที่ไม่มีใน devices

    บางตารางไม่มี FK จริง (เช่น self_service_cases) จึงมีแถวกำพร้าค้างอยู่ได้
    ตั้งแต่ก่อนย้ายรหัส — ต้องวัดค่าตั้งต้นไว้เทียบ ไม่ใช่บังคับให้เป็น 0
    """
    counts: dict[str, int] = {}
    for table, column in child_columns:
        counts[f"{table}.{column}"] = db.execute(text(
            f'SELECT COUNT(*) FROM "{table}" c '
            f'WHERE c."{column}" IS NOT NULL AND NOT EXISTS '
            f'  (SELECT 1 FROM devices d WHERE d.device_id = c."{column}")'
        )).scalar() or 0
    return counts


# ---------------------------------------------------------------------------
# วางแผนรหัสใหม่
# ---------------------------------------------------------------------------


def build_plan(db, maxlen: int) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    """คืน (คู่ที่ต้องย้าย, รหัสที่ถูกต้องอยู่แล้ว, คำเตือน)"""
    rows = db.execute(text(
        "SELECT d.device_id, d.organization_id, o.code AS org_code, "
        "       r.code AS room_code, r.building, r.floor, "
        "       d.device_type::text AS device_type "
        "FROM devices d "
        "JOIN organizations o ON o.id = d.organization_id "
        "LEFT JOIN rooms r ON r.id = d.room_id "
        "ORDER BY o.code, r.code NULLS LAST, d.device_type::text, d.device_id"
    )).mappings().all()

    # จับคู่รหัส → prefix เป้าหมาย
    targets: list[tuple[str, str]] = []
    for r in rows:
        prefix = device_id_prefix(r["org_code"], r["organization_id"], r["room_code"],
                                 r["building"], r["floor"], r["device_type"])
        targets.append((r["device_id"], prefix))

    # เครื่องที่อยู่ในรูปแบบใหม่ถูกต้องแล้ว — จองลำดับของตัวเองไว้ ไม่ต้องแตะ
    used: dict[str, set[int]] = defaultdict(set)
    keep: list[str] = []
    todo: list[tuple[str, str]] = []
    for device_id, prefix in targets:
        tail = device_id[len(prefix):] if device_id.startswith(prefix) else None
        if tail is not None and tail.isdigit():
            used[prefix].add(int(tail))
            keep.append(device_id)
        else:
            todo.append((device_id, prefix))

    existing = {device_id for device_id, _ in targets}
    pairs: list[tuple[str, str]] = []
    warnings: list[str] = []
    next_free: dict[str, int] = {}
    for device_id, prefix in todo:
        seq = next_free.get(prefix, 1)
        while seq in used[prefix]:
            seq += 1
        new_id = f"{prefix}{seq:02d}"
        # กันชนกับรหัสที่ยังไม่ถูกย้าย (รหัสเก่าของเครื่องอื่นอาจเท่ากับรหัสใหม่นี้
        # ได้ในทางทฤษฎี) — เดินลำดับต่อไปจนว่างจริง
        while new_id in existing and new_id != device_id:
            seq += 1
            new_id = f"{prefix}{seq:02d}"
        used[prefix].add(seq)
        next_free[prefix] = seq + 1
        if len(new_id) > maxlen:
            warnings.append(f"ข้าม {device_id}: รหัสใหม่ {new_id} ยาว {len(new_id)} "
                            f"เกิน {maxlen} ตัว")
            continue
        existing.add(new_id)
        pairs.append((device_id, new_id))
    return pairs, keep, warnings


# ---------------------------------------------------------------------------
# เขียนจริง
# ---------------------------------------------------------------------------


def rename(db, old: str, new: str, child_columns: list[tuple[str, str]],
           audit_value_columns: list[tuple[str, str]]) -> None:
    """เปลี่ยนรหัสหนึ่งตัว พร้อมทุกที่ที่อ้างถึงรหัสนั้น"""
    db.execute(text("UPDATE devices SET device_id = :new WHERE device_id = :old"),
               {"old": old, "new": new})
    for table, column in child_columns:
        db.execute(text(f'UPDATE "{table}" SET "{column}" = :new WHERE "{column}" = :old'),
                   {"old": old, "new": new})
    db.execute(text(
        "UPDATE audit_logs SET entity_id = :new "
        "WHERE entity_type = 'device' AND entity_id = :old"
    ), {"old": old, "new": new})
    # รหัสที่ฝังใน JSON ของ audit log — แทนเฉพาะค่าที่อยู่ในคำพูดเต็มตัว
    # ("DEV-2026-0101") เพื่อไม่ให้ไปโดนรหัสอื่นที่มีรหัสนี้เป็นส่วนหน้า
    for column, data_type in audit_value_columns:
        quoted_old = f'"{old}"'
        quoted_new = f'"{new}"'
        cast = "::jsonb" if data_type == "jsonb" else ("::json" if data_type == "json" else "")
        db.execute(text(
            f'UPDATE audit_logs SET "{column}" = '
            f'replace("{column}"::text, :qold, :qnew){cast} '
            f'WHERE "{column}" IS NOT NULL AND "{column}"::text LIKE :pat'
        ), {"qold": quoted_old, "qnew": quoted_new, "pat": f"%{quoted_old}%"})


def main() -> int:
    parser = argparse.ArgumentParser(
        description="ย้ายรหัสอุปกรณ์เก่าให้เป็นรูปแบบ <รร>-<อาคาร>-<ห้อง>-<ประเภท>-<ลำดับ>"
    )
    parser.add_argument("--apply", action="store_true",
                        help="เขียนลงฐานข้อมูลจริง (ไม่ใส่ = ดูผลล่วงหน้าเท่านั้น)")
    args = parser.parse_args()

    db = SessionLocal()
    try:
        maxlen = device_id_maxlen(db)
        child_columns = device_id_columns(db)
        fks = device_fks(db)
        audit_value_columns = [
            (col, column_type(db, "audit_logs", col) or "text")
            for col in ("old_value", "new_value")
            if column_type(db, "audit_logs", col)
        ]

        stale = db.execute(text(
            "SELECT COUNT(*) FROM devices WHERE device_id LIKE :p"
        ), {"p": f"{TEMP_PREFIX}%"}).scalar()
        if stale:
            print(f"✗ มีรหัสค้างรูปแบบชั่วคราว {TEMP_PREFIX}* อยู่ {stale} ตัว "
                  f"— ตรวจสอบก่อน ไม่ควรรันต่อ")
            return 1

        pairs, keep, warnings = build_plan(db, maxlen)

        print(f"คอลัมน์ที่อ้างรหัสอุปกรณ์: "
              f"{', '.join(f'{t}.{c}' for t, c in child_columns) or '(ไม่มี)'}")
        print(f"audit_logs: entity_id + {', '.join(c for c, _ in audit_value_columns) or '-'}")
        print("FK ที่จะถอดและใส่กลับ:")
        for fk in fks:
            print(f"  {fk['table_name']}.{fk['name']}: {fk['definition']}")
        print(f"\nรูปแบบใหม่อยู่แล้ว {len(keep)} ตัว / ต้องย้าย {len(pairs)} ตัว "
              f"(ความยาวสูงสุด {maxlen})")
        for w in warnings:
            print(f"  ⚠ {w}")
        for old, new in pairs:
            print(f"  {old:<24} → {new}")

        if not pairs:
            print("\nไม่มีอะไรต้องย้าย")
            return 0
        if not args.apply:
            print("\n(ดูผลล่วงหน้าเท่านั้น — ใส่ --apply เพื่อเขียนจริง)")
            return 0

        # ค่าตั้งต้นของแถวกำพร้า — ที่มีอยู่ก่อนย้ายถือว่า "ไม่ใช่ความผิดของเรา"
        # แต่ถ้าหลังย้ายเพิ่มขึ้น แปลว่าการย้ายทำลิงก์ขาด → ต้องย้อนกลับ
        orphans_before = orphan_counts(db, child_columns)
        pre_existing = {k: v for k, v in orphans_before.items() if v}
        if pre_existing:
            print("\nแถวกำพร้าที่มีอยู่ก่อนย้าย (ยอมรับไว้ ไม่แก้ในสคริปต์นี้):")
            for key, n in sorted(pre_existing.items()):
                print(f"  {key}: {n} แถว")
        # ── เขียนจริงในทรานแซกชันเดียว ──────────────────────────────────
        for fk in fks:
            db.execute(text(f'ALTER TABLE "{fk["table_name"]}" '
                            f'DROP CONSTRAINT "{fk["name"]}"'))

        temp_of = {old: f"{TEMP_PREFIX}{i + 1}" for i, (old, _) in enumerate(pairs)}
        for old, _new in pairs:                      # จังหวะ 1: เก่า → ชั่วคราว
            rename(db, old, temp_of[old], child_columns, audit_value_columns)
        for old, new in pairs:                       # จังหวะ 2: ชั่วคราว → ใหม่
            rename(db, temp_of[old], new, child_columns, audit_value_columns)

        for fk in fks:
            db.execute(text(f'ALTER TABLE "{fk["table_name"]}" '
                            f'ADD CONSTRAINT "{fk["name"]}" {fk["definition"]}'))

        # ── ตรวจก่อน commit: ลูกกำพร้าต้องไม่ "เพิ่มขึ้น" และไม่มีรหัสชั่วคราวค้าง ──
        problems = []
        orphans_after = orphan_counts(db, child_columns)
        for key, after in sorted(orphans_after.items()):
            before = orphans_before.get(key, 0)
            if after > before:
                problems.append(f"{key}: แถวกำพร้าเพิ่มจาก {before} เป็น {after} "
                                f"— การย้ายทำลิงก์ขาด")
        left = db.execute(text(
            "SELECT COUNT(*) FROM devices WHERE device_id LIKE :p"
        ), {"p": f"{TEMP_PREFIX}%"}).scalar()
        if left:
            problems.append(f"devices: เหลือรหัสชั่วคราว {left} ตัว")
        if problems:
            db.rollback()
            print("\n✗ ย้อนกลับทั้งหมด — พบปัญหา:")
            for p in problems:
                print(f"   {p}")
            return 1

        db.commit()
        print(f"\n✔ ย้ายรหัสอุปกรณ์แล้ว {len(pairs)} ตัว (FK ใส่กลับครบ "
              f"{len(fks)} ตัว, ไม่มีลูกกำพร้า)")
        return 0
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    raise SystemExit(main())