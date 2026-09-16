"""test_error_envelope.py — เทสต์ error contract §35 ของ backend

§35 กำหนดว่า response ที่ผิดพลาดต้องเป็น
    {"success": false, "data": null, "error": {"code": ..., "message": ...}}

ข้อสำคัญที่ต้องกันไว้ด้วยเทสต์: ต้อง "ยังมี" key `detail` รูปแบบเดิมอยู่ เพราะฝั่งที่
เรียกใช้อ่านจาก detail จริง —
  - frontend/src/api/client.ts  → parsed?.detail และ detail.code
  - backend/test_line_create_ticket.py → res.json()["detail"]
  - n8n workflow (ข้อความ error ที่ส่งกลับเข้า LINE)
ถ้าใครถอด detail ออกในอนาคต ข้อความ error บน UI และใน LINE จะกลายเป็น "HTTP 4xx"
ทั้งระบบ เทสต์ชุดนี้จึงต้องแดงทันที

เทสต์ใช้ TestClient (ไม่ต้องรัน server) และไม่เขียนข้อมูลลงฐานข้อมูล
"""
import sys

import pytest

sys.path.insert(0, '.')

from starlette.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)


def _assert_envelope(res, expected_status: int, expected_code: str) -> dict:
    """ตรวจโครงสร้าง envelope §35 + คง detail เดิม แล้วคืน body ให้ตรวจต่อ"""
    assert res.status_code == expected_status, res.text
    body = res.json()

    assert body.get("success") is False, f"ต้องมี success=false: {body}"
    assert "data" in body and body["data"] is None, f"data ต้องเป็น null: {body}"

    error = body.get("error")
    assert isinstance(error, dict), f"error ต้องเป็น object: {body}"
    assert error.get("code") == expected_code, f"error.code ไม่ตรง: {body}"
    assert isinstance(error.get("message"), str) and error["message"].strip(), (
        f"error.message ต้องเป็นข้อความที่ไม่ว่าง: {body}"
    )

    # backward compatibility — ห้ามถอด key นี้ (ดู docstring ด้านบน)
    assert "detail" in body, (
        "หาย key 'detail' — frontend (parsed?.detail) และ n8n จะอ่านข้อความ error ไม่ได้"
    )
    return body


def test_unauthorized_returns_envelope():
    """401: endpoint ที่ต้องล็อกอิน เรียกโดยไม่มี token"""
    res = client.get("/api/users")
    body = _assert_envelope(res, 401, "UNAUTHORIZED")
    # detail เดิมของ HTTPException เป็น string ภาษาไทย → ต้องถูกยกไปเป็น message ด้วย
    assert body["detail"] == body["error"]["message"]


def test_not_found_route_returns_envelope():
    """404 ที่ Starlette สร้างเอง (ไม่ใช่ HTTPException ในโค้ดเรา) ต้องเข้า envelope ด้วย"""
    res = client.get("/api/no-such-endpoint-สำหรับเทสต์")
    _assert_envelope(res, 404, "NOT_FOUND")


def test_method_not_allowed_returns_envelope():
    """405: method ที่ route ไม่รองรับ"""
    res = client.delete("/api/stats")
    _assert_envelope(res, 405, "METHOD_NOT_ALLOWED")


def test_validation_error_keeps_pydantic_detail_list():
    """422: pydantic validation — detail ต้องยังเป็น list ของ errors เหมือน default FastAPI"""
    res = client.post("/api/tickets", json={"device_id": "X"})
    body = _assert_envelope(res, 422, "VALIDATION_ERROR")
    assert isinstance(body["detail"], list) and body["detail"], (
        f"detail ของ 422 ต้องเป็น list ของ validation errors: {body}"
    )
    assert all("loc" in item for item in body["detail"]), (
        f"แต่ละ error ต้องมี loc เพื่อให้ฟอร์มชี้ฟิลด์ที่ผิดได้: {body['detail']}"
    )


@pytest.mark.parametrize(
    "status_code, detail, expected_code",
    [
        (409, {"code": "DUPLICATE_OPEN_TICKET", "message": "ซ้ำ", "existing_ticket_no": "T-1"}, "DUPLICATE_OPEN_TICKET"),
        (409, "ข้อความอย่างเดียว", "CONFLICT"),
        (418, "status ที่ไม่อยู่ในตาราง", "HTTP_418"),
        (500, None, "INTERNAL_ERROR"),
    ],
)
def test_error_envelope_helper_maps_detail(status_code, detail, expected_code):
    """ตรวจตัวแปลง detail → envelope โดยตรง (ครอบเคส dict ที่มีฟิลด์เสริม)"""
    from app.main import _error_envelope

    body = _error_envelope(status_code, detail, "ข้อความสำรอง")

    assert body["success"] is False
    assert body["data"] is None
    assert body["detail"] == detail, "ต้องคง detail ต้นฉบับไว้ทุกกรณี"
    assert body["error"]["code"] == expected_code
    assert body["error"]["message"]

    if isinstance(detail, dict):
        # ฟิลด์เสริม (เช่น existing_ticket_no) ต้องไม่หายไปจาก error
        for key, value in detail.items():
            assert body["error"][key] == value
    elif detail is None:
        assert body["error"]["message"] == "ข้อความสำรอง"