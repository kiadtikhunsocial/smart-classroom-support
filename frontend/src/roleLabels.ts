// ─── ป้ายชื่อบทบาท (ใช้ร่วมกันทุกหน้า) ──────────────────────────────
// ก่อนหน้านี้แต่ละหน้าเขียน ternary เอง ทำให้ owner/admin_school ตกไปที่
// fallback "นักเรียน/นักศึกษา" — ใช้ map นี้แทนเสมอ
//
// บทบาท ครู (teacher) / นักเรียน (student) ถูกยกเลิกแล้ว: ผู้แจ้งซ่อมไม่ต้องมีบัญชี
// (ใช้หน้าแจ้งซ่อมสาธารณะ + สแกน QR ด้วยรหัสอุปกรณ์) จึงเหลือแต่บทบาทผู้ปฏิบัติงาน
// ยังคงป้ายกำกับของบทบาทเก่าไว้ใน LEGACY_ROLE_LABEL_TH เพื่อให้บัญชีเดิมในฐานข้อมูล
// ไม่แสดงเป็นรหัสดิบ และผู้ดูแลรู้ว่าต้องย้ายบทบาท
export const ROLE_LABEL_TH: Record<string, string> = {
  owner: 'เจ้าของระบบ (Owner)',
  super_admin: 'ผู้ดูแลระบบสูงสุด',
  admin: 'ผู้ดูแลบริษัท',
  admin_school: 'ผู้ดูแลโรงเรียน',
  it_support: 'เจ้าหน้าที่ IT',
};

export const ROLE_LABEL_FULL_TH: Record<string, string> = {
  owner: 'เจ้าของระบบ (Owner)',
  super_admin: 'ผู้ดูแลระบบสูงสุด (Super Admin)',
  admin: 'ผู้ดูแลบริษัท (Admin)',
  admin_school: 'ผู้ดูแลโรงเรียน (Admin School)',
  it_support: 'เจ้าหน้าที่ IT (IT Support)',
};

/** บทบาทที่เลิกใช้แล้ว — แสดงได้ แต่เลือกใหม่ไม่ได้ */
export const LEGACY_ROLE_LABEL_TH: Record<string, string> = {
  teacher: 'ครู (บทบาทที่เลิกใช้)',
  student: 'นักเรียน (บทบาทที่เลิกใช้)',
};

/** บทบาททั้งหมดที่กำหนดให้ผู้ใช้ได้ เรียงจากสิทธิ์มากไปน้อย */
export const ASSIGNABLE_ROLES: string[] = [
  'owner',
  'super_admin',
  'admin',
  'admin_school',
  'it_support',
];

/** บทบาทที่ถูกยกเลิก — ตรงกับ RETIRED_ROLES ฝั่ง backend */
export const RETIRED_ROLES: string[] = ['teacher', 'student'];

/** true ถ้าบทบาทนี้เลิกใช้แล้ว (บัญชีเก่าที่ยังไม่ถูกย้าย) */
export function isRetiredRole(role?: string | null): boolean {
  return !!role && RETIRED_ROLES.includes(role);
}

/** ป้ายชื่อบทบาทแบบสั้น — ไม่รู้จัก role → คืนค่า role เดิม */
export function roleLabel(role?: string | null): string {
  if (!role) return '—';
  return ROLE_LABEL_TH[role] ?? LEGACY_ROLE_LABEL_TH[role] ?? role;
}

/** ป้ายชื่อบทบาทแบบเต็ม (มีคำอังกฤษกำกับ) */
export function roleLabelFull(role?: string | null): string {
  if (!role) return '—';
  return ROLE_LABEL_FULL_TH[role] ?? LEGACY_ROLE_LABEL_TH[role] ?? role;
}

/** บทบาทที่เห็นข้อมูลทุกโรงเรียน (global scope) */
export const GLOBAL_SCOPE_ROLES = ['owner', 'super_admin', 'admin'];

/** บทบาทที่จัดการอุปกรณ์/QR/ticket ได้ — owner มีสิทธิ์เต็ม */
export const MANAGE_ROLES = ['owner', 'super_admin', 'admin', 'it_support', 'admin_school'];

/** บทบาทที่จัดการแผน PM ได้ทั้งหมด (สร้าง/แก้ไข/ลบ/ปิดงาน) */
export const PM_MANAGE_ROLES = ['owner', 'super_admin', 'admin', 'it_support'];

/** true = แก้ไขแผน PM ได้ทุกอย่าง (super_admin เทียบเท่า owner ในงาน PM) */
export function canManagePM(role?: string | null): boolean {
  return !!role && PM_MANAGE_ROLES.includes(role);
}