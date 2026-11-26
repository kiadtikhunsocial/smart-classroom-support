import React from 'react';
import type { Ticket } from '../../types';
import { STATUS_LABELS_TICKET, ticketDetailPriority } from './ticketLabels';
import TicketHolder from './TicketHolder';

export interface TicketCardProps {
  ticket: Ticket;
  onOpen: (ticket: Ticket) => void;
}

function shortDate(value: string) {
  return new Date(value).toLocaleDateString('th-TH', { day: 'numeric', month: 'short' });
}

/** การ์ดใบงานสำหรับจอมือถือ — ทั้งการ์ดเป็นปุ่มเดียว เปิดแผงรายละเอียด
 *  (เปลี่ยนสถานะทำในแผงรายละเอียด ไม่ใส่ dropdown ในการ์ดเพื่อกันกดพลาดตอนเลื่อนจอ) */
export default function TicketCard({ ticket, onOpen }: TicketCardProps) {
  const status = (STATUS_LABELS_TICKET[ticket.status] || ticket.status).split(' (')[0];
  const where = [ticket.organization_name, ticket.reporter_name].filter(Boolean).join(' · ');
  return (
    <li>
      <button type="button" className={`tk-card tk-prio tk-prio-${ticket.priority}`} onClick={() => onOpen(ticket)}
        aria-label={`ดูรายละเอียดใบงาน ${ticket.ticket_id}`}>
        <span className="tk-card-top">
          <span className={`badge badge-${ticket.status}`}>{status}</span>
          <span className={`badge badge-priority-${ticket.priority}`}>{ticketDetailPriority[ticket.priority] || ticket.priority}</span>
          <time className="tk-card-date" dateTime={ticket.created_at}>{shortDate(ticket.created_at)}</time>
        </span>
        <span className="tk-card-title">{ticket.title}</span>
        <span className="tk-card-device">{ticket.device_label || ticket.device_type || ticket.device_id}</span>
        {where && <span className="tk-card-meta">{where}</span>}
        <TicketHolder ticket={ticket} />
        <span className="tk-card-id">{ticket.ticket_id}</span>
      </button>
    </li>
  );
}
