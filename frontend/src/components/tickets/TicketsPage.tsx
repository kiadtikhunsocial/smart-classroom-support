import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { Ticket } from '../../types';
import Pagination from './Pagination';
import TicketCard from './TicketCard';
import TicketDetailSheet from './TicketDetailSheet';
import { ALL_STATUSES, STATUS_LABELS_TICKET, ticketDetailPriority } from './ticketLabels';
import {
  EMPTY_FILTERS, PAGE_SIZE, TICKET_TABS, activeFilterCount, buildTicketParams, clampPage, tabCount,
  type TicketFilters, type TicketTabId,
} from './ticketQuery';
import '../../styles/tickets.css';

export interface TicketsPageProps {
  onBack: () => void;
  /** แจ้ง App ว่าใบงานเปลี่ยน (Dashboard ยังถือรายการของตัวเองอยู่) */
  onTicketsChanged: () => void;
  canManage: boolean;
  focusId?: string;
  onFocusHandled?: () => void;
}

const SEARCH_DEBOUNCE_MS = 300;
const PRIORITIES = ['low', 'normal', 'high', 'critical'];

function formatDate(value: string) {
  return new Date(value).toLocaleDateString('th-TH', { day: '2-digit', month: 'short', year: 'numeric' });
}

/** หน้าใบงานซ่อม — ดึงทีละหน้าจาก server (ไม่โหลดทั้งหมดมากรองในเบราว์เซอร์แล้ว) */
export default function TicketsPage({ onBack, onTicketsChanged, canManage, focusId, onFocusHandled }: TicketsPageProps) {
  const [filters, setFilters] = useState<TicketFilters>(EMPTY_FILTERS);
  const [searchText, setSearchText] = useState('');
  const [page, setPage] = useState(1);
  const [items, setItems] = useState<Ticket[]>([]);
  const [total, setTotal] = useState(0);
  const [counts, setCounts] = useState<{ total: number; by_status: Record<string, number> }>({ total: 0, by_status: {} });
  const [loading, setLoading] = useState(true);
  const [loadedOnce, setLoadedOnce] = useState(false);
  const [error, setError] = useState('');
  const [reloadKey, setReloadKey] = useState(0);
  const [updating, setUpdating] = useState<string | null>(null);
  const [rowError, setRowError] = useState('');
  const [openTicket, setOpenTicket] = useState<{ id: string; initial?: Ticket } | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [orgOptions, setOrgOptions] = useState<[string, string][]>([]);
  const [typeOptions, setTypeOptions] = useState<string[]>([]);
  const [categoryOptions, setCategoryOptions] = useState<string[]>([]);
  const generation = useRef(0);
  const tabRefs = useRef<(HTMLButtonElement | null)[]>([]);

  // ── ตัวเลือกของ dropdown: โหลดครั้งเดียว ถ้าล้มเหลว dropdown นั้นถูกปิดไว้ ──
  useEffect(() => {
    api.listOrganizations()
      .then((orgs) => setOrgOptions(
        orgs.map((o: any) => [String(o.id), `${o.short_name || o.name}${o.code ? ` (${o.code})` : ''}`] as [string, string])
          .sort((a, b) => a[1].localeCompare(b[1], 'th')),
      ))
      .catch(() => setOrgOptions([]));
    api.listDeviceCategories()
      .then((r) => {
        setCategoryOptions(r.categories.map((c) => c.category));
        setTypeOptions(Array.from(new Set(r.categories.flatMap((c) => c.device_types))).sort((a, b) => a.localeCompare(b, 'th')));
      })
      .catch(() => { setCategoryOptions([]); setTypeOptions([]); });
  }, []);

  // ── คำค้นรอผู้ใช้หยุดพิมพ์ก่อนค่อยยิง ──
  useEffect(() => {
    const id = window.setTimeout(() => {
      setFilters((f) => (f.q === searchText ? f : { ...f, q: searchText }));
      setPage(1);
    }, SEARCH_DEBOUNCE_MS);
    return () => window.clearTimeout(id);
  }, [searchText]);

  // ── โหลดหน้าปัจจุบัน + ตัวเลขบนแท็บ — คำตอบที่มาช้ากว่าคำขอล่าสุดถูกทิ้ง ──
  useEffect(() => {
    const gen = ++generation.current;
    const params = buildTicketParams(filters, page);
    setLoading(true); setError('');
    Promise.all([api.listTicketsPage(params), api.ticketCounts(params)])
      .then(([list, c]) => {
        if (gen !== generation.current) return;
        const fixed = clampPage(page, list.total);
        if (fixed !== page) { setPage(fixed); return; } // หน้าปัจจุบันว่างแล้ว → ถอยไปหน้าสุดท้ายที่มีรายการ
        setItems(list.items); setTotal(list.total); setCounts(c);
        setLoading(false); setLoadedOnce(true);
      })
      .catch((e: any) => {
        if (gen !== generation.current) return;
        setError(e?.message ? `โหลดรายการใบงานไม่สำเร็จ: ${e.message}` : 'โหลดรายการใบงานไม่สำเร็จ');
        setLoading(false); setLoadedOnce(true);
      });
  }, [filters, page, reloadKey]);

  const reload = useCallback(() => setReloadKey((k) => k + 1), []);
  const afterChange = useCallback(() => { reload(); onTicketsChanged(); }, [reload, onTicketsChanged]);

  // ── เปิดใบงานที่ถูกขอจากหน้าอื่น (ค้นหาบนหัวเว็บ / หน้าอุปกรณ์) — โหลดตามเลข ไม่ต้องอยู่ในหน้านี้ ──
  useEffect(() => {
    if (!focusId) return;
    setOpenTicket({ id: focusId });
    onFocusHandled?.();
  }, [focusId, onFocusHandled]);

  const setFilter = <K extends keyof TicketFilters>(key: K, value: TicketFilters[K]) => {
    setFilters((f) => ({ ...f, [key]: value }));
    setPage(1);
  };
  const clearFilters = () => { setSearchText(''); setFilters(EMPTY_FILTERS); setPage(1); };
  const hasFilter = Boolean(filters.q || filters.tab !== 'all' || activeFilterCount(filters));
  const dropdownCount = activeFilterCount(filters);

  const handleStatusChange = async (ticketId: string, newStatus: string) => {
    if (!newStatus) return;
    setUpdating(ticketId); setRowError('');
    try {
      await api.updateStatus(ticketId, { status: newStatus, author_name: 'ผู้ดูแลระบบ', force: true });
      afterChange();
    } catch (e: any) {
      setRowError(`อัปเดตสถานะใบงาน ${ticketId} ไม่สำเร็จ: ${e?.message || ''}`);
    } finally {
      setUpdating(null);
    }
  };

  const onTabKey = (e: React.KeyboardEvent, index: number) => {
    if (e.key !== 'ArrowRight' && e.key !== 'ArrowLeft') return;
    e.preventDefault();
    const next = (index + (e.key === 'ArrowRight' ? 1 : -1) + TICKET_TABS.length) % TICKET_TABS.length;
    setFilter('tab', TICKET_TABS[next].id);
    tabRefs.current[next]?.focus();
  };

  const busy = loading && loadedOnce;

  return (
    <div className="page-content tk-page">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack} aria-label="กลับแดชบอร์ด">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
          </button>
          <div>
            <h1 className="top-bar-title">ใบงานซ่อม</h1>
            <span className="top-bar-subtitle">{total} รายการ</span>
          </div>
        </div>
        <div className="top-bar-actions">
          <button className="btn btn-ghost" onClick={reload} disabled={loading}>
            <svg className="tk-icon" width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M21 12a9 9 0 11-3.5-7.1" />
              <path d="M21 3v6h-6" />
            </svg>
            รีเฟรช
          </button>
        </div>
      </div>

      <div className="page-section">
        <div className="section-body">
          <div className="tk-toolbar">
            <input
              className="form-input tk-search"
              type="search"
              value={searchText}
              onChange={(e) => setSearchText(e.target.value)}
              placeholder="ค้นหา: เลขใบงาน / อุปกรณ์ / หัวข้อ / ผู้แจ้ง / โรงเรียน"
              aria-label="ค้นหาใบงาน"
              maxLength={100}
            />
            <button type="button" className="btn btn-secondary tk-filter-toggle"
              aria-expanded={filtersOpen} aria-controls="tk-filter-panel"
              onClick={() => setFiltersOpen((o) => !o)}>
              ตัวกรอง{dropdownCount > 0 && <span className="tk-filter-badge" aria-label={`เลือกไว้ ${dropdownCount} ตัว`}>{dropdownCount}</span>}
            </button>
            <div id="tk-filter-panel" className={`tk-filters${filtersOpen ? ' is-open' : ''}`}>
              <select className="form-select" value={filters.priority} onChange={(e) => setFilter('priority', e.target.value)} aria-label="กรองตามความเร่งด่วน">
                <option value="">ทุกความเร่งด่วน</option>
                {PRIORITIES.map((p) => <option key={p} value={p}>{ticketDetailPriority[p]}</option>)}
              </select>
              <select className="form-select" value={filters.deviceCategory} onChange={(e) => setFilter('deviceCategory', e.target.value)}
                aria-label="กรองตามหมวดหมู่อุปกรณ์" disabled={categoryOptions.length === 0}>
                <option value="">ทุกหมวดหมู่อุปกรณ์</option>
                {categoryOptions.map((c) => <option key={c} value={c}>{c}</option>)}
              </select>
              <select className="form-select" value={filters.deviceType} onChange={(e) => setFilter('deviceType', e.target.value)}
                aria-label="กรองตามประเภทอุปกรณ์" disabled={typeOptions.length === 0}>
                <option value="">ทุกประเภทอุปกรณ์</option>
                {typeOptions.map((t) => <option key={t} value={t}>{t}</option>)}
              </select>
              <select className="form-select" value={filters.organizationId} onChange={(e) => setFilter('organizationId', e.target.value)}
                aria-label="กรองตามโรงเรียน" disabled={orgOptions.length === 0}>
                <option value="">ทุกโรงเรียน</option>
                {orgOptions.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
              </select>
              {hasFilter && <button type="button" className="btn btn-ghost" onClick={clearFilters}>ล้างตัวกรอง</button>}
            </div>
          </div>

          <div className="tk-tabs" role="tablist" aria-label="สถานะใบงาน">
            {TICKET_TABS.map((tab, i) => {
              const selected = filters.tab === tab.id;
              return (
                <button key={tab.id} type="button" role="tab" id={`tk-tab-${tab.id}`}
                  ref={(el) => { tabRefs.current[i] = el; }}
                  aria-selected={selected} aria-controls="tk-results" tabIndex={selected ? 0 : -1}
                  className={`tk-tab${selected ? ' is-active' : ''}`}
                  onClick={() => setFilter('tab', tab.id as TicketTabId)}
                  onKeyDown={(e) => onTabKey(e, i)}>
                  {tab.label}
                  <span className="tk-tab-count">{tabCount(tab.id, counts.by_status, counts.total)}</span>
                </button>
              );
            })}
          </div>

          {rowError && <div role="alert" className="alert alert-error tk-alert">{rowError}</div>}
          {error && (
            <div role="alert" className="alert alert-error tk-alert">
              {error} <button type="button" className="btn btn-ghost btn-sm" onClick={reload}>ลองใหม่</button>
            </div>
          )}

          <div id="tk-results" role="tabpanel" aria-labelledby={`tk-tab-${filters.tab}`} aria-busy={loading}
            className={`tk-results${busy ? ' is-busy' : ''}`}>
            {!loadedOnce ? (
              <ul className="tk-skeleton" aria-label="กำลังโหลด">
                {Array.from({ length: 5 }, (_, i) => <li key={i} className="tk-skeleton-row" />)}
              </ul>
            ) : items.length === 0 && !error ? (
              <div className="empty-state tk-empty">
                <svg className="empty-icon" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden="true">
                  <rect x="3" y="5" width="18" height="14" rx="2" />
                  <path d="M3 10h18M8 20a2 2 0 004 0M12 20a2 2 0 004 0M16 20a2 2 0 004 0" />
                </svg>
                <span className="empty-text">{hasFilter ? 'ไม่พบใบงานที่ตรงกับตัวกรอง' : 'ยังไม่มีใบงาน'}</span>
              </div>
            ) : (
              <>
              {/* จอเล็กแสดงการ์ด จอใหญ่แสดงตาราง — สลับด้วย CSS จากข้อมูลชุดเดียวกัน */}
              <ul className="tk-cards">
                {items.map((ticket) => (
                  <TicketCard key={ticket.ticket_id} ticket={ticket}
                    onOpen={(t) => setOpenTicket({ id: t.ticket_id, initial: t })} />
                ))}
              </ul>
              <div className="table-wrap tk-table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>เลขใบงาน</th>
                      <th>อุปกรณ์</th>
                      <th>หัวข้อ</th>
                      <th>ผู้แจ้ง</th>
                      <th>สถานะ</th>
                      <th>แจ้งเมื่อ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((ticket) => (
                      <tr key={ticket.ticket_id} className="clickable-data-row" tabIndex={0}
                        aria-label={`ดูรายละเอียดใบงาน ${ticket.ticket_id}`}
                        onClick={(e) => { if (!(e.target as HTMLElement).closest('button, a, select, input')) setOpenTicket({ id: ticket.ticket_id, initial: ticket }); }}
                        onKeyDown={(e) => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); setOpenTicket({ id: ticket.ticket_id, initial: ticket }); } }}>
                        <td className="table-id">{ticket.ticket_id}</td>
                        <td>
                          <div className="table-meta">
                            <span className="tk-device-id">{ticket.device_id}</span>
                            <span className="table-meta-row">
                              {ticket.device_label || ticket.device_type || ''}
                              {ticket.device_category ? ` · ${ticket.device_category}` : ''}
                              {ticket.organization_name ? ` · ${ticket.organization_name}` : ''}
                            </span>
                          </div>
                        </td>
                        <td>
                          <span className="tk-title" title={ticket.title}>{ticket.title}</span>
                          {/* ความเร่งด่วนอยู่ใต้หัวข้อ แทนคอลัมน์แยก — ตารางพอดีจอ 1280px โดยไม่ต้องเลื่อนข้าง */}
                          <span className={`badge badge-priority-${ticket.priority} tk-priority`}>
                            {ticketDetailPriority[ticket.priority] || ticket.priority}
                          </span>
                        </td>
                        <td className="tk-reporter">{ticket.reporter_name || '—'}</td>
                        <td>
                          {canManage ? (
                            <select className="form-select tk-status-select" value={ticket.status}
                              disabled={updating === ticket.ticket_id}
                              aria-label={`เปลี่ยนสถานะใบงาน ${ticket.ticket_id}`}
                              onChange={(e) => void handleStatusChange(ticket.ticket_id, e.target.value)}>
                              {ALL_STATUSES.map((s) => <option key={s} value={s}>{STATUS_LABELS_TICKET[s]}</option>)}
                            </select>
                          ) : (
                            <span className={`badge badge-${ticket.status}`}>
                              {STATUS_LABELS_TICKET[ticket.status] || ticket.status.replace(/_/g, ' ')}
                            </span>
                          )}
                        </td>
                        <td className="tk-date">{formatDate(ticket.created_at)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
              </>
            )}
          </div>

          <Pagination page={page} total={total} pageSize={PAGE_SIZE} onPage={setPage} disabled={loading} />
        </div>
      </div>

      {openTicket && (
        <TicketDetailSheet
          key={openTicket.id}
          ticketId={openTicket.id}
          initial={openTicket.initial}
          canManage={canManage}
          onClose={() => setOpenTicket(null)}
          onChanged={afterChange}
        />
      )}
    </div>
  );
}
