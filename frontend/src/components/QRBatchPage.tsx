import React, { useState, useEffect } from 'react';
import QRCode from 'qrcode';
import { api } from '../api/client';

export default function QRBatchPage({ onBack }: { onBack: () => void }) {
  const [devices, setDevices] = useState<any[]>([]);
  const [orgs, setOrgs] = useState<any[]>([]);
  const [orgFilter, setOrgFilter] = useState<number | ''>('');
  const [typeFilter, setTypeFilter] = useState<string>('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [qrMap, setQrMap] = useState<Record<string, string>>({});
  const [generating, setGenerating] = useState(false);

  const load = () => {
    setLoading(true);
    Promise.all([api.qrBatch(orgFilter ? orgFilter : undefined), api.listOrganizations()])
      .then(([d, o]) => { setDevices(d); setOrgs(o); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, [orgFilter]);

  const qrUrlFor = (d: any) =>
    d.qr_url && d.qr_url.startsWith('/scan')
      ? `${window.location.origin}${d.qr_url}`
      : `${window.location.origin}/scan?device=${encodeURIComponent(d.device_id)}`;

  const genAll = async () => {
    setGenerating(true);
    setError(null);
    const map: Record<string, string> = {};
    try {
      for (const d of visibleDevices) {
        map[d.device_id] = await QRCode.toDataURL(qrUrlFor(d), { width: 200, margin: 1 });
      }
      setQrMap(map);
    } catch {
      setError('สร้าง QR ไม่สำเร็จ (lib qrcode)');
    } finally {
      setGenerating(false);
    }
  };

  const printBatch = () => {
    if (Object.keys(qrMap).length === 0) { alert('กด "สร้าง QR ทั้งหมด" ก่อนพิมพ์'); return; }
    const win = window.open('', '_blank', 'width=800,height=600');
    if (!win) return;
    const rows = visibleDevices
      .map((d) => {
        const url = qrUrlFor(d);
        return `
          <div style="display:inline-block;border:1px dashed #999;border-radius:8px;padding:14px;margin:8px;text-align:center;page-break-inside:avoid;width:210px">
            <div style="font-size:13px;font-weight:600;margin-bottom:6px;font-family:sans-serif">${d.device_id}</div>
            <img src="${qrMap[d.device_id] || ''}" width="160" height="160" style="image-rendering:pixelated" />
            <div style="font-size:10px;color:#666;margin-top:4px;font-family:monospace">${url}</div>
          </div>`;
      })
      .join('');
    win.document.write(`<html><head><title>QR Batch — ${visibleDevices.length} อุปกรณ์</title>
      <style>@media print { body { margin: 10mm; } }</style></head>
      <body><h3 style="font-family:sans-serif">QR ติดอุปกรณ์ (${visibleDevices.length} เครื่อง)${typeFilter ? ` — หมวด ${typeFilter}` : ''}</h3>${rows}
      <script>window.onload = () => setTimeout(() => window.print(), 300);<${''}/script></body></html>`);
    win.document.close();
  };

  // ─── หมวดหมู่อุปกรณ์ที่มีอยู่จริง + จำนวนของแต่ละหมวด ───
  const typeCounts = devices.reduce<Record<string, number>>((acc, d) => {
    const t = d.device_type || 'Other';
    acc[t] = (acc[t] || 0) + 1;
    return acc;
  }, {});
  const typeOptions = Object.keys(typeCounts).sort((a, b) => a.localeCompare(b, 'th'));
  const visibleDevices = typeFilter
    ? devices.filter((d) => (d.device_type || 'Other') === typeFilter)
    : devices;

  return (
    <div className="page-content">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          </button>
          <div>
            <h1 className="top-bar-title">พิมพ์ QR (Batch)</h1>
            <span className="top-bar-subtitle">
              {typeFilter
                ? `${visibleDevices.length} เครื่อง · หมวด ${typeFilter} (ทั้งหมด ${devices.length})`
                : `QR ทั้งหมด ${devices.length} เครื่อง · ${typeOptions.length} หมวดหมู่`}
              {' '}— พิมพ์เป็นชุด พร้อมรหัสอ่านง่ายใต้ QR (TOR 1.5.4)
            </span>
          </div>
        </div>
        <div className="top-bar-actions">
          <select className="form-select" style={{ width: 180 }} value={orgFilter} onChange={(e) => setOrgFilter(e.target.value ? Number(e.target.value) : '')}>
            <option value="">ทุกโรงเรียน</option>
            {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
          </select>
          <select
            className="form-select"
            style={{ width: 200 }}
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
          <button className="btn btn-secondary" onClick={genAll} disabled={generating || visibleDevices.length === 0}>
            {generating ? 'กำลังสร้าง...' : 'สร้าง QR ทั้งหมด'}
          </button>
          <button className="btn btn-primary" onClick={printBatch} disabled={Object.keys(qrMap).length === 0}>พิมพ์ ({visibleDevices.length})</button>
        </div>
      </div>

      {error && <div style={{ padding: '10px 14px', background: 'var(--color-danger-light)', color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)', fontSize: '0.8rem', marginBottom: 16 }}>{error}</div>}

      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><div className="spinner" style={{ width: 30, height: 30, margin: '0 auto 12px' }} /></div>
      ) : devices.length === 0 ? (
        <div className="panel-card empty-text" style={{ padding: 40, textAlign: 'center' }}>
          ยังไม่มีอุปกรณ์ — เพิ่มอุปกรณ์ที่หน้า "อุปกรณ์" ก่อน
        </div>
      ) : (
        <div className="panel-card">
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: 12 }}>
            {visibleDevices.map((d) => (
              <div key={d.device_id} style={{ border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md)', padding: 12, textAlign: 'center' }}>
                <div style={{ fontWeight: 600, fontSize: '0.85rem', wordBreak: 'break-all' }}>{d.device_id}</div>
                <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)', margin: '2px 0 8px' }}>{d.device_type}{d.brand ? ` · ${d.brand}` : ''}</div>
                {qrMap[d.device_id] ? (
                  <img src={qrMap[d.device_id]} width={140} height={140} style={{ imageRendering: 'pixelated' }} alt={d.device_id} />
                ) : (
                  <div style={{ height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--color-text-tertiary)', fontSize: '0.75rem' }}>
                    ยังไม่ได้สร้าง
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
