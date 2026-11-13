/**
 * "งานแจ้งซ่อมของฉัน" — เลขใบงานที่เครื่องนี้เคยแจ้ง/เคยค้น เก็บใน localStorage
 * ผู้แจ้งไม่มีบัญชี จึงจำไว้ที่เบราว์เซอร์แทน: แจ้งเสร็จแล้วกลับมาหน้าแรกก็เห็นสถานะทันที ไม่ต้องจดเลข
 */
export const RECENT_KEY = 'sc_recent_tickets';
export const RECENT_MAX = 6;

export function loadRecent(): string[] {
  try {
    const raw = localStorage.getItem(RECENT_KEY);
    const arr = raw ? JSON.parse(raw) : [];
    if (!Array.isArray(arr)) return [];
    return arr.filter((x): x is string => typeof x === 'string' && x.trim() !== '').slice(0, RECENT_MAX);
  } catch {
    return [];
  }
}

export function saveRecent(no: string | null | undefined): string[] {
  const clean = (no || '').trim().toUpperCase();
  if (!clean || clean === '-') return loadRecent();
  const next = [clean, ...loadRecent().filter((x) => x !== clean)].slice(0, RECENT_MAX);
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch {
    // โหมดส่วนตัว/พื้นที่เต็ม — จำไม่ได้ก็ไม่เป็นไร ไม่ต้องขัดจังหวะผู้ใช้
  }
  return next;
}

export function forgetRecent(no: string): string[] {
  const next = loadRecent().filter((x) => x !== no.trim().toUpperCase());
  try {
    localStorage.setItem(RECENT_KEY, JSON.stringify(next));
  } catch { /* ignore */ }
  return next;
}

/** ข้อความที่ผู้ใช้พิมพ์เป็นเลขใบงานหรือไม่ — ไม่ใช่ก็ถือเป็นรหัสอุปกรณ์ (สติกเกอร์บนเครื่อง) */
export function looksLikeTicketNo(raw: string): boolean {
  return /^TK[.\-_]/i.test(raw.trim());
}
