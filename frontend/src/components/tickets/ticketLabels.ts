// ป้ายสถานะ/ความเร่งด่วน/ช่องทาง และรูปแบบวันที่ของใบงาน — ย้ายมาจาก App.tsx
export const STATUS_LABELS_TICKET: Record<string, string> = {
  new: 'รอรับเรื่อง (New)', assigned: 'มอบหมายแล้ว (Assigned)', in_progress: 'กำลังดำเนินการ (In Progress)',
  pending: 'รออะไหล่/รอภายนอก (Pending)', waiting_parts: 'รออะไหล่ (Waiting for Parts)', waiting_user: 'รอผู้ใช้ (Waiting for User)',
  resolved: 'ซ่อมเสร็จ รอยืนยัน (Resolved)',
  closed: 'ปิดงาน (Closed)', cancelled: 'ยกเลิก (Cancelled)',
};
export const ticketDetailStatus = (value: string | null | undefined) =>
  value ? (STATUS_LABELS_TICKET[value] || value).split(' (')[0] : '—';
export const ticketDetailPriority: Record<string, string> = { low: 'ต่ำ', normal: 'ปกติ', high: 'สูง', critical: 'เร่งด่วนมาก' };
export const ticketDetailChannel: Record<string, string> = { qr: 'สแกน QR', line: 'LINE OA', web: 'เว็บไซต์', manual: 'เจ้าหน้าที่', phone: 'โทรศัพท์', public: 'ฟอร์มแจ้งซ่อมออนไลน์', chat: 'แชตบนเว็บ' };
/** เบอร์ไทย 10 หลัก → 081-234-5678 (รูปแบบอื่นคืนค่าเดิม) */
export const formatThaiPhone = (v: string | null | undefined) => {
  if (!v) return '';
  const d = String(v).replace(/\D/g, '');
  if (d.length === 10) return `--`;
  if (d.length === 9) return `--`;
  return String(v);
};
export const ticketDetailDate = (value: string | null | undefined) => {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('th-TH', { timeZone: 'Asia/Bangkok' });
};
export const ALL_STATUSES = Object.keys(STATUS_LABELS_TICKET);

/** วันที่แบบอ่านง่าย เช่น "พฤ. 17 ต.ค. 2569 · 10:09 น." (เวลาไทย) */
export const ticketDateLong = (value: string | null | undefined) => {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  const opts = { timeZone: 'Asia/Bangkok' } as const;
  const day = d.toLocaleDateString('th-TH', { ...opts, weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });
  const time = d.toLocaleTimeString('th-TH', { ...opts, hour: '2-digit', minute: '2-digit' });
  return `${day} · ${time} น.`;
};

/** ระยะเวลาจากตอนนี้ เช่น "3 ชม. ที่แล้ว" / "อีก 2 วัน" */
export const ticketRelative = (value: string | null | undefined, now = Date.now()) => {
  if (!value) return '';
  const t = new Date(value).getTime();
  if (Number.isNaN(t)) return '';
  const diff = t - now;
  const mins = Math.round(Math.abs(diff) / 60000);
  const span = mins < 1 ? 'ไม่ถึงนาที'
    : mins < 60 ? `${mins} นาที`
    : mins < 60 * 24 ? `${Math.round(mins / 60)} ชม.`
    : `${Math.round(mins / 1440)} วัน`;
  return diff < 0 ? `${span}ที่แล้ว` : `อีก ${span}`;
};
