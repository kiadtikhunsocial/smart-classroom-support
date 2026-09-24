"""Optional, task-specific chatbot guidance. Core safety/grounding rules stay in code."""
from pathlib import Path
import logging

_ROOT = Path(__file__).resolve().parent.parent / "chatbot_prompts"
_ALLOWED = frozenset({"global_style", "intent", "field_extraction", "kb_match", "kb_explanation",
                      "orchestration", "repair_reply", "slot_question", "line_reply"})
ALLOWED_PROMPT_TASKS = tuple(sorted(_ALLOWED))
logger = logging.getLogger(__name__)


def guidance_for_task(task: str) -> str:
    if task not in _ALLOWED:
        raise ValueError(f"Unknown chatbot prompt task: {task}")
    try:
        from app.models import ChatbotPromptSetting, SessionLocal
        with SessionLocal() as db:
            setting = db.get(ChatbotPromptSetting, task)
            if setting is not None:
                return setting.guidance.strip()[:2000] if setting.enabled else ""
    except Exception:
        # A temporary DB outage must not disable the chatbot. This also lets
        # a new release run safely before the create-only migration completes.
        logger.exception("Could not read chatbot prompt setting for %s", task)
    try:
        return (_ROOT / f"{task}.txt").read_text(encoding="utf-8").strip()[:2000]
    except FileNotFoundError:
        return ""


def with_extension(task: str, prompt: str) -> str:
    guidance = guidance_for_task(task)
    global_guidance = guidance_for_task("global_style") if task != "global_style" else ""
    combined = "\n".join(value for value in (global_guidance, guidance) if value)
    if not combined:
        return prompt
    return (prompt + "\n\nแนวทางเพิ่มเติมสำหรับงานนี้ (ใช้เฉพาะเมื่อไม่ขัดกับกฎความปลอดภัย "
            "รูปแบบ JSON และข้อมูลอ้างอิงข้างต้น):\n" + combined)
