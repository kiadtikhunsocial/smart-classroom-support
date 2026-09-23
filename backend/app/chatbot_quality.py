"""Small, deterministic review queue for improving chatbot knowledge.

This is a candidate list for human review, not an automatic accuracy score.
Keep it independent from LINE/Gemini/DB so staff examples can be regression-tested.
"""
from app.gemini_service import mask_pii

_CONTROL_UTTERANCES = {
    "ยังไม่หาย", "หายแล้ว", "ไม่มีแล้ว", "ใช่", "ไม่ใช่", "ตกลง", "ยกเลิก",
    "ค่ะ", "ครับ", "โอเค", "ok", "yes", "no", "?",
}


def curate_review_questions(messages, limit: int = 20) -> list[str]:
    """Deduplicate likely missed questions and mask contact details before UI."""
    result: list[str] = []
    seen: set[str] = set()
    for raw in messages:
        message = " ".join(str(raw or "").split()).strip()
        key = message.casefold()
        if len(message) < 6 or key in _CONTROL_UTTERANCES or key in seen:
            continue
        seen.add(key)
        result.append(mask_pii(message)[:300])
        if len(result) >= limit:
            break
    return result
