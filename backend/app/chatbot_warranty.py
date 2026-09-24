"""LINE warranty lookup: exact product/device identifier, no AI-generated facts."""
import re
from datetime import datetime, timezone

from sqlalchemy import select, func

from app.models import Device, SessionLocal
from app import pm_rules

_INTENT = re.compile(r"ประกัน|warranty|เคลม", re.IGNORECASE)
_CODE = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9][A-Za-z0-9_-]{4,63}(?![A-Za-z0-9_-])")
_IGNORED = {"warranty", "device", "serial", "สินค้า", "ประกัน"}


def is_warranty_question(message: str) -> bool:
    return bool(_INTENT.search(message or ""))


def extract_code(message: str) -> str | None:
    for match in _CODE.finditer(message or ""):
        candidate = match.group().strip()
        if candidate.lower() not in _IGNORED:
            return candidate
    return None


def warranty_answer(code: str) -> str:
    """Return only warranty fields; never share owner, room, QR token or internal notes."""
    db = SessionLocal()
    try:
        normalized = code.strip().upper()
        # Exact match only. Do not perform fuzzy lookup on customer identifiers.
        device = db.execute(select(Device).where(
            (func.upper(Device.device_id) == normalized) |
            (func.upper(Device.serial_number) == normalized)
        )).scalars().first()
        if device is None:
            return "ไม่พบรหัสนี้ในทะเบียนอุปกรณ์ค่ะ กรุณาตรวจรหัสอุปกรณ์หรือ Serial บนสติกเกอร์อีกครั้ง หากยังไม่พบให้เจ้าหน้าที่ช่วยตรวจเอกสารประกันนะคะ"
        until = device.warranty_until
        if until is None:
            status = "ยังไม่มีวันสิ้นสุดประกันในระบบ"
            date_text = "ไม่ระบุ"
        else:
            if until.tzinfo is None:
                until = until.replace(tzinfo=timezone.utc)
            days = (until - datetime.now(timezone.utc)).days
            status = ("หมดประกันแล้ว" if days < 0 else
                      "ใกล้หมดประกัน" if days <= pm_rules.WARRANTY_WARN_DAYS else "อยู่ในระยะประกัน")
            date_text = until.astimezone(timezone.utc).strftime("%d/%m/%Y")
        return (f"ตรวจจากทะเบียนอุปกรณ์รหัส {device.device_id} ({device.device_type}) ค่ะ\n"
                f"สถานะ: {status}\nวันสิ้นสุดประกันที่บันทึก: {date_text}\n"
                "ข้อมูลนี้อ้างอิงทะเบียนในระบบ หากต้องการยืนยันสิทธิ์เคลมจริง กรุณาให้เจ้าหน้าที่ตรวจใบซื้อและเงื่อนไขผู้ขายอีกครั้งค่ะ")
    finally:
        db.close()
