"""Warranty/rating/payment commands must bypass generative intent routing."""
from app import chatbot_core, chatbot_helpers, chatbot_warranty, chatbot_rating, chatbot_sales, chatbot_knowledge


def _stub_session(monkeypatch):
    state = {"phase": "new"}
    monkeypatch.setattr(chatbot_core, "get_session", lambda _uid: dict(state))
    monkeypatch.setattr(chatbot_core, "save_session", lambda _uid, value: state.update(value))
    monkeypatch.setattr(chatbot_helpers, "get_profile", lambda _uid: {"phone": "0812345678", "last_ticket_id": "TK-1"})
    monkeypatch.setattr(chatbot_helpers, "log_conversation", lambda *a, **k: None)
    monkeypatch.setattr(chatbot_helpers, "record_faq_interaction", lambda *a, **k: None)
    return state


def test_warranty_requires_code_then_uses_db_lookup(monkeypatch):
    state = _stub_session(monkeypatch)
    seen = []
    monkeypatch.setattr(chatbot_warranty, "warranty_answer", lambda code: seen.append(code) or "ข้อมูลจากทะเบียน")
    first = chatbot_core.handle_message("u-test", "ตรวจประกันได้ไหม", "")
    assert "ขอรหัสอุปกรณ์" in first and state["phase"] == "warranty_pending"
    second = chatbot_core.handle_message("u-test", "SERIAL-12345", "")
    assert second == "ข้อมูลจากทะเบียน" and seen == ["SERIAL-12345"]


def test_rating_and_payment_go_to_structured_handlers(monkeypatch):
    state = _stub_session(monkeypatch)
    monkeypatch.setattr(chatbot_rating, "record_rating", lambda *a: "บันทึกคะแนนแล้ว")
    assert chatbot_core.handle_message("u-test", "ประเมินบอท 5", "") == "บันทึกคะแนนแล้ว"
    monkeypatch.setattr(chatbot_sales, "request_line_payment", lambda _uid, product: f"รับคำขอ {product}")
    asked = chatbot_core.handle_message("u-test", "ต้องการชำระเงิน", "")
    assert "สินค้า/บริการใด" in asked and state["phase"] == "payment_product_pending"
    assert chatbot_core.handle_message("u-test", "กล้องสอนออนไลน์", "") == "รับคำขอ กล้องสอนออนไลน์"


def test_reviewed_general_answer_does_not_override_live_facts(monkeypatch):
    _stub_session(monkeypatch)
    seen = []
    monkeypatch.setattr(chatbot_helpers, "detect_intent", lambda _text: "other")
    monkeypatch.setattr(chatbot_knowledge, "answer_for_question", lambda value: seen.append(value) or "คำตอบที่ตรวจแล้ว")
    assert chatbot_core.handle_message("u-test", "เปิดให้บริการวันใด", "") == "คำตอบที่ตรวจแล้ว"
    assert seen == ["เปิดให้บริการวันใด"]
    monkeypatch.setattr(chatbot_warranty, "warranty_answer", lambda _code: "ข้อมูลประกันจากทะเบียน")
    assert chatbot_core.handle_message("u-test", "ประกัน SERIAL-12345", "") == "ข้อมูลประกันจากทะเบียน"
    assert seen == ["เปิดให้บริการวันใด"]
