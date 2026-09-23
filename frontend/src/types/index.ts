import { Organization, User } from './user';

export interface DeviceInfo {
  device_id: string;
  device_type: string;
  brand: string | null;
  model: string | null;
  serial_number: string | null;
  room_name: string | null;
  room_code: string | null;
  organization_id: number | null;
  organization_name: string | null;
  organization?: Organization | null;
  room?: Room | null;
  status: string | null;
  page_role?: string | null;
  gps_lat?: number | null;
  gps_lng?: number | null;
  support_contact?: string | null;
}

/** หมวดหมู่อุปกรณ์ 1 หมวด จาก /api/public/options (ตรงกับ DeviceCategoryOut)
 *
 *  backend ส่งมาครบทุกหมวดเสมอและเรียงคงที่ เพื่อให้ตัวเลือกบนหน้าเว็บไม่สลับที่
 *  ทุกครั้งที่โหลด ส่วน device_count = จำนวนอุปกรณ์ของหน่วยงานนั้นในหมวดนี้
 *  (0 = หน้าเว็บเลือกซ่อนหมวดนั้นได้เอง)
 */
export interface DeviceCategoryOption {
  category: string;
  device_types: string[];
  device_count: number;
}

/** อุปกรณ์เท่าที่ endpoint สาธารณะส่งออกได้ (ตรงกับ PublicDeviceInfo ใน backend)
 *
 *  จงใจไม่มี qr_token / qr_url / serial_number / firmware_version /
 *  warranty_until / notes / gps_lat / gps_lng — endpoint นี้ไม่ต้อง auth
 *  ห้ามเพิ่มฟิลด์เหล่านั้นที่นี่ (backend มีเทสต์ล็อกรายการคีย์ไว้ใน
 *  backend/test_public_options.py)
 */
export interface PublicDeviceInfo {
  device_id: string;
  device_type: string;
  /** หมวดหมู่ที่ map จาก device_type — ใช้จัดกลุ่มตัวเลือก */
  device_category: string | null;
  /** ชื่อที่คนอ่านรู้เรื่อง: ประเภท · ยี่ห้อรุ่น · ห้อง (ไม่ใช่รหัสเปล่า ๆ) */
  device_label: string | null;
  brand: string | null;
  model: string | null;
  status: string;
  room_code: string | null;
  room_name: string | null;
  building: string | null;
  floor: string | null;
  organization_code: string;
  organization_name: string;
  organization_id: number | null;
}

/** ผลของ GET /api/public/options
 *
 *  requires_organization = true หมายถึงยังไม่ได้ระบุรหัสหน่วยงาน devices จะว่าง
 *  เสมอ (กันการไล่ดูผังอุปกรณ์ของทุกโรงเรียนโดยไม่ต้องล็อกอิน) แต่ device_types
 *  และ device_categories ยังส่งมาให้ใช้ในโหมดกรอกเอง
 */
export interface PublicOptions {
  organization_code: string | null;
  organization_name: string | null;
  requires_organization: boolean;
  device_types: string[];
  device_categories: DeviceCategoryOption[];
  devices: PublicDeviceInfo[];
}

export interface Ticket {
  /** หมวดหมู่อุปกรณ์ (map จาก device_type ที่ backend) — ใช้จัดกลุ่ม/กรองงานซ่อม */
  device_category?: string | null;
  /** ชื่ออุปกรณ์แบบอ่านรู้เรื่อง: ประเภท · ยี่ห้อรุ่น · ห้อง (ไม่ใช่รหัสเปล่า ๆ) */
  device_label?: string | null;
  /** โรงเรียนเจ้าของอุปกรณ์ — ใช้จัดกลุ่ม/กรองงานเป็นหมวดโรงเรียน (prefix ของเลข Ticket ตรงกับ organization_code) */
  organization_id?: number | null;
  organization_code?: string | null;
  organization_name?: string | null;
  ticket_id: string;
  device_id: string;
  device_type?: string;
  title: string;
  description: string;
  status: string;
  priority: string;
  reporter_name: string | null;
  reporter_email: string | null;
  reporter_phone: string | null;
  reporter_type: string | null;
  assigned_to: number | null;
  assigned_user?: User | null;
  created_by: number | null;
  created_by_user?: User | null;
  created_at: string;
  updated_at: string;
  closed_at: string | null;
  scan_timestamp?: string | null;
  scan_gps_lat?: number | null;
  scan_gps_lng?: number | null;
}

export interface TicketUpdate {
  id: number;
  ticket_id: string;
  note: string;
  status: string;
  created_by: number | null;
  created_at: string;
}

export interface TicketCreate {
  device_id?: string;
  title: string;
  description?: string;
  reporter_name?: string;
  reporter_email?: string;
  reporter_phone?: string;
  reporter_type?: string;
  priority?: string;
  channel?: string;
  symptom_code?: string;
  ai_session_id?: string;
  attachments?: string[];
  scan_gps_lat?: number | null;
  scan_gps_lng?: number | null;
  scan_timestamp?: string;
  scan_user_agent?: string;
}

export interface TicketUpdateCreate {
  ticket_id: string;
  note?: string;
  status?: string;
}

export interface Stats {
  total_devices: number;
  total_tickets: number;
  open: number;
  new: number;
  assigned: number;
  in_progress: number;
  waiting_parts: number;
  waiting_user: number;
  resolved: number;
  closed: number;
  cancelled: number;
  pending: number;
  low: number;
  normal: number;
  high: number;
  critical: number;
  by_type: Record<string, number>;
  by_status: Record<string, number>;
  by_priority: Record<string, number>;
  devices_by_status: Record<string, number>;
  self_service_total?: number;
  recent_tickets: Ticket[];
  organization_id?: number | null;
}

export interface DeviceCreate {
  device_id?: string;
  device_type?: string;
  brand?: string;
  model?: string;
  serial_number?: string;
  room_id?: number;
  organization_id?: number;
  status?: string;
}

export type DevicePageRole = 'owner' | 'admin' | 'admin_school' | 'it_support' | 'super_admin' | 'none';

export const DEVICE_PAGE_ROLES: Record<DevicePageRole | string, string> = {
  owner: 'Owner',
  admin: 'admin',
  admin_school: 'School Admin',
  it_support: 'IT Support',
  super_admin: 'Super Admin',
  none: '—',
  '': '—',
};

export const DEVICE_PAGE_ROLE_BADGE: Record<DevicePageRole | string, string> = {
  owner: 'owner',
  admin: 'admin',
  admin_school: 'admin_school',
  it_support: 'it_support',
  super_admin: 'super_admin',
  none: 'none',
  '': 'none',
};

export interface Room {
  id: number;
  name: string;
  code: string;
  organization_id: number;
  organization?: Organization | null;
  device_count?: number;
}
