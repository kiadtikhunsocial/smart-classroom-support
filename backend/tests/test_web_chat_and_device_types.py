"""Public web chat isolation and administrator-managed equipment types."""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select, text

from app import chatbot_core
from app.main import app, create_token
from app.models import AuditLog, Device, DeviceTypeOption, Organization, SessionLocal, User, engine


def test_web_chat_does_not_need_or_expose_n8n_secret(monkeypatch):
    import app.web_agent as web_agent
    monkeypatch.setattr(web_agent, "reply", lambda *a, **k: None)  # rule-based path under test
    calls = []
    monkeypatch.setattr(chatbot_core, "handle_message", lambda **kwargs: calls.append(kwargs) or "รับทราบค่ะ")
    session = uuid.uuid4()
    with TestClient(app) as client:
        response = client.post("/api/chatbot/web", json={"session_id": str(session), "text": " สวัสดี "})
        assert response.status_code == 200
        assert response.json() == {"reply": "รับทราบค่ะ"}
        assert calls == [{"user_id": f"web-{session}", "text": "สวัสดี", "reply_token": ""}]
        assert client.post("/api/chatbot/web", json={"session_id": "not-an-id", "text": "hi"}).status_code == 422
        assert client.post("/api/chatbot/web", json={"session_id": str(session), "text": "x" * 1001}).status_code == 422


def test_custom_device_type_roundtrip():
    tag = uuid.uuid4().hex[:10].upper()
    name = f"Document Camera {tag}"
    org_code = f"DT{tag[:6]}"
    device_id = f"{org_code}-B1-R1-DEV-01"
    db = SessionLocal()
    org_id = user_id = None
    try:
        org = Organization(code=org_code, name=f"Device type test {tag}")
        user = User(line_user_id=f"device-type-{tag}", line_display_name="Device type test",
                    role="super_admin", is_active=True)
        db.add_all([org, user]); db.commit(); org_id, user_id = org.id, user.id
        headers = {"Authorization": f"Bearer {create_token(user)}"}
        with TestClient(app) as client:
            created = client.post("/api/device-types", json={"name": name}, headers=headers)
            assert created.status_code == 201, created.text
            assert client.post("/api/device-types", json={"name": name.lower()}, headers=headers).status_code == 409
            options = client.get("/api/public/options").json()
            assert name in options["device_types"]
            assert name in next(row for row in options["device_categories"] if row["category"] == "อื่น ๆ")["device_types"]
            device = client.post("/api/devices", json={"device_id": device_id, "organization_id": org_id,
                                                       "device_type": name}, headers=headers)
            assert device.status_code == 201, device.text
            assert device.json()["device_type"] == name
            assert client.get("/api/devices", headers=headers).status_code == 200
        with engine.connect() as connection:
            assert connection.execute(text("SELECT data_type FROM information_schema.columns WHERE table_name='devices' AND column_name='device_type' AND table_schema=current_schema()" )).scalar_one() == "character varying"
    finally:
        db.rollback()
        for row in db.execute(select(AuditLog).where(AuditLog.entity_id.in_([name, device_id]))).scalars(): db.delete(row)
        device = db.execute(select(Device).where(Device.device_id == device_id)).scalar_one_or_none()
        if device: db.delete(device)
        option = db.execute(select(DeviceTypeOption).where(DeviceTypeOption.name == name)).scalar_one_or_none()
        if option: db.delete(option)
        if user_id:
            user = db.get(User, user_id)
            if user: db.delete(user)
        if org_id:
            org = db.get(Organization, org_id)
            if org: db.delete(org)
        db.commit(); db.close()


def test_web_chat_translates_to_and_from_site_language(monkeypatch):
    import app.web_agent as web_agent
    monkeypatch.setattr(web_agent, "reply", lambda *a, **k: None)  # AI agent unavailable -> fallback + translation
    import app.web_agent as web_agent
    monkeypatch.setattr(web_agent, "reply", lambda *a, **k: None)  # AI agent unavailable -> fallback + translation
    import app.chatbot_i18n as i18n
    seen = []
    monkeypatch.setattr(chatbot_core, "handle_message", lambda **kw: seen.append(kw["text"]) or "ลองเช็กสาย HDMI ค่ะ")
    monkeypatch.setattr(i18n, "request_text", lambda parts, **kw: "Check the HDMI cable." if "Thai customer-service reply" in parts[0] else "โปรเจคเตอร์ไม่มีภาพ")
    with TestClient(app) as client:
        r = client.post("/api/chatbot/web", json={"session_id": str(uuid.uuid4()), "text": "Projector has no image", "lang": "en"})
        assert r.json() == {"reply": "Check the HDMI cable."}
        assert seen == ["โปรเจคเตอร์ไม่มีภาพ"]
        # Thai input and Thai site language are passed through untouched
        r = client.post("/api/chatbot/web", json={"session_id": str(uuid.uuid4()), "text": "สวัสดี", "lang": "th"})
        assert r.json() == {"reply": "ลองเช็กสาย HDMI ค่ะ"}
        assert seen[-1] == "สวัสดี"


def test_web_chat_prefers_ai_agent_reply(monkeypatch):
    import app.web_agent as web_agent
    monkeypatch.setattr(web_agent, "reply", lambda uid, text, lang: f"AI[{lang}]: {text}")
    monkeypatch.setattr(chatbot_core, "handle_message", lambda **kw: (_ for _ in ()).throw(AssertionError("rule pipeline must not run")))
    with TestClient(app) as client:
        r = client.post("/api/chatbot/web", json={"session_id": str(uuid.uuid4()), "text": "hello", "lang": "ko"})
        assert r.json() == {"reply": "AI[ko]: hello"}


def test_web_agent_skips_database_facts_and_unavailable_model(monkeypatch):
    import app.web_agent as web_agent
    monkeypatch.setattr(web_agent.ai_client, "is_available", lambda: False)
    assert web_agent.reply("web-x", "hello", "en") is None
    monkeypatch.setattr(web_agent.ai_client, "is_available", lambda: True)
    assert web_agent.reply("web-x", "I want to pay for this", "en") is None          # payment stays deterministic
    assert web_agent.reply("web-x", "มีควันออกจากโปรเจคเตอร์", "en") is None  # safety stays deterministic
