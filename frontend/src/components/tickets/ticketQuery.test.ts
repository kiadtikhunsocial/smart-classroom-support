import { describe, expect, it } from 'vitest';
import {
  EMPTY_FILTERS,
  activeFilterCount,
  buildTicketParams,
  clampPage,
  pageCount,
  holderText,
  tabCount,
} from './ticketQuery';

describe('buildTicketParams', () => {
  it('builds params for a plain first page', () => {
    expect(buildTicketParams(EMPTY_FILTERS, 1)).toEqual({ limit: '20', offset: '0' });
  });

  it('joins the statuses of a tab and trims the search text', () => {
    expect(buildTicketParams({ ...EMPTY_FILTERS, tab: 'waiting', q: '  จอ  ' }, 3)).toEqual({
      q: 'จอ',
      status: 'pending,waiting_parts,waiting_user',
      limit: '20',
      offset: '40',
    });
  });

  it('maps filter fields to API parameter names', () => {
    expect(
      buildTicketParams(
        { ...EMPTY_FILTERS, priority: 'high', deviceType: 'Projector', deviceCategory: 'จอภาพ', organizationId: '7' },
        1,
      ),
    ).toMatchObject({ priority: 'high', device_type: 'Projector', device_category: 'จอภาพ', organization_id: '7' });
  });
});

describe('paging', () => {
  it('never reports zero pages', () => {
    expect(pageCount(0)).toBe(1);
    expect(pageCount(20)).toBe(1);
    expect(pageCount(21)).toBe(2);
  });

  it('falls back to the last page that has rows', () => {
    expect(clampPage(3, 40)).toBe(2);
    expect(clampPage(0, 40)).toBe(1);
    expect(clampPage(5, 0)).toBe(1);
  });
});

describe('tabs and filters', () => {
  it('sums tab counts across the statuses of the tab', () => {
    const by = { new: 4, pending: 1, waiting_user: 2, closed: 5, cancelled: 1 };
    expect(tabCount('waiting', by, 13)).toBe(3);
    expect(tabCount('done', by, 13)).toBe(6);
    expect(tabCount('all', by, 13)).toBe(13);
    expect(tabCount('resolved', by, 13)).toBe(0);
  });

  it('counts only the dropdown filters as active', () => {
    expect(activeFilterCount({ ...EMPTY_FILTERS, q: 'x', tab: 'new', priority: 'high', organizationId: '7' })).toBe(2);
  });
});

describe('my work tab', () => {
  it('asks the server for my unfinished tickets only', () => {
    const p = buildTicketParams({ ...EMPTY_FILTERS, tab: 'mine' }, 1);
    expect(p.mine).toBe('true');
    expect(p.status).toBe('assigned,in_progress,pending,waiting_parts,waiting_user');
  });
  it('other tabs never send mine', () => {
    expect(buildTicketParams({ ...EMPTY_FILTERS, tab: 'new' }, 1).mine).toBeUndefined();
  });
  it('counts come from mine_open, not from the status totals', () => {
    expect(tabCount('mine', { in_progress: 9 }, 9, 2)).toBe(2);
  });
});

describe('holderText', () => {
  it('flags new tickets nobody holds', () => {
    expect(holderText({ status: 'new', assigned_to: null })).toEqual({ kind: 'none', text: 'ยังไม่มีคนรับ' });
  });
  it('shows a pending offer differently from an accepted job', () => {
    expect(holderText({ status: 'assigned', assigned_to: 'สมชาย', auto_assigned: true })?.kind).toBe('offer');
    expect(holderText({ status: 'in_progress', assigned_to: 'สมชาย' })).toEqual({ kind: 'person', text: 'ช่าง: สมชาย' });
  });
  it('hides cancelled tickets', () => {
    expect(holderText({ status: 'cancelled', assigned_to: 'สมชาย' })).toBeNull();
  });
});
