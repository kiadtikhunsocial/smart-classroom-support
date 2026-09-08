import { Ticket } from '../types';

interface TicketCardProps {
  ticket: Ticket;
  onView?: (ticketId: string) => void;
}

export function TicketCard({ ticket, onView }: TicketCardProps) {
  const statusColor: Record<string, string> = {
    open: '#e53e3e',
    assigned: '#dd6b20',
    in_progress: '#d69e2e',
    waiting_parts: '#3182ce',
    waiting_user: '#805ad5',
    completed: '#38a169',
    closed: '#718096',
    cancelled: '#c53030',
    pending: '#718096',
  };

  return (
    <div className="ticket-card">
      <div className="ticket-card-header">
        <span className="ticket-id">{ticket.ticket_id}</span>
        <span className="ticket-status-badge" style={{ backgroundColor: statusColor[ticket.status] || '#718096' }}>
          {ticket.status}
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
