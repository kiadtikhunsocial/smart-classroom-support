import React, { useEffect, useRef } from 'react';
import '../styles/confirm-dialog.css';

export interface ConfirmDialogProps {
  title: string;
  message: string;
  confirmLabel: string;
  danger?: boolean;
  busy?: boolean;
  onConfirm: () => void;
  onCancel: () => void;
}

/**
 * กล่องยืนยันของระบบ แทน window.confirm() ที่หน้าตาไม่เข้ากับเว็บและปิดกั้นทั้งหน้า
 * โฟกัสเริ่มที่ปุ่ม "ยกเลิก" (กด Enter พลาดก็ไม่ลบ), Esc = ยกเลิก, Tab วนอยู่ในกล่อง,
 * ปิดแล้วคืนโฟกัสให้ปุ่มที่เปิดกล่อง
 */
export default function ConfirmDialog({ title, message, confirmLabel, danger, busy, onConfirm, onCancel }: ConfirmDialogProps) {
  const boxRef = useRef<HTMLDivElement | null>(null);
  const cancelRef = useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    const opener = document.activeElement as HTMLElement | null;
    cancelRef.current?.focus();
    return () => { opener?.focus?.(); };
  }, []);

  const onKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Escape') { e.stopPropagation(); if (!busy) onCancel(); return; }
    if (e.key !== 'Tab' || !boxRef.current) return;
    const focusable = Array.from(boxRef.current.querySelectorAll<HTMLElement>('button:not([disabled])'));
    if (!focusable.length) return;
    const first = focusable[0];
    const last = focusable[focusable.length - 1];
    if (e.shiftKey && document.activeElement === first) { e.preventDefault(); last.focus(); }
    else if (!e.shiftKey && document.activeElement === last) { e.preventDefault(); first.focus(); }
  };

  return (
    <div className="confirm-overlay" onClick={() => { if (!busy) onCancel(); }}>
      <div ref={boxRef} className="confirm-box" role="alertdialog" aria-modal="true"
        aria-labelledby="confirm-title" aria-describedby="confirm-message"
        onClick={(e) => e.stopPropagation()} onKeyDown={onKeyDown}>
        <h2 id="confirm-title" className="confirm-title">{title}</h2>
        <p id="confirm-message" className="confirm-message">{message}</p>
        <div className="confirm-actions">
          <button ref={cancelRef} type="button" className="btn btn-secondary" onClick={onCancel} disabled={busy}>ยกเลิก</button>
          <button type="button" className={`btn ${danger ? 'btn-danger' : 'btn-primary'}`} onClick={onConfirm} disabled={busy}>
            {busy ? 'กำลังดำเนินการ…' : confirmLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
