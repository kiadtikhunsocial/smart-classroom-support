"""n8n notifications must not hold up the request that raised them.

`_notify_n8n` used to call the webhook inline, so every ticket create and
status change waited for n8n (up to the 2 s timeout, longer when DNS failed).
These tests pin the background-worker behaviour: return at once, keep the
order events were raised in, and never let a webhook failure escape.
"""
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

import app.main as main


@pytest.fixture(autouse=True)
def fresh_notify_pool(monkeypatch):
    """Each test gets its own worker. The shared one may still be busy with real
    sends queued by other tests (n8n is not running in the test network, so each
    of those waits on a failed DNS lookup), which would make timings flaky."""
    pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="n8n-notify-test")
    monkeypatch.setattr(main, "_NOTIFY_POOL", pool)
    yield
    pool.shutdown(wait=True)


def test_notify_returns_before_the_webhook_finishes(monkeypatch):
    calls = []

    def slow_post(url, json, timeout):
        time.sleep(1.0)
        calls.append(json["event"])

    monkeypatch.setattr(main.httpx, "post", slow_post)
    started = time.perf_counter()
    main._notify_n8n("ticket.created", {"ticket_id": "X"})
    assert time.perf_counter() - started < 0.2
    main._flush_notifications()
    assert calls == ["ticket.created"]


def test_notify_preserves_event_order(monkeypatch):
    seen = []
    monkeypatch.setattr(main.httpx, "post", lambda url, json, timeout: seen.append(json["event"]))
    for event in ["ticket.created", "ticket.status_changed", "ticket.status_changed"]:
        main._notify_n8n(event, {"ticket_id": "X"})
    main._flush_notifications()
    assert seen == ["ticket.created", "ticket.status_changed", "ticket.status_changed"]


def test_notify_swallows_webhook_errors(monkeypatch):
    def boom(*args, **kwargs):
        raise RuntimeError("n8n down")

    monkeypatch.setattr(main.httpx, "post", boom)
    main._notify_n8n("ticket.created", {"ticket_id": "X"})
    main._flush_notifications()  # must not raise


def test_notify_sends_event_and_payload_to_notify_webhook(monkeypatch):
    sent = []
    monkeypatch.setattr(main.httpx, "post", lambda url, json, timeout: sent.append((url, json, timeout)))
    main._notify_n8n("ticket.created", {"ticket_id": "TK.X", "title": "จอดับ"})
    main._flush_notifications()
    url, body, timeout = sent[0]
    assert url == f"{main.N8N_WEBHOOK_URL}notify"
    assert body == {"event": "ticket.created", "ticket_id": "TK.X", "title": "จอดับ"}
    assert timeout == 2.0
