import { Link } from 'react-router-dom';

export function Footer() {
  return (
    <footer className="mt-24 border-t border-white/10 bg-slate-950/60">
      <div className="mx-auto grid w-full max-w-7xl gap-10 px-6 py-14 md:grid-cols-3 md:px-10">
        <div>
          <p className="font-display text-xl tracking-tight text-slate-50">RailSense - AI prediction</p>
          <p className="mt-3 max-w-sm text-sm leading-relaxed text-slate-300">
            Predictive diagnostics platform for compressor systems, blending physics priors with temporal and statistical
            intelligence.
          </p>
        </div>

        <div>
          <p className="text-xs uppercase tracking-[0.26em] text-slate-400">Explore</p>
          <div className="mt-4 flex flex-col gap-2 text-sm">
            <Link className="text-slate-200 transition hover:text-cyan-200" to="/">
              Home
            </Link>
            <Link className="text-slate-200 transition hover:text-cyan-200" to="/services">
              Services
            </Link>
            <Link className="text-slate-200 transition hover:text-cyan-200" to="/prediction">
              Prediction Console
            </Link>
          </div>
        </div>

        <div>
          <p className="text-xs uppercase tracking-[0.26em] text-slate-400">Built For</p>
          <ul className="mt-4 space-y-2 text-sm text-slate-300">
            <li>Reliability Engineers</li>
            <li>Operations Teams</li>
            <li>Industrial AI Programs</li>
          </ul>
        </div>
      </div>
    </footer>
  );
}
