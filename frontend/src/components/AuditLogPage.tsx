import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';

const PAGE_SIZE = 50;

// ป้ายกำกับของ action ที่ยืนยันแล้วว่ามีใน backend — ที่เหลือแสดงค่าดิบตามจริง
const ACTION_LABELS: Record<string, string> = {
  pm_plan_create: 'สร้างแผน PM',
  pm_generate: 'สร้างงาน PM ตามรอบ',
  pm_task_submit: 'ส่งผลตรวจ PM',
  pm_task_skip: 'ข้ามงาน PM',
};

function fmtDateTime(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('th-TH', { dateStyle: 'medium', timeStyle: 'medium' });
}

/** old_value/new_value อาจเป็น object, array หรือข้อความล้วน */
function formatValue(value: unknown): string {
  if (value === null || value === undefined || value === '') return '—';
  if (typeof value === 'string') return value;
  try {
    return JSON.stringify(value, null, 2);
  } catch {
    return String(value);
  }
}

function summarize(value: unknown, max = 60): string {
  const text = formatValue(value).replace(/\s+/g, ' ').trim();
  if (text === '—') return '—';
  return text.length > max ? `${text.slice(0, max)}…` : text;
}

export default function AuditLogPage({ onBack }: { onBack: () => void }) {
  const [logs, setLogs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [detail, setDetail] = useState<any | null>(null);

  // ค่าที่พิมพ์ในฟอร์ม (ยังไม่ยิง) แยกจากค่าที่ใช้ค้นจริง เพื่อไม่ยิง API ทุกตัวอักษร
  const [draft, setDraft] = useState({ action: '', entity_type: '', entity_id: '', user_id: '' });
  const [filters, setFilters] = useState({ action: '', entity_type: '', entity_id: '', user_id: '' });

  const load = useCallback(() => {
    setLoading(true);
    setError(null);
    const userId = Number(filters.user_id);
    api
      .listAuditLogs({
        action: filters.action.trim() || undefined,
        entity_type: filters.entity_type.trim() || undefined,
        entity_id: filters.entity_id.trim() || undefined,
        user_id: filters.user_id.trim() && Number.isFinite(userId) ? userId : undefined,
        limit: PAGE_SIZE,
        offset: page * PAGE_SIZE,
      })
      .then((rows) => setLogs(Array.isArray(rows) ? rows : []))
      .catch((e: any) => setError(e?.message || 'โหลดประวัติการใช้งานไม่สำเร็จ'))
      .finally(() => setLoading(false));
  }, [filters, page]);

  useEffect(() => { load(); }, [load]);

  const applyFilters = (e: React.FormEvent) => {
    e.preventDefault();
    setPage(0);
    setFilters({ ...draft });
  };

  const clearFilters = () => {
    const empty = { action: '', entity_type: '', entity_id: '', user_id: '' };
    setDraft(empty);
    setFilters(empty);
    setPage(0);
  };

  const hasNext = logs.length === PAGE_SIZE;

  return (
    <div className="page-content">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack} aria-label="กลับ">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
          </button>
          <div>
            <h1 className="top-bar-title">ประวัติการใช้งานระบบ (Audit Log)</h1>
            <span className="top-bar-subtitle">
              หน้า {page + 1} · แสดง {logs.length} รายการ — เรียงจากใหม่ไปเก่า
            </span>
          </div>
        </div>
        <div className="top-bar-actions">
          <button className="btn btn-ghost" onClick={load} aria-label="โหลดใหม่">⟳</button>
        </div>
      </div>

      <form onSubmit={applyFilters}>
        <div className="form-row" style={{ marginBottom: 8 }}>
          <div className="form-group">
            <label className="form-label">การกระทำ (action)</label>
            <input
              className="form-input"
              value={draft.action}
              onChange={(e) => setDraft({ ...draft, action: e.target.value })}
              placeholder="เช่น pm_task_submit"
            />
          </div>
          <div className="form-group">
            <label className="form-label">ชนิดข้อมูล (entity type)</label>
            <input
              className="form-input"
              value={draft.entity_type}
              onChange={(e) => setDraft({ ...draft, entity_type: e.target.value })}
              placeholder="เช่น pm_task"
            />
          </div>
        </div>
        <div className="form-row" style={{ marginBottom: 12 }}>
          <div className="form-group">
            <label className="form-label">รหัสข้อมูล (entity id)</label>
            <input
              className="form-input"
              value={draft.entity_id}
              onChange={(e) => setDraft({ ...draft, entity_id: e.target.value })}
              placeholder="เช่น PM-202609-0001"
            />
          </div>
          <div className="form-group">
            <label className="form-label">รหัสผู้ใช้ (user id)</label>
            <input
              className="form-input"
              type="number"
              min={1}
              value={draft.user_id}
              onChange={(e) => setDraft({ ...draft, user_id: e.target.value })}
              placeholder="เช่น 3"
            />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
          <button type="submit" className="btn btn-primary">ค้นหา</button>
          <button type="button" className="btn btn-ghost" onClick={clearFilters}>ล้างตัวกรอง</button>
        </div>
      </form>

      {error && (
        <div style={{ padding: '10px 14px', background: 'var(--color-danger-light)', color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem', marginBottom: 16 }}>
          {error}
        </div>
      )}

      <div className="page-section">
        <div className="section-body">
          {loading ? (
            <div className="loading-state" style={{ padding: 40 }}>
              <div className="spinner" />
              <span>กำลังโหลด...</span>
            </div>
          ) : logs.length === 0 ? (
            <div className="empty-state" style={{ padding: 40 }}>
              <svg className="empty-icon" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                <path d="M14 2v6h6M9 13h6M9 17h6"/>
              </svg>
              <span className="empty-text">ไม่พบรายการตามเงื่อนไขนี้</span>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>เวลา</th>
                    <th>ผู้ใช้</th>
                    <th>การกระทำ</th>
                    <th>ข้อมูลที่ถูกแก้</th>
                    <th>ค่าใหม่</th>
                    <th>IP</th>
                    <th></th>
                  </tr>
                </thead>
                <tbody>
                  {logs.map((log) => (
                    <tr key={log.id}>
                      <td style={{ fontSize: '0.78rem', whiteSpace: 'nowrap' }}>{fmtDateTime(log.created_at)}</td>
                      <td style={{ fontSize: '0.82rem' }}>
                        {log.user_name || (log.user_id ? `#${log.user_id}` : 'ระบบ')}
                        {log.user_role && (
                          <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)' }}>{log.user_role}</div>
                        )}
                      </td>
                      <td style={{ fontSize: '0.82rem', fontWeight: 500 }}>
                        {ACTION_LABELS[log.action] || log.action}
                        {ACTION_LABELS[log.action] && (
                          <div style={{ fontSize: '0.7rem', color: 'var(--color-text-tertiary)', fontWeight: 400 }}>{log.action}</div>
                        )}
                      </td>
                      <td style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary)' }}>
                        {log.entity_type || '—'}
                        {log.entity_id && <div style={{ fontSize: '0.72rem' }}>{log.entity_id}</div>}
                      </td>
                      <td style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)', maxWidth: 240, overflowWrap: 'anywhere' }}>
                        {summarize(log.new_value)}
                      </td>
                      <td style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)' }}>{log.ip_address || '—'}</td>
                      <td>
                        <button
                          className="btn btn-ghost"
                          style={{ padding: '4px 10px', fontSize: '0.78rem' }}
                          onClick={() => setDetail(log)}
                        >
                          ดู
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      <div style={{ display: 'flex', gap: 8, justifyContent: 'center', alignItems: 'center', marginTop: 16, flexWrap: 'wrap' }}>
        <button className="btn btn-ghost" onClick={() => setPage((p) => Math.max(0, p - 1))} disabled={page === 0 || loading}>
          ← ก่อนหน้า
        </button>
        <span style={{ fontSize: '0.82rem', color: 'var(--color-text-secondary)' }}>หน้า {page + 1}</span>
        <button className="btn btn-ghost" onClick={() => setPage((p) => p + 1)} disabled={!hasNext || loading}>
          ถัดไป →
        </button>
      </div>

      {detail && (
        <div className="panel-overlay" onClick={() => setDetail(null)}>
          <div className="repair-panel" style={{ width: 620, maxWidth: '95vw' }} onClick={(e) => e.stopPropagation()}>
            <div className="repair-panel-header">
              <h3 className="repair-panel-title">{ACTION_LABELS[detail.action] || detail.action}</h3>
              <button className="repair-panel-close" onClick={() => setDetail(null)} aria-label="ปิด">✕</button>
            </div>
            <div className="repair-panel-body">
              <div className="form-row" style={{ marginBottom: 12 }}>
                <div className="form-group">
                  <div className="form-label">เวลา</div>
                  <div style={{ fontSize: '0.85rem' }}>{fmtDateTime(detail.created_at)}</div>
                </div>
                <div className="form-group">
                  <div className="form-label">ผู้ใช้</div>
                  <div style={{ fontSize: '0.85rem' }}>
                    {detail.user_name || (detail.user_id ? `#${detail.user_id}` : 'ระบบ')}
                    {detail.user_role ? ` · ${detail.user_role}` : ''}
                  </div>
                </div>
              </div>
              <div className="form-row" style={{ marginBottom: 12 }}>
                <div className="form-group">
                  <div className="form-label">ข้อมูล</div>
                  <div style={{ fontSize: '0.85rem' }}>
                    {detail.entity_type || '—'}{detail.entity_id ? ` · ${detail.entity_id}` : ''}
                  </div>
                </div>
                <div className="form-group">
                  <div className="form-label">IP</div>
                  <div style={{ fontSize: '0.85rem' }}>{detail.ip_address || '—'}</div>
                </div>
              </div>

              <div className="form-group">
                <div className="form-label">ค่าก่อนแก้</div>
                <pre style={{
                  margin: 0, padding: 12, background: 'var(--color-bg)',
                  borderRadius: 'var(--radius-sm)', fontSize: '0.75rem',
                  whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 200, overflowY: 'auto',
                }}>
                  {formatValue(detail.old_value)}
                </pre>
              </div>
              <div className="form-group">
                <div className="form-label">ค่าหลังแก้</div>
                <pre style={{
                  margin: 0, padding: 12, background: 'var(--color-bg)',
                  borderRadius: 'var(--radius-sm)', fontSize: '0.75rem',
                  whiteSpace: 'pre-wrap', overflowWrap: 'anywhere', maxHeight: 200, overflowY: 'auto',
                }}>
                  {formatValue(detail.new_value)}
                </pre>
              </div>

              <button className="btn btn-ghost btn-full" onClick={() => setDetail(null)}>ปิด</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}