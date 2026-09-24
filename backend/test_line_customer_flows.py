"""DB-backed checks for exact warranty, LINE ratings and unverified sales signals."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import func, select, text

from app.chatbot_rating import record_rating
from app.chatbot_sales import record_line_interest, request_line_payment
from app.chatbot_warranty import warranty_answer
from app.models import (Device, LineServiceRating, Organization, RepairTicket,
                        SalesLead, SalesRecord, SessionLocal, init_db)


@pytest.fixture
def customer_case(monkeypatch):
    try:
        init_db()  # CREATE TABLE IF NOT EXISTS for the newly added rating table
        db = SessionLocal()
        db.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Local database unavailable: {exc}")
    suffix = uuid.uuid4().hex[:8].upper()
    line_id = f"line-test-{suffix}"
    device_id = f"LT{suffix[:6]}-CAM-01"
    ticket_id = f"TK.LT{suffix[:6]}.26.0001-T"
    org = Organization(code=f"LT{suffix[:6]}", name="LINE flow test")
    db.add(org); db.flush()
    device = Device(device_id=device_id, organization_id=org.id, device_type="Camera", status="active",
                    serial_number=f"SERIAL-{suffix}", warranty_until=datetime.now(timezone.utc) + timedelta(days=90))
    db.add(device); db.flush()
    ticket = RepairTicket(ticket_id=ticket_id, organization_id=org.id, device_id=device_id,
                          title="Test", priority="normal", status="closed", reporter_phone="0812345678")
    lead = SalesLead(user_id=line_id, name="Test customer", phone="0812345678",
                     interest="Camera", products="Camera", source="LINE", status="new")
    db.add_all([ticket, lead]); db.commit()
    ids = org.id, lead.id
    monkeypatch.setattr("app.main._sync_sales_record_async", lambda *args: None)
    monkeypatch.setattr("app.line_bot.LINE_GROUP_ID", "")
    try:
        yield db, line_id, device_id, ticket_id, lead.id, f"SERIAL-{suffix}"
    finally:
        db.rollback()
        db.execute(text("DELETE FROM line_service_ratings WHERE line_user_id = :uid"), {"uid": line_id})
        db.execute(text("DELETE FROM sales_records WHERE lead_id = :lid"), {"lid": ids[1]})
        db.execute(text("DELETE FROM sales_leads WHERE id = :lid"), {"lid": ids[1]})
        db.execute(text("DELETE FROM repair_tickets WHERE ticket_id = :tid"), {"tid": ticket_id})
        db.execute(text("DELETE FROM devices WHERE device_id = :did"), {"did": device_id})
        db.execute(text("DELETE FROM organizations WHERE id = :oid"), {"oid": ids[0]})
        db.commit(); db.close()


def test_warranty_is_exact_and_grounded(customer_case):
    _db, _uid, device_id, _tid, _lead_id, serial = customer_case
    answer = warranty_answer(serial)
    assert device_id in answer and "อยู่ในระยะประกัน" in answer
    assert "0812345678" not in answer
    assert "ไม่พบรหัส" in warranty_answer("NOT-REGISTERED-123")


def test_line_ratings_are_scoped_and_updatable(customer_case):
    db, uid, _device_id, ticket_id, _lead_id, _serial = customer_case
    assert "4/5" in record_rating(uid, "ประเมินบอท 4", None)
    assert "5/5" in record_rating(uid, "ประเมินบอท 5", None)
    assert "ยังประเมินงานนี้ไม่ได้" in record_rating(uid, f"ประเมินเจ้าหน้าที่ {ticket_id} 5", "0899999999", ticket_id)
    assert "ยังประเมินงานนี้ไม่ได้" in record_rating(uid, f"ประเมินเจ้าหน้าที่ {ticket_id} 5", "0812345678")
    assert "5/5" in record_rating(uid, f"ประเมินเจ้าหน้าที่ {ticket_id} 5", "0812345678", ticket_id)
    db.rollback()
    rows = db.execute(select(LineServiceRating).where(LineServiceRating.line_user_id == uid)).scalars().all()
    assert len(rows) == 2
    assert {r.target: r.score for r in rows} == {"bot": 5, "staff": 5}


def test_line_interest_and_payment_stay_unverified(customer_case):
    db, uid, _device_id, _ticket_id, lead_id, _serial = customer_case
    assert record_line_interest(lead_id, "Camera") is True
    assert record_line_interest(lead_id, "Camera") is False
    assert "ยังไม่ใช่การชำระเงินสำเร็จ" in request_line_payment(uid, "Camera")
    assert "รอเจ้าหน้าที่ตรวจสอบอยู่แล้ว" in request_line_payment(uid, "Camera")
    assert "อย่าส่งเลขบัตร" in request_line_payment(uid, "4111111111111111")
    db.rollback()
    rows = db.execute(select(SalesRecord).where(SalesRecord.lead_id == lead_id)).scalars().all()
    assert {(r.kind, r.status) for r in rows} == {("deal", "interested"), ("payment_request", "requested")}
    assert all(r.amount_thb is None for r in rows)
