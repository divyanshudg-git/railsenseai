import { Link } from 'react-router-dom';
import { PageTransition } from '../components/PageTransition';

export function NotFoundPage() {
  return (
    <PageTransition>
      <section className="mx-auto flex min-h-[55vh] w-full max-w-3xl flex-col items-center justify-center px-6 text-center">
        <p className="text-xs uppercase tracking-[0.28em] text-cyan-200">404</p>
        <h1 className="mt-3 font-display text-5xl text-slate-50">Page not found</h1>
        <p className="mt-4 text-slate-300">The route does not exist in this build. Jump back to the landing page.</p>
        <Link
          to="/"
          className="mt-8 rounded-full border border-cyan-200/30 bg-cyan-300/15 px-5 py-2 text-sm font-semibold text-cyan-100 transition hover:bg-cyan-300/25"
        >
          Back to home
        </Link>
      </section>
    </PageTransition>
  );
}
