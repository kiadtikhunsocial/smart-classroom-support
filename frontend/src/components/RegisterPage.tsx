import React, { useState } from 'react';
import { api } from '../api/client';

/** ชื่อผู้ใช้ต้องตรงกับ pattern ฝั่ง backend (MembershipApplyIn.username) */
const USERNAME_RE = /^[a-zA-Z0-9._-]{3,64}$/;
const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface FormState {
  username: string;
  password: string;
  confirm: string;
  full_name: string;
  email: string;
  phone: string;
  organization_code: string;
  note: string;
}

const EMPTY_FORM: FormState = {
  username: '',
  password: '',
  confirm: '',
  full_name: '',
  email: '',
  phone: '',
  organization_code: '',
  note: '',
};

/**
 * หน้าสมัครสมาชิกสาธารณะ (/?register=1)
 *
 * ส่งคำขอไป POST /api/public/register — ยังไม่ได้บัญชีทันที ต้องรอผู้ดูแลอนุมัติ
 * จึงจะเข้าสู่ระบบด้วยชื่อผู้ใช้/รหัสผ่านที่กรอกไว้ตรงนี้ได้
 */
export default function RegisterPage() {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ id: number; message: string } | null>(null);

  const setField =
    (key: keyof FormState) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const { value } = e.target;
      setForm((prev) => ({ ...prev, [key]: value }));
    };

  /** ตรวจฝั่งหน้าเว็บก่อนยิง เพื่อไม่เสีย quota rate limit (5 คำขอ/ชม.) ไปกับฟอร์มที่กรอกผิด */
  const validate = (): string | null => {
    const username = form.username.trim();
    if (!USERNAME_RE.test(username)) {
      return 'ชื่อผู้ใช้ต้องยาว 3–64 ตัว ใช้ได้เฉพาะ a-z A-Z 0-9 . _ -';
    }
    if (form.password.length < 8) return 'รหัสผ่านต้องยาวอย่างน้อย 8 ตัวอักษร';
    if (form.password.length > 128) return 'รหัสผ่านยาวเกิน 128 ตัวอักษร';
    if (form.password !== form.confirm) return 'ยืนยันรหัสผ่านไม่ตรงกัน';
    if (form.full_name.trim().length < 2) return 'กรุณากรอกชื่อ-นามสกุล';
    const email = form.email.trim();
    if (email && !EMAIL_RE.test(email)) return 'รูปแบบอีเมลไม่ถูกต้อง';
    return null;
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    const invalid = validate();
    if (invalid) {
      setError(invalid);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const res = await api.publicRegister({
        username: form.username.trim(),
        password: form.password,
        full_name: form.full_name.trim(),
        email: form.email.trim() || undefined,
        phone: form.phone.trim() || undefined,
        organization_code: form.organization_code.trim() || undefined,
        note: form.note.trim() || undefined,
      });
      setDone({ id: res.id, message: res.message });
      setForm(EMPTY_FORM);
    } catch (err: any) {
      setError(err?.message || 'ส่งคำขอสมัครสมาชิกไม่สำเร็จ');
    } finally {
      setLoading(false);
    }
  };

  if (done) {
    return (
      <div className="login-page">
        <div className="login-card">
          <div
            style={{
              width: 52,
              height: 52,
              borderRadius: '50%',
              margin: '0 auto 14px',
              display: 'grid',
              placeItems: 'center',
              background: 'var(--color-success-light, #DCFCE7)',
              color: 'var(--color-success, #16A34A)',
            }}
            aria-hidden="true"
          >
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M20 6L9 17l-5-5" />
            </svg>
          </div>
          <h1 className="login-title" style={{ textAlign: 'center' }}>
            ส่งคำขอสมัครสมาชิกแล้ว
          </h1>
          <p
            className="login-subtitle"
            style={{ textAlign: 'center', marginTop: 6 }}
            role="status"
          >
            {done.message}
          </p>
          <p
            style={{
              textAlign: 'center',
              fontSize: '0.8rem',
              color: 'var(--color-text-tertiary)',
              marginTop: 10,
            }}
          >
            เลขที่คำขอ: <strong>#{done.id}</strong> — เมื่อผู้ดูแลอนุมัติ ให้เข้าสู่ระบบด้วยชื่อผู้ใช้และรหัสผ่านที่กรอกไว้
          </p>
          <div className="login-divider" />
          <div style={{ display: 'grid', gap: 10 }}>
            <a className="btn btn-primary btn-full" href="/?login=1" style={{ padding: '12px', textAlign: 'center' }}>
              ไปหน้าเข้าสู่ระบบ
            </a>
            <a
              href="/"
              style={{
                textAlign: 'center',
                fontSize: '0.8rem',
                color: 'var(--color-primary)',
                fontWeight: 600,
              }}
            >
              ← กลับหน้าแรก (แจ้งซ่อม/ติดตามสถานะ)
            </a>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="login-page">
      <div className="login-card" style={{ maxWidth: 520 }}>
        <a href="/" className="login-back-link">
          ← กลับหน้าแรก (แจ้งซ่อม/ติดตามสถานะ)
        </a>
        <div className="login-logo">
          <div className="login-logo-icon">
            <img
              src="/logo.jpg"
              alt="IWA"
              style={{ width: 22, height: 22, objectFit: 'contain', borderRadius: 4 }}
            />
          </div>
          <div>
            <h1 className="login-title">สมัครสมาชิก</h1>
            <p className="login-subtitle">สำหรับเจ้าหน้าที่ — ใช้งานได้เมื่อผู้ดูแลอนุมัติ</p>
          </div>
        </div>
        <div className="login-divider" />

        <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 14 }} noValidate>
          <div className="form-group">
            <label className="form-label" htmlFor="reg-username">
              ชื่อผู้ใช้ (username) <span aria-hidden="true">*</span>
            </label>
            <input
              id="reg-username"
              type="text"
              className="form-input"
              value={form.username}
              onChange={setField('username')}
              placeholder="เช่น somchai.it"
              autoComplete="username"
              required
              autoFocus
            />
          </div>

          <div
            style={{
              display: 'grid',
              gap: 14,
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            }}
          >
            <div className="form-group">
              <label className="form-label" htmlFor="reg-password">
                รหัสผ่าน <span aria-hidden="true">*</span>
              </label>
              <input
                id="reg-password"
                type="password"
                className="form-input"
                value={form.password}
                onChange={setField('password')}
                placeholder="อย่างน้อย 8 ตัวอักษร"
                autoComplete="new-password"
                required
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="reg-confirm">
                ยืนยันรหัสผ่าน <span aria-hidden="true">*</span>
              </label>
              <input
                id="reg-confirm"
                type="password"
                className="form-input"
                value={form.confirm}
                onChange={setField('confirm')}
                placeholder="พิมพ์รหัสผ่านอีกครั้ง"
                autoComplete="new-password"
                required
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="reg-fullname">
              ชื่อ-นามสกุล <span aria-hidden="true">*</span>
            </label>
            <input
              id="reg-fullname"
              type="text"
              className="form-input"
              value={form.full_name}
              onChange={setField('full_name')}
              placeholder="ชื่อจริง นามสกุล"
              autoComplete="name"
              required
            />
          </div>

          <div
            style={{
              display: 'grid',
              gap: 14,
              gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
            }}
          >
            <div className="form-group">
              <label className="form-label" htmlFor="reg-email">
                อีเมล
              </label>
              <input
                id="reg-email"
                type="email"
                className="form-input"
                value={form.email}
                onChange={setField('email')}
                placeholder="name@example.com"
                autoComplete="email"
              />
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="reg-phone">
                เบอร์โทร
              </label>
              <input
                id="reg-phone"
                type="tel"
                className="form-input"
                value={form.phone}
                onChange={setField('phone')}
                placeholder="08x-xxx-xxxx"
                autoComplete="tel"
              />
            </div>
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="reg-org">
              รหัสหน่วยงาน/โรงเรียน
            </label>
            <input
              id="reg-org"
              type="text"
              className="form-input"
              value={form.organization_code}
              onChange={setField('organization_code')}
              placeholder="เช่น TEST1 (ไม่ทราบให้เว้นว่าง)"
            />
          </div>

          <div className="form-group">
            <label className="form-label" htmlFor="reg-note">
              หมายเหตุถึงผู้ดูแล
            </label>
            <textarea
              id="reg-note"
              className="form-input"
              value={form.note}
              onChange={setField('note')}
              rows={3}
              maxLength={1000}
              placeholder="เช่น ตำแหน่งงาน หรือผู้แนะนำให้สมัคร"
              style={{ resize: 'vertical' }}
            />
          </div>

          {error && (
            <div
              role="alert"
              style={{
                padding: '10px 14px',
                background: 'var(--color-danger-light)',
                color: 'var(--color-danger)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.8rem',
              }}
            >
              {error}
            </div>
          )}

          <button
            type="submit"
            className="btn btn-primary btn-full"
            style={{ padding: '12px' }}
            disabled={loading}
          >
            {loading ? (
              <>
                <span
                  className="spinner"
                  style={{
                    width: 14,
                    height: 14,
                    marginRight: 8,
                    borderWidth: 2,
                    display: 'inline-block',
                  }}
                />
                กำลังส่งคำขอ...
              </>
            ) : (
              <>ส่งคำขอสมัครสมาชิก</>
            )}
          </button>
        </form>

        <p className="login-note">
          ระบบจะไม่สร้างบัญชีให้ทันที — ผู้ดูแลต้องตรวจและอนุมัติคำขอก่อน
        </p>
        <div style={{ textAlign: 'center', marginTop: 8, fontSize: '0.8rem' }}>
          <span style={{ color: 'var(--color-text-tertiary)' }}>มีบัญชีอยู่แล้ว? </span>
          <a href="/?login=1" style={{ color: 'var(--color-primary)', fontWeight: 600 }}>
            เข้าสู่ระบบ
          </a>
        </div>
      </div>
    </div>
  );
}