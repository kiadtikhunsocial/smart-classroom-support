import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import { ASSIGNABLE_ROLES, ROLE_LABEL_FULL_TH, LEGACY_ROLE_LABEL_TH } from '../roleLabels';

const ROLES = ASSIGNABLE_ROLES;

// ป้ายชื่อบทบาท: ใช้แหล่งกลางใน roleLabels.ts แทนแผนที่เดิมในไฟล์นี้ที่ drift ไปแล้ว
// (ของเดิมตั้ง super_admin = 'ผู้ดูแลบริษัท' ซ้ำกับ admin)
// บทบาทที่เลิกใช้ยังคงป้ายไว้ เพื่อให้บัญชีเก่าในตารางไม่แสดงเป็นรหัสดิบ
// แต่เลือกใหม่ไม่ได้ เพราะไม่อยู่ใน ASSIGNABLE_ROLES
const ROLE_LABELS: Record<string, string> = { ...ROLE_LABEL_FULL_TH, ...LEGACY_ROLE_LABEL_TH };

// บทบาทที่ผู้ใช้ปัจจุบันเลือกได้เมื่อสร้าง/แก้ไข user (จำกัดตามสิทธิ์)
function creatableRoles(myRole?: string): string[] {
  if (myRole === 'admin_school') return ['it_support']; // ผู้ดูแลรร: สร้างได้แค่เจ้าหน้าที่ IT ของโรงเรียนตนเอง
  if (myRole === 'owner') return ROLES; // Owner: สร้างได้ทุกบทบาท
  return ROLES.filter((r) => r !== 'owner'); // super_admin/admin: สร้างได้ทุกบทบาทยกเว้น owner
}

export default function UsersPage({ onBack, currentUserId, currentUserRole }: { onBack: () => void; currentUserId?: number; currentUserRole?: string }) {
  const [users, setUsers] = useState<any[]>([]);
  const [orgs, setOrgs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ line_user_id: '', line_display_name: '', line_email: '', organization_id: 0, role: 'it_support', is_active: true, password: '' });
  const [editingId, setEditingId] = useState<number | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const isSchoolAdmin = currentUserRole === 'admin_school';
  const allowedRoles = creatableRoles(currentUserRole);

  const load = () => {
    setLoading(true);
    Promise.all([api.listUsers(), api.listOrganizations()])
      .then(([u, o]) => { setUsers(u); setOrgs(o); })
      .catch((e) => setError(e.message || 'โหลดไม่สำเร็จ'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const openAdd = () => {
    // admin_school: ตั้ง org เป็นของตัวเองเสมอ + บทบาทเริ่มต้นตามสิทธิ์ที่สร้างได้
    const myOrg = isSchoolAdmin ? (orgs.find((o) => o.id === myOrgId())?.id || 0) : 0;
    setForm({ line_user_id: '', line_display_name: '', line_email: '', organization_id: myOrg, role: allowedRoles[0] || 'it_support', is_active: true, password: '' });
    setEditingId(null);
    setShowForm(true);
  };

  const myOrgId = () => {
    const u = users.find((x) => x.id === currentUserId);
    return u?.organization_id || 0;
  };

  const openEdit = (u: any) => {
    setForm({
      line_user_id: u.line_user_id,
      line_display_name: u.line_display_name || '',
      line_email: u.line_email || '',
      organization_id: u.organization_id || 0,
      role: u.role,
      is_active: u.is_active,
      password: '', // ไม่โชว์รหัสเดิม
    });
    setEditingId(u.id);
    setShowForm(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.line_user_id.trim()) { alert('กรุณาระบุชื่อผู้ใช้ (LINE User ID)'); return; }
    setSaving(true);
    setError(null);
    try {
      if (editingId) {
        const data: any = {
          line_display_name: form.line_display_name || undefined,
          line_email: form.line_email || undefined,
          organization_id: form.organization_id || null,
          role: form.role,
          is_active: form.is_active,
        };
        if (form.password) data.password = form.password;
        await api.updateUser(editingId, data);
      } else {
        await api.createUser({
          line_user_id: form.line_user_id.trim(),
          line_display_name: form.line_display_name || undefined,
          line_email: form.line_email || undefined,
          organization_id: form.organization_id || undefined,
          role: form.role,
          is_active: form.is_active,
          password: form.password || undefined,
        });
      }
      setShowForm(false);
      load();
    } catch (err: any) {
      setError(err.message || 'บันทึกไม่สำเร็จ');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (u: any) => {
    if (u.id === currentUserId) { alert('ไม่สามารถลบบัญชีตัวเองได้'); return; }
    if (!window.confirm(`ลบผู้ใช้ "${u.line_display_name || u.line_user_id}"?`)) return;
    setBusy(u.id);
    try {
      await api.deleteUser(u.id);
      setShowForm(false);
      load();
    } catch (err: any) {
      alert(err.message || 'ลบไม่สำเร็จ');
    } finally {
      setBusy(null);
    }
  };

  const handleRoleChange = async (userId: number, role: string) => {
    setBusy(userId);
    try {
      await api.updateUser(userId, { role });
      load();
    } catch (err: any) {
      alert(err.message || 'เปลี่ยนบทบาทไม่สำเร็จ');
    } finally {
      setBusy(null);
    }
  };

  const handleActiveToggle = async (userId: number, is_active: boolean) => {
    setBusy(userId);
    try {
      await api.updateUser(userId, { is_active });
      load();
    } catch (err: any) {
      alert(err.message || 'เปลี่ยนสถานะไม่สำเร็จ');
    } finally {
      setBusy(null);
    }
  };

  const orgName = (id: number | null | undefined) => {
    if (!id) return '—';
    return orgs.find((o) => o.id === id)?.name || `#${id}`;
  };

  return (
    <div className="page-content">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
          </button>
          <div>
            <h1 className="top-bar-title">ผู้ใช้งาน</h1>
            <span className="top-bar-subtitle">{users.length} คน</span>
          </div>
        </div>
        <div className="top-bar-actions">
          <button className="btn btn-primary" onClick={openAdd}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 6, verticalAlign: 'middle' }}>
              <path d="M12 5v14M5 12h14"/>
            </svg>
            เพิ่มผู้ใช้
          </button>
          <button className="btn btn-ghost btn-icon" onClick={load} aria-label="โหลดใหม่" title="โหลดใหม่">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M21 12a9 9 0 11-3.5-7.1" />
              <path d="M21 3v6h-6" />
            </svg>
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: '10px 14px', background: 'var(--color-danger-light)', color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem', marginBottom: 16 }}>
          {error}
        </div>
      )}

      {showForm && (
        <div className="panel-overlay" onClick={() => setShowForm(false)}>
          <div className="repair-panel" style={{ width: 500, maxWidth: '95vw' }} onClick={(e) => e.stopPropagation()}>
            <div className="repair-panel-header">
              <h3 className="repair-panel-title">{editingId ? `แก้ไขผู้ใช้: ${form.line_user_id}` : 'เพิ่มผู้ใช้ใหม่'}</h3>
              <button className="repair-panel-close" onClick={() => setShowForm(false)} aria-label="ปิด" title="ปิด">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="repair-panel-body">
              <form onSubmit={handleSave}>
                <div className="form-group">
                  <label className="form-label">ชื่อผู้ใช้ (LINE User ID) *</label>
                  <input className="form-input" value={form.line_user_id} onChange={(e) => setForm({ ...form, line_user_id: e.target.value })} placeholder="เช่น itsupport01" disabled={!!editingId} />
                </div>
                <div className="form-group">
                  <label className="form-label">ชื่อ (LINE Display Name)</label>
                  <input className="form-input" value={form.line_display_name} onChange={(e) => setForm({ ...form, line_display_name: e.target.value })} />
                </div>
                <div className="form-group">
                  <label className="form-label">อีเมล</label>
                  <input className="form-input" type="email" value={form.line_email} onChange={(e) => setForm({ ...form, line_email: e.target.value })} />
                </div>
                <div className="form-group">
                  <label className="form-label">รหัสผ่าน {editingId ? '(เว้นว่าง = ใช้รหัสเดิม)' : '*'}</label>
                  <input className="form-input" type="password" autoComplete="new-password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder={editingId ? 'ปล่อยว่างถ้าไม่เปลี่ยน' : 'ตั้งรหัสผ่านให้ผู้ใช้'} />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">โรงเรียน {isSchoolAdmin ? '(อัตโนมัติ — รรตัวเอง)' : ''}</label>
                    <select className="form-select" value={form.organization_id} onChange={(e) => setForm({ ...form, organization_id: Number(e.target.value) })} disabled={isSchoolAdmin}>
                      <option value={0}>— (ไม่สังกัด / super_admin) —</option>
                      {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">บทบาท</label>
                    <select className="form-select" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}>
                      {allowedRoles.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                    </select>
                  </div>
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                  <button type="submit" className="btn btn-primary" style={{ flex: 1 }} disabled={saving}>
                    {saving ? 'กำลังบันทึก...' : 'บันทึก'}
                  </button>
                  <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>ยกเลิก</button>
                </div>
                {editingId != null && editingId !== currentUserId && <div style={{ marginTop: 20, paddingTop: 16, borderTop: '1px solid var(--color-border)' }}>
                  <button type="button" className="btn btn-danger" disabled={busy === editingId} onClick={() => { const target = users.find((u) => u.id === editingId); if (target) void handleDelete(target); }}>{busy === editingId ? 'กำลังลบ…' : 'ลบบัญชีนี้'}</button>
                </div>}
              </form>
            </div>
          </div>
        </div>
      )}

      <div className="page-section">
        <div className="section-body">
          {loading ? (
            <div className="loading-state" style={{ padding: '40px' }}>
              <div className="spinner" />
              <span>กำลังโหลด...</span>
            </div>
          ) : users.length === 0 ? (
            <div className="empty-state" style={{ padding: '40px' }}>
              <svg className="empty-icon" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <circle cx="12" cy="8" r="4"/>
                <path d="M4 20c0-4 4-7 8-7s8 3 8 7"/>
              </svg>
              <span className="empty-text">ยังไม่มีผู้ใช้ — กด "เพิ่มผู้ใช้"</span>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ชื่อ</th>
                    <th>ชื่อผู้ใช้</th>
                    <th>โรงเรียน</th>
                    <th>บทบาท</th>
                    <th>สถานะ</th>
                    <th>จัดการ</th>
                  </tr>
                </thead>
                <tbody>
                  {users.map((u) => (
                    <tr key={u.id} style={u.id === currentUserId ? { background: 'var(--color-primary-light)' } : undefined}>
                      <td style={{ fontWeight: 500 }}>{u.line_display_name || u.line_user_id}{u.id === currentUserId ? ' (คุณ)' : ''}</td>
                      <td style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>{u.line_user_id}</td>
                      <td>{orgName(u.organization_id)}</td>
                      <td>
                        {isSchoolAdmin && !allowedRoles.includes(u.role) ? (
                          <span style={{ fontSize: '0.82rem', color: 'var(--color-text-secondary)' }}>{ROLE_LABELS[u.role] || u.role}</span>
                        ) : (
                          <select
                            className="form-select"
                            style={{ width: 170, padding: '5px 8px', fontSize: '0.8rem' }}
                            value={u.role}
                            disabled={busy === u.id}
                            onChange={(e) => handleRoleChange(u.id, e.target.value)}
                          >
                            {allowedRoles.map((r) => <option key={r} value={r}>{ROLE_LABELS[r]}</option>)}
                          </select>
                        )}
                      </td>
                      <td>
                        <button
                          className={`btn btn-sm ${u.is_active ? 'btn-success' : 'btn-ghost'}`}
                          disabled={busy === u.id}
                          onClick={() => handleActiveToggle(u.id, !u.is_active)}
                          style={{ padding: '4px 10px', fontSize: '0.78rem' }}
                        >
                          {u.is_active ? 'ใช้งาน' : 'ปิด'}
                        </button>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                          <button className="btn btn-secondary btn-sm" onClick={() => openEdit(u)} style={{ padding: '4px 10px', fontSize: '0.78rem' }}>แก้ไข</button>
                        </div>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
