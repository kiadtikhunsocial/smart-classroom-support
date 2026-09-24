import React, { useState, useEffect, ReactNode } from 'react';
import { DeviceInfo, Ticket, Stats, DeviceCreate, TicketCreate } from './types';
import { User, UserRole, Organization } from './types/user';
import { isRetiredRole } from './roleLabels';
import { DevicePageRole, DEVICE_PAGE_ROLES, DEVICE_PAGE_ROLE_BADGE } from './types/index';
import { api, login, setToken } from './api/client';
import StatCard from './components/StatCard';
import Sidebar, { ROLE_MENUS, LEGACY_FALLBACK_MENUS } from './components/Sidebar';
import SchoolsPage, { SchoolAdminView } from './components/SchoolsPage';
import ScanPage from './components/ScanPage';
import PublicNoLoginReportView from './components/PublicNoLoginReportView';
import PublicHomeView from './components/PublicHomeView';
import DevicesPage from './components/DevicesPage';
import AIChatWidget from './components/AIChatWidget';
import UsersPage from './components/UsersPage';
import ReportsPage from './components/ReportsPage';
import SettingsPage from './components/SettingsPage';
import ProfilePage from './components/ProfilePage';
import KBPage from './components/KBPage';
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
// เลเยอร์ธีม futuristic ของหน้าแรก — ต้องโหลด "หลัง" dashboard.css เพื่อทับค่าเดิมได้
// โดยไม่ใช้ !important (ทุก selector สโคปอยู่ใต้ .dsh-page จึงไม่กระทบหน้าอื่น)
import './styles/dashboard-futuristic.css';

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
    <div className="login-page">
      <div className="login-card">
        {/* หน้า login เป็นหน้าแยกแล้ว — ต้องมีทางกลับหน้าแรกสาธารณะ */}
        <a href="/" className="login-back-link">← กลับหน้าแรก (แจ้งซ่อม/ติดตามสถานะ)</a>
        <div className="login-logo">
          <a href="https://iwa-web.onrender.com/" target="_blank" rel="noopener noreferrer" style={{ display: 'flex', alignItems: 'center', textDecoration: 'none', color: 'inherit' }}>
            <div className="login-logo-icon"><AppLogo size={22} /></div>
            <div>
              <h1 className="login-title">IWA Smart Classroom Support</h1>
              <p className="login-subtitle">เข้าสู่ระบบสำหรับเจ้าหน้าที่</p>
            </div>
          </a>
        </div>
        <div className="login-divider" />
        <form onSubmit={handleSubmit} style={{ display: 'grid', gap: 14 }}>
          <div className="form-group">
            <label className="form-label">ชื่อผู้ใช้</label>
            <input
              type="text"
              className="form-input"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              placeholder="ชื่อผู้ใช้ (username)"
              autoFocus
            />
          </div>
          <div className="form-group">
            <label className="form-label">รหัสผ่าน</label>
            <input
              type="password"
              className="form-input"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              placeholder="รหัสผ่าน"
            />
          </div>
          {error && (
            <div style={{
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
                กำลังเข้าสู่ระบบ...
              </>
            ) : (
              <>เข้าสู่ระบบ</>
            )}
          </button>
        </form>
        <p className="login-note">
          เข้าสู่ระบบเพื่อจัดการแจ้งซ่อมอุปกรณ์และติดตามสถานะซ่อม
        </p>
        <div style={{ textAlign: 'center', marginTop: 8, fontSize: '0.8rem' }}>
          <span style={{ color: 'var(--color-text-tertiary)' }}>ยังไม่มีบัญชีเจ้าหน้าที่? </span>
          <a href="/?register=1" style={{ color: 'var(--color-primary)', fontWeight: 600 }}>
            สมัครสมาชิก (รอผู้ดูแลอนุมัติ)
          </a>
        </div>
        <div style={{ textAlign: 'center', marginTop: 8, fontSize: '0.8rem' }}>
          <span style={{ color: 'var(--color-text-tertiary)' }}>มีเลข Ticket แล้วแต่ยังไม่มีบัญชี? </span>
          <a
            href="#"
            style={{ color: 'var(--color-primary)', fontWeight: 600 }}
            onClick={(e) => { e.preventDefault(); setShowTrack(true); }}
          >
            ติดตามสถานะโดยไม่ต้องเข้าสู่ระบบ
          </a>
        </div>
        <div style={{ textAlign: 'center', marginTop: 14, fontSize: '0.8rem', borderTop: '1px solid var(--color-border)', paddingTop: 14 }}>
          <span style={{ color: 'var(--color-text-tertiary)' }}>ยังไม่มีบัญชี? </span>
          <a
            href="/?publicreport=1"
            style={{ color: 'var(--color-primary)', fontWeight: 600 }}
          >
            แจ้งซ่อม โดยไม่ต้องมีบัญชี
          </a>
        </div>
        <div style={{ textAlign: 'center', marginTop: 6, fontSize: '0.78rem' }}>
          <span style={{ color: 'var(--color-text-tertiary)' }}>การใช้งานเว็บไซต์นี้อยู่ภายใต้ </span>
          <a
            href="#"
            style={{ color: 'var(--color-primary)' }}
            onClick={(e) => { e.preventDefault(); onPrivacy?.(); }}
          >
            นโยบายความเป็นส่วนตัว
          </a>
        </div>

        {/* ─── Modal: ติดตามสถานะด้วยเลข Ticket (ไม่ต้อง login) ─── */}
        {showTrack && (
          <div
            className="panel-overlay"
            onClick={() => setShowTrack(false)}
            style={{ display: 'flex', alignItems: 'center', justifyContent: 'center', padding: '20px' }}
          >
            <div
              style={{
                width: 440, maxWidth: '92vw', background: 'var(--color-surface)',
                borderRadius: 'var(--radius-lg)', border: '1px solid var(--color-border)',
                padding: 24, position: 'relative', maxHeight: '85vh', overflowY: 'auto',
              }}
              onClick={(e) => e.stopPropagation()}
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
                  placeholder="TK.TEST1.26.0001-V"
                  value={tNo}
                  onChange={(e) => setTNo(e.target.value)}
                  style={{ flex: 1, textTransform: 'uppercase' }}
                />
                <button type="submit" className="btn btn-primary" disabled={tLoading}>
                  {tLoading ? '...' : 'ค้นหา'}
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
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Header ────────────────────────────────────────────────────────────────
function AppHeader({ pageTitle, user, onMenuToggle, devices, tickets, onNavigate, onLogout }: {
  pageTitle: string;
  user?: User | null;
  onMenuToggle?: () => void;
  devices?: DeviceInfo[];
  tickets?: Ticket[];
  onNavigate?: (menu: string) => void;
  onLogout?: () => void;
}) {
  const [q, setQ] = useState('');
  const [showResults, setShowResults] = useState(false);
  const [showNotif, setShowNotif] = useState(false);
  const [showUserMenu, setShowUserMenu] = useState(false);

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

  return (
    <header className="app-header">
      <div className="header-left">
        {onMenuToggle && (
          <button className="header-menu-toggle" onClick={onMenuToggle} aria-label="เปิดเมนู">
            <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M3 6h18M3 12h18M3 18h18"/>
            </svg>
          </button>
        )}
        <a href="/?home=1" aria-label="ไปหน้าแรกแจ้งซ่อม" style={{ display: 'inline-flex' }}><AppLogo size={22} /></a>
        <h2 className="header-page-title">{pageTitle}</h2>
      </div>
      <div className="header-right">
        {/* ค้นหา */}
        <div className="header-search" style={{ position: 'relative' }}>
          <span className="header-search-icon"><SearchIcon /></span>
          <input
            className="header-search-input"
            type="text"
            placeholder="ค้นหาอุปกรณ์ / Ticket..."
            value={q}
            onChange={(e) => { setQ(e.target.value); setShowResults(true); }}
            onFocus={() => setShowResults(true)}
            onBlur={() => setTimeout(() => setShowResults(false), 150)}
          />
          {showResults && q.trim() && (
            <div style={{
              position: 'absolute', top: 'calc(100% + 6px)', left: 0, right: 0,
              background: 'var(--color-surface)', border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-md)', boxShadow: '0 8px 24px rgba(0,0,0,0.1)',
              zIndex: 100, maxHeight: 320, overflow: 'auto', fontSize: '0.8rem',
            }}>
              {searchResults.devices.length === 0 && searchResults.tickets.length === 0 && (
                <div style={{ padding: 12, color: 'var(--color-text-tertiary)' }}>ไม่พบผลการค้นหา</div>
              )}
              {searchResults.devices.length > 0 && (
                <>
                  <div style={{ padding: '6px 12px', fontWeight: 600, color: 'var(--color-text-tertiary)', fontSize: '0.7rem', background: 'var(--color-bg)' }}>อุปกรณ์</div>
                  {searchResults.devices.map((d) => (
                    <button
                      key={d.device_id}
                      style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px', border: 'none', background: 'transparent', cursor: 'pointer', fontSize: '0.8rem', color: 'var(--color-text)' }}
                      onMouseDown={() => { onNavigate?.('devices'); setShowResults(false); setQ(''); }}
                    >
                      <span style={{ fontWeight: 600 }}>{d.device_id}</span>
                      <span style={{ color: 'var(--color-text-tertiary)', marginLeft: 6 }}>{d.device_type}{d.room_name ? ` · ${d.room_name}` : ''}</span>
                    </button>
                  ))}
                </>
              )}
              {searchResults.tickets.length > 0 && (
                <>
                  <div style={{ padding: '6px 12px', fontWeight: 600, color: 'var(--color-text-tertiary)', fontSize: '0.7rem', background: 'var(--color-bg)' }}>Ticket</div>
                  {searchResults.tickets.map((t) => (
                    <button
                      key={t.ticket_id}
                      style={{ display: 'block', width: '100%', textAlign: 'left', padding: '8px 12px', border: 'none', background: 'transparent', cursor: 'pointer', fontSize: '0.8rem', color: 'var(--color-text)' }}
                      onMouseDown={() => { onNavigate?.('tickets'); setShowResults(false); setQ(''); }}
                    >
                      <span style={{ fontWeight: 600 }}>{t.ticket_id}</span>
                      <span style={{ color: 'var(--color-text-tertiary)', marginLeft: 6 }}>{t.title}</span>
                    </button>
                  ))}
                </>
              )}
            </div>
          )}
        </div>

        {/* แจ้งเตือน */}
        <div style={{ position: 'relative' }}>
          <button
            onClick={() => setShowNotif(!showNotif)}
            style={{ background: 'none', border: 'none', cursor: 'pointer', position: 'relative', padding: 4 }}
            aria-label="แจ้งเตือน"
          >
            <BellIcon badge={openTickets.length} />
          </button>
          {showNotif && (
            <div style={{
              position: 'absolute', top: 'calc(100% + 6px)', right: 0, width: 320,
              background: 'var(--color-surface)', border: '1px solid var(--color-border)',
              borderRadius: 'var(--radius-md)', boxShadow: '0 8px 24px rgba(0,0,0,0.1)',
              zIndex: 100, maxHeight: 380, overflow: 'auto',
            }}>
              <div style={{ padding: '10px 14px', fontWeight: 600, fontSize: '0.85rem', borderBottom: '1px solid var(--color-border)' }}>
                การแจ้งเตือน ({openTickets.length})
              </div>
              {openTickets.length === 0 ? (
                <div style={{ padding: 20, textAlign: 'center', color: 'var(--color-text-tertiary)', fontSize: '0.8rem' }}>
                  ไม่มีงานค้าง
                </div>
              ) : (
                openTickets.slice(0, 10).map((t) => (
                  <button
                    key={t.ticket_id}
                    style={{ display: 'block', width: '100%', textAlign: 'left', padding: '10px 14px', border: 'none', borderBottom: '1px solid var(--color-border)', background: 'transparent', cursor: 'pointer' }}
                    onMouseDown={() => { onNavigate?.('tickets'); setShowNotif(false); }}
                  >
                    <div style={{ fontSize: '0.8rem', fontWeight: 600 }}>{t.ticket_id}</div>
                    <div style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary)', marginTop: 2 }}>{t.title}</div>
                    <span className={`badge badge-${t.status}`} style={{ fontSize: '0.68rem', marginTop: 4 }}>
                      {STATUS_LABELS_TICKET[t.status] || t.status}
                    </span>
                  </button>
                ))
              )}
            </div>
          )}
        </div>

        {user && (
          <div style={{ position: 'relative' }}>
            <button
              className="header-user"
              onClick={() => setShowUserMenu((v) => !v)}
              style={{ background: 'none', border: 'none', cursor: 'pointer', display: 'flex', alignItems: 'center', gap: 8, padding: 4 }}
              aria-label="เมนูผู้ใช้"
            >
              {user.line_picture_url ? (
                <img className="header-user-avatar" src={user.line_picture_url} alt="" style={{ objectFit: 'cover' }} />
              ) : (
                <div className="header-user-avatar">
                  {user.line_display_name?.charAt(0) || 'U'}
                </div>
              )}
              <div className="header-user-info">
                <span className="header-user-name">{user.line_display_name || 'ผู้ใช้'}</span>
                <span className="header-user-role">
                  {user.role}
                  <span className={`role-badge ${user.role}`} style={{ marginLeft: 6, verticalAlign: 'middle', fontSize: '0.6rem' }}>
                    {user.role}
                  </span>
                </span>
              </div>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ color: 'var(--color-text-tertiary)' }}>
                <path d="M6 9l6 6 6-6"/>
              </svg>
            </button>

            {/* Dropdown: โปรไฟล์ / การตั้งค่า / ออกจากระบบ */}
            {showUserMenu && (
              <>
                <div style={{ position: 'fixed', inset: 0, zIndex: 98 }} onClick={() => setShowUserMenu(false)} />
                <div style={{
                  position: 'absolute', top: 'calc(100% + 8px)', right: 0, width: 220,
                  background: 'var(--color-surface)', border: '1px solid var(--color-border)',
                  borderRadius: 'var(--radius-md)', boxShadow: '0 12px 32px rgba(0,0,0,0.14)',
                  zIndex: 99, overflow: 'hidden',
                }}>
                  <div style={{ padding: '12px 14px', borderBottom: '1px solid var(--color-border)', background: 'var(--color-bg)' }}>
                    <div style={{ fontWeight: 600, fontSize: '0.85rem' }}>{user.line_display_name || 'ผู้ใช้'}</div>
                    <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)', marginTop: 2 }}>
                      {roleLabel(user.role)}
                    </div>
                  </div>
                  <button
                    style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '11px 14px', border: 'none', background: 'transparent', cursor: 'pointer', fontSize: '0.85rem', color: 'var(--color-text)', textAlign: 'left' }}
                    onMouseDown={() => { setShowUserMenu(false); onNavigate?.('profile'); }}
                  >
                    โปรไฟล์
                  </button>
                  <button
                    style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '11px 14px', border: 'none', background: 'transparent', cursor: 'pointer', fontSize: '0.85rem', color: 'var(--color-text)', textAlign: 'left' }}
                    onMouseDown={() => { setShowUserMenu(false); onNavigate?.('settings'); }}
                  >
                    การตั้งค่า
                  </button>
                  <div style={{ borderTop: '1px solid var(--color-border)' }} />
                  <button
                    style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '11px 14px', border: 'none', background: 'transparent', cursor: 'pointer', fontSize: '0.85rem', color: 'var(--color-danger)', textAlign: 'left' }}
                    onMouseDown={() => { setShowUserMenu(false); onLogout?.(); }}
                  >
                    ออกจากระบบ
                  </button>
                </div>
              </>
            )}
          </div>
        )}
      </div>
    </header>
  );
}

// ─── Dashboard Content ─────────────────────────────────────────────────────
function DashboardContent({ 
  onOpenRepairPanel,
  stats,
  tickets,
  devices,
  loading,
  needsOrgFilter,
  currentOrgId,
  userRole,
}: { 
  onOpenRepairPanel: (deviceId?: string) => void;
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
      <div className="spinner" />
      <span>กำลังโหลดข้อมูล...</span>
    </div>
  );

  // ─── Dashboard สำหรับครู/นักเรียน: เฉพาะของตัวเอง + แจ้งซ่อมเร็ว ──────────
  if (isLegacyReporterRole) {
    return (
      <div className="dsh-page">
        {/* Hero banner ต้อนรับ — สไตล์อยู่ในคลาส .dsh-hero (dashboard.css) เปลี่ยนตามธีมเอง */}
        <div className="dsh-hero">
          <div>
            <div className="dsh-hero-title">สวัสดีครับ ยินดีต้อนรับ</div>
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
                            {ticket.priority}
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
      {/* Hero banner สรุปภาพรวม */}
      <div className="dsh-hero">
        <div>
          <div className="dsh-hero-title">ภาพรวมระบบซ่อมบำรุง</div>
          <div className="dsh-hero-sub">
            มี Ticket ทั้งหมด <b>{stats?.total_tickets ?? 0}</b> รายการ · กำลังดำเนินการ <b>{stats?.in_progress ?? 0}</b> · รอรับเรื่อง <b>{stats?.new ?? 0}</b>
          </div>
        </div>
        <div className="dsh-hero-chips">
          <span className="dsh-chip">เสร็จสิ้น {stats?.resolved ?? 0}</span>
          <span className="dsh-chip">อุปกรณ์ {stats?.total_devices ?? 0}</span>
        </div>
      </div>

      {/* KPI Stat Cards — ทันสมัย */}
      <div className="dsh-kpi-grid">
        {[
          { icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4', value: stats?.total_tickets ?? 0, label: 'Ticket ทั้งหมด', color: '--chart-1', sub: 'ทุกสถานะ' },
          { icon: 'M12 6v6l4 2', value: stats?.new ?? 0, label: 'รอรับเรื่อง', color: '--status-assigned', sub: 'ยังไม่มีช่างรับ' },
          { icon: 'M13 10V3L4 14h7v7l9-11h-7z', value: stats?.in_progress ?? 0, label: 'กำลังดำเนินการ', color: '--status-in-progress', sub: 'อยู่ระหว่างซ่อม' },
          { icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z', value: stats?.resolved ?? 0, label: 'ซ่อมเสร็จ', color: '--status-resolved', sub: 'รอ/ปิดงาน' },
          { icon: 'M12 19l9 2-9-18-9 18 9-2zm0 0v-8', value: stats?.high ?? 0, label: 'ความเร่งด่วนสูง', color: '--status-new', sub: 'high+critical' },
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
          <label className="dsh-toolbar-label" htmlFor="dsh-filter-status">สถานะ Ticket</label>
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
                    <tr key={ticket.ticket_id}>
                      <td className="dsh-td-id">{ticket.ticket_id}</td>
                      <td>
                        <span style={{ fontWeight: 500 }}>{ticket.device_id}</span>
                      </td>
                      <td className="dsh-td-wrap">{ticket.title}</td>
                      <td>
                        <span className={`badge badge-${ticket.status}`}>
                          {ticket.status.replace(/_/g, ' ')}
                        </span>
                      </td>
                      <td>
                        <span className={`badge badge-priority-${ticket.priority}`}>
                          {ticket.priority}
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
                            <button className="btn btn-primary btn-sm">
                              แจ้งซ่อม
                            </button>
                            <button className="btn btn-secondary btn-sm">
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

// ─── Tickets Page ───────────────────────────────────────────────────────────
const STATUS_LABELS_TICKET: Record<string, string> = {
  new: 'รอรับเรื่อง (New)', assigned: 'มอบหมายแล้ว (Assigned)', in_progress: 'กำลังดำเนินการ (In Progress)',
  pending: 'รออะไหล่/รอภายนอก (Pending)', waiting_parts: 'รออะไหล่ (Waiting for Parts)', waiting_user: 'รอผู้ใช้ (Waiting for User)',
  resolved: 'ซ่อมเสร็จ รอยืนยัน (Resolved)',
  closed: 'ปิดงาน (Closed)', cancelled: 'ยกเลิก (Cancelled)',
};
const ALL_STATUSES = Object.keys(STATUS_LABELS_TICKET);

function TicketsPage({ tickets, onBack, onTicketsChanged, canManage }: {
  tickets: Ticket[];
  onBack: () => void;
  onTicketsChanged: () => void;
  canManage: boolean;
}) {
  const [updating, setUpdating] = useState<string | null>(null);
  const [deleting, setDeleting] = useState<string | null>(null);
  const [detailTicket, setDetailTicket] = useState<any | null>(null);
  const [detailHistory, setDetailHistory] = useState<any[]>([]);
  const [detailComments, setDetailComments] = useState<any[]>([]);
  const [detailAttachments, setDetailAttachments] = useState<any[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  const [detailError, setDetailError] = useState('');
  const detailRequest = React.useRef(0);
  const openTicketDetail = async (ticket: Ticket) => {
    const requestId = ++detailRequest.current;
    setDetailTicket(ticket); setDetailLoading(true); setDetailError('');
    setDetailHistory([]); setDetailComments([]); setDetailAttachments([]);
    const [full, history, comments, attachments] = await Promise.allSettled([
      api.getTicket(ticket.ticket_id), api.getTicketHistory(ticket.ticket_id),
      api.listTicketComments(ticket.ticket_id), api.listTicketAttachments(ticket.ticket_id),
    ]);
    if (requestId !== detailRequest.current) return;
    if (full.status === 'fulfilled') setDetailTicket(full.value);
    else setDetailError('โหลดรายละเอียดล่าสุดไม่สำเร็จ กำลังแสดงข้อมูลจากรายการ');
    if (history.status === 'fulfilled') setDetailHistory(history.value);
    if (comments.status === 'fulfilled') setDetailComments(comments.value);
    if (attachments.status === 'fulfilled') setDetailAttachments(attachments.value);
    setDetailLoading(false);
  };
  const closeTicketDetail = () => { detailRequest.current += 1; setDetailTicket(null); };
  // ── ตัวกรองรายการ Ticket: คำค้น / สถานะ / ความเร่งด่วน / ประเภทอุปกรณ์ ──
  const [q, setQ] = useState('');
  const [fStatus, setFStatus] = useState('');
  const [fPriority, setFPriority] = useState('');
  const [fType, setFType] = useState('');
  const [fCategory, setFCategory] = useState('');
  // กรองเป็นหมวดโรงเรียน — เก็บเป็น organization_id (string) เพื่อไม่ชนกรณีชื่อซ้ำ
  const [fOrg, setFOrg] = useState('');

  // ประเภทอุปกรณ์เอาจากรายการที่มีจริง ไม่ต้องเรียก API เพิ่ม
  const deviceTypes = Array.from(
    new Set(tickets.map((t) => (t.device_type || '').trim()).filter(Boolean)),
  ).sort((a, b) => a.localeCompare(b, 'th'));

  // หมวดหมู่อุปกรณ์เอาจาก ticket ที่มีจริงเช่นกัน (backend map ประเภท → หมวดให้แล้ว)
  const deviceCategories = Array.from(
    new Set(tickets.map((t) => (t.device_category || '').trim()).filter(Boolean)),
  ).sort((a, b) => a.localeCompare(b, 'th'));

  // รายชื่อโรงเรียนจาก ticket ที่มองเห็นจริง (Map กัน id ซ้ำ) → [id, ป้ายที่แสดง]
  const ticketOrgs = Array.from(
    new Map(
      tickets
        .filter((t) => t.organization_id != null)
        .map((t) => [
          String(t.organization_id),
          `${t.organization_name || 'ไม่ระบุโรงเรียน'}${t.organization_code ? ` (${t.organization_code})` : ''}`,
        ] as [string, string]),
    ).entries(),
  ).sort((a, b) => a[1].localeCompare(b[1], 'th'));

  const kw = q.trim().toLowerCase();
  const filtered = tickets.filter((t) => {
    if (fStatus && t.status !== fStatus) return false;
    if (fPriority && t.priority !== fPriority) return false;
    if (fType && (t.device_type || '') !== fType) return false;
    if (fCategory && (t.device_category || '') !== fCategory) return false;
    if (fOrg && String(t.organization_id ?? '') !== fOrg) return false;
    if (!kw) return true;
    // ค้นด้วยชื่ออุปกรณ์/โรงเรียนได้ด้วย ไม่ใช่แค่รหัส
    return [
      t.ticket_id, t.device_id, t.device_label, t.device_category,
      t.organization_name, t.organization_code,
      t.title, t.reporter_name, t.description,
    ].some((v) => (v || '').toLowerCase().includes(kw));
  });
  const hasFilter = !!(kw || fStatus || fPriority || fType || fCategory || fOrg);
  const clearFilters = () => {
    setQ(''); setFStatus(''); setFPriority(''); setFType(''); setFCategory(''); setFOrg('');
  };

  const handleStatusChange = async (ticketId: string, newStatus: string) => {
    if (!newStatus) return;
    setUpdating(ticketId);
    try {
      await api.updateStatus(ticketId, { status: newStatus, author_name: 'ผู้ดูแลระบบ', force: true });
      onTicketsChanged();
    } catch (e: any) {
      alert('อัปเดตสถานะไม่สำเร็จ: ' + (e.message || ''));
    } finally {
      setUpdating(null);
    }
  };

  const handleDelete = async (ticketId: string) => {
    if (!window.confirm(`ลบ Ticket ${ticketId}? การลบไม่สามารถกู้คืนได้`)) return;
    setDeleting(ticketId);
    try {
      await api.deleteTicket(ticketId);
      onTicketsChanged();
    } catch (e: any) {
      alert('ลบไม่สำเร็จ: ' + (e.message || ''));
    } finally {
      setDeleting(null);
    }
  };

  return (
    <div className="page-content">
      <div className="top-bar">
        <div className="top-bar-title-group">
          <button className="btn btn-ghost btn-icon" onClick={onBack}>
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
              <path d="M19 12H5M12 19l-7-7 7-7"/>
            </svg>
          </button>
          <div>
            <h1 className="top-bar-title">Tickets</h1>
            <span className="top-bar-subtitle">
              {hasFilter ? `${filtered.length} / ${tickets.length} รายการ` : `${tickets.length} รายการ`}
            </span>
          </div>
        </div>
        <div className="top-bar-actions">
          <button className="btn btn-ghost" onClick={onTicketsChanged}>
            <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" style={{ marginRight: 6, verticalAlign: '-2px' }}>
              <path d="M21 12a9 9 0 11-3.5-7.1" />
              <path d="M21 3v6h-6" />
            </svg>
            รีเฟรช
          </button>
        </div>
      </div>

      <div className="page-section">
        <div className="section-body">
          <div
            style={{
              display: 'flex', flexWrap: 'wrap', gap: 8, alignItems: 'center',
              marginBottom: 'var(--spacing-md)',
            }}
          >
            <input
              className="form-input"
              style={{ flex: '1 1 200px', minWidth: 160, maxWidth: 340 }}
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="ค้นหา: เลข Ticket / อุปกรณ์ / หัวข้อ / ผู้แจ้ง"
              aria-label="ค้นหา Ticket"
            />
            <select
              className="form-select"
              style={{ flex: '0 1 190px', minWidth: 150 }}
              value={fStatus}
              onChange={(e) => setFStatus(e.target.value)}
              aria-label="กรองตามสถานะ"
            >
              <option value="">ทุกสถานะ</option>
              {ALL_STATUSES.map((s) => (
                <option key={s} value={s}>{STATUS_LABELS_TICKET[s]}</option>
              ))}
            </select>
            <select
              className="form-select"
              style={{ flex: '0 1 170px', minWidth: 140 }}
              value={fPriority}
              onChange={(e) => setFPriority(e.target.value)}
              aria-label="กรองตามความเร่งด่วน"
            >
              <option value="">ทุกความเร่งด่วน</option>
              <option value="low">low</option>
              <option value="normal">normal</option>
              <option value="high">high</option>
              <option value="critical">critical</option>
            </select>
            <select
              className="form-select"
              style={{ flex: '0 1 190px', minWidth: 150 }}
              value={fType}
              onChange={(e) => setFType(e.target.value)}
              aria-label="กรองตามประเภทอุปกรณ์"
              disabled={deviceTypes.length === 0}
            >
              <option value="">ทุกประเภทอุปกรณ์</option>
              {deviceTypes.map((dt) => (
                <option key={dt} value={dt}>{dt}</option>
              ))}
            </select>
            <select
              className="form-select"
              style={{ flex: '0 1 190px', minWidth: 150 }}
              value={fCategory}
              onChange={(e) => setFCategory(e.target.value)}
              aria-label="กรองตามหมวดหมู่อุปกรณ์"
              disabled={deviceCategories.length === 0}
            >
              <option value="">ทุกหมวดหมู่อุปกรณ์</option>
              {deviceCategories.map((dc) => (
                <option key={dc} value={dc}>{dc}</option>
              ))}
            </select>
            <select
              className="form-select"
              style={{ flex: '0 1 220px', minWidth: 160 }}
              value={fOrg}
              onChange={(e) => setFOrg(e.target.value)}
              aria-label="กรองตามโรงเรียน"
              disabled={ticketOrgs.length === 0}
            >
              <option value="">ทุกโรงเรียน</option>
              {ticketOrgs.map(([id, label]) => (
                <option key={id} value={id}>{label}</option>
              ))}
            </select>
            {hasFilter && (
              <button type="button" className="btn btn-ghost" onClick={clearFilters}>
                ล้างตัวกรอง
              </button>
            )}
          </div>
          {filtered.length === 0 ? (
            <div className="empty-state" style={{ padding: '32px 16px' }}>
              <svg className="empty-icon" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="5" width="18" height="14" rx="2"/>
                <path d="M3 10h18M8 20a2 2 0 004 0M12 20a2 2 0 004 0M16 20a2 2 0 004 0"/>
              </svg>
              <span className="empty-text">
                {tickets.length === 0 ? 'ไม่มี Ticket' : 'ไม่พบ Ticket ที่ตรงกับตัวกรอง'}
              </span>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>Ticket ID</th>
                    <th>อุปกรณ์</th>
                    <th>หัวข้อ</th>
                    <th>ผู้แจ้ง</th>
                    <th>สถานะ</th>
                    <th>ความเร่งด่วน</th>
                    <th>สร้างเมื่อ</th>
                    {canManage && <th>จัดการ</th>}
                  </tr>
                </thead>
                <tbody>
                  {filtered.map((ticket) => (
                    <tr key={ticket.ticket_id} className="clickable-data-row" tabIndex={0}
                      aria-label={`ดูรายละเอียด Ticket ${ticket.ticket_id}`}
                      onClick={(e) => { if (!(e.target as HTMLElement).closest('button, a, select, input')) void openTicketDetail(ticket); }}
                      onKeyDown={(e) => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); void openTicketDetail(ticket); } }}>
                      <td className="table-id">{ticket.ticket_id}</td>
                      <td>
                        <div className="table-meta">
                          <span style={{ fontWeight: 500 }}>{ticket.device_id}</span>
                          <span className="table-meta-row">
                            {ticket.device_label || ticket.device_type || ''}
                            {ticket.device_category ? ` · ${ticket.device_category}` : ''}
                            {ticket.organization_name ? ` · ${ticket.organization_name}` : ''}
                          </span>
                        </div>
                      </td>
                      <td>{ticket.title}</td>
                      <td>{ticket.reporter_name || '—'}</td>
                      <td>
                        {canManage ? (
                          <select
                            className="form-select"
                            style={{ width: 140, padding: '5px 8px', fontSize: '0.8rem' }}
                            value={ticket.status}
                            disabled={updating === ticket.ticket_id}
                            onChange={(e) => handleStatusChange(ticket.ticket_id, e.target.value)}
                          >
                            {ALL_STATUSES.map((s) => (
                              <option key={s} value={s}>{STATUS_LABELS_TICKET[s]}</option>
                            ))}
                          </select>
                        ) : (
                          <span className={`badge badge-${ticket.status}`}>
                            {STATUS_LABELS_TICKET[ticket.status] || ticket.status.replace(/_/g, ' ')}
                          </span>
                        )}
                      </td>
                      <td>
                        <span className={`badge badge-priority-${ticket.priority}`}>
                          {ticket.priority}
                        </span>
                      </td>
                      <td style={{ color: 'var(--color-text-tertiary)', fontSize: '0.8rem' }}>
                        {new Date(ticket.created_at).toLocaleDateString('th-TH', {
                          day: '2-digit', month: 'short', year: 'numeric',
                        })}
                      </td>
                      {canManage && (
                        <td style={{ display: 'flex', gap: 6 }}>
                          <button className="btn btn-secondary btn-sm" onClick={() => void openTicketDetail(ticket)}>รายละเอียด</button>
                          <button
                            className="btn btn-danger btn-sm"
                            disabled={deleting === ticket.ticket_id}
                            onClick={() => handleDelete(ticket.ticket_id)}
                            style={{ padding: '4px 10px', fontSize: '0.78rem' }}
                          >
                            {deleting === ticket.ticket_id ? 'ลบ...' : 'ลบ'}
                          </button>
                        </td>
                      )}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </div>
      </div>
      {detailTicket && <div className="panel-overlay" onClick={closeTicketDetail}>
        <div className="repair-panel" style={{ width: 680, maxWidth: '96vw' }} onClick={(e) => e.stopPropagation()} role="dialog" aria-modal="true" aria-label={`รายละเอียด Ticket ${detailTicket.ticket_id}`}>
          <div className="repair-panel-header"><h3 className="repair-panel-title">Ticket {detailTicket.ticket_id}</h3><button className="repair-panel-close" onClick={closeTicketDetail} aria-label="ปิด">×</button></div>
          <div className="repair-panel-body" style={{ overflowY: 'auto' }}>
            {detailLoading && <p>กำลังโหลดรายละเอียด...</p>}
            {detailError && <p role="alert">{detailError}</p>}
            <h3>{detailTicket.title}</h3>
            <div className="ticket-detail-grid">
              {([
                ['สถานะ', STATUS_LABELS_TICKET[detailTicket.status] || detailTicket.status],
                ['ความเร่งด่วน', detailTicket.priority], ['อุปกรณ์', detailTicket.device_label || detailTicket.device_id],
                ['รหัสอุปกรณ์', detailTicket.device_id], ['โรงเรียน', detailTicket.organization_name],
                ['ผู้แจ้ง', detailTicket.reporter_name], ['เบอร์ติดต่อ', detailTicket.reporter_phone],
                ['ผู้รับผิดชอบ', detailTicket.assigned_to], ['ช่องทาง', detailTicket.channel],
                ['สร้างเมื่อ', detailTicket.created_at && new Date(detailTicket.created_at).toLocaleString('th-TH')],
                ['อัปเดตล่าสุด', detailTicket.updated_at && new Date(detailTicket.updated_at).toLocaleString('th-TH')],
                ['กำหนด SLA', detailTicket.sla_due_at && new Date(detailTicket.sla_due_at).toLocaleString('th-TH')],
              ] as [string, any][]).map(([label, value]) => <div key={label}><small>{label}</small><div>{value || '—'}</div></div>)}
            </div>
            <h4>อาการ / รายละเอียด</h4><p style={{ whiteSpace: 'pre-wrap' }}>{detailTicket.description || 'ไม่มีรายละเอียดเพิ่มเติม'}</p>
            {detailTicket.root_cause && <><h4>สาเหตุ</h4><p style={{ whiteSpace: 'pre-wrap' }}>{detailTicket.root_cause}</p></>}
            {detailTicket.solution && <><h4>วิธีแก้ไข</h4><p style={{ whiteSpace: 'pre-wrap' }}>{detailTicket.solution}</p></>}
            <h4>ประวัติสถานะ</h4>{detailHistory.length ? detailHistory.map((h, i) => <p key={h.id || i}>{h.created_at ? new Date(h.created_at).toLocaleString('th-TH') : ''} · {STATUS_LABELS_TICKET[h.to_status] || h.to_status || 'อัปเดต'}{h.note ? ` — ${h.note}` : ''}</p>) : <p>ไม่มีประวัติสถานะ</p>}
            <h4>ความเห็น</h4>{detailComments.length ? detailComments.map((c, i) => <p key={c.id || i}>{c.author_name || 'เจ้าหน้าที่'}{c.is_internal ? ' (ภายใน)' : ''}: {c.note || '—'}</p>) : <p>ไม่มีความเห็น</p>}
            <h4>ไฟล์แนบ</h4>{detailAttachments.length ? detailAttachments.map((a, i) => <p key={a.id || i}><a href={a.file_url || a.url} target="_blank" rel="noreferrer">{a.file_name || a.filename || `ไฟล์ ${i + 1}`}</a></p>) : <p>ไม่มีไฟล์แนบ</p>}
          </div>
        </div>
      </div>}
    </div>
  );
}

// ─── Repair Panel (Right Slide-in) ──────────────────────────────────────────
function RepairPanel({ deviceId, onClose, onSubmit }: {
  deviceId?: string;
  onClose: () => void;
  onSubmit: (data: { success: boolean; ticket_id?: string }) => void;
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
  const [submitted, setSubmitted] = useState(false);
  const [successTicketId, setSuccessTicketId] = useState('');
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
      // ไม่ใส่เลขตัวอย่างปลอม ('SC-xxxx' เป็นรูปแบบเก่าและทำให้ผู้แจ้งจดเลขผิด)
      // ถ้า backend ไม่คืนเลขมา ให้เว้นไว้ แล้วให้ผู้ใช้ไปดูจากหน้าติดตามสถานะ
      setSuccessTicketId(result.ticket_id || '');
      setSubmitted(true);
      setTimeout(() => {
        onSubmit({ success: true, ticket_id: result.ticket_id });
      }, 1200);
    } catch (err: any) {
      const msg = err.message || 'เกิดข้อผิดพลาด';
      setError(msg);
      setSubmitting(false);
    }
  };

  return (
    <div className="panel-overlay" onClick={onClose}>
      <div className="repair-panel" onClick={(e) => e.stopPropagation()}>
        <div className="repair-panel-header">
          <h3 className="repair-panel-title">แจ้งซ่อมอุปกรณ์</h3>
          <button className="repair-panel-close" onClick={onClose}>
            <CloseIcon />
          </button>
        </div>

        <div className="repair-panel-body">
          {submitted ? (
            <div className="success-state">
              <div className="success-icon" aria-hidden="true">
                <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M20 6L9 17l-5-5" />
                </svg>
              </div>
              <div className="success-title">ส่งคำร้องเรียบร้อยแล้ว</div>
              <div className="success-sub">หมายเลข Ticket:</div>
              <div className="success-ticket-id">{successTicketId}</div>
              <div style={{ marginTop: 16, fontSize: '0.8rem', color: 'var(--color-text-secondary)', maxWidth: 280 }}>
                เจ้าหน้าที่จะดำเนินการตรวจสอบและซ่อมแซมภายใน 24 ชั่วโมง
              </div>
            </div>
          ) : (
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
                  กำลังตรวจสอบประวัติ...
                </div>
              )}
              {!recentLoading && recentTicket && !submitted && (
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
                  placeholder="บรรยายอาการที่เกิดขึ้น..."
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
                    กำลังส่ง...
                  </>
                ) : (
                  <>ส่งคำร้องแจ้งซ่อม</>
                )}
              </button>
            </form>
          )}
        </div>

        {!submitted && (
          <div className="repair-panel-footer">
            <button className="btn btn-ghost" onClick={onClose}>
              ยกเลิก
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Public Report (สแกน QR ไม่ต้อง login) ─────────────────────────────
function PublicReportView({ deviceId }: { deviceId: string }) {
  const [device, setDevice] = useState<DeviceInfo | null>(null);
  const [deviceLoading, setDeviceLoading] = useState(true);
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
  const [submitted, setSubmitted] = useState(false);
  const [ticketId, setTicketId] = useState('');
  const [attachments, setAttachments] = useState<string[]>([]);
  const [uploading, setUploading] = useState(false);
  // AI วินิจฉัย (KB)
  const [diag, setDiag] = useState<any | null>(null);
  const [diagLoading, setDiagLoading] = useState(false);
  // กันแจ้งซ้ำ (409)
  const [dupAlert, setDupAlert] = useState<{
    existing_ticket_no?: string;
    existing_status?: string;
    existing_status_label?: string;
    existing_device_label?: string;
    existing_title?: string;
    can_add_note?: boolean;
  } | null>(null);
  // งานค้างที่ตรวจล่วงหน้าตอนเปิดหน้า — ไม่ต้องให้ผู้แจ้งกรอกทั้งใบแล้วค่อยเจอ 409
  const [openTicket, setOpenTicket] = useState<any | null>(null);
  // แจ้งอาการ/ข้อมูลเพิ่มเข้าใบเดิมที่ยังไม่ปิด — ใช้แทนการเปิดใบซ้ำ
  const [noteText, setNoteText] = useState('');
  const [noteSending, setNoteSending] = useState(false);
  const [noteError, setNoteError] = useState<string | null>(null);
  const [noteDone, setNoteDone] = useState<string | null>(null);
  // เลื่อนหน้าจอไปที่กล่องงานค้างเมื่อกดส่งแล้วเจอ 409 (กล่องอยู่เหนือฟอร์ม อาจพ้นจอ)
  const blockRef = React.useRef<HTMLDivElement | null>(null);
  // งานล่าสุดของเครื่อง (ช่วยหาเลขคืนถ้าลืม — ตรงตามที่ต้องการ)
  const [recentTicket, setRecentTicket] = useState<any | null>(null);
  const [recentLoading, setRecentLoading] = useState(false);

  // โหลดข้อมูลอุปกรณ์จาก ?device= (ห้อง/ยี่ห้อ/รุ่น — ตาม TOR: QR มีแค่ URL+device token)
  useEffect(() => {
    api.getDevice(deviceId)
      .then((d) => { setDevice(d); setDeviceLoading(false); })
      .catch(() => { setDeviceLoading(false); });
    // โหลด ticket ล่าสุดของอุปกรณ์นี้
    api.getDeviceRecent(deviceId)
      .then((r: any) => { setRecentTicket(r?.recent_ticket ?? null); setRecentLoading(false); })
      .catch(() => { setRecentLoading(false); });
    // อุปกรณ์นี้มีงานค้างอยู่ไหม — รู้ก่อนกรอก จะได้แจ้งเพิ่มเข้าใบเดิมแทนการเปิดใบซ้ำ
    api.publicDeviceOpenTicket(deviceId)
      .then((r: any) => { setOpenTicket(r?.has_open_ticket ? (r.open_ticket ?? null) : null); })
      .catch(() => { setOpenTicket(null); });
  }, [deviceId]);

  const setField = (field: string, value: string) => {
    setForm((f) => ({ ...f, [field]: value }));
  };

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setSubmitting(true);
    setError(null);
    setNoteError(null);
    setNoteDone(null);

    if (!form.title.trim()) {
      setError('โปรดระบุหัวข้อ');
      setSubmitting(false);
      return;
    }

    // มีใบงานค้างอยู่แล้ว → ไม่ต้องยิงให้ backend ตอบ 409 ซ้ำ ชี้ไปที่ช่องแจ้งเพิ่มเลย
    if (openTicket && openTicket.can_add_note !== false) {
      setError(
        `อุปกรณ์นี้มีใบงานค้างอยู่ (${openTicket.ticket_no || '-'}) — ` +
        'กรุณาแจ้งอาการเพิ่มเข้าใบเดิมในกล่องด้านบน ระบบไม่สร้าง Ticket ซ้ำ'
      );
      setSubmitting(false);
      blockRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
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
        attachments: attachments.length > 0 ? attachments : undefined,
        ai_session_id: diag?.session_id,
        scan_gps_lat: null,
        scan_gps_lng: null,
        scan_timestamp: new Date().toISOString(),
        scan_user_agent: navigator.userAgent,
      };

      const result = await api.createTicket(payload);
      setTicketId(result.ticket_id || '-');
      setSubmitted(true);
    } catch (err: any) {
      // กันแจ้งซ้ำ: อุปกรณ์มี ticket ค้างอยู่ (409 DUPLICATE_OPEN_TICKET)
      if (err?.status === 409 && err?.code === 'DUPLICATE_OPEN_TICKET') {
        const d = err.detail || {};
        setDupAlert({
          existing_ticket_no: d.existing_ticket_no,
          existing_status: d.existing_status,
          existing_status_label: d.existing_status_label || d.open_ticket?.status_label,
          existing_device_label: d.existing_device_label || d.open_ticket?.device_label,
          existing_title: d.existing_title || d.open_ticket?.title,
          can_add_note: d.can_add_note !== false,
        });
        setError('อุปกรณ์นี้มีใบงานค้างอยู่ — แจ้งอาการเพิ่มเข้าใบเดิมได้ในกล่องด้านบน');
        // กล่องรายละเอียด + ช่องแจ้งเพิ่มอยู่เหนือฟอร์ม เลื่อนไปให้เห็นหลัง state อัปเดต
        setTimeout(
          () => blockRef.current?.scrollIntoView({ behavior: 'smooth', block: 'center' }),
          0,
        );
      } else {
        setError(err.message || 'เกิดข้อผิดพลาด');
      }
      setSubmitting(false);
    }
  };

  /** ส่งอาการ/ข้อมูลเพิ่มเข้า Ticket เดิม (ไม่ต้องล็อกอิน) — ไม่เปลี่ยนสถานะงาน ไม่ทับข้อมูลเดิม */
  const handleAddNote = async () => {
    const ticketNo = (dupAlert?.existing_ticket_no || openTicket?.ticket_no || '').trim();
    if (!ticketNo) return;
    const note = noteText.trim();
    const name = form.reporter_name.trim();
    if (note.length < 3) {
      setNoteError('กรุณาระบุอาการหรือข้อมูลที่ต้องการแจ้งเพิ่ม (อย่างน้อย 3 ตัวอักษร)');
      return;
    }
    if (!name) {
      setNoteError('กรุณากรอกชื่อผู้แจ้งในฟอร์มด้านล่างก่อน');
      return;
    }
    setNoteError(null);
    setNoteDone(null);
    setNoteSending(true);
    try {
      const res = await api.publicAddTicketNote(ticketNo, {
        note,
        reporter_name: name,
        reporter_phone: form.reporter_phone.trim() || undefined,
        attachments: attachments.length > 0 ? attachments : undefined,
      });
      setNoteDone(res?.message || `บันทึกข้อมูลเพิ่มเข้า Ticket ${ticketNo} เรียบร้อยแล้ว`);
      setNoteText('');
    } catch (err: any) {
      if (err?.status === 409) {
        // งานถูกปิดไปแล้วระหว่างที่ผู้แจ้งกรอก → เปิดทางให้แจ้งซ่อมใบใหม่
        setNoteError(err?.detail?.message || err?.message || 'Ticket นี้ปิดงานแล้ว — กรุณาแจ้งซ่อมใหม่');
        setDupAlert((d) => (d ? { ...d, can_add_note: false } : d));
        setOpenTicket((t: any) => (t ? { ...t, can_add_note: false } : t));
      } else {
        setNoteError(err?.message || 'ส่งข้อมูลเพิ่มไม่สำเร็จ กรุณาลองอีกครั้ง');
      }
    } finally {
      setNoteSending(false);
    }
  };

  // อัปโหลดรูปแนบ (TOR 1.5.2 — ฟอร์มแจ้งซ่อมต้องมีรูปได้)
  const handleUpload = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const files = e.target.files;
    if (!files || files.length === 0) return;
    setUploading(true);
    setError(null);
    try {
      const urls: string[] = [];
      for (const f of Array.from(files).slice(0, 3)) {
        const r = await api.upload(f);
        urls.push(r.url);
      }
      setAttachments((prev) => [...prev, ...urls]);
    } catch (err: any) {
      setError(err.message || 'อัปโหลดรูปไม่สำเร็จ');
    } finally {
      setUploading(false);
      if (e.target) e.target.value = '';
    }
  };

  // AI วินิจฉัยจาก KB (ไม่ใช้ LLM ให้เดา — ตอบจากฐานความรู้เท่านั้น)
  const runDiagnose = async () => {
    if (!form.title.trim()) {
      setError('กรอกหัวข้อ/อาการก่อนกดวินิจฉัย');
      return;
    }
    setDiagLoading(true);
    setError(null);
    try {
      const r = await api.diagnose({
        device_id: deviceId || undefined,
        device_type: device?.device_type || undefined,
        symptom_text: `${form.title} ${form.description || ''}`.trim(),
      });
      setDiag(r);
    } catch (err: any) {
      setError(err.message || 'ระบบวินิจฉัยไม่พร้อมใช้งานชั่วคราว');
    } finally {
      setDiagLoading(false);
    }
  };

  // งานค้างที่ต้องแจ้งเพิ่มเข้าใบเดิม — รวมทั้งที่ตรวจล่วงหน้า (open-ticket) และที่ 409 ตอบกลับ
  // ให้เป็นรูปแบบเดียว เพื่อให้ UI มีที่เดียวไม่ต้องเขียนกล่องเตือนสองแบบ
  const blocking = dupAlert
    ? {
        ticket_no: dupAlert.existing_ticket_no || '',
        status_label: dupAlert.existing_status_label || dupAlert.existing_status || '',
        device_label: dupAlert.existing_device_label || '',
        title: dupAlert.existing_title || '',
        can_add_note: dupAlert.can_add_note !== false,
      }
    : openTicket
      ? {
          ticket_no: openTicket.ticket_no || '',
          status_label: openTicket.status_label || openTicket.status || '',
          device_label: openTicket.device_label || '',
          title: openTicket.title || '',
          can_add_note: openTicket.can_add_note !== false,
        }
      : null;

  return (
    <div className="login-page">
      <div className="login-card" style={{ maxWidth: 480 }}>
        <div className="login-logo">
          <a href="https://iwa-web.onrender.com/" target="_blank" rel="noopener noreferrer" style={{ display: 'flex', alignItems: 'center', textDecoration: 'none', color: 'inherit' }}>
            <div className="login-logo-icon"><AppLogo size={22} /></div>
            <div>
              <h1 className="login-title">IWA Smart Classroom Support</h1>
              <p className="login-subtitle">แจ้งซ่อมออนไลน์ — ไม่ต้องเข้าสู่ระบบ</p>
            </div>
          </a>
        </div>
        <div className="login-divider" />

        {submitted ? (
          <div className="success-state">
            <div className="success-icon" aria-hidden="true">
              <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round">
                <path d="M20 6L9 17l-5-5" />
              </svg>
            </div>
            <div className="success-title">ส่งคำร้องเรียบร้อยแล้ว</div>
            <div className="success-sub">หมายเลข Ticket:</div>
            <div className="success-ticket-id">{ticketId}</div>
            <div style={{ marginTop: 16, fontSize: '0.8rem', color: 'var(--color-text-secondary)' }}>
              เจ้าหน้าที่จะดำเนินการตรวจสอบและซ่อมแซมโดยเร็วที่สุด
            </div>
            <button className="btn btn-primary" style={{ marginTop: 20 }} onClick={() => window.location.href = '/'}>
              กลับหน้าแรก
            </button>
            <button
              className="btn btn-ghost"
              style={{ marginTop: 8, width: '100%' }}
              onClick={() => window.location.href = `/?ticket=${encodeURIComponent(ticketId)}`}
            >
              ติดตามสถานะ Ticket นี้
            </button>
          </div>
        ) : (
          <>
            {/* ข้อมูลอุปกรณ์จาก QR */}
            {deviceLoading ? (
              <div style={{ display: 'flex', alignItems: 'center', gap: 10, padding: '10px 14px', marginBottom: 16, background: 'var(--color-surface-secondary)', borderRadius: 'var(--radius-md)' }}>
                <span className="spinner" style={{ width: 16, height: 16, borderWidth: 2 }} />
                <span style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>กำลังโหลดข้อมูลอุปกรณ์...</span>
              </div>
            ) : device ? (
              <div className="device-select-card" style={{ marginBottom: 16 }}>
                <div className="device-select-icon">
                  <DeviceIconSvg type={device.device_type} />
                </div>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="device-select-name">{device.device_id}</div>
                  <div className="device-select-sub">
                    {[device.device_type, device.brand, device.model].filter(Boolean).join(' · ') || 'อุปกรณ์'}
                    {device.room_name ? ` · ${device.room_name}` : ''}
                  </div>
                  <div style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)', marginTop: 4 }}>
                    {device.organization_name || ''}
                  </div>
                </div>
              </div>
            ) : (
              <div style={{ padding: '10px 14px', marginBottom: 16, background: 'var(--color-warning-light)', borderRadius: 'var(--radius-sm)', fontSize: '0.8rem' }}>
                ไม่พบข้อมูลอุปกรณ์ {deviceId} — ตรวจสอบว่ารหัสถูกต้องหรือไม่
              </div>
            )}

            {/* มีใบงานค้างอยู่แล้ว → แจ้งอาการเพิ่มเข้าใบเดิม ไม่เปิดใบซ้ำ */}
            {blocking && !submitted && (
              <div
                ref={blockRef}
                style={{
                  padding: '14px 16px',
                  marginBottom: 16,
                  background: 'var(--color-warning-light)',
                  border: '1px solid var(--color-warning, #F59E0B)',
                  borderRadius: 'var(--radius-md)',
                  color: 'var(--badge-warning-text, #92400E)',
                  fontSize: '0.85rem',
                }}
              >
                <div style={{ fontWeight: 700, marginBottom: 6 }}>
                  อุปกรณ์นี้มีการแจ้งซ่อมที่ยังไม่ปิดอยู่แล้ว
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <strong>{blocking.ticket_no || '-'}</strong>
                  {blocking.status_label && <span>· สถานะ: {blocking.status_label}</span>}
                </div>
                {blocking.title && (
                  <div style={{ fontSize: '0.8rem', marginTop: 2 }}>อาการที่แจ้งไว้: {blocking.title}</div>
                )}
                {blocking.device_label && blocking.device_label !== '-' && (
                  <div style={{ fontSize: '0.8rem', marginTop: 2 }}>อุปกรณ์: {blocking.device_label}</div>
                )}
                {blocking.ticket_no && (
                  <a
                    href={`/?ticket=${encodeURIComponent(blocking.ticket_no)}`}
                    style={{ display: 'inline-block', marginTop: 8, color: 'var(--color-primary)', fontWeight: 600, fontSize: '0.8rem' }}
                  >
                    ดูสถานะ Ticket นี้ → (ไม่ต้องเข้าสู่ระบบ)
                  </a>
                )}

                {blocking.can_add_note ? (
                  <div style={{ marginTop: 12, paddingTop: 12, borderTop: '1px solid var(--color-border, rgba(0,0,0,0.12))' }}>
                    <label className="form-label" htmlFor="public-add-note">
                      แจ้งอาการ/ข้อมูลเพิ่มเข้า Ticket นี้
                    </label>
                    <textarea
                      id="public-add-note"
                      className="form-textarea"
                      rows={3}
                      value={noteText}
                      onChange={(e) => setNoteText(e.target.value)}
                      placeholder="เช่น อาการแย่ลง จอดับเองบ่อยขึ้น / ใช้ห้องช่วงบ่ายไม่ได้"
                      maxLength={2000}
                      disabled={noteSending}
                    />
                    <div style={{ fontSize: '0.72rem', marginTop: 4, opacity: 0.9 }}>
                      กรอกชื่อผู้แจ้งในฟอร์มด้านล่างก่อนกดส่ง
                      {attachments.length > 0 ? ` · รูปที่แนบไว้ ${attachments.length} รูปจะถูกส่งไปด้วย` : ''}
                    </div>
                    {noteError && (
                      <div role="alert" style={{ color: 'var(--color-danger)', fontSize: '0.78rem', marginTop: 6 }}>
                        {noteError}
                      </div>
                    )}
                    {noteDone && (
                      <div role="status" style={{ color: 'var(--color-success, #047857)', fontSize: '0.78rem', marginTop: 6, fontWeight: 600 }}>
                        {noteDone}
                      </div>
                    )}
                    <button
                      type="button"
                      className="btn btn-primary"
                      style={{ width: '100%', marginTop: 8 }}
                      onClick={handleAddNote}
                      disabled={noteSending || !noteText.trim()}
                    >
                      {noteSending ? 'กำลังส่ง...' : 'ส่งข้อมูลเพิ่มเข้า Ticket เดิม'}
                    </button>
                    <div style={{ fontSize: '0.72rem', marginTop: 6, opacity: 0.9 }}>
                      ระบบไม่สร้าง Ticket ซ้ำ — ข้อมูลที่ส่งจะเข้าไปในงานเดิมให้ช่างเห็นตามลำดับเวลา
                    </div>
                  </div>
                ) : (
                  <div style={{ fontSize: '0.78rem', marginTop: 8 }}>
                    งานเดิมปิดแล้ว — กรอกฟอร์มด้านล่างเพื่อแจ้งซ่อมใหม่ได้เลย
                  </div>
                )}
              </div>
            )}

            {/* งานแจ้งซ่อมล่าสุดของเครื่องนี้ (ช่วยผู้ใช้ที่ลืมเลขหาเลขคืน) */}
            {recentLoading && (
              <div style={{ fontSize: '0.8rem', color: 'var(--color-text-tertiary)', marginBottom: 12 }}>
                กำลังตรวจสอบประวัติการแจ้งซ่อม...
              </div>
            )}
            {!recentLoading && recentTicket && !blocking && !submitted && (
              <div style={{
                padding: '12px 14px', marginBottom: 16,
                background: 'var(--color-info-light)', borderRadius: 'var(--radius-md)',
                fontSize: '0.85rem', border: '1px solid var(--color-primary-light)',
              }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>งานแจ้งซ่อมล่าสุดของเครื่องนี้</div>
                <div style={{ display: 'flex', alignItems: 'center', gap: 8, flexWrap: 'wrap' }}>
                  <strong style={{ color: 'var(--color-primary)' }}>{recentTicket.ticket_id}</strong>
                  <span className={`badge badge-${recentTicket.status}`} style={{ fontSize: '0.68rem' }}>
                    {recentTicket.status === 'new' ? 'รอรับเรื่อง' : recentTicket.status === 'assigned' ? 'มอบหมายแล้ว' : recentTicket.status === 'in_progress' ? 'กำลังดำเนินการ' : recentTicket.status === 'pending' ? 'รออะไหล่' : recentTicket.status === 'resolved' ? 'ซ่อมเสร็จ' : recentTicket.status === 'closed' ? 'ปิดงานแล้ว' : recentTicket.status === 'cancelled' ? 'ยกเลิก' : recentTicket.status}
                  </span>
                </div>
                {recentTicket.title && (
                  <div style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary)', marginTop: 4 }}>
                    {recentTicket.title}
                  </div>
                )}
                <div style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)', marginTop: 2 }}>
                  แจ้งเมื่อ {recentTicket.created_at ? new Date(recentTicket.created_at).toLocaleDateString('th-TH', { day: '2-digit', month: 'short', year: 'numeric' }) : ''}
                  {recentTicket.status === 'closed' ? ' · งานนี้ปิดแล้ว' : recentTicket.status === 'resolved' ? ' · รอยืนยันปิดงาน' : ' · งานยังไม่เสร็จ'}
                </div>
                <a
                  href={`/?ticket=${encodeURIComponent(recentTicket.ticket_id)}`}
                  style={{ display: 'inline-block', marginTop: 8, color: 'var(--color-primary)', fontWeight: 600, fontSize: '0.8rem' }}
                >
                  ดูสถานะงานนี้ → (ไม่ต้องเข้าสู่ระบบ)
                </a>
                <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)', marginTop: 6 }}>
                  ลืมเลข Ticket ไหม? กดดูสถานะด้านบน หรือแจ้งซ่อมใหม่ด้านล่าง
                </div>
              </div>
            )}

            <form onSubmit={handleSubmit}>
              <div className="form-group">
                <label className="form-label">หัวข้อ<span className="required">*</span></label>
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
                  placeholder="บรรยายอาการที่เกิดขึ้น... (เช่น เปิดเครื่องแล้วจอไม่ติด ไฟไม่เข้า)"
                  rows={3}
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

              {/* กันแจ้งซ้ำ: รายละเอียดงานค้าง + ช่องแจ้งอาการเพิ่มเข้าใบเดิม
                  อยู่ในกล่องเหนือฟอร์ม (blocking) แล้ว ไม่ซ้ำที่นี่อีก */}

              {/* AI วินิจฉัยเบื้องต้น (ตอบจาก KB เท่านั้น) */}
              <div style={{ marginBottom: 'var(--spacing-md)' }}>
                <button
                  type="button"
                  className="btn btn-ghost"
                  style={{ width: '100%', fontSize: '0.85rem' }}
                  onClick={runDiagnose}
                  disabled={diagLoading || submitting}
                >
                  {diagLoading ? (
                    <>
                      <span className="spinner" style={{ width: 14, height: 14, marginRight: 8, borderWidth: 2, display: 'inline-block' }} />
                      กำลังวิเคราะห์อาการ...
                    </>
                  ) : diag ? (
                    <>
                      <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true" style={{ marginRight: 6, verticalAlign: '-2px' }}>
                        <path d="M21 12a9 9 0 11-3.5-7.1" />
                        <path d="M21 3v6h-6" />
                      </svg>
                      วิเคราะห์ใหม่
                    </>
                  ) : (
                    'ทดลองวินิจฉัยอัตโนมัติ (แนะนำวิธีแก้เบื้องต้น)'
                  )}
                </button>

                {diag && diag.found && (
                  <div style={{
                    marginTop: 10,
                    padding: '12px 14px',
                    background: 'var(--color-primary-light)',
                    borderRadius: 'var(--radius-sm)',
                    fontSize: '0.83rem',
                  }}>
                    <div style={{ fontWeight: 600, marginBottom: 6 }}>{diag.title || 'วิธีแก้ไขเบื้องต้น'}</div>
                    <ol style={{ margin: '0 0 8px 18px', padding: 0 }}>
                      {(diag.steps || []).map((s: string, i: number) => (
                        <li key={i} style={{ marginBottom: 4 }}>{s}</li>
                      ))}
                    </ol>
                    <div style={{ display: 'flex', gap: 8, marginTop: 8 }}>
                      <button
                        type="button"
                        className="btn btn-secondary"
                        style={{ fontSize: '0.78rem', padding: '6px 10px' }}
                        onClick={async () => {
                          try {
                            await api.createSelfService({
                              device_id: deviceId || undefined,
                              symptom: form.title,
                              ai_session_id: diag?.session_id,
                              time_saved_minutes: 5,
                            });
                            setDiag(null);
                            setForm((f) => ({ ...f, title: '', description: '' }));
                            setError('ดีใจด้วยที่แก้ไขได้ บันทึกเป็นกรณีแก้เองแล้ว');
                          } catch {
                            setDiag(null);
                            setForm((f) => ({ ...f, title: '', description: '' }));
                          }
                        }}
                      >
                        แก้ไขได้แล้ว
                      </button>
                      <button
                        type="button"
                        className="btn btn-primary"
                        style={{ fontSize: '0.78rem', padding: '6px 10px' }}
                        onClick={() => setDiag(null)}
                      >
                        ยังไม่หาย → แจ้งช่าง
                      </button>
                    </div>
                  </div>
                )}
              </div>

              {/* รูปภาพแนบ (TOR 1.5.2) */}
              <div className="form-group">
                <label className="form-label">รูปภาพ (ไม่บังคับ — สูงสุด 3 รูป)</label>
                <input
                  type="file"
                  accept="image/*"
                  multiple
                  className="form-input"
                  onChange={handleUpload}
                  disabled={uploading || attachments.length >= 3}
                  style={{ padding: 8, fontSize: '0.8rem' }}
                />
                {uploading && <div style={{ fontSize: '0.75rem', color: 'var(--color-text-secondary)', marginTop: 4 }}>กำลังอัปโหลด...</div>}
                {attachments.length > 0 && (
                  <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, marginTop: 8 }}>
                    {attachments.map((u, i) => (
                      <div key={i} style={{ position: 'relative' }}>
                        <img src={u} alt={`แนบ ${i + 1}`} style={{ width: 64, height: 64, objectFit: 'cover', borderRadius: 8 }} />
                        <button
                          type="button"
                          onClick={() => setAttachments((prev) => prev.filter((_, j) => j !== i))}
                          aria-label="ลบรูปนี้"
                          title="ลบรูปนี้"
                          style={{
                            position: 'absolute', top: -6, right: -6,
                            background: 'var(--color-danger)', color: '#fff',
                            border: 'none', borderRadius: '50%', width: 18, height: 18,
                            cursor: 'pointer', lineHeight: 0, padding: 0,
                            display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          }}
                        >
                          <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" aria-hidden="true">
                            <path d="M18 6L6 18M6 6l12 12" />
                          </svg>
                        </button>
                      </div>
                    ))}
                  </div>
                )}
              </div>

              <button
                type="submit"
                className="btn btn-primary btn-full"
                style={{ padding: '12px' }}
                disabled={submitting || !form.title.trim() || dupAlert !== null}
              >
                {submitting ? (
                  <>
                    <span className="spinner" style={{ width: 14, height: 14, marginRight: 8, borderWidth: 2, display: 'inline-block' }} />
                    กำลังส่ง...
                  </>
                ) : (
                  <>ส่งคำร้องแจ้งซ่อม</>
                )}
              </button>
            </form>
          </>
        )}
      </div>
    </div>
  );
}

// ─── Track Status (ติดตามสถานะด้วยเลข ticket — ไม่ต้อง login) ─────────────
const STATUS_LABELS_PUBLIC: Record<string, string> = {
  new: 'เปิดคำร้อง (New)',
  assigned: 'มอบหมายงาน (Assigned)',
  in_progress: 'กำลังดำเนินการ (In Progress)',
  pending: 'รออะไหล่/รอภายนอก (Pending)',
  waiting_parts: 'รออะไหล่ (Waiting for Parts)',
  waiting_user: 'รอผู้ใช้ (Waiting for User)',
  resolved: 'ซ่อมเสร็จแล้ว (Resolved)',
  closed: 'ปิดงาน (Closed)',
  cancelled: 'ยกเลิก (Cancelled)',
};

function TrackStatusView({ initialTicketId }: { initialTicketId?: string }) {
  const [ticketInput, setTicketInput] = useState(initialTicketId || '');
  const [ticket, setTicket] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);

  // Auto-search เมื่อเปิดมาพร้อมเลข Ticket จาก URL (?ticket=xxxx) — กด "ดูสถานะ" แล้วเห็นผลทันที
  useEffect(() => {
    if (initialTicketId) {
      search();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const search = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    const id = ticketInput.trim();
    if (!id) return;
    setLoading(true);
    setError(null);
    setSearched(false);
    setTicket(null);
    try {
      const result = await api.trackTicket(id);
      setTicket(result);
    } catch (err: any) {
      setError(err.message || 'ไม่พบ Ticket นี้');
    } finally {
      setLoading(false);
      setSearched(true);
    }
  };

  return (
    <div className="login-page">
      <div className="login-card" style={{ maxWidth: 480 }}>
        <div className="login-logo">
          <a href="https://iwa-web.onrender.com/" target="_blank" rel="noopener noreferrer" style={{ display: 'flex', alignItems: 'center', textDecoration: 'none', color: 'inherit' }}>
            <div className="login-logo-icon"><AppLogo size={22} /></div>
            <div>
              <h1 className="login-title">IWA Smart Classroom Support</h1>
              <p className="login-subtitle">ติดตามสถานะการแจ้งซ่อม — ไม่ต้องเข้าสู่ระบบ</p>
            </div>
          </a>
        </div>
        <div className="login-divider" />

        {/* ช่องกรอกเลข Ticket */}
        <form onSubmit={search}>
          <div className="form-group" style={{ display: 'flex', gap: 8, marginBottom: 16 }}>
            <input
              type="text"
              className="form-input"
              value={ticketInput}
              onChange={(e) => setTicketInput(e.target.value.toUpperCase())}
              placeholder="กรอกเลข Ticket เช่น TK.TEST1.26.0001-V"
              style={{ flex: 1 }}
            />
            <button type="submit" className="btn btn-primary" disabled={loading || !ticketInput.trim()}>
              {loading ? <span className="spinner" style={{ width: 14, height: 14, borderWidth: 2, display: 'inline-block' }} /> : 'ค้นหา'}
            </button>
          </div>
        </form>

        {error && (
          <div style={{
            padding: '10px 14px',
            background: 'var(--color-danger-light)',
            color: 'var(--color-danger)',
            borderRadius: 'var(--radius-sm)',
            fontSize: '0.8rem',
            marginBottom: 16,
          }}>
            {error} — ตรวจสอบเลข Ticket ให้ถูกต้อง (เช่น TK.TEST1.26.0001-V)
          </div>
        )}

        {ticket && (
          <div>
            {/* ข้อมูล Ticket */}
            <div className="device-select-card" style={{ marginBottom: 12 }}>
              <div className="device-select-icon">
                <DeviceIconSvg type={ticket.device_info?.device_type || 'อุปกรณ์'} />
              </div>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 8 }}>
                  <div className="device-select-name" style={{ fontSize: '0.95rem' }}>{ticket.ticket_id}</div>
                  <span className={`badge badge-${ticket.status}`}>
                    {STATUS_LABELS_PUBLIC[ticket.status] || ticket.status}
                  </span>
                </div>
                <div className="device-select-sub">{ticket.title}</div>
                <div style={{ fontSize: '0.75rem', color: 'var(--color-text-tertiary)', marginTop: 4 }}>
                  {ticket.device_info ? `${ticket.device_info.device_id}${ticket.device_info.room_name ? ' · ' + ticket.device_info.room_name : ''}${ticket.device_info.organization_name ? ' · ' + ticket.device_info.organization_name : ''}` : ticket.device_id}
                </div>
              </div>
            </div>

            <div className="form-row" style={{ marginBottom: 12 }}>
              <div className="form-group">
                <div className="form-label">ความเร่งด่วน</div>
                <div style={{ fontSize: '0.85rem' }}>
                  <span className={`badge badge-priority badge-${ticket.priority}`}>
                    {ticket.priority === 'critical' ? 'เร่งด่วนมาก' : ticket.priority === 'high' ? 'High' : ticket.priority === 'low' ? 'Low' : 'Normal'}
                  </span>
                </div>
              </div>
              <div className="form-group">
                <div className="form-label">แจ้งเมื่อ</div>
                <div style={{ fontSize: '0.85rem', color: 'var(--color-text-secondary)' }}>
                  {new Date(ticket.created_at).toLocaleString('th-TH', { dateStyle: 'medium', timeStyle: 'short' })}
                </div>
              </div>
            </div>

            {/* Timeline ประวัติ */}
            <div className="form-label">ประวัติการดำเนินการ</div>
            <div style={{ display: 'flex', flexDirection: 'column', gap: 10, marginTop: 6, marginBottom: 12 }}>
              {Array.isArray(ticket.history) && ticket.history.length > 0 ? (
                ticket.history.map((h: any, i: number) => (
                  <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'flex-start' }}>
                    <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                      <div style={{
                        width: 10, height: 10, borderRadius: '50%',
                        background: 'var(--color-primary)', flexShrink: 0, marginTop: 4,
                      }} />
                      {i < ticket.history.length - 1 && <div style={{ width: 2, flex: 1, background: 'var(--color-border)' }} />}
                    </div>
                    <div style={{ paddingBottom: 8, flex: 1 }}>
                      <div style={{ fontSize: '0.85rem', fontWeight: 600 }}>
                        {STATUS_LABELS_PUBLIC[h.to_status || h.status] || h.to_status || h.status}
                      </div>
                      {h.note && <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', marginTop: 2 }}>{h.note}</div>}
                      <div style={{ fontSize: '0.72rem', color: 'var(--color-text-tertiary)', marginTop: 2 }}>
                        {new Date(h.created_at).toLocaleString('th-TH', { dateStyle: 'medium', timeStyle: 'short' })}
                        {h.author_name ? ` · ${h.author_name}` : ''}
                      </div>
                    </div>
                  </div>
                ))
              ) : (
                <div style={{ fontSize: '0.8rem', color: 'var(--color-text-secondary)', padding: '8px 0' }}>
                  ยังไม่มีประวัติการอัปเดต — รอเจ้าหน้าที่รับเรื่อง
                </div>
              )}
            </div>

            {ticket.status === 'resolved' && ticket.resolution_notes && (
              <div style={{
                padding: '10px 14px',
                background: 'var(--color-success-light)',
                color: 'var(--color-success)',
                borderRadius: 'var(--radius-sm)',
                fontSize: '0.82rem',
                marginBottom: 12,
              }}>
                <strong>หมายเหตุการซ่อม:</strong> {ticket.resolution_notes}
              </div>
            )}
          </div>
        )}

        {!ticket && !error && !loading && (
          <div style={{ fontSize: '0.8rem', color: 'var(--color-text-tertiary)', textAlign: 'center', padding: '8px 0' }}>
            กรอกเลข Ticket ที่ได้รับตอนแจ้งซ่อม เพื่อดูสถานะล่าสุด
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Qr Token Resolve (สแกน QR แบบ ?t=token → แปลงเป็น device_id) ────────
function QrTokenResolveView({ token }: { token: string }) {
  const [deviceId, setDeviceId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api.qrResolve(token)
      .then((r) => {
        if (r?.device?.device_id) {
          // ล้าง ?t= จาก URL แล้วเปิดฟอร์มแจ้งซ่อมให้ device นั้น
          window.history.replaceState({}, '', `/scan?device=${encodeURIComponent(r.device.device_id)}`);
          setDeviceId(r.device.device_id);
        } else {
          setError('QR Code นี้ไม่ตรงกับอุปกรณ์ใดในระบบ');
        }
      })
      .catch(() => setError('ไม่พบอุปกรณ์ที่ตรงกับ QR Code นี้ — ตรวจสอบว่าสติกเกอร์ถูกต้อง'));
  }, [token]);

  if (error) {
    return (
      <div className="login-page">
        <div className="login-card" style={{ maxWidth: 440, textAlign: 'center' }}>
          <div className="login-logo">
            <a href="https://iwa-web.onrender.com/" target="_blank" rel="noopener noreferrer" style={{ display: 'inline-flex', alignItems: 'center', textDecoration: 'none', color: 'inherit' }}>
              <div className="login-logo-icon"><AppLogo size={22} /></div>
              <div>
                <h1 className="login-title">IWA Smart Classroom Support</h1>
                <p className="login-subtitle">แจ้งซ่อมออนไลน์</p>
              </div>
            </a>
          </div>
          <div className="login-divider" />
          <div style={{ color: 'var(--color-danger)', fontSize: '0.9rem', marginBottom: 16 }}>{error}</div>
          <a href="/" className="btn btn-primary" style={{ display: 'inline-block' }}>กลับหน้าแรก</a>
        </div>
      </div>
    );
  }

  if (!deviceId) {
    return (
      <div className="login-page" style={{ minHeight: '100vh' }}>
        <div style={{ textAlign: 'center' }}>
          <div className="spinner" style={{ width: 36, height: 36, margin: '0 auto 16px' }} />
          <span style={{ color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>กำลังตรวจสอบ QR Code...</span>
        </div>
      </div>
    );
  }

  return <PublicReportView deviceId={deviceId} />;
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
  const [pageTitle, setPageTitle] = useState('Dashboard');
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [selectedSchoolId, setSelectedSchoolId] = useState<number | null>(null);
  const [showRepairPanel, setShowRepairPanel] = useState(false);
  const [repairDeviceId, setRepairDeviceId] = useState<string | undefined>();
  const [ticketSubmitResult, setTicketSubmitResult] = useState<{ success: boolean; ticket_id?: string } | null>(null);
  
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
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [auth.isAuthenticated, reloadData]);

  // ─── ฟัง event จาก SettingsPage (ปุ่ม "แก้ไขโปรไฟล์ →") ────────────────
  useEffect(() => {
    const handler = (e: Event) => {
      const menu = (e as CustomEvent).detail;
      if (typeof menu === 'string') handleMenuChange(menu);
    };
    window.addEventListener('navigate', handler);
    return () => window.removeEventListener('navigate', handler);
  });

  const handleMenuChange = (menu: string) => {
    // Role guard: ถ้าเมนูไม่ได้รับอนุญาตสำหรับบทบาทนี้ → กลับ Dashboard
    const allowed = ROLE_MENUS[role] || LEGACY_FALLBACK_MENUS;
    if (!allowed.includes(menu)) menu = 'dashboard';
    setMenu(menu);
    if (menu === 'dashboard') reloadData();  // กลับหน้า Dashboard → ดึงข้อมูลใหม่เสมอ (ไม่ต้อง hard refresh)
    if (menu !== 'schools') setSelectedSchoolId(null);
    const titles: Record<string, string> = {
      dashboard: 'Dashboard',
      devices: 'อุปกรณ์',
      scan: 'สแกน QR',
      tickets: 'Tickets',
      kb: 'ฐานความรู้',
      qrbatch: 'พิมพ์ QR',
      pm: 'บำรุงรักษา (PM)',
      users: 'Users',
      reports: 'Reports',
      audit: 'ประวัติการใช้งาน',
      sales: 'ลูกค้าและการขาย',
      registrations: 'อนุมัติเจ้าหน้าที่',
      schools: 'โรงเรียน',
      settings: 'การตั้งค่า',
      profile: 'โปรไฟล์',
    };
    setPageTitle(titles[menu] || menu);
  };

  const openRepairPanel = (deviceId?: string) => {
    setRepairDeviceId(deviceId);
    setShowRepairPanel(true);
  };

  const handleTicketSubmit = (result: { success: boolean; ticket_id?: string }) => {
    setShowRepairPanel(false);
    setRepairDeviceId(undefined);
    setTicketSubmitResult(result);
    // Reload data
    reloadData();
  };

  if (auth.isLoading) return (
    <div className="login-page" style={{ minHeight: '100vh' }}>
      <div style={{ textAlign: 'center' }}>
        <div className="spinner" style={{ width: 36, height: 36, margin: '0 auto 16px' }} />
        <span style={{ color: 'var(--color-text-secondary)', fontSize: '0.9rem' }}>กำลังโหลด...</span>
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

  const qrDevice = qrParams.get('device');
  if (qrDevice) {
    return <PublicReportView deviceId={qrDevice} />;
  }

  // ─── สแกน QR (รูปแบบ token): URL มี ?t=xxxx → resolve token → เปิดฟอร์มแจ้งซ่อม
  const qrToken = qrParams.get('t');
  if (qrToken) {
    return <QrTokenResolveView token={qrToken} />;
  }

  // ─── ติดตามสถานะ: URL มี ?ticket=TK.SCHM01.26.0001-T (หรือ ?ticket= เปล่า)
  //     → หน้าแรกสาธารณะ เปิดพร้อมค้นเลขใบงานนั้นให้เลย
  const trackTicket = qrParams.get('ticket');
  if (trackTicket !== null) {
    return <PublicHomeView initialTicketId={trackTicket || undefined} />;
  }

  if (!auth.isAuthenticated) {
    // เปิดหน้า นโยบายความเป็นส่วนตัว ได้โดยไม่ต้อง login
    if (menu === 'privacy') {
      return <PrivacyPage onBack={() => setMenu('dashboard')} />;
    }
    // หน้าเข้าสู่ระบบเจ้าหน้าที่แยกเป็นอีกหน้า — เข้าถึงด้วย /?login=1 เท่านั้น
    if (qrParams.get('login') !== null) {
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
        <Sidebar
          activeMenu={menu}
          onMenuChange={handleMenuChange}
          schoolName={sidebarSchoolName}
          userRole={auth.user?.role}
          userOrgId={auth.user?.organization_id}
          userName={auth.user?.line_display_name || auth.user?.line_user_id}
          userAvatar={auth.user?.line_picture_url}
          open={sidebarOpen}
          onClose={() => setSidebarOpen(false)}
          onLogout={auth.logout}
        />

        <div className="main-column">
          <AppHeader
            pageTitle={pageTitle}
            user={auth.user}
            onMenuToggle={() => setSidebarOpen(true)}
            devices={devices}
            tickets={tickets}
            onNavigate={(m) => handleMenuChange(m)}
            onLogout={auth.logout}
          />

          <div className="app-main">
            <div className="page-content">
              {dataError && (
                <div role="alert" className="alert alert-error">
                  โหลดข้อมูลล่าสุดไม่สำเร็จ กรุณาลองอีกครั้ง{' '}
                  <button type="button" onClick={() => { void reloadData(); }}>โหลดใหม่</button>
                </div>
              )}
              {menu === 'dashboard' && (
                <DashboardContent
                  onOpenRepairPanel={openRepairPanel}
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
                  onBack={() => handleMenuChange('dashboard')}
                  currentOrgId={currentOrgId}
                  isSuperAdmin={globalScope}
                  canManage={canManage}
                  userRole={role}
                />
              )}
              {menu === 'tickets' && (
                <TicketsPage
                  tickets={tickets}
                  onBack={() => handleMenuChange('dashboard')}
                  onTicketsChanged={reloadData}
                  canManage={canManage}
                />
              )}
              {menu === 'kb' && (
                <KBPage onBack={() => handleMenuChange('dashboard')} userRole={role} userOrgId={auth.user?.organization_id} />
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
                <AuditLogPage onBack={() => handleMenuChange('dashboard')} />
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
          </div>
        </div>

        {showRepairPanel && (
          <RepairPanel
            deviceId={repairDeviceId}
            onClose={() => { setShowRepairPanel(false); setRepairDeviceId(undefined); }}
            onSubmit={handleTicketSubmit}
          />
        )}

        <AIChatWidget user={auth.user} />
      </div>
    </>
  );
}
