"""The ticket workflow endpoints (accept / resolve / close / reopen / cancel) must tell
n8n about the status change exactly like PATCH /api/tickets/{id}/status does, so the
staff LINE group hears about work moved from the new detail-sheet buttons."""
import app.main as main


def _capture(monkeypatch):
    events = []
    monkeypatch.setattr(main, "_notify_n8n", lambda event, payload: events.append((event, payload)))
    return events


def _status_events(events):
    return [(p["ticket_id"], p["from_status"], p["to_status"]) for e, p in events if e == "ticket.status_changed"]


def test_accept_resolve_close_each_notify_once(client, admin_headers, ticket_ids, monkeypatch):
    events = _capture(monkeypatch)
    tid = ticket_ids[0]  # status new
    assert client.post(f"/api/tickets/{tid}/accept", headers=admin_headers).status_code == 200
    assert client.post(f"/api/tickets/{tid}/resolve", json={"solution": "เปลี่ยนสาย HDMI"}, headers=admin_headers).status_code == 200
    assert client.post(f"/api/tickets/{tid}/close", json={}, headers=admin_headers).status_code == 200
    assert _status_events(events) == [
        (tid, "new", "in_progress"),
        (tid, "in_progress", "resolved"),
        (tid, "resolved", "closed"),
    ]
    payload = events[0][1]
    # same shape as PATCH /status: _ticket_event_payload + from/to, so the n8n Dispatcher parses it unchanged
    for key in ("ticket_id", "title", "status", "priority", "device_id", "channel", "from_status", "to_status"):
        assert key in payload


def test_reopen_and_cancel_notify(client, admin_headers, ticket_ids, monkeypatch):
    tid = ticket_ids[1]  # status pending
    assert client.post(f"/api/tickets/{tid}/resolve", json={"solution": "ซ่อมแล้ว"}, headers=admin_headers).status_code == 200
    assert client.post(f"/api/tickets/{tid}/close", json={}, headers=admin_headers).status_code == 200
    events = _capture(monkeypatch)
    assert client.post(f"/api/tickets/{tid}/reopen", json={"note": "อาการกลับมา"}, headers=admin_headers).status_code == 200
    assert client.post(f"/api/tickets/{tid}/cancel", json={"note": "ผู้แจ้งยกเลิก"}, headers=admin_headers).status_code == 200
    assert _status_events(events) == [
        (tid, "closed", "in_progress"),
        (tid, "in_progress", "cancelled"),
    ]


def test_refused_action_does_not_notify(client, admin_headers, ticket_ids, monkeypatch):
    events = _capture(monkeypatch)
    tid = ticket_ids[2]  # waiting_parts: accept is not allowed
    assert client.post(f"/api/tickets/{tid}/accept", headers=admin_headers).status_code == 409
    assert _status_events(events) == []
