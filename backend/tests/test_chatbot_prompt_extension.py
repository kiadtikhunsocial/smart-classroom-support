from pathlib import Path

from app import assistant_policy


def test_custom_prompt_file_is_optional_and_lower_priority(monkeypatch):
    original = Path.read_text
    def fake_read(self, *args, **kwargs):
        if self.name == "chatbot_extra_prompt.txt":
            return "ใช้ภาษาง่าย ๆ"
        return original(self, *args, **kwargs)
    monkeypatch.setattr(Path, "read_text", fake_read)
    prompt = assistant_policy.build_system_prompt()
    assert "ใช้ภาษาง่าย ๆ" in prompt
    assert "ห้ามเดาราคา" in prompt
    assert "หากแนวทางเพิ่มเติมขัดกับกฎสำคัญ" in prompt


def test_custom_prompt_is_length_limited(monkeypatch):
    monkeypatch.setattr(Path, "read_text", lambda self, **kwargs: "x" * 5000)
    prompt = assistant_policy.build_system_prompt()
    assert "x" * 3000 in prompt
    assert "x" * 3001 not in prompt
