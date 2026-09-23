/* ============================================================================
   DashboardCharts.tsx — กราฟทั้งหมดของหน้า Dashboard
   ----------------------------------------------------------------------------
   แยกออกจาก App.tsx เพื่อให้ recharts (+ d3/victory-vendor ~86 kB gzip)
   ถูกโหลดเฉพาะเมื่อผู้ใช้เปิดหน้า Dashboard จริง ๆ
   หน้าอื่น (login, หน้าแจ้งซ่อมสาธารณะ, หน้าสแกน) จึงไม่ต้องดาวน์โหลดเลย
   → App.tsx เรียกผ่าน React.lazy + Suspense

   หมายเหตุสำคัญเรื่องสี: recharts ใส่สีเป็น attribute ของ <svg> ซึ่งไม่ขยาย
   var() ให้ จึงต้องอ่านค่าที่คำนวณแล้วด้วย cssVar() ทุกครั้งที่ render และ
   บังคับ re-render เมื่อธีมเปลี่ยนด้วย useThemeVersion()
   ========================================================================== */

import React from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer, PieChart, Pie, Cell, Legend
} from 'recharts';
import { useThemeVersion, chartPalette, cssVar } from '../theme';

/** สถานะ Ticket — สีถูกคิดมาจากฝั่ง App (STATUS_COLORS ของธีมปัจจุบัน) */
export type StatusDatum = { name: string; value: number; color: string };
/** ยอดรายเดือน — month เป็นรูปแบบ YYYY-MM */
export type MonthlyDatum = { month: string; value: number };
/** สัดส่วนอุปกรณ์ตามประเภท (มาจาก /api/stats by_type) */
export type DeviceTypeDatum = { name: string; value: number };

export interface DashboardChartsProps {
  statusData: StatusDatum[];
  monthlyData: MonthlyDatum[];
  /** ป้ายช่วงปีของกราฟรายเดือน เช่น "2026" หรือ "2025–2026" */
  monthlyRangeLabel: string;
  deviceTypeData: DeviceTypeDatum[];
  totalDevices: number;
}

/** สไตล์ tooltip ใช้ร่วมกันทุกกราฟ — ตรงนี้เป็น CSS property ปกติ ใช้ var() ได้
 *  --fx-* มาจาก dashboard-futuristic.css (ประกาศที่ .dsh-page) ซึ่ง tooltip อยู่ภายใน
 *  จึงสืบทอดค่าได้ และมี fallback เป็น token เดิมเผื่อ render นอกหน้าแรก */
const TOOLTIP_STYLE: React.CSSProperties = {
  borderRadius: 10,
  border: '1px solid var(--fx-line, var(--color-border))',
  background: 'var(--fx-glass-2, var(--color-surface))',
  backdropFilter: 'blur(10px)',
  WebkitBackdropFilter: 'blur(10px)',
  boxShadow: '0 14px 34px -20px rgba(0, 0, 0, 0.75), 0 0 20px -12px rgba(36, 155, 255, 0.85)',
  color: 'var(--color-text)',
  fontSize: 12,
};

/** เงาเมาส์บนแท่งกราฟ — โทนฟ้าอ่อนแทนสีเทาเริ่มต้นของ recharts */
const BAR_CURSOR = { fill: 'rgba(36, 155, 255, 0.10)' } as const;

/* ── สีที่ recharts ต้องได้เป็น "ค่าที่คำนวณแล้ว" ────────────────────────────
   recharts ใส่สีเป็น attribute ของ <svg> ซึ่งไม่ขยาย var() ให้ — เดิมจึงอ่านผ่าน
   cssVar() ที่ดูจาก :root  แต่หน้าแรก (dashboard-futuristic.css) ทับ
   --chart-grid / --chart-axis / --color-surface ไว้ที่ .dsh-page ไม่ใช่ :root
   → ค่าที่ได้จาก :root เป็นโทนดำอมเทาของโหมดมืดเดิม ไม่ใช่ navy ของหน้านี้
   วิธีแก้: อ่านจาก element ที่อยู่ในหน้าจริง (custom property สืบทอดลงมาให้แล้ว)
   ค่าเริ่มต้นยังใช้ :root เพื่อให้ render รอบแรกมีสีถูกต้องพอใช้ ไม่กระพริบ */
type ScopedChartVars = {
  grid: string;
  axis: string;
  pieStroke: string;
  barFrom: string;
  barTo: string;
};

const CHART_VAR_FALLBACK: ScopedChartVars = {
  grid: '#EAEBF3',
  axis: '#86868F',
  pieStroke: '#FFFFFF',
  barFrom: '#249BFF',
  barTo: '#7C4DFF',
};

function readRootChartVars(): ScopedChartVars {
  return {
    grid: cssVar('--chart-grid', CHART_VAR_FALLBACK.grid),
    axis: cssVar('--chart-axis', CHART_VAR_FALLBACK.axis),
    pieStroke: cssVar('--color-surface', CHART_VAR_FALLBACK.pieStroke),
    barFrom: cssVar('--chart-1', CHART_VAR_FALLBACK.barFrom),
    barTo: cssVar('--chart-8', CHART_VAR_FALLBACK.barTo),
  };
}

function readScopedChartVars(el: HTMLElement | null): ScopedChartVars | null {
  if (!el || typeof window === 'undefined') return null;
  const cs = window.getComputedStyle(el);
  const pick = (name: string, fallback: string) =>
    cs.getPropertyValue(name).trim() || fallback;
  return {
    grid: pick('--chart-grid', CHART_VAR_FALLBACK.grid),
    axis: pick('--chart-axis', CHART_VAR_FALLBACK.axis),
    pieStroke: pick('--color-surface', CHART_VAR_FALLBACK.pieStroke),
    barFrom: pick('--chart-1', CHART_VAR_FALLBACK.barFrom),
    barTo: pick('--chart-8', CHART_VAR_FALLBACK.barTo),
  };
}

function sameChartVars(a: ScopedChartVars, b: ScopedChartVars): boolean {
  return (
    a.grid === b.grid &&
    a.axis === b.axis &&
    a.pieStroke === b.pieStroke &&
    a.barFrom === b.barFrom &&
    a.barTo === b.barTo
  );
}

export default function DashboardCharts({
  statusData,
  monthlyData,
  monthlyRangeLabel,
  deviceTypeData,
  totalDevices,
}: DashboardChartsProps) {
  // ธีมเปลี่ยน → อ่าน token สีชุดใหม่ (ตัวนับนี้ยังบังคับ re-render ให้ด้วย)
  const themeVersion = useThemeVersion();

  // ref วางบน .dsh-charts ซึ่งอยู่ใต้ .dsh-page → ได้ token ที่ถูกทับไว้จริง
  const chartsRef = React.useRef<HTMLDivElement>(null);
  const [vars, setVars] = React.useState<ScopedChartVars>(readRootChartVars);

  React.useEffect(() => {
    const scoped = readScopedChartVars(chartsRef.current);
    if (!scoped) return;
    // เทียบก่อน set เพื่อไม่ให้ re-render ซ้ำเมื่อค่าเท่าเดิม
    setVars((prev) => (sameChartVars(prev, scoped) ? prev : scoped));
  }, [themeVersion]);

  const { grid, axis, pieStroke, barFrom, barTo } = vars;
  const axisTick = { fontSize: 11, fill: axis };
  const devicePieColors = chartPalette();

  return (
    <>
      {/* Charts Row — ref ใช้อ่าน CSS variable ที่หน้านี้ทับไว้ (ดู ScopedChartVars) */}
      <div className="dsh-charts" ref={chartsRef}>
        <div className="dsh-card">
          <div className="dsh-card-head">
            <span className="dsh-card-title">สถานะ Ticket</span>
            <span className="dsh-card-badge">ปัจจุบัน</span>
          </div>
          <div className="dsh-chart-box">
            {statusData.length === 0 ? (
              <div className="dsh-empty">ยังไม่มี Ticket</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={statusData} margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
                  <CartesianGrid strokeDasharray="3 3" stroke={grid} />
                  <XAxis dataKey="name" tick={axisTick} stroke={axis} />
                  <YAxis tick={axisTick} stroke={axis} />
                  <RechartsTooltip contentStyle={TOOLTIP_STYLE} cursor={BAR_CURSOR} />
                  <Bar dataKey="value" radius={[4, 4, 0, 0]} barSize={32}>
                    {statusData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="dsh-card">
          <div className="dsh-card-head">
            <span className="dsh-card-title">ยอด Ticket รายเดือน</span>
            <span className="dsh-card-badge">{monthlyRangeLabel}</span>
          </div>
          <div className="dsh-chart-box">
            {monthlyData.length === 0 ? (
              <div className="dsh-empty">ยังไม่มี Ticket</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={monthlyData} margin={{ top: 10, right: 10, left: 10, bottom: 10 }}>
                  {/* เกรเดียนต์ของแท่ง — id ต้องไม่ชนกับ svg อื่นในหน้า จึงใส่ prefix fx- */}
                  <defs>
                    <linearGradient id="fx-bar-monthly" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={barTo} stopOpacity={0.95} />
                      <stop offset="100%" stopColor={barFrom} stopOpacity={0.65} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke={grid} />
                  <XAxis dataKey="month" tick={axisTick} stroke={axis} />
                  <YAxis tick={axisTick} stroke={axis} />
                  <RechartsTooltip contentStyle={TOOLTIP_STYLE} cursor={BAR_CURSOR} />
                  <Bar
                    dataKey="value"
                    fill="url(#fx-bar-monthly)"
                    radius={[6, 6, 0, 0]}
                    barSize={40}
                  />
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      {/* Pie chart: อุปกรณ์ตามประเภท */}
      <div className="dsh-card">
        <div className="dsh-card-head">
          <span className="dsh-card-title">อุปกรณ์ตามประเภท</span>
          <span className="dsh-card-badge">ทั้งหมด {totalDevices} เครื่อง</span>
        </div>
        <div className="dsh-chart-box dsh-chart-box--pie">
          {deviceTypeData.length === 0 ? (
            <div className="dsh-empty">ยังไม่มีข้อมูลอุปกรณ์</div>
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
                    <Cell
                      key={i}
                      fill={devicePieColors[i % devicePieColors.length]}
                      stroke={pieStroke}
                      strokeWidth={2}
                    />
                  ))}
                </Pie>
                <RechartsTooltip contentStyle={TOOLTIP_STYLE} />
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
    </>
  );
}