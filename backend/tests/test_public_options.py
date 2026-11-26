"""test_public_options.py — เทสต์การบังคับ organization_code ของ GET /api/public/options

พฤติกรรมที่ต้องคงไว้ (กันการถอยกลับเป็นช่องข้อมูลรั่ว)
------------------------------------------------------
เดิม endpoint นี้เปิดสาธารณะ (ไม่ต้อง auth) และคืนอุปกรณ์ของ "ทุกโรงเรียน" ถึง 500
รายการ ใครก็ไล่ดูผังอุปกรณ์/ห้องของทุกหน่วยงานได้ ตอนนี้:

1. ไม่ส่ง organization_code → 200 แต่ devices ต้องว่าง และ requires_organization=true
2. ส่งรหัสที่ไม่มีจริง      → 404 error.code = ORGANIZATION_NOT_FOUND และไม่มี devices
3. ส่งรหัสที่ถูกต้อง        → คืนอุปกรณ์ของหน่วยงานนั้น "เท่านั้น"
4. ทุกกรณีต้องไม่มีฟิลด์อ่อนไหวติดออกไป (qr_token, serial_number, gps_lat, ...)
   ข้อ 4 ตรวจจาก "คีย์" ที่มีอยู่จริงใน response ไม่ใช่ค้นข้อความ เพราะฟิลด์ที่ค่าเป็น
   null ก็ยังนับว่ารั่ว: schema สาธารณะไม่ควรประกาศฟิลด์นั้นตั้งแต่ต้น (PublicDeviceInfo)

ใช้ TestClient (ไม่ต้องรัน uvicorn) และเป็นเทสต์อ่านล้วน — ไม่เขียน/ลบข้อมูลใด ๆ
ถ้าต่อฐานข้อมูลไม่ได้หรือยังไม่ได้ seed หน่วยงาน+อุปกรณ์ เทสต์ที่ต้องใช้ข้อมูลจริง
จะถูก skip ไม่ใช่ fail (ไม่ใช่ความผิดของโค้ดที่ทดสอบ) — seed ด้วย
`python scripts/seed_db.py`
"""
import sys

import pytest

sys.path.insert(0, '.')

from sqlalchemy import text as sa_text  # noqa: E402
from starlette.testclient import TestClient  # noqa: E402

from app.main import DEVICE_CATEGORY_TYPES, app  # noqa: E402
from app.models import SessionLocal  # noqa: E402

client = TestClient(app)

# ฟิลด์ที่ห้ามปรากฏใน response ของ endpoint สาธารณะ แม้จะมีค่าเป็น null
SENSITIVE_FIELDS = (
    "qr_token",
    "qr_url",
    "serial_number",
    "firmware_version",
    "warranty_until",
    "notes",
    "gps_lat",
    "gps_lng",
)

# คีย์ที่อุปกรณ์แต่ละตัวส่งออกได้ (ตรงกับ PublicDeviceInfo ใน app/main.py)
ALLOWED_DEVICE_FIELDS = {
    "device_id",
    "device_type",
    # หมวดหมู่ + ชื่อที่คนอ่านรู้เรื่อง: ไม่อ่อนไหว (ผู้แจ้งเห็นของจริงอยู่ตรงหน้าแล้ว)
    # และจำเป็นต่อการเลือกอุปกรณ์โดยไม่ต้องจำรหัส
    "device_category",
    "device_label",
    "brand",
    "model",
    "status",
    "room_code",
    "room_name",
    "building",
    "floor",
    "organization_code",
    "organization_name",
    "organization_id",
}

# รหัสที่จะไม่มีในฐานข้อมูลจริงแน่นอน
UNKNOWN_ORG_CODE = "no-such-org-for-automated-test-9137"

# limit ที่ endpoint ใช้ (ต้องตรงกับ .limit(...) ใน public_options)
DEVICE_LIMIT = 200


def _db():
    try:
        return SessionLocal()
    except Exception as exc:  # pragma: no cover - ขึ้นกับ environment
        pytest.skip(f"ต่อฐานข้อมูลไม่ได้: {exc!r}")


def _org_with_devices():
    """คืน (code, name, device_count, total_devices) ของหน่วยงานที่มีอุปกรณ์มากที่สุด"""
    db = _db()
    try:
        row = db.execute(
            sa_text(
                "SELECT o.code AS code, o.name AS name, count(d.id) AS n "
                "FROM organizations o "
                "JOIN devices d ON d.organization_id = o.id "
                "GROUP BY o.code, o.name "
                "ORDER BY n DESC, o.code "
                "LIMIT 1"
            )
        ).mappings().first()
        total_devices = db.execute(sa_text("SELECT count(*) FROM devices")).scalar_one()
    except Exception as exc:  # pragma: no cover - ขึ้นกับ environment
        pytest.skip(f"อ่านตาราง organizations/devices ไม่ได้: {exc!r}")
    finally:
        db.close()

    if row is None:
        pytest.skip(
            "ยังไม่มีหน่วยงานที่มีอุปกรณ์ในฐานข้อมูล — รัน `python scripts/seed_db.py` ก่อน"
        )
    return row["code"], row["name"], int(row["n"]), int(total_devices)


def _assert_devices_expose_only_safe_fields(devices: list) -> None:
    """ตรวจทุกอุปกรณ์: ห้ามมีคีย์อ่อนไหว และห้ามมีคีย์นอกรายการที่อนุญาต"""
    for d in devices:
        keys = set(d.keys())

        leaked = keys.intersection(SENSITIVE_FIELDS)
        assert not leaked, (
            f"ฟิลด์อ่อนไหว {sorted(leaked)} หลุดออก /api/public/options "
            f"(อุปกรณ์ {d.get('device_id')}) — endpoint นี้ไม่ต้อง auth"
        )

        unexpected = keys - ALLOWED_DEVICE_FIELDS
        assert not unexpected, (
            f"มีฟิลด์ใหม่ {sorted(unexpected)} โผล่ใน response สาธารณะ "
            "— ถ้าเพิ่มโดยเจตนาให้ทบทวนความอ่อนไหวก่อน แล้วอัปเดต ALLOWED_DEVICE_FIELDS"
        )


def _assert_device_categories(body: dict, devices: list) -> None:
    """device_categories ต้องครบทุกหมวด เรียงคงที่ และนับจำนวนตรงกับ devices

    หน้าเว็บใช้ค่านี้ทำ dropdown แบบจัดกลุ่ม ถ้าลำดับหรือรายการหมวดเปลี่ยนไปตาม
    ข้อมูลในฐานข้อมูล ตัวเลือกจะสลับที่ทุกครั้งที่โหลด จึงล็อกไว้ว่าต้องคงที่เสมอ
    """
    cats = body["device_categories"]
    assert isinstance(cats, list) and cats, "ต้องส่ง device_categories เสมอ"
    assert [c["category"] for c in cats] == list(DEVICE_CATEGORY_TYPES), (
        "ลำดับ/รายการหมวดหมู่ต้องตรงกับ DEVICE_CATEGORY_TYPES ทุกครั้ง"
    )
    for c in cats:
        assert c["device_types"] == list(DEVICE_CATEGORY_TYPES[c["category"]]), (
            f"ประเภทอุปกรณ์ในหมวด {c['category']} ไม่ตรงกับตารางกลาง"
        )
        assert isinstance(c["device_count"], int) and c["device_count"] >= 0

    expected: dict[str, int] = {}
    for d in devices:
        category = d["device_category"]
        assert category, f"อุปกรณ์ {d['device_id']} ไม่มีหมวดหมู่"
        expected[category] = expected.get(category, 0) + 1
    got = {c["category"]: c["device_count"] for c in cats if c["device_count"]}
    assert got == expected, (
        f"device_count ไม่ตรงกับรายการอุปกรณ์ที่ส่งมา: {got} != {expected}"
    )


def test_without_org_code_returns_no_devices():
    """ข้อ 1: ไม่ระบุรหัสหน่วยงาน → ห้ามคืนรายการอุปกรณ์ใด ๆ"""
    res = client.get("/api/public/options")
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["requires_organization"] is True, (
        "ต้องบอก frontend ว่ายังต้องระบุรหัสหน่วยงาน"
    )
    assert body["devices"] == [], (
        f"ห้ามคืนอุปกรณ์เมื่อไม่ระบุรหัสหน่วยงาน แต่ได้ {len(body['devices'])} รายการ"
    )
    # dropdown ประเภทอุปกรณ์ยังต้องใช้ได้ เพื่อให้กรอกเองได้โดยไม่ต้องมีรหัส
    assert isinstance(body["device_types"], list) and body["device_types"], (
        "device_types ต้องยังส่งมาเสมอ (โหมดกรอกเอง)"
    )
    assert body["organization_code"] is None
    assert body["organization_name"] is None
    # หมวดหมู่ยังต้องส่งมา (ใช้จัดกลุ่มช่องเลือกประเภทในโหมดกรอกเอง) แต่ไม่มีอุปกรณ์
    # จึงต้องนับเป็น 0 ทุกหมวด — ไม่ใช่ช่องทางนับอุปกรณ์ทั้งระบบโดยไม่ต้องล็อกอิน
    _assert_device_categories(body, [])


def test_unknown_org_code_returns_404_envelope():
    """ข้อ 2: รหัสผิด → 404 ORGANIZATION_NOT_FOUND (ตาม error envelope §35) และไม่มี devices"""
    res = client.get("/api/public/options", params={"organization_code": UNKNOWN_ORG_CODE})
    assert res.status_code == 404, res.text
    body = res.json()

    assert body.get("success") is False, body
    assert body["error"]["code"] == "ORGANIZATION_NOT_FOUND", body
    assert isinstance(body["error"].get("message"), str) and body["error"]["message"].strip()
    assert "devices" not in body, f"response ผิดพลาดต้องไม่พ่วงรายการอุปกรณ์: {body}"


def test_too_short_org_code_is_rejected():
    """รหัสสั้นกว่าที่กำหนด (min_length=2) → 422 ไม่ใช่การ query ทั้งระบบ"""
    res = client.get("/api/public/options", params={"organization_code": "x"})
    assert res.status_code == 422, res.text
    body = res.json()
    assert body.get("success") is False, body
    assert body["error"]["code"] == "VALIDATION_ERROR", body


def test_valid_org_code_returns_only_that_org_devices():
    """ข้อ 3: รหัสถูกต้อง → คืนอุปกรณ์ของหน่วยงานนั้นเท่านั้น"""
    code, name, org_device_count, total_devices = _org_with_devices()

    res = client.get("/api/public/options", params={"organization_code": code})
    assert res.status_code == 200, res.text
    body = res.json()

    assert body["requires_organization"] is False
    assert body["organization_code"] == code
    assert body["organization_name"] == name

    devices = body["devices"]
    expected = min(org_device_count, DEVICE_LIMIT)
    assert len(devices) == expected, (
        f"หน่วยงาน {code} มีอุปกรณ์ {org_device_count} รายการ (limit {DEVICE_LIMIT}) "
        f"แต่ endpoint คืน {len(devices)}"
    )
    if total_devices > org_device_count:
        assert len(devices) < total_devices, (
            "ยังคืนอุปกรณ์เกินขอบเขตหน่วยงาน — การกรองด้วย organization_id ไม่ทำงาน"
        )

    for d in devices:
        assert d["organization_code"] == code, (
            f"อุปกรณ์ {d['device_id']} เป็นของ {d['organization_code']} ไม่ใช่ {code}"
        )
        assert d["device_id"] and d["device_type"], f"ข้อมูลอุปกรณ์ไม่ครบ: {d}"

    # ข้อ 4: ฟิลด์อ่อนไหวต้องไม่มีแม้เป็น null
    _assert_devices_expose_only_safe_fields(devices)

    # ผู้แจ้งต้องเลือกอุปกรณ์ได้โดยไม่ต้องจำรหัส → ต้องมีชื่อที่อ่านรู้เรื่องทุกตัว
    for d in devices:
        assert d["device_label"], f"อุปกรณ์ {d['device_id']} ไม่มี device_label"
        assert d["device_type"] in d["device_label"], (
            f"device_label ของ {d['device_id']} ควรมีประเภทอุปกรณ์อยู่ด้วย: "
            f"{d['device_label']!r}"
        )
        room_label = d["room_name"] or d["room_code"]
        if room_label:
            assert room_label in d["device_label"], (
                f"device_label ของ {d['device_id']} ควรบอกห้องด้วย: {d['device_label']!r}"
            )
    _assert_device_categories(body, devices)


def test_org_code_is_trimmed():
    """รหัสที่มีช่องว่างหน้า/หลัง (พิมพ์เองหรือ copy จากสติกเกอร์) ต้องยังหาเจอ"""
    code, _name, _n, _total = _org_with_devices()

    res = client.get("/api/public/options", params={"organization_code": f"  {code}  "})
    assert res.status_code == 200, res.text
    assert res.json()["organization_code"] == code