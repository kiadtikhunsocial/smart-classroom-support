"""test_ticket_creation.py — เทสต์ด้านบวกของการสร้าง Ticket จาก Chatbot

อ้างอิง Blueprint:
- §46 UAT-001  : อุปกรณ์ที่ลงทะเบียนแล้ว ต้องสร้าง Ticket ได้และได้เลขที่อ้างอิง
- §11          : Ticket Number ต้องไม่ซ้ำ
- §13          : ทุกการเปลี่ยนสถานะต้องมี History (ticket_updates แถวแรก = new)
- §15 / §17    : Priority Engine + Safety Guardrail (safety_critical → critical + escalate)

เทสต์ชุดนี้เขียนลง PostgreSQL จริง (DATABASE_URL) จึงลบ Ticket ที่สร้างขึ้นทุกครั้ง
ผ่าน fixture cleanup — ticket_updates ถูกลบตาม cascade ของ FK (ondelete="CASCADE")
ถ้ายังไม่ได้ seed อุปกรณ์ (รัน `python scripts/seed_db.py`) เทสต์จะถูก skip
ไม่ใช่ fail เพราะไม่ใช่ความผิดของโค้ดที่ทดสอบ
"""
import sys

import pytest

sys.path.insert(0, '.')

from sqlalchemy import text as sa_text

from app.chatbot_core import _create_ticket_from_fields
from app.models import SessionLocal

# ห้องที่ seed_db.py สร้างไว้ — มีอุปกรณ์หลายเครื่อง ใช้ทดสอบเคสระบุกำกวม
SEEDED_ROOM_CODE = "301"


def _lookup_seeded_device() -> str | None:
    """รหัสอุปกรณ์ในห้อง 301 จากฐานข้อมูลจริง (None = ยังไม่ seed / ต่อ DB ไม่ได้)

    รหัสอุปกรณ์ไม่ฮาร์ดโค้ดอีกแล้ว: รูปแบบใหม่ผูกกับโรงเรียน/อาคาร/ห้อง
    (เช่น SCHDEMO-B3-301-DISP-01) และ scripts/seed_db.py ขอเลขจาก
    generate_device_id ตอนรัน จึงเดารหัสล่วงหน้าไม่ได้

    เลือกเครื่องที่ยังไม่มีใบงานค้างก่อน ไม่อย่างนั้นการแจ้งจะเข้าทางกันแจ้งซ้ำ
    (TOR 1.5.2) แล้วได้เลขใบเดิมกลับมาแทนการเปิดใบใหม่ — ใช้รายชื่อสถานะจาก
    app.main.OPEN_TICKET_STATUSES ตัวเดียวกับที่ find_open_ticket ใช้
    """
    from app.main import OPEN_TICKET_STATUSES

    try:
        db = SessionLocal()
    except Exception:  # pragma: no cover - ขึ้นกับ environment
        return None
    try:
        return db.execute(
            sa_text(
                "SELECT d.device_id FROM devices d "
                "JOIN rooms r ON r.id = d.room_id "
                "WHERE r.code = :room "
                # EXISTS = false มาก่อน true ใน ORDER BY ASC → เครื่องที่ไม่มีใบค้างขึ้นก่อน
                "ORDER BY EXISTS ("
                "  SELECT 1 FROM repair_tickets t "
                "  WHERE t.device_id = d.device_id "
                "    AND t.status::text = ANY(:open)"
                "), d.device_id "
                "LIMIT 1"
            ),
            {"room": SEEDED_ROOM_CODE, "open": list(OPEN_TICKET_STATUSES)},
        ).scalar()
    except Exception:  # pragma: no cover - ขึ้นกับ environment
        return None
    finally:
        db.close()


SEEDED_DEVICE_ID = _lookup_seeded_device()


@pytest.fixture
def created_tickets():
    """เก็บ ticket_id ที่เทสต์สร้าง แล้วลบทิ้งตอนจบ (ไม่ทิ้งขยะใน DB)"""
    bucket: list[str] = []
    yield bucket
    if not bucket:
        return
    db = SessionLocal()
    try:
        db.execute(
            sa_text("DELETE FROM repair_tickets WHERE ticket_id = ANY(:ids)"),
            {"ids": bucket},
        )
        db.commit()
    finally:
        db.close()


def _require_seeded_device() -> None:
    """skip เทสต์ถ้าฐานข้อมูลยังไม่มีอุปกรณ์ตัวอย่าง หรือต่อ DB ไม่ได้"""
    if not SEEDED_DEVICE_ID:
        pytest.skip(
            f"ยังไม่มีอุปกรณ์ในห้อง {SEEDED_ROOM_CODE} หรือต่อฐานข้อมูลไม่ได้ "
            "— รัน `python scripts/seed_db.py` ก่อน"
        )


def _fetch_ticket(ticket_no: str):
    db = SessionLocal()
    try:
        return db.execute(
            sa_text(
                "SELECT ticket_id, device_id, organization_id, status, priority, "
                "escalation_level, channel, reporter_name, reporter_phone, "
                "description, sla_due_at "
                "FROM repair_tickets WHERE ticket_id = :t"
            ),
            {"t": ticket_no},
        ).mappings().first()
    finally:
        db.close()


def _count_status_history(ticket_no: str) -> int:
    db = SessionLocal()
    try:
        return db.execute(
            sa_text(
                "SELECT count(*) FROM ticket_updates u "
                "JOIN repair_tickets t ON t.id = u.ticket_id "
                "WHERE t.ticket_id = :t AND u.to_status = 'new'"
            ),
            {"t": ticket_no},
        ).scalar_one()
    finally:
        db.close()


def test_registered_device_creates_ticket(created_tickets):
    """§46 UAT-001: ระบุรหัสอุปกรณ์ที่มีจริง → ต้องได้ Ticket ผูกกับอุปกรณ์นั้น"""
    _require_seeded_device()

    ticket_no, error = _create_ticket_from_fields({
        'device_id': SEEDED_DEVICE_ID,
        'name': 'ครูสมชาย (เทสต์อัตโนมัติ)',
        'phone': '0812345678',
        'symptom': 'จอ Interactive Display ไม่มีภาพ ไฟ Power ติดปกติ',
    })

    assert error is None, f"ต้องสร้าง Ticket ได้ แต่ได้ error: {error}"
    assert ticket_no, "ต้องได้ Ticket Number กลับมา"
    created_tickets.append(ticket_no)

    row = _fetch_ticket(ticket_no)
    assert row is not None, "Ticket ต้องถูกบันทึกลงฐานข้อมูลจริง"
    assert row['device_id'] == SEEDED_DEVICE_ID, "Ticket ต้องผูกกับอุปกรณ์ที่ผู้ใช้แจ้ง"
    assert row['organization_id'] is not None, "ต้องสืบทอด organization จากอุปกรณ์"
    assert row['status'] == 'new'
    assert row['channel'] == 'line'
    assert row['reporter_phone'] == '0812345678'
    assert row['sla_due_at'] is not None, "ต้องคำนวณ SLA due ตอนสร้าง"
    # §13: ทุกการเปลี่ยนสถานะต้องมี History — แถวแรกคือ new
    assert _count_status_history(ticket_no) == 1


def test_room_only_resolves_when_unambiguous(created_tickets):
    """ระบุเฉพาะเลขห้องที่มีหลายอุปกรณ์ → ต้องถามกลับ ห้ามเดาเครื่อง

    เคสนี้เคยพลาด: "301" ไป substring ตรงกับรหัส DEV-2024-00301 (Router ห้อง 201)
    ทำให้ ticket ผูกกับอุปกรณ์คนละห้องของผู้แจ้ง (§52 ข้อ 1 Asset First)
    """
    _require_seeded_device()

    ticket_no, error = _create_ticket_from_fields({
        'device_id': SEEDED_ROOM_CODE,
        'name': 'ครูสมหญิง (เทสต์อัตโนมัติ)',
        'phone': '0898765432',
        'symptom': 'อุปกรณ์ในห้องใช้งานไม่ได้',
    })

    if ticket_no:
        created_tickets.append(ticket_no)
        pytest.fail(
            f"ห้อง {SEEDED_ROOM_CODE} มีอุปกรณ์หลายเครื่อง ระบบไม่ควรเดาเครื่องให้ "
            f"แต่สร้าง {ticket_no} ผูกกับอุปกรณ์ที่เดาเอง"
        )
    assert error, "ต้องคืนข้อความอธิบายว่าเลือกเครื่องไม่ได้"
    assert 'หลายเครื่อง' in error or 'ไม่พบอุปกรณ์' in error, error


def test_safety_critical_sets_critical_priority(created_tickets):
    """§15/§17: เคสความปลอดภัย → priority critical + escalation_level 1"""
    _require_seeded_device()

    ticket_no, error = _create_ticket_from_fields({
        'device_id': SEEDED_DEVICE_ID,
        'name': 'ครูสมศรี (เทสต์อัตโนมัติ)',
        'phone': '0800000000',
        'symptom': 'มีกลิ่นไหม้และมีควันออกจากด้านหลังจอ',
        'urgency': 'safety_critical',
    })

    assert error is None, f"เคสฉุกเฉินต้องสร้าง Ticket ได้ แต่ได้ error: {error}"
    assert ticket_no
    created_tickets.append(ticket_no)

    row = _fetch_ticket(ticket_no)
    assert row is not None
    # ต้องเป็นค่าใน priority_enum จริง (low/normal/high/critical) ไม่ใช่ "urgent"
    assert row['priority'] == 'critical'
    assert row['escalation_level'] == 1


def _devices_without_open_ticket(count: int) -> list[str]:
    """รหัสอุปกรณ์ที่ "ยังไม่มีใบงานค้าง" จำนวน count เครื่อง (skip ถ้าไม่พอ)

    ใช้รายชื่อสถานะจาก app.main.OPEN_TICKET_STATUSES ตัวเดียวกับที่ find_open_ticket
    ใช้ ไม่เดารายชื่อเอง เพราะถ้าเลือกเครื่องที่มีใบค้างมาทดสอบ ระบบจะเข้าทาง
    กันแจ้งซ้ำ (TOR 1.5.2) แล้วคืนเลขใบของ seed data กลับมา — fixture cleanup
    จะลบข้อมูลตั้งต้นของระบบทิ้ง
    """
    from app.main import OPEN_TICKET_STATUSES

    try:
        db = SessionLocal()
    except Exception as exc:  # pragma: no cover - ขึ้นกับ environment
        pytest.skip(f"ต่อฐานข้อมูลไม่ได้: {exc!r}")
    try:
        rows = db.execute(
            sa_text(
                "SELECT d.device_id FROM devices d "
                "WHERE NOT EXISTS ("
                "  SELECT 1 FROM repair_tickets t "
                "  WHERE t.device_id = d.device_id "
                "    AND t.status::text = ANY(:open)"
                ") ORDER BY d.device_id LIMIT :n"
            ),
            {"open": list(OPEN_TICKET_STATUSES), "n": count},
        ).scalars().all()
    except Exception as exc:  # pragma: no cover - ขึ้นกับ environment
        pytest.skip(f"อ่านฐานข้อมูลไม่ได้: {exc!r}")
    finally:
        db.close()

    if len(rows) < count:
        pytest.skip(
            f"ต้องมีอุปกรณ์ที่ไม่มีใบงานค้างอย่างน้อย {count} เครื่อง แต่พบ {len(rows)} "
            "— รัน `python scripts/seed_db.py` ก่อน"
        )
    return list(rows)


def _count_tickets_of_device(device_id: str) -> int:
    db = SessionLocal()
    try:
        return db.execute(
            sa_text("SELECT count(*) FROM repair_tickets WHERE device_id = :d"),
            {"d": device_id},
        ).scalar_one()
    finally:
        db.close()


def _count_reporter_notes(ticket_no: str) -> int:
    """จำนวนบันทึก "แจ้งเพิ่ม" ของผู้แจ้งในใบงานนั้น (ไม่ใช่แถวเปลี่ยนสถานะ)"""
    db = SessionLocal()
    try:
        return db.execute(
            sa_text(
                "SELECT count(*) FROM ticket_updates u "
                "JOIN repair_tickets t ON t.id = u.ticket_id "
                "WHERE t.ticket_id = :t AND u.note LIKE :p"
            ),
            {"t": ticket_no, "p": "[แจ้งเพิ่มจากผู้ใช้ LINE]%"},
        ).scalar_one()
    finally:
        db.close()


def test_ticket_numbers_are_unique(created_tickets):
    """§11: ใบงานต่างใบต้องได้ Ticket Number ไม่ซ้ำกัน

    เดิมเทสต์นี้แจ้ง "อุปกรณ์เดียวกัน" ติดกัน 2 ครั้งเพื่อให้ได้ 2 ใบ ซึ่งขัดกับ
    กันแจ้งซ้ำ (TOR 1.5.2) ที่ตอนนี้ไม่เปิดใบใหม่ให้เครื่องที่มีใบค้างอยู่แล้ว
    จึงเปลี่ยนมาสร้างจาก 2 เครื่องที่ยังไม่มีใบค้าง — ข้อกำหนดเรื่องเลขไม่ซ้ำ
    ยังถูกตรวจเหมือนเดิม (ดูพฤติกรรมแจ้งซ้ำที่ test_duplicate_report_appends_to_open_ticket)
    """
    _require_seeded_device()
    devices = _devices_without_open_ticket(2)

    numbers = []
    for i, device_id in enumerate(devices, 1):
        ticket_no, error = _create_ticket_from_fields({
            'device_id': device_id,
            'name': f'ผู้แจ้ง {i} (เทสต์อัตโนมัติ)',
            'phone': '0811111111',
            'symptom': f'ทดสอบเลข Ticket ไม่ซ้ำ เครื่องที่ {i} ({device_id})',
        })
        assert error is None, f"เครื่อง {device_id} สร้างไม่สำเร็จ: {error}"
        assert ticket_no
        created_tickets.append(ticket_no)
        numbers.append(ticket_no)

    assert len(set(numbers)) == len(numbers), f"Ticket Number ซ้ำ: {numbers}"


def test_duplicate_report_appends_to_open_ticket(created_tickets):
    """TOR 1.5.2: เครื่องที่มีใบงานค้างอยู่ แจ้งซ้ำต้องไม่เปิดใบใหม่

    ต้องได้เลขใบเดิมกลับไปให้ผู้แจ้งติดตามต่อ และอาการที่แจ้งรอบสองต้องถูกบันทึก
    เป็น ticket_updates ของใบเดิม (§13) ไม่ทับ description ของผู้แจ้งคนก่อน
    """
    _require_seeded_device()
    device_id = _devices_without_open_ticket(1)[0]

    first_no, error = _create_ticket_from_fields({
        'device_id': device_id,
        'name': 'ผู้แจ้งคนแรก (เทสต์อัตโนมัติ)',
        'phone': '0811111111',
        'symptom': 'จอไม่มีภาพ (ใบแรก)',
    })
    assert error is None, f"ใบแรกต้องสร้างได้: {error}"
    assert first_no
    created_tickets.append(first_no)

    before = _count_tickets_of_device(device_id)

    second_no, error2 = _create_ticket_from_fields({
        'device_id': device_id,
        'name': 'ผู้แจ้งคนที่สอง (เทสต์อัตโนมัติ)',
        'phone': '0822222222',
        'symptom': 'เสียงไม่ออกด้วย (แจ้งเพิ่ม)',
    })

    assert error2 is None, f"การแจ้งซ้ำต้องไม่เป็น error แต่ได้: {error2}"
    assert second_no == first_no, (
        f"ต้องคืนเลขใบเดิม {first_no} ไม่เปิดใบใหม่ แต่ได้ {second_no}"
    )
    if second_no != first_no:  # pragma: no cover - กันขยะค้าง DB ถ้า guardrail ถูกถอด
        created_tickets.append(second_no)

    assert _count_tickets_of_device(device_id) == before, (
        "จำนวนใบงานของอุปกรณ์ต้องไม่เพิ่มขึ้นจากการแจ้งซ้ำ"
    )
    row = _fetch_ticket(first_no)
    assert row is not None
    assert row['description'] == 'จอไม่มีภาพ (ใบแรก)', "ห้ามทับอาการของผู้แจ้งคนแรก"
    assert _count_reporter_notes(first_no) >= 1, "อาการที่แจ้งเพิ่มต้องถูกบันทึกเข้าใบเดิม"