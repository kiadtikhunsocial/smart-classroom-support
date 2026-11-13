"""Large JSON responses are gzip-compressed and the ticket list ordering is indexed."""
from sqlalchemy import text

from app.models import SessionLocal


def test_large_json_is_gzipped(client, admin_headers):
    r = client.get("/api/tickets", params={"limit": 200}, headers={**admin_headers, "Accept-Encoding": "gzip"})
    assert r.status_code == 200
    assert r.headers.get("content-encoding") == "gzip"


def test_small_json_is_not_gzipped(client):
    r = client.get("/health", headers={"Accept-Encoding": "gzip"})
    assert r.headers.get("content-encoding") is None


def test_ticket_ordering_index_exists():
    with SessionLocal() as db:
        names = {row[0] for row in db.execute(text("select indexname from pg_indexes where tablename='repair_tickets'"))}
    assert "ix_repair_tickets_created_at_id" in names
