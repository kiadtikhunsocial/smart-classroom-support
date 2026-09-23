# -*- coding: utf-8 -*-
"""Google Sheet connector — ส่งข้อมูลการสมัครสมาชิกไปต่อท้ายชีต

ใช้เฉพาะไลบรารีที่โปรเจกต์มีอยู่แล้ว (google-auth + httpx) จึงไม่ต้องเพิ่ม
dependency ใหม่: เซ็น JWT ของ service account ด้วย google-auth แล้วแลกเป็น
access token กับ OAuth endpoint ผ่าน httpx

ตั้งค่าด้วย environment variables
  GOOGLE_SHEET_ID               id ของสเปรดชีต (ส่วนกลางของ URL /d/<id>/edit)
  GOOGLE_SHEET_RANGE            ช่วงที่จะ append (ค่าเริ่มต้น "Members!A1")
  GOOGLE_SERVICE_ACCOUNT_JSON   เนื้อ JSON ของ service account (เหมาะกับ Railway)
  GOOGLE_SERVICE_ACCOUNT_FILE   หรือพาธไฟล์ JSON แทน

ต้องแชร์สเปรดชีตให้อีเมล client_email ของ service account แบบ Editor ก่อน

ถ้าไม่ได้ตั้งค่า ทุกฟังก์ชันจะไม่ทำอะไรและคืน False — การสมัครสมาชิกยังทำงานได้
ปกติ (Sheet เป็นช่องทางรายงานสำรอง ไม่ใช่แหล่งข้อมูลหลัก)
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any, Optional
from urllib.parse import quote

import httpx

logger = logging.getLogger(__name__)

SCOPE = "https://www.googleapis.com/auth/spreadsheets"
TOKEN_URI_DEFAULT = "https://oauth2.googleapis.com/token"
SHEETS_API = "https://sheets.googleapis.com/v4/spreadsheets"
DEFAULT_RANGE = "Members!A1"
DEFAULT_LEAD_RANGE = "Leads!A1"
HTTP_TIMEOUT = 10.0

#: หัวตารางที่คาดหวังในชีต (แถวแรก) — เรียงตรงกับ _membership_values()
MEMBERSHIP_HEADER: tuple[str, ...] = (
    "วันที่สมัคร",
    "เลขคำขอ",
    "ชื่อผู้ใช้",
    "ชื่อ-นามสกุล",
    "อีเมล",
    "โทรศัพท์",
    "รหัสหน่วยงาน",
    "บทบาทที่ขอ",
    "สถานะ",
    "หมายเหตุ",
)

_lock = threading.Lock()
_token_cache: dict[str, Any] = {"access_token": None, "expires_at": 0.0}


# ---------------------------------------------------------------------------
# การตั้งค่า
# ---------------------------------------------------------------------------

def _env(name: str) -> Optional[str]:
    return (os.environ.get(name) or "").strip() or None


def _sheet_id() -> Optional[str]:
    return _env("GOOGLE_SHEET_ID")


def _sheet_range() -> str:
    return _env("GOOGLE_SHEET_RANGE") or DEFAULT_RANGE


def _service_account_info() -> Optional[dict]:
    """อ่าน service account จาก env (JSON ตรง ๆ หรือพาธไฟล์) — คืน None ถ้าไม่ตั้งค่า/ไม่ถูกต้อง"""
    raw = _env("GOOGLE_SERVICE_ACCOUNT_JSON")
    if not raw:
        path = _env("GOOGLE_SERVICE_ACCOUNT_FILE")
        if not path:
            return None
        try:
            with open(path, "r", encoding="utf-8") as fh:
                raw = fh.read()
        except OSError as exc:
            # ไม่ log เนื้อไฟล์/พาธเต็ม — กันความลับรั่วลง log
            logger.warning("Google Sheet: อ่านไฟล์ service account ไม่ได้ (%s)", exc.__class__.__name__)
            return None
    try:
        info = json.loads(raw)
    except ValueError:
        logger.warning("Google Sheet: ค่า service account ไม่ใช่ JSON ที่ถูกต้อง")
        return None
    if not isinstance(info, dict) or not info.get("client_email") or not info.get("private_key"):
        logger.warning("Google Sheet: service account ไม่มี client_email หรือ private_key")
        return None
    return info


def is_configured() -> bool:
    """True เมื่อมีทั้ง sheet id และ service account ที่อ่านได้"""
    return bool(_sheet_id()) and _service_account_info() is not None


# ---------------------------------------------------------------------------
# OAuth (service account → access token)
# ---------------------------------------------------------------------------

def _access_token() -> Optional[str]:
    info = _service_account_info()
    if not info:
        return None
    now = time.time()
    with _lock:
        cached = _token_cache.get("access_token")
        if cached and float(_token_cache.get("expires_at") or 0) - 60 > now:
            return cached
        try:
            from google.auth import crypt
            from google.auth import jwt as google_jwt
        except ImportError:
            logger.warning("Google Sheet: ไม่พบไลบรารี google-auth")
            return None
        token_uri = info.get("token_uri") or TOKEN_URI_DEFAULT
        try:
            signer = crypt.RSASigner.from_service_account_info(info)
            assertion = google_jwt.encode(signer, {
                "iss": info["client_email"],
                "scope": SCOPE,
                "aud": token_uri,
                "iat": int(now),
                "exp": int(now) + 3600,
            })
            if isinstance(assertion, bytes):
                assertion = assertion.decode("ascii")
            resp = httpx.post(
                token_uri,
                timeout=HTTP_TIMEOUT,
                data={
                    "grant_type": "urn:ietf:params:oauth:grant-type:jwt-bearer",
                    "assertion": assertion,
                },
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as exc:
            # ข้อความ error ของ OAuth อาจมีส่วนของ assertion — log แค่ชนิดข้อผิดพลาด
            logger.warning("Google Sheet: ขอ access token ไม่สำเร็จ (%s)", exc.__class__.__name__)
            return None
        token = data.get("access_token") if isinstance(data, dict) else None
        if not token:
            logger.warning("Google Sheet: ไม่ได้รับ access token จาก Google")
            return None
        try:
            ttl = float(data.get("expires_in") or 3600)
        except (TypeError, ValueError):
            ttl = 3600.0
        _token_cache["access_token"] = token
        _token_cache["expires_at"] = now + ttl
        return token


# ---------------------------------------------------------------------------
# เขียนข้อมูลลงชีต
# ---------------------------------------------------------------------------

def append_row(values: list[Any], sheet_range: Optional[str] = None) -> bool:
    """ต่อท้าย 1 แถวในชีต — คืน False ถ้าไม่ได้ตั้งค่าไว้หรือเรียก API ไม่สำเร็จ"""
    sheet_id = _sheet_id()
    if not sheet_id:
        return False
    token = _access_token()
    if not token:
        return False
    target = sheet_range or _sheet_range()
    url = f"{SHEETS_API}/{quote(sheet_id, safe='')}/values/{quote(target, safe='')}:append"
    row = ["" if v is None else str(v) for v in values]
    try:
        resp = httpx.post(
            url,
            timeout=HTTP_TIMEOUT,
            params={"valueInputOption": "USER_ENTERED", "insertDataOption": "INSERT_ROWS"},
            headers={"Authorization": f"Bearer {token}"},
            json={"values": [row]},
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.warning("Google Sheet: append ไม่สำเร็จ (HTTP %s)", exc.response.status_code)
        return False
    except Exception as exc:
        logger.warning("Google Sheet: append ไม่สำเร็จ (%s)", exc.__class__.__name__)
        return False
    return True


def _iso(value: Any) -> str:
    return value.isoformat() if hasattr(value, "isoformat") else ("" if value is None else str(value))


def _membership_values(application: Any) -> list[Any]:
    """แปลงคำขอสมัครสมาชิกเป็นแถวของชีต (ห้ามใส่ password_hash)"""
    return [
        _iso(getattr(application, "created_at", None)),
        getattr(application, "id", None),
        getattr(application, "username", None),
        getattr(application, "full_name", None),
        getattr(application, "email", None),
        getattr(application, "phone", None),
        getattr(application, "organization_code", None),
        getattr(application, "requested_role", None),
        getattr(application, "status", None),
        getattr(application, "note", None),
    ]


def append_membership_row(application: Any, sheet_range: Optional[str] = None) -> bool:
    """ส่งคำขอสมัครสมาชิก 1 รายการขึ้นชีต — ไม่โยน exception ออกมา"""
    if not _sheet_id():
        return False
    return append_row(_membership_values(application), sheet_range=sheet_range)


# ---------------------------------------------------------------------------
# Sales lead (ผู้สนใจซื้อ / ขอให้ติดต่อกลับ จาก LINE)
# ---------------------------------------------------------------------------

#: หัวตารางแท็บ Leads (แถวแรก) — เรียงตรงกับ _lead_values()
LEAD_HEADER: tuple[str, ...] = (
    "วันที่",
    "เลข Lead",
    "LINE user id",
    "ชื่อผู้สนใจ",
    "โทรศัพท์",
    "เรื่องที่สนใจ",
    "สินค้า",
    "ช่องทาง",
    "สถานะ",
    "หมายเหตุ",
)


def _lead_range() -> str:
    """ช่วงที่ append lead — ตั้ง GOOGLE_SHEET_LEAD_RANGE ได้ (ค่าเริ่มต้น Leads!A1)"""
    return _env("GOOGLE_SHEET_LEAD_RANGE") or DEFAULT_LEAD_RANGE


def _lead_values(lead: dict) -> list[Any]:
    """แปลง lead (dict) เป็นแถวของชีต — ถ้าไม่ส่ง created_at มาจะใช้เวลาปัจจุบัน"""
    products = lead.get("products")
    if isinstance(products, (list, tuple, set)):
        products = ", ".join(str(p) for p in products if p)
    created_at = lead.get("created_at") or datetime.now(timezone.utc)
    return [
        _iso(created_at),
        lead.get("id"),
        lead.get("user_id"),
        lead.get("name"),
        lead.get("phone"),
        (lead.get("interest") or "")[:200],
        (products or "")[:500],
        lead.get("source") or "LINE",
        lead.get("status") or "new",
        (lead.get("note") or "")[:500],
    ]


def append_lead_row(lead: dict, sheet_range: Optional[str] = None) -> bool:
    """ส่ง sales lead 1 รายการขึ้นชีต — ไม่โยน exception ออกมา"""
    if not _sheet_id():
        return False
    return append_row(_lead_values(lead), sheet_range=sheet_range or _lead_range())