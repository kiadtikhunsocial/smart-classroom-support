import React, { useId } from 'react';
import '../styles/confirm-dialog.css';
import ModalOverlay from './ModalOverlay';

export interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

export default function ConfirmDialog({ title, message, confirmLabel, danger, busy, onConfirm, onCancel }: ConfirmDialogProps) {
  const titleId = useId();
  const messageId = useId();
  return (
    <ModalOverlay className="confirm-overlay" alert labelledBy={titleId} describedBy={messageId} onClose={() => { if (!busy) onCancel(); }}>
      <div className="confirm-box" aria-busy={busy}>
        <h2 id={titleId} className="confirm-title">{title}</h2>
        <p id={messageId} className="confirm-message">{message}</p>
        <div className="confirm-actions">
          <button type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>ยกเลิก</button>
          <button type="button" className={danger ? 'btn btn-danger' : 'btn btn-primary'} onClick={onConfirm} disabled={busy}>
            {busy ? 'กำลังดำเนินการ…' : confirmLabel}
          </button>
        </div>
      </div>
    </ModalOverlay>
  );
}
