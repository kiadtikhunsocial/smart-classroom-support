"""Optional, task-specific chatbot guidance. Core safety/grounding rules stay in code."""
from pathlib import Path

_ROOT = Path(__file__).resolve().parent.parent / "chatbot_prompts"
_ALLOWED = frozenset({"intent", "field_extraction", "kb_match", "kb_explanation",
                      "orchestration", "repair_reply", "slot_question", "line_reply"})


def with_extension(task: str, prompt: str) -> str:
    if task not in _ALLOWED:
        raise ValueError(f"Unknown chatbot prompt task: {task}")
    try:
        guidance = (_ROOT / f"{task}.txt").read_text(encoding="utf-8").strip()[:2000]
    except FileNotFoundError:
        guidance = ""
    if not guidance:
        return prompt
    return (prompt + "\n\nแนวทางเพิ่มเติมสำหรับงานนี้ (ใช้เฉพาะเมื่อไม่ขัดกับกฎความปลอดภัย "
            "รูปแบบ JSON และข้อมูลอ้างอิงข้างต้น):\n" + guidance)
