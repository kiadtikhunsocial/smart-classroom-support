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


def test_uploads_are_not_recompressed():
    """Photos are already compressed; gzipping them only costs CPU. Checked on the
    middleware itself with a tiny app, so no real upload file is needed."""
    from starlette.applications import Starlette
    from starlette.responses import Response
    from starlette.routing import Route
    from starlette.testclient import TestClient

    from app.main import _GZipExceptUploads

    body = b"x" * 4096
    inner = Starlette(routes=[
        Route("/uploads/photo.jpg", lambda r: Response(body, media_type="image/jpeg")),
        Route("/api/big", lambda r: Response(body, media_type="application/json")),
    ])
    c = TestClient(_GZipExceptUploads(inner, minimum_size=1024))
    assert c.get("/uploads/photo.jpg", headers={"Accept-Encoding": "gzip"}).headers.get("content-encoding") is None
    assert c.get("/api/big", headers={"Accept-Encoding": "gzip"}).headers.get("content-encoding") == "gzip"


def test_ticket_ordering_index_exists():
    with SessionLocal() as db:
        names = {row[0] for row in db.execute(text("select indexname from pg_indexes where tablename='repair_tickets'"))}
    assert "ix_repair_tickets_created_at_id" in names
