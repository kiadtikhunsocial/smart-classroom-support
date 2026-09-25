"""Real PostgreSQL flow from LINE chat link to QR form to private ticket details."""
import uuid
from urllib.parse import parse_qs, urlsplit

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app.chatbot_core import handle_message
from app.chatbot_rating import record_rating
from app.chat_session import save_session
from app.main import app
from app.models import Device, Organization, RepairTicket, SessionLocal, init_db
from app.ticket_rating_invite import invite_staff_rating


def test_line_link_binds_public_ticket_once_and_replies_to_original_user(monkeypatch):
    try:
        init_db()
        db = SessionLocal()
        db.execute(text("SELECT 1"))
    except Exception as exc:
        pytest.skip(f"Local database unavailable: {exc}")
    suffix = uuid.uuid4().hex[:8].upper()
    uid = f"line-bridge-{suffix}"
    other_uid = f"other-line-{suffix}"
    org = Organization(code=f"LR{suffix[:6]}", name="LINE bridge test")
    db.add(org); db.flush()
    device = Device(device_id=f"LR{suffix[:6]}-CAM-01", organization_id=org.id,
                    device_type="Camera", status="active")
    db.add(device); db.commit()
    pushed = []
    monkeypatch.setenv("REPORT_FORM_URL", "https://example.test/?publicreport=1")
    monkeypatch.setattr("app.line_report_link.send_line_push",
                        lambda to, message: pushed.append((to, message)) or True)
    monkeypatch.setattr("app.ticket_rating_invite.send_line_push",
                        lambda to, message: pushed.append((to, message)) or True)
    monkeypatch.setattr("app.main._notify_n8n", lambda *_: None)
    monkeypatch.setattr("app.gemini_service.phrase_repair_reply", lambda *_: None)
    token = None
    ticket_id = None
    try:
        save_session(uid, {"phase": "new", "resolving": True, "symptom_buf": "กล้องไม่ทำงาน"})
        reply = handle_message(uid, "ยังไม่หาย", "")
        link = next((part for part in reply.split() if part.startswith("https://example.test/")), None)
        assert link and "line-bridge" not in link
        token = parse_qs(urlsplit(link).fragment)["line_link"][0]
        assert token not in urlsplit(link).query
        logged = db.execute(text("SELECT ai_response FROM chatbot_logs WHERE user_id = :uid "
                                 "ORDER BY id DESC LIMIT 1"), {"uid": uid}).scalar_one()
        assert token not in logged and "REDACTED" in logged
        session_data = db.execute(text("SELECT data::text FROM line_sessions WHERE user_id = :uid"),
                                  {"uid": uid}).scalar_one()
        assert token not in session_data
        client = TestClient(app)
        payload = {"organization_code": org.code, "device_id": device.device_id,
                   "title": "กล้องไม่ทำงาน", "reporter_name": "ผู้ทดสอบ",
                   "reporter_phone": "0812345678", "line_report_token": token,
                   "scan_gps_lat": 13.75, "scan_gps_lng": 100.5}
        created = client.post("/api/public/report", json=payload)
        assert created.status_code == 201, created.text
        result = created.json()
        ticket_id = result["ticket_id"]
        assert result["line_receipt_sent"] is True
        assert pushed == [(uid, pushed[0][1])]
        assert ticket_id in pushed[0][1]
        db.expire_all()
        ticket = db.execute(select(RepairTicket).where(RepairTicket.ticket_id == ticket_id)).scalar_one()
        assert ticket.line_user_id == uid
        assert ticket.channel == "public"
        assert float(ticket.scan_gps_lat) == 13.75
        assert float(ticket.scan_gps_lng) == 100.5
        assert ticket_id in handle_message(uid, "รายละเอียดใบงาน", "")
        assert ticket_id in handle_message(uid, "ช่างซ่อมถึงไหนแล้ว", "")
        assert ticket_id not in handle_message(other_uid, "รายละเอียดใบงาน", "")
        reused = client.post("/api/public/report", json=payload)
        assert reused.status_code == 422
        assert reused.json()["detail"]["code"] == "LINE_REPORT_LINK_EXPIRED"
        expired_reply = handle_message(uid, "ขอลิงก์แจ้งซ่อม", "")
        expired_url = next(part for part in expired_reply.split() if part.startswith("https://example.test/"))
        expired_token = parse_qs(urlsplit(expired_url).fragment)["line_link"][0]
        from app.line_report_link import _token_hash
        db.execute(text("UPDATE line_report_links SET expires_at = now() - interval '1 minute' "
                        "WHERE token_hash = :h"), {"h": _token_hash(expired_token)})
        db.commit()
        expired = client.post("/api/public/report", json={**payload, "line_report_token": expired_token})
        assert expired.status_code == 422
        assert expired.json()["detail"]["code"] == "LINE_REPORT_LINK_EXPIRED"
        ticket.status = "resolved"
        db.commit()
        assert invite_staff_rating(db, ticket) is True
        assert len(pushed) == 2 and pushed[1][0] == uid
        assert "5/5" in record_rating(uid, f"ประเมินเจ้าหน้าที่ {ticket_id} 5", None)
        assert "ยังประเมินงานนี้ไม่ได้" in record_rating(
            other_uid, f"ประเมินเจ้าหน้าที่ {ticket_id} 5", "0812345678", ticket_id)
    finally:
        db.rollback()
        if ticket_id:
            db.execute(text("DELETE FROM line_service_ratings WHERE ticket_id = :tid"), {"tid": ticket_id})
            db.execute(text("DELETE FROM scan_logs WHERE ticket_id = :tid"), {"tid": ticket_id})
            db.execute(text("DELETE FROM ticket_updates WHERE ticket_id = "
                            "(SELECT id FROM repair_tickets WHERE ticket_id = :tid)"), {"tid": ticket_id})
            db.execute(text("DELETE FROM repair_tickets WHERE ticket_id = :tid"), {"tid": ticket_id})
        db.execute(text("DELETE FROM line_report_links WHERE line_user_id = :uid"), {"uid": uid})
        db.execute(text("DELETE FROM chatbot_logs WHERE user_id IN (:u, :other)"),
                   {"u": uid, "other": other_uid})
        db.execute(text("DELETE FROM line_sessions WHERE user_id IN (:u, :other)"),
                   {"u": uid, "other": other_uid})
        db.delete(device); db.delete(org); db.commit(); db.close()
