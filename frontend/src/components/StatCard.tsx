import React from 'react';

interface StatCardProps {
  label: string;
  value: number | string;
  icon?: string;
  color?: string;
  iconColor?: string;
  iconLabel?: string;
  iconEmoji?: string;
  change?: string;
  changeType?: string;
}

/**
 * ชื่อสีเชิงความหมาย → CSS token ของธีม
 * ไม่เก็บค่าเลขฐานสิบหกไว้ในคอมโพเนนต์ เพื่อให้สลับโหมดสว่าง/มืด
 * และเปลี่ยนสีเน้นแล้วการ์ดเปลี่ยนตามทันทีโดยไม่ต้อง re-render
 */
const ICON_COLOR_VARS: Record<string, string> = {
  purple: '--color-primary',
  primary: '--color-primary',
  blue: '--status-in-progress',
  green: '--status-resolved',
  teal: '--color-success',
  amber: '--status-assigned',
  orange: '--chart-10',
  red: '--status-new',
  rose: '--color-danger',
  gray: '--color-muted',
};

/** สี hardcode ที่หน้าอื่นยังส่งเข้ามา — จับคู่กับ token ให้เปลี่ยนตามธีมด้วย */
const LEGACY_HEX_VARS: Record<string, string> = {
  '#7c3aed': '--color-primary',
  '#5b5bd6': '--color-primary',
  '#2563eb': '--status-in-progress',
  '#2b6cb0': '--status-in-progress',
  '#f59e0b': '--status-assigned',
  '#10b981': '--status-resolved',
  '#ef4444': '--status-new',
  '#8b5cf6': '--status-pending',
  '#6b7280': '--color-muted',
};

function toThemeColor(raw?: string): string {
  const value = (raw ?? '').trim();
  if (!value) return 'var(--color-primary)';
  if (value.startsWith('var(') || value.startsWith('--')) {
    return value.startsWith('--') ? `var(${value})` : value;
  }
  const token = LEGACY_HEX_VARS[value.toLowerCase()];
  return token ? `var(${token}, ${value})` : value;
}

export default function StatCard({
  label,
  value,
  icon,
  color,
  iconColor,
  iconLabel,
  iconEmoji,
  change,
  changeType,
}: StatCardProps) {
  const displayIcon = icon || iconEmoji || iconLabel;

  const namedToken = iconColor ? ICON_COLOR_VARS[iconColor.toLowerCase()] : undefined;
  const displayColor = namedToken
    ? `var(${namedToken})`
    : toThemeColor(iconColor || color);

  return (
    <div className="stat-card">
      {displayIcon && (
        <div className="stat-icon" style={{ color: displayColor }} aria-hidden="true">
          {displayIcon}
        </div>
      )}
      <div className="stat-value" style={{ color: displayColor }}>{value}</div>
      <div className="stat-label">{label}</div>
      {change && (
        <div className={`stat-change ${changeType === 'up' ? 'up' : changeType === 'down' ? 'down' : ''}`}>
          {change}
        </div>
      )}
    </div>
  );
}