import { motion as Motion, useScroll, useSpring } from 'framer-motion';

export function ScrollProgress() {
  const { scrollYProgress } = useScroll();
  const scaleX = useSpring(scrollYProgress, {
    stiffness: 180,
    damping: 24,
    mass: 0.25,
  });

  return (
    <Motion.div
      className="pointer-events-none fixed left-0 right-0 top-0 z-[70] h-1 origin-left bg-gradient-to-r from-cyan-300 via-emerald-200 to-amber-300"
      style={{ scaleX }}
    />
  );
}
