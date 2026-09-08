import React, { useState, useEffect } from 'react';
import { api } from '../api/client';

const STATUS_OPTIONS = ['new', 'assigned', 'in_progress', 'pending', 'resolved', 'closed', 'cancelled'];

const STATUS_LABELS: Record<string, string> = {
  new: 'รอรับเรื่อง',
  assigned: 'มอบหมายแล้ว',
  in_progress: 'กำลังดำเนินการ',
  pending: 'รออะไหล่/รอภายนอก',
  resolved: 'เสร็จสิ้น',
  closed: 'ปิดงาน',
  cancelled: 'ยกเลิก',
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

  const handleDelete = async (org: any) => {
    if (!window.confirm(`ลบโรงเรียน "${org.name}" พร้อมอุปกรณ์และ tickets ทั้งหมด? ไม่สามารถกู้คืนได้`)) return;
    setSaving(true);
    setError(null);
    try {
      await api.deleteOrganization(org.id);
      load();
    } catch (err: any) {
      setError(err.message || 'ลบโรงเรียนไม่สำเร็จ');
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
    <div className="page-content">
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
          <button className="btn btn-ghost" onClick={load}>⟳</button>
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
              <button className="repair-panel-close" onClick={() => setShowForm(false)}>✕</button>
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

      <div className="device-grid">
        {orgs.map((org) => (
          <div
            key={org.id}
            className="device-card"
            style={{ cursor: 'pointer' }}
            onClick={() => onSelectSchool(org.id)}
          >
            <div className="device-card-top">
              <div className="device-card-icon-box" style={{ background: 'var(--color-primary-light)', color: 'var(--color-primary)' }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M3 21h18M5 21V7l7-4 7 4v14M9 21v-4h6v4M9 10h.01M15 10h.01M9 14h.01M15 14h.01"/>
                </svg>
              </div>
              <span className="role-badge">{org.code}</span>
            </div>
            <div className="device-card-id">{org.name}</div>
            <div className="device-card-type">{org.short_name || '—'}</div>
            <div className="device-card-room">
              🖥️ {org.device_count} อุปกรณ์ • 🎫 {org.ticket_count} tickets
            </div>
            <div className="device-card-bottom">
              <div className="device-card-actions">
                <button className="btn btn-primary btn-sm" onClick={(e) => { e.stopPropagation(); onSelectSchool(org.id); }}>
                  เข้าดูข้อมูล
                </button>
                <button className="btn btn-danger btn-sm" onClick={(e) => { e.stopPropagation(); handleDelete(org); }} disabled={saving} style={{ padding: '4px 10px', fontSize: '0.78rem' }}>
                  ลบ
                </button>
              </div>
            </div>
          </div>
        ))}
      </div>

      {orgs.length === 0 && !loading && (
        <div className="empty-state" style={{ padding: '40px' }}>
          <span className="empty-text">ยังไม่มีโรงเรียนในระบบ</span>
        </div>
      )}
    </div>
  );
}

// ─── หน้า Admin รายโรงเรียน (ดู + จัดการ ticket เร็ว) ──────────────
export function SchoolAdminView({ orgId, onBack }: {
  orgId: number;
  onBack: () => void;
}) {
  const [org, setOrg] = useState<any | null>(null);
  const [tickets, setTickets] = useState<any[]>([]);
  const [devices, setDevices] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [updating, setUpdating] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [view, setView] = useState<'tickets' | 'devices'>('tickets');

  const load = () => {
    setLoading(true);
    Promise.all([
      api.getOrgStats(orgId),
      api.listTickets({ organization_id: orgId }),
      api.listDevices(100, orgId),
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
        api.listTickets({ organization_id: orgId }),
        api.listDevices(100, orgId),
      ]);
      setOrg(o); setTickets(t); setDevices(d);
    } catch (e: any) {
      alert('อัปเดตสถานะไม่สำเร็จ: ' + (e.message || ''));
    } finally {
      setUpdating(null);
    }
  };

  const filteredTickets = statusFilter ? tickets.filter((t) => t.status === statusFilter) : tickets;

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
          {/* Tab: Tickets / อุปกรณ์ */}
          <div style={{ display: 'flex', background: 'var(--color-bg)', borderRadius: 'var(--radius-sm)', padding: 3 }}>
            <button
              onClick={() => setView('tickets')}
              style={{
                padding: '6px 14px', borderRadius: 'var(--radius-sm)', border: 'none', cursor: 'pointer',
                background: view === 'tickets' ? 'var(--color-primary)' : 'transparent',
                color: view === 'tickets' ? '#fff' : 'var(--color-text-secondary)', fontSize: '0.82rem',
              }}
            >🎫 Tickets</button>
            <button
              onClick={() => setView('devices')}
              style={{
                padding: '6px 14px', borderRadius: 'var(--radius-sm)', border: 'none', cursor: 'pointer',
                background: view === 'devices' ? 'var(--color-primary)' : 'transparent',
                color: view === 'devices' ? '#fff' : 'var(--color-text-secondary)', fontSize: '0.82rem',
              }}
            >🖥️ อุปกรณ์ ({devices.length})</button>
          </div>
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

      {/* สถิติสรุป */}
      <div className="stat-cards-grid">
        <div className="stat-card">
          <div className="stat-card-icon blue">🎫</div>
          <div className="stat-card-value">{org?.total_tickets ?? 0}</div>
          <div className="stat-card-label">Tickets ทั้งหมด</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-icon red">🟠</div>
          <div className="stat-card-value">{org?.open_tickets ?? 0}</div>
          <div className="stat-card-label">รอดำเนินการ</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-icon green">🖥️</div>
          <div className="stat-card-value">{org?.total_devices ?? 0}</div>
          <div className="stat-card-label">อุปกรณ์</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-icon gray">📋</div>
          <div className="stat-card-value">{devices.length}</div>
          <div className="stat-card-label">อุปกรณ์ในระบบ</div>
        </div>
      </div>

      {/* ตาราง Ticket พร้อมแก้สถานะเร็ว */}
      {view === 'tickets' && (
      <div className="page-section">
        <div className="section-header">
          <span className="section-title">Tickets ของโรงเรียน ({filteredTickets.length})</span>
          <span className="section-action" onClick={load}>⟳ รีเฟรช</span>
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
                      <td>{ticket.device_id}</td>
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
            <span className="section-title">อุปกรณ์ในโรงเรียน ({devices.length})</span>
            <span className="section-action" onClick={load}>⟳ รีเฟรช</span>
          </div>
          <div className="section-body">
            {loading ? (
              <div className="loading-state" style={{ padding: '40px' }}>
                <div className="spinner" />
                <span>กำลังโหลด...</span>
              </div>
            ) : devices.length === 0 ? (
              <div className="empty-state" style={{ padding: '32px 16px' }}>
                <span className="empty-text">ยังไม่มีอุปกรณ์ในโรงเรียนนี้</span>
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
                    {devices.map((d) => (
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
