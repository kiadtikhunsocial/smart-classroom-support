import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import type { SalesRecord, SalesSummary } from '../types/sales';
import '../styles/sales.css';

export default function SalesDashboardWidget({ onOpenSales }: { onOpenSales: () => void }) {
  const [summary, setSummary] = useState<SalesSummary | null>(null);
  const [recent, setRecent] = useState<SalesRecord[]>([]);

  useEffect(() => {
    api.getSalesSummary().then(setSummary).catch(() => setSummary(null));
    api.listSalesRecords(0).then((rows) => setRecent(rows.slice(0, 3))).catch(() => setRecent([]));
  }, []);

  if (!summary) return null;
  return (
    <section className="dsh-card sales-dashboard-widget" aria-label="ภาพรวมการซื้อขาย">
      <div className="dsh-card-head">
        <span className="dsh-card-title">ลูกค้าและการขาย</span>
        <button type="button" className="btn btn-ghost" onClick={onOpenSales}>เปิดพื้นที่งานขาย →</button>
      </div>
      <div className="dsh-card-body">
        <p className="sales-dashboard-hint">งานที่ควรติดตามวันนี้ · คำขอชำระเงินยังไม่ใช่ยอดรับเงินจริง</p>
        <div className="sales-record-kpis">
          <span>ลูกค้า / ผู้สนใจ <strong>{summary.lead_count}</strong></span>
          <span>ดีลเปิดอยู่ <strong>{summary.open_deals}</strong></span>
          <span>ปิดการขาย <strong>{summary.won_deals}</strong></span>
          <span>คำขอชำระเงินรอตรวจ <strong>{summary.payment_requests}</strong></span>
        </div>
        <div className="sales-dashboard-foot"><span>มูลค่าดีลที่ปิดแล้ว <strong>{Number(summary.won_amount_thb || 0).toLocaleString('th-TH')} ฿</strong></span><button type="button" onClick={onOpenSales}>จัดการดีลและลูกค้า →</button></div>
        {recent.length > 0 && (
          <div className="sales-dashboard-recent">
            {recent.map((item) => (
              <span key={item.id}>
                <strong>{item.lead_name}</strong> · {item.product} · {' '}
                {item.kind === 'deal' ? 'บันทึกดีล' : 'ขอชำระเงิน'}
              </span>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}
