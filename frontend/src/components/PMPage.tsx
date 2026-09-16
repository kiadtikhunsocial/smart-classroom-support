import React, { useState, useEffect, useCallback } from 'react';
import { api } from '../api/client';

// ─── สถานะงาน PM (ตรงกับ backend: pending / overdue / done / skipped) ──────
const TASK_STATUS_LABELS: Record<string, string> = {
  pending: 'รอดำเนินการ',
  overdue: 'เลยกำหนด',
  done: 'ตรวจเสร็จแล้ว',
  skipped: 'ข้ามรอบนี้',
};

// map สถานะ PM → คลาส badge ที่มีอยู่จริงใน global.css
const TASK_STATUS_BADGE: Record<string, string> = {
  pending: 'badge-pending',
  overdue: 'badge-new',
  done: 'badge-resolved',
  skipped: 'badge-closed',
};

const PLAN_MANAGE_ROLES = ['owner', 'super_admin', 'admin'];

// ─── PM Rule Engine (§38) — สามกฎตาม Blueprint ─────────────────────────────
const RULE_LABELS: Record<string, string> = {
  REPEATED_FAILURE: 'ซ่อมซ้ำบ่อย (≥ 3 ครั้ง / 90 วัน)',
  WARRANTY_EXPIRING: 'ประกันใกล้หมด (ภายใน 30 วัน)',
  REPLACEMENT_CANDIDATE: 'เสนอพิจารณาเปลี่ยนเครื่อง',
};

const FLAG_STATUS_LABELS: Record<string, string> = {
  open: 'ยังไม่จัดการ',
  acknowledged: 'รับทราบแล้ว',
  resolved: 'ปิดแล้ว',
};

// ใช้คลาส badge ที่มีอยู่จริงใน global.css
const SEVERITY_BADGE: Record<string, string> = {
  critical: 'badge-new',
  warning: 'badge-pending',
  info: 'badge-closed',
};

type ChecklistResult = { item: string; value: boolean; note: string };

/** checklist ของแผนอาจเก็บเป็น string หรือ object — normalize เป็นข้อความ */
function checklistItemLabel(raw: any, index: number): string {
  if (typeof raw === 'string' && raw.trim()) return raw.trim();
  if (raw && typeof raw === 'object') {
    const label = raw.item ?? raw.name ?? raw.label ?? raw.title;
    if (typeof label === 'string' && label.trim()) return label.trim();
  }
  return `รายการตรวจที่ ${index + 1}`;
}

function fmtDate(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleDateString('th-TH', { dateStyle: 'medium' });
}

function fmtDateTime(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('th-TH', { dateStyle: 'medium', timeStyle: 'short' });
}

function isOverdue(task: any): boolean {
  if (task.status === 'overdue') return true;
  if (task.status !== 'pending' || !task.due_date) return false;
  const due = new Date(task.due_date);
  return !Number.isNaN(due.getTime()) && due.getTime() < Date.now();
}

interface PMPageProps {
  onBack: () => void;
  userRole?: string;
  /** เห็นข้อมูลทุกโรงเรียน → แสดงตัวกรองโรงเรียน */
  isGlobalScope?: boolean;
  /** โรงเรียนของผู้ใช้ (ใช้ล็อกขอบเขตเมื่อไม่ใช่ global) */
  currentOrgId?: number | null;
}

export default function PMPage({ onBack, userRole, isGlobalScope = false, currentOrgId }: PMPageProps) {
  const [tab, setTab] = useState<'tasks' | 'plans' | 'flags'>('tasks');

  const [tasks, setTasks] = useState<any[]>([]);
  const [plans, setPlans] = useState<any[]>([]);
  const [orgs, setOrgs] = useState<any[]>([]);
  const [deviceTypes, setDeviceTypes] = useState<string[]>([]);

  const [statusFilter, setStatusFilter] = useState<string>('');
  const [orgFilter, setOrgFilter] = useState<number | ''>('');
  const [deviceFilter, setDeviceFilter] = useState('');

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [generating, setGenerating] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);

  // งานที่กำลังกรอกผลตรวจ / กำลังขอข้าม
  const [submitTask, setSubmitTask] = useState<any | null>(null);
  const [results, setResults] = useState<ChecklistResult[]>([]);
  const [photos, setPhotos] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [panelError, setPanelError] = useState<string | null>(null);

  const [skipTask, setSkipTask] = useState<any | null>(null);
  const [skipReason, setSkipReason] = useState('');

  // แจ้งเตือนจาก Rule Engine (§38)
  const [flags, setFlags] = useState<any[]>([]);
  const [flagStatusFilter, setFlagStatusFilter] = useState('open');
  const [flagRuleFilter, setFlagRuleFilter] = useState('');
  const [runningRules, setRunningRules] = useState(false);
  const [flagUpdatingId, setFlagUpdatingId] = useState<number | null>(null);

  // ฟอร์มแผน PM
  const [showPlanForm, setShowPlanForm] = useState(false);
  const [planForm, setPlanForm] = useState({
    name: '',
    device_type: '',
    interval_days: 90,
    checklistText: '',
    is_active: true,
  });

  const canManagePlans = PLAN_MANAGE_ROLES.includes(userRole || '');
  const effectiveOrgId = isGlobalScope
    ? (orgFilter === '' ? undefined : orgFilter)
    : (currentOrgId ?? undefined);

  const loadTasks = useCallback(() => {
    setLoading(true);
    setError(null);
    api
      .listPMTasks({
        status: statusFilter || undefined,
        device_id: deviceFilter.trim() || undefined,
        organization_id: effectiveOrgId,
        limit: 200,
      })
      .then((rows) => setTasks(Array.isArray(rows) ? rows : []))
      .catch((e: any) => setError(e?.message || 'โหลดงาน PM ไม่สำเร็จ'))
      .finally(() => setLoading(false));
  }, [statusFilter, deviceFilter, effectiveOrgId]);

  const loadPlans = useCallback(() => {
    api
      .listPMPlans()
      .then((rows) => setPlans(Array.isArray(rows) ? rows : []))
      .catch((e: any) => setError(e?.message || 'โหลดแผน PM ไม่สำเร็จ'));
  }, []);

  useEffect(() => {
    loadTasks();
  }, [loadTasks]);

  useEffect(() => {
    loadPlans();
  }, [loadPlans]);

  const loadFlags = useCallback(() => {
    api
      .listHealthFlags({
        status: flagStatusFilter || undefined,
        rule_code: flagRuleFilter || undefined,
        organization_id: effectiveOrgId,
        limit: 200,
      })
      .then((rows) => setFlags(Array.isArray(rows) ? rows : []))
      .catch((e: any) => setError(e?.message || 'โหลดรายการแจ้งเตือนไม่สำเร็จ'));
  }, [flagStatusFilter, flagRuleFilter, effectiveOrgId]);

  // โหลดเมื่อเข้าแท็บแจ้งเตือนเท่านั้น — ไม่ยิง API ทิ้งตอนดูงาน/แผน
  useEffect(() => {
    if (tab === 'flags') loadFlags();
  }, [tab, loadFlags]);

  // ข้อมูลประกอบ: โรงเรียน (เฉพาะ global scope) + ชนิดอุปกรณ์ที่มีจริงในระบบ
  useEffect(() => {
    let alive = true;
    if (isGlobalScope) {
      api
        .listOrganizations()
        .then((rows) => { if (alive) setOrgs(Array.isArray(rows) ? rows : []); })
        .catch(() => { /* ตัวกรองโรงเรียนไม่ขึ้น ไม่ถือว่าหน้าเสีย */ });
    }
    api
      .listDevices(200)
      .then((rows) => {
        if (!alive) return;
        const types = Array.from(
          new Set((Array.isArray(rows) ? rows : []).map((d: any) => d?.device_type).filter(Boolean)),
        ) as string[];
        setDeviceTypes(types.sort());
      })
      .catch(() => { /* datalist ว่างได้ — ยังพิมพ์เองได้ */ });
    return () => { alive = false; };
  }, [isGlobalScope]);

  const orgName = (id?: number | null) => {
    if (!id) return '—';
    return orgs.find((o) => o.id === id)?.name || `#${id}`;
  };

  const handleGenerate = async () => {
    setGenerating(true);
    setError(null);
    setNotice(null);
    try {
      const r = await api.generatePMTasks();
      setNotice(
        `สร้างงาน PM ใหม่ ${r?.generated ?? 0} งาน · ข้ามเพราะมีงานค้างอยู่แล้ว ${r?.skipped_duplicate ?? 0} · ปรับเป็นเลยกำหนด ${r?.marked_overdue ?? 0}`,
      );
      loadTasks();
    } catch (e: any) {
      setError(e?.message || 'สร้างงาน PM ไม่สำเร็จ');
    } finally {
      setGenerating(false);
    }
  };

  const openSubmit = (task: any) => {
    const items: any[] = Array.isArray(task.checklist) ? task.checklist : [];
    setResults(
      items.length > 0
        ? items.map((raw, i) => ({ item: checklistItemLabel(raw, i), value: true, note: '' }))
        : [{ item: 'ตรวจสภาพทั่วไปของอุปกรณ์', value: true, note: '' }],
    );
    setPhotos([]);
    setPanelError(null);
    setSubmitTask(task);
  };

  const closeSubmit = () => {
    setSubmitTask(null);
    setResults([]);
    setPhotos([]);
    setPanelError(null);
  };

  const setResultAt = (index: number, patch: Partial<ChecklistResult>) => {
    setResults((prev) => prev.map((r, i) => (i === index ? { ...r, ...patch } : r)));
  };

  const handleUploadPhotos = async (files: FileList | null) => {
    if (!files || files.length === 0) return;
    setUploading(true);
    setPanelError(null);
    try {
      const urls: string[] = [];
      for (const file of Array.from(files)) {
        const r = await api.upload(file);
        if (r?.url) urls.push(r.url);
      }
      setPhotos((prev) => [...prev, ...urls]);
    } catch (e: any) {
      setPanelError(e?.message || 'อัปโหลดรูปไม่สำเร็จ');
    } finally {
      setUploading(false);
    }
  };

  const handleSubmitResult = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!submitTask) return;
    setSaving(true);
    setPanelError(null);
    try {
      const r = await api.submitPMTask(submitTask.id, {
        result: results.map((x) => ({ item: x.item, value: x.value, note: x.note.trim() || undefined })),
        photos,
      });
      const failed = r?.failed_items ?? 0;
      setNotice(
        failed > 0
          ? `บันทึกผลตรวจ ${r?.task_no || submitTask.task_no} แล้ว — พบไม่ผ่าน ${failed} รายการ${r?.auto_ticket_id ? ` และเปิด Ticket ${r.auto_ticket_id} อัตโนมัติ` : ''}`
          : `บันทึกผลตรวจ ${r?.task_no || submitTask.task_no} แล้ว — ผ่านทุกรายการ (รอบถัดไป ${fmtDate(r?.next_due)})`,
      );
      closeSubmit();
      loadTasks();
    } catch (err: any) {
      setPanelError(err?.message || 'บันทึกผลตรวจไม่สำเร็จ');
    } finally {
      setSaving(false);
    }
  };

  const handleSkip = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!skipTask) return;
    const reason = skipReason.trim();
    if (reason.length < 3) {
      setPanelError('กรุณาระบุเหตุผลอย่างน้อย 3 ตัวอักษร (เก็บไว้ตรวจย้อนหลัง)');
      return;
    }
    setSaving(true);
    setPanelError(null);
    try {
      await api.skipPMTask(skipTask.id, reason);
      setNotice(`ข้ามงาน ${skipTask.task_no} แล้ว — บันทึกเหตุผลไว้ในระบบ`);
      setSkipTask(null);
      setSkipReason('');
      loadTasks();
    } catch (err: any) {
      setPanelError(err?.message || 'ข้ามงาน PM ไม่สำเร็จ');
    } finally {
      setSaving(false);
    }
  };

  const handleSavePlan = async (e: React.FormEvent) => {
    e.preventDefault();
    if (planForm.name.trim().length < 3) {
      setPanelError('ชื่อแผนต้องยาวอย่างน้อย 3 ตัวอักษร');
      return;
    }
    setSaving(true);
    setPanelError(null);
    try {
      const checklist = planForm.checklistText
        .split('\n')
        .map((s) => s.trim())
        .filter(Boolean);
      await api.createPMPlan({
        name: planForm.name.trim(),
        device_type: planForm.device_type || undefined,
        interval_days: planForm.interval_days,
        checklist,
        is_active: planForm.is_active,
      });
      setShowPlanForm(false);
      setPlanForm({ name: '', device_type: '', interval_days: 90, checklistText: '', is_active: true });
      setNotice('สร้างแผน PM แล้ว — กด "สร้างงานตามรอบ" เพื่อออกงานให้อุปกรณ์ที่ถึงกำหนด');
      loadPlans();
    } catch (err: any) {
      setPanelError(err?.message || 'บันทึกแผน PM ไม่สำเร็จ');
    } finally {
      setSaving(false);
    }
  };

  const handleRunRules = async () => {
    setRunningRules(true);
    setError(null);
    setNotice(null);
    try {
      const r = await api.runPMRules(effectiveOrgId);
      const by = r?.by_rule || {};
      setNotice(
        `ตรวจตามกฎแล้ว — พบใหม่ ${r?.created ?? 0} รายการ (ซ่อมซ้ำ ${by.REPEATED_FAILURE ?? 0} · ประกันใกล้หมด ${by.WARRANTY_EXPIRING ?? 0} · เสนอเปลี่ยนเครื่อง ${by.REPLACEMENT_CANDIDATE ?? 0})`,
      );
      loadFlags();
    } catch (e: any) {
      setError(e?.message || 'รันกฎตรวจสุขภาพอุปกรณ์ไม่สำเร็จ');
    } finally {
      setRunningRules(false);
    }
  };

  const handleFlagStatus = async (flag: any, status: 'acknowledged' | 'resolved') => {
    setFlagUpdatingId(flag.id);
    setError(null);
    try {
      await api.updateHealthFlag(flag.id, status);
      setNotice(
        status === 'resolved'
          ? `ปิดรายการแจ้งเตือนของ ${flag.device_id} แล้ว — กฎจะแจ้งใหม่ได้ถ้าเงื่อนไขเกิดอีก`
          : `บันทึกว่ารับทราบรายการของ ${flag.device_id} แล้ว`,
      );
      loadFlags();
    } catch (e: any) {
      setError(e?.message || 'อัปเดตสถานะแจ้งเตือนไม่สำเร็จ');
    } finally {
      setFlagUpdatingId(null);
    }
  };

  const counts = {
    pending: tasks.filter((t) => t.status === 'pending').length,
    overdue: tasks.filter((t) => isOverdue(t)).length,
    done: tasks.filter((t) => t.status === 'done').length,
  };
  const openFlagCount = flags.filter((f) => f.status === 'open').length;

  return (
    <div className="page-content">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack} aria-label="กลับ">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
          </button>
          <div>
            <h1 className="top-bar-title">บำรุงรักษาเชิงป้องกัน (PM)</h1>
            <span className="top-bar-subtitle">
              {tab === 'tasks'
                ? `${tasks.length} งาน · รอทำ ${counts.pending} · เลยกำหนด ${counts.overdue} · เสร็จ ${counts.done}`
                : tab === 'plans'
                  ? `${plans.length} แผน — รอบตรวจตามชนิดอุปกรณ์`
                  : `${flags.length} รายการ · ยังไม่จัดการ ${openFlagCount} — จากกฎตรวจสุขภาพอุปกรณ์`}
            </span>
          </div>
        </div>
        <div className="top-bar-actions">
          {tab === 'flags' ? (
            <button className="btn btn-secondary" onClick={handleRunRules} disabled={runningRules}>
              {runningRules ? 'กำลังตรวจ...' : 'ตรวจตามกฎทันที'}
            </button>
          ) : (
            <button className="btn btn-secondary" onClick={handleGenerate} disabled={generating}>
              {generating ? 'กำลังสร้าง...' : 'สร้างงานตามรอบ'}
            </button>
          )}
          {tab === 'plans' && canManagePlans && (
            <button className="btn btn-primary" onClick={() => { setPanelError(null); setShowPlanForm(true); }}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 6, verticalAlign: 'middle' }}>
                <path d="M12 5v14M5 12h14"/>
              </svg>
              เพิ่มแผน PM
            </button>
          )}
          <button
            className="btn btn-ghost"
            onClick={() => { loadTasks(); loadPlans(); if (tab === 'flags') loadFlags(); }}
            aria-label="โหลดใหม่"
          >
            ⟳
          </button>
        </div>
      </div>

      {/* แท็บ งาน / แผน */}
      <div style={{ display: 'flex', gap: 8, marginBottom: 16, flexWrap: 'wrap' }}>
        <button
          className={`btn ${tab === 'tasks' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setTab('tasks')}
        >
          งาน PM
        </button>
        <button
          className={`btn ${tab === 'plans' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setTab('plans')}
        >
          แผน PM
        </button>
        <button
          className={`btn ${tab === 'flags' ? 'btn-primary' : 'btn-ghost'}`}
          onClick={() => setTab('flags')}
        >
          แจ้งเตือนสุขภาพอุปกรณ์
        </button>
      </div>

      {error && (
        <div style={{ padding: '10px 14px', background: 'var(--color-danger-light)', color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem', marginBottom: 16 }}>
          {error}
        </div>
      )}
      {notice && (
        <div style={{ padding: '10px 14px', background: 'var(--color-success-light)', color: 'var(--color-success)', borderRadius: 'var(--radius-sm)', fontSize: '0.85rem', marginBottom: 16, display: 'flex', justifyContent: 'space-between', gap: 12 }}>
          <span>{notice}</span>
          <button className="btn btn-ghost" style={{ padding: '0 6px', minHeight: 0 }} onClick={() => setNotice(null)} aria-label="ปิดข้อความ">✕</button>
        </div>
      )}

      {tab === 'tasks' && (
        <>
          <div className="form-row" style={{ marginBottom: 12 }}>
            <div className="form-group">
              <label className="form-label">สถานะ</label>
              <select className="form-select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
                <option value="">ทุกสถานะ</option>
                <option value="pending">รอดำเนินการ</option>
                <option value="overdue">เลยกำหนด</option>
                <option value="done">ตรวจเสร็จแล้ว</option>
                <option value="skipped">ข้ามรอบนี้</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">รหัสอุปกรณ์</label>
              <input
                className="form-input"
                value={deviceFilter}
                onChange={(e) => setDeviceFilter(e.target.value)}
                placeholder="เช่น DEV-0001 (เว้นว่าง = ทุกเครื่อง)"
              />
            </div>
            {isGlobalScope && (
              <div className="form-group">
                <label className="form-label">โรงเรียน</label>
                <select
                  className="form-select"
                  value={orgFilter}
                  onChange={(e) => setOrgFilter(e.target.value ? Number(e.target.value) : '')}
                >
                  <option value="">ทุกโรงเรียน</option>
                  {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                </select>
              </div>
            )}
          </div>

          <div className="page-section">
            <div className="section-body">
              {loading ? (
                <div className="loading-state" style={{ padding: 40 }}>
                  <div className="spinner" />
                  <span>กำลังโหลด...</span>
                </div>
              ) : tasks.length === 0 ? (
                <div className="empty-state" style={{ padding: 40 }}>
                  <svg className="empty-icon" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <rect x="3" y="4" width="18" height="17" rx="2"/>
                    <path d="M3 10h18M8 2v4M16 2v4M9 15l2 2 4-4"/>
                  </svg>
                  <span className="empty-text">ยังไม่มีงาน PM — สร้างแผนก่อน แล้วกด "สร้างงานตามรอบ"</span>
                </div>
              ) : (
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>เลขงาน</th>
                        <th>แผน / อุปกรณ์</th>
                        {isGlobalScope && <th>โรงเรียน</th>}
                        <th>กำหนดตรวจ</th>
                        <th>สถานะ</th>
                        <th>ผู้ตรวจ</th>
                        <th>จัดการ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {tasks.map((t) => {
                        const overdue = isOverdue(t);
                        const badgeKey = overdue ? 'overdue' : t.status;
                        const open = t.status === 'pending' || t.status === 'overdue';
                        return (
                          <tr key={t.id}>
                            <td style={{ fontWeight: 600, fontSize: '0.82rem' }}>{t.task_no}</td>
                            <td>
                              <div style={{ fontSize: '0.85rem' }}>{t.plan_name || '— ไม่ผูกแผน —'}</div>
                              <div style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)' }}>
                                {t.device_id || '—'}{t.device_type ? ` · ${t.device_type}` : ''}
                              </div>
                              {t.ticket_id && (
                                <div style={{ fontSize: '0.72rem', color: 'var(--color-danger)', marginTop: 2 }}>
                                  เปิด Ticket: {t.ticket_id}
                                </div>
                              )}
                              {t.skip_reason && (
                                <div style={{ fontSize: '0.72rem', color: 'var(--color-text-secondary)', marginTop: 2 }}>
                                  เหตุผลที่ข้าม: {t.skip_reason}
                                </div>
                              )}
                            </td>
                            {isGlobalScope && <td style={{ fontSize: '0.82rem' }}>{orgName(t.organization_id)}</td>}
                            <td style={{ fontSize: '0.82rem', color: overdue ? 'var(--color-danger)' : undefined, fontWeight: overdue ? 600 : undefined }}>
                              {fmtDate(t.due_date)}
                              {t.next_due && (
                                <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)', fontWeight: 400 }}>
                                  รอบถัดไป {fmtDate(t.next_due)}
                                </div>
                              )}
                            </td>
                            <td>
                              <span className={`badge ${TASK_STATUS_BADGE[badgeKey] || 'badge-pending'}`}>
                                {TASK_STATUS_LABELS[badgeKey] || badgeKey}
                              </span>
                            </td>
                            <td style={{ fontSize: '0.8rem' }}>
                              {t.done_by || '—'}
                              {t.done_at && (
                                <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)' }}>{fmtDateTime(t.done_at)}</div>
                              )}
                            </td>
                            <td>
                              {open ? (
                                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                  <button className="btn btn-primary" style={{ padding: '4px 10px', fontSize: '0.78rem' }} onClick={() => openSubmit(t)}>
                                    กรอกผลตรวจ
                                  </button>
                                  <button
                                    className="btn btn-ghost"
                                    style={{ padding: '4px 10px', fontSize: '0.78rem' }}
                                    onClick={() => { setSkipTask(t); setSkipReason(''); setPanelError(null); }}
                                  >
                                    ข้าม
                                  </button>
                                </div>
                              ) : (
                                <span style={{ fontSize: '0.78rem', color: 'var(--color-text-tertiary)' }}>ปิดแล้ว</span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {tab === 'plans' && (
        <div className="page-section">
          <div className="section-body">
            {plans.length === 0 ? (
              <div className="empty-state" style={{ padding: 40 }}>
                <svg className="empty-icon" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                  <path d="M9 11l3 3L22 4M21 12v7a2 2 0 01-2 2H5a2 2 0 01-2-2V5a2 2 0 012-2h11"/>
                </svg>
                <span className="empty-text">
                  {canManagePlans ? 'ยังไม่มีแผน PM — กด "เพิ่มแผน PM"' : 'ยังไม่มีแผน PM (ผู้ดูแลระบบเป็นผู้สร้างแผน)'}
                </span>
              </div>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>ชื่อแผน</th>
                      <th>ชนิดอุปกรณ์</th>
                      <th>รอบ (วัน)</th>
                      <th>รายการตรวจ</th>
                      <th>สถานะ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {plans.map((p) => (
                      <tr key={p.id}>
                        <td style={{ fontWeight: 500 }}>{p.name}</td>
                        <td style={{ fontSize: '0.82rem' }}>{p.device_type || 'ทุกชนิด'}</td>
                        <td style={{ fontSize: '0.82rem' }}>{p.interval_days}</td>
                        <td style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
                          {Array.isArray(p.checklist) && p.checklist.length > 0
                            ? `${p.checklist.length} รายการ — ${p.checklist.map((c: any, i: number) => checklistItemLabel(c, i)).slice(0, 3).join(', ')}${p.checklist.length > 3 ? ' …' : ''}`
                            : 'ไม่ระบุ'}
                        </td>
                        <td>
                          <span className={`badge ${p.is_active ? 'badge-resolved' : 'badge-closed'}`}>
                            {p.is_active ? 'ใช้งาน' : 'ปิดใช้งาน'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ─── แท็บ: แจ้งเตือนจาก Rule Engine (§38) ─────────────────── */}
      {tab === 'flags' && (
        <>
          <div
            style={{
              padding: '10px 14px',
              background: 'var(--color-bg-subtle, rgba(0,0,0,0.03))',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.82rem',
              color: 'var(--color-text-secondary)',
              marginBottom: 12,
              lineHeight: 1.6,
            }}
          >
            กฎที่ระบบใช้ตรวจ: ซ่อมซ้ำตั้งแต่ 3 ครั้งใน 90 วัน · ประกันหมดภายใน 30 วัน ·
            อายุเกิน 4 ปีและซ่อมสะสมตั้งแต่ 5 ครั้ง — อุปกรณ์ที่มีรายการเดิมค้างอยู่จะไม่ถูกแจ้งซ้ำ
          </div>

          <div className="form-row" style={{ marginBottom: 12 }}>
            <div className="form-group">
              <label className="form-label">สถานะ</label>
              <select
                className="form-select"
                value={flagStatusFilter}
                onChange={(e) => setFlagStatusFilter(e.target.value)}
              >
                <option value="">ทุกสถานะ</option>
                <option value="open">ยังไม่จัดการ</option>
                <option value="acknowledged">รับทราบแล้ว</option>
                <option value="resolved">ปิดแล้ว</option>
              </select>
            </div>
            <div className="form-group">
              <label className="form-label">กฎ</label>
              <select
                className="form-select"
                value={flagRuleFilter}
                onChange={(e) => setFlagRuleFilter(e.target.value)}
              >
                <option value="">ทุกกฎ</option>
                <option value="REPEATED_FAILURE">ซ่อมซ้ำบ่อย</option>
                <option value="WARRANTY_EXPIRING">ประกันใกล้หมด</option>
                <option value="REPLACEMENT_CANDIDATE">เสนอเปลี่ยนเครื่อง</option>
              </select>
            </div>
            {isGlobalScope && (
              <div className="form-group">
                <label className="form-label">โรงเรียน</label>
                <select
                  className="form-select"
                  value={orgFilter}
                  onChange={(e) => setOrgFilter(e.target.value ? Number(e.target.value) : '')}
                >
                  <option value="">ทุกโรงเรียน</option>
                  {orgs.map((o) => <option key={o.id} value={o.id}>{o.name}</option>)}
                </select>
              </div>
            )}
          </div>

          <div className="page-section">
            <div className="section-body">
              {flags.length === 0 ? (
                <div className="empty-state" style={{ padding: 40 }}>
                  <svg className="empty-icon" width="40" height="40" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                    <path d="M12 9v4M12 17h.01" />
                    <path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0z" />
                  </svg>
                  <span className="empty-text">
                    ไม่มีรายการตามเงื่อนไขนี้ — กด "ตรวจตามกฎทันที" เพื่อประมวลผลใหม่
                  </span>
                </div>
              ) : (
                <div className="table-wrap">
                  <table className="data-table">
                    <thead>
                      <tr>
                        <th>อุปกรณ์</th>
                        <th>กฎที่เข้าเงื่อนไข</th>
                        {isGlobalScope && <th>โรงเรียน</th>}
                        <th>รายละเอียด</th>
                        <th>ระดับ</th>
                        <th>สถานะ</th>
                        <th>จัดการ</th>
                      </tr>
                    </thead>
                    <tbody>
                      {flags.map((f) => {
                        const busy = flagUpdatingId === f.id;
                        return (
                          <tr key={f.id}>
                            <td style={{ fontWeight: 600, fontSize: '0.82rem' }}>{f.device_id}</td>
                            <td style={{ fontSize: '0.82rem' }}>{RULE_LABELS[f.rule_code] || f.rule_code}</td>
                            {isGlobalScope && <td style={{ fontSize: '0.82rem' }}>{orgName(f.organization_id)}</td>}
                            <td style={{ fontSize: '0.82rem', maxWidth: 320 }}>
                              {f.message}
                              <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)', marginTop: 2 }}>
                                ตรวจพบ {fmtDateTime(f.created_at)}
                              </div>
                            </td>
                            <td>
                              <span className={`badge ${SEVERITY_BADGE[f.severity] || 'badge-pending'}`}>
                                {f.severity === 'critical' ? 'เร่งด่วน' : f.severity === 'info' ? 'ทั่วไป' : 'เฝ้าระวัง'}
                              </span>
                            </td>
                            <td style={{ fontSize: '0.8rem' }}>
                              {FLAG_STATUS_LABELS[f.status] || f.status}
                              {f.acknowledged_by && (
                                <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)' }}>
                                  โดย {f.acknowledged_by}
                                </div>
                              )}
                            </td>
                            <td>
                              {f.status === 'resolved' ? (
                                <span style={{ fontSize: '0.78rem', color: 'var(--color-text-tertiary)' }}>ปิดแล้ว</span>
                              ) : (
                                <div style={{ display: 'flex', gap: 6, flexWrap: 'wrap' }}>
                                  {f.status === 'open' && (
                                    <button
                                      className="btn btn-ghost"
                                      style={{ padding: '4px 10px', fontSize: '0.78rem' }}
                                      onClick={() => handleFlagStatus(f, 'acknowledged')}
                                      disabled={busy}
                                    >
                                      {busy ? 'กำลังบันทึก...' : 'รับทราบ'}
                                    </button>
                                  )}
                                  <button
                                    className="btn btn-primary"
                                    style={{ padding: '4px 10px', fontSize: '0.78rem' }}
                                    onClick={() => handleFlagStatus(f, 'resolved')}
                                    disabled={busy}
                                  >
                                    {busy ? 'กำลังบันทึก...' : 'ปิดรายการ'}
                                  </button>
                                </div>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        </>
      )}

      {/* ─── Panel: กรอกผลตรวจ PM ───────────────────────────────── */}
      {submitTask && (
        <div className="panel-overlay" onClick={closeSubmit}>
          <div className="repair-panel" style={{ width: 560, maxWidth: '95vw' }} onClick={(e) => e.stopPropagation()}>
            <div className="repair-panel-header">
              <h3 className="repair-panel-title">ผลตรวจ {submitTask.task_no}</h3>
              <button className="repair-panel-close" onClick={closeSubmit} aria-label="ปิด">✕</button>
            </div>
            <div className="repair-panel-body">
              <div style={{ fontSize: '0.82rem', color: 'var(--color-text-secondary)', marginBottom: 12 }}>
                {submitTask.plan_name || 'ไม่ผูกแผน'} · {submitTask.device_id || '—'} · กำหนด {fmtDate(submitTask.due_date)}
              </div>
              <form onSubmit={handleSubmitResult}>
                {results.map((r, i) => (
                  <div key={i} className="form-group" style={{ borderBottom: '1px solid var(--color-border)', paddingBottom: 10, marginBottom: 10 }}>
                    <label className="form-label">{r.item}</label>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 6, flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        className={`btn ${r.value ? 'btn-primary' : 'btn-ghost'}`}
                        style={{ padding: '4px 12px', fontSize: '0.8rem' }}
                        onClick={() => setResultAt(i, { value: true })}
                        aria-pressed={r.value}
                      >
                        ผ่าน
                      </button>
                      <button
                        type="button"
                        className={`btn ${!r.value ? 'btn-primary' : 'btn-ghost'}`}
                        style={{ padding: '4px 12px', fontSize: '0.8rem' }}
                        onClick={() => setResultAt(i, { value: false })}
                        aria-pressed={!r.value}
                      >
                        ไม่ผ่าน
                      </button>
                    </div>
                    <input
                      className="form-input"
                      value={r.note}
                      onChange={(e) => setResultAt(i, { note: e.target.value })}
                      placeholder={r.value ? 'หมายเหตุ (ไม่บังคับ)' : 'อาการที่พบ — ใช้เปิด Ticket อัตโนมัติ'}
                    />
                  </div>
                ))}

                <div className="form-group">
                  <label className="form-label">รูปประกอบ (ไม่บังคับ)</label>
                  <input
                    className="form-input"
                    type="file"
                    accept="image/*"
                    multiple
                    onChange={(e) => handleUploadPhotos(e.target.files)}
                    disabled={uploading}
                  />
                  {uploading && <div style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary)', marginTop: 4 }}>กำลังอัปโหลด...</div>}
                  {photos.length > 0 && (
                    <div style={{ display: 'flex', gap: 8, marginTop: 8, flexWrap: 'wrap' }}>
                      {photos.map((url) => (
                        <div key={url} style={{ position: 'relative' }}>
                          <img src={url} alt="" style={{ width: 64, height: 64, objectFit: 'cover', borderRadius: 'var(--radius-sm)', border: '1px solid var(--color-border)' }} />
                          <button
                            type="button"
                            onClick={() => setPhotos((p) => p.filter((x) => x !== url))}
                            aria-label="ลบรูป"
                            style={{ position: 'absolute', top: -6, right: -6, width: 20, height: 20, borderRadius: '50%', border: 'none', background: 'var(--color-danger)', color: '#fff', cursor: 'pointer', fontSize: '0.7rem', lineHeight: '20px', padding: 0 }}
                          >
                            ✕
                          </button>
                        </div>
                      ))}
                    </div>
                  )}
                </div>

                {results.some((r) => !r.value) && (
                  <div style={{ padding: '8px 12px', background: 'var(--color-warning-light)', color: '#B45309', borderRadius: 'var(--radius-sm)', fontSize: '0.8rem', marginBottom: 12 }}>
                    มีรายการไม่ผ่าน — ระบบจะเปิด Ticket ซ่อมให้อุปกรณ์นี้อัตโนมัติเมื่อบันทึก
                  </div>
                )}
                {panelError && (
                  <div style={{ padding: '8px 12px', background: 'var(--color-danger-light)', color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)', fontSize: '0.8rem', marginBottom: 12 }}>
                    {panelError}
                  </div>
                )}

                <div style={{ display: 'flex', gap: 8, marginTop: 12 }}>
                  <button type="submit" className="btn btn-primary" style={{ flex: 1 }} disabled={saving || uploading}>
                    {saving ? 'กำลังบันทึก...' : 'บันทึกผลตรวจ'}
                  </button>
                  <button type="button" className="btn btn-ghost" onClick={closeSubmit}>ยกเลิก</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* ─── Panel: ข้ามงาน PM ──────────────────────────────────── */}
      {skipTask && (
        <div className="panel-overlay" onClick={() => setSkipTask(null)}>
          <div className="repair-panel" style={{ width: 460, maxWidth: '95vw' }} onClick={(e) => e.stopPropagation()}>
            <div className="repair-panel-header">
              <h3 className="repair-panel-title">ข้ามงาน {skipTask.task_no}</h3>
              <button className="repair-panel-close" onClick={() => setSkipTask(null)} aria-label="ปิด">✕</button>
            </div>
            <div className="repair-panel-body">
              <form onSubmit={handleSkip}>
                <div className="form-group">
                  <label className="form-label">เหตุผลที่ข้าม *</label>
                  <textarea
                    className="form-input"
                    rows={3}
                    value={skipReason}
                    onChange={(e) => setSkipReason(e.target.value)}
                    placeholder="เช่น ห้องปิดปรับปรุง / อุปกรณ์ถูกยกไปซ่อมที่ศูนย์"
                  />
                </div>
                {panelError && (
                  <div style={{ padding: '8px 12px', background: 'var(--color-danger-light)', color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)', fontSize: '0.8rem', marginBottom: 12 }}>
                    {panelError}
                  </div>
                )}
                <div style={{ display: 'flex', gap: 8 }}>
                  <button type="submit" className="btn btn-primary" style={{ flex: 1 }} disabled={saving}>
                    {saving ? 'กำลังบันทึก...' : 'ยืนยันข้ามรอบนี้'}
                  </button>
                  <button type="button" className="btn btn-ghost" onClick={() => setSkipTask(null)}>ยกเลิก</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}

      {/* ─── Panel: เพิ่มแผน PM ─────────────────────────────────── */}
      {showPlanForm && (
        <div className="panel-overlay" onClick={() => setShowPlanForm(false)}>
          <div className="repair-panel" style={{ width: 520, maxWidth: '95vw' }} onClick={(e) => e.stopPropagation()}>
            <div className="repair-panel-header">
              <h3 className="repair-panel-title">เพิ่มแผน PM</h3>
              <button className="repair-panel-close" onClick={() => setShowPlanForm(false)} aria-label="ปิด">✕</button>
            </div>
            <div className="repair-panel-body">
              <form onSubmit={handleSavePlan}>
                <div className="form-group">
                  <label className="form-label">ชื่อแผน *</label>
                  <input
                    className="form-input"
                    value={planForm.name}
                    onChange={(e) => setPlanForm({ ...planForm, name: e.target.value })}
                    placeholder="เช่น ตรวจจอ Interactive ทุกไตรมาส"
                  />
                </div>
                <div className="form-row">
                  <div className="form-group">
                    <label className="form-label">ชนิดอุปกรณ์ (เว้นว่าง = ทุกชนิด)</label>
                    <input
                      className="form-input"
                      list="pm-device-types"
                      value={planForm.device_type}
                      onChange={(e) => setPlanForm({ ...planForm, device_type: e.target.value })}
                      placeholder="เช่น Interactive Display"
                    />
                    <datalist id="pm-device-types">
                      {deviceTypes.map((t) => <option key={t} value={t} />)}
                    </datalist>
                  </div>
                  <div className="form-group">
                    <label className="form-label">รอบตรวจ (วัน)</label>
                    <input
                      className="form-input"
                      type="number"
                      min={1}
                      max={3650}
                      value={planForm.interval_days}
                      onChange={(e) => setPlanForm({ ...planForm, interval_days: Math.min(3650, Math.max(1, Number(e.target.value) || 1)) })}
                    />
                  </div>
                </div>
                <div className="form-group">
                  <label className="form-label">รายการตรวจ (บรรทัดละ 1 รายการ)</label>
                  <textarea
                    className="form-input"
                    rows={5}
                    value={planForm.checklistText}
                    onChange={(e) => setPlanForm({ ...planForm, checklistText: e.target.value })}
                    placeholder={'ทำความสะอาดหน้าจอ\nทดสอบระบบสัมผัส\nตรวจสายสัญญาณ HDMI\nตรวจลำโพงและไมค์'}
                  />
                </div>
                <div className="form-group">
                  <label className="form-label" style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
                    <input
                      type="checkbox"
                      checked={planForm.is_active}
                      onChange={(e) => setPlanForm({ ...planForm, is_active: e.target.checked })}
                    />
                    เปิดใช้งานแผนนี้ทันที
                  </label>
                </div>
                {panelError && (
                  <div style={{ padding: '8px 12px', background: 'var(--color-danger-light)', color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)', fontSize: '0.8rem', marginBottom: 12 }}>
                    {panelError}
                  </div>
                )}
                <div style={{ display: 'flex', gap: 8 }}>
                  <button type="submit" className="btn btn-primary" style={{ flex: 1 }} disabled={saving}>
                    {saving ? 'กำลังบันทึก...' : 'บันทึกแผน'}
                  </button>
                  <button type="button" className="btn btn-ghost" onClick={() => setShowPlanForm(false)}>ยกเลิก</button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}