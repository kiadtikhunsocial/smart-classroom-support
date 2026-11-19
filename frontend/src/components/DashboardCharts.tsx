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

   อ่านง่ายทั้งสองโหมด:
   - tooltip เป็นคอมโพเนนต์ของเราเอง (.dsh-tip ใน dashboard.css) ใช้ token ของธีม
     เดิม recharts ระบายตัวอักษรในทูลทิปเป็นสีดำตายตัว → มองไม่เห็นบนพื้น navy
   - สถานะใบงาน เป็นแท่งแนวนอน: ป้ายภาษาไทยยาว ๆ ไม่ชนกัน/ไม่หาย และมีตัวเลขท้ายแท่ง
   - วงล้ออุปกรณ์แสดง 8 ประเภทแรก + "อื่น ๆ" เพื่อไม่ให้สีซ้ำ และมีตารางสีข้าง ๆ
     บอกจำนวน/เปอร์เซ็นต์ ชี้ที่แถวไหนชิ้นในวงล้อจะเด่นขึ้น
   ========================================================================== */

import React from 'react';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RechartsTooltip,
  ResponsiveContainer, PieChart, Pie, Cell, LabelList, Sector,
} from 'recharts';
import { useThemeVersion, chartPalette, cssVar } from '../theme';

/** สถานะใบงาน — สีถูกคิดมาจากฝั่ง App (STATUS_COLORS ของธีมปัจจุบัน) */
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

/* ── สีที่ recharts ต้องได้เป็น "ค่าที่คำนวณแล้ว" ────────────────────────────
   อ่านจาก element ที่อยู่ในหน้าจริง เพราะ dashboard-futuristic.css ทับ token
   ไว้ที่ .dsh-page ไม่ใช่ :root  ค่าเริ่มต้นอ่านจาก :root เพื่อไม่ให้กระพริบ */
type ScopedChartVars = {
  grid: string;
  axis: string;
  label: string;
  pieStroke: string;
  barFrom: string;
  barTo: string;
};

const CHART_VAR_FALLBACK: ScopedChartVars = {
  grid: '#EAEBF3',
  axis: '#86868F',
  label: '#1F2030',
  pieStroke: '#FFFFFF',
  barFrom: '#249BFF',
  barTo: '#7C4DFF',
};

const VAR_NAMES: Record<keyof ScopedChartVars, string> = {
  grid: '--chart-grid',
  axis: '--chart-axis',
  label: '--color-text',
  pieStroke: '--color-surface',
  barFrom: '--chart-1',
  barTo: '--chart-8',
};

function readRootChartVars(): ScopedChartVars {
  const out = { ...CHART_VAR_FALLBACK };
  (Object.keys(VAR_NAMES) as (keyof ScopedChartVars)[]).forEach((k) => {
    out[k] = cssVar(VAR_NAMES[k], CHART_VAR_FALLBACK[k]);
  });
  return out;
}

function readScopedChartVars(el: HTMLElement | null): ScopedChartVars | null {
  if (!el || typeof window === 'undefined') return null;
  const cs = window.getComputedStyle(el);
  const out = { ...CHART_VAR_FALLBACK };
  (Object.keys(VAR_NAMES) as (keyof ScopedChartVars)[]).forEach((k) => {
    out[k] = cs.getPropertyValue(VAR_NAMES[k]).trim() || CHART_VAR_FALLBACK[k];
  });
  return out;
}

function sameChartVars(a: ScopedChartVars, b: ScopedChartVars): boolean {
  return (Object.keys(a) as (keyof ScopedChartVars)[]).every((k) => a[k] === b[k]);
}

/** เงาเมาส์บนแท่งกราฟ — โทนฟ้าอ่อนแทนสีเทาเริ่มต้นของ recharts */
const BAR_CURSOR = { fill: 'rgba(36, 155, 255, 0.10)' } as const;

const nf = new Intl.NumberFormat('th-TH');

/** ทูลทิปของเราเอง — สีมาจาก CSS (.dsh-tip) จึงอ่านออกทั้งโหมดมืดและสว่าง */
function ChartTip({
  active, payload, label, unit, total,
}: {
  active?: boolean;
  payload?: any[];
  label?: string;
  unit: string;
  total?: number;
}) {
  if (!active || !payload?.length) return null;
  const p = payload[0];
  const name = label ?? p?.payload?.name ?? p?.name;
  const value = Number(p?.value ?? 0);
  const color = p?.payload?.color || p?.payload?.fill || p?.color;
  const pct = total ? ` (${((value / total) * 100).toFixed(1)}%)` : '';
  return (
    <div className="dsh-tip">
      <div className="dsh-tip-title">
        {color && <span className="dsh-tip-dot" style={{ background: color }} />}
        {name}
      </div>
      <div className="dsh-tip-value">
        {nf.format(value)} {unit}{pct}
      </div>
      {p?.payload?.members && (
        <div className="dsh-tip-note">{p.payload.members}</div>
      )}
    </div>
  );
}

/** แสดงชื่อเดือนแบบไทยสั้น ๆ เช่น 2026-07 → ก.ค. 69 */
const TH_MONTHS = ['ม.ค.', 'ก.พ.', 'มี.ค.', 'เม.ย.', 'พ.ค.', 'มิ.ย.', 'ก.ค.', 'ส.ค.', 'ก.ย.', 'ต.ค.', 'พ.ย.', 'ธ.ค.'];
function monthLabel(ym: string): string {
  const m = /^(\d{4})-(\d{2})$/.exec(ym || '');
  if (!m) return ym;
  const be = (Number(m[1]) + 543) % 100;
  return `${TH_MONTHS[Number(m[2]) - 1]} ${String(be).padStart(2, '0')}`;
}

/** ชิ้นวงล้อที่ถูกชี้ — ขยายออกเล็กน้อยให้เห็นชัดว่าตรงกับแถวไหน */
function ActiveSlice(props: any) {
  return <Sector {...props} outerRadius={props.outerRadius + 7} />;
}

/** 8 ประเภทแรกได้สีไม่ซ้ำ (ข้าม --chart-8 ที่ใกล้สีม่วงหลัก และ --chart-9 สีเทาที่สงวนให้ "อื่น ๆ") */
const PIE_TOP_N = 8;
const PIE_COLOR_ORDER = [0, 1, 2, 3, 4, 5, 6, 9];

export default function DashboardCharts({
  statusData,
  monthlyData,
  monthlyRangeLabel,
  deviceTypeData,
  totalDevices,
}: DashboardChartsProps) {
  // ธีมเปลี่ยน → อ่าน token สีชุดใหม่ (ตัวนับนี้ยังบังคับ re-render ให้ด้วย)
  const themeVersion = useThemeVersion();

  const chartsRef = React.useRef<HTMLDivElement>(null);
  const [vars, setVars] = React.useState<ScopedChartVars>(readRootChartVars);
  const [activeSlice, setActiveSlice] = React.useState<number | undefined>(undefined);

  React.useEffect(() => {
    const scoped = readScopedChartVars(chartsRef.current);
    if (!scoped) return;
    setVars((prev) => (sameChartVars(prev, scoped) ? prev : scoped));
  }, [themeVersion]);

  const { grid, axis, label, pieStroke, barFrom, barTo } = vars;
  const axisTick = { fontSize: 12, fill: axis };
  const valueLabel = { fontSize: 12, fontWeight: 700, fill: label } as const;

  const ticketTotal = statusData.reduce((s, d) => s + d.value, 0);
  const monthly = monthlyData.map((d) => ({ ...d, name: monthLabel(d.month) }));

  // วงล้อ: เรียงมากไปน้อย → 8 อันดับแรก + รวมที่เหลือเป็น "อื่น ๆ"
  // (จานสีมี 10 สี ถ้าแสดง 17 ประเภทสีจะซ้ำกันจนแยกไม่ออก)
  const palette = chartPalette();
  const deviceSlices = React.useMemo(() => {
    const sorted = [...deviceTypeData].sort((a, b) => b.value - a.value);
    const top = sorted.slice(0, PIE_TOP_N);
    const rest = sorted.slice(PIE_TOP_N);
    const slices: { name: string; value: number; members?: string }[] = [...top];
    if (rest.length) {
      slices.push({
        name: `อื่น ๆ (${rest.length} ประเภท)`,
        value: rest.reduce((s, d) => s + d.value, 0),
        members: rest.map((d) => `${d.name} ${d.value}`).join(' · '),
      });
    }
    return slices;
  }, [deviceTypeData]);
  const deviceSum = deviceSlices.reduce((s, d) => s + d.value, 0) || 1;
  const sliceColor = (i: number) =>
    i >= PIE_TOP_N ? pieOtherColor(palette) : palette[PIE_COLOR_ORDER[i]] || palette[i % palette.length];

  return (
    <>
      <div className="dsh-charts" ref={chartsRef}>
        <div className="dsh-card">
          <div className="dsh-card-head">
            <span className="dsh-card-title">สถานะใบงาน</span>
            <span className="dsh-card-badge">ทั้งหมด {nf.format(ticketTotal)} ใบ</span>
          </div>
          <div className="dsh-chart-box">
            {statusData.length === 0 ? (
              <div className="dsh-empty">ยังไม่มีใบงาน</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                {/* แท่งแนวนอน: ชื่อสถานะภาษาไทยยาว ๆ อยู่ซ้ายครบทุกตัว ไม่โดนซ่อน */}
                <BarChart
                  data={statusData}
                  layout="vertical"
                  margin={{ top: 4, right: 36, left: 4, bottom: 4 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke={grid} horizontal={false} />
                  <XAxis type="number" tick={axisTick} stroke={axis} allowDecimals={false} />
                  <YAxis
                    type="category"
                    dataKey="name"
                    tick={{ ...axisTick, fill: label }}
                    stroke={axis}
                    width={104}
                    interval={0}
                  />
                  <RechartsTooltip
                    cursor={BAR_CURSOR}
                    content={<ChartTip unit="ใบ" total={ticketTotal} />}
                  />
                  <Bar dataKey="value" isAnimationActive={false} radius={[0, 6, 6, 0]} barSize={18}>
                    {statusData.map((entry, i) => (
                      <Cell key={i} fill={entry.color} />
                    ))}
                    <LabelList dataKey="value" position="right" style={valueLabel} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>

        <div className="dsh-card">
          <div className="dsh-card-head">
            <span className="dsh-card-title">ใบงานรายเดือน</span>
            <span className="dsh-card-badge">{monthlyRangeLabel}</span>
          </div>
          <div className="dsh-chart-box">
            {monthly.length === 0 ? (
              <div className="dsh-empty">ยังไม่มีใบงาน</div>
            ) : (
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={monthly} margin={{ top: 22, right: 10, left: -8, bottom: 4 }}>
                  {/* id ต้องไม่ชนกับ svg อื่นในหน้า จึงใส่ prefix fx- */}
                  <defs>
                    <linearGradient id="fx-bar-monthly" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor={barTo} stopOpacity={0.95} />
                      <stop offset="100%" stopColor={barFrom} stopOpacity={0.7} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke={grid} vertical={false} />
                  <XAxis dataKey="name" tick={axisTick} stroke={axis} interval={0} />
                  <YAxis tick={axisTick} stroke={axis} allowDecimals={false} />
                  <RechartsTooltip cursor={BAR_CURSOR} content={<ChartTip unit="ใบ" />} />
                  <Bar dataKey="value" isAnimationActive={false} fill="url(#fx-bar-monthly)" radius={[6, 6, 0, 0]} maxBarSize={44}>
                    <LabelList dataKey="value" position="top" style={valueLabel} />
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            )}
          </div>
        </div>
      </div>

      {/* วงล้อ: อุปกรณ์ตามประเภท + ตารางสีบอกจำนวน */}
      <div className="dsh-card">
        <div className="dsh-card-head">
          <span className="dsh-card-title">อุปกรณ์ตามประเภท</span>
          <span className="dsh-card-badge">ทั้งหมด {nf.format(totalDevices)} เครื่อง</span>
        </div>
        {deviceSlices.length === 0 ? (
          <div className="dsh-chart-box"><div className="dsh-empty">ยังไม่มีข้อมูลอุปกรณ์</div></div>
        ) : (
          <div className="dsh-donut">
            <div className="dsh-donut-chart">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={deviceSlices}
                    cx="50%"
                    cy="50%"
                    innerRadius="58%"
                    outerRadius="86%"
                    dataKey="value"
                    paddingAngle={1.5}
                    activeIndex={activeSlice}
                    activeShape={ActiveSlice}
                    onMouseEnter={(_, i) => setActiveSlice(i)}
                    onMouseLeave={() => setActiveSlice(undefined)}
                    isAnimationActive={false}
                  >
                    {deviceSlices.map((_, i) => (
                      <Cell key={i} fill={sliceColor(i)} stroke={pieStroke} strokeWidth={2} />
                    ))}
                  </Pie>
                </PieChart>
              </ResponsiveContainer>
              {/* ตัวเลขกลางวง — เปลี่ยนตามชิ้นที่ชี้ */}
              <div className="dsh-donut-center" aria-hidden="true">
                <strong>
                  {nf.format(activeSlice !== undefined ? deviceSlices[activeSlice].value : deviceSum)}
                </strong>
                <span>
                  {activeSlice !== undefined ? deviceSlices[activeSlice].name.replace(/ \(.*\)$/, '') : 'เครื่องทั้งหมด'}
                </span>
              </div>
            </div>

            <ul className="dsh-donut-legend">
              {deviceSlices.map((d, i) => (
                <li
                  key={d.name}
                  className={activeSlice === i ? 'is-active' : undefined}
                  onMouseEnter={() => setActiveSlice(i)}
                  onMouseLeave={() => setActiveSlice(undefined)}
                  title={d.members}
                >
                  <span className="dsh-donut-dot" style={{ background: sliceColor(i) }} />
                  <span className="dsh-donut-name">{d.name}</span>
                  <span className="dsh-donut-num">{nf.format(d.value)}</span>
                  <span className="dsh-donut-pct">{((d.value / deviceSum) * 100).toFixed(0)}%</span>
                </li>
              ))}
            </ul>
          </div>
        )}
      </div>
    </>
  );
}

/** "อื่น ๆ" ใช้สีเทาของจาน (--chart-9) ให้ดูเป็นกลุ่มรวม ไม่แย่งความสนใจ */
function pieOtherColor(palette: string[]): string {
  return palette[8] || '#9CA3AF';
}
