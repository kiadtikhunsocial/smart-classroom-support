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
export const ticketDetailChannel: Record<string, string> = { qr: 'สแกน QR', line: 'LINE OA', web: 'เว็บไซต์', manual: 'เจ้าหน้าที่', phone: 'โทรศัพท์' };
export const ticketDetailDate = (value: string | null | undefined) => {
  if (!value) return '—';
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? '—' : date.toLocaleString('th-TH', { timeZone: 'Asia/Bangkok' });
};
export const ALL_STATUSES = Object.keys(STATUS_LABELS_TICKET);
