"""หน้าติดตามของผู้แจ้ง: ไทม์ไลน์มีเวลา, ชื่อช่างหลังกดรับ, สถานะหลายใบพร้อมกัน"""
from app import dispatch
from app.models import RepairTicket, SessionLocal, User


def _tech(tag):
    with SessionLocal() as s:
        u = User(line_user_id=f"pt-{tag}", line_display_name="นายสมชาย ใจดี", role="it_support", is_active=True)
        s.add(u); s.commit()
        return u


def _cleanup(u):
    from app.models import AuditLog
    with SessionLocal() as s:
        s.query(AuditLog).filter(AuditLog.user_id == u.id).delete(synchronize_session=False)
        s.query(RepairTicket).filter(RepairTicket.assigned_user_id == u.id).update({"assigned_user_id": None})
        s.query(User).filter(User.id == u.id).delete(synchronize_session=False)
        s.commit()


def test_track_shows_timeline_and_technician_after_accept(client, ticket_ids, tag):
    from app.main import create_token
    no = ticket_ids[0]  # new
    body = client.get(f"/api/tickets/track/{no}").json()
    assert body["technician"] is None
    assert [h["status"] for h in body["history"]] == ["new"]
    assert body["history"][0]["created_at"]

    u = _tech(tag)
    try:
        r = client.post(f"/api/tickets/{no}/accept", headers={"Authorization": f"Bearer {create_token(u)}"})
        assert r.status_code == 200, r.text
        body = client.get(f"/api/tickets/track/{no}").json()
        assert body["technician"] == "สมชาย"  # ชื่อแรก ไม่มีคำนำหน้า ไม่มีนามสกุล
        assert body["history"][-1]["status"] == "in_progress"
        assert body["history"][-1]["label"] == "กำลังดำเนินการ"
    finally:
        _cleanup(u)


def test_system_offer_is_shown_as_finding_a_technician(client, ticket_ids, tag):
    no = ticket_ids[0]
    u = _tech(tag)
    try:
        with SessionLocal() as s:
            t = s.query(RepairTicket).filter(RepairTicket.ticket_id == no).one()
            t.status, t.auto_assigned, t.assigned_user_id, t.assigned_to = "assigned", True, u.id, "นายสมชาย ใจดี"
            dispatch._history(s, t, "new", "assigned", "ระบบเสนองาน")
            s.commit()
        body = client.get(f"/api/tickets/track/{no}").json()
        assert body["status_label"] == "กำลังจัดหาช่าง"
        assert body["finding_technician"] is True
        assert body["technician"] is None
        assert [h["status"] for h in body["history"]] == ["new"]  # การเสนองานของระบบไม่โผล่ในไทม์ไลน์
    finally:
        _cleanup(u)


def test_public_status_batch_returns_known_tickets_in_order(client, ticket_ids):
    r = client.post("/api/public/tickets/status",
                    json={"ticket_nos": [ticket_ids[2].lower(), "TK.NOPE.00.0000-X", ticket_ids[0]]})
    assert r.status_code == 200
    rows = r.json()
    assert [x["ticket_no"] for x in rows] == [ticket_ids[2], ticket_ids[0]]
    assert rows[0]["status"] == "waiting_parts" and rows[0]["status_label"] == "รออะไหล่"
    assert set(rows[0]) == {"ticket_no", "status", "status_label", "title", "device_label", "created_at", "updated_at"}


def test_public_status_batch_rejects_more_than_ten(client):
    assert client.post("/api/public/tickets/status", json={"ticket_nos": ["X"] * 11}).status_code == 422


def test_first_name_keeps_role_style_account_names_whole():
    from app.main import _public_first_name
    assert _public_first_name("นางสาวมาลี ศรีสุข") == "มาลี"
    assert _public_first_name("ช่าง IT วัดราษฎร์บำรุง") == "ช่าง IT วัดราษฎร์บำรุง"
    assert _public_first_name("ช่างหนึ่ง") == "ช่างหนึ่ง"
    assert _public_first_name("  ") is None
