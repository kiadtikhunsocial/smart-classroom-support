import React, { useState, useEffect } from 'react';
import QRCode from 'qrcode';
import { api } from '../api/client';

const DEVICE_TYPES = [
  'Interactive Display', 'Computer AIO', 'Computer Notebook', 'Computer Desktop',
  'Router', 'Access Point', 'Switch', 'Speaker', 'Camera', 'Visualizer',
  'Microphone', 'UPS', 'Printer', 'Projector', 'Software (Picaro)', 'Software (Phonics Hero)', 'Other',
];

const DEVICE_STATUSES = ['active', 'inactive', 'decommissioned'];

const EMPTY_FORM = {
  device_id: '',
  organization_id: 0,
  room_code: '',
  device_type: 'Interactive Display',
  brand: '',
  model: '',
  serial_number: '',
  firmware_version: '',
  status: 'active',
  notes: '',
};

export default function DevicesPage({ onBack, currentOrgId, isSuperAdmin, canManage }: {
  onBack: () => void;
  currentOrgId?: number | null;
  isSuperAdmin: boolean;
  canManage: boolean;
}) {
  const [devices, setDevices] = useState<any[]>([]);
  const [orgs, setOrgs] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [orgFilter, setOrgFilter] = useState<number | ''>(isSuperAdmin ? '' : (currentOrgId ?? ''));
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [qrDevice, setQrDevice] = useState<any | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string>('');
  const [rooms, setRooms] = useState<any[]>([]);
  const [roomsLoading, setRoomsLoading] = useState(false);

  // QR content: URL + device token (ตาม TOR — ไม่ฝังข้อมูลอุปกรณ์ใน QR, ย้ายได้ไม่ต้องพิมพ์ใหม่)
  const qrUrlFor = (d: any) =>
    d.qr_url && d.qr_url.startsWith('/scan')
      ? `${window.location.origin}${d.qr_url}`
      : `${window.location.origin}/scan?device=${encodeURIComponent(d.device_id)}`;

  const showQr = async (d: any) => {
    setQrDevice(d);
    const url = qrUrlFor(d);
    try {
      const dataUrl = await QRCode.toDataURL(url, { width: 300, margin: 2 });
      setQrDataUrl(dataUrl);
    } catch {
      setQrDataUrl('');
    }
  };

  const downloadQr = () => {
    if (!qrDataUrl || !qrDevice) return;
    const a = document.createElement('a');
    a.href = qrDataUrl;
    a.download = `qr-${qrDevice.device_id}.png`;
    a.click();
  };

  const load = () => {
    setLoading(true);
    Promise.all([
      api.listDevices(500, orgFilter === '' ? undefined : orgFilter),
      api.listOrganizations(),
    ])
      .then(([d, o]) => { setDevices(d); setOrgs(o); })
      .catch((e) => setError(e.message || 'โหลดไม่สำเร็จ'))
      .finally(() => setLoading(false));
  };

  useEffect(() => { load(); }, [orgFilter]);

  const openAdd = () => {
    setForm({ ...EMPTY_FORM, organization_id: orgFilter === '' && orgs[0] ? orgs[0].id : (orgFilter || currentOrgId || 0) });
    setEditingId(null);
    setShowForm(true);
  };

  const openEdit = (d: any) => {
    setForm({
      device_id: d.device_id,
      organization_id: d.organization_id ?? (orgs.find((o) => o.name === d.organization_name)?.id ?? 0),
      room_code: d.room_code || '',
      device_type: d.device_type,
      brand: d.brand || '',
      model: d.model || '',
      serial_number: d.serial_number || '',
      firmware_version: d.firmware_version || '',
      status: d.status || 'active',
      notes: d.notes || '',
    });
    setEditingId(d.device_id);
    setShowForm(true);
  };

  const handleSave = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.organization_id) { alert('กรุณาเลือกโรงเรียน'); return; }
    setSaving(true);
    setError(null);
    try {
      if (editingId) {
        await api.updateDevice(editingId, {
          device_type: form.device_type,
          room_code: form.room_code,
          brand: form.brand,
          model: form.model,
          serial_number: form.serial_number,
          firmware_version: form.firmware_version,
          status: form.status,
          notes: form.notes,
        });
      } else {
        await api.createDevice({
          device_id: form.device_id || undefined,
          organization_id: form.organization_id,
          room_code: form.room_code || undefined,
          device_type: form.device_type,
          brand: form.brand || undefined,
          model: form.model || undefined,
          serial_number: form.serial_number || undefined,
          firmware_version: form.firmware_version || undefined,
          status: form.status,
          notes: form.notes || undefined,
        });
      }
      setShowForm(false);
      load();
    } catch (err: any) {
      setError(err.message || 'บันทึกไม่สำเร็จ');
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (d: any) => {
    if (!window.confirm(`ลบอุปกรณ์ ${d.device_id} (${d.device_type})?`)) return;
    setBusy(d.device_id);
    try {
      await api.deleteDevice(d.device_id);
      load();
    } catch (err: any) {
      alert(err.message || 'ลบไม่สำเร็จ');
    } finally {
      setBusy(null);
    }
  };

  // ─── จัดการห้อง (เพิ่มห้องผ่าน UI) ────────────────────────────────
  const loadRooms = async (orgId: number | null) => {
    if (!orgId) { setRooms([]); return; }
    setRoomsLoading(true);
    try {
      const r = await api.listRooms(Number(orgId));
      setRooms(r || []);
    } catch { setRooms([]); }
    finally { setRoomsLoading(false); }
  };

  const handleAddRoom = async () => {
    const orgId = Number(form.organization_id);
    if (!orgId) { alert('กรุณาเลือกโรงเรียนก่อน'); return; }
    const code = window.prompt('รหัสห้อง (เช่น 101, 201):');
    if (!code) return;
    const name = window.prompt(`ชื่อห้อง (เช่น ห้อง ${code}):`) || `ห้อง ${code}`;
    const building = window.prompt('อาคาร/ชั้น (เช่น อาคาร 1 ชั้น 2 หรือเว้นว่าง):') || '';
    const floor = window.prompt('ชั้น (เช่น 1, 2 หรือเว้นว่าง):') || '';
    try {
      await api.createRoom(orgId, { code, name, building, floor: floor || undefined });
      alert('✅ เพิ่มห้องเรียบร้อย');
      await loadRooms(orgId);
      setForm((f: any) => ({ ...f, room_code: code })); // เลือกห้องที่เพิ่งสร้าง
    } catch (err: any) {
      alert(err.message || 'เพิ่มห้องไม่สำเร็จ');
    }
  };

  // โหลดห้องเมื่อเปลี่ยนโรงเรียนในฟอร์ม
  useEffect(() => {
    if (showForm) loadRooms(form.organization_id || null);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [showForm, form.organization_id]);

  return (
    <div className="page-content">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
          </button>
          <div>
            <h1 className="top-bar-title">อุปกรณ์ทั้งหมด</h1>
            <span className="top-bar-subtitle">{devices.length} เครื่อง</span>
          </div>
        </div>
        <div className="top-bar-actions" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {isSuperAdmin && (
            <select className="form-select" style={{ width: 200 }} value={orgFilter} onChange={(e) => setOrgFilter(e.target.value === '' ? '' : Number(e.target.value))}>
              <option value="">ทุกโรงเรียน</option>
              {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          )}
          <button className="btn btn-primary" onClick={openAdd} disabled={!canManage}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 6, verticalAlign: 'middle' }}>
              <path d="M12 5v14M5 12h14"/>
            </svg>
            เพิ่มอุปกรณ์
          </button>
          <button className="btn btn-ghost" onClick={load}>⟳</button>
        </div>
      </div>

      {error && (
        <div style={{ padding: '10px 14px', background: 'var(--color-danger-light)', color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem', marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* ฟอร์มเพิ่ม/แก้ไข */}
      {showForm && (
        <div className="panel-overlay" onClick={() => setShowForm(false)}>
          <div className="repair-panel" style={{ width: 520, maxWidth: '95vw' }} onClick={(e) => e.stopPropagation()}>
            <div className="repair-panel-header">
              <h3 className="repair-panel-title">{editingId ? `แก้ไข ${editingId}` : 'เพิ่มอุปกรณ์ใหม่'}</h3>
              <button className="repair-panel-close" onClick={() => setShowForm(false)}>✕</button>
            </div>
            <div className="repair-panel-body">
              <form onSubmit={handleSave}>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">รหัสอุปกรณ์ (DEV-xxxx)</label>
                    <input className="form-input" value={form.device_id} onChange={(e) => setForm({ ...form, device_id: e.target.value })} placeholder="เว้นว่าง = สร้างอัตโนมัติ" disabled={!!editingId} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">โรงเรียน *</label>
                    <select className="form-select" value={form.organization_id} onChange={(e) => setForm({ ...form, organization_id: Number(e.target.value) })} disabled={!!editingId}>
                      <option value={0}>— เลือกโรงเรียน —</option>
                      {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                    </select>
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">ประเภทอุปกรณ์</label>
                    <select className="form-select" value={form.device_type} onChange={(e) => setForm({ ...form, device_type: e.target.value })}>
                      {DEVICE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                    </select>
                  </div>
                  <div className="form-group">
                    <label className="form-label">ห้อง</label>
                    <div style={{ display: 'flex', gap: 6 }}>
                      <select
                        className="form-select"
                        style={{ flex: 1 }}
                        value={rooms.some((r) => r.code === form.room_code) ? form.room_code : ''}
                        onChange={(e) => setForm({ ...form, room_code: e.target.value })}
                      >
                        <option value="">— ไม่ระบุห้อง / พิมพ์รหัสเองไม่ได้ —</option>
                        {rooms.map((r) => (
                          <option key={r.id} value={r.code}>
                            {r.code} · {r.name}{r.building ? ` (${r.building})` : ''}
                          </option>
                        ))}
                      </select>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        onClick={handleAddRoom}
                        title="เพิ่มห้องใหม่ให้โรงเรียนนี้"
                        style={{ whiteSpace: 'nowrap', flexShrink: 0 }}
                      >
                        ＋
                      </button>
                    </div>
                    {roomsLoading && <div style={{ fontSize: '0.7rem', color: 'var(--color-text-tertiary)', marginTop: 4 }}>กำลังโหลดห้อง...</div>}
                    {!roomsLoading && rooms.length === 0 && (
                      <div style={{ fontSize: '0.7rem', color: 'var(--color-text-tertiary)', marginTop: 4 }}>
                        ยังไม่มีห้องในโรงเรียนนี้ — กด ＋ เพื่อเพิ่มห้อง
                      </div>
                    )}
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">ยี่ห้อ</label>
                    <input className="form-input" value={form.brand} onChange={(e) => setForm({ ...form, brand: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">รุ่น</label>
                    <input className="form-input" value={form.model} onChange={(e) => setForm({ ...form, model: e.target.value })} />
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">Serial No.</label>
                    <input className="form-input" value={form.serial_number} onChange={(e) => setForm({ ...form, serial_number: e.target.value })} />
                  </div>
                  <div className="form-group">
                    <label className="form-label">สถานะ</label>
                    <select className="form-select" value={form.status} onChange={(e) => setForm({ ...form, status: e.target.value })}>
                      {DEVICE_STATUSES.map((s) => <option key={s} value={s}>{s}</option>)}
                    </select>
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">หมายเหตุ</label>
                  <textarea className="form-textarea" rows={2} value={form.notes} onChange={(e) => setForm({ ...form, notes: e.target.value })} />
                </div>
                <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                  <button type="submit" className="btn btn-primary" style={{ flex: 1 }} disabled={saving}>
                    {saving ? 'กำลังบันทึก...' : 'บันทึก'}
                  </button>
                  <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>ยกเลิก</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* QR Modal */}
      {qrDevice && (
        <div className="panel-overlay" onClick={() => setQrDevice(null)}>
          <div className="repair-panel" style={{ width: 380, maxWidth: '95vw', textAlign: 'center' }} onClick={(e) => e.stopPropagation()}>
            <div className="repair-panel-header">
              <h3 className="repair-panel-title">QR Code — {qrDevice.device_id}</h3>
              <button className="repair-panel-close" onClick={() => setQrDevice(null)}>✕</button>
            </div>
            <div className="repair-panel-body" style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: 12 }}>
              {qrDataUrl ? (
                <img src={qrDataUrl} alt={`QR ${qrDevice.device_id}`} style={{ width: 220, height: 220, borderRadius: 8, border: '1px solid var(--color-border)' }} />
              ) : (
                <div className="spinner" style={{ width: 32, height: 32 }} />
              )}
              <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>{qrDevice.device_type}</div>
              <div style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary)' }}>
                {qrDevice.room_name || qrDevice.room_code || '—'} • {qrDevice.organization_name || ''}
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)', wordBreak: 'break-all', maxWidth: 300 }}>
                {qrUrlFor(qrDevice)}
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)' }}>
                สแกนด้วยกล้องมือถือ → เปิดหน้าแจ้งซ่อมให้อุปกรณ์นี้ทันที
              </div>
              <button className="btn btn-primary" onClick={downloadQr} disabled={!qrDataUrl}>
                ⬇ ดาวน์โหลด PNG
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ตารางอุปกรณ์ */}
      <div className="page-section">
        <div className="section-body">
          {loading ? (
            <div className="loading-state" style={{ padding: '40px' }}>
              <div className="spinner" />
              <span>กำลังโหลด...</span>
            </div>
          ) : devices.length === 0 ? (
            <div className="empty-state" style={{ padding: '40px' }}>
              <svg className="empty-icon" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="2" y="4" width="20" height="14" rx="2"/>
                <path d="M2 10h20M12 14v6"/>
              </svg>
              <span className="empty-text">ไม่มีอุปกรณ์ — กด "เพิ่มอุปกรณ์" เพื่อเพิ่มเครื่องแรก</span>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>รหัส</th>
                    <th>ประเภท</th>
                    <th>ยี่ห้อ/รุ่น</th>
                    <th>ห้อง</th>
                    <th>โรงเรียน</th>
                    <th>สถานะ</th>
                    {canManage && <th>จัดการ</th>}
                  </tr>
                </thead>
                <tbody>
                  {devices.map((d) => (
                    <tr key={d.device_id}>
                      <td className="table-id">{d.device_id}</td>
                      <td>{d.device_type}</td>
                      <td>{d.brand || '—'} {d.model || ''}</td>
                      <td>{d.room_name || d.room_code || '—'}</td>
                      <td>{d.organization_name || '—'}</td>
                      <td>
                        <span className={`badge badge-${d.status}`}>{d.status}</span>
                      </td>
                      {canManage && (
                        <td>
                          <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                            <button className="btn btn-secondary btn-sm" onClick={() => showQr(d)} style={{ padding: '4px 10px', fontSize: '0.78rem' }}>QR</button>
                            <button className="btn btn-secondary btn-sm" onClick={() => openEdit(d)} style={{ padding: '4px 10px', fontSize: '0.78rem' }}>แก้ไข</button>
                            <button className="btn btn-danger btn-sm" disabled={busy === d.device_id} onClick={() => handleDelete(d)} style={{ padding: '4px 10px', fontSize: '0.78rem' }}>
                              {busy === d.device_id ? '...' : 'ลบ'}
                            </button>
                          </div>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
