"""Top-level chatbot management: DB knowledge, prompt override and private ratings."""
import uuid

import pytest
from sqlalchemy import text
from starlette.testclient import TestClient

from app.main import app, create_token
from app.models import (ChatbotKnowledgeEntry, ChatbotPromptSetting, LineServiceRating,
                        SessionLocal, User, init_db)
from app.chatbot_knowledge import answer_for_question
from app.prompt_extensions import with_extension


@pytest.fixture
def studio():
    try:
        init_db()
    except Exception as exc:
        pytest.skip(f"PostgreSQL unavailable: {exc}")
    db = SessionLocal()
    suffix = uuid.uuid4().hex[:12]
    previous_prompt = db.get(ChatbotPromptSetting, "line_reply")
    prompt_backup = ({"guidance": previous_prompt.guidance, "enabled": previous_prompt.enabled,
                      "updated_by": previous_prompt.updated_by} if previous_prompt else None)
    admin = User(line_user_id=f"studio-admin-{suffix}", role="super_admin", is_active=True)
    regular = User(line_user_id=f"studio-regular-{suffix}", role="admin", is_active=True)
    db.add_all([admin, regular]); db.commit()
    headers = {"Authorization": f"Bearer {create_token(admin)}"}
    denied = {"Authorization": f"Bearer {create_token(regular)}"}
    try:
        yield TestClient(app), headers, denied, suffix
    finally:
        db.rollback()
        db.execute(text("DELETE FROM audit_logs WHERE user_id IN (:a, :r)"), {"a": admin.id, "r": regular.id})
        db.execute(text("DELETE FROM chatbot_knowledge_entries WHERE updated_by = :a"), {"a": admin.id})
        if prompt_backup is None:
            db.execute(text("DELETE FROM chatbot_prompt_settings WHERE task = 'line_reply' AND updated_by = :a"), {"a": admin.id})
        else:
            prompt = db.get(ChatbotPromptSetting, "line_reply")
            prompt.guidance = prompt_backup["guidance"]
            prompt.enabled = prompt_backup["enabled"]
            prompt.updated_by = prompt_backup["updated_by"]
        db.execute(text("DELETE FROM line_service_ratings WHERE line_user_id = :uid"), {"uid": suffix})
        db.delete(admin); db.delete(regular); db.commit(); db.close()


def test_knowledge_is_draft_until_published_and_role_is_enforced(studio):
    client, headers, denied, suffix = studio
    question = f"เปิดให้บริการวันใด {suffix}"
    payload = {"question": question, "answer": "เปิดวันจันทร์ถึงศุกร์ค่ะ", "aliases": [], "is_published": False}
    assert client.post("/api/chatbot/manage/knowledge", json=payload, headers=denied).status_code == 403
    created = client.post("/api/chatbot/manage/knowledge", json=payload, headers=headers)
    assert created.status_code == 201, created.text
    assert answer_for_question(question) is None
    payload["is_published"] = True
    updated = client.put(f"/api/chatbot/manage/knowledge/{created.json()['id']}", json=payload, headers=headers)
    assert updated.status_code == 200, updated.text
    assert answer_for_question(question) == payload["answer"]
    assert client.get("/api/chatbot/manage/knowledge", headers=denied).status_code == 403
    assert client.post("/api/chatbot/manage/knowledge", json={**payload, "question": f"ราคา {suffix}"}, headers=headers).status_code == 422


def test_prompt_override_and_ratings_are_private(studio):
    client, headers, denied, suffix = studio
    assert client.get("/api/chatbot/manage/prompts", headers=denied).status_code == 403
    response = client.put("/api/chatbot/manage/prompts/line_reply", headers=headers,
                          json={"guidance": f"ใช้คำสั้น {suffix}", "enabled": True})
    assert response.status_code == 200, response.text
    assert suffix in with_extension("line_reply", "ฐาน")
    assert client.put("/api/chatbot/manage/prompts/not-a-task", headers=headers,
                      json={"guidance": "x", "enabled": True}).status_code == 404
    db = SessionLocal()
    try:
        db.add(LineServiceRating(line_user_id=suffix, target="bot", score=5)); db.commit()
    finally:
        db.close()
    assert client.get("/api/chatbot/manage/ratings", headers=denied).status_code == 403
    ratings = client.get("/api/chatbot/manage/ratings", headers=headers)
    assert ratings.status_code == 200
    assert any(item["score"] == 5 for item in ratings.json()["recent"])
    general_report = client.get("/api/reports/chatbot-analytics", headers=denied)
    assert general_report.status_code == 200
    assert "line_ratings" not in general_report.json()


def test_global_style_is_added_without_replacing_fixed_prompt(monkeypatch):
    from app import prompt_extensions
    monkeypatch.setattr(prompt_extensions, "guidance_for_task",
                        lambda task: {"global_style": "สุภาพและกระชับ", "line_reply": "ถามทีละข้อ"}.get(task, ""))
    combined = prompt_extensions.with_extension("line_reply", "กฎเดิม")
    assert "กฎเดิม" in combined and "สุภาพและกระชับ" in combined and "ถามทีละข้อ" in combined
