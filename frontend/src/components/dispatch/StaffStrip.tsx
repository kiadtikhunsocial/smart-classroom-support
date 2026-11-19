import React, { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { DispatchStaff, StaffDetail, StaffTicketRow } from '../../types';
import { ticketDateLong, ticketDetailPriority, ticketDetailStatus, ticketRelative } from '../tickets/ticketLabels';
import '../../styles/detail-sheet.css';

const STATE_TEXT: Record<string, string> = { free: 'ว่าง', busy: 'กำลังทำงาน', off: 'ปิดรับงาน' };
const ORDER = ['free', 'busy', 'off'];

function Avatar({ name, url, size = 56 }: { name: string; url?: string | null; size?: number }) {
  const [broken, setBroken] = useState(false);
  return url && !broken
    ? <img className="st-avatar" src={url} alt="" width={size} height={size} onError={() => setBroken(true)} />
    : <span className="st-avatar is-initial" style={{ width: size, height: size, fontSize: size * 0.4 }} aria-hidden="true">
        {(name || '?').trim().slice(0, 1)}
      </span>;
}

/** แถบรูปช่างบนสุดของหน้าทีมช่าง: ว่าง → กำลังทำ → ปิดรับงาน กดที่คนไหนเปิดรายละเอียด */
export default function StaffStrip({ staff, onOpenTicket }: {
  staff: DispatchStaff[];
  onOpenTicket: (ticketId: string) => void;
}) {
  const [openId, setOpenId] = useState<number | null>(null);
  const sorted = [...staff].sort((a, b) =>
    ORDER.indexOf(a.state) - ORDER.indexOf(b.state) || (a.active ?? a.open) - (b.active ?? b.open) || a.name.localeCompare(b.name, 'th'));
  const count = (s: string) => staff.filter((x) => x.state === s).length;

  if (!staff.length) return null;
  return (
    <section className="st-strip-wrap" aria-labelledby="st-strip-h">
      <header className="st-strip-head">
        <h2 id="st-strip-h">ช่างตอนนี้</h2>
        <span className="st-legend">
          <span><i className="st-dot is-free" />ว่าง {count('free')}</span>
          <span><i className="st-dot is-busy" />กำลังทำงาน {count('busy')}</span>
          <span><i className="st-dot is-off" />ปิดรับงาน {count('off')}</span>
        </span>
      </header>
      <ul className="st-strip">
        {sorted.map((s) => (
          <li key={s.id}>
            <button type="button" className={`st-card is-${s.state}`} onClick={() => setOpenId(s.id)}
              aria-label={`${s.name} — ${STATE_TEXT[s.state]} — ดูรายละเอียด`}>
              <span className="st-photo">
                <Avatar name={s.name} url={s.picture_url} />
                <i className={`st-dot is-${s.state}`} aria-hidden="true" />
              </span>
              <strong className="st-name">{s.name}</strong>
              <span className={`st-state is-${s.state}`}>
                {s.state === 'busy' ? `ทำอยู่ ${s.active ?? s.open} งาน` : STATE_TEXT[s.state]}
              </span>
              <span className="st-current" title={s.current?.title}>
                {s.current ? s.current.title : s.on_duty && !s.reachable ? 'ติดต่อไม่ได้ (ยังไม่เปิดแอป/ผูก LINE)' : s.state === 'free' ? 'พร้อมรับงานใหม่' : `เสร็จวันนี้ ${s.done_today}`}
              </span>
            </button>
          </li>
        ))}
      </ul>
      {openId != null && (
        <StaffSheet userId={openId} onClose={() => setOpenId(null)}
          onOpenTicket={(id) => { setOpenId(null); onOpenTicket(id); }} />
      )}
    </section>
  );
}

function hours(h: number | null) {
  if (h == null) return '—';
  return h < 24 ? `${h} ชม.` : `${(h / 24).toFixed(1)} วัน`;
}

function TicketList({ rows, empty, done, onOpen }: { rows: StaffTicketRow[]; empty: string; done?: boolean; onOpen: (id: string) => void }) {
  if (!rows.length) return <p className="detail-sheet-empty">{empty}</p>;
  return (
    <ul className="st-jobs">
      {rows.map((t) => {
        const late = !done && t.sla_due_at && new Date(t.sla_due_at).getTime() < Date.now();
        return (
          <li key={t.ticket_id}>
            <button type="button" className={`st-job tk-prio tk-prio-${t.priority}`} onClick={() => onOpen(t.ticket_id)}>
              <span className="st-job-top">
                <span className={`badge badge-${t.status}`}>{ticketDetailStatus(t.status)}</span>
                <span className={`badge badge-priority-${t.priority}`}>{ticketDetailPriority[t.priority] || t.priority}</span>
                {late && <span className="tk-chip-late">เกิน SLA</span>}
                <span className="st-job-id">{t.ticket_id}</span>
              </span>
              <strong className="st-job-title">{t.title}</strong>
              <span className="st-job-meta">{[t.device_label, t.organization_name, t.reporter_name && `ผู้แจ้ง ${t.reporter_name}`].filter(Boolean).join(' · ')}</span>
              <span className="st-job-meta">
                {done
                  ? `ซ่อมเสร็จ ${ticketDateLong(t.resolved_at)}${t.rating ? ` · คะแนน ${t.rating}/5` : ''}`
                  : `รับงาน ${t.assigned_at ? ticketRelative(t.assigned_at) : '—'} · แจ้งเมื่อ ${ticketDateLong(t.created_at)}`}
              </span>
              {!done && t.last_update?.note && (
                <span className="st-job-note">ล่าสุด: {t.last_update.note} <em>({ticketRelative(t.last_update.at)})</em></span>
              )}
            </button>
          </li>
        );
      })}
    </ul>
  );
}

/** แผงรายละเอียดช่าง: สรุป (ตัวเลข) + เจาะลึก (งานที่ถืออยู่ทุกใบ / งานที่ปิดล่าสุด) */
function StaffSheet({ userId, onClose, onOpenTicket }: { userId: number; onClose: () => void; onOpenTicket: (id: string) => void }) {
  const [d, setD] = useState<StaffDetail | null>(null);
  const [error, setError] = useState('');
  useEffect(() => {
    let alive = true;
    api.dispatchStaff(userId).then((x) => alive && setD(x)).catch((e: any) => alive && setError(e?.message || 'โหลดข้อมูลไม่สำเร็จ'));
    return () => { alive = false; };
  }, [userId]);
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape') onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose]);

  const l = d?.load;
  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="repair-panel detail-sheet st-sheet" onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="st-sheet-title">
        <div className="repair-panel-header">
          <h3 className="repair-panel-title" id="st-sheet-title">รายละเอียดช่าง</h3>
          <button className="repair-panel-close" onClick={onClose} aria-label="ปิด">×</button>
        </div>
        <div className="repair-panel-body">
          {error && <p className="detail-sheet-warning" role="alert">{error}</p>}
          {!d && !error && <p className="detail-sheet-help" role="status">กำลังโหลด…</p>}
          {d && l && <>
            <div className="st-profile">
              <Avatar name={d.name} url={d.picture_url} size={64} />
              <div>
                <h4 className="detail-sheet-name">{d.name}</h4>
                <p className="detail-sheet-subtitle">{d.username}{d.email ? ` · ${d.email}` : ''}</p>
                <p className="detail-sheet-subtitle">{d.organization_name}</p>
                <div className="tk-chips">
                  <span className={`st-state is-${d.state}`}><i className={`st-dot is-${d.state}`} />{STATE_TEXT[d.state]}</span>
                  <span className="st-tag">{d.line_linked ? 'ผูก LINE แล้ว' : 'ยังไม่ผูก LINE'}</span>
                  <span className="st-tag">{d.last_seen_at ? `เปิดแอปล่าสุด ${ticketRelative(d.last_seen_at)}` : 'ยังไม่เคยเปิดแอป'}</span>
                </div>
              </div>
            </div>

            <section className="detail-sheet-section"><h4>สรุป</h4>
              <div className="st-kpis">
                <div><strong>{l.active}</strong><span>กำลังทำ</span></div>
                <div><strong>{l.open}</strong><span>ถืออยู่ทั้งหมด</span></div>
                <div><strong>{l.done_today}</strong><span>เสร็จวันนี้</span></div>
                <div><strong>{l.done_7d}</strong><span>เสร็จ 7 วัน</span></div>
                <div><strong>{l.done_30d}</strong><span>เสร็จ 30 วัน</span></div>
                <div><strong>{hours(l.avg_hours_30d)}</strong><span>เวลาซ่อมเฉลี่ย</span></div>
                <div><strong>{l.avg_rating_30d ?? '—'}</strong><span>คะแนนเฉลี่ย</span></div>
                <div><strong>{l.sla_total_30d ? `${Math.round((l.sla_met_30d / l.sla_total_30d) * 100)}%` : '—'}</strong><span>ทัน SLA</span></div>
              </div>
            </section>

            <section className="detail-sheet-section"><h4>งานที่ถืออยู่ ({d.open_tickets.length})</h4>
              <TicketList rows={d.open_tickets} empty="ไม่มีงานค้าง — ว่างพร้อมรับงาน" onOpen={onOpenTicket} />
            </section>

            <section className="detail-sheet-section"><h4>งานที่ปิดล่าสุด</h4>
              <TicketList rows={d.recent_done} empty="ยังไม่มีงานที่ซ่อมเสร็จ" done onOpen={onOpenTicket} />
            </section>
          </>}
        </div>
      </div>
    </div>
  );
}
