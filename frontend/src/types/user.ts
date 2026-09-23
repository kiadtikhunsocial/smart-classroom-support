export interface User {
  id: number;
  line_user_id: string;
  line_display_name: string | null;
  line_picture_url: string | null;
  line_email: string | null;
  organization_id: number | null;
  role: UserRole;
  is_active: boolean;
  last_login_at: string | null;
  created_at: string;
  organization?: Organization | null;
}

// บทบาทที่ใช้งานได้จริง — teacher/student ถูกยกเลิกแล้ว (ผู้แจ้งซ่อมไม่ต้องมีบัญชี)
export type UserRole = 'owner' | 'super_admin' | 'admin' | 'admin_school' | 'it_support';

// บทบาทเก่าที่ยังพบได้ในบัญชีที่สร้างไว้ก่อนหน้า — ใช้เฉพาะตอนแสดงผล
export type LegacyUserRole = 'teacher' | 'student';

/** role ที่มาจาก API อาจเป็นบทบาทเก่าได้ ใช้ชนิดนี้เวลาอ่านค่าดิบ */
export type AnyUserRole = UserRole | LegacyUserRole;

export interface Organization {
  id: number;
  code: string;
  name: string;
  short_name: string | null;
  timezone: string;
}

export interface AuthState {
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
}