"""Customer-originated LINE sales signals; never marks a deal won or payment received."""
import re
import logging
from sqlalchemy import select

from app.models import SalesLead, SalesRecord, SessionLocal

logger = logging.getLogger(__name__)


def record_line_interest(lead_id: int, product: str) -> bool:
    product = (product or "").strip()[:255]
    if re.search(r"(?:\d[ -]?){12,}", product):
        return False
    if not product:
        return False
    db = SessionLocal()
    try:
        lead = db.get(SalesLead, lead_id)
        if not lead or lead.source == "DEMO":
            return False
        existing = db.execute(select(SalesRecord.id).where(
            SalesRecord.lead_id == lead_id, SalesRecord.kind == "deal",
            SalesRecord.product == product, SalesRecord.status.in_(["interested", "quoted", "won"]),
        ).limit(1)).scalar_one_or_none()
        if existing:
            return False
        record = SalesRecord(lead_id=lead_id, kind="deal", product=product,
                             quantity=1, status="interested", note="ลูกค้ายืนยันความสนใจผ่าน LINE")
        db.add(record); db.commit(); db.refresh(record)
        try:
            from app.main import _sync_sales_record_async
            _sync_sales_record_async(record, lead.name or "", lead.source)
        except Exception:
            logger.exception("Could not queue sales interest Sheet sync")
        return True
    finally:
        db.close()


def request_line_payment(user_id: str, product: str) -> str:
    """Create an unverified request tied to this LINE user's lead, not an actual payment."""
    product = (product or "").strip()[:255]
    if re.search(r"(?:\d[ -]?){12,}", product):
        return "เพื่อความปลอดภัย อย่าส่งเลขบัตรหรือข้อมูลบัญชีในแชทนะคะ กรุณาบอกเฉพาะชื่อสินค้า/บริการ"
    db = SessionLocal()
    try:
        lead = db.execute(select(SalesLead).where(SalesLead.user_id == user_id,
                                                 SalesLead.source != "DEMO")
                          .order_by(SalesLead.id.desc()).limit(1)).scalar_one_or_none()
        if not lead:
            from app.chatbot_helpers import customer_signup_link
            return "ก่อนรับคำขอชำระเงิน กรุณาลงทะเบียนข้อมูลติดต่อกับทีมขายก่อนนะคะ: " + customer_signup_link(user_id, product, [product])
        if not product:
            return "ขอชื่อสินค้า/บริการที่ต้องการชำระเงินก่อนนะคะ เพื่อส่งให้เจ้าหน้าที่ตรวจสอบ"
        existing = db.execute(select(SalesRecord.id).where(
            SalesRecord.lead_id == lead.id, SalesRecord.kind == "payment_request",
            SalesRecord.product == product, SalesRecord.status.in_(["requested", "reviewing"]),
        ).limit(1)).scalar_one_or_none()
        if existing:
            return "มีคำขอชำระเงินรายการนี้รอเจ้าหน้าที่ตรวจสอบอยู่แล้วค่ะ ไม่ต้องส่งซ้ำ และอย่าส่งข้อมูลบัตรหรือบัญชีในแชทนะคะ"
        record = SalesRecord(lead_id=lead.id, kind="payment_request", product=product,
                             quantity=1, status="requested", note="คำขอจาก LINE; ยังไม่ยืนยันการชำระเงิน")
        db.add(record); db.commit(); db.refresh(record)
        try:
            from app.main import _sync_sales_record_async
            _sync_sales_record_async(record, lead.name or "", lead.source)
        except Exception:
            logger.exception("Could not queue payment request Sheet sync")
        try:
            from app.line_bot import LINE_GROUP_ID, send_line_push
            if LINE_GROUP_ID:
                send_line_push(LINE_GROUP_ID, f"คำขอชำระเงิน #{record.id} จาก {lead.name or 'ลูกค้า'}: {product} — รอเจ้าหน้าที่ตรวจสอบ (ยังไม่ชำระ)")
        except Exception:
            logger.exception("Could not notify staff of LINE payment request")
        return "รับคำขอชำระเงินแล้วค่ะ เจ้าหน้าที่จะตรวจสอบและติดต่อกลับผ่านช่องทางที่คุณลงทะเบียนไว้ รายการนี้ยังไม่ใช่การชำระเงินสำเร็จ และไม่ต้องส่งข้อมูลบัตรหรือบัญชีในแชทนะคะ"
    finally:
        db.close()
