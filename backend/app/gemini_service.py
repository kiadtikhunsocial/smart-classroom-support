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
import time
from typing import Optional
import httpx

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-flash-latest")
_ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"

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
    if not kb_steps:
        return None
    if not API_KEY:
        return None
    step_list = "\n".join(f"{i+1}. {s}" for i, s in enumerate(kb_steps))
    prompt = (
        f"ลูกค้าแจ้งปัญหา: {symptom_text}\n"
        f"ประเภทอุปกรณ์: {device_type or 'ไม่ระบุ'}\n\n"
        "ขั้นตอนแก้ไขเบื้องต้นที่ระบบระบุไว้ (ใช้ขั้นตอนเหล่านี้เท่านั้น ห้ามเพิ่ม/แก้ไข/สร้างขั้นตอนใหม่):\n"
        f"{step_list}\n\n"
        "จงเขียนคำตอบถึงลูกค้าเป็นภาษาไทย อบอุ่น เหมือนพนักงานบริการคนไทย ปรับภาษาตามที่ลูกค้าพิมพ์ "
        "(ถ้าลูกค้าพิมพ์ภาษาพูด/กำกวม/สั้น ก็ตอบแบบสบายๆ เข้าใจง่าย ไม่ยัดเยียดศัพท์เทคนิค) "
        "เกริ่นอย่างเห็นใจก่อน แล้วอธิบายขั้นตอนให้เข้าใจง่ายทีละข้อ (เรียงตามลำดับ) "
        "ปิดท้ายด้วยคำแนะนำว่า ถ้าทำแล้วไม่หาย ให้บอก 'ยังไม่หาย' เพื่อให้ช่างช่วยต่อ\n"
        "ห้ามประดิษฐ์ขั้นตอนที่ไม่ใช่ในรายการ ห้ามแนะนำการถอด/เปิดฝาอุปกรณ์ ห้ามใช้คำว่า 'ฉัน' ใช้ 'คะ/ค่ะ'"
    )
    body = {
        "contents": [{"parts": [{"text": _BASE_POLICY}, {"text": prompt}]}],
        "generationConfig": {"temperature": 0.6, "maxOutputTokens": 500},
    }
    try:
        resp = None
        for attempt in range(2):
            try:
                resp = httpx.post(_ENDPOINT, headers={"X-goog-api-key": API_KEY}, json=body, timeout=12.0)
            except Exception:
                resp = None
            if resp is not None and resp.status_code == 200:
                break
            if attempt < 1:
                time.sleep(0.8)
        if resp is None or resp.status_code != 200:
            return None
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        return text if text else None
    except Exception:
        return None


def is_available() -> bool:
    return bool(API_KEY)


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
        f"ผู้ใช้แจ้งอาการ: {symptom_text}\n"
        f"ประเภทอุปกรณ์: {device_type or 'ไม่ระบุ'}\n\n"
        "รายการบทความในฐานความรู้ (เลือกจากรายการนี้เท่านั้น ห้ามสร้างบทความ/วิธีแก้เอง):\n"
        f"{list_text}\n\n"
        "จงเลือกบทความที่ตรงกับอาการผู้ใช้มากที่สุด โดย: ถ้าอาการกำกวม/กว้าง (เช่น 'จอเสีย' 'พัง' ไม่บอกอาการเฉพาะ) แต่รู้ประเภทอุปกรณ์ ให้เลือกบทความที่ใกล้เคียงที่สุดในประเภทเดียวกัน (เช่น จอ → 'จอไม่มีภาพ') เพื่อแนะนำเบื้องต้นก่อน; ตอบว่างเฉพาะเมื่อไม่มีบทความในประเภทที่เกี่ยวข้องเลย\n"
        'ตอบเป็น JSON เท่านั้น รูปแบบ {"kb_id": "รหัสบทความที่เลือก หรือ ว่างถ้าไม่มีในประเภทที่เกี่ยวข้อง"}'
    )
    body = {
        "contents": [{"parts": [{"text": _SYSTEM_PROMPT}, {"text": instruction}]}],
        "generationConfig": {"temperature": 0.1, "maxOutputTokens": 300},
    }
    try:
        if not API_KEY:
            raise RuntimeError("Gemini key unavailable")
        resp = None
        for attempt in range(2):  # retry สั้น ทน 503/429 ชั่วคราว (ไม่ให้ response ช้าเกิน)
            try:
                resp = httpx.post(
                    _ENDPOINT, headers={"X-goog-api-key": API_KEY}, json=body, timeout=5.0
                )
            except Exception:
                resp = None
            if resp is not None and resp.status_code == 200:
                break
            if attempt < 1:
                time.sleep(0.8)
        if resp is None or resp.status_code != 200:
            raise RuntimeError("Gemini unavailable")
        data = resp.json()
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        if text.startswith("```"):
            text = text.strip("`").lstrip("json").strip()
        parsed = json.loads(text)
        chosen_id = str(parsed.get("kb_id", "") or "").strip()
        # หาบทความที่เลือกใน candidates (ต้องอยู่ใน list เท่านั้น)
        for a in candidates:
            if a.get("kb_id") == chosen_id:
                return {"kb_id": chosen_id, "steps": a.get("steps", []),
                        "device_type": a.get("device_type", "")}
        return None  # เลือกบทความที่ไม่อยู่ใน list / ไม่มี → ไม่ match
    except Exception:
        pass

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
