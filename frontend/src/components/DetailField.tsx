import type { ReactNode } from 'react';
import '../styles/detail-sheet.css';

export default function DetailField({ label, value, mono = false, wide = false }: {
  label: string;
  value: ReactNode;
  mono?: boolean;
  wide?: boolean;
}) {
  return <div className={`detail-sheet-field${mono ? ' is-mono' : ''}${wide ? ' is-wide' : ''}`}>
    <dt>{label}</dt>
    <dd>{value === null || value === undefined || value === '' ? '—' : value}</dd>
  </div>;
}
