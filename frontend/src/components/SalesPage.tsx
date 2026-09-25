import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import type { SalesLead, SalesRecord, SalesSummary } from '../types/sales';
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
  DEMO: 'ตัวอย่าง',
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
  const [leadType, setLeadType] = useState<'all' | 'real' | 'demo'>('all');
  const [leads, setLeads] = useState<SalesLead[]>([]);
  const [summary, setSummary] = useState<SalesSummary | null>(null);
  const [records, setRecords] = useState<SalesRecord[]>([]);
  const [recordsLoading, setRecordsLoading] = useState(true);
  const [recordsError, setRecordsError] = useState(false);
  const [integrations, setIntegrations] = useState<{ google_sheet_configured: boolean; line_group_configured: boolean } | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState<number | null>(null);
  const [selectedLead, setSelectedLead] = useState<SalesLead | null>(null);

  const loadLeads = async () => {
    const all: SalesLead[] = [];
    while (true) {
      const page = await api.listSalesLeads(all.length);
      all.push(...page);
      if (page.length < 200) break;
    }
    setLeads(all);
  };

  const loadRecords = async () => {
    setRecordsLoading(true); setRecordsError(false);
    try {
      const all: SalesRecord[] = [];
      while (true) {
        const page = await api.listSalesRecords(all.length);
        all.push(...page);
        if (page.length < 200) break;
      }
      setRecords(all);
    } catch { setRecordsError(true); }
    finally { setRecordsLoading(false); }
  };

  useEffect(() => {
    setLoading(true);
    setError(null);
    loadLeads()
      .catch((e) => setError(e?.message || 'โหลดข้อมูลไม่สำเร็จ'))
      .finally(() => setLoading(false));
    api.getSalesIntegrations().then(setIntegrations).catch(() => setIntegrations(null));
    api.getSalesSummary().then(setSummary).catch(() => setSummary(null));
    void loadRecords();
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
      .then(() => { setSelectedLead(null); return loadLeads(); })
      .catch((e) => alert(e?.message || 'ลบไม่สำเร็จ'))
      .finally(() => setBusy(null));
  };

  // ── สรุปยอด ──
  const realLeads = leads.filter((l) => l.source !== 'DEMO');
  const demoCount = leads.length - realLeads.length;
  const total = realLeads.length;
  const contacted = realLeads.filter((l) => l.status === 'contacted').length;
  const newCount = realLeads.filter((l) => l.status === 'new').length;
  // สินค้าที่ถูกสนใจบ่อย (จาก products/interest)
  const productCount: Record<string, number> = {};
  realLeads.forEach((l) => {
    const prods = (l.products || '').split(',').map((s: string) => s.trim()).filter((s: string) => s.length > 0);
    prods.forEach((p: string) => { productCount[p] = (productCount[p] || 0) + 1; });
  });
  const topProducts = Object.entries(productCount).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const realLeadIds = new Set(realLeads.map((lead) => lead.id));
  const realRecords = records.filter((record) => realLeadIds.has(record.lead_id));
  const latestDeals = realRecords.filter((record) => record.kind === 'deal').slice(0, 6);
  const monthBuckets = Array.from({ length: 6 }, (_, index) => {
    const date = new Date(); date.setDate(1); date.setMonth(date.getMonth() - (5 - index));
    const key = `${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`;
    const value = realRecords.filter((record) => record.kind === 'deal' && record.status === 'won'
      && (record.updated_at || record.created_at).slice(0, 7) === key)
      .reduce((sum, record) => sum + Number(record.amount_thb || 0), 0);
    return { key, label: date.toLocaleDateString('th-TH', { month: 'short' }), value };
  });
  const maxMonthAmount = Math.max(1, ...monthBuckets.map((month) => month.value));
  const visibleLeads = leads.filter((lead) => {
    const needle = leadQuery.trim().toLocaleLowerCase();
    return (leadStatus === 'all' || lead.status === leadStatus)
      && (leadType === 'all' || (leadType === 'demo') === (lead.source === 'DEMO'))
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
            onClick={() => { setLoading(true); loadLeads().catch((e) => setError(e.message)).finally(() => setLoading(false)); api.getSalesSummary().then(setSummary).catch(() => setSummary(null)); void loadRecords(); }}
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

      {demoCount > 0 && <div role="note" className="sales-demo-notice">
        มีข้อมูลตัวอย่าง {demoCount} รายชื่อเพื่อทดลองหน้าจอ — ไม่มีข้อมูลติดต่อจริง และไม่นับรวมยอดขายจริง
        <button type="button" onClick={() => { setLeadType('demo'); setView('leads'); }}>ดูข้อมูลตัวอย่าง →</button>
      </div>}

      <nav className="sales-main-tabs" aria-label="ส่วนของงานขาย">
        {([
          ['overview', 'ภาพรวม'], ['records', 'ดีลและการชำระเงิน'], ['leads', `รายชื่อลูกค้า (${leads.length})`],
        ] as const).map(([key, label]) => (
          <button key={key} type="button" className={view === key ? 'sales-main-tab active' : 'sales-main-tab'}
            aria-current={view === key ? 'page' : undefined} onClick={() => setView(key)}>{label}</button>
        ))}
      </nav>

      {view === 'overview' && <>
      <div className="sales-overview-intro">
        <div><span className="sales-eyebrow">ภาพรวมงานขาย</span><h2>เริ่มจากลูกค้าที่รอการติดต่อ</h2>
          <p>ตัวเลขนี้เป็นจำนวนรายการ ไม่ใช่ยอดเงินรับชำระ ใช้แทนกันไม่ได้</p></div>
        <button type="button" className="btn btn-primary" onClick={() => { setLeadType('real'); setLeadStatus('new'); setView('leads'); }}>ดูรายชื่อที่ต้องติดต่อ →</button>
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

      {summary && <div className="sales-record-kpis sales-overview-record-kpis" aria-label="สถานะการขายจริง">
        <span>ดีลที่กำลังติดตาม <strong>{summary.open_deals}</strong></span>
        <span>ปิดการขาย <strong>{summary.won_deals}</strong></span>
        <span>มูลค่าดีลที่ปิด <strong>{Number(summary.won_amount_thb).toLocaleString('th-TH')} ฿</strong></span>
        <span>คำขอชำระเงินรอตรวจ <strong>{summary.payment_requests}</strong></span>
      </div>}

      <div className="sales-analytics-grid">
        <section className="sales-analytics-card sales-revenue-card" aria-label="มูลค่าดีลที่ปิดรายเดือน">
          <div className="sales-card-heading"><div><span>มูลค่าดีลที่ปิด</span><h3>ย้อนหลัง 6 เดือน</h3></div><strong>{Number(summary?.won_amount_thb || 0).toLocaleString('th-TH')} ฿</strong></div>
          <p>แสดงมูลค่าดีลที่บันทึกว่าปิดการขายแล้ว ไม่ใช่ยอดรับชำระ</p>
          {recordsError ? <div className="sales-chart-empty">โหลดบันทึกการขายไม่สำเร็จ</div> : recordsLoading ? <div className="sales-chart-empty">กำลังโหลดกราฟ…</div>
            : monthBuckets.every((month) => month.value === 0) ? <div className="sales-chart-empty">ยังไม่มีดีลที่ปิดในช่วง 6 เดือนนี้</div>
            : <div className="sales-revenue-chart">{monthBuckets.map((month) => <div key={month.key} className="sales-revenue-month" title={`${month.label}: ${month.value.toLocaleString('th-TH')} บาท`}><span>{month.value ? `${Math.round(month.value / 1000)}k` : ''}</span><div className="sales-revenue-track"><i style={{ height: `${Math.max(4, month.value / maxMonthAmount * 100)}%` }} /></div><small>{month.label}</small></div>)}</div>}
        </section>
        <section className="sales-analytics-card sales-products-card" aria-label="สินค้าที่ลูกค้าสนใจ">
          <div className="sales-card-heading"><div><span>ความสนใจของลูกค้า</span><h3>สินค้าที่ถูกสอบถามบ่อย</h3></div></div>
          {topProducts.length ? topProducts.map(([name, count]) => <div className="sales-product-row" key={name}><div><span>{name}</span><b>{count} ราย</b></div><div className="sales-product-track"><i style={{ width: `${count / topProducts[0][1] * 100}%` }} /></div></div>) : <p className="sales-chart-empty">ยังไม่มีข้อมูลสินค้าที่สนใจ</p>}
        </section>
      </div>

      <section className="sales-latest-card" aria-label="ดีลล่าสุด"><div className="sales-card-heading"><div><span>การซื้อขาย</span><h3>ดีลล่าสุด</h3></div><button type="button" className="btn btn-secondary btn-sm" onClick={() => setView('records')}>ดูดีลทั้งหมด →</button></div>
        {recordsError ? <p>โหลดบันทึกการขายไม่สำเร็จ</p> : recordsLoading ? <p>กำลังโหลดรายการ…</p> : latestDeals.length ? <div className="table-wrap"><table className="data-table"><thead><tr><th>ลูกค้า</th><th>สินค้า</th><th>สถานะ</th><th>มูลค่า</th><th>อัปเดต</th></tr></thead><tbody>{latestDeals.map((record) => <tr key={record.id}><td>{record.lead_name}</td><td>{record.product}</td><td>{({ interested: 'สนใจ', quoted: 'เสนอราคา', won: 'ปิดการขาย', lost: 'ไม่สำเร็จ' } as Record<string, string>)[record.status] || record.status}</td><td>{record.amount_thb ? `${Number(record.amount_thb).toLocaleString('th-TH')} ฿` : 'ยังไม่ระบุ'}</td><td>{fmtDate(record.updated_at || record.created_at)}</td></tr>)}</tbody></table></div> : <p>ยังไม่มีดีลที่บันทึกไว้</p>}
      </section>

      {summary && <section className="page-section" aria-label="สถิติการขาย" style={{ marginBottom: 18 }}>
        <div className="section-header"><span className="section-title">สถิติที่ช่วยวางแผนติดตาม</span></div>
        <div className="section-body sales-stats-grid">
          <div><h3>สถานะดีล</h3><p>นับเฉพาะรายการจริง ไม่รวม DEMO</p>
            {([['interested', 'สนใจ'], ['quoted', 'เสนอราคา'], ['won', 'ปิดการขาย'], ['lost', 'ไม่สำเร็จ']] as const).map(([key, label]) => {
              const count = summary.deal_status_counts?.[key] || 0;
              const max = Math.max(1, ...Object.values(summary.deal_status_counts || {}));
              return <div className="sales-stat-row" key={key}><span>{label}</span><div><i style={{ width: `${count / max * 100}%` }} /></div><strong>{count}</strong></div>;
            })}</div>
          <div><h3>ลูกค้ามาจากช่องทางไหน</h3><p>ลูกค้าใหม่ 7 วันล่าสุด: <strong>{summary.new_leads_7d || 0} ราย</strong></p>
            {Object.entries(summary.lead_by_source || {}).length ? Object.entries(summary.lead_by_source || {}).map(([source, count]) => <div className="sales-stat-row" key={source}><span>{LEAD_SOURCE_LABEL[source] || source}</span><div><i style={{ width: `${count / Math.max(1, ...Object.values(summary.lead_by_source || {})) * 100}%` }} /></div><strong>{count}</strong></div>) : <p>ยังไม่มีลูกค้าจริง</p>}
            <p>อัตราปิดดีล: <strong>{Math.round(summary.won_deals * 100 / Math.max(1, Object.values(summary.deal_status_counts || {}).reduce((a, b) => a + b, 0)))}%</strong> ของดีลที่บันทึก</p>
          </div>
        </div>
      </section>}

      <div className="sales-next-actions">
        <button type="button" onClick={() => { setLeadType('real'); setLeadStatus('new'); setView('leads'); }}>
          <strong>1 · ติดต่อผู้สนใจ</strong><span>ดูข้อมูลลูกค้าที่เพิ่งลงทะเบียนและบันทึกการติดต่อ</span><b>{newCount} ราย →</b>
        </button>
        <button type="button" onClick={() => setView('records')}>
          <strong>2 · บันทึกการซื้อขาย</strong><span>ติดตามสถานะดีล หรือรับคำขอชำระเงินให้เจ้าหน้าที่ตรวจ</span><b>เปิดบันทึก →</b>
        </button>
      </div>

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
            <label>ประเภทข้อมูล<select className="form-input" value={leadType} onChange={(e) => setLeadType(e.target.value as 'all' | 'real' | 'demo')}>
              <option value="all">ทั้งหมด</option><option value="real">ลูกค้าจริง</option><option value="demo">ข้อมูลตัวอย่าง</option>
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
                        <td style={{ fontWeight: 600 }}>{l.name || '—'}{l.source === 'DEMO' && <span className="sales-demo-badge">ตัวอย่าง</span>}</td>
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
                            <button className="btn btn-secondary" style={{ padding: '4px 10px', fontSize: '0.78rem' }} onClick={() => setSelectedLead(l)}>รายละเอียด</button>
                            {l.source === 'DEMO' ? <span className="sales-demo-muted">ไม่ต้องติดต่อ</span> : l.status === 'new' ? (
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
                            {canDelete && l.source !== 'DEMO' && (
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
      {selectedLead && <div className="panel-overlay" onClick={() => setSelectedLead(null)}><div className="repair-panel detail-sheet" style={{ width: 620, maxWidth: '96vw' }} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label="รายละเอียดลูกค้า">
        <div className="repair-panel-header"><h3 className="repair-panel-title">ข้อมูลลูกค้า #{selectedLead.id}</h3><button className="repair-panel-close" onClick={() => setSelectedLead(null)} aria-label="ปิด">×</button></div>
        <div className="repair-panel-body"><div className="detail-sheet-identity"><h4 className="detail-sheet-name">{selectedLead.name || 'ไม่ระบุชื่อ'}</h4><p className="detail-sheet-subtitle">{selectedLead.source === 'DEMO' ? 'ข้อมูลตัวอย่าง' : LEAD_SOURCE_LABEL[selectedLead.source] || selectedLead.source}</p></div>
          <dl className="detail-sheet-grid"><div><dt>เบอร์ติดต่อ</dt><dd>{selectedLead.phone || '—'}</dd></div><div><dt>สถานะ</dt><dd>{LEAD_STATUS[selectedLead.status]?.label || selectedLead.status}</dd></div><div><dt>สินค้าที่สนใจ</dt><dd>{selectedLead.products || '—'}</dd></div><div><dt>ความต้องการ</dt><dd>{selectedLead.interest || '—'}</dd></div><div><dt>รับข้อมูลเมื่อ</dt><dd>{fmtDate(selectedLead.created_at)}</dd></div><div><dt>หมายเหตุ</dt><dd>{selectedLead.note || '—'}</dd></div></dl>
          <p className="studio-help">รายการที่มีประวัติการขายหรือคำขอชำระเงินจะลบไม่ได้ เพื่อรักษาประวัติธุรกรรม</p>
        </div>
        <div className="detail-sheet-footer"><button className="btn btn-secondary" onClick={() => setSelectedLead(null)}>ปิดรายละเอียด</button>{canDelete && selectedLead.source !== 'DEMO' && <button className="btn btn-danger" disabled={busy === selectedLead.id} onClick={() => removeLead(selectedLead.id, selectedLead.name)}>{busy === selectedLead.id ? 'กำลังลบ…' : 'ลบลูกค้ารายนี้'}</button>}</div>
      </div></div>}
    </div>
  );
}
