"""ย้ายเลข Ticket รูปแบบเก่าในฐานข้อมูลให้เป็นรูปแบบใหม่ (แยกตามโรงเรียน)

ทำไมต้องมีสคริปต์นี้: generate_ticket_id / ticket_no_of มีผลกับใบที่ "สร้างใหม่"
เท่านั้น ใบที่ seed ไว้ก่อนแก้โค้ด (SC-YYYY-NNNNNN, TK-YYYYMM-NNNN, SC-<รร>-YYYY-NNNN)
ยังเป็นเลขเดิมอยู่ในฐานข้อมูล และ seed_mockup_5_schools.py จะข้ามโรงเรียนที่มีอยู่แล้ว
จึงไม่เขียนเลขทับให้

เลขใหม่: TK.<รหัสโรงเรียน>.<ปี 2 หลัก>.<ลำดับ>-<ตัวตรวจสอบ>
ลำดับนับแยกต่อโรงเรียนต่อปี ตามลำดับเวลาที่แจ้ง (created_at)

ใช้:
    python backend/scripts/migrate_ticket_numbers.py           # ดูผลก่อน ไม่แก้อะไรเลย
    python backend/scripts/migrate_ticket_numbers.py --apply   # แก้จริง (ทำในทรานแซกชันเดียว)

ใบที่เป็นรูปแบบใหม่และตัวตรวจสอบถูกต้องอยู่แล้วจะไม่ถูกแตะ และลำดับของใบที่ย้าย
จะนับต่อจากเลขสูงสุดที่ใช้อยู่ในโรงเรียน/ปีนั้น เพื่อไม่ให้ชนกับใบเดิม
"""
import os
import re
import sys
from datetime import datetime, timezone

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from sqlalchemy import text  # noqa: E402

from app.main import (  # noqa: E402
    TICKET_NO_PREFIX,
    _mod37_36_check_char,
    _org_code_token,
    ticket_no_of,
)
from app.models import SessionLocal  # noqa: E402

#: ความยาวคอลัมน์ repair_tickets.ticket_id
MAX_LEN = 32

#: ตารางอื่นที่เก็บ "เลขใบงาน" เป็นสตริง (ticket_updates.ticket_id เป็น FK ตัวเลข ไม่เกี่ยว)
STRING_REFS = [
    ("scan_logs", "ticket_id"),
    ("pm_tasks", "ticket_id"),
    ("ticket_comments", "ticket_id"),
    ("ticket_attachments", "ticket_id"),
    ("notification_logs", "ticket_id"),
    ("repair_history", "ticket_no"),
]

_NEW_RE = re.compile(
    rf"^{re.escape(TICKET_NO_PREFIX)}\.([A-Z0-9]{{1,8}})\.(\d{{2}})\.(\d+)-([0-9A-Z])$"
)


def parse_new_format(ticket_no: str):
    """คืน (token, ปี 2 หลัก, ลำดับ) ถ้าเป็นเลขรูปแบบใหม่ที่ตัวตรวจสอบตรง ไม่ใช่คืน None

    เช็คตัวตรวจสอบด้วย ไม่ใช่ดูแค่หน้าตา เพราะเลขที่หน้าตาถูกแต่ check ไม่ตรงจะเปิด
    ดูไม่ได้ผ่าน API และต้องถือว่าเป็นเลขที่ต้องย้ายเหมือนกัน
    """
    m = _NEW_RE.match(ticket_no or "")
    if not m:
        return None
    body, _, check = ticket_no.rpartition("-")
    if _mod37_36_check_char(body) != check:
        return None
    return m.group(1), m.group(2), int(m.group(3))


def existing_string_ref_columns(db):
    """เหลือเฉพาะคอลัมน์ที่มีอยู่จริงในสคีมา และยาวพอจะเก็บเลขใหม่"""
    out = []
    for table, column in STRING_REFS:
        row = db.execute(text(
            "SELECT data_type, character_maximum_length FROM information_schema.columns "
            "WHERE table_schema = 'public' AND table_name = :t AND column_name = :c"
        ), {"t": table, "c": column}).mappings().first()
        if row is None:
            continue
        if row["data_type"] not in ("character varying", "text", "character"):
            continue
        out.append((table, column, row["character_maximum_length"]))
    return out


def report_foreign_keys(db):
    """FK ที่ชี้มาที่ repair_tickets.ticket_id — ถ้ามีและไม่ CASCADE ต้องรู้ก่อนแก้"""
    rows = db.execute(text(
        "SELECT tc.table_name, kcu.column_name, tc.constraint_name, rc.update_rule "
        "FROM information_schema.table_constraints tc "
        "JOIN information_schema.key_column_usage kcu "
        "  ON kcu.constraint_name = tc.constraint_name "
        " AND kcu.table_schema = tc.table_schema "
        "JOIN information_schema.constraint_column_usage ccu "
        "  ON ccu.constraint_name = tc.constraint_name "
        " AND ccu.table_schema = tc.table_schema "
        "JOIN information_schema.referential_constraints rc "
        "  ON rc.constraint_name = tc.constraint_name "
        " AND rc.constraint_schema = tc.table_schema "
        "WHERE tc.constraint_type = 'FOREIGN KEY' "
        "  AND ccu.table_name = 'repair_tickets' AND ccu.column_name = 'ticket_id'"
    )).mappings().all()
    if not rows:
        print("FK ที่อ้าง repair_tickets.ticket_id: ไม่มี → อัปเดตตารางลูกเองได้ตรง ๆ")
    else:
        for r in rows:
            print(f"FK {r['constraint_name']}: {r['table_name']}.{r['column_name']} "
                  f"→ repair_tickets.ticket_id (ON UPDATE {r['update_rule']})")
    return rows


def build_mapping(db):
    """คำนวณเลขใหม่ของแต่ละใบที่ยังเป็นรูปแบบเก่า"""
    rows = db.execute(text(
        "SELECT t.id, t.ticket_id, t.created_at, "
        "       COALESCE(t.organization_id, d.organization_id) AS org_id, "
        "       COALESCE(o1.code, o2.code) AS org_code "
        "FROM repair_tickets t "
        "LEFT JOIN devices d ON d.device_id = t.device_id "
        "LEFT JOIN organizations o1 ON o1.id = t.organization_id "
        "LEFT JOIN organizations o2 ON o2.id = d.organization_id "
        "ORDER BY t.created_at NULLS LAST, t.id"
    )).mappings().all()

    used = {r["ticket_id"] for r in rows}
    counters: dict[tuple[str, str], int] = {}
    for r in rows:
        parsed = parse_new_format(r["ticket_id"])
        if parsed:
            token, yy, seq = parsed
            key = (token, yy)
            counters[key] = max(counters.get(key, 0), seq)

    mapping = []
    skipped = 0
    this_year = datetime.now(timezone.utc).year
    for r in rows:
        if parse_new_format(r["ticket_id"]):
            skipped += 1
            continue
        token = _org_code_token(r["org_code"], r["org_id"])
        year = r["created_at"].year if r["created_at"] else this_year
        key = (token, f"{year % 100:02d}")
        seq = counters.get(key, 0) + 1
        new_no = ticket_no_of(token, year, seq)
        while new_no in used:                 # กันชนกับเลขที่มีอยู่แล้วทุกกรณี
            seq += 1
            new_no = ticket_no_of(token, year, seq)
        if len(new_no) > MAX_LEN:
            raise SystemExit(f"เลขใหม่ยาวเกิน {MAX_LEN} ตัว: {new_no}")
        counters[key] = seq
        used.add(new_no)
        mapping.append({"pk": r["id"], "old": r["ticket_id"], "new": new_no})
    return mapping, skipped, len(rows)


def apply_mapping(db, mapping, ref_columns):
    """เขียนเลขใหม่แบบสองจังหวะ (เก่า → ชั่วคราว → ใหม่) กันชนดัชนี unique กลางทาง"""
    for item in mapping:
        item["tmp"] = f"MIG.{item['pk']}"     # สั้น ไม่ซ้ำ ไม่ตรงรูปแบบเลขจริงแน่นอน

    for stage_from, stage_to in (("old", "tmp"), ("tmp", "new")):
        for item in mapping:
            params = {"old": item[stage_from], "new": item[stage_to]}
            db.execute(text("UPDATE repair_tickets SET ticket_id = :new WHERE ticket_id = :old"),
                       params)
            for table, column, _length in ref_columns:
                db.execute(text(f"UPDATE {table} SET {column} = :new WHERE {column} = :old"),
                           params)
            db.execute(text("UPDATE audit_logs SET entity_id = :new "
                            "WHERE entity_type = 'ticket' AND entity_id = :old"), params)


def main() -> None:
    do_apply = "--apply" in sys.argv[1:]
    db = SessionLocal()
    try:
        ref_columns = existing_string_ref_columns(db)
        print("== ตารางที่อ้างเลขใบงานเป็นสตริง (จะอัปเดตพร้อมกัน) ==")
        for table, column, length in ref_columns:
            print(f"   {table}.{column} varchar({length})")
        print()
        report_foreign_keys(db)
        print()

        mapping, skipped, total = build_mapping(db)
        print(f"== ใบงานทั้งหมด {total} ใบ | รูปแบบใหม่อยู่แล้ว {skipped} ใบ | "
              f"ต้องย้าย {len(mapping)} ใบ ==\n")
        for item in mapping:
            print(f"   {item['old']:<26} →  {item['new']}")

        if not mapping:
            print("\nไม่มีอะไรต้องย้าย")
            return
        if not do_apply:
            print("\nนี่เป็นการดูผลล่วงหน้า ยังไม่ได้แก้ฐานข้อมูล — สั่งซ้ำด้วย --apply เพื่อเขียนจริง")
            return

        apply_mapping(db, mapping, ref_columns)
        db.commit()
        print(f"\nเขียนแล้ว {len(mapping)} ใบ (พร้อมตารางที่อ้างถึงและ audit log)")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()