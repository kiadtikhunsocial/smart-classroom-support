import { useMemo, useState } from 'react';

export type Rating = {
  id: number;
  target: 'bot' | 'staff';
  score: number;
  resolved: boolean | null;
  ticket_id: string | null;
  created_at: string;
};

type RatingSummary = {
  count: number;
  average: number;
  scores: Record<string, number>;
  solved?: number;
  not_solved?: number;
};

export type Ratings = {
  days: number;
  summary: Record<'bot' | 'staff', RatingSummary>;
  recent: Rating[];
};

type TargetFilter = 'all' | 'bot' | 'staff';
type ResultFilter = 'all' | 'solved' | 'not_solved' | 'unspecified';

const dateFormatter = new Intl.DateTimeFormat('th-TH', {
  dateStyle: 'medium', timeStyle: 'short', timeZone: 'Asia/Bangkok',
});

function ratingCount(summary: RatingSummary, score: number) {
  return Number(summary.scores?.[String(score)] || 0);
}

function percent(part: number, total: number) {
  return total > 0 ? Math.round((part / total) * 100) : 0;
}

function ScoreDistribution({ title, subtitle, summary }: { title: string; subtitle: string; summary: RatingSummary }) {
  const max = Math.max(1, ...[1, 2, 3, 4, 5].map((score) => ratingCount(summary, score)));
  return <section className="ratings-panel ratings-distribution dsh-card" aria-label={`การกระจายคะแนน${title}`}>
    <div className="ratings-panel-heading"><div><h3>{title}</h3><p>{subtitle}</p></div><span>{summary.count} ครั้ง</span></div>
    {[5, 4, 3, 2, 1].map((score) => {
      const count = ratingCount(summary, score);
      return <div className="ratings-bar-row" key={score}>
        <span className="ratings-bar-label">{score} ดาว</span>
        <div className="ratings-bar-track" role="img" aria-label={`${score} ดาว ${count} ครั้ง`}>
          <div className={`ratings-bar-fill ${score <= 2 ? 'is-low' : ''}`} style={{ width: `${percent(count, max)}%` }} />
        </div>
        <strong>{count}</strong>
      </div>;
    })}
  </section>;
}

export default function RatingsResults({ ratings, days, onDaysChange, onRefresh }: {
  ratings: Ratings | null;
  days: number;
  onDaysChange: (days: number) => void;
  onRefresh: () => void;
}) {
  const [targetFilter, setTargetFilter] = useState<TargetFilter>('all');
  const [scoreFilter, setScoreFilter] = useState('all');
  const [resultFilter, setResultFilter] = useState<ResultFilter>('all');
  const [ticketQuery, setTicketQuery] = useState('');

  const bot = ratings?.summary.bot;
  const staff = ratings?.summary.staff;
  const botCount = bot?.count || 0;
  const staffCount = staff?.count || 0;
  const solved = bot?.solved || 0;
  const notSolved = bot?.not_solved || 0;
  const knownOutcomes = solved + notSolved;
  const lowScores = (bot ? ratingCount(bot, 1) + ratingCount(bot, 2) : 0)
    + (staff ? ratingCount(staff, 1) + ratingCount(staff, 2) : 0);

  const filtered = useMemo(() => (ratings?.recent || []).filter((row) => {
    if (targetFilter !== 'all' && row.target !== targetFilter) return false;
    if (scoreFilter !== 'all' && row.score !== Number(scoreFilter)) return false;
    if (resultFilter !== 'all') {
      if (row.target !== 'bot') return false;
      if (resultFilter === 'solved' && row.resolved !== true) return false;
      if (resultFilter === 'not_solved' && row.resolved !== false) return false;
      if (resultFilter === 'unspecified' && row.resolved !== null) return false;
    }
    return !ticketQuery.trim() || (row.ticket_id || '').toLocaleLowerCase().includes(ticketQuery.trim().toLocaleLowerCase());
  }), [ratings, targetFilter, scoreFilter, resultFilter, ticketQuery]);

  return <div className="ratings-page dsh-page">
    <header className="ratings-hero dsh-hero">
      <div><span className="ratings-eyebrow">CUSTOMER FEEDBACK · LINE OA</span>
        <h2>เสียงจากลูกค้า หลังได้รับความช่วยเหลือ</h2>
        <p>ดูผลของบอทและเจ้าหน้าที่แยกกัน เพื่อเห็นทั้งการแก้ปัญหาเบื้องต้นและคุณภาพงานซ่อม</p>
      </div>
      <button className="btn btn-secondary" type="button" onClick={onRefresh}>↻ โหลดข้อมูลใหม่</button>
    </header>

    <nav className="ratings-periods" aria-label="เลือกช่วงเวลาผลประเมิน">
      {[7, 30, 90, 365].map((period) => <button key={period} type="button"
        className={`ratings-period ${days === period ? 'is-active' : ''}`}
        aria-pressed={days === period} onClick={() => onDaysChange(period)}>
        {period === 365 ? '1 ปี' : `${period} วัน`}
      </button>)}
      <span>นับย้อนหลังจากวันนี้ · เวลาไทย</span>
    </nav>

    <div className="ratings-kpis">
      <div className="ratings-kpi dsh-kpi"><span>คะแนนแชตบอต</span><strong>{botCount ? bot?.average.toFixed(1) : '—'}<small>{botCount ? ' / 5' : ''}</small></strong><p>จาก {botCount} การประเมิน</p></div>
      <div className="ratings-kpi dsh-kpi"><span>บอทช่วยแก้ได้</span><strong>{knownOutcomes ? `${percent(solved, knownOutcomes)}%` : '—'}</strong><p>{knownOutcomes ? `${solved} จาก ${knownOutcomes} รายการที่ระบุผล` : 'ยังไม่มีรายการที่ระบุผล'}</p></div>
      <div className="ratings-kpi dsh-kpi"><span>คะแนนเจ้าหน้าที่</span><strong>{staffCount ? staff?.average.toFixed(1) : '—'}<small>{staffCount ? ' / 5' : ''}</small></strong><p>จาก {staffCount} การประเมิน</p></div>
      <div className={`ratings-kpi dsh-kpi ${lowScores ? 'ratings-kpi-attention' : ''}`}><span>คะแนนต่ำที่ควรดู</span><strong>{lowScores}</strong><p>คะแนน 1–2 ดาว รวมทั้งสองประเภท</p></div>
    </div>

    <div className="ratings-insights">
      <ScoreDistribution title="แชตบอต" subtitle="คำแนะนำแก้ปัญหาเบื้องต้น" summary={bot || { count: 0, average: 0, scores: {} }} />
      <ScoreDistribution title="เจ้าหน้าที่" subtitle="การดูแลหลังงานซ่อม" summary={staff || { count: 0, average: 0, scores: {} }} />
    </div>

    <div className="ratings-outcomes dsh-card">
      <div><strong>ผลจากการคุยกับบอท</strong><span>เฉพาะลูกค้าที่ระบุผลเอง</span></div>
      <div className="ratings-outcome-pills"><span className="is-solved">แก้ได้ {solved}</span><span className="is-unsolved">ยังไม่หาย {notSolved}</span><span>ไม่ระบุผล {Math.max(0, botCount - knownOutcomes)}</span></div>
    </div>

    <section className="ratings-records dsh-card">
      <div className="ratings-records-head"><div><h3>รายการประเมินล่าสุด</h3><p>แสดง {filtered.length} จาก {ratings?.recent.length || 0} รายการล่าสุด (ระบบส่งกลับสูงสุด 200 รายการ)</p></div></div>
      <div className="ratings-filters">
        <label>ประเภท<select className="form-select" value={targetFilter} onChange={(e) => { setTargetFilter(e.target.value as TargetFilter); if (e.target.value === 'staff') setResultFilter('all'); }}><option value="all">ทั้งหมด</option><option value="bot">แชตบอต</option><option value="staff">เจ้าหน้าที่</option></select></label>
        <label>คะแนน<select className="form-select" value={scoreFilter} onChange={(e) => setScoreFilter(e.target.value)}><option value="all">ทุกคะแนน</option>{[5, 4, 3, 2, 1].map((score) => <option key={score} value={score}>{score} ดาว</option>)}</select></label>
        <label>ผลแก้เบื้องต้น<select className="form-select" value={resultFilter} onChange={(e) => setResultFilter(e.target.value as ResultFilter)} disabled={targetFilter === 'staff'}><option value="all">ทุกผล</option><option value="solved">แก้ได้</option><option value="not_solved">ยังไม่หาย</option><option value="unspecified">ไม่ระบุผล</option></select></label>
        <label>เลขใบงาน<input className="form-input" value={ticketQuery} onChange={(e) => setTicketQuery(e.target.value)} placeholder="ค้นหา Ticket" aria-label="ค้นหาตามเลขใบงาน" /></label>
      </div>
      {!ratings ? <div className="ratings-empty">กำลังโหลดผลประเมิน…</div>
        : filtered.length === 0 ? <div className="ratings-empty"><strong>{ratings.recent.length ? 'ไม่พบรายการที่ตรงกับตัวกรอง' : 'ยังไม่มีผลประเมินในช่วงนี้'}</strong><p>{ratings.recent.length ? 'ลองเปลี่ยนช่วงเวลา ประเภท หรือคะแนน' : 'เมื่อมีลูกค้าประเมินผ่าน LINE รายการจะปรากฏที่นี่'}</p></div>
          : <div className="studio-table-wrap"><table className="data-table ratings-table"><thead><tr><th>วันที่ · เวลาไทย</th><th>ประเมิน</th><th>คะแนน</th><th>ผลแก้เบื้องต้น</th><th>เลขใบงาน</th></tr></thead><tbody>{filtered.map((row) => <tr key={row.id}>
            <td data-label="วันที่">{dateFormatter.format(new Date(row.created_at))}</td>
            <td data-label="ประเมิน"><span className={`ratings-type ${row.target}`}>{row.target === 'bot' ? 'แชตบอต' : 'เจ้าหน้าที่'}</span></td>
            <td data-label="คะแนน"><span className={`ratings-score ${row.score <= 2 ? 'is-low' : ''}`}>{row.score} / 5 ★</span></td>
            <td data-label="ผลแก้เบื้องต้น">{row.target === 'staff' ? '—' : row.resolved === true ? <span className="ratings-result is-solved">แก้ได้</span> : row.resolved === false ? <span className="ratings-result is-unsolved">ยังไม่หาย</span> : 'ไม่ระบุ'}</td>
            <td data-label="เลขใบงาน" className="ratings-ticket">{row.ticket_id || '—'}</td>
          </tr>)}</tbody></table></div>}
      <p className="ratings-footnote">คะแนนบอทและเจ้าหน้าที่เป็นคนละช่วงบริการ ไม่ควรนำคะแนนเฉลี่ยมารวมกัน · การประเมินเจ้าหน้าที่เปิดเมื่อแจ้งว่างานซ่อมเสร็จแล้ว</p>
    </section>
  </div>;
}
