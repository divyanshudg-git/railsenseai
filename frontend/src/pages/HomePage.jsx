import { motion as Motion } from 'framer-motion';
import {
  Activity,
  ArrowRight,
  ChartNoAxesCombined,
  Cpu,
  GaugeCircle,
  Radar,
  ShieldCheck,
  Sparkles,
  Workflow,
} from 'lucide-react';
import { Link } from 'react-router-dom';
import { CinematicSection } from '../components/CinematicSection';
import { PageTransition } from '../components/PageTransition';

const highlights = [
  {
    icon: GaugeCircle,
    title: 'Realtime risk signal',
    copy: 'Live scoring pipeline with confidence bands and explainable component mix.',
  },
  {
    icon: Activity,
    title: 'Physics-first modeling',
    copy: 'Rule-constrained anomaly scoring that respects operational behavior and sensor context.',
  },
  {
    icon: Cpu,
    title: 'Hybrid intelligence',
    copy: 'Temporal, statistical, and physical layers fused into a single operational verdict.',
  },
  {
    icon: ShieldCheck,
    title: 'Operational readiness',
    copy: 'Action-oriented recommendations designed for control-room workflows.',
  },
];

const workflow = [
  {
    title: 'Observe',
    description: 'Operators answer plain-language health prompts, not raw telemetry equations.',
    icon: Radar,
  },
  {
    title: 'Translate',
    description: 'The platform maps observations into model-ready features with safety-aware constraints.',
    icon: Workflow,
  },
  {
    title: 'Predict',
    description: 'Hybrid AI fuses physics, temporal, and statistical cues for a calibrated risk outcome.',
    icon: ChartNoAxesCombined,
  },
  {
    title: 'Act',
    description: 'The UI returns one clear risk level and an immediate action recommendation.',
    icon: Sparkles,
  },
];

const stats = [
  { value: '112m', label: 'Median early warning lead time' },
  { value: '4-Layer', label: 'Hybrid model architecture' },
  { value: '1-click', label: 'Operator-friendly health checks' },
  { value: 'Batch + Live', label: 'Single and multi-row prediction paths' },
];

export function HomePage() {
  return (
    <PageTransition>
      <CinematicSection className="mx-auto w-full max-w-7xl px-6 pt-14 md:px-10">
        <div className="relative overflow-hidden rounded-[2rem] border border-white/10 bg-white/[0.03] px-8 pb-10 pt-16 shadow-2xl shadow-cyan-950/30 md:px-14">
          <div className="absolute -left-16 -top-24 h-56 w-56 rounded-full bg-cyan-400/25 blur-3xl" />
          <div className="absolute -bottom-24 -right-20 h-56 w-56 rounded-full bg-amber-300/20 blur-3xl" />
          <Motion.p
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="relative text-xs uppercase tracking-[0.3em] text-cyan-200/90"
          >
            Industrial Intelligence Platform
          </Motion.p>
          <Motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.65, delay: 0.05 }}
            className="relative mt-5 max-w-4xl font-display text-4xl leading-[1.02] tracking-tight text-slate-50 md:text-6xl"
          >
            Predict compressor failures before they become operational events.
          </Motion.h1>
          <Motion.p
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.65, delay: 0.12 }}
            className="relative mt-6 max-w-2xl text-base leading-relaxed text-slate-200/85 md:text-lg"
          >
            RailSense - AI prediction transforms raw telemetry into decision-grade diagnostics with elegant UX and
            explainable confidence. Designed for engineering teams who need precision, not dashboard noise.
          </Motion.p>
          <Motion.div
            initial={{ opacity: 0, y: 18 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.55, delay: 0.2 }}
            className="relative mt-9 flex flex-wrap gap-3"
          >
            <Link
              to="/prediction"
              className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-cyan-300 to-emerald-200 px-5 py-3 text-sm font-bold text-slate-950 transition hover:scale-[1.02]"
            >
              Try Live Prediction
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              to="/services"
              className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/5 px-5 py-3 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
            >
              Explore Services
            </Link>
          </Motion.div>
        </div>
      </CinematicSection>

      <CinematicSection className="mx-auto mt-14 w-full max-w-7xl px-6 md:px-10">
        <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-4">
          {highlights.map((item, index) => (
            <Motion.article
              key={item.title}
              initial={{ opacity: 0, y: 28 }}
              whileInView={{ opacity: 1, y: 0 }}
              viewport={{ once: true, amount: 0.2 }}
              transition={{ duration: 0.45, delay: index * 0.08 }}
              className="group rounded-3xl border border-white/10 bg-white/[0.04] p-6"
            >
              <div className="inline-flex rounded-2xl border border-cyan-200/20 bg-cyan-300/10 p-3 text-cyan-100">
                <item.icon className="h-5 w-5" />
              </div>
              <h3 className="mt-4 font-display text-xl text-slate-50">{item.title}</h3>
              <p className="mt-3 text-sm leading-relaxed text-slate-300">{item.copy}</p>
            </Motion.article>
          ))}
        </div>
      </CinematicSection>

      <CinematicSection
        className="mx-auto mt-16 w-full max-w-7xl px-6 md:px-10"
        glowClass="from-emerald-300/15 via-transparent to-cyan-300/10"
      >
        <div className="rounded-[2rem] border border-white/10 bg-white/[0.04] p-7 md:p-10">
          <div className="grid gap-8 lg:grid-cols-[1fr_1.3fr]">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-cyan-200">Why teams switch</p>
              <h2 className="mt-3 font-display text-3xl text-slate-50 md:text-4xl">
                From noisy dashboards to decision-grade reliability.
              </h2>
              <p className="mt-4 text-sm leading-relaxed text-slate-300 md:text-base">
                Most predictive tools either overwhelm operators with technical fields or hide important context behind
                black-box scores. RailSense is designed to bridge this gap with cinematic product UX and practical
                reliability logic.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              {[
                {
                  title: 'Before',
                  items: ['Hard-to-read control panels', 'False alerts with no clear action', 'Slow handoffs between operations and engineering'],
                },
                {
                  title: 'After',
                  items: ['Guided plain-language checks', 'Action-first recommendations', 'Shared timeline history for shift review'],
                },
              ].map((block) => (
                <article key={block.title} className="rounded-2xl border border-white/10 bg-slate-900/65 p-5">
                  <h3 className="font-display text-2xl text-slate-50">{block.title}</h3>
                  <ul className="mt-3 space-y-2 text-sm text-slate-300">
                    {block.items.map((item) => (
                      <li key={item} className="flex items-start gap-2">
                        <span className="mt-2 h-1.5 w-1.5 rounded-full bg-cyan-200" />
                        <span>{item}</span>
                      </li>
                    ))}
                  </ul>
                </article>
              ))}
            </div>
          </div>
        </div>
      </CinematicSection>

      <CinematicSection className="mx-auto mt-16 w-full max-w-7xl px-6 md:px-10">
        <div className="rounded-[2rem] border border-white/10 bg-white/[0.04] p-7 md:p-10">
          <p className="text-xs uppercase tracking-[0.28em] text-amber-200">How it works</p>
          <h2 className="mt-3 font-display text-3xl text-slate-50 md:text-4xl">
            Four-step reliability loop with built-in explainability.
          </h2>
          <div className="mt-8 grid gap-4 md:grid-cols-2">
            {workflow.map((step, index) => (
              <Motion.article
                key={step.title}
                whileHover={{ y: -4 }}
                className="rounded-2xl border border-white/10 bg-slate-900/65 p-5"
              >
                <div className="inline-flex rounded-xl border border-cyan-100/20 bg-cyan-200/10 p-2 text-cyan-100">
                  <step.icon className="h-5 w-5" />
                </div>
                <p className="mt-3 text-xs uppercase tracking-[0.24em] text-slate-400">Step {index + 1}</p>
                <h3 className="mt-1 font-display text-2xl text-slate-50">{step.title}</h3>
                <p className="mt-2 text-sm text-slate-300">{step.description}</p>
              </Motion.article>
            ))}
          </div>
        </div>
      </CinematicSection>

      <CinematicSection
        className="mx-auto mt-16 w-full max-w-7xl px-6 md:px-10"
        glowClass="from-cyan-300/12 via-transparent to-emerald-300/14"
      >
        <div className="grid gap-5 md:grid-cols-2 lg:grid-cols-4">
          {stats.map((stat) => (
            <article key={stat.label} className="rounded-2xl border border-white/10 bg-white/[0.04] p-6">
              <p className="font-display text-4xl text-slate-50">{stat.value}</p>
              <p className="mt-2 text-sm text-slate-300">{stat.label}</p>
            </article>
          ))}
        </div>
      </CinematicSection>

      <CinematicSection className="mx-auto mt-16 w-full max-w-7xl px-6 pb-10 md:px-10">
        <div className="rounded-[2rem] border border-cyan-200/20 bg-gradient-to-r from-cyan-300/15 via-transparent to-amber-300/15 p-8 md:p-12">
          <h2 className="max-w-2xl font-display text-3xl text-slate-50 md:text-5xl">
            Ready to move from reactive maintenance to predictive operations?
          </h2>
          <p className="mt-4 max-w-xl text-sm text-slate-200 md:text-base">
            Open the prediction console and run a guided health check in under one minute. The platform will provide an
            immediate risk verdict and action guidance your team can use right away.
          </p>
          <div className="mt-7 flex flex-wrap gap-3">
            <Link
              to="/prediction"
              className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-cyan-200 to-emerald-100 px-5 py-3 text-sm font-bold text-slate-950 transition hover:scale-[1.02]"
            >
              Start Prediction
              <ArrowRight className="h-4 w-4" />
            </Link>
            <Link
              to="/about"
              className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/5 px-5 py-3 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
            >
              Meet The Builder
            </Link>
          </div>
        </div>
      </CinematicSection>
    </PageTransition>
  );
}
