import React, { useEffect, useState } from 'react';
import { useLang } from '../publicI18n';
import { useReducedMotion } from '../hooks/useReducedMotion';

type Lang = 'th' | 'en' | 'zh' | 'ja' | 'ko';
type Step = { name: string; log: string; time: string };
type Txt = { badge: string; device: string; issue: string; status: string[]; eta: string; etaDone: string; steps: Step[] };

const TIMES = ['09:02', '09:10', '09:45', '10:20', '10:35'];
const mk = (names: string[], logs: string[]): Step[] => names.map((name, i) => ({ name, log: logs[i], time: TIMES[i] }));

const TXT: Record<Lang, Txt> = {
  th: {
    badge: 'ตัวอย่าง',
    device: 'โปรเจคเตอร์ · ห้อง 3/2',
    issue: 'ไม่มีภาพขึ้นจอ',
    status: ['รับเรื่องแล้ว', 'มอบหมายช่างแล้ว', 'กำลังซ่อม', 'กำลังทดสอบ', 'เสร็จสิ้น'],
    eta: 'คาดว่าเสร็จภายใน 1 ชม.',
    etaDone: 'ปิดงานเรียบร้อย',
    steps: mk(
      ['แจ้งซ่อม', 'มอบหมาย', 'ซ่อม', 'ทดสอบ', 'เสร็จสิ้น'],
      ['ระบบรับเรื่องและออกเลขใบงานให้ทันที', 'ช่างเทคนิครับงานและนัดเวลาเข้าตรวจ', 'ตรวจพบสาย HDMI ชำรุด กำลังเปลี่ยน', 'ทดสอบการแสดงภาพและเสียงกับห้องเรียน', 'ใช้งานได้ปกติ แจ้งผลกลับให้ผู้แจ้ง']
    ),
  },
  en: {
    badge: 'Sample',
    device: 'Projector · Room 3/2',
    issue: 'No picture on screen',
    status: ['Received', 'Assigned', 'Repairing', 'Testing', 'Done'],
    eta: 'Expected within 1 hr',
    etaDone: 'Ticket closed',
    steps: mk(
      ['Reported', 'Assigned', 'Repair', 'Test', 'Done'],
      ['Ticket number issued instantly', 'A technician accepts and schedules a visit', 'Faulty HDMI cable found, replacing it', 'Checking picture and sound in the room', 'Working again, reporter notified']
    ),
  },
  zh: {
    badge: '示例',
    device: '投影仪 · 3/2 教室',
    issue: '屏幕没有画面',
    status: ['已受理', '已派单', '维修中', '测试中', '已完成'],
    eta: '预计 1 小时内完成',
    etaDone: '工单已关闭',
    steps: mk(
      ['报修', '派单', '维修', '测试', '完成'],
      ['系统立即生成工单号', '技术员接单并预约上门时间', '发现 HDMI 线损坏，正在更换', '在教室测试画面与声音', '恢复正常，已通知报修人']
    ),
  },
  ja: {
    badge: 'サンプル',
    device: 'プロジェクター · 3/2教室',
    issue: '画面が映らない',
    status: ['受付済み', '担当決定', '修理中', 'テスト中', '完了'],
    eta: '1時間以内に完了予定',
    etaDone: '受付を完了しました',
    steps: mk(
      ['依頼', '割当', '修理', 'テスト', '完了'],
      ['受付番号をすぐに発行', '技術担当が受諾し訪問時間を調整', 'HDMIケーブルの不良を確認、交換中', '教室で映像と音声を確認', '正常に動作、依頼者へ連絡済み']
    ),
  },
  ko: {
    badge: '예시',
    device: '프로젝터 · 3/2 교실',
    issue: '화면이 나오지 않음',
    status: ['접수됨', '배정됨', '수리 중', '테스트 중', '완료'],
    eta: '1시간 내 완료 예정',
    etaDone: '접수가 종료되었습니다',
    steps: mk(
      ['요청', '배정', '수리', '테스트', '완료'],
      ['접수번호가 즉시 발급됩니다', '기술자가 수락하고 방문 시간을 정합니다', 'HDMI 케이블 불량 확인, 교체 중', '교실에서 화면과 소리 확인', '정상 작동, 요청자에게 알림']
    ),
  },
};

/** ตัวอย่างหน้าติดตามงาน (ข้อมูลจำลอง) — เดินสถานะเองเป็นวง เติมช่องว่างใต้ช่องค้นหา */
export default function TrackPreview() {
  const { lang } = useLang();
  const x = TXT[(lang as Lang) in TXT ? (lang as Lang) : 'th'];
  const reduced = useReducedMotion();
  const last = x.steps.length - 1;
  const [stage, setStage] = useState(reduced ? last : 0);

  useEffect(() => {
    if (reduced) {
      setStage(last);
      return;
    }
    const id = setTimeout(() => setStage((s) => (s >= last ? 0 : s + 1)), stage >= last ? 3200 : 2000);
    return () => clearTimeout(id);
  }, [stage, reduced, last]);

  const pct = (stage / last) * 100;
  const done = stage === last;

  return (
    <div className="pc-prev" aria-hidden="true">
      <div className="pc-prev-head">
        <span className="pc-prev-no">TK.SCHM01.26.0001-T</span>
        <span className="pc-prev-badge">{x.badge}</span>
        <span className={`pc-prev-status${done ? ' is-done' : ''}`} key={stage}>{x.status[stage]}</span>
      </div>
      <div className="pc-prev-dev">
        <b>{x.device}</b>
        <span>{x.issue}</span>
      </div>

      <div className="pc-prev-steps">
        <div className="pc-prev-line"><i style={{ width: `${pct}%` }} /></div>
        {x.steps.map((s, n) => (
          <div key={n} className={`pc-prev-step${n < stage ? ' is-past' : ''}${n === stage ? ' is-now' : ''}`}>
            <b>{n < stage || done ? '✓' : n + 1}</b>
            <span>{s.name}</span>
          </div>
        ))}
      </div>

      <ul className="pc-prev-log">
        {x.steps.slice(0, stage + 1).map((s, n) => (
          <li key={`${lang}-${n}`} className={n === stage ? 'is-new' : ''}>
            <time>{s.time}</time>
            <span>{s.log}</span>
          </li>
        ))}
      </ul>

      <div className="pc-prev-foot">
        <span className={`pc-prev-dot${done ? ' is-done' : ''}`} />
        {done ? x.etaDone : x.eta}
      </div>
    </div>
  );
}
