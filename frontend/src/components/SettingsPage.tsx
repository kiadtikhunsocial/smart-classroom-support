import React, { useState, useEffect } from 'react';
import { roleLabel } from '../roleLabels';

const THEMES = [
  { id: 'theme-purple', name: 'ม่วง', icon: '🟣', primary: '#7C3AED', desc: 'สีประจำระบบ' },
  { id: 'theme-blue', name: 'น้ำเงิน', icon: '🔵', primary: '#2563EB', desc: 'โทนเย็น สบายตา' },
  { id: 'theme-dark', name: 'มืด', icon: '⚫', primary: '#A78BFA', desc: 'โหมดกลางคืน' },
];

export default function SettingsPage({ onBack, user }: { onBack: () => void; user?: any | null }) {
  const [currentTheme, setCurrentTheme] = useState(() => {
    return localStorage.getItem('sc_theme') || 'theme-purple';
  });

  useEffect(() => {
    document.documentElement.className = currentTheme;
    localStorage.setItem('sc_theme', currentTheme);
  }, [currentTheme]);

  const roleLabelLocal = (r?: string) => roleLabel(r);

  return (
    <div className="page-content" style={{ maxWidth: 860, margin: '0 auto' }}>
      <div className="top-bar" style={{ paddingLeft: 0 }}>
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          </button>
          <div>
            <h1 className="top-bar-title">การตั้งค่า</h1>
            <span className="top-bar-subtitle">ปรับแต่งประสบการณ์ใช้งานของคุณ</span>
          </div>
        </div>
      </div>

      {/* ธีม */}
      <div className="panel-card" style={{ padding: 24, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 18 }}>
          <div style={{ width: 38, height: 38, borderRadius: 10, background: 'var(--color-primary-light)', color: 'var(--color-primary-dark)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.1rem', marginRight: 12 }}>🎨</div>
          <div>
            <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>ธีมสี</div>
            <div style={{ fontSize: '0.78rem', color: 'var(--color-text-tertiary)' }}>เลือกโทนสีที่ถนัด — เปลี่ยนได้ทุกเมื่อ</div>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
          {THEMES.map((t) => (
            <button
              key={t.id}
              onClick={() => setCurrentTheme(t.id)}
              style={{
                padding: '18px',
                border: `2px solid ${currentTheme === t.id ? t.primary : 'var(--color-border)'}`,
                borderRadius: 'var(--radius-md)',
                background: currentTheme === t.id ? 'var(--color-primary-light)' : 'var(--color-surface)',
                cursor: 'pointer',
                textAlign: 'left',
                transition: 'all 0.2s',
                display: 'flex',
                gap: 12,
                alignItems: 'center',
              }}
            >
              <span style={{ fontSize: '1.6rem' }}>{t.icon}</span>
              <div style={{ flex: 1 }}>
                <div style={{ fontWeight: 600, fontSize: '0.9rem', color: 'var(--color-text)' }}>{t.name}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)', marginTop: 2 }}>{t.desc}</div>
              </div>
              {currentTheme === t.id && <span style={{ color: t.primary, fontWeight: 700 }}>✓</span>}
            </button>
          ))}
        </div>
      </div>

      {/* บัญชี */}
      <div className="panel-card" style={{ padding: 24, marginBottom: 16 }}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 18 }}>
          <div style={{ width: 38, height: 38, borderRadius: 10, background: 'var(--color-primary-light)', color: 'var(--color-primary-dark)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.1rem', marginRight: 12 }}>👤</div>
          <div>
            <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>บัญชีผู้ใช้</div>
            <div style={{ fontSize: '0.78rem', color: 'var(--color-text-tertiary)' }}>จัดการข้อมูลส่วนตัวและรหัสผ่าน</div>
          </div>
        </div>
        <div style={{ display: 'flex', alignItems: 'center', gap: 14, padding: '14px 16px', background: 'var(--color-bg)', borderRadius: 'var(--radius-md)' }}>
          {user?.line_picture_url ? (
            <img src={user.line_picture_url} alt="" style={{ width: 52, height: 52, borderRadius: '50%', objectFit: 'cover' }} />
          ) : (
            <div style={{ width: 52, height: 52, borderRadius: '50%', background: 'var(--color-primary)', color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 700, fontSize: '1.2rem' }}>
              {(user?.line_display_name || 'U').charAt(0).toUpperCase()}
            </div>
          )}
          <div style={{ flex: 1 }}>
            <div style={{ fontWeight: 600 }}>{user?.line_display_name || 'ผู้ใช้'}</div>
            <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>{roleLabelLocal(user?.role)}</div>
          </div>
          <button className="btn btn-secondary" onClick={() => {
            window.dispatchEvent(new CustomEvent('navigate', { detail: 'profile' }));
          }}>
            แก้ไขโปรไฟล์ →
          </button>
        </div>
      </div>

      {/* ข้อมูลระบบ */}
      <div className="panel-card" style={{ padding: 24 }}>
        <div style={{ display: 'flex', alignItems: 'center', marginBottom: 18 }}>
          <div style={{ width: 38, height: 38, borderRadius: 10, background: 'var(--color-primary-light)', color: 'var(--color-primary-dark)', display: 'flex', alignItems: 'center', justifyContent: 'center', fontSize: '1.1rem', marginRight: 12 }}>ℹ️</div>
          <div>
            <div style={{ fontWeight: 600, fontSize: '0.95rem' }}>ข้อมูลระบบ</div>
            <div style={{ fontSize: '0.78rem', color: 'var(--color-text-tertiary)' }}>เวอร์ชันและรายละเอียดการใช้งาน</div>
          </div>
        </div>
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))', gap: 12 }}>
          {[
            ['เวอร์ชันระบบ', 'Smart Classroom v1.0'],
            ['ฐานความรู้', '31 บทความ · อัปเดตอัตโนมัติ'],
            ['รูปแบบ Ticket', 'SC-YYYY-NNNNNN'],
            ['เวลาทำการ', 'จ–ศ 08:00–16:30 น.'],
            ['แจ้งเตือน LINE', 'กำลังพัฒนา (รอเชื่อมต่อ OA)'],
          ].map(([k, v]) => (
            <div key={k} style={{ padding: '12px 14px', background: 'var(--color-bg)', borderRadius: 'var(--radius-sm)' }}>
              <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)' }}>{k}</div>
              <div style={{ fontSize: '0.85rem', fontWeight: 500, marginTop: 3, color: 'var(--color-text)' }}>{v}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}