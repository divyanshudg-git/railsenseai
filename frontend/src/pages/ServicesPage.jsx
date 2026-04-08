import { motion as Motion } from 'framer-motion';
import { DatabaseZap, ChartNoAxesCombined, Workflow, BotMessageSquare } from 'lucide-react';
import { PageTransition } from '../components/PageTransition';

const cards = [
  {
    icon: DatabaseZap,
    title: 'Data Pipeline Engineering',
    description:
      'Sensor ingestion, cleaning, feature generation, and validation windows tuned for industrial cadence and reliability.',
  },
  {
    icon: ChartNoAxesCombined,
    title: 'Model Calibration',
    description:
      'Threshold strategy aligned to false-alert budgets, event recall goals, and lead-time constraints for deployment reality.',
  },
  {
    icon: Workflow,
    title: 'UX For Operators',
    description:
      'Control-room experiences with actionable alerts, explainability layers, and crisp visual triage patterns.',
  },
  {
    icon: BotMessageSquare,
    title: 'Decision Support API',
    description:
      'Prediction endpoints for single-case and batch scoring that plug into downstream workflows and monitoring stacks.',
  },
];

export function ServicesPage() {
  return (
    <PageTransition>
      <section className="mx-auto w-full max-w-7xl px-6 pt-14 md:px-10">
        <p className="text-xs uppercase tracking-[0.3em] text-cyan-200">Services</p>
        <h1 className="mt-4 max-w-3xl font-display text-4xl tracking-tight text-slate-50 md:text-5xl">
          Built for teams that need reliability and design excellence together.
        </h1>
        <p className="mt-5 max-w-3xl text-slate-300">
          The stack combines model rigor with modern product design so engineers can make fast, confident decisions.
        </p>
      </section>

      <section className="mx-auto mt-12 grid w-full max-w-7xl gap-5 px-6 md:grid-cols-2 md:px-10">
        {cards.map((card, index) => (
          <Motion.article
            key={card.title}
            initial={{ opacity: 0, y: 24 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.5, delay: index * 0.08 }}
            className="rounded-3xl border border-white/10 bg-white/[0.04] p-7"
          >
            <div className="inline-flex rounded-2xl border border-amber-200/20 bg-amber-300/10 p-3 text-amber-100">
              <card.icon className="h-5 w-5" />
            </div>
            <h2 className="mt-4 font-display text-2xl text-slate-50">{card.title}</h2>
            <p className="mt-3 text-sm leading-relaxed text-slate-300">{card.description}</p>
          </Motion.article>
        ))}
      </section>
    </PageTransition>
  );
}
