// ศูนย์รวม label + color สถานะ ticket (ตรงกับคู่มือข้อ 9)
export const STATUS_LABEL: Record<string, string> = {
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
 * สีสถานะอ้าง CSS variable ของธีม (styles/theme-tokens.css) โดยตรง
 * ค่าเหล่านี้ถูกใช้เป็น CSS property (backgroundColor) จึงขยาย var() ได้
 * และเปลี่ยนตามโหมดสว่าง/มืดเองโดยไม่ต้อง re-render
 * หมายเหตุ: ถ้าต้องส่งค่าเข้า attribute ของ <svg> (เช่น recharts fill/stroke)
 * ให้แปลงด้วย themeColor() จาก theme.ts ก่อน เพราะ SVG attribute ไม่รู้จัก var()
 */
export const STATUS_COLOR: Record<string, string> = {
  new: 'var(--status-new, #e53e3e)',
  assigned: 'var(--status-assigned, #dd6b20)',
  in_progress: 'var(--status-in-progress, #d69e2e)',
  pending: 'var(--status-pending, #718096)',
  waiting_parts: 'var(--status-waiting-parts, #3182ce)',
  waiting_user: 'var(--status-waiting-user, #805ad5)',
  resolved: 'var(--status-resolved, #38a169)',
  closed: 'var(--status-closed, #718096)',
  cancelled: 'var(--status-cancelled, #c53030)',
};

// รายการสถานะที่ใช้เปลี่ยนได้ (สำหรับ dropdown ในหน้าจัดการงาน)
export const STATUS_OPTIONS = [
  'new', 'assigned', 'in_progress', 'pending', 'waiting_parts', 'waiting_user', 'resolved', 'closed', 'cancelled',
];
