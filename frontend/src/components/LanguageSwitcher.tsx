import React from 'react';
import { LANGS, useLang } from '../publicI18n';

/** ป้ายสั้นบนปุ่ม — แตะครั้งเดียวเปลี่ยนภาษา ไม่ต้องเปิดเมนู */
const SHORT: Record<string, string> = { th: 'ไทย', en: 'EN', zh: '中文', ja: '日本', ko: '한국' };

/** ปุ่มเปลี่ยนภาษาของหน้าสาธารณะ: เห็นทุกภาษาพร้อมกัน แตะภาษาที่ต้องการได้ทันที */
export default function LanguageSwitcher() {
  const { lang, setLang, t } = useLang();
  return (
    <div className="pc-lang" role="group" aria-label={t('lang')}>
      {LANGS.map((l) => (
        <button
          key={l.id}
          type="button"
          lang={l.id}
          className={`pc-lang-btn${lang === l.id ? ' is-on' : ''}`}
          aria-pressed={lang === l.id}
          aria-label={l.label}
          title={l.label}
          onClick={() => setLang(l.id)}
        >
          {SHORT[l.id]}
        </button>
      ))}
    </div>
  );
}
