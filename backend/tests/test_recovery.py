"""Round-trip recovery against the configured PostgreSQL test database."""
import uuid

from fastapi.testclient import TestClient
from sqlalchemy import select

from app.main import app, create_token
from app.models import (AuditLog, DeletedRecord, Device, Organization, RepairTicket,
                        ScanLog, SessionLocal, TicketAttachment, TicketComment, TicketUpdate, User)


def test_ticket_and_device_deletion_can_be_restored():
    tag = uuid.uuid4().hex[:10].upper()
    device_id = f"REC-{tag}"
    ticket_id = f"TK.REC.{tag}"
    db = SessionLocal()
    org_id = user_id = None
    try:
        org = Organization(code=f"REC{tag}", name=f"Recovery test {tag}")
        db.add(org); db.flush(); org_id = org.id
        user = User(line_user_id=f"recovery-{tag}", line_display_name="Recovery test",
                    role="super_admin", is_active=True)
        db.add(user); db.flush(); user_id = user.id
        db.add(Device(device_id=device_id, organization_id=org_id, device_type="Other", status="active"))
        db.flush()
        db.add(ScanLog(device_id=device_id, user_agent="Recovery test"))
        ticket = RepairTicket(ticket_id=ticket_id, organization_id=org_id, device_id=device_id,
                              title="จอไม่มีภาพ", status="new", priority="normal")
        db.add(ticket); db.flush()
        db.add(TicketUpdate(ticket_id=ticket.id, to_status="new", note="สร้างใบงาน"))
        db.add(TicketComment(ticket_id=ticket_id, note="ตรวจอุปกรณ์", author_name="เจ้าหน้าที่"))
        db.add(TicketAttachment(ticket_id=ticket_id, file_url="https://example.invalid/recovery-test.png"))
        db.commit()

        headers = {"Authorization": f"Bearer {create_token(user)}"}
        with TestClient(app) as client:
            assert client.delete(f"/api/tickets/{ticket_id}", headers=headers).status_code == 200
            assert client.delete(f"/api/devices/{device_id}", headers=headers).status_code == 200
            rows = client.get("/api/deleted-records", headers=headers).json()
            device_bin = next(row for row in rows if row["entity_id"] == device_id)
            ticket_bin = next(row for row in rows if row["entity_id"] == ticket_id)
            # Ticket cannot be restored until its device exists again.
            assert client.post(f"/api/deleted-records/{ticket_bin['id']}/restore", headers=headers).status_code == 409
            assert client.post(f"/api/deleted-records/{device_bin['id']}/restore", headers=headers).status_code == 200
            assert client.post(f"/api/deleted-records/{ticket_bin['id']}/restore", headers=headers).status_code == 200
            assert client.get(f"/api/tickets/{ticket_id}", headers=headers).status_code == 200

        db.expire_all()
        restored = db.execute(select(RepairTicket).where(RepairTicket.ticket_id == ticket_id)).scalar_one()
        assert db.execute(select(TicketUpdate).where(TicketUpdate.ticket_id == restored.id)).scalars().first() is not None
        assert db.execute(select(TicketComment).where(TicketComment.ticket_id == ticket_id)).scalars().first() is not None
        assert db.execute(select(TicketAttachment).where(TicketAttachment.ticket_id == ticket_id)).scalars().first() is not None
        assert db.execute(select(ScanLog).where(ScanLog.device_id == device_id)).scalars().first() is not None
    finally:
        db.rollback()
        # Test-only cleanup, scoped to the unique generated IDs.
        ticket = db.execute(select(RepairTicket).where(RepairTicket.ticket_id == ticket_id)).scalar_one_or_none()
        if ticket:
            for row in db.execute(select(TicketUpdate).where(TicketUpdate.ticket_id == ticket.id)).scalars(): db.delete(row)
            for row in db.execute(select(TicketComment).where(TicketComment.ticket_id == ticket_id)).scalars(): db.delete(row)
            for row in db.execute(select(TicketAttachment).where(TicketAttachment.ticket_id == ticket_id)).scalars(): db.delete(row)
            db.delete(ticket)
            db.flush()
        for row in db.execute(select(DeletedRecord).where(DeletedRecord.entity_id.in_([ticket_id, device_id]))).scalars(): db.delete(row)
        for row in db.execute(select(AuditLog).where(AuditLog.entity_id.in_([ticket_id, device_id]))).scalars(): db.delete(row)
        device = db.execute(select(Device).where(Device.device_id == device_id)).scalar_one_or_none()
        for row in db.execute(select(ScanLog).where(ScanLog.device_id == device_id)).scalars(): db.delete(row)
        if device: db.delete(device); db.flush()
        if user_id:
            row = db.get(User, user_id)
            if row: db.delete(row)
        if org_id:
            row = db.get(Organization, org_id)
            if row: db.delete(row)
        db.commit()
        db.close()
