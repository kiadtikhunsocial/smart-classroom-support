import React, { useEffect, useId, useRef, useState } from 'react';

// ใช้ base เดียวกับ client.ts เพื่อไม่ให้สองไฟล์ resolve URL คนละแบบ
import { API_BASE as BASE } from '../api/client';
import { useLang } from '../publicI18n';

type Msg = { role: 'user' | 'bot'; text: string };

function resolveSessionId(): string {
  // Web chat must never reuse a LINE ID or staff identifier.
  try {
    const saved = sessionStorage.getItem('iwa_web_chat_session');
    if (saved && /^[a-f\d-]{36}$/i.test(saved)) return saved;
    const created = crypto.randomUUID();
    sessionStorage.setItem('iwa_web_chat_session', created);
    return created;
  } catch {}
  // Old/locked-down browsers: avoid assigning every visitor the same conversation.
  return 'xxxxxxxx-xxxx-4xxx-yxxx-xxxxxxxxxxxx'.replace(/[xy]/g, (ch) => {
    const digit = Math.floor(Math.random() * 16);
    return (ch === 'x' ? digit : (digit & 3) | 8).toString(16);
  });
}


/**
 * inline=true: ปุ่มเปิดเป็นแถบในหน้า (อยู่คู่กับปุ่มแจ้งซ่อม/สแกน QR) แทนปุ่มลอยมุมจอ
 */
export default function AIChatWidget({ inline = false, embedded = false }: { inline?: boolean; embedded?: boolean }) {
  // embedded=true: แผงแชตฝังอยู่ในหน้า เปิดค้างไว้ตลอด (หน้าแรกสาธารณะ)
  const { t } = useLang();
  const starters = [t('ai_s1'), t('ai_s2'), t('ai_s3'), t('ai_s4')];
  const [open, setOpen] = useState(embedded);
  const [messages, setMessages] = useState<Msg[]>(() => (embedded ? [{ role: 'bot', text: t('ai_greeting') }] : []));
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [sessionId] = useState<string>(resolveSessionId);
  const [greeted, setGreeted] = useState(embedded);
  const bodyRef = useRef<HTMLDivElement>(null);
  const triggerRef = useRef<HTMLButtonElement>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const panelId = useId();

  // ข้อความต้อนรับตอนเปิดครั้งแรก
  useEffect(() => {
    if (open && !greeted) {
      setMessages((m) => (m.length === 0 ? [{ role: 'bot', text: t('ai_greeting') }] : m));
      setGreeted(true);
    }
  }, [open, greeted]);

  // autoscroll ลงล่างสุดทุกครั้งที่มีข้อความ / เปิด
  useEffect(() => {
    if (bodyRef.current) {
      bodyRef.current.scrollTop = bodyRef.current.scrollHeight;
    }
  }, [messages, typing, open]);

  useEffect(() => {
    if (open && !embedded) closeRef.current?.focus();
  }, [open, embedded]);

  const restart = () => {
    setMessages([{ role: 'bot', text: t('ai_greeting') }]);
    setInput('');
  };

  // เปลี่ยนภาษาตอนยังไม่ได้คุย → เปลี่ยนข้อความต้อนรับตามภาษาใหม่
  const greetingNow = t('ai_greeting');
  useEffect(() => {
    setMessages((m) => (m.length === 1 && m[0].role === 'bot' ? [{ role: 'bot', text: greetingNow }] : m));
  }, [greetingNow]);

  const close = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  const send = async (textOverride?: string) => {
    const text = (textOverride ?? input).trim();
    if (!text || typing) return;

    setMessages((m) => [...m, { role: 'user', text }]);
    setInput('');
    setTyping(true);

    try {
      const res = await fetch(`${BASE}/chatbot/web`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          session_id: sessionId,
          text,
        }),
      });
      if (!res.ok) {
        throw new Error(res.status === 429 ? t('ai_err_rate') : t('ai_err'));
      }
      const data = await res.json();
      setMessages((m) => [
        ...m,
        { role: 'bot', text: data?.reply || t('ai_empty') },
      ]);
    } catch (e: any) {
      setMessages((m) => [
        ...m,
          { role: 'bot', text: e?.message || t('ai_err_net') },
      ]);
    } finally {
      setTyping(false);
    }
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.nativeEvent.isComposing) {
      e.preventDefault();
      send();
    }
  };

  if (embedded) {
    const lastBot = messages.reduce((idx, m, i) => (m.role === 'bot' && i > 0 ? i : idx), -1);
    return (
      <section className="pc-chat" aria-labelledby={`${panelId}-title`}>
        <header className="pc-chat-head">
          <span className="pc-chat-icon" aria-hidden="true">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l1.4-3.5A7.5 7.5 0 1 1 20 11.5Z" />
              <path d="M9 10h6m-6 3h4" />
            </svg>
          </span>
          <div className="pc-chat-titles">
            <h2 id={`${panelId}-title`}>{t('ai_title')}</h2>
            <p>{t('ai_sub')}</p>
          </div>
          <button type="button" className="pc-chat-restart" onClick={restart} disabled={typing}>{t('ai_restart')}</button>
        </header>

        <div className="pc-chat-body" ref={bodyRef} aria-live="polite">
          {messages.map((m, i) => (
            <div key={i} className={`pc-msg pc-msg-${m.role}`}>
              <p>{m.text}</p>
              {i === lastBot && (
                <a className="pc-msg-link" href="/?publicreport=1">{t('ai_still')}</a>
              )}
            </div>
          ))}
          {messages.length <= 1 && !typing && (
            <div className="pc-ai-starters" role="group" aria-label={t('ai_starters')}>
              {starters.map((s) => (
                <button key={s} type="button" className="pc-ai-starter" onClick={() => send(s)}>{s}</button>
              ))}
            </div>
          )}
          {typing && <div className="pc-msg pc-msg-bot pc-msg-typing"><p>{t('ai_typing')}</p></div>}
        </div>

        <form className="pc-chat-input" onSubmit={(e) => { e.preventDefault(); send(); }}>
          <input
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={onKey}
            placeholder={t('ai_ph')}
            aria-label={t('ai_ph')}
            maxLength={500}
          />
          <button type="submit" disabled={typing || !input.trim()} aria-label={t('ai_send')}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
              <path d="M12 19V5M5 12l7-7 7 7" />
            </svg>
          </button>
        </form>
      </section>
    );
  }

  return (
    <>
      {inline ? (
        <button
          type="button" ref={triggerRef} className="pc-ai"
          aria-expanded={open} aria-controls={open ? panelId : undefined}
          onClick={() => open ? close() : setOpen(true)}
        >
          <span className="pc-ai-icon" aria-hidden="true">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l1.4-3.5A7.5 7.5 0 1 1 20 11.5Z" />
              <path d="M9 10h6m-6 3h4" />
            </svg>
          </span>
          <span className="pc-ai-text">
            <strong>ถามผู้ช่วย AI ก่อน</strong>
            <small>เล่าอาการ แล้วลองแก้เบื้องต้นด้วยตัวเอง</small>
          </span>
        </button>
      ) : (
        <button
          type="button" ref={triggerRef} className="public-chat-trigger"
          aria-label="คุยกับผู้ช่วย AI" aria-expanded={open} aria-controls={open ? panelId : undefined}
          onClick={() => open ? close() : setOpen(true)}
        >
          <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
            <path d="M20 11.5a7.5 7.5 0 0 1-7.5 7.5H5l1.4-3.5A7.5 7.5 0 1 1 20 11.5Z" />
            <path d="M9 10h6m-6 3h4" />
          </svg>
          <span>คุยกับผู้ช่วย AI</span>
        </button>
      )}

      {open && (
        <section
          id={panelId} className="public-chat-panel" role="dialog" aria-label="คุยกับผู้ช่วย AI"
          onKeyDown={(event) => { if (event.key === 'Escape') { event.stopPropagation(); close(); } }}
        >
          {/* Header */}
          <div
            style={{
              padding: '12px 16px',
              background: 'var(--chat-emphasis)',
              color: '#fff',
              fontWeight: 700,
              fontSize: 15,
              display: 'flex',
              alignItems: 'center',
              justifyContent: 'space-between',
            }}
          >
            <span>ผู้ช่วย AI</span>
            <button
              type="button" ref={closeRef} className="btn btn-ghost public-chat-close" onClick={close}
              aria-label="ปิด"
            >
              <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                <path d="M18 6L6 18M6 6l12 12" />
              </svg>
            </button>
          </div>

          {/* ประวัติข้อความ */}
          <div
            ref={bodyRef}
            aria-live="polite"
            style={{
              flex: 1,
              overflowY: 'auto',
              padding: 14,
              display: 'flex',
              flexDirection: 'column',
              gap: 10,
              background: 'var(--color-bg, #f9fafb)',
            }}
          >
            {messages.map((m, i) =>
              m.role === 'bot' ? (
                <div key={i} style={{ display: 'flex', gap: 8, maxWidth: '85%', alignSelf: 'flex-start' }}>
                  <div
                    style={{
                      width: 28,
                      height: 28,
                      borderRadius: '50%',
                      background: 'var(--color-primary-light, #dbeafe)',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      fontSize: 11,
                      fontWeight: 800,
                      letterSpacing: '0.03em',
                      color: 'var(--color-primary, #2563eb)',
                      flexShrink: 0,
                    }}
                  >
                    AI
                  </div>
                  <div
                    style={{
                      background: 'var(--color-surface-raised, #fff)',
                      border: '1px solid var(--color-border, #e5e7eb)',
                      color: 'var(--color-text, #111827)',
                      padding: '8px 12px',
                      borderRadius: '4px 12px 12px 12px',
                      fontSize: 13.5,
                      lineHeight: 1.45,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    {m.text}
                  </div>
                </div>
              ) : (
                <div key={i} style={{ display: 'flex', justifyContent: 'flex-end', maxWidth: '85%', alignSelf: 'flex-end' }}>
                  <div
                    style={{
                      background: 'var(--chat-emphasis)',
                      color: '#fff',
                      padding: '8px 12px',
                      borderRadius: '12px 4px 12px 12px',
                      fontSize: 13.5,
                      lineHeight: 1.45,
                      whiteSpace: 'pre-wrap',
                      wordBreak: 'break-word',
                    }}
                  >
                    {m.text}
                  </div>
                </div>
              )
            )}

            {/* typing */}
            {typing && (
              <div style={{ display: 'flex', gap: 8, maxWidth: '85%', alignSelf: 'flex-start' }}>
                <div
                  style={{
                    width: 28,
                    height: 28,
                    borderRadius: '50%',
                    background: 'var(--color-primary-light, #dbeafe)',
                    display: 'flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 11,
                    fontWeight: 800,
                    letterSpacing: '0.03em',
                    color: 'var(--color-primary, #2563eb)',
                    flexShrink: 0,
                  }}
                >
                  AI
                </div>
                <div
                  style={{
                    background: 'var(--color-surface-raised, #fff)',
                    border: '1px solid var(--color-border, #e5e7eb)',
                    color: 'var(--color-text-secondary, #6b7280)',
                    padding: '8px 12px',
                    borderRadius: '4px 12px 12px 12px',
                    fontSize: 13.5,
                    fontStyle: 'italic',
                  }}
                >
                  …กำลังพิมพ์
                </div>
              </div>
            )}

            {messages.length <= 1 && !typing && (
              <div className="pc-ai-starters" role="group" aria-label={t('ai_starters')}>
                {starters.map((s) => (
                  <button key={s} type="button" className="pc-ai-starter" onClick={() => send(s)}>{s}</button>
                ))}
              </div>
            )}

            {messages.length === 0 && !typing && (
              <div style={{ color: 'var(--color-text-tertiary, #9ca3af)', fontSize: 13, textAlign: 'center', margin: 'auto' }}>
                พิมพ์คำถามเพื่อเริ่มคุยกับผู้ช่วย
              </div>
            )}
          </div>

          {/* ลองแล้วไม่หาย → ไปแจ้งซ่อมได้ทันทีจากในแชต */}
          {messages.length > 1 && (
            <a className="pc-ai-report" href="/?publicreport=1">ยังไม่หาย? แจ้งซ่อมเลย</a>
          )}

          {/* ช่องพิมพ์ */}
          <div style={{ display: 'flex', gap: 8, padding: 10, borderTop: '1px solid var(--color-border, #e5e7eb)', background: 'var(--color-surface, #fff)' }}>
            <input
              className="form-input public-chat-input"
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              placeholder="พิมพ์ข้อความ…"
              aria-label="พิมพ์ข้อความถึงผู้ช่วย AI"
            />
            <button
              type="button" className="btn btn-primary" onClick={() => send()}
              disabled={typing || !input.trim()}
            >
              ส่ง
            </button>
          </div>
        </section>
      )}
    </>
  );
}
