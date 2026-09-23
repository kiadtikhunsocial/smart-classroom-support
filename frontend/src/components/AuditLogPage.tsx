import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import '../styles/audit-log.css';

const PAGE_SIZE = 30;
const ACTIONS: Record<string, string> = {
  login: 'เข้าสู่ระบบ', login_failed: 'เข้าสู่ระบบไม่สำเร็จ',
  device_create: 'เพิ่มอุปกรณ์', device_update: 'แก้ไขอุปกรณ์', device_delete: 'ลบอุปกรณ์',
  user_create: 'เพิ่มผู้ใช้', user_update: 'แก้ไขผู้ใช้', user_delete: 'ลบผู้ใช้', user_role_change: 'เปลี่ยนสิทธิ์ผู้ใช้',
  membership_apply: 'สมัครสมาชิก', membership_approve: 'อนุมัติสมาชิก', membership_reject: 'ปฏิเสธสมาชิก',
  ticket_assign: 'มอบหมายงานซ่อม', ticket_accept: 'รับงานซ่อม', ticket_resolve: 'ซ่อมเสร็จ',
  ticket_close: 'ปิดงานซ่อม', ticket_reopen: 'เปิดงานซ่อมอีกครั้ง', ticket_cancel: 'ยกเลิกงานซ่อม',
  kb_create: 'เพิ่มบทความ', kb_update: 'แก้ไขบทความ', kb_delete: 'ลบบทความ',
  pm_plan_create: 'สร้างแผน PM', pm_plan_update: 'แก้ไขแผน PM', pm_plan_delete: 'ลบแผน PM',
  pm_generate: 'สร้างงาน PM', pm_task_submit: 'ส่งผลตรวจ PM', pm_task_skip: 'ข้ามงาน PM', pm_task_edit: 'แก้ไขงาน PM ย้อนหลัง',
  pm_rules_run: 'ประมวลผลกฎ PM', pm_flag_update: 'อัปเดตสถานะอุปกรณ์',
  settings_update: 'เปลี่ยนการตั้งค่า', sales_record_create: 'เพิ่มรายการขาย', sales_record_status: 'เปลี่ยนสถานะการขาย',
  customer_signup: 'ลูกค้าลงทะเบียน',
};
const ENTITY: Record<string, string> = {
  device: 'อุปกรณ์', user: 'ผู้ใช้', ticket: 'งานซ่อม', kb_article: 'บทความ',
  pm_plan: 'แผน PM', pm_task: 'งาน PM', pm_rule: 'กฎ PM', device_health_flag: 'สุขภาพอุปกรณ์',
  setting: 'การตั้งค่า', sales_record: 'รายการขาย', sales_lead: 'ลูกค้า', membership_application: 'คำขอสมาชิก',
};
type AuditRow = {
  id: number; created_at: string; user_name?: string | null; user_id?: number | null; user_role?: string | null;
  action: string; entity_type?: string | null; entity_id?: string | number | null;
  old_value?: unknown; new_value?: unknown; ip_address?: string | null;
};
type Filters = { action: string; entity_id: string; user_id: string; date_from: string; date_to: string; include_logins: boolean };
const emptyFilters: Filters = { action: '', entity_id: '', user_id: '', date_from: '', date_to: '', include_logins: false };

function dateTime(value?: string | null): string {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('th-TH', { dateStyle: 'medium', timeStyle: 'short' });
}
function dayLabel(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'ไม่ทราบวันที่' : date.toLocaleDateString('th-TH', { weekday: 'long', day: 'numeric', month: 'long', year: 'numeric' });
}
function dateKey(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? 'unknown' : `${date.getFullYear()}-${date.getMonth()}-${date.getDate()}`;
}
function valueText(value: unknown): string {
  if (value === null || value === undefined || value === '') return 'ไม่มีข้อมูล';
  if (typeof value === 'string') return value;
  return JSON.stringify(value, null, 2);
}

export default function AuditLogPage({ onBack }: { onBack: () => void }) {
  const [logs, setLogs] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [page, setPage] = useState(0);
  const [detail, setDetail] = useState<AuditRow | null>(null);
  const [draft, setDraft] = useState<Filters>(emptyFilters);
  const [filters, setFilters] = useState<Filters>(emptyFilters);
  const [advanced, setAdvanced] = useState(false);

  const load = useCallback(async () => {
    setLoading(true); setError(null);
    try {
      const rows = await api.listAuditLogs({
        action: filters.action || undefined,
        include_logins: filters.include_logins,
        entity_id: filters.entity_id.trim() || undefined,
        user_id: filters.user_id ? Number(filters.user_id) : undefined,
        date_from: filters.date_from || undefined,
        date_to: filters.date_to || undefined,
        limit: PAGE_SIZE, offset: page * PAGE_SIZE,
      });
      setLogs(Array.isArray(rows) ? rows : []);
    } catch (err: any) { setError(err?.message || 'โหลดประวัติไม่สำเร็จ'); }
    finally { setLoading(false); }
  }, [filters, page]);
  useEffect(() => { void load(); }, [load]);

  const submit = (event: React.FormEvent) => {
    event.preventDefault();
    if (draft.date_from && draft.date_to && draft.date_from > draft.date_to) {
      setError('วันที่สิ้นสุดต้องไม่ก่อนวันที่เริ่ม'); return;
    }
    setPage(0); setFilters({ ...draft });
  };
  const clear = () => { setDraft(emptyFilters); setFilters(emptyFilters); setPage(0); };
  const groups = logs.reduce<{ key: string; label: string; rows: AuditRow[] }[]>((all, row) => {
    const key = dateKey(row.created_at);
    if (all[all.length - 1]?.key !== key) all.push({ key, label: dayLabel(row.created_at), rows: [] });
    all[all.length - 1].rows.push(row);
    return all;
  }, []);

  return <div className="page-content audit-page">
    <div className="top-bar">
      <div className="top-bar-title-group"><button className="btn btn-ghost btn-icon" onClick={onBack} aria-label="กลับ">←</button>
        <div><h1 className="top-bar-title">ประวัติการใช้งาน</h1><span className="top-bar-subtitle">ดูว่าใครทำอะไรกับข้อมูล เมื่อไร · เรียงล่าสุดก่อน</span></div></div>
      <button className="btn" type="button" onClick={() => void load()} disabled={loading}>โหลดใหม่</button>
    </div>

    <form className="audit-filters" onSubmit={submit}>
      <div className="audit-filter-row">
        <label>ประเภทเหตุการณ์<select className="form-input" value={draft.action} onChange={(e) => setDraft({ ...draft, action: e.target.value })}>
          <option value="">ทุกประเภท</option>{Object.entries(ACTIONS).map(([value, label]) => <option key={value} value={value}>{label}</option>)}
        </select></label>
        <label>ตั้งแต่วันที่<input className="form-input" type="date" value={draft.date_from} onChange={(e) => setDraft({ ...draft, date_from: e.target.value })} /></label>
        <label>ถึงวันที่<input className="form-input" type="date" value={draft.date_to} onChange={(e) => setDraft({ ...draft, date_to: e.target.value })} /></label>
      </div>
      <label className="audit-login-toggle"><input type="checkbox" checked={draft.include_logins} onChange={(e) => setDraft({ ...draft, include_logins: e.target.checked })} /> รวมเหตุการณ์เข้าสู่ระบบ</label>
      <button type="button" className="audit-advanced-toggle" aria-expanded={advanced} onClick={() => setAdvanced(!advanced)}>{advanced ? 'ซ่อนตัวกรองเพิ่มเติม ↑' : 'ค้นหาด้วยรหัสข้อมูล/ผู้ใช้ ↓'}</button>
      {advanced && <div className="audit-filter-row audit-filter-advanced">
        <label>รหัสข้อมูล<input className="form-input" value={draft.entity_id} onChange={(e) => setDraft({ ...draft, entity_id: e.target.value })} placeholder="เช่น รหัสใบงาน" /></label>
        <label>รหัสผู้ใช้<input className="form-input" type="number" min="1" value={draft.user_id} onChange={(e) => setDraft({ ...draft, user_id: e.target.value })} placeholder="เช่น 3" /></label>
      </div>}
      <div className="audit-filter-actions"><button className="btn btn-primary" type="submit">แสดงผล</button><button className="btn btn-ghost" type="button" onClick={clear}>ล้างตัวกรอง</button></div>
    </form>

    {error && <p className="audit-error" role="alert">{error}</p>}
    <div className="audit-list-head"><strong>เหตุการณ์ {logs.length} รายการ</strong><span>หน้า {page + 1}</span></div>
    {loading ? <div className="loading-state"><div className="spinner" />กำลังโหลด...</div>
      : logs.length === 0 ? <div className="audit-empty">ไม่พบเหตุการณ์ในช่วงเวลาหรือเงื่อนไขที่เลือก</div>
        : groups.map((group) => <section className="audit-day" key={group.key} aria-label={group.label}>
          <h2>{group.label}</h2><div className="audit-events">{group.rows.map((row) => <article className="audit-event" key={row.id}>
            <div className="audit-event-time">{dateTime(row.created_at).split(' ').slice(-1)[0]}</div>
            <div className="audit-event-main"><strong>{ACTIONS[row.action] || row.action}</strong>
              <p>{row.user_name || (row.user_id ? `ผู้ใช้ #${row.user_id}` : 'ระบบ')} · {ENTITY[row.entity_type || ''] || row.entity_type || 'ข้อมูล'}{row.entity_id ? ` #${row.entity_id}` : ''}</p>
            </div><button className="btn btn-ghost" type="button" onClick={() => setDetail(row)}>รายละเอียด</button>
          </article>)}</div>
        </section>)}
    <div className="audit-pagination"><button className="btn" disabled={page === 0 || loading} onClick={() => setPage(page - 1)}>← ก่อนหน้า</button><span>หน้า {page + 1}</span><button className="btn" disabled={logs.length < PAGE_SIZE || loading} onClick={() => setPage(page + 1)}>ถัดไป →</button></div>

    {detail && <div className="panel-overlay" onClick={() => setDetail(null)}><div className="repair-panel audit-detail" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="audit-detail-title">
      <div className="repair-panel-header"><h2 className="repair-panel-title" id="audit-detail-title">{ACTIONS[detail.action] || detail.action}</h2><button className="repair-panel-close" onClick={() => setDetail(null)} aria-label="ปิด">×</button></div>
      <div className="repair-panel-body"><dl className="audit-detail-meta"><div><dt>เวลา</dt><dd>{dateTime(detail.created_at)}</dd></div><div><dt>ผู้ใช้</dt><dd>{detail.user_name || (detail.user_id ? `#${detail.user_id}` : 'ระบบ')}</dd></div><div><dt>ข้อมูล</dt><dd>{ENTITY[detail.entity_type || ''] || detail.entity_type || '—'} {detail.entity_id || ''}</dd></div><div><dt>IP</dt><dd>{detail.ip_address || '—'}</dd></div></dl>
        <details><summary>ข้อมูลก่อนแก้ไข</summary><pre>{valueText(detail.old_value)}</pre></details><details><summary>ข้อมูลหลังแก้ไข</summary><pre>{valueText(detail.new_value)}</pre></details>
        <p className="audit-technical">รหัสเหตุการณ์: {detail.action} · ID: {detail.id}</p>
      </div></div></div>}
  </div>;
}
