import React from 'react';
import { motion } from 'motion/react';
import { useReducedMotion } from '../hooks/useReducedMotion';

type Props = {
  children: React.ReactNode;
  delay?: number;
  y?: number;
  as?: 'div' | 'section' | 'nav' | 'footer';
  className?: string;
  [k: string]: unknown;
};

/** เลื่อนขึ้น+ค่อย ๆ โผล่เมื่อเข้าจอ (ครั้งเดียว) */
export default function Reveal({ children, delay = 0, y = 22, as = 'div', className, ...rest }: Props) {
  const reduced = useReducedMotion();
  if (reduced) return React.createElement(as, { className, ...rest }, children);
  const Tag = (motion as any)[as];
  return (
    <Tag
      className={className}
      initial={{ opacity: 0, y }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '0px 0px -8% 0px' }}
      transition={{ duration: 0.6, delay, ease: [0.22, 1, 0.36, 1] }}
      {...rest}
    >
      {children}
    </Tag>
  );
}
