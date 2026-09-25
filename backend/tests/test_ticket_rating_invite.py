"""Notification guardrails without a running PostgreSQL or LINE account."""
from types import SimpleNamespace

from app.main import TicketCreate
from app.ticket_rating_invite import invite_staff_rating


class FakeDb:
    def __init__(self):
        self.commits = 0
        self.rollbacks = 0

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1


def test_invitation_only_to_original_line_reporter_and_once(monkeypatch):
    sent = []
    monkeypatch.setattr("app.ticket_rating_invite.send_line_push",
                        lambda to, message: sent.append((to, message)) or True)
    db = FakeDb()
    ticket = SimpleNamespace(status="resolved", line_user_id="line-customer", ticket_id="TK-TEST-1",
                             rating_invited_at=None)
    assert invite_staff_rating(db, ticket) is True
    assert sent[0][0] == "line-customer" and "TK-TEST-1" in sent[0][1]
    assert db.commits == 1 and ticket.rating_invited_at is not None
    assert invite_staff_rating(db, ticket) is False
    assert db.commits == 1 and len(sent) == 1


def test_qr_ticket_without_line_link_is_never_pushed(monkeypatch):
    monkeypatch.setattr("app.ticket_rating_invite.send_line_push",
                        lambda *_: (_ for _ in ()).throw(AssertionError("unexpected push")))
    db = FakeDb()
    ticket = SimpleNamespace(status="closed", line_user_id=None, ticket_id="TK-QR-1",
                             rating_invited_at=None)
    assert invite_staff_rating(db, ticket) is False
    assert db.commits == 0


def test_scan_coordinates_must_be_in_range():
    TicketCreate(device_id="DEVICE-1", title="จอไม่ติด", scan_gps_lat=13.75, scan_gps_lng=100.5)
    from pydantic import ValidationError
    try:
        TicketCreate(device_id="DEVICE-1", title="จอไม่ติด", scan_gps_lat=100, scan_gps_lng=100.5)
    except ValidationError:
        pass
    else:
        raise AssertionError("Invalid latitude should not validate")
