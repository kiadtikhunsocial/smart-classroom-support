# -*- coding: utf-8 -*-
"""app/responses.py — API Response Standard (Blueprint §35)

รูปแบบมาตรฐาน::

    {"success": true,  "data": {...}, "meta": {...}}
    {"success": false, "data": null, "error": {"code": "NOT_FOUND", "message": "..."}}

**หมายเหตุการนำไปใช้:** endpoint เดิมใน ``main.py`` คืน object ดิบ และ frontend
(``src/api/client.ts``) อ่าน object ดิบอยู่ ถ้าเปิด success envelope ทั้งระบบทันที
หน้าเว็บจะพัง จึงทำเป็น opt-in:

* ใช้ ``ok()`` / ``fail()`` ใน endpoint ใหม่ได้เลย
* error envelope ทั้งระบบเปิดด้วย env ``API_ENVELOPE=1`` แล้วเรียก
  ``install_error_envelope(app)`` — ปิดไว้เป็นค่าเริ่มต้น

**ห้ามถอด key ``detail``** ออกจาก error body: frontend อ่าน ``parsed?.detail`` และ
``detail.code``, ``backend/test_line_create_ticket.py`` อ่าน ``res.json()["detail"]``
และ n8n ใช้ข้อความนั้นส่งกลับเข้า LINE (ดู ``test_error_envelope.py``)
"""

from __future__ import annotations

import os
from typing import Any, Optional

from fastapi import HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

# map HTTP status → error code มาตรฐาน (§35)
STATUS_CODE_MAP: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
    500: "INTERNAL_ERROR",
    502: "UPSTREAM_ERROR",
    503: "SERVICE_UNAVAILABLE",
}

# ข้อความสำรองเมื่อ detail ว่าง — ผู้ใช้ต้องไม่เห็นแค่ "HTTP 500"
FALLBACK_MESSAGES: dict[int, str] = {
    400: "คำขอไม่ถูกต้อง",
    401: "กรุณาเข้าสู่ระบบก่อนใช้งาน",
    403: "บัญชีนี้ไม่มีสิทธิ์ใช้งานส่วนนี้",
    404: "ไม่พบข้อมูลที่ต้องการ",
    405: "วิธีเรียก API นี้ไม่ถูกต้อง",
    409: "ข้อมูลขัดแย้งกับที่มีอยู่แล้ว",
    422: "ข้อมูลที่กรอกไม่ครบหรือไม่ถูกต้อง",
    429: "เรียกใช้งานถี่เกินไป กรุณารอสักครู่",
    500: "ระบบขัดข้อง กรุณาลองใหม่อีกครั้ง",
    502: "ระบบภายนอกไม่ตอบสนอง",
    503: "ระบบไม่พร้อมให้บริการชั่วคราว",
}


def envelope_enabled() -> bool:
    """เปิด error envelope ทั้งระบบหรือไม่ — ควบคุมด้วย env ``API_ENVELOPE``"""
    return os.getenv("API_ENVELOPE", "0").strip().lower() in ("1", "true", "yes", "on")


def error_code_for(status_code: int) -> str:
    """error code มาตรฐานของ HTTP status — status ที่ไม่อยู่ในตารางใช้ ``HTTP_<code>``"""
    return STATUS_CODE_MAP.get(status_code, f"HTTP_{status_code}")


def fallback_message(status_code: int) -> str:
    return FALLBACK_MESSAGES.get(status_code, f"เกิดข้อผิดพลาด (HTTP {status_code})")


def ok(data: Any = None, **meta: Any) -> dict:
    """ห่อผลลัพธ์สำเร็จ — ``meta`` ใส่ page/total/etc. ได้"""
    body: dict[str, Any] = {"success": True, "data": data}
    if meta:
        body["meta"] = meta
    return body


def fail(code: str, message: str, details: Any = None) -> dict:
    """ห่อผลลัพธ์ผิดพลาด (ไม่ตั้ง HTTP status — ใช้คู่กับ ``ApiError``)

    คง key ``detail`` ไว้ให้ client เดิมอ่านได้เหมือน HTTPException ปกติ
    """
    error: dict[str, Any] = {"code": code, "message": message}
    if details is not None:
        error["details"] = details
    return {
        "success": False,
        "data": None,
        "error": error,
        "detail": details if details is not None else message,
    }


class ApiError(HTTPException):
    """HTTPException ที่พก error code ของ §35 มาด้วย

    ตัวจัดการ error ใน ``main.py`` อ่าน ``detail`` เป็น dict อยู่แล้ว จึงส่ง
    ``{"code": ..., "message": ...}`` เข้าไปเพื่อให้ code ถูกยกไปที่ ``error.code``
    """

    def __init__(
        self,
        status_code: int,
        code: Optional[str] = None,
        message: Optional[str] = None,
        details: Any = None,
        headers: Optional[dict[str, str]] = None,
    ) -> None:
        resolved_code = code or error_code_for(status_code)
        resolved_message = message or fallback_message(status_code)
        detail: dict[str, Any] = {"code": resolved_code, "message": resolved_message}
        if details is not None:
            detail["details"] = details
        super().__init__(status_code=status_code, detail=detail, headers=headers)
        self.code = resolved_code
        self.message = resolved_message
        self.details = details


def build_error_body(status_code: int, detail: Any) -> dict:
    """แปลง detail ของ HTTPException → error envelope §35 โดยคง detail ต้นฉบับ

    * detail เป็น dict → ยก ``code``/``message`` ขึ้นมา ฟิลด์อื่นแนบไว้ใน ``error``
    * detail เป็น str  → ใช้เป็น message, code มาจากตาราง status
    * detail เป็น list (pydantic 422) หรือ None → ใช้ข้อความสำรอง
    """
    code = error_code_for(status_code)
    message = fallback_message(status_code)
    extra: dict[str, Any] = {}

    if isinstance(detail, dict):
        raw_code = detail.get("code")
        raw_message = detail.get("message")
        if isinstance(raw_code, str) and raw_code.strip():
            code = raw_code.strip()
        if isinstance(raw_message, str) and raw_message.strip():
            message = raw_message.strip()
        extra = {k: v for k, v in detail.items() if k not in ("code", "message")}
    elif isinstance(detail, str) and detail.strip():
        message = detail.strip()

    error: dict[str, Any] = {"code": code, "message": message}
    error.update(extra)
    return {"success": False, "data": None, "error": error, "detail": detail}


def install_error_envelope(app) -> bool:
    """ติดตั้ง exception handler ให้ error ทุกชนิดออกเป็น envelope §35

    คืน ``False`` และไม่ทำอะไรเมื่อ ``API_ENVELOPE`` ปิดอยู่ เพื่อให้ import
    โมดูลนี้ปลอดภัยแม้ยังไม่ได้เปิดใช้
    """
    if not envelope_enabled():
        return False

    @app.exception_handler(StarletteHTTPException)
    async def _http_error(request: Request, exc: StarletteHTTPException):  # noqa: ARG001
        return JSONResponse(
            status_code=exc.status_code,
            content=build_error_body(exc.status_code, exc.detail),
            headers=getattr(exc, "headers", None),
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_error(request: Request, exc: RequestValidationError):  # noqa: ARG001
        # แปลง errors ให้ JSON serialize ได้เสมอ (ctx อาจมี Exception object)
        errors: list[dict[str, Any]] = []
        for err in exc.errors():
            item = {k: v for k, v in err.items() if k != "ctx"}
            ctx = err.get("ctx")
            if ctx:
                item["ctx"] = {k: str(v) for k, v in ctx.items()}
            item["loc"] = list(item.get("loc", ()))
            errors.append(item)
        return JSONResponse(status_code=422, content=build_error_body(422, errors))

    return True