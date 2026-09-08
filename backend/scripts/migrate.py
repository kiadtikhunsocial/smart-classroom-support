# -*- coding: utf-8 -*-
"""Migrate existing PostgreSQL DB: new columns + enum values (run inside backend container)"""
import sys, os
sys.path.insert(0, '/app')
os.chdir('/app')
from sqlalchemy import text
from app.models import SessionLocal, init_db

init_db()  # create_all — 新建表 (kb_articles, kb_suggestions, self_service_cases, pm_plans, pm_tasks)

db = SessionLocal()
try:
    # enum: add new ticket statuses + priority
    for v in ['new', 'pending', 'resolved']:
        db.execute(text("ALTER TYPE ticket_status_enum ADD VALUE IF NOT EXISTS :v"), {'v': v})
    db.execute(text("ALTER TYPE priority_enum ADD VALUE IF NOT EXISTS 'normal'"))

    # devices: qr_token
    db.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS qr_token VARCHAR(64)"))
    db.execute(text("CREATE UNIQUE INDEX IF NOT EXISTS ix_devices_qr_token ON devices(qr_token)"))

    # repair_tickets: new columns
    for col, ddl in [
        ("channel", "VARCHAR(32)"),
        ("symptom_code", "VARCHAR(64)"),
        ("ai_category", "VARCHAR(128)"),
        ("ai_session_id", "VARCHAR(64)"),
        ("attachments", "TEXT"),
        ("root_cause", "TEXT"),
        ("solution", "TEXT"),
        ("parts_used", "TEXT"),
        ("sla_due_at", "TIMESTAMPTZ"),
        ("sla_met", "BOOLEAN"),
        ("escalation_level", "INTEGER DEFAULT 0"),
        ("resolved_at", "TIMESTAMPTZ"),
        ("rating", "INTEGER"),
        ("feedback", "TEXT"),
    ]:
        db.execute(text(f"ALTER TABLE repair_tickets ADD COLUMN IF NOT EXISTS {col} {ddl}"))

    db.commit()
    print("MIGRATION OK")
finally:
    db.close()
