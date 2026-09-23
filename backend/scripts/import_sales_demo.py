"""Import fictional customer/sales examples once on production startup.

No credentials or real customer data are exported. Rows are labelled DEMO,
contain no contact details and are not sent to LINE or Google Sheets.
"""

import argparse
import os
import sys

from sqlalchemy import text

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.demo_sales import EXAMPLES, seed_demo_sales  # noqa: E402
from app.models import DataImportMarker, SessionLocal, engine, init_db  # noqa: E402

MARKER = "sales-demo-v2-20260923"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    print(f"Bundled fictional sales examples: {len(EXAMPLES)} customers, {len(EXAMPLES)} records")
    if not args.apply:
        return
    if os.environ.get("ENVIRONMENT", "").lower() not in {"production", "prod"}:
        raise SystemExit("Production import requires ENVIRONMENT=production")
    if (engine.url.host or "").lower() in {"localhost", "127.0.0.1", "::1", "postgres"}:
        raise SystemExit("Production import requires a remote database")
    init_db()
    with SessionLocal.begin() as db:
        db.execute(text("SELECT pg_advisory_xact_lock(2026092301)"))
        if db.get(DataImportMarker, MARKER):
            print("Sales demo already applied; no changes")
            return
        leads, records = seed_demo_sales(db)
        db.add(DataImportMarker(key=MARKER))
    print(f"Committed fictional sales demo: customers={leads}, records={records}")


if __name__ == "__main__":
    main()
