"""Small, defensive Gemini REST client shared by the chatbot.

The chatbot has several optional AI steps. Keeping the transport, retries,
response extraction, and JSON parsing in one place makes every caller fail in
the same predictable way.
"""

import json
import logging
import os
import random
import re
import time
from typing import Any

import httpx


logger = logging.getLogger(__name__)

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview")
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

_client = httpx.Client(
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
)


def is_available() -> bool:
    return bool(API_KEY)


def _post(body: dict[str, Any], timeout: float, retries: int = 1) -> dict[str, Any] | None:
    if not API_KEY:
        return None

    for attempt in range(retries + 1):
        try:
            response = _client.post(
                ENDPOINT,
                headers={"X-goog-api-key": API_KEY},
                json=body,
                timeout=timeout,
            )
            if response.status_code == 200:
                return response.json()

            if response.status_code not in RETRYABLE_STATUS_CODES or attempt >= retries:
                logger.warning("Gemini request failed with HTTP %s", response.status_code)
                return None
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            if attempt >= retries:
                logger.warning("Gemini request failed: %s", exc)
                return None

        # Short bounded backoff. This runs in a worker thread, so it does not
        # block FastAPI's event loop.
        time.sleep(min(1.5, 0.25 * (2 ** attempt) + random.random() * 0.15))

    return None


def _response_text(data: dict[str, Any] | None) -> str | None:
    """Extract text defensively from Gemini's response envelope."""
    for candidate in (data or {}).get("candidates", []):
        parts = ((candidate or {}).get("content") or {}).get("parts") or []
        text = "".join(str(part.get("text", "")) for part in parts if isinstance(part, dict))
        if text.strip():
            return text.strip()
    return None


def request_text(
    parts: list[str],
    *,
    generation_config: dict[str, Any] | None = None,
    timeout: float = 8.0,
    retries: int = 1,
) -> str | None:
    config = dict(generation_config or {})
    body = {
        "contents": [{"parts": [{"text": part} for part in parts if part]}],
        "generationConfig": config,
    }
    return _response_text(_post(body, timeout, retries))


def parse_json(raw: str | None) -> dict[str, Any] | None:
    """Parse plain JSON, fenced JSON, or JSON embedded in a short response."""
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text, flags=re.IGNORECASE)
        text = re.sub(r"\s*```$", "", text).strip()

    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start < 0 or end <= start:
            return None
        try:
            value = json.loads(text[start:end + 1])
            return value if isinstance(value, dict) else None
        except json.JSONDecodeError:
            return None


def request_json(
    parts: list[str],
    *,
    generation_config: dict[str, Any] | None = None,
    timeout: float = 8.0,
    retries: int = 1,
) -> dict[str, Any] | None:
    config = dict(generation_config or {})
    config.setdefault("responseMimeType", "application/json")
    return parse_json(request_text(parts, generation_config=config, timeout=timeout, retries=retries))
