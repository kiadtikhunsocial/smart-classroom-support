"""
chatbot_helpers.py — ฟังก์ชันช่วยเสริม LINE chatbot (A–F)
  A. intent ละเอียด (ซ่อม/สินค้า/บริการ/ติดต่อ/ซื้อ/ทักทาย/กำกวม)
  B. log ทุกสนทนาลง chatbot_logs
  E. บันทึก lead + แจ้งทีมขาย (sales_leads)
  F. profile/ความจำลูกค้า (จำชื่อ/สินค้าที่เคยกดดู จาก userId)
"""
import hashlib
import json
import logging
import os
import re
import unicodedata
from datetime import datetime, timezone

from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from app.models import ChatbotFAQ, ChatbotProfile, SessionLocal
from app.company_catalog import ALL_PRODUCTS


logger = logging.getLogger(__name__)

try:
    FAQ_CACHE_TTL_SECONDS = max(0, int(os.environ.get("FAQ_CACHE_TTL_SECONDS", "604800")))
except (TypeError, ValueError):
    FAQ_CACHE_TTL_SECONDS = 604800

# Only stable knowledge answers are replayed from this table. Repair, lead,
# tracking, and confirmation replies contain user/session-specific data.
FAQ_CACHEABLE_INTENTS = {"product", "buy", "service", "company", "catalog"}

# ── เจตนา (finer than business/repair) ──
INTENTS = {
    "greeting": ["สวัสดี", "hello", "hi", "ทัก", "ดีจ้า", "หวัดดี", "สวัสดีค่ะ", "good morning", "good afternoon"],
    "thanks": ["ขอบคุณ", "thank", "thanks", "ok ขอบคุณ", "ขอบใจ", "thanks มาก"],
    "repair": ["แจ้งซ่อม", "ซ่อม", "ช่าง", "พัง", "เสีย", "ไม่ติด", "ไม่ทำงาน", "มีปัญหา", "ไม่เปิด",
               "ไม่มีภาพ", "ไม่มีเสียง", "ค้าง", "จอดำ", "เข้าไม่ได้", "หลุด", "error", "อาการ",
               "ไม่ขึ้น", "ไม่ได้ยิน", "หน้าจอดำ", "ช่วยแก้", "ช่วยดู", "ช่วยหน่อย"],
    "buy": ["ซื้อ", "สั่งซื้อ", "สั่ง", "ราคา", "โปรโมชั่น", "โปร", "ขอราคา", "quote", "quo",
            "ใบเสนอราคา", "quotation", "สนใจซื้อ", "อยากได้", "จัดซื้อ", "ขาย"],
    "contact": ["ติดต่อ", "ที่อยู่", "address", "เบอร์", "โทร", "line id", "อีเมล", "email", "ช่องทาง",
                "แมสเซนเจอร์", "แอดไลน์", "เลขบัญชี"],
    "human": ["คุยกับคน", "คุยกับพนักงาน", "คุยกับเจ้าหน้าที่", "พนักงานขาย", "เจ้าหน้าที่", "คนจริง",
              "มนุษย์", "ตัวแทน", "sales rep", "อยากคุย", "ขอคุย", "ติดต่อเจ้าหน้าที่", "ติดต่อพนักงาน",
              "พูดกับคน", "แอดไลน์ทีม", "ทีมงาน", "consultant", "ที่ปรึกษา", "เจ้าหน้าที่ติดต่อ"],
    "company": ["บริษัท", "company", "เกี่ยวกับ", "about", "ประวัติ", "iwa", "rich you", "คือใคร"],
    "catalog": ["สินค้า", "มีอะไร", "แคตตาล็อก", "catalog", "รายการ", "product", "มีอะไรบ้าง"],
    "service": ["บริการ", "service", "โซลูชัน", "อบรม", "training", "สัมมนา", "seminar", "ติดตั้งระบบ"],
    "track": ["สถานะ", "ติดตาม", "ticket", "งานถึงไหน", "ตรวจสอบงาน", "เลขที่"],
}

# กำกวม: มีทั้งคำซ่อมและคำซื้อปนในประโยคเดียว
_AMBIG = [(r"จอ.*(เสีย|พัง|ไม่ติด|ไม่ทำงาน)", r"(ซื้อ|อยากได้|ราคา|ใหม่)"),
          (r"(เสีย|พัง|มีปัญหา)", r"(ซื้อ|อยากได้|ราคา|ใหม่)")]


def detect_ambiguous(text: str) -> bool:
    t = text.lower()
    for pat_a, pat_b in _AMBIG:
        if re.search(pat_a, t) and re.search(pat_b, t):
            return True
    return False


def detect_intent(text: str) -> str:
    """คืนเจตนาหลัก: greeting|thanks|repair|buy|contact|company|catalog|service|track|product|other"""
    t = text.strip().lower()
    if detect_ambiguous(t):
        return "ambiguous"
    # ชื่อสินค้าจริงในข้อความ (ยกเว้นคำซื้อชัดเจนให้เป็น buy ก่อน)
    prod_hit = [p for p in ALL_PRODUCTS if any(tag in t for tag in p["tags"])]
    if not any(w in t for w in INTENTS["repair"]):
        # เจอชื่อสินค้าเจาะจง → product (ตอบข้อมูล+ราคาใน LINE ทันที)
        # อย่าให้คำว่า "ราคา/ซื้อ" เบี่ยงไป flow เก็บชื่อก่อน ทั้งที่ลูกค้าแค่ถามราคา
        if prod_hit:
            return "product"
        if any(k in t for k in INTENTS["buy"]):
            return "buy"
    # ไล่เจตนาที่เจาะจงก่อน
    for key in ["greeting", "thanks", "repair", "buy", "human", "contact", "company", "catalog", "service", "track"]:
        if any(k in t for k in INTENTS[key]):
            return key
    if prod_hit:
        return "product"
    return "other"


def normalize_question(message: str) -> str:
    """สร้างรูปแบบกลางของคำถาม เพื่อรวมคำถามซ้ำที่ต่างกันแค่คำสุภาพ/วรรคตอน"""
    value = unicodedata.normalize("NFKC", str(message or "")).casefold()
    value = value.translate(str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789"))
    value = value.replace("เท่าไร", "เท่าไหร่")
    value = re.sub(r"[^\wก-๙\s]", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    value = re.sub(r"^(ขอสอบถาม|รบกวนสอบถาม|ขอทราบ|อยากทราบ)\s+", "", value)
    for _ in range(2):
        value = re.sub(r"(?:นะคะ|นะครับ|ครับ|ค่ะ|คะ|นะ|หน่อย|ด้วย|ที)$", "", value).strip()
    return value


def _question_key(normalized_question: str) -> str:
    return hashlib.sha256(normalized_question.encode("utf-8")).hexdigest()


def format_chatbot_reply(reply: str) -> str:
    """จัดรูปแบบคำตอบกลางให้ทุกช่องทางส่งข้อความที่อ่านง่ายสม่ำเสมอ

    LINE text messages do not render Markdown, so emphasis markers are
    removed and list/spacing conventions are normalized here.
    """
    value = str(reply or "").replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"\*\*(.*?)\*\*", r"\1", value, flags=re.DOTALL)
    value = re.sub(r"(?m)^[ \t]*[-*]\s+", "• ", value)
    value = re.sub(r"(?m)^(\s*)(\d+)[)]\s+", r"\1\2. ", value)
    value = re.sub(r"[ \t]+([,،.!?])", r"\1", value)
    value = re.sub(r"[ \t]+\n", "\n", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    value = re.sub(r"[ \t]{2,}", " ", value)
    return value.strip()[:5000]


def get_cached_faq_reply(message: str, intent: str | None = None) -> str | None:
    """คืนคำตอบมาตรฐานของคำถามซ้ำ ถ้าเป็น intent ที่ปลอดภัยและยังไม่หมดอายุ"""
    if intent not in FAQ_CACHEABLE_INTENTS:
        return None
    normalized = normalize_question(message)
    if not normalized:
        return None
    db = SessionLocal()
    try:
        row = db.get(ChatbotFAQ, _question_key(normalized))
        if not row or not row.answer:
            return None
        if FAQ_CACHE_TTL_SECONDS:
            last_seen = row.last_seen
            if last_seen and last_seen.tzinfo is None:
                last_seen = last_seen.replace(tzinfo=timezone.utc)
            if last_seen and (datetime.now(timezone.utc) - last_seen).total_seconds() > FAQ_CACHE_TTL_SECONDS:
                return None
        return format_chatbot_reply(row.answer)
    except Exception:
        logger.exception("Could not read chatbot FAQ cache")
        return None
    finally:
        db.close()


def record_faq_interaction(message: str, reply: str, intent: str,
                           cacheable: bool | None = None) -> None:
    """บันทึกคำถามทุกประเภทและเพิ่ม hit_count เมื่อเจอคำถามซ้ำ"""
    normalized = normalize_question(message)
    if not normalized:
        return
    now = datetime.now(timezone.utc)
    answer = format_chatbot_reply(reply)
    should_cache = cacheable if cacheable is not None else intent in FAQ_CACHEABLE_INTENTS
    key = _question_key(normalized)
    db = SessionLocal()
    try:
        row = db.get(ChatbotFAQ, key)
        if row:
            row.hit_count = int(row.hit_count or 0) + 1
            row.last_seen = now
            # Keep the latest deterministic answer for stable knowledge intents.
            if should_cache and answer:
                row.answer = answer
                row.intent = intent
        else:
            db.add(ChatbotFAQ(
                question_key=key,
                normalized_question=normalized[:2000],
                sample_question=str(message or "")[:500],
                answer=answer[:5000] if should_cache and answer else None,
                intent=intent,
                hit_count=1,
                created_at=now,
                last_seen=now,
            ))
        db.commit()
    except IntegrityError:
        # Two different users may ask the same question at the same time.
        # Recover the insert race and count the interaction instead of losing it.
        db.rollback()
        try:
            row = db.get(ChatbotFAQ, key)
            if row:
                row.hit_count = int(row.hit_count or 0) + 1
                row.last_seen = now
                if should_cache and answer:
                    row.answer = answer
                    row.intent = intent
                db.commit()
        except Exception:
            db.rollback()
            logger.exception("Could not recover chatbot FAQ insert race")
    except Exception:
        db.rollback()
        logger.exception("Could not record chatbot FAQ interaction")
    finally:
        db.close()


# ═══════════════════ B. Log สนทนา ═══════════════════
def log_conversation(user_id: str, message: str, reply: str, intent: str, resolved: bool = None):
    """บันทึกข้อความ+คำตอบ+เจตนา ลง chatbot_logs (ล้มไม่เป็นไร ไม่บล็อก)"""
    db = SessionLocal()
    try:
        db.execute(
            text("INSERT INTO chatbot_logs (user_id, message, ai_response, intent, resolved, created_at) "
                 "VALUES (:u,:m,:r,:i,:res,:t)"),
            {"u": user_id, "m": message, "r": reply[:2000], "i": intent,
             "res": bool(resolved), "t": datetime.now()},
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


# ═══════════════════ E. Lead + แจ้งทีมขาย ═══════════════════
def save_lead(user_id: str, name: str, phone: str, interest: str, product_names: list,
              note: str = "") -> int | None:
    """บันทึก sales lead ลง sales_leads → คืน id (หรือ None)"""
    db = SessionLocal()
    try:
        res = db.execute(
            text("INSERT INTO sales_leads (user_id,name,phone,interest,products,note,source,status,created_at) "
                 "VALUES (:u,:n,:p,:i,:pr,:note,'LINE','new',:t) RETURNING id"),
            {"u": user_id, "n": name, "p": phone, "i": interest[:200],
             "pr": ", ".join(product_names)[:500], "note": note[:500], "t": datetime.now()},
        )
        db.commit()
        row = res.fetchone()
        return row[0] if row else None
    except Exception:
        db.rollback()
        return None
    finally:
        db.close()


def notify_sales_group(lead_id: int, name: str, phone: str, interest: str, products: str,
                       human: bool = False):
    """Push ข้อความแจ้งทีมขาย (LINE group) ว่ามี lead ใหม่ (human=True → ต้องการคุยกับคนจริง)"""
    try:
        from app.line_bot import send_line_push, LINE_GROUP_ID as GID
    except Exception:
        return
    header = "🙋 **ต้องการคุยกับเจ้าหน้าที่**" if human else f"💼 **Lead ใหม่ #{lead_id}**"
    msg = (f"{header}\n"
           f"ชื่อ: {name or '-'}\nเบอร์: {phone or '-'}\n"
           f"สนใจ: {interest or '-'}\nสินค้า: {products or '-'}\n"
           f"ช่องทาง: LINE\nติดต่อกลับด่วนค่ะ")
    if GID:
        send_line_push(GID, msg)


# ═══════════════════ F. Profile / ความจำลูกค้า ═══════════════════
def get_profile(user_id: str) -> dict:
    """ดึง profile ลูกค้าจากตาราง chatbot_profiles (สร้างให้ถ้าไม่เคย)"""
    db = SessionLocal()
    try:
        row = db.get(ChatbotProfile, user_id)
        if row:
            # แถวมีอยู่แล้ว — profile อาจว่าง ({}) ได้ ห้าม INSERT ซ้ำ (ชน primary key)
            val = row.profile
            if isinstance(val, dict):
                return dict(val)
            parsed = json.loads(val) if val else {}
            return parsed if isinstance(parsed, dict) else {}
        # ยังไม่มีแถว → สร้างแถวเปล่า; ถ้าชนกันเพราะ request พร้อมกัน ให้ถือว่าสำเร็จ
        try:
            db.add(ChatbotProfile(
                user_id=user_id,
                profile={},
                updated_at=datetime.now(timezone.utc),
            ))
            db.commit()
        except IntegrityError:
            db.rollback()
    except Exception:
        db.rollback()
        logger.exception("Could not read/create chatbot profile for user %s", user_id)
    finally:
        db.close()
    return {}


def save_profile(user_id: str, patch: dict):
    """อัปเดต/merge profile ของ user"""
    db = SessionLocal()
    try:
        row = db.get(ChatbotProfile, user_id)
        current = row.profile if row and row.profile else {}
        if not isinstance(current, dict):
            current = json.loads(current)
        cur = dict(current) if isinstance(current, dict) else {}
        cur.update({k: v for k, v in patch.items() if v})
        if row:
            row.profile = cur
            row.updated_at = datetime.now(timezone.utc)
        else:
            db.add(ChatbotProfile(
                user_id=user_id,
                profile=cur,
                updated_at=datetime.now(timezone.utc),
            ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("Could not save chatbot profile for user %s", user_id)
    finally:
        db.close()


def get_product_hint(intent: str, text: str) -> list:
    """ดึงชื่อสินค้าที่พูดถึงในข้อความ (สำหรับบันทึก lead/product)"""
    t = text.lower()
    return [p["name"] for p in ALL_PRODUCTS if any(tag in t for tag in p["tags"])][:3]
