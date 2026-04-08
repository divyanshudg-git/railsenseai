import { useRef } from 'react';
import { motion as Motion, useReducedMotion, useScroll, useTransform } from 'framer-motion';

export function CinematicSection({ children, className = '', glowClass = 'from-cyan-400/15 via-transparent to-amber-300/10' }) {
  const ref = useRef(null);
  const reducedMotion = useReducedMotion();
  const { scrollYProgress } = useScroll({
    target: ref,
    offset: ['start 0.92', 'end 0.24'],
  });

  const opacity = useTransform(scrollYProgress, [0, 0.18, 1], [0, 0.82, 1]);
  const y = useTransform(scrollYProgress, [0, 1], [reducedMotion ? 0 : 52, 0]);
  const scale = useTransform(scrollYProgress, [0, 1], [reducedMotion ? 1 : 0.985, 1]);
  const glowY = useTransform(scrollYProgress, [0, 1], [36, -24]);

  return (
    <Motion.section
      ref={ref}
      style={{ opacity, y, scale }}
      className={`relative ${className}`}
    >
      <Motion.div
        aria-hidden="true"
        style={{ y: reducedMotion ? 0 : glowY }}
        className={`pointer-events-none absolute inset-0 -z-10 rounded-[2rem] bg-gradient-to-br blur-2xl ${glowClass}`}
      />
      {children}
    </Motion.section>
  );
}
