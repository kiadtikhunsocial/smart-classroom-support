import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../api/client';
import type { SalesLead, SalesRecord, SalesRecordKind, SalesSummary } from '../types/sales';

const STATUS: Record<SalesRecordKind, { value: string; label: string }[]> = {
  deal: [
    { value: 'interested', label: 'สนใจ' },
    { value: 'quoted', label: 'เสนอราคาแล้ว' },
    { value: 'won', label: 'ปิดการขาย' },
    { value: 'lost', label: 'ไม่สำเร็จ' },
  ],
  payment_request: [
    { value: 'requested', label: 'ขอชำระเงิน' },
    { value: 'reviewing', label: 'เจ้าหน้าที่กำลังตรวจสอบ' },
    { value: 'resolved', label: 'ดำเนินการแล้ว' },
    { value: 'cancelled', label: 'ยกเลิก' },
  ],
};

const money = (value: string | null | undefined) =>
  value == null ? '—' : `${Number(value).toLocaleString('th-TH', { maximumFractionDigits: 2 })} ฿`;

export default function SalesRecordsPanel({ leads, canSyncSheet }: { leads: SalesLead[]; canSyncSheet: boolean }) {
  const [kind, setKind] = useState<SalesRecordKind>('deal');
  const [showForm, setShowForm] = useState(false);
  const [query, setQuery] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [records, setRecords] = useState<SalesRecord[]>([]);
  const [summary, setSummary] = useState<SalesSummary | null>(null);
  const [leadId, setLeadId] = useState('');
  const [product, setProduct] = useState('');
  const [quantity, setQuantity] = useState('1');
  const [amount, setAmount] = useState('');
  const [note, setNote] = useState('');
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    try {
      const all: SalesRecord[] = [];
      while (true) {
        const page = await api.listSalesRecords(all.length);
        all.push(...page);
        if (page.length < 200) break;
      }
      const nextSummary = await api.getSalesSummary();
      setRecords(all);
      setSummary(nextSummary);
      setError(null);
    } catch (e: any) {
      setError(e?.message || 'โหลดบันทึกการขายไม่สำเร็จ');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => { void load(); }, [load]);

  const submit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!leadId || !product.trim()) {
      setError('เลือกลูกค้าและระบุสินค้า/บริการก่อนบันทึก');
      return;
    }
    setSaving(true);
    setError(null);
    setNotice(null);
    try {
      await api.createSalesRecord({
        lead_id: Number(leadId), kind, product: product.trim(),
        quantity: Number(quantity), amount_thb: amount || undefined,
        note: note.trim() || undefined,
      });
      setProduct(''); setQuantity('1'); setAmount(''); setNote('');
      setShowForm(false);
      setNotice(kind === 'deal' ? 'บันทึกดีลแล้ว' : 'บันทึกคำขอชำระเงินแล้ว — ยังไม่ถือว่าชำระสำเร็จ');
      await load();
    } catch (err: any) {
      setError(err?.message || 'บันทึกไม่สำเร็จ');
    } finally {
      setSaving(false);
    }
  };

  const changeStatus = async (record: SalesRecord, status: string) => {
    try {
      await api.updateSalesRecord(record.id, status);
      await load();
    } catch (err: any) {
      setError(err?.message || 'เปลี่ยนสถานะไม่สำเร็จ');
    }
  };

  const retrySheet = async (id: number) => {
    try {
      await api.retrySalesRecordSheetSync(id);
      setNotice(`ส่งรายการ #${id} ไปซิงก์ Google Sheet อีกครั้งแล้ว`);
      setError(null);
    } catch (err: any) {
      setError(err?.message || 'ส่งซิงก์ชีตไม่สำเร็จ');
    }
  };

  const visible = records.filter((record) => record.kind === kind
    && (statusFilter === 'all' || record.status === statusFilter)
    && (!query.trim() || [record.lead_name, record.product, record.note].some((value) =>
      (value || '').toLocaleLowerCase().includes(query.trim().toLocaleLowerCase()))));
  return (
    <section className="page-section" aria-label="บันทึกการซื้อขายและคำขอชำระเงิน">
      <div className="section-header" style={{ flexWrap: 'wrap', gap: 12 }}>
        <div>
          <span className="section-title">บันทึกการซื้อขาย</span>
          <p style={{ margin: '4px 0 0', fontSize: '0.82rem', color: 'var(--color-text-secondary)' }}>
            เลือกหมวดก่อนบันทึกหรือตรวจสอบสถานะ แต่ละรายการเชื่อมกับลูกค้าที่ลงทะเบียนแล้ว
          </p>
        </div>
        <button className="btn" type="button" onClick={() => void load()} disabled={loading}>รีเฟรช</button>
      </div>
      <div className="section-body">
        {summary && (
          <div className="sales-record-kpis">
            <span>ดีลที่กำลังติดตาม <strong>{summary.open_deals}</strong></span>
            <span>ปิดการขาย <strong>{summary.won_deals}</strong></span>
            <span>มูลค่าดีลที่ปิด <strong>{money(summary.won_amount_thb)}</strong></span>
            <span>คำขอชำระเงินที่รอจัดการ <strong>{summary.payment_requests}</strong></span>
          </div>
        )}

        <div role="tablist" aria-label="หมวดการซื้อขาย" className="sales-record-tabs">
          <button type="button" role="tab" aria-selected={kind === 'deal'}
            className={kind === 'deal' ? 'btn btn-primary' : 'btn'} onClick={() => { setKind('deal'); setStatusFilter('all'); setShowForm(false); }}>
            บันทึกดีล ({records.filter((r) => r.kind === 'deal').length})
          </button>
          <button type="button" role="tab" aria-selected={kind === 'payment_request'}
            className={kind === 'payment_request' ? 'btn btn-primary' : 'btn'} onClick={() => { setKind('payment_request'); setStatusFilter('all'); setShowForm(false); }}>
            ต้องการชำระเงิน ({records.filter((r) => r.kind === 'payment_request').length})
          </button>
        </div>

        {kind === 'payment_request' && (
          <p className="sales-record-caution" role="note">
            ส่วนนี้บันทึกคำขอเพื่อให้เจ้าหน้าที่ตรวจสอบเท่านั้น ไม่รับเลขบัตรหรือข้อมูลบัญชี และไม่ยืนยันการรับชำระเงินอัตโนมัติ
          </p>
        )}

        <div className="sales-record-toolbar">
          <div><strong>{kind === 'deal' ? 'บันทึกดีล' : 'คำขอชำระเงิน'}</strong>
            <small>{kind === 'deal' ? 'สนใจ → เสนอราคา → ปิดการขาย' : 'รับคำขอ → ตรวจสอบ → ดำเนินการ'}</small></div>
          <button type="button" className="btn btn-primary" onClick={() => setShowForm((value) => !value)}
            aria-expanded={showForm}>{showForm ? 'ปิดแบบฟอร์ม' : kind === 'deal' ? '+ เพิ่มบันทึกดีล' : '+ เพิ่มคำขอชำระเงิน'}</button>
        </div>

        {showForm && <form className="sales-record-form" onSubmit={submit}>
          <label>ลูกค้า / ผู้สนใจ
            <select className="form-input" value={leadId} onChange={(e) => setLeadId(e.target.value)} required>
              <option value="">เลือกลูกค้า</option>
              {leads.map((lead) => <option key={lead.id} value={lead.id}>{lead.name} · {lead.phone}</option>)}
            </select>
          </label>
          <label>สินค้า / บริการ
            <input className="form-input" value={product} onChange={(e) => setProduct(e.target.value)} maxLength={255} required />
          </label>
          <label>จำนวน
            <input className="form-input" type="number" min="1" max="10000" step="1" value={quantity}
              onChange={(e) => setQuantity(e.target.value)} required />
          </label>
          <label>มูลค่าโดยประมาณ (บาท)
            <input className="form-input" type="number" min="0" max="9999999999.99" step="0.01" value={amount}
              onChange={(e) => setAmount(e.target.value)} placeholder="ไม่บังคับ" />
          </label>
          <label className="sales-record-note">หมายเหตุ
            <input className="form-input" value={note} onChange={(e) => setNote(e.target.value)} maxLength={2000}
              placeholder={kind === 'payment_request' ? 'ระบุช่องทางติดต่อกลับ ไม่ใส่ข้อมูลบัตร/บัญชี' : 'รายละเอียดดีล'} />
          </label>
          <button className="btn btn-primary" type="submit" disabled={saving || leads.length === 0}>
            {saving ? 'กำลังบันทึก…' : kind === 'deal' ? 'บันทึกดีล' : 'บันทึกคำขอชำระเงิน'}
          </button>
        </form>}
        {leads.length === 0 && <p>ยังไม่มีลูกค้า — ให้ลูกค้าลงทะเบียนผ่านหน้า “สมัครสมาชิกลูกค้า” ก่อน</p>}
        {notice && <p role="status" className="sales-record-notice">{notice}</p>}
        {error && <p role="alert" className="sales-record-error">{error}</p>}

        <div className="sales-record-filters">
          <input className="form-input" type="search" aria-label="ค้นหาลูกค้าหรือสินค้า" placeholder="ค้นหาลูกค้าหรือสินค้า" value={query} onChange={(e) => setQuery(e.target.value)} />
          <select className="form-input" aria-label="กรองสถานะรายการ" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="all">ทุกสถานะ</option>{STATUS[kind].map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
          </select>
          <span>{visible.length} รายการ</span>
        </div>

        {loading ? <p>กำลังโหลดบันทึก…</p> : visible.length === 0 ? (
          <p className="empty-text">ยังไม่มี{kind === 'deal' ? 'บันทึกดีล' : 'คำขอชำระเงิน'}ในหมวดนี้</p>
        ) : (
          <div className="table-wrap">
            <table className="data-table">
              <thead><tr><th>ลูกค้า</th><th>สินค้า / บริการ</th><th>จำนวน</th><th>มูลค่า</th><th>สถานะ</th><th>วันที่</th>{canSyncSheet && <th>ชีต</th>}</tr></thead>
              <tbody>{visible.map((record) => (
                <tr key={record.id}>
                  <td>{record.lead_name}</td>
                  <td>{record.product}{record.note && <small className="sales-record-subnote">{record.note}</small>}</td>
                  <td>{record.quantity}</td>
                  <td>{money(record.amount_thb)}</td>
                  <td>
                    <select className="form-input" aria-label={`สถานะรายการ ${record.id}`}
                      value={record.status} onChange={(e) => void changeStatus(record, e.target.value)}>
                      {STATUS[record.kind].map((item) => <option key={item.value} value={item.value}>{item.label}</option>)}
                    </select>
                  </td>
                  <td>{new Date(record.created_at).toLocaleDateString('th-TH')}</td>
                  {canSyncSheet && <td><button className="btn" type="button" onClick={() => void retrySheet(record.id)}>ซิงก์ใหม่</button></td>}
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
