import React, { useState, useEffect } from 'react';
import { api } from '../api/client';

const LEAD_STATUS: Record<string, { label: string; color: string }> = {
  new: { label: 'ใหม่', color: '#EF4444' },
  contacted: { label: 'ติดต่อแล้ว', color: '#10B981' },
  closed: { label: 'ปิดแล้ว', color: '#6B7280' },
};

function fmtDate(iso?: string | null): string {
  if (!iso) return '—';
  const d = new Date(iso);
  if (isNaN(d.getTime())) return iso;
  return d.toLocaleString('th-TH', {
    day: '2-digit', month: 'short', year: 'numeric',
    hour: '2-digit', minute: '2-digit',
  });
}

export default function SalesPage({ onBack, userRole }: { onBack: () => void; userRole?: string }) {
  const [leads, setLeads] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const loadLeads = () => api.listSalesLeads().then(setLeads);

  useEffect(() => {
    setLoading(true);
    setError(null);
    loadLeads()
      .catch((e) => setError(e?.message || 'โหลดข้อมูลไม่สำเร็จ'))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const markContacted = (id: number) => {
    setBusy(id);
    api.markLeadContacted(id)
      .then(() => loadLeads())
      .catch((e) => alert(e?.message || 'ทำเครื่องหมายไม่สำเร็จ'))
      .finally(() => setBusy(null));
  };

  const canDelete = userRole === 'super_admin' || userRole === 'admin';
  const removeLead = (id: number, name: string) => {
    if (!window.confirm(`ลบ lead "${name}" ทิ้ง? (ข้อมูลเทส/ซ้ำ)`)) return;
    setBusy(id);
    api.deleteSalesLead(id)
      .then(() => loadLeads())
      .catch((e) => alert(e?.message || 'ลบไม่สำเร็จ'))
      .finally(() => setBusy(null));
  };

  // ── สรุปยอด ──
  const total = leads.length;
  const contacted = leads.filter((l) => l.status === 'contacted').length;
  const newCount = leads.filter((l) => l.status === 'new').length;
  // สินค้าที่ถูกสนใจบ่อย (จาก products/interest)
  const productCount: Record<string, number> = {};
  leads.forEach((l) => {
    const prods = (l.products || '').split(',').map((s: string) => s.trim()).filter((s: string) => s.length > 0);
    prods.forEach((p: string) => { productCount[p] = (productCount[p] || 0) + 1; });
  });
  const topProducts = Object.entries(productCount).sort((a, b) => b[1] - a[1]).slice(0, 5);

  if (loading) {
    return (
      <div className="page-content">
        <div className="loading-state" style={{ padding: '60px' }}>
          <div className="spinner" />
          <span>กำลังโหลดข้อมูล...</span>
        </div>
      </div>
    );
  }

  return (
    <div className="page-content">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7" /></svg>
          </button>
          <div>
            <h1 className="top-bar-title">ยอดขาย &amp; การขอติดต่อ</h1>
            <span className="top-bar-subtitle">ผู้สนใจซื้อ / ขอให้ติดต่อกลับ จาก LINE และเว็บ</span>
          </div>
        </div>
        <div className="top-bar-actions">
          <button className="btn btn-ghost" onClick={() => { setLoading(true); loadLeads().catch((e) => setError(e.message)).finally(() => setLoading(false)); }}>⟳</button>
        </div>
      </div>

      {error && (
        <div style={{ padding: '10px 14px', background: 'var(--color-danger-light)', color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem', marginBottom: 16 }}>
          {error}
        </div>
      )}

      {/* สรุปยอด */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit,minmax(140px,1fr))', gap: 12, marginBottom: 16 }}>
        {[
          { label: 'Lead ทั้งหมด', value: total, color: 'var(--color-primary)' },
          { label: 'รอติดต่อกลับ', value: newCount, color: '#EF4444' },
          { label: 'ติดต่อแล้ว', value: contacted, color: '#10B981' },
        ].map((c) => (
          <div key={c.label} style={{
            background: 'var(--color-surface-raised, var(--color-surface))',
            border: '1px solid var(--color-border)', borderRadius: 'var(--radius-md, 12px)', padding: '16px 18px',
          }}>
            <div style={{ fontSize: '0.78rem', color: 'var(--color-text-tertiary)' }}>{c.label}</div>
            <div style={{ fontSize: '1.9rem', fontWeight: 700, color: c.color, lineHeight: 1.1 }}>{c.value}</div>
          </div>
        ))}
      </div>

      {/* สินค้าที่ถูกสนใจบ่อย */}
      {topProducts.length > 0 && (
        <div className="page-section">
          <div className="section-header">
            <span className="section-title">สินค้าที่ถูกสอบถามบ่อย</span>
          </div>
          <div className="section-body" style={{ display: 'flex', flexWrap: 'wrap', gap: 8 }}>
            {topProducts.map(([name, cnt]) => (
              <span key={name} className="badge" style={{ fontSize: '0.85rem', padding: '6px 14px' }}>
                {name} <span style={{ fontWeight: 700, marginLeft: 6 }}>{cnt}</span>
              </span>
            ))}
          </div>
        </div>
      )}

      <div className="page-section">
        <div className="section-header">
          <span className="section-title">รายชื่อผู้ขอติดต่อ / สนใจซื้อ ({total})</span>
          <span className="section-action">เรียงใหม่ล่าสุด</span>
        </div>
        <div className="section-body">
          {leads.length === 0 ? (
            <div className="empty-state" style={{ padding: '24px' }}>
              <span className="empty-text">ยังไม่มี lead — ผู้สนใจซื้อหรือขอติดต่อจาก LINE/เว็บจะปรากฏที่นี่</span>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ชื่อ</th><th>เบอร์</th><th>สนใจ / ต้องการ</th><th>สินค้า</th>
                    <th>สถานะ</th><th>วันที่</th><th>จัดการ</th>
                  </tr>
                </thead>
                <tbody>
                  {leads.map((l) => {
                    const st = LEAD_STATUS[l.status] || LEAD_STATUS.new;
                    return (
                      <tr key={l.id}>
                        <td style={{ fontWeight: 600 }}>{l.name || '—'}</td>
                        <td style={{ whiteSpace: 'nowrap' }}>{l.phone || '—'}</td>
                        <td style={{ fontSize: '0.82rem' }}>{l.interest || '—'}</td>
                        <td style={{ fontSize: '0.82rem', color: 'var(--color-text-secondary)' }}>{l.products || '—'}</td>
                        <td>
                          <span style={{
                            display: 'inline-block', padding: '2px 10px', borderRadius: 999,
                            fontSize: '0.75rem', fontWeight: 600, color: '#fff', background: st.color,
                          }}>
                            {st.label}
                          </span>
                        </td>
                        <td style={{ fontSize: '0.8rem', color: 'var(--color-text-tertiary)', whiteSpace: 'nowrap' }}>
                          {fmtDate(l.created_at)}
                        </td>
                        <td>
                          <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
                            {l.status === 'new' ? (
                              <button
                                className="btn btn-primary"
                                style={{ padding: '4px 10px', fontSize: '0.78rem' }}
                                disabled={busy === l.id}
                                onClick={() => markContacted(l.id)}
                              >
                                {busy === l.id ? '…' : 'ติดต่อแล้ว'}
                              </button>
                            ) : (
                              <span style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)' }}>ติดต่อแล้ว</span>
                            )}
                            {canDelete && (
                              <button
                                className="btn btn-danger"
                                style={{ padding: '4px 10px', fontSize: '0.78rem' }}
                                disabled={busy === l.id}
                                onClick={() => removeLead(l.id, l.name)}
                                title="ลบ lead"
                              >
                                🗑
                              </button>
                            )}
                          </div>
                        </td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
