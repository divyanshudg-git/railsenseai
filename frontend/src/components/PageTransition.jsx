import { motion as Motion, useReducedMotion } from 'framer-motion';

export function PageTransition({ children }) {
  const reducedMotion = useReducedMotion();

  return (
    <Motion.div
      initial={reducedMotion ? { opacity: 0 } : { opacity: 0, y: 26, scale: 0.992, filter: 'blur(6px)' }}
      animate={reducedMotion ? { opacity: 1 } : { opacity: 1, y: 0, scale: 1, filter: 'blur(0px)' }}
      exit={reducedMotion ? { opacity: 0 } : { opacity: 0, y: -20, scale: 0.995, filter: 'blur(4px)' }}
      transition={{ duration: 0.48, ease: [0.23, 1, 0.32, 1] }}
      className="min-h-[60vh]"
    >
      {children}
    </Motion.div>
  );
}
