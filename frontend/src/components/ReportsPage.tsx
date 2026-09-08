import React, { useState, useEffect } from 'react';
import { api } from '../api/client';

const STATUS_LABELS: Record<string, string> = {
  new: 'รอรับเรื่อง', assigned: 'มอบหมายแล้ว', in_progress: 'กำลังดำเนินการ',
  pending: 'รออะไหล่/รอภายนอก', resolved: 'เสร็จสิ้น',
  closed: 'ปิดงาน', cancelled: 'ยกเลิก',
};
const PRIORITY_LABELS: Record<string, string> = {
  low: 'Low', normal: 'Normal', high: 'High', critical: 'Critical',
};
const STATUS_COLORS: Record<string, string> = {
  new: '#EF4444', assigned: '#F59E0B', in_progress: '#2563EB',
  pending: '#8B5CF6', resolved: '#10B981', closed: '#6B7280', cancelled: '#EF4444',
};
const PRIORITY_COLORS: Record<string, string> = {
  low: '#10B981', normal: '#2563EB', high: '#F59E0B', critical: '#EF4444',
};

export default function ReportsPage({ onBack }: { onBack: () => void }) {
  const [stats, setStats] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.getStats()
      .then(setStats)
      .catch((e) => setError(e.message || 'โหลดไม่สำเร็จ'))
      .finally(() => setLoading(false));
  }, []);

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

  if (loading) return (
    <div className="page-content">
      <div className="loading-state" style={{ padding: '60px' }}>
        <div className="spinner" />
        <span>กำลังโหลดรายงาน...</span>
      </div>
    </div>
  );

  const byStatus = stats?.by_status || {};
  const byPriority = stats?.by_priority || {};
  const byType = stats?.by_type || {};
  const devicesByStatus = stats?.devices_by_status || {};

  const totalTickets = stats?.total_tickets ?? 0;
  const totalDevices = stats?.total_devices ?? 0;
  const openTickets = (stats?.new ?? 0) + (stats?.assigned ?? 0) + (stats?.in_progress ?? 0);
  const closedCount = (stats?.resolved ?? 0) + (stats?.closed ?? 0);
  const resolutionRate = totalTickets > 0 ? Math.round(closedCount / totalTickets * 100) : 0;
  const selfService = stats?.self_service_total ?? 0;

  const statusRows = Object.entries(byStatus).map(([k, v]) => ({ k, label: STATUS_LABELS[k] || k, v: v as number })).sort((a, b) => b.v - a.v);
  const priorityRows = Object.entries(byPriority).map(([k, v]) => ({ k, label: PRIORITY_LABELS[k] || k, v: v as number })).sort((a, b) => b.v - a.v);
  const typeRows = Object.entries(byType).map(([k, v]) => ({ k, v: v as number })).sort((a, b) => b.v - a.v).slice(0, 10);

  const Bar = ({ label, value, total, color }: { label: string; value: number; total: number; color: string }) => (
    <div style={{ marginBottom: 12 }}>
      <div style={{ display: 'flex', justifyContent: 'space-between', fontSize: '0.82rem', marginBottom: 4 }}>
        <span style={{ color: 'var(--color-text-secondary)' }}>{label}</span>
        <span style={{ fontWeight: 600 }}>{value}</span>
      </div>
      <div style={{ background: 'var(--color-bg)', borderRadius: 6, height: 10, overflow: 'hidden' }}>
        <div style={{ width: `${total > 0 ? Math.min(100, (value / total) * 100) : 0}%`, background: color, height: 10, borderRadius: 6, transition: 'width 0.4s' }} />
      </div>
    </div>
  );

  return (
    <div className="page-content">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          </button>
          <div>
            <h1 className="top-bar-title">รายงาน</h1>
            <span className="top-bar-subtitle">สรุปภาพรวมและวิเคราะห์ข้อมูล</span>
          </div>
        </div>
        <div className="top-bar-actions">
          <button className="btn btn-secondary" onClick={exportCSV}>⬇ Export CSV</button>
          <button className="btn btn-ghost" onClick={() => { setLoading(true); api.getStats().then(setStats).catch((e) => setError(e.message)).finally(() => setLoading(false)); }}>⟳</button>
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
            {statusRows.length === 0 ? <div className="empty-text" style={{ padding: 20, textAlign: 'center' }}>ไม่มีข้อมูล</div> : (
              statusRows.map((r) => (
                <Bar key={r.k} label={r.label} value={r.v} total={totalTickets} color={STATUS_COLORS[r.k] || '#7C3AED'} />
              ))
            )}
          </div>
        </div>

        <div className="chart-card">
          <div className="card-header">
            <span className="card-title">Ticket ตามความเร่งด่วน</span>
            <span className="card-badge">{totalTickets} รายการ</span>
          </div>
          <div style={{ padding: '8px 16px 16px' }}>
            {priorityRows.length === 0 ? <div className="empty-text" style={{ padding: 20, textAlign: 'center' }}>ไม่มีข้อมูล</div> : (
              priorityRows.map((r) => (
                <Bar key={r.k} label={r.label} value={r.v} total={totalTickets} color={PRIORITY_COLORS[r.k] || '#7C3AED'} />
              ))
            )}
          </div>
        </div>
      </div>

      {/* กลุ่มชาร์ต 2: อุปกรณ์ */}
      <div className="charts-row">
        <div className="chart-card">
          <div className="card-header">
            <span className="card-title">อุปกรณ์ตามประเภท (Top 10)</span>
            <span className="card-badge">{totalDevices} เครื่อง</span>
          </div>
          <div style={{ padding: '8px 16px 16px' }}>
            {typeRows.length === 0 ? <div className="empty-text" style={{ padding: 20, textAlign: 'center' }}>ไม่มีข้อมูล</div> : (
              typeRows.map((r) => (
                <Bar key={r.k} label={r.k} value={r.v} total={totalDevices} color="#2563EB" />
              ))
            )}
          </div>
        </div>

        <div className="chart-card">
          <div className="card-header">
            <span className="card-title">สถานะอุปกรณ์</span>
            <span className="card-badge">{totalDevices} เครื่อง</span>
          </div>
          <div style={{ padding: '8px 16px 16px' }}>
            {Object.keys(devicesByStatus).length === 0 ? <div className="empty-text" style={{ padding: 20, textAlign: 'center' }}>ไม่มีข้อมูล</div> : (
              Object.entries(devicesByStatus).map(([k, v]) => {
                const vn = v as number;
                const label = k === 'active' ? 'ใช้งาน' : k === 'inactive' ? 'ไม่ใช้งาน' : k === 'decommissioned' ? 'ปลดระวาง' : k;
                return <Bar key={k} label={label} value={vn} total={totalDevices} color="#10B981" />;
              })
            )}
          </div>
        </div>
      </div>

      {/* Ticket ล่าสุด */}
      <div className="page-section">
        <div className="section-header">
          <span className="section-title">Ticket ล่าสุด ({stats?.recent_tickets?.length ?? 0})</span>
          <span className="section-action" onClick={exportCSV}>⬇ Export</span>
        </div>
        <div className="section-body">
          {!stats?.recent_tickets?.length ? (
            <div className="empty-state" style={{ padding: '24px' }}>
              <span className="empty-text">ยังไม่มี ticket</span>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr><th>Ticket</th><th>หัวข้อ</th><th>สถานะ</th><th>ความเร่งด่วน</th><th>อุปกรณ์</th><th>ห้อง</th><th>สร้างเมื่อ</th></tr>
                </thead>
                <tbody>
                  {stats.recent_tickets.map((t: any) => (
                    <tr key={t.ticket_id}>
                      <td className="table-id">{t.ticket_id}</td>
                      <td>{t.title}</td>
                      <td><span className={`badge badge-${t.status}`}>{STATUS_LABELS[t.status] || t.status}</span></td>
                      <td><span className={`badge badge-priority-${t.priority}`}>{t.priority}</span></td>
                      <td>{t.device_type || t.device_id || '—'}</td>
                      <td>{t.room_name || '—'}</td>
                      <td style={{ fontSize: '0.8rem', color: 'var(--color-text-tertiary)' }}>
                        {new Date(t.created_at).toLocaleDateString('th-TH', { day: '2-digit', month: 'short', year: 'numeric' })}
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