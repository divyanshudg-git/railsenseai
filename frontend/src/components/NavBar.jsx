import { NavLink } from 'react-router-dom';
import { motion as Motion } from 'framer-motion';
import { Radar } from 'lucide-react';

const links = [
  { to: '/', label: 'Home' },
  { to: '/services', label: 'Services' },
  { to: '/prediction', label: 'Prediction' },
  { to: '/labs', label: 'Labs' },
  { to: '/about', label: 'About' },
];

export function NavBar() {
  return (
    <header className="sticky top-0 z-50 border-b border-white/10 bg-slate-950/75 backdrop-blur-xl">
      <nav className="mx-auto flex w-full max-w-7xl items-center justify-between px-6 py-4 md:px-10">
        <NavLink to="/" className="group flex items-center gap-3">
          <div className="grid h-11 w-11 place-items-center rounded-2xl border border-cyan-200/25 bg-cyan-300/10">
            <Radar className="h-5 w-5 text-cyan-200" />
          </div>
          <div>
            <p className="font-display text-lg leading-none tracking-tight text-slate-100">RailSense - AI prediction</p>
            <p className="text-xs uppercase tracking-[0.24em] text-slate-400">Reliability Studio</p>
          </div>
        </NavLink>

        <div className="hidden items-center gap-1 rounded-full border border-white/10 bg-white/5 p-1 md:flex">
          {links.map((link) => (
            <NavLink
              key={link.to}
              to={link.to}
              className={({ isActive }) =>
                `relative rounded-full px-4 py-2 text-sm font-medium transition ${
                  isActive ? 'text-slate-50' : 'text-slate-300 hover:text-slate-50'
                }`
              }
            >
              {({ isActive }) => (
                <>
                  {isActive ? (
                    <Motion.span
                      layoutId="active-nav-pill"
                      className="absolute inset-0 rounded-full bg-gradient-to-r from-cyan-400/25 to-amber-300/25"
                      transition={{ type: 'spring', stiffness: 380, damping: 30 }}
                    />
                  ) : null}
                  <span className="relative z-10">{link.label}</span>
                </>
              )}
            </NavLink>
          ))}
        </div>
      </nav>
    </header>
  );
}
