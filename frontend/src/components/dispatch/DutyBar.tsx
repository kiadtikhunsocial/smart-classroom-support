import React, { useCallback, useEffect, useState } from 'react';
import { api } from '../../api/client';
import type { DispatchMe } from '../../types';
import '../../styles/dispatch.css';

/** แถบของช่างบนหน้าใบงาน: สวิตช์ "พร้อมรับงาน", งานค้าง/เสร็จวันนี้, ผูก LINE รับแจ้งเตือนส่วนตัว */
export default function DutyBar() {
  const [me, setMe] = useState<DispatchMe | null>(null);
  const [saving, setSaving] = useState(false);
  const [code, setCode] = useState<{ code: string; expires_at: string } | null>(null);
  const [message, setMessage] = useState('');

  const load = useCallback(() => {
    api.dispatchMe().then(setMe).catch(() => setMe(null));
  }, []);

  useEffect(() => {
    load();
    window.addEventListener('dispatch:changed', load);
    return () => window.removeEventListener('dispatch:changed', load);
  }, [load]);

  if (!me || !me.can_receive) return null;

  const toggle = async () => {
    setSaving(true); setMessage('');
    try {
      const r = await api.setMyDuty(!me.on_duty);
      setMe({ ...me, on_duty: r.on_duty });
      if (r.passed_on > 0) setMessage(`ส่งงานที่รอคุณตอบ ${r.passed_on} งานให้ช่างคนอื่นแล้ว`);
      window.dispatchEvent(new Event('dispatch:refresh'));
    } catch (e: any) {
      setMessage(e?.message || 'เปลี่ยนสถานะไม่สำเร็จ');
    } finally {
      setSaving(false);
    }
  };

  const getCode = async () => {
    setMessage('');
    try {
      setCode(await api.lineLinkCode());
    } catch (e: any) {
      setMessage(e?.message || 'ขอรหัสไม่สำเร็จ');
    }
  };

  const expires = code ? new Date(code.expires_at).toLocaleTimeString('th-TH', { hour: '2-digit', minute: '2-digit' }) : '';

  return (
    <section className="dp-duty" aria-label="สถานะรับงานของฉัน">
      <button type="button" role="switch" aria-checked={me.on_duty} disabled={saving}
        className={`dp-switch${me.on_duty ? ' is-on' : ''}`} onClick={() => void toggle()}>
        <span className="dp-switch-knob" aria-hidden="true" />
        <span className="dp-switch-label">{me.on_duty ? 'พร้อมรับงาน' : 'ปิดรับงาน'}</span>
      </button>
      <span className="dp-duty-stat"><strong>{me.open}</strong> งานค้าง</span>
      <span className="dp-duty-stat"><strong>{me.done_today}</strong> เสร็จวันนี้</span>
      {me.line_linked ? (
        <span className="dp-line is-linked">LINE แจ้งเตือนส่วนตัว: เปิดอยู่</span>
      ) : code ? (
        <span className="dp-line">
          ส่งข้อความ <strong className="dp-mono">ผูก {code.code}</strong> ไปที่ LINE OA ของระบบ (ใช้ได้ถึง {expires})
          <button type="button" className="btn btn-ghost btn-sm" onClick={load}>ส่งแล้ว</button>
        </span>
      ) : (
        <button type="button" className="btn btn-secondary btn-sm" onClick={() => void getCode()}>
          ผูก LINE เพื่อรับงานทางไลน์
        </button>
      )}
      {message && <span role="status" className="dp-duty-msg">{message}</span>}
    </section>
  );
}
