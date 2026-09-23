import React, { useEffect, useState } from 'react';
import { roleLabel } from '../roleLabels';
import {
  ACCENTS,
  DEFAULT_THEME,
  THEME_MODES,
  ThemeMode,
  ThemePrefs,
  useTheme,
} from '../theme';

/** ไอคอนโหมด — inline เพื่อไม่พึ่งฟอนต์อิโมจิของเครื่องผู้ใช้ */
function ModeIcon({ mode }: { mode: ThemeMode }) {
  if (mode === 'dark') {
    return (
      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
        <path d="M21 12.79A9 9 0 1111.21 3 7 7 0 0021 12.79z" />
      </svg>
    );
  }
  return (
    <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4" />
    </svg>
  );
}

export default function SettingsPage({ onBack, user }: { onBack: () => void; user?: any | null }) {
  // ธีมที่ "ใช้อยู่จริง" ทั้งแอป + ตัวร่างที่ยังไม่กดใช้ (โชว์ในการ์ดพรีวิว)
  const [applied, updateTheme] = useTheme();
  const [draft, setDraft] = useState<ThemePrefs>(applied);

  useEffect(() => {
    setDraft(applied);
  }, [applied.mode, applied.accent]);

  const dirty = draft.mode !== applied.mode || draft.accent !== applied.accent;
  const isDefault = applied.mode === DEFAULT_THEME.mode && applied.accent === DEFAULT_THEME.accent;
  const draftAccent = ACCENTS.find((a) => a.id === draft.accent) ?? ACCENTS[0];

  const apply = () => updateTheme(draft);
  const resetToDefault = () => {
    setDraft(DEFAULT_THEME);
    updateTheme(DEFAULT_THEME);
  };

  return (
    <div className="page-content" style={{ maxWidth: 900, margin: '0 auto' }}>
      <div className="top-bar" style={{ paddingLeft: 0 }}>
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack} aria-label="ย้อนกลับ">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
          </button>
          <div>
            <h1 className="top-bar-title">การตั้งค่า</h1>
            <span className="top-bar-subtitle">ปรับแต่งประสบการณ์ใช้งานของคุณ</span>
          </div>
        </div>
      </div>

      {/* ── ธีม ─────────────────────────────────────────────────────────── */}
      <section className="panel-card" style={{ padding: 24, marginBottom: 16 }} aria-labelledby="theme-heading">
        <div className="theme-section-head">
          <div className="theme-section-icon" aria-hidden="true">
            <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="13.5" cy="6.5" r=".5" fill="currentColor" />
              <circle cx="17.5" cy="10.5" r=".5" fill="currentColor" />
              <circle cx="8.5" cy="7.5" r=".5" fill="currentColor" />
              <circle cx="6.5" cy="12.5" r=".5" fill="currentColor" />
              <path d="M12 2a10 10 0 000 20 2 2 0 002-2v-1a2 2 0 012-2h1a4 4 0 004-4 10 10 0 00-9-11z" />
            </svg>
          </div>
          <div>
            <div className="theme-section-title" id="theme-heading">ธีม</div>
            <div className="theme-section-sub">
              เลือกโหมดและสีเน้น — มีผลกับเมนูด้านซ้าย แบนเนอร์ ปุ่ม และกราฟทั้งหมด
            </div>
          </div>
        </div>

        {/* โหมดสว่าง / โหมดมืด */}
        <div className="theme-field">
          <span className="theme-field-label" id="theme-mode-label">โหมดการแสดงผล</span>
          <div className="theme-seg" role="radiogroup" aria-labelledby="theme-mode-label">
            {THEME_MODES.map((m) => (
              <button
                key={m.id}
                type="button"
                role="radio"
                aria-checked={draft.mode === m.id}
                title={m.hint}
                className="theme-seg-btn"
                onClick={() => setDraft((d) => ({ ...d, mode: m.id }))}
              >
                <ModeIcon mode={m.id} />
                {m.label}
              </button>
            ))}
          </div>
        </div>

        {/* สีเน้น */}
        <div className="theme-field">
          <span className="theme-field-label" id="theme-accent-label">
            สีเน้น · {draftAccent.label}
          </span>
          <div className="theme-swatches" role="radiogroup" aria-labelledby="theme-accent-label">
            {ACCENTS.map((a) => (
              <button
                key={a.id}
                type="button"
                role="radio"
                aria-checked={draft.accent === a.id}
                aria-label={a.label}
                title={a.label}
                className="theme-swatch"
                onClick={() => setDraft((d) => ({ ...d, accent: a.id }))}
              >
                <span
                  className="theme-swatch-dot"
                  style={{ background: `linear-gradient(135deg, ${a.from} 0%, ${a.to} 100%)` }}
                />
                {draft.accent === a.id && (
                  <span className="theme-swatch-check" aria-hidden="true">
                    <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
                      <path d="M20 6L9 17l-5-5" />
                    </svg>
                  </span>
                )}
              </button>
            ))}
          </div>
        </div>

        {/* พรีวิวสด — ใส่ data-mode/data-accent เฉพาะบล็อกนี้ จึงเห็นผลก่อนกดใช้ */}
        <div className="theme-field">
          <span className="theme-field-label">ตัวอย่างก่อนใช้งาน</span>
          <div className="theme-preview" data-mode={draft.mode} data-accent={draft.accent}>
            <div className="theme-preview-side">
              <div className="theme-preview-brand">
                <span className="theme-preview-brand-icon" />
                <span className="theme-preview-brand-text" />
              </div>
              <div className="theme-preview-nav is-active"><i />Dashboard</div>
              <div className="theme-preview-nav"><i />Tickets</div>
              <div className="theme-preview-nav"><i />อุปกรณ์</div>
              <div className="theme-preview-nav"><i />ตั้งค่า</div>
            </div>

            <div className="theme-preview-main">
              <div className="theme-preview-hero">
                <div className="theme-preview-hero-title">ภาพรวมระบบซ่อมบำรุง</div>
                <div className="theme-preview-hero-sub">มี Ticket ทั้งหมด 128 รายการ · กำลังดำเนินการ 12</div>
                <div className="theme-preview-pills">
                  <span className="theme-preview-pill">เสร็จสิ้น 96</span>
                  <span className="theme-preview-pill">อุปกรณ์ 340</span>
                </div>
              </div>

              <div className="theme-preview-cards">
                {[
                  { value: '128', label: 'Ticket ทั้งหมด', color: 'var(--chart-1)' },
                  { value: '18', label: 'รอรับเรื่อง', color: 'var(--status-assigned)' },
                  { value: '96', label: 'ซ่อมเสร็จ', color: 'var(--status-resolved)' },
                ].map((c) => (
                  <div className="theme-preview-card" key={c.label}>
                    <div className="theme-preview-card-dot" style={{ background: c.color, opacity: 0.9 }} />
                    <div className="theme-preview-card-value">{c.value}</div>
                    <div className="theme-preview-card-label">{c.label}</div>
                  </div>
                ))}
              </div>

              <div className="theme-preview-chart" aria-hidden="true">
                {[38, 62, 48, 78, 56, 88].map((h, i) => (
                  <span key={i} className="theme-preview-bar" style={{ height: `${h}%` }} />
                ))}
              </div>
            </div>
          </div>
        </div>

        <div style={{ display: 'flex', flexWrap: 'wrap', gap: 10, alignItems: 'center', marginTop: 18 }}>
          <button className="btn btn-primary" onClick={apply} disabled={!dirty}>
            {dirty ? 'ใช้ธีมนี้' : 'ใช้ธีมนี้อยู่แล้ว'}
          </button>
          {dirty && (
            <button className="btn btn-secondary" onClick={() => setDraft(applied)}>
              ยกเลิกการเปลี่ยน
            </button>
          )}
          <button className="btn btn-ghost" onClick={resetToDefault} disabled={isDefault && !dirty}>
            คืนค่าเริ่มต้น
          </button>
          <span style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)' }}>
            บันทึกไว้ในเครื่องนี้ · ใช้ทันทีทั้งระบบเมื่อกด “ใช้ธีมนี้” (ไม่ต้องรีเฟรช)
          </span>
        </div>
      </section>

      {/* ── บัญชี ───────────────────────────────────────────────────────── */}
      <section className="panel-card" style={{ padding: 24, marginBottom: 16 }} aria-labelledby="account-heading">
        <div className="theme-section-head">
          <div className="theme-section-icon" aria-hidden="true">
            <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 21v-2a4 4 0 00-4-4H8a4 4 0 00-4 4v2" />
              <circle cx="12" cy="7" r="4" />
            </svg>
          </div>
          <div>
            <div className="theme-section-title" id="account-heading">บัญชีผู้ใช้</div>
            <div className="theme-section-sub">จัดการข้อมูลส่วนตัวและรหัสผ่าน</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 16px', background: 'var(--color-surface-sunken)', borderRadius: 'var(--radius-md)', flexWrap: 'wrap' }}>
          {user?.line_picture_url ? (
            <img src={user.line_picture_url} alt="" style={{ width: 52, height: 52, borderRadius: '50%', objectFit: 'cover' }} />
          ) : (
            <div style={{ width: 52, height: 52, borderRadius: '50%', background: 'var(--gradient-brand)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '1.2rem' }}>
              {(user?.line_display_name || 'U').charAt(0).toUpperCase()}
            </div>
          )}
          <div style={{ flex: 1, minWidth: 160 }}>
            <div style={{ fontWeight: 600, color: 'var(--color-text)' }}>{user?.line_display_name || 'ผู้ใช้'}</div>
            <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>{roleLabel(user?.role)}</div>
          </div>
          <button
            className="btn btn-secondary"
            onClick={() => window.dispatchEvent(new CustomEvent('navigate', { detail: 'profile' }))}
          >
            แก้ไขโปรไฟล์ →
          </button>
        </div>
      </section>

      {/* ── ข้อมูลระบบ ──────────────────────────────────────────────────── */}
      <section className="panel-card" style={{ padding: 24 }} aria-labelledby="system-heading">
        <div className="theme-section-head">
          <div className="theme-section-icon" aria-hidden="true">
            <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 16v-4M12 8h.01" />
            </svg>
          </div>
          <div>
            <div className="theme-section-title" id="system-heading">ข้อมูลระบบ</div>
            <div className="theme-section-sub">เวอร์ชันและรายละเอียดการใช้งาน</div>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
          {[
            ['เวอร์ชันระบบ', 'Smart Classroom Support v1.0'],
            ['ฐานความรู้', '31 บทความ · อัปเดตอัตโนมัติ'],
            ['รูปแบบ Ticket', 'TK.<รหัสโรงเรียน>.YY.NNNN-C'],
            ['เวลาทำการ', 'จ–ศ 08:00–16:30 น.'],
            ['แจ้งเตือน LINE', 'กำลังพัฒนา (รอเชื่อมต่อ OA)'],
          ].map(([k, v]) => (
            <div key={k} style={{ padding: '12px 14px', background: 'var(--color-surface-sunken)', borderRadius: 'var(--radius-sm)' }}>
              <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)' }}>{k}</div>
              <div style={{ fontSize: '0.85rem', fontWeight: 500, marginTop: 3, color: 'var(--color-text)' }}>{v}</div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}