"""Small, defensive Gemini REST client shared by the chatbot.

The chatbot has several optional AI steps. Keeping the transport, retries,
response extraction, and JSON parsing in one place makes every caller fail in
the same predictable way.
"""

import datetime
import json
import logging
import os
import random
import re
import threading
import time
from typing import Any

import httpx


logger = logging.getLogger(__name__)

API_KEY = os.environ.get("GEMINI_API_KEY", "")
MODEL = os.environ.get("GEMINI_MODEL", "gemini-3.1-pro-preview")
ENDPOINT = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}

# Optional fine-tuned model, served from a Vertex AI endpoint
# (projects/PROJECT/locations/us/endpoints/ENDPOINT_ID). When it is set the tuned
# model is tried first and the base model stays as the fallback, so a tuning
# rollout can never take the chatbot offline.
TUNED_ENDPOINT = os.environ.get("GEMINI_TUNED_ENDPOINT", "").strip()
_VERTEX_SCOPE = "https://www.googleapis.com/auth/cloud-platform"
# Multi-region / global Vertex endpoints are served from the unprefixed host.
_GLOBAL_LOCATIONS = {"us", "eu", "global"}

_client = httpx.Client(
    limits=httpx.Limits(max_connections=20, max_keepalive_connections=10),
)

_token_lock = threading.Lock()
_token_cache: dict[str, Any] = {"value": "", "expires_at": 0.0}


def is_available() -> bool:
    return bool(API_KEY) or bool(TUNED_ENDPOINT)


def vertex_url(resource: str) -> str:
    """generateContent URL for a Vertex AI model or endpoint resource name."""
    resource = resource.strip().lstrip("/")
    parts = resource.split("/")
    location = parts[3] if len(parts) > 3 and parts[2] == "locations" else "us-central1"
    host = "aiplatform.googleapis.com" if location in _GLOBAL_LOCATIONS else f"{location}-aiplatform.googleapis.com"
    return f"https://{host}/v1/{resource}:generateContent"


def vertex_access_token() -> str | None:
    """Cached OAuth token from application default credentials, or None."""
    now = time.time()
    with _token_lock:
        if _token_cache["value"] and now < float(_token_cache["expires_at"]):
            return str(_token_cache["value"])

        try:
            import google.auth
            import google.auth.transport.requests
        except ImportError:
            logger.warning("GEMINI_TUNED_ENDPOINT is set but google-auth is missing; using the base model")
            return None

        try:
            credentials, _ = google.auth.default(scopes=[_VERTEX_SCOPE])
            credentials.refresh(google.auth.transport.requests.Request())
        except Exception as exc:  # google.auth raises several unrelated error types
            logger.warning("Could not obtain Vertex AI credentials: %s", exc)
            return None

        token = str(getattr(credentials, "token", "") or "")
        if not token:
            return None

        ttl = 300.0
        expiry = getattr(credentials, "expiry", None)
        if isinstance(expiry, datetime.datetime):
            # google-auth stores a naive UTC expiry; keep a 2 minute safety margin.
            reference = expiry.replace(tzinfo=None) if expiry.tzinfo else expiry
            ttl = max(60.0, (reference - datetime.datetime.utcnow()).total_seconds() - 120)
        _token_cache.update(value=token, expires_at=now + ttl)
        return token


def _targets() -> list[tuple[str, str, dict[str, str]]]:
    """Ordered request targets: tuned model first, base model as fallback."""
    targets: list[tuple[str, str, dict[str, str]]] = []
    if TUNED_ENDPOINT:
        token = vertex_access_token()
        if token:
            targets.append(("tuned", vertex_url(TUNED_ENDPOINT), {"Authorization": f"Bearer {token}"}))
    if API_KEY:
        targets.append(("base", ENDPOINT, {"X-goog-api-key": API_KEY}))
    return targets


def _post_target(
    label: str,
    url: str,
    headers: dict[str, str],
    body: dict[str, Any],
    timeout: float,
    retries: int,
) -> dict[str, Any] | None:
    for attempt in range(retries + 1):
        try:
            response = _client.post(url, headers=headers, json=body, timeout=timeout)
            if response.status_code == 200:
                return response.json()

            if response.status_code not in RETRYABLE_STATUS_CODES or attempt >= retries:
                logger.warning("Gemini (%s) request failed with HTTP %s", label, response.status_code)
                return None
        except (httpx.HTTPError, ValueError, json.JSONDecodeError) as exc:
            if attempt >= retries:
                logger.warning("Gemini (%s) request failed: %s", label, exc)
                return None

        # Short bounded backoff. This runs in a worker thread, so it does not
        # block FastAPI's event loop.
        time.sleep(min(1.5, 0.25 * (2 ** attempt) + random.random() * 0.15))

    return None


def _post(body: dict[str, Any], timeout: float, retries: int = 1) -> dict[str, Any] | None:
    for label, url, headers in _targets():
        data = _post_target(label, url, headers, body, timeout, retries)
        if data is not None:
            return data
        logger.info("Gemini target %s unavailable, trying the next one", label)
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


# "\u0060" is a backtick. Written escaped so the triple-fence markers survive
# being copied through Markdown, which is what corrupted this parser before.
_FENCE = "\u0060" * 3
_FENCE_OPEN_RE = re.compile(r"^" + _FENCE + r"[A-Za-z0-9_+.-]*[ \t]*\r?\n?")
_FENCE_CLOSE_RE = re.compile(_FENCE + r"[ \t]*$")


def _strip_code_fence(text: str) -> str:
    """Remove a leading json (or ) fence and its closing marker."""
    if not text.startswith(_FENCE):
        return text
    text = _FENCE_OPEN_RE.sub("", text, count=1)
    return _FENCE_CLOSE_RE.sub("", text).strip()


def _first_json_object(text: str) -> dict[str, Any] | None:
    """Return the first balanced {...} object in text, ignoring braces in strings."""
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    try:
                        candidate = json.loads(text[start : index + 1])
                    except json.JSONDecodeError:
                        break
                    if isinstance(candidate, dict):
                        return candidate
                    break
        start = text.find("{", start + 1)
    return None


def parse_json(raw: str | None) -> dict[str, Any] | None:
    """Parse plain JSON, fenced JSON, or JSON embedded in a short response."""
    if not raw:
        return None
    text = _strip_code_fence(raw.strip())
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        data = None
    if isinstance(data, dict):
        return data
    embedded = _first_json_object(text)
    if embedded is not None:
        return embedded
    logger.debug("Could not parse JSON from model response: %r", raw[:200])
    return None


def request_json(
    parts: list[str],
    *,
    generation_config: dict[str, Any] | None = None,
    timeout: float = 8.0,
    retries: int = 1,
) -> dict[str, Any] | None:
    """Ask the model for a JSON object and return it parsed, or None.

    Every JSON-shaped caller (intent classification, orchestration, KB
    matching, field extraction) goes through here so a malformed or missing
    response always degrades to None instead of raising.
    """
    raw = request_text(
        parts,
        generation_config=generation_config,
        timeout=timeout,
        retries=retries,
    )
    return parse_json(raw)