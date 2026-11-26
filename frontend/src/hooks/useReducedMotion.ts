import { useEffect, useState } from 'react';

/** true เมื่อผู้ใช้ตั้งค่าลดการเคลื่อนไหวในระบบ — ใช้ปิดพิมพ์ดีด/สไลด์/คลื่น */
export function useReducedMotion(): boolean {
  const [reduced, setReduced] = useState(
    () => typeof window !== 'undefined' && !!window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
  );
  useEffect(() => {
    const mq = window.matchMedia?.('(prefers-reduced-motion: reduce)');
    if (!mq) return;
    const on = () => setReduced(mq.matches);
    mq.addEventListener('change', on);
    return () => mq.removeEventListener('change', on);
  }, []);
  return reduced;
}
