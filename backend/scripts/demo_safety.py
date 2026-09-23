"""Prevent demonstration seed scripts from changing a production database."""

import os

from app.models import engine


def require_local_demo_database() -> None:
    host = (engine.url.host or "").lower()
    environment = os.environ.get("ENVIRONMENT", "").lower()
    if environment in {"production", "prod"} or host not in {
        "localhost", "127.0.0.1", "::1", "postgres",
    }:
        raise SystemExit(
            "Demo data scripts may write only to local PostgreSQL "
            "(localhost, 127.0.0.1, ::1, or the Docker Compose postgres service)."
        )
