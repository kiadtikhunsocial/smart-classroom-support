import React from 'react';
import { useTheme } from '../theme';
import { useLang } from '../publicI18n';

/** ปุ่มสลับสว่าง/มืดแบบไอคอนเดียว (ตามแบบหน้าแรก) — ค่าเก็บร่วมกับหน้าตั้งค่าในระบบ */
export default function ThemeModeButton() {
  const [prefs, update] = useTheme();
  const { lang } = useLang();
  const dark = prefs.mode === 'dark';
  const label = lang === 'th' ? (dark ? 'เปลี่ยนเป็นโหมดสว่าง' : 'เปลี่ยนเป็นโหมดมืด') : (dark ? 'Switch to light mode' : 'Switch to dark mode');
  return (
    <button type="button" className="pc-mode-btn" onClick={() => update({ mode: dark ? 'light' : 'dark' })} aria-label={label} title={label}>
      {dark ? (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" aria-hidden="true">
          <circle cx="12" cy="12" r="4" />
          <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
        </svg>
      ) : (
        <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
          <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
        </svg>
      )}
    </button>
  );
}
