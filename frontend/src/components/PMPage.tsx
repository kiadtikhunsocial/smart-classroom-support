import React, { useState, useEffect } from 'react';
import { api } from '../api/client';

const STATUS_LABELS_PM: Record<string, string> = {
  pending: 'รอดำเนินการ',
  done: 'ทำแล้ว',
  skipped: 'ข้าม',
  overdue: 'เกินกำหนด',
};

export default function PMPage({ onBack }: { onBack: () => void }) {
  const [tasks, setTasks] = useState<any[]>([]);
  const [plans, setPlans] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [toast, setToast] = useState<string | null>(null);
  const [statusFilter, setStatusFilter] = useState('');
  const [view, setView] = useState<'tasks' | 'plans'>('tasks');
  const [showPlanForm, setShowPlanForm] = useState(false);
  const [saving, setSaving] = useState(false);
  const [editingPlan, setEditingPlan] = useState<any | null>(null);
  const [generating, setGenerating] = useState(false);
  const [planForm, setPlanForm] = useState({ name: '', device_type: '', interval_days: 90, checklist: '' });
  const [submitTask, setSubmitTask] = useState<any | null>(null);
  const [results, setResults] = useState<Record<number, any>>({});
  const [photos, setPhotos] = useState<string[]>([]);
  const [submitting, setSubmitting] = useState(false);

  const showToast = (msg: string) => {
    setToast(msg);
    setTimeout(() => setToast(null), 4000);
  };

  const load = () => {
    setLoading(true);
    Promise.all([api.listPMTasks(statusFilter ? { status: statusFilter } : undefined), api.listPMPlans()])
      .then(([t, p]) => { setTasks(t); setPlans(p); })
      .catch((e) => setError(e.message))
      .finally(() => setLoading(false));
  };

  useEffect(load, [statusFilter]);

  const generate = async () => {
    setGenerating(true);
    setError(null);
    try {
      const r = await api.pmGenerate();
      if (r.generated === 0 && r.skipped_duplicate > 0) {
        showToast('⚠️ งานทั้งหมดถูกสร้างแล้ว (ข้ามซ้ำ ' + r.skipped_duplicate + ' งาน)');
      } else if (r.generated === 0) {
        showToast('ℹ️ ยังไม่มีอุปกรณ์ที่ถึงรอบ PM — เพิ่มอุปกรณ์ก่อน หรือรอรอบถัดไป');
      } else {
        showToast(`✅ สร้างงาน PM ใหม่ ${r.generated} งาน (ข้ามซ้ำ ${r.skipped_duplicate})`);
      }
      load();
    } catch (e: any) {
      setError(e.message);
      showToast('❌ ' + e.message);
    } finally {
      setGenerating(false);
    }
  };

  const savePlan = async (e: React.FormEvent) => {
    e.preventDefault();
    setSaving(true);
    setError(null);
    try {
      const data = {
        name: planForm.name,
        device_type: planForm.device_type || null,
        interval_days: Number(planForm.interval_days) || 90,
        checklist: planForm.checklist.split('\n').map((s) => s.trim()).filter(Boolean).map((item, i) => ({ order: i + 1, item, type: 'boolean' })),
      };
      if (editingPlan) {
        await api.updatePMPlan(editingPlan.id, data);
        showToast('✅ แก้ไขแผนเรียบร้อย');
      } else {
        await api.createPMPlan(data);
        showToast('✅ สร้างแผนบำรุงรักษาเรียบร้อย');
      }
      setShowPlanForm(false);
      setEditingPlan(null);
      setPlanForm({ name: '', device_type: '', interval_days: 90, checklist: '' });
      load();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSaving(false);
    }
  };

  const editPlan = (p: any) => {
    setEditingPlan(p);
    setPlanForm({
      name: p.name,
      device_type: p.device_type || '',
      interval_days: p.interval_days || 90,
      checklist: Array.isArray(p.checklist) ? p.checklist.map((c: any) => c.item).join('\n') : '',
    });
    setShowPlanForm(true);
  };

  const removePlan = async (p: any) => {
    if (!window.confirm(`ลบแผน "${p.name}"? งานที่อ้างอิงแผนนี้จะถูกปลดการเชื่อมโยง`)) return;
    try {
      await api.deletePMPlan(p.id);
      showToast('🗑️ ลบแผนเรียบร้อย');
      if (editingPlan?.id === p.id) { setEditingPlan(null); setShowPlanForm(false); }
      load();
    } catch (err: any) {
      setError(err.message);
    }
  };

  const openSubmit = (t: any) => {
    setSubmitTask(t);
    const init: Record<number, any> = {};
    (t.checklist || []).forEach((c: any) => { init[c.order] = { value: true, note: '' }; });
    setResults(init);
    setPhotos([]);
  };

  const submitTaskResult = async () => {
    if (!submitTask) return;
    setSubmitting(true);
    setError(null);
    try {
      const result = Object.entries(results).map(([order, v]) => ({ order: Number(order), value: v.value, note: v.note || undefined }));
      const r = await api.pmSubmit(submitTask.id, { result, photos });
      setSubmitTask(null);
      if (r.auto_ticket) showToast(`⚠️ พบรายการไม่ผ่าน — สร้าง Ticket อัตโนมัติ: ${r.auto_ticket.ticket_no}`);
      else showToast('✅ บันทึกผล PM เรียบร้อย');
      load();
    } catch (err: any) {
      setError(err.message);
    } finally {
      setSubmitting(false);
    }
  };

  const skipTask = async (t: any) => {
    const reason = window.prompt('เหตุผลที่ข้ามงาน PM นี้:');
    if (!reason) return;
    try {
      await api.pmSkip(t.id, reason);
      showToast('✅ ข้ามงานเรียบร้อย');
      load();
    } catch (err: any) {
      setError(err.message);
    }
  };

  return (
    <div className="page-content">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2"><path d="M19 12H5M12 19l-7-7 7-7"/></svg>
          </button>
          <div>
            <h1 className="top-bar-title">บำรุงรักษาเชิงป้องกัน (PM)</h1>
            <span className="top-bar-subtitle">{view === 'tasks' ? `งาน PM ${tasks.length} รายการ` : `แผนบำรุงรักษา ${plans.length} แผน`}</span>
          </div>
        </div>
        <div className="top-bar-actions">
          <div style={{ display: 'flex', background: 'var(--color-bg)', borderRadius: 'var(--radius-sm)', padding: 3 }}>
            <button
              onClick={() => setView('tasks')}
              style={{
                padding: '6px 14px', borderRadius: 'var(--radius-sm)', border: 'none', cursor: 'pointer',
                background: view === 'tasks' ? 'var(--color-primary)' : 'transparent',
                color: view === 'tasks' ? '#fff' : 'var(--color-text-secondary)', fontSize: '0.82rem',
              }}
            >งาน</button>
            <button
              onClick={() => setView('plans')}
              style={{
                padding: '6px 14px', borderRadius: 'var(--radius-sm)', border: 'none', cursor: 'pointer',
                background: view === 'plans' ? 'var(--color-primary)' : 'transparent',
                color: view === 'plans' ? '#fff' : 'var(--color-text-secondary)', fontSize: '0.82rem',
              }}
            >แผนงาน</button>
          </div>
          {view === 'tasks' && (
            <button className="btn btn-secondary" onClick={generate} disabled={generating}>
              {generating ? 'กำลังสร้าง...' : '⚡ สร้างงานล่วงหน้า'}
            </button>
          )}
          {view === 'plans' && (
            <button className="btn btn-primary" onClick={() => setShowPlanForm(!showPlanForm)}>{showPlanForm ? 'ปิด' : '+ แผนใหม่'}</button>
          )}
        </div>
      </div>

      {/* Toast */}
      {toast && (
        <div style={{
          position: 'fixed', top: 80, right: 20, zIndex: 1000,
          background: 'var(--color-surface)', border: '1px solid var(--color-border)',
          borderRadius: 'var(--radius-md)', padding: '12px 18px', fontSize: '0.85rem',
          boxShadow: '0 4px 20px rgba(0,0,0,0.12)', maxWidth: 340,
          animation: 'slideDown 0.2s ease',
        }}>
          {toast}
        </div>
      )}

      {error && <div style={{ padding: '10px 14px', background: 'var(--color-danger-light)', color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)', fontSize: '0.8rem', marginBottom: 16 }}>{error}</div>}

      {/* มุมมองแผนงาน */}
      {view === 'plans' && (
        <>
          {showPlanForm && (
            <form onSubmit={savePlan} className="panel-card" style={{ padding: 20, marginBottom: 16 }}>
              <h3 style={{ margin: '0 0 14px', fontSize: '1rem' }}>{editingPlan ? '✏️ แก้ไขแผน' : '➕ แผนบำรุงรักษาใหม่'}</h3>
              <div className="form-row">
                <div className="form-group" style={{ flex: 2 }}>
                  <label className="form-label">ชื่อแผน<span className="required">*</span></label>
                  <input className="form-input" value={planForm.name} onChange={(e) => setPlanForm({ ...planForm, name: e.target.value })} placeholder="บำรุงรักษาจอ Interactive รายไตรมาส" />
                </div>
                <div className="form-group">
                  <label className="form-label">ประเภทอุปกรณ์</label>
                  <select className="form-select" value={planForm.device_type} onChange={(e) => setPlanForm({ ...planForm, device_type: e.target.value })}>
                    <option value="">ทุกประเภท</option>
                    {['Interactive Display', 'Computer Desktop', 'Computer AIO', 'Computer Notebook', 'Router', 'Access Point', 'Speaker', 'Camera', 'Projector'].map((t) => <option key={t} value={t}>{t}</option>)}
                  </select>
                </div>
                <div className="form-group">
                  <label className="form-label">รอบ (วัน)</label>
                  <input className="form-input" type="number" value={planForm.interval_days} onChange={(e) => setPlanForm({ ...planForm, interval_days: Number(e.target.value) })} />
                </div>
              </div>
              <div className="form-group">
                <label className="form-label">รายการตรวจ (ทีละบรรทัด)</label>
                <textarea className="form-textarea" rows={4} value={planForm.checklist} onChange={(e) => setPlanForm({ ...planForm, checklist: e.target.value })} placeholder={'ทำความสะอาดหน้าจอ\nทดสอบระบบสัมผัส\nตรวจสอบสายสัญญาณ'} />
              </div>
              <div style={{ display: 'flex', gap: 8, justifyContent: 'flex-end' }}>
                <button type="button" className="btn btn-ghost" onClick={() => setShowPlanForm(false)}>ยกเลิก</button>
                <button type="submit" className="btn btn-primary" disabled={saving}>{saving ? 'กำลังบันทึก...' : 'บันทึกแผน'}</button>
              </div>
            </form>
          )}

          {loading ? (
            <div style={{ textAlign: 'center', padding: 40 }}><div className="spinner" style={{ width: 30, height: 30, margin: '0 auto 12px' }} /></div>
          ) : plans.length === 0 ? (
            <div className="panel-card empty-text" style={{ padding: 40, textAlign: 'center' }}>ยังไม่มีแผน — กด "+ แผนใหม่" เพื่อสร้าง</div>
          ) : (
            <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(320px, 1fr))', gap: 12 }}>
              {plans.map((p) => (
                <div key={p.id} className="panel-card" style={{ padding: 18 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start' }}>
                    <div style={{ fontWeight: 600, fontSize: '0.92rem' }}>{p.name}</div>
                    {p.device_type && <span className="badge badge-in_progress" style={{ flexShrink: 0, fontSize: '0.68rem' }}>{p.device_type}</span>}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)', marginTop: 4 }}>
                    รอบทุก {p.interval_days} วัน · {Array.isArray(p.checklist) ? p.checklist.length : 0} รายการตรวจ
                  </div>
                  {Array.isArray(p.checklist) && p.checklist.length > 0 && (
                    <div style={{ marginTop: 10, fontSize: '0.78rem', color: 'var(--color-text-secondary)', lineHeight: 1.7 }}>
                      {p.checklist.map((c: any, i: number) => (
                        <div key={i}>☐ {c.item}</div>
                      ))}
                    </div>
                  )}
                  <div style={{ display: 'flex', gap: 8, marginTop: 14, borderTop: '1px solid var(--color-border)', paddingTop: 12 }}>
                    <button className="btn btn-secondary" style={{ fontSize: '0.75rem', padding: '5px 12px' }} onClick={() => editPlan(p)}>✏️ แก้ไข</button>
                    <button className="btn btn-ghost" style={{ fontSize: '0.75rem', padding: '5px 12px', color: 'var(--color-danger)' }} onClick={() => removePlan(p)}>🗑️ ลบ</button>
                    <div style={{ flex: 1 }} />
                    {p.is_active ? (
                      <span className="badge badge-resolved" style={{ fontSize: '0.68rem' }}>ใช้งาน</span>
                    ) : (
                      <span className="badge badge-closed" style={{ fontSize: '0.68rem' }}>ปิด</span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          )}
        </>
      )}

      {/* มุมมองงาน */}
      {view === 'tasks' && (
        loading ? (
          <div style={{ textAlign: 'center', padding: 40 }}><div className="spinner" style={{ width: 30, height: 30, margin: '0 auto 12px' }} /></div>
        ) : tasks.length === 0 ? (
          <div className="panel-card" style={{ padding: 40, textAlign: 'center' }}>
            <div style={{ fontSize: '2rem', marginBottom: 8 }}>🗓️</div>
            <div className="empty-text">ยังไม่มีงาน PM</div>
            <p style={{ fontSize: '0.82rem', color: 'var(--color-text-tertiary)', marginTop: 8 }}>
              กด "⚡ สร้างงานล่วงหน้า" — ระบบจะสร้างงานจากแผนให้อุปกรณ์ที่ถึงรอบ
              <br />ถ้ายังไม่มีแผน ให้สลับไปแท็บ "แผนงาน" แล้วกด "+ แผนใหม่"
            </p>
            <button className="btn btn-primary" onClick={generate} disabled={generating} style={{ marginTop: 12 }}>
              {generating ? 'กำลังสร้าง...' : '⚡ สร้างงานล่วงหน้า'}
            </button>
          </div>
        ) : (
          <div className="panel-card">
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>เลขงาน</th><th>อุปกรณ์</th><th>แผน</th><th>กำหนด</th><th>สถานะ</th><th>การจัดการ</th>
                  </tr>
                </thead>
                <tbody>
                  {tasks.map((t) => (
                    <tr key={t.id}>
                      <td style={{ fontWeight: 600 }}>{t.task_no}</td>
                      <td>
                        <div>{t.device_id}</div>
                        {t.device_type && <div style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)' }}>{t.device_type}</div>}
                      </td>
                      <td style={{ fontSize: '0.85rem' }}>{t.plan_name || '-'}</td>
                      <td style={{ fontSize: '0.85rem' }}>{t.due_date ? new Date(t.due_date).toLocaleDateString('th-TH') : '-'}</td>
                      <td>
                        <span className={`badge badge-${t.status === 'done' ? 'resolved' : t.status === 'overdue' ? 'cancelled' : t.status === 'skipped' ? 'closed' : 'pending'}`}>
                          {STATUS_LABELS_PM[t.status] || t.status}
                        </span>
                        {t.ticket_id && <div style={{ fontSize: '0.72rem', color: 'var(--color-primary)', marginTop: 2 }}>→ {t.ticket_id}</div>}
                      </td>
                      <td>
                        {t.status === 'pending' && (
                          <div style={{ display: 'flex', gap: 6 }}>
                            <button className="btn btn-primary" style={{ fontSize: '0.75rem', padding: '4px 10px' }} onClick={() => openSubmit(t)}>บันทึกผล</button>
                            <button className="btn btn-ghost" style={{ fontSize: '0.75rem', padding: '4px 10px' }} onClick={() => skipTask(t)}>ข้าม</button>
                          </div>
                        )}
                        {t.status === 'done' && Array.isArray(t.result) && t.result.length > 0 && (
                          <div style={{ fontSize: '0.7rem', color: 'var(--color-text-tertiary)' }}>
                            {t.result.filter((r: any) => r.value === false).length === 0 ? 'ผ่านทั้งหมด ✓' : `${t.result.filter((r: any) => r.value === false).length} รายการไม่ผ่าน`}
                          </div>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        )
      )}

      {/* Modal บันทึกผล */}
      {submitTask && (
        <div className="panel-overlay" onClick={() => setSubmitTask(null)}>
          <div className="repair-panel" onClick={(e) => e.stopPropagation()}>
            <div className="repair-panel-header">
              <h3 className="repair-panel-title">บันทึกผล PM — {submitTask.task_no}</h3>
              <button className="repair-panel-close" onClick={() => setSubmitTask(null)}>✕</button>
            </div>
            <div className="repair-panel-body">
              <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)', marginBottom: 12 }}>
                {submitTask.device_id} · {submitTask.plan_name || ''}
              </div>
              {(submitTask.checklist || []).map((c: any) => (
                <div key={c.order} className="form-group">
                  <label className="form-label">{c.order}. {c.item}</label>
                  <div style={{ display: 'flex', gap: 8, alignItems: 'center' }}>
                    <select
                      className="form-select"
                      style={{ width: 120 }}
                      value={String(results[c.order]?.value ?? true)}
                      onChange={(e) => setResults((prev) => ({ ...prev, [c.order]: { ...prev[c.order], value: e.target.value === 'true' } }))}
                    >
                      <option value="true">✅ ผ่าน</option>
                      <option value="false">❌ ไม่ผ่าน</option>
                    </select>
                    {c.type === 'number' && (
                      <input className="form-input" type="number" style={{ width: 90 }} placeholder="ค่า"
                        value={results[c.order]?.value ?? ''}
                        onChange={(e) => setResults((prev) => ({ ...prev, [c.order]: { ...prev[c.order], value: Number(e.target.value) } }))}
                      />
                    )}
                    <input className="form-input" style={{ flex: 1 }} placeholder="หมายเหตุ (ถ้าไม่ผ่าน)"
                      value={results[c.order]?.note ?? ''}
                      onChange={(e) => setResults((prev) => ({ ...prev, [c.order]: { ...prev[c.order], note: e.target.value } }))}
                    />
                  </div>
                </div>
              ))}
              <div className="form-group">
                <label className="form-label">รูปถ่าย (ไม่บังคับ)</label>
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  className="form-input"
                  onChange={async (e) => {
                    const files = e.target.files;
                    if (!files) return;
                    try {
                      for (const f of Array.from(files).slice(0, 3)) {
                        const r = await api.upload(f);
                        setPhotos((prev) => [...prev, r.url]);
                      }
                    } catch (err: any) { setError(err.message); }
                  }}
                />
                {photos.length > 0 && (
                  <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                    {photos.map((u, i) => <img key={i} src={u} style={{ width: 48, height: 48, objectFit: 'cover', borderRadius: 6 }} alt="" />)}
                  </div>
                )}
              </div>
              <button className="btn btn-primary btn-full" onClick={submitTaskResult} disabled={submitting}>
                {submitting ? 'กำลังบันทึก...' : 'บันทึกผลการบำรุงรักษา'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}