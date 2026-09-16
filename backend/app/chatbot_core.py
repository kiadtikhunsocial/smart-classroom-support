"""
chatbot_core.py — logic หลักตัดสินใจบทสนทนา chatbot

state ที่เก็บใน session (dict):
  {
    "phase": "new" | "collecting" | "confirm" | "done",
    "fields": {"name","phone","device_id","room","symptom"},   # ข้อมูลที่เก็บได้
    "collected": [...],   # field ที่เก็บครบแล้ว
    "ticket_no": "...",   # หลังสร้าง ticket
  }

การทำงาน:
  - phase=new + ข้อความดูเหมือนอาการปัญหา → เรียก AI diagnose (KB)
      - เจอวิธีแก้ → แนะนำขั้นตอน + ถาม "แก้ได้ไหม?" (ได้=บันทึก self-service)
      - ไม่เจอ → เริ่ม collecting ถามชื่อ
  - phase=collecting → ถามทีละ field ด้วย Gemini (ถามค่าที่ขาด)
  - phase=confirm → สรุป + ถามยืนยัน → สร้าง ticket + แจ้งเตือน
"""
import json
import os
import re
import threading
import time

from app.line_bot import _gemini_text, send_line_push
from app.chat_session import get_session, save_session, clear_session
from app.gemini_service import match_article
from app.models import SessionLocal
from sqlalchemy import text

# ── ภาพสินค้าที่จะส่งพร้อมคำตอบ (thread-local ปลอดภัยต่อ concurrent LINE) ──
_tls = threading.local()


def _clear_pending_image():
    _tls.pending_product_image = None
    _tls.pending_product = None


def _set_pending_image(url: str):
    if url:
        _tls.pending_product_image = url


def _set_pending_product(prod: dict | None):
    if prod:
        _tls.pending_product = prod


def _take_pending_product() -> dict | None:
    """คืนสินค้าที่เจอในคำตอบนี้ แล้วล้าง (ให้ handle_message จำ context ข้ามรอบ)"""
    prod = getattr(_tls, "pending_product", None)
    _tls.pending_product = None
    return prod


def get_pending_product_image() -> str | None:
    """คืน URL ภาพสินค้าที่เจอล่าสุดในคำตอบนี้ แล้วล้าง (ให้ main.py ส่งเป็น image message)"""
    url = getattr(_tls, "pending_product_image", None)
    _tls.pending_product_image = None
    return url


REQUIRED_FIELDS = [
    ("device_id", "ไม่ทราบว่าอุปกรณ์หรือห้องที่ใช้อยู่เป็นอะไรคะ? เช่น จอ Interactive Display ห้อง 201 หรือคอมพิวเตอร์ห้องสมุด ช่วยบอกหน่อยนะคะ"),
    ("name", "ขอทราบชื่อของคุณไว้ติดต่อกลับได้ไหมคะ?"),
    ("phone", "ขอเบอร์โทรไว้ติดต่อกลับด้วยนะคะ"),
    ("symptom", "อยากให้เล่าอาการคร่าว ๆ ให้ช่างเข้าใจไวขึ้นนะคะ เช่น ไม่มีภาพ ไม่มีเสียง หรือหน้าจอดำ"),
]

# คำ/น้ำเสียงที่บอกว่าแก้ได้แล้ว / ยังไม่หาย
RESOLVED_WORDS = ["หาย", "ได้แล้ว", "ok", "ใช้ได้", "เรียบร้อย", "สำเร็จ", "แก้ได้", "หายแล้ว"]
NOT_RESOLVED_WORDS = ["ไม่หาย", "ยังไม่", "ไม่ได้", "ไม่ใช่", "ไม่ได้ผล", "ไม่ได้เรื่อง", "ไม่ได้เลย", "ยัง"]
HELP_WORDS = ["ช่วย", "แจ้งซ่อม", "ซ่อม", "ช่าง", "แจ้งหน่อย", "ไม่รู้", "ทำไง", "ทำยังไง", "พัง", "เสีย", "มีปัญหา", "ไม่ทำงาน", "ไม่ติด"]
_ADMIN_CONTACT_TERMS = [
    "ติดต่อ", "ติดต่อเรา", "ติดต่อแอดมิน", "หาแอดมิน", "แอดมิน", "admin",
    "เจ้าหน้าที่", "พนักงาน", "คุยกับคน", "คุยกับพนักงาน", "คุยกับเจ้าหน้าที่",
    "คนจริง", "ติดต่อทีมงาน", "ทีมงาน", "ขอเบอร์", "เบอร์ติดต่อ", "line id",
    "ขอไลน์", "ไลน์ออฟฟิเชียล", "ช่องทางติดต่อ", "contact", "human", "talk to human",
]
_OUT_OF_SCOPE_TERMS = [
    "อากาศ", "พยากรณ์", "ฝนตก", "หวย", "การเมือง", "ข่าว", "สูตรอาหาร", "ทำอาหาร",
    "เพลง", "หนัง", "ภาพยนตร์", "เกม", "ท่องเที่ยว", "แปลภาษา", "คำนวณ", "การบ้าน",
    "ความรัก", "ดูดวง", "หุ้น", "คริปโต",
]

# ลิงก์ฟอร์มแจ้งซ่อมสาธารณะ (หน้า ?publicreport=1) — ตั้ง env REPORT_FORM_URL เป็น URL จริงใน production
REPORT_FORM_URL = os.environ.get("REPORT_FORM_URL", "http://localhost:5173/?publicreport=1")
ENABLE_GEMINI_CLASSIFIER = os.environ.get("ENABLE_GEMINI_CLASSIFIER", "0").lower() in {"1", "true", "yes", "on"}
ENABLE_GEMINI_ORCHESTRATION = os.environ.get("ENABLE_GEMINI_ORCHESTRATION", "0").lower() in {"1", "true", "yes", "on"}


def _normalized_reply(text: str) -> str:
    return " ".join((text or "").strip().lower().split())


def _is_affirmative(text: str) -> bool:
    value = _normalized_reply(text)
    return value in {"ยืนยัน", "ยืนยันค่ะ", "ยืนยันครับ", "ถูก", "ถูกต้อง", "ใช่", "ตกลง", "โอเค", "ok", "ได้เลย"}


def _is_negative(text: str) -> bool:
    value = _normalized_reply(text)
    return (value in {"ไม่", "ไม่ใช่", "ไม่ถูก", "ไม่ถูกต้อง", "ผิด", "แก้", "แก้ไข", "ยกเลิก"}
            or value.startswith(("ไม่ใช่", "ไม่ถูก", "ไม่เอา", "ไม่ยืนยัน")))


def _has_reply_phrase(text: str, phrases: list[str]) -> bool:
    value = _normalized_reply(text)
    for phrase in phrases:
        candidate = _normalized_reply(phrase)
        if candidate in {"ok", "ยัง"}:
            if value == candidate:
                return True
        elif candidate in value:
            return True
    return False


def _is_admin_contact_request(text: str) -> bool:
    value = _normalized_reply(text)
    return any(_normalized_reply(term) in value for term in _ADMIN_CONTACT_TERMS)


def _is_out_of_scope(text: str) -> bool:
    value = _normalized_reply(text)
    return any(_normalized_reply(term) in value for term in _OUT_OF_SCOPE_TERMS)


# คำที่บอกว่า "ผู้ใช้ต้องการแจ้งซ่อมตรง ๆ" (ไม่ใช่การเล่าอาการให้วินิจฉัย)
_EXPLICIT_REPAIR_KEYS = [
    "แจ้งซ่อม", "แจ้งปัญหา", "แจ้งเรื่องซ่อม", "สร้างงานซ่อม",
    "เรียกช่าง", "ให้ช่างมาตรวจ", "ให้ช่างมาดู",
]
_STRONG_SYMPTOM_WORDS = [
    "ไม่ติด", "ไม่มีภาพ", "ไม่มีเสียง", "จอดำ", "ค้าง", "พัง", "เสีย", "ไม่ทำงาน",
    "ไม่ขึ้น", "เข้าไม่ได้", "หลุด", "ร้อน", "ดัง", "ช้า", "เปิดไม่",
]
# คำถามธุรกิจที่ชัดเจน (ห้ามใช้ตอนผู้ใช้กำลังตอบเรื่องอุปกรณ์)
_CLEAR_BUSINESS_WORDS = [
    "สินค้า", "ราคา", "ใบเสนอราคา", "โปรโมชั่น", "แคตตาล็อก", "จัดจำหน่าย",
    "บริการ", "อบรม", "หลักสูตร", "สเปก", "ทดลองใช้", "มีอะไรขาย",
    "ซื้อ", "สั่งซื้อ", "อยากได้ใหม่", "รุ่นใหม่", "ของใหม่",
]


def _is_explicit_repair(text: str) -> bool:
    """true = ผู้ใช้สั่งแจ้งซ่อมตรง ๆ → เข้าเก็บข้อมูลทันที ไม่ต้องวินิจฉัยซ้ำ"""
    t = _normalized_reply(text)
    core = re.sub(r"\s+", "", t)
    core = re.sub(r"(ครับ|ค่ะ|คะ|นะคะ|นะครับ|จ้า|หน่อย|ด้วย)+$", "", core)
    if core in {"ซ่อม", "แจ้งซ่อม", "แจ้งซ่อมใหม่", "แจ้งปัญหา", "แจ้งเรื่องซ่อม",
                "สร้างงานซ่อม", "เรียกช่าง", "ให้ช่าง"}:
        return True
    # คำว่า "ซ่อม" ต่อท้ายข้อความสั้น ๆ (รองรับพิมพ์ผิดเล็กน้อย เช่น "เเจ้วซ่อม")
    if core.endswith("ซ่อม") and len(core) <= 8:
        return True
    if any(k in t for k in _EXPLICIT_REPAIR_KEYS):
        # ถ้ามีคำอาการปนมาด้วย ให้ลองวินิจฉัยจาก KB ก่อน (ผู้ใช้จะได้ลองแก้เอง)
        return not any(w in t for w in _STRONG_SYMPTOM_WORDS)
    return False


def _is_clear_business(text: str) -> bool:
    """true = ถามสินค้า/บริการชัดเจน (ใช้ตอนขัดจังหวะผู้ที่กำลังตอบเรื่องอุปกรณ์)"""
    t = _normalized_reply(text)
    return any(w in t for w in _CLEAR_BUSINESS_WORDS)


def _form_fallback_text() -> str:
    """ข้อความส่งต่อเมื่อแก้เบื้องต้นไม่ได้ — ให้แจ้งผ่านบอทตรงนี้ หรือสแกน QR บนตัวอุปกรณ์
    (ไม่มีลิงก์ฟอร์มสาธารณะอีกต่อไป — ลูกค้าไม่ต้องออกจาก LINE ไปกรอกที่อื่น)"""
    return (
        "เสียใจด้วยนะคะที่ยังหาวิธีแก้เบื้องต้นไม่เจอ 😔\n\n"
        "แจ้งซ่อมได้ง่าย ๆ โดยไม่ต้องไปไหนไกลค่ะ:\n"
        "📱 **สแกน QR Code ที่ติดอยู่บนตัวอุปกรณ์** แล้วกรอกข้อมูลตามฟอร์ม จะส่งงานให้ทีมช่างทันที\n"
        "หรือจะแจ้งผ่านบอทตรงนี้เลยก็ได้ — พิมพ์ **'แจ้งซ่อม'** แล้วกรอกชื่อ/เบอร์/อาการ ให้เราสร้างงานให้ค่ะ\n\n"
        "สแกน QR ที่ตัวเครื่อง → กรอกครบ → ทีมช่างรับเรื่องและไปดูแลถึงที่ให้ค่ะ"
    )



def _is_symptom(msg: str) -> bool:
    """เดาว่าข้อความเป็นอาการ/ปัญหาที่ต้องแจ้งซ่อม หรือเป็นคำถามปกติ

    เข้มงวด: ต้องมีคำ/สำนวนบ่งชี้ปัญหาเท่านั้นถึงเข้าข่าย — ไม่งั้นคำถามปกติ
    (สินค้า/บริษัท/สนทนาทั่วไป) จะถูกดึงไป flow แจ้งซ่อมโดยไม่จำเป็น."""
    m = msg.lower().strip()
    if any(w in m for w in HELP_WORDS):
        return True
    # สำนวนอาการชัดเจน (มีคำอาการปน)
    if re.search(r"(จอ|เครื่อง|ไฟ|เสียง|ภาพ|แป้น|เมาส์|เน็ต|wifi|โปรเจก|ลำโพง|ไมค์|กล้อง|แท็บเล็ต|interactive display)\s*(ไม่|ไม่มี|เสีย|พัง|ค้าง|ดำ|เพี้ยน|ดัง|เข้า)", m):
        return True
    return False


def _extract_field_from_text(field: str, text: str) -> str | None:
    """พยายามดึงค่า field จากข้อความที่ผู้ใช้พิมพ์ (แบบง่าย)"""
    t = text.strip()
    if field == "phone":
        m = re.search(r"0[0-9]{8,9}", t)
        return m.group(0) if m else None
    if field == "name":
        m = t.lower()
        # ถ้ามีคำแจ้งซ่อมชัดเจนชัด ๆ → ไม่ใช่ชื่อ
        if any(w in m for w in ["แจ้งซ่อม", "ซ่อม", "ช่าง", "พัง", "เสีย", "มีปัญหา", "ช่วย"]):
            return None
        # ตัดคำสุภาพ/คำลงท้ายที่อาจปนท้ายชื่อ (ครับ/ค่ะ/นะคะ...) 
        clean = re.sub(r"(ครับ|ค่ะ|คะ|นะคะ|นะครับ|ฮะ|จ้า|ขอรับ)$", "", t.strip()).strip(" ,")
        # ตัดคำอาการออกถ้าอยู่ในประโยค (กันเก็บประโยคอาการเป็นชื่อ) — เช็คกับ clean (ตัดคำสุภาพแล้ว)
        # อย่าเช็คกับ m ข้อความดิบ และอย่าให้ "ครับ/ค่ะ" อยู่ใน hint ไม่งั้นชื่อที่ลงท้ายสุภาพถูกปฏิเสธ
        _SYMPTOM_HINT = ["วันนี้", "เมื่อวาน", "เริ่ม", "ไฟติด", "จอดำ", "ไม่มีภาพ", "ไม่มีเสียง",
                         "หน้าจอ", "ห้อง", "เครื่อง", "ค้าง", "ไม่ขึ้น", "ไม่เข้า", "ช้า", "ร้อน",
                         "เครื่องพิมพ์", "โปรเจก", "กล้อง", "ลำโพง", "ไมค์",
                         "กดไม่ได้", "เปิดไม่"]
        if any(w in clean.lower() for w in _SYMPTOM_HINT):
            return None
        # ถ้ามีตัวเลขเบอร์โทร / รหัสอุปกรณ์ปนมา ให้เก็บเฉพาะส่วนที่เป็นชื่อ
        if re.search(r"\b0[0-9]{8,9}\b", clean):
            parts = [p for p in re.split(r"[,\s]+", clean) if not re.fullmatch(r"0[0-9]{8,9}", p)]
            clean = " ".join(parts).strip()
        # ชื่อสั้น ๆ (≤30) เท่านั้น — ป้องกันเก็บประโยคยาวเป็นชื่อ
        return clean if 2 <= len(clean) <= 30 else None
    if field == "device_id":
        m = re.search(r"((?:DEV|TEST|SCH|ROOM|SCHE)[\w-]+\d+|\b\d{2,4}\b|ห้อง\s*\d+|อาคาร\s*\d+)", t, re.IGNORECASE)
        if m:
            return m.group(1)
        # รองรับชื่ออุปกรณ์ที่ผู้ใช้พิมพ์เป็นภาษาคน แม้ไม่มีรหัส/เลขห้อง
        device_markers = [
            ("interactive display", "Interactive Display"),
            ("interactive", "Interactive Display"),
            ("aiboard", "Iwa AiBoard"),
            ("ai board", "Iwa AiBoard"),
            ("สมาร์ทบอร์ด", "Interactive Display"),
            ("คอมพิวเตอร์", "Computer"),
            ("โน้ตบุ๊ก", "Notebook"),
            ("laptop", "Notebook"),
            ("โปรเจกเตอร์", "Projector"),
            ("projector", "Projector"),
            ("wifi", "Wi-Fi"),
            ("wi-fi", "Wi-Fi"),
            ("เราเตอร์", "Router"),
            ("router", "Router"),
            ("ลำโพง", "Speaker"),
            ("ไมโครโฟน", "Microphone"),
            ("ไมค์", "Microphone"),
            ("กล้อง", "Camera"),
            ("เครื่องพิมพ์", "Printer"),
            ("ปริ้นเตอร์", "Printer"),
        ]
        low = t.lower()
        for marker, canonical in device_markers:
            if marker in low:
                return canonical
        return None
    if field == "symptom":
        return t
    return None


def _collect_fields(session: dict) -> dict:
    """คืน session ที่มี fields ครบถ้วนตามที่เก็บได้"""
    f = session.get("fields", {})
    return f


def _dispatch(user_id: str, text: str, reply_token: str, group: bool = False) -> str:
    """[inner] รับข้อความจาก LINE → คืนข้อความที่จะตอบกลับ (logic เดิม: แจ้งซ่อม/สินค้า)

    ถูกเรียกผ่าน handle_message() (wrapper) ซึ่งจัดการเจตนาใหม่ + log + lead/profile
    เรียกจาก /api/line/bot (n8n ส่งมาอีกที). จัดการ session + ตัดสินใจ flow.
    หมายเหตุ: การ reply LINE ทำที่ caller — ฟังก์ชันนี้คืน text + จัดการ side-effect
    """
    session = get_session(user_id)
    phase = session.get("phase", "new")

    # ── ขัดจังหวะ: ผู้ใช้ถามสินค้า/บริการชัดเจน → ตอบเรื่องนั้น ไม่ว่าจะอยู่สถานะไหน ──
    # ใช้ _is_clear_business (คำชัดเจน) ไม่ใช่ classify()==business เพราะข้อความตอบคำถาม
    # เรื่องอุปกรณ์ เช่น "จอ Interactive Display ห้อง 2208" มีคำว่า จอ/interactive
    # ซึ่ง classify() ตีเป็น business ได้ → เดิมบอทหลุดไปขึ้นรายการสินค้าทั้งที่กำลังเก็บข้อมูลซ่อม
    from app.company_catalog import classify as _cls
    if _is_clear_business(text):
        keep = {"last_product": session["last_product"], "history": session.get("history")} if session.get("last_product") else {"history": session.get("history")}
        save_session(user_id, {"phase": "new", "fields": {}, **keep})
        return _answer_business(text)

    # ── ผู้ใช้สั่ง "แจ้งซ่อม" ตรง ๆ → เข้าเก็บข้อมูลทันที (เดี๋ยวนี้ตกไปวินิจฉัยซ้ำแล้วจบที่ลิงก์ฟอร์ม) ──
    if _is_explicit_repair(text) and phase in ("new", "done", "diagnosing"):
        fields = dict(session.get("fields") or {})
        dev = session.get("saved_device") or fields.get("device_id")
        sym = session.get("symptom_buf") or session.get("initial_symptom")
        if dev:
            fields["device_id"] = dev
        if sym and not fields.get("symptom"):
            fields["symptom"] = sym
        save_session(user_id, {"phase": "collecting", "fields": fields})
        if fields.get("device_id"):
            return ("ได้เลยค่ะ 🙏 จะแจ้งซ่อมให้ **" + str(fields["device_id"]) + "** นะคะ "
                    "ขอ **ชื่อผู้แจ้ง** ก่อนค่ะ")
        return ("ได้เลยค่ะ 🙏 ขอ **ชื่อผู้แจ้ง** ก่อนนะคะ "
                "(หรือบอกอุปกรณ์/ห้องที่จะแจ้งซ่อมมาก็ได้ค่ะ)")

    # ── DIAGNOSING: รวบรวมอาการ + เก็บ device/ข้อมูลที่ผู้ใช้ให้ไปแล้ว (ก่อนเก็บชื่อ) ──
    if phase == "diagnosing":
        buf = (session.get("symptom_buf", "") + " " + text).strip()
        rnd = session.get("diagnose_round", 1)
        session["symptom_buf"] = buf
        # เก็บ device/ห้อง ที่ผู้ใช้พูดถึง (ถ้ามี) ไม่ต้องถามซ้ำทีหลัง
        saved_dev = session.get("saved_device") or ""
        dv = saved_dev or (_extract_field_from_text("device_id", buf) or "")
        if dv:
            session["saved_device"] = dv
        # วินิจฉัยจาก KB ด้วยข้อความรวม (พยายามแนะนำวิธีแก้ก่อนเสมอ — ตามที่ต้องการ)
        from app.kb_loader import load_kb_candidates
        db = SessionLocal()
        try:
            cand = load_kb_candidates(db)
        finally:
            db.close()
        m = match_article(buf, None, cand)
        if m and m.get("steps"):
            session["phase"] = "new"; session["kb_steps"] = m["steps"]
            session["resolving"] = True
            session["symptom_buf"] = buf
            save_session(user_id, session)
            # ให้ Gemini ร่างคำตอบอธิบายจาก KB steps (เหมือน path ของ handle_message)
            from app.gemini_service import explain_steps
            explained = explain_steps(buf, m["steps"], m.get("device_type") or "")
            if explained:
                return explained
            steps = "\n".join(f"{i+1}. {s}" for i, s in enumerate(m["steps"][:6]))
            return (f"รับทราบนะคะ 🙏 ขอให้ลองทำตามนี้ก่อน ลองทีละขั้นดูค่ะ:\n{steps}\n\n"
                    "ถ้าลองทำตามแล้ว **หาย** ก็บอก 'หายแล้ว' ได้เลยนะคะ หรือถ้ายัง**ไม่หาย** พิมพ์ 'ยังไม่หาย' "
                    "เดี๋ยวเราจะให้ช่างไปช่วยตรวจถึงที่ให้ค่ะ")
        # ยังไม่เจอ → เก็บรายละเอียดเพิ่ม (แต่ถ้า device มีแล้ว + มีรายละเอียดพอ ให้เข้าข้อมูลผู้แจ้งได้)
        has_detail = len([w for w in re.split(r"[\s,]", buf) if len(w) >= 2]) >= 4
        if rnd < 3 and not (dv and has_detail):
            session["diagnose_round"] = rnd + 1
            save_session(user_id, session)
            # หมุนข้อความถามต่อตามรอบ (ลดความรู้สึกเป็นแม่พิมพ์/บอทซ้ำ)
            _ask_more = [
                "รับทราบค่ะ 🙏 ช่วยเล่าเพิ่มอีกหน่อยได้ไหมคะ ว่าเริ่มเป็นตอนไหน มีเสียง/ภาพ/ไฟยังไงบ้าง "
                "หรือลองทำอะไรไปแล้วบ้าง? เราจะได้วิเคราะห์ให้ตรงจุดขึ้นนะคะ",
                "ขอบคุณที่แจ้งรายละเอียดนะคะ 😊 อยากรู้เพิ่มอีกนิดว่าตอนนี้ไฟ/เสียง/ภาพเป็นยังไงบ้างคะ "
                "หรือลองแก้ไขอะไรไปแล้ว? จะได้ช่วยตรงจุดที่สุดค่ะ",
            ]
            return _ask_more[(rnd - 1) % len(_ask_more)]
        # ยังไม่เจอ KB + ครบ/พอแล้ว → ส่งลิงก์ฟอร์มแจ้งซ่อม (ไม่บังคับกรอกอุปกรณ์ทีละ field)
        session["phase"] = "new"
        if dv:
            session["saved_device"] = dv
        save_session(user_id, session)
        return _form_fallback_text()

    # ── ถ้าอยู่ระหว่างเก็บข้อมูล (collecting) → ถาม field ถัดไป ──
    if phase == "collecting":
        fields = session.get("fields", {})
        # เคส safety-critical เก็บชื่อ/เบอร์ก่อนข้อมูลอุปกรณ์ เพื่อให้เจ้าหน้าที่ติดต่อด่วนได้
        field_order = REQUIRED_FIELDS
        if fields.get("urgency") == "safety_critical":
            by_key = {key: (key, question) for key, question in REQUIRED_FIELDS}
            field_order = [by_key[k] for k in ("name", "phone", "device_id", "symptom")]
        # Gemini สกัดข้อมูลจากข้อความก่อน (แม่นกว่า regex กับข้อความธรรมชาติ/หลายข้อมูลในประโยค)
        from app.gemini_service import extract_fields_ai, phrase_slot_question
        missing = [k for k, _q in field_order if not fields.get(k)]
        ai_extracted = extract_fields_ai(text, fields, missing)
        for k, v in ai_extracted.items():
            fields[k] = v
        # fallback regex เฉพาะ field ที่ Gemini ยังไม่ได้ (กัน Gemini ล่ม/ไม่มี key)
        for key, _q in field_order:
            if not fields.get(key):
                # ห้ามเก็บชื่อ/เบอร์ที่เพิ่งตอบ มาเป็น "อาการ" — คำตอบสั้น ๆ ที่ไม่ใช่อาการ
                # จะกลายเป็น description ของ ticket ที่ผิด (เช่น symptom = "สมหญิง ใจดี")
                if key == "symptom" and session.get("_ask_field") != "symptom":
                    continue
                val = _extract_field_from_text(key, text)
                if val:
                    fields[key] = val
        # ถาม field ที่ขาดถัดไป — ให้ Gemini ถามธรรมชาติ (มี fallback template เดิม)
        for key, question in field_order:
            if not fields.get(key):
                # กันวังวน: ถ้าถาม field เดิมซ้ำหลายรอบแล้วผู้ใช้ยังให้ไม่ได้
                # (เช่น ไม่รู้รหัสอุปกรณ์) → ส่งลิงก์ฟอร์มแจ้งซ่อมแทน ไม่ถามวนไปเรื่อย ๆ
                asked = session.get("_ask_field")
                tries = session.get("_ask_tries", 0) + 1 if asked == key else 1
                if tries >= 3:
                    session["phase"] = "new"
                    session["fields"] = fields
                    session.pop("_ask_field", None)
                    session.pop("_ask_tries", None)
                    save_session(user_id, session)
                    return _form_fallback_text()
                session["fields"] = fields
                session["_ask_field"] = key
                session["_ask_tries"] = tries
                save_session(user_id, session)
                natural = phrase_slot_question(fields, key, text)
                return natural or f"ขอบคุณนะคะ 🙏 ถ้าอย่างนั้น {question}"
        # ครบทุก field → ยืนยัน
        session["phase"] = "confirm"
        session["fields"] = fields
        session.pop("_ask_field", None)
        session.pop("_ask_tries", None)
        save_session(user_id, session)
        summary = "\n".join(f"• {k}: {v}" for k, v in fields.items())
        _confirm_texts = [
            f"ขอเช็คข้อมูลให้ครบอีกครั้งนะคะ 🙏\n{summary}\n\nข้อมูลถูกต้องครบถ้วนไหมคะ? พิมพ์ **ยืนยัน** เพื่อส่งเรื่องให้ช่าง หรือ **แก้ไข** ถ้าอยากแก้อะไรค่ะ",
            f"ได้ข้อมูลมาครบแล้วนะคะ 🎯\n{summary}\n\nช่วยยืนยันให้อีกครั้งว่า**ถูกต้อง**ไหมคะ? พิมพ์ 'ยืนยัน' เพื่อส่งให้ช่าง หรือบอก 'แก้ไข' ได้เลยค่ะ",
        ]
        return _confirm_texts[int(fields.get("_confirm_round", 0)) % len(_confirm_texts)]

    # ── ยืนยันสร้าง ticket ──
    if phase == "confirm":
        fields = session.get("fields", {})
        if _is_affirmative(text):
            ticket_no, err = _create_ticket_from_fields(fields)
            if err:
                # ไม่เปิดเผยรายละเอียด DB/exception ให้ผู้ใช้เห็น
                print(f"[chatbot] ticket creation failed: {err}")
                return "ขออภัยค่ะ ระบบยังสร้าง Ticket ไม่สำเร็จ ข้อมูลยังไม่ถูกส่งซ้ำค่ะ ขอให้ลองอีกครั้งหรือติดต่อเจ้าหน้าที่โดยตรงนะคะ 🙏"
            session["phase"] = "done"
            session["ticket_no"] = ticket_no
            save_session(user_id, session)
            _notify_ticket_created(fields, ticket_no)
            # ใช้ template แน่นอน (ไม่ให้ Gemini ใส่ placeholder หลุดในข้อความยืนยันสำคัญ)
            name = (fields.get("name") or "").strip()
            who = f"คุณ{name} " if name else ""
            return (f"✅ แจ้งซ่อมเรียบร้อยแล้วนะคะ {who}เลขที่ใบงานของคุณคือ **{ticket_no}**\n"
                    "ทีมงานจะรีบตรวจสอบและดำเนินการให้เร็วที่สุดเลยค่ะ ขอบคุณที่ไว้วางใจให้เราดูแลนะคะ 🙏\n"
                    "ติดตามสถานะได้โดยพิมพ์ 'ติดตาม' หรือส่งเลขใบงานมาได้ทุกเมื่อค่ะ")
        if _is_negative(text):
            session["phase"] = "collecting"
            # reset ให้ถามใหม่
            session["fields"] = {}
            save_session(user_id, session)
            return "ไม่เป็นไรค่ะ 😊 เราเริ่มเก็บข้อมูลใหม่ให้เลย ขอ **ชื่อของคุณ** ก่อนนะคะ"
        return "ช่วยพิมพ์ **ยืนยัน** เพื่อส่งเรื่องให้ช่าง หรือ **แก้ไข** เพื่อกรอกข้อมูลใหม่ให้หน่อยนะคะ 🙏"

    # ── phase=new / เริ่มคุย / หลังทำเสร็จ ──
    # ตรวจว่าแก้ได้แล้ว (จากขั้นตอนก่อนหน้า)
    if phase == "done" and _has_reply_phrase(text, RESOLVED_WORDS):
        clear_session(user_id)
        return "ดีใจด้วยนะคะ 🎉 ที่แก้ได้ด้วยตัวเอง! บันทึกไว้แล้วนะคะ ถ้ามีปัญหาอื่นอีก พิมพ์บอกเราได้เสมอเลยค่ะ 😊"

    # resolving ต้องถูกตรวจสอบก่อนเริ่ม intent ใหม่ มิฉะนั้น state จะถูก reset
    # และคำตอบ 'หายแล้ว/ยังไม่หาย' จะถูกตีความเป็นข้อความใหม่
    if phase == "new" and session.get("resolving"):
        # ต้องตรวจคำปฏิเสธก่อน เพราะ "ยังไม่หาย" มี substring "หาย"
        not_resolved = _has_reply_phrase(text, NOT_RESOLVED_WORDS)
        resolved = _has_reply_phrase(text, RESOLVED_WORDS) and not not_resolved
        if not_resolved:
            session["phase"] = "new"
            session["resolving"] = False
            # เก็บประเภทอุปกรณ์จากข้อความเดิมไว้ใช้ได้ (ไม่ถามซ้ำ)
            original = session.get("symptom_buf") or text
            inferred_device = _extract_field_from_text("device_id", original) or ""
            if not inferred_device:
                low = original.lower()
                for marker in ["interactive display", "aiboard", "คอมพิวเตอร์", "โน้ตบุ๊ก", "โปรเจกเตอร์", "ลำโพง", "ไมโครโฟน", "กล้อง", "เครื่องพิมพ์", "wifi", "wi-fi"]:
                    if marker in low:
                        inferred_device = marker
                        break
            if inferred_device:
                session["saved_device"] = inferred_device
            save_session(user_id, session)
            # ให้ Gemini แต่งคำตอบเห็นใจ + แจ้งขั้นตอน (fallback template เดิม)
            from app.gemini_service import phrase_repair_reply
            natural = phrase_repair_reply("not_resolved", f"อาการเดิม: {original}")
            base = natural or "รับทราบค่ะ เสียใจด้วยนะคะที่ยังไม่หาย 😔 เดี๋ยวจะส่งลิงก์ฟอร์มแจ้งซ่อมให้ทีมช่างได้เลยค่ะ"
            return base + "\n\n" + _form_fallback_text()
        if resolved:
            # ── บันทึก self-service จริง (ตาราง self_service_cases) ──
            try:
                from app.models import SelfServiceCase
                _db = SessionLocal()
                try:
                    _device = (session.get("saved_device") or session.get("symptom_buf") or "")[:64]
                    _sym = (session.get("symptom_buf") or text or "")[:300]
                    _db.add(SelfServiceCase(
                        device_id=_device or None,
                        symptom=_sym,
                        resolved=True,
                        time_saved_minutes=10,
                    ))
                    _db.commit()
                finally:
                    _db.close()
            except Exception as _e:
                print(f"[chatbot] save self-service failed: {_e}")
            clear_session(user_id)
            from app.gemini_service import phrase_repair_reply as _pr
            return _pr("resolve_success", "") or "ดีใจด้วยนะคะ 🎉 ที่แก้ได้ด้วยตัวเอง! บันทึกเป็นการแก้ไขเบื้องต้นไว้แล้วค่ะ 😊"
        return "ลองทำตามขั้นตอนที่แนะนำแล้วเป็นอย่างไรบ้างคะ? พิมพ์ **หายแล้ว** หรือ **ยังไม่หาย** ได้เลยค่ะ 😊"

    # เริ่มต้นรอบใหม่เฉพาะ phase==new (ไม่ reset state resolving)
    if phase == "new":
        # เก็บ context สินค้าล่าสุดไว้ (มิฉะนั้นคำถามติดตามเช่น 'มีขนาดอื่นไหม' จะหล่นไป flow แจ้งซ่อม)
        _keep = {"last_product": session["last_product"], "history": session.get("history")} if session.get("last_product") else {"history": session.get("history")}
        session = {"phase": "new", "fields": {}, **_keep}
        save_session(user_id, session)

    # ทักทาย/ไม่ใช่อาการ
    greeting = any(w in text for w in ["สวัสดี", "hello", "hi", "ทัก"])
    if greeting and not _is_symptom(text):
        return ("สวัสดีค่ะ 👋 ยินดีที่ได้คุยด้วยนะคะ วันนี้มีอะไรให้ช่วยไหมคะ? 😊\n"
                "ถ้าอยาก**สอบถามสินค้า/บริการ** พิมพ์ชื่อได้เลย เช่น 'Iwa AiBoard' 'หลักสูตรภาษาอังกฤษ'\n"
                "หรือถ้าเจอ**ปัญหาอุปกรณ์** อยากแจ้งซ่อม พิมพ์ 'แจ้งซ่อม' หรือบอกอาการ เช่น 'จอไม่ติด' ก็ได้ค่ะ\n"
                "📞 สนใจติดต่อทีมงาน พิมพ์ 'ติดต่อ' ได้เลยนะคะ")

    # ── คำถามเชิงธุรกิจ (สินค้า/บริการ/ราคา/ติดต่อ) ──
    from app.company_catalog import classify, search_products, find_product, ALL_PRODUCTS, \
        SERVICES, COMPANY, PRODUCT_CATEGORIES, contact_text
    _biz = classify(text)
    if _biz == "business" and not (_is_product_followup(text) and session.get("last_product")):
        # A business question explicitly changes the subject. Park any active
        # repair/lead/tracking state so the next message starts cleanly.
        if phase not in ("new", "done") or session.get("resolving"):
            keep = {"last_product": session["last_product"], "history": session.get("history")} if session.get("last_product") else {"history": session.get("history")}
            session = {"phase": "new", "fields": {}, **keep}
            save_session(user_id, session)
        _reply = _answer_business(text)
        # จำ context สินค้าล่าสุดไว้ใช้ตอบคำถามติดตาม (เช่น 'มีขนาดอื่นไหม')
        _prod = _take_pending_product()
        if not _prod:
            # thread-local อาจไม่ sync กับ async request — ลองหา product จาก text ตรงๆ
            try:
                from app.company_catalog import find_product as _fp, PRODUCT_CATEGORIES as _PC
                _p = _fp(text)
                if not _p and any(k in text.lower() for k in ["aiboard", "ai board", "สมาร์ทบอร์ด", "aboard"]):
                    _bc = next((c for c in _PC if c["id"] == "smart-board"), None)
                    if _bc and _bc["products"]:
                        _p = {**_bc["products"][0], "cat_id": "smart-board", "category": _bc["name"]}
                _prod = _p
            except Exception:
                pass
        if _prod:
            try:
                _s = get_session(user_id)
                save_session(user_id, {**_s, "last_product": {
                    "name": _prod.get("name"), "cat_id": _prod.get("cat_id"),
                    "category": _prod.get("category"), "summary": _prod.get("summary"),
                    "img": _prod.get("img")}})
            except Exception as _e:
                print(f"[last_product save err] {_e}")
        return _reply  # wrapper handle_message() จะ log/จัดรูปแบบให้เอง

    # ── คำถามติดตามสินค้า (ขนาด/รุ่น/สเปก/เทียบ) — อิงจากสินค้าที่เพิ่งคุย ชนะ flow แจ้งซ่อม ──
    if _is_product_followup(text) and _biz != "repair" and session.get("last_product"):
        return _answer_product_followup(session.get("last_product"), text)

    # อาการ → วินิจฉัยจาก KB (ผ่าน Gemini + KB)
    # ใช้ classify() ของ catalog เสริม เพราะข้อความอาการจริงใน LINE มักไม่มีคำใน HELP_WORDS
    # (เช่น "หน้าจอห้อง 201 ค้าง กดอะไรไม่ได้เลย") — เดิมตกไปตอบว่า "นอกขอบเขต"
    if _is_symptom(text) or _cls(text) == "repair":
        from app.kb_loader import load_kb_candidates
        db = SessionLocal()
        try:
            cand = load_kb_candidates(db)
        finally:
            db.close()
        m = match_article(text, None, cand)  # ลอง Gemini เลือกบทความ
        if m and m.get("steps"):
            session["phase"] = "new"  # ให้แนะนำแล้วรอ feedback
            session["kb_steps"] = m["steps"]
            session["resolving"] = True
            # เก็บอาการต้นฉบับไว้ใช้ต่อ หากผู้ใช้ตอบว่า "ยังไม่หาย"
            session["symptom_buf"] = text
            session["initial_symptom"] = text
            save_session(user_id, session)
            # ให้ Gemini ร่างคำตอบอธิบายจาก KB steps (ฟังภาษาพูด/กำกวม + อธิบายให้เข้าใจง่าย)
            from app.gemini_service import explain_steps
            explained = explain_steps(text, m["steps"], m.get("device_type") or "")
            if explained:
                return explained
            # fallback: เรียง list เดิมเมื่อ Gemini ล่ม
            steps = "\n".join(f"{i+1}. {s}" for i, s in enumerate(m["steps"][:6]))
            return (f"รับทราบนะคะ 🙏 ขอให้ลองทำตามนี้ก่อน ลองทีละขั้นดูค่ะ:\n{steps}\n\n"
                    "ถ้าลองทำตามแล้ว **หาย** ก็บอก 'หายแล้ว' ได้เลยนะคะ หรือถ้ายัง**ไม่หาย** พิมพ์ 'ยังไม่หาย' "
                    "เดี๋ยวเราจะให้ช่างไปช่วยตรวจถึงที่ให้ค่ะ")
        # ไม่พบ KB จากข้อความแรก: เก็บอุปกรณ์ที่ผู้ใช้ระบุไว้ทันที
        # ห้ามถามอุปกรณ์ซ้ำ หากข้อความเดิมมี device/ห้องอยู่แล้ว
        session["phase"] = "diagnosing"
        session["symptom_buf"] = text
        session["diagnose_round"] = 1
        first_device = _extract_field_from_text("device_id", text) or ""
        if first_device:
            session["saved_device"] = first_device
        save_session(user_id, session)
        detail_count = len([w for w in re.split(r"[\s,]", text) if len(w) >= 2])
        if first_device and detail_count >= 4:
            # มีอุปกรณ์ + รายละเอียดเพียงพอแล้ว: ไปเก็บผู้แจ้งต่อทันที
            session["phase"] = "collecting"
            session["fields"] = {"device_id": first_device, "symptom": text}
            save_session(user_id, session)
            return ("รับทราบอาการแล้วค่ะ 🙏 เบื้องต้นยังไม่พบวิธีแก้ที่ตรงพอจะให้ลองเองอย่างปลอดภัย "
                    "เดี๋ยวให้ช่างช่วยตรวจต่อค่ะ ขอทราบ **ชื่อของคุณ** ก่อนนะคะ")
        if first_device:
            return ("เข้าใจแล้วค่ะ เป็นอุปกรณ์ **" + first_device + "** ใช่ไหมคะ? "
                    "ช่วยเล่าเพิ่มอีกนิดว่าอาการเป็นอย่างไร เช่น ไม่มีภาพ ไม่มีเสียง ค้าง หรือเปิดไม่ติด "
                    "จะได้แนะนำวิธีแก้ให้ตรงจุดที่สุดค่ะ")
        return ("รับทราบค่ะ 🙏 ก่อนอื่นอยากให้เล่าว่า**อุปกรณ์หรือห้อง**ที่ใช้อยู่เป็นอะไรคะ? "
                "เช่น จอ Interactive Display ห้อง 201 หรือคอมพิวเตอร์ห้องสมุด "
                "แล้วตอนนี้มีอาการอย่างไรบ้างคะ?")

    # กรณี resolving อยู่ แล้วบอกไม่หาย
    if session.get("resolving") and _has_reply_phrase(text, NOT_RESOLVED_WORDS):
        session["phase"] = "collecting"
        session["fields"] = {"symptom": session.get("initial_symptom", text)}
        save_session(user_id, session)
        return "รับทราบค่ะ เสียใจด้วยนะคะที่ยังไม่หาย 😔 เดี๋ยวจะแจ้งช่างให้ไปช่วยตรวจถึงที่เลย ขอข้อมูลหน่อยนะคะ **ชื่อของคุณ** คืออะไรคะ?"

    # หลังทำเสร็จแล้วถามอย่างอื่น → เริ่มใหม่
    if phase == "done":
        clear_session(user_id)
        return handle_message(user_id, text, reply_token, group)

    return _answer_out_of_scope()


def _looks_like_device_code(value: str) -> bool:
    """ข้อความนี้พอจะเป็น "รหัสอุปกรณ์" ได้หรือไม่

    ต้องมีตัวอักษรปนอยู่และยาวพอ — ตัวเลขล้วนอย่าง "301" ถือเป็นเลขห้อง ไม่ใช่รหัสอุปกรณ์
    ถ้าเอาไป substring match กับ devices.device_id มันจะไปตรงกับ DEV-2024-00301
    ซึ่งเป็นอุปกรณ์คนละห้อง (Router ห้อง 201) แล้ว ticket จะผูกผิดเครื่อง/ผิดห้อง
    """
    v = (value or "").strip()
    return len(v) >= 3 and any(ch.isalpha() for ch in v)


def _ambiguous_device_error(matches) -> str:
    """ข้อความเมื่อตรงหลายเครื่อง — ต้องถามผู้ใช้ ห้ามเลือกเครื่องให้เอง"""
    codes = ", ".join(str(m["device_id"]) for m in matches[:3])
    return (f"พบอุปกรณ์หลายเครื่องที่ตรงกับข้อมูลนี้ ({codes}) "
            "รบกวนระบุรหัสอุปกรณ์บนสติกเกอร์ QR ให้ชัดเจนอีกครั้งนะคะ")


def _create_ticket_from_fields(fields: dict):
    """สร้าง ticket ผ่าน DB ตรง (ใช้ helper ของ main) — คืน (ticket_no, err)"""
    from app.models import Device, Organization, RepairTicket, TicketUpdate, TicketStatus, get_db
    from app.main import generate_ticket_id, calc_sla_due
    from datetime import datetime, timezone
    db = SessionLocal()
    try:
        device_id = (fields.get("device_id") or "").strip()
        symptom = (fields.get("symptom") or "").strip()
        if not device_id and not symptom:
            return None, "ไม่พบข้อมูลอุปกรณ์หรืออาการ"
        # 1) ค้นแบบตรงตัวก่อน (case-insensitive) — ปลอดภัยที่สุด
        dev = None
        if device_id:
            dev = db.execute(text(
                "SELECT * FROM devices WHERE lower(device_id) = lower(:d) LIMIT 1"
            ), {"d": device_id}).mappings().first()
        # 2) ค้นบางส่วนของรหัสอุปกรณ์ — ทำได้เฉพาะเมื่อข้อความ "ดูเหมือนรหัสอุปกรณ์"
        #    ห้ามทำกับตัวเลขล้วน เช่น "301": ILIKE '%301%' ไปตรงกับ DEV-2024-00301
        #    ซึ่งอยู่ห้อง 201 → ticket ผูกผิดเครื่อง ช่างถูกส่งไปผิดห้อง
        #    และถ้าตรงหลายเครื่องคือกำกวม ต้องถามผู้ใช้ ห้ามหยิบเครื่องแรกมาใช้
        if not dev and device_id and _looks_like_device_code(device_id):
            code_matches = db.execute(text(
                "SELECT * FROM devices WHERE device_id ILIKE '%'||:d||'%' LIMIT 3"
            ), {"d": device_id}).mappings().all()
            if len(code_matches) == 1:
                dev = code_matches[0]
            elif len(code_matches) > 1:
                return None, _ambiguous_device_error(code_matches)
        # 3) ระบุเป็นห้อง → ใช้ได้เฉพาะกรณีห้องนั้นมีอุปกรณ์เครื่องเดียว
        if not dev and device_id:
            in_room = db.execute(text(
                "SELECT d.* FROM devices d JOIN rooms r ON r.id=d.room_id "
                "WHERE r.code ILIKE :q OR r.name ILIKE :q LIMIT 3"
            ), {"q": f"%{device_id}%"}).mappings().all()
            if len(in_room) == 1:
                dev = in_room[0]
            elif len(in_room) > 1:
                return None, _ambiguous_device_error(in_room)
        # 4) หาไม่เจอ → หยุด ห้ามเดาเครื่องให้
        # ห้ามใส่ fallback แบบ "เอาเครื่องชนิดเดียวกัน" หรือ "เอาเครื่องแรกในระบบ" กลับมา:
        # มันสร้าง ticket ผูกกับอุปกรณ์/โรงเรียนที่ไม่ใช่ของผู้แจ้ง ช่างจะถูกส่งไปผิดห้อง
        # และข้อมูลข้ามองค์กร (guardrail: test_unknown_device_never_falls_back_to_test_device)
        if not dev:
            return None, f"ไม่พบอุปกรณ์ที่ตรงกับ '{device_id or symptom[:40]}'"
        did = dev["device_id"]
        org_id = dev["organization_id"]
        now = datetime.now(timezone.utc)
        # priority ต้องเป็นค่าใน priority_enum เท่านั้น (low/normal/high/critical)
        # "urgent" ไม่มีใน enum → PostgreSQL จะ error และ calc_sla_due จะ fallback เป็น normal
        _is_safety_critical = fields.get("urgency") == "safety_critical"
        _priority = "critical" if _is_safety_critical else "normal"
        ticket = RepairTicket(
            ticket_id=generate_ticket_id(db, org_id),
            organization_id=org_id,
            device_id=did,
            title=f"LINE แจ้งซ่อม: {fields.get('symptom','')[:80]}",
            description=fields.get("symptom", ""),
            reporter_name=fields.get("name", "ผู้ใช้ LINE"),
            reporter_phone=fields.get("phone"),
            priority=_priority,
            escalation_level=1 if _is_safety_critical else 0,
            status=TicketStatus.NEW,
            channel="line",
            sla_due_at=calc_sla_due(now, _priority),
        )
        db.add(ticket)
        db.flush()
        db.add(TicketUpdate(ticket=ticket, from_status=None, to_status="new",
                            note="สร้างจาก LINE chatbot", author_name=fields.get("name"),
                            author_role="reporter"))
        db.commit()
        return ticket.ticket_id, None
    except Exception as e:
        db.rollback()
        # log ของจริงไว้ที่ server เท่านั้น — ข้อความที่คืนไปจะถูกนำไปแสดงต่อผู้ใช้ LINE
        print(f"[chatbot] _create_ticket_from_fields failed: {e!r}")
        return None, "ระบบขัดข้องระหว่างสร้างใบงาน"
    finally:
        db.close()


def _notify_ticket_created(fields: dict, ticket_no: str):
    """แจ้งเตือนหลังสร้าง ticket: กลุ่ม LINE + push ส่วนตัวเจ้าหน้าที่ (จากตาราง users/line_staff)"""
    try:
        from app.line_bot import send_line_push, LINE_GROUP_ID as GID
        msg = (f"🆕 **Ticket ใหม่: {ticket_no}**\n"
               f"ผู้แจ้ง: {fields.get('name','-')}\n"
               f"เบอร์: {fields.get('phone','-')}\n"
               f"อุปกรณ์/ห้อง: {fields.get('device_id','-')}\n"
               f"อาการ: {fields.get('symptom','-')}\n"
               f"ช่องทาง: LINE")
        # กลุ่ม LINE เจ้าหน้าที่
        if GID:
            send_line_push(GID, msg)
        # push ส่วนตัวเจ้าหน้าที่จากตาราง users + line_staff_contacts
        # ดึงรายชื่อเจ้าหน้าที่ — แยก try ต่อ query เพราะตารางเสริม (line_staff_contacts)
        # อาจไม่มีในบางสภาพแวดล้อม และไม่ควรทำให้การแจ้งเตือนทั้งหมดล้ม
        staff, extra = [], []
        db = SessionLocal()
        try:
            try:
                staff = db.execute(text(
                    "SELECT line_user_id FROM users WHERE role IN ('it_support','admin','owner') "
                    "AND line_user_id IS NOT NULL AND is_active=TRUE"
                )).fetchall()
            except Exception:
                db.rollback()
            try:
                extra = db.execute(text("SELECT user_id FROM line_staff_contacts")).fetchall()
            except Exception:
                db.rollback()
        finally:
            db.close()
        seen = set()
        for (uid,) in staff + extra:
            if uid and uid not in seen and uid != fields.get("_line_user"):
                seen.add(uid)
                send_line_push(uid, msg)
        # email แจ้ง (ย่อ: ผูกกับ SMTP ทีหลัง — ตอนนี้ log)
        print(f"[notify] ticket {ticket_no} -> group/IT staff + email (placeholder)")
    except Exception:
        # Notification failure must not hide a ticket that was already created.
        print(f"[notify] failed for ticket {ticket_no}")


# ═══════════════════════════════════════════════════════════════════════
# ตอบคำถามเชิงธุรกิจ — สินค้า / บริการ / บริษัท / ติดต่อ (ตาม company_catalog)
# ═══════════════════════════════════════════════════════════════════════
def _answer_business(text: str) -> str:
    """wrapper: ตอบคำถามธุรกิจ + ต่อท้ายด้วย offer เชิญชวนต่อ (ทุกคำตอบ)"""
    body = _ab_inner(text)
    # ถ้าจบด้วยข้อมูลติดต่อแล้ว ไม่ต้อง offer ซ้ำเยอะ
    if not any(k in body for k in ["🛍️", "📦", "🔍", "🏢", "🎓"]):
        return body
    if "ติดต่อ" in body and "LINE:" in body:
        return body + "\n\nยังมีเรื่องอื่นให้ช่วยไหมคะ? พิมพ์ 'สินค้า' หรือ 'แจ้งซ่อม' ได้เลย"
    return body + "\n\n🙂 ยังมีเรื่องอื่นให้ช่วยไหมคะ? พิมพ์ชื่อสินค้า/บริการที่สนใจ หรือ 'เมนู' เพื่อดูตัวเลือก"


def _answer_admin_contact() -> str:
    """ตอบช่องทางติดต่อทันที แม้ผู้ใช้อยู่กลาง flow แจ้งซ่อมหรือขาย"""
    from app.company_catalog import contact_text
    return (
        "ได้เลยค่ะ 😊 หากต้องการคุยกับแอดมินหรือเจ้าหน้าที่ สามารถติดต่อได้ทันทีตามช่องทางนี้ค่ะ\n\n"
        f"📞 ช่องทางติดต่อ:\n{contact_text()}\n\n"
        "หากกำลังรอแอดมินตอบกลับ รบกวนรอประมาณ 5–10 นาทีในเวลาทำการนะคะ "
        "ทีมงานจะรีบดูแลให้ค่ะ"
    )


def _answer_out_of_scope() -> str:
    """ตอบอย่างสุภาพเมื่อคำถามอยู่นอกขอบเขตของระบบ"""
    from app.company_catalog import contact_text
    return (
        "ขออภัยค่ะ ระบบนี้ให้บริการข้อมูลสินค้า/บริการของบริษัท รับแจ้งซ่อมอุปกรณ์ "
        "และช่วยติดตาม Ticket เป็นหลักนะคะ\n\n"
        "หากต้องการสอบถามเรื่องอื่นหรือขอให้แอดมินช่วยดูแลต่อ ติดต่อได้ที่:\n"
        f"{contact_text()}\n\n"
        "กรุณารอประมาณ 5–10 นาทีในเวลาทำการสำหรับการติดต่อกลับนะคะ 🙏"
    )


def _format_product_reply(prod: dict, extra: str = "") -> str:
    """ตอบสินค้าโดยใช้เฉพาะข้อมูลใน company_catalog และปิดคำถามให้ครบใน LINE (ไม่มีลิงก์ให้เปิดเอง)"""
    price = prod.get("price")
    price_line = f"💰 ราคา: {price}" if price not in (None, "") else "💰 ราคา/โปรโมชั่น: กรุณาติดต่อทีมงานเพื่อขอใบเสนอราคาตามรุ่นและจำนวนค่ะ"
    parts = [
        f"📦 **{prod.get('name', 'สินค้า')}**",
        f"หมวด: {prod.get('category', '-')}",
        f"รายละเอียด: {prod.get('summary', '-')}",
    ]
    if extra:
        parts.append(extra.strip())
    parts.append(price_line)
    parts.append("สนใจสอบถามราคา ขอใบเสนอราคา หรือให้ทีมงานแนะนำรุ่นที่เหมาะสม พิมพ์ **ติดต่อเรา** ได้เลยนะคะ")
    return "\n".join(parts)


def _ab_inner(text: str) -> str:
    """ตอบคำถามสินค้า/บริการ/ราคา/ติดต่อ จาก company_catalog (grounded ไม่สร้างเอง)"""
    from app.company_catalog import (search_products, find_product, ALL_PRODUCTS,
                                     SERVICES, COMPANY, PRODUCT_CATEGORIES, contact_text,
                                     find_service, company_summary_text, _fuzzy_product_names)
    t = text.strip().lower()

    # 1) ติดต่อ / ที่อยู่ / เบอร์ / line / email
    if any(w in t for w in ["ติดต่อ", "ที่อยู่", "address", "เบอร์", "โทร", "line", "อีเมล",
                            "email", "ช่องทาง", "สั่ง", "inquire"]):
        return f"{company_summary_text()}\n\n📞 {contact_text()}"

    # 2) บริการ — ตรวจเจาะจงก่อน (ดูแลรักษา/บำรุง/network/software/จัดจำหน่าย/อบรม) แล้วตอบตัวนั้น
    if any(w in t for w in ["บริการ", "service", "โซลูชัน", "อบรม", "training", "สัมมนา",
                            "ดูแลรักษา", "บำรุง", "เครือข่าย", "network", "จัดจำหน่าย",
                            "ซัพพลาย", "จำหน่ายอุปกรณ์", "net", "ระบบเน็ต", "maintenance",
                            "เมนเทน", "ซ่อมบำรุง", "กู้คืน", "ติดตั้งระบบ", "software", "ซอฟต์แวร์"]):
        # map คำไทย → service id
        service_keywords = {
            "network": ["network", "เครือข่าย", "เน็ตเวิร์ก", "ระบบเน็ต", "แลน", "lan", "fiber", "ไฟเบอร์"],
            "software": ["software", "ซอฟต์แวร์", "แอป", "application", "แอปพลิเคชัน", "ระบบงาน", "พัฒนา"],
            "maintenance": ["ดูแลรักษา", "บำรุง", "maintenance", "เมนเทน", "ดูแลระบบ", "ซ่อมบำรุง", "กู้คืน", "ตรวจเช็ก", "ตรวจเช็ค"],
            "supply": ["จัดจำหน่าย", "จำหน่าย", "ขายอุปกรณ์", "อุปกรณ์", "hardware", "ซัพพลาย", "จัดหา"],
            "training": ["อบรม", "training", "สัมมนา", "seminar", "train"],
        }
        found_sid = None
        for sid, kws in service_keywords.items():
            if any(k in t for k in kws):
                found_sid = sid
                break
        if found_sid:
            sv = find_service(found_sid)
            if sv:
                items = "\n".join(f"• {i}" for i in sv["items"])
                return (f"🏢 **{sv['name']}**\n{sv['desc']}\n{items}\n\n"
                        "สนใจสอบถาม/ใช้บริการ ติดต่อทีมงานได้เลยค่ะ (พิมพ์ 'ติดต่อ')")
        # ยังไม่เจาะจง → รายชื่อทั้งหมด
        lines = [f"{i+1}. **{s['name']}** — {s['desc']}" for i, s in enumerate(SERVICES)]
        return ("🏢 **บริการของ IWA RICH YOU D**\n" + "\n".join(lines) +
                "\n\nพิมพ์ชื่อบริการ เช่น 'บริการดูแลรักษา' 'อบรม' หรือ 'ติดต่อ' เพื่อสอบถามเพิ่มค่ะ")

    # 3) ดูหมวดสินค้าทั้งหมด
    if any(w in t for w in ["สินค้า", "product", "มีอะไร", "แคตตาล็อก", "catalog", "รายการ"]):
        lines = [f"• **{c['name']}** — {len(c['products'])} รายการ" for c in PRODUCT_CATEGORIES]
        return ("🛍️ **หมวดสินค้าของเรา**\n" + "\n".join(lines) +
                "\n\nพิมพ์ชื่อสินค้า/หมวด เพื่อดูรายละเอียด เช่น 'Iwa AiBoard' 'สื่อปฐมวัย' 'หลักสูตรอังกฤษ'")

    # 4) ค้นหาสินค้าที่ตรง
    # กรณี AiBoard หลายรุ่น / ยังไม่ระบุขนาด → ขึ้นรายการรุ่นก่อน (รับคำผิดด้วย เช่น 'aboard')
    _fuzzy_names = _fuzzy_product_names(text)
    _is_ai_family = ("aiboard" in t or "ai board" in t or "สมาร์ทบอร์ด" in t or "smart board" in t
                     or any("aiboard" in n.lower() for n in _fuzzy_names))
    if _is_ai_family and not any(sz in t for sz in ["65", "75", "86", "นิ้ว", "inch"]):
        board_cat = next((c for c in PRODUCT_CATEGORIES if c["id"] == "smart-board"), None)
        if board_cat:
            lines = [f"• {p['name']}" for p in board_cat["products"]]
            if board_cat["products"]:
                _set_pending_product({**board_cat["products"][0], "cat_id": "smart-board",
                                      "category": board_cat["name"]})
                _set_pending_image(board_cat["products"][0].get("img") or "")
            return (f"🖥️ **{board_cat['name']}** มีให้เลือก {len(board_cat['products'])} รุ่น:\n"
                    + "\n".join(lines) +
                    f"\n\n✨ {board_cat.get('common','')}\n\n"
                    "พิมพ์รุ่นที่สนใจ เช่น 'Iwa AiBoard 86 นิ้ว' หรือ 'ติดต่อ' เพื่อสอบถามราคาค่ะ")
    prod = find_product(text)
    if prod:
        extra = ""
        if prod["category"].startswith("Iwa AiBoard"):
            cat = next((c for c in PRODUCT_CATEGORIES if c["id"] == prod["cat_id"]), None)
            extra = f"\n\n✨ {cat['common']}" if cat else ""
        _set_pending_image(prod.get("img") or "")
        _set_pending_product(prod)
        return _format_product_reply(prod, extra)
    # 5) เจอสินค้าหลายตัว → ขึ้นรายการ
    res = search_products(text)
    if res:
        seen = {}
        for p in res:
            if p["name"] not in seen:
                seen[p["name"]] = p
        lines = [f"• {name} — {p['summary'][:80]}…" for name, p in list(seen.items())[:5]]
        return ("🔍 พบสินค้าที่เกี่ยวข้อง:\n" + "\n".join(lines) +
                "\n\nพิมพ์ชื่อสินค้าที่สนใจ หรือ 'ติดต่อ' เพื่อสอบถามราคาค่ะ")

    # 6) เกี่ยวกับบริษัท
    if any(w in t for w in ["บริษัท", "company", "เกี่ยวกับ", "about", "iwa", "rich"]):
        return company_summary_text()

    # 7) ไม่ชัด → ให้เมนู
    return ("ฉันช่วยเรื่องสินค้า/บริการของ IWA RICH YOU D ค่ะ 🛍️\n"
            "ลองพิมพ์ เช่น:\n"
            "• 'Iwa AiBoard 86 นิ้ว' — ข้อมูลจออัจฉริยะ\n"
            "• 'หลักสูตรภาษาอังกฤษ' / 'สื่อปฐมวัย' — หมวดสินค้า\n"
            "• 'บริการอบรม' — ดูบริการ\n"
            "• 'ติดต่อ' — ช่องทางติดต่อทีมงาน")


# ── คำถามติดตามสินค้า (ขนาด/รุ่น/สเปก/เทียบ) — ใช้ context สินค้าที่เพิ่งคุย ──
_PRODUCT_FOLLOWUP_KW = [
    "ขนาด", "รุ่นอื่น", "ตัวอื่น", "นิ้วอื่น", "กี่นิ้ว", "กี่ขนาด", "ใหญ่กว่า", "เล็กกว่า",
    "ใหญ่ขึ้น", "เล็กลง", "มีกี่", "สเปก", "spec", "เทียบ", "ต่างกัน", "ต่างยังไง",
    "อื่นไหม", "อื่นๆ", "อื่นอีก", "ทั้งหมด", "อีกไหม", "กี่รุ่น",
    "เท่าไหร่", "เท่าไร", "ราคา", "กี่บาท", "แพงไหม", "ซื้อเท่าไหร่", "ราคาเท่าไหร่",
    "ขายเท่าไหร่", "ราคาเท่าไร", "ลดได้ไหม", "ส่วนลด", "โปร",
]


def _is_product_followup(text: str) -> bool:
    t = text.strip().lower()
    if any(k in t for k in _PRODUCT_FOLLOWUP_KW):
        return True
    # ติดตามแบบสั้นจากสินค้าที่เพิ่งคุย: พูดถึงขนาด/ตัว/นิ้ว/รุ่น
    # เช่น 'แล้วตัว 75 ล่ะ' 'จอ 86' — ต้องตอบราคาจริงจากระบบ ไม่ให้ Gemini เดา
    if re.search(r"\b(65|75|86)\b", t) or "นิ้ว" in t or "ตัว" in t or "รุ่น" in t:
        return True
    return False


def _answer_product_followup(last: dict, text: str) -> str:
    """ตอบคำถามติดตามจากสินค้าที่เพิ่งคุย (เช่น 'มีขนาดอื่นไหม' 'แล้ว 75 ราคาเท่าไหร่')
    ใช้ข้อมูลจริงใน company_catalog (ราคาจริง ไม่ให้ Gemini เดา)"""
    from app.company_catalog import PRODUCT_CATEGORIES, find_product
    t = text.strip().lower()
    # ระบุขนาด/รุ่นเฉพาะ (เช่น 75, 86, นิ้ว) → ตอบราคารุ่นนั้นตรง ๆ
    sz = None
    for s in ("86", "75", "65"):
        if s in t and ("นิ้ว" in t or "ตัว" in t or "ขนาด" in t or "รุ่น" in t or "เท่า" in t or s in last.get("name", "")):
            sz = s
            break
    if sz and last.get("cat_id") == "smart-board":
        cat = next((c for c in PRODUCT_CATEGORIES if c["id"] == "smart-board"), None)
        if cat:
            for p in cat["products"]:
                if sz in p["name"]:
                    _set_pending_product({**p, "cat_id": "smart-board", "category": cat["name"]})
                    _set_pending_image(p.get("img") or "")
                    price = p.get("price")
                    pl = f"💰 ราคา: {price}" if price else "💰 ราคา: กรุณาติดต่อขอใบเสนอราคาค่ะ"
                    return (f"📦 **{p['name']}**\n{p['summary']}\n{pl}\n\n"
                            "สนใจสอบถามราคา/โปรโมชั่น พิมพ์ **ติดต่อเรา** ได้เลยนะคะ")
    if last.get("cat_id") == "smart-board":
        cat = next((c for c in PRODUCT_CATEGORIES if c["id"] == "smart-board"), None)
        if cat and cat["products"]:
            _set_pending_product({**cat["products"][0], "cat_id": "smart-board",
                                  "category": cat["name"]})
            _set_pending_image(cat["products"][0].get("img") or "")
            lines = []
            for p in cat["products"]:
                price = p.get("price")
                pl = f" — {price}" if price else ""
                lines.append(f"• **{p['name']}**{pl}\n   {p['summary']}")
            return ("🖥️ **Iwa AiBoard มีให้เลือกหลายขนาด (พร้อมราคา):**\n" + "\n".join(lines) +
                    "\n\nพิมพ์ขนาดที่สนใจ เช่น 'Iwa AiBoard 86 นิ้ว' หรือ 'ติดต่อ' เพื่อสอบถามราคาค่ะ")
    # สินค้าไม่ใช่ AiBoard — ลองหา product ที่ตรงจากข้อความ ถ้าเจอตอบราคา
    p = find_product(text)
    if p:
        _set_pending_product(p)
        _set_pending_image(p.get("img") or "")
        price = p.get("price")
        pl = f"💰 ราคา: {price}" if price else "💰 ราคา: กรุณาติดต่อขอใบเสนอราคาค่ะ"
        return f"📦 **{p['name']}**\n{p['summary']}\n{pl}\n\nสนใจสอบถามราคา พิมพ์ **ติดต่อเรา** ได้เลยนะคะ"
    _set_pending_image(last.get("img") or "")
    return (f"📦 **{last.get('name', 'สินค้า')}**\n{last.get('summary', '')}\n\n"
            "สนใจสอบถามราคาหรือรายละเอียดเพิ่ม ติดต่อทีมงานได้เลยค่ะ (พิมพ์ 'ติดต่อ')")


# ═══════════════════════════════════════════════════════════════════════
# handle_message — WRAPPER หลัก (A–F): จำเจตนา → lead / menu / track /
# greeting personalized / ambiguous → else เรียก _dispatch → log + profile
# ═══════════════════════════════════════════════════════════════════════
def handle_message(user_id: str, text: str, reply_token: str, group: bool = False) -> str:
    _clear_pending_image()  # เริ่มตอบใหม่ทุกครั้ง ไม่ให้ภาพเก่าติดไปกับคำตอบอื่น
    from app.chatbot_helpers import (detect_intent, detect_ambiguous, log_conversation,
                                     get_profile, save_profile, get_product_hint,
                                     save_lead, notify_sales_group, get_cached_faq_reply,
                                     record_faq_interaction, format_chatbot_reply)
    session = get_session(user_id)
    phase = session.get("phase", "new")
    intent = detect_intent(text)
    profile = get_profile(user_id)
    name_known = profile.get("name")

    def _finish(reply: str, resolved: bool = None, intent_used: str = intent,
                qr: list | None = None, faq_cacheable: bool | None = None):
        reply = format_chatbot_reply(reply)
        # A: จดจำประวัติสนทนา (ย้อนหลัง ~6 รอบ) — ให้ตอบต่อเนื่องเมื่อลูกค้าเปลี่ยนหัวข้อ
        # กระทันหันหรือถามย้อนกลับสิ่งที่เพิ่งคุย (คล้าย AI ที่จดจำ sessions ได้ดี)
        try:
            s = get_session(user_id)
            hist = list(s.get("history") or [])
            hist.append({"u": text, "b": reply})
            save_session(user_id, {**s, "history": hist[-6:]})
        except Exception:
            pass
        # ฝาก quick-reply suggestions ลง session ให้ main ดึงไป attach กับ reply (G)
        if qr:
            try:
                s = get_session(user_id)
                save_session(user_id, {**s, "_pending_qr": qr})
            except Exception:
                pass
        # B: log ทุกสนทนา
        try:
            log_conversation(user_id, text, reply, intent_used, resolved)
        except Exception:
            pass
        try:
            record_faq_interaction(text, reply, intent, cacheable=faq_cacheable)
        except Exception:
            pass
        return reply

    from app.assistant_policy import contains_prompt_injection, classify_urgency, INJECTION_REPLY, SAFETY_REPLY
    # Security and safety gates must run before any optional Gemini call.
    if contains_prompt_injection(text):
        return _finish(INJECTION_REPLY, intent_used="security_refusal")
    if classify_urgency(text) == "safety_critical":
        save_session(user_id, {"phase": "collecting", "fields": {"symptom": text, "urgency": "safety_critical"}})
        return _finish(SAFETY_REPLY, intent_used="safety_critical")

    # Contact/admin requests are a high-priority interrupt. Do this before
    # collecting fields so phrases such as "แอดมิน", "ติดต่อเรา", or a Rich
    # Menu contact action never get mistaken for a name/device/symptom.
    if _is_admin_contact_request(text):
        keep = {"last_product": session["last_product"], "history": session.get("history")} if session.get("last_product") else {"history": session.get("history")}
        save_session(user_id, {"phase": "new", "fields": {}, **keep})
        return _finish(_answer_admin_contact(), intent_used="admin_contact")

    # Clearly unrelated questions should receive a graceful hand-off even if
    # the user is currently midway through a repair or sales flow.
    if _is_out_of_scope(text):
        keep = {"last_product": session["last_product"], "history": session.get("history")} if session.get("last_product") else {"history": session.get("history")}
        save_session(user_id, {"phase": "new", "fields": {}, **keep})
        return _finish(_answer_out_of_scope(), intent_used="out_of_scope")

    # Reuse only stable product/service knowledge. Repair, lead, tracking, and
    # confirmation flows must always use the current user's session state.
    if (phase in ("new", "done") and not session.get("resolving")
            and not _is_product_followup(text)):
        cached = get_cached_faq_reply(text, intent)
        if cached:
            return _finish(cached, intent_used=f"faq_cached_{intent}")

    # Gemini classifier is opt-in. Keyword routing remains the stable default.
    from app.company_catalog import _fuzzy_product_names
    _has_product = bool(_fuzzy_product_names(text))
    if (ENABLE_GEMINI_CLASSIFIER and phase in ("new",) and intent in ("other", "service", "buy")
            and not _is_product_followup(text) and not _has_product):
        try:
            from app.gemini_service import classify_intent
            _gi = classify_intent(text)
            if _gi and _gi.get("confidence", 0) >= 0.6:
                _gintent = _gi.get("intent")
                if _gintent in ("repair", "buy", "product", "service", "company", "contact", "track", "human"):
                    intent = _gintent
        except Exception:
            pass

    # ── Gemini orchestration layer (opt-in): ให้ Gemini ตัดสินใจ+ร่างคำตอบธรรมชาติ
    # เฉพาะ phase ใหม่ + ข้อความปกติ (ไม่ใช่ flow เจาะจงที่ rule จัดการได้ดีอยู่แล้ว)
    # ถ้า Gemini ล่ม/429 → fallback ไป rule FSM เดิม (ปลอดภัย ไม่พัง)
    if (ENABLE_GEMINI_ORCHESTRATION and phase in ("new", "done")
            and intent in ("product", "service", "company", "greeting", "thanks", "other")
            and not _is_product_followup(text) and not _has_product):
        try:
            from app.gemini_service import gemini_orchestrate
            _gctx = {"phase": phase, "fields": session.get("fields", {}),
                     "name": profile.get("name") if profile else None,
                     "history": session.get("history")}
            _go = gemini_orchestrate(text, _gctx)
            if _go and _go.get("reply") and _go.get("confidence", 0) >= 0.6:
                action = _go.get("action")
                if action == "search_kb":
                    # ให้ค้น KB + แนะนำขั้นตอนจริง (แทนการตอบเฉยๆ) — fallback ไป rule FSM
                    from app.gemini_service import match_article, explain_steps
                    from app.kb_loader import load_kb_candidates
                    _db = SessionLocal()
                    try:
                        _cand = load_kb_candidates(_db)
                    finally:
                        _db.close()
                    _m = match_article(text, None, _cand)
                    if _m and _m.get("steps"):
                        _exp = explain_steps(text, _m["steps"], _m.get("device_type") or "")
                        if _exp:
                            return _finish(_exp, intent_used="orchestrate_search_kb")
                        _steps = "\n".join(f"{i+1}. {s}" for i, s in enumerate(_m["steps"][:6]))
                        return _finish(f"รับทราบนะคะ 🙏 ขอให้ลองทำตามนี้ก่อน ลองทีละขั้นดูค่ะ:\n{_steps}\n\n"
                                       "ถ้าทำแล้วไม่หาย พิมพ์ 'ยังไม่หาย' เดี๋ยวให้ช่างช่วยตรวจถึงที่ค่ะ",
                                       intent_used="orchestrate_search_kb")
                    # ไม่เจอ KB → ใช้คำตอบ Gemini เดิม + เสนอแจ้งซ่อม
                    return _finish(_go["reply"] + "\n\nถ้ายังแก้ไม่ได้ พิมพ์ 'แจ้งซ่อม' ได้เลยนะคะ",
                                   intent_used="orchestrate_search_kb_nokb")
                # เฉพาะ action ปลอดภัย: answer/ask_info (ไม่ override การสร้าง ticket/ซ่อม)
                if action in ("answer", "ask_info"):
                    return _finish(_go["reply"], intent_used=f"orchestrate_{action}")
        except Exception:
            pass

    # ── TRACK_PENDING: อยู่ระหว่างรอเลข ticket — ข้อความถัดไปเป็นเลข/รหัส → ตอบสถานะ ──
    if phase == "track_pending":
        return _finish(_answer_track(user_id, text), intent_used="track")

    # ── LEAD FLOW (E): ระหว่างเก็บข้อมูล lead (ซื้อสินค้า) ──
    if phase == "lead_collect":
        lead = session.get("lead", {}) or {}
        t = (text or "").strip()
        now = time.time()

        # 2) ยกเลิก lead flow → clear session, ตอบสุภาพ
        if any(k in t for k in ["ยกเลิก", "ไม่เอาแล้ว", "ไม่เอาละ", "ไม่เอา", "ลืม", "เลิก"]):
            clear_session(user_id)
            return _finish("ไม่เป็นไรค่ะ 🙏 ยกเลิกได้เลยนะคะ "
                           "ถ้าอยากทราบข้อมูลอีกครั้ง กลับมาพิมพ์ชื่อสินค้าได้เสมอเลยค่ะ 😊",
                           intent_used="lead_cancel")

        # 1) แก้ไข / แก → reset เก็บใหม่ (ล้าง name/phone) ถามชื่อใหม่
        if "แก้ไข" in t or t == "แก้":
            lead = {"name": "", "phone": "", "interest": lead.get("interest"),
                    "products": lead.get("products", []), "_ts": now,
                    "human": lead.get("human")}
            save_session(user_id, {**session, "phase": "lead_collect", "lead": lead})
            return _finish("ได้ค่ะ 🙆 เริ่มเก็บข้อมูลใหม่ให้เลย ขอ **ชื่อของคุณ** อีกครั้งนะคะ",
                           intent_used="lead_edit")

        # 5) timeout — lead ค้างนานเกิน 10 นาที → เริ่มใหม่
        try:
            lead_ts = float(lead.get("_ts") or now)
        except (TypeError, ValueError):
            lead_ts = now
        if not lead.get("_ts"):
            lead["_ts"] = now
        elif now - lead_ts > 600:
            lead = {"name": "", "phone": "", "interest": lead.get("interest"),
                    "products": lead.get("products", []), "_ts": now}
            save_session(user_id, {**session, "phase": "lead_collect", "lead": lead})
            return _finish("⏰ ห่างกันไปนานเลยนะคะ เดี๋ยวขอเริ่มเก็บข้อมูลใหม่ให้ค่ะ "
                           "**ชื่อของคุณ** คืออะไรคะ?",
                           intent_used="lead_timeout")

        # 3/4) ดึงเบอร์จากข้อความนี้ถ้ามี (รองรับพิมพ์ชื่อ+เบอร์รอบเดียว, หรือเบอร์ตรงๆ)
        phone_in_msg = None
        _m = re.search(r"0[0-9]{8,9}", t)
        if _m:
            phone_in_msg = _m.group(0)

        name = lead.get("name")
        phone = lead.get("phone")

        # ยังไม่มีชื่อ → เก็บชื่อ (ตัดเบอร์ออกถ้าพิมปนกัน) → ต่อมาถามเบอร์
        if not name:
            nm = _extract_name(t)
            if not nm:
                return _finish("รับทราบค่ะ ขอ **ชื่อของคุณ** ก่อนนะคะ 😊")
            lead["name"] = nm
            if phone_in_msg and not phone:
                lead["phone"] = phone_in_msg
        # ยังไม่มีเบอร์ → เก็บเบอร์ (พิมพ์เบอร์ตรง / เบอร์ปนมา)
        elif not phone:
            if phone_in_msg:
                lead["phone"] = phone_in_msg
            elif re.fullmatch(r"0\d{9}", t.replace(" ", "")):
                lead["phone"] = t.replace(" ", "")
            else:
                save_session(user_id, {**session, "phase": "lead_collect", "lead": lead})
                return _finish("ขอบคุณนะคะ ขอ **เบอร์โทร** ไว้ติดต่อกลับด้วยนะคะ 😊")
        # ครบชื่อ+เบอร์ → ถามยืนยัน
        elif not lead.get("confirm"):
            if _is_affirmative(t):
                lead["confirm"] = True
        # else: ครบแล้วแต่ยังตอบซ้ำ → ถามยืนยันต่อไป

        # ── เก็บครบ + ยืนยัน → สร้าง lead (เช็คซ้ำก่อน) ──
        if lead.get("confirm") and lead.get("name") and lead.get("phone"):
            # 6) เช็ค lead ซ้ำ (ชื่อ+เบอร์เคยส่งไปแล้ว) → ไม่สร้างซ้ำ
            if _lead_duplicate_exists(lead.get("name"), lead.get("phone")):
                clear_session(user_id)
                return _finish("เราเคยรับข้อมูลของคุณไว้แล้วค่ะ 🙏 ทีมจะติดต่อกลับนะคะ",
                               intent_used="lead_dup")
            lid = save_lead(user_id, lead.get("name"), lead.get("phone"),
                            lead.get("interest"), lead.get("products", []))
            if lid is None:
                save_session(user_id, {**session, "phase": "lead_collect", "lead": lead})
                return _finish("ขออภัยค่ะ ระบบยังบันทึกข้อมูลติดต่อไม่ได้ชั่วคราว 🙏 "
                               "กรุณาพิมพ์ **ยืนยัน** อีกครั้ง หรือติดต่อทีมงานโดยตรงนะคะ",
                               intent_used="lead_save_failed")
            notify_sales_group(lid, lead.get("name"), lead.get("phone"),
                               lead.get("interest"), ", ".join(lead.get("products", [])),
                               human=bool(lead.get("human")))
            save_profile(user_id, {"name": lead.get("name"), "phone": lead.get("phone"),
                                   "interested": lead.get("interest")})
            clear_session(user_id)
            return _finish("✅ ขอบคุณมากนะคะ! ทีมขายจะรีบติดต่อกลับภายในเวลาทำการเลย 🙏\n"
                           "ยังมีเรื่องอื่นให้ช่วยอีกไหมคะ? พิมพ์ 'สินค้า' 'แจ้งซ่อม' หรือ 'เมนู' ได้เลยนะคะ",
                           intent_used="lead_confirm")

        # ── ยังไม่จบ → เซฟความคืบหน้า แล้วถามขั้นตอนถัดไป ──
        save_session(user_id, {**session, "phase": "lead_collect", "lead": lead, "_ts": lead.get("_ts")})
        if lead.get("name") and lead.get("phone") and not lead.get("confirm"):
            return _finish("ขอสรุปข้อมูลให้ดูอีกครั้งนะคะ 🙏\n"
                           f"• ชื่อ: {lead.get('name')}\n• เบอร์: {lead.get('phone')}\n"
                           f"• สนใจ: {lead.get('interest','-')}\n\n"
                           "ยืนยันให้ทีมขายติดต่อกลับไหมคะ? พิมพ์ **ยืนยัน** หรือ **แก้ไข** ได้เลยนะคะ")
        if not lead.get("phone"):
            return _finish("ขอบคุณนะคะ ขอ **เบอร์โทร** ไว้ติดต่อกลับด้วยนะคะ 😊")
        return _finish("สรุปข้อมูล:\n"
                       f"• ชื่อ: {lead.get('name')}\n• เบอร์: {lead.get('phone')}\n"
                       f"• สนใจ: {lead.get('interest','-')}\n\n"
                       "ยืนยันให้ทีมขายติดต่อกลับไหม? (พิมพ์ **ยืนยัน** / **แก้ไข**)")

    # ── เริ่ม LEAD (เจตนา buy / สนใจซื้อ) ──
    if intent == "buy" and phase not in ("collecting", "confirm"):
        hint = get_product_hint(intent, text)
        # บันทึก product ที่สนใจลง profile (F)
        if hint:
            save_profile(user_id, {"interested": hint[0], "last_seen": hint[:3]})
        save_session(user_id, {"phase": "lead_collect",
                               "lead": {"name": "", "phone": "", "interest": text,
                                        "products": hint, "_ts": time.time()}})
        if hint:
            return _finish(f"🛍️ คุณสนใจ **{', '.join(hint)}** ใช่ไหมคะ?\n"
                           "ขอ **ชื่อ-นามสกุล** เพื่อให้ทีมขายติดต่อกลับพร้อมรายละเอียดราคานะคะ 😊",
                           intent_used="buy")
        return _finish("ขอบคุณที่สนใจสินค้าของเราค่ะ 🛍️ ขอ **ชื่อของคุณ** เพื่อให้ทีมขายติดต่อกลับพร้อมรายละเอียดนะคะ",
                       intent_used="buy")

    # ── HUMAN: ลูกค้าอยากคุยกับคนจริง → เก็บชื่อ/เบอร์ แล้วแจ้งทีมใน LINE group (วิธีที่เลือก) ──
    if intent == "human" and phase not in ("collecting", "confirm", "lead_collect"):
        save_session(user_id, {"phase": "lead_collect",
                               "lead": {"name": "", "phone": "", "interest": text,
                                        "products": [], "human": True, "_ts": time.time()}})
        return _finish("ได้เลยค่ะ 🙋 เดี๋ยวจะให้เจ้าหน้าที่ติดต่อกลับโดยเร็วที่สุดเลย\n"
                       "ขอ **ชื่อของคุณ** ก่อนนะคะ", intent_used="human")

    # ── GREETING personalized (F) ──
    if intent == "greeting":
        greet = f"สวัสดีค่ะ คุณ{name_known} 👋" if name_known else "สวัสดีค่ะ 👋"
        return _finish(greet + " วันนี้มีอะไรให้ช่วยไหมคะ? 😊\n"
                       "🛍️ อยากดูสินค้า/บริการ พิมพ์ 'สินค้า' หรือชื่อสินค้า เช่น 'Iwa AiBoard' 'หลักสูตรภาษาอังกฤษ'\n"
                       "🔧 เจอปัญหาอุปกรณ์ พิมพ์ 'แจ้งซ่อม' หรือบอกอาการ เช่น 'จอไม่ติด'\n"
                       "📞 สนใจติดต่อทีมงาน พิมพ์ 'ติดต่อ' ได้เลยนะคะ",
                       intent_used="greeting",
                       qr=["ดูสินค้า", "บริการ", "แจ้งซ่อม", "ติดต่อ"])

    # ── THANKS ──
    if intent == "thanks":
        return _finish("ด้วยความยินดีค่ะ 😊 ถ้ามีเรื่องอื่นให้ช่วยอีก พิมพ์ 'สินค้า' 'แจ้งซ่อม' หรือ 'ติดต่อ' ได้เลยนะคะ",
                       intent_used="thanks")

    # ── AMBIGUOUS (C): ซ่อม vs ซื้อ กำกวม → ถามให้ชัด ──
    if intent == "ambiguous":
        return _finish("ขอเช็คให้ชัดเจนอีกนิดนะคะ 😊 เรื่องที่พูดถึงหมายถึงแบบไหนคะ:\n"
                       "🔧 ต้องการ **แจ้งซ่อม** อุปกรณ์เดิมที่ใช้งานอยู่?\n"
                       "🛍️ หรือสนใจ **ซื้อสินค้า/สอบถามราคา** ใหม่?\n"
                       "พิมพ์ 'แจ้งซ่อม' หรือ 'ซื้อ' ตามที่ตรงกับคุณเลยนะคะ",
                       intent_used="ambiguous", qr=["แจ้งซ่อม", "ซื้อสินค้า"])

    # ── TRACK (ติดตามสถานะ ticket) — ดึงสถานะจริงจาก DB ──
    if intent == "track":
        return _finish(_answer_track(user_id, text), intent_used="track")

    # ── MENU ──
    if intent == "other" and any(k in text.lower() for k in ["เมนู", "menu", "ช่วยอะไร", "ทำอะไรได้"]):
        return _finish("นี่คือสิ่งที่ฉันช่วยได้นะคะ 📋\n"
                       "🛍️ 'สินค้า' — ดูหมวดสินค้า/บริการ\n"
                       "💬 พิมพ์ชื่อสินค้า เช่น 'Iwa AiBoard 86' 'Smart Quiz' 'Phonics Hero'\n"
                       "📦 'บริการ' — ดูบริการของบริษัท\n"
                       "🔧 'แจ้งซ่อม' — แจ้งปัญหาอุปกรณ์\n"
                       "📞 'ติดต่อ' — ช่องทางติดต่อทีมงาน\n\n"
                       "อยากทำเรื่องไหน พิมพ์บอกได้เลยนะคะ 😊", intent_used="menu")

    # ── ELSE → เรียก logic เดิม (แจ้งซ่อม/สินค้า) ──
    reply = _dispatch(user_id, text, reply_token, group)
    # F: จดชื่อ/เบอร์จากระหว่างเก็บข้อมูลแจ้งซ่อม
    if profile is not None:
        try:
            sess = get_session(user_id)
            flds = sess.get("fields", {})
            if flds.get("name") or flds.get("phone"):
                save_profile(user_id, {"name": flds.get("name"), "phone": flds.get("phone")})
        except Exception:
            pass
    return _finish(reply, intent_used=intent)


def _extract_name(text: str) -> str | None:
    """ดึงชื่อจากข้อความ (ตัดเบอร์/คำที่ไม่ใช่ชื่อ)"""
    t = text.strip()
    if not t or len(t) > 60:
        return None
    # ตัดเบอร์ออก
    t2 = re.sub(r"0[0-9]{8,9}", "", t).strip(" ,;:") 
    return t2 if 2 <= len(t2) <= 60 else None


def _lead_duplicate_exists(name: str, phone: str) -> bool:
    """เช็คว่าเคยมี lead (sales_leads) ที่มีชื่อ+เบอร์นี้แล้วหรือยัง"""
    if not phone:
        return False
    db = SessionLocal()
    try:
        row = db.execute(
            text("SELECT 1 FROM sales_leads WHERE phone=:p AND name=:n LIMIT 1"),
            {"p": phone, "n": name},
        ).fetchone()
        return row is not None
    except Exception:
        return False
    finally:
        db.close()


# สถานะ ticket → ไทย (map จาก ticket_status_enum)
_TICKET_STATUS_TH = {
    "new": "🆕 รับแจ้งแล้ว (รอเจ้าหน้าที่รับงาน)",
    "assigned": "👷 รับงานแล้ว",
    "in_progress": "🔧 กำลังซ่อมอยู่",
    "pending": "⏳ รออะไหล่/รอผู้ใช้",
    "resolved": "✅ ซ่อมเสร็จแล้ว",
    "closed": "🔒 ปิดงานแล้ว",
    "cancelled": "❌ ยกเลิก",
}

def _answer_track(user_id: str, user_msg: str) -> str:
    """ติดตามสถานะจาก ticket_id หรือ device_id โดยอ่านจาก DB จริง"""
    sess = get_session(user_id)
    ticket_match = re.search(r"(TK[-_]?\d{4,6}[-_]?\d{1,6}|SC[-_]\d{4,6}[-_]\d{1,6})", user_msg, re.IGNORECASE)
    device_match = re.search(r"\b(?:TEST|DEV|SCH|ROOM)[A-Z0-9_-]*\d+\b", user_msg, re.IGNORECASE)
    db = SessionLocal()
    try:
        row = None
        lookup_label = ""
        if ticket_match:
            lookup_label = ticket_match.group(0)
            row = db.execute(text(
                "SELECT ticket_id, title, status, device_id, reporter_name, created_at, assigned_to "
                "FROM repair_tickets WHERE ticket_id ILIKE :t"), {"t": lookup_label}).mappings().first()
            if not row:
                save_session(user_id, {**sess, "phase": "new", "track_pending": False})
                return f"ไม่พบ Ticket **{lookup_label}** ในระบบนะคะ ลองเช็คเลขให้ถูกต้อง หรือพิมพ์ 'แจ้งซ่อม' เพื่อสร้างใหม่ค่ะ"
        elif device_match:
            lookup_label = device_match.group(0)
            row = db.execute(text(
                "SELECT ticket_id, title, status, device_id, reporter_name, created_at, assigned_to "
                "FROM repair_tickets WHERE device_id ILIKE :d ORDER BY created_at DESC LIMIT 1"),
                {"d": lookup_label}).mappings().first()
            if not row:
                save_session(user_id, {**sess, "phase": "new", "track_pending": False})
                return f"ยังไม่พบงานซ่อมของอุปกรณ์ **{lookup_label}** ในระบบนะคะ"
        else:
            if sess.get("track_pending"):
                return "กรุณาพิมพ์ **เลข Ticket** หรือรหัสอุปกรณ์ เช่น SC-2026-000001 / TEST1-00001 ค่ะ"
            save_session(user_id, {**sess, "phase": "track_pending", "track_pending": True})
            return "📋 อยากเช็คสถานะงานใช่ไหมคะ? กรุณาพิมพ์ **เลข Ticket** หรือ **รหัสอุปกรณ์** แล้วส่งมาได้เลยค่ะ"

        save_session(user_id, {**sess, "phase": "new", "track_pending": False})
        status = row["status"]
        label = _TICKET_STATUS_TH.get(status, status)
        if status == "assigned" and row["assigned_to"]:
            label = f"👷 รับงานแล้ว โดย {row['assigned_to']}"
        return (f"📋 **{row['ticket_id']}**\n"
                f"เรื่อง: {row['title']}\n"
                f"อุปกรณ์: {row['device_id'] or '-'}\n"
                f"สถานะ: {label}\n"
                f"แจ้งเมื่อ: {str(row['created_at'])[:16]}\n\n"
                "มีเรื่องอื่นให้ช่วยไหมคะ? พิมพ์ 'สินค้า' หรือ 'แจ้งซ่อม' ได้เลย")
    finally:
        db.close()
