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
    # enum: add admin_school role (ต้อง hardcode ค่า — PG ไม่รองรับ parameter ใน DDL)
    db.execute(text("ALTER TYPE user_role_enum ADD VALUE IF NOT EXISTS 'admin_school'"))

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

    # devices: purchase_date (PM Rule 3 — อายุอุปกรณ์)
    db.execute(text("ALTER TABLE devices ADD COLUMN IF NOT EXISTS purchase_date TIMESTAMPTZ"))

    # repair_tickets: Priority Engine (§15) + issue_category (§32)
    for col, ddl in [
        ("user_priority", "VARCHAR(16)"),
        ("impact", "VARCHAR(16)"),
        ("urgency", "VARCHAR(16)"),
        ("system_priority", "VARCHAR(2)"),
        ("issue_category_id", "INTEGER"),
        ("self_service_attempted", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ]:
        db.execute(text(f"ALTER TABLE repair_tickets ADD COLUMN IF NOT EXISTS {col} {ddl}"))

    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_repair_tickets_system_priority "
        "ON repair_tickets(system_priority)"
    ))
    db.execute(text(
        "CREATE INDEX IF NOT EXISTS ix_repair_tickets_issue_category_id "
        "ON repair_tickets(issue_category_id)"
    ))

    # backfill: ticket เดิมยังไม่มี system_priority → map จาก priority เดิม
    db.execute(text("""
        UPDATE repair_tickets SET system_priority = CASE priority
            WHEN 'critical' THEN 'P1'
            WHEN 'high'     THEN 'P2'
            WHEN 'normal'   THEN 'P3'
            ELSE 'P4'
        END
        WHERE system_priority IS NULL
    """))

    db.commit()
    print("MIGRATION OK")
finally:
    db.close()
