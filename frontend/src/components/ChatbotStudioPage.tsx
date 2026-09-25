import React, { useEffect, useState } from 'react';
import { api } from '../api/client';
import RatingsResults, { type Ratings } from './RatingsResults';
import '../styles/chatbot-studio.css';

type Knowledge = { id: number; question: string; answer: string; aliases: string[]; source_label: string | null; source_url: string | null; is_published: boolean; updated_at: string };
type Prompt = { task: string; guidance: string; enabled: boolean; source: string };
type Runtime = { provider: string; model: string; base_key_configured: boolean; tuned_endpoint_configured: boolean; classifier_enabled: boolean; orchestration_enabled: boolean; natural_replies_enabled: boolean };
type Preview = { route: string; intent: string; reply: string | null; note: string };
type Tab = 'knowledge' | 'prompts' | 'test' | 'guide' | 'ratings';

const PROMPT_LABELS: Record<string, string> = {
  global_style: 'น้ำเสียงและแนวทางร่วม',
  intent: 'เข้าใจเจตนาลูกค้า', field_extraction: 'จับข้อมูลจากข้อความ', kb_match: 'จับคู่ฐานความรู้',
  kb_explanation: 'อธิบายวิธีแก้', orchestration: 'วางลำดับบทสนทนา',
  repair_reply: 'ตอบเรื่องแจ้งซ่อม', slot_question: 'ถามข้อมูลที่ขาด', line_reply: 'รูปแบบคำตอบ LINE',
};
const EMPTY = { question: '', answer: '', aliases: '', source_label: '', source_url: '', is_published: false };

export default function ChatbotStudioPage({ onBack, onNavigate, ratingsOnly = false }: { onBack: () => void; onNavigate: (menu: string) => void; ratingsOnly?: boolean }) {
  const [tab, setTab] = useState<Tab>(ratingsOnly ? 'ratings' : 'knowledge');
  const [knowledge, setKnowledge] = useState<Knowledge[]>([]);
  const [prompts, setPrompts] = useState<Prompt[]>([]);
  const [ratings, setRatings] = useState<Ratings | null>(null);
  const [runtime, setRuntime] = useState<Runtime | null>(null);
  const [testMessage, setTestMessage] = useState('');
  const [preview, setPreview] = useState<Preview | null>(null);
  const [canViewRatings, setCanViewRatings] = useState(false);
  const [accessLoaded, setAccessLoaded] = useState(false);
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
    setRatings(null);
    try {
      if (ratingsOnly) {
        const access = await api.getChatbotManageAccess();
        setCanViewRatings(access.can_view_ratings);
        setRatings(access.can_view_ratings ? await api.getLineRatings(days) : null);
        return;
      }
      const [k, p, access, status] = await Promise.all([api.listChatbotKnowledge(), api.listChatbotPrompts(), api.getChatbotManageAccess(), api.getChatbotRuntime()]);
      const r = access.can_view_ratings ? await api.getLineRatings(days) : null;
      setKnowledge(k); setPrompts(p); setRatings(r); setCanViewRatings(access.can_view_ratings); setRuntime(status);
    } catch (e: any) { setError(e.message || 'โหลดข้อมูลไม่สำเร็จ'); }
    finally { setAccessLoaded(true); }
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
        source_label: form.source_label.trim() || null, source_url: form.source_url.trim() || null,
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

  const runPreview = async (e: React.FormEvent) => {
    e.preventDefault(); setBusy(true); setError(''); setPreview(null);
    try { setPreview(await api.previewChatbot(testMessage.trim())); }
    catch (err: any) { setError(err.message || 'ทดลองไม่สำเร็จ'); }
    finally { setBusy(false); }
  };

  return <div className="page-content chatbot-studio">
    <div className="top-bar"><div className="top-bar-title-group">
      <button className="btn btn-ghost btn-icon" onClick={onBack} aria-label="กลับแดชบอร์ด">←</button>
      <div><h1 className="top-bar-title">{ratingsOnly ? 'ผลประเมินลูกค้า' : 'จัดการแชตบอตและ LINE OA'}</h1><span className="top-bar-subtitle">{ratingsOnly ? 'คะแนนแชตบอตและเจ้าหน้าที่หลังจบงาน' : 'คำตอบที่ตรวจแล้ว · คำแนะนำ AI · ผลประเมิน'}</span></div>
    </div></div>
    {error && <div className="alert alert-error" role="alert">{error}</div>}
    {notice && <div className="alert alert-success" role="status">{notice}</div>}
    {!ratingsOnly && <div className="studio-intro panel-card">
      <div><strong>เพิ่มข้อมูลโดยไม่ต้องแก้โค้ด</strong><p>คำถาม–คำตอบที่เผยแพร่จะตอบใน LINE เมื่อข้อความตรงกัน ส่วนบทความแก้ปัญหาอุปกรณ์อยู่ในฐานความรู้เดิม อุปกรณ์ที่ยังไม่มีให้เจ้าหน้าที่ตรวจข้อมูลโรงเรียนและเพิ่มจากทะเบียนอุปกรณ์ก่อน บอตจะไม่ลงทะเบียนเครื่องให้เอง</p><small>AI: {runtime?.provider || 'กำลังตรวจ'} {runtime?.model || ''} · คีย์ {runtime?.base_key_configured ? 'พร้อม' : 'ยังไม่ตั้ง'} · จำแนกเจตนา {runtime?.classifier_enabled ? 'เปิด' : 'ปิด'} · วางบทสนทนา {runtime?.orchestration_enabled ? 'เปิด' : 'ปิด'}</small></div>
      <div className="studio-intro-actions"><button className="btn btn-secondary" onClick={() => onNavigate('kb')}>จัดการฐานความรู้</button><button className="btn btn-secondary" onClick={() => onNavigate('devices')}>+ เพิ่มอุปกรณ์ที่ยังไม่มี</button></div>
    </div>}
    {!ratingsOnly && <div className="studio-tabs" role="tablist" aria-label="หมวดการจัดการแชตบอต">
      {([['knowledge', 'คำถาม–คำตอบ'], ['prompts', 'คำแนะนำ AI'], ['test', 'ทดลองถาม'], ['guide', 'คู่มือ'], ...(canViewRatings ? [['ratings', 'ผลประเมิน'] as const] : [])] as const).map(([key, label]) =>
        <button key={key} role="tab" aria-selected={tab === key} className={`btn ${tab === key ? 'btn-primary' : 'btn-secondary'}`} onClick={() => { setTab(key); setError(''); setNotice(''); }}>{label}</button>)}
    </div>}
    {ratingsOnly && accessLoaded && !canViewRatings && !error && <div className="panel-card" style={{ padding: 22 }}>บัญชีนี้ไม่มีสิทธิ์ดูผลประเมิน</div>}

    {tab === 'knowledge' && <div className="studio-columns">
      <section className="panel-card"><h2>{editingId == null ? 'เพิ่มคำตอบใหม่' : 'แก้ไขคำตอบ'}</h2>
        <p className="studio-help">เริ่มเป็นฉบับร่างก่อนเผยแพร่ คำถามทางเลือกให้พิมพ์บรรทัดละหนึ่งข้อ ระบบตอบเฉพาะข้อความที่ตรงกัน ไม่ใช้แทนข้อมูลราคา ประกัน หรือสถานะงานซ่อม</p>
        <form onSubmit={saveKnowledge} className="studio-form">
          <label>คำถามหลัก<input className="form-input" required minLength={3} maxLength={500} value={form.question} onChange={(e) => setForm({ ...form, question: e.target.value })} placeholder="เช่น ติดต่อฝ่ายบริการเวลาใด" /></label>
          <label>คำถามทางเลือก<textarea className="form-input" rows={3} value={form.aliases} onChange={(e) => setForm({ ...form, aliases: e.target.value })} placeholder="พิมพ์บรรทัดละหนึ่งรูปแบบ" /></label>
          <label>คำตอบที่ตรวจสอบแล้ว<textarea className="form-input" required minLength={3} maxLength={3000} rows={6} value={form.answer} onChange={(e) => setForm({ ...form, answer: e.target.value })} /></label>
          <label>แหล่งข้อมูล / ผู้ยืนยัน<input className="form-input" maxLength={160} value={form.source_label} onChange={(e) => setForm({ ...form, source_label: e.target.value })} placeholder="เช่น คู่มือผู้ผลิต รุ่น X ฉบับ 2026 หรือฝ่ายบริการ" /></label>
          <label>ลิงก์อ้างอิง (ถ้ามี)<input className="form-input" type="url" maxLength={500} value={form.source_url} onChange={(e) => setForm({ ...form, source_url: e.target.value })} placeholder="https://..." /></label>
          <label className="studio-check"><input type="checkbox" checked={form.is_published} onChange={(e) => setForm({ ...form, is_published: e.target.checked })} /> เผยแพร่ให้ LINE ตอบได้</label>
          <div className="studio-actions"><button className="btn btn-primary" disabled={busy}>{busy ? 'กำลังบันทึก...' : 'บันทึกลงฐานข้อมูล'}</button>{editingId != null && <button type="button" className="btn btn-ghost" onClick={() => { setEditingId(null); setForm(EMPTY); }}>ยกเลิกแก้ไข</button>}</div>
        </form>
      </section>
      <section className="panel-card"><h2>คำตอบที่มีอยู่ ({knowledge.length})</h2>
        {knowledge.length === 0 ? <p className="studio-help">ยังไม่มีคำตอบที่เพิ่มเอง</p> : <div className="studio-list">{knowledge.map((item) =>
          <article key={item.id} className="studio-item"><div><strong>{item.question}</strong><span className={`studio-status ${item.is_published ? 'live' : ''}`}>{item.is_published ? 'เผยแพร่' : 'ฉบับร่าง'}</span></div>
            <p>{item.answer}</p><small>คำถามทางเลือก {item.aliases.length} รายการ · ที่มา: {item.source_label || 'ยังไม่ระบุ'}{item.source_url && <> · <a href={item.source_url} target="_blank" rel="noopener noreferrer">เปิดแหล่งข้อมูล</a></>}</small>
            <button className="btn btn-ghost" onClick={() => { setEditingId(item.id); setForm({ question: item.question, answer: item.answer, aliases: item.aliases.join('\n'), source_label: item.source_label || '', source_url: item.source_url || '', is_published: item.is_published }); }}>แก้ไข</button>
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

    {tab === 'test' && <section className="panel-card studio-prompt"><h2>ทดลองถามก่อนเผยแพร่</h2>
      <p className="studio-help">พรีวิวนี้ตรวจชั้นกฎ คำตอบที่เผยแพร่ และประกันตามรหัสจริงเท่านั้น ไม่ส่งข้อความไป LINE ไม่สร้างใบงาน ไม่บันทึกบทสนทนาลูกค้า และไม่เรียก Gemini คำตอบจริงอาจต่างเมื่อมีบริบทแชต</p>
      <div className="studio-examples">{['ช่วยด้วย', 'จอเสียอยากซื้อใหม่', 'รอเจ้าหน้าที่ติดต่อกลับอยู่', 'ตรวจประกันได้ไหม'].map((example) => <button type="button" className="btn btn-secondary" key={example} onClick={() => { setTestMessage(example); setPreview(null); }}>{example}</button>)}</div>
      <form onSubmit={runPreview} className="studio-form"><label>ข้อความตัวอย่าง<input className="form-input" required maxLength={1000} value={testMessage} onChange={(e) => setTestMessage(e.target.value)} placeholder="เช่น จอเสียอยากซื้อใหม่ หรือ ประกัน SCH01-..." /></label><button className="btn btn-primary" disabled={busy || !testMessage.trim()}>{busy ? 'กำลังตรวจ...' : 'ตรวจเส้นทางคำตอบ'}</button></form>
      {preview && <div className="studio-preview" role="status"><strong>เส้นทาง: {preview.route} · เจตนา: {preview.intent}</strong><p>{preview.reply || 'ข้อความนี้จะเข้าสู่บทสนทนาจริง จึงไม่มีคำตอบจำลองในพรีวิว'}</p><small>{preview.note}</small></div>}
    </section>}

    {tab === 'guide' && <section className="panel-card studio-guide"><h2>คู่มือปรับปรุงบอตอย่างปลอดภัย</h2>
      <ol><li><strong>ข้อมูลทั่วไป:</strong> เพิ่มคำถาม คำตอบ และคำถามทางเลือกในแท็บแรก ระบุแหล่งข้อมูล เก็บเป็นฉบับร่างก่อน เมื่อทดสอบแล้วค่อยเผยแพร่ ข้อความตรงกันจะใช้คำตอบใหม่ทันที</li>
        <li><strong>วิธีแก้ปัญหา:</strong> เข้า “ฐานความรู้” เพิ่มอาการและขั้นตอนที่ตรวจแล้ว แล้วเผยแพร่ บอตใช้บทความที่เผยแพร่จากฐานข้อมูล ไม่ควรใส่วิธีที่เสี่ยงอันตราย</li>
        <li><strong>ประกัน/สินค้า:</strong> เข้า “ทะเบียนอุปกรณ์” เพิ่มรหัสอุปกรณ์ Serial วันสิ้นสุดประกัน และ “รายละเอียดประกันที่ให้บอตตอบลูกค้า” หรืออัปโหลด CSV จาก Google Sheets แล้วตรวจตัวอย่างก่อนนำเข้า ลูกค้าต้องแจ้งรหัสหรือ Serial ก่อน บอตอ่านข้อมูลนี้จากทะเบียนทันที ไม่ควรใส่ข้อมูลประกันลงคำตอบทั่วไป</li>
        <li><strong>น้ำเสียง/ความกำกวม:</strong> ใช้แท็บ “คำแนะนำ AI” เพิ่มคำแนะนำสั้น ๆ พร้อมตัวอย่างคำถามกลับหนึ่งข้อ แล้วเปิดใช้ ค่านี้มีผลต่อคำขอ AI ใหม่ทันที เฉพาะขั้นตอนที่เปิด Gemini อยู่ ไม่ใช่การฝึกน้ำหนักโมเดล</li>
        <li><strong>วัดผลซ้ำ:</strong> ทดลองหลายรูปแบบในแท็บ “ทดลองถาม” ทดสอบ LINE จริงด้วยบัญชีทดสอบ ดูผลประเมินและบทสนทนาที่ตอบไม่ตรง แล้วแก้ข้อมูลหรือคำแนะนำทีละเรื่อง</li></ol>
      <p className="studio-help">ระบบไม่อ่าน URL หรือ Google Sheets อัตโนมัติ: ต้องตรวจความถูกต้องและนำเข้าข้อมูลเองก่อนเผยแพร่ หลีกเลี่ยงข้อมูลส่วนบุคคล รหัสผ่าน ราคา และสิทธิ์เคลมที่ยังไม่ยืนยัน</p>
    </section>}

    {tab === 'ratings' && canViewRatings && !error && <RatingsResults ratings={ratings} days={days} onDaysChange={setDays} onRefresh={() => void refresh()} />}
  </div>;
}
