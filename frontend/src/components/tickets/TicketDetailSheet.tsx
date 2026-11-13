import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { Ticket } from '../../types';
import ConfirmDialog from '../ConfirmDialog';
import DetailField from '../DetailField';
import { actionsFor, validateActionInput, type TicketAction } from './ticketActions';
import {
  ticketDetailChannel, ticketDetailDate, ticketDetailPriority, ticketDetailStatus,
} from './ticketLabels';

export interface TicketDetailSheetProps {
  ticketId: string;
  /** ข้อมูลจากแถวในรายการ — แสดงก่อนระหว่างรอข้อมูลเต็ม */
  initial?: Ticket;
  canManage: boolean;
  onClose: () => void;
  /** เรียกหลังใบงานถูกเปลี่ยน (ลบ/เปลี่ยนสถานะ) เพื่อให้รายการโหลดใหม่ */
  onChanged: () => void;
}

/** แผงรายละเอียดใบงาน — โหลดข้อมูลเต็ม ประวัติ ความเห็น และไฟล์แนบเองจากเลขใบงาน */
export default function TicketDetailSheet({ ticketId, initial, canManage, onClose, onChanged }: TicketDetailSheetProps) {
  const [ticket, setTicket] = useState<any | null>(initial ?? null);
  const [history, setHistory] = useState<any[]>([]);
  const [comments, setComments] = useState<any[]>([]);
  const [attachments, setAttachments] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');
  const [deleting, setDeleting] = useState(false);
  const [confirmDelete, setConfirmDelete] = useState(false);
  // ขั้นตอนงานที่กำลังกรอก (บันทึกผลซ่อม / เหตุผลยกเลิก / เหตุผลเปิดใหม่)
  const [pending, setPending] = useState<TicketAction | null>(null);
  const [solution, setSolution] = useState('');
  const [rootCause, setRootCause] = useState('');
  const [note, setNote] = useState('');
  const [running, setRunning] = useState<TicketAction['id'] | null>(null);
  const [actionError, setActionError] = useState('');
  const requestId = useRef(0);

  const load = useCallback(async () => {
    const id = ++requestId.current;
    setLoading(true); setError('');
    const [full, hist, comm, att] = await Promise.allSettled([
      api.getTicket(ticketId), api.getTicketHistory(ticketId),
      api.listTicketComments(ticketId), api.listTicketAttachments(ticketId),
    ]);
    if (id !== requestId.current) return;
    if (full.status === 'fulfilled') setTicket(full.value);
    else setError(initial ? 'โหลดรายละเอียดล่าสุดไม่สำเร็จ กำลังแสดงข้อมูลจากรายการ' : 'โหลดใบงานนี้ไม่สำเร็จ');
    setHistory(hist.status === 'fulfilled' ? hist.value : []);
    setComments(comm.status === 'fulfilled' ? comm.value : []);
    setAttachments(att.status === 'fulfilled' ? att.value : []);
    setLoading(false);
  }, [ticketId, initial]);

  useEffect(() => { void load(); return () => { requestId.current += 1; }; }, [load]);

  // Esc ปิดแผง — ยกเว้นตอนกล่องยืนยันเปิดอยู่หรือกำลังบันทึก
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => { if (e.key === 'Escape' && !confirmDelete && !running) onClose(); };
    window.addEventListener('keydown', onKey);
    return () => window.removeEventListener('keydown', onKey);
  }, [onClose, confirmDelete, running]);

  const handleDelete = async () => {
    setDeleting(true);
    try {
      await api.deleteTicket(ticketId);
      setConfirmDelete(false);
      onChanged();
      onClose();
    } catch (e: any) {
      setConfirmDelete(false);
      setError('ลบไม่สำเร็จ: ' + (e?.message || ''));
    } finally {
      setDeleting(false);
    }
  };

  const startAction = (action: TicketAction) => {
    setActionError('');
    if (action.needs === 'none') { void runAction(action); return; }
    setPending(action); setSolution(''); setRootCause(''); setNote('');
  };

  const runAction = async (action: TicketAction) => {
    const problem = validateActionInput(action, { solution, note });
    if (problem) { setActionError(problem); return; }
    setRunning(action.id); setActionError('');
    try {
      if (action.id === 'accept') await api.acceptTicket(ticketId);
      else if (action.id === 'resolve') await api.resolveTicket(ticketId, { solution: solution.trim(), root_cause: rootCause.trim() || undefined });
      else if (action.id === 'close') await api.closeTicket(ticketId, {});
      else if (action.id === 'reopen') await api.reopenTicket(ticketId, note.trim());
      else if (action.id === 'cancel') await api.cancelTicket(ticketId, note.trim());
      setPending(null);
      onChanged();
    } catch (e: any) {
      // เช่น อีกคนรับงานไปก่อน (409) — แสดงข้อความจาก server แล้วโหลดสถานะล่าสุด
      setActionError(e?.message || 'บันทึกไม่สำเร็จ');
    } finally {
      setRunning(null);
      void load();
    }
  };

  const actions = ticket ? actionsFor(ticket.status, canManage) : [];

  const t = ticket;
  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="repair-panel detail-sheet tk-sheet" onClick={(e) => e.stopPropagation()}
        role="dialog" aria-modal="true" aria-labelledby="ticket-detail-title">
        <div className="repair-panel-header">
          <h3 className="repair-panel-title" id="ticket-detail-title">รายละเอียดใบงาน</h3>
          <button className="repair-panel-close" onClick={onClose} aria-label="ปิด">×</button>
        </div>
        <div className="repair-panel-body">
          {loading && <p className="detail-sheet-help" role="status">กำลังโหลดข้อมูลล่าสุด…</p>}
          {error && <p className="detail-sheet-warning" role="alert">{error}</p>}
          {t && !loading && <>
            <div className="detail-sheet-identity">
              <p className="detail-sheet-kicker">ใบงาน {t.ticket_id}</p>
              <h4 className="detail-sheet-name">{t.title || 'ไม่ได้ระบุหัวข้อ'}</h4>
              <div className="detail-sheet-statuses">
                <span>{ticketDetailStatus(t.status)}</span>
                <span>ความเร่งด่วน {ticketDetailPriority[t.priority] || t.priority || '—'}</span>
              </div>
            </div>

            <section className="detail-sheet-section"><h4>สถานะและเวลา</h4>
              <dl className="detail-sheet-grid">
                <DetailField label="สถานะ" value={ticketDetailStatus(t.status)} />
                <DetailField label="ความเร่งด่วน" value={ticketDetailPriority[t.priority] || t.priority} />
                <DetailField label="แจ้งเมื่อ" value={ticketDetailDate(t.created_at)} />
                <DetailField label="อัปเดตล่าสุด" value={ticketDetailDate(t.updated_at)} />
                <DetailField label="กำหนด SLA" value={ticketDetailDate(t.sla_due_at)} />
                <DetailField label="ช่องทาง" value={ticketDetailChannel[t.channel] || t.channel} />
              </dl>
            </section>

            <section className="detail-sheet-section"><h4>อุปกรณ์และผู้เกี่ยวข้อง</h4>
              <dl className="detail-sheet-grid">
                <DetailField label="อุปกรณ์" value={t.device_label || t.device_id} wide />
                <DetailField label="รหัสอุปกรณ์" value={t.device_id} mono />
                <DetailField label="โรงเรียน" value={t.organization_name} />
                <DetailField label="ผู้แจ้ง" value={t.reporter_name} />
                <DetailField label="เบอร์ติดต่อ" value={t.reporter_phone} />
                <DetailField label="ผู้รับผิดชอบ" value={t.assigned_to} />
              </dl>
            </section>

            <section className="detail-sheet-section"><h4>อาการ / รายละเอียดที่แจ้ง</h4>
              <p className="detail-sheet-note">{t.description || 'ไม่มีรายละเอียดเพิ่มเติม'}</p>
            </section>

            <section className="detail-sheet-section"><h4>ตำแหน่งขณะแจ้งผ่าน QR</h4>
              {t.scan_gps_lat != null && t.scan_gps_lng != null ? (
                <p className="detail-sheet-note">
                  {Number(t.scan_gps_lat).toFixed(6)}, {Number(t.scan_gps_lng).toFixed(6)}
                  {t.scan_timestamp && <> · {ticketDetailDate(t.scan_timestamp)}</>}
                  {' · '}<a href={`https://www.google.com/maps?q=${encodeURIComponent(`${t.scan_gps_lat},${t.scan_gps_lng}`)}`} target="_blank" rel="noopener noreferrer">เปิดแผนที่ ↗</a>
                </p>
              ) : <p className="detail-sheet-empty">ไม่มีพิกัดจากการสแกนครั้งนี้ หรือแจ้งจากช่องทางอื่น</p>}
              <p className="detail-sheet-help">พิกัดจากอุปกรณ์ผู้แจ้งอาจคลาดเคลื่อน ไม่ใช่หลักฐานยืนยันตำแหน่งอุปกรณ์</p>
            </section>

            {(t.root_cause || t.solution) && <section className="detail-sheet-section"><h4>ผลการดำเนินงาน</h4>
              <dl className="detail-sheet-grid">
                {t.root_cause && <DetailField label="สาเหตุ" value={t.root_cause} wide />}
                {t.solution && <DetailField label="วิธีแก้ไข" value={t.solution} wide />}
              </dl>
            </section>}

            <section className="detail-sheet-section"><h4>ประวัติสถานะ</h4>
              {history.length ? <ul className="detail-sheet-list">{history.map((h, i) => <li key={h.id || i}>
                {h.created_at && <time>{ticketDetailDate(h.created_at)}</time>}
                <strong>{ticketDetailStatus(h.to_status)}</strong>{h.note ? ` — ${h.note}` : ''}
              </li>)}</ul> : <p className="detail-sheet-empty">ไม่มีประวัติสถานะ</p>}
            </section>
            <section className="detail-sheet-section"><h4>ความเห็น</h4>
              {comments.length ? <ul className="detail-sheet-list">{comments.map((c, i) => <li key={c.id || i}>
                <strong>{c.author_name || 'เจ้าหน้าที่'}{c.is_internal ? ' (ภายใน)' : ''}</strong>: {c.note || '—'}
              </li>)}</ul> : <p className="detail-sheet-empty">ไม่มีความเห็น</p>}
            </section>
            <section className="detail-sheet-section"><h4>ไฟล์แนบ</h4>
              {attachments.length ? <ul className="detail-sheet-list">{attachments.map((a, i) => <li key={a.id || i}>
                <a href={a.file_url || a.url} target="_blank" rel="noreferrer">{a.file_name || a.filename || `ไฟล์ ${i + 1}`}</a>
              </li>)}</ul> : <p className="detail-sheet-empty">ไม่มีไฟล์แนบ</p>}
            </section>

            {/* ลบอยู่ท้ายแผง แยกจากปุ่มขั้นตอนงาน — เดิมอยู่ติดปุ่มปิดที่ footer เสี่ยงกดพลาด */}
            {canManage && (
              <section className="detail-sheet-section tk-danger-zone">
                <button type="button" className="tk-link-danger" disabled={deleting}
                  onClick={() => setConfirmDelete(true)}>
                  ย้ายใบงานนี้ไปถังกู้คืน
                </button>
              </section>
            )}
          </>}
        </div>

        {pending && (
          <form className="tk-action-form" onSubmit={(e) => { e.preventDefault(); void runAction(pending); }}>
            {pending.needs === 'solution' ? (
              <>
                <label className="form-label" htmlFor="tk-solution">วิธีแก้ไข <span className="required">*</span></label>
                <textarea id="tk-solution" className="form-input" rows={3} maxLength={2000} autoFocus
                  value={solution} onChange={(e) => setSolution(e.target.value)}
                  placeholder="เช่น เปลี่ยนสาย HDMI ใหม่ ทดสอบภาพขึ้นปกติ" />
                <label className="form-label" htmlFor="tk-root-cause">สาเหตุ (ไม่บังคับ)</label>
                <input id="tk-root-cause" className="form-input" maxLength={500}
                  value={rootCause} onChange={(e) => setRootCause(e.target.value)} />
              </>
            ) : (
              <>
                <label className="form-label" htmlFor="tk-note">เหตุผล <span className="required">*</span></label>
                <textarea id="tk-note" className="form-input" rows={2} maxLength={2000} autoFocus
                  value={note} onChange={(e) => setNote(e.target.value)} />
              </>
            )}
            <div className="tk-action-form-buttons">
              <button type="button" className="btn btn-ghost" onClick={() => { setPending(null); setActionError(''); }} disabled={!!running}>
                ไม่ใช่ตอนนี้
              </button>
              <button type="submit" className={`btn ${pending.id === 'cancel' ? 'btn-danger' : 'btn-primary'}`} disabled={!!running}>
                {running ? 'กำลังบันทึก…' : `ยืนยัน${pending.label}`}
              </button>
            </div>
          </form>
        )}

        {actionError && <p className="tk-action-error" role="alert">{actionError}</p>}

        <div className="detail-sheet-footer tk-sheet-footer">
          {!pending && actions.map((a) => (
            <button key={a.id} type="button"
              className={`btn ${a.kind === 'primary' ? 'btn-primary' : 'btn-secondary'}`}
              disabled={loading || !!running}
              onClick={() => startAction(a)}>
              {running === a.id ? 'กำลังบันทึก…' : a.label}
            </button>
          ))}
          <span className="tk-footer-spacer" />
          <button type="button" className="btn btn-secondary" onClick={onClose} disabled={!!running}>ปิด</button>
        </div>
      </div>

      {confirmDelete && (
        <ConfirmDialog
          title="ย้ายใบงานไปถังกู้คืน"
          message={`ย้ายใบงาน ${ticketId} ไปถังข้อมูลที่กู้คืนได้?`}
          confirmLabel="ย้ายไปถังกู้คืน"
          danger
          busy={deleting}
          onConfirm={() => void handleDelete()}
          onCancel={() => setConfirmDelete(false)}
        />
      )}
    </div>
  );
}
