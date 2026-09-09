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

export const STATUS_COLOR: Record<string, string> = {
  new: '#e53e3e',
  assigned: '#dd6b20',
  in_progress: '#d69e2e',
  pending: '#718096',
  waiting_parts: '#3182ce',
  waiting_user: '#805ad5',
  resolved: '#38a169',
  closed: '#718096',
  cancelled: '#c53030',
};

// รายการสถานะที่ใช้เปลี่ยนได้ (สำหรับ dropdown ในหน้าจัดการงาน)
export const STATUS_OPTIONS = [
  'new', 'assigned', 'in_progress', 'pending', 'waiting_parts', 'waiting_user', 'resolved', 'closed', 'cancelled',
];
