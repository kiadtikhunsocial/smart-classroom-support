// ─── ป้ายชื่อบทบาท (ใช้ร่วมกันทุกหน้า) ──────────────────────────────
// ก่อนหน้านี้แต่ละหน้าเขียน ternary เอง ทำให้ owner/admin_school ตกไปที่
// fallback "นักเรียน/นักศึกษา" — ใช้ map นี้แทนเสมอ
export const ROLE_LABEL_TH: Record<string, string> = {
  owner: 'เจ้าของระบบ (Owner)',
  super_admin: 'ผู้ดูแลระบบสูงสุด',
  admin: 'ผู้ดูแลบริษัท',
  admin_school: 'ผู้ดูแลโรงเรียน',
  it_support: 'เจ้าหน้าที่ IT',
  teacher: 'ครูผู้สอน',
  student: 'นักเรียน/นักศึกษา',
};

export const ROLE_LABEL_FULL_TH: Record<string, string> = {
  owner: 'เจ้าของระบบ (Owner)',
  super_admin: 'ผู้ดูแลระบบสูงสุด (Super Admin)',
  admin: 'ผู้ดูแลบริษัท (Admin)',
  admin_school: 'ผู้ดูแลโรงเรียน (Admin School)',
  it_support: 'เจ้าหน้าที่ IT (IT Support)',
  teacher: 'ครู (Teacher)',
  student: 'นักเรียน (Student)',
};

/** ป้ายชื่อบทบาทแบบสั้น — ไม่รู้จัก role → คืนค่า role เดิม */
export function roleLabel(role?: string | null): string {
  if (!role) return '—';
  return ROLE_LABEL_TH[role] ?? role;
}

/** ป้ายชื่อบทบาทแบบเต็ม (มีคำอังกฤษกำกับ) */
export function roleLabelFull(role?: string | null): string {
  if (!role) return '—';
  return ROLE_LABEL_FULL_TH[role] ?? role;
}

/** บทบาทที่เห็นข้อมูลทุกโรงเรียน (global scope) */
export const GLOBAL_SCOPE_ROLES = ['owner', 'super_admin', 'admin'];

/** บทบาทที่จัดการอุปกรณ์/QR/ticket ได้ — owner มีสิทธิ์เต็ม */
export const MANAGE_ROLES = ['owner', 'super_admin', 'admin', 'it_support', 'admin_school'];
