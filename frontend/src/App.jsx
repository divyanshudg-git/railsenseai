import { lazy, Suspense } from 'react';
import { AnimatePresence } from 'framer-motion';
import { Route, Routes, useLocation } from 'react-router-dom';
import { Footer } from './components/Footer';
import { NavBar } from './components/NavBar';
import { ScrollProgress } from './components/ScrollProgress';
import { SmoothScroll } from './components/SmoothScroll';
import { NotFoundPage } from './pages/NotFoundPage';

const HomePage = lazy(() => import('./pages/HomePage').then((module) => ({ default: module.HomePage })));
const ServicesPage = lazy(() => import('./pages/ServicesPage').then((module) => ({ default: module.ServicesPage })));
const PredictionPage = lazy(() => import('./pages/PredictionPage').then((module) => ({ default: module.PredictionPage })));
const LabsPage = lazy(() => import('./pages/LabsPage').then((module) => ({ default: module.LabsPage })));
const AboutPage = lazy(() => import('./pages/AboutPage').then((module) => ({ default: module.AboutPage })));

function AppRoutes() {
  const location = useLocation();

  return (
    <AnimatePresence mode="wait">
      <Suspense
        fallback={
          <div className="mx-auto flex min-h-[70vh] w-full max-w-7xl items-center justify-center px-6 md:px-10">
            <div className="rounded-full border border-cyan-200/25 bg-cyan-300/10 px-5 py-2 text-sm text-cyan-100">
              Loading experience...
            </div>
          </div>
        }
      >
        <Routes location={location} key={location.pathname}>
          <Route path="/" element={<HomePage />} />
          <Route path="/services" element={<ServicesPage />} />
          <Route path="/prediction" element={<PredictionPage />} />
          <Route path="/labs" element={<LabsPage />} />
          <Route path="/about" element={<AboutPage />} />
          <Route path="*" element={<NotFoundPage />} />
        </Routes>
      </Suspense>
    </AnimatePresence>
  );
}

export default function App() {
  return (
    <div className="relative min-h-screen overflow-x-hidden bg-slate-950 text-slate-100">
      <SmoothScroll />
      <ScrollProgress />
      <div className="pointer-events-none fixed inset-0 bg-[radial-gradient(circle_at_15%_15%,rgba(56,189,248,0.20),transparent_26%),radial-gradient(circle_at_80%_20%,rgba(251,191,36,0.12),transparent_24%),radial-gradient(circle_at_70%_80%,rgba(16,185,129,0.12),transparent_24%)]" />
      <NavBar />
      <main className="relative z-10">
        <AppRoutes />
      </main>
      <Footer />
    </div>
  );
}
