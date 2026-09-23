"""Import the bundled mock schools into an isolated, temporary local database."""

from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.models import Base, engine
from scripts.import_demo_pack import read_pack
from scripts.promote_local_mockup import copy_data


def test_bundled_demo_pack_imports_once():
    if (engine.url.host or "").lower() not in {"localhost", "127.0.0.1"}:
        pytest.skip("Temporary demo import database is local-only")
    db_name = f"smart_demo_test_{uuid4().hex[:10]}"
    admin = create_engine(engine.url.set(database="postgres"), isolation_level="AUTOCOMMIT")
    target = None
    try:
        with admin.connect() as conn:
            conn.execute(text(f'CREATE DATABASE "{db_name}"'))
        target = create_engine(engine.url.set(database=db_name))
        Base.metadata.create_all(bind=target)
        TargetSession = sessionmaker(bind=target, expire_on_commit=False)
        with TargetSession.begin() as db:
            counts = copy_data(db, read_pack())
        assert counts == {
            "schools": 5, "rooms": 25, "devices": 100, "tickets": 66,
            "updates": 220, "plans": 11, "tasks": 90, "flags": 12,
        }
        with TargetSession.begin() as db:
            repeat = copy_data(db, read_pack())
        assert all(count == 0 for count in repeat.values())
    finally:
        if target is not None:
            target.dispose()
        with admin.connect() as conn:
            conn.execute(text(f'DROP DATABASE IF EXISTS "{db_name}" WITH (FORCE)'))
        admin.dispose()
