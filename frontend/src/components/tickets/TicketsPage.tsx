import React, { useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { Ticket } from '../../types';
import DetailField from '../DetailField';
import {
  ALL_STATUSES, STATUS_LABELS_TICKET, ticketDetailChannel, ticketDetailDate,
  ticketDetailPriority, ticketDetailStatus,
} from './ticketLabels';

export default function TicketsPage({ tickets, onBack, onTicketsChanged, canManage, focusId, onFocusHandled }: {
  tickets: Ticket[];
  onBack: () => void;
  onTicketsChanged: () => void;
  canManage: boolean;
  focusId?: string;
  onFocusHandled?: () => void;
}) {
  const [updating, setUpdating] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [detailTicket, setDetailTicket] = useState<any | null>(null);
  const [detailHistory, setDetailHistory] = useState<any[]>([]);
  const [detailComments, setDetailComments] = useState<any[]>([]);
  const [detailAttachments, setDetailAttachments] = useState<any[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const detailRequest = React.useRef(0);
  const openTicketDetail = async (ticket: Ticket) => {
    const requestId = ++detailRequest.current;
    setDetailTicket(ticket); setDetailLoading(true); setDetailError('');
    setDetailHistory([]); setDetailComments([]); setDetailAttachments([]);
    const [full, history, comments, attachments] = await Promise.allSettled([
      api.getTicket(ticket.ticket_id), api.getTicketHistory(ticket.ticket_id),
      api.listTicketComments(ticket.ticket_id), api.listTicketAttachments(ticket.ticket_id),
    ]);
    if (requestId !== detailRequest.current) return;
    if (full.status === 'fulfilled') setDetailTicket(full.value);
    else setDetailError('โหลดรายละเอียดล่าสุดไม่สำเร็จ กำลังแสดงข้อมูลจากรายการ');
    if (history.status === 'fulfilled') setDetailHistory(history.value);
    if (comments.status === 'fulfilled') setDetailComments(comments.value);
    if (attachments.status === 'fulfilled') setDetailAttachments(attachments.value);
    setDetailLoading(false);
  };
  const closeTicketDetail = () => { detailRequest.current += 1; setDetailTicket(null); };
  useEffect(() => {
    if (!focusId) return;
    const found = tickets.find((ticket) => ticket.ticket_id === focusId);
    if (found) { void openTicketDetail(found); onFocusHandled?.(); }
  // A new focus request or refreshed ticket list is enough to reopen the exact record.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusId, tickets]);
  // ── ตัวกรองรายการ Ticket: คำค้น / สถานะ / ความเร่งด่วน / ประเภทอุปกรณ์ ──
  const [q, setQ] = useState('');
  const [fStatus, setFStatus] = useState('');
  const [fPriority, setFPriority] = useState('');
  const [fType, setFType] = useState('');
  const [fCategory, setFCategory] = useState('');
  // กรองเป็นหมวดโรงเรียน — เก็บเป็น organization_id (string) เพื่อไม่ชนกรณีชื่อซ้ำ
  const [fOrg, setFOrg] = useState('');

  // ประเภทอุปกรณ์เอาจากรายการที่มีจริง ไม่ต้องเรียก API เพิ่ม
  const deviceTypes = Array.from(
    new Set(tickets.map((t) => (t.device_type || '').trim()).filter(Boolean)),
  ).sort((a, b) => a.localeCompare(b, 'th'));

  // หมวดหมู่อุปกรณ์เอาจาก ticket ที่มีจริงเช่นกัน (backend map ประเภท → หมวดให้แล้ว)
  const deviceCategories = Array.from(
    new Set(tickets.map((t) => (t.device_category || '').trim()).filter(Boolean)),
  ).sort((a, b) => a.localeCompare(b, 'th'));

  // รายชื่อโรงเรียนจาก ticket ที่มองเห็นจริง (Map กัน id ซ้ำ) → [id, ป้ายที่แสดง]
  const ticketOrgs = Array.from(
    new Map(
      tickets
        .filter((t) => t.organization_id != null)
        .map((t) => [
          String(t.organization_id),
          `${t.organization_name || 'ไม่ระบุโรงเรียน'}${t.organization_code ? ` (${t.organization_code})` : ''}`,
        ] as [string, string]),
    ).entries(),
  ).sort((a, b) => a[1].localeCompare(b[1], 'th'));

  const kw = q.trim().toLowerCase();
  const filtered = tickets.filter((t) => {
    if (fStatus && t.status !== fStatus) return false;
    if (fPriority && t.priority !== fPriority) return false;
    if (fType && (t.device_type || '') !== fType) return false;
    if (fCategory && (t.device_category || '') !== fCategory) return false;
    if (fOrg && String(t.organization_id ?? '') !== fOrg) return false;
    if (!kw) return true;
    // ค้นด้วยชื่ออุปกรณ์/โรงเรียนได้ด้วย ไม่ใช่แค่รหัส
    return [
      t.ticket_id, t.device_id, t.device_label, t.device_category,
      t.organization_name, t.organization_code,
      t.title, t.reporter_name, t.description,
    ].some((v) => (v || '').toLowerCase().includes(kw));
  });
  const hasFilter = !!(kw || fStatus || fPriority || fType || fCategory || fOrg);
  const clearFilters = () => {
    setQ(''); setFStatus(''); setFPriority(''); setFType(''); setFCategory(''); setFOrg('');
  };

  const handleStatusChange = async (ticketId: string, newStatus: string) => {
    if (!newStatus) return;
    setUpdating(ticketId);
    try {
      await api.updateStatus(ticketId, { status: newStatus, author_name: 'ผู้ดูแลระบบ', force: true });
      onTicketsChanged();
    } catch (e: any) {
      alert('อัปเดตสถานะไม่สำเร็จ: ' + (e.message || ''));
    } finally {
      setUpdating(null);
    }
  };

  const handleDelete = async (ticketId: string) => {
    if (!window.confirm(`ย้าย Ticket ${ticketId} ไปถังข้อมูลที่กู้คืนได้?`)) return;
    setDeleting(ticketId);
    try {
      await api.deleteTicket(ticketId);
      closeTicketDetail();
      onTicketsChanged();
    } catch (e: any) {
      alert('ลบไม่สำเร็จ: ' + (e.message || ''));
    } finally {
      setDeleting(null);
    }
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
            <h1 className="top-bar-title">Tickets</h1>
            <span className="top-bar-subtitle">
              {hasFilter ? `${filtered.length} / ${tickets.length} รายการ` : `${tickets.length} รายการ`}
            </span>
          </div>
        </div>
        <div className="top-bar-actions">
          <button className="btn btn-ghost" onClick={onTicketsChanged}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" style={{ marginRight: 6, verticalAlign: '-2px' }}>
              <path d="M21 12a9 9 0 11-3.5-7.1" />
              <path d="M21 3v6h-6" />
            </svg>
            รีเฟรช
          </button>
        </div>
      </div>

      <div className="page-section">
        <div className="section-body">
          <div
            style={{
              display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center',
              marginBottom: 'var(--spacing-md)',
            }}
          >
            <input
              className="form-input"
              style={{ flex: '1 1 200px', minWidth: 160, maxWidth: 340 }}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="ค้นหา: เลข Ticket / อุปกรณ์ / หัวข้อ / ผู้แจ้ง"
              aria-label="ค้นหา Ticket"
            />
            <select
              className="form-select"
              style={{ flex: '0 1 190px', minWidth: 150 }}
              value={fStatus}
              onChange={(e) => setFStatus(e.target.value)}
              aria-label="กรองตามสถานะ"
            >
              <option value="">ทุกสถานะ</option>
              {ALL_STATUSES.map((s) => (
                <option key={s} value={s}>{STATUS_LABELS_TICKET[s]}</option>
              ))}
            </select>
            <select
              className="form-select"
              style={{ flex: '0 1 170px', minWidth: 140 }}
              value={fPriority}
              onChange={(e) => setFPriority(e.target.value)}
              aria-label="กรองตามความเร่งด่วน"
            >
              <option value="">ทุกความเร่งด่วน</option>
              <option value="low">low</option>
              <option value="normal">normal</option>
              <option value="high">high</option>
              <option value="critical">critical</option>
            </select>
            <select
              className="form-select"
              style={{ flex: '0 1 190px', minWidth: 150 }}
              value={fType}
              onChange={(e) => setFType(e.target.value)}
              aria-label="กรองตามประเภทอุปกรณ์"
              disabled={deviceTypes.length === 0}
            >
              <option value="">ทุกประเภทอุปกรณ์</option>
              {deviceTypes.map((dt) => (
                <option key={dt} value={dt}>{dt}</option>
              ))}
            </select>
            <select
              className="form-select"
              style={{ flex: '0 1 190px', minWidth: 150 }}
              value={fCategory}
              onChange={(e) => setFCategory(e.target.value)}
              aria-label="กรองตามหมวดหมู่อุปกรณ์"
              disabled={deviceCategories.length === 0}
            >
              <option value="">ทุกหมวดหมู่อุปกรณ์</option>
              {deviceCategories.map((dc) => (
                <option key={dc} value={dc}>{dc}</option>
              ))}
            </select>
            <select
              className="form-select"
              style={{ flex: '0 1 220px', minWidth: 160 }}
              value={fOrg}
              onChange={(e) => setFOrg(e.target.value)}
              aria-label="กรองตามโรงเรียน"
              disabled={ticketOrgs.length === 0}
            >
              <option value="">ทุกโรงเรียน</option>
              {ticketOrgs.map(([id, label]) => (
                <option key={id} value={id}>{label}</option>
              ))}
            </select>
            {hasFilter && (
              <button type="button" className="btn btn-ghost" onClick={clearFilters}>
                ล้างตัวกรอง
              </button>
            )}
          </div>
          {filtered.length === 0 ? (
            <div className="empty-state" style={{ padding: '32px 16px' }}>
              <svg className="empty-icon" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="5" width="18" height="14" rx="2"/>
                <path d="M3 10h18M8 20a2 2 0 004 0M12 20a2 2 0 004 0M16 20a2 2 0 004 0"/>
              </svg>
              <span className="empty-text">
                {tickets.length === 0 ? 'ไม่มี Ticket' : 'ไม่พบ Ticket ที่ตรงกับตัวกรอง'}
              </span>
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
                    <th>สถานะ</th>
                    <th>ความเร่งด่วน</th>
                    <th>สร้างเมื่อ</th>
                    {canManage && <th>จัดการ</th>}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((ticket) => (
                    <tr key={ticket.ticket_id} className="clickable-data-row" tabIndex={0}
                      aria-label={`ดูรายละเอียด Ticket ${ticket.ticket_id}`}
                      onClick={(e) => { if (!(e.target as HTMLElement).closest('button, a, select, input')) void openTicketDetail(ticket); }}
                      onKeyDown={(e) => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); void openTicketDetail(ticket); } }}>
                      <td className="table-id">{ticket.ticket_id}</td>
                      <td>
                        <div className="table-meta">
                          <span style={{ fontWeight: 500 }}>{ticket.device_id}</span>
                          <span className="table-meta-row">
                            {ticket.device_label || ticket.device_type || ''}
                            {ticket.device_category ? ` · ${ticket.device_category}` : ''}
                            {ticket.organization_name ? ` · ${ticket.organization_name}` : ''}
                          </span>
                        </div>
                      </td>
                      <td>{ticket.title}</td>
                      <td>{ticket.reporter_name || '—'}</td>
                      <td>
                        {canManage ? (
                          <select
                            className="form-select"
                            style={{ width: 140, padding: '5px 8px', fontSize: '0.8rem' }}
                            value={ticket.status}
                            disabled={updating === ticket.ticket_id}
                            onChange={(e) => handleStatusChange(ticket.ticket_id, e.target.value)}
                          >
                            {ALL_STATUSES.map((s) => (
                              <option key={s} value={s}>{STATUS_LABELS_TICKET[s]}</option>
                            ))}
                          </select>
                        ) : (
                          <span className={`badge badge-${ticket.status}`}>
                            {STATUS_LABELS_TICKET[ticket.status] || ticket.status.replace(/_/g, ' ')}
                          </span>
                        )}
                      </td>
                      <td>
                        <span className={`badge badge-priority-${ticket.priority}`}>
                          {ticket.priority}
                        </span>
                      </td>
                      <td style={{ color: 'var(--color-text-tertiary)', fontSize: '0.8rem' }}>
                        {new Date(ticket.created_at).toLocaleDateString('th-TH', {
                          day: '2-digit', month: 'short', year: 'numeric',
                        })}
                      </td>
                      {canManage && (
                        <td style={{ display: 'flex', gap: 6 }}>
                          <button className="btn btn-secondary btn-sm" onClick={() => void openTicketDetail(ticket)}>รายละเอียด</button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
      {detailTicket && <div className="panel-overlay" onClick={closeTicketDetail}>
        <div className="repair-panel detail-sheet" style={{ width: 760, maxWidth: '96vw' }} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="ticket-detail-title">
          <div className="repair-panel-header"><h3 className="repair-panel-title" id="ticket-detail-title">รายละเอียดใบงาน</h3><button className="repair-panel-close" onClick={closeTicketDetail} aria-label="ปิด">×</button></div>
          <div className="repair-panel-body">
            {detailLoading && <p className="detail-sheet-help" role="status">กำลังโหลดข้อมูลล่าสุด…</p>}
            {detailError && <p className="detail-sheet-warning" role="alert">{detailError}</p>}
            {!detailLoading && <>
            <div className="detail-sheet-identity">
              <p className="detail-sheet-kicker">TICKET {detailTicket.ticket_id}</p>
              <h4 className="detail-sheet-name">{detailTicket.title || 'ไม่ได้ระบุหัวข้อ'}</h4>
              <div className="detail-sheet-statuses">
                <span>{ticketDetailStatus(detailTicket.status)}</span>
                <span>ความเร่งด่วน {ticketDetailPriority[detailTicket.priority] || detailTicket.priority || '—'}</span>
              </div>
            </div>

            <section className="detail-sheet-section"><h4>สถานะและเวลา</h4>
              <dl className="detail-sheet-grid">
                <DetailField label="สถานะ" value={ticketDetailStatus(detailTicket.status)} />
                <DetailField label="ความเร่งด่วน" value={ticketDetailPriority[detailTicket.priority] || detailTicket.priority} />
                <DetailField label="แจ้งเมื่อ" value={ticketDetailDate(detailTicket.created_at)} />
                <DetailField label="อัปเดตล่าสุด" value={ticketDetailDate(detailTicket.updated_at)} />
                <DetailField label="กำหนด SLA" value={ticketDetailDate(detailTicket.sla_due_at)} />
                <DetailField label="ช่องทาง" value={ticketDetailChannel[detailTicket.channel] || detailTicket.channel} />
              </dl>
            </section>

            <section className="detail-sheet-section"><h4>อุปกรณ์และผู้เกี่ยวข้อง</h4>
              <dl className="detail-sheet-grid">
                <DetailField label="อุปกรณ์" value={detailTicket.device_label || detailTicket.device_id} wide />
                <DetailField label="รหัสอุปกรณ์" value={detailTicket.device_id} mono />
                <DetailField label="โรงเรียน" value={detailTicket.organization_name} />
                <DetailField label="ผู้แจ้ง" value={detailTicket.reporter_name} />
                <DetailField label="เบอร์ติดต่อ" value={detailTicket.reporter_phone} />
                <DetailField label="ผู้รับผิดชอบ" value={detailTicket.assigned_to} />
              </dl>
            </section>

            <section className="detail-sheet-section"><h4>อาการ / รายละเอียดที่แจ้ง</h4>
              <p className="detail-sheet-note">{detailTicket.description || 'ไม่มีรายละเอียดเพิ่มเติม'}</p>
            </section>

            <section className="detail-sheet-section"><h4>ตำแหน่งขณะแจ้งผ่าน QR</h4>
              {detailTicket.scan_gps_lat != null && detailTicket.scan_gps_lng != null ? (
                <p className="detail-sheet-note">
                  {Number(detailTicket.scan_gps_lat).toFixed(6)}, {Number(detailTicket.scan_gps_lng).toFixed(6)}
                  {detailTicket.scan_timestamp && <> · {ticketDetailDate(detailTicket.scan_timestamp)}</>}
                  {' · '}<a href={`https://www.google.com/maps?q=${encodeURIComponent(`${detailTicket.scan_gps_lat},${detailTicket.scan_gps_lng}`)}`} target="_blank" rel="noopener noreferrer">เปิดแผนที่ ↗</a>
                </p>
              ) : <p className="detail-sheet-empty">ไม่มีพิกัดจากการสแกนครั้งนี้ หรือแจ้งจากช่องทางอื่น</p>}
              <p className="detail-sheet-help">พิกัดจากอุปกรณ์ผู้แจ้งอาจคลาดเคลื่อน ไม่ใช่หลักฐานยืนยันตำแหน่งอุปกรณ์</p>
            </section>

            {(detailTicket.root_cause || detailTicket.solution) && <section className="detail-sheet-section"><h4>ผลการดำเนินงาน</h4>
              <dl className="detail-sheet-grid">
                {detailTicket.root_cause && <DetailField label="สาเหตุ" value={detailTicket.root_cause} wide />}
                {detailTicket.solution && <DetailField label="วิธีแก้ไข" value={detailTicket.solution} wide />}
              </dl>
            </section>}

            <section className="detail-sheet-section"><h4>ประวัติสถานะ</h4>
              {detailHistory.length ? <ul className="detail-sheet-list">{detailHistory.map((h, i) => <li key={h.id || i}>
                {h.created_at && <time>{ticketDetailDate(h.created_at)}</time>}
                <strong>{ticketDetailStatus(h.to_status)}</strong>{h.note ? ` — ${h.note}` : ''}
              </li>)}</ul> : <p className="detail-sheet-empty">ไม่มีประวัติสถานะ</p>}
            </section>
            <section className="detail-sheet-section"><h4>ความเห็น</h4>
              {detailComments.length ? <ul className="detail-sheet-list">{detailComments.map((c, i) => <li key={c.id || i}>
                <strong>{c.author_name || 'เจ้าหน้าที่'}{c.is_internal ? ' (ภายใน)' : ''}</strong>: {c.note || '—'}
              </li>)}</ul> : <p className="detail-sheet-empty">ไม่มีความเห็น</p>}
            </section>
            <section className="detail-sheet-section"><h4>ไฟล์แนบ</h4>
              {detailAttachments.length ? <ul className="detail-sheet-list">{detailAttachments.map((a, i) => <li key={a.id || i}>
                <a href={a.file_url || a.url} target="_blank" rel="noreferrer">{a.file_name || a.filename || `ไฟล์ ${i + 1}`}</a>
              </li>)}</ul> : <p className="detail-sheet-empty">ไม่มีไฟล์แนบ</p>}
            </section>
            </>}
          </div>
          <div className="detail-sheet-footer"><button className="btn btn-secondary" onClick={closeTicketDetail}>ปิดรายละเอียด</button>{canManage && <button className="btn btn-danger" disabled={deleting === detailTicket.ticket_id || detailLoading} onClick={() => void handleDelete(detailTicket.ticket_id)}>{deleting === detailTicket.ticket_id ? 'กำลังลบ…' : 'ลบใบงาน'}</button>}</div>
        </div>
      </div>}
    </div>
  );
}
