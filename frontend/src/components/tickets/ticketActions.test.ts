import { describe, expect, it } from 'vitest';
import { actionsFor, validateActionInput } from './ticketActions';

describe('actionsFor', () => {
  it('offers nothing to read-only users', () => {
    expect(actionsFor('new', false)).toEqual([]);
  });

  it('offers accept first on a new ticket', () => {
    expect(actionsFor('new', true).map((a) => a.id)).toEqual(['accept', 'cancel']);
    expect(actionsFor('assigned', true)[0]).toMatchObject({ id: 'accept', kind: 'primary', needs: 'none' });
  });

  it('offers resolve while work is under way or waiting', () => {
    for (const s of ['in_progress', 'pending', 'waiting_parts', 'waiting_user']) {
      expect(actionsFor(s, true).map((a) => a.id)).toEqual(['resolve', 'cancel']);
    }
  });

  // ตรงกับกติกาฝั่ง server: /reopen รับเฉพาะ closed, /cancel ไม่รับ closed/cancelled
  it('offers close on a resolved ticket', () => {
    expect(actionsFor('resolved', true).map((a) => a.id)).toEqual(['close', 'cancel']);
  });

  it('offers reopen only on a closed ticket', () => {
    expect(actionsFor('closed', true).map((a) => a.id)).toEqual(['reopen']);
  });

  it('offers nothing on a cancelled ticket', () => {
    expect(actionsFor('cancelled', true)).toEqual([]);
  });

  it('offers nothing for an unknown status', () => {
    expect(actionsFor('weird', true)).toEqual([]);
  });
});

describe('validateActionInput', () => {
  it('requires a solution of three characters', () => {
    const resolve = actionsFor('in_progress', true)[0];
    expect(validateActionInput(resolve, { solution: ' ก ' })).toBe('กรุณากรอกวิธีแก้ไขอย่างน้อย 3 ตัวอักษร');
    expect(validateActionInput(resolve, { solution: 'เปลี่ยนสาย HDMI' })).toBeNull();
  });

  it('requires a reason to cancel or reopen', () => {
    const cancel = actionsFor('new', true)[1];
    expect(validateActionInput(cancel, { note: '   ' })).toBe('กรุณาระบุเหตุผล');
    expect(validateActionInput(cancel, { note: 'x'.repeat(2001) })).toBe('ข้อความยาวเกิน 2000 ตัวอักษร');
    expect(validateActionInput(cancel, { note: 'ผู้แจ้งยกเลิกเอง' })).toBeNull();
  });
});
