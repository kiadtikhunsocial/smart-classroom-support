"""test_line_create_ticket.py — เทสต์ guardrail ของ POST /api/line/create-ticket

endpoint นี้เป็นทางเข้าของ n8n (LINE) จึงต้องมีกติกาเดียวกับ chatbot:
- §52 ข้อ 1 Asset First : ห้าม fallback ไป "อุปกรณ์ตัวแรกในระบบ" / default TEST1
                           เพราะ ticket จะผูก organization_id ขององค์กรอื่น
                           และช่างถูกส่งผิดห้อง
- ระบุกำกวม (ตรงหลายเครื่อง) → ต้องถามกลับ ห้ามเลือกเครื่องให้เอง (409)
- ระบุไม่ได้เลย → 422 ไม่ใช่การสร้าง ticket ผูกอุปกรณ์มั่ว
- §11/§13       : สร้างสำเร็จต้องได้ ticket_no ไม่ซ้ำ + ticket_updates แถวแรก = new

N8N_SHARED_SECRET ต้องตั้งก่อน import app.main เพราะโมดูลอ่านค่าตอน import
เทสต์เขียนลง PostgreSQL จริง จึงลบ ticket ที่สร้างทุกครั้งผ่าน fixture
ถ้า DB ไม่พร้อม/ยังไม่ seed จะ skip ไม่ใช่ fail
"""
import os
import sys

import pytest

sys.path.insert(0, '.')

TEST_SECRET = "test-n8n-secret"
os.environ["N8N_SHARED_SECRET"] = TEST_SECRET

from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text as sa_text  # noqa: E402

from app.main import app  # noqa: E402
from app.models import SessionLocal  # noqa: E402

client = TestClient(app)

# ห้องที่ scripts/seed_db.py สร้างไว้ — มีอุปกรณ์หลายเครื่อง ใช้ทดสอบเคสระบุกำกวม
SEEDED_ROOM_CODE = "301"


def _lookup_seeded_device() -> str | None:
    """รหัสอุปกรณ์ในห้อง 301 จากฐานข้อมูลจริง (None = ยังไม่ seed / ต่อ DB ไม่ได้)

    ห้ามฮาร์ดโค้ด: รูปแบบรหัสใหม่ผูกกับโรงเรียน/อาคาร/ห้อง (เช่น
    SCHDEMO-B3-301-DISP-01) และ scripts/seed_db.py ขอเลขจาก generate_device_id
    ตอนรัน จึงเดารหัสล่วงหน้าไม่ได้

    เลือกเครื่องที่ยังไม่มีใบงานค้างก่อน ไม่อย่างนั้น test_registered_device_creates_ticket
    จะเข้าทางกันแจ้งซ้ำ (TOR 1.5.2) แล้วได้ duplicate=True กับเลขใบของ seed data
    ใช้ฟังก์ชันนี้ตอน import module จึงไม่เรียก pytest.skip ข้างใน (skip นอก test
    จะกลายเป็น error) — คืน None แล้วให้ _require_seeded_device จัดการ
    """
    from app.main import OPEN_TICKET_STATUSES

    try:
        db = SessionLocal()
    except Exception:  # pragma: no cover - ขึ้นกับ environment
        return None
    try:
        return db.execute(
            sa_text(
                "SELECT d.device_id FROM devices d "
                "JOIN rooms r ON r.id = d.room_id "
                "WHERE r.code = :room "
                # EXISTS = false มาก่อน true ใน ORDER BY ASC → เครื่องที่ไม่มีใบค้างขึ้นก่อน
                "ORDER BY EXISTS ("
                "  SELECT 1 FROM repair_tickets t "
                "  WHERE t.device_id = d.device_id "
                "    AND t.status::text = ANY(:open)"
                "), d.device_id "
                "LIMIT 1"
            ),
            {"room": SEEDED_ROOM_CODE, "open": list(OPEN_TICKET_STATUSES)},
        ).scalar()
    except Exception:  # pragma: no cover - ขึ้นกับ environment
        return None
    finally:
        db.close()


SEEDED_DEVICE_ID = _lookup_seeded_device()

HEADERS = {"X-N8N-Secret": TEST_SECRET}


def _payload(**over) -> dict:
    """payload camelCase ตามที่ n8n workflow ส่งมา"""
    base = {
        "reporterName": "ครูทดสอบอัตโนมัติ",
        "organization": "โรงเรียนทดสอบ",
        "room": "",
        "contact": "0812345678",
        "deviceId": "",
        "deviceType": "Interactive Display",
        "problemDetail": "ทดสอบ guardrail ของ endpoint n8n",
        "urgency": "Normal",
        "channel": "LINE",
    }
    base.update(over)
    return base


@pytest.fixture
def created_tickets():
    """เก็บ ticket_id ที่เทสต์สร้าง แล้วลบทิ้งตอนจบ (ticket_updates ลบตาม cascade)"""
    bucket: list[str] = []
    yield bucket
    if not bucket:
        return
    db = SessionLocal()
    try:
        db.execute(
            sa_text("DELETE FROM repair_tickets WHERE ticket_id = ANY(:ids)"),
            {"ids": bucket},
        )
        db.commit()
    finally:
        db.close()


def _query(sql: str, params: dict):
    try:
        db = SessionLocal()
    except Exception as exc:  # pragma: no cover - ขึ้นกับ environment
        pytest.skip(f"ต่อฐานข้อมูลไม่ได้: {exc!r}")
    try:
        return db.execute(sa_text(sql), params).mappings().all()
    except Exception as exc:  # pragma: no cover - ขึ้นกับ environment
        pytest.skip(f"อ่านฐานข้อมูลไม่ได้: {exc!r}")
    finally:
        db.close()


def _require_seeded_device() -> None:
    if not SEEDED_DEVICE_ID:
        pytest.skip(
            f"ยังไม่มีอุปกรณ์ในห้อง {SEEDED_ROOM_CODE} หรือต่อฐานข้อมูลไม่ได้ "
            "— รัน `python scripts/seed_db.py` ก่อน"
        )


def _devices_in_room(room: str):
    return _query(
        "SELECT d.device_id FROM devices d JOIN rooms r ON r.id = d.room_id "
        "WHERE r.code ILIKE :rc OR r.name ILIKE :rc",
        {"rc": f"%{room}%"},
    )


def _status_history_count(ticket_no: str) -> int:
    rows = _query(
        "SELECT count(*) AS c FROM ticket_updates u "
        "JOIN repair_tickets t ON t.id = u.ticket_id "
        "WHERE t.ticket_id = :t AND u.to_status = 'new'",
        {"t": ticket_no},
    )
    return rows[0]["c"] if rows else 0


def test_requires_n8n_secret():
    """endpoint automation ต้องไม่เปิดให้เรียกโดยไม่มี secret (§39 RBAC/Least Privilege)"""
    # ไม่เรียก _require_seeded_device: เทสต์นี้ตรวจแค่ชั้น auth จึงต้องผ่านแม้ยังไม่ seed
    # (deviceId ต้องเป็น str ตาม schema — ถ้ายังไม่ seed ใช้ค่าสมมุติ เพราะ 401 เกิดก่อนค้นอุปกรณ์)
    res = client.post(
        "/api/line/create-ticket",
        json=_payload(deviceId=SEEDED_DEVICE_ID or "SCHDEMO-B3-301-DISP-01"),
    )
    assert res.status_code == 401, res.text


def test_registered_device_creates_ticket(created_tickets):
    """รหัสอุปกรณ์ที่มีจริง → 201 และ ticket ผูกกับอุปกรณ์นั้น"""
    _require_seeded_device()

    res = client.post(
        "/api/line/create-ticket",
        json=_payload(deviceId=SEEDED_DEVICE_ID, problemDetail="จอไม่มีภาพ ไฟ Power ติดปกติ"),
        headers=HEADERS,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    assert body["success"] is True
    assert body["ticket_no"], "ต้องคืน ticket_no ให้ n8n เอาไป notify"
    created_tickets.append(body["ticket_no"])

    assert body["device_id"] == SEEDED_DEVICE_ID, "ห้ามผูกกับอุปกรณ์อื่น"
    assert body["status"] == "new"
    # §13: ทุกการเปลี่ยนสถานะต้องมี History — แถวแรกคือ new
    assert _status_history_count(body["ticket_no"]) == 1


def test_case_insensitive_device_code_resolves(created_tickets):
    """พิมพ์รหัสเป็นตัวเล็ก → ยังต้องเจอเครื่องเดิม ไม่ตกไปเป็น 422"""
    _require_seeded_device()

    res = client.post(
        "/api/line/create-ticket",
        json=_payload(deviceId=SEEDED_DEVICE_ID.lower()),
        headers=HEADERS,
    )
    assert res.status_code == 201, res.text
    body = res.json()
    created_tickets.append(body["ticket_no"])
    assert body["device_id"] == SEEDED_DEVICE_ID


def test_unknown_device_never_falls_back(created_tickets):
    """อุปกรณ์ที่ไม่มีในระบบ → 422 ห้ามสร้าง ticket ผูกอุปกรณ์ขององค์กรอื่น"""
    res = client.post(
        "/api/line/create-ticket",
        json=_payload(deviceId="Interactive Display ห้องที่ไม่ลงทะเบียน"),
        headers=HEADERS,
    )
    if res.status_code == 201:  # pragma: no cover - เจอเมื่อ guardrail ถูกถอด
        created_tickets.append(res.json()["ticket_no"])
        pytest.fail(f"ไม่ควรสร้าง ticket จากอุปกรณ์ที่ไม่รู้จัก: {res.text}")
    assert res.status_code == 422, res.text
    assert "ไม่พบอุปกรณ์" in res.json()["detail"]


def test_empty_payload_does_not_create_ticket(created_tickets):
    """ไม่ส่งทั้ง deviceId และ room → 422 (เดิมเคย fallback เป็น TEST1-00001)"""
    res = client.post("/api/line/create-ticket", json=_payload(), headers=HEADERS)
    if res.status_code == 201:  # pragma: no cover - เจอเมื่อ guardrail ถูกถอด
        created_tickets.append(res.json()["ticket_no"])
        pytest.fail(f"payload ว่างไม่ควรสร้าง ticket: {res.text}")
    assert res.status_code == 422, res.text


def test_room_is_never_guessed_when_ambiguous(created_tickets):
    """ระบุแต่เลขห้อง: หลายเครื่อง → 409 ถามกลับ / เครื่องเดียว → ผูกเครื่องในห้องนั้นจริง"""
    _require_seeded_device()
    devices = _devices_in_room(SEEDED_ROOM_CODE)
    if not devices:
        pytest.skip(f"ห้อง {SEEDED_ROOM_CODE} ไม่มีอุปกรณ์ในฐานข้อมูล")

    res = client.post(
        "/api/line/create-ticket",
        json=_payload(room=SEEDED_ROOM_CODE),
        headers=HEADERS,
    )

    if len(devices) > 1:
        if res.status_code == 201:  # pragma: no cover - เจอเมื่อ guardrail ถูกถอด
            created_tickets.append(res.json()["ticket_no"])
            pytest.fail(f"ห้องมี {len(devices)} เครื่อง ระบบไม่ควรเดาเครื่อง: {res.text}")
        assert res.status_code == 409, res.text
        assert "หลายเครื่อง" in res.json()["detail"]
    else:
        assert res.status_code == 201, res.text
        body = res.json()
        created_tickets.append(body["ticket_no"])
        assert body["device_id"] == devices[0]["device_id"]


def test_room_number_is_not_matched_as_device_code(created_tickets):
    """เลขห้องล้วนใน deviceId ต้องไม่ substring ไปตรงรหัสอุปกรณ์คนละห้อง

    เคสที่เคยพลาด: "301" ไปตรงกับ DEV-2024-00301 (Router ห้อง 201)
    ผลลัพธ์ที่ยอมรับได้คือ 409 (กำกวม) หรือ 422 (ไม่พบ) หรือถ้าสร้างได้
    ก็ต้องเป็นอุปกรณ์ที่อยู่ในห้องนั้นจริง ๆ เท่านั้น
    """
    _require_seeded_device()
    room_devices = {r["device_id"] for r in _devices_in_room(SEEDED_ROOM_CODE)}

    res = client.post(
        "/api/line/create-ticket",
        json=_payload(deviceId=SEEDED_ROOM_CODE, room=SEEDED_ROOM_CODE),
        headers=HEADERS,
    )

    if res.status_code == 201:
        body = res.json()
        created_tickets.append(body["ticket_no"])
        assert body["device_id"] in room_devices, (
            f"เลขห้อง {SEEDED_ROOM_CODE} ถูกตีความเป็นรหัสอุปกรณ์ "
            f"{body['device_id']} ซึ่งไม่ได้อยู่ในห้องนั้น"
        )
    else:
        assert res.status_code in (409, 422), res.text


def _devices_without_open_ticket(count: int):
    """รหัสอุปกรณ์ที่ยังไม่มีใบงานค้าง จำนวน count เครื่อง (skip ถ้าไม่พอ)

    ใช้ OPEN_TICKET_STATUSES จาก app.main ชุดเดียวกับ find_open_ticket เพื่อไม่ให้
    เทสต์ไปโดนเครื่องที่มีใบค้างอยู่ ซึ่งจะเข้าทางกันแจ้งซ้ำแล้วคืนเลขใบของ
    seed data — fixture cleanup จะลบข้อมูลตั้งต้นทิ้ง
    """
    from app.main import OPEN_TICKET_STATUSES

    rows = _query(
        "SELECT d.device_id FROM devices d "
        "WHERE NOT EXISTS ("
        "  SELECT 1 FROM repair_tickets t "
        "  WHERE t.device_id = d.device_id AND t.status::text = ANY(:open)"
        ") ORDER BY d.device_id LIMIT :n",
        {"open": list(OPEN_TICKET_STATUSES), "n": count},
    )
    if len(rows) < count:
        pytest.skip(
            f"ต้องมีอุปกรณ์ที่ไม่มีใบงานค้างอย่างน้อย {count} เครื่อง แต่พบ {len(rows)} "
            "— รัน `python scripts/seed_db.py` ก่อน"
        )
    return [r["device_id"] for r in rows]


def _ticket_count_of_device(device_id: str) -> int:
    rows = _query(
        "SELECT count(*) AS c FROM repair_tickets WHERE device_id = :d",
        {"d": device_id},
    )
    return rows[0]["c"] if rows else 0


def test_ticket_numbers_are_unique(created_tickets):
    """§11: ใบงานต่างใบต้องได้เลข ticket ไม่ซ้ำ (สร้างจาก 2 เครื่องที่ไม่มีใบค้าง)

    เดิมยิงอุปกรณ์เดิม 2 ครั้งเพื่อให้ได้ 2 ใบ ซึ่งตอนนี้ถูกกันแจ้งซ้ำ (TOR 1.5.2)
    endpoint จะคืนเลขใบเดิมพร้อม duplicate=True — พฤติกรรมนั้นทดสอบแยกที่
    test_duplicate_report_appends_to_open_ticket
    """
    _require_seeded_device()
    devices = _devices_without_open_ticket(2)

    numbers = []
    for i, device_id in enumerate(devices, 1):
        res = client.post(
            "/api/line/create-ticket",
            json=_payload(deviceId=device_id, problemDetail=f"ทดสอบเลขไม่ซ้ำ #{i}"),
            headers=HEADERS,
        )
        assert res.status_code == 201, res.text
        body = res.json()
        assert not body.get("duplicate"), f"เครื่อง {device_id} ไม่ควรมีใบค้างอยู่: {body}"
        created_tickets.append(body["ticket_no"])
        numbers.append(body["ticket_no"])

    assert len(set(numbers)) == len(numbers), f"Ticket Number ซ้ำ: {numbers}"


def test_duplicate_report_appends_to_open_ticket(created_tickets):
    """TOR 1.5.2: แจ้งเครื่องเดิมซ้ำขณะมีใบค้าง → ไม่เปิดใบใหม่ แต่ต่ออาการเข้าใบเดิม"""
    _require_seeded_device()
    device_id = _devices_without_open_ticket(1)[0]

    first = client.post(
        "/api/line/create-ticket",
        json=_payload(deviceId=device_id, problemDetail="จอไม่มีภาพ (ใบแรก)"),
        headers=HEADERS,
    )
    assert first.status_code == 201, first.text
    first_no = first.json()["ticket_no"]
    created_tickets.append(first_no)

    before = _ticket_count_of_device(device_id)

    second = client.post(
        "/api/line/create-ticket",
        json=_payload(deviceId=device_id, problemDetail="เสียงไม่ออกด้วย (แจ้งเพิ่ม)"),
        headers=HEADERS,
    )
    assert second.status_code == 201, second.text
    body = second.json()
    if body["ticket_no"] != first_no:  # pragma: no cover - เจอเมื่อ guardrail ถูกถอด
        created_tickets.append(body["ticket_no"])
        pytest.fail(f"ต้องคืนเลขใบเดิม {first_no} ไม่เปิดใบใหม่: {second.text}")

    assert body["duplicate"] is True
    assert body["code"] == "DUPLICATE_OPEN_TICKET"
    assert body["note_added"] is True
    assert body["status_label"], "ต้องมีป้ายสถานะภาษาไทยให้ n8n ตอบผู้แจ้ง"
    assert _ticket_count_of_device(device_id) == before, (
        "จำนวนใบงานของอุปกรณ์ต้องไม่เพิ่มจากการแจ้งซ้ำ"
    )
    # §13: อาการที่แจ้งเพิ่มต้องถูกบันทึกเป็น ticket_updates ของใบเดิม
    notes = _query(
        "SELECT count(*) AS c FROM ticket_updates u "
        "JOIN repair_tickets t ON t.id = u.ticket_id "
        "WHERE t.ticket_id = :t AND u.note LIKE :p",
        {"t": first_no, "p": "[แจ้งเพิ่มจากผู้ใช้ LINE]%"},
    )
    assert notes and notes[0]["c"] >= 1, "ต้องบันทึกอาการที่แจ้งเพิ่มเข้าใบเดิม"