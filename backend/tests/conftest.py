"""ทำให้ `import app...` ใช้ได้จากในโฟลเดอร์ tests โดยไม่ต้องติดตั้งแพ็กเกจ
และรวม fixture ที่ใช้ร่วมกันของเทสต์รายการใบงาน (ticket list / counts / compression)"""

import pathlib
import sys
import uuid

import pytest

BACKEND_ROOT = pathlib.Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))


@pytest.fixture
def client():
    from fastapi.testclient import TestClient
    from app.main import app
    with TestClient(app) as c:
        yield c


@pytest.fixture
def tag():
    """คำเฉพาะของเทสต์นี้ — ใส่ไว้ในหัวข้อใบงานทุกใบ แล้วค้นด้วยคำนี้
    เพื่อไม่ให้ข้อมูลที่มีอยู่แล้วในฐานข้อมูลมาปน"""
    return f"ZQ{uuid.uuid4().hex[:8].upper()}"


@pytest.fixture
def ticket_world(tag):
    """สองโรงเรียน: โรงเรียน A มีใบงาน 3 ใบ (new / pending / waiting_parts), โรงเรียน B มี 1 ใบ
    ผู้ใช้: super_admin (เห็นทุกโรงเรียน) และ admin_school ของโรงเรียน B"""
    from app.main import create_token
    from app.models import AuditLog, Device, Organization, RepairTicket, SessionLocal, User

    db = SessionLocal()
    created: dict = {"org_ids": [], "user_ids": [], "device_ids": [], "ticket_ids": []}
    try:
        org_a = Organization(code=f"A{tag}", name=f"โรงเรียนทดสอบ A {tag}")
        org_b = Organization(code=f"B{tag}", name=f"โรงเรียนทดสอบ B {tag}")
        db.add_all([org_a, org_b]); db.flush()
        created["org_ids"] = [org_a.id, org_b.id]

        admin = User(line_user_id=f"adm-{tag}", line_display_name="admin test", role="super_admin", is_active=True)
        school_admin = User(line_user_id=f"sch-{tag}", line_display_name="school test", role="admin_school",
                            organization_id=org_b.id, is_active=True)
        db.add_all([admin, school_admin]); db.flush()
        created["user_ids"] = [admin.id, school_admin.id]

        dev_a = Device(device_id=f"DA-{tag}", organization_id=org_a.id, device_type="Projector", status="active")
        dev_a2 = Device(device_id=f"DA2-{tag}", organization_id=org_a.id, device_type="Projector", status="active")
        dev_a3 = Device(device_id=f"DA3-{tag}", organization_id=org_a.id, device_type="Speaker", status="active")
        dev_b = Device(device_id=f"DB-{tag}", organization_id=org_b.id, device_type="Projector", status="active")
        db.add_all([dev_a, dev_a2, dev_a3, dev_b]); db.flush()
        created["device_ids"] = [d.device_id for d in (dev_a, dev_a2, dev_a3, dev_b)]

        rows = [
            (f"TK.A{tag}.1", org_a.id, dev_a.device_id, f"จอดับ 100%_x {tag}", "new"),
            (f"TK.A{tag}.2", org_a.id, dev_a2.device_id, f"จอดับ 100AAx {tag}", "pending"),
            (f"TK.A{tag}.3", org_a.id, dev_a3.device_id, f"ลำโพงไม่ดัง {tag}", "waiting_parts"),
            (f"TK.B{tag}.1", org_b.id, dev_b.device_id, f"เปิดไม่ติด {tag}", "new"),
        ]
        for ticket_id, org_id, device_id, title, status in rows:
            db.add(RepairTicket(ticket_id=ticket_id, organization_id=org_id, device_id=device_id,
                                title=title, status=status, priority="normal",
                                description="รายละเอียดทดสอบ " * 8))
        db.commit()
        created["ticket_ids"] = [r[0] for r in rows]

        yield {
            "admin_headers": {"Authorization": f"Bearer {create_token(admin)}"},
            "school_admin_headers": {"Authorization": f"Bearer {create_token(school_admin)}"},
            "ticket_ids": created["ticket_ids"],
        }
    finally:
        db.rollback()
        for t in db.query(RepairTicket).filter(RepairTicket.ticket_id.in_(created["ticket_ids"] or ["-"])):
            db.delete(t)
        db.flush()
        for d in db.query(Device).filter(Device.device_id.in_(created["device_ids"] or ["-"])):
            db.delete(d)
        db.flush()
        db.query(AuditLog).filter(AuditLog.user_id.in_(created["user_ids"] or [-1])).delete(synchronize_session=False)
        for u in db.query(User).filter(User.id.in_(created["user_ids"] or [-1])):
            db.delete(u)
        db.flush()
        for o in db.query(Organization).filter(Organization.id.in_(created["org_ids"] or [-1])):
            db.delete(o)
        db.commit()
        db.close()


@pytest.fixture
def admin_headers(ticket_world):
    return ticket_world["admin_headers"]


@pytest.fixture
def school_admin_headers(ticket_world):
    return ticket_world["school_admin_headers"]


@pytest.fixture
def ticket_ids(ticket_world):
    return ticket_world["ticket_ids"]
