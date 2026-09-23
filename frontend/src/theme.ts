/* ============================================================================
   theme.ts — แหล่งความจริงเดียวของธีม (โหมดสว่าง/มืด + สีเน้น)
   ----------------------------------------------------------------------------
   หลักการ:
   1. ค่าธีมถูกเก็บเป็น 2 มิติ: mode (light|dark) และ accent (purple|blue|...)
      แล้วเขียนลง <html data-mode="..." data-accent="..."> เท่านั้น
      สีจริงทั้งหมดอยู่ใน styles/theme-tokens.css → ไม่มีสีใน TS/TSX
   2. เปลี่ยนแล้วมีผลทันทีทั้งแอป เพราะ CSS variable ถูกผูกกับ attribute บน :root
      (sidebar / hero / ปุ่ม / การ์ด / badge อ่าน token เดียวกันหมด)
   3. recharts วาดสีเป็น attribute ของ <svg> ซึ่ง "ไม่" ขยาย var() ให้
      จึงต้องอ่านค่าที่คำนวณแล้วด้วย cssVar() และ re-render ชาร์ตเมื่อธีมเปลี่ยน
      (useThemeVersion) — ส่วน CSS property ปกติใช้ var() ได้ตรง ๆ
   ========================================================================== */

import { useCallback, useEffect, useState } from 'react';

export type ThemeMode = 'light' | 'dark';
export type AccentId = 'purple' | 'blue' | 'teal' | 'orange' | 'rose';

export interface ThemePrefs {
  mode: ThemeMode;
  accent: AccentId;
}

/**
 * ค่าเริ่มต้น = โหมดมืด + สีเน้นม่วง
 * ทำไมเป็นมืด: หน้าแรกถูกออกแบบเป็น dark navy + neon (dashboard-futuristic.css)
 * ซึ่งเลเยอร์ neon ผูกกับ [data-mode='dark'] → ถ้าเริ่มด้วยสว่างผู้ใช้ใหม่จะเห็น
 * แค่การ์ดแก้วจาง ๆ ไม่ใช่ดีไซน์จริงของระบบ
 * ผู้ใช้เดิมไม่ถูกเขียนทับ: readThemePrefs() อ่านค่าที่บันทึกไว้ก่อนเสมอ
 * และยังสลับกลับเป็นโหมดสว่างได้ที่หน้าตั้งค่า (โหมดสว่างยังรองรับครบ)
 */
export const DEFAULT_THEME: ThemePrefs = { mode: 'dark', accent: 'purple' };

export const THEME_MODES: { id: ThemeMode; label: string; hint: string }[] = [
  { id: 'light', label: 'โหมดสว่าง', hint: 'พื้นขาว อ่านง่ายในที่แสงจ้า' },
  { id: 'dark', label: 'โหมดมืด', hint: 'ถนอมตาเวลากลางคืน' },
];

/**
 * สีเน้นที่เลือกได้ — ค่า from/to ใช้เฉพาะแสดง swatch ในหน้าตั้งค่า
 * ตัวจริงที่ทาสีทั้งแอปอยู่ใน theme-tokens.css ([data-accent="..."])
 */
export const ACCENTS: {
  id: AccentId;
  label: string;
  from: string;
  to: string;
}[] = [
  { id: 'purple', label: 'ม่วง (ค่าเริ่มต้น)', from: '#4C3FD6', to: '#7B3FD6' },
  { id: 'blue', label: 'น้ำเงิน', from: '#1E63E9', to: '#38BDF8' },
  { id: 'teal', label: 'เขียวมิ้นต์', from: '#0D9488', to: '#22D3EE' },
  { id: 'orange', label: 'ส้ม', from: '#EA580C', to: '#F59E0B' },
  { id: 'rose', label: 'ชมพูกุหลาบ', from: '#E11D48', to: '#FB7185' },
];

/**
 * สีแถบเบราว์เซอร์/แถบสถานะบนมือถือ ต้องเดินตามธีมของแอป ไม่ใช่ของ OS
 * index.html ตั้งค่าเริ่มต้นเป็น navy ไว้ ฟังก์ชันนี้แก้ให้ตรงเมื่อสลับโหมด
 * (โหมดสว่างใช้สีพื้นของธีม ไม่ใช่สีเน้น เพื่อให้กลืนกับ header สีขาว)
 */
const CHROME_COLOR: Record<ThemeMode, string> = {
  dark: '#050B1C',
  light: '#F7F8FB',
};

function syncBrowserChrome(mode: ThemeMode): void {
  if (typeof document === 'undefined') return;
  let tag = document.querySelector<HTMLMetaElement>('meta[name="theme-color"]');
  if (!tag) {
    tag = document.createElement('meta');
    tag.name = 'theme-color';
    document.head.appendChild(tag);
  }
  tag.content = CHROME_COLOR[mode];
}

const STORAGE_KEY = 'sc_theme_prefs';
/** คีย์เดิมของหน้าตั้งค่ารุ่นก่อน (เก็บเป็นชื่อคลาส เช่น theme-dark) */
const LEGACY_STORAGE_KEY = 'sc_theme';
const THEME_EVENT = 'sc:themechange';

const MODE_IDS: ThemeMode[] = ['light', 'dark'];
const ACCENT_IDS: AccentId[] = ACCENTS.map((a) => a.id);

function isMode(value: unknown): value is ThemeMode {
  return typeof value === 'string' && (MODE_IDS as string[]).includes(value);
}

function isAccent(value: unknown): value is AccentId {
  return typeof value === 'string' && (ACCENT_IDS as string[]).includes(value);
}

/** ค่าที่ใช้อยู่จริงในหน้านี้ (sync กับ attribute บน <html> เสมอ) */
let currentPrefs: ThemePrefs = { ...DEFAULT_THEME };

/** อ่านค่าที่บันทึกไว้ พร้อมย้ายข้อมูลจากคีย์รุ่นเก่าให้อัตโนมัติ */
export function readThemePrefs(): ThemePrefs {
  if (typeof window === 'undefined') return { ...DEFAULT_THEME };

  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (raw) {
      const parsed: unknown = JSON.parse(raw);
      if (parsed && typeof parsed === 'object') {
        const obj = parsed as Record<string, unknown>;
        return {
          mode: isMode(obj.mode) ? obj.mode : DEFAULT_THEME.mode,
          accent: isAccent(obj.accent) ? obj.accent : DEFAULT_THEME.accent,
        };
      }
    }

    // ── ย้ายค่าจากรุ่นก่อน: theme-purple / theme-blue / theme-dark ──────────
    const legacy = window.localStorage.getItem(LEGACY_STORAGE_KEY);
    if (legacy === 'theme-dark') return { mode: 'dark', accent: 'purple' };
    if (legacy === 'theme-blue') return { mode: 'light', accent: 'blue' };
    if (legacy === 'theme-purple') return { mode: 'light', accent: 'purple' };
  } catch {
    /* localStorage ถูกปิด (โหมดส่วนตัว / นโยบายองค์กร) — ใช้ค่าเริ่มต้น */
  }

  return { ...DEFAULT_THEME };
}

/** ค่าธีมที่กำลังใช้อยู่ */
export function getThemePrefs(): ThemePrefs {
  return { ...currentPrefs };
}

/**
 * ทาธีมลง <html> + บันทึก + ประกาศให้คอมโพเนนต์ที่ต้อง re-render รู้
 * persist=false ใช้ตอนบูต เพื่อไม่เขียนไฟล์ค่าเดิมซ้ำ
 */
export function applyThemePrefs(prefs: ThemePrefs, persist = true): ThemePrefs {
  const next: ThemePrefs = {
    mode: isMode(prefs.mode) ? prefs.mode : DEFAULT_THEME.mode,
    accent: isAccent(prefs.accent) ? prefs.accent : DEFAULT_THEME.accent,
  };
  currentPrefs = next;

  if (typeof document !== 'undefined') {
    const root = document.documentElement;
    root.setAttribute('data-mode', next.mode);
    root.setAttribute('data-accent', next.accent);
    root.style.colorScheme = next.mode;
    // คลาสธีมรุ่นเก่าต้องถูกถอด ไม่งั้น token ของสองระบบชนกัน
    root.classList.remove('theme-purple', 'theme-blue', 'theme-dark');
    syncBrowserChrome(next.mode);
  }

  if (persist && typeof window !== 'undefined') {
    try {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
      window.localStorage.removeItem(LEGACY_STORAGE_KEY);
    } catch {
      /* บันทึกไม่ได้ก็ยังใช้ธีมในเซสชันนี้ได้ */
    }
  }

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new CustomEvent<ThemePrefs>(THEME_EVENT, { detail: next }));
  }

  return next;
}

/** เรียกครั้งเดียวก่อน render — กันหน้าจอกระพริบเป็นธีมผิด */
export function initTheme(): ThemePrefs {
  return applyThemePrefs(readThemePrefs(), false);
}

export function setThemeMode(mode: ThemeMode): void {
  applyThemePrefs({ ...getThemePrefs(), mode });
}

export function setAccent(accent: AccentId): void {
  applyThemePrefs({ ...getThemePrefs(), accent });
}

export function subscribeTheme(listener: (prefs: ThemePrefs) => void): () => void {
  if (typeof window === 'undefined') return () => undefined;
  const handler = (event: Event) => {
    const detail = (event as CustomEvent<ThemePrefs>).detail;
    listener(detail ?? getThemePrefs());
  };
  window.addEventListener(THEME_EVENT, handler);
  return () => window.removeEventListener(THEME_EVENT, handler);
}

/** hook หลัก: [ค่าที่ใช้อยู่, ฟังก์ชันอัปเดตบางส่วน] */
export function useTheme(): [ThemePrefs, (patch: Partial<ThemePrefs>) => void] {
  const [prefs, setPrefs] = useState<ThemePrefs>(() => getThemePrefs());

  useEffect(() => subscribeTheme(setPrefs), []);

  const update = useCallback((patch: Partial<ThemePrefs>) => {
    applyThemePrefs({ ...getThemePrefs(), ...patch });
  }, []);

  return [prefs, update];
}

/** ตัวนับสำหรับบังคับ re-render ชาร์ต (recharts อ่าน var() ไม่ได้) */
export function useThemeVersion(): number {
  const [version, setVersion] = useState(0);
  useEffect(() => subscribeTheme(() => setVersion((v) => v + 1)), []);
  return version;
}

/** อ่านค่า CSS variable ที่คำนวณแล้วจาก :root */
export function cssVar(name: string, fallback = ''): string {
  if (!name || typeof window === 'undefined' || typeof document === 'undefined') {
    return fallback;
  }
  const value = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return value || fallback;
}

/* ── แผนที่สี hardcode เดิม → token ปัจจุบัน ────────────────────────────────
   โค้ดเก่าส่งสีเป็นเลขฐานสิบหกตรง ๆ (เช่น '#7C3AED') อยู่หลายจุด
   ฟังก์ชัน themeColor/themeTint แปลงให้เป็นสีของธีมที่เลือกอยู่ โดยไม่ต้อง
   ไปแก้ทุกบรรทัดที่ส่งสีเข้ามา และยังคืนค่าเดิมถ้าเจอสีที่ไม่รู้จัก */
const LEGACY_HEX_TO_VAR: Record<string, string> = {
  '#7c3aed': '--color-primary',
  '#5b5bd6': '--color-primary',
  '#6d28d9': '--color-primary-dark',
  '#8b5cf6': '--status-pending',
  '#2563eb': '--status-in-progress',
  '#1e63e9': '--status-in-progress',
  '#2b6cb0': '--status-in-progress',
  '#f59e0b': '--status-assigned',
  '#c77700': '--color-warning',
  '#10b981': '--status-resolved',
  '#0f9d6e': '--color-success',
  '#ef4444': '--status-new',
  '#dc2b3f': '--color-danger',
  '#6b7280': '--color-muted',
  '#ec4899': '--chart-6',
  '#0ea5e9': '--chart-7',
  '#f97316': '--chart-10',
};

/** คืนสีจริงของธีมปัจจุบันจากชื่อ token, var(...) หรือสี hardcode เดิม */
export function themeColor(input?: string | null, fallback = ''): string {
  const value = (input ?? '').trim();
  if (!value) return fallback || cssVar('--color-muted', '#6B7280');

  if (value.startsWith('--')) return cssVar(value, fallback || value);

  const varMatch = /^var\(\s*(--[\w-]+)\s*(?:,\s*([^)]+))?\)$/.exec(value);
  if (varMatch) return cssVar(varMatch[1], (varMatch[2] || fallback).trim());

  const token = LEGACY_HEX_TO_VAR[value.toLowerCase()];
  if (token) return cssVar(token, value);

  return value;
}

function parseRgb(color: string): [number, number, number] | null {
  const value = color.trim();

  const hex = /^#([0-9a-f]{3,8})$/i.exec(value);
  if (hex) {
    let h = hex[1];
    if (h.length === 3 || h.length === 4) {
      h = h
        .slice(0, 3)
        .split('')
        .map((c) => c + c)
        .join('');
    }
    if (h.length >= 6) {
      return [
        parseInt(h.slice(0, 2), 16),
        parseInt(h.slice(2, 4), 16),
        parseInt(h.slice(4, 6), 16),
      ];
    }
    return null;
  }

  // รองรับทั้ง rgb(1, 2, 3) และ rgb(1 2 3 / 0.5)
  const rgb = /^rgba?\(([^)]+)\)$/i.exec(value);
  if (rgb) {
    const parts = rgb[1]
      .replace(/\//g, ' ')
      .split(/[\s,]+/)
      .filter(Boolean)
      .map(Number);
    if (parts.length >= 3 && parts.slice(0, 3).every((n) => Number.isFinite(n))) {
      return [parts[0], parts[1], parts[2]];
    }
  }

  return null;
}

/** สีโปร่งแสงสำหรับพื้นหลังไอคอน/แท็ก — ผูกกับสีธีมเช่นเดียวกับ themeColor */
export function themeTint(input?: string | null, alpha = 0.12): string {
  const resolved = themeColor(input);
  const rgb = parseRgb(resolved);
  if (!rgb) return resolved;
  const a = Math.min(Math.max(alpha, 0), 1);
  return `rgba(${rgb[0]}, ${rgb[1]}, ${rgb[2]}, ${a})`;
}

const CHART_FALLBACK = [
  '#7C3AED', '#2563EB', '#10B981', '#F59E0B', '#EF4444',
  '#EC4899', '#0EA5E9', '#8B5CF6', '#6B7280', '#F97316',
];

/** จานสีของชาร์ต (สีแรกคือสีเน้นของธีม) */
export function chartPalette(): string[] {
  return CHART_FALLBACK.map((fallback, i) => cssVar(`--chart-${i + 1}`, fallback));
}

/** สีของเส้นกริด/แกน/ทูลทิป เพื่อให้ชาร์ตอ่านออกทั้งสองโหมด */
export function chartTokens(): {
  grid: string;
  axis: string;
  tooltipBg: string;
  tooltipBorder: string;
  tooltipText: string;
} {
  return {
    grid: cssVar('--chart-grid', '#E7E7F0'),
    axis: cssVar('--chart-axis', '#86868F'),
    tooltipBg: cssVar('--color-surface', '#FFFFFF'),
    tooltipBorder: cssVar('--color-border', '#E7E7F0'),
    tooltipText: cssVar('--color-text', '#15151D'),
  };
}