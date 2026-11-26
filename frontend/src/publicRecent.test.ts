import { beforeEach, describe, expect, it } from 'vitest';
import { forgetRecent, loadRecent, looksLikeTicketNo, saveRecent } from './publicRecent';

const store: Record<string, string> = {};
beforeEach(() => {
  for (const k of Object.keys(store)) delete store[k];
  (globalThis as any).localStorage = {
    getItem: (k: string) => store[k] ?? null,
    setItem: (k: string, v: string) => { store[k] = v; },
  };
});

describe('my tickets on this device', () => {
  it('puts the newest first, upper-cases and de-duplicates', () => {
    saveRecent('tk.a.26.0001-x');
    saveRecent('TK.B.26.0002-Y');
    expect(saveRecent('TK.A.26.0001-X')).toEqual(['TK.A.26.0001-X', 'TK.B.26.0002-Y']);
  });
  it('ignores the "-" placeholder used when the server sent no number', () => {
    expect(saveRecent('-')).toEqual([]);
  });
  it('keeps at most six', () => {
    for (let i = 0; i < 9; i++) saveRecent(`TK.A.26.000${i}-X`);
    expect(loadRecent()).toHaveLength(6);
  });
  it('can forget one', () => {
    saveRecent('TK.A.26.0001-X'); saveRecent('TK.B.26.0002-Y');
    expect(forgetRecent('tk.a.26.0001-x')).toEqual(['TK.B.26.0002-Y']);
  });
});

describe('looksLikeTicketNo', () => {
  it('tells ticket numbers from device codes', () => {
    expect(looksLikeTicketNo('tk.schm01.26.0001-t')).toBe(true);
    expect(looksLikeTicketNo('SCHM01-PRJ-001')).toBe(false);
  });
});
