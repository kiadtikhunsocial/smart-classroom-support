"""Add labelled, idempotent sales examples to the local demo database only."""

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.demo_sales import seed_demo_sales  # noqa: E402
from app.models import SessionLocal, init_db  # noqa: E402
from demo_safety import require_local_demo_database  # noqa: E402


def main() -> None:
    require_local_demo_database()
    init_db()
    with SessionLocal.begin() as db:
        created_leads, created_records = seed_demo_sales(db)
    print(f"Local sales mockup ready: {created_leads} leads, {created_records} records added")


if __name__ == "__main__":
    main()
