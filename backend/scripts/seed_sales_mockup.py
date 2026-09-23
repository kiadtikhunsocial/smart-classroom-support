"""Add labelled, idempotent sales examples to the local demo database only."""

import os
import sys
from decimal import Decimal

from sqlalchemy import select

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.models import SalesLead, SalesRecord, SessionLocal, init_db  # noqa: E402
from demo_safety import require_local_demo_database  # noqa: E402


EXAMPLES = (
    ("[DEMO] โรงเรียนบ้านหนองปลาไหล", "Iwa AiBoard 86", "quoted", Decimal("189000.00")),
    ("[DEMO] โรงเรียนอนุบาลเมืองใหม่", "Smart Quiz", "interested", Decimal("24000.00")),
    ("[DEMO] โรงเรียนวัดราษฎร์บำรุง", "Phonics Hero", "won", Decimal("38500.00")),
    ("[DEMO] โรงเรียนเทศบาลสองพี่น้อง", "Interactive Display", "requested", Decimal("125000.00")),
    ("[DEMO] โรงเรียนสาธิตวิทยาลัยครู", "Iwa AiBoard 75", "reviewing", Decimal("159000.00")),
)


def main() -> None:
    require_local_demo_database()
    init_db()
    db = SessionLocal()
    created_leads = 0
    created_records = 0
    try:
        for name, product, status, amount in EXAMPLES:
            lead = db.execute(select(SalesLead).where(SalesLead.name == name, SalesLead.source == "DEMO")).scalar_one_or_none()
            if lead is None:
                lead = SalesLead(
                    name=name, phone=None, interest=f"ข้อมูลตัวอย่าง: {product}",
                    products=product, source="DEMO", status="new",
                    note="ข้อมูลตัวอย่างเพื่อทดสอบหน้าจอ — ห้ามติดต่อหรือส่งแจ้งเตือน",
                )
                db.add(lead)
                db.flush()
                created_leads += 1
            kind = "payment_request" if status in {"requested", "reviewing"} else "deal"
            record = db.execute(select(SalesRecord).where(
                SalesRecord.lead_id == lead.id, SalesRecord.kind == kind, SalesRecord.product == product,
            )).scalar_one_or_none()
            if record is None:
                db.add(SalesRecord(
                    lead_id=lead.id, kind=kind, product=product,
                    quantity=1, amount_thb=amount, status=status,
                    note="ข้อมูลตัวอย่าง local เท่านั้น — ไม่ใช่รายการเงินจริง",
                ))
                created_records += 1
        db.commit()
        print(f"Local sales mockup ready: {created_leads} leads, {created_records} records added")
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
