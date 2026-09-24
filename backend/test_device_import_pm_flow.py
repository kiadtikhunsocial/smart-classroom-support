"""Integration checks for CSV preview/import and manually scheduled PM work."""
import uuid
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import select, text
from starlette.testclient import TestClient

from app.main import app, create_token
from app.models import AuditLog, Device, Organization, PMPlan, PMTask, SessionLocal, User


@pytest.fixture
def sample():
    db = SessionLocal()
    try:
        db.execute(text("SELECT 1 FROM pm_tasks LIMIT 1"))
    except Exception as exc:
        db.close()
        pytest.skip(f"PM database not available: {exc}")
    suffix = uuid.uuid4().hex[:8].upper()
    org = Organization(code=f"IM{suffix}", name="Import test school")
    db.add(org); db.flush()
    user = User(line_user_id=f"import-test-{suffix}", line_display_name="Import tester",
                role="admin", is_active=True)
    db.add(user); db.flush()
    plan = PMPlan(name=f"Test plan {suffix}", device_type="Camera", interval_days=90,
                  checklist='["ตรวจภาพ", "ตรวจสาย"]', is_active=True)
    db.add(plan); db.commit()
    ids = (org.id, user.id, plan.id, org.code)
    try:
        yield db, ids, {"Authorization": f"Bearer {create_token(user)}"}
    finally:
        db.rollback()
        db.execute(text("DELETE FROM audit_logs WHERE user_id = :user_id"), {"user_id": ids[1]})
        db.execute(text("DELETE FROM pm_tasks WHERE plan_id = :plan_id"), {"plan_id": ids[2]})
        db.execute(text("DELETE FROM pm_plans WHERE id = :plan_id"), {"plan_id": ids[2]})
        db.execute(text("DELETE FROM devices WHERE organization_id = :org_id"), {"org_id": ids[0]})
        db.execute(text("DELETE FROM users WHERE id = :user_id"), {"user_id": ids[1]})
        db.execute(text("DELETE FROM organizations WHERE id = :org_id"), {"org_id": ids[0]})
        db.commit(); db.close()


def test_import_preview_commit_duplicate_and_pm(sample):
    db, (org_id, _user_id, plan_id, code), headers = sample
    client = TestClient(app)
    device_id = f"{code[:8]}-CAM-01"
    csv_data = ("organization_code,device_id,device_type,brand,status\n"
                f"{code},{device_id},Camera,Example,active\n").encode()

    def upload(commit=False, data=csv_data):
        return client.post(f"/api/devices/import-csv?commit={str(commit).lower()}",
                           files={"file": ("devices.csv", data, "text/csv")}, headers=headers)

    preview = upload()
    assert preview.status_code == 200, preview.text
    assert preview.json()["valid"] == 1
    assert db.execute(select(Device).where(Device.device_id == device_id)).scalar_one_or_none() is None

    imported = upload(True)
    assert imported.status_code == 200, imported.text
    assert imported.json()["imported"] == 1
    db.rollback()  # close the snapshot opened by the preview assertion
    assert db.execute(select(Device).where(Device.device_id == device_id)).scalar_one_or_none(), imported.json()
    assert upload().json()["invalid"] == 1
    assert upload(True).status_code == 422

    due = (datetime.now(timezone.utc) + timedelta(days=2)).isoformat()
    created = client.post("/api/pm/tasks", json={"plan_id": plan_id, "device_id": device_id,
                                                   "due_date": due}, headers=headers)
    assert created.status_code == 201, created.text
    assert created.json()["task_no"].startswith("PM-")
    assert client.post("/api/pm/tasks", json={"plan_id": plan_id, "device_id": device_id,
                                               "due_date": due}, headers=headers).status_code == 409
    tasks = client.get("/api/pm/tasks", headers=headers).json()
    assert any(t["device_id"] == device_id and t["checklist"] == ["ตรวจภาพ", "ตรวจสาย"] for t in tasks)


def test_import_rejects_partial_file(sample):
    db, (org_id, _user_id, _plan_id, code), headers = sample
    client = TestClient(app)
    good_id = f"{code[:8]}-CAM-02"
    content = ("organization_code,device_id,device_type\n"
               f"{code},{good_id},Camera\n{code},{good_id},Camera\n").encode()
    response = client.post("/api/devices/import-csv?commit=true",
                           files={"file": ("devices.csv", content, "text/csv")}, headers=headers)
    assert response.status_code == 422
    db.rollback()
    assert db.execute(select(Device).where(Device.device_id == good_id)).scalar_one_or_none() is None
