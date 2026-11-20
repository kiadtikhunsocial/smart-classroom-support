import React, { useEffect, useRef, useState } from 'react';
import { useLang } from '../publicI18n';
import { useReducedMotion } from '../hooks/useReducedMotion';

type Lang = 'th' | 'en' | 'zh' | 'ja' | 'ko';
type Txt = {
  title: string;
  sub: string;
  tabs: [string, string, string];
  caps: [string, string, string];
  field: string;
  typed: string;
  steps: [string, string, string];
  job: string;
};

const TXT: Record<Lang, Txt> = {
  th: {
    title: 'ลองดูการใช้งาน',
    sub: 'สามขั้นตอนสั้น ๆ ไม่ต้องสมัครสมาชิก',
    tabs: ['สแกน QR', 'แจ้งอาการ', 'ติดตามผล'],
    caps: ['สแกน QR ที่ติดบนอุปกรณ์ หรือกรอกรหัสอุปกรณ์', 'พิมพ์อาการสั้น ๆ แล้วกดส่ง รับเลขใบงานทันที', 'ดูสถานะงานได้ตลอด จากหน้าแรก'],
    field: 'อาการที่พบ',
    typed: 'โปรเจคเตอร์ไม่ขึ้นภาพ',
    steps: ['รับเรื่อง', 'กำลังซ่อม', 'เสร็จสิ้น'],
    job: 'ใบงาน',
  },
  en: {
    title: 'See how it works',
    sub: 'Three quick steps, no account needed',
    tabs: ['Scan QR', 'Report', 'Track'],
    caps: ['Scan the QR on the device or enter its code', 'Describe the issue and send; get a ticket number', 'Check the status any time from the home page'],
    field: 'Problem',
    typed: 'Projector shows no image',
    steps: ['Received', 'Repairing', 'Done'],
    job: 'Ticket',
  },
  zh: {
    title: '看看如何使用',
    sub: '三步搞定，无需注册',
    tabs: ['扫码', '报修', '跟踪'],
    caps: ['扫描设备上的二维码或输入设备编号', '简述故障并提交，立即获得工单号', '随时在首页查看处理进度'],
    field: '故障描述',
    typed: '投影仪没有画面',
    steps: ['已受理', '维修中', '已完成'],
    job: '工单',
  },
  ja: {
    title: '使い方を見る',
    sub: '3ステップ・登録不要',
    tabs: ['QR読取', '修理依頼', '進捗確認'],
    caps: ['機器のQRを読み取るか機器コードを入力', '症状を入力して送信、受付番号を即発行', 'トップページでいつでも進捗確認'],
    field: '症状',
    typed: 'プロジェクターが映らない',
    steps: ['受付', '修理中', '完了'],
    job: '受付番号',
  },
  ko: {
    title: '사용 방법 보기',
    sub: '3단계, 가입 불필요',
    tabs: ['QR 스캔', '수리 요청', '진행 확인'],
    caps: ['기기의 QR을 스캔하거나 기기 코드를 입력', '증상을 입력해 전송하면 접수번호 발급', '첫 화면에서 언제든 진행 상태 확인'],
    field: '증상',
    typed: '프로젝터 화면이 나오지 않음',
    steps: ['접수', '수리 중', '완료'],
    job: '접수번호',
  },
};

/** การ์ดสาธิตสามขั้นตอน: วนเองทุก ~5 วินาที หยุดเมื่อนอกจอ/hover; ไม่มีข้อมูลจริง */
export default function HomeDemo() {
  const { lang } = useLang();
  const x = TXT[(lang as Lang) in TXT ? (lang as Lang) : 'th'];
  const reduced = useReducedMotion();
  const [tab, setTab] = useState(0);
  const [hover, setHover] = useState(false);
  const [visible, setVisible] = useState(false);
  const root = useRef<HTMLElement>(null);
  const [typed, setTyped] = useState(0);
  const [stage, setStage] = useState(0);

  useEffect(() => {
    const el = root.current;
    if (!el || typeof IntersectionObserver === 'undefined') {
      setVisible(true);
      return;
    }
    const io = new IntersectionObserver(([e]) => setVisible(e.isIntersecting), { threshold: 0.25 });
    io.observe(el);
    return () => io.disconnect();
  }, []);

  useEffect(() => {
    if (reduced || hover || !visible) return;
    const id = setInterval(() => setTab((n) => (n + 1) % 3), 5200);
    return () => clearInterval(id);
  }, [reduced, hover, visible]);

  // ขั้น 2: พิมพ์อาการ  ขั้น 3: แถบสถานะเดินหน้า
  useEffect(() => {
    setTyped(0);
    setStage(0);
    if (reduced) {
      setTyped(99);
      setStage(2);
      return;
    }
    if (tab === 1) {
      const id = setInterval(() => setTyped((n) => n + 1), 70);
      return () => clearInterval(id);
    }
    if (tab === 2) {
      const t1 = setTimeout(() => setStage(1), 900);
      const t2 = setTimeout(() => setStage(2), 2300);
      return () => {
        clearTimeout(t1);
        clearTimeout(t2);
      };
    }
  }, [tab, reduced, lang]);

  return (
    <section className="pc-demo" ref={root} aria-labelledby="pc-demo-title" onMouseEnter={() => setHover(true)} onMouseLeave={() => setHover(false)}>
      <div className="pc-demo-head">
        <h2 className="pc-h3" id="pc-demo-title">{x.title}</h2>
        <p className="pc-muted">{x.sub}</p>
      </div>
      <div className="pc-demo-body">
        <div className="pc-demo-tabs" role="tablist">
          {x.tabs.map((label, n) => (
            <button key={n} type="button" role="tab" aria-selected={tab === n} className={`pc-demo-tab${tab === n ? ' is-on' : ''}`} onClick={() => setTab(n)}>
              <b>{n + 1}</b>
              <span>{label}</span>
              {tab === n && !reduced && !hover && <i className="pc-demo-prog" key={`${tab}-${lang}`} />}
            </button>
          ))}
          <p className="pc-demo-cap" aria-live="polite">{x.caps[tab]}</p>
        </div>

        <div className="pc-phone" aria-hidden="true">
          <div className="pc-phone-notch" />
          {tab === 0 && (
            <div className="pc-scan">
              <div className="pc-scan-box">
                <span className="c1" /><span className="c2" /><span className="c3" /><span className="c4" />
                <svg viewBox="0 0 7 7" className="pc-qr">
                  {'1110111 1010101 1110111 0001000 1110101 0100111 1110101'.split(' ').flatMap((row, r) =>
                    row.split('').map((c, k) => (c === '1' ? <rect key={`${r}-${k}`} x={k} y={r} width="1" height="1" rx=".15" /> : null))
                  )}
                </svg>
                <em className="pc-scan-line" />
              </div>
            </div>
          )}
          {tab === 1 && (
            <div className="pc-form">
              <small>{x.field}</small>
              <div className="pc-form-field">
                {Array.from(x.typed).slice(0, typed).join('')}
                <span className="tw-caret is-typing" />
              </div>
              <div className={`pc-form-btn${typed >= x.typed.length ? ' is-ready' : ''}`}>→</div>
            </div>
          )}
          {tab === 2 && (
            <div className="pc-track-demo">
              <small>{x.job} TK.SCHM01.26.0001-T</small>
              <ol>
                {x.steps.map((s, n) => (
                  <li key={n} className={n <= stage ? 'is-done' : ''}>
                    <b>{n <= stage ? '✓' : n + 1}</b>
                    <span>{s}</span>
                  </li>
                ))}
              </ol>
            </div>
          )}
        </div>
      </div>
    </section>
  );
}
