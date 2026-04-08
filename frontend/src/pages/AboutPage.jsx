import { motion as Motion } from 'framer-motion';
import { HeartHandshake, Telescope, WandSparkles } from 'lucide-react';
import { PageTransition } from '../components/PageTransition';

const values = [
  {
    icon: HeartHandshake,
    title: 'Human-centered engineering',
    copy: 'Every screen is designed to reduce operator load and make high-stakes decisions clearer.',
  },
  {
    icon: Telescope,
    title: 'Long-horizon reliability',
    copy: 'We optimize for practical deployment metrics, not one-off benchmark wins.',
  },
  {
    icon: WandSparkles,
    title: 'Crafted product feel',
    copy: 'Industrial software does not have to look industrial-era. This experience is intentionally premium.',
  },
];

export function AboutPage() {
  return (
    <PageTransition>
      <section className="mx-auto w-full max-w-7xl px-6 pt-14 md:px-10">
        <p className="text-xs uppercase tracking-[0.3em] text-cyan-200">About The Developer</p>
        <h1 className="mt-4 max-w-3xl font-display text-4xl tracking-tight text-slate-50 md:text-5xl">
          Built by a reliability-focused developer who obsesses over both model quality and product experience.
        </h1>
        <p className="mt-6 max-w-3xl text-base leading-relaxed text-slate-300">
          This platform was crafted to bridge a common gap in ML products: strong modeling with weak UX. The goal is a
          system where engineering insight feels immediate, beautiful, and trustworthy in real operations.
        </p>
      </section>

      <section className="mx-auto mt-12 grid w-full max-w-7xl gap-5 px-6 md:grid-cols-3 md:px-10">
        {values.map((value, index) => (
          <Motion.article
            key={value.title}
            initial={{ opacity: 0, y: 20 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.45, delay: index * 0.08 }}
            className="rounded-3xl border border-white/10 bg-white/[0.04] p-6"
          >
            <div className="inline-flex rounded-2xl border border-cyan-100/20 bg-cyan-100/10 p-3 text-cyan-100">
              <value.icon className="h-5 w-5" />
            </div>
            <h2 className="mt-4 font-display text-xl text-slate-50">{value.title}</h2>
            <p className="mt-3 text-sm leading-relaxed text-slate-300">{value.copy}</p>
          </Motion.article>
        ))}
      </section>
    </PageTransition>
  );
}
