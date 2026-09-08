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

export interface Ticket {
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
  completed: number;
  resolved: number;
  closed: number;
  cancelled: number;
  pending: number;
  low: number;
  normal: number;
  medium: number;
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

export type DevicePageRole = 'admin' | 'teacher' | 'it_support' | 'student' | 'super_admin' | 'none';

export const DEVICE_PAGE_ROLES: Record<DevicePageRole | string, string> = {
  admin: 'admin',
  teacher: 'teacher',
  it_support: 'IT Support',
  student: 'Student',
  super_admin: 'Super Admin',
  none: '—',
  '': '—',
};

export const DEVICE_PAGE_ROLE_BADGE: Record<DevicePageRole | string, string> = {
  admin: 'admin',
  teacher: 'teacher',
  it_support: 'it_support',
  student: 'student',
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
