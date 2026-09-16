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

# อุปกรณ์ที่ seed_db.py สร้างไว้: Interactive Display ห้อง 301
SEEDED_DEVICE_ID = "DEV-2024-00123"
SEEDED_ROOM_CODE = "301"


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
    try:
        db = SessionLocal()
    except Exception as exc:  # pragma: no cover - ขึ้นกับ environment
        pytest.skip(f"ต่อฐานข้อมูลไม่ได้: {exc!r}")
    try:
        row = db.execute(
            sa_text("SELECT device_id FROM devices WHERE device_id = :d"),
            {"d": SEEDED_DEVICE_ID},
        ).first()
    except Exception as exc:  # pragma: no cover - ขึ้นกับ environment
        pytest.skip(f"อ่านตาราง devices ไม่ได้: {exc!r}")
    finally:
        db.close()
    if row is None:
        pytest.skip(
            f"ยังไม่มีอุปกรณ์ {SEEDED_DEVICE_ID} ในฐานข้อมูล "
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


def test_ticket_numbers_are_unique(created_tickets):
    """§11: Ticket Number ต้องไม่ซ้ำ แม้แจ้งอุปกรณ์เดียวกันติดกัน"""
    _require_seeded_device()

    numbers = []
    for i in range(2):
        ticket_no, error = _create_ticket_from_fields({
            'device_id': SEEDED_DEVICE_ID,
            'name': f'ผู้แจ้งซ้ำ {i + 1} (เทสต์อัตโนมัติ)',
            'phone': '0811111111',
            'symptom': f'ทดสอบเลข Ticket ไม่ซ้ำ ครั้งที่ {i + 1}',
        })
        assert error is None, f"ครั้งที่ {i + 1} สร้างไม่สำเร็จ: {error}"
        assert ticket_no
        created_tickets.append(ticket_no)
        numbers.append(ticket_no)

    assert len(set(numbers)) == len(numbers), f"Ticket Number ซ้ำ: {numbers}"