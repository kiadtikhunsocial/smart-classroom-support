import React, { useCallback, useEffect, useMemo, useState } from 'react';
import { api } from '../api/client';

/** โครงข้อมูลตรงกับ MembershipApplicationOut ฝั่ง backend (ไม่มี password_hash) */
interface MembershipApplication {
  id: number;
  username: string;
  full_name: string;
  email?: string | null;
  phone?: string | null;
  organization_id?: number | null;
  organization_code?: string | null;
  requested_role: string;
  status: string;
  note?: string | null;
  reject_reason?: string | null;
  created_at?: string | null;
  reviewed_at?: string | null;
  sheet_synced_at?: string | null;
}

interface RegistrationsPageProps {
  onBack: () => void;
}

/** บทบาทที่กำหนดให้ผู้สมัครได้ตอนอนุมัติ — backend ตรวจซ้ำอีกชั้น (validate_assignable_role) */
const ROLE_OPTIONS: { value: string; label: string }[] = [
  { value: 'it_support', label: 'ช่างซ่อม / IT Support' },
  { value: 'admin_school', label: 'ผู้ดูแลโรงเรียน' },
  { value: 'admin', label: 'ผู้ดูแลระบบ' },
];

const STATUS_FILTERS: { value: string; label: string }[] = [
  { value: 'pending', label: 'รออนุมัติ' },
  { value: 'approved', label: 'อนุมัติแล้ว' },
  { value: 'rejected', label: 'ปฏิเสธ' },
  { value: '', label: 'ทั้งหมด' },
];

/** สีของสถานะ — accent ใช้เป็นแถบซ้ายของการ์ด ให้กวาดตาเจอสถานะได้ทันที */
const STATUS_STYLE: Record<string, { bg: string; fg: string; accent: string; label: string }> = {
  pending: {
    bg: 'var(--color-warning-light, #FEF3C7)',
    fg: 'var(--color-warning, #B45309)',
    accent: 'var(--color-warning, #D97706)',
    label: 'รออนุมัติ',
  },
  approved: {
    bg: 'var(--color-success-light, #DCFCE7)',
    fg: 'var(--color-success, #16A34A)',
    accent: 'var(--color-success, #16A34A)',
    label: 'อนุมัติแล้ว',
  },
  rejected: {
    bg: 'var(--color-danger-light, #FEE2E2)',
    fg: 'var(--color-danger, #DC2626)',
    accent: 'var(--color-danger, #DC2626)',
    label: 'ปฏิเสธ',
  },
};

const FALLBACK_STYLE = {
  bg: 'var(--color-bg-subtle, #F3F4F6)',
  fg: 'var(--color-text-secondary, #4B5563)',
  accent: 'var(--color-border, #D1D5DB)',
  label: '',
};

function formatDateTime(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  return d.toLocaleString('th-TH', { dateStyle: 'medium', timeStyle: 'short' });
}

/** เวลาแบบ "3 ชั่วโมงที่ผ่านมา" — เจ้าหน้าที่สนใจว่าคำขอค้างมานานแค่ไหน */
function formatRelative(value?: string | null): string {
  if (!value) return '—';
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return '—';
  const mins = Math.floor((Date.now() - d.getTime()) / 60000);
  if (mins < 1) return 'เมื่อสักครู่';
  if (mins < 60) return `${mins} นาทีที่ผ่านมา`;
  const hours = Math.floor(mins / 60);
  if (hours < 24) return `${hours} ชั่วโมงที่ผ่านมา`;
  const days = Math.floor(hours / 24);
  if (days < 31) return `${days} วันที่ผ่านมา`;
  const months = Math.floor(days / 30);
  if (months < 12) return `${months} เดือนที่ผ่านมา`;
  return `${Math.max(1, Math.floor(days / 365))} ปีที่ผ่านมา`;
}

/** จำนวนวันที่คำขอค้างอยู่ — ใช้ขึ้นป้ายเตือนเมื่อค้างเกิน 3 วัน */
function daysWaiting(value?: string | null): number | null {
  if (!value) return null;
  const d = new Date(value);
  if (Number.isNaN(d.getTime())) return null;
  return Math.floor((Date.now() - d.getTime()) / 86400000);
}

function roleText(role: string): string {
  return ROLE_OPTIONS.find((r) => r.value === role)?.label ?? role;
}

function orgText(row: MembershipApplication): string {
  if (row.organization_code) return row.organization_code;
  if (row.organization_id) return `ID ${row.organization_id}`;
  return 'ไม่ระบุ';
}

/** อักษรย่อสำหรับวงกลมหน้าชื่อ — ช่วยแยกแถวด้วยตาเวลาคำขอเยอะ */
function initials(row: MembershipApplication): string {
  const source = (row.full_name || row.username || '?').trim();
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length === 0) return '?';
  if (parts.length === 1) return parts[0].slice(0, 1).toUpperCase();
  return (parts[0].slice(0, 1) + parts[1].slice(0, 1)).toUpperCase();
}

/** ช่องข้อมูลย่อยในการ์ด: ป้ายเล็กด้านบน ค่าด้านล่าง อ่านง่ายกว่าข้อความคั่นด้วยจุด */
function MetaItem({ label, value, mono }: { label: string; value: React.ReactNode; mono?: boolean }) {
  return (
    <div style={{ minWidth: 0 }}>
      <div
        style={{
          fontSize: '0.68rem',
          letterSpacing: '0.02em',
          color: 'var(--color-text-tertiary)',
          textTransform: 'uppercase',
          marginBottom: 2,
        }}
      >
        {label}
      </div>
      <div
        style={{
          fontSize: '0.82rem',
          color: 'var(--color-text-primary, #111827)',
          overflowWrap: 'anywhere',
          fontFamily: mono ? 'var(--font-mono, ui-monospace, "SFMono-Regular", Menlo, monospace)' : undefined,
        }}
      >
        {value}
      </div>
    </div>
  );
}

/**
 * หน้าอนุมัติคำขอสมัครสมาชิก (เมนู "อนุมัติสมาชิก")
 *
 * ใช้ GET /api/registrations, POST /api/registrations/{id}/approve|reject
 * สิทธิ์คุมจาก backend (owner / super_admin / admin / admin_school) และ
 * admin_school จะเห็นเฉพาะคำขอของโรงเรียนตัวเอง
 *
 * โหลดคำขอทุกสถานะครั้งเดียวแล้วกรองในหน้า เพื่อให้แท็บแสดงจำนวนจริงของแต่ละสถานะ
 * และสลับแท็บ/ค้นหาได้ทันทีโดยไม่ยิง API ซ้ำ
 */
export default function RegistrationsPage({ onBack }: RegistrationsPageProps) {
  const [rows, setRows] = useState<MembershipApplication[]>([]);
  const [status, setStatus] = useState('pending');
  const [query, setQuery] = useState('');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<number | null>(null);
  const [roleById, setRoleById] = useState<Record<number, string>>({});
  const [rejectingId, setRejectingId] = useState<number | null>(null);
  const [rejectReason, setRejectReason] = useState('');

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await api.listRegistrations({ status: undefined, limit: 500 });
      setRows(Array.isArray(data) ? (data as MembershipApplication[]) : []);
    } catch (err: any) {
      setError(err?.message || 'โหลดรายการคำขอสมัครสมาชิกไม่สำเร็จ');
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load();
  }, [load]);

  const counts = useMemo(() => {
    const result: Record<string, number> = { '': rows.length, pending: 0, approved: 0, rejected: 0 };
    for (const row of rows) {
      result[row.status] = (result[row.status] ?? 0) + 1;
    }
    return result;
  }, [rows]);

  const visible = useMemo(() => {
    const q = query.trim().toLowerCase();
    const list = rows.filter((row) => {
      if (status && row.status !== status) return false;
      if (!q) return true;
      return [
        row.full_name,
        row.username,
        row.email,
        row.phone,
        row.organization_code,
        String(row.id),
      ]
        .filter(Boolean)
        .some((field) => String(field).toLowerCase().includes(q));
    });
    // รออนุมัติขึ้นก่อนเสมอ ภายในกลุ่มเรียงคำขอเก่าสุดก่อน (ค้างนานที่สุดควรถูกจัดการก่อน)
    return list.sort((a, b) => {
      if (a.status !== b.status) {
        if (a.status === 'pending') return -1;
        if (b.status === 'pending') return 1;
      }
      const ta = a.created_at ? new Date(a.created_at).getTime() : 0;
      const tb = b.created_at ? new Date(b.created_at).getTime() : 0;
      return a.status === 'pending' && b.status === 'pending' ? ta - tb : tb - ta;
    });
  }, [rows, status, query]);

  const handleApprove = async (row: MembershipApplication) => {
    setBusyId(row.id);
    setError(null);
    setNotice(null);
    try {
      const role = roleById[row.id] || row.requested_role || 'it_support';
      const res = await api.approveRegistration(row.id, { role });
      const username = res?.user?.username ?? row.username;
      setNotice(`อนุมัติแล้ว — สร้างบัญชี "${username}" บทบาท ${roleText(role)} เรียบร้อย`);
      await load();
    } catch (err: any) {
      setError(err?.message || 'อนุมัติคำขอไม่สำเร็จ');
    } finally {
      setBusyId(null);
    }
  };

  const handleReject = async (row: MembershipApplication) => {
    setBusyId(row.id);
    setError(null);
    setNotice(null);
    try {
      await api.rejectRegistration(row.id, rejectReason.trim() || undefined);
      setNotice(`ปฏิเสธคำขอของ "${row.username}" แล้ว`);
      setRejectingId(null);
      setRejectReason('');
      await load();
    } catch (err: any) {
      setError(err?.message || 'ปฏิเสธคำขอไม่สำเร็จ');
    } finally {
      setBusyId(null);
    }
  };

  const pendingCount = counts.pending ?? 0;
  const oldestPendingDays = useMemo(() => {
    const waits = rows
      .filter((r) => r.status === 'pending')
      .map((r) => daysWaiting(r.created_at))
      .filter((d): d is number => d !== null);
    return waits.length ? Math.max(...waits) : null;
  }, [rows]);

  return (
    <div className="page">
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'space-between',
          flexWrap: 'wrap',
          gap: 12,
          marginBottom: 14,
        }}
      >
        <div style={{ minWidth: 0 }}>
          <h2 style={{ margin: 0, fontSize: '1.15rem' }}>อนุมัติสมาชิก</h2>
          <p style={{ margin: '4px 0 0', fontSize: '0.8rem', color: 'var(--color-text-tertiary)' }}>
            คำขอสมัครจากหน้าสาธารณะ — บัญชีจะถูกสร้างเมื่อกดอนุมัติ
            {pendingCount > 0 ? ` · รออนุมัติ ${pendingCount} รายการ` : ' · ไม่มีคำขอค้าง'}
            {oldestPendingDays !== null && oldestPendingDays >= 3
              ? ` · ค้างนานสุด ${oldestPendingDays} วัน`
              : ''}
          </p>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <button type="button" className="btn" onClick={() => void load()} disabled={loading}>
            {loading ? 'กำลังโหลด...' : 'รีเฟรช'}
          </button>
          <button type="button" className="btn" onClick={onBack}>
            ← กลับ Dashboard
          </button>
        </div>
      </div>

      <div
        style={{
          display: 'flex',
          gap: 10,
          flexWrap: 'wrap',
          alignItems: 'center',
          justifyContent: 'space-between',
          marginBottom: 14,
        }}
      >
        <div role="tablist" aria-label="กรองตามสถานะ" style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          {STATUS_FILTERS.map((f) => {
            const active = f.value === status;
            const n = counts[f.value] ?? 0;
            return (
              <button
                key={f.value || 'all'}
                type="button"
                role="tab"
                aria-selected={active}
                className={active ? 'btn btn-primary' : 'btn'}
                onClick={() => setStatus(f.value)}
              >
                {f.label}
                <span
                  style={{
                    marginLeft: 6,
                    padding: '1px 7px',
                    borderRadius: 999,
                    fontSize: '0.72rem',
                    fontWeight: 700,
                    background: active ? 'rgba(255,255,255,0.22)' : 'var(--color-bg-subtle, #F3F4F6)',
                    color: active ? 'inherit' : 'var(--color-text-secondary, #4B5563)',
                  }}
                >
                  {n}
                </span>
              </button>
            );
          })}
        </div>

        <div style={{ position: 'relative', flex: '1 1 240px', maxWidth: 340 }}>
          <input
            type="search"
            className="form-input"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="ค้นหาชื่อ / username / อีเมล / เบอร์ / รหัสโรงเรียน"
            aria-label="ค้นหาคำขอสมัครสมาชิก"
            style={{ width: '100%', paddingRight: query ? 34 : undefined }}
          />
          {query && (
            <button
              type="button"
              onClick={() => setQuery('')}
              aria-label="ล้างคำค้น"
              title="ล้างคำค้น"
              style={{
                position: 'absolute',
                right: 6,
                top: '50%',
                transform: 'translateY(-50%)',
                border: 'none',
                background: 'transparent',
                cursor: 'pointer',
                color: 'var(--color-text-tertiary)',
                fontSize: '1rem',
                lineHeight: 1,
                padding: 4,
              }}
            >
              ×
            </button>
          )}
        </div>
      </div>

      <div aria-live="polite">
        {error && (
          <div
            role="alert"
            style={{
              padding: '10px 14px',
              marginBottom: 12,
              background: 'var(--color-danger-light)',
              color: 'var(--color-danger)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.82rem',
            }}
          >
            {error}
          </div>
        )}
        {notice && (
          <div
            role="status"
            style={{
              padding: '10px 14px',
              marginBottom: 12,
              background: 'var(--color-success-light, #DCFCE7)',
              color: 'var(--color-success, #16A34A)',
              borderRadius: 'var(--radius-sm)',
              fontSize: '0.82rem',
            }}
          >
            {notice}
          </div>
        )}
      </div>

      {loading ? (
        <p style={{ fontSize: '0.85rem', color: 'var(--color-text-tertiary)' }}>กำลังโหลด...</p>
      ) : visible.length === 0 ? (
        <div
          style={{
            border: '1px dashed var(--color-border)',
            borderRadius: 'var(--radius-md, 10px)',
            padding: '28px 18px',
            textAlign: 'center',
            fontSize: '0.85rem',
            color: 'var(--color-text-tertiary)',
          }}
        >
          {query.trim()
            ? `ไม่พบคำขอที่ตรงกับ "${query.trim()}" ในสถานะนี้`
            : 'ไม่มีคำขอสมัครสมาชิกในสถานะนี้'}
        </div>
      ) : (
        <div style={{ display: 'grid', gap: 10 }}>
          {visible.map((row) => {
            const badge = STATUS_STYLE[row.status] ?? { ...FALLBACK_STYLE, label: row.status };
            const isPending = row.status === 'pending';
            const busy = busyId === row.id;
            const waiting = isPending ? daysWaiting(row.created_at) : null;
            return (
              <div
                key={row.id}
                style={{
                  border: '1px solid var(--color-border)',
                  borderLeft: `3px solid ${badge.accent}`,
                  borderRadius: 'var(--radius-md, 10px)',
                  padding: 14,
                  background: 'var(--color-surface, #fff)',
                }}
              >
                <div
                  style={{
                    display: 'flex',
                    justifyContent: 'space-between',
                    alignItems: 'flex-start',
                    gap: 10,
                    flexWrap: 'wrap',
                  }}
                >
                  <div style={{ display: 'flex', gap: 10, minWidth: 0, flex: '1 1 260px' }}>
                    <span
                      aria-hidden="true"
                      style={{
                        width: 34,
                        height: 34,
                        flexShrink: 0,
                        borderRadius: '50%',
                        background: badge.bg,
                        color: badge.fg,
                        display: 'flex',
                        alignItems: 'center',
                        justifyContent: 'center',
                        fontSize: '0.8rem',
                        fontWeight: 700,
                      }}
                    >
                      {initials(row)}
                    </span>
                    <div style={{ minWidth: 0 }}>
                      <div style={{ fontWeight: 700, overflowWrap: 'anywhere' }}>
                        {row.full_name}{' '}
                        <span
                          style={{
                            fontWeight: 400,
                            color: 'var(--color-text-tertiary)',
                            fontSize: '0.85rem',
                          }}
                        >
                          ({row.username})
                        </span>
                      </div>
                      <div style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)', marginTop: 2 }}>
                        คำขอ #{row.id} · <span title={formatDateTime(row.created_at)}>{formatRelative(row.created_at)}</span>
                      </div>
                    </div>
                  </div>
                  <div style={{ display: 'flex', gap: 6, alignItems: 'center', flexWrap: 'wrap' }}>
                    {waiting !== null && waiting >= 3 && (
                      <span
                        title={`ส่งคำขอเมื่อ ${formatDateTime(row.created_at)}`}
                        style={{
                          background: 'var(--color-danger-light, #FEE2E2)',
                          color: 'var(--color-danger, #DC2626)',
                          borderRadius: 999,
                          padding: '3px 10px',
                          fontSize: '0.72rem',
                          fontWeight: 700,
                          whiteSpace: 'nowrap',
                        }}
                      >
                        ค้าง {waiting} วัน
                      </span>
                    )}
                    <span
                      style={{
                        background: badge.bg,
                        color: badge.fg,
                        borderRadius: 999,
                        padding: '3px 10px',
                        fontSize: '0.74rem',
                        fontWeight: 700,
                        whiteSpace: 'nowrap',
                      }}
                    >
                      {badge.label || row.status}
                    </span>
                  </div>
                </div>

                <div
                  style={{
                    display: 'grid',
                    gridTemplateColumns: 'repeat(auto-fit, minmax(150px, 1fr))',
                    gap: 10,
                    marginTop: 12,
                    paddingTop: 10,
                    borderTop: '1px solid var(--color-border)',
                  }}
                >
                  <MetaItem label="หน่วยงาน" value={orgText(row)} mono={!!row.organization_code} />
                  <MetaItem label="บทบาทที่ขอ" value={roleText(row.requested_role)} />
                  <MetaItem label="อีเมล" value={row.email || 'ไม่ระบุ'} />
                  <MetaItem label="เบอร์โทร" value={row.phone || 'ไม่ระบุ'} />
                  <MetaItem label="ส่งคำขอ" value={formatDateTime(row.created_at)} />
                  <MetaItem
                    label="Google Sheet"
                    value={row.sheet_synced_at ? 'ส่งแล้ว' : 'ยังไม่ส่ง'}
                  />
                  {!isPending && <MetaItem label="ตรวจสอบเมื่อ" value={formatDateTime(row.reviewed_at)} />}
                </div>

                {row.note && (
                  <div
                    style={{
                      marginTop: 10,
                      padding: '8px 10px',
                      background: 'var(--color-bg-subtle, #F9FAFB)',
                      borderRadius: 'var(--radius-sm, 8px)',
                      fontSize: '0.8rem',
                      overflowWrap: 'anywhere',
                    }}
                  >
                    <strong style={{ fontWeight: 600 }}>หมายเหตุจากผู้สมัคร:</strong> {row.note}
                  </div>
                )}

                {row.status === 'rejected' && (
                  <div
                    style={{
                      marginTop: 10,
                      padding: '8px 10px',
                      background: 'var(--color-danger-light, #FEE2E2)',
                      color: 'var(--color-danger, #DC2626)',
                      borderRadius: 'var(--radius-sm, 8px)',
                      fontSize: '0.8rem',
                      overflowWrap: 'anywhere',
                    }}
                  >
                    <strong style={{ fontWeight: 600 }}>เหตุผลที่ปฏิเสธ:</strong>{' '}
                    {row.reject_reason || 'ไม่ได้ระบุ'}
                  </div>
                )}

                {isPending && (
                  <div
                    style={{
                      display: 'flex',
                      gap: 8,
                      alignItems: 'flex-end',
                      flexWrap: 'wrap',
                      marginTop: 12,
                      paddingTop: 12,
                      borderTop: '1px solid var(--color-border)',
                    }}
                  >
                    <div className="form-group" style={{ margin: 0, minWidth: 190 }}>
                      <label className="form-label" htmlFor={`role-${row.id}`}>
                        บทบาทที่จะให้
                      </label>
                      <select
                        id={`role-${row.id}`}
                        className="form-input"
                        value={roleById[row.id] || row.requested_role || 'it_support'}
                        onChange={(e) => setRoleById((prev) => ({ ...prev, [row.id]: e.target.value }))}
                        disabled={busy}
                      >
                        {ROLE_OPTIONS.map((r) => (
                          <option key={r.value} value={r.value}>
                            {r.label}
                          </option>
                        ))}
                      </select>
                    </div>
                    <button
                      type="button"
                      className="btn btn-primary"
                      onClick={() => void handleApprove(row)}
                      disabled={busy}
                    >
                      {busy ? 'กำลังดำเนินการ...' : 'อนุมัติ'}
                    </button>
                    {rejectingId === row.id ? (
                      <>
                        <div className="form-group" style={{ margin: 0, flex: '1 1 220px' }}>
                          <label className="form-label" htmlFor={`reason-${row.id}`}>
                            เหตุผลที่ปฏิเสธ
                          </label>
                          <input
                            id={`reason-${row.id}`}
                            type="text"
                            className="form-input"
                            value={rejectReason}
                            onChange={(e) => setRejectReason(e.target.value)}
                            maxLength={500}
                            placeholder="เช่น ไม่ใช่เจ้าหน้าที่ของหน่วยงาน"
                            disabled={busy}
                          />
                        </div>
                        <button
                          type="button"
                          className="btn"
                          onClick={() => void handleReject(row)}
                          disabled={busy}
                          style={{ color: 'var(--color-danger)', fontWeight: 600 }}
                        >
                          ยืนยันปฏิเสธ
                        </button>
                        <button
                          type="button"
                          className="btn"
                          onClick={() => {
                            setRejectingId(null);
                            setRejectReason('');
                          }}
                          disabled={busy}
                        >
                          ยกเลิก
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        className="btn"
                        onClick={() => {
                          setRejectingId(row.id);
                          setRejectReason('');
                        }}
                        disabled={busy}
                      >
                        ปฏิเสธ
                      </button>
                    )}
                  </div>
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}