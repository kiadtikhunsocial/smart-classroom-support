"""Clearly labelled, fictional customer and sales examples.

These rows have no contact details and must never trigger LINE or Sheet sync.
They are deliberately separate from real WEB/LINE leads.
"""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import SalesLead, SalesRecord


EXAMPLES = (
    ("[DEMO] โรงเรียนบ้านหนองปลาไหล", "Iwa AiBoard 86", "deal", "quoted", "189000.00", "contacted"),
    ("[DEMO] โรงเรียนอนุบาลเมืองใหม่", "Smart Quiz", "deal", "interested", "24000.00", "new"),
    ("[DEMO] โรงเรียนวัดราษฎร์บำรุง", "Phonics Hero", "deal", "won", "38500.00", "closed"),
    ("[DEMO] โรงเรียนเทศบาลสองพี่น้อง", "Interactive Display", "payment_request", "requested", "125000.00", "contacted"),
    ("[DEMO] โรงเรียนสาธิตวิทยาลัยครู", "Iwa AiBoard 75", "payment_request", "reviewing", "159000.00", "contacted"),
    ("[DEMO] ศูนย์การเรียนรู้ชุมชน", "Computer AIO", "deal", "interested", "92000.00", "new"),
    ("[DEMO] โรงเรียนบ้านคลองใหม่", "Projector", "deal", "lost", "46000.00", "closed"),
    ("[DEMO] วิทยาลัยเทคนิคเมืองเหนือ", "Iwa AiBoard 86", "deal", "quoted", "378000.00", "contacted"),
    ("[DEMO] โรงเรียนบ้านดอนทอง", "Smart Quiz", "payment_request", "requested", "36000.00", "new"),
    ("[DEMO] ศูนย์พัฒนาเด็กเล็กบ้านสวน", "Phonics Hero", "deal", "won", "29000.00", "closed"),
)


def seed_demo_sales(db: Session) -> tuple[int, int]:
    """Idempotently insert example rows in the caller's transaction."""
    created_leads = created_records = 0
    for name, product, kind, status, amount, lead_status in EXAMPLES:
        lead = db.execute(select(SalesLead).where(
            SalesLead.name == name, SalesLead.source == "DEMO",
        )).scalar_one_or_none()
        if lead is None:
            lead = SalesLead(
                name=name, phone=None, interest=f"ข้อมูลตัวอย่าง: {product}",
                products=product, source="DEMO", status=lead_status,
                note="ข้อมูลสมมติสำหรับทดลองหน้าจอ — ไม่ใช่ลูกค้าจริง ห้ามติดต่อ",
            )
            db.add(lead)
            db.flush()
            created_leads += 1
        record = db.execute(select(SalesRecord).where(
            SalesRecord.lead_id == lead.id,
            SalesRecord.kind == kind,
            SalesRecord.product == product,
        )).scalar_one_or_none()
        if record is None:
            db.add(SalesRecord(
                lead_id=lead.id, kind=kind, product=product,
                quantity=1, amount_thb=Decimal(amount), status=status,
                note="[DEMO] ข้อมูลสมมติ ไม่ใช่รายการเงินจริงหรือการรับชำระเงิน",
            ))
            created_records += 1
    return created_leads, created_records
