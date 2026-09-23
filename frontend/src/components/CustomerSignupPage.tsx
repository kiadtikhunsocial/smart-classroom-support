import React, { useState } from 'react';
import { api } from '../api/client';

const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;

interface FormState {
  full_name: string;
  phone: string;
  email: string;
  organization: string;
  products: string;
  note: string;
  consent: boolean;
}

const EMPTY_FORM: FormState = {
  full_name: '',
  phone: '',
  email: '',
  organization: '',
  products: '',
  note: '',
  consent: false,
};

/** เหลือแต่ตัวเลข — ฝั่ง backend ตรวจ 0 ตามด้วย 8–9 หลัก */
const onlyDigits = (value: string) => value.replace(/\D/g, '');

const labelStyle: React.CSSProperties = {
  display: 'block',
  fontSize: '0.82rem',
  fontWeight: 600,
  color: 'var(--color-text-secondary)',
  marginBottom: 6,
};

const inputStyle: React.CSSProperties = {
  width: '100%',
  boxSizing: 'border-box',
  padding: '10px 12px',
  fontSize: '0.95rem',
  fontFamily: 'inherit',
  color: 'var(--color-text-primary, #111827)',
  background: 'var(--color-surface, #fff)',
  border: '1px solid var(--color-border, #D1D5DB)',
  borderRadius: 'var(--radius-sm, 8px)',
};

const rowStyle: React.CSSProperties = {
  display: 'grid',
  gridTemplateColumns: 'repeat(auto-fit, minmax(200px, 1fr))',
  gap: 12,
};

/**
 * หน้าสมัครสมาชิกลูกค้า (/?customer=1)
 *
 * ไม่ได้สร้างบัญชีผู้ใช้ — ส่งข้อมูลติดต่อไป POST /api/public/customer-signup
 * ระบบบันทึกเป็น lead (ช่องทาง WEB) แล้วทีมขายติดต่อกลับ
 */
export default function CustomerSignupPage() {
  const [form, setForm] = useState<FormState>(EMPTY_FORM);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<{ message: string } | null>(null);

  const setField =
    (key: keyof FormState) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      const target = e.target as HTMLInputElement;
      const value =
        key === 'consent'
          ? target.checked
          : key === 'phone'
          ? onlyDigits(target.value)
          : target.value;
      setForm((prev) => ({ ...prev, [key]: value }));
    };

  /** ตรวจฝั่งหน้าเว็บก่อนยิง เพื่อไม่เสีย quota rate limit (10 คำขอ/ชม.) ไปกับฟอร์มที่กรอกผิด */
  const validate = (): string | null => {
    if (form.full_name.trim().length < 2) return 'กรุณากรอกชื่อ-นามสกุล';
    const phone = form.phone;
    if (!phone.startsWith('0') || phone.length < 9 || phone.length > 10) {
      return 'เบอร์โทรไม่ถูกต้อง (ตัวอย่าง 0812345678)';
    }
    const email = form.email.trim();
    if (email && !EMAIL_RE.test(email)) return 'รูปแบบอีเมลไม่ถูกต้อง';
    if (!form.consent) return 'กรุณายินยอมให้ทีมงานติดต่อกลับก่อนส่งข้อมูล';
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
      const res = await api.publicCustomerSignup({
        full_name: form.full_name.trim(),
        phone: form.phone,
        email: form.email.trim() || undefined,
        organization: form.organization.trim() || undefined,
        products: form.products.trim() || undefined,
        note: form.note.trim() || undefined,
        consent: form.consent,
      });
      setDone({ message: res.message });
      setForm(EMPTY_FORM);
    } catch (err: any) {
      setError(err?.message || 'ส่งข้อมูลสมัครสมาชิกไม่สำเร็จ');
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
            สมัครสมาชิกเรียบร้อย
          </h1>
          <p className="login-subtitle" style={{ textAlign: 'center', marginTop: 6 }} role="status">
            {done.message}
          </p>
          <div style={{ display: 'flex', gap: 10, justifyContent: 'center', marginTop: 18, flexWrap: 'wrap' }}>
            <a className="btn btn-primary" href="/" style={{ textDecoration: 'none' }}>
              กลับหน้าแรก
            </a>
            <button className="btn btn-ghost" type="button" onClick={() => setDone(null)}>
              สมัครอีกรายการ
            </button>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="login-page">
      <div className="login-card" style={{ maxWidth: 560 }}>
        <h1 className="login-title">สมัครสมาชิกลูกค้า</h1>
        <p className="login-subtitle">
          กรอกข้อมูลติดต่อไว้ ทีมขายจะติดต่อกลับพร้อมรายละเอียดสินค้า ราคา และโปรโมชั่น
          (ไม่ต้องตั้งรหัสผ่าน ไม่ใช่การเปิดบัญชีเจ้าหน้าที่)
        </p>

        {error && (
          <div
            role="alert"
            style={{
              padding: '10px 14px',
              background: 'var(--color-danger-light, #FEE2E2)',
              color: 'var(--color-danger, #DC2626)',
              borderRadius: 'var(--radius-sm, 8px)',
              fontSize: '0.85rem',
              margin: '14px 0',
            }}
          >
            {error}
          </div>
        )}

        <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 14, marginTop: 16 }} noValidate>
          <div style={rowStyle}>
            <div>
              <label htmlFor="cs-name" style={labelStyle}>
                ชื่อ-นามสกุล <span style={{ color: 'var(--color-danger, #DC2626)' }}>*</span>
              </label>
              <input
                id="cs-name"
                style={inputStyle}
                value={form.full_name}
                onChange={setField('full_name')}
                autoComplete="name"
                maxLength={128}
                required
              />
            </div>
            <div>
              <label htmlFor="cs-phone" style={labelStyle}>
                เบอร์โทร <span style={{ color: 'var(--color-danger, #DC2626)' }}>*</span>
              </label>
              <input
                id="cs-phone"
                style={inputStyle}
                value={form.phone}
                onChange={setField('phone')}
                inputMode="numeric"
                autoComplete="tel"
                placeholder="0812345678"
                maxLength={10}
                required
              />
            </div>
          </div>

          <div style={rowStyle}>
            <div>
              <label htmlFor="cs-email" style={labelStyle}>
                อีเมล (ไม่บังคับ)
              </label>
              <input
                id="cs-email"
                type="email"
                style={inputStyle}
                value={form.email}
                onChange={setField('email')}
                autoComplete="email"
                maxLength={128}
              />
            </div>
            <div>
              <label htmlFor="cs-org" style={labelStyle}>
                หน่วยงาน / โรงเรียน (ไม่บังคับ)
              </label>
              <input
                id="cs-org"
                style={inputStyle}
                value={form.organization}
                onChange={setField('organization')}
                autoComplete="organization"
                maxLength={128}
              />
            </div>
          </div>

          <div>
            <label htmlFor="cs-products" style={labelStyle}>
              สินค้า / บริการที่สนใจ (ไม่บังคับ)
            </label>
            <input
              id="cs-products"
              style={inputStyle}
              value={form.products}
              onChange={setField('products')}
              placeholder="คั่นหลายรายการด้วยเครื่องหมาย ,"
              maxLength={500}
            />
          </div>

          <div>
            <label htmlFor="cs-note" style={labelStyle}>
              รายละเอียดเพิ่มเติม (ไม่บังคับ)
            </label>
            <textarea
              id="cs-note"
              style={{ ...inputStyle, minHeight: 90, resize: 'vertical' }}
              value={form.note}
              onChange={setField('note')}
              maxLength={500}
            />
          </div>

          <label
            htmlFor="cs-consent"
            style={{
              display: 'flex',
              gap: 10,
              alignItems: 'flex-start',
              fontSize: '0.83rem',
              color: 'var(--color-text-secondary)',
              lineHeight: 1.5,
            }}
          >
            <input
              id="cs-consent"
              type="checkbox"
              checked={form.consent}
              onChange={setField('consent')}
              style={{ width: 18, height: 18, marginTop: 1, flexShrink: 0 }}
              required
            />
            <span>
              ยินยอมให้เก็บชื่อและเบอร์โทรไว้เพื่อให้ทีมงานติดต่อกลับเรื่องสินค้า/บริการ
            </span>
          </label>

          <button className="btn btn-primary" type="submit" disabled={loading} style={{ width: '100%', padding: '11px 16px' }}>
            {loading ? 'กำลังส่งข้อมูล…' : 'สมัครสมาชิก'}
          </button>
        </form>

        <p style={{ textAlign: 'center', fontSize: '0.8rem', color: 'var(--color-text-tertiary)', marginTop: 14 }}>
          เป็นเจ้าหน้าที่?{' '}
          <a href="/?register=1" style={{ color: 'var(--color-primary)', fontWeight: 600 }}>
            ขอเปิดบัญชีเจ้าหน้าที่
          </a>
        </p>
      </div>
    </div>
  );
}