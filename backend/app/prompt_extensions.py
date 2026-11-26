"""prompt_extensions.py — คำแนะนำ AI ที่แก้ได้โดยไม่ต้องแตะโค้ด (แยกตาม "งาน")

ภาพรวม
------
prompt หลักของแต่ละงาน (กฎความปลอดภัย, รูปแบบ JSON, ข้อมูลอ้างอิง) อยู่ในโค้ดและห้ามแก้ผ่านไฟล์นี้
ส่วนที่แก้ได้คือ "คำแนะนำเพิ่มเติม" ที่ต่อท้าย prompt หลักผ่าน ``with_extension(task, prompt)``

ค่าคำแนะนำของแต่ละงานมาจาก 2 ที่ (เรียงตามลำดับความสำคัญ):
  1. ตาราง ``chatbot_prompt_settings`` ในฐานข้อมูล (Supabase)
     แก้จากเว็บ: เมนู "จัดการ AI / LINE OA" → แท็บ "คำแนะนำ AI" (owner/super_admin) มีผลทันที ไม่ต้อง deploy
  2. ไฟล์ ``backend/chatbot_prompts/<task>.txt`` — ค่าเริ่มต้นที่มากับโค้ด (ต้อง deploy ใหม่ถึงมีผล)
     **ใช้เฉพาะเมื่อยังไม่เคยบันทึกงานนั้นจากเว็บ** ถ้าเคยบันทึกแล้ว แก้ไฟล์จะไม่มีผล
     ให้กด "กลับไปใช้ค่าจากไฟล์" บนเว็บ (DELETE /api/chatbot/manage/prompts/{task}) ก่อน

งานที่มี (ต้องตรงกับ PROMPT_LABELS ใน frontend/src/components/ChatbotStudioPage.tsx):
  global_style      ต่อท้ายทุกงาน (น้ำเสียงร่วม)
  intent, field_extraction, kb_match, kb_explanation, orchestration,
  repair_reply, slot_question  → app/gemini_service.py (สายแชตบอต LINE)
  line_reply        → app/line_bot.py (ข้อความตอบกลับใน LINE)
  web_chat          → app/web_agent.py (แชต AI บนหน้าเว็บ POST /api/chatbot/web)

เพิ่มงานใหม่: ใส่ชื่อใน ``_ALLOWED`` + เรียก ``with_extension("<ชื่อ>", prompt)`` ที่จุดสร้าง prompt
+ เพิ่ม label ใน ChatbotStudioPage.tsx + (ถ้าต้องการ) ไฟล์ค่าเริ่มต้น ``chatbot_prompts/<ชื่อ>.txt``
แผนที่ prompt ทั้งหมด: backend/chatbot_prompts/README.md
"""
from pathlib import Path
import logging

_ROOT = Path(__file__).resolve().parent.parent / "chatbot_prompts"
_ALLOWED = frozenset({"global_style", "intent", "field_extraction", "kb_match", "kb_explanation",
                      "orchestration", "repair_reply", "slot_question", "line_reply", "web_chat"})
ALLOWED_PROMPT_TASKS = tuple(sorted(_ALLOWED))
MAX_GUIDANCE_CHARS = 2000
logger = logging.getLogger(__name__)


def file_guidance(task: str) -> str:
    """ค่าเริ่มต้นจากไฟล์ chatbot_prompts/<task>.txt (ว่างถ้าไม่มีไฟล์)"""
    if task not in _ALLOWED:
        raise ValueError(f"Unknown chatbot prompt task: {task}")
    try:
        return (_ROOT / f"{task}.txt").read_text(encoding="utf-8").strip()[:MAX_GUIDANCE_CHARS]
    except FileNotFoundError:
        return ""


def guidance_for_task(task: str) -> str:
    """คำแนะนำที่ใช้จริงตอนนี้: ค่าใน DB ถ้ามี (ถ้าปิดไว้ = ว่าง) ไม่งั้นค่าจากไฟล์"""
    if task not in _ALLOWED:
        raise ValueError(f"Unknown chatbot prompt task: {task}")
    try:
        from app.models import ChatbotPromptSetting, SessionLocal
        with SessionLocal() as db:
            setting = db.get(ChatbotPromptSetting, task)
            if setting is not None:
                return setting.guidance.strip()[:MAX_GUIDANCE_CHARS] if setting.enabled else ""
    except Exception:
        # A temporary DB outage must not disable the chatbot. This also lets
        # a new release run safely before the create-only migration completes.
        logger.exception("Could not read chatbot prompt setting for %s", task)
    return file_guidance(task)


def with_extension(task: str, prompt: str) -> str:
    """ต่อท้าย prompt หลักด้วย global_style + คำแนะนำของงาน (prompt หลักชนะเสมอเมื่อขัดกัน)"""
    guidance = guidance_for_task(task)
    global_guidance = guidance_for_task("global_style") if task != "global_style" else ""
    combined = "\n".join(value for value in (global_guidance, guidance) if value)
    if not combined:
        return prompt
    return (prompt + "\n\nแนวทางเพิ่มเติมสำหรับงานนี้ (ใช้เฉพาะเมื่อไม่ขัดกับกฎความปลอดภัย "
            "รูปแบบ JSON และข้อมูลอ้างอิงข้างต้น):\n" + combined)
