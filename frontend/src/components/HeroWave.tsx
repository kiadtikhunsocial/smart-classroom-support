import React, { useEffect, useRef } from 'react';
import { useReducedMotion } from '../hooks/useReducedMotion';

/** คาบคลื่น 720 หน่วย 6 คาบ เริ่มที่ x=-720 เลื่อนทีละ 720 จึงวนไม่สะดุด */
function wave(amp: number, y: number): string {
  let d = `M-720 ${y}`;
  for (let k = 0; k < 6; k++) d += ` q180 ${-amp} 360 0 t360 0`;
  return `${d} V120 H-720 Z`;
}

/** คลื่นคั่นระหว่าง hero กับเนื้อหา (ไม่เป็นสี่เหลี่ยม) — เลื่อนช้า ๆ ด้วย GSAP โหลดแบบ lazy */
export default function HeroWave() {
  const reduced = useReducedMotion();
  const a = useRef<SVGGElement>(null);
  const b = useRef<SVGGElement>(null);

  useEffect(() => {
    if (reduced) return;
    let ctx: { revert: () => void } | undefined;
    let dead = false;
    import('gsap').then(({ gsap }) => {
      if (dead) return;
      ctx = gsap.context(() => {
        gsap.fromTo(a.current, { x: 0 }, { x: 720, duration: 18, ease: 'none', repeat: -1 });
        gsap.fromTo(b.current, { x: 720 }, { x: 0, duration: 26, ease: 'none', repeat: -1 });
      });
    });
    return () => {
      dead = true;
      ctx?.revert();
    };
  }, [reduced]);

  return (
    <svg className="hw" viewBox="0 0 1440 120" preserveAspectRatio="none" aria-hidden="true">
      <g ref={b} opacity="0.4">
        <path d={wave(34, 56)} fill="var(--pc-bg)" />
      </g>
      <g ref={a}>
        <path d={wave(26, 84)} fill="var(--pc-bg)" />
      </g>
    </svg>
  );
}
