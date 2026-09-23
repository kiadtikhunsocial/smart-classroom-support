"""
chatbot_nlu.py — ชั้น "เข้าใจข้อความ" ของแชทบอท (rule-based ล้วน ไม่พึ่ง LLM)

ทำไมต้องมีไฟล์นี้
-----------------
chatbot_core เดิมตัดสินเจตนาด้วย `คำ in ข้อความ` ตรง ๆ ภาษาไทยไม่มีช่องว่างระหว่างคำ
คำสั้นจึงไปโผล่กลางคำอื่นและทำให้บอทตอบผิดเรื่อง (อาการ "ตอบไม่ตรงประเด็น"):

  • "อากาศ" อยู่ใน "เครื่องปรับอากาศไม่เย็น" → แจ้งซ่อมแอร์ กลายเป็น "ถามพยากรณ์อากาศ"
  • "หนัง"  อยู่ใน "หนังสือเรียน"            → ถามสินค้า กลายเป็น "ถามหนัง/ภาพยนตร์"
  • "เกม"   อยู่ใน "เกมการศึกษา"             → ถามสื่อการเรียน กลายเป็น "ถามเรื่องเกม"
  • "เพลง"  อยู่ใน "เพลงเด็กปฐมวัย"          → เช่นเดียวกัน
  • "ทีมงาน"/"ติดต่อ" ใน "รอทีมงานติดต่อกลับอยู่" → ตอบช่องทางติดต่อซ้ำ แทนเรื่องที่ค้าง
  • "ติดต่อ" ใน "งาน T0001 ถึงไหนแล้ว ติดต่อไม่ได้" → ตอบเบอร์โทร แทนสถานะงาน

หลักการที่ใช้แก้
----------------
1. normalize ก่อนเทียบ  — ตัดคำลงท้ายสุภาพ, แก้ "เเ"→"แ", ยุบตัวอักษรซ้ำ ("ไม่ติดดดด")
2. guard word          — คำหนึ่งจะนับเฉพาะเมื่อ "ไม่ได้" เป็นส่วนของวลีที่ความหมายต่าง
3. veto ด้วยสัญญาณธุรกิจ — ถ้าข้อความมีสัญญาณซ่อม/สินค้า/ติดตามงาน ห้ามตีเป็นนอกขอบเขต
4. ให้คะแนนหลายเจตนา   — เจตนาเสมอกัน = กำกวมจริง ให้ถามกลับ 1 คำถามที่เจาะจง
                          (แทนการโปะเมนูยาว ๆ ซึ่งคือต้นเหตุอาการ "ตอบกำกวม")
5. เผื่อพิมพ์ผิด        — ข้อความคำเดียวเทียบความคล้ายกับคำสั่งหลัก ("เเจ้วซ่อม" → "แจ้งซ่อม")

โมดูลนี้ไม่ import โมดูลอื่นของแอป จึงเรียกใช้ได้จากทุกที่โดยไม่เกิด circular import
"""

from __future__ import annotations

import difflib
import re
import unicodedata

# ── 1. Normalize ────────────────────────────────────────────────────────────

# คำลงท้ายสุภาพ/คำเสริมที่ไม่มีผลต่อความหมาย — ตัดออกท้ายประโยคเพื่อให้เทียบคำสั่งสั้นได้
_TAIL_PARTICLES = re.compile(
    r"(ครับ|คับ|ครัช|ค่ะ|คะ|ค๋ะ|นะ|น่ะ|จ้า|จ้ะ|จ๊ะ|ฮะ|หน่อย|ด้วย|เลย|ที|นิ|อะ|ๆ|\s)+$"
)

# พิมพ์ผิดที่พบบ่อยบนคีย์บอร์ดไทย
_TYPO_REPLACEMENTS = (
    ("เเ", "แ"),      # กด เ สองครั้งแทน แ
    ("ํา", "ำ"),      # นิคหิต + สระอา แทน สระอำ
    ("ๅ", "า"),       # ลากข้าง แทน สระอา
    ("\u200b", ""),   # zero-width space จากการ copy
)

_THAI_DIGITS = str.maketrans("๐๑๒๓๔๕๖๗๘๙", "0123456789")


def normalize(text: str) -> str:
    """ข้อความรูปแบบกลาง: ตัวเล็ก, ไม่มีวรรคตอน, ไม่มีคำลงท้าย, แก้พิมพ์ผิดพื้นฐาน"""
    value = unicodedata.normalize("NFKC", str(text or "")).casefold()
    value = value.translate(_THAI_DIGITS)
    for wrong, right in _TYPO_REPLACEMENTS:
        value = value.replace(wrong, right)
    # วรรคตอน/อีโมจิ → ช่องว่าง (เก็บตัวเลข ตัวอักษรไทย-อังกฤษ ไว้)
    value = re.sub(r"[^\w\u0e00-\u0e7f\s]", " ", value, flags=re.UNICODE)
    value = re.sub(r"\s+", " ", value).strip()
    # ยุบอักษรซ้ำ 3 ตัวขึ้นไป: "ไม่ติดดดด" → "ไม่ติด", "helpppp" → "help"
    value = re.sub(r"(.)\1{2,}", r"\1", value)
    for _ in range(3):  # "ไม่ติดเลยค่ะนะคะ" ต้องตัดหลายชั้น
        stripped = _TAIL_PARTICLES.sub("", value).strip()
        if stripped == value:
            break
        value = stripped
    return value


def compact(text: str) -> str:
    """normalize แล้วตัดช่องว่างทิ้ง — ภาษาไทยเว้นวรรคไม่แน่นอน ช่องว่างทำให้เทียบพลาด"""
    return normalize(text).replace(" ", "")


def _strip_guards(haystack: str, guards: tuple[str, ...]) -> str:
    """ลบวลีที่ความหมายต่างออกก่อนเทียบ เพื่อไม่ให้คำสั้นข้างในถูกนับ"""
    for guard in guards:
        haystack = haystack.replace(guard, " ")
    return haystack


def _hit(haystack: str, terms) -> str | None:
    """คืนคำแรกที่พบ (ใช้ debug/log ได้) หรือ None"""
    for term in terms:
        if term and term in haystack:
            return term
    return None


# ── 2. สัญญาณของแต่ละเจตนา ──────────────────────────────────────────────────

REPAIR_SIGNALS = (
    "แจ้งซ่อม", "ซ่อม", "เสีย", "พัง", "ชำรุด", "ไม่ติด", "ไม่ขึ้น", "ไม่มีภาพ", "ไม่มีเสียง",
    "จอดำ", "ภาพไม่ขึ้น", "ค้าง", "แฮงค์", "ไม่ทำงาน", "เปิดไม่ได้", "ปิดไม่ได้", "ใช้ไม่ได้",
    "เข้าไม่ได้", "ช่าง", "ไม่เย็น", "น้ำหยด", "ไฟไม่เข้า", "กระตุก", "เบลอ", "จอเบลอ",
    "สัญญาณหาย", "เน็ตหลุด", "เน็ตช้า", "ปริ้นไม่ออก", "พิมพ์ไม่ออก", "หมึกหมด", "ทัชไม่ติด",
    "แตะไม่ติด", "ทัชสกรีน", "รีโมทไม่ทำงาน", "เครื่องร้อน", "มีควัน", "ไหม้", "ดังผิดปกติ",
)

BUSINESS_SIGNALS = (
    "สินค้า", "ราคา", "ใบเสนอราคา", "เสนอราคา", "โปรโมชัน", "โปรโมชั่น", "แคตตาล็อก",
    "สเปก", "สเปค", "ซื้อ", "สั่งซื้อ", "จัดซื้อ", "งบประมาณ", "เช่า", "บริการ", "อบรม",
    "หลักสูตร", "สื่อการเรียน", "สื่อปฐมวัย", "หนังสือ", "เกมการศึกษา", "aiboard",
    "aiboard", "สมาร์ทบอร์ด", "กระดานอัจฉริยะ", "จอทัชสกรีน", "โครงการ", "ทดลองใช้",
    "สาธิต", "demo", "ผ่อน", "วางบิล", "ใบกำกับ", "เพลงเด็ก",
)

TRACK_SIGNALS = (
    "สถานะ", "ติดตาม", "ถึงไหน", "คืบหน้า", "อัปเดต", "อัพเดท", "เช็คงาน", "เช็กงาน",
    "ticket", "เลขที่แจ้ง", "เลขงาน", "งานซ่อมของ", "ซ่อมเสร็จ", "เสร็จเมื่อไหร่",
    "มาเมื่อไหร่", "จะมาวันไหน", "ยังไม่มา", "รอนาน",
)

CONTACT_SIGNALS = (
    "ติดต่อ", "แอดมิน", "admin", "เจ้าหน้าที่", "พนักงาน", "คุยกับคน", "คุยกับพนักงาน",
    "คุยกับเจ้าหน้าที่", "คนจริง", "ขอเบอร์", "เบอร์โทร", "เบอร์ติดต่อ", "line id",
    "ไลน์ไอดี", "ขอไลน์", "ไลน์ออฟฟิเชียล", "ช่องทางติดต่อ", "ติดต่อทีมงาน",
    "contact", "human", "talk to human",
)

# วลีที่ "ดูเหมือน" สัญญาณติดต่อ แต่จริง ๆ เป็นการเล่าความ ไม่ใช่การขอช่องทางติดต่อ
_CONTACT_GUARDS: dict[str, tuple[str, ...]] = {
    "ติดต่อ": ("ติดต่อกลับ", "รอติดต่อ", "ติดต่อไม่ได้", "ติดต่อช่าง", "ทีมงานติดต่อ"),
    "เจ้าหน้าที่": ("เจ้าหน้าที่มา", "เจ้าหน้าที่จะมา", "เจ้าหน้าที่ยังไม่"),
    "พนักงาน": ("พนักงานมา", "พนักงานจะมา", "พนักงานยังไม่"),
}

# วลีเล่าความทั้งหมด — ใช้ตัดออกก่อนเทียบ "ลิสต์คำติดต่อชุดเดิม" ใน chatbot_core
# (ลิสต์เดิมมีคำกว้างอย่าง "ทีมงาน" ซึ่งไปโดน "รอทีมงานติดต่อกลับอยู่")
_NARRATIVE_CONTACT_PHRASES = (
    "รอทีมงาน", "ทีมงานติดต่อ", "ทีมงานจะ", "ทีมงานยัง", "ทีมงานมา",
    "ติดต่อกลับ", "รอติดต่อ", "ติดต่อไม่ได้", "ติดต่อช่าง",
    "เจ้าหน้าที่มา", "เจ้าหน้าที่จะมา", "เจ้าหน้าที่ยังไม่",
    "พนักงานมา", "พนักงานจะมา", "พนักงานยังไม่",
)


def strip_context_guards(text: str) -> str:
    """compact + ตัดวลีเล่าความเรื่องการติดต่อออก — ให้ chatbot_core ใช้ก่อนเทียบลิสต์เดิม"""
    return _strip_guards(compact(text), _NARRATIVE_CONTACT_PHRASES)


# คำถามนอกขอบเขต + วลีที่อยู่ในขอบเขตซึ่ง "มีคำนั้นซ่อนอยู่ข้างใน" (guard)
_OUT_OF_SCOPE: dict[str, tuple[str, ...]] = {
    "พยากรณ์": (),
    "ฝนตก": (),
    "อากาศ": ("เครื่องปรับอากาศ", "ปรับอากาศ", "ระบายอากาศ", "ฟอกอากาศ", "แอร์"),
    "หวย": (),
    "การเมือง": (),
    "ข่าว": ("ข่าวสาร", "ข่าวประชาสัมพันธ์", "ข่าวบริษัท"),
    "สูตรอาหาร": (),
    "ทำอาหาร": (),
    "เพลง": ("เพลงเด็ก", "เพลงประกอบ", "สื่อเพลง", "เพลงการศึกษา", "เพลงกิจกรรม"),
    "หนัง": ("หนังสือ", "หนังสือเรียน", "แผ่นหนัง"),
    "ภาพยนตร์": (),
    "เกม": ("เกมการศึกษา", "เกมส์การศึกษา", "เกมคณิต", "เกมฝึก", "เกมเด็ก", "เกมพัฒนา"),
    "ท่องเที่ยว": (),
    "แปลภาษา": (),
    "การบ้าน": (),
    "ความรัก": (),
    "ดูดวง": (),
    "หุ้น": ("หุ้นส่วน",),
    "คริปโต": (),
    "บิทคอยน์": (),
}


def is_out_of_scope(text: str) -> bool:
    """นอกขอบเขตจริงหรือไม่ — สัญญาณธุรกิจ/ซ่อม/ติดตามงาน veto ได้ทันที"""
    c = compact(text)
    if not c:
        return False
    if _hit(c, REPAIR_SIGNALS) or _hit(c, BUSINESS_SIGNALS) or _hit(c, TRACK_SIGNALS):
        return False
    for term, guards in _OUT_OF_SCOPE.items():
        if term in _strip_guards(c, guards):
            return True
    return False


def is_admin_contact(text: str) -> bool:
    """ขอคุยกับคน/ขอช่องทางติดต่อจริง — ไม่ใช่ประโยคที่เผอิญมีคำว่า "ติดต่อ" ปนอยู่

    ถ้าข้อความเป็นการถามสถานะงาน (มีคำติดตาม) ให้ flow ติดตามงานชนะ
    เพราะผู้ใช้ต้องการคำตอบเรื่องงาน ไม่ใช่รายการเบอร์โทร
    """
    c = compact(text)
    if not c:
        return False
    if _hit(c, TRACK_SIGNALS):
        return False
    _asks_number = _hit(c, ("ขอเบอร์", "เบอร์โทร", "เบอร์ติดต่อ", "line id", "ขอไลน์", "ไลน์ไอดี"))
    if re.search(r"[a-z]{0,3}\d{4,}", c) and not _asks_number:
        # มีรหัสงาน/เลขอ้างอิงในข้อความ → เป็นการถามถึงงานนั้น ไม่ใช่ขอช่องทางติดต่อ
        return False
    for term in CONTACT_SIGNALS:
        if term in _strip_guards(c, _CONTACT_GUARDS.get(term, ())):
            return True
    return False


# ── 3. ให้คะแนนเจตนา + จับความกำกวม ────────────────────────────────────────

_INTENT_SIGNALS: dict[str, tuple[str, ...]] = {
    "repair": REPAIR_SIGNALS,
    "product": BUSINESS_SIGNALS,
    "track": TRACK_SIGNALS,
    "contact": CONTACT_SIGNALS,
}

_INTENT_LABEL = {
    "repair": "แจ้งซ่อม / อุปกรณ์มีปัญหา",
    "product": "สอบถามสินค้า / ราคา / บริการ",
    "track": "ติดตามสถานะงานที่แจ้งไว้",
    "contact": "คุยกับเจ้าหน้าที่",
}

_INTENT_REPLY_WORD = {
    "repair": "แจ้งซ่อม",
    "product": "สินค้า",
    "track": "ติดตามงาน",
    "contact": "ติดต่อเรา",
}


def score_intents(text: str) -> dict[str, int]:
    """นับสัญญาณของแต่ละเจตนา (คำที่พบ = 1 คะแนน) — ใช้ตัดสินว่ากำกวมหรือไม่"""
    c = compact(text)
    scores: dict[str, int] = {}
    for intent, signals in _INTENT_SIGNALS.items():
        guards = _CONTACT_GUARDS if intent == "contact" else {}
        hits = 0
        counted: set[str] = set()
        for term in signals:
            if term in counted:
                continue
            haystack = _strip_guards(c, guards.get(term, ())) if guards else c
            if term in haystack:
                counted.add(term)
                hits += 1
        if hits:
            scores[intent] = hits
    return scores


def is_vague(text: str) -> bool:
    """ข้อความสั้นและไม่มีสัญญาณใดเลย → ถามกลับดีกว่าเดาแล้วตอบผิด"""
    c = compact(text)
    if not c:
        return True
    if score_intents(text):
        return False
    if is_out_of_scope(text):
        return False
    # ข้อความสั้น ๆ แบบ "ช่วยด้วย" "สอบถาม" "มีอะไรบ้าง" "งงมาก"
    return len(c) <= 14


def ambiguous_intents(text: str) -> list[str]:
    """คืนเจตนาที่คะแนนเท่ากันและสูงสุด (>=2 ตัว = กำกวมจริง ต้องถามกลับ)"""
    scores = score_intents(text)
    if len(scores) < 2:
        return []
    top = max(scores.values())
    tied = sorted(k for k, v in scores.items() if v == top)
    return tied if len(tied) >= 2 else []


def clarify_prompt(text: str) -> dict | None:
    """คำถามกลับ "หนึ่งคำถาม เจาะจง" + ตัวเลือกให้กด

    คืน None เมื่อข้อความชัดพออยู่แล้ว (ไม่ต้องถามกลับ ไม่ต้องโปะเมนู)
    """
    tied = ambiguous_intents(text)
    if tied:
        options = [(_INTENT_LABEL[i], _INTENT_REPLY_WORD[i]) for i in tied if i in _INTENT_LABEL]
        if len(options) >= 2:
            lines = "\n".join(f"{n}. {label}" for n, (label, _) in enumerate(options, 1))
            return {
                "message": ("ขอถามให้ชัดก่อนนะคะ เพื่อตอบให้ตรงเรื่องเลย 🙏\n"
                            f"{lines}\n\nกดตัวเลือกด้านล่าง หรือพิมพ์เลขข้อได้เลยค่ะ"),
                "quick_replies": [word for _, word in options],
                "intents": tied,
            }
    if is_vague(text):
        return {
            "message": ("รับทราบค่ะ 🙏 ขอทราบเพิ่มนิดนึงเพื่อช่วยได้ตรงจุดนะคะ\n"
                        "ต้องการเรื่องไหนคะ?\n"
                        "1. แจ้งซ่อมอุปกรณ์ (บอกอาการสั้น ๆ เช่น \"จอไม่ติด ห้อง 301\")\n"
                        "2. สอบถามสินค้า/ราคา\n"
                        "3. ติดตามงานที่แจ้งไว้ (มีเลขงานยิ่งดีค่ะ)"),
            "quick_replies": ["แจ้งซ่อม", "สินค้า", "ติดตามงาน", "ติดต่อเรา"],
            "intents": [],
        }
    return None


# ── 4. เผื่อพิมพ์ผิด: ข้อความคำเดียวที่สะกดเพี้ยน ──────────────────────────

# คำสั่งหลักที่ผู้ใช้พิมพ์บ่อย → รูปแบบมาตรฐานที่ chatbot_core รู้จัก
_COMMAND_VOCAB = {
    "แจ้งซ่อม": "แจ้งซ่อม",
    "ซ่อม": "แจ้งซ่อม",
    "แจ้งปัญหา": "แจ้งซ่อม",
    "เรียกช่าง": "แจ้งซ่อม",
    "สถานะ": "สถานะ",
    "ติดตาม": "สถานะ",
    "ติดตามงาน": "สถานะ",
    "ติดต่อ": "ติดต่อ",
    "ติดต่อเรา": "ติดต่อ",
    "แอดมิน": "ติดต่อ",
    "สินค้า": "สินค้า",
    "ราคา": "ราคา",
    "บริการ": "บริการ",
    "เมนู": "เมนู",
    "ยกเลิก": "ยกเลิก",
    "ยืนยัน": "ยืนยัน",
    "ประกัน": "ประกัน",
}


def correct_command(text: str, threshold: float = 0.74) -> str | None:
    """ข้อความสั้นที่สะกดเพี้ยน → คำสั่งมาตรฐาน (เช่น "เเจ้วซ่อม" → "แจ้งซ่อม")

    ใช้เฉพาะข้อความสั้น (<= 18 อักขระ) เพื่อไม่ให้ประโยคเล่าอาการถูกบิดความหมาย
    คืน None ถ้าไม่มั่นใจพอ — ยอมถามกลับดีกว่าเดาผิด
    """
    c = compact(text)
    if not c or len(c) > 18:
        return None
    if c in _COMMAND_VOCAB:
        return _COMMAND_VOCAB[c]
    best_word, best_ratio = None, 0.0
    for word, canonical in _COMMAND_VOCAB.items():
        ratio = difflib.SequenceMatcher(None, c, word).ratio()
        if ratio > best_ratio:
            best_word, best_ratio = canonical, ratio
    if best_word and best_ratio >= threshold:
        return best_word
    return None


def understand(text: str, phase: str = "new") -> dict:
    """สรุปความเข้าใจข้อความหนึ่งก้อน ให้ chatbot_core เอาไปตัดสินใจต่อ"""
    return {
        "normalized": normalize(text),
        "compact": compact(text),
        "scores": score_intents(text),
        "out_of_scope": is_out_of_scope(text),
        "admin_contact": is_admin_contact(text),
        "ambiguous": ambiguous_intents(text),
        "vague": is_vague(text) if phase in ("new", "done") else False,
        "command": correct_command(text),
    }