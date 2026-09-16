import React, { useState, useEffect } from 'react';
import { api } from '../api/client';

const STATUS_LABELS: Record<string, string> = {
  new: 'รอรับเรื่อง (New)', assigned: 'มอบหมายแล้ว (Assigned)', in_progress: 'กำลังดำเนินการ (In Progress)',
  pending: 'รออะไหล่/รอภายนอก (Pending)', waiting_parts: 'รออะไหล่ (Waiting for Parts)', waiting_user: 'รอผู้ใช้ (Waiting for User)',
  resolved: 'ซ่อมเสร็จ รอยืนยัน (Resolved)', closed: 'ปิดงาน (Closed)', cancelled: 'ยกเลิก (Cancelled)',
};
const STATUS_COLORS: Record<string, string> = {
  new: '#EF4444', assigned: '#F59E0B', in_progress: '#2563EB',
  pending: '#8B5CF6', waiting_parts: '#3182CE', waiting_user: '#805AD5',
  resolved: '#10B981', closed: '#6B7280', cancelled: '#EF4444',
};
const PRIORITY_LABELS: Record<string, string> = {
  low: 'Low', normal: 'Normal', high: 'High', critical: 'Critical',
};
const PRIORITY_COLORS: Record<string, string> = {
  low: '#10B981', normal: '#2563EB', high: '#F59E0B', critical: '#EF4444',
};

function fmtDate(iso?: string) {
  if (!iso) return '—';
  return new Date(iso).toLocaleDateString('th-TH', { day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit' });
}

export default function ReportsPage({ onBack }: { onBack: () => void }) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [stats, setStats] = useState<any>(null);
  const [topIssues, setTopIssues] = useState<any[]>([]);
  const [topDevices, setTopDevices] = useState<any[]>([]);
  const [analytics, setAnalytics] = useState<any>({ by_issue_category: {}, by_device_type: {}, recent_self_service: [], ticket_metrics: {}, avg_resolution_hours: null });
  const [history, setHistory] = useState<any[]>([]);
  const [historyTicket, setHistoryTicket] = useState('');
  const [historyLoading, setHistoryLoading] = useState(false);
  const [ticketsByDevice, setTicketsByDevice] = useState<any[]>([]);
  const [deviceTicketsLoading, setDeviceTicketsLoading] = useState(false);
  const [selectedTicket, setSelectedTicket] = useState<any>(null);
  const [avgRes, setAvgRes] = useState<any>(null);
  const [selfServiceList, setSelfServiceList] = useState<any[]>([]);
  const [selfServiceLoading, setSelfServiceLoading] = useState(false);

  const loadAll = () => {
    setLoading(true);
    Promise.all([
      api.getStats().catch(() => null),
      api.reportTopIssues(5).catch(() => []),
      api.reportTopDevices(5).catch(() => []),
      api.getChatbotAnalytics().catch(() => null),
    ])
      .then(([statsRes, issuesRes, devicesRes, analyticsRes]) => {
        setStats(statsRes);
        setTopIssues(issuesRes?.slice(0, 5) || []);
        setTopDevices(devicesRes?.slice(0, 5) || []);
        setAnalytics(analyticsRes || { by_issue_category: {}, by_device_type: {}, recent_self_service: [], ticket_metrics: {}, avg_resolution_hours: null });
      })
      .catch((e) => setError(e.message || 'โหลดไม่สำเร็จ'))
      .finally(() => setLoading(false));
  };

  const loadSelfService = () => {
    setSelfServiceLoading(true);
    api.listSelfService({ limit: 100 })
      .then((data: any) => setSelfServiceList(data || []))
      .catch(() => setSelfServiceList([]))
      .finally(() => setSelfServiceLoading(false));
  };

  const exportCSV = () => {
    if (!stats?.recent_tickets?.length) { alert('ไม่มีข้อมูล ticket'); return; }
    const header = 'ticket_id,title,status,priority,created_at,device_type,room';
    const rows = stats.recent_tickets.map((t: any) =>
      [t.ticket_id, `"${(t.title || '').replace(/"/g, '""')}"`, t.status, t.priority, t.created_at, t.device_type || '', t.room_name || ''].join(',')
    );
    const csv = [header, ...rows].join('\n');
    const blob = new Blob(['\uFEFF' + csv], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `reports-tickets-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  useEffect(() => { loadAll(); }, []);

  const fetchHistory = (ticketId?: string) => {
    const id = ticketId || historyTicket;
    if (!id) return;
    setHistoryLoading(true);
    api.getTicketHistory(id)
      .then((data) => setHistory(data || []))
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false));
  };

  const fetchTicketsByDevice = (deviceId: string) => {
    if (!deviceId) return;
    setDeviceTicketsLoading(true);
    api.listTickets({ device_id: deviceId, limit: 50 })
      .then((res: any) => setTicketsByDevice(res?.items || res || []))
      .catch(() => setTicketsByDevice([]))
      .finally(() => setDeviceTicketsLoading(false));
  };

  const fetchAvgResolution = () => {
    api.getAvgResolution().then(setAvgRes).catch(() => setAvgRes(null));
  };

  const openTicket = (id: string) => {
    setSelectedTicket(null);
    api.getTicket(id)
      .then((t: any) => { setSelectedTicket(t); fetchHistory(id); })
      .catch(() => setSelectedTicket(null));
  };

  const byStatus = stats?.by_status || {};
  const byPriority = stats?.by_priority || {};
  const byType = stats?.by_type || {};
  const devicesByStatus = stats?.devices_by_status || {};
  const issuesByDevice = analytics?.by_issue_category || {};
  const devicesByIssue = analytics?.by_device_type || {};
  const recentSelfService = analytics?.recent_self_service || [];
  const ticketMetrics = analytics?.ticket_metrics || {};

  const totalTickets = stats?.total_tickets ?? 0;
  const totalDevices = stats?.total_devices ?? 0;
  const openTickets = (stats?.new ?? 0) + (stats?.assigned ?? 0) + (stats?.in_progress ?? 0) + (stats?.pending ?? 0) + (stats?.waiting_parts ?? 0) + (stats?.waiting_user ?? 0);
  const closedCount = (stats?.resolved ?? 0) + (stats?.closed ?? 0);
  const resolutionRate = totalTickets > 0 ? Math.round(closedCount / totalTickets * 100) : 0;
  const selfService = stats?.self_service_total ?? 0;
  const avgResolutionHours = analytics?.avg_resolution_hours ?? avgRes?.avg_hours ?? ticketMetrics?.avg_resolution_hours ?? null;

  const statusRows = Object.entries(byStatus).map(([k, v]) => ({ k, label: STATUS_LABELS[k] || k, v: v as number })).sort((a, b) => b.v - a.v);
  const priorityRows = Object.entries(byPriority).map(([k, v]) => ({ k, label: PRIORITY_LABELS[k] || k, v: v as number })).sort((a, b) => b.v - a.v);
  const typeRows = Object.entries(byType).map(([k, v]) => ({ k, v: v as number })).sort((a, b) => b.v - a.v).slice(0, 10);

  const issueRows = Object.entries(issuesByDevice).map(([k, v]) => ({ k, label: k, v: v as number })).sort((a, b) => b.v - a.v).slice(0, 10);
  const deviceIssueRows = Object.entries(devicesByIssue).map(([k, v]) => ({ k, label: k, v: v as number })).sort((a, b) => b.v - a.v).slice(0, 10);

  const Bar = ({ label, value, total, color }: { label: string; value: number; total: number; color: string }) => (
    <div style={{ marginBottom: 10 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.8rem', marginBottom: 3 }}>
        <span style={{ color: 'var(--color-text-secondary)' }}>{label}</span>
        <span style={{ fontWeight: 600 }}>{value}</span>
      </div>
      <div style={{ background: 'var(--color-bg)', borderRadius: 6, height: 8, overflow: 'hidden' }}>
        <div style={{ width: `${total > 0 ? Math.min(100, (value / total) * 100) : 0}%`, background: color, height: 8, borderRadius: 6 }} />
      </div>
    </div>
  );

  return (
    <div className="page-content">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
          </button>
          <div>
            <h1 className="top-bar-title">รายงาน</h1>
            <span className="top-bar-subtitle">สรุปภาพรวมและวิเคราะห์ข้อมูล</span>
          </div>
        </div>
        <div className="top-bar-actions">
          <button className="btn btn-secondary" onClick={() => fetchAvgResolution()}>⏱ Avg Resolution</button>
          <button className="btn btn-secondary" onClick={exportCSV}>⬇ Export CSV</button>
          <button className="btn btn-secondary" onClick={loadSelfService}>🤖 Self-Service</button>
          <button className="btn btn-ghost" onClick={loadAll}>⟳</button>
        </div>
      </div>

      {error && (
        <div style={{ padding: '10px 14px', background: 'var(--color-danger-light)', color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem', marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* สรุปภาพรวม */}
      <div className="stat-cards-grid">
        <div className="stat-card">
          <div className="stat-card-icon purple">🎫</div>
          <div className="stat-card-value">{totalTickets}</div>
          <div className="stat-card-label">Ticket ทั้งหมด</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-icon blue">🟠</div>
          <div className="stat-card-value">{openTickets}</div>
          <div className="stat-card-label">งานที่ยังไม่เสร็จ</div>
        </div>
        <div className="stat-card">
          <div className="stat-card-icon green">✅</div>
          <div className="stat-card-value">{resolutionRate}%</div>
          <div className="stat-card-label">อัตราปิดงาน ({closedCount})</div>
        </div>
        {avgResolutionHours != null && (
          <div className="stat-card">
            <div className="stat-card-icon orange">⏱</div>
            <div className="stat-card-value">{typeof avgResolutionHours === 'number' ? avgResolutionHours.toFixed(1) : avgResolutionHours}</div>
            <div className="stat-card-label">เวลาเฉลี่ยแก้ไข (ชม.)</div>
          </div>
        )}
        <div className="stat-card">
          <div className="stat-card-icon gray">🖥️</div>
          <div className="stat-card-value">{totalDevices}</div>
          <div className="stat-card-label">อุปกรณ์</div>
        </div>
        {selfService > 0 && (
          <div className="stat-card">
            <div className="stat-card-icon teal">🤖</div>
            <div className="stat-card-value">{selfService}</div>
            <div className="stat-card-label">แก้ไขได้เอง (AI)</div>
          </div>
        )}
      </div>

      {/* กลุ่มชาร์ต 1: สถานะ + ความเร่งด่วน */}
      <div className="charts-row">
        <div className="chart-card">
          <div className="card-header">
            <span className="card-title">Ticket ตามสถานะ</span>
            <span className="card-badge">{totalTickets} รายการ</span>
          </div>
          <div style={{ padding: '8px 16px 16px' }}>
            {statusRows.length === 0 ? <div className="empty-text" style={{ padding: 20, textAlign: 'center' }}>ไม่มีข้อมูล</div> :
              statusRows.map((r) => (<Bar key={r.k} label={r.label} value={r.v} total={totalTickets} color={STATUS_COLORS[r.k] || '#7C3AED'} />))}
          </div>
        </div>
        <div className="chart-card">
          <div className="card-header">
            <span className="card-title">Ticket ตามความเร่งด่วน</span>
            <span className="card-badge">{totalTickets} รายการ</span>
          </div>
          <div style={{ padding: '8px 16px 16px' }}>
            {priorityRows.length === 0 ? <div className="empty-text" style={{ padding: 20, textAlign: 'center' }}>ไม่มีข้อมูล</div> :
              priorityRows.map((r) => (<Bar key={r.k} label={r.label} value={r.v} total={totalTickets} color={PRIORITY_COLORS[r.k] || '#7C3AED'} />))}
          </div>
        </div>
      </div>

      {/* กลุ่มชาร์ต 2: อุปกรณ์ + ปัญหาตามอุปกรณ์ */}
      <div className="charts-row">
        <div className="chart-card">
          <div className="card-header">
            <span className="card-title">อุปกรณ์ตามประเภท (Top 10)</span>
            <span className="card-badge">{totalDevices} เครื่อง</span>
          </div>
          <div style={{ padding: '8px 16px 16px' }}>
            {typeRows.length === 0 ? <div className="empty-text" style={{ padding: 20, textAlign: 'center' }}>ไม่มีข้อมูล</div> :
              typeRows.map((r) => (<Bar key={r.k} label={r.k} value={r.v} total={totalDevices} color="#2563EB" />))}
          </div>
        </div>
        <div className="chart-card">
          <div className="card-header">
            <span className="card-title">ปัญหาตามประเภท (Top 10)</span>
            <span className="card-badge">{issueRows.length} หมวด</span>
          </div>
          <div style={{ padding: '8px 16px 16px' }}>
            {issueRows.length === 0 ? <div className="empty-text" style={{ padding: 20, textAlign: 'center' }}>ไม่มีข้อมูล</div> :
              issueRows.map((r) => (<Bar key={r.k} label={r.label} value={r.v} total={totalTickets} color="#8B5CF6" />))}
          </div>
        </div>
      </div>

      {/* Self-service + อุปกรณ์ตามปัญหา */}
      <div className="charts-row">
        {recentSelfService.length > 0 && (
          <div className="chart-card" style={{ flex: 1 }}>
            <div className="card-header"><span className="card-title">Self-Service ล่าสุด</span></div>
            <div style={{ padding: '8px 16px 16px', fontSize: '0.82rem' }}>
              {recentSelfService.map((s: any) => (
                <div key={s.ticket_id || s.id} style={{ marginBottom: 6 }}>
                  <b>{s.ticket_id || '—'}</b>: {s.title || s.symptom || '—'} <span style={{ color: 'var(--color-text-secondary)' }}>| {fmtDate(s.created_at)}</span>
                </div>
              ))}
            </div>
          </div>
        )}
        <div className="chart-card" style={{ flex: 1 }}>
          <div className="card-header"><span className="card-title">อุปกรณ์ตามปัญหา (Top)</span></div>
          <div style={{ padding: '8px 16px 16px' }}>
            {deviceIssueRows.length === 0 ? <div className="empty-text" style={{ padding: 20, textAlign: 'center' }}>ไม่มีข้อมูล</div> :
              deviceIssueRows.map((r) => (<Bar key={r.k} label={r.label} value={r.v} total={totalTickets} color="#10B981" />))}
          </div>
        </div>
      </div>

      {/* Ticket ล่าสุด */}
      <div className="page-section">
        <div className="section-header">
          <span className="section-title">Ticket ล่าสุด ({stats?.recent_tickets?.length ?? 0})</span>
          <span className="section-action" onClick={() => { setLoading(true); loadAll(); }}>⟳ Refresh</span>
        </div>
        <div className="section-body">
          {!stats?.recent_tickets?.length ? (
            <div className="empty-state" style={{ padding: '24px' }}><span className="empty-text">ยังไม่มี ticket</span></div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr><th>Ticket</th><th>หัวข้อ</th><th>สถานะ</th><th>ความเร่งด่วน</th><th>อุปกรณ์</th><th>ห้อง</th><th>สร้างเมื่อ</th></tr>
                </thead>
                <tbody>
                  {stats.recent_tickets.map((t: any) => (
                    <tr key={t.ticket_id} style={{ cursor: 'pointer' }} onClick={() => openTicket(t.ticket_id)}>
                      <td className="table-id">{t.ticket_id}</td>
                      <td>{t.title}</td>
                      <td><span className={`badge badge-${t.status}`}>{STATUS_LABELS[t.status] || t.status}</span></td>
                      <td><span className={`badge badge-priority-${t.priority}`}>{t.priority}</span></td>
                      <td>{t.device_type || t.device_id || '—'}</td>
                      <td>{t.room_name || '—'}</td>
                      <td style={{ fontSize: '0.8rem', color: 'var(--color-text-tertiary)' }}>{fmtDate(t.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* ประวัติการอัปเดต Ticket */}
      <div className="page-section">
        <div className="section-header">
          <span className="section-title">ประวัติการอัปเดต Ticket</span>
          <span className="section-action">คลิกแถว ticket ข้างบนเพื่อดูประวัติ</span>
        </div>
        <div className="section-body">
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input className="input" placeholder="กรอก Ticket ID เช่น SC-2026-000001" value={historyTicket}
              onChange={(e) => setHistoryTicket(e.target.value)}
              style={{ maxWidth: 280 }} />
            <button className="btn btn-primary" onClick={() => fetchHistory()}>ดึงประวัติ</button>
          </div>
          {historyLoading && <div className="empty-text">กำลังโหลด...</div>}
          {!historyLoading && history.length === 0 && <div className="empty-text">ยังไม่มีประวัติ (เลือก ticket หรือกรอก ID กดดึง)</div>}
          {history.length > 0 && (
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>อันดับ</th><th>จากสถานะ</th><th>ไปสถานะ</th><th>ผู้ดำเนินการ</th><th>หมายเหตุ</th><th>เวลา</th></tr></thead>
                <tbody>
                  {history.map((h: any, i: number) => (
                    <tr key={h.id || i}>
                      <td>{i + 1}</td>
                      <td>{h.from_status || '—'}</td>
                      <td><b>{h.to_status}</b></td>
                      <td>{h.author_name || h.changed_by || '—'}</td>
                      <td>{h.note || '—'}</td>
                      <td style={{ fontSize: '0.8rem', color: 'var(--color-text-tertiary)' }}>{fmtDate(h.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* ยอด ticket ตามอุปกรณ์ */}
      <div className="page-section">
        <div className="section-header">
          <span className="section-title">ยอด Ticket ตามอุปกรณ์ (Device)</span>
        </div>
        <div className="section-body">
          <div style={{ display: 'flex', gap: 8, marginBottom: 12 }}>
            <input className="input" placeholder="กรอก Device ID เช่น DIS-01"
              onKeyDown={(e) => { if (e.key === 'Enter') fetchTicketsByDevice((e.target as HTMLInputElement).value); }} />
            <button className="btn btn-primary" onClick={() => {
              const inp = document.querySelector<HTMLInputElement>('.page-section .input');
              if (inp) fetchTicketsByDevice(inp.value);
            }}>ค้นหา</button>
          </div>
          {deviceTicketsLoading && <div className="empty-text">กำลังโหลด...</div>}
          {!deviceTicketsLoading && ticketsByDevice.length === 0 && <div className="empty-text">ไม่มีข้อมูลอุปกรณ์นี้</div>}
          {ticketsByDevice.length > 0 && (
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>Ticket</th><th>หัวข้อ</th><th>สถานะ</th><th>อุปกรณ์</th><th>ห้อง</th><th>ความเร่งด่วน</th><th>สร้างเมื่อ</th></tr></thead>
                <tbody>
                  {ticketsByDevice.map((t: any) => (
                    <tr key={t.ticket_id}>
                      <td className="table-id">{t.ticket_id}</td>
                      <td>{t.title}</td>
                      <td><span className={`badge badge-${t.status}`}>{STATUS_LABELS[t.status] || t.status}</span></td>
                      <td>{t.device_id || '—'}</td>
                      <td>{t.room_name || '—'}</td>
                      <td>{t.priority}</td>
                      <td style={{ fontSize: '0.8rem', color: 'var(--color-text-tertiary)' }}>{fmtDate(t.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* ปัญหาแยกตามอุปกรณ์ */}
      <div className="page-section">
        <div className="section-header"><span className="section-title">ปัญหาพบตามอุปกรณ์ (Issue × Device)</span></div>
        <div className="section-body">
          {Object.keys(issuesByDevice).length === 0 ? <div className="empty-text">ยังไม่มีข้อมูล</div> : (
            <div className="table-wrap">
              <table className="data-table">
                <thead><tr><th>ประเภทปัญหา</th><th>จำนวน</th><th>คิดเป็น %</th></tr></thead>
                <tbody>
                  {issueRows.map((r: any) => (
                    <tr key={r.k}><td>{r.label}</td><td>{r.v}</td><td>{totalTickets > 0 ? Math.round(r.v / totalTickets * 100) : 0}%</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Self-Service ที่ผ่านมา */}
      <div className="page-section">
        <div className="section-header">
          <span className="section-title">Self-Service ที่ผ่านมา ({selfServiceList.length})</span>
          <span className="section-action" onClick={loadSelfService}>⟳ โหลด</span>
        </div>
        <div className="section-body">
          {selfServiceLoading ? <div className="empty-text">กำลังโหลด...</div>
            : selfServiceList.length === 0 ? <div className="empty-text">ยังไม่มีข้อมูล self-service — กดปุ่ม "🤖 Self-Service" เพื่อโหลด</div>
            : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr><th>วันที่</th><th>อุปกรณ์</th><th>ประเภท</th><th>ห้อง</th><th>อาการ/ปัญหา</th><th>ช่วยได้ไหม</th><th>เวลาที่ประหยัด</th></tr>
                  </thead>
                  <tbody>
                    {selfServiceList.map((s: any) => (
                      <tr key={s.id}>
                        <td style={{ fontSize: '0.8rem', color: 'var(--color-text-tertiary)', whiteSpace: 'nowrap' }}>{fmtDate(s.created_at)}</td>
                        <td className="table-id">{s.device_id || '—'}</td>
                        <td>{s.device_type || '—'}</td>
                        <td>{s.room_name || '—'}</td>
                        <td style={{ fontSize: '0.85rem' }}>{s.symptom || '—'}</td>
                        <td>
                          <span className={`badge ${s.resolved ? 'badge-resolved' : 'badge-cancelled'}`} style={{ fontSize: '0.75rem' }}>
                            {s.resolved ? '✅ แก้ได้เอง' : '❌ ส่งต่อช่าง'}
                          </span>
                        </td>
                        <td>{s.time_saved_minutes != null ? `~${s.time_saved_minutes} นาที` : '—'}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
        </div>
      </div>

      {selectedTicket && (
        <div className="page-section">
          <div className="section-header">
            <span className="section-title">Ticket: {selectedTicket.ticket_id}</span>
            <span className="section-action" onClick={() => setSelectedTicket(null)}>✕ ปิด</span>
          </div>
          <div className="section-body" style={{ fontSize: '0.9rem' }}>
            <p><b>หัวข้อ:</b> {selectedTicket.title}</p>
            <p><b>สถานะ:</b> {STATUS_LABELS[selectedTicket.status] || selectedTicket.status}</p>
            <p><b>อุปกรณ์:</b> {selectedTicket.device_id || '—'} | <b>ห้อง:</b> {selectedTicket.room_name || '—'}</p>
            <p><b>ผู้แจ้ง:</b> {selectedTicket.reporter_name || '—'} | <b>เบอร์:</b> {selectedTicket.reporter_phone || '—'}</p>
            <p><b>อาการ:</b> {selectedTicket.symptom || '—'}</p>
            <p><b>สร้างเมื่อ:</b> {fmtDate(selectedTicket.created_at)}</p>
          </div>
        </div>
      )}
    </div>
  );
}