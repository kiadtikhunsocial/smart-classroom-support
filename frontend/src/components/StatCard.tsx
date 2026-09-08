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

export default function StatCard({ 
  label, 
  value, 
  icon, 
  color = '#2b6cb0',
  iconColor,
  iconLabel,
  iconEmoji,
  change,
  changeType,
}: StatCardProps) {
  const displayIcon = icon || iconEmoji || iconLabel;
  const displayColor = iconColor ? 
    (iconColor === 'purple' ? '#7C3AED' : 
     iconColor === 'red' ? '#EF4444' : 
     iconColor === 'blue' ? '#2563EB' : 
     iconColor === 'green' ? '#10B981' : 
     iconColor === 'gray' ? '#6B7280' : 
     iconColor === 'amber' ? '#F59E0B' : color) 
    : color;

  return (
    <div className="stat-card">
      {displayIcon && <div className="stat-icon" style={{ color: displayColor }}>{displayIcon}</div>}
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
