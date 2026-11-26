# ── แผนที่ไฟล์ ──────────────────────────────────────────────
# หน้าที่      : แปลภาษาแชตเว็บ 5 ภาษา <-> ภาษาไทย (ใช้ตอน AI สนทนาไม่ได้)
# ถูกเรียกจาก  : main (POST /api/chatbot/web)
# เชื่อมต่อไป  : ai_client (Gemini)
# env ที่อ่าน  : -
# ภาพรวมระบบ  : docs/SYSTEM_MAP.md
# ─────────────────────────────────────────────────────────
"""Language bridge for the public web chat.

The chatbot pipeline (NLU, knowledge base, ticket flow) is written in Thai.
For other site languages we translate the visitor's message to Thai going in
and the Thai reply to the site language going out, so the answer always
matches the language the visitor chose on the page. Any failure (no API key,
timeout, empty answer) falls back to the original text, so chat never breaks.
"""
from __future__ import annotations

import re

from app.ai_client import request_text

SUPPORTED = {"th": "Thai", "en": "English", "zh": "Simplified Chinese", "ja": "Japanese", "ko": "Korean"}

_KEEP = (
    "Keep ticket numbers (like TK.SCHM01.26.0001-T), device codes, phone numbers, "
    "emails, URLs, numbers and line breaks exactly as they are. "
    "Output ONLY the translated text, no quotes, no notes."
)


_NOTICE = {
    "en": "(Translation is unavailable right now, so this reply is in Thai.)",
    "zh": "（暂时无法翻译，以下回复为泰语。）",
    "ja": "（現在翻訳できないため、返信はタイ語です。）",
    "ko": "(현재 번역을 사용할 수 없어 답변이 태국어로 표시됩니다.)",
}


# The Thai pipeline matches fixed helpdesk vocabulary, so steer the translation towards it.
_TH_STYLE = (
    "Write short, plain Thai the way a teacher types to a helpdesk, in Thai script only (no English or other scripts, "
    "except codes). Phrase problems as '<device> + symptom'. Use these exact terms: "
    "projector = โปรเจคเตอร์; interactive display / smart board = จอ Interactive; touch screen not responding = ทัชสกรีนกดไม่ได้; "
    "no picture / no image = ไม่มีภาพ; no sound = ไม่มีเสียง; won't turn on = เปิดไม่ติด; internet/Wi-Fi not working = ต่ออินเทอร์เน็ตไม่ได้; "
    "slow = ช้า; freezes = ค้าง; printer = ปริ้นเตอร์; computer = คอมพิวเตอร์; "
    "'I tried it but it did not help / still not fixed' = ยังไม่หาย; 'it is fixed / works now' = หายแล้ว; "
    "'report a repair' = แจ้งซ่อม; 'contact' = ติดต่อ; 'products' = สินค้า. "
    "Do not add politeness particles or extra words."
)


def normalize_lang(value: str | None) -> str:
    v = (value or "th").strip().lower()[:2]
    return v if v in SUPPORTED else "th"


def _has_thai(text: str) -> bool:
    return bool(re.search(r"[฀-๿]", text))


def to_thai(text: str, lang: str) -> str:
    """Visitor message -> Thai for the existing pipeline. Thai input is untouched."""
    if lang == "th" or _has_thai(text):
        return text
    # Codes / ticket numbers / one-word answers carry no language: leave them alone.
    if not re.search(r"[A-Za-z぀-ヿ㐀-鿿가-힯]{2,}\s*[A-Za-z぀-ヿ㐀-鿿가-힯]", text) and re.fullmatch(r"[A-Za-z0-9._\-\s]{1,40}", text):
        return text
    out = request_text(
        [f"Translate this {SUPPORTED[lang]} message from a school IT-repair website visitor into Thai. {_TH_STYLE} {_KEEP}", text],
        generation_config={"temperature": 0, "maxOutputTokens": 600},
        timeout=10.0,
        retries=3,
    )
    return (out or "").strip() or text


def from_thai(reply: str, lang: str) -> str:
    """Thai chatbot reply -> the page language."""
    if lang == "th" or not reply:
        return reply
    out = request_text(
        [f"Translate this Thai customer-service reply into natural, polite {SUPPORTED[lang]}. {_KEEP}", reply],
        generation_config={"temperature": 0.1, "maxOutputTokens": 2000},
        timeout=15.0,
        retries=3,
    )
    out = (out or "").strip()
    if out:
        return out
    # แปลไม่ได้ (ไม่มี key/API ล่ม): บอกตรง ๆ ว่าตอบเป็นภาษาไทย แทนที่จะเงียบ
    return (_NOTICE.get(lang, "") + "\n\n" + reply).strip()
