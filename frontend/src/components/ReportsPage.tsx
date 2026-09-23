import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';
import '../styles/reports.css';

/* ============================================================================
   ReportsPage — หน้ารายงาน/วิเคราะห์
   ----------------------------------------------------------------------------
   โครงใหม่: KPI ด้านบน → แท็บ 4 กลุ่ม (ภาพรวม / Ticket / อุปกรณ์ / Self-Service)
   เดิมทุกอย่างต่อกันเป็นหน้ายาวมาก เลื่อนหาข้อมูลลำบาก และชาร์ตกับตาราง
   ซ้ำหัวข้อกันหลายจุด แท็บช่วยให้แต่ละกลุ่มอ่านจบในหน้าเดียว
   ข้อมูลโหลดครั้งเดียว (loadAll) แล้วสลับแท็บได้ทันทีโดยไม่ยิง API ซ้ำ
   ========================================================================== */

const STATUS_LABELS: Record<string, string> = {
  new: 'รอรับเรื่อง (New)',
  assigned: 'มอบหมายแล้ว (Assigned)',
  in_progress: 'กำลังดำเนินการ (In Progress)',
  pending: 'รออะไหล่/รอภายนอก (Pending)',
  waiting_parts: 'รออะไหล่ (Waiting for Parts)',
  waiting_user: 'รอผู้ใช้ (Waiting for User)',
  resolved: 'ซ่อมเสร็จ รอยืนยัน (Resolved)',
  closed: 'ปิดงาน (Closed)',
  cancelled: 'ยกเลิก (Cancelled)',
};

/**
 * สีของแถบใช้เป็น CSS property (background) ไม่ใช่ attribute ของ <svg>
 * จึงอ้าง var() ได้ตรง ๆ และเปลี่ยนตามธีมเองโดยไม่ต้อง re-render
 * (fallback ไว้กันกรณี token ยังไม่ถูกโหลด)
 */
const STATUS_COLORS: Record<string, string> = {
  new: 'var(--status-new, #EF4444)',
  assigned: 'var(--status-assigned, #F59E0B)',
  in_progress: 'var(--status-in-progress, #2563EB)',
  pending: 'var(--status-pending, #8B5CF6)',
  waiting_parts: 'var(--status-waiting-parts, #3182CE)',
  waiting_user: 'var(--status-waiting-user, #805AD5)',
  resolved: 'var(--status-resolved, #10B981)',
  closed: 'var(--status-closed, #6B7280)',
  cancelled: 'var(--status-cancelled, #EF4444)',
};

const PRIORITY_LABELS: Record<string, string> = {
  low: 'Low', normal: 'Normal', high: 'High', critical: 'Critical',
};

const PRIORITY_COLORS: Record<string, string> = {
  low: 'var(--status-resolved, #10B981)',
  normal: 'var(--status-in-progress, #2563EB)',
  high: 'var(--status-assigned, #F59E0B)',
  critical: 'var(--status-new, #EF4444)',
};

/** สีเน้นของธีม — fallback ของแถบที่ไม่มีสีเฉพาะ */
const ACCENT_BAR = 'var(--chart-1, #7C3AED)';

type TabId = 'overview' | 'tickets' | 'devices' | 'selfservice';

/** แท็บใช้ข้อความล้วน — ไม่ใช้อิโมจิ เพื่อให้อ่านสม่ำเสมอทุกแพลตฟอร์ม/screen reader */
const TABS: { id: TabId; label: string }[] = [
  { id: 'overview', label: 'ภาพรวม' },
  { id: 'tickets', label: 'Ticket และประวัติ' },
  { id: 'devices', label: 'อุปกรณ์และปัญหา' },
  { id: 'selfservice', label: 'Self-Service (AI)' },
];

function fmtDate(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('th-TH', {
    day: '2-digit', month: 'short', year: 'numeric', hour: '2-digit', minute: '2-digit',
  });
}

function fmtNum(n: number | null | undefined): string {
  if (n == null || !Number.isFinite(Number(n))) return '—';
  return Number(n).toLocaleString('th-TH');
}

/** backend ส่งชื่อคอลัมน์ไม่ตรงกันในแต่ละ endpoint — ดึงป้ายชื่อแบบยืดหยุ่น */
function pickLabel(row: any): string {
  if (row == null) return '—';
  if (typeof row === 'string') return row;
  const v = row.label ?? row.name ?? row.title ?? row.issue ?? row.issue_category
    ?? row.category ?? row.symptom ?? row.device_type ?? row.device_id ?? row.key;
  return v == null || v === '' ? '—' : String(v);
}

/** ป้ายชื่อของ /reports/top-devices — ต้องเป็นตัวเครื่อง ไม่ใช่ประเภท
 *  (pickLabel เจอ device_type ก่อน device_id ทำให้ทุกแถบชื่อซ้ำกัน) */
function pickDeviceLabel(row: any): string {
  if (row == null) return '—';
  if (typeof row === 'string') return row;
  const id = row.device_id ?? row.device_code ?? '';
  const extra = [row.room_name, row.device_type].filter(Boolean).join(' · ');
  if (id) return extra ? `${id} (${extra})` : String(id);
  return pickLabel(row);
}

/** เช่นเดียวกับ pickLabel — ยอดนับอาจมาเป็น count/total/value/failure_count
 *  (/reports/top-devices ส่ง failure_count ทำให้แถบเป็น 0 ถ้าไม่รับชื่อนี้) */
function pickValue(row: any): number {
  if (typeof row === 'number') return row;
  const v = row?.count ?? row?.total ?? row?.value ?? row?.tickets
    ?? row?.ticket_count ?? row?.failure_count ?? row?.failures ?? 0;
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

/** แปลง Record<string, number> เป็นแถวเรียงมากไปน้อย */
function toRows(obj: unknown, limit?: number): { k: string; label: string; v: number }[] {
  if (!obj || typeof obj !== 'object') return [];
  const rows = Object.entries(obj as Record<string, unknown>)
    .map(([k, v]) => ({ k, label: k, v: Number(v) || 0 }))
    .sort((a, b) => b.v - a.v);
  return limit ? rows.slice(0, limit) : rows;
}

/** คีย์หมวดปัญหาของ ticket — ชื่อฟิลด์ไม่ตรงกันตามช่องทางที่แจ้ง (เว็บ / LINE / AI) */
function pickIssueKey(t: any): string {
  const v = t?.issue_category ?? t?.issue_category_name ?? t?.category
    ?? t?.issue ?? t?.symptom ?? t?.problem_title ?? t?.device_type;
  const s = v == null ? '' : String(v).trim();
  return s || 'ไม่ระบุหมวด';
}

/** นับจำนวนแถวตามคีย์ที่ดึงออกมา แล้วเรียงมากไปน้อย */
function countBy<T>(
  rows: T[],
  keyOf: (row: T) => string,
  limit?: number,
): { k: string; label: string; v: number }[] {
  if (!Array.isArray(rows) || rows.length === 0) return [];
  const map = new Map<string, number>();
  for (const row of rows) {
    const k = keyOf(row);
    map.set(k, (map.get(k) ?? 0) + 1);
  }
  const out = [...map.entries()]
    .map(([k, v]) => ({ k, label: k, v }))
    .sort((a, b) => b.v - a.v);
  return limit ? out.slice(0, limit) : out;
}

/** แถบสัดส่วน — ประกาศเป็น progressbar เพื่อให้ screen reader อ่านค่าได้ */
function Bar({ label, value, total, max, color }: {
  label: string; value: number; total: number; max?: number; color: string;
}) {
  // pct = สัดส่วนจริงของค่านี้เทียบ total (ตัวเลขที่ผู้ใช้อ่าน ต้องรวมกันได้ ~100%)
  const pct = total > 0 ? Math.min(100, Math.round((value / total) * 1000) / 10) : 0;
  // ความกว้างของแถบเทียบกับค่าสูงสุดในชุด เพื่อให้เปรียบเทียบด้วยตาได้ชัดเมื่อมี
  // หลายหมวดและแต่ละหมวดมีสัดส่วนน้อย — ไม่ส่ง max มาก็ใช้ total เหมือนเดิม
  const barBase = max != null && max > 0 ? max : total;
  const barWidth = barBase > 0 ? Math.min(100, Math.round((value / barBase) * 1000) / 10) : 0;
  return (
    <div className="rp-bar">
      <div className="rp-bar-head">
        <span className="rp-bar-label" title={label}>{label}</span>
        <span className="rp-bar-value">
          {fmtNum(value)}
          {total > 0 && <span className="rp-bar-pct">{pct}%</span>}
        </span>
      </div>
      <div
        className="rp-bar-track"
        role="progressbar"
        aria-label={`${label}: ${value}`}
        aria-valuenow={value}
        aria-valuemin={0}
        aria-valuemax={total > 0 ? total : value || 1}
      >
        <span className="rp-bar-fill" style={{ width: `${barWidth}%`, background: color }} />
      </div>
    </div>
  );
}

function Card({ title, badge, flush, children }: {
  title: string; badge?: React.ReactNode; flush?: boolean; children: React.ReactNode;
}) {
  return (
    <section className="rp-card">
      <div className="rp-card-head">
        <span className="rp-card-title">{title}</span>
        {badge != null && <span className="rp-card-badge">{badge}</span>}
      </div>
      <div className={flush ? 'rp-card-body rp-card-body--flush' : 'rp-card-body'}>{children}</div>
    </section>
  );
}

function Empty({ text }: { text: string }) {
  return <div className="rp-empty">{text}</div>;
}

export default function ReportsPage({ onBack }: { onBack: () => void }) {
  const [tab, setTab] = useState<TabId>('overview');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [stats, setStats] = useState<any>(null);
  // Ticket ชุดเต็มสำหรับตาราง + Export CSV — stats.recent_tickets ถูก backend ล็อกไว้ LIMIT 10
  const [allTickets, setAllTickets] = useState<any[]>([]);
  const [topIssues, setTopIssues] = useState<any[]>([]);
  const [topDevices, setTopDevices] = useState<any[]>([]);
  const [analytics, setAnalytics] = useState<any>({
    by_issue_category: {}, by_device_type: {}, recent_self_service: [],
    ticket_metrics: {}, avg_resolution_hours: null,
  });
  const [avgRes, setAvgRes] = useState<any>(null);

  const [history, setHistory] = useState<any[]>([]);
  const [historyTicket, setHistoryTicket] = useState('');
  const [historyLoading, setHistoryLoading] = useState(false);
  const [selectedTicket, setSelectedTicket] = useState<any>(null);

  const [deviceQuery, setDeviceQuery] = useState('');
  const [ticketsByDevice, setTicketsByDevice] = useState<any[]>([]);
  const [deviceSearched, setDeviceSearched] = useState(false);
  const [deviceTicketsLoading, setDeviceTicketsLoading] = useState(false);

  const [selfServiceList, setSelfServiceList] = useState<any[]>([]);
  const [selfServiceLoading, setSelfServiceLoading] = useState(false);
  const [selfServiceLoaded, setSelfServiceLoaded] = useState(false);

  const loadAll = useCallback(() => {
    setLoading(true);
    setError(null);
    Promise.all([
      api.getStats().catch(() => null),
      // reportTopIssues/TopDevices รับ organization_id ไม่ใช่จำนวนแถว — เดิมส่ง 5 เข้าไป
      // ทำให้กรองเป็นองค์กร id 5 โดยไม่ตั้งใจ จึงตัดอาร์กิวเมนต์ออกและ slice ฝั่งนี้
      api.reportTopIssues().catch(() => []),
      api.reportTopDevices().catch(() => []),
      api.getChatbotAnalytics().catch(() => null),
      api.getAvgResolution().catch(() => null),
      // ดึงครบทุกหน้า โดย backend จำกัดครั้งละไม่เกิน 200 รายการ
      api.listAllTickets().catch(() => []),
    ])
      .then(([statsRes, issuesRes, devicesRes, analyticsRes, avgResRes, ticketsRes]) => {
        setStats(statsRes);
        setAllTickets(
          Array.isArray(ticketsRes)
            ? ticketsRes
            : Array.isArray((ticketsRes as any)?.items)
              ? (ticketsRes as any).items
              : [],
        );
        setTopIssues(Array.isArray(issuesRes) ? issuesRes.slice(0, 8) : []);
        setTopDevices(Array.isArray(devicesRes) ? devicesRes.slice(0, 8) : []);
        setAnalytics(analyticsRes || {
          by_issue_category: {}, by_device_type: {}, recent_self_service: [],
          ticket_metrics: {}, avg_resolution_hours: null,
        });
        setAvgRes(avgResRes);
      })
      .catch((e: any) => setError(e?.message || 'โหลดข้อมูลรายงานไม่สำเร็จ'))
      .finally(() => setLoading(false));
  }, []);

  const loadSelfService = useCallback(() => {
    setSelfServiceLoading(true);
    api.listSelfService({ limit: 100 })
      .then((data: any) => setSelfServiceList(Array.isArray(data) ? data : []))
      .catch(() => setSelfServiceList([]))
      .finally(() => { setSelfServiceLoading(false); setSelfServiceLoaded(true); });
  }, []);

  useEffect(() => { loadAll(); }, [loadAll]);

  // เข้าแท็บ Self-Service ครั้งแรก = โหลดให้เลย ผู้ใช้ไม่ต้องกดปุ่มก่อนจะเห็นอะไร
  useEffect(() => {
    if (tab === 'selfservice' && !selfServiceLoaded && !selfServiceLoading) loadSelfService();
  }, [tab, selfServiceLoaded, selfServiceLoading, loadSelfService]);

  const fetchHistory = useCallback((ticketId?: string) => {
    const id = (ticketId || historyTicket).trim();
    if (!id) return;
    setHistoryLoading(true);
    api.getTicketHistory(id)
      .then((data: any) => setHistory(Array.isArray(data) ? data : []))
      .catch(() => setHistory([]))
      .finally(() => setHistoryLoading(false));
  }, [historyTicket]);

  const fetchTicketsByDevice = useCallback((deviceId: string) => {
    const id = deviceId.trim();
    if (!id) return;
    setDeviceTicketsLoading(true);
    api.listAllTickets({ device_id: id })
      .then((res: any) => setTicketsByDevice(res?.items || (Array.isArray(res) ? res : [])))
      .catch(() => setTicketsByDevice([]))
      .finally(() => { setDeviceTicketsLoading(false); setDeviceSearched(true); });
  }, []);

  const openTicket = useCallback((id: string) => {
    setTab('tickets');
    setHistoryTicket(id);
    api.getTicket(id)
      .then((t: any) => { setSelectedTicket(t); fetchHistory(id); })
      .catch(() => setSelectedTicket(null));
  }, [fetchHistory]);

  const exportCSV = () => {
    // ใช้ชุดเดียวกับตารางด้านล่าง (allTickets) ไม่ใช่ recent_tickets ที่จำกัด 10 แถว
    const rowsSrc: any[] = allTickets.length > 0 ? allTickets : (stats?.recent_tickets || []);
    if (!rowsSrc.length) { alert('ไม่มีข้อมูล ticket ให้ export'); return; }
    const header = 'ticket_id,title,status,priority,created_at,device_id,device_type,school,device_label';
    const esc = (v: unknown) => `"${String(v ?? '').replace(/"/g, '""')}"`;
    const rows = rowsSrc.map((t) => [
      t.ticket_id, esc(t.title), t.status, t.priority, t.created_at,
      esc(t.device_id || ''), esc(t.device_type || ''),
      esc(t.organization_name || ''), esc(t.device_label || t.room_name || ''),
    ].join(','));
    const blob = new Blob(['\uFEFF' + [header, ...rows].join('\n')], { type: 'text/csv;charset=utf-8' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `reports-tickets-${new Date().toISOString().slice(0, 10)}.csv`;
    a.click();
    URL.revokeObjectURL(url);
  };

  // ── ข้อมูลที่คำนวณแล้ว ────────────────────────────────────────────────
  const totalTickets: number = stats?.total_tickets ?? 0;
  const totalDevices: number = stats?.total_devices ?? 0;
  // เดิม: stats.recent_tickets (backend ORDER BY created_at DESC LIMIT 10) ทำให้หน้ารายงาน
  // และ Export CSV เห็นได้แค่ 10 ใบเสมอ ตอนนี้ใช้ /api/tickets แล้ว fallback เป็นค่าเดิม
  const recentTickets: any[] = allTickets.length > 0 ? allTickets : (stats?.recent_tickets || []);
  const ticketMetrics = analytics?.ticket_metrics || {};
  const recentSelfService: any[] = Array.isArray(analytics?.recent_self_service) ? analytics.recent_self_service : [];

  const openCount = ['new', 'assigned', 'in_progress', 'pending', 'waiting_parts', 'waiting_user']
    .reduce((sum, k) => sum + (stats?.[k] ?? 0), 0);
  const closedCount = (stats?.resolved ?? 0) + (stats?.closed ?? 0);
  const resolutionRate = totalTickets > 0 ? Math.round((closedCount / totalTickets) * 100) : 0;
  const selfServiceTotal: number = stats?.self_service_total ?? 0;
  const avgResolutionHours: number | null = (() => {
    const raw = analytics?.avg_resolution_hours ?? avgRes?.avg_hours ?? ticketMetrics?.avg_resolution_hours;
    const n = Number(raw);
    return raw != null && Number.isFinite(n) ? n : null;
  })();

  const statusRows = useMemo(
    () => toRows(stats?.by_status).map((r) => ({ ...r, label: STATUS_LABELS[r.k] || r.k })),
    [stats],
  );
  const priorityRows = useMemo(
    () => toRows(stats?.by_priority).map((r) => ({ ...r, label: PRIORITY_LABELS[r.k] || r.k })),
    [stats],
  );
  const typeRows = useMemo(() => toRows(stats?.by_type, 10), [stats]);
  const deviceStatusRows = useMemo(() => toRows(stats?.devices_by_status), [stats]);
  /* /api/reports/chatbot-analytics คืนแค่ total_conversations / self_service_rate /
     intent_distribution / missed_queries — ไม่มี by_issue_category และ by_device_type
     การอ่านสองคีย์นั้นทำให้การ์ดในแท็บ "อุปกรณ์และปัญหา" ขึ้น "ยังไม่มีข้อมูล" ตลอด
     จึงคำนวณจากแหล่งที่มีจริง และยังเผื่อคีย์จาก analytics ไว้ก่อน เพื่อให้ใช้ได้เอง
     ถ้าวันหลัง backend เพิ่มสองคีย์นี้เข้ามา */
  const issueRows = useMemo(() => {
    const fromApi = toRows(analytics?.by_issue_category, 10);
    return fromApi.length > 0 ? fromApi : countBy(allTickets, pickIssueKey, 10);
  }, [analytics, allTickets]);

  const deviceIssueRows = useMemo(() => {
    const fromApi = toRows(analytics?.by_device_type, 10);
    if (fromApi.length > 0) return fromApi;
    // /reports/top-issues group by device_type อยู่แล้ว — ตรงกับความหมายของการ์ดนี้
    if (topIssues.length > 0) {
      return topIssues
        .map((r) => ({
          k: String(r?.device_type ?? pickLabel(r)),
          label: pickLabel(r),
          v: pickValue(r),
        }))
        .filter((r) => r.v > 0)
        .sort((a, b) => b.v - a.v)
        .slice(0, 10);
    }
    return toRows(stats?.by_type, 10);
  }, [analytics, topIssues, stats]);

  /* % ต้องหารด้วยผลรวมของชุดเดียวกัน ไม่ใช่ total_tickets (คนละชุด ทำให้รวมไม่ถึง 100)
     และความกว้างแถบใช้ค่าสูงสุดของชุด เพื่อให้เทียบกันด้วยตาได้ */
  const issueTotal = useMemo(() => issueRows.reduce((s, r) => s + r.v, 0), [issueRows]);
  const issueMax = issueRows.length > 0 ? issueRows[0].v : 0;
  const deviceIssueTotal = useMemo(
    () => deviceIssueRows.reduce((s, r) => s + r.v, 0),
    [deviceIssueRows],
  );
  const deviceIssueMax = deviceIssueRows.length > 0 ? deviceIssueRows[0].v : 0;

  const timeSavedTotal = useMemo(
    () => selfServiceList.reduce((s, r) => s + (Number(r?.time_saved_minutes) || 0), 0),
    [selfServiceList],
  );
  const selfResolvedCount = useMemo(
    () => selfServiceList.filter((r) => r?.resolved).length,
    [selfServiceList],
  );

  // icon เป็นตัวย่อข้อความ (ไม่ใช้อิโมจิ) — แสดงผลเหมือนกันทุก OS และ screen reader
  // ข้ามได้ด้วย aria-hidden ตรงจุดเรนเดอร์
  const kpis: { icon: string; value: string; label: string; sub: string; tint: string }[] = [
    { icon: 'TKT', value: fmtNum(totalTickets), label: 'Ticket ทั้งหมด', sub: 'ทุกสถานะ', tint: 'var(--chart-1, #7C3AED)' },
    { icon: 'OPEN', value: fmtNum(openCount), label: 'งานที่ยังไม่เสร็จ', sub: 'รอรับ/กำลังทำ/รออะไหล่', tint: 'var(--status-assigned, #F59E0B)' },
    { icon: 'DONE', value: `${resolutionRate}%`, label: `อัตราปิดงาน (${fmtNum(closedCount)})`, sub: 'resolved + closed', tint: 'var(--status-resolved, #10B981)' },
    { icon: 'AVG', value: avgResolutionHours != null ? `${avgResolutionHours.toFixed(1)} ชม.` : '—', label: 'เวลาเฉลี่ยที่ใช้แก้', sub: 'จากงานที่ปิดแล้ว', tint: 'var(--status-in-progress, #2563EB)' },
    { icon: 'DEV', value: fmtNum(totalDevices), label: 'อุปกรณ์ที่ลงทะเบียน', sub: 'ทุกโรงเรียน', tint: 'var(--color-muted, #6B7280)' },
    { icon: 'AI', value: fmtNum(selfServiceTotal), label: 'ผู้ใช้แก้ได้เอง (AI)', sub: 'ไม่ต้องเปิด ticket', tint: 'var(--chart-3, #10B981)' },
  ];

  const tabCounts: Record<TabId, number | undefined> = {
    overview: undefined,
    tickets: recentTickets.length || undefined,
    devices: typeRows.length || undefined,
    selfservice: (selfServiceList.length || selfServiceTotal) || undefined,
  };

  /** ลูกศรซ้าย/ขวาเลื่อนแท็บ ตามพฤติกรรมมาตรฐานของ tablist */
  const onTabKeyDown = (e: React.KeyboardEvent<HTMLDivElement>) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const i = TABS.findIndex((t) => t.id === tab);
    const next = e.key === 'ArrowRight' ? (i + 1) % TABS.length : (i - 1 + TABS.length) % TABS.length;
    setTab(TABS[next].id);
    const el = document.getElementById(`rp-tab-${TABS[next].id}`);
    el?.focus();
  };

  const StatusBadge = ({ status }: { status?: string }) => (
    <span className={`badge badge-${status || 'new'}`}>{STATUS_LABELS[status || ''] || status || '—'}</span>
  );

  return (
    <div className="page-content">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack} aria-label="ย้อนกลับ">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
          </button>
          <div>
            <h1 className="top-bar-title">รายงาน</h1>
            <span className="top-bar-subtitle">สรุปภาพรวมและวิเคราะห์ข้อมูลงานซ่อม</span>
          </div>
        </div>
        <div className="top-bar-actions">
          <button className="btn btn-secondary" onClick={exportCSV}>Export CSV</button>
          <button className="btn btn-ghost btn-icon" onClick={loadAll} aria-label="โหลดข้อมูลใหม่" title="โหลดข้อมูลใหม่">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M21 12a9 9 0 11-3.5-7.1" />
              <path d="M21 3v6h-6" />
            </svg>
          </button>
        </div>
      </div>

      <div className="rp-page">
        {error && <div className="rp-alert" role="alert">{error}</div>}

        {loading ? (
          <div className="loading-state" style={{ minHeight: 220, padding: 40 }}>
            <div className="spinner" />
            <span>กำลังโหลดข้อมูลรายงาน...</span>
          </div>
        ) : (
          <>
            <div className="rp-hero">
              <div>
                <div className="rp-hero-title">ภาพรวมงานซ่อมบำรุง</div>
                <p className="rp-hero-sub">
                  Ticket ทั้งหมด <b>{fmtNum(totalTickets)}</b> รายการ · ยังไม่เสร็จ <b>{fmtNum(openCount)}</b> ·
                  ปิดแล้ว <b>{fmtNum(closedCount)}</b> ({resolutionRate}%)
                  {avgResolutionHours != null && <> · ใช้เวลาเฉลี่ย <b>{avgResolutionHours.toFixed(1)}</b> ชั่วโมงต่องาน</>}
                </p>
              </div>
              <div className="rp-hero-chips">
                <span className="rp-chip">อุปกรณ์ {fmtNum(totalDevices)}</span>
                <span className="rp-chip">แก้เองได้ {fmtNum(selfServiceTotal)}</span>
              </div>
            </div>

            <div className="rp-kpi-grid">
              {kpis.map((k) => (
                <div key={k.label} className="rp-kpi">
                  <div className="rp-kpi-top">
                    <span className="rp-kpi-icon" style={{ background: `color-mix(in srgb, ${k.tint} 14%, transparent)` }} aria-hidden="true">
                      {k.icon}
                    </span>
                    <span className="rp-kpi-sub">{k.sub}</span>
                  </div>
                  <div>
                    <div className="rp-kpi-value">{k.value}</div>
                    <div className="rp-kpi-label">{k.label}</div>
                  </div>
                </div>
              ))}
            </div>

            <div className="rp-tabs" role="tablist" aria-label="กลุ่มรายงาน" onKeyDown={onTabKeyDown}>
              {TABS.map((t) => (
                <button
                  key={t.id}
                  id={`rp-tab-${t.id}`}
                  className="rp-tab"
                  role="tab"
                  type="button"
                  aria-selected={tab === t.id}
                  aria-controls={`rp-panel-${t.id}`}
                  tabIndex={tab === t.id ? 0 : -1}
                  onClick={() => setTab(t.id)}
                >
                  {t.label}
                  {tabCounts[t.id] != null && <span className="rp-tab-count">{fmtNum(tabCounts[t.id] as number)}</span>}
                </button>
              ))}
            </div>

            {/* ── แท็บ: ภาพรวม ───────────────────────────────────────── */}
            {tab === 'overview' && (
              <div id="rp-panel-overview" role="tabpanel" aria-labelledby="rp-tab-overview" className="rp-page">
                <div className="rp-grid">
                  <Card title="Ticket ตามสถานะ" badge={`${fmtNum(totalTickets)} รายการ`}>
                    {statusRows.length === 0 ? <Empty text="ไม่มีข้อมูล" /> :
                      statusRows.map((r) => (
                        <Bar key={r.k} label={r.label} value={r.v} total={totalTickets} color={STATUS_COLORS[r.k] || ACCENT_BAR} />
                      ))}
                  </Card>
                  <Card title="Ticket ตามความเร่งด่วน" badge={`${fmtNum(totalTickets)} รายการ`}>
                    {priorityRows.length === 0 ? <Empty text="ไม่มีข้อมูล" /> :
                      priorityRows.map((r) => (
                        <Bar key={r.k} label={r.label} value={r.v} total={totalTickets} color={PRIORITY_COLORS[r.k] || ACCENT_BAR} />
                      ))}
                  </Card>
                </div>

                <div className="rp-grid">
                  <Card title="อุปกรณ์ตามประเภท (Top 10)" badge={`${fmtNum(totalDevices)} เครื่อง`}>
                    {typeRows.length === 0 ? <Empty text="ไม่มีข้อมูล" /> :
                      typeRows.map((r) => (
                        <Bar key={r.k} label={r.label} value={r.v} total={totalDevices} color="var(--chart-2, #2563EB)" />
                      ))}
                  </Card>
                  <Card title="สถานะอุปกรณ์" badge={`${fmtNum(deviceStatusRows.length)} สถานะ`}>
                    {deviceStatusRows.length === 0 ? <Empty text="ไม่มีข้อมูล" /> :
                      deviceStatusRows.map((r) => (
                        <Bar key={r.k} label={r.label} value={r.v} total={totalDevices} color={STATUS_COLORS[r.k] || 'var(--chart-4, #0EA5E9)'} />
                      ))}
                  </Card>
                </div>

                <div className="rp-grid">
                  <Card title="ปัญหาที่พบบ่อยที่สุด" badge={`Top ${fmtNum(topIssues.length)}`}>
                    {topIssues.length === 0 ? <Empty text="ยังไม่มีข้อมูลจาก /reports/top-issues" /> :
                      topIssues.map((row, i) => (
                        <Bar
                          key={`${pickLabel(row)}-${i}`}
                          label={pickLabel(row)}
                          value={pickValue(row)}
                          total={pickValue(topIssues[0])}
                          color="var(--chart-8, #8B5CF6)"
                        />
                      ))}
                  </Card>
                  <Card title="อุปกรณ์ที่ถูกแจ้งซ่อมบ่อย" badge={`Top ${fmtNum(topDevices.length)}`}>
                    {topDevices.length === 0 ? <Empty text="ยังไม่มีข้อมูลจาก /reports/top-devices" /> :
                      topDevices.map((row, i) => (
                        <Bar
                          key={`${pickDeviceLabel(row)}-${i}`}
                          label={pickDeviceLabel(row)}
                          value={pickValue(row)}
                          total={pickValue(topDevices[0])}
                          color="var(--chart-5, #F59E0B)"
                        />
                      ))}
                  </Card>
                </div>
              </div>
            )}

            {/* ── แท็บ: Ticket & ประวัติ ─────────────────────────────── */}
            {tab === 'tickets' && (
              <div id="rp-panel-tickets" role="tabpanel" aria-labelledby="rp-tab-tickets" className="rp-page">
                <Card
                  title="รายการ Ticket"
                  badge={
                    recentTickets.length >= 200
                      ? `${fmtNum(recentTickets.length)} รายการ (ล่าสุด)`
                      : `${fmtNum(recentTickets.length)} รายการ`
                  }
                  flush
                >
                  {recentTickets.length === 0 ? <Empty text="ยังไม่มี ticket" /> : (
                    <div className="rp-table-wrap">
                      <table className="rp-table">
                        <caption className="rp-sr-only">รายการ ticket ล่าสุด คลิกรหัสเพื่อดูรายละเอียดและประวัติ</caption>
                        <thead>
                          <tr>
                            <th scope="col">Ticket</th>
                            <th scope="col">หัวข้อ</th>
                            <th scope="col">สถานะ</th>
                            <th scope="col">ความเร่งด่วน</th>
                            <th scope="col">อุปกรณ์</th>
                            <th scope="col">ห้อง / โรงเรียน</th>
                            <th scope="col">สร้างเมื่อ</th>
                          </tr>
                        </thead>
                        <tbody>
                          {recentTickets.map((t) => (
                            <tr key={t.ticket_id}>
                              <td className="rp-td-id">
                                <button className="rp-linkbtn" type="button" onClick={() => openTicket(t.ticket_id)}>
                                  {t.ticket_id}
                                </button>
                              </td>
                              <td className="rp-td-wrap">{t.title || '—'}</td>
                              <td><StatusBadge status={t.status} /></td>
                              <td><span className={`badge badge-priority-${t.priority}`}>{t.priority || '—'}</span></td>
                              <td>{t.device_type || t.device_id || '—'}</td>
                              <td className="rp-td-wrap">
                                {t.room_name || t.device_label || t.organization_name || '—'}
                              </td>
                              <td className="rp-td-muted">{fmtDate(t.created_at)}</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Card>

                {selectedTicket && (
                  <Card
                    title={`รายละเอียด: ${selectedTicket.ticket_id}`}
                    badge={<button className="rp-linkbtn" type="button" onClick={() => setSelectedTicket(null)}>ปิด</button>}
                  >
                    <div className="rp-detail">
                      <div className="rp-detail-item">
                        <span className="rp-detail-key">หัวข้อ</span>
                        <span className="rp-detail-val">{selectedTicket.title || '—'}</span>
                      </div>
                      <div className="rp-detail-item">
                        <span className="rp-detail-key">สถานะ</span>
                        <span className="rp-detail-val"><StatusBadge status={selectedTicket.status} /></span>
                      </div>
                      <div className="rp-detail-item">
                        <span className="rp-detail-key">อุปกรณ์ / ห้อง</span>
                        <span className="rp-detail-val">{selectedTicket.device_id || '—'} · {selectedTicket.room_name || '—'}</span>
                      </div>
                      <div className="rp-detail-item">
                        <span className="rp-detail-key">ผู้แจ้ง</span>
                        <span className="rp-detail-val">{selectedTicket.reporter_name || '—'} · {selectedTicket.reporter_phone || '—'}</span>
                      </div>
                      <div className="rp-detail-item">
                        <span className="rp-detail-key">อาการ</span>
                        <span className="rp-detail-val">{selectedTicket.symptom || selectedTicket.description || '—'}</span>
                      </div>
                      <div className="rp-detail-item">
                        <span className="rp-detail-key">สร้างเมื่อ</span>
                        <span className="rp-detail-val">{fmtDate(selectedTicket.created_at)}</span>
                      </div>
                    </div>
                  </Card>
                )}

                <Card title="ประวัติการอัปเดต Ticket" badge={history.length ? `${fmtNum(history.length)} รายการ` : undefined}>
                  <form
                    className="rp-toolbar"
                    onSubmit={(e) => { e.preventDefault(); fetchHistory(); }}
                  >
                    <label className="rp-sr-only" htmlFor="rp-history-input">Ticket ID</label>
                    <input
                      id="rp-history-input"
                      className="rp-input"
                      placeholder="กรอก Ticket ID เช่น TK.ALL.26.000001-K"
                      value={historyTicket}
                      onChange={(e) => setHistoryTicket(e.target.value)}
                    />
                    <button className="btn btn-primary" type="submit" disabled={!historyTicket.trim() || historyLoading}>
                      {historyLoading ? 'กำลังโหลด...' : 'ดึงประวัติ'}
                    </button>
                  </form>
                  {historyLoading ? <Empty text="กำลังโหลด..." />
                    : history.length === 0 ? <Empty text="ยังไม่มีประวัติ — คลิกรหัส ticket ด้านบน หรือกรอก ID แล้วกดดึงประวัติ" />
                    : (
                      <div className="rp-table-wrap">
                        <table className="rp-table">
                          <thead>
                            <tr>
                              <th scope="col">#</th>
                              <th scope="col">จากสถานะ</th>
                              <th scope="col">ไปสถานะ</th>
                              <th scope="col">ผู้ดำเนินการ</th>
                              <th scope="col">หมายเหตุ</th>
                              <th scope="col">เวลา</th>
                            </tr>
                          </thead>
                          <tbody>
                            {history.map((h, i) => (
                              <tr key={h.id ?? `${h.to_status}-${i}`}>
                                <td>{i + 1}</td>
                                <td>{STATUS_LABELS[h.from_status] || h.from_status || '—'}</td>
                                <td><StatusBadge status={h.to_status} /></td>
                                <td>{h.author_name || h.changed_by || '—'}</td>
                                <td className="rp-td-wrap">{h.note || '—'}</td>
                                <td className="rp-td-muted">{fmtDate(h.created_at)}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                </Card>
              </div>
            )}

            {/* ── แท็บ: อุปกรณ์ & ปัญหา ──────────────────────────────── */}
            {tab === 'devices' && (
              <div id="rp-panel-devices" role="tabpanel" aria-labelledby="rp-tab-devices" className="rp-page">
                <Card title="ค้นหา Ticket ตามอุปกรณ์" badge={ticketsByDevice.length ? `${fmtNum(ticketsByDevice.length)} รายการ` : undefined} >
                  <form
                    className="rp-toolbar"
                    onSubmit={(e) => { e.preventDefault(); fetchTicketsByDevice(deviceQuery); }}
                  >
                    <label className="rp-sr-only" htmlFor="rp-device-input">Device ID</label>
                    <input
                      id="rp-device-input"
                      className="rp-input"
                      placeholder="กรอก Device ID เช่น DIS-01"
                      value={deviceQuery}
                      onChange={(e) => setDeviceQuery(e.target.value)}
                    />
                    <button className="btn btn-primary" type="submit" disabled={!deviceQuery.trim() || deviceTicketsLoading}>
                      {deviceTicketsLoading ? 'กำลังค้นหา...' : 'ค้นหา'}
                    </button>
                  </form>
                  {deviceTicketsLoading ? <Empty text="กำลังโหลด..." />
                    : ticketsByDevice.length === 0
                      ? <Empty text={deviceSearched ? 'ไม่พบ ticket ของอุปกรณ์นี้' : 'กรอกรหัสอุปกรณ์เพื่อดูประวัติงานซ่อมของเครื่องนั้น'} />
                      : (
                        <div className="rp-table-wrap">
                          <table className="rp-table">
                            <thead>
                              <tr>
                                <th scope="col">Ticket</th>
                                <th scope="col">หัวข้อ</th>
                                <th scope="col">สถานะ</th>
                                <th scope="col">อุปกรณ์</th>
                                <th scope="col">ห้อง</th>
                                <th scope="col">ความเร่งด่วน</th>
                                <th scope="col">สร้างเมื่อ</th>
                              </tr>
                            </thead>
                            <tbody>
                              {ticketsByDevice.map((t) => (
                                <tr key={t.ticket_id}>
                                  <td className="rp-td-id">
                                    <button className="rp-linkbtn" type="button" onClick={() => openTicket(t.ticket_id)}>
                                      {t.ticket_id}
                                    </button>
                                  </td>
                                  <td className="rp-td-wrap">{t.title || '—'}</td>
                                  <td><StatusBadge status={t.status} /></td>
                                  <td>{t.device_id || '—'}</td>
                                  <td>{t.room_name || '—'}</td>
                                  <td><span className={`badge badge-priority-${t.priority}`}>{t.priority || '—'}</span></td>
                                  <td className="rp-td-muted">{fmtDate(t.created_at)}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      )}
                </Card>

                <div className="rp-grid">
                  <Card title="ปัญหาตามหมวด (Top 10)" badge={`${fmtNum(issueRows.length)} หมวด`}>
                    {issueRows.length === 0 ? <Empty text="ยังไม่มีข้อมูล" /> :
                      issueRows.map((r) => (
                        <Bar key={r.k} label={r.label} value={r.v} total={issueTotal} max={issueMax} color="var(--chart-8, #8B5CF6)" />
                      ))}
                  </Card>
                  <Card title="ปัญหาแยกตามประเภทอุปกรณ์ (Top 10)" badge={`${fmtNum(deviceIssueRows.length)} ประเภท`}>
                    {deviceIssueRows.length === 0 ? <Empty text="ยังไม่มีข้อมูล" /> :
                      deviceIssueRows.map((r) => (
                        <Bar key={r.k} label={r.label} value={r.v} total={deviceIssueTotal} max={deviceIssueMax} color="var(--chart-3, #10B981)" />
                      ))}
                  </Card>
                </div>

                <Card title="ตารางปัญหา (Issue × สัดส่วน)" flush>
                  {issueRows.length === 0 ? <Empty text="ยังไม่มีข้อมูล" /> : (
                    <div className="rp-table-wrap">
                      <table className="rp-table">
                        <thead>
                          <tr>
                            <th scope="col">ประเภทปัญหา</th>
                            <th scope="col">จำนวน</th>
                            <th scope="col">คิดเป็น %</th>
                          </tr>
                        </thead>
                        <tbody>
                          {issueRows.map((r) => (
                            <tr key={r.k}>
                              <td className="rp-td-wrap">{r.label}</td>
                              <td>{fmtNum(r.v)}</td>
                              <td>{issueTotal > 0 ? Math.round((r.v / issueTotal) * 1000) / 10 : 0}%</td>
                            </tr>
                          ))}
                        </tbody>
                      </table>
                    </div>
                  )}
                </Card>
              </div>
            )}

            {/* ── แท็บ: Self-Service ─────────────────────────────────── */}
            {tab === 'selfservice' && (
              <div id="rp-panel-selfservice" role="tabpanel" aria-labelledby="rp-tab-selfservice" className="rp-page">
                <div className="rp-kpi-grid">
                  <div className="rp-kpi">
                    <div className="rp-kpi-top">
                      <span className="rp-kpi-icon" aria-hidden="true">AI</span>
                      <span className="rp-kpi-sub">ทั้งระบบ</span>
                    </div>
                    <div>
                      <div className="rp-kpi-value">{fmtNum(selfServiceTotal || selfServiceList.length)}</div>
                      <div className="rp-kpi-label">ครั้งที่ AI ช่วยแก้</div>
                    </div>
                  </div>
                  <div className="rp-kpi">
                    <div className="rp-kpi-top">
                      <span className="rp-kpi-icon" aria-hidden="true">OK</span>
                      <span className="rp-kpi-sub">จากรายการที่โหลด</span>
                    </div>
                    <div>
                      <div className="rp-kpi-value">{fmtNum(selfResolvedCount)}</div>
                      <div className="rp-kpi-label">แก้ได้เองสำเร็จ</div>
                    </div>
                  </div>
                  <div className="rp-kpi">
                    <div className="rp-kpi-top">
                      <span className="rp-kpi-icon" aria-hidden="true">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
                          <circle cx="12" cy="12" r="9" />
                          <path d="M12 7v5l3 2" />
                        </svg>
                      </span>
                      <span className="rp-kpi-sub">ประมาณการ</span>
                    </div>
                    <div>
                      <div className="rp-kpi-value">{timeSavedTotal > 0 ? `${fmtNum(timeSavedTotal)} นาที` : '—'}</div>
                      <div className="rp-kpi-label">เวลาช่างที่ประหยัดได้</div>
                    </div>
                  </div>
                </div>

                {recentSelfService.length > 0 && (
                  <Card title="Self-Service ล่าสุด (จาก chatbot analytics)">
                    <ul className="rp-list">
                      {recentSelfService.map((s: any, i: number) => (
                        <li key={s.ticket_id || s.id || i}>
                          <b>{s.ticket_id || '—'}</b> · {s.title || s.symptom || '—'}
                          <span className="rp-bar-pct">{fmtDate(s.created_at)}</span>
                        </li>
                      ))}
                    </ul>
                  </Card>
                )}

                <Card
                  title={`ประวัติ Self-Service (${fmtNum(selfServiceList.length)})`}
                  badge={(
                    <button className="rp-linkbtn" type="button" onClick={loadSelfService}>
                      <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" style={{ marginRight: 5, verticalAlign: '-2px' }}>
                        <path d="M21 12a9 9 0 11-3.5-7.1" />
                        <path d="M21 3v6h-6" />
                      </svg>
                      โหลดใหม่
                    </button>
                  )}
                  flush
                >
                  {selfServiceLoading ? <Empty text="กำลังโหลด..." />
                    : selfServiceList.length === 0 ? <Empty text="ยังไม่มีข้อมูล self-service" />
                    : (
                      <div className="rp-table-wrap">
                        <table className="rp-table">
                          <thead>
                            <tr>
                              <th scope="col">วันที่</th>
                              <th scope="col">อุปกรณ์</th>
                              <th scope="col">ประเภท</th>
                              <th scope="col">ห้อง</th>
                              <th scope="col">อาการ/ปัญหา</th>
                              <th scope="col">ช่วยได้ไหม</th>
                              <th scope="col">เวลาที่ประหยัด</th>
                            </tr>
                          </thead>
                          <tbody>
                            {selfServiceList.map((s: any, i: number) => (
                              <tr key={s.id ?? i}>
                                <td className="rp-td-muted">{fmtDate(s.created_at)}</td>
                                <td className="rp-td-id">{s.device_id || '—'}</td>
                                <td>{s.device_type || '—'}</td>
                                <td>{s.room_name || '—'}</td>
                                <td className="rp-td-wrap">{s.symptom || '—'}</td>
                                <td>
                                  <span className={`badge ${s.resolved ? 'badge-resolved' : 'badge-cancelled'}`}>
                                    {s.resolved ? 'แก้ได้เอง' : 'ส่งต่อช่าง'}
                                  </span>
                                </td>
                                <td>{s.time_saved_minutes != null ? `~${fmtNum(s.time_saved_minutes)} นาที` : '—'}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    )}
                </Card>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
