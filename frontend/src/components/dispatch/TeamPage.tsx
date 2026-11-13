import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { DispatchSummary } from '../../types';
import { ticketDetailPriority } from '../tickets/ticketLabels';
import '../../styles/dispatch.css';

const REFRESH_MS = 30_000;

const STATE_LABEL: Record<string, string> = { free: 'ว่าง', busy: 'มีงาน', off: 'ปิดรับงาน' };

function ago(value: string) {
  const mins = Math.max(0, Math.round((Date.now() - new Date(value).getTime()) / 60000));
  if (mins < 60) return `${mins} นาทีที่แล้ว`;
  const hours = Math.round(mins / 60);
  return hours < 24 ? `${hours} ชม.ที่แล้ว` : `${Math.round(hours / 24)} วันที่แล้ว`;
}

export interface TeamPageProps {
  onBack: () => void;
  onOpenTicket: (ticketId: string) => void;
}

/** หน้าสรุปทีมช่างของแอดมิน: ใครว่าง/มีงาน, งานที่ยังไม่มีคนรับ, มอบหมายด้วยมือได้ในคลิกเดียว */
export default function TeamPage({ onBack, onOpenTicket }: TeamPageProps) {
  const [data, setData] = useState<DispatchSummary | null>(null);
  const [error, setError] = useState('');
  const [busyId, setBusyId] = useState<string | number | null>(null);
  const [pick, setPick] = useState<Record<string, string>>({});

  const load = useCallback(() => {
    api.dispatchSummary()
      .then((d) => { setData(d); setError(''); })
      .catch((e: any) => setError(e?.message || 'โหลดข้อมูลทีมไม่สำเร็จ'));
  }, []);

  useEffect(() => {
    load();
    const id = window.setInterval(() => { if (document.visibilityState === 'visible') load(); }, REFRESH_MS);
    return () => window.clearInterval(id);
  }, [load]);

  const toggleDuty = async (id: number, on: boolean) => {
    setBusyId(id);
    try { await api.setStaffDuty(id, on); load(); }
    catch (e: any) { setError(e?.message || 'เปลี่ยนสถานะไม่สำเร็จ'); }
    finally { setBusyId(null); }
  };

  const assign = async (ticketId: string) => {
    const userId = Number(pick[ticketId]);
    if (!userId) return;
    setBusyId(ticketId);
    try { await api.assignTicket(ticketId, { assignee_user_id: userId }); load(); }
    catch (e: any) { setError(e?.message || 'มอบหมายไม่สำเร็จ'); }
    finally { setBusyId(null); }
  };

  const staff = data?.staff ?? [];
  const sorted = [...staff].sort((a, b) =>
    ['free', 'busy', 'off'].indexOf(a.state) - ['free', 'busy', 'off'].indexOf(b.state) || a.open - b.open);
  const onDuty = staff.filter((s) => s.on_duty);

  return (
    <div className="page-content dp-team">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack} aria-label="กลับแดชบอร์ด">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
          </button>
          <div>
            <h1 className="top-bar-title">ทีมช่าง</h1>
            <span className="top-bar-subtitle">
              {data ? `พร้อมรับงาน ${onDuty.length} จาก ${staff.length} คน · อัปเดตทุก 30 วินาที` : 'กำลังโหลด…'}
            </span>
          </div>
        </div>
        <div className="top-bar-actions">
          <button className="btn btn-ghost" onClick={load}>รีเฟรช</button>
        </div>
      </div>

      {error && <div role="alert" className="alert alert-error dp-alert">{error}</div>}
      {data && !data.auto_assign && (
        <div className="alert alert-warning dp-alert">ระบบส่งงานอัตโนมัติปิดอยู่ (AUTO_ASSIGN_ENABLED=0) — งานใหม่ต้องมอบหมายเอง</div>
      )}
      {data && !data.line_push_configured && (
        <div className="alert alert-warning dp-alert">ยังไม่ได้ตั้งค่า LINE_CHANNEL_TOKEN — ระบบเสนองานได้ แต่ส่ง LINE ส่วนตัวไม่ได้</div>
      )}

      <div className="dp-kpis">
        <div className={`dp-kpi${data && data.tickets.unclaimed > 0 ? ' is-alert' : ''}`}>
          <span className="dp-kpi-num">{data?.tickets.unclaimed ?? '–'}</span>
          <span className="dp-kpi-label">ยังไม่มีคนรับ</span>
        </div>
        <div className="dp-kpi">
          <span className="dp-kpi-num">{data?.tickets.offering ?? '–'}</span>
          <span className="dp-kpi-label">รอช่างกดรับ</span>
        </div>
        <div className="dp-kpi">
          <span className="dp-kpi-num">{data?.tickets.in_progress ?? '–'}</span>
          <span className="dp-kpi-label">กำลังดำเนินการ</span>
        </div>
        <div className="dp-kpi">
          <span className="dp-kpi-num">{data?.tickets.done_today ?? '–'}</span>
          <span className="dp-kpi-label">เสร็จวันนี้</span>
        </div>
      </div>

      <div className="dp-grid">
        <section className="page-section dp-panel" aria-labelledby="dp-staff-h">
          <h2 id="dp-staff-h" className="dp-panel-title">ช่างทั้งหมด</h2>
          {data && staff.length === 0 && (
            <p className="dp-empty">ยังไม่มีบัญชีช่าง (บทบาท IT Support) — เพิ่มได้ที่เมนูผู้ใช้</p>
          )}
          <ul className="dp-staff">
            {sorted.map((s) => (
              <li key={s.id} className="dp-staff-row">
                <span className={`dp-dot is-${s.state}`} aria-hidden="true" />
                <span className="dp-staff-name">
                  {s.name}
                  <span className="dp-staff-sub">
                    {STATE_LABEL[s.state]} · ค้าง {s.open} · เสร็จวันนี้ {s.done_today}
                    {s.offers > 0 && ` · รอตอบ ${s.offers}`}
                    {!s.line_linked && ' · ยังไม่ผูก LINE'}
                  </span>
                </span>
                <button type="button" role="switch" aria-checked={s.on_duty} disabled={busyId === s.id}
                  aria-label={`${s.name} พร้อมรับงาน`}
                  className={`dp-switch dp-switch-sm${s.on_duty ? ' is-on' : ''}`}
                  onClick={() => void toggleDuty(s.id, !s.on_duty)}>
                  <span className="dp-switch-knob" aria-hidden="true" />
                </button>
              </li>
            ))}
          </ul>
        </section>

        <section className="page-section dp-panel" aria-labelledby="dp-unclaimed-h">
          <h2 id="dp-unclaimed-h" className="dp-panel-title">งานที่ยังไม่มีคนรับ</h2>
          {data && data.unclaimed.length === 0 && <p className="dp-empty">ไม่มีงานค้าง — ทุกงานมีคนดูแลแล้ว</p>}
          <ul className="dp-unclaimed">
            {data?.unclaimed.map((t) => (
              <li key={t.ticket_id} className="dp-unclaimed-row">
                <button type="button" className="dp-link" onClick={() => onOpenTicket(t.ticket_id)}>
                  <span className="dp-unclaimed-title">{t.title}</span>
                  <span className="dp-staff-sub">
                    {t.ticket_id} · {t.organization_name || t.device_label} · {ago(t.created_at)}
                    {t.tried ? ` · เสนอแล้ว ${t.tried} คน ไม่มีใครรับ` : ''}
                  </span>
                </button>
                <span className={`badge badge-priority-${t.priority}`}>{ticketDetailPriority[t.priority] || t.priority}</span>
                <span className="dp-assign">
                  <select className="form-select" value={pick[t.ticket_id] || ''} aria-label={`มอบหมาย ${t.ticket_id} ให้`}
                    onChange={(e) => setPick((p) => ({ ...p, [t.ticket_id]: e.target.value }))}>
                    <option value="">เลือกช่าง…</option>
                    {sorted.map((s) => (
                      <option key={s.id} value={s.id}>{s.name} ({STATE_LABEL[s.state]}, ค้าง {s.open})</option>
                    ))}
                  </select>
                  <button type="button" className="btn btn-primary btn-sm" disabled={!pick[t.ticket_id] || busyId === t.ticket_id}
                    onClick={() => void assign(t.ticket_id)}>มอบหมาย</button>
                </span>
              </li>
            ))}
          </ul>
        </section>
      </div>
    </div>
  );
}
