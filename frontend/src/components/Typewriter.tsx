import React, { useEffect, useRef, useState } from 'react';
import { useReducedMotion } from '../hooks/useReducedMotion';

function graphemes(s: string): string[] {
  const Seg = (Intl as any).Segmenter;
  if (!Seg) return Array.from(s);
  return Array.from(new Seg(undefined, { granularity: 'grapheme' }).segment(s), (x: any) => x.segment as string);
}

type Props = {
  text: string;
  speed?: number;
  deleteSpeed?: number;
  startDelay?: number;
  caret?: boolean;
  className?: string;
};

/**
 * พิมพ์ข้อความทีละตัว; เมื่อ text เปลี่ยน (เช่นเปลี่ยนภาษา) จะลบของเดิมก่อนแล้วพิมพ์ใหม่
 * ข้อความเต็มซ่อนไว้ใต้ตัวพิมพ์เพื่อจองความสูง กันเลย์เอาต์กระโดด
 */
export default function Typewriter({ text, speed = 38, deleteSpeed = 16, startDelay = 250, caret = true, className }: Props) {
  const reduced = useReducedMotion();
  // full = ข้อความที่กำลังพิมพ์/ลบอยู่ (ทั้งก้อน) ส่วน n = จำนวนตัวที่โชว์
  // ส่วนที่ยังไม่พิมพ์ render เป็น visibility:hidden จึงตัดบรรทัดเหมือนข้อความเต็มเสมอ (ไม่กระโดด/ไม่ซ้อน)
  const [state, setState] = useState<{ full: string[]; n: number; typing: boolean }>({ full: graphemes(text), n: 0, typing: true });
  const ref = useRef(state);
  ref.current = state;

  useEffect(() => {
    const target = graphemes(text);
    if (reduced) {
      setState({ full: target, n: target.length, typing: false });
      return;
    }
    let timer: ReturnType<typeof setTimeout>;
    let cancelled = false;
    const set = (v: { full: string[]; n: number; typing: boolean }) => { ref.current = v; setState(v); };

    const step = () => {
      if (cancelled) return;
      const { full, n } = ref.current;
      let common = 0;
      while (common < n && common < target.length && full[common] === target[common]) common++;
      if (n > common) {
        set({ full, n: n - 1, typing: true });
        timer = setTimeout(step, deleteSpeed);
        return;
      }
      // ลบเสร็จ: สลับไปข้อความใหม่ที่จุดนี้ แล้วพิมพ์ต่อ
      const cur = ref.current.full === target ? full : target;
      if (n < target.length) {
        set({ full: cur, n: n + 1, typing: true });
        timer = setTimeout(step, speed);
      } else {
        set({ full: target, n, typing: false });
      }
    };
    timer = setTimeout(step, ref.current.n ? 0 : startDelay);
    return () => { cancelled = true; clearTimeout(timer); };
  }, [text, reduced, speed, deleteSpeed, startDelay]);

  const shown = state.full.slice(0, state.n).join('');
  const rest = state.full.slice(state.n).join('');
  return (
    <span className={`tw ${className || ''}`}>
      <span aria-hidden="true">
        {shown}
        {caret && <span className={`tw-caret${state.typing ? ' is-typing' : ''}`} />}
        <span className="tw-rest">{rest}</span>
      </span>
      <span className="tw-sr">{text}</span>
    </span>
  );
}
