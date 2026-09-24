import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import '../styles/chatbot-studio.css';

type Knowledge = { id: number; question: string; answer: string; aliases: string[]; is_published: boolean; updated_at: string };
type Prompt = { task: string; guidance: string; enabled: boolean; source: string };
type Rating = { id: number; target: 'bot' | 'staff'; score: number; ticket_id: string | null; created_at: string };
type Ratings = { days: number; summary: Record<'bot' | 'staff', { count: number; average: number }>; recent: Rating[] };
type Tab = 'knowledge' | 'prompts' | 'ratings';

const PROMPT_LABELS: Record<string, string> = {
  global_style: 'น้ำเสียงและแนวทางร่วม',
  intent: 'เข้าใจเจตนาลูกค้า', field_extraction: 'จับข้อมูลจากข้อความ', kb_match: 'จับคู่ฐานความรู้',
  kb_explanation: 'อธิบายวิธีแก้', orchestration: 'วางลำดับบทสนทนา',
  repair_reply: 'ตอบเรื่องแจ้งซ่อม', slot_question: 'ถามข้อมูลที่ขาด', line_reply: 'รูปแบบคำตอบ LINE',
};
const EMPTY = { question: '', answer: '', aliases: '', is_published: false };

export default function ChatbotStudioPage({ onBack, onNavigate }: { onBack: () => void; onNavigate: (menu: string) => void }) {
  const [tab, setTab] = useState<Tab>('knowledge');
  const [knowledge, setKnowledge] = useState<Knowledge[]>([]);
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [ratings, setRatings] = useState<Ratings | null>(null);
  const [days, setDays] = useState(30);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [form, setForm] = useState(EMPTY);
  const [selectedTask, setSelectedTask] = useState('global_style');
  const [guidance, setGuidance] = useState('');
  const [enabled, setEnabled] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');

  const refresh = async () => {
    setError('');
    try {
      const [k, p, r] = await Promise.all([api.listChatbotKnowledge(), api.listChatbotPrompts(), api.getLineRatings(days)]);
      setKnowledge(k); setPrompts(p); setRatings(r);
    } catch (e: any) { setError(e.message || 'โหลดข้อมูลไม่สำเร็จ'); }
  };
  useEffect(() => { void refresh(); }, [days]);
  useEffect(() => {
    const prompt = prompts.find((p) => p.task === selectedTask);
    setGuidance(prompt?.guidance || ''); setEnabled(Boolean(prompt?.enabled));
  }, [prompts, selectedTask]);

  const saveKnowledge = async (e: React.FormEvent) => {
    e.preventDefault(); setError(''); setNotice(''); setBusy(true);
    try {
      const payload = { question: form.question.trim(), answer: form.answer.trim(),
        aliases: form.aliases.split('\n').map((s) => s.trim()).filter(Boolean), is_published: form.is_published };
      if (editingId != null) await api.updateChatbotKnowledge(editingId, payload);
      else await api.createChatbotKnowledge(payload);
      setEditingId(null); setForm(EMPTY); setNotice('บันทึกคำตอบลงฐานข้อมูลแล้ว');
      setKnowledge(await api.listChatbotKnowledge());
    } catch (err: any) { setError(err.message || 'บันทึกไม่สำเร็จ'); }
    finally { setBusy(false); }
  };

  const savePrompt = async (e: React.FormEvent) => {
    e.preventDefault(); setError(''); setNotice(''); setBusy(true);
    try {
      const updated = await api.updateChatbotPrompt(selectedTask, { guidance, enabled });
      setPrompts((old) => old.map((p) => p.task === selectedTask ? updated : p));
      setNotice('บันทึกคำแนะนำแล้ว — คำถามใหม่จะใช้ค่าจากฐานข้อมูลทันที');
    } catch (err: any) { setError(err.message || 'บันทึกไม่สำเร็จ'); }
    finally { setBusy(false); }
  };

  return <div className="page-content chatbot-studio">
    <div className="top-bar"><div className="top-bar-title-group">
      <button className="btn btn-ghost btn-icon" onClick={onBack} aria-label="กลับแดชบอร์ด">←</button>
      <div><h1 className="top-bar-title">จัดการแชตบอตและ LINE OA</h1><span className="top-bar-subtitle">คำตอบที่ตรวจแล้ว · คำแนะนำ AI · ผลประเมิน</span></div>
    </div></div>
    {error && <div className="alert alert-error" role="alert">{error}</div>}
    {notice && <div className="alert alert-success" role="status">{notice}</div>}
    <div className="studio-intro panel-card">
      <div><strong>เพิ่มข้อมูลโดยไม่ต้องแก้โค้ด</strong><p>คำถาม–คำตอบที่เผยแพร่จะตอบใน LINE เมื่อข้อความตรงกัน ส่วนบทความแก้ปัญหาอุปกรณ์อยู่ในฐานความรู้เดิม อุปกรณ์ที่ยังไม่มีให้เจ้าหน้าที่ตรวจข้อมูลโรงเรียนและเพิ่มจากทะเบียนอุปกรณ์ก่อน บอตจะไม่ลงทะเบียนเครื่องให้เอง</p></div>
      <div className="studio-intro-actions"><button className="btn btn-secondary" onClick={() => onNavigate('kb')}>จัดการฐานความรู้</button><button className="btn btn-secondary" onClick={() => onNavigate('devices')}>+ เพิ่มอุปกรณ์ที่ยังไม่มี</button></div>
    </div>
    <div className="studio-tabs" role="tablist" aria-label="หมวดการจัดการแชตบอต">
      {([['knowledge', 'คำถาม–คำตอบ'], ['prompts', 'คำแนะนำ AI'], ['ratings', 'ผลประเมิน']] as const).map(([key, label]) =>
        <button key={key} role="tab" aria-selected={tab === key} className={`btn ${tab === key ? 'btn-primary' : 'btn-secondary'}`} onClick={() => { setTab(key); setError(''); setNotice(''); }}>{label}</button>)}
    </div>

    {tab === 'knowledge' && <div className="studio-columns">
      <section className="panel-card"><h2>{editingId == null ? 'เพิ่มคำตอบใหม่' : 'แก้ไขคำตอบ'}</h2>
        <p className="studio-help">เริ่มเป็นฉบับร่างก่อนเผยแพร่ คำถามทางเลือกให้พิมพ์บรรทัดละหนึ่งข้อ ระบบตอบเฉพาะข้อความที่ตรงกัน ไม่ใช้แทนข้อมูลราคา ประกัน หรือสถานะงานซ่อม</p>
        <form onSubmit={saveKnowledge} className="studio-form">
          <label>คำถามหลัก<input className="form-input" required minLength={3} maxLength={500} value={form.question} onChange={(e) => setForm({ ...form, question: e.target.value })} placeholder="เช่น ติดต่อฝ่ายบริการเวลาใด" /></label>
          <label>คำถามทางเลือก<textarea className="form-input" rows={3} value={form.aliases} onChange={(e) => setForm({ ...form, aliases: e.target.value })} placeholder="พิมพ์บรรทัดละหนึ่งรูปแบบ" /></label>
          <label>คำตอบที่ตรวจสอบแล้ว<textarea className="form-input" required minLength={3} maxLength={3000} rows={6} value={form.answer} onChange={(e) => setForm({ ...form, answer: e.target.value })} /></label>
          <label className="studio-check"><input type="checkbox" checked={form.is_published} onChange={(e) => setForm({ ...form, is_published: e.target.checked })} /> เผยแพร่ให้ LINE ตอบได้</label>
          <div className="studio-actions"><button className="btn btn-primary" disabled={busy}>{busy ? 'กำลังบันทึก...' : 'บันทึกลงฐานข้อมูล'}</button>{editingId != null && <button type="button" className="btn btn-ghost" onClick={() => { setEditingId(null); setForm(EMPTY); }}>ยกเลิกแก้ไข</button>}</div>
        </form>
      </section>
      <section className="panel-card"><h2>คำตอบที่มีอยู่ ({knowledge.length})</h2>
        {knowledge.length === 0 ? <p className="studio-help">ยังไม่มีคำตอบที่เพิ่มเอง</p> : <div className="studio-list">{knowledge.map((item) =>
          <article key={item.id} className="studio-item"><div><strong>{item.question}</strong><span className={`studio-status ${item.is_published ? 'live' : ''}`}>{item.is_published ? 'เผยแพร่' : 'ฉบับร่าง'}</span></div>
            <p>{item.answer}</p><small>คำถามทางเลือก {item.aliases.length} รายการ</small>
            <button className="btn btn-ghost" onClick={() => { setEditingId(item.id); setForm({ question: item.question, answer: item.answer, aliases: item.aliases.join('\n'), is_published: item.is_published }); }}>แก้ไข</button>
          </article>)}</div>}
      </section>
    </div>}

    {tab === 'prompts' && <section className="panel-card studio-prompt"><h2>คำแนะนำเพิ่มเติมสำหรับ AI</h2>
      <p className="studio-help">เลือกงานที่ต้องการปรับ คำแนะนำนี้ใช้ทันทีหลังบันทึกโดยไม่ต้อง deploy ใหม่ แต่ไม่สามารถเปลี่ยนกฎความปลอดภัยหรือข้อมูลจริงจากฐานข้อมูลได้</p>
      <form onSubmit={savePrompt} className="studio-form">
        <label>ประเภทงาน<select className="form-select" value={selectedTask} onChange={(e) => setSelectedTask(e.target.value)}>{prompts.map((p) => <option key={p.task} value={p.task}>{PROMPT_LABELS[p.task] || p.task}</option>)}</select></label>
        <label>คำแนะนำเพิ่มเติม<textarea className="form-input" rows={10} maxLength={2000} value={guidance} onChange={(e) => setGuidance(e.target.value)} placeholder="เช่น ตอบอย่างกระชับ ใช้ภาษาไทยสุภาพ และถามทีละประเด็น" /></label>
        <div className="studio-help">{guidance.length}/2000 ตัวอักษร · ค่าเดิมจาก {prompts.find((p) => p.task === selectedTask)?.source === 'database' ? 'ฐานข้อมูล' : 'ไฟล์เริ่มต้น'}</div>
        <label className="studio-check"><input type="checkbox" checked={enabled} onChange={(e) => setEnabled(e.target.checked)} /> เปิดใช้คำแนะนำนี้</label>
        <button className="btn btn-primary" disabled={busy || prompts.length === 0}>{busy ? 'กำลังบันทึก...' : 'บันทึกคำแนะนำ'}</button>
      </form>
    </section>}

    {tab === 'ratings' && <section className="panel-card"><div className="studio-rating-head"><div><h2>ผลประเมินจาก LINE</h2><p className="studio-help">แยกคะแนนแชตบอตกับงานเจ้าหน้าที่ ข้อมูลนี้เปิดเฉพาะ superadmin</p></div><label>ช่วงเวลา <select className="form-select" value={days} onChange={(e) => setDays(Number(e.target.value))}><option value={7}>7 วัน</option><option value={30}>30 วัน</option><option value={90}>90 วัน</option><option value={365}>365 วัน</option></select></label></div>
      <div className="studio-rating-cards">{(['bot', 'staff'] as const).map((target) => <div className="studio-rating-card" key={target}><span>{target === 'bot' ? 'แชตบอต' : 'เจ้าหน้าที่'}</span><strong>{ratings?.summary[target]?.count ? `${ratings.summary[target].average}/5` : '—'}</strong><small>{ratings?.summary[target]?.count || 0} รายการ</small></div>)}</div>
      <h3>รายการล่าสุด</h3>{!ratings?.recent.length ? <p className="studio-help">ยังไม่มีคะแนนในช่วงนี้</p> : <div className="studio-table-wrap"><table className="data-table"><thead><tr><th>วันที่</th><th>ประเมิน</th><th>คะแนน</th><th>ใบงาน</th></tr></thead><tbody>{ratings.recent.map((r) => <tr key={r.id}><td>{new Date(r.created_at).toLocaleString('th-TH')}</td><td>{r.target === 'bot' ? 'แชตบอต' : 'เจ้าหน้าที่'}</td><td>{r.score}/5</td><td>{r.ticket_id || '—'}</td></tr>)}</tbody></table></div>}
    </section>}
  </div>;
}
