import { motion as Motion } from 'framer-motion';
import { Beaker, Waves, AlarmClock, ShieldAlert } from 'lucide-react';
import { PageTransition } from '../components/PageTransition';

const experiments = [
  {
    icon: Waves,
    title: 'Signal Drift Lens',
    description: 'Track feature drift against baseline medians to catch gradual degradation.',
    status: 'Planned',
  },
  {
    icon: AlarmClock,
    title: 'Lead-Time Optimizer',
    description: 'Tune threshold strategy around desired early-warning windows by context.',
    status: 'In progress',
  },
  {
    icon: ShieldAlert,
    title: 'False Alert Firewall',
    description: 'Rule-aware post-processing to suppress noisy bursts while preserving event recall.',
    status: 'Prototype',
  },
];

export function LabsPage() {
  return (
    <PageTransition>
      <section className="mx-auto w-full max-w-7xl px-6 pt-14 md:px-10">
        <p className="text-xs uppercase tracking-[0.3em] text-cyan-200">Labs</p>
        <h1 className="mt-4 max-w-3xl font-display text-4xl tracking-tight text-slate-50 md:text-5xl">
          Product experiments for next-generation reliability operations.
        </h1>
        <p className="mt-5 max-w-3xl text-slate-300">
          This page tracks advanced features we can activate next to keep the platform ahead in UX and operational value.
        </p>
      </section>

      <section className="mx-auto mt-12 grid w-full max-w-7xl gap-5 px-6 md:px-10">
        {experiments.map((experiment, index) => (
          <Motion.article
            key={experiment.title}
            initial={{ opacity: 0, y: 18 }}
            whileInView={{ opacity: 1, y: 0 }}
            viewport={{ once: true, amount: 0.2 }}
            transition={{ duration: 0.45, delay: index * 0.08 }}
            className="rounded-3xl border border-white/10 bg-white/[0.04] p-6 md:p-7"
          >
            <div className="flex flex-wrap items-center justify-between gap-4">
              <div className="inline-flex items-center gap-3">
                <div className="rounded-2xl border border-cyan-200/20 bg-cyan-300/10 p-3 text-cyan-100">
                  <experiment.icon className="h-5 w-5" />
                </div>
                <h2 className="font-display text-2xl text-slate-50">{experiment.title}</h2>
              </div>
              <span className="rounded-full border border-amber-200/25 bg-amber-300/10 px-3 py-1 text-xs font-semibold uppercase tracking-[0.2em] text-amber-100">
                {experiment.status}
              </span>
            </div>
            <p className="mt-4 text-sm leading-relaxed text-slate-300">{experiment.description}</p>
          </Motion.article>
        ))}
      </section>

      <section className="mx-auto mt-10 w-full max-w-7xl px-6 pb-6 md:px-10">
        <div className="rounded-3xl border border-white/10 bg-gradient-to-r from-cyan-400/15 via-transparent to-amber-300/10 p-8">
          <div className="flex items-start gap-4">
            <div className="rounded-2xl border border-white/20 bg-white/10 p-3 text-cyan-100">
              <Beaker className="h-5 w-5" />
            </div>
            <div>
              <h3 className="font-display text-2xl text-slate-50">Milestone UX roadmap</h3>
              <p className="mt-2 max-w-2xl text-sm leading-relaxed text-slate-300">
                Next iterations can include timeline playback, maintenance simulation, role-based dashboards, and alert
                storytelling views to make this feel like a true command system.
              </p>
            </div>
          </div>
        </div>
      </section>
    </PageTransition>
  );
}
