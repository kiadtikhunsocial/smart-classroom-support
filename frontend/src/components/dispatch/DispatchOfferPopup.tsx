import React, { useCallback, useEffect, useRef, useState } from 'react';
import { api } from '../../api/client';
import type { DispatchOffer } from '../../types';
import { ticketDetailPriority } from '../tickets/ticketLabels';
import '../../styles/dispatch.css';

const POLL_MS = 15_000;
/** งานค้างที่ช่างกด "ไว้ก่อน" — จำไว้ในแท็บนี้ ไม่เด้งซ้ำทุก 15 วินาที */
const DISMISSED_KEY = 'sc_pool_dismissed';

/** เสียงสั้น ๆ ตอนมีงานใหม่ — เบราว์เซอร์บางตัวไม่ให้เล่นจนกว่าผู้ใช้จะเคยกดหน้าเว็บ ก็ข้ามไป */
function chime(soft = false) {
  try {
    const Ctx = window.AudioContext || (window as any).webkitAudioContext;
    if (!Ctx) return;
    const ctx = new Ctx();
    (soft ? [660] : [880, 1175]).forEach((freq, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = freq;
      gain.gain.setValueAtTime(0.0001, ctx.currentTime + i * 0.18);
      gain.gain.exponentialRampToValueAtTime(soft ? 0.12 : 0.25, ctx.currentTime + i * 0.18 + 0.02);
      gain.gain.exponentialRampToValueAtTime(0.0001, ctx.currentTime + i * 0.18 + 0.16);
      osc.connect(gain).connect(ctx.destination);
      osc.start(ctx.currentTime + i * 0.18);
      osc.stop(ctx.currentTime + i * 0.18 + 0.17);
    });
    // สั่นได้เฉพาะหลังผู้ใช้เคยแตะหน้าเว็บ (กฎเบราว์เซอร์) — ไม่งั้นได้คำเตือนใน console
    if (!soft && (navigator as any).userActivation?.hasBeenActive) navigator.vibrate?.([120, 60, 120]);
  } catch { /* ไม่มีเสียงก็ยังเห็น popup */ }
}

function secondsLeft(expiresAt: string | null, now: number) {
  if (!expiresAt) return null;
  return Math.max(0, Math.round((new Date(expiresAt).getTime() - now) / 1000));
}

function readDismissed(): Set<string> {
  try { return new Set(JSON.parse(sessionStorage.getItem(DISMISSED_KEY) || '[]')); } catch { return new Set(); }
}
function saveDismissed(s: Set<string>) {
  try { sessionStorage.setItem(DISMISSED_KEY, JSON.stringify([...s].slice(-50))); } catch { /* ไม่มีที่เก็บก็แค่เด้งซ้ำ */ }
}

function ageText(iso: string | null | undefined, now: number): string {
  if (!iso) return '';
  const mins = Math.max(0, Math.round((now - new Date(iso).getTime()) / 60000));
  if (mins < 1) return 'เพิ่งเข้ามา';
  if (mins < 60) return `รอมา ${mins} นาที`;
  const h = Math.floor(mins / 60);
  return h < 24 ? `รอมา ${h} ชม.` : `รอมา ${Math.floor(h / 24)} วัน`;
}

export interface DispatchOfferPopupProps {
  /** กดรับแล้ว → เปิดใบงานนั้นในหน้าใบงาน */
  onAccepted: (ticketId: string) => void;
}

/** แจ้งเตือนงานของช่าง (ถามเซิร์ฟเวอร์ทุก 15 วินาทีตอนเปิดหน้าเว็บอยู่)
 *  1) ระบบมอบงานให้เรา (เราว่าง) → หน้าต่างเด้งกลางจอ "รับงาน" / "ส่งต่อ" + นับถอยหลัง
 *  2) ทีมยุ่งทั้งหมด มีงานค้าง → แถบแจ้งเตือนมุมจอ ไม่บังงาน "รับงานนี้" / "ไว้ก่อน" ไม่รับก็ไม่เป็นไร */
export default function DispatchOfferPopup({ onAccepted }: DispatchOfferPopupProps) {
  const [offers, setOffers] = useState<DispatchOffer[]>([]);
  const [pool, setPool] = useState<DispatchOffer[]>([]);
  const [active, setActive] = useState(0);
  const [busy, setBusy] = useState<'' | 'accept' | 'skip' | 'claim'>('');
  const [error, setError] = useState('');
  const [now, setNow] = useState(Date.now());
  const [dismissed, setDismissed] = useState<Set<string>>(readDismissed);
  const seen = useRef<Set<string>>(new Set());
  const acceptRef = useRef<HTMLButtonElement | null>(null);

  const poll = useCallback(async () => {
    if (document.visibilityState === 'hidden') return;
    try {
      const me = await api.dispatchMe();
      if (!me.can_receive) return;
      setOffers(me.offers);
      setPool(me.pool || []);
      setActive(me.active ?? me.open ?? 0);
      setNow(Date.now());
      const freshOffers = me.offers.filter((o) => !seen.current.has(o.ticket_id));
      const freshPool = (me.pool || []).filter((o) => !seen.current.has(o.ticket_id));
      [...freshOffers, ...freshPool].forEach((o) => seen.current.add(o.ticket_id));
      if (freshOffers.length) chime();
      else if (freshPool.length) chime(true);
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
  const poolItems = pool.filter((p) => !dismissed.has(p.ticket_id));
  const poolItem = poolItems[0];

  useEffect(() => {
    if (!offer) return;
    const id = window.setInterval(() => setNow(Date.now()), 1000);
    acceptRef.current?.focus();
    return () => window.clearInterval(id);
  }, [offer?.ticket_id]);

  const flashError = (e: any) => {
    setError(e?.message || 'ทำรายการไม่สำเร็จ');
    window.setTimeout(() => setError(''), 4000);
  };

  const act = async (kind: 'accept' | 'skip') => {
    if (!offer) return;
    setBusy(kind); setError('');
    try {
      if (kind === 'accept') await api.acceptTicket(offer.ticket_id);
      else await api.declineTicket(offer.ticket_id);
      setOffers((list) => list.filter((o) => o.ticket_id !== offer.ticket_id));
      window.dispatchEvent(new Event('dispatch:changed'));
      if (kind === 'accept') onAccepted(offer.ticket_id);
    } catch (e: any) {
      // คนอื่นรับไปแล้ว / หมดเวลา → เอาออกจากจอ ไม่ต้องให้กดซ้ำ
      flashError(e);
      setOffers((list) => list.filter((o) => o.ticket_id !== offer.ticket_id));
    } finally {
      setBusy('');
    }
  };

  const dismissPool = (ticketId: string) => {
    const next = new Set(dismissed); next.add(ticketId);
    setDismissed(next); saveDismissed(next);
  };

  const claim = async () => {
    if (!poolItem) return;
    setBusy('claim'); setError('');
    try {
      await api.acceptTicket(poolItem.ticket_id);
      setPool((list) => list.filter((o) => o.ticket_id !== poolItem.ticket_id));
      window.dispatchEvent(new Event('dispatch:changed'));
      onAccepted(poolItem.ticket_id);
    } catch (e: any) {
      flashError(e);  // ระบบเพิ่งมอบให้คนที่ว่าง / มีคนรับไปแล้ว
      setPool((list) => list.filter((o) => o.ticket_id !== poolItem.ticket_id));
    } finally {
      setBusy('');
    }
  };

  // ── 1) งานที่ระบบมอบให้เรา: หน้าต่างกลางจอ ─────────────────────────────
  if (offer) {
    const left = secondsLeft(offer.expires_at, now);
    const mmss = left === null ? '' : `${Math.floor(left / 60)}:${String(left % 60).padStart(2, '0')}`;
    return (
      <div className="dp-overlay" role="presentation">
        <section className="dp-offer" role="alertdialog" aria-modal="true" aria-labelledby="dp-offer-title"
          aria-describedby="dp-offer-desc">
          <header className="dp-offer-head">
            <span className="dp-pulse" aria-hidden="true" />
            <h2 id="dp-offer-title">ระบบมอบงานให้คุณ</h2>
            {mmss && <span className={`dp-timer${left !== null && left < 60 ? ' is-low' : ''}`} aria-label={`เหลือเวลา ${mmss} นาที`}>{mmss}</span>}
          </header>
          <div id="dp-offer-desc" className="dp-offer-body">
            <p className="dp-offer-reason">คุณว่างอยู่ ระบบจึงส่งงานนี้ให้คุณก่อน</p>
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
              {busy === 'skip' ? 'กำลังส่งต่อ…' : 'ส่งต่อ'}
            </button>
            <button ref={acceptRef} type="button" className="btn btn-primary dp-accept" disabled={!!busy} onClick={() => void act('accept')}>
              {busy === 'accept' ? 'กำลังรับงาน…' : 'รับงาน'}
            </button>
          </footer>
          <p className="dp-hint">ไม่ตอบภายในเวลา ระบบจะส่งงานนี้ให้ช่างที่ว่างคนถัดไป</p>
        </section>
      </div>
    );
  }

  // ── 2) งานค้างของทีม: แถบมุมจอ ไม่บังการทำงาน ──────────────────────────
  if (poolItem) {
    return (
      <aside className="dp-pool" role="status" aria-live="polite" aria-label="งานค้างของทีม">
        <div className="dp-pool-head">
          <span className="dp-pool-dot" aria-hidden="true" />
          <strong>มีงานใหม่ — ทีมยังไม่ว่าง</strong>
          {poolItems.length > 1 && <span className="dp-pool-count">{poolItems.length} งาน</span>}
        </div>
        <p className="dp-pool-title">{poolItem.title}</p>
        <p className="dp-pool-meta">
          {poolItem.device_label || poolItem.device_id}
          {poolItem.organization_name ? ` · ${poolItem.organization_name}` : ''}
          {' · '}{ageText(poolItem.created_at, now)}
        </p>
        <p className="dp-pool-hint">
          คุณมีงานที่กำลังทำ {active} งาน — รับเพิ่มได้ถ้าสะดวก ไม่รับก็ไม่เป็นไร ใครว่างก่อนระบบจะมอบให้เอง
        </p>
        {error && <p role="alert" className="dp-error">{error}</p>}
        <div className="dp-pool-actions">
          <button type="button" className="btn btn-ghost btn-sm" disabled={!!busy} onClick={() => dismissPool(poolItem.ticket_id)}>
            ไว้ก่อน
          </button>
          <button type="button" className="btn btn-primary btn-sm" disabled={!!busy} onClick={() => void claim()}>
            {busy === 'claim' ? 'กำลังรับงาน…' : 'รับงานนี้'}
          </button>
        </div>
      </aside>
    );
  }

  return error ? <div className="dp-toast" role="alert">{error}</div> : null;
}
