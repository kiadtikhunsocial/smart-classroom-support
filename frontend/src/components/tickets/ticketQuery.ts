/**
 * ตรรกะล้วนของหน้าใบงาน: แปลงตัวกรองเป็นพารามิเตอร์ API, คำนวณหน้า, นับตัวเลขบนแท็บ
 * แยกจากคอมโพเนนต์เพื่อให้เทสต์ได้ (ticketQuery.test.ts)
 */

export const PAGE_SIZE = 20;

export type TicketTabId = 'all' | 'new' | 'assigned' | 'in_progress' | 'waiting' | 'resolved' | 'done';

/** แท็บสถานะ — แต่ละแท็บรวมได้หลายสถานะ (ส่งไป API แบบคั่นจุลภาค) */
export const TICKET_TABS: { id: TicketTabId; label: string; statuses: string[] }[] = [
  { id: 'all', label: 'ทั้งหมด', statuses: [] },
  { id: 'new', label: 'รอรับเรื่อง', statuses: ['new'] },
  { id: 'assigned', label: 'มอบหมายแล้ว', statuses: ['assigned'] },
  { id: 'in_progress', label: 'กำลังซ่อม', statuses: ['in_progress'] },
  { id: 'waiting', label: 'รออะไหล่/ผู้ใช้', statuses: ['pending', 'waiting_parts', 'waiting_user'] },
  { id: 'resolved', label: 'ซ่อมเสร็จ', statuses: ['resolved'] },
  { id: 'done', label: 'ปิดแล้ว', statuses: ['closed', 'cancelled'] },
];

export interface TicketFilters {
  q: string;
  tab: TicketTabId;
  priority: string;
  deviceType: string;
  deviceCategory: string;
  organizationId: string;
}

export const EMPTY_FILTERS: TicketFilters = {
  q: '',
  tab: 'all',
  priority: '',
  deviceType: '',
  deviceCategory: '',
  organizationId: '',
};

function tabStatuses(tab: TicketTabId): string[] {
  return TICKET_TABS.find((t) => t.id === tab)?.statuses ?? [];
}

/** พารามิเตอร์ของ GET /api/tickets — ตัดค่าว่างทิ้ง, หน้าเริ่มที่ 1 */
export function buildTicketParams(f: TicketFilters, page: number): Record<string, string> {
  const params: Record<string, string> = {};
  const q = f.q.trim();
  if (q) params.q = q;
  const statuses = tabStatuses(f.tab);
  if (statuses.length) params.status = statuses.join(',');
  if (f.priority) params.priority = f.priority;
  if (f.deviceType) params.device_type = f.deviceType;
  if (f.deviceCategory) params.device_category = f.deviceCategory;
  if (f.organizationId) params.organization_id = f.organizationId;
  params.limit = String(PAGE_SIZE);
  params.offset = String((Math.max(1, page) - 1) * PAGE_SIZE);
  return params;
}

/** จำนวนหน้า — อย่างน้อย 1 เสมอ (ไม่มีรายการก็ยังเป็น "หน้า 1 จาก 1") */
export function pageCount(total: number): number {
  return Math.max(1, Math.ceil(total / PAGE_SIZE));
}

/** หน้าที่ใช้ได้จริง — เช่น ลบ/เปลี่ยนสถานะจนหน้า 3 ว่าง ให้ถอยไปหน้าสุดท้ายที่มีรายการ */
export function clampPage(page: number, total: number): number {
  return Math.min(Math.max(1, page), pageCount(total));
}

export function tabCount(tab: TicketTabId, byStatus: Record<string, number>, total: number): number {
  const statuses = tabStatuses(tab);
  if (!statuses.length) return total;
  return statuses.reduce((sum, s) => sum + (byStatus[s] ?? 0), 0);
}

/** จำนวนตัวกรองแบบ dropdown ที่เลือกไว้ (ไม่นับคำค้นและแท็บ — สองอย่างนั้นมองเห็นอยู่แล้ว) */
export function activeFilterCount(f: TicketFilters): number {
  return [f.priority, f.deviceType, f.deviceCategory, f.organizationId].filter(Boolean).length;
}
