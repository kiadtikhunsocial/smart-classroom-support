import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api/client';
import '../styles/public-home.css';
// เลเยอร์ธีม: ผูก --ph-* เข้ากับ token กลาง จึงต้องมาหลัง public-home.css
import '../styles/public-theme.css';
// การ์ดตรวจสอบประกัน — ใช้ตัวแปร --ph-* จึงต้องมาหลังไฟล์ธีมข้างบน
import '../styles/public-warranty.css';
import '../styles/public-premium.css';
import '../styles/public-refresh.css';
// เลย์เอาต์ใหม่ (pc-*) ตามแบบที่เจ้าของงานส่งมา — โหลดท้ายสุด
import '../styles/public-clean.css';
import ThemeModeButton from './ThemeModeButton';
import LanguageSwitcher from './LanguageSwitcher';
import AIChatWidget from './AIChatWidget';
import { forgetRecent, loadRecent, looksLikeTicketNo, saveRecent } from '../publicRecent';
import { useLang } from '../publicI18n';
import type { PublicTicketStatus } from '../types';

type T = (key: string, vars?: Record<string, string | number>) => string;

/** ขั้นตอนหลักที่ผู้แจ้งเข้าใจได้ — สถานะย่อย (รออะไหล่/รอผู้ใช้) นับอยู่ในขั้น "กำลังซ่อม" */
const STEP_KEYS = ['new', 'assigned', 'in_progress', 'resolved', 'closed'];

const STEP_INDEX: Record<string, number> = {
  new: 0,
  assigned: 1,
  in_progress: 2,
  pending: 2,
  waiting_parts: 2,
  waiting_user: 2,
  resolved: 3,
  closed: 4,
  cancelled: -1,
};

const KNOWN_STATUS = new Set(['new', 'assigned', 'in_progress', 'pending', 'waiting_parts', 'waiting_user', 'resolved', 'closed', 'cancelled']);
const KNOWN_PRIORITY = new Set(['critical', 'high', 'normal', 'low']);

/** งานที่ยังไม่จบ — หน้าติดตามรีเฟรชสถานะเองทุก 60 วินาที */
const LIVE_REFRESH_MS = 60_000;
const FINISHED = new Set(['closed', 'cancelled']);

/** เวลาที่เข้าแต่ละขั้นของ stepper — จากไทม์ไลน์ (เอาครั้งแรกที่ถึงขั้นนั้น) */
function stepTimes(history: any[]): Record<number, string> {
  const out: Record<number, string> = {};
  for (const h of history) {
    const idx = STEP_INDEX[h.status ?? h.to_status];
    if (typeof idx === 'number' && idx >= 0 && !(idx in out) && h.created_at) out[idx] = h.created_at;
  }
  return out;
}

function shortTime(v: string | null | undefined, locale: string): string {
  if (!v) return '';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return '';
  const sameDay = d.toDateString() === new Date().toDateString();
  const time = d.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' });
  return sameDay ? time : d.toLocaleDateString(locale, { day: 'numeric', month: 'short' }) + ' ' + time;
}

function fmtDateTime(v: string | null | undefined, locale: string): string {
  if (!v) return '-';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleString(locale, { dateStyle: 'medium', timeStyle: 'short' });
}

/** วันที่แบบไม่มีเวลา — ข้อมูลประกันเป็นระดับวัน */
function fmtDate(v: string | null | undefined, locale: string): string {
  if (!v) return '-';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleDateString(locale, { dateStyle: 'medium' });
}

/** ระยะเวลาตั้งแต่แจ้ง — ช่วยให้ผู้แจ้งเห็นว่าเรื่องค้างมานานเท่าไหร่ */
function sinceText(v: string | null | undefined, t: T): string {
  if (!v) return '';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return '';
  const mins = Math.floor((Date.now() - d.getTime()) / 60000);
  if (mins < 0) return '';
  if (mins < 60) return t('since_min', { n: mins });
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return t('since_hour', { n: hrs });
  return t('since_day', { n: Math.floor(hrs / 24) });
}

function statusText(status: string | undefined, fallback: string | undefined, t: T): string {
  if (status && KNOWN_STATUS.has(status)) return t(`st_${status}`);
  return fallback || status || '';
}

function statusLabelOf(tk: any, t: T): string {
  if (!tk) return '';
  if (tk.finding_technician) return t('st_finding');
  return statusText(tk.status, tk.status_label, t);
}

// ─── Icons ───────────────────────────────────────────────────────────────────

function ScanIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" aria-hidden="true">
      <path d="M3 8V5a2 2 0 012-2h3M16 3h3a2 2 0 012 2v3M21 16v3a2 2 0 01-2 2h-3M8 21H5a2 2 0 01-2-2v-3" />
      <path d="M3 12h18" />
    </svg>
  );
}

function SearchIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <circle cx="11" cy="11" r="8" />
      <path d="M21 21l-4.35-4.35" />
    </svg>
  );
}

function CheckIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" aria-hidden="true">
      <path d="M20 6L9 17l-5-5" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M12 3l7 3v5.5c0 4.4-2.9 8.2-7 9.5-4.1-1.3-7-5.1-7-9.5V6l7-3z" />
      <path d="M9.5 12.2l1.9 1.9 3.6-3.7" />
    </svg>
  );
}

function HeadsetIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M4 14v-2a8 8 0 0116 0v2" />
      <path d="M4 14h3v5H5a1 1 0 01-1-1v-4zM20 14h-3v5h2a1 1 0 001-1v-4z" />
    </svg>
  );
}

function RefreshIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M20 11a8 8 0 10-2.3 5.7" />
      <path d="M20 5v6h-6" />
    </svg>
  );
}

function LinkIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M10 13a4 4 0 005.7 0l3-3a4 4 0 00-5.7-5.7l-1.2 1.2" />
      <path d="M14 11a4 4 0 00-5.7 0l-3 3A4 4 0 009 19.7l1.2-1.2" />
    </svg>
  );
}

function PlusIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M12 5v14M5 12h14" />
    </svg>
  );
}

function ArrowIcon() {
  return (
    <svg className="pc-arrow" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

function CloseIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <path d="M6 6l12 12M18 6L6 18" />
    </svg>
  );
}

function MetaItem({ label, value, sub }: { label: string; value: React.ReactNode; sub?: React.ReactNode }) {
  return (
    <div className="ph-meta">
      <span className="ph-meta-label">{label}</span>
      <span className="ph-meta-value">{value}</span>
      {sub ? <span className="ph-meta-sub">{sub}</span> : null}
    </div>
  );
}

/**
 * เลื่อนผลลัพธ์ขึ้นมาให้เห็นและย้ายโฟกัสไปที่ผลลัพธ์ ทุกครั้งที่ `tick` เปลี่ยน
 * บนมือถือผลลัพธ์อยู่ใต้ขอบจอ ถ้าไม่เลื่อน ผู้ใช้จะรู้สึกว่ากดแล้วไม่มีอะไรเกิดขึ้น
 */
function useRevealResult(ref: React.RefObject<HTMLElement>, tick: number) {
  useEffect(() => {
    if (tick === 0 || !ref.current) return;
    const reduce = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches;
    ref.current.scrollIntoView({ behavior: reduce ? 'auto' : 'smooth', block: 'start' });
    ref.current.focus({ preventScroll: true });
  }, [tick, ref]);
}

const WARRANTY_TONE: Record<string, 'ok' | 'warn' | 'danger' | 'muted'> = {
  active: 'ok',
  expiring: 'warn',
  expired: 'danger',
  unknown: 'muted',
};

/**
 * แผง "ตรวจสอบประกัน" — เปิดจากปุ่มในแถวลิงก์ใต้ติดตามงาน
 * กรอกหมายเลขสินค้า (หรือรหัสอุปกรณ์) แล้วดูสถานะประกันได้เอง ไม่ต้องล็อกอิน
 */
function WarrantyCard({ onClose }: { onClose: () => void }) {
  const { t, locale } = useLang();
  const [code, setCode] = useState('');
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const serialRef = useRef<HTMLInputElement | null>(null);
  const resultRef = useRef<HTMLDivElement | null>(null);
  const [revealTick, setRevealTick] = useState(0);
  useRevealResult(resultRef, revealTick);

  useEffect(() => {
    serialRef.current?.focus();
  }, []);

  const lookup = useCallback(async () => {
    const q = code.trim();
    if (!q) {
      setError(t('w_empty'));
      setData(null);
      setSearched(false);
      serialRef.current?.focus();
      return;
    }
    setLoading(true);
    setError(null);
    setData(null);
    setSearched(false);
    try {
      setData(await api.checkWarranty(q));
    } catch (err: any) {
      setError(err?.message || t('w_not_found'));
    } finally {
      setLoading(false);
      setSearched(true);
      setRevealTick((n) => n + 1);
    }
  }, [code, t]);

  const status: string = typeof data?.warranty_status === 'string' ? data.warranty_status : 'unknown';
  const tone = WARRANTY_TONE[status] ?? 'muted';
  const statusLabel = WARRANTY_TONE[status] ? t(`w_${status}`) : (data?.warranty_status_label || t('w_unknown'));
  const daysLeft: number | null = typeof data?.days_left === 'number' ? data.days_left : null;
  const daysText = !data
    ? ''
    : daysLeft === null
      ? t('w_days_none')
      : daysLeft < 0
        ? t('w_days_past', { n: Math.abs(daysLeft) })
        : daysLeft === 0
          ? t('w_days_today')
          : t('w_days_left', { n: daysLeft });

  const openTicket = data?.open_ticket ?? null;
  const openTicketNo: string = openTicket?.ticket_id || openTicket?.ticket_no || '';

  return (
    <section className="pc-sheet phw-card" id="ph-warranty" aria-labelledby="phw-title">
      <div className="pc-sheet-head">
        <h2 className="pc-h2" id="phw-title">{t('w_title')}</h2>
        <button type="button" className="pc-icon-btn" onClick={onClose} aria-label={t('w_close')}><CloseIcon /></button>
      </div>
      <p className="pc-muted">{t('w_sub')}</p>

      <form className="pc-search" onSubmit={(e) => { e.preventDefault(); lookup(); }}>
        <label className="ph-sr-only" htmlFor="phw-serial">{t('w_label')}</label>
        <input
          id="phw-serial"
          ref={serialRef}
          className="pc-input"
          type="text"
          autoComplete="off"
          spellCheck={false}
          value={code}
          onChange={(e) => setCode(e.target.value.toUpperCase())}
          placeholder={t('w_ph')}
          aria-describedby="phw-hint"
        />
        <button type="submit" className="pc-btn-outline" disabled={loading}>
          {loading ? <span className="ph-spinner" aria-hidden="true" /> : <ShieldIcon />}
          <span>{loading ? t('w_checking') : t('w_btn')}</span>
        </button>
      </form>
      <p className="pc-hint" id="phw-hint">{t('w_hint')}</p>

      <div aria-live="polite" ref={resultRef} tabIndex={-1} className="ph-result-region" aria-label={t('w_region')}>
        {error && <div className="ph-alert ph-alert-danger">{error}</div>}
        {!error && searched && !data && !loading && <div className="ph-alert ph-alert-warn">{t('w_not_found')}</div>}

        {data && (
          <div className={`phw-result phw-${tone}`}>
            <div className="phw-result-head">
              <span className={`phw-status phw-status-${tone}`}>
                <span className="phw-status-dot" aria-hidden="true" />
                {statusLabel}
              </span>
              <span className="phw-days">{daysText}</span>
            </div>
            <div className="phw-device">
              <strong className="phw-device-name">{data.device_label || data.device_type || data.device_id || t('m_device')}</strong>
              <span className="phw-device-sub">{[data.brand, data.model].filter(Boolean).join(' ') || t('w_nobrand')}</span>
            </div>
            <div className="phw-grid">
              <MetaItem label={t('w_serial')} value={data.serial_number || t('w_none')} />
              <MetaItem label={t('w_device_id')} value={data.device_id || '-'} />
              <MetaItem label={t('w_bought')} value={fmtDate(data.purchase_date, locale)} />
              <MetaItem label={t('w_until')} value={fmtDate(data.warranty_until, locale)} />
              <MetaItem label={t('w_room')} value={data.room_name || t('w_none')} />
              <MetaItem label={t('w_org')} value={data.organization_name || '-'} />
            </div>
            <p className="phw-note">
              {data.has_open_ticket && openTicketNo
                ? t('w_open', { no: openTicketNo })
                : status === 'expired'
                  ? t('w_note_expired')
                  : status === 'unknown'
                    ? t('w_note_unknown')
                    : t('w_note_ok')}
            </p>
            <a className="phw-cta" href="/?publicreport=1">{t('w_report')} <ArrowIcon /></a>
          </div>
        )}
      </div>
    </section>
  );
}

function UserIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" aria-hidden="true">
      <circle cx="12" cy="8" r="4" />
      <path d="M4 21a8 8 0 0116 0" />
    </svg>
  );
}

/**
 * หน้าแรกสาธารณะ (ไม่ต้องเข้าสู่ระบบ)
 * ซ้าย: หัวเรื่อง + ปุ่มแจ้งซ่อม/สแกน QR + ติดตามงานซ่อม
 * ขวา: ผู้ช่วย AI ฝังในหน้า (ถามอาการเบื้องต้นก่อนแจ้งซ่อม)
 * ล่าง: ตรวจสอบประกัน / สอบถามสินค้า, ขั้นตอน, คำถามที่พบบ่อย
 * ทางเข้าเจ้าหน้าที่อยู่ที่ท้ายหน้า (แถบบนเป็นปุ่มเปลี่ยนภาษาแทน)
 */
export default function PublicHomeView({ initialTicketId, staffLoggedIn = false }: { initialTicketId?: string; staffLoggedIn?: boolean }) {
  const { t, locale } = useLang();
  const [input, setInput] = useState((initialTicketId || '').toUpperCase());
  const [ticket, setTicket] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [recent, setRecent] = useState<string[]>(() => loadRecent());
  /** สถานะของงานที่เครื่องนี้จำไว้ — null = โหลดไม่สำเร็จ (ยังแสดงเป็นปุ่มเลขใบงานแทน) */
  const [mine, setMine] = useState<PublicTicketStatus[] | null>([]);
  const [lastChecked, setLastChecked] = useState<Date | null>(null);
  const [copied, setCopied] = useState(false);
  const [showWarranty, setShowWarranty] = useState(false);

  const inputRef = useRef<HTMLInputElement | null>(null);
  const trackRef = useRef<HTMLDivElement | null>(null);
  const autoRan = useRef(false);
  const resultRef = useRef<HTMLDivElement | null>(null);
  const [revealTick, setRevealTick] = useState(0);
  useRevealResult(resultRef, revealTick);

  const search = useCallback(
    async (raw?: string, opts: { quiet?: boolean } = {}) => {
      let no = (raw ?? input).replace(/\s+/g, '').toUpperCase();
      if (!no) {
        setError(t('err_empty'));
        setTicket(null);
        setSearched(false);
        inputRef.current?.focus();
        return;
      }
      if (!opts.quiet) setInput(no); // รีเฟรชเบื้องหลังต้องไม่ทับสิ่งที่ผู้ใช้กำลังพิมพ์
      if (!opts.quiet) {
        setLoading(true);
        setError(null);
        setTicket(null);
        setSearched(false);
        setCopied(false);
      }
      try {
        // ไม่ใช่เลขใบงาน → ถือเป็นรหัสอุปกรณ์ แล้วเปิดใบงานล่าสุดของเครื่องนั้น
        if (!looksLikeTicketNo(no)) {
          let found: any;
          try {
            found = await api.getDeviceRecent(no);
          } catch {
            throw new Error(t('err_not_found', { no }));
          }
          if (!found?.recent_ticket?.ticket_id) throw new Error(t('err_no_ticket', { no }));
          no = String(found.recent_ticket.ticket_id).toUpperCase();
          setInput(no);
        }
        const r: any = await api.trackTicket(no);
        setLastChecked(new Date());
        setTicket(r);
        // endpoint สาธารณะคืนคีย์ ticket_no (ส่วน endpoint ที่ต้องล็อกอินคืน ticket_id)
        const resolvedNo: string = r?.ticket_no || r?.ticket_id || no;
        if (!opts.quiet) setRecent(saveRecent(resolvedNo));
        try {
          window.history.replaceState({}, '', `/?ticket=${encodeURIComponent(resolvedNo)}`);
        } catch {
          // บางเบราว์เซอร์ในโหมดจำกัดสิทธิ์เขียน history ไม่ได้ — ข้ามไป
        }
      } catch (err: any) {
        if (!opts.quiet) setError(err?.message || t('err_generic'));
      } finally {
        setLoading(false);
        setSearched(true);
        if (!opts.quiet) setRevealTick((n) => n + 1);
      }
    },
    [input, t],
  );

  // ── งานที่ฉันแจ้งไว้: สถานะล่าสุดของทุกเลขที่เครื่องนี้จำไว้ (คำขอเดียว) ──
  useEffect(() => {
    if (!recent.length) { setMine([]); return; }
    let alive = true;
    api.publicTicketStatuses(recent)
      .then((rows) => { if (alive) setMine(rows); })
      .catch(() => { if (alive) setMine(null); });
    return () => { alive = false; };
  }, [recent, ticket?.status]);

  // ── ใบงานที่เปิดอยู่และยังไม่จบ: อัปเดตเองทุก 60 วินาที (เฉพาะตอนเปิดหน้าอยู่) ──
  const openNo: string | undefined = ticket?.ticket_no || ticket?.ticket_id;
  const openFinished = FINISHED.has(ticket?.status);
  useEffect(() => {
    if (!openNo || openFinished) return;
    const id = window.setInterval(() => {
      if (document.visibilityState === 'visible') void search(openNo, { quiet: true });
    }, LIVE_REFRESH_MS);
    return () => window.clearInterval(id);
  }, [openNo, openFinished, search]);

  useEffect(() => {
    if (initialTicketId && !autoRan.current) {
      autoRan.current = true;
      search(initialTicketId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialTicketId]);

  const copyLink = async () => {
    const no = ticket?.ticket_no || ticket?.ticket_id || input;
    if (!no) return;
    const url = `${window.location.origin}/?ticket=${encodeURIComponent(no)}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError(t('copy_fail'));
    }
  };

  const stepIndex = useMemo(() => {
    if (!ticket?.status) return -1;
    const idx = STEP_INDEX[ticket.status];
    return typeof idx === 'number' ? idx : 0;
  }, [ticket]);

  const cancelled = ticket?.status === 'cancelled';
  const ticketNo: string = ticket?.ticket_no || ticket?.ticket_id || input;
  /** ข้อมูลอุปกรณ์ — endpoint สาธารณะคืนฟิลด์แบบแบน ส่วน endpoint ที่ต้องล็อกอินคืน device_info ซ้อนอยู่ */
  const dev = useMemo<Record<string, any> | null>(() => {
    if (!ticket) return null;
    if (ticket.device_info) return ticket.device_info as Record<string, any>;
    const code = ticket.device_code ?? ticket.device_id ?? null;
    if (!code && !ticket.device_type && !ticket.room_name) return null;
    return {
      device_id: code,
      device_type: ticket.device_type ?? null,
      device_label: ticket.device_label ?? null,
      brand: null,
      model: null,
      room_name: ticket.room_name ?? null,
      organization_name: ticket.organization_name ?? null,
    };
  }, [ticket]);
  const history: any[] = Array.isArray(ticket?.history) ? ticket.history : [];
  const times = useMemo(() => stepTimes(history), [ticket]);
  const subNote = ticket?.status && ['pending', 'waiting_parts', 'waiting_user'].includes(ticket.status) ? t(`sub_${ticket.status}`) : undefined;
  const progressPct = stepIndex < 0 ? 0 : Math.min(100, Math.round((stepIndex / (STEP_KEYS.length - 1)) * 100));
  const priorityText = ticket?.priority && KNOWN_PRIORITY.has(ticket.priority) ? t(`pr_${ticket.priority}`) : (ticket?.priority || t('pr_normal'));

  return (
    <div className="ph-page pc-home">
      <header className="ph-topbar pc-topbar">
        <a className="ph-brand" href={staffLoggedIn ? '/' : '/?home=1'}>
          <img className="pc-logo" src="/logo.jpg" alt="IWA" width="36" height="36" />
          <span className="ph-brand-text">
            <strong>IWA Smart Classroom Support</strong>
            <small>{t('brand_sub')}</small>
          </span>
        </a>
        <div className="ph-topbar-right">
          <LanguageSwitcher />
          <ThemeModeButton />
        </div>
      </header>

      <main className="ph-main pc-main">
        <div className="pc-left">
          <section className="pc-hero" aria-labelledby="pc-title">
            <h1 className="pc-title" id="pc-title">{t('title1')}<br /><span className="pc-title-accent">{t('title2')}</span></h1>
            <p className="pc-lead">{t('lead')}</p>
            <div className="pc-cta-row">
              <a href="/?publicreport=1" className="pc-cta">
                <ScanIcon />
                <span>{t('cta')}</span>
              </a>
              <span className="pc-cta-note">{t('cta_note')}</span>
            </div>
          </section>

          <section className="pc-track" ref={trackRef} aria-labelledby="ph-track-title">
            <h2 className="pc-h2" id="ph-track-title">{t('track_title')}</h2>
            <p className="pc-muted">{t('track_sub')}</p>

            <form className="pc-search" onSubmit={(e) => { e.preventDefault(); search(); }}>
              <label className="ph-sr-only" htmlFor="ph-ticket-input">{t('track_label')}</label>
              <input
                id="ph-ticket-input"
                ref={inputRef}
                className="pc-input"
                type="text"
                autoComplete="off"
                spellCheck={false}
                value={input}
                onChange={(e) => setInput(e.target.value.toUpperCase())}
                placeholder={t('track_ph')}
                aria-describedby="ph-ticket-hint"
              />
              <button type="submit" className="pc-btn-outline" disabled={loading}>
                {loading ? <span className="ph-spinner" aria-hidden="true" /> : <SearchIcon />}
                <span>{loading ? t('searching') : t('track_btn')}</span>
              </button>
            </form>
            <p className="pc-hint" id="ph-ticket-hint">
              {t('example')} <span className="pc-mono">TK.SCHM01.26.0001-T</span>
            </p>

            {recent.length > 0 && (
              <div className="ph-mine" aria-labelledby="ph-mine-title">
                <h3 className="ph-mine-title" id="ph-mine-title">{t('mine_title')} <small>{t('mine_saved')}</small></h3>
                {mine && mine.length > 0 ? (
                  <ul className="ph-mine-list">
                    {mine.map((m) => (
                      <li key={m.ticket_no} className={m.ticket_no === openNo ? 'is-open' : ''}>
                        <button type="button" className="ph-mine-row" onClick={() => search(m.ticket_no)} disabled={loading}
                          aria-label={t('view_ticket', { no: m.ticket_no })}>
                          <span className={`badge badge-${m.status} ph-mine-badge`}>{statusText(m.status, m.status_label, t)}</span>
                          <span className="ph-mine-body">
                            <strong>{m.title}</strong>
                            <small>{m.device_label} · {t('updated')} {sinceText(m.updated_at, t) || shortTime(m.updated_at, locale)}</small>
                          </span>
                          <span className="ph-mine-no">{m.ticket_no}</span>
                        </button>
                        <button type="button" className="ph-mine-forget" aria-label={t('remove_ticket', { no: m.ticket_no })}
                          onClick={() => setRecent(forgetRecent(m.ticket_no))}><CloseIcon /></button>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <div className="ph-recent">
                    {recent.map((no) => (
                      <button key={no} type="button" className="ph-chip" onClick={() => search(no)} disabled={loading}>{no}</button>
                    ))}
                  </div>
                )}
              </div>
            )}

            <div aria-live="polite" ref={resultRef} tabIndex={-1} className="ph-result-region" aria-label={t('result_region')}>
              {error && <div className="ph-alert ph-alert-danger">{error}</div>}
              {!error && searched && !ticket && !loading && <div className="ph-alert ph-alert-warn">{t('not_found_warn')}</div>}

              {ticket && (
                <div className="ph-result">
                  <div className="ph-result-head">
                    <div className="ph-result-no">
                      <span className="ph-result-no-label">{t('ticket_no')}</span>
                      <strong>{ticketNo}</strong>
                    </div>
                    <span className={`badge badge-${ticket.status} ph-status-badge`}>{statusLabelOf(ticket, t)}</span>
                  </div>

                  {ticket.title && <p className="ph-result-title">{ticket.title}</p>}

                  {cancelled ? (
                    <div className="ph-alert ph-alert-danger">{t('cancelled')}</div>
                  ) : (
                    <>
                      <div className="ph-progress" aria-hidden="true">
                        <span className="ph-progress-fill" style={{ width: `${progressPct}%` }} />
                      </div>
                      <ol className="ph-steps" aria-label={t('progress')}>
                        {STEP_KEYS.map((key, i) => {
                          const done = i < stepIndex;
                          const current = i === stepIndex;
                          return (
                            <li key={key} className={`ph-step${done ? ' is-done' : ''}${current ? ' is-current' : ''}`} aria-current={current ? 'step' : undefined}>
                              <span className="ph-step-dot">{done ? <CheckIcon /> : i + 1}</span>
                              <span className="ph-step-label">{t(`step_${key}`)}</span>
                              {times[i] && (done || current) && (
                                <time className="ph-step-time" dateTime={times[i]}>{shortTime(times[i], locale)}</time>
                              )}
                            </li>
                          );
                        })}
                      </ol>
                      {subNote && <div className="ph-alert ph-alert-info">{subNote}</div>}
                      {ticket.finding_technician && <div className="ph-alert ph-alert-info">{t('finding_tech')}</div>}
                    </>
                  )}

                  <div className="ph-meta-grid">
                    <MetaItem
                      label={t('m_device')}
                      value={<>{dev?.device_label || dev?.device_type || t('m_device')}{dev?.brand ? ` · ${dev.brand}` : ''}{dev?.model ? ` ${dev.model}` : ''}</>}
                      sub={dev?.device_id || ticket.device_code || ticket.device_id || '-'}
                    />
                    <MetaItem label={t('m_place')} value={dev?.room_name || '-'} sub={dev?.organization_name || undefined} />
                    {ticket.technician && <MetaItem label={t('m_tech')} value={ticket.technician} />}
                    <MetaItem label={t('m_priority')} value={priorityText} />
                    <MetaItem label={t('m_reported')} value={fmtDateTime(ticket.created_at, locale)} sub={sinceText(ticket.created_at, t) || undefined} />
                    {ticket.estimated_completion && !ticket.closed_at && (
                      <MetaItem label={t('m_sla')} value={fmtDateTime(ticket.estimated_completion, locale)} />
                    )}
                    {ticket.closed_at && (
                      <MetaItem label={t('m_closed')} value={fmtDateTime(ticket.closed_at, locale)} sub={sinceText(ticket.closed_at, t) || undefined} />
                    )}
                  </div>

                  <h3 className="ph-sub-title">{t('history')}</h3>
                  {history.length > 0 ? (
                    <ul className="ph-timeline">
                      {history.map((h: any, i: number) => {
                        const code = h.to_status || h.status;
                        return (
                          <li className="ph-timeline-item" key={`${h.created_at || i}-${i}`}>
                            <span className="ph-timeline-dot" aria-hidden="true" />
                            <div className="ph-timeline-body">
                              <div className="ph-timeline-status">{KNOWN_STATUS.has(code) ? t(`st_${code}`) : (h.label || code || t('history_update'))}</div>
                              {h.note && <div className="ph-timeline-note">{h.note}</div>}
                              <div className="ph-timeline-time">{fmtDateTime(h.created_at, locale)}{h.author_name ? ` · ${h.author_name}` : ''}</div>
                            </div>
                          </li>
                        );
                      })}
                    </ul>
                  ) : (
                    <p className="ph-empty">{t('history_empty')}</p>
                  )}

                  {ticket.resolution_notes && (
                    <div className="ph-alert ph-alert-success"><strong>{t('resolution')}</strong> {ticket.resolution_notes}</div>
                  )}

                  <div className="ph-result-actions">
                    <button type="button" className="ph-btn" onClick={() => search(ticketNo)} disabled={loading}>
                      <RefreshIcon /><span>{t('refresh')}</span>
                    </button>
                    {lastChecked && (
                      <span className="ph-last-checked" role="status">
                        {t('last_updated', { time: lastChecked.toLocaleTimeString(locale, { hour: '2-digit', minute: '2-digit' }) })}
                        {!FINISHED.has(ticket.status) && t('auto_refresh')}
                      </span>
                    )}
                    <button type="button" className="ph-btn" onClick={copyLink}>
                      <LinkIcon /><span>{copied ? t('copied') : t('copy_link')}</span>
                    </button>
                    <a className="ph-btn" href="/?publicreport=1"><PlusIcon /><span>{t('report_other')}</span></a>
                  </div>
                </div>
              )}
            </div>
          </section>
        </div>

        <div className="pc-right">
          <AIChatWidget embedded />
        </div>

        <nav className="pc-links" aria-label={t('more_links')}>
          <button type="button" className="pc-link-cell" onClick={() => setShowWarranty((v) => !v)} aria-expanded={showWarranty} aria-controls="ph-warranty">
            <span className="pc-link-icon" aria-hidden="true"><ShieldIcon /></span>
            <span className="pc-link-text"><strong>{t('warranty')}</strong><small>{t('warranty_sub')}</small></span>
            <ArrowIcon />
          </button>
          <a className="pc-link-cell" href="/?customer=1">
            <span className="pc-link-icon" aria-hidden="true"><HeadsetIcon /></span>
            <span className="pc-link-text"><strong>{t('inquiry')}</strong><small>{t('inquiry_sub')}</small></span>
            <ArrowIcon />
          </a>
        </nav>

        {showWarranty && <WarrantyCard onClose={() => setShowWarranty(false)} />}

        <section className="pc-flow" aria-labelledby="pc-flow-title">
          <h2 className="pc-h3" id="pc-flow-title">{t('flow_title')}</h2>
          <ol>
            <li><b>1</b><span>{t('flow1')}</span></li>
            <li><b>2</b><span>{t('flow2')}</span></li>
            <li><b>3</b><span>{t('flow3')}</span></li>
          </ol>
        </section>

        <section className="pc-faq" aria-labelledby="pc-faq-title">
          <h2 className="pc-h3" id="pc-faq-title">{t('faq_title')}</h2>
          <details><summary>{t('faq1q')}</summary><p>{t('faq1a')}</p></details>
          <details><summary>{t('faq2q')}</summary><p>{t('faq2a')}</p></details>
          <details><summary>{t('faq3q')}</summary><p>{t('faq3a')}</p></details>
        </section>
      </main>

      <footer className="pc-footer">
        <span>{t('footer_company')}</span>
        <nav aria-label={t('more_links')}>
          <a href={staffLoggedIn ? '/' : '/?login=1'}><UserIcon />{t('footer_staff')}</a>
          <a href="/?register=1">{t('footer_register')}</a>
          <a href="/?privacy=1">{t('footer_privacy')}</a>
        </nav>
      </footer>
    </div>
  );
}
