import React from 'react';
import { LANGS, useLang, type Lang } from '../publicI18n';

/** ปุ่มเปลี่ยนภาษาของหน้าสาธารณะ — ใช้ <select> ของระบบ จึงใช้คีย์บอร์ด/โปรแกรมอ่านจอได้ทันที */
export default function LanguageSwitcher() {
  const { lang, setLang, t } = useLang();
  return (
    <label className="pc-lang">
      <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <path d="M3 12h18M12 3c2.5 2.6 3.8 5.6 3.8 9s-1.3 6.4-3.8 9c-2.5-2.6-3.8-5.6-3.8-9S9.5 5.6 12 3z" />
      </svg>
      <span className="ph-sr-only">{t('lang')}</span>
      <select value={lang} onChange={(e) => setLang(e.target.value as Lang)} aria-label={t('lang')}>
        {LANGS.map((l) => (
          <option key={l.id} value={l.id} lang={l.id}>{l.label}</option>
        ))}
      </select>
    </label>
  );
}
