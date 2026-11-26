// ── แผนที่ไฟล์ ──────────────────────────────────────────────
// หน้าที่     : ตัวเลือกหน้า (ไม่มี router): หน้าสาธารณะเลือกจาก ?query, หน้าเจ้าหน้าที่จาก #/<เมนู>
// ข้อมูลจาก  : api/client.ts -> backend Render /api/* -> Supabase
// แผนที่หน้า : frontend/README.md  |  ภาพรวมระบบ: docs/SYSTEM_MAP.md
// ─────────────────────────────────────────────────────────
import React, { useState, useEffect, ReactNode } from 'react';
import ModalOverlay from './components/ModalOverlay';
import { DeviceInfo, Ticket, Stats, DeviceCreate, TicketCreate } from './types';
import { User, UserRole, Organization } from './types/user';
import { isRetiredRole } from './roleLabels';
import { DevicePageRole, DEVICE_PAGE_ROLES, DEVICE_PAGE_ROLE_BADGE } from './types/index';
import { api, login, setToken } from './api/client';
import StatCard from './components/StatCard';
import Sidebar, { visibleMenusForRole } from './components/Sidebar';
import SchoolsPage, { SchoolAdminView } from './components/SchoolsPage';
import ScanPage from './components/ScanPage';
import PublicNoLoginReportView from './components/PublicNoLoginReportView';
import PublicHomeView from './components/PublicHomeView';
import DevicesPage from './components/DevicesPage';
import DetailField from './components/DetailField';
import TicketsPage from './components/tickets/TicketsPage';
import { STATUS_LABELS_TICKET, ticketDetailPriority, ticketDetailStatus } from './components/tickets/ticketLabels';
import TeamPage from './components/dispatch/TeamPage';
import { saveRecent } from './publicRecent';
import DispatchOfferPopup from './components/dispatch/DispatchOfferPopup';
import UsersPage from './components/UsersPage';
import ReportsPage from './components/ReportsPage';
import SettingsPage from './components/SettingsPage';
import ProfilePage from './components/ProfilePage';
import KBPage from './components/KBPage';
import ChatbotStudioPage from './components/ChatbotStudioPage';
import QRBatchPage from './components/QRBatchPage';
import SalesPage from './components/SalesPage';
import PMPage from './components/PMPage';
import AuditLogPage from './components/AuditLogPage';
import RegistrationsPage from './components/RegistrationsPage';
import RegisterPage from './components/RegisterPage';
import CustomerSignupPage from './components/CustomerSignupPage';
import PrivacyPage from './components/PrivacyPage';
import { roleLabel } from './roleLabels';
import { REPORTER_TYPE_OPTIONS, DEFAULT_REPORTER_TYPE } from './reporterTypes';
import { useThemeVersion, themeColor, themeTint, cssVar } from './theme';
import './styles/dashboard.css';
// ดีไซน์ Calm: เลเยอร์ neon/futuristic ของหน้าแรกถูกลบออกแล้ว
// เพื่อให้สบายตาและเป็นทางการ — ไฟล์ยังเก็บไว้ ถ้าต้องการกลับมาใช้ให้ import คืน

/** กราฟ Dashboard โหลดแยกก้อน — recharts + d3 ราว 86 kB gzip
 *  หน้าอื่น (login / แจ้งซ่อมสาธารณะ / สแกน QR) จึงไม่ต้องดาวน์โหลดไลบรารีกราฟเลย
 *  ตัวกราฟทั้งหมดอยู่ใน components/DashboardCharts.tsx */
const DashboardCharts = React.lazy(() => import('./components/DashboardCharts'));

/** ที่ว่างระหว่างรอก้อนกราฟโหลด — ใช้คลาสเดิมเพื่อไม่ให้เลย์เอาต์กระโดด */
function ChartsFallback() {
  return (
    <div className="dsh-card">
      <div className="dsh-chart-box">
        <div className="dsh-empty" aria-live="polite">กำลังโหลดกราฟ…</div>
      </div>
    </div>
  );
}

// ─── Auth Context ────────────────────────────────────────────────────────────
const AuthContext = React.createContext<{
  user: User | null;
  isLoading: boolean;
  isAuthenticated: boolean;
  login: (user: User) => void;
  updateUser: (user: User) => void;
  logout: () => void;
}>({ user: null, isLoading: true, isAuthenticated: false, login: () => {}, updateUser: () => {}, logout: () => {} });

function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  useEffect(() => {
    const stored = localStorage.getItem('sc_user');
    const token = localStorage.getItem('sc_token');
    if (stored && token) {
      try {
        setUser(JSON.parse(stored));
        // validate token กับ backend — ถ้า expired ให้ logout
        api.authMe().then((r) => {
          setUser(r.user);
          localStorage.setItem('sc_user', JSON.stringify(r.user));
        }).catch(() => {
          localStorage.removeItem('sc_user');
          localStorage.removeItem('sc_token');
          setUser(null);
        });
      } catch {
        localStorage.removeItem('sc_user');
        localStorage.removeItem('sc_token');
      }
    }
    setIsLoading(false);
  }, []);

  const login = (u: User) => { setUser(u); localStorage.setItem('sc_user', JSON.stringify(u)); };
  const updateUser = (u: User) => { setUser(u); localStorage.setItem('sc_user', JSON.stringify(u)); };
  const logout = () => { setUser(null); localStorage.removeItem('sc_user'); localStorage.removeItem('sc_token'); };

  return (
    <AuthContext.Provider value={{ user, isLoading, isAuthenticated: !!user, login, updateUser, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

const useAuth = () => React.useContext(AuthContext);

/** หน้าปัจจุบันจาก URL แบบ #/tickets (null = ไม่มี) */
function menuFromHash(): string | null {
  const m = /^#\/([a-z_]+)/.exec(window.location.hash || '');
  return m ? m[1] : null;
}

// ─── Icon helpers ────────────────────────────────────────────────────────────
function AppLogo({ size = 22 }: { size?: number }) {
  return (
    <img
      src="/logo.jpg"
      alt="IWA"
      style={{ width: size, height: size, objectFit: 'contain', borderRadius: 4 }}
    />
  );
}

function SearchIcon() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <circle cx="11" cy="11" r="8"/>
      <path d="M21 21l-4.35-4.35"/>
    </svg>
  );
}

function BellIcon({ badge }: { badge?: number }) {
  return (
    <div className="header-icon-btn">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M18 8A6 6 0 006 8c0 7-3 9-3 9h18s-3-2-3-9"/>
        <path d="M13.73 21a2 2 0 01-3.46 0"/>
      </svg>
      {badge !== undefined && badge > 0 && <span className="header-notification-dot" />}
    </div>
  );
}

function CloseIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M18 6L6 18M6 6l12 12"/>
    </svg>
  );
}

function ChevronDownIcon() {
  return (
    <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <path d="M6 9l6 6 6-6"/>
    </svg>
  );
}

function DeviceIconSvg({ type }: { type: string }) {
  if (type.includes('Display') || type.includes('Interactive')) {
    return (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="2" y="4" width="20" height="14" rx="2"/>
        <path d="M2 10h20M12 14v6"/>
      </svg>
    );
  }
  if (type.includes('Computer') || type.includes('AIO') || type.includes('Notebook')) {
    return (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="4" width="18" height="12" rx="1"/>
        <path d="M8 20h8M12 16v4"/>
      </svg>
    );
  }
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
      <rect x="3" y="3" width="18" height="18" rx="2"/>
      <path d="M9 12h6M12 9v6"/>
    </svg>
  );
}

// ─── Status colors ──────────────────────────────────────────────────────────
const STATUS_COLOR_VARS: Record<string, string> = {
  new: '--status-new', assigned: '--status-assigned', in_progress: '--status-in-progress',
  pending: '--status-pending', resolved: '--status-resolved', closed: '--status-closed',
  cancelled: '--status-cancelled',
};

/** ค่าสำรองกรณีอ่าน CSS variable ไม่ได้ (เช่นเทสต์ที่ไม่มี DOM จริง) */
const STATUS_COLOR_FALLBACK: Record<string, string> = {
  new: '#EF4444', assigned: '#F59E0B', in_progress: '#2563EB',
  pending: '#8B5CF6', resolved: '#10B981', closed: '#6B7280', cancelled: '#EF4444',
};

/**
 * recharts รับสีเป็น attribute ของ <svg> ซึ่งไม่ขยาย var() ให้
 * จึงต้องอ่านค่าที่คำนวณแล้วทุกครั้งที่อ่านคีย์ — อ่านสด ๆ ผ่าน Proxy
 * ทำให้ทุกจุดที่เขียน STATUS_COLORS.xxx ได้สีของธีมปัจจุบันโดยไม่ต้องแก้
 */
const STATUS_COLORS: Record<string, string> = new Proxy({} as Record<string, string>, {
  get: (_target, key) => {
    const k = String(key);
    return cssVar(
      STATUS_COLOR_VARS[k] ?? '',
      STATUS_COLOR_FALLBACK[k] ?? '#6B7280',
    );
  },
  has: (_target, key) => String(key) in STATUS_COLOR_VARS,
  ownKeys: () => Object.keys(STATUS_COLOR_VARS),
  getOwnPropertyDescriptor: () => ({ enumerable: true, configurable: true }),
});

// ─── Login Page (จริง: username + password) ─────────────────────────────────
function LoginPage({ onLogin, onPrivacy }: { onLogin: (u: User) => void; onPrivacy?: () => void }) {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!username.trim() || !password) {
      setError('กรุณากรอกชื่อผู้ใช้และรหัสผ่าน');
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const resp = await login(username.trim(), password);
      setToken(resp.token);
      onLogin(resp.user);
    } catch (err: any) {
      setError(err.message || 'เข้าสู่ระบบไม่สำเร็จ');
    } finally {
      setLoading(false);
    }
  };

  // ─── ติดตามสถานะด้วยเลข Ticket (ไม่ต้อง login) ──────────────────
  const [showTrack, setShowTrack] = useState(false);
  const [tNo, setTNo] = useState('');
  const [tRes, setTRes] = useState<any | null>(null);
  const [tErr, setTErr] = useState<string | null>(null);
  const [tLoading, setTLoading] = useState(false);

  const handleTrack = async (e: React.FormEvent) => {
    e.preventDefault();
    const no = tNo.trim().toUpperCase();
    if (!no) { setTErr('กรอกหมายเลข Ticket (เช่น TK.TEST1.26.0001-V)'); return; }
    setTLoading(true); setTErr(null); setTRes(null);
    try {
      const r = await api.trackTicket(no);
      setTRes(r);
    } catch (err: any) {
      setTErr(err.message || 'ไม่พบหมายเลข Ticket นี้');
    } finally {
      setTLoading(false);
    }
  };

  const STATUS_TRACK_LABEL: Record<string, string> = {
    new: 'รอรับเรื่อง', assigned: 'มอบหมายแล้ว', in_progress: 'กำลังดำเนินการ',
    pending: 'รออะไหล่/รอภายนอก', resolved: 'ซ่อมเสร็จ รอยืนยัน', closed: 'ปิดงาน', cancelled: 'ยกเลิก',
  };

  return (
    <main className="login-page">
      <div className="login-card login-staff">
        {/* หน้า login เป็นหน้าแยกแล้ว — ต้องมีทางกลับหน้าแรกสาธารณะ */}
        <a href="/?home=1" className="login-back-link">← กลับไปหน้าบริการ</a>
        <div className="login-logo">
          <a href="https://iwa-web.onrender.com/" target="_blank" rel="noopener noreferrer" style={{ display: 'flex', alignItems: 'center', textDecoration: 'none', color: 'inherit' }}>
            <div className="login-logo-icon"><AppLogo size={22} /></div>
            <div>
              <h1 className="login-title">เข้าสู่ระบบเจ้าหน้าที่</h1>
              <p className="login-subtitle">IWA Smart Classroom Support</p>
            </div>
          </a>
        </div>
        <div className="login-divider" />
        <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 14 }}>
          <div className="form-group">
            <label className="form-label" htmlFor="staff-username">ชื่อผู้ใช้</label>
            <input
              type="text"
              className="form-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              id="staff-username"
              autoComplete="username"
              required
            />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="staff-password">รหัสผ่าน</label>
            <input
              type="password"
              className="form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              id="staff-password"
              autoComplete="current-password"
              required
            />
          </div>
          {error && (
            <div role="alert" style={{
              padding: '10px 14px', background: 'var(--color-danger-light)',
              color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)',
              fontSize: '0.8rem',
            }}>
              {error}
            </div>
          )}
          <button type="submit" className="btn btn-primary btn-full" style={{ padding: '12px' }} disabled={loading}>
            {loading ? (
              <>
                <span className="spinner" style={{ width: 14, height: 14, marginRight: 8, borderWidth: 2, display: 'inline-block' }} />
                กำลังเข้าสู่ระบบ…
              </>
            ) : (
              <>เข้าสู่ระบบ</>
            )}
          </button>
        </form>
        <div className="login-help" aria-label="ทางเลือกในการใช้บริการ">
          <a href="/?register=1">ขอเปิดบัญชีเจ้าหน้าที่</a>
          <a href="/?publicreport=1">แจ้งซ่อมอุปกรณ์</a>
          <button type="button" onClick={() => setShowTrack(true)}>ติดตามงานซ่อม</button>
          <button type="button" onClick={onPrivacy}>นโยบายความเป็นส่วนตัว</button>
        </div>

        {/* ─── Modal: ติดตามสถานะด้วยเลข Ticket (ไม่ต้อง login) ─── */}
        {showTrack && (
          <ModalOverlay label="ติดตามสถานะงานซ่อม" onClose={() => setShowTrack(false)} style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}>
            <div
              style={{
                width: 'min(440px, 100%)', background: 'var(--color-surface)',
                borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border)',
                padding: 24, position: 'relative', maxHeight: '85vh', overflowY: 'auto',
              }}
            >
              <button
                onClick={() => setShowTrack(false)}
                aria-label="ปิด"
                title="ปิด"
                style={{ position: 'absolute', top: 12, right: 12, border: 'none', background: 'transparent', cursor: 'pointer', lineHeight: 0, padding: 4, color: 'var(--color-text-tertiary)' }}
              >
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
                  <path d="M18 6L6 18M6 6l12 12" />
                </svg>
              </button>
              <h3 style={{ margin: '0 0 6px', fontSize: '1.1rem' }}>ติดตามสถานะงานซ่อม</h3>
              <p style={{ fontSize: '0.8rem', color: 'var(--color-text-tertiary)', margin: '0 0 16px' }}>
                กรอกหมายเลข Ticket ที่ได้รับตอนแจ้งซ่อม — ไม่ต้องเข้าสู่ระบบ
              </p>
              <form onSubmit={handleTrack} style={{ display: 'flex', gap: 8 }}>
                <input
                  className="form-input"
                  aria-label="เลขใบงาน"
                  placeholder="เช่น TK.SCHM01.26.0001-T"
                  value={tNo}
                  onChange={(e) => setTNo(e.target.value)}
                  style={{ flex: 1, textTransform: 'uppercase' }}
                />
                <button type="submit" className="btn btn-primary" disabled={tLoading}>
                  {tLoading ? 'กำลังค้นหา…' : 'ค้นหา'}
                </button>
              </form>

              {tErr && (
                <div style={{ marginTop: 14, padding: '10px 14px', background: 'var(--color-danger-light)', color: 'var(--color-danger)', borderRadius: 'var(--radius-sm)', fontSize: '0.82rem' }}>
                  {tErr}
                </div>
              )}

              {tRes && (
                <div style={{ marginTop: 18, borderTop: '1px solid var(--color-border)', paddingTop: 14 }}>
                  <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 }}>
                    <span style={{ fontWeight: 700 }}>{tRes.ticket_no}</span>
                    <span className={`badge badge-${tRes.status}`} style={{ fontSize: '0.72rem' }}>
                      {STATUS_TRACK_LABEL[tRes.status] || tRes.status_label || tRes.status}
                    </span>
                  </div>
                  <div style={{ fontSize: '0.85rem', marginBottom: 4 }}>{tRes.title}</div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)', marginBottom: 10 }}>
                    {tRes.device_code ? `${tRes.device_code} · ` : ''}{tRes.device_type || ''} {tRes.room_name ? ` · ${tRes.room_name}` : ''}
                  </div>
                  {/* Progress */}
                  {(tRes.progress || []).length > 0 && (
                    <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                      {(tRes.progress as any[]).map((p, i) => (
                        <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 8, fontSize: '0.8rem' }}>
                          <span style={{
                            width: 18, height: 18, borderRadius: '50%', flexShrink: 0,
                            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                            background: p.done ? 'var(--status-resolved, #10B981)' : 'var(--color-border)',
                            color: p.done ? '#FFFFFF' : 'var(--color-text-tertiary)',
                            fontSize: '0.6rem',
                          }}>
                            {p.done && (
                              <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                                <path d="M20 6L9 17l-5-5" />
                              </svg>
                            )}
                          </span>
                          <span style={{ color: p.done ? 'var(--color-text)' : 'var(--color-text-tertiary)' }}>{p.step}</span>
                        </div>
                      ))}
                    </div>
                  )}
                </div>
              )}
            </div>
          </ModalOverlay>
        )}
      </div>
    </main>
  );
}

// ─── Header ────────────────────────────────────────────────────────────────
function AppHeader({ pageTitle, user, onMenuToggle, devices, tickets, onNavigate, onOpenRecord, onLogout, sidebarOpen }: {
  pageTitle: string;
  user?: User | null;
  onMenuToggle?: () => void;
  sidebarOpen?: boolean;
  devices?: DeviceInfo[];
  tickets?: Ticket[];
  onNavigate?: (menu: string) => void;
  onOpenRecord?: (kind: 'devices' | 'tickets', id: string) => void;
  onLogout?: () => void;
}) {
  const [q, setQ] = useState('');
  const [popover, setPopover] = useState<'search' | 'notifications' | 'account' | null>(null);
  const headerRef = React.useRef<HTMLElement>(null);
  const triggerRef = React.useRef<HTMLButtonElement | null>(null);

  useEffect(() => {
    if (!popover) return;
    const closeOutside = (event: PointerEvent | FocusEvent) => {
      if (event.target instanceof Node && !headerRef.current?.contains(event.target)) setPopover(null);
    };
    document.addEventListener('pointerdown', closeOutside);
    document.addEventListener('focusin', closeOutside);
    return () => {
      document.removeEventListener('pointerdown', closeOutside);
      document.removeEventListener('focusin', closeOutside);
    };
  }, [popover]);

  const toggle = (next: NonNullable<typeof popover>, trigger: HTMLButtonElement) => {
    triggerRef.current = trigger;
    setPopover(popover === next ? null : next);
  };

  // ─── ค้นหา: อุปกรณ์ + Ticket ──────────────────────────────────────────
  const searchResults = (() => {
    const term = q.trim().toLowerCase();
    if (!term) return { devices: [], tickets: [] };
    const devs = (devices || []).filter((d) =>
      d.device_id.toLowerCase().includes(term) ||
      (d.device_type && d.device_type.toLowerCase().includes(term)) ||
      (d.brand && d.brand.toLowerCase().includes(term)) ||
      (d.model && d.model.toLowerCase().includes(term)) ||
      (d.room_name && d.room_name.toLowerCase().includes(term))
    ).slice(0, 5);
    const tks = (tickets || []).filter((t) =>
      t.ticket_id.toLowerCase().includes(term) ||
      t.title.toLowerCase().includes(term) ||
      (t.device_id && t.device_id.toLowerCase().includes(term))
    ).slice(0, 5);
    return { devices: devs, tickets: tks };
  })();

  // ─── แจ้งเตือน: Ticket ที่ยังไม่เสร็จ ───────────────────────────────────
  const openTickets = (tickets || []).filter((t) =>
    ['new', 'assigned', 'in_progress', 'pending'].includes(t.status)
  );

  const openRecord = (kind: 'devices' | 'tickets', id: string) => {
    setPopover(null);
    setQ('');
    onOpenRecord?.(kind, id);
  };

  return (
    <header className="app-header" ref={headerRef} onKeyDown={(event) => {
      if (event.key === 'Escape' && popover) {
        event.stopPropagation();
        setPopover(null);
        triggerRef.current?.focus();
      }
    }}>
      <div className="header-left">
        {onMenuToggle && (
          <button type="button" className="header-menu-toggle" onClick={onMenuToggle} aria-label="เปิดเมนูหลัก" aria-controls="workspace-sidebar" aria-expanded={sidebarOpen}>
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" aria-hidden="true"><path d="M3 6h18M3 12h18M3 18h18" /></svg>
          </button>
        )}
        <p className="header-page-title">{pageTitle}</p>
      </div>
      <div className="workspace-tools">
        <button type="button" className="workspace-tool workspace-search-trigger" aria-label="ค้นหาอุปกรณ์หรือใบงาน" aria-expanded={popover === 'search'} onClick={(event) => toggle('search', event.currentTarget)}>
          <SearchIcon /><span>ค้นหาอุปกรณ์หรือใบงาน</span>
        </button>
        <button type="button" className="workspace-tool" aria-label={openTickets.length ? 'งานค้าง ' + openTickets.length + ' รายการ' : 'งานค้าง'} aria-expanded={popover === 'notifications'} onClick={(event) => toggle('notifications', event.currentTarget)}>
          <BellIcon badge={openTickets.length} />
        </button>
        {user && (
          <button type="button" className="workspace-tool workspace-account" aria-label="เมนูบัญชี" aria-expanded={popover === 'account'} onClick={(event) => toggle('account', event.currentTarget)}>
            {user.line_picture_url ? <img className="header-user-avatar" src={user.line_picture_url} alt="" /> :
              <span className="header-user-avatar" aria-hidden="true">{(user.line_display_name || 'U').charAt(0).toUpperCase()}</span>}
            <span className="workspace-account-name">{user.line_display_name || 'ผู้ใช้'}</span>
            <ChevronDownIcon />
          </button>
        )}
      </div>
      {popover === 'search' && (
        <section className="workspace-popover workspace-search-panel" aria-label="ค้นหาในระบบ">
          <label className="form-label" htmlFor="workspace-search">ค้นหาอุปกรณ์หรือใบงาน</label>
          <input id="workspace-search" type="search" className="form-input" autoFocus value={q} onChange={(event) => setQ(event.target.value)} placeholder="รหัส ชื่ออุปกรณ์ หรือเลขใบงาน" />
          <div className="workspace-popover-list">
            {q.trim() && !searchResults.devices.length && !searchResults.tickets.length && <p className="workspace-popover-empty" role="status">ไม่พบรายการ ลองตรวจสอบรหัสหรือใช้คำค้นสั้นลง</p>}
            {searchResults.devices.length > 0 && <h2>อุปกรณ์</h2>}
            {searchResults.devices.map((device) => <button key={device.device_id} type="button" onClick={() => openRecord('devices', device.device_id)}>
              <strong>{device.device_id}</strong><span>{[device.device_type, device.room_name].filter(Boolean).join(' · ')}</span>
            </button>)}
            {searchResults.tickets.length > 0 && <h2>ใบงาน</h2>}
            {searchResults.tickets.map((ticket) => <button key={ticket.ticket_id} type="button" onClick={() => openRecord('tickets', ticket.ticket_id)}>
              <strong>{ticket.ticket_id}</strong><span>{ticket.title}</span>
            </button>)}
          </div>
        </section>
      )}
      {popover === 'notifications' && (
        <section className="workspace-popover" aria-label="งานค้าง">
          <h2>งานค้าง ({openTickets.length})</h2>
          <div className="workspace-popover-list">
            {!openTickets.length && <p className="workspace-popover-empty">ไม่มีงานค้าง</p>}
            {openTickets.slice(0, 10).map((ticket) => (
              <button key={ticket.ticket_id} type="button" onClick={() => openRecord('tickets', ticket.ticket_id)}>
                <strong>{ticket.ticket_id}</strong><span>{ticket.title}</span>
                <span className={'badge badge-' + ticket.status}>{STATUS_LABELS_TICKET[ticket.status] || ticket.status}</span>
              </button>
            ))}
          </div>
        </section>
      )}
      {popover === 'account' && user && (
        <section className="workspace-popover workspace-account-panel" aria-label="เมนูบัญชี">
          <h2>{user.line_display_name || 'ผู้ใช้'}</h2>
          <p>{roleLabel(user.role)}</p>
          <div className="workspace-popover-list">
            <button type="button" onClick={() => { setPopover(null); onNavigate?.('profile'); }}>โปรไฟล์</button>
            <button type="button" onClick={() => { setPopover(null); onNavigate?.('settings'); }}>การตั้งค่า</button>
            <button type="button" onClick={() => { setPopover(null); onLogout?.(); }}>ออกจากระบบ</button>
          </div>
        </section>
      )}
    </header>
  );
}

// ─── Dashboard Content ─────────────────────────────────────────────────────
function DashboardContent({
  onOpenRepairPanel,
  onOpenTicket,
  onOpenDevice,
  onNavigate,
  canScan,
  stats,
  tickets,
  devices,
  loading,
  needsOrgFilter,
  currentOrgId,
  userRole,
}: { 
  onOpenRepairPanel: (deviceId?: string) => void;
  /** กดแถวใบงานบน Dashboard → เปิดใบงานนั้นในหน้า Tickets */
  onOpenTicket?: (ticketId: string) => void;
  /** ปุ่ม "ดูรายละเอียด" บนการ์ดอุปกรณ์ → เปิดเครื่องนั้นในหน้าอุปกรณ์ */
  onOpenDevice?: (deviceId: string) => void;
  onNavigate: (menu: string) => void;
  canScan: boolean;
  stats: Stats | null;
  tickets: Ticket[];
  devices: DeviceInfo[];
  loading: boolean;
  needsOrgFilter: boolean;
  currentOrgId: number | null | undefined;
  userRole?: string;
}) {
  // ธีมเปลี่ยน → ต้อง re-render ให้ชาร์ตอ่าน token สีชุดใหม่ (var() ใช้ใน svg ไม่ได้)
  useThemeVersion();
  const [filterDevice, setFilterDevice] = useState('');
  const [filterStatus, setFilterStatus] = useState('');
  // หมวดหมู่อุปกรณ์ที่เลือกดู ('' = ทุกหมวดหมู่)
  const [deviceTypeFilter, setDeviceTypeFilter] = useState('');
  // โรงเรียนที่เลือกดู ('' = ทุกโรงเรียนที่มีสิทธิ์เห็น) — มีผลกับ Ticket, อุปกรณ์ และหมวดหมู่
  const [schoolFilter, setSchoolFilter] = useState('');

  // ─── บทบาทครู/นักเรียน: dashboard เบา ๆ เฉพาะของตัวเอง ─────────────────
  // บัญชีเก่าที่ยังติดบทบาท teacher/student (เลิกใช้แล้ว) — ให้เห็น dashboard แบบจำกัด
  const isLegacyReporterRole = isRetiredRole(userRole);
  const myTickets = tickets;
  const myOpenTickets = myTickets.filter((t) => ['new', 'assigned', 'in_progress', 'pending'].includes(t.status));
  const myResolved = myTickets.filter((t) => t.status === 'resolved' || t.status === 'closed');

  // หมายเหตุ: ข้อมูลกราฟย้ายไปคำนวณหลังบล็อกตัวกรองด้านล่าง
  // (ต้องใช้ filteredTicketsEntities / filteredDevices ซึ่งประกาศทีหลัง)

  // ─── ขอบเขตอุปกรณ์ตามสิทธิ์ + รายชื่อโรงเรียนที่มีอุปกรณ์จริง ───
  const UNKNOWN_SCHOOL = 'ไม่ระบุโรงเรียน';
  const schoolNameOf = (d: DeviceInfo): string =>
    d.organization_name || d.organization?.name || UNKNOWN_SCHOOL;

  const scopedDevices = devices.filter(
    (d) => !needsOrgFilter || d.organization_id === currentOrgId,
  );
  const schoolCounts = scopedDevices.reduce<Record<string, number>>((acc, d) => {
    const s = schoolNameOf(d);
    acc[s] = (acc[s] || 0) + 1;
    return acc;
  }, {});
  const schoolOptions = Object.keys(schoolCounts).sort((a, b) => a.localeCompare(b, 'th'));
  // ถ้าโรงเรียนที่เลือกไม่มีอยู่แล้ว (ข้อมูลเปลี่ยน) ให้ถือว่าดูทุกโรงเรียน
  const activeSchoolFilter = schoolOptions.includes(schoolFilter) ? schoolFilter : '';

  const filteredTicketsEntities = tickets.filter((t) => {
    if (needsOrgFilter && currentOrgId) {
      const dev = devices.find((d) => d.device_id === t.device_id);
      if (dev && dev.organization_id !== currentOrgId) return false;
    }
    if (activeSchoolFilter) {
      const dev = devices.find((d) => d.device_id === t.device_id);
      if (!dev || schoolNameOf(dev) !== activeSchoolFilter) return false;
    }
    if (filterDevice && t.device_id !== filterDevice) return false;
    if (filterStatus && t.status !== filterStatus) return false;
    return true;
  });

  const filteredDevices = scopedDevices.filter((d) => {
    if (!filterDevice) return true;
    const q = filterDevice.toLowerCase();
    return (
      d.device_id.toLowerCase().includes(q) ||
      d.device_type.toLowerCase().includes(q) ||
      (d.brand && d.brand.toLowerCase().includes(q)) ||
      (d.model && d.model.toLowerCase().includes(q)) ||
      (d.room_name && d.room_name.toLowerCase().includes(q))
    );
  }).filter((d) => !activeSchoolFilter || schoolNameOf(d) === activeSchoolFilter);

  // ─── หมวดหมู่อุปกรณ์ที่มีอยู่จริง + จำนวนของแต่ละหมวด (มาก → น้อย) ───
  const UNKNOWN_TYPE = 'ไม่ระบุประเภท';
  const deviceTypeCounts = filteredDevices.reduce<Record<string, number>>((acc, d) => {
    const t = d.device_type || UNKNOWN_TYPE;
    acc[t] = (acc[t] || 0) + 1;
    return acc;
  }, {});
  const deviceTypeOptions = Object.keys(deviceTypeCounts).sort(
    (a, b) => deviceTypeCounts[b] - deviceTypeCounts[a] || a.localeCompare(b, 'th'),
  );
  // ถ้าหมวดที่เลือกหายไป (เปลี่ยนตัวกรองอื่น) ให้ถือว่าแสดงทุกหมวด
  const activeTypeFilter = deviceTypeOptions.includes(deviceTypeFilter) ? deviceTypeFilter : '';
  const visibleDevices = activeTypeFilter
    ? filteredDevices.filter((d) => (d.device_type || UNKNOWN_TYPE) === activeTypeFilter)
    : filteredDevices;

  // ─── ข้อมูลกราฟ — คำนวณจาก "ผลหลังกรอง" ───────────────────────────────
  // เดิมอ่านจาก stats (ทั้งระบบ) ทำให้เลือกโรงเรียน/อุปกรณ์/สถานะแล้วกราฟนิ่งอยู่กับที่
  // ไม่ตรงกับตัวเลขในตารางด้านล่าง ตอนนี้ทุกกราฟใช้ชุดข้อมูลเดียวกับตาราง
  const ticketStatusCounts = filteredTicketsEntities.reduce<Record<string, number>>((acc, t) => {
    acc[t.status] = (acc[t.status] || 0) + 1;
    return acc;
  }, {});

  const statusChartData = [
    { key: 'new', name: 'เปิด', color: STATUS_COLORS.new },
    { key: 'assigned', name: 'รอซ่อม', color: STATUS_COLORS.assigned },
    { key: 'in_progress', name: 'กำลังดำเนินการ', color: STATUS_COLORS.in_progress },
    { key: 'pending', name: 'รออะไหล่/รอภายนอก', color: STATUS_COLORS.pending },
    { key: 'resolved', name: 'เสร็จสิ้น', color: STATUS_COLORS.resolved },
    { key: 'closed', name: 'ปิดงาน', color: STATUS_COLORS.closed },
    { key: 'cancelled', name: 'ยกเลิก', color: STATUS_COLORS.cancelled },
  ]
    .map(({ key, name, color }) => ({ name, value: ticketStatusCounts[key] ?? 0, color }))
    .filter((d) => d.value > 0);

  // Pie: สัดส่วนอุปกรณ์ตามประเภท — ใช้ยอดนับชุดเดียวกับตัวกรองหมวดหมู่
  // (deviceTypeOptions เรียงมาก→น้อยอยู่แล้ว) จานสีอยู่ใน DashboardCharts
  const deviceTypeData = deviceTypeOptions.map((name) => ({
    name,
    value: deviceTypeCounts[name] ?? 0,
  }));

  const monthlyData = (() => {
    const map = new Map<string, number>();
    filteredTicketsEntities.forEach((t) => {
      const d = new Date(t.created_at);
      if (Number.isNaN(d.getTime())) return;
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      map.set(key, (map.get(key) || 0) + 1);
    });
    return Array.from(map.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([month, value]) => ({ month, value }));
  })();

  // ป้ายกำกับช่วงปีของกราฟรายเดือน — คำนวณจากข้อมูลจริง (เดิม hardcode '2026')
  const monthlyRangeLabel = (() => {
    if (monthlyData.length === 0) return String(new Date().getFullYear());
    const firstYear = monthlyData[0].month.slice(0, 4);
    const lastYear = monthlyData[monthlyData.length - 1].month.slice(0, 4);
    return firstYear === lastYear ? firstYear : `${firstYear}–${lastYear}`;
  })();

  // ─── จัดกลุ่มอุปกรณ์ที่แสดง: โรงเรียน → หมวดหมู่ ────────────────────────
  // เดิมการ์ด "อุปกรณ์ทั้งหมด" เทรายการทุกโรงเรียนรวมในกริดเดียว ทำให้แยกไม่ออกว่า
  // เครื่องไหนอยู่โรงเรียนใด (ข้อมูลจริงมีหลายโรงเรียนและจำนวนไม่เท่ากัน)
  // จึงจัดเป็นกลุ่มต่อโรงเรียน เรียงจากโรงเรียนที่มีอุปกรณ์มากไปน้อย
  // และในแต่ละกลุ่มเรียงอุปกรณ์ตามหมวดใหญ่ → หมวดเล็ก แล้วไล่ตามรหัสเครื่อง
  const devicesBySchool = (() => {
    const groups = new Map<string, DeviceInfo[]>();
    visibleDevices.forEach((d) => {
      const s = schoolNameOf(d);
      const list = groups.get(s);
      if (list) list.push(d);
      else groups.set(s, [d]);
    });
    return Array.from(groups.entries())
      .map(([school, items]) => {
        const typeCounts = items.reduce<Record<string, number>>((acc, d) => {
          const t = d.device_type || UNKNOWN_TYPE;
          acc[t] = (acc[t] || 0) + 1;
          return acc;
        }, {});
        const types = Object.keys(typeCounts).sort(
          (a, b) => typeCounts[b] - typeCounts[a] || a.localeCompare(b, 'th'),
        );
        const sorted = [...items].sort((a, b) => {
          const ta = a.device_type || UNKNOWN_TYPE;
          const tb = b.device_type || UNKNOWN_TYPE;
          if (ta !== tb) return typeCounts[tb] - typeCounts[ta] || ta.localeCompare(tb, 'th');
          return a.device_id.localeCompare(b.device_id, 'th', { numeric: true });
        });
        return { school, items: sorted, types, typeCounts };
      })
      .sort((a, b) => b.items.length - a.items.length || a.school.localeCompare(b.school, 'th'));
  })();

  if (loading) return (
    <div className="dsh-loading" role="status" aria-live="polite">
      <div className="spinner" aria-hidden="true" />
      <span>กำลังโหลดภาพรวม…</span>
    </div>
  );

  // ─── Dashboard สำหรับครู/นักเรียน: เฉพาะของตัวเอง + แจ้งซ่อมเร็ว ──────────
  if (isLegacyReporterRole) {
    return (
      <div className="dsh-page">
        {/* Hero banner ต้อนรับ — สไตล์อยู่ในคลาส .dsh-hero (dashboard.css) เปลี่ยนตามธีมเอง */}
        <div className="dsh-hero">
          <div>
            <h1 className="dsh-hero-title">งานแจ้งซ่อมของฉัน</h1>
            <div className="dsh-hero-sub">
              ติดตามงานแจ้งซ่อมของคุณได้ที่นี่ — หากพบปัญหาอุปกรณ์ สแกน QR ที่ตัวเครื่องเพื่อแจ้งซ่อม
            </div>
          </div>
          <div className="dsh-hero-chips">
            <span className="dsh-chip">กำลังดำเนินการ {myOpenTickets.length}</span>
            <span className="dsh-chip">ซ่อมเสร็จ {myResolved.length}</span>
          </div>
        </div>

        {/* สถิติของฉัน — KPI ทันสมัย */}
        <div className="dsh-kpi-grid dsh-kpi-grid--compact">
          {[
            { icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4', value: myTickets.length, label: 'แจ้งซ่อมทั้งหมด', color: '--chart-1', sub: 'ทุกครั้ง' },
            { icon: 'M12 6v6l4 2', value: myOpenTickets.length, label: 'กำลังดำเนินการ', color: '--status-assigned', sub: 'ยังไม่เสร็จ' },
            { icon: 'M13 10V3L4 14h7v7l9-11h-7z', value: myResolved.length, label: 'ซ่อมเสร็จแล้ว', color: '--status-resolved', sub: 'แก้ไขได้แล้ว' },
          ].map((kpi) => (
            <div key={kpi.label} className="dsh-kpi">
              <div className="dsh-kpi-top">
                <div className="dsh-kpi-icon" style={{ background: themeTint(kpi.color, 0.1) }}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={themeColor(kpi.color)} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d={kpi.icon} /></svg>
                </div>
                <span className="dsh-kpi-sub">{kpi.sub}</span>
              </div>
              <div>
                <div className="dsh-kpi-value">{kpi.value}</div>
                <div className="dsh-kpi-label">{kpi.label}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Ticket ของฉัน */}
        <div className="dsh-card">
          <div className="dsh-card-head">
            <span className="dsh-card-title">Ticket ของฉัน</span>
            <span className="dsh-card-badge">{myTickets.length} รายการ</span>
          </div>
          <div className="dsh-card-body dsh-card-body--flush">
            {myTickets.length === 0 ? (
              <div className="dsh-empty">
                ยังไม่มี Ticket — สแกน QR ที่ตัวเครื่องเพื่อแจ้งซ่อม
              </div>
            ) : (
              <div className="dsh-table-wrap">
                <table className="dsh-table">
                  <thead>
                    <tr>
                      <th>Ticket ID</th><th>อุปกรณ์</th><th>หัวข้อ</th><th>สถานะ</th><th>ความเร่งด่วน</th><th>สร้างเมื่อ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {myTickets.slice(0, 8).map((ticket) => (
                      <tr key={ticket.ticket_id}>
                        <td className="dsh-td-id">{ticket.ticket_id}</td>
                        <td className="dsh-td-muted">{ticket.device_id}</td>
                        <td className="dsh-td-wrap">{ticket.title}</td>
                        <td>
                          <span className={`badge badge-${ticket.status}`}>
                            {STATUS_LABELS_TICKET[ticket.status] || ticket.status}
                          </span>
                        </td>
                        <td>
                          <span className={`badge badge-priority-${ticket.priority}`}>
                            {ticketDetailPriority[ticket.priority] || ticket.priority}
                          </span>
                        </td>
                        <td className="dsh-td-muted">
                          {new Date(ticket.created_at).toLocaleDateString('th-TH', { day: '2-digit', month: 'short', year: 'numeric' })}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="dsh-page">
      <section className="dsh-hero workspace-overview" aria-labelledby="workspace-overview-title">
        <div>
          <h1 className="dsh-hero-title" id="workspace-overview-title">งานซ่อมและอุปกรณ์</h1>
          <p className="dsh-hero-sub">ตรวจงานค้างและความพร้อมของอุปกรณ์ในที่เดียว</p>
        </div>
        <div className="workspace-overview-actions">
          <button type="button" className="btn btn-primary" onClick={() => onNavigate('tickets')}>ดูใบงาน</button>
          {canScan && <button type="button" className="btn btn-secondary" onClick={() => onNavigate('scan')}>สแกน QR</button>}
        </div>
      </section>

      {/* KPI Stat Cards — ทันสมัย */}
      <div className="dsh-kpi-grid">
        {[
          { icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4', value: stats?.total_tickets ?? 0, label: 'ใบงานทั้งหมด', color: '--chart-1', sub: 'ทุกสถานะ' },
          { icon: 'M12 6v6l4 2', value: stats?.new ?? 0, label: 'รอรับเรื่อง', color: '--status-assigned', sub: 'ยังไม่มีช่างรับ' },
          { icon: 'M13 10V3L4 14h7v7l9-11h-7z', value: stats?.in_progress ?? 0, label: 'กำลังดำเนินการ', color: '--status-in-progress', sub: 'อยู่ระหว่างซ่อม' },
          { icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z', value: stats?.resolved ?? 0, label: 'ซ่อมเสร็จ', color: '--status-resolved', sub: 'รอยืนยันหรือปิดงาน' },
          { icon: 'M12 19l9 2-9-18-9 18 9-2zm0 0v-8', value: stats?.high ?? 0, label: 'ความเร่งด่วนสูง', color: '--status-new', sub: 'ระดับสูงขึ้นไป' },
          { icon: 'M3 6h18M3 12h18M3 18h18', value: stats?.total_devices ?? 0, label: 'อุปกรณ์ทั้งหมด', color: '--color-muted', sub: 'ที่ลงทะเบียน' },
        ].map((kpi) => (
          <div key={kpi.label} className="dsh-kpi">
            <div className="dsh-kpi-top">
              <div className="dsh-kpi-icon" style={{ background: themeTint(kpi.color, 0.1) }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={themeColor(kpi.color)} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                  <path d={kpi.icon} />
                </svg>
              </div>
              <span className="dsh-kpi-sub">{kpi.sub}</span>
            </div>
            <div>
              <div className="dsh-kpi-value">{kpi.value}</div>
              <div className="dsh-kpi-label">{kpi.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* แถบตัวกรอง — ควบคุม schoolFilter / filterDevice / filterStatus ที่ประกาศไว้ด้านบน */}
      <div className="dsh-toolbar">
        {schoolOptions.length > 1 && (
          <div className="dsh-toolbar-field">
            <label className="dsh-toolbar-label" htmlFor="dsh-filter-school">โรงเรียน</label>
            <select
              id="dsh-filter-school"
              className="dsh-select"
              value={activeSchoolFilter}
              onChange={(e) => { setSchoolFilter(e.target.value); setFilterDevice(''); }}
            >
              <option value="">ทุกโรงเรียน ({scopedDevices.length} เครื่อง)</option>
              {schoolOptions.map((s) => (
                <option key={s} value={s}>{s} ({schoolCounts[s]})</option>
              ))}
            </select>
          </div>
        )}

        <div className="dsh-toolbar-field">
          <label className="dsh-toolbar-label" htmlFor="dsh-filter-device">อุปกรณ์</label>
          <select
            id="dsh-filter-device"
            className="dsh-select"
            value={filterDevice}
            onChange={(e) => setFilterDevice(e.target.value)}
          >
            <option value="">ทุกอุปกรณ์</option>
            {scopedDevices
              .filter((d) => !activeSchoolFilter || schoolNameOf(d) === activeSchoolFilter)
              .map((d) => (
                <option key={d.device_id} value={d.device_id}>
                  {d.device_id} · {d.device_type}
                  {d.room_name || d.room_code ? ` · ${d.room_name || d.room_code}` : ''}
                </option>
              ))}
          </select>
        </div>

        <div className="dsh-toolbar-field">
          <label className="dsh-toolbar-label" htmlFor="dsh-filter-status">สถานะใบงาน</label>
          <select
            id="dsh-filter-status"
            className="dsh-select"
            value={filterStatus}
            onChange={(e) => setFilterStatus(e.target.value)}
          >
            <option value="">ทุกสถานะ</option>
            {['new', 'assigned', 'in_progress', 'pending', 'resolved', 'closed', 'cancelled'].map((s) => (
              <option key={s} value={s}>{STATUS_LABELS_TICKET[s] || s}</option>
            ))}
          </select>
        </div>

        <button
          type="button"
          className="btn btn-ghost dsh-toolbar-reset"
          onClick={() => { setFilterDevice(''); setFilterStatus(''); setSchoolFilter(''); setDeviceTypeFilter(''); }}
          disabled={!filterDevice && !filterStatus && !activeSchoolFilter && !deviceTypeFilter}
        >
          ล้างตัวกรอง
        </button>

        {(filterDevice || filterStatus || activeSchoolFilter) && (
          <span className="dsh-toolbar-count" aria-live="polite">
            แสดง {filteredTicketsEntities.length} Ticket · {filteredDevices.length} อุปกรณ์
          </span>
        )}
      </div>

      {/* Charts + Pie — โหลดแยกก้อนตอนเปิดหน้า Dashboard (ดู DashboardCharts.tsx) */}
      <React.Suspense fallback={<ChartsFallback />}>
        <DashboardCharts
          statusData={statusChartData}
          monthlyData={monthlyData}
          monthlyRangeLabel={monthlyRangeLabel}
          deviceTypeData={deviceTypeData}
          totalDevices={filteredDevices.length}
        />
      </React.Suspense>

      {/* Tickets Table */}
      <div className="dsh-card">
        <div className="dsh-card-head">
          <span className="dsh-card-title">Ticket ล่าสุด</span>
          <span className="dsh-card-badge">{Math.min(filteredTicketsEntities.length, 10)} / {filteredTicketsEntities.length}</span>
        </div>
        <div className="dsh-card-body dsh-card-body--flush">
          {filteredTicketsEntities.length === 0 ? (
            <div className="dsh-empty">ยังไม่มี Ticket</div>
          ) : (
            <div className="dsh-table-wrap">
              <table className="dsh-table">
                <thead>
                  <tr>
                    <th>Ticket ID</th>
                    <th>อุปกรณ์</th>
                    <th>หัวข้อ</th>
                    <th>สถานะ</th>
                    <th>ความเร่งด่วน</th>
                    <th>สร้างเมื่อ</th>
                  </tr>
                </thead>
                <tbody>
                  {filteredTicketsEntities.slice(0, 10).map((ticket) => (
                    <tr key={ticket.ticket_id} className="dsh-row-link" tabIndex={0}
                      aria-label={`เปิดใบงาน ${ticket.ticket_id}`}
                      onClick={() => onOpenTicket?.(ticket.ticket_id)}
                      onKeyDown={(e) => { if (e.key === 'Enter') onOpenTicket?.(ticket.ticket_id); }}>
                      <td className="dsh-td-id">{ticket.ticket_id}</td>
                      <td>
                        <span style={{ fontWeight: 500 }}>{ticket.device_id}</span>
                      </td>
                      <td className="dsh-td-wrap">{ticket.title}</td>
                      <td>
                        <span className={`badge badge-${ticket.status}`}>
                          {ticketDetailStatus(ticket.status)}
                        </span>
                      </td>
                      <td>
                        <span className={`badge badge-priority-${ticket.priority}`}>
                          {ticketDetailPriority[ticket.priority] || ticket.priority}
                        </span>
                      </td>
                      <td className="dsh-td-muted">
                        {new Date(ticket.created_at).toLocaleDateString('th-TH', {
                          day: '2-digit', month: 'short', year: 'numeric',
                        })}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>

      {/* Device List */}
      <div className="dsh-card">
        <div className="dsh-card-head">
          <span className="dsh-card-title">อุปกรณ์ทั้งหมด</span>
          <span className="dsh-card-note">
            {activeSchoolFilter
              ? `${activeSchoolFilter} · `
              : `${devicesBySchool.length} โรงเรียน · `}
            {activeTypeFilter
              ? `${visibleDevices.length} เครื่อง · หมวด ${activeTypeFilter} (ทั้งหมด ${filteredDevices.length})`
              : `${filteredDevices.length} เครื่อง · ${deviceTypeOptions.length} หมวดหมู่ · สแกน QR ที่ตัวอุปกรณ์เพื่อแจ้งซ่อม`}
          </span>
          <select
            className="dsh-select"
            value={activeTypeFilter}
            onChange={(e) => setDeviceTypeFilter(e.target.value)}
            aria-label="เลือกหมวดหมู่อุปกรณ์"
            disabled={deviceTypeOptions.length === 0}
          >
            <option value="">ทุกหมวดหมู่อุปกรณ์</option>
            {deviceTypeOptions.map((t) => (
              <option key={t} value={t}>{t} ({deviceTypeCounts[t]})</option>
            ))}
          </select>
        </div>
        <div className="dsh-card-body dsh-card-body--flush">
          {visibleDevices.length === 0 ? (
            <div className="dsh-empty">
              {activeTypeFilter ? `ไม่มีอุปกรณ์ในหมวด "${activeTypeFilter}"` : 'ไม่มีอุปกรณ์'}
            </div>
          ) : (
            <div className="dsh-device-pane">
              {devicesBySchool.map((group) => (
                <section className="dsh-school-group" key={group.school}>
                  <div className="dsh-school-head">
                    <span className="dsh-school-name">{group.school}</span>
                    <span className="dsh-school-meta">
                      {group.items.length} เครื่อง · {group.types.length} หมวดหมู่
                    </span>
                  </div>
                  {/* ชิปหมวดหมู่ของโรงเรียนนี้ — กดเพื่อกรอง/ยกเลิกกรองหมวดเดียวกับ select ด้านบน */}
                  <div className="dsh-school-chips">
                    {group.types.map((t) => (
                      <button
                        type="button"
                        key={t}
                        className={activeTypeFilter === t ? 'dsh-type-chip is-active' : 'dsh-type-chip'}
                        aria-pressed={activeTypeFilter === t}
                        title={activeTypeFilter === t ? `ยกเลิกกรองหมวด ${t}` : `กรองเฉพาะหมวด ${t}`}
                        onClick={() => setDeviceTypeFilter(activeTypeFilter === t ? '' : t)}
                      >
                        <span className="dsh-type-chip-name">{t}</span>
                        <span className="dsh-type-chip-n">{group.typeCounts[t]}</span>
                      </button>
                    ))}
                  </div>
                  <div className="device-grid">
                    {group.items.map((device) => (
                      <div
                        key={device.device_id}
                        className="device-card"
                        onClick={() => onOpenRepairPanel(device.device_id)}
                      >
                        <div className="device-card-top">
                          <div className="device-card-icon-box">
                            <DeviceIconSvg type={device.device_type} />
                          </div>
                          <span className={`role-badge ${device.page_role ? (DEVICE_PAGE_ROLES[device.page_role] ?? 'other') : 'other'}`}>
                            {device.page_role === 'none' ? '-' : device.page_role ? (DEVICE_PAGE_ROLE_BADGE[device.page_role] ?? device.page_role) : '-'}
                          </span>
                        </div>
                        <div className="device-card-id">{device.device_id}</div>
                        <div className="device-card-type">{device.device_type}</div>
                        <div className="device-card-room">
                          {device.room_name || device.room_code || '—'}
                        </div>
                        <div className="device-card-bottom">
                          <div className="device-card-actions">
                            <button type="button" className="btn btn-primary btn-sm"
                              onClick={(e) => { e.stopPropagation(); onOpenRepairPanel(device.device_id); }}>
                              แจ้งซ่อม
                            </button>
                            {/* เดิมปุ่มนี้เปิดฟอร์มแจ้งซ่อมเหมือนปุ่มแรก — ตอนนี้เปิดข้อมูลเครื่องในหน้าอุปกรณ์ */}
                            <button type="button" className="btn btn-secondary btn-sm"
                              onClick={(e) => { e.stopPropagation(); (onOpenDevice ?? onOpenRepairPanel)(device.device_id); }}>
                              ดูรายละเอียด
                            </button>
                          </div>
                        </div>
                      </div>
                    ))}
                  </div>
                </section>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ─── Repair Panel (Right Slide-in) ──────────────────────────────────────────
function RepairPanel({ deviceId, onClose, onSubmit }: {
  deviceId?: string;
  onClose: () => void;
  onSubmit: (ticketId?: string) => void;
}) {
  const [form, setForm] = useState({
    title: '',
    description: '',
    reporter_name: '',
    reporter_email: '',
    reporter_phone: '',
    reporter_type: DEFAULT_REPORTER_TYPE,
    priority: 'normal',
  });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [recentTicket, setRecentTicket] = useState<any | null>(null);
  const [recentLoading, setRecentLoading] = useState(false);

  // โหลด Ticket ล่าสุดของอุปกรณ์ (ช่วยผู้ใช้ที่ลืมเลขหาเลขคืน)
  useEffect(() => {
    if (!deviceId) return;
    let cancelled = false;
    setRecentLoading(true);
    api.getDeviceRecent(deviceId)
      .then((r: any) => { if (!cancelled) setRecentTicket(r?.recent_ticket ?? null); })
      .catch(() => { if (!cancelled) setRecentTicket(null); })
      .finally(() => { if (!cancelled) setRecentLoading(false); });
    return () => { cancelled = true; };
  }, [deviceId]);

  const setField = (field: string, value: string) => {
    setForm((f) => ({ ...f, [field]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);

    if (!form.title.trim()) {
      setError('โปรดระบุหัวข้อ');
      setSubmitting(false);
      return;
    }

    try {
      const payload: TicketCreate = {
        device_id: deviceId || '',
        title: form.title,
        description: form.description,
        reporter_name: form.reporter_name,
        reporter_email: form.reporter_email,
        reporter_phone: form.reporter_phone,
        reporter_type: form.reporter_type,
        priority: form.priority,
        scan_gps_lat: null,
        scan_gps_lng: null,
        scan_timestamp: new Date().toISOString(),
        scan_user_agent: navigator.userAgent,
      };

      const result = await api.createTicket(payload);
      onSubmit(result.ticket_id);
    } catch (err: any) {
      const msg = err.message || 'เกิดข้อผิดพลาด';
      setError(msg);
      setSubmitting(false);
    }
  };

  return (
    <ModalOverlay labelledBy="staff-repair-title" onClose={() => { if (!submitting) onClose(); }}>
      <div className="repair-panel">
        <div className="repair-panel-header">
          <h2 className="repair-panel-title" id="staff-repair-title">แจ้งซ่อมอุปกรณ์</h2>
          <button type="button" className="repair-panel-close" onClick={onClose} disabled={submitting} aria-label="ปิดหน้าต่างแจ้งซ่อม">
            <CloseIcon />
          </button>
        </div>

        <div className="repair-panel-body">
          <form onSubmit={handleSubmit}>
            {deviceId && (
              <div className="device-select-card">
                <div className="device-select-icon">
                  <DeviceIconSvg type="อุปกรณ์" />
                </div>
                <div className="device-select-text">
                  <div className="device-select-name">{deviceId}</div>
                  <div className="device-select-sub">อุปกรณ์ที่เลือก</div>
                </div>
              </div>
            )}

            {/* การ์ด: งานแจ้งซ่อมล่าสุดของเครื่องนี้ (ช่วยหาเลขคืนถ้าลืม) */}
            {recentLoading && (
              <div style={{ fontSize: '0.8rem', color: 'var(--color-text-tertiary)', marginBottom: 'var(--spacing-md)' }}>
                กำลังตรวจสอบประวัติ…
              </div>
            )}
            {!recentLoading && recentTicket && (
              <div style={{
                padding: '12px 14px', marginBottom: 'var(--spacing-md)',
                background: 'var(--color-info-light)', borderRadius: 'var(--radius-sm)',
                fontSize: '0.85rem', color: 'var(--color-text)',
                border: '1px solid var(--color-border)',
              }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>
                  งานแจ้งซ่อมล่าสุดของเครื่องนี้
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <strong style={{ color: 'var(--color-primary)' }}>{recentTicket.ticket_id}</strong>
                  <span className={`badge badge-${recentTicket.status}`} style={{ fontSize: '0.68rem' }}>
                    {STATUS_LABELS_TICKET[recentTicket.status] || recentTicket.status}
                  </span>
                </div>
                <div style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary)', marginTop: 4 }}>
                  {recentTicket.title || ''}
                </div>
                <a
                  href="#"
                  style={{ display: 'inline-block', marginTop: 8, color: 'var(--color-primary)', fontWeight: 600, fontSize: '0.8rem' }}
                  onClick={(e) => { e.preventDefault(); window.location.href = `/?ticket=${encodeURIComponent(recentTicket.ticket_id)}`; }}
                >
                  ดูสถานะงานนี้ → (ไม่ต้องเข้าสู่ระบบ)
                </a>
              </div>
            )}

            <div className="form-group">
              <label className="form-label">
                หัวข้อ<span className="required">*</span>
              </label>
              <input
                type="text"
                className="form-input"
                value={form.title}
                onChange={(e) => setField('title', e.target.value)}
                placeholder="เช่น จอภาพไม่ติด, Wi-Fi ไม่เข้า"
                maxLength={200}
                required
              />
            </div>

            <div className="form-group">
              <label className="form-label">อาการละเอียด</label>
              <textarea
                className="form-textarea"
                value={form.description}
                onChange={(e) => setField('description', e.target.value)}
                placeholder="บรรยายอาการที่เกิดขึ้น…"
                rows={4}
              />
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">ชื่อผู้แจ้ง</label>
                <input
                  type="text"
                  className="form-input"
                  value={form.reporter_name}
                  onChange={(e) => setField('reporter_name', e.target.value)}
                  placeholder="ชื่อ-นามสกุล"
                />
              </div>
              <div className="form-group">
                <label className="form-label">ประเภท</label>
                <select
                  className="form-select"
                  value={form.reporter_type}
                  onChange={(e) => setField('reporter_type', e.target.value)}
                >
                  {REPORTER_TYPE_OPTIONS.map((opt) => (
                    <option key={opt.value} value={opt.value}>{opt.label}</option>
                  ))}
                </select>
              </div>
            </div>

            <div className="form-row">
              <div className="form-group">
                <label className="form-label">เบอร์ติดต่อ</label>
                <input
                  type="tel"
                  className="form-input"
                  value={form.reporter_phone}
                  onChange={(e) => setField('reporter_phone', e.target.value)}
                  placeholder="08xxx xxxx"
                />
              </div>
              <div className="form-group">
                <label className="form-label">อีเมล (optional)</label>
                <input
                  type="email"
                  className="form-input"
                  value={form.reporter_email}
                  onChange={(e) => setField('reporter_email', e.target.value)}
                  placeholder="email@example.com"
                />
              </div>
            </div>

            <div className="form-group">
              <label className="form-label">ระดับความเร่งด่วน</label>
              <select
                className="form-select"
                value={form.priority}
                onChange={(e) => setField('priority', e.target.value)}
              >
                <option value="low">Low — ไม่เร่งด่วน</option>
                <option value="normal">Normal — ปกติ</option>
                <option value="high">High — ค่อนข้างเร่งด่วน</option>
                <option value="critical">Critical — เร่งด่วนมาก</option>
              </select>
            </div>

            {error && (
              <div style={{
                padding: '10px 14px',
                background: 'var(--color-danger-light)',
                color: 'var(--color-danger)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.8rem',
                marginBottom: 'var(--spacing-md)',
              }}>
                {error}
              </div>
            )}

            <button
              type="submit"
              className="btn btn-primary btn-full"
              style={{ padding: '12px' }}
              disabled={submitting || !form.title.trim()}
            >
              {submitting ? (
                <>
                  <span className="spinner" style={{ width: 14, height: 14, marginRight: 8, borderWidth: 2, display: 'inline-block' }} />
                  กำลังส่ง…
                </>
              ) : (
                <>ส่งคำร้องแจ้งซ่อม</>
              )}
            </button>
          </form>
        </div>

        <div className="repair-panel-footer">
          <button type="button" className="btn btn-ghost" onClick={onClose} disabled={submitting}>ยกเลิก</button>
        </div>
      </div>
    </ModalOverlay>
  );
}

// ─── App (Root) ────────────────────────────────────────────────────────────
export default function App() {
  return (
    <AuthProvider>
      <AppInner />
    </AuthProvider>
  );
}

function AppInner() {
  const auth = useAuth();
  const [menu, setMenu] = useState('dashboard');
  const [pageTitle, setPageTitle] = useState('ภาพรวม');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const closeSidebar = React.useCallback(() => setSidebarOpen(false), []);
  const [selectedSchoolId, setSelectedSchoolId] = useState<number | null>(null);
  const [focusRecord, setFocusRecord] = useState<{ kind: 'devices' | 'tickets'; id: string } | null>(null);
  const [showRepairPanel, setShowRepairPanel] = useState(false);
  const [repairDeviceId, setRepairDeviceId] = useState<string | undefined>();
  const [ticketSubmitResult, setTicketSubmitResult] = useState<{ ticketId?: string } | null>(null);
  
  // Shared data state
  const [stats, setStats] = useState<Stats | null>(null);
  const [tickets, setTickets] = useState<Ticket[]>([]);
  const [devices, setDevices] = useState<DeviceInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [dataError, setDataError] = useState(false);
  const loadGeneration = React.useRef(0);

  const { user } = auth;
  // Owner/admin see every school; school-scoped roles only narrow further when
  // they actually have an organization. The API remains the authority for ACL.
  const needsOrgFilter = Boolean(user?.organization_id &&
    !['owner', 'super_admin', 'admin'].includes(user.role));
  const currentOrgId = user?.organization_id;

  // โหลดข้อมูลทั้งหมด (ใช้ซ้ำตอน refresh / submit / ลบ)
  const reloadData = React.useCallback(async () => {
    const generation = ++loadGeneration.current;
    setLoading(true);
    setDataError(false);
    try {
      const [s, t, d] = await Promise.all([
        api.getStats(),
        api.listAllTickets(),
        api.listAllDevices(),
      ]);
      if (generation !== loadGeneration.current) return;
      setStats(s);
      setTickets(t);
      setDevices(d);
    } catch {
      if (generation === loadGeneration.current) setDataError(true);
    } finally {
      if (generation === loadGeneration.current) setLoading(false);
    }
  }, []);

  // Fetch data (ครั้งแรก)
  useEffect(() => {
    if (!auth.isAuthenticated) {
      ++loadGeneration.current;
      setTicketSubmitResult(null);
      setStats(null);
      setTickets([]);
      setDevices([]);
      setLoading(false);
      return;
    }
    void reloadData();

    // ─── สแกน QR เข้ามา (คนที่มีบัญชี): URL มี ?device=DEV-xxxx → เปิดฟอร์มแจ้งซ่อมทันที
    //     หมายเหตุ: คนที่ยังไม่ login จะถูกจัดการที่ render (PublicReportView) ก่อนถึงตรงนี้ —
    //     effect นี้ล้าง URL ได้เฉพาะเมื่อ logged-in แล้ว เพื่อไม่ให้ไปตัด ?device= ของหน้า public
    const params = new URLSearchParams(window.location.search);
    const deviceParam = params.get('device');
    if (deviceParam) {
      openRepairPanel(deviceParam);
      // ล้าง query param ออกจาก URL (ไม่ให้กด refresh แล้วเปิดซ้ำ) — เฉพาะ logged-in
      window.history.replaceState({}, '', window.location.pathname);
    }
    // ─── ลิงก์งานจาก LINE ของช่าง: ?job=TK... → เปิดใบงานในแอปเจ้าหน้าที่ (มีปุ่มรับงาน)
    const jobParam = params.get('job');
    if (jobParam) {
      setFocusRecord({ kind: 'tickets', id: jobParam });
      handleMenuChange('tickets', { fromHistory: true });
      window.history.replaceState({}, '', `${window.location.pathname}#/tickets`);
    } else {
      // เปิดแอป/กดรีเฟรชที่ #/devices → กลับไปหน้าเดิม (ตรวจสิทธิ์ใน handleMenuChange)
      const fromHash = menuFromHash();
      if (fromHash && fromHash !== 'dashboard') handleMenuChange(fromHash, { fromHistory: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.isAuthenticated, reloadData]);

  // ─── ปุ่มย้อนกลับ/ไปข้างหน้าของเบราว์เซอร์ → เปลี่ยนหน้าตาม URL ─────────────
  useEffect(() => {
    if (!auth.isAuthenticated) return;
    const onPop = () => handleMenuChange(menuFromHash() || 'dashboard', { fromHistory: true });
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  });

  // ─── ฟัง event จาก SettingsPage (ปุ่ม "แก้ไขโปรไฟล์ →") ────────────────
  useEffect(() => {
    const handler = (e: Event) => {
      const menu = (e as CustomEvent).detail;
      if (typeof menu === 'string') handleMenuChange(menu);
    };
    window.addEventListener('navigate', handler);
    return () => window.removeEventListener('navigate', handler);
  });

  const handleMenuChange = (menu: string, opts: { fromHistory?: boolean } = {}) => {
    // Role guard: ถ้าเมนูไม่ได้รับอนุญาตสำหรับบทบาทนี้ → กลับ Dashboard
    const allowed = visibleMenusForRole(role, auth.user?.organization_id);
    if (!allowed.includes(menu)) menu = 'dashboard';
    setMenu(menu);
    setTicketSubmitResult(null);
    // หน้าอยู่ใน URL (#/tickets) — กดรีเฟรชแล้วอยู่หน้าเดิม ปุ่มย้อนกลับของเบราว์เซอร์ใช้ได้
    if (!opts.fromHistory && window.location.hash !== `#/${menu}`) {
      try {
        window.history.pushState({ menu }, '', `${window.location.pathname}#/${menu}`);
      } catch { /* โหมดจำกัดสิทธิ์ — ไม่มี URL ก็ยังใช้งานได้ */ }
    }
    if (menu === 'dashboard') reloadData();  // กลับหน้า Dashboard → ดึงข้อมูลใหม่เสมอ (ไม่ต้อง hard refresh)
    if (menu !== 'schools') setSelectedSchoolId(null);
    const titles: Record<string, string> = {
      dashboard: 'ภาพรวม',
      devices: 'อุปกรณ์',
      scan: 'สแกน QR',
      tickets: 'งานแจ้งซ่อม',
      team: 'ทีมช่าง',
      kb: 'ฐานความรู้',
      chatbot: 'จัดการ AI / LINE OA',
      ratings: 'ผลประเมินลูกค้า',
      qrbatch: 'พิมพ์ QR',
      pm: 'บำรุงรักษา (PM)',
      users: 'ผู้ใช้งาน',
      reports: 'รายงาน',
      audit: 'ประวัติการใช้งาน',
      sales: 'ลูกค้าและการขาย',
      registrations: 'อนุมัติเจ้าหน้าที่',
      schools: 'โรงเรียน',
      settings: 'การตั้งค่า',
      profile: 'โปรไฟล์',
    };
    setPageTitle(titles[menu] || menu);
    // หน้าใหม่เริ่มที่ด้านบนเสมอ (ไม่ค้างตำแหน่งเลื่อนของหน้าก่อน)
    window.scrollTo({ top: 0 });
  };

  const openRepairPanel = (deviceId?: string) => {
    setRepairDeviceId(deviceId);
    setShowRepairPanel(true);
  };

  const handleTicketSubmit = (ticketId?: string) => {
    setShowRepairPanel(false);
    setRepairDeviceId(undefined);
    setTicketSubmitResult({ ticketId });
    // Reload data
    reloadData();
  };

  if (auth.isLoading) return (
    <div className="boot" role="status">
      <div className="boot-inner">
        <img className="boot-logo" src="/logo.jpg" alt="" width="52" height="52" />
        <span className="boot-name">IWA Smart Classroom Support</span>
        <span className="boot-spin" aria-hidden="true" />
        <span className="boot-sub">กำลังเปิดระบบ…</span>
      </div>
    </div>
  );

  // ─── สแกน QR เข้ามา: URL มี ?device=DEV-xxxx → เปิดหน้าสาธารณะแจ้งซ่อมทันที (ไม่ต้อง login)
  //     ตรวจก่อน auth gate → ทั้งคนมีบัญชีและไม่มีบัญชี เห็นหน้าเดียวกัน
  const qrParams = new URLSearchParams(window.location.search);

  // ─── สมัครสมาชิกลูกค้า (ไม่ต้อง login): /?customer=1 → ฟอร์มฝากข้อมูลให้ทีมขายติดต่อกลับ
  //     คนละอย่างกับ /?register=1 ซึ่งเป็นการขอเปิดบัญชีเจ้าหน้าที่
  if (qrParams.get('customer') !== null) {
    return <CustomerSignupPage />;
  }

  if (qrParams.get('home') !== null) {
    return <PublicHomeView staffLoggedIn={auth.isAuthenticated} />;
  }

  // ─── สมัครสมาชิก (ไม่ต้อง login): /?register=1 → ฟอร์มขอเปิดบัญชีเจ้าหน้าที่
  //     ต้องตรวจก่อน auth gate เพื่อให้เข้าถึงได้ทั้งคนที่ยังไม่มีบัญชีและคนที่ล็อกอินอยู่
  if (qrParams.get('register') !== null) {
    return <RegisterPage />;
  }

  // ─── แจ้งซ่อมสาธารณะ (คนไม่มีบัญชี): ?publicreport=1 → ต้องตรวจก่อน ?device= / ?t=
  //     เพราะลิงก์จากการสแกนอาจเป็น ?publicreport=1&t=TOKEN — ฟอร์มสาธารณะ
  //     resolve token เองแล้วเติมโรงเรียน/อุปกรณ์ให้ ไม่ต้องเด้งไปหน้าอื่น
  if (qrParams.get('publicreport') === '1') {
    return <PublicNoLoginReportView />;
  }

  // ─── สแกน QR: ?device=DEV-xxxx หรือ ?t=TOKEN → ฟอร์มแจ้งซ่อมเดียวกับปุ่มบนหน้าแรก
  //     (ฟอร์มอ่าน t/device จาก URL เองแล้วล็อกอุปกรณ์ให้ทันที) — ลูกค้าเห็นฟอร์มเดียวเสมอ
  if (qrParams.get('device') || qrParams.get('t')) {
    return <PublicNoLoginReportView />;
  }

  // ─── ติดตามสถานะ: URL มี ?ticket=TK.SCHM01.26.0001-T (หรือ ?ticket= เปล่า)
  //     → หน้าแรกสาธารณะ เปิดพร้อมค้นเลขใบงานนั้นให้เลย
  const trackTicket = qrParams.get('ticket');
  if (trackTicket !== null) {
    return <PublicHomeView initialTicketId={trackTicket || undefined} />;
  }

  if (!auth.isAuthenticated) {
    // เปิดหน้า นโยบายความเป็นส่วนตัว ได้โดยไม่ต้อง login
    if (menu === 'privacy' || qrParams.get('privacy') !== null) {
      // ?privacy=1 มาจากลิงก์ท้ายหน้าแรกสาธารณะ → กดกลับแล้วไปหน้าแรก
      return (
        <PrivacyPage
          onBack={() => {
            if (qrParams.get('privacy') !== null) window.location.href = '/?home=1';
            else setMenu('dashboard');
          }}
        />
      );
    }
    // หน้าเข้าสู่ระบบเจ้าหน้าที่แยกเป็นอีกหน้า — เข้าถึงด้วย /?login=1 เท่านั้น
    // ?job= มาจากข้อความ LINE ของช่าง — ยังไม่ล็อกอินก็พาไปหน้าเข้าสู่ระบบ (URL คงไว้ เข้าแล้วเปิดใบงานต่อ)
    if (qrParams.get('login') !== null || qrParams.get('job') !== null) {
      return <LoginPage onLogin={auth.login} onPrivacy={() => setMenu('privacy')} />;
    }
    // หน้าแรก = หน้าสาธารณะ (ติดตามสถานะ + สแกนแจ้งซ่อม) ไม่ใช่หน้า login อีกแล้ว
    return <PublicHomeView />;
  }

  const role = auth.user?.role ?? 'super_admin';
  const DEVICE_PAGE_ROLE_KEY = role as DevicePageRole;
  const devicePageRole = DEVICE_PAGE_ROLES[DEVICE_PAGE_ROLE_KEY] ?? 'other';
  const devicePageRoleBadge = DEVICE_PAGE_ROLE_BADGE[DEVICE_PAGE_ROLE_KEY] ?? DEVICE_PAGE_ROLE_KEY;
  const canManage = ['owner', 'super_admin', 'admin', 'it_support', 'admin_school'].includes(role);
  // เห็นข้อมูลทุกโรงเรียน: owner/super_admin/admin + เจ้าหน้าที่ IT ที่ไม่มีสังกัด (สร้างโดยส่วนกลาง)
  const globalScope = ['owner', 'super_admin', 'admin'].includes(role)
    || (role === 'it_support' && !auth.user?.organization_id);

  const sidebarSchoolName = auth.user?.organization?.name ?? 'Smart Classroom Support';

  return (
    <>
      <div className="app-layout">
        <a className="skip-link" href="#main-content">ข้ามไปยังเนื้อหา</a>
        <Sidebar
          activeMenu={menu}
          onMenuChange={handleMenuChange}
          schoolName={sidebarSchoolName}
          userRole={auth.user?.role}
          userOrgId={auth.user?.organization_id}
          userName={auth.user?.line_display_name || auth.user?.line_user_id}
          userAvatar={auth.user?.line_picture_url}
          open={sidebarOpen}
          onClose={closeSidebar}
          onLogout={auth.logout}
        />

        <div className="main-column">
          <AppHeader
            pageTitle={pageTitle}
            user={auth.user}
            onMenuToggle={() => setSidebarOpen(true)}
            sidebarOpen={sidebarOpen}
            devices={devices}
            tickets={tickets}
            onNavigate={(m) => handleMenuChange(m)}
            onOpenRecord={(kind, id) => { setFocusRecord({ kind, id }); handleMenuChange(kind); }}
            onLogout={auth.logout}
          />

          <main className="app-main" id="main-content" tabIndex={-1}>
            {/* งานเด้งแบบ Grab — เฉพาะช่าง; ทำงานทุกหน้า ไม่ใช่แค่หน้าใบงาน */}
            {role === 'it_support' && (
              <DispatchOfferPopup onAccepted={(id) => { setFocusRecord({ kind: 'tickets', id }); handleMenuChange('tickets'); }} />
            )}
            {/* key={menu}: เปลี่ยนหน้า = เล่นแอนิเมชันเข้าใหม่ (เฟดขึ้นสั้น ๆ, ปิดเองเมื่อผู้ใช้ลดการเคลื่อนไหว) */}
            <div className="page-content page-enter" key={menu}>
              {ticketSubmitResult && (
                <div className="alert alert-success workspace-feedback">
                  <p role="status">แจ้งซ่อมเรียบร้อยแล้ว {ticketSubmitResult.ticketId && <strong>{ticketSubmitResult.ticketId}</strong>}</p>
                  <div>
                    {ticketSubmitResult.ticketId && <button type="button" className="btn btn-secondary" onClick={() => {
                      setFocusRecord({ kind: 'tickets', id: ticketSubmitResult.ticketId! });
                      handleMenuChange('tickets');
                    }}>ดูใบงาน</button>}
                    <button type="button" className="btn btn-ghost" onClick={() => setTicketSubmitResult(null)}>ปิด</button>
                  </div>
                </div>
              )}
              {dataError && (
                <div role="alert" className="alert alert-error">
                  โหลดข้อมูลล่าสุดไม่สำเร็จ กรุณาลองอีกครั้ง{' '}
                  <button type="button" onClick={() => { void reloadData(); }}>โหลดใหม่</button>
                </div>
              )}
              {menu === 'dashboard' && (
                <DashboardContent
                  onOpenRepairPanel={openRepairPanel}
                  onOpenTicket={(id) => { setFocusRecord({ kind: 'tickets', id }); handleMenuChange('tickets'); }}
                  onOpenDevice={(id) => { setFocusRecord({ kind: 'devices', id }); handleMenuChange('devices'); }}
                  onNavigate={handleMenuChange}
                  canScan={visibleMenusForRole(role, currentOrgId).includes('scan')}
                  stats={stats}
                  tickets={tickets}
                  devices={devices}
                  loading={loading}
                  needsOrgFilter={needsOrgFilter}
                  currentOrgId={currentOrgId}
                  userRole={auth.user?.role}
                />
              )}
              {menu === 'devices' && (
                <DevicesPage
                  onOpenTicket={(id) => { setFocusRecord({ kind: 'tickets', id }); handleMenuChange('tickets'); }}
                  focusId={focusRecord?.kind === 'devices' ? focusRecord.id : undefined}
                  onFocusHandled={() => setFocusRecord(null)}
                  onBack={() => handleMenuChange('dashboard')}
                  currentOrgId={currentOrgId}
                  isSuperAdmin={globalScope}
                  canManage={canManage}
                  userRole={role}
                />
              )}
              {menu === 'tickets' && (
                <TicketsPage
                  focusId={focusRecord?.kind === 'tickets' ? focusRecord.id : undefined}
                  onFocusHandled={() => setFocusRecord(null)}
                  onBack={() => handleMenuChange('dashboard')}
                  onTicketsChanged={reloadData}
                  canManage={canManage}
                  userRole={role}
                />
              )}
              {menu === 'team' && (
                <TeamPage
                  onBack={() => handleMenuChange('dashboard')}
                  onOpenTicket={(id) => { setFocusRecord({ kind: 'tickets', id }); handleMenuChange('tickets'); }}
                />
              )}
              {menu === 'kb' && (
                <KBPage onBack={() => handleMenuChange('dashboard')} userRole={role} userOrgId={auth.user?.organization_id} />
              )}
              {menu === 'chatbot' && ['owner', 'super_admin'].includes(role) && (
                <ChatbotStudioPage onBack={() => handleMenuChange('dashboard')} onNavigate={handleMenuChange} />
              )}
              {menu === 'ratings' && ['owner', 'super_admin'].includes(role) && (
                <ChatbotStudioPage ratingsOnly onBack={() => handleMenuChange('dashboard')} onNavigate={handleMenuChange} />
              )}
              {menu === 'qrbatch' && (
                <QRBatchPage onBack={() => handleMenuChange('dashboard')} />
              )}
              {menu === 'pm' && (
                <PMPage
                  onBack={() => handleMenuChange('dashboard')}
                  userRole={role}
                  isGlobalScope={globalScope}
                  currentOrgId={currentOrgId}
                />
              )}
              {menu === 'scan' && (
                <ScanPage
                  onScanDevice={openRepairPanel}
                  onBack={() => handleMenuChange('dashboard')}
                />
              )}
              {menu === 'schools' && !selectedSchoolId && (
                <SchoolsPage
                  onSelectSchool={(id) => setSelectedSchoolId(id)}
                  onBack={() => handleMenuChange('dashboard')}
                />
              )}
              {menu === 'schools' && selectedSchoolId && (
                <SchoolAdminView
                  orgId={selectedSchoolId}
                  canDelete={role === 'owner' || role === 'super_admin'}
                  onBack={() => setSelectedSchoolId(null)}
                />
              )}
              {menu === 'users' && (
                <UsersPage onBack={() => handleMenuChange('dashboard')} currentUserId={auth.user?.id} currentUserRole={auth.user?.role} />
              )}
              {menu === 'reports' && (
                <ReportsPage onBack={() => handleMenuChange('dashboard')} />
              )}
              {menu === 'audit' && (
                <AuditLogPage onBack={() => handleMenuChange('dashboard')} userRole={role} />
              )}
              {menu === 'registrations' && (
                <RegistrationsPage
                  onBack={() => handleMenuChange('dashboard')}
                  onOpenSales={() => handleMenuChange('sales')}
                />
              )}
              {menu === 'sales' && (
                <SalesPage onBack={() => handleMenuChange('dashboard')} userRole={auth.user?.role} />
              )}
              {menu === 'settings' && (
                <SettingsPage onBack={() => handleMenuChange('dashboard')} user={auth.user} />
              )}
              {menu === 'profile' && (
                <ProfilePage
                  user={auth.user}
                  onUpdateUser={auth.updateUser}
                  onBack={() => handleMenuChange('dashboard')}
                />
              )}
              {menu === 'privacy' && (
                <PrivacyPage onBack={() => handleMenuChange('dashboard')} />
              )}
            </div>
          </main>
        </div>

        {showRepairPanel && (
          <RepairPanel
            deviceId={repairDeviceId}
            onClose={() => { setShowRepairPanel(false); setRepairDeviceId(undefined); }}
            onSubmit={handleTicketSubmit}
          />
        )}

      </div>
    </>
  );
}
