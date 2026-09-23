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
        <span className="dsh-card-title">ภาพรวมการซื้อขาย</span>
        <button type="button" className="btn btn-ghost" onClick={onOpenSales}>ดูหน้ายอดขาย →</button>
      </div>
      <div className="dsh-card-body">
        <div className="sales-record-kpis">
          <span>ลูกค้า / ผู้สนใจ <strong>{summary.lead_count}</strong></span>
          <span>ดีลที่กำลังติดตาม <strong>{summary.open_deals}</strong></span>
          <span>ปิดการขาย <strong>{summary.won_deals}</strong></span>
          <span>รอจัดการคำขอชำระเงิน <strong>{summary.payment_requests}</strong></span>
        </div>
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
