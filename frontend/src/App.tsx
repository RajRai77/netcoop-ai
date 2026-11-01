import { lazy, Suspense, type ComponentType } from 'react';
import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom';
import { Shell } from './components/Shell';
import { Loading } from './components/ui';
import { CommandCenter } from './pages/CommandCenter';
import { CLERK_ENABLED } from './auth/session';
import { RequireAuth, SsoCallback } from './auth/clerk';

const Landing = lazy(() => import('./pages/Landing'));
const Incidents = lazy(() => import('./pages/Incidents'));
const TopologyPage = lazy(() => import('./pages/TopologyPage'));
const AgentsPage = lazy(() => import('./pages/AgentsPage'));
const EvidencePage = lazy(() => import('./pages/EvidencePage'));
const ReasoningPage = lazy(() => import('./pages/ReasoningPage'));
const ReportPage = lazy(() => import('./pages/ReportPage'));
const ScenariosPage = lazy(() => import('./pages/ScenariosPage'));
const EvaluationPage = lazy(() => import('./pages/EvaluationPage'));
const SettingsPage = lazy(() => import('./pages/SettingsPage'));

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route index element={<Suspense fallback={<Loading />}><Landing /></Suspense>} />
        {CLERK_ENABLED && <Route path="sso-callback" element={<SsoCallback />} />}
        <Route element={<RequireAuth><Shell /></RequireAuth>}>
          <Route path="command" element={<CommandCenter />} />
          {[
            ['incidents', Incidents], ['topology', TopologyPage], ['agents', AgentsPage], ['evidence', EvidencePage],
            ['reasoning', ReasoningPage], ['report', ReportPage], ['scenarios', ScenariosPage], ['evaluation', EvaluationPage],
            ['settings', SettingsPage],
          ].map(([path, C]) => {
            const Page = C as ComponentType;
            return <Route key={path as string} path={path as string} element={<Suspense fallback={<Loading />}><Page /></Suspense>} />;
          })}
          <Route path="*" element={<Navigate to="/command" replace />} />
        </Route>
      </Routes>
    </BrowserRouter>
  );
}
