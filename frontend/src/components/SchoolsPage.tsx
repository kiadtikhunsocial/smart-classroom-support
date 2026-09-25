import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import '../styles/schools.css';

const STATUS_OPTIONS = ['new', 'assigned', 'in_progress', 'pending', 'waiting_parts', 'waiting_user', 'resolved', 'closed', 'cancelled'];

const STATUS_LABELS: Record<string, string> = {
  new: 'รอรับเรื่อง (New)',
  assigned: 'มอบหมายแล้ว (Assigned)',
  in_progress: 'กำลังดำเนินการ (In Progress)',
  pending: 'รออะไหล่/รอภายนอก (Pending)',
  waiting_parts: 'รออะไหล่ (Waiting for Parts)',
  waiting_user: 'รอผู้ใช้ (Waiting for User)',
  resolved: 'ซ่อมเสร็จแล้ว (Resolved)',
  closed: 'ปิดงาน (Closed)',
  cancelled: 'ยกเลิก (Cancelled)',
};

// ─── หน้ารายการโรงเรียน (super_admin) ─────────────────────────────
export default function SchoolsPage({ onSelectSchool, onBack }: {
  onSelectSchool: (orgId: number) => void;
  onBack: () => void;
}) {
  const [orgs, setOrgs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({ code: '', name: '', short_name: '' });
  const [query, setQuery] = useState('');
  const visibleOrgs = orgs.filter((org) => `${org.name} ${org.short_name || ''} ${org.code}`.toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()));
  const totalDevices = orgs.reduce((sum, org) => sum + Number(org.device_count || 0), 0);
  const totalTickets = orgs.reduce((sum, org) => sum + Number(org.ticket_count || 0), 0);

  const load = () => {
    setLoading(true);
    api.listOrganizations()
      .then(setOrgs)
      .catch((e) => setError(e.message || 'โหลดข้อมูลไม่สำเร็จ'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, []);

  const handleCreate = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.code.trim() || !form.name.trim()) { alert('กรุณากรอก รหัสโรงเรียน และ ชื่อโรงเรียน'); return; }
    setSaving(true);
    setError(null);
    try {
      await api.createOrganization({
        code: form.code.trim().toUpperCase(),
        name: form.name.trim(),
        short_name: form.short_name.trim() || undefined,
      });
      setShowForm(false);
      setForm({ code: '', name: '', short_name: '' });
      load();
    } catch (err: any) {
      setError(err.message || 'เพิ่มโรงเรียนไม่สำเร็จ');
    } finally {
      setSaving(false);
    }
  };

  if (loading) return (
    <div className="loading-state" style={{ minHeight: 200, padding: '40px' }}>
      <div className="spinner" />
      <span>กำลังโหลดโรงเรียน...</span>
    </div>
  );

  return (
    <div className="page-content schools-page">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
          </button>
          <div>
            <h1 className="top-bar-title">โรงเรียนทั้งหมด</h1>
            <span className="top-bar-subtitle">{orgs.length} แห่ง</span>
          </div>
        </div>
        <div className="top-bar-actions">
          <button className="btn btn-primary" onClick={() => setShowForm(true)}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 6, verticalAlign: 'middle' }}>
              <path d="M12 5v14M5 12h14"/>
            </svg>
            เพิ่มโรงเรียน
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

      {/* ฟอร์มเพิ่มโรงเรียน */}
      {showForm && (
        <div className="panel-overlay" onClick={() => setShowForm(false)}>
          <div className="repair-panel" style={{ width: 440, maxWidth: '95vw' }} onClick={(e) => e.stopPropagation()}>
            <div className="repair-panel-header">
              <h3 className="repair-panel-title">เพิ่มโรงเรียนใหม่</h3>
              <button className="repair-panel-close" onClick={() => setShowForm(false)} aria-label="ปิด" title="ปิด">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="repair-panel-body">
              <form onSubmit={handleCreate}>
                <div className="form-group">
                  <label className="form-label">รหัสโรงเรียน *</label>
                  <input className="form-input" value={form.code} onChange={(e) => setForm({ ...form, code: e.target.value })} placeholder="เช่น SCH-04" />
                  <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)', marginTop: 4 }}>
                    ใช้เป็น prefix รหัสอุปกรณ์ (DEV-xxxx) และกรองข้อมูล
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">ชื่อโรงเรียน *</label>
                  <input className="form-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="เช่น โรงเรียนบ้านทุ่งสุข" />
                </div>
                <div className="form-group">
                  <label className="form-label">ชื่อย่อ</label>
                  <input className="form-input" value={form.short_name} onChange={(e) => setForm({ ...form, short_name: e.target.value })} placeholder="เช่น ทุ่งสุข" />
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                  <button type="submit" className="btn btn-primary" style={{ flex: 1 }} disabled={saving}>
                    {saving ? 'กำลังเพิ่ม...' : 'เพิ่มโรงเรียน'}
                  </button>
                  <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>ยกเลิก</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      <div className="schools-summary" aria-label="ภาพรวมโรงเรียน"><div><span>โรงเรียนทั้งหมด</span><strong>{orgs.length}</strong><small>แห่งในระบบ</small></div><div><span>อุปกรณ์ที่ลงทะเบียน</span><strong>{totalDevices.toLocaleString('th-TH')}</strong><small>ทุกโรงเรียน</small></div><div><span>ใบงานทั้งหมด</span><strong>{totalTickets.toLocaleString('th-TH')}</strong><small>ทุกสถานะ</small></div></div>
      <div className="schools-list-heading"><div><h2>รายชื่อโรงเรียน</h2><p>เลือกโรงเรียนเพื่อดูอุปกรณ์และใบงานของแต่ละแห่ง</p></div><input className="form-input" type="search" value={query} onChange={(event) => setQuery(event.target.value)} placeholder="ค้นหาชื่อหรือรหัสโรงเรียน" aria-label="ค้นหาโรงเรียน" /></div>
      <div className="schools-grid">
        {visibleOrgs.map((org) => <button type="button" key={org.id} className="school-card" onClick={() => onSelectSchool(org.id)}>
          <div className="school-card-top"><span className="school-card-icon" aria-hidden="true">⌂</span><span className="school-card-code">{org.code}</span></div>
          <strong>{org.name}</strong><small>{org.short_name || 'โรงเรียนในระบบ'}</small>
          <div className="school-card-stats"><span><b>{Number(org.device_count || 0)}</b> อุปกรณ์</span><span><b>{Number(org.ticket_count || 0)}</b> ใบงาน</span></div>
          <span className="school-card-link">ดูข้อมูลโรงเรียน <span aria-hidden="true">→</span></span>
        </button>)}
      </div>
      {orgs.length > 0 && visibleOrgs.length === 0 && <p className="schools-no-results">ไม่พบโรงเรียนที่ตรงกับคำค้น</p>}

      {orgs.length === 0 && !loading && (
        <div className="empty-state" style={{ padding: '40px' }}>
          <span className="empty-text">ยังไม่มีโรงเรียนในระบบ</span>
        </div>
      )}
    </div>
  );
}

// ─── หน้า Admin รายโรงเรียน (ดู + จัดการ ticket เร็ว) ──────────────
export function SchoolAdminView({ orgId, onBack, canDelete }: {
  orgId: number;
  onBack: () => void;
  canDelete?: boolean;
}) {
  const [org, setOrg] = useState<any | null>(null);
  const [tickets, setTickets] = useState<any[]>([]);
  const [devices, setDevices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<string | null>(null);
  const [deleting, setDeleting] = useState(false);
  const [deleteError, setDeleteError] = useState('');
  const deleteSchool = async () => {
    if (!window.confirm(`ลบโรงเรียน "${org?.name || orgId}"? ระบบจะยอมลบเฉพาะโรงเรียนที่ไม่มีข้อมูลผูกอยู่ และการลบนี้กู้คืนไม่ได้`)) return;
    setDeleting(true); setDeleteError('');
    try { await api.deleteOrganization(orgId); onBack(); }
    catch (err: any) { setDeleteError(err?.message || 'ลบโรงเรียนไม่สำเร็จ'); }
    finally { setDeleting(false); }
  };
  const [statusFilter, setStatusFilter] = useState('');
  const [deviceTypeFilter, setDeviceTypeFilter] = useState('');
  const [view, setView] = useState<'tickets' | 'devices'>('tickets');

  const load = () => {
    setLoading(true);
    Promise.all([
      api.getOrgStats(orgId),
      api.listAllTickets({ organization_id: orgId }),
      api.listAllDevices(orgId),
    ])
      .then(([o, t, d]) => { setOrg(o); setTickets(t); setDevices(d); })
      .catch(() => {})
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [orgId]);

  const handleStatusChange = async (ticketId: string, newStatus: string) => {
    if (!newStatus) return;
    setUpdating(ticketId);
    try {
      await api.updateStatus(ticketId, { status: newStatus, author_name: 'ผู้ดูแลระบบ', force: true });
      // รีเฟรชข้อมูลทันที
      const [o, t, d] = await Promise.all([
        api.getOrgStats(orgId),
        api.listAllTickets({ organization_id: orgId }),
        api.listAllDevices(orgId),
      ]);
      setOrg(o); setTickets(t); setDevices(d);
    } catch (e: any) {
      alert('อัปเดตสถานะไม่สำเร็จ: ' + (e.message || ''));
    } finally {
      setUpdating(null);
    }
  };

  const filteredTickets = statusFilter ? tickets.filter((t) => t.status === statusFilter) : tickets;

  // ─── หมวดหมู่อุปกรณ์ของโรงเรียนนี้ + จำนวนแต่ละหมวด (มาก → น้อย) ───
  const UNKNOWN_DEVICE_TYPE = 'ไม่ระบุประเภท';
  const deviceTypeCounts = devices.reduce<Record<string, number>>((acc, d) => {
    const t = d.device_type || UNKNOWN_DEVICE_TYPE;
    acc[t] = (acc[t] || 0) + 1;
    return acc;
  }, {});
  const deviceTypeOptions = Object.keys(deviceTypeCounts).sort(
    (a, b) => deviceTypeCounts[b] - deviceTypeCounts[a] || a.localeCompare(b, 'th'),
  );
  // ถ้าหมวดที่เลือกไม่มีในโรงเรียนนี้ (เปลี่ยนโรงเรียน/โหลดใหม่) ให้ถือว่าแสดงทุกหมวด
  const activeDeviceType = deviceTypeOptions.includes(deviceTypeFilter) ? deviceTypeFilter : '';
  const visibleDevices = activeDeviceType
    ? devices.filter((d) => (d.device_type || UNKNOWN_DEVICE_TYPE) === activeDeviceType)
    : devices;

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
            <h1 className="top-bar-title">{org?.name || 'โรงเรียน'}</h1>
            <span className="top-bar-subtitle">{org?.code || ''}</span>
          </div>
        </div>
        <div className="top-bar-actions">
          {canDelete && <button className="btn btn-danger" disabled={deleting} onClick={() => void deleteSchool()}>{deleting ? 'กำลังลบ…' : 'ลบโรงเรียนนี้'}</button>}
          {/* Tab: Tickets / อุปกรณ์ */}
          <div style={{ display: 'flex', background: 'var(--color-bg)', borderRadius: 'var(--radius-sm)', padding: 3 }}>
            <button
              onClick={() => setView('tickets')}
              style={{
                padding: '6px 14px', borderRadius: 'var(--radius-sm)', border: 'none', cursor: 'pointer',
                background: view === 'tickets' ? 'var(--color-primary)' : 'transparent',
                color: view === 'tickets' ? '#fff' : 'var(--color-text-secondary)', fontSize: '0.82rem',
              }}
            >Tickets</button>
            <button
              onClick={() => setView('devices')}
              style={{
                padding: '6px 14px', borderRadius: 'var(--radius-sm)', border: 'none', cursor: 'pointer',
                background: view === 'devices' ? 'var(--color-primary)' : 'transparent',
                color: view === 'devices' ? '#fff' : 'var(--color-text-secondary)', fontSize: '0.82rem',
              }}
            >อุปกรณ์ ({devices.length})</button>
          </div>
          {view === 'devices' && (
            <select
              className="form-select"
              style={{ width: 210 }}
              value={activeDeviceType}
              onChange={(e) => setDeviceTypeFilter(e.target.value)}
              aria-label="กรองตามหมวดหมู่อุปกรณ์"
              disabled={deviceTypeOptions.length === 0}
            >
              <option value="">ทุกหมวดหมู่ ({devices.length})</option>
              {deviceTypeOptions.map((t) => (
                <option key={t} value={t}>{t} ({deviceTypeCounts[t]})</option>
              ))}
            </select>
          )}
          {view === 'tickets' && (
            <select
              className="form-select"
              style={{ width: 160 }}
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
            >
              <option value="">สถานะทั้งหมด</option>
              {STATUS_OPTIONS.map((s) => (
                <option key={s} value={s}>{STATUS_LABELS[s]}</option>
              ))}
            </select>
          )}
        </div>
      </div>

      {deleteError && <div className="alert alert-error" role="alert">{deleteError}</div>}

      {/* สถิติสรุป */}
      <div className="stat-cards-grid">
        <div className="stat-card">
          <div className="stat-card-icon blue">TKT</div>
          <div className="stat-card-value">{org?.total_tickets ?? 0}</div>
          <div className="stat-card-label">Tickets ทั้งหมด</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-icon red">OPEN</div>
          <div className="stat-card-value">{org?.open_tickets ?? 0}</div>
          <div className="stat-card-label">รอดำเนินการ</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-icon green">DEV</div>
          <div className="stat-card-value">{org?.total_devices ?? 0}</div>
          <div className="stat-card-label">อุปกรณ์</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-icon gray">LOG</div>
          <div className="stat-card-value">{devices.length}</div>
          <div className="stat-card-label">อุปกรณ์ในระบบ</div>
        </div>
      </div>

      {/* ตาราง Ticket พร้อมแก้สถานะเร็ว */}
      {view === 'tickets' && (
      <div className="page-section">
        <div className="section-header">
          <span className="section-title">Tickets ของโรงเรียน ({filteredTickets.length})</span>
          <button type="button" className="section-action" onClick={load}>
            <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" style={{ marginRight: 5, verticalAlign: '-2px' }}>
              <path d="M21 12a9 9 0 11-3.5-7.1" />
              <path d="M21 3v6h-6" />
            </svg>
            รีเฟรช
          </button>
        </div>
        <div className="section-body">
          {loading ? (
            <div className="loading-state" style={{ padding: '40px' }}>
              <div className="spinner" />
              <span>กำลังโหลด...</span>
            </div>
          ) : filteredTickets.length === 0 ? (
            <div className="empty-state" style={{ padding: '32px 16px' }}>
              <span className="empty-text">ไม่มี Ticket{statusFilter ? ` (สถานะ: ${STATUS_LABELS[statusFilter]})` : ''}</span>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Ticket ID</th>
                    <th>อุปกรณ์</th>
                    <th>หัวข้อ</th>
                    <th>ผู้แจ้ง</th>
                    <th>ความเร่งด่วน</th>
                    <th>สถานะ (แก้ได้ทันที)</th>
                    <th>สร้างเมื่อ</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTickets.map((ticket) => (
                    <tr key={ticket.ticket_id}>
                      <td className="table-id">{ticket.ticket_id}</td>
                      <td>
                        {/* ชื่อ/ประเภทอุปกรณ์มาก่อน รหัสไว้อ้างอิงกับสติกเกอร์ */}
                        <div>{ticket.device_label || ticket.device_type || ticket.device_id || '—'}</div>
                        {ticket.device_category && (
                          <div style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)' }}>
                            {ticket.device_category}
                          </div>
                        )}
                        {ticket.device_id && (ticket.device_label || ticket.device_type) && (
                          <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)' }}>
                            {ticket.device_id}
                          </div>
                        )}
                      </td>
                      <td>{ticket.title}</td>
                      <td>{ticket.reporter_name || '—'}</td>
                      <td>
                        <span className={`badge badge-priority-${ticket.priority}`}>
                          {ticket.priority}
                        </span>
                      </td>
                      <td>
                        <select
                          className="form-select"
                          style={{ width: 150, padding: '6px 8px', fontSize: '0.8rem' }}
                          value={ticket.status}
                          disabled={updating === ticket.ticket_id}
                          onChange={(e) => handleStatusChange(ticket.ticket_id, e.target.value)}
                        >
                          {STATUS_OPTIONS.map((s) => (
                            <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                          ))}
                        </select>
                        {updating === ticket.ticket_id && (
                          <span className="spinner" style={{ width: 12, height: 12, marginLeft: 6, borderWidth: 2, display: 'inline-block', verticalAlign: 'middle' }} />
                        )}
                      </td>
                      <td style={{ color: 'var(--color-text-tertiary)', fontSize: '0.8rem' }}>
                        {new Date(ticket.created_at).toLocaleDateString('th-TH', {
                          day: '2-digit', month: 'short', year: 'numeric',
                        })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
      )}

      {/* ตารางอุปกรณ์ของโรงเรียน */}
      {view === 'devices' && (
        <div className="page-section">
          <div className="section-header">
            <span className="section-title">
              อุปกรณ์ในโรงเรียน ({activeDeviceType ? `${visibleDevices.length}/${devices.length}` : devices.length})
              {deviceTypeOptions.length > 0 && ` · ${deviceTypeOptions.length} หมวดหมู่`}
            </span>
            <button type="button" className="section-action" onClick={load}>
              <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" style={{ marginRight: 5, verticalAlign: '-2px' }}>
                <path d="M21 12a9 9 0 11-3.5-7.1" />
                <path d="M21 3v6h-6" />
              </svg>
              รีเฟรช
            </button>
          </div>
          <div className="section-body">
            {/* ชิปหมวดหมู่ — กดสลับกรองได้ ทำงานคู่กับ dropdown ด้านบน */}
            {!loading && deviceTypeOptions.length > 0 && (
              <div className="dev-type-chips" role="group" aria-label="หมวดหมู่อุปกรณ์">
                <button
                  type="button"
                  className={`dev-type-chip${activeDeviceType ? '' : ' is-active'}`}
                  aria-pressed={!activeDeviceType}
                  onClick={() => setDeviceTypeFilter('')}
                >
                  ทุกหมวดหมู่
                  <span className="dev-type-chip-count">{devices.length}</span>
                </button>
                {deviceTypeOptions.map((t) => (
                  <button
                    key={t}
                    type="button"
                    className={`dev-type-chip${activeDeviceType === t ? ' is-active' : ''}`}
                    aria-pressed={activeDeviceType === t}
                    onClick={() => setDeviceTypeFilter(activeDeviceType === t ? '' : t)}
                  >
                    {t}
                    <span className="dev-type-chip-count">{deviceTypeCounts[t]}</span>
                  </button>
                ))}
              </div>
            )}
            {loading ? (
              <div className="loading-state" style={{ padding: '40px' }}>
                <div className="spinner" />
                <span>กำลังโหลด...</span>
              </div>
            ) : devices.length === 0 ? (
              <div className="empty-state" style={{ padding: '32px 16px' }}>
                <span className="empty-text">ยังไม่มีอุปกรณ์ในโรงเรียนนี้</span>
              </div>
            ) : visibleDevices.length === 0 ? (
              <div className="empty-state" style={{ padding: '32px 16px' }}>
                <span className="empty-text">ไม่มีอุปกรณ์ในหมวด "{activeDeviceType}"</span>
              </div>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>รหัสอุปกรณ์</th>
                      <th>ประเภท</th>
                      <th>ยี่ห้อ/รุ่น</th>
                      <th>ห้อง</th>
                      <th>สถานะ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {visibleDevices.map((d) => (
                      <tr key={d.device_id}>
                        <td className="table-id">{d.device_id}</td>
                        <td>{d.device_type}</td>
                        <td>{[d.brand, d.model].filter(Boolean).join(' ') || '—'}</td>
                        <td>{d.room_name || d.room_code || '—'}</td>
                        <td>
                          <span className={`badge badge-${d.status === 'active' ? 'in_progress' : d.status === 'decommissioned' ? 'closed' : 'pending'}`}>
                            {d.status === 'active' ? 'ใช้งาน' : d.status === 'inactive' ? 'ไม่ใช้งาน' : 'ปลดระวาง'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
