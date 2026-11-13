import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { DispatchOffer } from '../../types';
import { ticketDetailPriority } from '../tickets/ticketLabels';
import '../../styles/dispatch.css';

const POLL_MS = 15_000;

/** เสียงสั้น ๆ ตอนมีงานใหม่ — เบราว์เซอร์บางตัวไม่ให้เล่นจนกว่าผู้ใช้จะเคยกดหน้าเว็บ ก็ข้ามไป */
function chime() {
  try {
    const Ctx = window.AudioContext || (window as any).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    [880, 1175].forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, ctx.currentTime + i * 0.18);
      gain.gain.exponentialRampToValueAtTime(0.25, ctx.currentTime + i * 0.18 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + i * 0.18 + 0.16);
      osc.connect(gain).connect(ctx.destination);
      osc.start(ctx.currentTime + i * 0.18);
      osc.stop(ctx.currentTime + i * 0.18 + 0.17);
    });
    // สั่นได้เฉพาะหลังผู้ใช้เคยแตะหน้าเว็บ (กฎเบราว์เซอร์) — ไม่งั้นได้คำเตือนใน console
    if ((navigator as any).userActivation?.hasBeenActive) navigator.vibrate?.([120, 60, 120]);
  } catch { /* ไม่มีเสียงก็ยังเห็น popup */ }
}

function secondsLeft(expiresAt: string | null, now: number) {
  if (!expiresAt) return null;
  return Math.max(0, Math.round((new Date(expiresAt).getTime() - now) / 1000));
}

export interface DispatchOfferPopupProps {
  /** กดรับแล้ว → เปิดใบงานนั้นในหน้าใบงาน */
  onAccepted: (ticketId: string) => void;
}

/** งานเด้ง (แบบ Grab) — ช่างเห็นงานที่ระบบเสนอให้ กด "รับงาน" หรือ "ข้าม"
 *  ถามเซิร์ฟเวอร์ทุก 15 วินาทีเฉพาะตอนเปิดหน้าเว็บอยู่ (แท็บซ่อน = ไม่ถาม, LINE ยังแจ้งอยู่) */
export default function DispatchOfferPopup({ onAccepted }: DispatchOfferPopupProps) {
  const [offers, setOffers] = useState<DispatchOffer[]>([]);
  const [busy, setBusy] = useState<'' | 'accept' | 'skip'>('');
  const [error, setError] = useState('');
  const [now, setNow] = useState(Date.now());
  const seen = useRef<Set<string>>(new Set());
  const acceptRef = useRef<HTMLButtonElement | null>(null);

  const poll = useCallback(async () => {
    if (document.visibilityState === 'hidden') return;
    try {
      const me = await api.dispatchMe();
      if (!me.can_receive) return;
      setOffers(me.offers);
      const fresh = me.offers.filter((o) => !seen.current.has(o.ticket_id));
      if (fresh.length) {
        fresh.forEach((o) => seen.current.add(o.ticket_id));
        chime();
      }
    } catch { /* เครือข่ายสะดุด — รอบหน้าลองใหม่ */ }
  }, []);

  useEffect(() => {
    void poll();
    const id = window.setInterval(() => void poll(), POLL_MS);
    const onVisible = () => { if (document.visibilityState === 'visible') void poll(); };
    document.addEventListener('visibilitychange', onVisible);
    window.addEventListener('dispatch:refresh', poll as EventListener);
    return () => {
      window.clearInterval(id);
      document.removeEventListener('visibilitychange', onVisible);
      window.removeEventListener('dispatch:refresh', poll as EventListener);
    };
  }, [poll]);

  const offer = offers[0];

  useEffect(() => {
    if (!offer) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    acceptRef.current?.focus();
    return () => window.clearInterval(id);
  }, [offer?.ticket_id]);

  if (!offer) return error ? <div className="dp-toast" role="alert">{error}</div> : null;

  const left = secondsLeft(offer.expires_at, now);
  const mmss = left === null ? '' : `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;

  const act = async (kind: 'accept' | 'skip') => {
    setBusy(kind); setError('');
    try {
      if (kind === 'accept') await api.acceptTicket(offer.ticket_id);
      else await api.declineTicket(offer.ticket_id);
      setOffers((list) => list.filter((o) => o.ticket_id !== offer.ticket_id));
      window.dispatchEvent(new Event('dispatch:changed'));
      if (kind === 'accept') onAccepted(offer.ticket_id);
    } catch (e: any) {
      // คนอื่นรับไปแล้ว / หมดเวลา → เอาออกจากจอ ไม่ต้องให้กดซ้ำ
      setError(e?.message || 'ทำรายการไม่สำเร็จ');
      setOffers((list) => list.filter((o) => o.ticket_id !== offer.ticket_id));
      window.setTimeout(() => setError(''), 4000);
    } finally {
      setBusy('');
    }
  };

  return (
    <div className="dp-overlay" role="presentation">
      <section className="dp-offer" role="alertdialog" aria-modal="true" aria-labelledby="dp-offer-title"
        aria-describedby="dp-offer-desc">
        <header className="dp-offer-head">
          <span className="dp-pulse" aria-hidden="true" />
          <h2 id="dp-offer-title">มีงานซ่อมใหม่สำหรับคุณ</h2>
          {mmss && <span className={`dp-timer${left !== null && left < 60 ? ' is-low' : ''}`} aria-label={`เหลือเวลา ${mmss} นาที`}>{mmss}</span>}
        </header>
        <div id="dp-offer-desc" className="dp-offer-body">
          <p className="dp-offer-title">{offer.title}</p>
          <dl className="dp-offer-facts">
            <div><dt>อุปกรณ์</dt><dd>{offer.device_label || offer.device_id}</dd></div>
            {offer.organization_name && <div><dt>สถานที่</dt><dd>{offer.organization_name}</dd></div>}
            <div><dt>ความเร่งด่วน</dt><dd><span className={`badge badge-priority-${offer.priority}`}>{ticketDetailPriority[offer.priority] || offer.priority}</span></dd></div>
            <div><dt>เลขใบงาน</dt><dd className="dp-mono">{offer.ticket_id}</dd></div>
          </dl>
          {offers.length > 1 && <p className="dp-more">และอีก {offers.length - 1} งานที่รอคุณตอบ</p>}
          {error && <p role="alert" className="dp-error">{error}</p>}
        </div>
        <footer className="dp-offer-actions">
          <button type="button" className="btn btn-ghost dp-skip" disabled={!!busy} onClick={() => void act('skip')}>
            {busy === 'skip' ? 'กำลังส่งต่อ…' : 'ข้าม'}
          </button>
          <button ref={acceptRef} type="button" className="btn btn-primary dp-accept" disabled={!!busy} onClick={() => void act('accept')}>
            {busy === 'accept' ? 'กำลังรับงาน…' : 'รับงาน'}
          </button>
        </footer>
        <p className="dp-hint">ไม่ตอบภายในเวลา ระบบจะส่งงานนี้ให้ช่างคนถัดไป</p>
      </section>
    </div>
  );
}
