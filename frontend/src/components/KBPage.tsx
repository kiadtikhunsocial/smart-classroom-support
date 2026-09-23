import React, { useState, useEffect } from 'react';
import { api } from '../api/client';
import '../styles/chatbot-review.css';

const DEVICE_TYPES = [
  'Interactive Display', 'Computer AIO', 'Computer Notebook', 'Computer Tablet',
  'Computer Desktop', 'Router', 'Access Point', 'Switch', 'Speaker', 'Camera',
  'Visualizer', 'Microphone', 'UPS', 'Printer', 'Projector',
  'Software (Picaro)', 'Software (Phonics Hero)', 'Other',
];

export default function KBPage({ onBack, userRole, userOrgId }: { onBack: () => void; userRole?: string; userOrgId?: number | null }) {
  // เจ้าหน้าที่ IT ที่มีสังกัด (สร้างโดยผู้ดูแลโรงเรียน) = ดูความรู้ได้ แต่แก้ไขไม่ได้
  const canEditKB = userRole === 'owner' || userRole === 'super_admin' || userRole === 'admin'
    || userRole === 'admin_school' || (userRole === 'it_support' && !userOrgId);
  // admin_school แก้ได้เฉพาะบทความของรรตัวเอง (บทความส่วนกลาง read-only)
  const canEditArticle = (a: any) =>
    canEditKB && !(userRole === 'admin_school' && (a?.organization_id ?? null) !== (userOrgId ?? null));
  const canReviewBot = !userOrgId && ['owner', 'super_admin', 'admin', 'it_support'].includes(userRole || '');
  const [botReviewOpen, setBotReviewOpen] = useState(false);
  const [botStats, setBotStats] = useState<{ total_conversations: number; self_service_rate: number; missed_queries: string[] } | null>(null);
  const [botReviewError, setBotReviewError] = useState<string | null>(null);
  const [articles, setArticles] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [q, setQ] = useState('');
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<any | null>(null);
  const [saving, setSaving] = useState(false);
  const [selected, setSelected] = useState<any | null>(null);
  const [form, setForm] = useState({
    title: '',
    device_type: '',
    symptom_tags: '',
    steps: '',
    is_published: true,
  });

  const load = () => {
    setLoading(true);
    api.listKB({ q: q || undefined, limit: 100 })
      .then(setArticles)
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, []);

  const openEdit = (a: any) => {
    setEditing(a);
    setForm({
      title: a.title,
      device_type: a.device_type || '',
      symptom_tags: Array.isArray(a.symptom_tags) ? a.symptom_tags.join(', ') : '',
      steps: Array.isArray(a.steps) ? a.steps.map((s: any) => (typeof s === 'string' ? s : s.text)).join('\n') : '',
      is_published: a.is_published,
    });
    setShowForm(true);
    setSelected(null);
  };

  const openNew = () => {
    setEditing(null);
    setForm({ title: '', device_type: '', symptom_tags: '', steps: '', is_published: true });
    setShowForm(true);
    setSelected(null);
  };

  const reviewQuestion = (question: string) => {
    setEditing(null);
    setForm({ title: '', device_type: '', symptom_tags: question.slice(0, 120), steps: '', is_published: false });
    setShowForm(true);
    setSelected(null);
  };

  const toggleReview = async () => {
    if (botReviewOpen) { setBotReviewOpen(false); return; }
    setBotReviewOpen(true); setBotReviewError(null);
    try { setBotStats(await api.getChatbotAnalytics(30)); }
    catch (e: any) { setBotReviewError(e?.message || 'โหลดคำถามที่ควรตรวจไม่สำเร็จ'); }
  };

  const save = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!form.title.trim()) { setError('กรอกหัวข้อ'); return; }
    setSaving(true);
    setError(null);
    const data = {
      title: form.title.trim(),
      device_type: form.device_type || null,
      symptom_tags: form.symptom_tags.split(',').map((s) => s.trim()).filter(Boolean),
      steps: form.steps.split('\n').map((s) => s.trim()).filter(Boolean).map((t, i) => ({ order: i + 1, text: t })),
      is_published: form.is_published,
    };
    try {
      if (editing) await api.updateKB(editing.kb_id, data);
      else await api.createKB(data);
      setShowForm(false);
      setEditing(null);
      setForm({ title: '', device_type: '', symptom_tags: '', steps: '', is_published: true });
      load();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const remove = async (a: any) => {
    if (!window.confirm(`ลบบทความ "${a.title}"?`)) return;
    try {
      await api.deleteKB(a.kb_id);
      if (selected?.kb_id === a.kb_id) setSelected(null);
      load();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const stepsArray = (a: any) => {
    if (Array.isArray(a.steps)) return a.steps.map((s: any) => typeof s === 'string' ? s : (s.text || ''));
    return [];
  };

  return (
    <div className="page-content">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          </button>
          <div>
            <h1 className="top-bar-title">ฐานความรู้แชตบอต</h1>
            <span className="top-bar-subtitle">แก้บทความได้เอง · เผยแพร่เฉพาะข้อมูลที่ตรวจสอบแล้ว</span>
          </div>
        </div>
        <div className="top-bar-actions">
          <input className="form-input" style={{ width: 200 }} placeholder="ค้นหาบทความ..." value={q}
            onChange={(e) => setQ(e.target.value)} onKeyDown={(e) => e.key === 'Enter' && load()} />
          <button className="btn btn-secondary btn-icon" onClick={load} aria-label="โหลดใหม่" title="โหลดใหม่">
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
              <path d="M21 12a9 9 0 11-3.5-7.1" />
              <path d="M21 3v6h-6" />
            </svg>
          </button>
          {canEditKB && <button className="btn btn-primary" onClick={openNew}>+ เพิ่มบทความ</button>}
        </div>
      </div>

      {error && <div style={{ padding: '10px 14px', background: 'var(--color-danger-light)', color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)', fontSize: '0.8rem', marginBottom: 16 }}>{error}</div>}

      <section className="bot-review-guide" aria-label="วิธีพัฒนาแชตบอต">
        <div><span className="bot-review-kicker">ปรับคำตอบได้ด้วยตัวเอง</span>
          <h2>ทบทวนคำถาม → เพิ่มความรู้ → ทดสอบ → เผยแพร่</h2>
          <p>เขียนขั้นตอนที่ตรวจสอบได้พร้อมคำค้นหลายรูปแบบ บันทึกเป็นฉบับร่างก่อน ทวนข้อมูลกับผู้เชี่ยวชาญ แล้วจึงเปิด “เผยแพร่” และทดสอบในสภาพแวดล้อมทดสอบ</p></div>
        {canReviewBot && <button className="btn" type="button" onClick={() => void toggleReview()} aria-expanded={botReviewOpen}>{botReviewOpen ? 'ซ่อนคำถามที่ควรตรวจ' : 'ดูคำถามที่บอตตอบไม่ชัด'}</button>}
      </section>
      {botReviewOpen && <section className="bot-review-panel" aria-label="คุณภาพแชตบอต">
        <div className="bot-review-head"><h3>ทบทวนคำถามย้อนหลัง 30 วัน</h3><span>รายการนี้เป็นสัญญาณให้มนุษย์ตรวจ ไม่ใช่การตัดสินว่าบอตผิดทุกข้อ</span></div>
        {botReviewError && <p role="alert">{botReviewError}</p>}
        {botStats && <><p className="bot-review-summary">บทสนทนา {botStats.total_conversations.toLocaleString('th-TH')} ครั้ง · คำถามที่ควรทบทวน (ไม่ซ้ำ) {botStats.missed_queries.length} รายการ</p>
          {botStats.missed_queries.length === 0 ? <p>ยังไม่มีคำถามที่ระบบจัดเป็น “ควรตรวจ” ในช่วงนี้</p>
            : <ol>{botStats.missed_queries.slice(0, 20).map((question, index) => <li key={`${index}-${question}`}>
                <span>{question}</span>{canEditKB && <button className="btn btn-ghost" type="button" onClick={() => reviewQuestion(question)}>สร้างบทความฉบับร่าง</button>}
              </li>)}</ol>}</>}
      </section>}

      {/* รายการบทความ (เต็มความกว้าง) */}
      {loading ? (
        <div style={{ textAlign: 'center', padding: 40 }}><div className="spinner" style={{ width: 30, height: 30, margin: '0 auto 12px' }} /></div>
      ) : articles.length === 0 ? (
        <div className="panel-card empty-text" style={{ padding: 40, textAlign: 'center' }}>ยังไม่มีบทความ — กด "+ เพิ่มบทความ" เพื่อสร้าง</div>
      ) : (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(300px, 1fr))', gap: 12 }}>
          {articles.map((a) => (
            <div
              key={a.kb_id}
              onClick={() => { setSelected(a); setShowForm(false); }}
              style={{
                border: '1px solid var(--color-border)',
                borderRadius: 'var(--radius-md)', padding: 16, cursor: 'pointer',
                background: 'var(--color-surface)',
                transition: 'all 0.15s',
                boxShadow: '0 1px 3px rgba(0,0,0,0.04)',
              }}
              onMouseEnter={(e) => { e.currentTarget.style.borderColor = 'var(--color-primary)'; e.currentTarget.style.boxShadow = '0 4px 14px rgba(0,0,0,0.08)'; }}
              onMouseLeave={(e) => { e.currentTarget.style.borderColor = 'var(--color-border)'; e.currentTarget.style.boxShadow = '0 1px 3px rgba(0,0,0,0.04)'; }}
            >
              <div style={{ display: 'flex', justifyContent: 'space-between', gap: 8, alignItems: 'flex-start' }}>
                <div style={{ fontWeight: 600, fontSize: '0.9rem' }}>{a.title}</div>
                {a.device_type && <span className="badge badge-in_progress" style={{ flexShrink: 0, fontSize: '0.68rem' }}>{a.device_type}</span>}
              </div>
              <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)', marginTop: 6 }}>
                {a.kb_id} · ดู {a.view_count} ครั้ง · ช่วยได้ {a.success_count} ครั้ง · {stepsArray(a).length} ขั้นตอน
                {(a.organization_id ?? null) === null
                  ? <span style={{ marginLeft: 6, color: 'var(--color-primary)' }}>· ส่วนกลาง</span>
                  : <span style={{ marginLeft: 6, color: 'var(--color-success, #2F855A)' }}>· เฉพาะโรงเรียน</span>}
              </div>
              {!a.is_published && <div style={{ fontSize: '0.7rem', color: 'var(--color-danger)', marginTop: 4 }}>ยังไม่เผยแพร่</div>}
              {stepsArray(a).length > 0 && (
                <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)', marginTop: 8, lineHeight: 1.5, display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                  {stepsArray(a).slice(0, 2).map((s: string, i: number) => (
                    <div key={i}>{i + 1}. {s}</div>
                  ))}
                </div>
              )}
              <div style={{ marginTop: 10, fontSize: '0.72rem', color: 'var(--color-primary)', fontWeight: 600 }}>
                ดูรายละเอียด →
              </div>
            </div>
          ))}
        </div>
      )}

      {/* ─── Panel ดูบทความ (slide จากขวา) ─── */}
      {selected && (
        <div className="panel-overlay" onClick={() => setSelected(null)}>
          <div className="repair-panel" style={{ width: 560, maxWidth: '95vw' }} onClick={(e) => e.stopPropagation()}>
            <div className="repair-panel-header">
              <div>
                <h3 className="repair-panel-title">{selected.title}</h3>
                <div style={{ fontSize: '0.78rem', color: 'var(--color-text-tertiary)', marginTop: 2 }}>
                  {selected.kb_id}
                  {selected.device_type ? ` · ${selected.device_type}` : ''}
                  {selected.is_published ? '' : ' · ยังไม่เผยแพร่'}
                </div>
              </div>
              <button className="repair-panel-close" onClick={() => setSelected(null)}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>

            <div className="repair-panel-body">
              {/* Tags */}
              {Array.isArray(selected.symptom_tags) && selected.symptom_tags.length > 0 && (
                <div style={{ marginBottom: 20 }}>
                  <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: 8 }}>คำค้นที่เกี่ยวข้อง</div>
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 6 }}>
                    {selected.symptom_tags.map((t: string, i: number) => (
                      <span key={i} style={{
                        padding: '4px 12px', background: 'var(--color-primary-light)',
                        color: 'var(--color-primary-dark)', borderRadius: 20, fontSize: '0.78rem',
                      }}>{t}</span>
                    ))}
                  </div>
                </div>
              )}

              {/* Steps */}
              <div style={{ fontSize: '0.8rem', fontWeight: 600, color: 'var(--color-text-secondary)', marginBottom: 10 }}>
                ขั้นตอนวิธีแก้ไข ({stepsArray(selected).length} ขั้น)
              </div>
              <ol style={{ margin: 0, padding: '0 0 0 22px', lineHeight: 1.9 }}>
                {stepsArray(selected).map((s: string, i: number) => (
                  <li key={i} style={{ fontSize: '0.92rem', color: 'var(--color-text)', marginBottom: 8 }}>
                    <span style={{ color: 'var(--color-primary)', fontWeight: 600, marginRight: 6 }}>{i + 1}.</span>
                    {s}
                  </li>
                ))}
              </ol>

              {/* Stats + actions */}
              <div style={{
                display: 'flex', alignItems: 'center', gap: 20,
                marginTop: 24, padding: '14px 18px', background: 'var(--color-bg)',
                borderRadius: 'var(--radius-md)',
              }}>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontWeight: 700, fontSize: '1.15rem', color: 'var(--color-text)' }}>{selected.view_count || 0}</div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--color-text-tertiary)' }}>ผู้เข้าชม</div>
                </div>
                <div style={{ textAlign: 'center' }}>
                  <div style={{ fontWeight: 700, fontSize: '1.15rem', color: 'var(--color-text)' }}>{selected.success_count || 0}</div>
                  <div style={{ fontSize: '0.7rem', color: 'var(--color-text-tertiary)' }}>แก้ไขสำเร็จ</div>
                </div>
                <div style={{ flex: 1 }} />
                {canEditArticle(selected) && (
                  <>
                    <button className="btn btn-secondary" style={{ fontSize: '0.82rem', padding: '8px 16px' }} onClick={() => openEdit(selected)}>แก้ไขบทความ</button>
                    <button className="btn btn-ghost" style={{ fontSize: '0.82rem', padding: '8px 16px', color: 'var(--color-danger)' }} onClick={() => remove(selected)}>ลบ</button>
                  </>
                )}
                {!canEditArticle(selected) && (
                  <span style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)' }}>
                    {(selected.organization_id ?? null) === null ? 'บทความส่วนกลาง — ดูได้อย่างเดียว' : 'ดูได้อย่างเดียว'}
                  </span>
                )}
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ─── Panel ฟอร์มเพิ่ม/แก้ไข (slide จากขวา) ─── */}
      {showForm && (
        <div className="panel-overlay" onClick={() => setShowForm(false)}>
          <div className="repair-panel" style={{ width: 560, maxWidth: '95vw' }} onClick={(e) => e.stopPropagation()}>
            <div className="repair-panel-header">
              <h3 className="repair-panel-title">{editing ? 'แก้ไขบทความ' : 'เพิ่มบทความใหม่'}</h3>
              <button className="repair-panel-close" onClick={() => setShowForm(false)}>
                <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M18 6L6 18M6 6l12 12"/></svg>
              </button>
            </div>
            <form onSubmit={save} className="repair-panel-body">
              <div className="form-row">
                <div className="form-group" style={{ flex: 2 }}>
                  <label className="form-label">หัวข้อ<span className="required">*</span></label>
                  <input className="form-input" value={form.title} onChange={(e) => setForm({ ...form, title: e.target.value })} placeholder="จอ Interactive ไม่มีภาพ" />
                </div>
                <div className="form-group">
                  <label className="form-label">ประเภท</label>
                  <select className="form-select" value={form.device_type} onChange={(e) => setForm({ ...form, device_type: e.target.value })}>
                    <option value="">ทุกประเภท</option>
                    {DEVICE_TYPES.map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">คำค้น (คั่นด้วย ,)</label>
                <input className="form-input" value={form.symptom_tags} onChange={(e) => setForm({ ...form, symptom_tags: e.target.value })} placeholder="จอไม่ติด, ไม่มีภาพ, no signal" />
              </div>
              <div className="form-group">
                <label className="form-label">ขั้นตอน (ทีละบรรทัด)</label>
                <textarea className="form-textarea" rows={6} value={form.steps} onChange={(e) => setForm({ ...form, steps: e.target.value })} placeholder={'ตรวจสอบสาย HDMI\nกดปุ่ม Source\nปิดจอค้าง 10 วิ'} />
              </div>
              <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                <label style={{ display: 'flex', alignItems: 'center', gap: 6, fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>
                  <input type="checkbox" checked={form.is_published} onChange={(e) => setForm({ ...form, is_published: e.target.checked })} /> เผยแพร่
                </label>
                <div style={{ flex: 1 }} />
                <button type="button" className="btn btn-ghost" onClick={() => setShowForm(false)}>ยกเลิก</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'กำลังบันทึก...' : (editing ? 'บันทึก' : 'เพิ่ม')}</button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
