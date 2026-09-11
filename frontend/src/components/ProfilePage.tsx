import React, { useState, useRef } from 'react';
import { api, setToken } from '../api/client';
import { User } from '../types/user';
import { roleLabel } from '../roleLabels';

export default function ProfilePage({ user, onUpdateUser, onBack }: {
  user?: User | null;
  onUpdateUser?: (u: User) => void;
  onBack: () => void;
}) {
  const [form, setForm] = useState({
    name: user?.line_display_name || '',
    email: user?.line_email || '',
    password: '',
    confirm: '',
  });
  const [avatar, setAvatar] = useState<string | null>(user?.line_picture_url || null);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [success, setSuccess] = useState<string | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const uploadAvatar = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => {
      const img = new Image();
      img.onload = () => {
        const canvas = document.createElement('canvas');
        canvas.width = 256; canvas.height = 256;
        const ctx = canvas.getContext('2d')!;
        ctx.drawImage(img, 0, 0, 256, 256);
        setAvatar(canvas.toDataURL('image/jpeg', 0.85));
      };
      img.src = ev.target?.result as string;
    };
    reader.readAsDataURL(file);
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null); setSuccess(null);
    if (form.password && form.password !== form.confirm) {
      setError('รหัสผ่านทั้งสองช่องไม่ตรงกัน');
      return;
    }
    if (form.password && form.password.length < 4) {
      setError('รหัสผ่านต้องมีอย่างน้อย 4 ตัวอักษร');
      return;
    }
    setSaving(true);
    try {
      const data: any = {};
      if (form.name !== user?.line_display_name) data.line_display_name = form.name;
      if (form.email !== user?.line_email) data.line_email = form.email;
      if (avatar && avatar !== user?.line_picture_url) data.line_picture_url = avatar;
      if (form.password) data.password = form.password;
      if (Object.keys(data).length === 0) { setError('ไม่มีข้อมูลที่เปลี่ยนแปลง'); setSaving(false); return; }
      const result = await api.updateProfile(data);
      setToken(result.token);
      onUpdateUser?.(result.user);
      setSuccess('บันทึกข้อมูลเรียบร้อย ✅');
      setForm((f) => ({ ...f, password: '', confirm: '' }));
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="page-content" style={{ display: 'flex', justifyContent: 'center' }}>
      <div style={{ maxWidth: 520, width: '100%' }}>
        <div className="top-bar" style={{ paddingLeft: 0 }}>
          <div className="top-bar-title-group">
            <button className="btn btn-ghost btn-icon" onClick={onBack}>
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
            </button>
            <div>
              <h1 className="top-bar-title">โปรไฟล์</h1>
              <span className="top-bar-subtitle">แก้ไขข้อมูลส่วนตัวของคุณ</span>
            </div>
          </div>
        </div>

        <div className="panel-card" style={{ padding: '32px 32px 28px' }}>
          {/* Avatar ตรงกลาง */}
          <div style={{ textAlign: 'center', marginBottom: 24 }}>
            <div
              style={{
                width: 96, height: 96, borderRadius: '50%',
                border: '3px solid var(--color-primary-light)',
                overflow: 'hidden', margin: '0 auto 12px', cursor: 'pointer',
                background: 'var(--color-bg)',
                display: 'flex', alignItems: 'center', justifyContent: 'center',
                position: 'relative',
              }}
              onClick={() => fileRef.current?.click()}
              title="คลิกเพื่อเปลี่ยนรูป"
            >
              {avatar ? (
                <img src={avatar} alt="" style={{ width: '100%', height: '100%', objectFit: 'cover' }} />
              ) : (
                <span style={{ fontSize: '2.2rem', color: 'var(--color-primary)', fontWeight: 700 }}>
                  {(user?.line_display_name || 'U').charAt(0).toUpperCase()}
                </span>
              )}
              <div style={{
                position: 'absolute', bottom: 0, left: 0, right: 0,
                background: 'rgba(0,0,0,0.55)', color: '#fff', fontSize: '0.65rem', padding: '4px 0',
              }}>
                📷 เปลี่ยนรูป
              </div>
            </div>
            <input ref={fileRef} type="file" accept="image/*" style={{ display: 'none' }} onChange={uploadAvatar} />
            <div style={{ fontWeight: 600, fontSize: '1.05rem', color: 'var(--color-text)' }}>{user?.line_display_name || 'ผู้ใช้'}</div>
            <div style={{ fontSize: '0.8rem', color: 'var(--color-text-tertiary)', marginTop: 2 }}>
              {roleLabel(user?.role)}
            </div>
          </div>

          <div style={{ borderTop: '1px solid var(--color-border)', paddingTop: 20 }}>
            <form onSubmit={save}>
              <div className="form-group">
                <label className="form-label">ชื่อแสดง</label>
                <input className="form-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="ชื่อ-นามสกุล" />
              </div>
              <div className="form-group">
                <label className="form-label">อีเมล</label>
                <input className="form-input" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })} placeholder="email@example.com" />
              </div>

              <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--color-text-secondary)', margin: '18px 0 10px' }}>
                เปลี่ยนรหัสผ่าน
              </div>
              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">รหัสผ่านใหม่</label>
                  <input className="form-input" type="password" value={form.password} onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="เว้นว่างถ้าไม่เปลี่ยน" />
                </div>
                <div className="form-group">
                  <label className="form-label">ยืนยันรหัสผ่าน</label>
                  <input className="form-input" type="password" value={form.confirm} onChange={(e) => setForm({ ...form, confirm: e.target.value })} placeholder="พิมพ์อีกครั้ง" />
                </div>
              </div>

              {error && (
                <div style={{ padding: '10px 14px', background: 'var(--color-danger-light)', color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)', fontSize: '0.82rem', marginBottom: 'var(--spacing-md)' }}>
                  {error}
                </div>
              )}
              {success && (
                <div style={{ padding: '10px 14px', background: 'var(--color-success-light)', color: '#065F46', borderRadius: 'var(--radius-sm)', fontSize: '0.82rem', marginBottom: 'var(--spacing-md)' }}>
                  {success}
                </div>
              )}

              <button type="submit" className="btn btn-primary btn-full" style={{ padding: 12 }} disabled={saving}>
                {saving ? 'กำลังบันทึก...' : '💾 บันทึกข้อมูล'}
              </button>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}