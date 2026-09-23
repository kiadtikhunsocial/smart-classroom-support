import React, { useCallback, useEffect, useRef, useState } from 'react';
import {
  ACCENTS,
  DEFAULT_THEME,
  THEME_MODES,
  ThemeMode,
  useTheme,
} from '../theme';

/* ป้ายของปุ่ม "คืนค่าเริ่มต้น" ต้องอ่านจาก DEFAULT_THEME ไม่ใช่เขียนสีไว้ตรง ๆ
   เดิมข้อความ hardcode ว่า "สว่าง/ม่วง" ทำให้หลังเปลี่ยนค่าเริ่มต้นเป็นโหมดมืด
   ปุ่มโฆษณาผิด (กดแล้วได้มืด แต่บอกว่าสว่าง) และปุ่มยังถูกซ่อนผิดจังหวะด้วย
   เพราะ isDefault เทียบกับค่าเริ่มต้นชุดใหม่
   ตัดคำ "โหมด" และวงเล็บ "(ค่าเริ่มต้น)" ออกเพื่อให้อ่านสั้นในปุ่มแคบ ๆ */
const DEFAULT_THEME_LABEL = [
  (THEME_MODES.find((m) => m.id === DEFAULT_THEME.mode)?.label ?? '').replace(/^โหมด/, ''),
  (ACCENTS.find((a) => a.id === DEFAULT_THEME.accent)?.label ?? '').replace(/\s*\([^)]*\)\s*$/, ''),
]
  .filter(Boolean)
  .join('/');

/** ไอคอนโหมด — inline ให้เหมือนหน้าตั้งค่า ไม่พึ่งฟอนต์อิโมจิของเครื่อง */
function ModeIcon({ mode }: { mode: ThemeMode }) {
  if (mode === 'dark') {
    return (
      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
      </svg>
    );
  }
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

/**
 * ปุ่มสลับธีมสำหรับหน้าสาธารณะ (แถบบนของ PublicHomeView / PublicNoLoginReportView)
 * ใช้ useTheme ตัวเดียวกับหน้าตั้งค่าในระบบ → ค่าที่เลือกถูกบันทึกลง localStorage
 * และมีผลต่อทั้งแอป (แดชบอร์ดด้วย) ทันที
 */
export default function PublicThemeToggle() {
  const [prefs, updateTheme] = useTheme();
  const [open, setOpen] = useState(false);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const btnRef = useRef<HTMLButtonElement | null>(null);

  const close = useCallback(() => setOpen(false), []);

  // ปิดเมื่อคลิกนอกกรอบ หรือกด Esc (คืนโฟกัสให้ปุ่มเพื่อไม่ให้โฟกัสหลุด)
  useEffect(() => {
    if (!open) return;

    const onPointerDown = (e: MouseEvent | TouchEvent) => {
      const target = e.target as Node | null;
      if (target && wrapRef.current && !wrapRef.current.contains(target)) close();
    };
    const onKeyDown = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        close();
        btnRef.current?.focus();
      }
    };

    document.addEventListener('mousedown', onPointerDown);
    document.addEventListener('touchstart', onPointerDown);
    document.addEventListener('keydown', onKeyDown);
    return () => {
      document.removeEventListener('mousedown', onPointerDown);
      document.removeEventListener('touchstart', onPointerDown);
      document.removeEventListener('keydown', onKeyDown);
    };
  }, [open, close]);

  const currentMode = THEME_MODES.find((m) => m.id === prefs.mode) ?? THEME_MODES[0];
  const isDefault = prefs.mode === DEFAULT_THEME.mode && prefs.accent === DEFAULT_THEME.accent;

  return (
    <div className="ph-theme" ref={wrapRef}>
      <button
        type="button"
        ref={btnRef}
        className="ph-theme-btn"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <ModeIcon mode={prefs.mode} />
        <span className="ph-theme-btn-label">ธีม</span>
        <span className="ph-theme-btn-dot" aria-hidden="true" />
        <span className="ph-sr-only">
          {`ธีมปัจจุบัน: ${currentMode.label} — เปิดตัวเลือกธีม`}
        </span>
      </button>

      {open && (
        <div className="ph-theme-pop" role="dialog" aria-label="ตั้งค่าธีม">
          <div>
            <span className="ph-theme-group-label" id="ph-theme-mode-label">
              โหมดการแสดงผล
            </span>
            <div className="ph-theme-seg" role="radiogroup" aria-labelledby="ph-theme-mode-label">
              {THEME_MODES.map((m) => (
                <button
                  key={m.id}
                  type="button"
                  role="radio"
                  aria-checked={prefs.mode === m.id}
                  className={`ph-theme-seg-btn${prefs.mode === m.id ? ' is-active' : ''}`}
                  title={m.hint}
                  onClick={() => updateTheme({ mode: m.id })}
                >
                  <ModeIcon mode={m.id} />
                  {m.label}
                </button>
              ))}
            </div>
          </div>

          <div>
            <span className="ph-theme-group-label" id="ph-theme-accent-label">
              สีเน้น
            </span>
            <div className="ph-theme-swatches" role="radiogroup" aria-labelledby="ph-theme-accent-label">
              {ACCENTS.map((a) => (
                <button
                  key={a.id}
                  type="button"
                  role="radio"
                  aria-checked={prefs.accent === a.id}
                  aria-label={a.label}
                  title={a.label}
                  className="ph-theme-swatch"
                  style={{ ['--sw-from' as any]: a.from, ['--sw-to' as any]: a.to }}
                  onClick={() => updateTheme({ accent: a.id })}
                >
                  <span className="ph-theme-swatch-fill" aria-hidden="true" />
                </button>
              ))}
            </div>
          </div>

          {!isDefault && (
            <button
              type="button"
              className="ph-theme-reset"
              onClick={() => updateTheme(DEFAULT_THEME)}
            >
              {`คืนค่าเริ่มต้น (${DEFAULT_THEME_LABEL})`}
            </button>
          )}
        </div>
      )}
    </div>
  );
}