"""Mechanically export only the five local demo schools as a deployable data pack."""

import json
import os
import sys
from datetime import datetime
from decimal import Decimal
from pathlib import Path

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models import SessionLocal
from scripts.demo_safety import require_local_demo_database
from scripts.promote_local_mockup import source_data

NAMES = ("schools", "rooms", "devices", "tickets", "updates", "plans", "tasks", "flags")
OUTPUT = Path(__file__).resolve().parent / "demo_schools.json"


def clean(value):
    if isinstance(value, (datetime, Decimal)):
        return str(value) if isinstance(value, Decimal) else value.isoformat()
    return value


def main():
    require_local_demo_database()
    with SessionLocal() as db:
        groups = source_data(db)
        payload = {"version": 1, "groups": {}}
        for name, rows in zip(NAMES, groups):
            payload["groups"][name] = []
            for row in rows:
                record = {column.name: clean(getattr(row, column.name))
                          for column in row.__table__.columns}
                # QR tokens are credentials for public forms: regenerate remotely.
                if name == "devices":
                    record["qr_token"] = None
                payload["groups"][name].append(record)
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT.write_text(json.dumps(payload, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print("Wrote demo-only data pack:", OUTPUT,
          ", ".join(f"{name}={len(payload['groups'][name])}" for name in NAMES))


if __name__ == "__main__":
    main()
