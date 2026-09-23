import { User } from '../types/user';
import type { PublicOptions } from '../types';

// ─── API base URL ───────────────────────────────────────────────────────
// ลำดับ: ค่าที่ฝังตอน build (__VITE_API_URL__) → import.meta.env → same-origin '/api'
// ห้าม fallback เป็น http://localhost:8000/api: build ที่ deploy แล้วจะยิงไป localhost
// ของเครื่องผู้ใช้ปลายทาง (เบราว์เซอร์บล็อก mixed content) ซึ่งเป็นต้นเหตุที่ล็อกอินไม่ผ่าน
// ส่วน dev ยังใช้ '/api' ได้เพราะ vite proxy ส่งต่อไป localhost:8000 ให้อยู่แล้ว
function resolveApiBase(): string {
  const injected = typeof __VITE_API_URL__ === 'string' ? __VITE_API_URL__ : '';
  const fromEnv =
    typeof import.meta.env?.VITE_API_URL === 'string' ? import.meta.env.VITE_API_URL : '';
  const explicit = (injected || fromEnv).trim().replace(/\/+$/, '');
  return explicit || '/api';
}

export const API_BASE = resolveApiBase();

const BASE = API_BASE;

function resolveUploadUrl(url: string): string {
  if (!url.startsWith('/uploads/') || !/^https?:\/\//i.test(BASE)) return url;
  try {
    return new URL(url, new URL(BASE).origin).toString();
  } catch {
    return url;
  }
}

// ─── Token helpers ──────────────────────────────────────────────────────
export function getToken(): string | null {
  return localStorage.getItem('sc_token');
}

export function setToken(token: string | null) {
  if (token) localStorage.setItem('sc_token', token);
  else localStorage.removeItem('sc_token');
}

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const token = getToken();
  const res = await fetch(`${BASE}${path}`, {
    headers: {
      'Content-Type': 'application/json',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    cache: 'no-store',
    ...options,
  });
  if (!res.ok) {
    const body = await res.text();
    let parsed: any = null;
    try { parsed = JSON.parse(body); } catch {}
    const detail = parsed?.detail ?? parsed ?? body;
    const err: any = new Error(
      typeof detail === 'string' ? detail : (detail?.message || `HTTP ${res.status}`)
    );
    err.status = res.status;
    err.code = typeof detail === 'object' && detail !== null ? detail.code : undefined;
    err.detail = detail;
    throw err;
  }
  return res.json();
}

async function collectPages<T>(fetchPage: (offset: number, limit: number) => Promise<T[]>, limit: number): Promise<T[]> {
  const all: T[] = [];
  for (;;) {
    const page = await fetchPage(all.length, limit);
    all.push(...page);
    if (page.length < limit) return all;
  }
}

export const api = {
  getDevice: (deviceId: string) => request<any>(`/devices/${deviceId}`),

  createTicket: (data: any) =>
    request<any>('/tickets', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listTickets: (params?: { status?: string; priority?: string; device_id?: string; device_type?: string; device_category?: string; organization_id?: number; limit?: number; offset?: number }) => {
      const qs = new URLSearchParams();
      if (params?.status) qs.set('status', params.status);
      if (params?.priority) qs.set('priority', params.priority);
      if (params?.device_id) qs.set('device_id', params.device_id);
      if (params?.device_type) qs.set('device_type', params.device_type);
      if (params?.device_category) qs.set('device_category', params.device_category);
      if (params?.organization_id !== undefined) qs.set('organization_id', String(params.organization_id));
      if (params?.limit) qs.set('limit', String(params.limit));
      if (params?.offset !== undefined) qs.set('offset', String(params.offset));
      const q = qs.toString();
      return request<any[]>(`/tickets${q ? '?' + q : ''}`);
    },

  listAllTickets: (params?: { status?: string; priority?: string; device_id?: string; device_type?: string; device_category?: string; organization_id?: number }) =>
    collectPages((offset, limit) => api.listTickets({ ...params, offset, limit }), 200),

  getTicket: (ticketId: string) => request<any>(`/tickets/${ticketId}`),

  deleteTicket: (ticketId: string) =>
    request<any>(`/tickets/${ticketId}`, { method: 'DELETE' }),

  updateStatus: (ticketId: string, data: { status: string; note?: string; author_name?: string; force?: boolean }) =>
    request<any>(`/tickets/${ticketId}/status`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  getStats: () => request<any>('/stats'),

  listDevices: (limit: number = 100, organization_id?: number, offset: number = 0) =>
    request<any[]>(`/devices?limit=${limit}&offset=${offset}${organization_id ? `&organization_id=${organization_id}` : ''}`),

  listAllDevices: (organization_id?: number) =>
    collectPages((offset, limit) => api.listDevices(limit, organization_id, offset), 500),

  listOrganizations: () => request<any[]>('/organizations'),

  createOrganization: (data: { code: string; name: string; short_name?: string; timezone?: string }) =>
    request<any>('/organizations', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  deleteOrganization: (orgId: number) =>
    request<any>(`/organizations/${orgId}`, { method: 'DELETE' }),

  getOrgStats: (orgId: number) => request<any>(`/organizations/${orgId}/stats`),

  createDevice: (data: any) =>
    request<any>('/devices', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateDevice: (deviceId: string, data: any) =>
    request<any>(`/devices/${deviceId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteDevice: (deviceId: string) =>
    request<any>(`/devices/${deviceId}`, { method: 'DELETE' }),

  listUsers: () => request<any[]>('/users'),

  createUser: (data: any) =>
    request<any>('/users', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  updateUser: (userId: number, data: any) =>
    request<any>(`/users/${userId}`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  deleteUser: (userId: number) =>
    request<any>(`/users/${userId}`, { method: 'DELETE' }),

  // ─── Auth / Profile ────────────────────────────────────────────────
  authMe: () => request<{ user: User }>('/auth/me'),

  updateProfile: (data: { line_display_name?: string; username?: string; line_email?: string; line_picture_url?: string; password?: string }) =>
    request<{ token: string; user: User }>('/auth/profile', {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  // ─── Knowledge Base (KB) ───────────────────────────────────────────
  listKB: (params?: { q?: string; device_type?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.q) qs.set('q', params.q);
    if (params?.device_type) qs.set('device_type', params.device_type);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return request<any[]>(`/kb/articles${q ? '?' + q : ''}`);
  },

  getKB: (kbId: string) => request<any>(`/kb/articles/${kbId}`),

  createKB: (data: any) =>
    request<any>('/kb/articles', { method: 'POST', body: JSON.stringify(data) }),

  updateKB: (kbId: string, data: any) =>
    request<any>(`/kb/articles/${kbId}`, { method: 'PATCH', body: JSON.stringify(data) }),

  deleteKB: (kbId: string) =>
    request<any>(`/kb/articles/${kbId}`, { method: 'DELETE' }),

  // ─── AI Diagnose + Self-Service ────────────────────────────────────
  diagnose: (data: { device_id?: string; device_type?: string; symptom_text: string }) =>
    request<any>('/ai/diagnose', { method: 'POST', body: JSON.stringify(data) }),

  createSelfService: (data: any) =>
    request<any>('/self-service', { method: 'POST', body: JSON.stringify(data) }),

  listSelfService: (params?: { device_id?: string; limit?: number; offset?: number }) => {
    const q = new URLSearchParams();
    if (params?.device_id) q.set('device_id', params.device_id);
    if (params?.limit) q.set('limit', String(params.limit));
    if (params?.offset) q.set('offset', String(params.offset));
    const qs = q.toString();
    return request<any[]>(`/self-service${qs ? `?${qs}` : ''}`);
  },

  // ─── Uploads ───────────────────────────────────────────────────────
  upload: async (file: File): Promise<{ url: string }> => {
    const token = getToken();
    const fd = new FormData();
    fd.append('file', file);
    const uploadPath = token ? '/uploads' : '/public/uploads';
    const res = await fetch(`${BASE}${uploadPath}`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    });
    if (!res.ok) throw new Error('อัปโหลดรูปไม่สำเร็จ');
    const result = await res.json();
    return { ...result, url: resolveUploadUrl(result.url) };
  },

  // ─── SLA ───────────────────────────────────────────────────────────
  slaCheck: () => request<any>('/internal/sla/check'),

  // ─── Preventive Maintenance (Blueprint §38) ────────────────────────
  listPMPlans: () => request<any[]>('/pm/plans'),
  createPMPlan: (data: {
    name: string;
    device_type?: string;
    interval_days?: number;
    checklist?: any[];
    is_active?: boolean;
  }) => request<any>('/pm/plans', { method: 'POST', body: JSON.stringify(data) }),
  updatePMPlan: (planId: number, data: {
    name?: string;
    device_type?: string | null;
    interval_days?: number;
    checklist?: any[];
    is_active?: boolean;
  }) => request<any>(`/pm/plans/${planId}`, { method: 'PUT', body: JSON.stringify(data) }),
  deletePMPlan: (planId: number) =>
    request<any>(`/pm/plans/${planId}`, { method: 'DELETE' }),
  generatePMTasks: () => request<any>('/pm/generate', { method: 'POST' }),
  listPMTasks: (params?: {
    status?: string;
    device_id?: string;
    organization_id?: number;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.device_id) qs.set('device_id', params.device_id);
    if (params?.organization_id !== undefined) qs.set('organization_id', String(params.organization_id));
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return request<any[]>(`/pm/tasks${q ? '?' + q : ''}`);
  },
  submitPMTask: (taskId: number, data: { result?: any[]; photos?: string[] }) =>
    request<any>(`/pm/tasks/${taskId}/submit`, { method: 'POST', body: JSON.stringify(data) }),
  skipPMTask: (taskId: number, reason: string) =>
    request<any>(`/pm/tasks/${taskId}/skip`, { method: 'POST', body: JSON.stringify({ reason }) }),

  // ─── PM Rule Engine (Blueprint §38 — Rule 1/2/3) ───────────────────
  runPMRules: (organizationId?: number) => {
    const qs = new URLSearchParams();
    if (organizationId !== undefined) qs.set('organization_id', String(organizationId));
    const q = qs.toString();
    return request<any>(`/pm/rules/run${q ? '?' + q : ''}`, { method: 'POST' });
  },
  listHealthFlags: (params?: {
    status?: string;
    rule_code?: string;
    device_id?: string;
    organization_id?: number;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.rule_code) qs.set('rule_code', params.rule_code);
    if (params?.device_id) qs.set('device_id', params.device_id);
    if (params?.organization_id !== undefined) qs.set('organization_id', String(params.organization_id));
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return request<any[]>(`/pm/flags${q ? '?' + q : ''}`);
  },
  updateHealthFlag: (flagId: number, status: 'acknowledged' | 'resolved') =>
    request<any>(`/pm/flags/${flagId}`, { method: 'PATCH', body: JSON.stringify({ status }) }),

  // ─── Audit Log (Blueprint §40) ─────────────────────────────────────
  listAuditLogs: (params?: {
    action?: string;
    entity_type?: string;
    entity_id?: string;
    user_id?: number;
    /** วันที่เริ่ม (YYYY-MM-DD) — นับรวมวันนั้นทั้งวัน */
    date_from?: string;
    /** วันที่สิ้นสุด (YYYY-MM-DD) — นับรวมวันนั้นทั้งวัน */
    date_to?: string;
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.action) qs.set('action', params.action);
    if (params?.entity_type) qs.set('entity_type', params.entity_type);
    if (params?.entity_id) qs.set('entity_id', params.entity_id);
    if (params?.user_id !== undefined) qs.set('user_id', String(params.user_id));
    if (params?.date_from) qs.set('date_from', params.date_from);
    if (params?.date_to) qs.set('date_to', params.date_to);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return request<any[]>(`/audit-logs${q ? '?' + q : ''}`);
  },

  // ─── QR ────────────────────────────────────────────────────────────
  qrResolve: (token: string) => request<any>(`/qr/resolve/${token}`),
  qrRotate: (deviceId: string) =>
    request<any>(`/qr/rotate/${deviceId}`, { method: 'POST' }),
  qrLookup: (q: string) => request<any[]>(`/qr/lookup?q=${encodeURIComponent(q)}`),
  qrBatch: (organization_id?: number) =>
    request<any[]>(`/qr/batch${organization_id ? `?organization_id=${organization_id}` : ''}`),
  roomDevices: (roomId: number) => request<any>(`/rooms/${roomId}/devices`),

  // ─── Ticket ล่าสุดของอุปกรณ์ (ช่วยหาเลขคืนเมื่อลืม) ──────────────
  getDeviceRecent: (deviceId: string) => request<any>(`/devices/${encodeURIComponent(deviceId)}/recent`),

  checkWarranty: (code: string) => request<any>(`/public/warranty/${encodeURIComponent(code)}`),

  // ─── Ticket lifecycle actions (Batch 1 backend) ──────────────────
    trackTicket: (ticketNo: string) => request<any>(`/tickets/track/${encodeURIComponent(ticketNo)}`),
    assignTicket: (ticketId: string, data: { assignee: string; note?: string }) =>
      request<any>(`/tickets/${ticketId}/assign`, { method: 'POST', body: JSON.stringify(data) }),
    acceptTicket: (ticketId: string) =>
      request<any>(`/tickets/${ticketId}/accept`, { method: 'POST' }),
    resolveTicket: (ticketId: string, data: any) =>
      request<any>(`/tickets/${ticketId}/resolve`, { method: 'POST', body: JSON.stringify(data) }),
    closeTicket: (ticketId: string, data: { rating?: number; feedback?: string }) =>
      request<any>(`/tickets/${ticketId}/close`, { method: 'POST', body: JSON.stringify(data) }),
    reopenTicket: (ticketId: string, note: string) =>
      request<any>(`/tickets/${ticketId}/reopen`, { method: 'POST', body: JSON.stringify({ note }) }),
    cancelTicket: (ticketId: string, note: string) =>
      request<any>(`/tickets/${ticketId}/cancel`, { method: 'POST', body: JSON.stringify({ note }) }),
    listTicketComments: (ticketId: string) => request<any[]>(`/tickets/${ticketId}/comments`),
    addTicketComment: (ticketId: string, data: { note: string; is_internal?: boolean }) =>
      request<any>(`/tickets/${ticketId}/comments`, { method: 'POST', body: JSON.stringify(data) }),
    listTicketAttachments: (ticketId: string) => request<any[]>(`/tickets/${ticketId}/attachments`),

    // ─── Ticket history ─────────────────────────────────────────
    getTicketHistory: (ticketId: string) => request<any[]>(`/tickets/${encodeURIComponent(ticketId)}/history`),

    // ─── Reports + analytics ──────────────────────────────────
    reportSummary: (orgId?: number) => request<any>(`/reports/summary${orgId ? `?organization_id=${orgId}` : ''}`),
    reportTopIssues: (orgId?: number) => request<any>(`/reports/top-issues${orgId ? `?organization_id=${orgId}` : ''}`),
    reportTopDevices: (orgId?: number) => request<any>(`/reports/top-devices${orgId ? `?organization_id=${orgId}` : ''}`),
    getChatbotAnalytics: (days?: number) => request<any>(`/reports/chatbot-analytics${days != null ? `?days=${days}` : ''}`),

    // ─── Avg resolution time ──────────────────────────────────
    getAvgResolution: () => request<any>('/reports/avg-resolution'),

  // ─── Rooms / Buildings ───────────────────────────────────────────
  listRooms: (orgId: number) => request<any[]>(`/organizations/${orgId}/rooms`),
  createRoom: (orgId: number, data: any) =>
    request<any>(`/organizations/${orgId}/rooms`, { method: 'POST', body: JSON.stringify(data) }),
  listBuildings: (orgId: number) => request<any[]>(`/organizations/${orgId}/buildings`),
  createBuilding: (orgId: number, data: any) =>
    request<any>(`/organizations/${orgId}/buildings`, { method: 'POST', body: JSON.stringify(data) }),

  // ─── Public report (คนไม่มีบัญชี) ─────────────────────────────────────
  // ไม่ส่ง organization_code = ได้แต่ประเภทอุปกรณ์ (backend ไม่คืนรายการอุปกรณ์ให้ไล่ดู)
  publicOptions: (organizationCode?: string) => {
    const code = (organizationCode || '').trim();
    const qs = code ? `?organization_code=${encodeURIComponent(code)}` : '';
    return request<PublicOptions>(`/public/options${qs}`);
  },
  // อุปกรณ์นี้มีงานค้างอยู่ไหม — เช็คตอนสแกน ก่อนให้ผู้แจ้งกรอกฟอร์มทั้งใบ
  publicDeviceOpenTicket: (code: string) =>
    request<any>(`/public/devices/${encodeURIComponent(code)}/open-ticket`),

  // แจ้งอาการ/ข้อมูลเพิ่มเข้า Ticket เดิมที่ยังไม่ปิด (ไม่ต้องล็อกอิน) — แทนการแจ้งซ้ำ
  publicAddTicketNote: (
    ticketNo: string,
    data: { note: string; reporter_name: string; reporter_phone?: string; attachments?: string[] },
  ) =>
    request<any>(`/public/tickets/${encodeURIComponent(ticketNo)}/notes`, {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  // หมวดหมู่อุปกรณ์ + ประเภทในแต่ละหมวด — ใช้ทำตัวกรองหมวดหมู่ในหน้ารายการงาน
  listDeviceCategories: () =>
    request<{ categories: { category: string; device_types: string[] }[] }>(
      '/device-categories'
    ),

  publicReport: (data: any) =>
    request<any>('/public/report', { method: 'POST', body: JSON.stringify(data) }),

  // ─── Sales Leads + Chatbot Logs ──────────────────────────────────
  listSalesLeads: () => request<any[]>('/sales/leads'),
  // สมัครสมาชิกลูกค้าจากหน้าเว็บ — ไม่ต้อง login, บันทึกเป็น lead ช่องทาง WEB
  publicCustomerSignup: (data: {
    full_name: string;
    phone: string;
    email?: string;
    organization?: string;
    interest?: string;
    products?: string;
    note?: string;
    consent: boolean;
  }) =>
    request<{ id: number; duplicate: boolean; message: string }>(
      '/public/customer-signup',
      { method: 'POST', body: JSON.stringify(data) },
    ),
  markLeadContacted: (leadId: number) =>
    request<any>(`/sales/leads/${leadId}`, { method: 'PATCH', body: JSON.stringify({ status: 'contacted' }) }),
  deleteSalesLead: (leadId: number) =>
    request<any>(`/sales/leads/${leadId}`, { method: 'DELETE' }),
  // ─── สมัครสมาชิก (Membership) ────────────────────────────────────
  // /public/register ไม่ต้อง login — request() แนบ token ให้เฉพาะกรณีที่มีอยู่แล้ว
  publicRegister: (data: {
    username: string;
    password: string;
    full_name: string;
    email?: string;
    phone?: string;
    organization_code?: string;
    note?: string;
  }) =>
    request<{ id: number; status: string; sheet_synced: boolean; message: string }>(
      '/public/register',
      { method: 'POST', body: JSON.stringify(data) },
    ),

  listRegistrations: (params?: { status?: string; limit?: number; offset?: number }) => {
    const qs = new URLSearchParams();
    if (params?.status) qs.set('status', params.status);
    if (params?.limit) qs.set('limit', String(params.limit));
    if (params?.offset) qs.set('offset', String(params.offset));
    const q = qs.toString();
    return request<any[]>(`/registrations${q ? '?' + q : ''}`);
  },

  approveRegistration: (
    applicationId: number,
    data?: { role?: string; organization_id?: number },
  ) =>
    request<any>(`/registrations/${applicationId}/approve`, {
      method: 'POST',
      body: JSON.stringify(data ?? {}),
    }),

  rejectRegistration: (applicationId: number, reason?: string) =>
    request<any>(`/registrations/${applicationId}/reject`, {
      method: 'POST',
      body: JSON.stringify({ reason }),
    }),

  listChatbotLogs: () => request<any[]>('/chatbot/logs'),
};

// LINE Login — คืน {url} ถ้า backend มี LINE OAuth, คืน null ถ้ายังไม่มี endpoint
export async function lineLogin(): Promise<{ url?: string; user?: User } | null> {
  const res = await fetch(`${BASE}/auth/line/login`, {
    method: 'GET',
    credentials: 'include',
  });
  if (!res.ok) return null;
  return res.json();
}

// Login จริง (username + password) — คืน token + user
export async function login(username: string, password: string): Promise<{ token: string; user: User }> {
  try {
    return await loginRequest(username, password);
  } catch (err) {
    // fetch โยน TypeError เมื่อคำขอไปไม่ถึงเซิร์ฟเวอร์เลย (backend ปิด / CORS / mixed content)
    // ข้อความเดิม "Failed to fetch" ไม่บอกว่าต้องแก้อะไร
    if (err instanceof TypeError) {
      throw new Error(
        `ติดต่อเซิร์ฟเวอร์ที่ ${BASE} ไม่ได้ — ตรวจว่า backend เปิดอยู่ และตั้งค่า VITE_API_URL / CORS_ORIGINS ถูกต้อง`
      );
    }
    throw err;
  }
}

async function loginRequest(username: string, password: string): Promise<{ token: string; user: User }> {
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = (body as any)?.detail;
    throw new Error(
      typeof detail === 'string'
        ? detail
        : typeof detail?.message === 'string'
          ? detail.message
          : res.status === 401
            ? 'ชื่อผู้ใช้หรือรหัสผ่านไม่ถูกต้อง'
            : `HTTP ${res.status}`
    );
  }
  return body;
}
