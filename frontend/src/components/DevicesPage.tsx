import React, { useState, useEffect, useMemo, useRef } from 'react';
import QRCode from 'qrcode';
import { api } from '../api/client';
import DetailField from './DetailField';
import '../styles/devices-page.css';

const DEVICE_TYPES = [
  'Interactive Display', 'Computer AIO', 'Computer Notebook', 'Computer Desktop',
  'Router', 'Access Point', 'Switch', 'Speaker', 'Camera', 'Visualizer',
  'Microphone', 'UPS', 'Printer', 'Projector', 'Software (Picaro)', 'Software (Phonics Hero)', 'Other',
];

const DEVICE_STATUSES = ['active', 'inactive', 'decommissioned'];

//: เกณฑ์ "ใกล้หมดประกัน" ต้องตรงกับ pm_rules.WARRANTY_WARN_DAYS ของ backend (PM Rule 2)
const WARRANTY_WARN_DAYS = 30;

const DEVICE_STATUS_LABELS: Record<string, string> = {
  active: 'ใช้งานอยู่',
  inactive: 'พักการใช้งาน',
  decommissioned: 'ปลดระวาง',
};

const TICKET_STATUS_LABELS: Record<string, string> = {
  new: 'รอรับเรื่อง',
  assigned: 'มอบหมายแล้ว',
  in_progress: 'กำลังดำเนินการ',
  pending: 'รอดำเนินการต่อ',
  waiting_parts: 'รออะไหล่',
  waiting_user: 'รอผู้แจ้งยืนยัน',
  resolved: 'ซ่อมเสร็จ รอยืนยัน',
  closed: 'ปิดงาน',
  cancelled: 'ยกเลิก',
};

type WarrantyStatus = 'active' | 'expiring' | 'expired' | 'unknown';

/** สถานะประกันจาก warranty_until — ใช้ทั้งในตารางและแผงรายละเอียด */
const warrantyInfo = (value: any): { status: WarrantyStatus; label: string; short: string; daysLeft: number | null } => {
  if (!value) return { status: 'unknown', label: 'ไม่มีข้อมูลวันสิ้นสุดประกัน', short: 'ไม่มีข้อมูล', daysLeft: null };
  const until = new Date(value);
  if (Number.isNaN(until.getTime())) {
    return { status: 'unknown', label: 'ไม่มีข้อมูลวันสิ้นสุดประกัน', short: 'ไม่มีข้อมูล', daysLeft: null };
  }
  const days = Math.floor((until.getTime() - Date.now()) / 86400000);
  if (days < 0) {
    return { status: 'expired', label: `หมดประกันมาแล้ว ${Math.abs(days)} วัน`, short: 'หมดประกัน', daysLeft: days };
  }
  if (days <= WARRANTY_WARN_DAYS) {
    return { status: 'expiring', label: `ใกล้หมดประกัน — เหลือ ${days} วัน`, short: `เหลือ ${days} วัน`, daysLeft: days };
  }
  return { status: 'active', label: `อยู่ในระยะประกัน — เหลือ ${days} วัน`, short: `เหลือ ${days} วัน`, daysLeft: days };
};

// ใช้ fallback ใน var() เพราะธีมบางชุดยังไม่ประกาศ --color-warning
const WARRANTY_COLOR: Record<WarrantyStatus, string> = {
  active: 'var(--color-success, #15803d)',
  expiring: 'var(--color-warning, #b45309)',
  expired: 'var(--color-danger, #b91c1c)',
  unknown: 'var(--color-text-tertiary, #94a3b8)',
};

/** วันที่แบบไทย ไม่มีเวลา — ข้อมูลทรัพย์สินเป็นระดับวัน */
const fmtDateTh = (v: any): string => {
  if (!v) return '—';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleDateString('th-TH', { dateStyle: 'medium' });
};

const fmtDateTimeTh = (v: any): string => {
  if (!v) return '—';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return String(v);
  return d.toLocaleString('th-TH', { dateStyle: 'medium', timeStyle: 'short' });
};

/** อายุอุปกรณ์จากวันจัดซื้อ — PM Rule 3 ใช้เกณฑ์เดียวกันคือนับจาก purchase_date */
const deviceAgeText = (v: any): string => {
  if (!v) return 'ไม่ทราบ (ไม่มีวันจัดซื้อ)';
  const d = new Date(v);
  if (Number.isNaN(d.getTime())) return 'ไม่ทราบ';
  const months = Math.max(0, Math.round((Date.now() - d.getTime()) / 2629800000));
  const years = Math.floor(months / 12);
  const rest = months % 12;
  if (years <= 0) return `${rest} เดือน`;
  return rest ? `${years} ปี ${rest} เดือน` : `${years} ปี`;
};

/** แถวข้อมูล label/value ในแผงรายละเอียด */
function DetailRow({ label, value, mono, wide }: { label: string; value: React.ReactNode; mono?: boolean; wide?: boolean }) {
  return <DetailField label={label} value={value} mono={mono} wide={wide} />;
}

// รหัสอุปกรณ์ต้องขึ้นต้นด้วยรหัสโรงเรียน — logic ต้องให้ผลตรงกับ _org_code_token
// ใน backend/app/main.py (A–Z0–9 ยาวไม่เกิน 8, ไม่มี code → ORG<id>)
const orgCodeToken = (org: { id?: number; code?: string | null } | undefined): string => {
  if (!org) return '';
  const token = String(org.code ?? '').replace(/[^A-Za-z0-9]/g, '').toUpperCase().slice(0, 8);
  if (token) return token;
  return org.id != null ? `ORG${org.id}` : '';
};

// เติมรหัสโรงเรียนให้รหัสที่ผู้ใช้พิมพ์เอง (คืน '' = ให้ backend สร้างอัตโนมัติ)
const withOrgPrefix = (raw: string, token: string): string => {
  const cleaned = raw.replace(/\s+/g, '').toUpperCase().replace(/^-+|-+$/g, '');
  if (!cleaned || !token) return cleaned;
  if (cleaned === token) return '';
  return cleaned.startsWith(`${token}-`) ? cleaned : `${token}-${cleaned}`;
};

/** ISO datetime จาก backend → ค่าของ <input type="date"> (YYYY-MM-DD) */
const toDateInput = (value: any): string =>
  value ? String(value).slice(0, 10) : '';

/** ค่าจาก <input type="date"> → ISO แบบมี timezone (+07:00)
 *  ส่งเป็น date เปล่าจะได้ datetime แบบไม่มี tz ซึ่งเทียบกับคอลัมน์ timestamptz
 *  ใน PM Rule ไม่ได้ จึงผูกเวลาเที่ยงคืนตามเวลาไทยไปเลย
 */
const dateInputToIso = (value: string): string | null =>
  value ? `${value}T00:00:00+07:00` : null;

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
  purchase_date: '',
  warranty_until: '',
  warranty_details: '',
  notes: '',
};

export default function DevicesPage({ onBack, onOpenTicket, currentOrgId, isSuperAdmin, canManage, userRole, focusId, onFocusHandled }: {
  onBack: () => void;
  onOpenTicket?: (id: string) => void;
  currentOrgId?: number | null;
  isSuperAdmin: boolean;
  canManage: boolean;
  userRole?: string;
  focusId?: string;
  onFocusHandled?: () => void;
}) {
  // admin_school จัดการได้เฉพาะรรตัวเอง — ไม่ต้องมี dropdown เลือกโรงเรียน และล็อกฟอร์มที่รรตัวเอง
  const lockedToOwnSchool = userRole === 'admin_school';
  const [devices, setDevices] = useState<any[]>([]);
  const [orgs, setOrgs] = useState<any[]>([]);
  const [deviceTypes, setDeviceTypes] = useState<string[]>(DEVICE_TYPES);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [orgFilter, setOrgFilter] = useState<number | ''>(isSuperAdmin ? '' : (currentOrgId ?? ''));
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [showForm, setShowForm] = useState(false);
  const [form, setForm] = useState(EMPTY_FORM);
  const [editingId, setEditingId] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [qrDevice, setQrDevice] = useState<any | null>(null);
  const [qrDataUrl, setQrDataUrl] = useState<string>('');
  const [rooms, setRooms] = useState<any[]>([]);
  const [roomsLoading, setRoomsLoading] = useState(false);
  // แผงรายละเอียดอุปกรณ์: เปิดจากแถวในตาราง แล้วดึงข้อมูลล่าสุด + ใบงานล่าสุดของเครื่องนั้น
  const [detailDevice, setDetailDevice] = useState<any | null>(null);
  const [detailData, setDetailData] = useState<any | null>(null);
  const [detailRecent, setDetailRecent] = useState<any | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState<string | null>(null);
  const [importFile, setImportFile] = useState<File | null>(null);
  const [importPreview, setImportPreview] = useState<any | null>(null);
  const [importBusy, setImportBusy] = useState(false);
  const [importError, setImportError] = useState('');
  // กันผลลัพธ์ของเครื่องที่กดก่อนหน้ามาทับ เมื่อผู้ใช้กดสลับเครื่องเร็ว ๆ
  const detailReqRef = useRef<string | null>(null);

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

  const openDetail = async (d: any) => {
    detailReqRef.current = d.device_id;
    setDetailDevice(d);
    setDetailData(null);
    setDetailRecent(null);
    setDetailError(null);
    setDetailLoading(true);
    const [full, recent] = await Promise.all([
      api.getDevice(d.device_id).catch(() => null),
      api.getDeviceRecent(d.device_id).catch(() => null),
    ]);
    if (detailReqRef.current !== d.device_id) return; // เปลี่ยนเครื่องไปแล้ว
    if (full) setDetailData(full);
    else setDetailError('โหลดข้อมูลล่าสุดไม่สำเร็จ — กำลังแสดงข้อมูลจากรายการอุปกรณ์แทน');
    setDetailRecent(recent?.recent_ticket ?? null);
    setDetailLoading(false);
  };

  const closeDetail = () => {
    detailReqRef.current = null;
    setDetailDevice(null);
    setDetailData(null);
    setDetailRecent(null);
    setDetailError(null);
    setDetailLoading(false);
  };
  useEffect(() => {
    if (!focusId) return;
    const found = devices.find((device) => device.device_id === focusId);
    if (found) { void openDetail(found); onFocusHandled?.(); }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusId, devices]);

  const load = () => {
    setLoading(true);
    Promise.all([
      api.listAllDevices(orgFilter === '' ? undefined : orgFilter),
      api.listOrganizations(),
      api.publicOptions(),
    ])
      .then(([d, o, options]) => { setDevices(d); setOrgs(o); setDeviceTypes(options.device_types); })
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
      purchase_date: toDateInput(d.purchase_date),
      warranty_until: toDateInput(d.warranty_until),
      warranty_details: d.warranty_details || '',
      notes: d.notes || '',
    });
    setEditingId(d.device_id);
    setShowForm(true);
  };

  // โรงเรียนที่ฟอร์มกำลังอ้างถึง + prefix รหัสอุปกรณ์ของโรงเรียนนั้น
  const formOrgId = Number(lockedToOwnSchool ? (currentOrgId ?? form.organization_id) : form.organization_id);
  const selectedOrg = orgs.find((o) => o.id === formOrgId);
  const devicePrefix = orgCodeToken(selectedOrg);
  // รหัสที่จะถูกส่งจริง ('' = ให้ระบบสร้างต่อท้าย prefix เอง)
  const previewDeviceId = withOrgPrefix(form.device_id, devicePrefix);

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
          // ล้างช่องวันที่ให้ว่างได้ → ส่ง null (PATCH ใช้ exclude_unset จึงต้องส่งค่ามาจริง)
          purchase_date: dateInputToIso(form.purchase_date),
          warranty_until: dateInputToIso(form.warranty_until),
          warranty_details: form.warranty_details.trim() || null,
          notes: form.notes,
        });
      } else {
        await api.createDevice({
          device_id: previewDeviceId || undefined,
          organization_id: form.organization_id,
          room_code: form.room_code || undefined,
          device_type: form.device_type,
          brand: form.brand || undefined,
          model: form.model || undefined,
          serial_number: form.serial_number || undefined,
          firmware_version: form.firmware_version || undefined,
          status: form.status,
          purchase_date: dateInputToIso(form.purchase_date) ?? undefined,
          warranty_until: dateInputToIso(form.warranty_until) ?? undefined,
          warranty_details: form.warranty_details.trim() || undefined,
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
      closeDetail();
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
      alert('เพิ่มห้องเรียบร้อย');
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

  // ─── หมวดหมู่อุปกรณ์: นับจำนวนจริงในรายการ + เรียงตามลำดับใน DEVICE_TYPES ───
  const typeCounts = devices.reduce<Record<string, number>>((acc, d) => {
    const t = d.device_type || 'Other';
    acc[t] = (acc[t] || 0) + 1;
    return acc;
  }, {});
  const typeOptions = Object.keys(typeCounts).sort((a, b) => {
    const ia = deviceTypes.indexOf(a);
    const ib = deviceTypes.indexOf(b);
    if (ia !== -1 && ib !== -1) return ia - ib;
    if (ia !== -1) return -1;
    if (ib !== -1) return 1;
    return a.localeCompare(b, 'th');
  });
  const visibleDevices = typeFilter
    ? devices.filter((d) => (d.device_type || 'Other') === typeFilter)
    : devices;

  // สรุปสถานะประกันของรายการที่เห็นอยู่ — ให้ผู้ดูแลรู้ภาพรวมก่อนไล่ดูรายเครื่อง
  const warrantySummary = useMemo(() => {
    const acc = { total: visibleDevices.length, active: 0, expiring: 0, expired: 0, unknown: 0 };
    for (const d of visibleDevices) acc[warrantyInfo(d.warranty_until).status] += 1;
    return acc;
  }, [visibleDevices]);

  // แผงรายละเอียดใช้ข้อมูลล่าสุดถ้าโหลดมาได้ ไม่ได้ก็ใช้แถวที่กดมา
  const detailView = detailData || detailDevice;
  const detailWarranty = warrantyInfo(detailView?.warranty_until);
  const detailOpenTicket = detailView?.open_ticket ?? null;
  const detailIsDemo = /mock|ตัวอย่าง|เดโม/i.test(`${detailView?.notes || ''} ${detailView?.serial_number || ''}`);

  return (
    <div className="devices-page">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
          </button>
          <div>
            <h1 className="top-bar-title">อุปกรณ์ทั้งหมด</h1>
            <span className="top-bar-subtitle">
              {typeFilter
                ? `${visibleDevices.length} เครื่อง · หมวด ${typeFilter} (ทั้งหมด ${devices.length})`
                : `${devices.length} เครื่อง · ${typeOptions.length} หมวดหมู่`}
              {!loading && warrantySummary.total > 0 && (
                ` · ประกันปกติ ${warrantySummary.active} · ใกล้หมด ${warrantySummary.expiring}`
                + ` · หมดแล้ว ${warrantySummary.expired}`
                + (warrantySummary.unknown ? ` · ไม่มีข้อมูล ${warrantySummary.unknown}` : '')
              )}
            </span>
          </div>
        </div>
        <div className="top-bar-actions" style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
          {isSuperAdmin && !lockedToOwnSchool && (
            <select className="form-select" style={{ width: 200 }} value={orgFilter} onChange={(e) => setOrgFilter(e.target.value === '' ? '' : Number(e.target.value))}>
              <option value="">ทุกโรงเรียน</option>
              {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
            </select>
          )}
          <select
            className="form-select"
            style={{ width: 210 }}
            value={typeFilter}
            onChange={(e) => setTypeFilter(e.target.value)}
            aria-label="กรองตามหมวดหมู่อุปกรณ์"
            disabled={loading || typeOptions.length === 0}
          >
            <option value="">ทุกหมวดหมู่อุปกรณ์</option>
            {typeOptions.map((t) => (
              <option key={t} value={t}>{t} ({typeCounts[t]})</option>
            ))}
          </select>
          <button className="btn btn-primary" onClick={openAdd} disabled={!canManage}>
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 6, verticalAlign: 'middle' }}>
              <path d="M12 5v14M5 12h14"/>
            </svg>
            เพิ่มอุปกรณ์
          </button>
          {canManage && <button className="btn btn-secondary" onClick={() => { setImportFile(null); setImportPreview(null); setImportError(''); document.getElementById('device-csv-import')?.click(); }}>นำเข้า Google Sheets CSV</button>}
          <input id="device-csv-import" type="file" accept=".csv,text/csv" style={{ display: 'none' }} onChange={async (e) => {
            const file = e.target.files?.[0]; e.target.value = '';
            if (!file) return;
            setImportFile(file); setImportPreview(null); setImportBusy(true); setImportError('');
            try { setImportPreview(await api.importDevicesCsv(file)); }
            catch (err: any) { setImportError(err.message || 'ตรวจไฟล์ไม่สำเร็จ'); }
            finally { setImportBusy(false); }
          }} />
          <button className="btn btn-ghost btn-icon" onClick={load} aria-label="โหลดใหม่" title="โหลดใหม่">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M21 12a9 9 0 11-3.5-7.1" />
              <path d="M21 3v6h-6" />
            </svg>
          </button>
        </div>
      </div>

      {(importFile || importBusy) && <div className="panel-overlay" onClick={() => { if (!importBusy) setImportFile(null); }}>
        <div className="repair-panel" style={{ width: 680, maxWidth: '96vw' }} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="นำเข้าอุปกรณ์จาก Google Sheets">
          <div className="repair-panel-header"><h3 className="repair-panel-title">นำเข้าอุปกรณ์จาก Google Sheets</h3><button className="repair-panel-close" onClick={() => setImportFile(null)} aria-label="ปิด">×</button></div>
          <div className="repair-panel-body">
            <p>ใน Google Sheets เลือก ไฟล์ → ดาวน์โหลด → ค่าที่คั่นด้วยจุลภาค (.csv) แล้วเลือกไฟล์ที่นี่ ระบบจะตรวจทุกแถวก่อนเพิ่มข้อมูล โดยไม่เขียนทับอุปกรณ์เดิม</p>
            <p>คอลัมน์จำเป็น: <code>organization_code, device_id, device_type</code> · เพิ่ม <code>room_code, brand, model, serial_number, firmware_version, status, purchase_date, warranty_until, warranty_details, notes</code> ได้ วันที่ใช้ YYYY-MM-DD</p>
            <button className="btn btn-secondary" type="button" onClick={() => {
              const csv = '\uFEFForganization_code,device_id,device_type,room_code,brand,model,serial_number,firmware_version,status,purchase_date,warranty_until,warranty_details,notes\r\n';
              const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }));
              const link = document.createElement('a'); link.href = url; link.download = 'device-import-template.csv'; link.click();
              window.setTimeout(() => URL.revokeObjectURL(url), 1000);
            }}>ดาวน์โหลดแม่แบบ CSV</button>
            <p>ไฟล์: {importFile?.name} {importBusy ? '· กำลังตรวจ...' : ''}</p>
            {importError && <p role="alert" style={{ color: 'var(--color-danger)' }}>{importError}</p>}
            {importPreview && <>
              <p><strong>ทั้งหมด {importPreview.total} แถว · พร้อมนำเข้า {importPreview.valid} · ต้องแก้ไข {importPreview.invalid}</strong></p>
              <div style={{ maxHeight: 280, overflowY: 'auto' }}><table className="data-table"><thead><tr><th>แถว</th><th>โรงเรียน</th><th>รหัส</th><th>ประเภท</th><th>ผลตรวจ</th></tr></thead><tbody>{importPreview.rows.map((r: any) => <tr key={r.row}><td>{r.row}</td><td>{r.organization_code}</td><td>{r.device_id}</td><td>{r.device_type}</td><td style={{ color: r.errors.length ? 'var(--color-danger)' : 'var(--color-success)' }}>{r.errors.length ? r.errors.join(', ') : 'พร้อม'}</td></tr>)}</tbody></table></div>
              <button className="btn btn-primary" disabled={importBusy || importPreview.invalid > 0 || !importPreview.valid} onClick={async () => {
                if (!importFile) return;
                setImportBusy(true); setImportError('');
                try { const result = await api.importDevicesCsv(importFile, true); setImportFile(null); setImportPreview(null); load(); alert(`นำเข้าอุปกรณ์ ${result.imported} รายการแล้ว`); }
                catch (err: any) { setImportError(err.message || 'นำเข้าไม่สำเร็จ'); }
                finally { setImportBusy(false); }
              }}>ยืนยันนำเข้า {importPreview.valid} รายการ</button>
            </>}
          </div>
        </div>
      </div>}

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
              <button className="repair-panel-close" onClick={() => setShowForm(false)} aria-label="ปิด" title="ปิด">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="repair-panel-body">
              <form onSubmit={handleSave}>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label" htmlFor="device-id-input">รหัสอุปกรณ์</label>
                    <input
                      id="device-id-input"
                      className="form-input"
                      value={form.device_id}
                      onChange={(e) => setForm({ ...form, device_id: e.target.value })}
                      placeholder={devicePrefix ? `เว้นว่าง = สร้างอัตโนมัติ (${devicePrefix}-…)` : 'เว้นว่าง = สร้างอัตโนมัติ'}
                      disabled={!!editingId}
                      aria-describedby="device-id-hint"
                    />
                    {!editingId && (
                      <div
                        id="device-id-hint"
                        style={{ marginTop: 4, fontSize: '0.75rem', color: 'var(--color-text-tertiary)', overflowWrap: 'anywhere' }}
                      >
                        {!devicePrefix
                          ? 'เลือกโรงเรียนก่อน — รหัสอุปกรณ์จะผูกกับรหัสของโรงเรียนนั้น'
                          : previewDeviceId
                            ? `จะบันทึกเป็น ${previewDeviceId}`
                            : `แต่ละโรงเรียนมีรหัสของตัวเอง ระบบจะขึ้นต้นด้วย ${devicePrefix}- เพื่อไม่ให้รหัสซ้ำกับโรงเรียนอื่น`}
                      </div>
                    )}
                  </div>
                  <div className="form-group">
                    <label className="form-label">โรงเรียน *</label>
                    {lockedToOwnSchool ? (
                      <input className="form-input" value={orgs.find((o) => o.id === (currentOrgId ?? form.organization_id))?.name || '—'}
                        disabled title="ผู้ดูแลโรงเรียนจัดการได้เฉพาะโรงเรียนของตนเอง" />
                    ) : (
                      <select className="form-select" value={form.organization_id} onChange={(e) => setForm({ ...form, organization_id: Number(e.target.value) })} disabled={!!editingId}>
                        <option value={0}>— เลือกโรงเรียน —</option>
                        {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                      </select>
                    )}
                  </div>
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">ประเภทอุปกรณ์</label>
                    <select className="form-select" value={form.device_type} onChange={(e) => setForm({ ...form, device_type: e.target.value })}>
                      {deviceTypes.map((t) => <option key={t} value={t}>{t}</option>)}
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
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label" htmlFor="device-purchase-date">วันที่จัดซื้อ</label>
                    <input
                      id="device-purchase-date"
                      type="date"
                      className="form-input"
                      value={form.purchase_date}
                      max={form.warranty_until || undefined}
                      onChange={(e) => setForm({ ...form, purchase_date: e.target.value })}
                    />
                  </div>
                  <div className="form-group">
                    <label className="form-label" htmlFor="device-warranty-until">วันหมดประกัน</label>
                    <input
                      id="device-warranty-until"
                      type="date"
                      className="form-input"
                      value={form.warranty_until}
                      min={form.purchase_date || undefined}
                      onChange={(e) => setForm({ ...form, warranty_until: e.target.value })}
                    />
                    <div style={{ fontSize: '0.7rem', color: 'var(--color-text-tertiary)', marginTop: 4 }}>
                      ใช้แจ้งเตือน “ประกันใกล้หมด” ใน PM (ภายใน 30 วัน)
                    </div>
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">รายละเอียดประกันที่ให้บอตตอบลูกค้า</label>
                  <textarea className="form-textarea" rows={3} maxLength={500} value={form.warranty_details} onChange={(e) => setForm({ ...form, warranty_details: e.target.value })} placeholder="เช่น ประกันอุปกรณ์ 3 ปีจากผู้ขาย ติดต่อฝ่ายบริการพร้อมใบเสร็จ" />
                  <div style={{ fontSize: '0.7rem', color: 'var(--color-text-tertiary)', marginTop: 4 }}>ข้อมูลนี้อาจถูกแสดงใน LINE หลังลูกค้าระบุรหัสอุปกรณ์หรือ Serial ห้ามใส่ข้อมูลส่วนตัว</div>
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
              <button className="repair-panel-close" onClick={() => setQrDevice(null)} aria-label="ปิด" title="ปิด">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
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
                ดาวน์โหลด PNG
              </button>
            </div>
          </div>
        </div>
      )}

      {/* แผงรายละเอียดอุปกรณ์ */}
      {detailDevice && (
        <div className="panel-overlay" onClick={closeDetail}>
          <div className="repair-panel detail-sheet" style={{ width: 740, maxWidth: '96vw' }} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-labelledby="device-detail-title">
            <div className="repair-panel-header">
              <h3 className="repair-panel-title" id="device-detail-title">รายละเอียดอุปกรณ์</h3>
              <button className="repair-panel-close" onClick={closeDetail} aria-label="ปิด" title="ปิด">
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
            </div>
            <div className="repair-panel-body">
              {detailLoading && (
                <div className="loading-state" style={{ padding: '16px 0' }}>
                  <div className="spinner" style={{ width: 24, height: 24 }} />
                  <span>กำลังโหลดข้อมูลล่าสุด...</span>
                </div>
              )}

              {detailError && (
                <div className="detail-sheet-warning" role="alert">
                  {detailError}
                </div>
              )}

              {!detailLoading && detailView && (
                <>
                  <div className="detail-sheet-identity">
                    <p className="detail-sheet-kicker">{detailView.device_id}</p>
                    <h4 className="detail-sheet-name">{detailView.device_type}</h4>
                    <p className="detail-sheet-subtitle">{[detailView.brand, detailView.model].filter(Boolean).join(' ') || 'ไม่ระบุยี่ห้อ/รุ่น'}</p>
                    <div className="detail-sheet-statuses">
                      {detailIsDemo && <span>ข้อมูลตัวอย่าง · ตรวจสอบก่อนใช้งานจริง</span>}
                      <span>{DEVICE_STATUS_LABELS[detailView.status] || detailView.status}</span>
                      <span>{detailWarranty.label}</span>
                    </div>
                  </div>

                  <section className="detail-sheet-section"><h4>ข้อมูลเครื่องและประกัน</h4>
                  <dl className="detail-sheet-grid">
                    <DetailRow label="รหัสอุปกรณ์" value={detailView.device_id} mono />
                    <DetailRow label="หมายเลขสินค้า (Serial)" value={detailView.serial_number || 'ไม่ระบุ'} mono />
                    <DetailRow label="เฟิร์มแวร์" value={detailView.firmware_version || '—'} />
                    <DetailRow label="วันที่จัดซื้อ" value={fmtDateTh(detailView.purchase_date)} />
                    <DetailRow label="อายุใช้งาน" value={deviceAgeText(detailView.purchase_date)} />
                    <DetailRow label="ประกันสิ้นสุด" value={fmtDateTh(detailView.warranty_until)} />
                    <DetailRow label="รายละเอียดประกันสำหรับลูกค้า" value={detailView.warranty_details || 'ยังไม่ระบุ'} wide />
                  </dl></section>

                  <section className="detail-sheet-section"><h4>ตำแหน่งติดตั้ง</h4>
                  <dl className="detail-sheet-grid">
                    <DetailRow label="โรงเรียน" value={detailView.organization_name || '—'} />
                    <DetailRow label="รหัสโรงเรียน" value={detailView.organization_code || '—'} mono />
                    <DetailRow
                      label="ห้อง"
                      value={
                        detailView.room_name
                          ? `${detailView.room_name}${detailView.room_code ? ` (${detailView.room_code})` : ''}`
                          : detailView.room_code || 'ไม่ระบุห้อง'
                      }
                    />
                    <DetailRow
                      label="อาคาร / ชั้น"
                      value={[detailView.building, detailView.floor ? `ชั้น ${detailView.floor}` : ''].filter(Boolean).join(' · ') || '—'}
                    />
                    <DetailRow
                      label="พิกัด"
                      value={
                        detailIsDemo ? 'พิกัดตัวอย่าง — ไม่ใช่ตำแหน่งจริง' : detailView.gps_lat != null && detailView.gps_lng != null ? (
                          <a
                            href={`https://www.google.com/maps?q=${detailView.gps_lat},${detailView.gps_lng}`}
                            target="_blank"
                            rel="noreferrer"
                          >
                            {Number(detailView.gps_lat).toFixed(5)}, {Number(detailView.gps_lng).toFixed(5)}
                          </a>
                        ) : (
                          '—'
                        )
                      }
                    />
                    <DetailRow label="QR ผูกกับเครื่อง" value={detailView.qr_token ? 'มีแล้ว' : 'ยังไม่มี'} />
                  </dl></section>

                  <section className="detail-sheet-section"><h4>งานซ่อม</h4>
                  {detailView.has_open_ticket && detailOpenTicket ? (
                    <div className="device-active-repair" role="status">
                      <div><span className="device-active-repair-label">● มีงานซ่อมที่กำลังดำเนินการ</span><strong>{detailOpenTicket.ticket_id || detailOpenTicket.ticket_no}</strong></div>
                      <p>{detailOpenTicket.title || 'ไม่ระบุอาการ'} · {TICKET_STATUS_LABELS[detailOpenTicket.status] || detailOpenTicket.status || 'รอตรวจสอบ'}</p>
                      <button type="button" className="btn btn-secondary btn-sm" onClick={() => { const id = detailOpenTicket.ticket_id || detailOpenTicket.ticket_no; closeDetail(); onOpenTicket?.(id); }} disabled={!onOpenTicket}>เปิดใบงานนี้ →</button>
                      <small>อุปกรณ์นี้ยังมีงานค้างอยู่ โปรดติดตามใบเดิมก่อนแจ้งซ้ำ</small>
                    </div>
                  ) : (
                    <p className="detail-sheet-empty">
                      ไม่มีใบงานค้างในขณะนี้
                    </p>
                  )}

                  {detailRecent ? (
                    <dl className="detail-sheet-grid" style={{ marginTop: 15 }}>
                      <DetailRow label="ใบงานล่าสุด" value={detailRecent.ticket_id} mono />
                      <DetailRow label="สถานะ" value={TICKET_STATUS_LABELS[detailRecent.status] || detailRecent.status} />
                      <DetailRow label="อาการที่แจ้ง" value={detailRecent.title || '—'} />
                      <DetailRow label="แจ้งเมื่อ" value={fmtDateTimeTh(detailRecent.created_at)} />
                      <DetailRow label="ปิดงานเมื่อ" value={fmtDateTimeTh(detailRecent.closed_at)} />
                    </dl>
                  ) : (
                    <p className="detail-sheet-empty" style={{ marginTop: 12 }}>
                      ยังไม่เคยมีประวัติแจ้งซ่อมของเครื่องนี้
                    </p>
                  )}
                  </section>

                  <section className="detail-sheet-section"><h4>หมายเหตุ / ข้อมูลจัดซื้อ</h4>
                  <div className="detail-sheet-note">
                    {detailView.notes || 'ไม่มีหมายเหตุ'}
                  </div>
                  </section>
                </>
              )}
            </div>
            {!detailLoading && detailView && <div className="detail-sheet-footer">
                    <button
                      className="btn btn-secondary"
                      onClick={() => { const d = detailView; closeDetail(); showQr(d); }}
                    >
                      ดู QR Code
                    </button>
                    {canManage && (
                      <button
                        className="btn btn-primary"
                        onClick={() => { const d = detailView; closeDetail(); openEdit(d); }}
                      >
                        แก้ไขข้อมูล
                      </button>
                    )}
                    {canManage && <button className="btn btn-danger" disabled={busy === detailView.device_id} onClick={() => void handleDelete(detailView)}>{busy === detailView.device_id ? 'กำลังลบ…' : 'ลบอุปกรณ์'}</button>}
                    <button className="btn btn-ghost" onClick={closeDetail}>ปิด</button>
                  </div>}
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
          ) : visibleDevices.length === 0 ? (
            <div className="empty-state" style={{ padding: '40px' }}>
              <svg className="empty-icon" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="2" y="4" width="20" height="14" rx="2"/>
                <path d="M2 10h20M12 14v6"/>
              </svg>
              <span className="empty-text">
                {typeFilter
                  ? `ไม่มีอุปกรณ์ในหมวด "${typeFilter}" — เลือก "ทุกหมวดหมู่อุปกรณ์" เพื่อดูทั้งหมด`
                  : 'ไม่มีอุปกรณ์ — กด "เพิ่มอุปกรณ์" เพื่อเพิ่มเครื่องแรก'}
              </span>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>รหัส</th>
                    <th>ประเภท</th>
                    <th>ยี่ห้อ/รุ่น</th>
                    <th>Serial No.</th>
                    <th>ห้อง</th>
                    <th>โรงเรียน</th>
                    <th>ประกัน</th>
                    <th>สถานะ</th>
                    <th>จัดการ</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleDevices.map((d) => (
                    <tr key={d.device_id} className="clickable-data-row" tabIndex={0}
                      aria-label={`ดูรายละเอียดอุปกรณ์ ${d.device_id}`}
                      onClick={(e) => { if (!(e.target as HTMLElement).closest('button, a, select, input')) void openDetail(d); }}
                      onKeyDown={(e) => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); void openDetail(d); } }}>
                      <td className="table-id">
                        <button
                          type="button"
                          onClick={() => openDetail(d)}
                          title="ดูรายละเอียดอุปกรณ์"
                          className="device-id-link"
                        >
                          {d.device_id}
                        </button>
                        {d.has_open_ticket && <span className="device-open-ticket-badge">มีงานซ่อม</span>}
                      </td>
                      <td>{d.device_type}{/mock|ตัวอย่าง|เดโม/i.test(`${d.notes || ''} ${d.serial_number || ''}`) && <span className="badge badge-pending" style={{ marginLeft: 6 }}>DEMO</span>}</td>
                      <td>{d.brand || '—'} {d.model || ''}</td>
                      <td style={{ fontFamily: 'ui-monospace, SFMono-Regular, Menlo, monospace', fontSize: '0.8rem' }}>
                        {d.serial_number || '—'}
                      </td>
                      <td>
                        {d.room_name || d.room_code || '—'}
                        {d.building && (
                          <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)' }}>
                            {d.building}{d.floor ? ` · ชั้น ${d.floor}` : ''}
                          </div>
                        )}
                      </td>
                      <td>{d.organization_name || '—'}</td>
                      <td>
                        {(() => {
                          const w = warrantyInfo(d.warranty_until);
                          return (
                            <span
                              style={{ display: 'inline-flex', alignItems: 'center', gap: 6, fontSize: '0.78rem', fontWeight: 600, color: WARRANTY_COLOR[w.status], whiteSpace: 'nowrap' }}
                              title={`${w.label} · สิ้นสุด ${fmtDateTh(d.warranty_until)}`}
                            >
                              <span style={{ width: 7, height: 7, borderRadius: '50%', background: 'currentColor', flexShrink: 0 }} aria-hidden="true" />
                              {w.short}
                            </span>
                          );
                        })()}
                      </td>
                      <td>
                        <span className={`badge badge-${d.status}`}>{DEVICE_STATUS_LABELS[d.status] || d.status}</span>
                      </td>
                      <td>
                        <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                          <button className="btn btn-secondary btn-sm" onClick={() => openDetail(d)} style={{ padding: '4px 10px', fontSize: '0.78rem' }}>รายละเอียด</button>
                          {canManage && (
                            <>
                              <button className="btn btn-secondary btn-sm" onClick={() => showQr(d)} style={{ padding: '4px 10px', fontSize: '0.78rem' }}>QR</button>
                              <button className="btn btn-secondary btn-sm" onClick={() => openEdit(d)} style={{ padding: '4px 10px', fontSize: '0.78rem' }}>แก้ไข</button>
                            </>
                          )}
                        </div>
                      </td>
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
