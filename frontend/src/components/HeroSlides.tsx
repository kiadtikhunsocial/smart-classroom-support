import React, { useEffect, useState } from 'react';
import { AnimatePresence, motion } from 'motion/react';
import { useReducedMotion } from '../hooks/useReducedMotion';

const SLIDES = [1, 2, 3, 4, 5].map((n) => `/hero/hero-${n}.webp`);

/** พื้นหลังสไลด์ครอสเฟด + ซูมช้า ๆ; หยุดเมื่อ paused */
export default function HeroSlides({ paused }: { paused?: boolean }) {
  const reduced = useReducedMotion();
  const [i, setI] = useState(0);

  useEffect(() => {
    SLIDES.slice(1).forEach((src) => {
      const im = new Image();
      im.src = src;
    });
  }, []);

  useEffect(() => {
    if (reduced || paused) return;
    const id = setInterval(() => setI((x) => (x + 1) % SLIDES.length), 6500);
    return () => clearInterval(id);
  }, [reduced, paused]);

  return (
    <div className="hs" aria-hidden="true">
      <AnimatePresence initial={false}>
        <motion.img
          key={SLIDES[i]}
          className="hs-img"
          src={SLIDES[i]}
          alt=""
          initial={{ opacity: 0, scale: 1 }}
          animate={{ opacity: 1, scale: reduced ? 1 : 1.09 }}
          exit={{ opacity: 0 }}
          transition={{ opacity: { duration: 1.2 }, scale: { duration: 8, ease: 'linear' } }}
        />
      </AnimatePresence>
      <div className="hs-shade" />
      <div className="hs-dots">
        {SLIDES.map((_, n) => (
          <button key={n} type="button" tabIndex={-1} className={n === i ? 'is-on' : ''} onClick={() => setI(n)} />
        ))}
      </div>
    </div>
  );
}
