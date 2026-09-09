import { Ticket } from '../types';
import { STATUS_LABEL, STATUS_COLOR } from '../statusLabels';

interface TicketCardProps {
  ticket: Ticket;
  onView?: (ticketId: string) => void;
}

export function TicketCard({ ticket, onView }: TicketCardProps) {
  return (
    <div className="ticket-card">
      <div className="ticket-card-header">
        <span className="ticket-id">{ticket.ticket_id}</span>
        <span className="ticket-status-badge" style={{ backgroundColor: STATUS_COLOR[ticket.status] || '#718096' }}>
          {STATUS_LABEL[ticket.status] || ticket.status}
        </span>
      </div>
      <div className="ticket-title">{ticket.title}</div>
      {ticket.device_id && (
        <div className="ticket-device">อุปกรณ์: {ticket.device_id}</div>
      )}
      <div className="ticket-meta">
        <span className={`priority-${ticket.priority}`}>{ticket.priority}</span>
        <span>•</span>
        <span>{new Date(ticket.created_at).toLocaleString('th-TH')}</span>
      </div>
      {onView && (
        <button 
          className="ticket-view-btn" 
          onClick={() => onView(ticket.ticket_id)}
        >
          ดูรายละเอียด
        </button>
      )}
    </div>
  );
}
