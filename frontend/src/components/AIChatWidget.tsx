import React, { useEffect, useRef, useState } from 'react';

// ใช้ base เดียวกับ client.ts เพื่อไม่ให้สองไฟล์ resolve URL คนละแบบ
import { API_BASE as BASE } from '../api/client';

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

export default function AIChatWidget() {
  const [open, setOpen] = useState(false);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [input, setInput] = useState('');
  const [typing, setTyping] = useState(false);
  const [sessionId] = useState<string>(resolveSessionId);
  const [greeted, setGreeted] = useState(false);
  const bodyRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // ข้อความต้อนรับตอนเปิดครั้งแรก
  useEffect(() => {
    if (open && !greeted) {
      setMessages((m) => [
        ...m,
        { role: 'bot', text: 'สวัสดีค่ะ วันนี้มีอะไรให้ช่วยคะ? ถามได้เลยเรื่องอุปกรณ์เรียนหรือแจ้งซ่อม' },
      ]);
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
    if (open) setTimeout(() => inputRef.current?.focus(), 60);
  }, [open]);

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
        throw new Error(res.status === 429 ? 'ส่งข้อความเร็วเกินไป กรุณารอสักครู่' : 'ระบบผู้ช่วยยังไม่พร้อม กรุณาลองใหม่อีกครั้ง');
      }
      const data = await res.json();
      setMessages((m) => [
        ...m,
        { role: 'bot', text: data?.reply || 'ขออภัย ไม่ได้คำตอบจากผู้ช่วยค่ะ ลองใหม่อีกครั้งนะคะ' },
      ]);
    } catch (e: any) {
      setMessages((m) => [
        ...m,
          { role: 'bot', text: e?.message || 'ติดต่อผู้ช่วยไม่ได้ในขณะนี้ กรุณาลองใหม่ค่ะ' },
      ]);
    } finally {
      setTyping(false);
    }
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter') {
      e.preventDefault();
      send();
    }
  };

  return (
    <>
      {/* ปุ่มลอย มุมขวาล่าง */}
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        title="คุยกับผู้ช่วย AI"
        style={{
          position: 'fixed',
          bottom: 22,
          right: 22,
          zIndex: 9999,
          display: 'flex',
          alignItems: 'center',
          gap: 8,
          padding: '12px 18px',
          borderRadius: 999,
          border: 'none',
          cursor: 'pointer',
          background: 'var(--color-primary, #2563eb)',
          color: '#fff',
          fontSize: 14,
          fontWeight: 600,
          boxShadow: '0 6px 20px rgba(0,0,0,0.25)',
        }}
      >
        <span>คุยกับผู้ช่วย AI</span>
      </button>

      {/* Panel แชท */}
      {open && (
        <div
          role="dialog"
          aria-label="คุยกับผู้ช่วย AI"
          style={{
            position: 'fixed',
            bottom: 80,
            right: 22,
            zIndex: 9999,
            width: 360,
            maxWidth: 'calc(100vw - 32px)',
            height: 480,
            maxHeight: 'calc(100vh - 120px)',
            display: 'flex',
            flexDirection: 'column',
            background: 'var(--color-surface, #fff)',
            border: '1px solid var(--color-border, #e5e7eb)',
            borderRadius: 16,
            overflow: 'hidden',
            boxShadow: '0 12px 40px rgba(0,0,0,0.3)',
          }}
        >
          {/* Header */}
          <div
            style={{
              padding: '12px 16px',
              background: 'var(--color-primary, #2563eb)',
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
              onClick={() => setOpen(false)}
              style={{ background: 'transparent', border: 'none', color: '#fff', cursor: 'pointer', lineHeight: 0, padding: 2, display: 'inline-flex' }}
              title="ปิด"
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
                      background: 'var(--color-primary, #2563eb)',
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

            {messages.length === 0 && !typing && (
              <div style={{ color: 'var(--color-text-tertiary, #9ca3af)', fontSize: 13, textAlign: 'center', margin: 'auto' }}>
                พิมพ์คำถามเพื่อเริ่มคุยกับผู้ช่วย
              </div>
            )}
          </div>

          {/* ช่องพิมพ์ */}
          <div style={{ display: 'flex', gap: 8, padding: 10, borderTop: '1px solid var(--color-border, #e5e7eb)', background: 'var(--color-surface, #fff)' }}>
            <input
              ref={inputRef}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={onKey}
              placeholder="พิมพ์ข้อความ..."
              aria-label="พิมพ์ข้อความถึงผู้ช่วย AI"
              style={{
                flex: 1,
                padding: '9px 12px',
                borderRadius: 8,
                border: '1px solid var(--color-border, #e5e7eb)',
                background: 'var(--color-bg, #f9fafb)',
                color: 'var(--color-text, #111827)',
                fontSize: 13.5,
                outline: 'none',
              }}
            />
            <button
              onClick={() => send()}
              disabled={typing || !input.trim()}
              style={{
                padding: '9px 16px',
                borderRadius: 8,
                border: 'none',
                background: typing || !input.trim() ? 'var(--color-muted, #9ca3af)' : 'var(--color-primary, #2563eb)',
                color: '#fff',
                fontWeight: 600,
                fontSize: 13.5,
                cursor: typing || !input.trim() ? 'not-allowed' : 'pointer',
              }}
            >
              ส่ง
            </button>
          </div>
        </div>
      )}
    </>
  );
}
