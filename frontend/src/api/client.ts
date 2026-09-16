import { User } from '../types/user';

const BASE = (typeof __VITE_API_URL__ !== 'undefined' ? __VITE_API_URL__ : import.meta.env.VITE_API_URL) || 'http://localhost:8000/api';

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

export const api = {
  getDevice: (deviceId: string) => request<any>(`/devices/${deviceId}`),

  createTicket: (data: any) =>
    request<any>('/tickets', {
      method: 'POST',
      body: JSON.stringify(data),
    }),

  listTickets: (params?: { status?: string; priority?: string; device_id?: string; organization_id?: number; limit?: number }) => {
      const qs = new URLSearchParams();
      if (params?.status) qs.set('status', params.status);
      if (params?.priority) qs.set('priority', params.priority);
      if (params?.device_id) qs.set('device_id', params.device_id);
      if (params?.organization_id !== undefined) qs.set('organization_id', String(params.organization_id));
      if (params?.limit) qs.set('limit', String(params.limit));
      const q = qs.toString();
      return request<any[]>(`/tickets${q ? '?' + q : ''}`);
    },

  getTicket: (ticketId: string) => request<any>(`/tickets/${ticketId}`),

  deleteTicket: (ticketId: string) =>
    request<any>(`/tickets/${ticketId}`, { method: 'DELETE' }),

  updateStatus: (ticketId: string, data: { status: string; note?: string; author_name?: string; force?: boolean }) =>
    request<any>(`/tickets/${ticketId}/status`, {
      method: 'PATCH',
      body: JSON.stringify(data),
    }),

  getStats: () => request<any>('/stats'),

  listDevices: (limit: number = 100, organization_id?: number) =>
    request<any[]>(`/devices?limit=${limit}${organization_id ? `&organization_id=${organization_id}` : ''}`),

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

  updateProfile: (data: { line_display_name?: string; line_email?: string; line_picture_url?: string; password?: string }) =>
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
    const res = await fetch(`${BASE}/uploads`, {
      method: 'POST',
      headers: token ? { Authorization: `Bearer ${token}` } : {},
      body: fd,
    });
    if (!res.ok) throw new Error('อัปโหลดรูปไม่สำเร็จ');
    return res.json();
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
    limit?: number;
    offset?: number;
  }) => {
    const qs = new URLSearchParams();
    if (params?.action) qs.set('action', params.action);
    if (params?.entity_type) qs.set('entity_type', params.entity_type);
    if (params?.entity_id) qs.set('entity_id', params.entity_id);
    if (params?.user_id !== undefined) qs.set('user_id', String(params.user_id));
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
  publicOptions: () => request<any>('/public/options'),
  publicReport: (data: any) =>
    request<any>('/public/report', { method: 'POST', body: JSON.stringify(data) }),

  // ─── Sales Leads + Chatbot Logs ──────────────────────────────────
  listSalesLeads: () => request<any[]>('/sales/leads'),
  markLeadContacted: (leadId: number) =>
    request<any>(`/sales/leads/${leadId}`, { method: 'PATCH', body: JSON.stringify({ status: 'contacted' }) }),
  deleteSalesLead: (leadId: number) =>
    request<any>(`/sales/leads/${leadId}`, { method: 'DELETE' }),
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
  const res = await fetch(`${BASE}/auth/login`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ username, password }),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(body.detail || `HTTP ${res.status}`);
  }
  return body;
}
