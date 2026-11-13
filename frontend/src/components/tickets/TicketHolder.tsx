import React from 'react';
import type { Ticket } from '../../types';
import { holderText } from './ticketQuery';

/** บรรทัด "ใครถืองานนี้" ใต้สถานะ — ดูปราดเดียวรู้ว่างานไหนยังไม่มีคนรับ / รอช่างตอบ / ใครทำอยู่ */
export default function TicketHolder({ ticket }: { ticket: Ticket }) {
  const h = holderText(ticket);
  if (!h) return null;
  return <span className={`dp-holder is-${h.kind}`} title={h.text}>{h.text}</span>;
}
