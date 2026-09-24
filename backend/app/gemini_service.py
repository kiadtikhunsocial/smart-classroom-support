"""
gemini_service.py — Google Gemini API (REST) สำหรับ AI Troubleshooting
เรียกผ่าน httpx (ไม่มี SDK dependency) ตาม TOR 5.5 / SD-05

กฎสำคัญ (ตาม spec 1.5.5 / R4):
- ตอบจาก CONTEXT (KB) ที่ให้เท่านั้น ห้ามให้ AI สร้างคำตอบเอง (กัน hallucination)
- ถ้า context ไม่พอ / ไม่เจอ → คืน found=False ให้ส่งต่อช่าง
- timeout สั้น (5 วินาที) — ถ้า API ช้า/ล่ม คืน None ให้ caller ใช้ KB ดิบ (fallback)
"""
import os
import json
import re
from typing import Optional

from app.ai_client import is_available as _ai_available
from app.ai_client import request_json, request_text
from app.prompt_extensions import with_extension


def mask_pii(text: str) -> str:
    """mask ข้อมูลส่วนบุคคลก่อนส่ง Gemini — ลดความเสี่ยง data privacy กับ 3rd-party AI
    - เบอร์โทร (ไทย) → 08X-XXX-XXXX   - email → a***@domain"""
    if not text:
        return text
    text = re.sub(r'(?<!\d)(\+?66)?0\d{1,2}[- ]?\d{3}[- ]?\d{3,4}', '08X-XXX-XXXX', text)
    text = re.sub(r'[\w.+-]+@[\w-]+\.[\w.]+',
                  lambda m: m.group(0).split('@')[0][:2] + '***@' + m.group(0).split('@')[1], text)
    text = re.sub(r'(?<!\w)@[A-Za-z0-9_.-]{3,}', '@***', text)
    return text


API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview")
_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
ENABLE_NATURAL_REPLIES = os.environ.get("ENABLE_GEMINI_NATURAL_REPLIES", "0").lower() in {"1", "true", "yes", "on"}

# Prompt ที่บังคับตอบจาก KB เท่านั้น (ตาม spec 4.6 หลักการออกแบบ Prompt)
try:
    from app.assistant_policy import build_system_prompt
    _BASE_POLICY = build_system_prompt()
except Exception:
    _BASE_POLICY = "คุณคือผู้ช่วย IT ของระบบ Smart Classroom ตอบจาก CONTEXT เท่านั้น"
_SYSTEM_PROMPT = _BASE_POLICY + """

คุณคือผู้ช่วยเจ้าหน้าที่ IT ของโรงเรียน (ระบบ Smart Classroom)

กฎเหล็ก:
1. ตอบจากข้อมูลใน CONTEXT ที่ให้เท่านั้น ห้ามสร้างคำตอบเอง
2. หากข้อมูลใน CONTEXT ไม่เพียงพอ ให้ตอบว่า "ไม่พบข้อมูล"
3. ตอบเป็นขั้นตอน 3–5 ข้อ ภาษาไทยสุภาพ เข้าใจง่าย
4. ห้ามแนะนำการถอดหรือเปิดฝาอุปกรณ์
5. ห้ามแนะนำวิธีที่อาจทำให้อุปกรณ์เสียหายเพิ่ม
6. ตอบเป็น JSON เท่านั้น รูปแบบ:
   {"found": true/false, "steps": ["ข้อ 1", "ข้อ 2", ...], "summary": "สรุปสั้น 1 บรรทัด"}
   - found=true เมื่อ CONTEXT มีวิธีแก้ที่ตรงกับอาการ
   - found=false เมื่อ CONTEXT ไม่มีข้อมูลเพียงพอ (จะส่งต่อช่าง)"""


def _build_context(kb_articles: list) -> str:
    """รวม KB top candidates ให้เป็น context สั้น ๆ สำหรับ prompt"""
    parts = []
    for a in kb_articles:
        title = a.get("title", "")
        steps = a.get("steps", [])
        parts.append(f"- [{a.get('kb_id','')}] {title}\n  วิธีแก้: {' / '.join(steps)}")
    return "\n".join(parts) if parts else "(ไม่มีข้อมูลในฐานความรู้)"


def explain_steps(symptom_text: str, kb_steps: list, device_type: str = "") -> str | None:
    """ให้ Gemini ร่างคำตอบอธิบายขั้นตอนจาก KB เป็นภาษาไทยธรรมชาติ อบอุ่นเหมือนพนักงาน
    รับมือกับคำกำกวม/ภาษาพูดที่ลูกค้าพิมพ์หลากหลาย แล้วอธิบายขั้นตอนให้เข้าใจง่าย
    ยังอิงจาก kb_steps ที่ให้เท่านั้น (ห้ามสร้างขั้นตอนใหม่) — กัน hallucination
    คืนข้อความไทย หรือ None ถ้า Gemini ล่ม (caller ใช้ list เปล่าแทน)"""
    if not ENABLE_NATURAL_REPLIES or not kb_steps:
        return None
    if not API_KEY:
        return None
    step_list = "\n".join(f"{i+1}. {s}" for i, s in enumerate(kb_steps))
    prompt = (
        f"ลูกค้าแจ้งปัญหา: {mask_pii(symptom_text)}\n"
        f"ประเภทอุปกรณ์: {device_type or 'ไม่ระบุ'}\n\n"
        "ขั้นตอนแก้ไขเบื้องต้นที่ระบบระบุไว้ (ใช้ขั้นตอนเหล่านี้เท่านั้น ห้ามเพิ่ม/แก้ไข/สร้างขั้นตอนใหม่):\n"
        f"{step_list}\n\n"
        "จงเขียนคำตอบถึงลูกค้าเป็นภาษาไทย อบอุ่น เหมือนพนักงานบริการคนไทย ปรับภาษาตามที่ลูกค้าพิมพ์ "
        "(ถ้าลูกค้าพิมพ์ภาษาพูด/กำกวม/สั้น ก็ตอบแบบสบายๆ เข้าใจง่าย ไม่ยัดเยียดศัพท์เทคนิค) "
        "เกริ่นอย่างเห็นใจก่อน แล้วอธิบายขั้นตอนให้เข้าใจง่ายทีละข้อ (เรียงตามลำดับ) "
        "ปิดท้ายด้วยคำแนะนำว่า ถ้าทำแล้วไม่หาย ให้บอก 'ยังไม่หาย' เพื่อให้ช่างช่วยต่อ\n"
        "ห้ามประดิษฐ์ขั้นตอนที่ไม่ใช่ในรายการ ห้ามแนะนำการถอด/เปิดฝาอุปกรณ์ ห้ามใช้คำว่า 'ฉัน' ใช้ 'คะ/ค่ะ'"
    )
    answer = request_text(
        [_BASE_POLICY, with_extension("kb_explanation", prompt)],
        generation_config={"temperature": 0.2, "maxOutputTokens": 500},
        timeout=12.0,
        retries=1,
    )
    from app.assistant_policy import is_grounded_kb_explanation
    return answer if is_grounded_kb_explanation(answer or "", kb_steps) else None


def is_available() -> bool:
    return _ai_available()


def classify_intent(text: str) -> dict | None:
    """ให้ Gemini จำแนกเจตนาเป็น JSON — ช่วยเข้าใจภาษาไทยหลากหลาย/กำกวมที่ keyword จับไม่ได้
    คืน {"intent": "repair|buy|product|service|company|contact|track|human|greeting|thanks|other",
          "product": "ชื่อสินค้าที่พูดถึง(ถ้ามี)", "service": "บริการที่พูดถึง(ถ้ามี)",
          "confidence": 0-1}
    คืน None ถ้า Gemini ล่ม/429 → caller ใช้ keyword fallback เดิม"""
    if not API_KEY:
        return None
    prompt = (
        "จงจำแนกเจตนาของข้อความลูกค้าต่อไปนี้ (ธุรกิจขาย ICT + สื่อการเรียนของไทย):\n"
        f"ข้อความ: {mask_pii(text)}\n\n"
        "เลือก 1 เจตนาจาก: repair(แจ้งซ่อม/ปัญหาอุปกรณ์), buy(อยากซื้อ/ถามราคา/สั่งซื้อ), "
        "product(ถามข้อมูลสินค้าตัวไหน), service(ถามบริการตัวไหน), company(ถามข้อมูลบริษัท), "
        "contact(ขอช่องทางติดต่อ), track(ติดตามงาน/ticket), human(อยากคุยคนจริง), "
        "greeting(ทักทาย), thanks(ขอบคุณ), other\n"
        "ตอบ JSON เท่านั้น รูปแบบ: "
        '{"intent":"...","product":"ชื่อสินค้า(ถ้าเจอ ไม่มี=ว่าง)","service":"ชื่อบริการ(ถ้าเจอ ไม่มี=ว่าง)","confidence":0.0-1.0}'
    )
    parsed = request_json(
        [_BASE_POLICY, with_extension("intent", prompt)],
        generation_config={"temperature": 0.0, "maxOutputTokens": 120},
        timeout=8.0,
        retries=1,
    )
    if not parsed:
        return None
    valid_intents = {"repair", "buy", "product", "service", "company", "contact",
                     "track", "human", "greeting", "thanks", "other"}
    intent = parsed.get("intent", "other")
    if intent not in valid_intents:
        intent = "other"
    try:
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "intent": intent,
        "product": str(parsed.get("product", "") or ""),
        "service": str(parsed.get("service", "") or ""),
        "confidence": confidence,
    }


def extract_fields_ai(text: str, known: dict, missing_keys: list[str]) -> dict:
    """ให้ Gemini ดึงข้อมูล (ชื่อ/เบอร์/อุปกรณ์/อาการ) จากข้อความอิสระของผู้ใช้
    รับข้อความภาษาพูด/กำกวม/หลายข้อมูลในประโยคเดียวได้ดีกว่า regex เดิม
    คืน dict เฉพาะ key ที่สกัดได้ใหม่ หรือ {} ถ้า Gemini ล่ม/ไม่มี key (caller ใช้ regex fallback ต่อ)"""
    if not API_KEY or not missing_keys:
        return {}
    prompt = (
        f'ข้อความจากลูกค้า: "{mask_pii(text)}"\n'
        f"ข้อมูลที่มีอยู่แล้ว: {json.dumps({k: mask_pii(str(v)) for k, v in (known or {}).items()}, ensure_ascii=False)}\n"
        f"ข้อมูลที่ยังขาดและต้องพยายามดึงจากข้อความนี้: {missing_keys}\n\n"
        "จงดึงเฉพาะข้อมูลที่ปรากฏชัดเจนในข้อความ ห้ามเดา/แต่งข้อมูลที่ไม่มี\n"
        "field ที่เป็นไปได้: name (ชื่อคนเท่านั้น ไม่ใช่ประโยคอาการ/คำอุทาน), "
        "phone (เบอร์โทร), device_id (ชื่ออุปกรณ์/ห้อง/รหัส), symptom (คำอธิบายอาการ)\n"
        'ตอบเป็น JSON เท่านั้น: {"name": "...หรือ null", "phone": "...หรือ null", '
        '"device_id": "...หรือ null", "symptom": "...หรือ null"}'
    )
    parsed = request_json(
        [_BASE_POLICY, with_extension("field_extraction", prompt)],
        generation_config={"temperature": 0.0, "maxOutputTokens": 200},
        timeout=5.0,
        retries=1,
    )
    if not parsed:
        return {}
    return {
        k: parsed.get(k)
        for k in missing_keys
        if parsed.get(k) not in (None, "")
    }


def phrase_slot_question(known: dict, next_field: str, last_user_msg: str) -> str | None:
    """ให้ Gemini ถามข้อมูลที่ขาดต่อไปแบบธรรมชาติ อ้างอิงสิ่งที่ลูกค้าเพิ่งพูด
    แทนการดึง template คงที่ซ้ำทุกครั้ง — ลดความรู้สึก 'เป็นบอท'
    คืน None ถ้า Gemini ล่ม (caller ใช้ template เดิมเป็น fallback)"""
    if not ENABLE_NATURAL_REPLIES or not API_KEY:
        return None
    field_labels = {
        "name": "ชื่อผู้แจ้ง", "phone": "เบอร์โทรติดต่อกลับ",
        "device_id": "อุปกรณ์หรือห้องที่ใช้งาน", "symptom": "อาการที่พบ",
    }
    prompt = (
        f'ลูกค้าเพิ่งพิมพ์ว่า: "{mask_pii(last_user_msg)}"\n'
        f"ข้อมูลที่เก็บได้แล้ว: {json.dumps({k: mask_pii(str(v)) for k, v in (known or {}).items()}, ensure_ascii=False)}\n"
        f"ข้อมูลที่ยังขาดและต้องถามต่อไป: {field_labels.get(next_field, next_field)}\n\n"
        "จงถามข้อมูลที่ขาดนี้ต่อ 1 ประโยคสั้นๆ ภาษาไทยสุภาพ เป็นธรรมชาติ ไม่ต้องใช้รูปแบบเดิมซ้ำทุกครั้ง "
        "ถ้าเหมาะสมให้ตอบรับสิ่งที่ลูกค้าเพิ่งพูดสั้นๆ ก่อนถามต่อ ห้ามใช้คำว่า 'ฉัน' ใช้ 'ค่ะ' ลงท้าย"
    )
    return request_text(
        [_BASE_POLICY, with_extension("slot_question", prompt)],
        generation_config={"temperature": 0.2, "maxOutputTokens": 100},
        timeout=5.0,
        retries=1,
    )


# context ที่ใช้ในการ orchestration: เรียกแล้วถ้าล่มคืน None → caller fallback ไป rule FSM เดิม
_ORCH_CONTEXT = {
    "services": None,  # set at first call
    "categories": None,
}


def _orchestrate_context() -> str:
    """สร้าง context ย่อๆ (บริการ/หมวดสินค้า) สำหรับให้ Gemini ตอบ/ตัดสินใจ โดยไม่อ้างราคา"""
    if _ORCH_CONTEXT["services"] is None:
        from app.company_catalog import SERVICES, PRODUCT_CATEGORIES
        _ORCH_CONTEXT["services"] = "; ".join(f"{s['name']}({s['desc']})" for s in SERVICES)
        _ORCH_CONTEXT["categories"] = "; ".join(f"{c['name']}" for c in PRODUCT_CATEGORIES)
    return (f"บริการที่มี: {_ORCH_CONTEXT['services']}\n"
            f"หมวดสินค้า: {_ORCH_CONTEXT['categories']}")


def gemini_orchestrate(text: str, user_context: dict) -> dict | None:
    """ให้ Gemini ตัดสินใจ turn ถัดไป + ร่างคำตอบธรรมชาติ (ปลอดภัยแบบ opt-in)
    คืน {"reply": str, "action": "answer|ask_info|search_kb|create_ticket|escalate",
          "product": str, "service": str, "confidence": float}
    คืน None ถ้า Gemini ล่ม/429 → caller fallback ไป rule FSM เดิม
    user_context: {phase, fields, has_product, has_service, name, history}
    history: [{u, b}, ...] ประวัติสนทนาก่อนหน้านี้ (ย้อนไป ~6 รอบ) — ให้ตอบต่อเนื่อง
    เมื่อลูกค้าเปลี่ยนหัวข้อกระทันหัน หรือถามย้อนกลับสิ่งที่เพิ่งคุย"""
    if not API_KEY:
        return None
    ctx = _orchestrate_context()
    hist = user_context.get("history") or []
    history_text = ""
    if hist:
        lines = []
        for turn in hist[-6:]:
            u = mask_pii(str(turn.get("u", "")))[:200]
            b = mask_pii(str(turn.get("b", "")))[:200]
            if u:
                lines.append(f"ลูกค้า: {u}")
            if b:
                lines.append(f"บอท: {b}")
        if lines:
            history_text = "ประวัติการสนทนาที่ผ่านมา:\n" + "\n".join(lines) + "\n\n"
    prompt = (
        f"ข้อความล่าสุดของลูกค้า: {mask_pii(text)}\n"
        f"{history_text}"
        f"บริบทสนทนา: {mask_pii(str(user_context))[:1000]}\n"
        f"ข้อมูลธุรกิจ:\n{ctx}\n\n"
        "จงตัดสินใจว่าบอทควรทำอะไรใน turn นี้ และร่างคำตอบถึงลูกค้า:\n"
        "- answer: ตอบตรงๆ (ข้อมูลสินค้า/บริการ/บริษัท/ทักทาย/ขอบคุณ)\n"
        "- ask_info: ยังข้อมูลไม่พอ ต้องถามลูกค้าเพิ่ม (เช่น ชื่อ/เบอร์/อุปกรณ์/อาการ)\n"
        "- search_kb: ดูเป็นปัญหาอุปกรณ์ที่ควรแนะนำวิธีแก้\n"
        "- create_ticket: ข้อมูลครบแล้ว ควรสร้าง ticket แจ้งซ่อม\n"
        "- escalate: อาการอันตราย/กำกวม ควรส่งช่าง\n"
        "ใช้ประวัติการสนทนาช่วย — ถ้าลูกค้าเปลี่ยนหัวข้อกระทันหัน หรืออ้างถึงสิ่งที่คุยไปแล้ว "
        "ให้ตอบต่อเนื่องสอดคล้องกับที่คุยมา ไม่ใช่เริ่มต้นใหม่\n"
        "คำตอบภาษาไทยสุภาพ อบอุ่น เหมือนพนักงานไทย 1-3 ประโยค ใช้ 'ค่ะ' ไม่ใช้ 'ฉัน'\n"
        'ตอบ JSON เท่านั้น: {"reply":"...", "action":"answer|ask_info|search_kb|create_ticket|escalate", '
        '"product":"ชื่อสินค้าถ้าเจอ หรือว่าง", "service":"ชื่อบริการถ้าเจอ หรือว่าง", "confidence":0.0-1.0}'
    )
    parsed = request_json(
        [_BASE_POLICY, with_extension("orchestration", prompt)],
        generation_config={"temperature": 0.2, "maxOutputTokens": 250},
        timeout=7.0,
        retries=1,
    )
    if not parsed:
        return None
    valid_actions = {"answer", "ask_info", "search_kb", "create_ticket", "escalate"}
    action = parsed.get("action", "answer")
    if action not in valid_actions:
        action = "answer"
    try:
        confidence = max(0.0, min(1.0, float(parsed.get("confidence", 0))))
    except (TypeError, ValueError):
        confidence = 0.0
    return {
        "reply": str(parsed.get("reply", "") or ""),
        "action": action,
        "product": str(parsed.get("product", "") or ""),
        "service": str(parsed.get("service", "") or ""),
        "confidence": confidence,
    }


def phrase_repair_reply(context: str, detail: str) -> str | None:
    """ให้ Gemini แต่งคำตอบสั้นๆ ธรรมชาติในจุดต่างๆ ของ flow แจ้งซ่อม
    (เริ่มวินิจฉัย / แก้ไม่ได้→ส่งช่าง / สร้าง ticket สำเร็จ) แทน template คงที่ซ้ำ
    context: สถานการณ์ (เช่น 'begin_diagnose' / 'not_resolved' / 'ticket_created')
    detail: ข้อมูลประกอบ (อาการที่พูด / ข้อมูลที่เก็บ / เลข ticket)
    คืน None ถ้า Gemini ล่ม → caller ใช้ template เดิมเป็น fallback"""
    if not ENABLE_NATURAL_REPLIES or not API_KEY:
        return None
    scenario = {
        "begin_diagnose": "เพิ่งเริ่มวินิจฉัยปัญหา ยังไม่รู้สาเหตุชัดเจน ต้องการขอรายละเอียดเพิ่มจากลูกค้า",
        "not_resolved": "ลองแก้เบื้องต้นแล้วยังไม่หาย ต้องส่งต่อให้ช่าง ควรพูดเห็นใจและแจ้งขั้นตอนถัดไป",
        "ticket_created": "เพิ่งสร้าง ticket แจ้งซ่อมสำเร็จ ควรแจ้งเลข ticket และบอกลูกค้าถึงขั้นตอนถัดไป",
        "resolve_success": "ลูกค้าแจ้งว่าแก้ได้แล้ว ควรชื่นชมสั้นๆ",
    }.get(context, context)
    prompt = (
        f"สถานการณ์: {scenario}\n"
        f"ข้อมูลประกอบ: {mask_pii(detail)}\n\n"
        "จงเขียนคำตอบถึงลูกค้า 1-2 ประโยค ภาษาไทยสุภาพ อบอุ่น เป็นธรรมชาติ เหมือนพนักงานไทย "
        "ไม่ใช้รูปแบบเดิมซ้ำทุกครั้ง ห้ามใช้คำว่า 'ฉัน' ใช้ 'ค่ะ' ลงท้าย ถ้าเป็น ticket_created ให้ระบุเลข ticket"
    )
    return request_text(
        [_BASE_POLICY, with_extension("repair_reply", prompt)],
        generation_config={"temperature": 0.2, "maxOutputTokens": 120},
        timeout=6.0,
        retries=1,
    )


def match_article(symptom_text: str, device_type: Optional[str], candidates: list) -> Optional[dict]:
    """ให้ Gemini เลือกบทความ KB ที่ตรงกับอาการจาก candidates ที่ keyword คัดมาแล้ว
    ตอบจาก candidates ที่ให้เท่านั้น — เลือก kb_id ที่ตรงที่สุด ไม่ให้สร้างขั้นตอนใหม่เอง (กัน hallucination)

    candidates: list ของ dict {kb_id, title, steps:[...]}
    คืน {"kb_id": str, "steps": [str,...]} (steps = ของบทความที่เลือก) หรือ None ถ้าไม่มี key/API ล่ม/ไม่มีบทความตรง
    """
    # Gemini เป็นตัวช่วย semantic matching; ถ้าไม่มี key ยังต้องใช้ safe lexical fallback
    if not candidates:
        return None
    list_text = "\n".join(
        f"- [{a['kb_id']}] {a.get('device_type','')} | {a['title']}\n"
        f"    อาการที่ตรง: {' / '.join(a.get('tags', []) or a.get('steps', []))}"
        for a in candidates
    )
    instruction = (
        f"ผู้ใช้แจ้งอาการ: {mask_pii(symptom_text)}\n"
        f"ประเภทอุปกรณ์: {device_type or 'ไม่ระบุ'}\n\n"
        "รายการบทความในฐานความรู้ (เลือกจากรายการนี้เท่านั้น ห้ามสร้างบทความ/วิธีแก้เอง):\n"
        f"{list_text}\n\n"
        "จงเลือกบทความที่ตรงกับอาการผู้ใช้มากที่สุด โดย: ถ้าอาการกำกวม/กว้าง (เช่น 'จอเสีย' 'พัง' ไม่บอกอาการเฉพาะ) แต่รู้ประเภทอุปกรณ์ ให้เลือกบทความที่ใกล้เคียงที่สุดในประเภทเดียวกัน (เช่น จอ → 'จอไม่มีภาพ') เพื่อแนะนำเบื้องต้นก่อน; ตอบว่างเฉพาะเมื่อไม่มีบทความในประเภทที่เกี่ยวข้องเลย\n"
        'ตอบเป็น JSON เท่านั้น รูปแบบ {"kb_id": "รหัสบทความที่เลือก หรือ ว่างถ้าไม่มีในประเภทที่เกี่ยวข้อง"}'
    )
    parsed = request_json(
        [_SYSTEM_PROMPT, with_extension("kb_match", instruction)],
        generation_config={"temperature": 0.0, "maxOutputTokens": 300},
        timeout=5.0,
        retries=1,
    )
    if parsed:
        chosen_id = str(parsed.get("kb_id", "") or "").strip()
        # หาบทความที่เลือกใน candidates (ต้องอยู่ใน list เท่านั้น)
        for a in candidates:
            if a.get("kb_id") == chosen_id:
                return {"kb_id": chosen_id, "steps": a.get("steps", []),
                        "device_type": a.get("device_type", "")}

    # Safe fallback เมื่อ Gemini timeout/ตอบ JSON ไม่ถูกต้อง:
    # เลือกได้เฉพาะบทความที่มีอยู่ใน candidates และคืน steps เดิมจาก KB เท่านั้น
    # ห้ามสร้างขั้นตอนใหม่หรือเดาคำตอบนอกฐานความรู้
    def _norm(s: str) -> str:
        return " ".join(str(s or "").lower().split())

    q = _norm(symptom_text)
    dev = _norm(device_type)
    # อนุมานประเภทจากภาษาที่ผู้ใช้ใช้ เมื่อไม่ได้ส่ง device_type มา
    inferred = ""
    for words, dtype in [
        (["จอ", "interactive", "aiboard", "สมาร์ทบอร์ด"], "interactive display"),
        (["คอม", "คอมพิวเตอร์", "โน้ตบุ๊ก", "laptop"], "computer"),
        (["wifi", "wi-fi", "อินเทอร์เน็ต", "เน็ต", "router"], "router"),
        (["โปรเจกเตอร์", "projector"], "projector"),
        (["ลำโพง", "speaker"], "speaker"),
        (["ไมค์", "ไมโครโฟน", "microphone"], "microphone"),
        (["กล้อง", "camera"], "camera"),
        (["ปริ้น", "เครื่องพิมพ์", "printer"], "printer"),
    ]:
        if any(w in q for w in words):
            inferred = dtype
            break
    dev = dev or inferred
    best = None
    best_score = 0
    best_type = None
    # วลีที่มีความหมายเฉพาะควรมีน้ำหนักมากกว่าคำทั่วไป เช่น "ไม่มีภาพ"
    phrases = [
        "ไม่มีภาพ", "จอดำ", "ไม่มีเสียง", "ระบบสัมผัส", "ไม่ทำงาน", "ไม่ติด",
        "ต่ออินเทอร์เน็ตไม่ได้", "เน็ตไม่ได้", "ช้า", "ค้าง", "ชาร์จไม่เข้า",
        "ไม่ขึ้นภาพ", "ภาพเพี้ยน", "มีเส้น", "ร้อนจัด", "พัดลมดัง", "ไฟกระพริบ",
    ]
    for a in candidates:
        title = _norm(a.get("title"))
        atype = _norm(a.get("device_type"))
        score = 0
        for phrase in phrases:
            if phrase in q and phrase in title:
                score += 5
        if atype and dev and (atype in dev or dev in atype):
            score += 2
        # คำสำคัญจากชื่อบทความ: ต้องตรงอย่างน้อย 2 ตัวอักษร เพื่อไม่ match กว้างเกินไป
        title_terms = [x for x in re.split(r"[^a-z0-9ก-๙]+", title) if len(x) >= 3]
        score += sum(1 for term in title_terms if term in q)
        # ถ้ารู้ประเภทอุปกรณ์ ให้กันบทความคนละประเภทออกก่อน
        type_ok = True
        if dev:
            type_ok = (dev in atype or atype in dev or
                       (dev == "computer" and "computer" in atype))
        if type_ok and score > best_score and a.get("steps"):
            best, best_score, best_type = a, score, atype
    # อาการกว้างมากแต่รู้ประเภท: เลือกบทความหลักของประเภทนั้นแบบ deterministic
    if best is None and dev:
        same_type = [a for a in candidates if dev in _norm(a.get("device_type")) or
                     _norm(a.get("device_type")) in dev or
                     (dev == "computer" and "computer" in _norm(a.get("device_type")))]
        same_type = [a for a in same_type if a.get("steps")]
        if same_type:
            same_type.sort(key=lambda a: str(a.get("kb_id", "")))
            best, best_score = same_type[0], 2
    return ({"kb_id": best.get("kb_id"), "steps": best.get("steps", []),
             "device_type": best.get("device_type")} if best is not None and best_score >= 2 else None)
