import React from 'react';
import { pageCount } from './ticketQuery';

export interface PaginationProps {
  page: number;
  total: number;
  pageSize: number;
  onPage: (page: number) => void;
  disabled?: boolean;
}

/** ปุ่มเปลี่ยนหน้า — ซ่อนเมื่อมีรายการไม่เกินหนึ่งหน้า */
export default function Pagination({ page, total, pageSize, onPage, disabled }: PaginationProps) {
  if (total <= pageSize) return null;
  const pages = pageCount(total);
  const from = (page - 1) * pageSize + 1;
  const to = Math.min(page * pageSize, total);
  return (
    <nav className="tk-pager" aria-label="เปลี่ยนหน้า">
      <button type="button" className="btn btn-secondary tk-pager-btn" onClick={() => onPage(page - 1)}
        disabled={disabled || page <= 1}>
        ก่อนหน้า
      </button>
      <p className="tk-pager-info">
        <span className="tk-pager-page">หน้า {page} จาก {pages}</span>
        <span className="tk-pager-range">แสดง {from}–{to} จาก {total} รายการ</span>
      </p>
      <button type="button" className="btn btn-secondary tk-pager-btn" onClick={() => onPage(page + 1)}
        disabled={disabled || page >= pages}>
        ถัดไป
      </button>
    </nav>
  );
}
