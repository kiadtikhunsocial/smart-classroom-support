"""Human-reviewed LINE answers for exact, normalized questions only.

Never use this store for warranty, prices, payments, repair state, or identity
decisions: those must come from their existing database-backed workflows.
"""
import logging
import json

from sqlalchemy import select

from app.chatbot_helpers import normalize_question
from app.models import ChatbotKnowledgeEntry, SessionLocal

logger = logging.getLogger(__name__)


def answer_for_question(question: str) -> str | None:
    key = normalize_question(question)
    if not key:
        return None
    db = SessionLocal()
    try:
        rows = db.execute(select(ChatbotKnowledgeEntry).where(
            ChatbotKnowledgeEntry.is_published.is_(True)
        )).scalars().all()
        for row in rows:
            try:
                variants = [row.question, *json.loads(row.aliases or "[]")]
            except (TypeError, ValueError):
                variants = [row.question]
            if any(normalize_question(value) == key for value in variants):
                return row.answer
    except Exception:
        logger.exception("Could not read reviewed chatbot knowledge")
    finally:
        db.close()
    return None
