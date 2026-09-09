import React, { useState, useEffect, ReactNode } from 'react';
import { DeviceInfo, Ticket, Stats, DeviceCreate, TicketCreate } from './types';
import { User, UserRole, Organization } from './types/user';
import { DevicePageRole, DEVICE_PAGE_ROLES, DEVICE_PAGE_ROLE_BADGE } from './types/index';
import { api, login, setToken } from './api/client';
import StatCard from './components/StatCard';
import Sidebar, { ROLE_MENUS } from './components/Sidebar';
import SchoolsPage, { SchoolAdminView } from './components/SchoolsPage';
import ScanPage from './components/ScanPage';
import PublicNoLoginReportView from './components/PublicNoLoginReportView';
import DevicesPage from './components/DevicesPage';
import AIChatWidget from './components/AIChatWidget';
import UsersPage from './components/UsersPage';
import ReportsPage from './components/ReportsPage';
import SettingsPage from './components/SettingsPage';
import ProfilePage from './components/ProfilePage';
import KBPage from './components/KBPage';
import PMPage from './components/PMPage';
import QRBatchPage from './components/QRBatchPage';
import SalesPage from './components/SalesPage';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend
} from 'recharts';

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
const STATUS_COLORS: Record<string, string> = {
  new: '#EF4444', assigned: '#F59E0B', in_progress: '#2563EB',
  pending: '#8B5CF6', resolved: '#10B981', closed: '#6B7280', cancelled: '#EF4444',
};

// ─── Login Page (จริง: username + password) ─────────────────────────────────
function LoginPage({ onLogin }: { onLogin: (u: User) => void }) {
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
    if (!no) { setTErr('กรอกหมายเลข Ticket (เช่น TK-202609-0001)'); return; }
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
        <div className="login-logo">
          <div className="login-logo-icon"><AppLogo size={22} /></div>
          <div>
            <h1 className="login-title">IWA Smart Classroom Support</h1>
            <p className="login-subtitle">ระบบจัดการแจ้งซ่อมอุปกรณ์อัจฉริยะ</p>
          </div>
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
                style={{ position: 'absolute', top: 12, right: 12, border: 'none', background: 'transparent', cursor: 'pointer', fontSize: '1.1rem', color: 'var(--color-text-tertiary)' }}
              >✕</button>
              <h3 style={{ margin: '0 0 6px', fontSize: '1.1rem' }}>🔎 ติดตามสถานะงานซ่อม</h3>
              <p style={{ fontSize: '0.8rem', color: 'var(--color-text-tertiary)', margin: '0 0 16px' }}>
                กรอกหมายเลข Ticket ที่ได้รับตอนแจ้งซ่อม — ไม่ต้องเข้าสู่ระบบ
              </p>
              <form onSubmit={handleTrack} style={{ display: 'flex', gap: 8 }}>
                <input
                  className="form-input"
                  placeholder="TK-202609-0001"
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
                            background: p.done ? '#10B981' : 'var(--color-border)', color: p.done ? '#fff' : 'var(--color-text-tertiary)',
                            fontSize: '0.6rem',
                          }}>{p.done ? '✓' : ''}</span>
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
        <AppLogo size={22} />
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
                🔔 การแจ้งเตือน ({openTickets.length})
              </div>
              {openTickets.length === 0 ? (
                <div style={{ padding: 20, textAlign: 'center', color: 'var(--color-text-tertiary)', fontSize: '0.8rem' }}>
                  ไม่มีงานค้าง 🎉
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
                      {user.role === 'super_admin' ? 'ผู้ดูแลระบบสูงสุด' : user.role === 'admin' ? 'ผู้ดูแลระบบ' : user.role === 'it_support' ? 'เจ้าหน้าที่ IT' : user.role === 'teacher' ? 'ครูผู้สอน' : 'นักเรียน/นักศึกษา'}
                    </div>
                  </div>
                  <button
                    style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '11px 14px', border: 'none', background: 'transparent', cursor: 'pointer', fontSize: '0.85rem', color: 'var(--color-text)', textAlign: 'left' }}
                    onMouseDown={() => { setShowUserMenu(false); onNavigate?.('profile'); }}
                  >
                    <span style={{ fontSize: '1rem' }}>👤</span> โปรไฟล์
                  </button>
                  <button
                    style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '11px 14px', border: 'none', background: 'transparent', cursor: 'pointer', fontSize: '0.85rem', color: 'var(--color-text)', textAlign: 'left' }}
                    onMouseDown={() => { setShowUserMenu(false); onNavigate?.('settings'); }}
                  >
                    <span style={{ fontSize: '1rem' }}>⚙️</span> การตั้งค่า
                  </button>
                  <div style={{ borderTop: '1px solid var(--color-border)' }} />
                  <button
                    style={{ display: 'flex', alignItems: 'center', gap: 10, width: '100%', padding: '11px 14px', border: 'none', background: 'transparent', cursor: 'pointer', fontSize: '0.85rem', color: 'var(--color-danger)', textAlign: 'left' }}
                    onMouseDown={() => { setShowUserMenu(false); onLogout?.(); }}
                  >
                    <span style={{ fontSize: '1rem' }}>🚪</span> ออกจากระบบ
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
  const [filterDevice, setFilterDevice] = useState('');
  const [filterStatus, setFilterStatus] = useState('');

  // ─── บทบาทครู/นักเรียน: dashboard เบา ๆ เฉพาะของตัวเอง ─────────────────
  const isBasicRole = userRole === 'teacher' || userRole === 'student';
  const myTickets = tickets;
  const myOpenTickets = myTickets.filter((t) => ['new', 'assigned', 'in_progress', 'pending'].includes(t.status));
  const myResolved = myTickets.filter((t) => t.status === 'resolved' || t.status === 'closed');

  const statusChartData = [
    { name: 'เปิด', value: stats?.new ?? 0, color: STATUS_COLORS.new },
    { name: 'รอซ่อม', value: stats?.assigned ?? 0, color: STATUS_COLORS.assigned },
    { name: 'กำลังดำเนินการ', value: stats?.in_progress ?? 0, color: STATUS_COLORS.in_progress },
    { name: 'เสร็จสิ้น', value: stats?.resolved ?? 0, color: STATUS_COLORS.resolved },
    { name: 'ยกเลิก', value: stats?.cancelled ?? 0, color: STATUS_COLORS.cancelled },
  ].filter((d) => d.value > 0);

  // Pie: สัดส่วนอุปกรณ์ตามประเภท (ข้อมูลจริงจาก /api/stats by_type)
  const DEVICE_PIE_COLORS = ['#7C3AED', '#2563EB', '#10B981', '#F59E0B', '#EF4444', '#EC4899', '#0EA5E9', '#8B5CF6', '#6B7280', '#F97316'];
  const deviceTypeData = Object.entries(stats?.by_type ?? {})
    .map(([name, value]) => ({ name, value }))
    .sort((a, b) => b.value - a.value);

  const monthlyData = (() => {
    const map = new Map<string, number>();
    tickets.forEach((t) => {
      const d = new Date(t.created_at);
      const key = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}`;
      map.set(key, (map.get(key) || 0) + 1);
    });
    return Array.from(map.entries())
      .sort((a, b) => a[0].localeCompare(b[0]))
      .map(([month, value]) => ({ month, value }));
  })();

  const filteredTicketsEntities = tickets.filter((t) => {
    if (needsOrgFilter && currentOrgId) {
      const dev = devices.find((d) => d.device_id === t.device_id);
      if (dev && dev.organization_id !== currentOrgId) return false;
    }
    if (filterDevice && t.device_id !== filterDevice) return false;
    if (filterStatus && t.status !== filterStatus) return false;
    return true;
  });

  const filteredDevices = devices.filter((d) => {
    if (!filterDevice) return true;
    const q = filterDevice.toLowerCase();
    return (
      d.device_id.toLowerCase().includes(q) ||
      d.device_type.toLowerCase().includes(q) ||
      (d.brand && d.brand.toLowerCase().includes(q)) ||
      (d.model && d.model.toLowerCase().includes(q)) ||
      (d.room_name && d.room_name.toLowerCase().includes(q))
    );
  }).filter((d) => !needsOrgFilter || d.organization_id === currentOrgId);

  if (loading) return (
    <div className="loading-state" style={{ minHeight: 200, padding: '40px', margin: '0 auto', width: '100%' }}>
      <div className="spinner" />
      <span>กำลังโหลดข้อมูล...</span>
    </div>
  );

  // ─── Dashboard สำหรับครู/นักเรียน: เฉพาะของตัวเอง + แจ้งซ่อมเร็ว ──────────
  if (isBasicRole) {
    return (
      <div>
        {/* Hero banner ต้อนรับ */}
        <div style={{
          padding: '22px 26px', marginBottom: 18, borderRadius: 'var(--radius-lg)',
          background: 'linear-gradient(120deg, var(--color-primary) 0%, var(--color-primary-dark) 60%, #1E1B2E 100%)',
          color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
          flexWrap: 'wrap', gap: 16, boxShadow: '0 8px 24px rgba(124,58,237,0.18)',
        }}>
          <div>
            <div style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: 4 }}>
              สวัสดีครับ 👋 {userRole === 'student' ? 'นักเรียน' : 'คุณครู'}
            </div>
            <div style={{ fontSize: '0.85rem', opacity: 0.85 }}>
              ติดตามงานแจ้งซ่อมของคุณได้ที่นี่ — หากพบปัญหาอุปกรณ์ สแกน QR ที่ตัวเครื่องเพื่อแจ้งซ่อม
            </div>
          </div>
          <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
            <span style={{ fontSize: '0.8rem', background: 'rgba(255,255,255,0.18)', padding: '6px 14px', borderRadius: 20 }}>
              🟠 กำลังดำเนินการ {myOpenTickets.length}
            </span>
            <span style={{ fontSize: '0.8rem', background: 'rgba(255,255,255,0.18)', padding: '6px 14px', borderRadius: 20 }}>
              ✅ ซ่อมเสร็จ {myResolved.length}
            </span>
          </div>
        </div>

        {/* สถิติของฉัน — KPI ทันสมัย */}
        <div className="stat-cards-grid" style={{ gridTemplateColumns: 'repeat(auto-fit, minmax(170px, 1fr))' }}>
          {[
            { icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4', value: myTickets.length, label: 'แจ้งซ่อมทั้งหมด', color: '#7C3AED', sub: 'ทุกครั้ง' },
            { icon: 'M12 6v6l4 2', value: myOpenTickets.length, label: 'กำลังดำเนินการ', color: '#F59E0B', sub: 'ยังไม่เสร็จ' },
            { icon: 'M13 10V3L4 14h7v7l9-11h-7z', value: myResolved.length, label: 'ซ่อมเสร็จแล้ว', color: '#10B981', sub: 'แก้ไขได้แล้ว' },
          ].map((kpi) => (
            <div key={kpi.label} style={{
              background: 'var(--color-surface)', borderRadius: 'var(--radius-md)',
              border: '1px solid var(--color-border)', padding: '16px 18px',
              display: 'flex', flexDirection: 'column', gap: 10,
            }}>
              <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <div style={{ width: 40, height: 40, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center', background: `${kpi.color}1a` }}>
                  <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={kpi.color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d={kpi.icon} /></svg>
                </div>
                <span style={{ fontSize: '0.68rem', color: 'var(--color-text-tertiary)' }}>{kpi.sub}</span>
              </div>
              <div>
                <div style={{ fontSize: '1.7rem', fontWeight: 800, lineHeight: 1, color: 'var(--color-text)' }}>{kpi.value}</div>
                <div style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary)', marginTop: 5, fontWeight: 600 }}>{kpi.label}</div>
              </div>
            </div>
          ))}
        </div>

        {/* Ticket ของฉัน */}
        <div className="page-section">
          <div className="section-header">
            <span className="section-title">Ticket ของฉัน ({myTickets.length})</span>
          </div>
          <div className="section-body">
            {myTickets.length === 0 ? (
              <div className="empty-state" style={{ padding: '32px 16px' }}>
                <span className="empty-text">ยังไม่มี Ticket — สแกน QR ที่ตัวเครื่องเพื่อแจ้งซ่อม</span>
              </div>
            ) : (
              <div className="table-wrap">
                <table className="data-table">
                  <thead>
                    <tr>
                      <th>Ticket ID</th><th>อุปกรณ์</th><th>หัวข้อ</th><th>สถานะ</th><th>ความเร่งด่วน</th><th>สร้างเมื่อ</th>
                    </tr>
                  </thead>
                  <tbody>
                    {myTickets.slice(0, 8).map((ticket) => (
                      <tr key={ticket.ticket_id}>
                        <td className="table-id">{ticket.ticket_id}</td>
                        <td>{ticket.device_id}</td>
                        <td>{ticket.title}</td>
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
                        <td style={{ color: 'var(--color-text-tertiary)', fontSize: '0.8rem' }}>
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
    <div>
      {/* Hero banner สรุปภาพรวม */}
      <div className="dash-hero" style={{
        padding: '22px 26px', marginBottom: 18, borderRadius: 'var(--radius-lg)',
        background: 'linear-gradient(120deg, var(--color-primary) 0%, var(--color-primary-dark) 60%, #1E1B2E 100%)',
        color: '#fff', display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        flexWrap: 'wrap', gap: 16, boxShadow: '0 8px 24px rgba(124,58,237,0.18)',
      }}>
        <div>
          <div style={{ fontSize: '1.25rem', fontWeight: 800, marginBottom: 4 }}>ภาพรวมระบบซ่อมบำรุง 📊</div>
          <div style={{ fontSize: '0.85rem', opacity: 0.85 }}>
            มี Ticket ทั้งหมด <b>{stats?.total_tickets ?? 0}</b> รายการ · กำลังดำเนินการ <b>{stats?.in_progress ?? 0}</b> · รอรับเรื่อง <b>{stats?.new ?? 0}</b>
          </div>
        </div>
        <div style={{ display: 'flex', gap: 10, alignItems: 'center' }}>
          <span style={{ fontSize: '0.8rem', background: 'rgba(255,255,255,0.18)', padding: '6px 14px', borderRadius: 20 }}>
            ✅ เสร็จสิ้น {stats?.resolved ?? 0}
          </span>
          <span style={{ fontSize: '0.8rem', background: 'rgba(255,255,255,0.18)', padding: '6px 14px', borderRadius: 20 }}>
            🖥️ อุปกรณ์ {stats?.total_devices ?? 0}
          </span>
        </div>
      </div>

      {/* KPI Stat Cards — ทันสมัย */}
      <div className="stat-cards-grid">
        {[
          { icon: 'M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4', value: stats?.total_tickets ?? 0, label: 'Ticket ทั้งหมด', color: '#7C3AED', sub: 'ทุกสถานะ' },
          { icon: 'M12 6v6l4 2', value: stats?.new ?? 0, label: 'รอรับเรื่อง', color: '#F59E0B', sub: 'ยังไม่มีช่างรับ' },
          { icon: 'M13 10V3L4 14h7v7l9-11h-7z', value: stats?.in_progress ?? 0, label: 'กำลังดำเนินการ', color: '#2563EB', sub: 'อยู่ระหว่างซ่อม' },
          { icon: 'M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z', value: stats?.resolved ?? 0, label: 'ซ่อมเสร็จ', color: '#10B981', sub: 'รอ/ปิดงาน' },
          { icon: 'M12 19l9 2-9-18-9 18 9-2zm0 0v-8', value: stats?.high ?? 0, label: 'ความเร่งด่วนสูง', color: '#EF4444', sub: 'high+critical' },
          { icon: 'M3 6h18M3 12h18M3 18h18', value: stats?.total_devices ?? 0, label: 'อุปกรณ์ทั้งหมด', color: '#6B7280', sub: 'ที่ลงทะเบียน' },
        ].map((kpi) => (
          <div key={kpi.label} className="kpi-card" style={{
            background: 'var(--color-surface)', borderRadius: 'var(--radius-md)',
            border: '1px solid var(--color-border)', padding: '16px 18px',
            display: 'flex', flexDirection: 'column', gap: 10,
            transition: 'transform 0.15s, box-shadow 0.15s',
          }}>
            <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
              <div style={{
                width: 40, height: 40, borderRadius: 12, display: 'flex', alignItems: 'center', justifyContent: 'center',
                background: `${kpi.color}1a`,
              }}>
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke={kpi.color} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d={kpi.icon} />
                </svg>
              </div>
              <span style={{ fontSize: '0.68rem', color: 'var(--color-text-tertiary)' }}>{kpi.sub}</span>
            </div>
            <div>
              <div style={{ fontSize: '1.7rem', fontWeight: 800, lineHeight: 1, color: 'var(--color-text)' }}>{kpi.value}</div>
              <div style={{ fontSize: '0.78rem', color: 'var(--color-text-secondary)', marginTop: 5, fontWeight: 600 }}>{kpi.label}</div>
            </div>
          </div>
        ))}
      </div>

      {/* Charts Row */}
      <div className="charts-row">
        <div className="chart-card">
          <div className="card-header">
            <span className="card-title">สถานะ Ticket</span>
            <span className="card-badge">ปัจจุบัน</span>
          </div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={statusChartData} margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="name" tick={{ fontSize: 11 }} stroke="#9894A4" />
                <YAxis tick={{ fontSize: 11 }} stroke="#9894A4" />
                <RechartsTooltip
                  contentStyle={{
                    borderRadius: 8, border: '1px solid var(--color-border)',
                    background: 'var(--color-surface)', fontSize: 12,
                  }}
                />
                <Bar dataKey="value" radius={[4, 4, 0, 0]} barSize={32}>
                  {statusChartData.map((entry, i) => (
                    <Cell key={i} fill={entry.color} />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>

        <div className="chart-card">
          <div className="card-header">
            <span className="card-title">ยอด Ticket รายเดือน</span>
            <span className="card-badge">2026</span>
          </div>
          <div className="chart-container">
            <ResponsiveContainer width="100%" height="100%">
              <BarChart data={monthlyData} margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="var(--color-border)" />
                <XAxis dataKey="month" tick={{ fontSize: 11 }} stroke="#9894A4" />
                <YAxis tick={{ fontSize: 11 }} stroke="#9894A4" />
                <RechartsTooltip
                  contentStyle={{
                    borderRadius: 8, border: '1px solid var(--color-border)',
                    background: 'var(--color-surface)', fontSize: 12,
                  }}
                />
                <Bar dataKey="value" fill="#7C3AED" radius={[6, 6, 0, 0]} barSize={40} />
              </BarChart>
            </ResponsiveContainer>
          </div>
        </div>
      </div>

      {/* Pie chart: อุปกรณ์ตามประเภท */}
      <div className="chart-card" style={{ marginBottom: 'var(--spacing-xl)' }}>
        <div className="card-header">
          <span className="card-title">อุปกรณ์ตามประเภท</span>
          <span className="card-badge">ทั้งหมด {stats?.total_devices ?? 0} เครื่อง</span>
        </div>
        <div className="chart-pie-container">
          {deviceTypeData.length === 0 ? (
            <div className="empty-state" style={{ padding: '40px' }}>
              <span className="empty-text">ยังไม่มีข้อมูลอุปกรณ์</span>
            </div>
          ) : (
            <ResponsiveContainer width="100%" height="100%">
              <PieChart>
                <Pie
                  data={deviceTypeData}
                  cx="50%"
                  cy="50%"
                  innerRadius={60}
                  outerRadius={100}
                  dataKey="value"
                  paddingAngle={2}
                >
                  {deviceTypeData.map((entry, i) => (
                    <Cell key={i} fill={DEVICE_PIE_COLORS[i % DEVICE_PIE_COLORS.length]} />
                  ))}
                </Pie>
                <RechartsTooltip
                  contentStyle={{
                    borderRadius: 8, border: '1px solid var(--color-border)',
                    background: 'var(--color-surface)', fontSize: 12,
                  }}
                />
                <Legend
                  verticalAlign="bottom"
                  iconType="circle"
                  iconSize={8}
                  formatter={(value) => value}
                />
              </PieChart>
            </ResponsiveContainer>
          )}
        </div>
      </div>

      {/* Tickets Table */}
      <div className="page-section">
        <div className="section-header">
          <span className="section-title">Ticket ล่าสุด</span>
        </div>
        <div className="section-body">
          {filteredTicketsEntities.length === 0 ? (
            <div className="empty-state" style={{ padding: '32px 16px' }}>
              <svg className="empty-icon" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="5" width="18" height="14" rx="2"/>
                <path d="M3 10h18M8 20a2 2 0 004 0M12 20a2 2 0 004 0M16 20a2 2 0 004 0"/>
              </svg>
              <span className="empty-text">ยังไม่มี Ticket</span>
            </div>
          ) : (
            <div className="table-wrap">
              <table className="data-table">
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
                      <td className="table-id">{ticket.ticket_id}</td>
                      <td>
                        <div className="table-meta">
                          <span style={{ fontWeight: 500 }}>{ticket.device_id}</span>
                        </div>
                      </td>
                      <td>{ticket.title}</td>
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
                      <td style={{ color: 'var(--color-text-tertiary)', fontSize: '0.8rem' }}>
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
      <div className="page-section">
        <div className="section-header">
          <span className="section-title">อุปกรณ์ทั้งหมด</span>
          <span className="section-subnote" style={{ fontSize: '0.78rem', color: 'var(--color-text-tertiary)' }}>
            สแกน QR ที่ตัวอุปกรณ์เพื่อแจ้งซ่อม
          </span>
        </div>
        <div className="section-body">
          {filteredDevices.length === 0 ? (
            <div className="empty-state" style={{ padding: '32px 16px' }}>
              <svg className="empty-icon" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="2" y="4" width="20" height="14" rx="2"/>
                <path d="M2 10h20M12 14v6"/>
              </svg>
              <span className="empty-text">ไม่มีอุปกรณ์</span>
            </div>
          ) : (
            <div className="device-grid">
              {filteredDevices.map((device) => (
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
                    {device.room_name || device.room_code || '—'} • {device.organization_name || device.organization?.name || '—'}
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
            <span className="top-bar-subtitle">{tickets.length} รายการ</span>
          </div>
        </div>
        <div className="top-bar-actions">
          <button className="btn btn-ghost" onClick={onTicketsChanged}>⟳ รีเฟรช</button>
        </div>
      </div>

      <div className="page-section">
        <div className="section-body">
          {tickets.length === 0 ? (
            <div className="empty-state" style={{ padding: '32px 16px' }}>
              <svg className="empty-icon" width="36" height="36" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5">
                <rect x="3" y="5" width="18" height="14" rx="2"/>
                <path d="M3 10h18M8 20a2 2 0 004 0M12 20a2 2 0 004 0M16 20a2 2 0 004 0"/>
              </svg>
              <span className="empty-text">ไม่มี Ticket</span>
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
                  {tickets.map((ticket) => (
                    <tr key={ticket.ticket_id}>
                      <td className="table-id">{ticket.ticket_id}</td>
                      <td>
                        <div className="table-meta">
                          <span style={{ fontWeight: 500 }}>{ticket.device_id}</span>
                          <span className="table-meta-row">{ticket.device_type || ''}</span>
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
                        <td>
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
    reporter_type: 'teacher',
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
      setSuccessTicketId(result.ticket_id || 'SC-xxxx');
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
              <div className="success-icon">✓</div>
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
                    🕘 งานแจ้งซ่อมล่าสุดของเครื่องนี้
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
                    📋 ดูสถานะงานนี้ → (ไม่ต้องเข้าสู่ระบบ)
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
                    <option value="teacher">ครูผู้สอน</option>
                    <option value="staff">เจ้าหน้าที่</option>
                    <option value="student">นักเรียน/นักศึกษา</option>
                    <option value="it_admin">เจ้าหน้าที่ IT</option>
                    <option value="other">อื่นๆ</option>
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
    reporter_type: 'teacher',
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
  const [dupAlert, setDupAlert] = useState<{ existing_ticket_no?: string; existing_status?: string } | null>(null);
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
        attachments: attachments.length > 0 ? attachments : undefined,
        ai_session_id: diag?.session_id,
        scan_gps_lat: null,
        scan_gps_lng: null,
        scan_timestamp: new Date().toISOString(),
        scan_user_agent: navigator.userAgent,
      };

      const result = await api.createTicket(payload);
      setTicketId(result.ticket_id || 'TK-xxxx');
      setSubmitted(true);
    } catch (err: any) {
      // กันแจ้งซ้ำ: อุปกรณ์มี ticket ค้างอยู่ (409 DUPLICATE_OPEN_TICKET)
      if (err?.status === 409 && err?.code === 'DUPLICATE_OPEN_TICKET') {
        setDupAlert({ existing_ticket_no: err.detail?.existing_ticket_no, existing_status: err.detail?.existing_status });
      } else {
        setError(err.message || 'เกิดข้อผิดพลาด');
      }
      setSubmitting(false);
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

  return (
    <div className="login-page">
      <div className="login-card" style={{ maxWidth: 480 }}>
        <div className="login-logo">
          <div className="login-logo-icon"><AppLogo size={22} /></div>
          <div>
            <h1 className="login-title">IWA Smart Classroom Support</h1>
            <p className="login-subtitle">แจ้งซ่อมออนไลน์ — ไม่ต้องเข้าสู่ระบบ</p>
          </div>
        </div>
        <div className="login-divider" />

        {submitted ? (
          <div className="success-state">
            <div className="success-icon">✓</div>
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
              📋 ติดตามสถานะ Ticket นี้
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

            {/* งานแจ้งซ่อมล่าสุดของเครื่องนี้ (ช่วยผู้ใช้ที่ลืมเลขหาเลขคืน) */}
            {recentLoading && (
              <div style={{ fontSize: '0.8rem', color: 'var(--color-text-tertiary)', marginBottom: 12 }}>
                กำลังตรวจสอบประวัติการแจ้งซ่อม...
              </div>
            )}
            {!recentLoading && recentTicket && !submitted && (
              <div style={{
                padding: '12px 14px', marginBottom: 16,
                background: 'var(--color-info-light)', borderRadius: 'var(--radius-md)',
                fontSize: '0.85rem', border: '1px solid var(--color-primary-light)',
              }}>
                <div style={{ fontWeight: 700, marginBottom: 6 }}>🕘 งานแจ้งซ่อมล่าสุดของเครื่องนี้</div>
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
                  📋 ดูสถานะงานนี้ → (ไม่ต้องเข้าสู่ระบบ)
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
                    <option value="teacher">ครูผู้สอน</option>
                    <option value="staff">เจ้าหน้าที่</option>
                    <option value="student">นักเรียน/นักศึกษา</option>
                    <option value="it_admin">เจ้าหน้าที่ IT</option>
                    <option value="other">อื่นๆ</option>
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

              {/* กันแจ้งซ้ำ: อุปกรณ์มี ticket ค้างอยู่ */}
              {dupAlert && (
                <div style={{
                  padding: '12px 14px',
                  marginBottom: 'var(--spacing-md)',
                  background: 'var(--color-warning-light)',
                  borderRadius: 'var(--radius-sm)',
                  fontSize: '0.85rem',
                  color: '#92400E',
                }}>
                  <div style={{ fontWeight: 600, marginBottom: 4 }}>⚠️ อุปกรณ์นี้มีการแจ้งซ่อมที่ยังไม่ปิดอยู่แล้ว</div>
                  <div>
                    Ticket ที่ค้างอยู่: <strong>{dupAlert.existing_ticket_no || '-'}</strong>
                    {' · '}สถานะ: {dupAlert.existing_status || '-'}
                  </div>
                  <a
                    href={`/?ticket=${encodeURIComponent(dupAlert.existing_ticket_no || '')}`}
                    style={{ color: 'var(--color-primary)', fontWeight: 600, fontSize: '0.8rem' }}
                  >
                    📋 ดูสถานะ Ticket นี้
                  </a>
                  <div style={{ fontSize: '0.75rem', marginTop: 4, color: '#78350F' }}>
                    กรุณารอเจ้าหน้าที่ดำเนินการงานเดิมก่อน — ระบบไม่สร้าง Ticket ซ้ำ
                  </div>
                </div>
              )}

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
                    '⟳ วิเคราะห์ใหม่'
                  ) : (
                    '🤖 ทดลองวินิจฉัยอัตโนมัติ (แนะนำวิธีแก้เบื้องต้น)'
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
                    <div style={{ fontWeight: 600, marginBottom: 6 }}>💡 {diag.title || 'วิธีแก้ไขเบื้องต้น'}</div>
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
                            setError('🎉 ดีใจด้วยที่แก้ไขได้! บันทึกเป็นกรณีแก้เองแล้ว');
                          } catch {
                            setDiag(null);
                            setForm((f) => ({ ...f, title: '', description: '' }));
                          }
                        }}
                      >
                        ✅ แก้ไขได้แล้ว
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
                          style={{
                            position: 'absolute', top: -6, right: -6,
                            background: 'var(--color-danger)', color: '#fff',
                            border: 'none', borderRadius: '50%', width: 18, height: 18,
                            fontSize: 11, cursor: 'pointer', lineHeight: '18px',
                          }}
                        >
                          ✕
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

const STATUS_ICONS: Record<string, string> = {
  new: '🕐',
  assigned: '👤',
  in_progress: '🔧',
  pending: '📦',
  waiting_parts: '📦',
  waiting_user: '👤',
  resolved: '✅',
  closed: '🔒',
  cancelled: '❌',
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
          <div className="login-logo-icon"><AppLogo size={22} /></div>
          <div>
            <h1 className="login-title">IWA Smart Classroom Support</h1>
            <p className="login-subtitle">ติดตามสถานะการแจ้งซ่อม — ไม่ต้องเข้าสู่ระบบ</p>
          </div>
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
              placeholder="กรอกเลข Ticket เช่น SC-2026-00001"
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
            {error} — ตรวจสอบเลข Ticket ให้ถูกต้อง (เช่น SC-2026-00001)
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
                    {STATUS_ICONS[ticket.status] || ''} {STATUS_LABELS_PUBLIC[ticket.status] || ticket.status}
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
                    {ticket.priority === 'critical' ? '🔥 เร่งด่วนมาก' : ticket.priority === 'high' ? 'High' : ticket.priority === 'low' ? 'Low' : 'Medium'}
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
                        {STATUS_ICONS[h.to_status || h.status] || ''}{' '}
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
            <div className="login-logo-icon"><AppLogo size={22} /></div>
            <div>
              <h1 className="login-title">IWA Smart Classroom Support</h1>
              <p className="login-subtitle">แจ้งซ่อมออนไลน์</p>
            </div>
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

  const { user } = auth;
  const needsOrgFilter = user?.role !== 'super_admin';
  const currentOrgId = user?.organization_id;

  // โหลดข้อมูลทั้งหมด (ใช้ซ้ำตอน refresh / submit / ลบ)
  const reloadData = React.useCallback(() => {
    Promise.all([
      api.getStats(),
      api.listTickets(),
      api.listDevices(100),
    ])
      .then(([s, t, d]) => { setStats(s); setTickets(t); setDevices(d); })
      .catch(() => {});
  }, []);

  // Fetch data (ครั้งแรก)
  useEffect(() => {
    reloadData();
    setLoading(false);

    // ─── สแกน QR เข้ามา (คนที่มีบัญชี): URL มี ?device=DEV-xxxx → เปิดฟอร์มแจ้งซ่อมทันที
    //     หมายเหตุ: คนที่ยังไม่ login จะถูกจัดการที่ render (PublicReportView) ก่อนถึงตรงนี้ —
    //     effect นี้ล้าง URL ได้เฉพาะเมื่อ logged-in แล้ว เพื่อไม่ให้ไปตัด ?device= ของหน้า public
    const params = new URLSearchParams(window.location.search);
    const deviceParam = params.get('device');
    if (deviceParam && auth.isAuthenticated) {
      openRepairPanel(deviceParam);
      // ล้าง query param ออกจาก URL (ไม่ให้กด refresh แล้วเปิดซ้ำ) — เฉพาะ logged-in
      window.history.replaceState({}, '', window.location.pathname);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

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
    const allowed = ROLE_MENUS[role] || ROLE_MENUS.teacher;
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
      pm: 'บำรุงรักษา',
      qrbatch: 'พิมพ์ QR',
      users: 'Users',
      reports: 'Reports',
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
  const qrDevice = qrParams.get('device');
  if (qrDevice) {
    return <PublicReportView deviceId={qrDevice} />;
  }

  // ─── สแกน QR (รูปแบบ token): URL มี ?t=xxxx → resolve token → เปิดฟอร์มแจ้งซ่อม
  const qrToken = qrParams.get('t');
  if (qrToken) {
    return <QrTokenResolveView token={qrToken} />;
  }

  // ─── ติดตามสถานะ: URL มี ?ticket=SC-xxxx (หรือ ?ticket= เปล่า) → เปิดหน้าสาธารณะติดตามสถานะ
  const trackTicket = qrParams.get('ticket');
  if (trackTicket !== null) {
    return <TrackStatusView initialTicketId={trackTicket || undefined} />;
  }

  // ─── แจ้งซ่อมสาธารณะ (คนไม่มีบัญชี): URL มี ?publicreport=1 → เปิดหน้าก่อน auth gate
  if (qrParams.get('publicreport') === '1') {
    return <PublicNoLoginReportView />;
  }

  if (!auth.isAuthenticated) {
    return <LoginPage onLogin={auth.login} />;
  }

  const role = auth.user?.role ?? 'super_admin';
  const DEVICE_PAGE_ROLE_KEY = role as DevicePageRole;
  const devicePageRole = DEVICE_PAGE_ROLES[DEVICE_PAGE_ROLE_KEY] ?? 'other';
  const devicePageRoleBadge = DEVICE_PAGE_ROLE_BADGE[DEVICE_PAGE_ROLE_KEY] ?? DEVICE_PAGE_ROLE_KEY;
  const canManage = ['super_admin', 'admin', 'it_support'].includes(role);

  const sidebarSchoolName = auth.user?.organization?.name ?? 'Smart Classroom';

  return (
    <>
      <div className="app-layout">
        <Sidebar
          activeMenu={menu}
          onMenuChange={handleMenuChange}
          schoolName={sidebarSchoolName}
          userRole={auth.user?.role}
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
                  isSuperAdmin={auth.user?.role === 'super_admin'}
                  canManage={canManage}
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
                <KBPage onBack={() => handleMenuChange('dashboard')} />
              )}
              {menu === 'pm' && (
                <PMPage onBack={() => handleMenuChange('dashboard')} />
              )}
              {menu === 'qrbatch' && (
                <QRBatchPage onBack={() => handleMenuChange('dashboard')} />
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
                <UsersPage onBack={() => handleMenuChange('dashboard')} currentUserId={auth.user?.id} />
              )}
              {menu === 'reports' && (
                <ReportsPage onBack={() => handleMenuChange('dashboard')} />
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
