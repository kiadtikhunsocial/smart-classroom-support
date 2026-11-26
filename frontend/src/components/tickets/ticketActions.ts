/**
 * ปุ่มขั้นตอนงานในแผงรายละเอียดใบงาน — กติกาตรงกับ endpoint ฝั่ง server:
 *   POST /tickets/{id}/accept   รับได้เฉพาะ new / assigned
 *   POST /tickets/{id}/resolve  ต้องมีวิธีแก้ไข 3–2000 ตัวอักษร
 *   POST /tickets/{id}/close    รับได้เฉพาะ resolved
 *   POST /tickets/{id}/reopen   รับได้เฉพาะ closed
 *   POST /tickets/{id}/cancel   ไม่รับ closed / cancelled
 * แสดงเฉพาะปุ่มที่ server จะยอมรับ เพื่อไม่ให้ผู้ใช้กดแล้วเจอ 409
 */

export type TicketActionId = 'accept' | 'resolve' | 'close' | 'reopen' | 'cancel';

export interface TicketAction {
  id: TicketActionId;
  label: string;
  kind: 'primary' | 'secondary';
  /** ต้องกรอกอะไรก่อนส่ง: none = กดแล้วทำเลย, solution = วิธีแก้ไข, note = เหตุผล */
  needs: 'none' | 'solution' | 'note';
}

const ACCEPT: TicketAction = { id: 'accept', label: 'รับงาน', kind: 'primary', needs: 'none' };
const RESOLVE: TicketAction = { id: 'resolve', label: 'บันทึกผลซ่อม', kind: 'primary', needs: 'solution' };
const CLOSE: TicketAction = { id: 'close', label: 'ปิดงาน', kind: 'primary', needs: 'none' };
const REOPEN: TicketAction = { id: 'reopen', label: 'เปิดงานใหม่', kind: 'secondary', needs: 'note' };
const CANCEL: TicketAction = { id: 'cancel', label: 'ยกเลิกงาน', kind: 'secondary', needs: 'note' };

const BY_STATUS: Record<string, TicketAction[]> = {
  new: [ACCEPT, CANCEL],
  assigned: [ACCEPT, CANCEL],
  in_progress: [RESOLVE, CANCEL],
  pending: [RESOLVE, CANCEL],
  waiting_parts: [RESOLVE, CANCEL],
  waiting_user: [RESOLVE, CANCEL],
  resolved: [CLOSE, CANCEL],
  closed: [REOPEN],
  cancelled: [],
};

export function actionsFor(status: string, canManage: boolean): TicketAction[] {
  if (!canManage) return [];
  return BY_STATUS[status] ?? [];
}

const MAX_LEN = 2000;

/** ข้อความผิดพลาดภาษาไทย หรือ null ถ้าส่งได้ — ขีดจำกัดตรงกับ TicketResolveReq / TicketCommentReq */
export function validateActionInput(action: TicketAction, input: { solution?: string; note?: string }): string | null {
  if (action.needs === 'solution') {
    const s = (input.solution ?? '').trim();
    if (s.length < 3) return 'กรุณากรอกวิธีแก้ไขอย่างน้อย 3 ตัวอักษร';
    if (s.length > MAX_LEN) return 'ข้อความยาวเกิน 2000 ตัวอักษร';
  }
  if (action.needs === 'note') {
    const n = (input.note ?? '').trim();
    if (!n) return 'กรุณาระบุเหตุผล';
    if (n.length > MAX_LEN) return 'ข้อความยาวเกิน 2000 ตัวอักษร';
  }
  return null;
}
