import { useEffect, useState } from 'react';
import { AnimatePresence, motion as Motion } from 'framer-motion';
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

const heroMessages = [
  {
    title: 'Predict failures before they stop operations.',
    description:
      'RailSense AI turns compressor inputs into a live failure probability, clear warning bands, and a fast operator-ready decision.',
  },
  {
    title: 'Compare old PTAD logic with the new live model.',
    description:
      'The homepage now shows exactly how the new model improves recall, F1, and live compatibility over the older prediction flow.',
  },
  {
    title: 'Ask RailSense AI for instant Gemini insight.',
    description:
      'After every prediction, users can get a short plain-English explanation of what the input pattern means and what to check next.',
  },
  {
    title: 'Switch from raw scores to explainable action.',
    description:
      'Guided controls, expert mode, and AI insight work together so operators and engineers can read risk faster and respond with confidence.',
  },
];

const highlights = [
  {
    icon: Sparkles,
    title: 'AI Insight with Gemini',
    copy: 'Get a compact explanation of the score, unusual signals, and next step without leaving the prediction flow.',
  },
  {
    icon: GaugeCircle,
    title: 'Live-compatible model',
    copy: 'The new model is trained for snapshot inputs, so the frontend and prediction backend now speak the same language.',
  },
  {
    icon: ChartNoAxesCombined,
    title: 'Better failure capture',
    copy: 'Higher recall and stronger F1 improve confidence that risky states are surfaced before they are ignored.',
  },
  {
    icon: ShieldCheck,
    title: 'Operator-ready output',
    copy: 'Every prediction returns a readable risk band, a verdict, and a short operational explanation.',
  },
];

const comparisonRows = [
  {
    label: 'Failure Recall',
    oldValue: 70.83,
    newValue: 98.86,
    oldNote: 'PTAD old model',
    newNote: 'New live model',
  },
  {
    label: 'Failure Precision',
    oldValue: 97.02,
    newValue: 98.31,
    oldNote: 'PTAD old model',
    newNote: 'New live model',
  },
  {
    label: 'Failure F1',
    oldValue: 81.88,
    newValue: 98.59,
    oldNote: 'PTAD old model',
    newNote: 'New live model',
  },
  {
    label: 'PR-AUC',
    oldValue: 92.0,
    newValue: 99.87,
    oldNote: 'Earlier hybrid benchmark',
    newNote: 'New live model',
  },
];

const capabilities = [
  {
    icon: Cpu,
    title: 'Old PTAD flow',
    points: [
      'Rule-heavy and engineering-oriented',
      'Useful for explainability experiments',
      'Not tightly aligned with the live snapshot UI',
    ],
  },
  {
    icon: Activity,
    title: 'New RailSense model',
    points: [
      'Built for frontend-driven live inputs',
      'Higher recall with strong precision balance',
      'Returns probability, warning band, and failure-likely verdict together',
    ],
  },
  {
    icon: Sparkles,
    title: 'Gemini AI insight',
    points: [
      'Explains what the entered values mean',
      'Summarizes the risk in plain language',
      'Helps users act faster without reading raw telemetry',
    ],
  },
];

const workflow = [
  {
    title: 'Capture',
    description: 'Users enter machine condition through guided sliders or expert controls.',
    icon: Radar,
  },
  {
    title: 'Score',
    description: 'The new live-compatible model converts inputs into calibrated failure probability and warning bands.',
    icon: Workflow,
  },
  {
    title: 'Explain',
    description: 'Gemini AI insight translates the score into a short operational explanation.',
    icon: ChartNoAxesCombined,
  },
  {
    title: 'Act',
    description: 'Teams get a clear next step instead of a black-box number with no context.',
    icon: Sparkles,
  },
];

const stats = [
  { value: '98.86%', label: 'Failure recall on the new live model' },
  { value: '98.31%', label: 'Failure precision on the new live model' },
  { value: 'Gemini', label: 'AI insight built into the prediction flow' },
  { value: 'Guided + Expert', label: 'Two input modes for operators and engineers' },
];

function useTypingText(text, speed = 34, hold = 1400) {
  const [displayed, setDisplayed] = useState('');

  useEffect(() => {
    let frame;
    let timeout;
    let index = 0;

    const step = () => {
      if (index <= text.length) {
        setDisplayed(text.slice(0, index));
        index += 1;
        frame = window.setTimeout(step, speed);
      } else {
        timeout = window.setTimeout(() => {
          setDisplayed('');
        }, hold);
      }
    };

    step();

    return () => {
      window.clearTimeout(frame);
      window.clearTimeout(timeout);
    };
  }, [text, speed, hold]);

  return displayed;
}

function MetricBar({ label, value, tone = 'cyan' }) {
  const width = `${Math.max(6, Math.min(100, value))}%`;
  const color =
    tone === 'amber'
      ? 'from-amber-300 to-orange-300'
      : 'from-cyan-300 to-emerald-200';

  return (
    <div>
      <div className="mb-2 flex items-center justify-between text-xs uppercase tracking-[0.2em] text-slate-400">
        <span>{label}</span>
        <span className="text-slate-200">{value.toFixed(2)}%</span>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/10">
        <div className={`h-full rounded-full bg-gradient-to-r ${color}`} style={{ width }} />
      </div>
    </div>
  );
}

export function HomePage() {
  const [activeIndex, setActiveIndex] = useState(0);
  const [showUpgradeModal, setShowUpgradeModal] = useState(false);
  const activeMessage = heroMessages[activeIndex];
  const typedTitle = useTypingText(activeMessage.title);

  useEffect(() => {
    const interval = window.setInterval(() => {
      setActiveIndex((current) => (current + 1) % heroMessages.length);
    }, 4800);
    return () => window.clearInterval(interval);
  }, []);

  useEffect(() => {
    const key = 'railsense-upgrade-modal-seen';
    const hasSeen = window.localStorage.getItem(key);
    if (!hasSeen) {
      setShowUpgradeModal(true);
      window.localStorage.setItem(key, 'true');
    }
  }, []);

  return (
    <PageTransition>
      <AnimatePresence>
        {showUpgradeModal ? (
          <>
            <Motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="fixed inset-0 z-[70] bg-slate-950/72 backdrop-blur-md"
            />
            <Motion.div
              initial={{ opacity: 0, scale: 0.88, y: 16 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.94, y: 10 }}
              transition={{ duration: 0.24, ease: 'easeOut' }}
              className="fixed inset-0 z-[80] flex items-start justify-center px-5 pt-[12vh]"
            >
              <div className="relative w-full max-w-2xl overflow-hidden rounded-[1.6rem] border border-cyan-200/20 bg-slate-950 shadow-2xl shadow-cyan-950/40">
                <div className="absolute -left-10 top-0 h-32 w-32 rounded-full bg-cyan-400/20 blur-3xl" />
                <div className="absolute -bottom-10 right-0 h-32 w-32 rounded-full bg-amber-300/15 blur-3xl" />
                <div className="relative p-6 md:p-7">
                  <div className="flex flex-wrap items-center gap-2">
                    <div className="inline-flex items-center gap-2 rounded-full border border-cyan-200/20 bg-cyan-300/10 px-4 py-2 text-[11px] uppercase tracking-[0.28em] text-cyan-100">
                      <Sparkles className="h-3.5 w-3.5" />
                      Update
                    </div>
                    <div className="inline-flex items-center gap-2 rounded-full border border-white/10 bg-white/[0.04] px-3 py-2 text-xs text-slate-100">
                      <span className="inline-flex h-5 w-5 items-center justify-center rounded-full bg-[conic-gradient(from_220deg,_#4f8cff,_#6ee7ff,_#7c3aed,_#4f8cff)] text-[10px] font-bold text-white">
                        G
                      </span>
                      Gemini AI Insight
                    </div>
                  </div>
                  <div className="mt-4 inline-flex items-center gap-2 rounded-full border border-cyan-200/20 bg-cyan-300/10 px-4 py-2 text-xs uppercase tracking-[0.28em] text-cyan-100">
                    <Sparkles className="h-3.5 w-3.5" />
                    What's New In RailSense AI
                  </div>
                  <h2 className="mt-4 max-w-xl font-display text-2xl leading-tight text-slate-50 md:text-4xl">
                    Old PTAD model replaced with a new live-ready system.
                  </h2>
                  <p className="mt-3 max-w-xl text-sm leading-relaxed text-slate-300 md:text-[15px]">
                    The new model is trained for live snapshot inputs, gives stronger precision and recall, and now pairs
                    with Gemini AI Insight to explain the score in simple language.
                  </p>

                  <div className="mt-5 grid gap-3 md:grid-cols-3">
                    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3.5">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Model upgrade</p>
                      <p className="mt-2 text-sm text-slate-200">
                        Built for the current prediction UI, not old rule-only flow.
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3.5">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Performance</p>
                      <p className="mt-2 text-sm text-slate-200">
                        Better recall, precision, F1, and more reliable live risk scoring.
                      </p>
                    </div>
                    <div className="rounded-2xl border border-white/10 bg-white/[0.04] p-3.5">
                      <p className="text-xs uppercase tracking-[0.2em] text-slate-400">Gemini AI help</p>
                      <p className="mt-2 text-sm text-slate-200">
                        Short explanation of what the entered values and score mean.
                      </p>
                    </div>
                  </div>

                  <div className="mt-6 flex flex-wrap gap-3">
                    <Link
                      to="/prediction"
                      onClick={() => setShowUpgradeModal(false)}
                      className="inline-flex items-center gap-2 rounded-full bg-gradient-to-r from-cyan-300 to-emerald-200 px-5 py-3 text-sm font-bold text-slate-950 transition hover:scale-[1.02]"
                    >
                      Try Prediction Now
                      <ArrowRight className="h-4 w-4" />
                    </Link>
                    <button
                      type="button"
                      onClick={() => setShowUpgradeModal(false)}
                      className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/5 px-5 py-3 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
                    >
                      I'll go myself
                    </button>
                  </div>
                </div>
              </div>
            </Motion.div>
          </>
        ) : null}
      </AnimatePresence>

      <CinematicSection className="mx-auto w-full max-w-7xl px-6 pt-14 md:px-10">
        <div className="relative overflow-hidden rounded-[2rem] border border-white/10 bg-white/[0.03] px-8 pb-10 pt-16 shadow-2xl shadow-cyan-950/30 md:px-14">
          <div className="absolute -left-16 -top-24 h-56 w-56 rounded-full bg-cyan-400/25 blur-3xl" />
          <div className="absolute -bottom-24 -right-20 h-56 w-56 rounded-full bg-amber-300/20 blur-3xl" />
          <Motion.div
            initial={{ opacity: 0, y: 14 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.5 }}
            className="relative inline-flex items-center gap-2 rounded-full border border-cyan-200/20 bg-cyan-300/10 px-4 py-2 text-xs uppercase tracking-[0.28em] text-cyan-100"
          >
            <Sparkles className="h-3.5 w-3.5" />
            AI Insight Powered By Gemini
          </Motion.div>
          <Motion.h1
            initial={{ opacity: 0, y: 20 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.65, delay: 0.05 }}
            className="relative mt-5 min-h-[7.5rem] max-w-5xl font-display text-4xl leading-[1.02] tracking-tight text-slate-50 md:min-h-[9rem] md:text-6xl"
          >
            {typedTitle}
            <span className="ml-1 inline-block h-[0.95em] w-[0.08em] translate-y-1 rounded-full bg-cyan-200/90 align-baseline animate-pulse" />
          </Motion.h1>
          <AnimatePresence mode="wait">
            <Motion.p
              key={activeMessage.description}
              initial={{ opacity: 0, y: 16 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -12 }}
              transition={{ duration: 0.35 }}
              className="relative mt-6 max-w-3xl text-base leading-relaxed text-slate-200/85 md:text-lg"
            >
              {activeMessage.description}
            </Motion.p>
          </AnimatePresence>
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
              to="/about"
              className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/5 px-5 py-3 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
            >
              Explore The Platform
            </Link>
          </Motion.div>
        </div>
      </CinematicSection>

      <CinematicSection
        className="mx-auto mt-14 w-full max-w-7xl px-6 md:px-10"
        glowClass="from-emerald-300/15 via-transparent to-cyan-300/10"
      >
        <div className="rounded-[2rem] border border-white/10 bg-white/[0.04] p-7 md:p-10">
          <div className="flex flex-col gap-4 md:flex-row md:items-end md:justify-between">
            <div>
              <p className="text-xs uppercase tracking-[0.28em] text-cyan-200">Model comparison</p>
              <h2 className="mt-3 font-display text-3xl text-slate-50 md:text-4xl">
                Old PTAD vs new live model, side by side.
              </h2>
              <p className="mt-4 max-w-3xl text-sm leading-relaxed text-slate-300 md:text-base">
                PTAD old stack was useful for engineering logic, but live frontend snapshots were not tightly aligned with it.
                The new model is trained for the live input format, so the prediction page is now stronger and more trustworthy.
              </p>
            </div>
            <div className="rounded-2xl border border-emerald-200/15 bg-emerald-300/10 px-4 py-3 text-sm text-emerald-100">
              New model F1 improved from <span className="font-bold text-white">81.88%</span> to <span className="font-bold text-white">98.59%</span>
            </div>
          </div>

          <div className="mt-8 grid gap-5 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="rounded-3xl border border-white/10 bg-slate-950/65 p-6">
              <div className="grid gap-6">
                {comparisonRows.map((row) => (
                  <div key={row.label} className="rounded-2xl border border-white/8 bg-white/[0.03] p-4">
                    <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
                      <h3 className="font-display text-xl text-slate-50">{row.label}</h3>
                      <span className="rounded-full border border-cyan-200/20 bg-cyan-300/10 px-3 py-1 text-xs uppercase tracking-[0.22em] text-cyan-100">
                        Improvement {(row.newValue - row.oldValue).toFixed(2)} pts
                      </span>
                    </div>
                    <div className="grid gap-4 md:grid-cols-2">
                      <MetricBar label={row.oldNote} value={row.oldValue} tone="amber" />
                      <MetricBar label={row.newNote} value={row.newValue} tone="cyan" />
                    </div>
                  </div>
                ))}
              </div>
            </div>

            <div className="grid gap-4">
              {capabilities.map((block, index) => (
                <Motion.article
                  key={block.title}
                  initial={{ opacity: 0, y: 20 }}
                  whileInView={{ opacity: 1, y: 0 }}
                  viewport={{ once: true, amount: 0.2 }}
                  transition={{ duration: 0.45, delay: index * 0.08 }}
                  className="rounded-3xl border border-white/10 bg-slate-900/65 p-6"
                >
                  <div className="inline-flex rounded-2xl border border-cyan-200/20 bg-cyan-300/10 p-3 text-cyan-100">
                    <block.icon className="h-5 w-5" />
                  </div>
                  <h3 className="mt-4 font-display text-2xl text-slate-50">{block.title}</h3>
                  <div className="mt-4 space-y-3 text-sm leading-relaxed text-slate-300">
                    {block.points.map((item) => (
                      <div key={item} className="flex items-start gap-3">
                        <span className="mt-2 h-1.5 w-1.5 rounded-full bg-cyan-200" />
                        <span>{item}</span>
                      </div>
                    ))}
                  </div>
                </Motion.article>
              ))}
            </div>
          </div>
        </div>
      </CinematicSection>

      <CinematicSection className="mx-auto mt-16 w-full max-w-7xl px-6 md:px-10">
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

      <CinematicSection className="mx-auto mt-16 w-full max-w-7xl px-6 md:px-10">
        <div className="rounded-[2rem] border border-white/10 bg-white/[0.04] p-7 md:p-10">
          <p className="text-xs uppercase tracking-[0.28em] text-amber-200">How it works now</p>
          <h2 className="mt-3 font-display text-3xl text-slate-50 md:text-4xl">
            Prediction is no longer just a score. It is a score plus an explanation.
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
          <h2 className="max-w-3xl font-display text-3xl text-slate-50 md:text-5xl">
            Open the prediction page to see the new model and Gemini insight working together.
          </h2>
          <p className="mt-4 max-w-2xl text-sm text-slate-200 md:text-base">
            The homepage now explains the model upgrade early, and the prediction page turns that upgrade into a live experience with guided input, expert mode, risk scoring, and short AI help.
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
              to="/services"
              className="inline-flex items-center gap-2 rounded-full border border-white/20 bg-white/5 px-5 py-3 text-sm font-semibold text-slate-100 transition hover:bg-white/10"
            >
              Explore Services
            </Link>
          </div>
        </div>
      </CinematicSection>
    </PageTransition>
  );
}
