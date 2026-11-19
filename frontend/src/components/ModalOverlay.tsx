import React, { useLayoutEffect, useRef } from 'react';

type ModalOverlayProps = {
  children: React.ReactNode;
  label?: string;
  labelledBy?: string;
  describedBy?: string;
  alert?: boolean;
  className?: string;
  style?: React.CSSProperties;
  onClose: () => void;
};

export default function ModalOverlay({ children, label, labelledBy, describedBy, alert, className = 'panel-overlay', style, onClose }: ModalOverlayProps) {
  const ref = useRef<HTMLDialogElement>(null);

  useLayoutEffect(() => {
    const dialog = ref.current!;
    const opener = document.activeElement;
    dialog.showModal();
    return () => {
      if (dialog.open) dialog.close();
      if (opener instanceof HTMLElement && opener.isConnected) opener.focus({ preventScroll: true });
    };
  }, []);

  return (
    <dialog
      ref={ref}
      className={`modal-frame ${className}`}
      style={style}
      role={alert ? 'alertdialog' : undefined}
      aria-label={label}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      onCancel={(event) => { event.preventDefault(); event.stopPropagation(); onClose(); }}
      onClick={(event) => { if (event.target === event.currentTarget) onClose(); }}
    >
      {children}
    </dialog>
  );
}
