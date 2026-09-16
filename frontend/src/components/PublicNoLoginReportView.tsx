import React, { useEffect, useState } from 'react';
import { api } from '../api/client';

// ─── แจ้งซ่อมสาธารณะ (คนไม่มีบัญชี) ─────────────────────────────────────────
// ทางเข้า: URL ?publicreport=1 หรือปุ่มบนหน้า Login — อยู่ก่อน auth gate
export default function PublicNoLoginReportView() {
  const [deviceTypes, setDeviceTypes] = useState<string[]>([]);
  const [devices, setDevices] = useState<any[]>([]);
  const [optionsLoading, setOptionsLoading] = useState(true);

  // เลือกอุปกรณ์จากระบบ หรือกรอกอิสระ
  const [deviceMode, setDeviceMode] = useState<'list' | 'free'>('free');
  const [selectedDeviceId, setSelectedDeviceId] = useState('');
  const [form, setForm] = useState({
    room_text: '',
    device_type: 'Other',
    device_detail: '',
    title: '',
    description: '',
    reporter_name: '',
    reporter_phone: '',
    reporter_type: 'teacher',
    priority: 'normal',
  });

  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [fieldErr, setFieldErr] = useState<{ name?: string; phone?: string }>({});
  const [photos, setPhotos] = useState<string[]>([]);
  const [submitted, setSubmitted] = useState(false);
  const [ticketId, setTicketId] = useState('');
  const [resultDevice, setResultDevice] = useState<any>(null);
  const [dupAlert, setDupAlert] = useState<{ existing_ticket_no?: string; existing_status?: string } | null>(null);

  useEffect(() => {
    api.publicOptions()
      .then((r) => {
        setDeviceTypes(r.device_types || []);
        setDevices(r.devices || []);
        setOptionsLoading(false);
      })
      .catch(() => setOptionsLoading(false));
  }, []);

  const setField = (field: string, value: string) => {
    setForm((f) => ({ ...f, [field]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setDupAlert(null);
    setFieldErr({});

    const fe: { name?: string; phone?: string } = {};
    if (!form.reporter_name.trim()) fe.name = 'กรุณากรอกชื่อผู้แจ้ง (จำเป็น)';
    if (!form.reporter_phone.trim()) fe.phone = 'กรุณากรอกเบอร์โทรติดต่อ (จำเป็น)';
    if (fe.name || fe.phone) {
      setFieldErr(fe);
      setSubmitting(false);
      return;
    }
    if (!form.title.trim()) {
      setError('กรุณาระบุหัวข้อ/อาการ (จำเป็น)');
      setSubmitting(false);
      return;
    }

    const payload: any = {
      organization_code: 'testschool',
      title: form.title,
      description: form.description,
      reporter_name: form.reporter_name.trim(),
      reporter_phone: form.reporter_phone.trim(),
      reporter_type: form.reporter_type,
      priority: form.priority,
      attachments: photos,
    };
    if (deviceMode === 'list' && selectedDeviceId) {
      payload.device_id = selectedDeviceId;
    } else {
      payload.room_text = form.room_text.trim();
      payload.device_type = form.device_type;
      payload.device_detail = form.device_detail.trim();
    }

    try {
      const result = await api.publicReport(payload);
      setTicketId(result.ticket_id || '-');
      setResultDevice(result);
      setSubmitted(true);
    } catch (err: any) {
      if (err?.status === 409 && err?.code === 'DUPLICATE_OPEN_TICKET') {
        setDupAlert({ existing_ticket_no: err.detail?.existing_ticket_no, existing_status: err.detail?.existing_status });
      } else {
        setError(err.message || 'เกิดข้อผิดพลาด ไม่สามารถส่งคำร้องได้');
      }
      setSubmitting(false);
    }
  };

  const RESET = { background: 'transparent', border: 'none', cursor: 'pointer', color: 'var(--color-primary)', fontWeight: 600, fontSize: '0.8rem', padding: 0 };

  return (
    <div className="login-page">
      <div className="login-card" style={{ maxWidth: 500 }}>
        <div className="login-logo">
          <a href="https://iwa-web.onrender.com/" target="_blank" rel="noopener noreferrer" style={{ display: 'flex', alignItems: 'center', textDecoration: 'none', color: 'inherit' }}>
            <div className="login-logo-icon">
              <img src="/logo.jpg" alt="IWA" style={{ width: 22, height: 22, objectFit: 'contain', borderRadius: 4 }} />
            </div>
            <div>
              <h1 className="login-title">Smart Classroom Support</h1>
              <p className="login-subtitle">แจ้งซ่อมสาธารณะ — ไม่ต้องมีบัญชี</p>
            </div>
          </a>
        </div>
        <div className="login-divider" />

        {submitted ? (
          <div className="success-state">
            <div className="success-icon">✓</div>
            <div className="success-title">ส่งคำร้องเรียบร้อยแล้ว</div>
            <div className="success-sub">หมายเลข Ticket:</div>
            <div className="success-ticket-id">{ticketId}</div>
            {resultDevice?.device_id && (
              <div style={{ marginTop: 10, fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
                รหัสอุปกรณ์: {resultDevice.device_id}
              </div>
            )}
            <div style={{ marginTop: 16, fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
              เจ้าหน้าที่จะดำเนินการตรวจสอบและซ่อมแซมโดยเร็วที่สุด — จดเลข Ticket ไว้เพื่อติดตามสถานะ
            </div>
            <button className="btn btn-primary" style={{ marginTop: 20 }} onClick={() => { window.location.href = '/'; }}>
              กลับหน้าแรก
            </button>
            <button
              className="btn btn-ghost"
              style={{ marginTop: 8, width: '100%' }}
              onClick={() => window.location.href = `/?ticket=${encodeURIComponent(ticketId)}`}
            >
              📋 ติดตามสถานะ Ticket นี้
            </button>
          </div>
        ) : (
          <>
            {/* ─── เลือกวิธีระบุอุปกรณ์ ─── */}
            <div style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
              <button
                type="button"
                className={`btn ${deviceMode === 'free' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ flex: 1, fontSize: '0.82rem', padding: '9px' }}
                onClick={() => setDeviceMode('free')}
              >
                ✏️ กรอกเอง (ห้อง/อุปกรณ์)
              </button>
              <button
                type="button"
                className={`btn ${deviceMode === 'list' ? 'btn-primary' : 'btn-ghost'}`}
                style={{ flex: 1, fontSize: '0.82rem', padding: '9px' }}
                onClick={() => setDeviceMode('list')}
              >
                📋 เลือกจากระบบ
              </button>
            </div>

            {optionsLoading && deviceMode === 'list' ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', marginBottom: 16, background: 'var(--color-surface-secondary)', borderRadius: 'var(--radius-md)' }}>
                <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
                <span style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>กำลังโหลดรายการอุปกรณ์...</span>
              </div>
            ) : deviceMode === 'list' ? (
              <div className="form-group" style={{ marginBottom: 16 }}>
                <label className="form-label">เลือกอุปกรณ์ (จากระบบ)</label>
                <select
                  className="form-select"
                  value={selectedDeviceId}
                  onChange={(e) => setSelectedDeviceId(e.target.value)}
                >
                  <option value="">— เลือกอุปกรณ์ที่ติด QR ในระบบ —</option>
                  {(devices || []).map((d) => (
                    <option key={d.device_id} value={d.device_id}>
                      {d.device_id} · {d.device_type}{d.room_name ? ` · ${d.room_name}` : ''}
                    </option>
                  ))}
                </select>
                {(!devices || devices.length === 0) && (
                  <div style={{ fontSize: '0.78rem', color: 'var(--color-text-tertiary)', marginTop: 6 }}>
                    ยังไม่มีอุปกรณ์ลงทะเบียนในระบบ — เลือก "กรอกเอง" เพื่อระบุห้อง/อุปกรณ์
                  </div>
                )}
              </div>
            ) : (
              <>
                <div className="form-group">
                  <label className="form-label">ห้อง/สถานที่ <span className="required">*</span></label>
                  <input
                    type="text"
                    className="form-input"
                    value={form.room_text}
                    onChange={(e) => setField('room_text', e.target.value)}
                    placeholder="เช่น อาคาร 1 ชั้น 2 ห้อง 201"
                    required={deviceMode === 'free'}
                  />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">ประเภทอุปกรณ์</label>
                    <select
                      className="form-select"
                      value={form.device_type}
                      onChange={(e) => setField('device_type', e.target.value)}
                    >
                      {(deviceTypes.length ? deviceTypes : ['Other']).map((t) => (
                        <option key={t} value={t}>{t}</option>
                      ))}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">ชื่อ/รหัสอุปกรณ์</label>
                    <input
                      type="text"
                      className="form-input"
                      value={form.device_detail}
                      onChange={(e) => setField('device_detail', e.target.value)}
                      placeholder="เช่น จอ Interactive ตัวที่ 2"
                    />
                  </div>
                </div>
              </>
            )}

            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">หัวข้อ/อาการ <span className="required">*</span></label>
                <input
                  type="text"
                  className="form-input"
                  value={form.title}
                  onChange={(e) => setField('title', e.target.value)}
                  placeholder="เช่น จอภาพไม่ติด, Wi-Fi ไม่เข้า, ไฟไม่มา"
                  maxLength={200}
                  required
                />
              </div>

              <div className="form-group">
                <label className="form-label">รายละเอียด</label>
                <textarea
                  className="form-textarea"
                  value={form.description}
                  onChange={(e) => setField('description', e.target.value)}
                  placeholder="บรรยายอาการที่เกิดขึ้น (เช่น เปิดเครื่องแล้วจอไม่ติด ไฟไม่เข้า)"
                  rows={3}
                />
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">ชื่อผู้แจ้ง <span className="required">*</span></label>
                  <input
                    type="text"
                    className="form-input"
                    value={form.reporter_name}
                    onChange={(e) => setField('reporter_name', e.target.value)}
                    placeholder="ชื่อ-นามสกุล"
                  />
                  {fieldErr.name && <div style={{ fontSize: '0.75rem', color: 'var(--color-danger)', marginTop: 4 }}>{fieldErr.name}</div>}
                </div>
                <div className="form-group">
                  <label className="form-label">เบอร์ติดต่อ <span className="required">*</span></label>
                  <input
                    type="tel"
                    className="form-input"
                    value={form.reporter_phone}
                    onChange={(e) => setField('reporter_phone', e.target.value)}
                    placeholder="08xxxxxxxx"
                  />
                  {fieldErr.phone && <div style={{ fontSize: '0.75rem', color: 'var(--color-danger)', marginTop: 4 }}>{fieldErr.phone}</div>}
                </div>
              </div>

              <div className="form-row">
                <div className="form-group">
                  <label className="form-label">ประเภทผู้แจ้ง</label>
                  <select className="form-select" value={form.reporter_type} onChange={(e) => setField('reporter_type', e.target.value)}>
                    <option value="teacher">ครูผู้สอน</option>
                    <option value="staff">เจ้าหน้าที่</option>
                    <option value="student">นักเรียน/นักศึกษา</option>
                    <option value="other">อื่นๆ / บุคคลภายนอก</option>
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">ระดับความเร่งด่วน</label>
                  <select className="form-select" value={form.priority} onChange={(e) => setField('priority', e.target.value)}>
                    <option value="low">Low — ไม่เร่งด่วน</option>
                    <option value="normal">Normal — ปกติ</option>
                    <option value="high">High — ค่อนข้างเร่งด่วน</option>
                    <option value="critical">Critical — เร่งด่วนมาก</option>
                  </select>
                </div>
              </div>

              <div className="form-group">
                <label className="form-label">แนบรูปภาพปัญหา (ไม่บังคับ, สูงสุด 3 ภาพ)</label>
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  className="form-input"
                  onChange={async (e) => {
                    const files = e.target.files;
                    if (!files) return;
                    try {
                      for (const f of Array.from(files).slice(0, 3)) {
                        const r = await api.upload(f);
                        setPhotos((prev) => [...prev, r.url]);
                      }
                    } catch (err: any) { setError(err.message || 'อัปโหลดรูปไม่สำเร็จ'); }
                  }}
                />
                {photos.length > 0 && (
                  <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                    {photos.map((u, i) => (
                      <img key={i} src={u} style={{ width: 56, height: 56, objectFit: 'cover', borderRadius: 6 }} alt="" />
                    ))}
                  </div>
                )}
              </div>

              {error && (
                <div style={{ padding: '10px 14px', background: 'var(--color-danger-light)', color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)', fontSize: '0.8rem', marginBottom: 'var(--spacing-md)' }}>
                  {error}
                </div>
              )}

              {dupAlert && (
                <div style={{ padding: '12px 14px', marginBottom: 'var(--spacing-md)', background: 'var(--color-warning-light)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem', color: '#92400E' }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>⚠️ อุปกรณ์นี้มีการแจ้งซ่อมที่ยังไม่ปิดอยู่แล้ว</div>
                  <div>
                    Ticket ที่ค้างอยู่: <strong>{dupAlert.existing_ticket_no || '-'}</strong>{' · '}สถานะ: {dupAlert.existing_status || '-'}
                  </div>
                  <a href={`/?ticket=${encodeURIComponent(dupAlert.existing_ticket_no || '')}`} style={{ color: 'var(--color-primary)', fontWeight: 600, fontSize: '0.8rem' }}>
                    📋 ดูสถานะ Ticket นี้
                  </a>
                  <div style={{ fontSize: '0.75rem', marginTop: 4, color: '#78350F' }}>
                    กรุณารอเจ้าหน้าที่ดำเนินการงานเดิมก่อน — ระบบไม่สร้าง Ticket ซ้ำ
                  </div>
                </div>
              )}

              <button
                type="submit"
                className="btn btn-primary btn-full"
                style={{ padding: '12px' }}
                disabled={submitting || (deviceMode === 'list' && !selectedDeviceId)}
              >
                {submitting ? (
                  <>
                    <span className="spinner" style={{ width: 14, height: 14, marginRight: 8, borderWidth: 2, display: 'inline-block' }} />
                    กำลังส่ง...
                  </>
                ) : (
                  <>ส่งคำร้องแจ้งซ่อม</>
                )}
              </button>
            </form>

            <div style={{ textAlign: 'center', marginTop: 16, fontSize: '0.8rem' }}>
              <button type="button" style={RESET} onClick={() => { window.location.href = '/'; }}>
                ← กลับไปเข้าสู่ระบบ
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
