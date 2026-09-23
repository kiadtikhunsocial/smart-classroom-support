"""Import bundled demo schools once inside Render, using its existing DATABASE_URL.

No production credential is exported to a terminal, file or chat. The import
and marker commit atomically. Run only with --apply in ENVIRONMENT=production.
"""

import argparse
import json
import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from sqlalchemy import DateTime, Numeric

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models import (
    DataImportMarker, Device, DeviceHealthFlag, Organization, PMPlan, PMTask,
    RepairTicket, Room, SessionLocal, TicketUpdate, engine, init_db,
)
from scripts.promote_local_mockup import SCHOOL_CODES, copy_data

PACK = Path(__file__).resolve().parent / "demo_schools.json"
MARKER = "demo-schools-5-20260923"
GROUPS = (
    ("schools", Organization), ("rooms", Room), ("devices", Device),
    ("tickets", RepairTicket), ("updates", TicketUpdate),
    ("plans", PMPlan), ("tasks", PMTask), ("flags", DeviceHealthFlag),
)


class PackedRow:
    def __init__(self, model, record):
        self.__table__ = model.__table__
        for column in model.__table__.columns:
            value = record.get(column.name)
            if value is not None and isinstance(column.type, DateTime):
                value = datetime.fromisoformat(value)
            elif value is not None and isinstance(column.type, Numeric):
                value = Decimal(value)
            setattr(self, column.name, value)


def read_pack():
    payload = json.loads(PACK.read_text(encoding="utf-8"))
    if payload.get("version") != 1:
        raise RuntimeError("Unsupported demo pack version")
    groups = payload["groups"]
    if {item["code"] for item in groups["schools"]} != set(SCHOOL_CODES):
        raise RuntimeError("Demo pack does not contain exactly five expected schools")
    return tuple([PackedRow(model, row) for row in groups[name]] for name, model in GROUPS)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="commit the one-time import")
    args = parser.parse_args()
    data = read_pack()
    print("Bundled demo pack:", ", ".join(
        f"{name}={len(rows)}" for (name, _), rows in zip(GROUPS, data)))
    if not args.apply:
        return
    if os.environ.get("ENVIRONMENT", "").lower() not in {"production", "prod"}:
        raise SystemExit("One-time bundled import requires ENVIRONMENT=production")
    if (engine.url.host or "").lower() in {"localhost", "127.0.0.1", "::1", "postgres"}:
        raise SystemExit("One-time bundled import requires a remote database")
    init_db()
    with SessionLocal.begin() as db:
        if db.get(DataImportMarker, MARKER):
            print("Demo pack already applied; no changes")
            return
        created = copy_data(db, data)
        db.add(DataImportMarker(key=MARKER))
    print("Committed demo pack:", ", ".join(f"{key}={value}" for key, value in created.items()))


if __name__ == "__main__":
    main()
