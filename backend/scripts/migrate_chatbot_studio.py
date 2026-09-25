"""Idempotent additions to existing chatbot tables (create_all does not ALTER)."""
import sys
from pathlib import Path

from sqlalchemy import text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from app.models import engine, init_db


def migrate() -> None:
    init_db()
    with engine.begin() as connection:
        connection.execute(text("ALTER TABLE chatbot_knowledge_entries ADD COLUMN IF NOT EXISTS source_label VARCHAR(160)"))
        connection.execute(text("ALTER TABLE chatbot_knowledge_entries ADD COLUMN IF NOT EXISTS source_url VARCHAR(500)"))
        connection.execute(text("ALTER TABLE line_service_ratings ADD COLUMN IF NOT EXISTS resolved BOOLEAN"))
        connection.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS warranty_details VARCHAR(500)"))
        connection.execute(text("ALTER TABLE repair_tickets ADD COLUMN IF NOT EXISTS line_user_id VARCHAR(128)"))
        connection.execute(text("CREATE INDEX IF NOT EXISTS ix_repair_tickets_line_user_id ON repair_tickets (line_user_id)"))
        connection.execute(text("ALTER TABLE repair_tickets ADD COLUMN IF NOT EXISTS rating_invited_at TIMESTAMPTZ"))


if __name__ == "__main__":
    migrate()
    print("Chatbot studio schema ready")
