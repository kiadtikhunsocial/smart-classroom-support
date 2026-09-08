"""
chatbot_helpers.py — ฟังก์ชันช่วยเสริม LINE chatbot (A–F)
  A. intent ละเอียด (ซ่อม/สินค้า/บริการ/ติดต่อ/ซื้อ/ทักทาย/กำกวม)
  B. log ทุกสนทนาลง chatbot_logs
  E. บันทึก lead + แจ้งทีมขาย (sales_leads)
  F. profile/ความจำลูกค้า (จำชื่อ/สินค้าที่เคยกดดู จาก userId)
"""
import json
import re
from datetime import datetime

from sqlalchemy import text
from app.models import SessionLocal
from app.company_catalog import ALL_PRODUCTS

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
        # buy ชนะ product (อยากซื้อ X)
        if any(k in t for k in INTENTS["buy"]):
            return "buy"
        if prod_hit:
            return "product"
    # ไล่เจตนาที่เจาะจงก่อน
    for key in ["greeting", "thanks", "repair", "buy", "human", "contact", "company", "catalog", "service", "track"]:
        if any(k in t for k in INTENTS[key]):
            return key
    if prod_hit:
        return "product"
    return "other"


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
        row = db.execute(
            text("SELECT profile FROM chatbot_profiles WHERE user_id=:u"), {"u": user_id}
        ).fetchone()
        if row and row[0]:
            val = row[0]
            return val if isinstance(val, dict) else json.loads(val)
        # ไม่มี → สร้างแถวเปล่า
        db.execute(text("INSERT INTO chatbot_profiles (user_id, profile, updated_at) "
                        "VALUES (:u,'{}'::jsonb,:t) ON CONFLICT (user_id) DO NOTHING"),
                   {"u": user_id, "t": datetime.now()})
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()
    return {}


def save_profile(user_id: str, patch: dict):
    """อัปเดต/merge profile ของ user"""
    db = SessionLocal()
    try:
        cur = get_profile(user_id)
        cur.update({k: v for k, v in patch.items() if v})
        db.execute(
            text("INSERT INTO chatbot_profiles (user_id, profile, updated_at) VALUES (:u,:p,:t) "
                 "ON CONFLICT (user_id) DO UPDATE SET profile=:p, updated_at=:t"),
            {"u": user_id, "p": json.dumps(cur, ensure_ascii=False), "t": datetime.now()},
        )
        db.commit()
    except Exception:
        db.rollback()
    finally:
        db.close()


def get_product_hint(intent: str, text: str) -> list:
    """ดึงชื่อสินค้าที่พูดถึงในข้อความ (สำหรับบันทึก lead/product)"""
    t = text.lower()
    return [p["name"] for p in ALL_PRODUCTS if any(tag in t for tag in p["tags"])][:3]
