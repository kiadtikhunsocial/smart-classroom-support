import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import type { SalesLead } from '../types/sales';
import SalesRecordsPanel from './SalesRecordsPanel';
import '../styles/sales.css';

/**
 * สีของ badge สถานะ lead — ใช้เป็น CSS property (background) จึงอ้าง var() ได้ตรง ๆ
 * และเปลี่ยนตามธีมเองโดยไม่ต้อง re-render (มี fallback กันกรณี token ยังไม่โหลด)
 */
const LEAD_STATUS: Record<string, { label: string; color: string }> = {
  new: { label: 'ใหม่', color: 'var(--status-new, #EF4444)' },
  contacted: { label: 'ติดต่อแล้ว', color: 'var(--status-resolved, #10B981)' },
  closed: { label: 'ปิดแล้ว', color: 'var(--status-closed, #6B7280)' },
};

/** ช่องทางที่ lead เข้ามา — WEB มาจากฟอร์มสมัครสมาชิกลูกค้า (/?customer=1) */
const LEAD_SOURCE_LABEL: Record<string, string> = {
  LINE: 'LINE',
  WEB: 'เว็บไซต์',
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
  const [view, setView] = useState<'overview' | 'records' | 'leads'>('overview');
  const [leadQuery, setLeadQuery] = useState('');
  const [leadStatus, setLeadStatus] = useState('all');
  const [leads, setLeads] = useState<SalesLead[]>([]);
  const [integrations, setIntegrations] = useState<{ google_sheet_configured: boolean; line_group_configured: boolean } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);

  const loadLeads = async () => {
    const all: SalesLead[] = [];
    while (true) {
      const page = await api.listSalesLeads(all.length);
      all.push(...page);
      if (page.length < 200) break;
    }
    setLeads(all);
  };

  useEffect(() => {
    setLoading(true);
    setError(null);
    loadLeads()
      .catch((e) => setError(e?.message || 'โหลดข้อมูลไม่สำเร็จ'))
      .finally(() => setLoading(false));
    api.getSalesIntegrations().then(setIntegrations).catch(() => setIntegrations(null));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const markContacted = (id: number) => {
    setBusy(id);
    api.markLeadContacted(id)
      .then(() => loadLeads())
      .catch((e) => alert(e?.message || 'ทำเครื่องหมายไม่สำเร็จ'))
      .finally(() => setBusy(null));
  };

  const canDelete = userRole === 'owner' || userRole === 'super_admin' || userRole === 'admin';
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
  const visibleLeads = leads.filter((lead) => {
    const needle = leadQuery.trim().toLocaleLowerCase();
    return (leadStatus === 'all' || lead.status === leadStatus)
      && (!needle || [lead.name, lead.phone, lead.interest, lead.products].some((value) =>
        (value || '').toLocaleLowerCase().includes(needle)));
  });

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
            <h1 className="top-bar-title">ลูกค้าและการขาย</h1>
            <span className="top-bar-subtitle">ติดตามผู้สนใจ บันทึกดีล และตรวจคำขอชำระเงินในที่เดียว</span>
          </div>
        </div>
        <div className="top-bar-actions">
          <a className="btn" href="/?customer=1" target="_blank" rel="noopener noreferrer">
            เปิดแบบฟอร์มลูกค้า ↗
          </a>
          <button
            className="btn btn-ghost btn-icon"
            onClick={() => { setLoading(true); loadLeads().catch((e) => setError(e.message)).finally(() => setLoading(false)); }}
            aria-label="โหลดใหม่"
            title="โหลดใหม่"
          >
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M21 12a9 9 0 11-3.5-7.1" />
              <path d="M21 3v6h-6" />
            </svg>
          </button>
        </div>
      </div>

      {error && (
        <div style={{ padding: '10px 14px', background: 'var(--color-danger-light)', color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem', marginBottom: 16 }}>
          {error}
        </div>
      )}

      {integrations && (!integrations.google_sheet_configured || !integrations.line_group_configured) && (
        <div role="status" className="sales-record-caution" style={{ marginBottom: 16 }}>
          ช่องทางแจ้งสำรองที่ยังไม่ได้ตั้งค่า: {' '}
          {!integrations.google_sheet_configured && 'Google Sheet'}
          {!integrations.google_sheet_configured && !integrations.line_group_configured && ' · '}
          {!integrations.line_group_configured && 'กลุ่ม LINE เจ้าหน้าที่'}
          {' '}— ข้อมูลยังบันทึกในฐานข้อมูลตามปกติ
        </div>
      )}

      <nav className="sales-main-tabs" aria-label="ส่วนของงานขาย">
        {([
          ['overview', 'ภาพรวม'], ['records', 'ดีลและการชำระเงิน'], ['leads', `รายชื่อลูกค้า (${total})`],
        ] as const).map(([key, label]) => (
          <button key={key} type="button" className={view === key ? 'sales-main-tab active' : 'sales-main-tab'}
            aria-current={view === key ? 'page' : undefined} onClick={() => setView(key)}>{label}</button>
        ))}
      </nav>

      {view === 'overview' && <>
      <div className="sales-overview-intro">
        <div><span className="sales-eyebrow">ภาพรวมงานขาย</span><h2>เริ่มจากลูกค้าที่รอการติดต่อ</h2>
          <p>ตัวเลขนี้เป็นจำนวนรายการ ไม่ใช่ยอดเงินรับชำระ ใช้แทนกันไม่ได้</p></div>
        <button type="button" className="btn btn-primary" onClick={() => setView('leads')}>ดูรายชื่อที่ต้องติดต่อ →</button>
      </div>
      <div className="sales-overview-kpis">
        {[
          { label: 'ลูกค้าทั้งหมด', value: total, color: 'var(--color-primary)', note: 'จากเว็บและ LINE' },
          { label: 'รอติดต่อกลับ', value: newCount, color: 'var(--status-new, #EF4444)', note: 'ควรเริ่มจากกลุ่มนี้' },
          { label: 'ติดต่อแล้ว', value: contacted, color: 'var(--status-resolved, #10B981)', note: 'ยังอาจมีดีลที่ต้องติดตาม' },
        ].map((c) => (
          <div key={c.label} className="sales-overview-kpi">
            <span>{c.label}</span><strong style={{ color: c.color }}>{c.value}</strong><small>{c.note}</small>
          </div>
        ))}
      </div>

      <div className="sales-next-actions">
        <button type="button" onClick={() => { setLeadStatus('new'); setView('leads'); }}>
          <strong>1 · ติดต่อผู้สนใจ</strong><span>ดูข้อมูลลูกค้าที่เพิ่งลงทะเบียนและบันทึกการติดต่อ</span><b>{newCount} ราย →</b>
        </button>
        <button type="button" onClick={() => setView('records')}>
          <strong>2 · บันทึกการซื้อขาย</strong><span>ติดตามสถานะดีล หรือรับคำขอชำระเงินให้เจ้าหน้าที่ตรวจ</span><b>เปิดบันทึก →</b>
        </button>
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
      </>}

      {view === 'records' && <SalesRecordsPanel leads={leads} canSyncSheet={Boolean(integrations?.google_sheet_configured && canDelete)} />}

      {view === 'leads' && <div className="page-section">
        <div className="section-header">
          <span className="section-title">รายชื่อลูกค้าและผู้สนใจ ({visibleLeads.length})</span>
          <span className="section-action">เรียงใหม่ล่าสุด</span>
        </div>
        <div className="section-body">
          <div className="sales-lead-filters">
            <label>ค้นหาชื่อ เบอร์ หรือสินค้า<input className="form-input" type="search" value={leadQuery} onChange={(e) => setLeadQuery(e.target.value)} placeholder="พิมพ์คำค้น" /></label>
            <label>สถานะ<select className="form-input" value={leadStatus} onChange={(e) => setLeadStatus(e.target.value)}>
              <option value="all">ทั้งหมด</option><option value="new">รอติดต่อกลับ</option><option value="contacted">ติดต่อแล้ว</option><option value="closed">ปิดแล้ว</option>
            </select></label>
          </div>
          {visibleLeads.length === 0 ? (
            <div className="empty-state" style={{ padding: '24px' }}>
              <span className="empty-text">ไม่พบลูกค้าตามเงื่อนไขนี้</span>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>ชื่อ</th><th>เบอร์</th><th>สนใจ / ต้องการ</th><th>สินค้า</th>
                    <th>ช่องทาง</th><th>สถานะ</th><th>วันที่</th><th>จัดการ</th>
                  </tr>
                </thead>
                <tbody>
                  {visibleLeads.map((l) => {
                    const st = LEAD_STATUS[l.status] || LEAD_STATUS.new;
                    return (
                      <tr key={l.id}>
                        <td style={{ fontWeight: 600 }}>{l.name || '—'}</td>
                        <td style={{ whiteSpace: 'nowrap' }}>{l.phone || '—'}</td>
                        <td style={{ fontSize: '0.82rem' }}>{l.interest || '—'}</td>
                        <td style={{ fontSize: '0.82rem', color: 'var(--color-text-secondary)' }}>{l.products || '—'}</td>
                        <td style={{ fontSize: '0.78rem', whiteSpace: 'nowrap' }}>{LEAD_SOURCE_LABEL[l.source] || l.source || 'LINE'}</td>
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
                                className="btn"
                                style={{ padding: '4px 10px', fontSize: '0.78rem' }}
                                disabled={busy === l.id || !integrations?.google_sheet_configured}
                                onClick={() => api.retrySalesLeadSheetSync(l.id)
                                  .then(() => alert('ส่งงานซิงก์ Google Sheet อีกครั้งแล้ว'))
                                  .catch((e) => alert(e?.message || 'ซิงก์ชีตไม่สำเร็จ'))}
                                title="ส่งรายการนี้ไป Google Sheet อีกครั้ง"
                              >ชีต</button>
                            )}
                            {canDelete && (
                              <button
                                className="btn btn-danger"
                                style={{ padding: '4px 10px', fontSize: '0.78rem' }}
                                disabled={busy === l.id}
                                onClick={() => removeLead(l.id, l.name)}
                                title="ลบ lead"
                              >
                                ลบ
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
      </div>}
    </div>
  );
}
