"""Local-PostgreSQL tests for customer signup, sales records and payment requests."""

from urllib.parse import parse_qs, urlsplit
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from app import chatbot_helpers, google_sheets
from app.main import app, create_token, limiter
from app.models import SalesLead, SessionLocal, User, engine, init_db


@pytest.fixture
def sales_case(monkeypatch):
    if engine.url.host not in {"localhost", "127.0.0.1"}:
        pytest.skip("Sales integration test is local-only")
    init_db()
    suffix = uuid4().hex[:8]
    db = SessionLocal()
    owner = User(
        line_user_id=f"salestest.{suffix}", line_display_name="Sales Test Owner",
        role="owner", is_active=True,
    )
    db.add(owner)
    db.commit()
    db.refresh(owner)
    old_limiter = limiter.enabled
    limiter.enabled = False
    monkeypatch.setattr(google_sheets, "is_configured", lambda: False)
    monkeypatch.setattr(google_sheets, "sync_lead_row", lambda row: True)
    monkeypatch.setattr(chatbot_helpers, "notify_sales_group", lambda *args, **kwargs: None)
    try:
        yield {"db": db, "owner": owner, "suffix": suffix, "client": TestClient(app)}
    finally:
        limiter.enabled = old_limiter
        db.rollback()
        db.execute(text("DELETE FROM audit_logs WHERE user_id = :uid OR new_value LIKE :pat"),
                   {"uid": owner.id, "pat": f"%{suffix}%"})
        db.execute(text("DELETE FROM sales_records WHERE lead_id IN "
                        "(SELECT id FROM sales_leads WHERE name LIKE :pat)"),
                   {"pat": f"%{suffix}%"})
        db.execute(text("DELETE FROM sales_leads WHERE name LIKE :pat"), {"pat": f"%{suffix}%"})
        db.execute(text("DELETE FROM chatbot_profiles WHERE user_id LIKE :pat"), {"pat": f"%{suffix}%"})
        db.execute(text("DELETE FROM line_sessions WHERE user_id LIKE :pat"), {"pat": f"%{suffix}%"})
        db.execute(text("DELETE FROM customer_signup_invites WHERE line_user_id LIKE :pat"),
                   {"pat": f"%{suffix}%"})
        db.delete(owner)
        db.commit()
        db.close()


def test_line_signup_link_connects_web_customer_once(sales_case):
    suffix = sales_case["suffix"]
    uid = f"U-sales-{suffix}"
    url = chatbot_helpers.customer_signup_link(uid, "สนใจจอ", ["Iwa AiBoard"])
    assert uid not in url
    token = parse_qs(urlsplit(url).query)["ref"][0]
    client = sales_case["client"]
    payload = {
        "full_name": f"ลูกค้าทดสอบ {suffix}", "phone": "0812345678",
        "consent": True, "ref": token,
    }
    response = client.post("/api/public/customer-signup", json=payload)
    assert response.status_code == 201, response.text
    lead_id = response.json()["id"]
    db = sales_case["db"]
    db.rollback()
    lead = db.get(SalesLead, lead_id)
    assert lead is not None
    assert lead.user_id == uid
    assert lead.products == "Iwa AiBoard"
    assert lead.source == "WEB"
    assert client.post("/api/public/customer-signup", json=payload).status_code == 400


def test_deals_and_payment_requests_are_separate_and_authorized(sales_case):
    db = sales_case["db"]
    suffix = sales_case["suffix"]
    lead = SalesLead(name=f"ลูกค้าทดสอบ {suffix}", phone="0899999999", source="WEB", status="new")
    db.add(lead)
    db.commit()
    db.refresh(lead)
    client = sales_case["client"]
    deal_payload = {"lead_id": lead.id, "kind": "deal", "product": "Iwa AiBoard", "quantity": 2,
                    "amount_thb": "150000.00"}
    assert client.post("/api/sales/records", json=deal_payload).status_code == 401
    headers = {"Authorization": f"Bearer {create_token(sales_case['owner'])}"}
    deal = client.post("/api/sales/records", json=deal_payload, headers=headers)
    assert deal.status_code == 201, deal.text
    assert deal.json()["status"] == "interested"
    payment = client.post("/api/sales/records", json={
        "lead_id": lead.id, "kind": "payment_request", "product": "Iwa AiBoard", "quantity": 1,
    }, headers=headers)
    assert payment.status_code == 201, payment.text
    assert payment.json()["status"] == "requested"
    assert client.patch(f"/api/sales/records/{payment.json()['id']}",
                        json={"status": "won"}, headers=headers).status_code == 422
    assert client.patch(f"/api/sales/records/{deal.json()['id']}",
                        json={"status": "won"}, headers=headers).status_code == 200
    summary = client.get("/api/sales/summary", headers=headers)
    assert summary.status_code == 200
    assert summary.json()["won_deals"] >= 1
    assert summary.json()["payment_requests"] >= 1
    assert client.delete(f"/api/sales/leads/{lead.id}", headers=headers).status_code == 409


def test_demo_leads_do_not_affect_real_sales_summary_or_sheet(sales_case, monkeypatch):
    db = sales_case["db"]
    suffix = sales_case["suffix"]
    client = sales_case["client"]
    headers = {"Authorization": f"Bearer {create_token(sales_case['owner'])}"}
    before = client.get("/api/sales/summary", headers=headers).json()
    demo = SalesLead(name=f"[DEMO] {suffix}", source="DEMO", status="new")
    db.add(demo)
    db.commit()
    db.refresh(demo)
    monkeypatch.setattr(google_sheets, "is_configured", lambda: True)
    synced = []
    monkeypatch.setattr(google_sheets, "sync_sales_record_row", lambda row: synced.append(row))
    created = client.post("/api/sales/records", json={
        "lead_id": demo.id, "kind": "deal", "product": "Demo screen", "amount_thb": "500.00",
    }, headers=headers)
    assert created.status_code == 201, created.text
    record_id = created.json()["id"]
    assert client.patch(f"/api/sales/records/{record_id}", json={"status": "won"}, headers=headers).status_code == 200
    after = client.get("/api/sales/summary", headers=headers).json()
    assert after["lead_count"] == before["lead_count"]
    assert after["won_deals"] == before["won_deals"]
    assert after["won_amount_thb"] == before["won_amount_thb"]
    assert after["demo_lead_count"] == before["demo_lead_count"] + 1
    assert client.post(f"/api/sales/leads/{demo.id}/sync-sheet", headers=headers).status_code == 400
    assert client.post(f"/api/sales/records/{record_id}/sync-sheet", headers=headers).status_code == 400
    assert synced == []
