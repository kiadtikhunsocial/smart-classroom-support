# -*- coding: utf-8 -*-
"""Update frontend status/priority labels: open->new, completed->resolved, waiting_*->pending, medium->normal"""
import io, os, re

base = r'C:\Users\nonam\smart-classroom-support\frontend\src'

def patch_file(path, pairs):
    with io.open(path, 'r', encoding='utf-8') as f:
        s = f.read()
    orig = s
    for old, new in pairs:
        s = s.replace(old, new)
    if s != orig:
        with io.open(path, 'w', encoding='utf-8', newline='') as f:
            f.write(s)
        print('PATCHED', path)

# App.tsx
app = os.path.join(base, 'App.tsx')
patch_file(app, [
    # STATUS_COLORS
    ("open: '#EF4444', assigned: '#F59E0B', in_progress: '#2563EB',\n  waiting_parts: '#8B5CF6', waiting_user: '#EC4899',\n  completed: '#10B981', closed: '#6B7280', cancelled: '#EF4444', pending: '#6B7280',",
     "new: '#EF4444', assigned: '#F59E0B', in_progress: '#2563EB',\n  pending: '#8B5CF6', resolved: '#10B981', closed: '#6B7280', cancelled: '#EF4444',"),
    # DashboardContent stat keys
    ("{ name: 'เปิด', value: stats?.open ?? 0, color: STATUS_COLORS.open },",
     "{ name: 'เปิด', value: stats?.new ?? 0, color: STATUS_COLORS.new },"),
    ("{ name: 'เสร็จสิ้น', value: stats?.completed ?? 0, color: STATUS_COLORS.completed },",
     "{ name: 'เสร็จสิ้น', value: stats?.resolved ?? 0, color: STATUS_COLORS.resolved },"),
    # StatCard completed
    ("value={stats?.completed ?? 0}\n          label=\"เสร็จสิ้น\"",
     "value={stats?.resolved ?? 0}\n          label=\"เสร็จสิ้น\""),
    # STATUS_LABELS_TICKET
    ("open: 'รอรับเรื่อง', assigned: 'มอบหมายแล้ว', in_progress: 'กำลังดำเนินการ',\n  waiting_parts: 'รออะไหล่', waiting_user: 'รอผู้แจ้ง', completed: 'เสร็จสิ้น',\n  closed: 'ปิดงาน', cancelled: 'ยกเลิก', pending: 'รอดำเนินการ',",
     "new: 'รอรับเรื่อง', assigned: 'มอบหมายแล้ว', in_progress: 'กำลังดำเนินการ',\n  pending: 'รออะไหล่/รอภายนอก', resolved: 'เสร็จสิ้น',\n  closed: 'ปิดงาน', cancelled: 'ยกเลิก',"),
    # RepairPanel priority default
    ("priority: 'medium',", "priority: 'normal',"),
    # RepairPanel priority option label
    ("<option value=\"medium\">Medium — ปกติ</option>", "<option value=\"normal\">Normal — ปกติ</option>"),
    # PublicReportView priority default
    ("priority: 'medium',", "priority: 'normal',"),
])

# global.css badges
css = os.path.join(base, 'styles', 'global.css')
patch_file(css, [
    (".badge-open       { background: var(--color-danger-light);  color: #B91C1C; }",
     ".badge-new        { background: var(--color-danger-light);  color: #B91C1C; }"),
    (".badge-waiting_parts{ background: var(--color-warning-light); color: #B45309; }",
     ".badge-pending    { background: var(--color-warning-light); color: #B45309; }"),
    (".badge-pending    { background: var(--color-bg);            color: var(--color-text-tertiary); }",
     ".badge-resolved   { background: var(--color-success-light); color: #065F46; }"),
    (".badge-completed  { background: var(--color-success-light); color: #065F46; }",
     ".badge-resolved   { background: var(--color-success-light); color: #065F46; }"),
    (".badge-priority-medium   { background: var(--color-warning-light); color: #B45309; }",
     ".badge-priority-normal   { background: var(--color-warning-light); color: #B45309; }"),
])

# ReportsPage / SchoolsPage STATUS_LABELS
for name in ['ReportsPage.tsx', 'SchoolsPage.tsx']:
    p = os.path.join(base, 'components', name)
    if os.path.exists(p):
        patch_file(p, [
            ("'open': 'รอรับเรื่อง',", "'new': 'รอรับเรื่อง',"),
            ("'completed': 'เสร็จสิ้น',", "'resolved': 'เสร็จสิ้น',"),
            ("'waiting_parts': 'รออะไหล่',", "'pending': 'รออะไหล่/รอภายนอก',"),
            ("'waiting_user': 'รอผู้แจ้ง',", ""),
            ("'medium': 'ปกติ',", "'normal': 'ปกติ',"),
        ])

print('DONE')
