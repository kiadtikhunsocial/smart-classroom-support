/**
 * ประเภทผู้แจ้ง (reporter_type) — แหล่งข้อมูลเดียวของทุกฟอร์มแจ้งซ่อม
 *
 * ครู/นักเรียน ถูกยกเลิกแล้ว จึงไม่มีให้เลือกอีกต่อไป
 * ค่า teacher/student ยังพบได้ใน ticket เก่าในฐานข้อมูล — ใช้ reporterTypeLabel()
 * เพื่อแสดงผลได้โดยไม่พัง
 */

export type ReporterType = 'staff' | 'it_admin' | 'other';

/** ค่าเริ่มต้นของฟอร์ม (เดิมเป็น 'teacher') */
export const DEFAULT_REPORTER_TYPE: ReporterType = 'staff';

export const REPORTER_TYPE_OPTIONS: ReadonlyArray<{ value: ReporterType; label: string }> = [
  { value: 'staff', label: 'เจ้าหน้าที่/บุคลากร' },
  { value: 'it_admin', label: 'เจ้าหน้าที่ IT' },
  { value: 'other', label: 'อื่นๆ / บุคคลภายนอก' },
];

/** ป้ายชื่อของค่าที่เลิกใช้แล้ว — มีเฉพาะ ticket เก่า */
const LEGACY_REPORTER_TYPE_LABELS: Record<string, string> = {
  teacher: 'ครูผู้สอน (เลิกใช้)',
  student: 'นักเรียน/นักศึกษา (เลิกใช้)',
  public: 'ผู้แจ้งทั่วไป',
  technician: 'ช่างเทคนิค',
};

/** แปลงค่า reporter_type เป็นข้อความไทย; ค่าที่ไม่รู้จักคืนค่าเดิม */
export function reporterTypeLabel(value?: string | null): string {
  if (!value) return '-';
  const active = REPORTER_TYPE_OPTIONS.find((opt) => opt.value === value);
  if (active) return active.label;
  return LEGACY_REPORTER_TYPE_LABELS[value] ?? value;
}