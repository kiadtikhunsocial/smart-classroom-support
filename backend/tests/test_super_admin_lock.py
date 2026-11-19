"""Super Admin = ผู้ดูแลสูงสุด: คนอื่นแก้/ลบไม่ได้ (ยกเว้น Owner), เจ้าของบัญชีแก้ได้แค่ข้อมูลส่วนตัว"""
import pytest

from app.models import AuditLog, SessionLocal, User


@pytest.fixture
def people(tag):
    from app.main import create_token
    with SessionLocal() as s:
        sa1 = User(line_user_id=f"sa1-{tag}", line_display_name="SA1", role="super_admin", is_active=True)
        sa2 = User(line_user_id=f"sa2-{tag}", line_display_name="SA2", role="super_admin", is_active=True)
        adm = User(line_user_id=f"adm-{tag}", line_display_name="ADM", role="admin", is_active=True)
        own = User(line_user_id=f"own-{tag}", line_display_name="OWN", role="owner", is_active=True)
        s.add_all([sa1, sa2, adm, own]); s.commit()
        ids = [sa1.id, sa2.id, adm.id, own.id]
        h = {u.line_display_name: {"Authorization": f"Bearer {create_token(u)}"} for u in (sa1, sa2, adm, own)}
    yield {"sa1": ids[0], "sa2": ids[1], "adm": ids[2], "own": ids[3], "h": h}
    with SessionLocal() as s:
        s.query(AuditLog).filter(AuditLog.user_id.in_(ids)).delete(synchronize_session=False)
        s.query(AuditLog).filter(AuditLog.entity_id.in_([str(i) for i in ids])).delete(synchronize_session=False)
        s.query(User).filter(User.id.in_(ids)).delete(synchronize_session=False)
        s.commit()


def test_other_admins_cannot_edit_or_delete_a_super_admin(client, people):
    p = people
    for who in ("SA2", "ADM"):
        r = client.patch(f"/api/users/{p['sa1']}", json={"line_display_name": "x"}, headers=p["h"][who])
        assert r.status_code == 403, (who, r.text)
        assert client.delete(f"/api/users/{p['sa1']}", headers=p["h"][who]).status_code == 403


def test_super_admin_edits_own_profile_but_not_own_role_or_status(client, people):
    p = people
    ok = client.patch(f"/api/users/{p['sa1']}", headers=p["h"]["SA1"],
                      json={"line_display_name": "SA1 ใหม่", "role": "super_admin", "is_active": True})
    assert ok.status_code == 200, ok.text
    assert client.patch(f"/api/users/{p['sa1']}", json={"role": "admin"}, headers=p["h"]["SA1"]).status_code == 403
    assert client.patch(f"/api/users/{p['sa1']}", json={"is_active": False}, headers=p["h"]["SA1"]).status_code == 403


def test_owner_can_still_manage_super_admins(client, people):
    p = people
    r = client.patch(f"/api/users/{p['sa2']}", json={"is_active": False}, headers=p["h"]["OWN"])
    assert r.status_code == 200, r.text
