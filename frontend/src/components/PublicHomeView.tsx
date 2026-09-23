import React, { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { api } from '../api/client';
import '../styles/public-home.css';
// เลเยอร์ธีม: ผูก --ph-* เข้ากับ token กลาง จึงต้องมาหลัง public-home.css
import '../styles/public-theme.css';
// การ์ดตรวจสอบประกัน — ใช้ตัวแปร --ph-* จึงต้องมาหลังไฟล์ธีมข้างบน
import '../styles/public-warranty.css';
// เลเยอร์ยกระดับดีไซน์ (glassmorphism + neon) — ต้องโหลดท้ายสุดเพื่อทับของเดิม
import '../styles/public-premium.css';
import '../styles/public-refresh.css';
import PublicThemeToggle from './PublicThemeToggle';

/** ป้ายสถานะภาษาไทย — ใช้ชุดเดียวกับหน้าอื่น เพื่อไม่ให้ผู้แจ้งเห็นคำเรียกต่างกัน */
const STATUS_LABELS: Record<string, string> = {
  new: 'รอรับเรื่อง',
  assigned: 'มอบหมายช่างแล้ว',
  in_progress: 'กำลังดำเนินการ',
  pending: 'รออะไหล่ / รอภายนอก',
  waiting_parts: 'รออะไหล่',
  waiting_user: 'รอข้อมูลจากผู้แจ้ง',
  resolved: 'ซ่อมเสร็จ รอยืนยัน',
  closed: 'ปิดงานแล้ว',
  cancelled: 'ยกเลิก',
};

const PRIORITY_LABELS: Record<string, string> = {
  critical: 'เร่งด่วนมาก',
  high: 'เร่งด่วน',
  normal: 'ปกติ',
  low: 'ไม่เร่งด่วน',
};

/** ขั้นตอนหลักที่ผู้แจ้งเข้าใจได้ — สถานะย่อย (รออะไหล่/รอผู้ใช้) นับอยู่ในขั้น "กำลังซ่อม" */
const STEPS: { key: string; label: string }[] = [
  { key: 'new', label: 'รับเรื่อง' },
  { key: 'assigned', label: 'มอบหมายช่าง' },
  { key: 'in_progress', label: 'กำลังซ่อม' },
  { key: 'resolved', label: 'ซ่อมเสร็จ' },
  { key: 'closed', label: 'ปิดงาน' },
];

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

/** สถานะย่อยที่ต้องอธิบายเพิ่ม เพราะ stepper แสดงเป็น "กำลังซ่อม" เหมือนกันหมด */
const SUB_STATUS_NOTE: Record<string, string> = {
  pending: 'งานหยุดรออะไหล่หรือรอผู้ให้บริการภายนอก เจ้าหน้าที่จะดำเนินการต่อทันทีที่พร้อม',
  waiting_parts: 'รออะไหล่เข้า — เมื่ออะไหล่มาถึงจะกลับมาซ่อมต่อ',
  waiting_user: 'รอข้อมูลเพิ่มจากผู้แจ้ง กรุณาติดต่อเจ้าหน้าที่หรือแจ้งอาการเพิ่มเติม',
};

const RECENT_KEY = 'sc_recent_tickets';

function loadRecent(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(arr)) return [];
    return arr.filter((x): x is string => typeof x === 'string' && x.trim() !== '').slice(0, 6);
  } catch {
    return [];
  }
}

function saveRecent(no: string): string[] {
  const clean = no.trim().toUpperCase();
  if (!clean) return loadRecent();
  const next = [clean, ...loadRecent().filter((x) => x !== clean)].slice(0, 6);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // โหมดส่วนตัว/พื้นที่เต็ม — จำไม่ได้ก็ไม่เป็นไร ไม่ต้องขัดจังหวะผู้ใช้
  }
  return next;
}

function fmtDateTime(v?: string | null): string {
  if (!v) return '-';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleString('th-TH', { dateStyle: 'medium', timeStyle: 'short' });
}

/** ระยะเวลาตั้งแต่แจ้ง — ช่วยให้ผู้แจ้งเห็นว่าเรื่องค้างมานานเท่าไหร่ */
function sinceText(v?: string | null): string {
  if (!v) return '';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return '';
  const mins = Math.floor((Date.now() - d.getTime()) / 60000);
  if (mins < 0) return '';
  if (mins < 60) return `${mins} นาทีที่ผ่านมา`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs} ชั่วโมงที่ผ่านมา`;
  const days = Math.floor(hrs / 24);
  return `${days} วันที่ผ่านมา`;
}

function statusLabelOf(t: any): string {
  if (!t) return '';
  return STATUS_LABELS[t.status] || t.status_label || t.status || '';
}

// ─── Icons ───────────────────────────────────────────────────────────────────

function ScanIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
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

function PulseIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M3 12h4l2.5-7 3 14L15 12h6" />
    </svg>
  );
}

function ShieldIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden="true">
      <path d="M12 3l7 3v5.5c0 4.4-2.9 8.2-7 9.5-4.1-1.3-7-5.1-7-9.5V6l7-3z" />
      <path d="M9.5 12.2l1.9 1.9 3.6-3.7" />
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
    <svg className="ph-action-arrow" width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}

// ─── ส่วนประกอบย่อยที่ใช้ซ้ำ ────────────────────────────────────────────────

/** จุดเรืองแสงบอกว่าระบบพร้อมรับเรื่อง — ใช้ในแถบบนและใน hero */
function LivePill({ children }: { children: React.ReactNode }) {
  return (
    <span className="ph-live">
      <span className="ph-live-dot" aria-hidden="true" />
      {children}
    </span>
  );
}

interface HighlightItem {
  icon: React.ReactNode;
  title: string;
  desc: string;
}

/** จุดเด่นของระบบ — เนื้อหาอธิบายความสามารถจริงของหน้านี้ ไม่ใช่ตัวเลขสมมติ */
const HIGHLIGHTS: HighlightItem[] = [
  {
    icon: <ScanIcon />,
    title: 'แจ้งซ่อมด้วย QR',
    desc: 'สแกนสติกเกอร์ที่ตัวอุปกรณ์ ระบบดึงรหัสเครื่องและห้องให้อัตโนมัติ',
  },
  {
    icon: <PulseIcon />,
    title: 'ติดตามได้ทุกขั้นตอน',
    desc: 'เห็นความคืบหน้าจากรับเรื่องถึงปิดงาน พร้อมประวัติการดำเนินการ',
  },
  {
    icon: <ShieldIcon />,
    title: 'ไม่ต้องสร้างบัญชี',
    desc: 'ผู้แจ้งใช้เพียงเลขใบงาน ข้อมูลเจ้าหน้าที่แยกอยู่หลังระบบล็อกอิน',
  },
];

function HighlightCard({ item }: { item: HighlightItem }) {
  return (
    <li className="ph-highlight">
      <span className="ph-highlight-icon" aria-hidden="true">{item.icon}</span>
      <strong className="ph-highlight-title">{item.title}</strong>
      <span className="ph-highlight-desc">{item.desc}</span>
    </li>
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
 * หน้าแรกสาธารณะ (ไม่ต้องเข้าสู่ระบบ)
 * - ติดตามสถานะใบงานด้วยเลข Ticket: แถบความคืบหน้า + ข้อมูลอุปกรณ์ + ไทม์ไลน์
 * - ทางเข้าแจ้งซ่อม/สแกน QR
 * - หน้าเข้าสู่ระบบเจ้าหน้าที่แยกไปที่ /?login=1
 */
/** สถานะประกัน -> ป้าย + โทนสีของการ์ดผลลัพธ์ */
const WARRANTY_TONE: Record<string, { label: string; tone: 'ok' | 'warn' | 'danger' | 'muted' }> = {
  active: { label: 'อยู่ในระยะประกัน', tone: 'ok' },
  expiring: { label: 'ใกล้หมดประกัน', tone: 'warn' },
  expired: { label: 'หมดประกันแล้ว', tone: 'danger' },
  unknown: { label: 'ไม่มีข้อมูลประกัน', tone: 'muted' },
};

/** วันที่แบบไม่มีเวลา — ข้อมูลประกันเป็นระดับวัน เวลาไม่มีความหมายกับผู้ใช้ */
function fmtDate(v?: string | null): string {
  if (!v) return '-';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleDateString('th-TH', { dateStyle: 'medium' });
}

/**
 * การ์ด "ตรวจสอบประกันสินค้า" — กรอกหมายเลขสินค้าของเครื่องที่ซื้อไปแล้ว
 * แล้วดูสถานะประกันได้เอง ไม่ต้องล็อกอินและไม่ต้องมีเลขใบงาน
 * (endpoint รับรหัสอุปกรณ์ของโรงเรียนและ QR token ได้ด้วย)
 */
function WarrantyCard() {
  const [code, setCode] = useState('');
  const [data, setData] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const serialRef = useRef<HTMLInputElement | null>(null);

  const lookup = useCallback(
    async (raw?: string) => {
      const q = (raw ?? code).trim();
      if (!q) {
        setError('กรุณากรอกหมายเลขสินค้า (Serial Number) ที่อยู่บนตัวเครื่อง');
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
        const r: any = await api.checkWarranty(q);
        setData(r);
      } catch (err: any) {
        setError(err?.message || 'ไม่พบหมายเลขสินค้านี้ในระบบ');
      } finally {
        setLoading(false);
        setSearched(true);
      }
    },
    [code],
  );

  const status: string = typeof data?.warranty_status === 'string' ? data.warranty_status : 'unknown';
  const tone = WARRANTY_TONE[status] ?? WARRANTY_TONE.unknown;
  const daysLeft: number | null = typeof data?.days_left === 'number' ? data.days_left : null;

  const daysText = useMemo(() => {
    if (!data) return '';
    if (daysLeft === null) return 'ยังไม่บันทึกวันสิ้นสุดประกันของเครื่องนี้';
    if (daysLeft < 0) return `หมดประกันมาแล้ว ${Math.abs(daysLeft)} วัน`;
    if (daysLeft === 0) return 'ประกันหมดวันนี้';
    return `เหลือเวลาประกันอีก ${daysLeft} วัน`;
  }, [data, daysLeft]);

  const openTicket = data?.open_ticket ?? null;
  const openTicketNo: string = openTicket?.ticket_id || openTicket?.ticket_no || '';

  return (
    <section className="ph-card phw-card" id="ph-warranty" aria-labelledby="phw-title">
      <div className="ph-card-head">
        <h2 className="ph-card-title" id="phw-title">ตรวจสอบประกันสินค้า</h2>
        <span className="ph-card-tag">WARRANTY CHECK</span>
      </div>

      <p className="phw-lead">
        กรอกหมายเลขสินค้าของอุปกรณ์ที่ซื้อไปแล้ว เพื่อดูว่ายังอยู่ในระยะประกันหรือไม่
        ตรวจได้เองบนเว็บ ไม่ต้องเข้าสู่ระบบและไม่ต้องมีเลขใบงาน
      </p>

      <form
        className="phw-form"
        onSubmit={(e) => {
          e.preventDefault();
          lookup();
        }}
      >
        <label className="ph-sr-only" htmlFor="phw-serial">หมายเลขสินค้า</label>
        <div className="ph-input-wrap">
          <span className="ph-input-icon" aria-hidden="true"><ShieldIcon /></span>
          <input
            id="phw-serial"
            ref={serialRef}
            className="ph-input"
            type="text"
            inputMode="text"
            autoComplete="off"
            spellCheck={false}
            value={code}
            onChange={(e) => setCode(e.target.value.toUpperCase())}
            placeholder="เช่น BE2417-8C3D1A"
            aria-describedby="phw-hint"
          />
        </div>
        <button type="submit" className="ph-btn ph-btn-primary" disabled={loading || !code.trim()}>
          {loading ? <span className="ph-spinner" aria-hidden="true" /> : <ShieldIcon />}
          <span>{loading ? 'กำลังตรวจสอบ' : 'ตรวจสอบประกัน'}</span>
        </button>
      </form>
      <p className="ph-hint" id="phw-hint">
        หมายเลขสินค้าอยู่บนสติกเกอร์ใต้ตัวเครื่องหรือด้านหลังจอ — พิมพ์รหัสอุปกรณ์ของโรงเรียน
        (เช่น <code>SCHM01-B1-R101-DISP-01</code>) ก็ค้นได้เหมือนกัน
      </p>

      <div aria-live="polite">
        {error && <div className="ph-alert ph-alert-danger">{error}</div>}

        {!error && searched && !data && !loading && (
          <div className="ph-alert ph-alert-warn">
            ไม่พบหมายเลขนี้ในระบบ — ลองตรวจตัวอักษรที่สับสนกันบ่อย (O กับ 0, I กับ 1) อีกครั้ง
          </div>
        )}

        {data && (
          <div className={`phw-result phw-${tone.tone}`}>
            <div className="phw-result-head">
              <span className={`phw-status phw-status-${tone.tone}`}>
                <span className="phw-status-dot" aria-hidden="true" />
                {data.warranty_status_label || tone.label}
              </span>
              <span className="phw-days">{daysText}</span>
            </div>

            <div className="phw-device">
              <strong className="phw-device-name">
                {data.device_label || data.device_type || data.device_id || 'อุปกรณ์'}
              </strong>
              <span className="phw-device-sub">
                {[data.brand, data.model].filter(Boolean).join(' ') || 'ไม่ระบุยี่ห้อ/รุ่น'}
              </span>
            </div>

            <div className="phw-grid">
              <MetaItem label="หมายเลขสินค้า" value={data.serial_number || 'ไม่ระบุ'} />
              <MetaItem label="รหัสอุปกรณ์" value={data.device_id || '-'} />
              <MetaItem label="วันที่ซื้อ" value={fmtDate(data.purchase_date)} />
              <MetaItem label="ประกันสิ้นสุด" value={fmtDate(data.warranty_until)} />
              <MetaItem label="ติดตั้งที่ห้อง" value={data.room_name || 'ไม่ระบุ'} />
              <MetaItem label="หน่วยงาน" value={data.organization_name || '-'} />
            </div>

            {data.has_open_ticket && openTicketNo ? (
              <p className="phw-note">
                เครื่องนี้มีงานซ่อมค้างอยู่แล้ว — เลขใบงาน <code>{openTicketNo}</code>
                {openTicket?.status ? ` สถานะ ${STATUS_LABELS[openTicket.status] || openTicket.status}` : ''}
                {' '}ไม่ต้องแจ้งซ้ำ ใช้เลขนี้ติดตามสถานะได้เลย
              </p>
            ) : (
              <p className="phw-note">
                {status === 'expired'
                  ? 'อุปกรณ์หมดประกันแล้ว ค่าซ่อมจะอยู่ในความรับผิดชอบของโรงเรียน แต่ยังแจ้งซ่อมได้ตามปกติ'
                  : status === 'unknown'
                    ? 'ระบบยังไม่มีวันสิ้นสุดประกันของเครื่องนี้ กรุณาแจ้งเจ้าหน้าที่เพื่อบันทึกข้อมูลจากใบเสร็จ'
                    : 'ถ้าอุปกรณ์มีปัญหา แจ้งซ่อมได้ทันที เจ้าหน้าที่จะตรวจสอบสิทธิ์ประกันกับผู้ขายให้อีกครั้ง'}
              </p>
            )}

            <a className="phw-cta" href="/?publicreport=1">
              แจ้งซ่อมอุปกรณ์
              <ArrowIcon />
            </a>
          </div>
        )}
      </div>
    </section>
  );
}

export default function PublicHomeView({ initialTicketId }: { initialTicketId?: string }) {
  const [input, setInput] = useState((initialTicketId || '').toUpperCase());
  const [ticket, setTicket] = useState<any | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  const [recent, setRecent] = useState<string[]>(() => loadRecent());
  const [copied, setCopied] = useState(false);

  const inputRef = useRef<HTMLInputElement | null>(null);
  const trackRef = useRef<HTMLDivElement | null>(null);
  const autoRan = useRef(false);

  const search = useCallback(
    async (raw?: string) => {
      const no = (raw ?? input).replace(/\s+/g, '').toUpperCase();
      if (!no) {
        setError('กรุณากรอกเลขใบงาน เช่น TK.SCHM01.26.0001-T');
        setTicket(null);
        setSearched(false);
        return;
      }
      setInput(no);
      setLoading(true);
      setError(null);
      setTicket(null);
      setSearched(false);
      setCopied(false);
      try {
        const r: any = await api.trackTicket(no);
        setTicket(r);
        // endpoint สาธารณะคืนคีย์ ticket_no (ส่วน endpoint ที่ต้องล็อกอินคืน ticket_id)
        const resolvedNo: string = r?.ticket_no || r?.ticket_id || no;
        setRecent(saveRecent(resolvedNo));
        // ให้ลิงก์แชร์/กดรีเฟรชแล้วยังอยู่ที่ใบงานเดิม
        try {
          window.history.replaceState({}, '', `/?ticket=${encodeURIComponent(resolvedNo)}`);
        } catch {
          // บางเบราว์เซอร์ในโหมดจำกัดสิทธิ์เขียน history ไม่ได้ — ข้ามไป
        }
      } catch (err: any) {
        setError(err?.message || 'ไม่พบเลขใบงานนี้ในระบบ');
      } finally {
        setLoading(false);
        setSearched(true);
      }
    },
    [input],
  );

  useEffect(() => {
    if (initialTicketId && !autoRan.current) {
      autoRan.current = true;
      search(initialTicketId);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [initialTicketId]);

  const focusTrack = () => {
    trackRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    setTimeout(() => inputRef.current?.focus(), 250);
  };

  const copyLink = async () => {
    const no = ticket?.ticket_no || ticket?.ticket_id || input;
    if (!no) return;
    const url = `${window.location.origin}/?ticket=${encodeURIComponent(no)}`;
    try {
      await navigator.clipboard.writeText(url);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      setError('คัดลอกลิงก์ไม่ได้ — กรุณาคัดลอกจากแถบที่อยู่เว็บ');
    }
  };

  const stepIndex = useMemo(() => {
    if (!ticket?.status) return -1;
    const idx = STEP_INDEX[ticket.status];
    return typeof idx === 'number' ? idx : 0;
  }, [ticket]);

  const cancelled = ticket?.status === 'cancelled';
  /** เลขใบงาน — /tickets/track คืน ticket_no, /tickets/{id} คืน ticket_id */
  const ticketNo: string = ticket?.ticket_no || ticket?.ticket_id || input;
  /** ข้อมูลอุปกรณ์ — endpoint สาธารณะคืนฟิลด์แบบแบน (device_code/device_label/room_name)
   *  ส่วน endpoint ที่ต้องล็อกอินคืน device_info ซ้อนอยู่ จึงรองรับทั้งสองรูปแบบ */
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
  const subNote = ticket?.status ? SUB_STATUS_NOTE[ticket.status] : undefined;

  /** เปอร์เซ็นต์ความคืบหน้าของแถบเรืองแสงใต้ stepper */
  const progressPct = useMemo(() => {
    if (stepIndex < 0) return 0;
    return Math.min(100, Math.round((stepIndex / (STEPS.length - 1)) * 100));
  }, [stepIndex]);

  return (
    <div className="ph-page">
      {/* ชั้นพื้นหลัง: แสงออโรร่า + เส้นวงจร — ตกแต่งล้วน ไม่รับโฟกัส */}
      <div className="ph-bg" aria-hidden="true">
        <span className="ph-bg-aurora ph-bg-aurora-1" />
        <span className="ph-bg-aurora ph-bg-aurora-2" />
        <span className="ph-bg-aurora ph-bg-aurora-3" />
        <span className="ph-bg-grid" />
        <span className="ph-bg-vignette" />
      </div>

      <header className="ph-topbar">
        <a className="ph-brand" href="/">
          <span className="ph-brand-mark">
            <img className="ph-brand-logo" src="/logo.jpg" alt="IWA" />
          </span>
          <span className="ph-brand-text">
            <strong>IWA Smart Classroom Support</strong>
            <small>ระบบแจ้งซ่อมและติดตามงานอุปกรณ์ห้องเรียน</small>
          </span>
        </a>
        <div className="ph-topbar-right">
          <LivePill>ระบบพร้อมรับแจ้ง</LivePill>
          <a className="ph-customer-link" href="/?customer=1">สำหรับลูกค้า</a>
          <PublicThemeToggle />
          <a className="ph-login-link" href="/?login=1">
            เข้าสู่ระบบเจ้าหน้าที่
          </a>
        </div>
      </header>

      <main className="ph-main">
        <section className="ph-hero">
          <div className="ph-hero-grid">
            <div className="ph-hero-copy">
              <span className="ph-eyebrow">IWA SMART CLASSROOM SUPPORT</span>
              <h1 className="ph-hero-title">
                ดูแลอุปกรณ์ห้องเรียน
                <br /><span className="ph-hero-accent">ในที่เดียว</span>
              </h1>
              <p className="ph-hero-sub">
                แจ้งซ่อม ติดตามงาน และตรวจสอบประกันได้ด้วยตัวเอง
                ไม่ต้องเข้าสู่ระบบ ส่วนเจ้าหน้าที่มีพื้นที่ทำงานแยกต่างหาก
              </p>
              <div className="ph-hero-cta">
                <a href="/?publicreport=1" className="ph-cta-primary">แจ้งซ่อมอุปกรณ์ <ArrowIcon /></a>
                <button type="button" className="ph-cta-secondary" onClick={focusTrack}>ติดตามงานซ่อม</button>
              </div>
            </div>
            <div className="ph-hero-panel" aria-label="ขั้นตอนการใช้งาน">
              <span className="ph-panel-kicker">เริ่มใช้งานง่าย ๆ</span>
              <h2>จากแจ้งปัญหา<br />ถึงติดตามผล</h2>
              <ol>
                <li><strong>01</strong><span>สแกน QR หรือกรอกรหัสอุปกรณ์เพื่อแจ้งปัญหา</span></li>
                <li><strong>02</strong><span>รับเลขใบงานทันที ใช้ค้นสถานะได้ตลอด</span></li>
                <li><strong>03</strong><span>ดูความคืบหน้าจากเจ้าหน้าที่ในหน้าเดียว</span></li>
              </ol>
            </div>
          </div>

          <div className="ph-actions">
            <a className="ph-action-card ph-action-primary" href="/?publicreport=1">
              <span className="ph-action-icon"><ScanIcon /></span>
              <span className="ph-action-body">
                <strong>แจ้งซ่อม / สแกน QR</strong>
                <small>สแกนสติกเกอร์ที่อุปกรณ์ หรือกรอกรหัสอุปกรณ์เอง</small>
              </span>
              <ArrowIcon />
            </a>
            <button type="button" className="ph-action-card" onClick={focusTrack}>
              <span className="ph-action-icon"><SearchIcon /></span>
              <span className="ph-action-body">
                <strong>ติดตามสถานะ</strong>
                <small>ใช้เลขใบงานที่ได้รับตอนแจ้ง เช่น TK.SCHM01.26.0001-T</small>
              </span>
              <ArrowIcon />
            </button>
            <a className="ph-action-card" href="#ph-warranty">
              <span className="ph-action-icon"><ShieldIcon /></span>
              <span className="ph-action-body">
                <strong>ตรวจสอบประกัน</strong>
                <small>กรอกหมายเลขสินค้าของเครื่องที่ซื้อไปแล้ว ดูวันหมดประกันได้ทันที</small>
              </span>
              <ArrowIcon />
            </a>
          </div>

          <div className="ph-customer-band">
            <div>
              <span className="ph-panel-kicker">สำหรับผู้สนใจสินค้าและบริการ</span>
              <h2>ต้องการข้อมูลสินค้า ราคา หรือให้ทีมงานติดต่อกลับ?</h2>
              <p>ลงทะเบียนลูกค้าแยกจากบัญชีเจ้าหน้าที่ ข้อมูลจะส่งตรงถึงทีมขาย</p>
            </div>
            <a href="/?customer=1" className="ph-customer-cta">สมัครสมาชิกลูกค้า <ArrowIcon /></a>
          </div>

          <ul className="ph-highlights">
            {HIGHLIGHTS.map((h) => (
              <HighlightCard key={h.title} item={h} />
            ))}
          </ul>
        </section>

        <section className="ph-card ph-track-card" ref={trackRef} aria-labelledby="ph-track-title">
          <div className="ph-card-head">
            <h2 className="ph-card-title" id="ph-track-title">ติดตามสถานะใบงาน</h2>
            <span className="ph-card-tag">TICKET TRACKING</span>
          </div>

          <form
            className="ph-track-form"
            onSubmit={(e) => {
              e.preventDefault();
              search();
            }}
          >
            <label className="ph-sr-only" htmlFor="ph-ticket-input">เลขใบงาน</label>
            <div className="ph-input-wrap">
              <span className="ph-input-icon" aria-hidden="true"><SearchIcon /></span>
              <input
                id="ph-ticket-input"
                ref={inputRef}
                className="ph-input"
                type="text"
                inputMode="text"
                autoComplete="off"
                spellCheck={false}
                value={input}
                onChange={(e) => setInput(e.target.value.toUpperCase())}
                placeholder="TK.SCHM01.26.0001-T"
                aria-describedby="ph-ticket-hint"
              />
            </div>
            <button type="submit" className="ph-btn ph-btn-primary" disabled={loading || !input.trim()}>
              {loading ? <span className="ph-spinner" aria-hidden="true" /> : <SearchIcon />}
              <span>{loading ? 'กำลังค้นหา' : 'ดูสถานะ'}</span>
            </button>
          </form>
          <p className="ph-hint" id="ph-ticket-hint">
            เลขใบงานแยกตามโรงเรียน — รูปแบบ <code>TK.รหัสโรงเรียน.ปี.ลำดับ-ตัวตรวจสอบ</code> พิมพ์เล็กหรือใหญ่ก็ได้
          </p>

          {recent.length > 0 && (
            <div className="ph-recent">
              <span className="ph-recent-label">ดูล่าสุด:</span>
              {recent.map((no) => (
                <button
                  key={no}
                  type="button"
                  className="ph-chip"
                  onClick={() => search(no)}
                  disabled={loading}
                >
                  {no}
                </button>
              ))}
            </div>
          )}

          <div aria-live="polite">
            {error && <div className="ph-alert ph-alert-danger">{error}</div>}

            {!error && searched && !ticket && !loading && (
              <div className="ph-alert ph-alert-warn">
                ไม่พบใบงานนี้ — ตรวจสอบเลขอีกครั้ง หรือถ้าจำไม่ได้ให้สแกน QR ที่อุปกรณ์ ระบบจะแสดงใบงานที่ค้างอยู่ให้
              </div>
            )}

            {ticket && (
              <div className="ph-result">
                <div className="ph-result-head">
                  <div className="ph-result-no">
                    <span className="ph-result-no-label">เลขใบงาน</span>
                    <strong>{ticketNo}</strong>
                  </div>
                  <span className={`badge badge-${ticket.status} ph-status-badge`}>{statusLabelOf(ticket)}</span>
                </div>

                {ticket.title && <p className="ph-result-title">{ticket.title}</p>}

                {cancelled ? (
                  <div className="ph-alert ph-alert-danger">ใบงานนี้ถูกยกเลิกแล้ว — หากอุปกรณ์ยังใช้งานไม่ได้ กรุณาแจ้งซ่อมใหม่</div>
                ) : (
                  <>
                    <div className="ph-progress" aria-hidden="true">
                      <span className="ph-progress-fill" style={{ width: `${progressPct}%` }} />
                    </div>
                    <ol className="ph-steps" aria-label="ความคืบหน้าของงาน">
                      {STEPS.map((s, i) => {
                        const done = i < stepIndex;
                        const current = i === stepIndex;
                        return (
                          <li
                            key={s.key}
                            className={`ph-step${done ? ' is-done' : ''}${current ? ' is-current' : ''}`}
                            aria-current={current ? 'step' : undefined}
                          >
                            <span className="ph-step-dot">{done ? <CheckIcon /> : i + 1}</span>
                            <span className="ph-step-label">{s.label}</span>
                          </li>
                        );
                      })}
                    </ol>
                    {subNote && <div className="ph-alert ph-alert-info">{subNote}</div>}
                  </>
                )}

                <div className="ph-meta-grid">
                  <MetaItem
                    label="อุปกรณ์"
                    value={
                      <>
                        {dev?.device_label || dev?.device_type || 'อุปกรณ์'}
                        {dev?.brand ? ` · ${dev.brand}` : ''}
                        {dev?.model ? ` ${dev.model}` : ''}
                      </>
                    }
                    sub={dev?.device_id || ticket.device_code || ticket.device_id || '-'}
                  />
                  <MetaItem
                    label="สถานที่"
                    value={dev?.room_name || '-'}
                    sub={dev?.organization_name || undefined}
                  />
                  <MetaItem
                    label="ความเร่งด่วน"
                    value={PRIORITY_LABELS[ticket.priority] || ticket.priority || 'ปกติ'}
                  />
                  <MetaItem
                    label="แจ้งเมื่อ"
                    value={fmtDateTime(ticket.created_at)}
                    sub={sinceText(ticket.created_at) || undefined}
                  />
                  {ticket.estimated_completion && !ticket.closed_at && (
                    <MetaItem
                      label="กำหนดเสร็จตาม SLA"
                      value={fmtDateTime(ticket.estimated_completion)}
                    />
                  )}
                  {ticket.closed_at && (
                    <MetaItem
                      label="ปิดงานเมื่อ"
                      value={fmtDateTime(ticket.closed_at)}
                      sub={sinceText(ticket.closed_at) || undefined}
                    />
                  )}
                </div>

                <h3 className="ph-sub-title">ประวัติการดำเนินการ</h3>
                {history.length > 0 ? (
                  <ul className="ph-timeline">
                    {history.map((h: any, i: number) => (
                      <li className="ph-timeline-item" key={`${h.created_at || i}-${i}`}>
                        <span className="ph-timeline-dot" aria-hidden="true" />
                        <div className="ph-timeline-body">
                          <div className="ph-timeline-status">
                            {STATUS_LABELS[h.to_status || h.status] || h.to_status || h.status || 'อัปเดต'}
                          </div>
                          {h.note && <div className="ph-timeline-note">{h.note}</div>}
                          <div className="ph-timeline-time">
                            {fmtDateTime(h.created_at)}
                            {h.author_name ? ` · ${h.author_name}` : ''}
                          </div>
                        </div>
                      </li>
                    ))}
                  </ul>
                ) : (
                  <p className="ph-empty">
                    ยังไม่มีบันทึกการดำเนินการที่แสดงได้ — ดูความคืบหน้าจากแถบขั้นตอนด้านบน
                  </p>
                )}

                {ticket.resolution_notes && (
                  <div className="ph-alert ph-alert-success">
                    <strong>ผลการซ่อม:</strong> {ticket.resolution_notes}
                  </div>
                )}

                <div className="ph-result-actions">
                  <button type="button" className="ph-btn" onClick={() => search(ticketNo)} disabled={loading}>
                    <RefreshIcon />
                    <span>รีเฟรชสถานะ</span>
                  </button>
                  <button type="button" className="ph-btn" onClick={copyLink}>
                    <LinkIcon />
                    <span>{copied ? 'คัดลอกลิงก์แล้ว' : 'คัดลอกลิงก์ติดตาม'}</span>
                  </button>
                  <a className="ph-btn" href="/?publicreport=1">
                    <PlusIcon />
                    <span>แจ้งอุปกรณ์อื่น</span>
                  </a>
                </div>
              </div>
            )}
          </div>
        </section>

        <WarrantyCard />

        <section className="ph-card ph-help">
          <div className="ph-card-head">
            <h2 className="ph-card-title">หาเลขใบงานไม่เจอ?</h2>
            <span className="ph-card-tag">HELP</span>
          </div>
          <ul className="ph-help-list">
            <li>สแกน QR ที่ติดอยู่กับอุปกรณ์ — ถ้าเครื่องนั้นมีงานค้างอยู่ ระบบจะแสดงเลขใบงานและสถานะให้ทันที</li>
            <li>เลขใบงานอยู่ในข้อความยืนยันตอนแจ้งซ่อม และแยกตามโรงเรียนเพื่อไม่ให้กรอกสลับกัน</li>
            <li>อุปกรณ์ที่แจ้งไปแล้วจะแจ้งซ้ำไม่ได้ — ให้แจ้งอาการเพิ่มเข้าใบงานเดิมแทน</li>
          </ul>
        </section>
      </main>

      <footer className="ph-footer">
        <span className="ph-footer-brand">IWA Smart Classroom Support</span>
        {/* จัดลิงก์เป็นกลุ่มเดียว เพื่อให้ space-between ของ .ph-footer ยังแบ่งเป็นสองฝั่งเหมือนเดิม */}
        <nav className="ph-footer-links" aria-label="ลิงก์เพิ่มเติม">
          <a href="/?login=1">เข้าสู่ระบบเจ้าหน้าที่</a>
          <a href="/?register=1">สมัครสมาชิกเจ้าหน้าที่</a>
          <a href="/?customer=1">สมัครสมาชิกลูกค้า</a>
        </nav>
      </footer>
    </div>
  );
}
