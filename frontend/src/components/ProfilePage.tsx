import React, { useState, useRef } from 'react';
import { api, setToken } from '../api/client';
import { User } from '../types/user';
import { roleLabel } from '../roleLabels';
import '../styles/profile.css';

const USERNAME_RE = /^[a-zA-Z0-9._-]{2,64}$/;

export default function ProfilePage({ user, onUpdateUser, onBack }: {
  user?: User | null;
  onUpdateUser?: (u: User) => void;
  onBack: () => void;
}) {
  const [form, setForm] = useState({
    name: user?.line_display_name || '',
    username: user?.line_user_id || '',
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
        const ctx = canvas.getContext('2d');
        if (!ctx) return;
        ctx.drawImage(img, 0, 0, 256, 256);
        setAvatar(canvas.toDataURL('image/jpeg', 0.85));
      };
      img.src = (ev.target?.result as string) || '';
    };
    reader.readAsDataURL(file);
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null); setSuccess(null);

    const username = form.username.trim();
    const email = form.email.trim();

    if (!username) {
      setError('ต้องระบุชื่อผู้ใช้ (username) สำหรับเข้าสู่ระบบ');
      return;
    }
    if (!USERNAME_RE.test(username)) {
      setError('ชื่อผู้ใช้ใช้ได้เฉพาะ a-z, A-Z, 0-9, จุด, ขีดล่าง, ขีดกลาง และยาว 2–64 ตัวอักษร');
      return;
    }
    if (email && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
      setError('รูปแบบอีเมลไม่ถูกต้อง');
      return;
    }
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
      const data: {
        line_display_name?: string;
        username?: string;
        line_email?: string;
        line_picture_url?: string;
        password?: string;
      } = {};
      if (form.name !== (user?.line_display_name || '')) data.line_display_name = form.name;
      if (username !== (user?.line_user_id || '')) data.username = username;
      if (email !== (user?.line_email || '')) data.line_email = email;
      if (avatar && avatar !== user?.line_picture_url) data.line_picture_url = avatar;
      if (form.password) data.password = form.password;

      if (Object.keys(data).length === 0) {
        setError('ไม่มีข้อมูลที่เปลี่ยนแปลง');
        setSaving(false);
        return;
      }

      const result = await api.updateProfile(data);
      setToken(result.token);
      onUpdateUser?.(result.user);
      setSuccess(
        data.username
          ? 'บันทึกข้อมูลเรียบร้อย — ครั้งต่อไปให้เข้าสู่ระบบด้วยชื่อผู้ใช้ใหม่'
          : 'บันทึกข้อมูลเรียบร้อย'
      );
      setForm((f) => ({ ...f, username, email, password: '', confirm: '' }));
    } catch (err: any) {
      setError(err?.message || 'บันทึกไม่สำเร็จ');
    } finally {
      setSaving(false);
    }
  };

  const initial = (form.name || user?.line_display_name || user?.line_user_id || 'U').charAt(0).toUpperCase();

  return (
    <div className="page-content prof-page">
      <div className="prof-wrap">
        <div className="top-bar prof-topbar">
          <div className="top-bar-title-group">
            <button className="btn btn-ghost btn-icon" onClick={onBack} aria-label="ย้อนกลับ">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
                <path d="M19 12H5M12 19l-7-7 7-7" />
              </svg>
            </button>
            <div>
              <h1 className="top-bar-title">โปรไฟล์</h1>
              <span className="top-bar-subtitle">ข้อมูลบัญชีและการเข้าสู่ระบบของคุณ</span>
            </div>
          </div>
        </div>

        <div className="panel-card prof-card">
          {/* ส่วนหัวโปรไฟล์ — จัดกึ่งกลาง */}
          <div className="prof-head">
            <button
              type="button"
              className="prof-avatar"
              onClick={() => fileRef.current?.click()}
              title="เปลี่ยนรูปโปรไฟล์"
              aria-label="เปลี่ยนรูปโปรไฟล์"
            >
              {avatar ? (
                <img className="prof-avatar-img" src={avatar} alt="" />
              ) : (
                <span className="prof-avatar-initial">{initial}</span>
              )}
              <span className="prof-avatar-overlay">เปลี่ยนรูป</span>
            </button>
            <input
              ref={fileRef}
              type="file"
              accept="image/*"
              className="prof-file"
              onChange={uploadAvatar}
            />

            <div className="prof-name">{form.name || user?.line_display_name || 'ผู้ใช้'}</div>
            <div className="prof-role">{roleLabel(user?.role)}</div>

            <dl className="prof-meta">
              <div className="prof-meta-item">
                <dt>ชื่อผู้ใช้ (login)</dt>
                <dd className="prof-meta-mono">{user?.line_user_id || '—'}</dd>
              </div>
              <div className="prof-meta-item">
                <dt>อีเมล</dt>
                <dd>{user?.line_email || 'ยังไม่ระบุ'}</dd>
              </div>
              <div className="prof-meta-item">
                <dt>โรงเรียน/หน่วยงาน</dt>
                <dd>{user?.organization?.name || '—'}</dd>
              </div>
            </dl>
          </div>

          <form className="prof-form" onSubmit={save}>
            <div className="prof-section-title">ข้อมูลบัญชี</div>

            <div className="form-group">
              <label className="form-label" htmlFor="prof-name">ชื่อแสดง</label>
              <input
                id="prof-name"
                className="form-input"
                value={form.name}
                onChange={(e) => setForm({ ...form, name: e.target.value })}
                placeholder="ชื่อ-นามสกุล"
                autoComplete="name"
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label" htmlFor="prof-username">ชื่อผู้ใช้ (username) *</label>
                <input
                  id="prof-username"
                  className="form-input"
                  value={form.username}
                  onChange={(e) => setForm({ ...form, username: e.target.value })}
                  placeholder="เช่น somchai.it"
                  autoComplete="username"
                  spellCheck={false}
                  required
                />
                <span className="form-hint">ใช้คู่กับรหัสผ่านเพื่อเข้าสู่ระบบ — ไม่ใช่อีเมล</span>
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="prof-email">อีเมล</label>
                <input
                  id="prof-email"
                  className="form-input"
                  type="email"
                  value={form.email}
                  onChange={(e) => setForm({ ...form, email: e.target.value })}
                  placeholder="email@example.com"
                  autoComplete="email"
                />
                <span className="form-hint">ใช้รับการแจ้งเตือน ไม่ใช้เข้าสู่ระบบ</span>
              </div>
            </div>

            <div className="prof-section-title">เปลี่ยนรหัสผ่าน</div>
            <div className="form-row">
              <div className="form-group">
                <label className="form-label" htmlFor="prof-pw">รหัสผ่านใหม่</label>
                <input
                  id="prof-pw"
                  className="form-input"
                  type="password"
                  value={form.password}
                  onChange={(e) => setForm({ ...form, password: e.target.value })}
                  placeholder="เว้นว่างถ้าไม่เปลี่ยน"
                  autoComplete="new-password"
                />
              </div>
              <div className="form-group">
                <label className="form-label" htmlFor="prof-pw2">ยืนยันรหัสผ่าน</label>
                <input
                  id="prof-pw2"
                  className="form-input"
                  type="password"
                  value={form.confirm}
                  onChange={(e) => setForm({ ...form, confirm: e.target.value })}
                  placeholder="พิมพ์อีกครั้ง"
                  autoComplete="new-password"
                />
              </div>
            </div>

            {error && <div className="prof-alert prof-alert--error" role="alert">{error}</div>}
            {success && <div className="prof-alert prof-alert--ok" role="status">{success}</div>}

            <button type="submit" className="btn btn-primary btn-full prof-submit" disabled={saving}>
              {saving ? 'กำลังบันทึก...' : 'บันทึกข้อมูล'}
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}