"""ระบบส่งงานแบบ Grab: เลือกช่างที่ว่างที่สุด, ข้าม/หมดเวลาแล้วส่งต่อ, กดรับ, ผูก LINE, หน้าสรุปแอดมิน"""
import json
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select

from app import dispatch
from app.models import AuditLog, Device, Organization, RepairTicket, SessionLocal, TicketUpdate, User


@pytest.fixture
def world(tag, monkeypatch):
    """โรงเรียน 2 แห่ง, ช่าง A/B (โรงเรียน 1), ช่าง C (ปิดรับงาน), ช่าง D (โรงเรียน 2), admin_school ของโรงเรียน 2
    ช่าง it_support อื่นในฐานข้อมูลถูกปิดรับงานชั่วคราวแล้วคืนค่าตอนจบ"""
    from app.main import create_token
    monkeypatch.setenv("AUTO_ASSIGN_ENABLED", "1")
    # kick() จริง = sweep ทั้งฐานข้อมูล จะไปมอบงาน demo ให้ช่างทดสอบ — เทสต์เรียก sweep(only_ids=...) เอง
    monkeypatch.setattr(dispatch, "kick", lambda: None)
    db = SessionLocal()
    others = {u.id: u.on_duty for u in db.execute(select(User).where(User.role == "it_support")).scalars()}
    for u in db.execute(select(User).where(User.id.in_(list(others) or [-1]))).scalars():
        u.on_duty = False
    org1 = Organization(code=f"D1{tag}", name=f"รร.ส่งงาน 1 {tag}")
    org2 = Organization(code=f"D2{tag}", name=f"รร.ส่งงาน 2 {tag}")
    db.add_all([org1, org2]); db.flush()
    mk = lambda key, **kw: User(line_user_id=f"{key}-{tag}", line_display_name=f"ช่าง{key}", role="it_support",
                                is_active=True, line_push_id=f"U{key}{tag}", **kw)
    a, b = mk("A", organization_id=org1.id), mk("B", organization_id=org1.id)
    c, d = mk("C", organization_id=org1.id, on_duty=False), mk("D", organization_id=org2.id)
    sch = User(line_user_id=f"S-{tag}", line_display_name="admin2", role="admin_school",
               organization_id=org2.id, is_active=True)
    db.add_all([a, b, c, d, sch]); db.flush()
    dev1 = Device(device_id=f"DD1-{tag}", organization_id=org1.id, device_type="Projector", status="active")
    dev2 = Device(device_id=f"DD2-{tag}", organization_id=org2.id, device_type="Projector", status="active")
    db.add_all([dev1, dev2]); db.commit()
    n = {"i": 0}

    def ticket(status="new", dev=dev1, **kw) -> RepairTicket:
        n["i"] += 1
        with SessionLocal() as s:
            t = RepairTicket(ticket_id=f"TD.{tag}.{n['i']}", organization_id=dev.organization_id, device_id=dev.device_id,
                             title=f"งานทดสอบ {tag}", status=status, priority="normal", **kw)
            s.add(t); s.commit()
            return t

    def fresh(t: RepairTicket) -> RepairTicket:
        with SessionLocal() as s:
            return s.get(RepairTicket, t.id)

    yield {
        "a": a, "b": b, "c": c, "d": d, "org1": org1, "org2": org2, "dev1": dev1, "dev2": dev2,
        "ticket": ticket, "fresh": fresh,
        "h": lambda u: {"Authorization": f"Bearer {create_token(u)}"},
        "sch": sch,
    }
    dispatch.flush()
    db.rollback()
    ids = [t.id for t in db.execute(select(RepairTicket).where(RepairTicket.ticket_id.like(f"TD.{tag}.%"))).scalars()]
    tids = [t.ticket_id for t in db.execute(select(RepairTicket).where(RepairTicket.id.in_(ids or [-1]))).scalars()]
    db.query(TicketUpdate).filter(TicketUpdate.ticket_id.in_(ids or [-1])).delete(synchronize_session=False)
    db.query(AuditLog).filter(AuditLog.entity_id.in_(tids or ["-"])).delete(synchronize_session=False)
    db.query(RepairTicket).filter(RepairTicket.id.in_(ids or [-1])).delete(synchronize_session=False)
    db.query(Device).filter(Device.device_id.in_([dev1.device_id, dev2.device_id])).delete(synchronize_session=False)
    uids = [a.id, b.id, c.id, d.id, sch.id]
    db.query(AuditLog).filter(AuditLog.user_id.in_(uids)).delete(synchronize_session=False)
    db.query(AuditLog).filter(AuditLog.entity_id.in_([str(x) for x in uids])).delete(synchronize_session=False)
    db.query(User).filter(User.id.in_(uids)).delete(synchronize_session=False)
    db.query(Organization).filter(Organization.id.in_([org1.id, org2.id])).delete(synchronize_session=False)
    for uid, on in others.items():
        u = db.get(User, uid)
        if u:
            u.on_duty = on
    db.commit()
    db.close()


def test_picks_staff_with_fewest_open_jobs(world):
    w = world
    w["ticket"]("in_progress", assigned_user_id=w["a"].id, assigned_to="ช่างA")
    with SessionLocal() as s:
        assert dispatch.pick_staff(s, w["org1"].id).id == w["b"].id


def test_tie_goes_to_who_finished_less_today(world):
    w = world
    w["ticket"]("resolved", assigned_user_id=w["b"].id, resolved_at=datetime.now(timezone.utc))
    with SessionLocal() as s:
        assert dispatch.pick_staff(s, w["org1"].id).id == w["a"].id


def test_off_duty_and_other_school_staff_are_never_picked(world):
    w = world
    with SessionLocal() as s:
        picked = dispatch.pick_staff(s, w["org1"].id, exclude_ids=[w["a"].id, w["b"].id])
    assert picked is None  # C ปิดรับงาน, D อยู่อีกโรงเรียน


def test_new_ticket_is_offered_and_two_at_once_go_to_two_people(world):
    w = world
    t1, t2 = w["ticket"](), w["ticket"]()
    dispatch.enqueue_dispatch(t1.id)
    dispatch.enqueue_dispatch(t2.id)
    dispatch.flush()
    f1, f2 = w["fresh"](t1), w["fresh"](t2)
    assert f1.status == f2.status == "assigned"
    assert f1.auto_assigned and f2.auto_assigned
    assert {f1.assigned_user_id, f2.assigned_user_id} == {w["a"].id, w["b"].id}


def test_skip_passes_to_next_then_back_to_new_when_everyone_skipped(client, world):
    w = world
    t = w["ticket"]()
    dispatch.dispatch_ticket(t.id)
    first = w["fresh"](t).assigned_user_id
    first_user = w["a"] if first == w["a"].id else w["b"]
    second_user = w["b"] if first_user is w["a"] else w["a"]

    r = client.post(f"/api/tickets/{t.ticket_id}/decline", headers=w["h"](first_user))
    assert r.status_code == 200, r.text
    assert w["fresh"](t).assigned_user_id == second_user.id

    # คนแรกกดข้ามซ้ำ (งานไม่ได้อยู่กับเขาแล้ว) → 409
    assert client.post(f"/api/tickets/{t.ticket_id}/decline", headers=w["h"](first_user)).status_code == 409

    client.post(f"/api/tickets/{t.ticket_id}/decline", headers=w["h"](second_user))
    f = w["fresh"](t)
    assert f.status == "new" and f.assigned_user_id is None and f.assigned_to is None
    assert sorted(dispatch._offer_state(f)["declined"]) == sorted([w["a"].id, w["b"].id])
    # sweep รอบต่อไปไม่เสนอให้คนเดิมวนซ้ำ
    dispatch.sweep(only_ids=[t.id])
    assert w["fresh"](t).status == "new"


def test_offer_times_out_to_next_person(world):
    w = world
    t = w["ticket"]()
    dispatch.dispatch_ticket(t.id)
    first = w["fresh"](t).assigned_user_id
    later = datetime.now(timezone.utc) + timedelta(minutes=dispatch.offer_minutes() + 1)
    assert dispatch.sweep(now=later, only_ids=[t.id]) == 1
    f = w["fresh"](t)
    assert f.status == "assigned" and f.assigned_user_id not in (None, first)


def test_admin_manual_assignment_is_never_moved_by_sweep(client, world, admin_headers):
    w = world
    t = w["ticket"]()
    r = client.post(f"/api/tickets/{t.ticket_id}/assign", json={"assignee_user_id": w["a"].id}, headers=admin_headers)
    assert r.status_code == 200, r.text
    later = datetime.now(timezone.utc) + timedelta(hours=2)
    dispatch.sweep(now=later, only_ids=[t.id])
    f = w["fresh"](t)
    assert f.assigned_user_id == w["a"].id and not f.auto_assigned


def test_assigned_tech_accepts_and_others_cannot_snatch_it(client, world):
    w = world
    t = w["ticket"]()
    dispatch.dispatch_ticket(t.id)
    offered_to = w["fresh"](t).assigned_user_id
    holder = w["a"] if offered_to == w["a"].id else w["b"]
    other = w["b"] if holder is w["a"] else w["a"]
    # งานที่ระบบมอบให้คนว่างแล้ว ช่างคนอื่นกดรับแทนไม่ได้
    assert client.post(f"/api/tickets/{t.ticket_id}/accept", headers=w["h"](other)).status_code == 409
    r = client.post(f"/api/tickets/{t.ticket_id}/accept", headers=w["h"](holder))
    assert r.status_code == 200, r.text
    f = w["fresh"](t)
    assert f.status == "in_progress" and f.assigned_user_id == holder.id and not f.auto_assigned
    # รับซ้ำ → 409
    assert client.post(f"/api/tickets/{t.ticket_id}/accept", headers=w["h"](holder)).status_code == 409
    other = holder

    mine = client.get("/api/tickets", params={"mine": "true"}, headers=w["h"](other))
    assert [x["ticket_id"] for x in mine.json()] == [t.ticket_id]
    assert mine.json()[0]["assigned_user_id"] == other.id
    counts = client.get("/api/tickets/counts", headers=w["h"](other)).json()
    assert counts["mine_open"] == 1


def test_dispatch_me_lists_my_offer_and_going_off_duty_passes_it_on(client, world):
    w = world
    t = w["ticket"]()
    dispatch.dispatch_ticket(t.id)
    holder = w["a"] if w["fresh"](t).assigned_user_id == w["a"].id else w["b"]
    me = client.get("/api/dispatch/me", headers=w["h"](holder)).json()
    assert [o["ticket_id"] for o in me["offers"]] == [t.ticket_id]
    assert me["on_duty"] is True and me["can_receive"] is True

    r = client.patch("/api/me/duty", json={"on_duty": False}, headers=w["h"](holder))
    assert r.json() == {"on_duty": False, "passed_on": 1}
    assert w["fresh"](t).assigned_user_id not in (None, holder.id)


def test_line_link_code_works_once(client, world):
    from app.main import _LINK_FAILS, _try_line_link
    w = world
    code = client.post("/api/me/line-link-code", headers=w["h"](w["a"])).json()["code"]
    line_id = "U" + "f" * 32
    _LINK_FAILS.pop(line_id, None)
    assert _try_line_link(line_id, "สวัสดี") is None  # ข้อความทั่วไป → chatbot ตามปกติ
    assert "ไม่ถูกต้อง" in _try_line_link(line_id, "ผูก 000000" if code != "000000" else "ผูก 111111")
    assert "เรียบร้อย" in _try_line_link(line_id, f"ผูก {code}")
    with SessionLocal() as s:
        assert s.get(User, w["a"].id).line_push_id == line_id
    assert "ไม่ถูกต้อง" in _try_line_link(line_id, f"link {code}")  # ใช้ซ้ำไม่ได้
    assert client.get("/api/dispatch/me", headers=w["h"](w["a"])).json()["line_linked"] is True


def test_line_link_locks_after_five_wrong_codes(world):
    from app.main import _LINK_FAILS, _try_line_link
    line_id = "U" + "e" * 32
    _LINK_FAILS.pop(line_id, None)
    for _ in range(5):
        _try_line_link(line_id, "ผูก 999999")
    assert "รอ 15 นาที" in _try_line_link(line_id, "ผูก 999999")
    _LINK_FAILS.pop(line_id, None)


def test_summary_shows_team_state_and_school_admin_sees_own_school_only(client, world, admin_headers):
    w = world
    w["ticket"]("in_progress", assigned_user_id=w["a"].id, assigned_to="ช่างA")
    unclaimed = w["ticket"](dev=w["dev2"])  # โรงเรียน 2
    other_school = w["ticket"]()
    body = client.get("/api/dispatch/summary", headers=admin_headers).json()
    by_id = {s["id"]: s for s in body["staff"]}
    assert by_id[w["a"].id]["state"] == "busy" and by_id[w["a"].id]["open"] == 1
    assert by_id[w["b"].id]["state"] == "free"
    assert by_id[w["c"].id]["state"] == "off"
    assert body["tickets"]["unclaimed"] >= 2

    mine = client.get("/api/dispatch/summary", headers=w["h"](w["sch"])).json()
    ids = {s["id"] for s in mine["staff"]}
    assert w["d"].id in ids and w["a"].id not in ids
    assert [u["ticket_id"] for u in mine["unclaimed"]] == [unclaimed.ticket_id]
    assert mine["tickets"]["unclaimed"] == 1 and other_school.ticket_id
    # ช่างใช้หน้าสรุปไม่ได้
    assert client.get("/api/dispatch/summary", headers=w["h"](w["a"])).status_code == 403


def test_unreachable_staff_are_skipped_until_they_open_the_app(client, world):
    w = world
    with SessionLocal() as s:  # A และ B ยังไม่ผูก LINE และไม่เคยเปิดเว็บ
        for u in s.query(User).filter(User.id.in_([w["a"].id, w["b"].id])):
            u.line_push_id = None
        s.commit()
        assert dispatch.pick_staff(s, w["org1"].id) is None
    # B เปิดหน้าเว็บ (หน้าเว็บถาม /api/dispatch/me) → ออนไลน์ → ได้งาน
    assert client.get("/api/dispatch/me", headers=w["h"](w["b"])).status_code == 200
    with SessionLocal() as s:
        assert dispatch.pick_staff(s, w["org1"].id).id == w["b"].id
    body = client.get("/api/dispatch/summary", headers=w["h"](w["sch"])).json()
    assert all("reachable" in r for r in body["staff"])


def test_lock_reads_the_latest_row_even_if_session_already_holds_it(world):
    w = world
    t = w["ticket"]()
    a = SessionLocal()
    try:
        held = a.get(RepairTicket, t.id)
        assert held.status == "new"
        with SessionLocal() as b:  # อีกคนกดรับไปก่อน
            b.get(RepairTicket, t.id).status = "in_progress"
            b.commit()
        locked = dispatch._locked_ticket(a, t.id)
        assert locked is held and locked.status == "in_progress"
    finally:
        a.rollback(); a.close()


def test_school_admin_cannot_switch_off_a_technician_who_serves_every_school(client, world, tag):
    w = world
    with SessionLocal() as s:
        g = User(line_user_id=f"G-{tag}", line_display_name="ช่างกลาง", role="it_support", is_active=True)
        s.add(g); s.commit()
    try:
        r = client.patch(f"/api/staff/{g.id}/duty", json={"on_duty": False}, headers=w["h"](w["sch"]))
        assert r.status_code == 403
        assert client.patch(f"/api/staff/{w['d'].id}/duty", json={"on_duty": False}, headers=w["h"](w["sch"])).status_code == 200
    finally:
        with SessionLocal() as s:
            s.query(AuditLog).filter(AuditLog.entity_id == str(g.id)).delete(synchronize_session=False)
            s.query(User).filter(User.id == g.id).delete(synchronize_session=False)
            s.commit()


def test_line_offer_links_to_the_staff_app_not_the_public_tracking_page(world):
    w = world
    t = w["ticket"]()
    with SessionLocal() as s:
        msg = dispatch.offer_message(s, s.get(RepairTicket, t.id))
    assert f"/?job={t.ticket_id}" in msg and "?ticket=" not in msg


# ─── v2: คนว่างได้งานทันที / ทีมยุ่ง = งานค้าง + แจ้งเตือน / ว่างแล้วได้งานค้าง ─────────

def test_busy_staff_are_not_auto_assigned_ticket_goes_to_backlog_and_team_is_alerted(world, monkeypatch):
    w = world
    w["ticket"]("in_progress", assigned_user_id=w["a"].id, assigned_to="ช่างA")
    w["ticket"]("in_progress", assigned_user_id=w["b"].id, assigned_to="ช่างB")
    alerted = []
    monkeypatch.setattr(dispatch, "push_backlog_alert", lambda db, t, u: alerted.append(u.id) or True)
    t = w["ticket"]()
    assert dispatch.dispatch_ticket(t.id) is None
    f = w["fresh"](t)
    assert f.status == "new" and f.assigned_user_id is None
    assert sorted(alerted) == sorted([w["a"].id, w["b"].id])  # C ปิดรับงาน, D คนละโรงเรียน
    with SessionLocal() as s:
        notes = [u.note for u in s.query(TicketUpdate).filter(TicketUpdate.ticket_id == t.id)]
    assert any("งานค้าง" in n for n in notes)


def test_waiting_for_parts_does_not_count_as_busy(world):
    w = world
    w["ticket"]("waiting_parts", assigned_user_id=w["a"].id, assigned_to="ช่างA")
    w["ticket"]("in_progress", assigned_user_id=w["b"].id, assigned_to="ช่างB")
    with SessionLocal() as s:
        assert dispatch.pick_staff(s, w["org1"].id).id == w["a"].id


def test_busy_tech_sees_backlog_in_pool_and_can_claim_it(client, world):
    w = world
    w["ticket"]("in_progress", assigned_user_id=w["a"].id, assigned_to="ช่างA")
    w["ticket"]("in_progress", assigned_user_id=w["b"].id, assigned_to="ช่างB")
    t = w["ticket"]()
    dispatch.dispatch_ticket(t.id)
    me = client.get("/api/dispatch/me", headers=w["h"](w["a"])).json()
    assert me["free"] is False and me["active"] == 1
    assert t.ticket_id in [p["ticket_id"] for p in me["pool"]]
    assert me["offers"] == []
    r = client.post(f"/api/tickets/{t.ticket_id}/accept", headers=w["h"](w["a"]))
    assert r.status_code == 200, r.text
    assert w["fresh"](t).assigned_user_id == w["a"].id
    # อีกโรงเรียนไม่เห็นคิวนี้
    other = client.get("/api/dispatch/me", headers=w["h"](w["d"])).json()
    assert t.ticket_id not in [p["ticket_id"] for p in other["pool"]]


def test_backlog_goes_to_whoever_frees_up_first_oldest_job_first(client, world, monkeypatch):
    w = world
    kicks = []
    # kick จริงจะ sweep ทั้งฐานข้อมูล (รวมข้อมูล demo) — ในเทสต์จำกัดเฉพาะใบของเรา
    monkeypatch.setattr(dispatch, "kick", lambda: kicks.append(1))
    job_a = w["ticket"]("in_progress", assigned_user_id=w["a"].id, assigned_to="ช่างA")
    w["ticket"]("in_progress", assigned_user_id=w["b"].id, assigned_to="ช่างB")
    old, newer = w["ticket"](), w["ticket"]()
    for t in (old, newer):
        dispatch.dispatch_ticket(t.id)
    assert w["fresh"](old).status == w["fresh"](newer).status == "new"
    # A ปิดงานเดิม → ว่าง → ระบบมอบงานค้างใบที่เก่าสุดให้ A ทันที (kick) ใบเดียว
    r = client.post(f"/api/tickets/{job_a.ticket_id}/resolve", json={"solution": "เปลี่ยนสาย"}, headers=w["h"](w["a"]))
    assert r.status_code == 200, r.text
    assert kicks, "ปิดงานแล้วต้องสั่งให้ระบบมอบงานค้างทันที"
    dispatch.sweep(only_ids=[old.id, newer.id])
    fo, fn = w["fresh"](old), w["fresh"](newer)
    assert fo.status == "assigned" and fo.assigned_user_id == w["a"].id and fo.auto_assigned
    assert fn.status == "new" and fn.assigned_user_id is None


def test_tech_who_does_not_answer_is_not_repinged_until_cooldown_or_app_opened(client, world):
    w = world
    w["ticket"]("in_progress", assigned_user_id=w["b"].id, assigned_to="ช่างB")  # เหลือ A ว่างคนเดียว
    t, other = w["ticket"](), w["ticket"]()
    dispatch.dispatch_ticket(t.id)
    assert w["fresh"](t).assigned_user_id == w["a"].id
    later = datetime.now(timezone.utc) + timedelta(minutes=dispatch.offer_minutes() + 1)
    dispatch.sweep(now=later, only_ids=[t.id, other.id])
    f = w["fresh"](t)
    # ไม่มีคนว่างอื่น → กลับเข้าคิวงานค้าง และไม่เด้งกลับไปหา A ทันที (ไม่ว่าใบไหน)
    assert f.status == "new" and f.assigned_user_id is None
    assert w["fresh"](other).assigned_user_id is None
    # sweep อีกรอบระหว่างช่วงพัก → ยังไม่เด้งซ้ำ
    dispatch.sweep(now=later + timedelta(minutes=10), only_ids=[t.id, other.id])
    assert w["fresh"](t).assigned_user_id is None
    # พ้นช่วงพัก → A ได้งานค้างใบเก่าสุดอีกครั้ง
    after = later + timedelta(minutes=dispatch.timeout_cooldown_minutes() + 1)
    dispatch.sweep(now=after, only_ids=[t.id, other.id])
    assert w["fresh"](t).assigned_user_id == w["a"].id


def test_tech_who_reopens_the_app_gets_backlog_again_before_cooldown(client, world):
    w = world
    w["ticket"]("in_progress", assigned_user_id=w["b"].id, assigned_to="ช่างB")
    t = w["ticket"]()
    dispatch.dispatch_ticket(t.id)
    timeout_at = datetime.now(timezone.utc) - timedelta(seconds=5)
    with SessionLocal() as s:  # ทำให้ข้อเสนอหมดเวลาไปแล้วตอนนี้
        s.get(RepairTicket, t.id).assigned_at = timeout_at - timedelta(minutes=dispatch.offer_minutes() + 1)
        s.commit()
    dispatch.sweep(now=timeout_at, only_ids=[t.id])
    assert w["fresh"](t).assigned_user_id is None
    # A เปิดแอป (หน้าเว็บถาม /api/dispatch/me) หลังหมดเวลา → กลับมาพร้อมแล้ว
    with SessionLocal() as s:
        s.get(User, w["a"].id).last_seen_at = None
        s.commit()
    client.get("/api/dispatch/me", headers=w["h"](w["a"]))
    dispatch.sweep(only_ids=[t.id])
    assert w["fresh"](t).assigned_user_id == w["a"].id

def test_staff_detail_shows_load_open_jobs_and_is_scoped(client, world, admin_headers):
    w = world
    job = w["ticket"]("in_progress", assigned_user_id=w["a"].id, assigned_to="ช่างA",
                      assigned_at=datetime.now(timezone.utc))
    w["ticket"]("resolved", assigned_user_id=w["a"].id, resolved_at=datetime.now(timezone.utc))
    body = client.get(f"/api/dispatch/staff/{w['a'].id}", headers=admin_headers)
    assert body.status_code == 200, body.text
    d = body.json()
    assert d["state"] == "busy" and d["load"]["active"] == 1 and d["load"]["done_7d"] == 1
    assert [t["ticket_id"] for t in d["open_tickets"]] == [job.ticket_id]
    assert len(d["recent_done"]) == 1
    summary = client.get("/api/dispatch/summary", headers=admin_headers).json()
    a_row = next(s for s in summary["staff"] if s["id"] == w["a"].id)
    assert a_row["current"]["ticket_id"] == job.ticket_id and "picture_url" in a_row
    # แอดมินโรงเรียน 2 ดูช่างโรงเรียน 1 ไม่ได้ / ช่างดูไม่ได้
    assert client.get(f"/api/dispatch/staff/{w['a'].id}", headers=w["h"](w["sch"])).status_code == 404
    assert client.get(f"/api/dispatch/staff/{w['a'].id}", headers=w["h"](w["b"])).status_code == 403
