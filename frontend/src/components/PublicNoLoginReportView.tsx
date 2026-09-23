import React, { useEffect, useRef, useState } from 'react';
import { api } from '../api/client';
import { REPORTER_TYPE_OPTIONS, DEFAULT_REPORTER_TYPE } from '../reporterTypes';
import '../styles/public-home.css';
import '../styles/public-report.css';
// เลเยอร์ธีม: ผูก --ph-*/--pr-* เข้ากับ token กลาง จึงต้องมาหลัง public-report.css
import '../styles/public-theme.css';
import PublicThemeToggle from './PublicThemeToggle';

// ─── แจ้งซ่อมสาธารณะ (คนไม่มีบัญชี) ─────────────────────────────────────────
// ทางเข้า: URL ?publicreport=1 หรือปุ่มบนหน้า Login — อยู่ก่อน auth gate
//
// การระบุอุปกรณ์ใช้การ "สแกน QR ที่ตัวอุปกรณ์" เท่านั้น
// (ตัดโหมดกรอกห้อง/อุปกรณ์เอง และโหมดเลือกจากรายการในระบบออกแล้ว)
// QR → /api/qr/resolve/{token} (ไม่ต้องล็อกอิน) → ได้ทั้งอุปกรณ์ ห้อง และรหัสหน่วยงาน
//
// หน้านี้ใช้ธีมเดียวกับหน้าแรกสาธารณะ (PublicHomeView): คลาส .ph-* จาก
// public-home.css + คลาสเฉพาะฟอร์ม .pr-* จาก public-report.css ทั้งสองไฟล์
// scope อยู่ใต้ .ph-page จึงไม่กระทบธีมของ dashboard

type ScannedDevice = {
  device_id: string;
  device_type: string;
  brand: string;
  model: string;
  room_label: string;
  org_code: string;
  org_name: string;
  /** วันหมดประกัน (ISO จาก /api/qr/resolve) — null = ไม่ได้บันทึกไว้ */
  warranty_until: string | null;
};

/** ต้องตรงกับ WARRANTY_WARN_DAYS ใน backend/app/pm_rules.py (PM Rule 2 §38)
 *  เพื่อให้ป้ายที่ผู้แจ้งเห็นกับ flag ที่ระบบสร้างใช้เกณฑ์เดียวกัน
 */
const WARRANTY_WARN_DAYS = 30;

type WarrantyState = { tone: 'ok' | 'warn' | 'expired'; label: string };

/** แปลงวันหมดประกันเป็นป้ายสถานะ — คืน null เมื่อไม่มีข้อมูลหรือวันที่ใช้ไม่ได้
 *  (ไม่บันทึกประกันไว้ก็ไม่ควรขึ้นป้ายอะไรเลย ดีกว่าขึ้นว่า "หมดประกัน" ผิด ๆ)
 */
const warrantyState = (value: string | null): WarrantyState | null => {
  if (!value) return null;
  const until = new Date(value);
  if (Number.isNaN(until.getTime())) return null;
  const dateText = until.toLocaleDateString('th-TH', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
  });
  const daysLeft = Math.ceil((until.getTime() - Date.now()) / 86400000);
  if (daysLeft < 0) return { tone: 'expired', label: `หมดประกันแล้ว (${dateText})` };
  if (daysLeft <= WARRANTY_WARN_DAYS) {
    return {
      tone: 'warn',
      label: daysLeft === 0
        ? `ประกันหมดวันนี้ (${dateText})`
        : `ประกันใกล้หมด เหลือ ${daysLeft} วัน (${dateText})`,
    };
  }
  return { tone: 'ok', label: `อยู่ในประกันถึง ${dateText}` };
};

/* ─── ไอคอน (inline SVG — ไม่พึ่ง icon library) ───────────────────────────── */

const ScanIcon = () => (
  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M3 8V5a2 2 0 0 1 2-2h3M16 3h3a2 2 0 0 1 2 2v3M21 16v3a2 2 0 0 1-2 2h-3M8 21H5a2 2 0 0 1-2-2v-3" />
    <path d="M7 12h10" />
  </svg>
);

const CheckIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M20 6L9 17l-5-5" />
  </svg>
);

const BackIcon = () => (
  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M15 18l-6-6 6-6" />
  </svg>
);

const CameraOffIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <rect x="3" y="7" width="13" height="12" rx="2" />
    <path d="M16 11l5-3v10l-5-3" />
    <path d="M3 3l18 18" />
  </svg>
);

const SendIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M22 2L11 13" />
    <path d="M22 2l-7 20-4-9-9-4z" />
  </svg>
);

const AlertIcon = () => (
  <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <path d="M10.3 3.9L1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0z" />
    <path d="M12 9v4M12 17h.01" />
  </svg>
);

const SearchIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
    <circle cx="11" cy="11" r="7" />
    <path d="M20 20l-3.5-3.5" />
  </svg>
);

const STEPS = ['สแกน QR อุปกรณ์', 'กรอกอาการเสีย', 'ส่งคำร้อง'];

export default function PublicNoLoginReportView() {
  // อุปกรณ์ที่ได้จากการสแกน QR — ต้องมีก่อนจึงจะกรอกอาการและส่งคำร้องได้
  const [scanned, setScanned] = useState<ScannedDevice | null>(null);

  // สถานะกล้อง/การตรวจสอบ QR
  const [scanning, setScanning] = useState(false);
  const [resolving, setResolving] = useState(false);
  const [scanStatus, setScanStatus] = useState<string | null>(null);
  const [scanError, setScanError] = useState<string | null>(null);
  const scannerRef = useRef<any>(null);

  // ช่องทางสำรองเมื่อกล้องใช้ไม่ได้ / สติกเกอร์ QR เสียหาย: พิมพ์โค้ดหรือลิงก์ใต้ QR
  const [manualCode, setManualCode] = useState('');

  const [form, setForm] = useState({
    title: '',
    description: '',
    reporter_name: '',
    reporter_phone: '',
    reporter_type: DEFAULT_REPORTER_TYPE,
    priority: 'normal',
  });

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErr, setFieldErr] = useState<{ name?: string; phone?: string }>({});
  const [photos, setPhotos] = useState<string[]>([]);
  const [submitted, setSubmitted] = useState(false);
  const [ticketId, setTicketId] = useState('');
  const [resultDevice, setResultDevice] = useState<any>(null);
  const [dupAlert, setDupAlert] = useState<{
    existing_ticket_no?: string;
    existing_status?: string;
    existing_status_label?: string;
    existing_device_label?: string;
    existing_title?: string;
    can_add_note?: boolean;
  } | null>(null);

  // งานค้างที่ตรวจล่วงหน้าทันทีหลังสแกน QR — ไม่ต้องให้ผู้แจ้งกรอกทั้งใบแล้วค่อยเจอ 409
  const [openTicket, setOpenTicket] = useState<any | null>(null);
  const [openTicketLoading, setOpenTicketLoading] = useState(false);

  // แจ้งอาการ/ข้อมูลเพิ่มเข้า Ticket เดิมที่ยังไม่ปิด — ใช้แทนการเปิดใบซ้ำ
  const [noteText, setNoteText] = useState('');
  const [noteSending, setNoteSending] = useState(false);
  const [noteError, setNoteError] = useState<string | null>(null);
  const [noteDone, setNoteDone] = useState<string | null>(null);

  // เลื่อนจอไปที่กล่องงานค้าง (อยู่เหนือฟอร์ม อาจพ้นจอเมื่อกดส่ง)
  const blockRef = useRef<HTMLDivElement | null>(null);

  /** ดึงโทเคน/รหัสอุปกรณ์ออกจากข้อความใน QR (รองรับทั้ง URL และโค้ดตรง ๆ) */
  const extractQrCode = (raw: string): string | null => {
    const s = raw.trim();
    if (!s) return null;
    const tokenMatch = s.match(/[?&](?:t|token|qr)=([^&\s]+)/i);
    if (tokenMatch) return decodeURIComponent(tokenMatch[1]);
    const deviceMatch = s.match(/[?&](?:device|device_id|code)=([^&\s]+)/i);
    if (deviceMatch) return decodeURIComponent(deviceMatch[1]);
    const devPattern = s.match(/DEV-[\w-]+/i);
    if (devPattern) return devPattern[0].toUpperCase();
    // QR ที่เก็บโทเคนเปล่า ๆ (backend ออกด้วย secrets.token_urlsafe(24))
    if (/^[A-Za-z0-9_-]{16,}$/.test(s)) return s;
    return null;
  };

  /** QR → อุปกรณ์: resolve ผ่าน /qr/resolve (ไม่ต้อง auth) แล้วล็อกอุปกรณ์ + หน่วยงานให้เลย */
  const applyQrDevice = async (raw: string) => {
    const code = extractQrCode(raw);
    if (!code) {
      setScanError(`อ่าน QR ไม่ได้: "${raw.trim().slice(0, 40)}" — ลองสแกนอีกครั้ง หรือพิมพ์โค้ดใต้สติกเกอร์`);
      setScanStatus(null);
      return;
    }
    setScanError(null);
    setScanStatus('กำลังตรวจสอบ QR...');
    setResolving(true);
    try {
      const resp = await api.qrResolve(code);
      const device = resp?.device;
      const orgCode = (resp?.organization?.code || '').trim();
      if (!device?.device_id || !orgCode) {
        setScanError('QR นี้ไม่ตรงกับอุปกรณ์ในระบบ — ตรวจสอบสติกเกอร์หรือแจ้งเจ้าหน้าที่');
        setScanStatus(null);
        return;
      }
      setScanned({
        device_id: device.device_id,
        device_type: device.device_type || '',
        brand: device.brand || '',
        model: device.model || '',
        room_label: [resp?.room?.building, resp?.room?.name].filter(Boolean).join(' ').trim(),
        org_code: orgCode,
        org_name: resp?.organization?.name || orgCode,
        warranty_until: device.warranty_until ?? null,
      });
      setScanStatus(null);
      setManualCode('');

      // อุปกรณ์นี้มีงานค้างอยู่ไหม — รู้ทันทีหลังสแกน จะได้แจ้งเพิ่มเข้าใบเดิมแทนการเปิดใบซ้ำ
      setOpenTicketLoading(true);
      try {
        const ot = await api.publicDeviceOpenTicket(device.device_id);
        setOpenTicket(ot?.has_open_ticket ? (ot.open_ticket ?? null) : null);
      } catch {
        // ตรวจไม่ได้ก็ไม่ปิดทางแจ้ง — backend ยังกัน 409 ให้อยู่
        setOpenTicket(null);
      } finally {
        setOpenTicketLoading(false);
      }
    } catch (err: any) {
      setScanError(err?.message || 'ตรวจสอบ QR ไม่สำเร็จ — ลองสแกนอีกครั้ง');
      setScanStatus(null);
    } finally {
      setResolving(false);
    }
  };

  const startScan = async () => {
    setScanError(null);
    setScanStatus('กำลังเปิดกล้อง...');
    setScanning(true);
    try {
      const Html5Qrcode = (await import('html5-qrcode')).Html5Qrcode;
      const scanner = new Html5Qrcode('public-qr-reader');
      scannerRef.current = scanner;
      await scanner.start(
        { facingMode: 'environment' },
        { fps: 10, qrbox: { width: 220, height: 220 } },
        (decodedText: string) => {
          // เจอ QR แล้ว — ปิดกล้องก่อนค่อยยิง API
          const finish = () => {
            scannerRef.current = null;
            setScanning(false);
            applyQrDevice(decodedText);
          };
          scanner.stop().then(finish).catch(finish);
        },
        () => { /* เฟรมที่ยังไม่เจอ QR — ข้าม */ }
      );
      setScanStatus('เล็ง QR บนอุปกรณ์ให้อยู่ในกรอบ');
    } catch {
      scannerRef.current = null;
      setScanning(false);
      setScanStatus(null);
      setScanError('เปิดกล้องไม่สำเร็จ — ต้องเปิดผ่าน HTTPS (หรือ localhost) และอนุญาตให้ใช้กล้อง');
    }
  };

  const stopScan = async () => {
    const scanner = scannerRef.current;
    scannerRef.current = null;
    if (scanner) {
      try { await scanner.stop(); } catch { /* ปิดไปแล้ว — ไม่ต้องทำอะไร */ }
    }
    setScanning(false);
    setScanStatus(null);
  };

  /** เริ่มใหม่: สแกนอุปกรณ์อื่น */
  const resetScan = () => {
    setScanned(null);
    setScanStatus(null);
    setScanError(null);
    setError(null);
    setDupAlert(null);
    setOpenTicket(null);
    setOpenTicketLoading(false);
    setNoteText('');
    setNoteError(null);
    setNoteDone(null);
  };

  // สแกน QR ด้วยแอปกล้องของเครื่อง แล้วเปิดลิงก์ ?publicreport=1&t=TOKEN → ล็อกอุปกรณ์ให้ทันที
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const token = (
      params.get('t') || params.get('token') || params.get('qr') ||
      params.get('device') || params.get('device_id') || ''
    ).trim();
    if (token) applyQrDevice(token);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // ปิดกล้องเสมอเมื่อออกจากหน้า (ไม่งั้นไฟกล้องค้าง)
  useEffect(() => {
    return () => {
      const scanner = scannerRef.current;
      scannerRef.current = null;
      if (scanner) scanner.stop().catch(() => {});
    };
  }, []);

  const setField = (field: string, value: string) => {
    setForm((f) => ({ ...f, [field]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setDupAlert(null);
    setNoteError(null);
    setNoteDone(null);
    setFieldErr({});

    if (!scanned) {
      setError('กรุณาสแกน QR ที่ตัวอุปกรณ์ก่อนส่งคำร้อง');
      setSubmitting(false);
      return;
    }

    const fe: { name?: string; phone?: string } = {};
    if (!form.reporter_name.trim()) fe.name = 'กรุณากรอกชื่อผู้แจ้ง (จำเป็น)';
    if (!form.reporter_phone.trim()) fe.phone = 'กรุณากรอกเบอร์โทรติดต่อ (จำเป็น)';
    if (fe.name || fe.phone) {
      setFieldErr(fe);
      setSubmitting(false);
      return;
    }
    if (!form.title.trim()) {
      setError('กรุณาระบุหัวข้อ/อาการ (จำเป็น)');
      setSubmitting(false);
      return;
    }

    // มีใบงานค้างอยู่แล้ว → ไม่ต้องยิงให้ backend ตอบ 409 ซ้ำ ชี้ไปที่ช่องแจ้งเพิ่มเลย
    if (openTicket && openTicket.can_add_note !== false) {
      setError(
        `อุปกรณ์นี้มีใบงานค้างอยู่ (${openTicket.ticket_no || '-'}) — ` +
        'กรุณาแจ้งอาการเพิ่มเข้าใบเดิมในกล่องด้านบน ระบบไม่สร้าง Ticket ซ้ำ'
      );
      setSubmitting(false);
      blockRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
      return;
    }

    // อุปกรณ์และหน่วยงานมาจาก QR ที่ resolve แล้วเท่านั้น — ไม่มีการกรอกเอง
    const payload = {
      organization_code: scanned.org_code,
      device_id: scanned.device_id,
      title: form.title,
      description: form.description,
      reporter_name: form.reporter_name.trim(),
      reporter_phone: form.reporter_phone.trim(),
      reporter_type: form.reporter_type,
      priority: form.priority,
      attachments: photos,
    };

    try {
      const result = await api.publicReport(payload);
      setTicketId(result.ticket_id || '-');
      setResultDevice(result);
      setSubmitted(true);
    } catch (err: any) {
      if (err?.status === 409 && err?.code === 'DUPLICATE_OPEN_TICKET') {
        const d = err.detail || {};
        setDupAlert({
          existing_ticket_no: d.existing_ticket_no,
          existing_status: d.existing_status,
          existing_status_label: d.existing_status_label || d.open_ticket?.status_label,
          existing_device_label: d.existing_device_label || d.open_ticket?.device_label,
          existing_title: d.existing_title || d.open_ticket?.title,
          can_add_note: d.can_add_note !== false,
        });
        setNoteError(null);
        setNoteDone(null);
        setTimeout(
          () => blockRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }),
          0,
        );
      } else {
        setError(err?.message || 'ส่งคำร้องไม่สำเร็จ กรุณาลองอีกครั้ง');
      }
    } finally {
      setSubmitting(false);
    }
  };

  /** ส่งอาการ/ข้อมูลเพิ่มเข้า Ticket เดิม (ไม่ต้องล็อกอิน) — ไม่เปลี่ยนสถานะงาน */
  const handleAddNote = async () => {
    const ticketNo = (dupAlert?.existing_ticket_no || openTicket?.ticket_no || '').trim();
    if (!ticketNo) return;
    const note = noteText.trim();
    const name = form.reporter_name.trim();
    if (note.length < 3) {
      setNoteError('กรุณาระบุอาการหรือข้อมูลที่ต้องการแจ้งเพิ่ม (อย่างน้อย 3 ตัวอักษร)');
      return;
    }
    if (!name) {
      setNoteError('กรุณากรอกชื่อผู้แจ้งในฟอร์มด้านล่างก่อน');
      return;
    }
    setNoteError(null);
    setNoteSending(true);
    try {
      const res = await api.publicAddTicketNote(ticketNo, {
        note,
        reporter_name: name,
        reporter_phone: form.reporter_phone.trim() || undefined,
        attachments: photos.length ? photos : undefined,
      });
      setNoteDone(res?.message || `บันทึกข้อมูลเพิ่มเข้า Ticket ${ticketNo} เรียบร้อยแล้ว`);
      setNoteText('');
    } catch (err: any) {
      if (err?.status === 409) {
        // งานถูกปิดไปแล้วระหว่างกรอก → เปิดฟอร์มแจ้งใหม่ได้
        setNoteError(err?.detail?.message || err?.message || 'Ticket นี้ปิดงานแล้ว — กรุณาแจ้งซ่อมใหม่');
        setDupAlert((d) => (d ? { ...d, can_add_note: false } : d));
        setOpenTicket((t: any) => (t ? { ...t, can_add_note: false } : t));
      } else {
        setNoteError(err?.message || 'ส่งข้อมูลเพิ่มไม่สำเร็จ กรุณาลองอีกครั้ง');
      }
    } finally {
      setNoteSending(false);
    }
  };

  // งานค้างที่ต้องแจ้งเพิ่มเข้าใบเดิม — รวมทั้งที่ตรวจล่วงหน้า (open-ticket) และที่ 409 ตอบกลับ
  // ให้เป็นรูปแบบเดียว เพื่อให้ UI มีกล่องเตือนที่เดียว
  const blocking = dupAlert
    ? {
        ticket_no: dupAlert.existing_ticket_no || '',
        status_label: dupAlert.existing_status_label || dupAlert.existing_status || '',
        device_label: dupAlert.existing_device_label || '',
        title: dupAlert.existing_title || '',
        can_add_note: dupAlert.can_add_note !== false,
      }
    : openTicket
      ? {
          ticket_no: openTicket.ticket_no || '',
          status_label: openTicket.status_label || openTicket.status || '',
          device_label: openTicket.device_label || '',
          title: openTicket.title || '',
          can_add_note: openTicket.can_add_note !== false,
        }
      : null;

  const stepIndex = submitted ? 2 : scanned ? 1 : 0;
  // สถานะประกันของเครื่องที่สแกนได้ — คำนวณตอน render เพราะขึ้นกับวันปัจจุบัน
  const warranty = scanned ? warrantyState(scanned.warranty_until) : null;

  return (
    <div className="ph-page pr-page">
      {/* พื้นหลังตกแต่ง — ชุดเดียวกับหน้าแรกสาธารณะ */}
      <div className="ph-bg" aria-hidden="true">
        <div className="ph-bg-aurora ph-bg-aurora-1" />
        <div className="ph-bg-aurora ph-bg-aurora-2" />
        <div className="ph-bg-aurora ph-bg-aurora-3" />
        <div className="ph-bg-grid" />
        <div className="ph-bg-vignette" />
      </div>

      <header className="ph-topbar">
        <a className="ph-brand" href="/" aria-label="กลับหน้าแรก">
          <span className="ph-brand-mark">
            <img className="ph-brand-logo" src="/logo.jpg" alt="" />
          </span>
          <span className="ph-brand-text">
            <strong>Smart Classroom Support</strong>
            <small>แจ้งซ่อมสาธารณะ — สแกน QR ที่ตัวอุปกรณ์</small>
          </span>
        </a>
        <div className="ph-topbar-right">
          <span className="ph-live">
            <span className="ph-live-dot" aria-hidden="true" />
            ไม่ต้องเข้าสู่ระบบ
          </span>
          <PublicThemeToggle />
          <a className="ph-login-link" href="/?login=1">
            เข้าสู่ระบบเจ้าหน้าที่
          </a>
        </div>
      </header>

      <main className="ph-main pr-main">
        <section className="pr-head">
          <span className="ph-eyebrow">PUBLIC REPAIR REQUEST</span>
          <h1 className="pr-title">
            แจ้งซ่อมอุปกรณ์<span className="ph-hero-accent">ในห้องเรียน</span>
          </h1>
          <p className="pr-sub">
            สแกน QR บนตัวอุปกรณ์ที่เสีย ระบบจะระบุห้อง อุปกรณ์ และโรงเรียนให้อัตโนมัติ
            จากนั้นกรอกอาการแล้วส่ง — จะได้เลขใบงานไว้ติดตามสถานะทันที
          </p>

          <ol className="pr-steps" aria-label="ขั้นตอนการแจ้งซ่อม">
            {STEPS.map((label, i) => {
              const done = i < stepIndex;
              const current = i === stepIndex;
              return (
                <li
                  key={label}
                  className={`pr-step${done ? ' is-done' : ''}${current ? ' is-current' : ''}`}
                  aria-current={current ? 'step' : undefined}
                >
                  <span className="pr-step-dot">{done ? <CheckIcon /> : i + 1}</span>
                  <span className="pr-step-label">{label}</span>
                </li>
              );
            })}
          </ol>
        </section>

        {submitted ? (
          /* ─── ผลลัพธ์: ส่งคำร้องสำเร็จ ─── */
          <section className="ph-card pr-card">
            <div className="pr-success">
              <div className="pr-success-icon" aria-hidden="true">
                <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6L9 17l-5-5" />
                </svg>
              </div>
              <h2 className="pr-success-title">ส่งคำร้องเรียบร้อยแล้ว</h2>
              <p className="pr-success-sub">หมายเลขใบงานของคุณ</p>
              <div className="pr-ticket-no">{ticketId}</div>
              {resultDevice?.device_id && (
                <p className="pr-success-meta">รหัสอุปกรณ์: {resultDevice.device_id}</p>
              )}
              <p className="pr-success-meta">
                เจ้าหน้าที่จะดำเนินการตรวจสอบและซ่อมแซมโดยเร็วที่สุด — จดเลขใบงานไว้เพื่อติดตามสถานะ
              </p>
              <div className="pr-success-actions">
                <a className="ph-btn ph-btn-primary" href={`/?ticket=${encodeURIComponent(ticketId)}`}>
                  <SearchIcon />
                  <span>ติดตามสถานะใบงานนี้</span>
                </a>
                <a className="ph-btn" href="/">
                  <BackIcon />
                  <span>กลับหน้าแรก</span>
                </a>
              </div>
            </div>
          </section>
        ) : !scanned ? (
          /* ─── ขั้นที่ 1: สแกน QR ที่ตัวอุปกรณ์ (ทางเดียวในการระบุอุปกรณ์) ─── */
          <section className="ph-card pr-card">
            <div className="ph-card-head">
              <h2 className="ph-card-title">สแกน QR ที่ตัวอุปกรณ์</h2>
              <span className="ph-card-tag">STEP 1</span>
            </div>

            <button
              type="button"
              className="ph-btn ph-btn-primary pr-btn-scan"
              onClick={scanning ? stopScan : startScan}
              disabled={resolving}
            >
              {resolving ? <span className="ph-spinner" aria-hidden="true" /> : <ScanIcon />}
              <span>{scanning ? 'หยุดสแกน' : resolving ? 'กำลังตรวจสอบ QR...' : 'เปิดกล้องสแกน QR'}</span>
            </button>

            <div
              id="public-qr-reader"
              className={`pr-scanner${scanning ? ' is-active' : ''}`}
              style={{ display: scanning ? 'block' : 'none' }}
            />

            <div aria-live="polite">
              {scanStatus && <div className="ph-alert ph-alert-info">{scanStatus}</div>}
              {scanError && (
                <div className="ph-alert ph-alert-danger" role="alert">
                  {scanError}
                </div>
              )}
            </div>

            {/* ช่องทางสำรอง: กล้องใช้ไม่ได้ / QR ชำรุด → พิมพ์โค้ดหรือลิงก์ใต้สติกเกอร์ */}
            <div className="pr-fallback">
              <div className="pr-fallback-head">
                <span className="pr-fallback-icon"><CameraOffIcon /></span>
                <label className="pr-label pr-label-inline" htmlFor="qr-manual-code">
                  กล้องใช้ไม่ได้? พิมพ์โค้ด/ลิงก์ใต้สติกเกอร์ QR
                </label>
              </div>
              <div className="pr-inline-row">
                <input
                  id="qr-manual-code"
                  type="text"
                  className="pr-input"
                  value={manualCode}
                  onChange={(e) => setManualCode(e.target.value)}
                  onKeyDown={(e) => {
                    if (e.key === 'Enter') {
                      e.preventDefault();
                      if (manualCode.trim().length >= 4 && !resolving) applyQrDevice(manualCode);
                    }
                  }}
                  placeholder="เช่น /scan?t=xxxxxxxx"
                  autoComplete="off"
                  maxLength={200}
                />
                <button
                  type="button"
                  className="ph-btn"
                  onClick={() => applyQrDevice(manualCode)}
                  disabled={resolving || manualCode.trim().length < 4}
                >
                  {resolving ? 'กำลังตรวจสอบ...' : 'ใช้โค้ดนี้'}
                </button>
              </div>
              <p className="ph-hint">
                ถ้าสติกเกอร์ QR หลุดหรืออ่านไม่ออก แจ้งเจ้าหน้าที่ IT ของโรงเรียนเพื่อออก QR ใหม่
              </p>
            </div>

            <div className="pr-back-row">
              <button type="button" className="pr-link-btn" onClick={() => { window.location.href = '/'; }}>
                <BackIcon />
                <span>กลับหน้าแรก</span>
              </button>
            </div>
          </section>
        ) : (
          /* ─── ขั้นที่ 2: อุปกรณ์ถูกล็อกจาก QR แล้ว → กรอกอาการเสีย ─── */
          <section className="ph-card pr-card">
            <div className="ph-card-head">
              <h2 className="ph-card-title">กรอกอาการที่พบ</h2>
              <span className="ph-card-tag">STEP 2</span>
            </div>

            <div className="pr-device">
              <div className="pr-device-main">
                <div className="pr-device-ok">
                  <CheckIcon />
                  <span>สแกน QR สำเร็จ</span>
                </div>
                <div className="pr-device-id">
                  {scanned.device_id}
                  {scanned.device_type ? ` · ${scanned.device_type}` : ''}
                </div>
                <div className="pr-device-meta">
                  {[scanned.brand, scanned.model].filter(Boolean).join(' ') || '—'}
                </div>
                <div className="pr-device-meta">
                  ห้อง: {scanned.room_label || '—'} · {scanned.org_name}
                </div>
                {warranty && (
                  <div className={`pr-warranty pr-warranty-${warranty.tone}`}>
                    {warranty.label}
                  </div>
                )}
              </div>
              <button type="button" className="pr-link-btn" onClick={resetScan}>
                <ScanIcon />
                <span>สแกนใหม่</span>
              </button>
            </div>

            {openTicketLoading && !blocking && (
              <p className="pr-checking" aria-live="polite">
                <span className="ph-spinner" aria-hidden="true" />
                กำลังตรวจสอบงานค้างของอุปกรณ์นี้...
              </p>
            )}

            {/* มีใบงานค้างอยู่แล้ว → แจ้งอาการเพิ่มเข้าใบเดิม ไม่เปิดใบซ้ำ */}
            {blocking && (
              <div className="pr-block" ref={blockRef}>
                <div className="pr-block-head">
                  <span className="pr-block-icon"><AlertIcon /></span>
                  <strong>อุปกรณ์นี้มีการแจ้งซ่อมที่ยังไม่ปิดอยู่แล้ว</strong>
                </div>
                <div className="pr-block-row">
                  <strong className="pr-block-no">{blocking.ticket_no || '-'}</strong>
                  {blocking.status_label && <span>· สถานะ: {blocking.status_label}</span>}
                </div>
                {blocking.title && (
                  <div className="pr-block-meta">อาการที่แจ้งไว้: {blocking.title}</div>
                )}
                {blocking.device_label && blocking.device_label !== '-' && (
                  <div className="pr-block-meta">อุปกรณ์: {blocking.device_label}</div>
                )}
                {blocking.ticket_no && (
                  <a className="pr-block-link" href={`/?ticket=${encodeURIComponent(blocking.ticket_no)}`}>
                    ดูสถานะใบงานนี้ → (ไม่ต้องเข้าสู่ระบบ)
                  </a>
                )}

                {blocking.can_add_note ? (
                  <div className="pr-note">
                    {noteDone ? (
                      <div className="ph-alert ph-alert-success" role="status">
                        {noteDone}
                      </div>
                    ) : (
                      <>
                        <label className="pr-label" htmlFor="dup-note">
                          แจ้งอาการ/ข้อมูลเพิ่มเข้าใบงานนี้
                        </label>
                        <textarea
                          id="dup-note"
                          className="pr-textarea"
                          value={noteText}
                          onChange={(e) => setNoteText(e.target.value)}
                          rows={3}
                          placeholder="เช่น อาการเพิ่มเติม เวลาที่เกิดปัญหา หรือข้อมูลติดต่อเพิ่ม"
                        />
                        {noteError && (
                          <div className="pr-field-err" role="alert">{noteError}</div>
                        )}
                        <button
                          type="button"
                          className="ph-btn pr-btn-full"
                          onClick={handleAddNote}
                          disabled={noteSending}
                        >
                          {noteSending ? <span className="ph-spinner" aria-hidden="true" /> : <SendIcon />}
                          <span>{noteSending ? 'กำลังส่ง...' : 'ส่งข้อมูลเพิ่มเข้าใบเดิม'}</span>
                        </button>
                        {photos.length > 0 && (
                          <p className="pr-note-hint">
                            รูปที่แนบไว้ {photos.length} รูป จะถูกส่งเข้าใบเดิมด้วย
                          </p>
                        )}
                        <p className="pr-note-hint">กรอกชื่อผู้แจ้งในฟอร์มด้านล่างก่อนส่งข้อมูลเพิ่ม</p>
                      </>
                    )}
                  </div>
                ) : (
                  <p className="pr-note-hint">
                    {noteError || 'ใบงานนี้ปิดแล้ว — แจ้งซ่อมใหม่ได้จากฟอร์มด้านล่าง'}
                  </p>
                )}
              </div>
            )}

            <form className="pr-form" onSubmit={handleSubmit}>
              <div className="pr-field">
                <label className="pr-label" htmlFor="pr-title">
                  หัวข้อ/อาการ <span className="pr-req">*</span>
                </label>
                <input
                  id="pr-title"
                  type="text"
                  className="pr-input"
                  value={form.title}
                  onChange={(e) => setField('title', e.target.value)}
                  placeholder="เช่น จอภาพไม่ติด, Wi-Fi ไม่เข้า, ไฟไม่มา"
                  maxLength={200}
                  required
                />
              </div>

              <div className="pr-field">
                <label className="pr-label" htmlFor="pr-desc">รายละเอียด</label>
                <textarea
                  id="pr-desc"
                  className="pr-textarea"
                  value={form.description}
                  onChange={(e) => setField('description', e.target.value)}
                  placeholder="บรรยายอาการที่เกิดขึ้น (เช่น เปิดเครื่องแล้วจอไม่ติด ไฟไม่เข้า)"
                  rows={3}
                />
              </div>

              <div className="pr-row">
                <div className="pr-field">
                  <label className="pr-label" htmlFor="pr-name">
                    ชื่อผู้แจ้ง <span className="pr-req">*</span>
                  </label>
                  <input
                    id="pr-name"
                    type="text"
                    className={`pr-input${fieldErr.name ? ' has-error' : ''}`}
                    value={form.reporter_name}
                    onChange={(e) => setField('reporter_name', e.target.value)}
                    placeholder="ชื่อ-นามสกุล"
                    aria-invalid={fieldErr.name ? true : undefined}
                  />
                  {fieldErr.name && <div className="pr-field-err">{fieldErr.name}</div>}
                </div>
                <div className="pr-field">
                  <label className="pr-label" htmlFor="pr-phone">
                    เบอร์ติดต่อ <span className="pr-req">*</span>
                  </label>
                  <input
                    id="pr-phone"
                    type="tel"
                    className={`pr-input${fieldErr.phone ? ' has-error' : ''}`}
                    value={form.reporter_phone}
                    onChange={(e) => setField('reporter_phone', e.target.value)}
                    placeholder="08xxxxxxxx"
                    aria-invalid={fieldErr.phone ? true : undefined}
                  />
                  {fieldErr.phone && <div className="pr-field-err">{fieldErr.phone}</div>}
                </div>
              </div>

              <div className="pr-row">
                <div className="pr-field">
                  <label className="pr-label" htmlFor="pr-reporter-type">ประเภทผู้แจ้ง</label>
                  <select
                    id="pr-reporter-type"
                    className="pr-select"
                    value={form.reporter_type}
                    onChange={(e) => setField('reporter_type', e.target.value)}
                  >
                    {REPORTER_TYPE_OPTIONS.map((opt) => (
                      <option key={opt.value} value={opt.value}>{opt.label}</option>
                    ))}
                  </select>
                </div>
                <div className="pr-field">
                  <label className="pr-label" htmlFor="pr-priority">ระดับความเร่งด่วน</label>
                  <select
                    id="pr-priority"
                    className="pr-select"
                    value={form.priority}
                    onChange={(e) => setField('priority', e.target.value)}
                  >
                    <option value="low">Low — ไม่เร่งด่วน</option>
                    <option value="normal">Normal — ปกติ</option>
                    <option value="high">High — ค่อนข้างเร่งด่วน</option>
                    <option value="critical">Critical — เร่งด่วนมาก</option>
                  </select>
                </div>
              </div>

              <div className="pr-field">
                <label className="pr-label" htmlFor="pr-photos">
                  แนบรูปภาพปัญหา (ไม่บังคับ, สูงสุด 3 ภาพ)
                </label>
                <input
                  id="pr-photos"
                  type="file"
                  accept="image/*"
                  multiple
                  className="pr-file"
                  onChange={async (e) => {
                    const files = e.target.files;
                    if (!files) return;
                    try {
                      for (const f of Array.from(files).slice(0, 3)) {
                        const r = await api.upload(f);
                        setPhotos((prev) => [...prev, r.url]);
                      }
                    } catch (err: any) { setError(err?.message || 'อัปโหลดรูปไม่สำเร็จ'); }
                  }}
                />
                {photos.length > 0 && (
                  <div className="pr-thumbs">
                    {photos.map((u, i) => (
                      <div className="pr-thumb" key={`${u}-${i}`}>
                        <img src={u} alt={`รูปที่แนบ ${i + 1}`} />
                        <button
                          type="button"
                          className="pr-thumb-remove"
                          onClick={() => setPhotos((prev) => prev.filter((_, idx) => idx !== i))}
                          aria-label={`ลบรูปที่ ${i + 1}`}
                        >
                          ×
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              {error && (
                <div className="ph-alert ph-alert-danger" role="alert">{error}</div>
              )}

              {/* กันแจ้งซ้ำ: รายละเอียดงานค้าง + ช่องแจ้งอาการเพิ่มเข้าใบเดิม
                  อยู่ในกล่องเหนือฟอร์ม (blocking) แล้ว ไม่ซ้ำที่นี่อีก */}

              <button
                type="submit"
                className="ph-btn ph-btn-primary pr-btn-full pr-btn-submit"
                disabled={submitting}
              >
                {submitting ? <span className="ph-spinner" aria-hidden="true" /> : <SendIcon />}
                <span>{submitting ? 'กำลังส่ง...' : 'ส่งคำร้องแจ้งซ่อม'}</span>
              </button>
            </form>

            <div className="pr-back-row">
              <button type="button" className="pr-link-btn" onClick={() => { window.location.href = '/'; }}>
                <BackIcon />
                <span>กลับหน้าแรก</span>
              </button>
            </div>
          </section>
        )}
      </main>

      <footer className="ph-footer">
        <span className="ph-footer-brand">IWA Smart Classroom Support</span>
        <a href="/?login=1">เข้าสู่ระบบเจ้าหน้าที่</a>
      </footer>
    </div>
  );
}