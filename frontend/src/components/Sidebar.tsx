import React from 'react';

interface SidebarProps {
  activeMenu: string;
  onMenuChange: (menu: string) => void;
  schoolName?: string;
  userRole?: string;
  userOrgId?: number | null;
  userName?: string;
  userAvatar?: string | null;
  open?: boolean;
  onClose?: () => void;
  onLogout?: () => void;
}

export interface MenuItem {
  id: string;
  label: string;
  icon: React.ReactNode;
  badge?: number;
}

const menuItems: MenuItem[] = [
  {
    id: 'dashboard',
    label: 'Dashboard',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="3" width="7" height="7" rx="1"/>
        <rect x="14" y="3" width="7" height="7" rx="1"/>
        <rect x="3" y="14" width="7" height="7" rx="1"/>
        <rect x="14" y="14" width="7" height="7" rx="1"/>
      </svg>
    ),
  },
  {
    id: 'devices',
    label: 'อุปกรณ์',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="2" y="4" width="20" height="14" rx="2"/>
        <path d="M2 10h20M12 14v6"/>
      </svg>
    ),
  },
  {
    id: 'scan',
    label: 'สแกน QR',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M3 7V5a2 2 0 012-2h2M17 3h2a2 2 0 012 2v2M21 17v2a2 2 0 01-2 2h-2M7 21H5a2 2 0 01-2-2v-2M7 12h10"/>
      </svg>
    ),
  },
  {
    id: 'tickets',
    label: 'Tickets',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="5" width="18" height="14" rx="2"/>
        <path d="M3 10h18M8 20a2 2 0 004 0M12 20a2 2 0 004 0M16 20a2 2 0 004 0"/>
      </svg>
    ),
  },
  {
    id: 'kb',
    label: 'ฐานความรู้',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M4 19.5A2.5 2.5 0 016.5 17H20M4 19.5A2.5 2.5 0 006.5 22H20V2H6.5A2.5 2.5 0 004 4.5v15z"/>
      </svg>
    ),
  },
  {
    id: 'qrbatch',
    label: 'พิมพ์ QR',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M4 7V5a1 1 0 011-1h2M17 4h2a1 1 0 011 1v2M20 17v2a1 1 0 01-1 1h-2M7 20H5a1 1 0 01-1-1v-2M7 8h3v3H7zM14 8h3v3h-3zM7 14h3v3H7zM14 14h3v3h-3z"/>
      </svg>
    ),
  },
  {
    id: 'pm',
    label: 'บำรุงรักษา (PM)',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <rect x="3" y="4" width="18" height="17" rx="2"/>
        <path d="M3 10h18M8 2v4M16 2v4M9 15l2 2 4-4"/>
      </svg>
    ),
  },
  {
    id: 'audit',
    label: 'ประวัติการใช้งาน',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
        <path d="M14 2v6h6M9 13h6M9 17h6"/>
      </svg>
    ),
  },
  {
    id: 'registrations',
    label: 'อนุมัติเจ้าหน้าที่',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="9" cy="8" r="4"/>
        <path d="M2 20c0-3.5 3.2-6 7-6M16 17l2 2 4-4"/>
      </svg>
    ),
  },
  {
    id: 'users',
    label: 'Users',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="8" r="4"/>
        <path d="M4 20c0-4 4-7 8-7s8 3 8 7"/>
      </svg>
    ),
  },
  {
    id: 'reports',
    label: 'Reports',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M18 20V10M12 20V4M6 20v-6"/>
      </svg>
    ),
  },
  {
    id: 'sales',
    label: 'ยอดขาย',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M12 2v20M17 5H9.5a3.5 3.5 0 000 7h5a3.5 3.5 0 010 7H6"/>
      </svg>
    ),
  },
  {
    id: 'schools',
    label: 'โรงเรียน',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <path d="M3 21h18M5 21V7l7-4 7 4v14M9 21v-4h6v4M9 10h.01M15 10h.01M9 14h.01M15 14h.01"/>
      </svg>
    ),
  },
  {
    id: 'settings',
    label: 'การตั้งค่า',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="12" r="3"/>
        <path d="M12 1v3M12 20v3M4.22 4.22l2.12 2.12M17.66 17.66l2.12 2.12M1 12h3M20 12h3M4.22 19.78l2.12-2.12M17.66 6.34l2.12-2.12"/>
      </svg>
    ),
  },
  {
    id: 'profile',
    label: 'โปรไฟล์',
    icon: (
      <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
        <circle cx="12" cy="8" r="4"/>
        <path d="M4 20c0-4 4-7 8-7s8 3 8 7"/>
      </svg>
    ),
  },
];

const baseMenuItems = menuItems.filter((i) => i.id !== 'schools');
const adminMenuItems = menuItems.filter((i) => i.id === 'schools');

// ─── บทบาทเห็นเมนูอะไรบ้าง (Role-based menu) ────────────────────────────
// super_admin   : เห็นทุกอย่าง
// admin         : จัดการรร ตัวเอง (อุปกรณ์/ติcket/user/รายงาน) — ไม่เห็นโรงเรียนอื่น/ตั้งค่าระบบ
// it_support    : ทำงานซ่อม (อุปกรณ์/สแกน/ticket/รายงาน) — ไม่จัดการ user/ตั้งค่า
// ไม่มีบทบาท teacher/student แล้ว — ผู้แจ้งซ่อมใช้หน้าแจ้งซ่อม/สแกน QR โดยไม่ต้องมีบัญชี
// บัญชีเก่าที่ยังติดบทบาทเดิมจะตกไปที่ LEGACY_FALLBACK_MENUS (เมนูจำกัดที่สุด)
// หมายเหตุสิทธิ์ฝั่ง backend: /api/pm/* → owner/super_admin/admin/it_support,
// /api/audit-logs → owner/super_admin/admin เท่านั้น (admin_school จึงไม่เห็นสองเมนูนี้)
const ROLE_MENUS: Record<string, string[]> = {
  owner: ['dashboard', 'devices', 'scan', 'tickets', 'kb', 'qrbatch', 'pm', 'sales', 'schools', 'registrations', 'users', 'reports', 'audit', 'settings', 'profile'],
  super_admin: ['dashboard', 'devices', 'scan', 'tickets', 'kb', 'qrbatch', 'pm', 'sales', 'schools', 'registrations', 'users', 'reports', 'audit', 'settings', 'profile'],
  admin: ['dashboard', 'devices', 'scan', 'tickets', 'kb', 'qrbatch', 'pm', 'sales', 'registrations', 'users', 'reports', 'audit', 'settings', 'profile'],
  admin_school: ['dashboard', 'devices', 'scan', 'tickets', 'kb', 'qrbatch', 'registrations', 'users', 'reports', 'settings', 'profile'],
  it_support: ['dashboard', 'devices', 'scan', 'tickets', 'kb', 'qrbatch', 'pm', 'sales', 'reports', 'settings', 'profile'],
};

export const LEGACY_FALLBACK_MENUS = ['dashboard', 'tickets', 'settings', 'profile'];

// it_support ที่มีสังกัด (สร้างโดย admin_school) ไม่เห็น ยอดขาย (sales) / การตั้งค่าโรงเรียน
export function visibleMenusForRole(role: string | undefined, organizationId?: number | null): string[] {
  const base = ROLE_MENUS[role || ''] || LEGACY_FALLBACK_MENUS;
  let menus = [...base];
  if (role === 'it_support' && organizationId) {
    menus = menus.filter((m) => m !== 'sales');
  }
  return menus;
}

export { ROLE_MENUS };

// เรียงเมนูตามลำดับเดิมใน menuItems
const ROLE_MENU_ORDER = ['dashboard', 'devices', 'scan', 'tickets', 'kb', 'qrbatch', 'pm', 'sales', 'schools', 'registrations', 'users', 'reports', 'audit', 'settings', 'profile'];

function visibleMenusFor(role: string | undefined, organizationId?: number | null): MenuItem[] {
  const allowed = visibleMenusForRole(role, organizationId);
  return ROLE_MENU_ORDER
    .filter((id) => allowed.includes(id))
    .map((id) => menuItems.find((i) => i.id === id)!)
    .filter(Boolean);
}

// ─── หมวดหมู่เมนู (จัดกลุ่มเพื่อการอ่าน ไม่เกี่ยวกับสิทธิ์) ──────────────────
// สิทธิ์การมองเห็นยังคุมด้วย ROLE_MENUS/visibleMenusForRole เท่านั้น
// กลุ่มไหนไม่มีเมนูที่ผู้ใช้เห็นได้เลย จะไม่ถูก render ทั้งกลุ่ม
const MENU_GROUPS: { label: string; ids: string[] }[] = [
  { label: 'ภาพรวม', ids: ['dashboard', 'reports'] },
  { label: 'งานซ่อม', ids: ['tickets', 'scan', 'pm'] },
  { label: 'คลังอุปกรณ์', ids: ['devices', 'qrbatch', 'kb'] },
  { label: 'จัดการระบบ', ids: ['schools', 'registrations', 'users', 'sales', 'audit'] },
  { label: 'บัญชีของฉัน', ids: ['settings', 'profile'] },
];

export default function Sidebar({ activeMenu, onMenuChange, schoolName = 'Smart Classroom Support', userRole, userOrgId, userName, userAvatar, open, onClose, onLogout }: SidebarProps) {
  const visibleItems = visibleMenusFor(userRole, userOrgId);

  // เมนูที่ยังไม่ได้จัดกลุ่ม (เผื่อมีการเพิ่ม id ใหม่ในอนาคต) — ต้องไม่หายไปจาก UI
  const groupedIds: Record<string, true> = {};
  MENU_GROUPS.forEach((g) => g.ids.forEach((id) => { groupedIds[id] = true; }));
  const ungroupedItems = visibleItems.filter((i) => !groupedIds[i.id]);

  const renderLink = (item: MenuItem) => (
    <li key={item.id}>
      <button
        type="button"
        className={`sidebar-link${activeMenu === item.id ? ' active' : ''}`}
        onClick={() => { onMenuChange(item.id); onClose?.(); }}
        aria-current={activeMenu === item.id ? 'page' : undefined}
      >
        <span className="sidebar-link-icon">{item.icon}</span>
        <span className="sidebar-link-label">{item.label}</span>
        {item.badge !== undefined && item.badge > 0 && (
          <span className="sidebar-link-badge" aria-label={`${item.badge} รายการใหม่`}>{item.badge}</span>
        )}
      </button>
    </li>
  );

  return (
    <>
      {/* Overlay เฉพาะมือถือ — คลิกปิด */}
      <div className={`sidebar-overlay${open ? ' open' : ''}`} onClick={onClose} />
      <aside className={`sidebar${open ? ' open' : ''}`}>
        <div className="sidebar-top">
          <div className="sidebar-brand">
            <a href="/?home=1" aria-label="ไปหน้าแรกแจ้งซ่อม" style={{ display: 'flex', alignItems: 'center', textDecoration: 'none', color: 'inherit', gap: 10 }}>
              <div className="sidebar-brand-icon">
                <img src="/logo.jpg" alt="IWA" style={{ width: 34, height: 34, objectFit: 'contain', borderRadius: 8 }} />
              </div>
              <div>
                <div className="sidebar-brand-text">Smart Classroom Support</div>
                <div className="sidebar-brand-sub">{schoolName}</div>
              </div>
            </a>
            <button className="sidebar-close-mobile" onClick={onClose} aria-label="ปิดเมนู">
              <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2">
                <path d="M18 6L6 18M6 6l12 12"/>
              </svg>
            </button>
          </div>
        </div>

        <nav className="sidebar-nav" aria-label="เมนูหลัก">
          {MENU_GROUPS.map((group) => {
            const items = group.ids
              .map((id) => visibleItems.find((i) => i.id === id))
              .filter((i): i is MenuItem => Boolean(i));
            if (items.length === 0) return null;
            return (
              <div className="sidebar-group" key={group.label}>
                <span className="sidebar-nav-section-label">{group.label}</span>
                <ul className="sidebar-nav-items">
                  {items.map(renderLink)}
                </ul>
              </div>
            );
          })}
          {ungroupedItems.length > 0 && (
            <div className="sidebar-group">
              <span className="sidebar-nav-section-label">อื่น ๆ</span>
              <ul className="sidebar-nav-items">
                {ungroupedItems.map(renderLink)}
              </ul>
            </div>
          )}
        </nav>

        <div className="sidebar-footer">
          <div className="sidebar-footer-user">
            {userAvatar ? (
              <img className="sidebar-footer-avatar" src={userAvatar} alt="" style={{ objectFit: 'cover' }} />
            ) : (
              <div className="sidebar-footer-avatar">{(userName || 'U').charAt(0).toUpperCase()}</div>
            )}
            <div>
              <div className="sidebar-footer-name">{userName || 'ผู้ใช้'}</div>
              <div className="sidebar-footer-role">{userRole || ''}</div>
            </div>
          </div>
          {onLogout && (
            <button className="sidebar-logout" onClick={onLogout}>
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" style={{ marginRight: 6, verticalAlign: 'middle' }}>
                <path d="M9 21H5a2 2 0 01-2-2V5a2 2 0 012-2h4M16 17l5-5-5-5M21 12H9"/>
              </svg>
              ออกจากระบบ
            </button>
          )}
        </div>
      </aside>
    </>
  );
}
