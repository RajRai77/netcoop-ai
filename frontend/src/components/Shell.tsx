import { useEffect, useMemo, useRef, useState } from 'react';
import { Link, NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom';
import {
  Activity, BarChart3, BrainCircuit, Database, FileText, LayoutDashboard, ListTree, Menu, Network, Play,
  Search, Settings, Upload, Users, Wifi, WifiOff,
} from 'lucide-react';
import { useAgents, useCreateFromScenario, useDiagnose, useHealth, useIncident, useIncidents, useMeta, useScenarios } from '@/api/hooks';
import { errorText } from '@/api/client';
import { useApp } from '@/state/settings';
import { agentLabel, STATE_LABEL, STATUS_LABEL } from '@/lib/format';
import { Chip, Logo } from './ui';
import { TERMINAL_STATES } from '@/api/types';
import { CLERK_ENABLED } from '@/auth/session';
import { UserMenu } from '@/auth/clerk';

const NAV = [
  { to: '/command', label: 'Command Center', icon: LayoutDashboard, end: true },
  { to: '/incidents', label: 'Investigations', icon: ListTree },
  { to: '/topology', label: 'Topology', icon: Network },
  { to: '/agents', label: 'Agent Collaboration', icon: Users },
  { to: '/reasoning', label: 'STEaR Reasoning', icon: BrainCircuit },
  { to: '/evidence', label: 'Evidence Explorer', icon: Database },
  { to: '/report', label: 'Reports', icon: FileText },
  { to: '/scenarios', label: 'Datasets & Upload', icon: Upload },
  { to: '/evaluation', label: 'Evaluation', icon: BarChart3 },
  { to: '/settings', label: 'Settings', icon: Settings },
];

// Curated launcher entries; only shown if the backend actually offers the scenario.
const LAUNCHER = [
  ['ORG-03-hardware-failure', 'Organizer · hardware failure'],
  ['ORG-02-latency-spike', 'Organizer · latency spike'],
  ['ORG-01-normal', 'Organizer · normal operation'],
  ['ORG-04-schema-drift', 'Organizer · schema drift (bad records)'],
  ['S19-ap-down-status-in-archive', 'Verification showcase · AP down'],
  ['S11-ambiguous-resolvable', 'Ambiguous · resolvable by verification'],
  ['S16-ambiguous-unresolvable', 'Ambiguous · cannot be resolved'],
  ['S09-upstream-outage', 'Upstream outage'],
  ['S01-congestion', 'Link congestion'],
  ['S05-weak-wifi', 'Weak Wi-Fi'],
  ['S02-interface-degradation', 'Interface fault'],
  ['S07-dns-failure', 'DNS failure'],
  ['S10-compound', 'Two simultaneous faults'],
  ['S13-csv-vendor-profile', 'Interop: vendor CSV'],
  ['S00-healthy', 'Normal operation'],
] as const;

function Sidebar({ open, onNavigate }: { open: boolean; onNavigate: () => void }) {
  const { selectedScenarioId, set, preview } = useApp();
  const scenarios = useScenarios();
  const agents = useAgents();
  const health = useHealth();
  const meta = useMeta();
  const create = useCreateFromScenario();
  const diagnose = useDiagnose();
  const nav = useNavigate();
  const [err, setErr] = useState<string | null>(null);
  const available = new Set((scenarios.data?.scenarios ?? []).map((s) => s.scenario_id));
  const entries = LAUNCHER.filter(([id]) => available.has(id));
  const busy = create.isPending || diagnose.isPending;
  const run = async () => {
    if (!selectedScenarioId) return;
    setErr(null);
    try {
      const r = await create.mutateAsync(selectedScenarioId);
      await diagnose.mutateAsync({ id: r.incident.incident_id, verification: true });
      set({ activeIncidentId: r.incident.incident_id });
      onNavigate();
      nav('/command');
    } catch (e) {
      setErr(errorText(e));
    }
  };
  const ag = agents.data?.agents ?? [];
  const apiOk = health.isSuccess;
  return (
    <aside className={`sidebar ${open ? 'open' : ''}`} aria-label="Primary">
      <Link to="/" className="brand" onClick={onNavigate} title="NetCoop AI overview">
        <Logo size={42} />
        <div>
          <div className="brand-name">NetCoop <b>AI</b></div>
          <div className="brand-tag">Evidence-seeking network diagnosis</div>
        </div>
      </Link>
      <nav className="nav">
        {NAV.map(({ to, label, icon: I, end }) => (
          <NavLink key={to} to={to} end={end} onClick={onNavigate} className={({ isActive }) => (isActive ? 'active' : '')}>
            <I className="ico" />{label}
          </NavLink>
        ))}
      </nav>
      <div className="side-section">
        <div className="side-label">New investigation</div>
        <div className="side-card" style={{ display: 'grid', gap: 8 }}>
          <select className="select" value={selectedScenarioId ?? ''} onChange={(e) => set({ selectedScenarioId: e.target.value })}
                  aria-label="Scenario to run" disabled={!entries.length}>
            {!entries.length && <option value="">{scenarios.isError ? 'Scenarios unavailable' : 'Loading scenarios…'}</option>}
            {entries.map(([id, label]) => <option key={id} value={id}>{label}</option>)}
          </select>
          <button className="btn primary" disabled={busy || preview || !selectedScenarioId} title={preview ? 'Preview mode is read-only' : undefined} onClick={run}>
            <Play size={16} />{busy ? 'Starting…' : 'Run diagnosis'}
          </button>
          <NavLink to="/scenarios#upload" onClick={onNavigate} className="btn sm"><Upload size={14} />Upload telemetry</NavLink>
          {err && <div className="err" style={{ fontSize: 12.5 }}>{err}</div>}
        </div>
      </div>
      <div className="side-foot">
        <div className="side-label">System status</div>
        <div className="side-card" style={{ display: 'grid', gap: 2 }}>
          <div className="sys-row">
            <span className="sys-dot" style={{ background: preview ? '#f59e0b' : apiOk ? '#4caf50' : '#e5484d' }} />Coordinator API
            <span className={`tag ${apiOk || preview ? 'on' : 'off'}`}>{preview ? 'Recorded' : apiOk ? 'Online' : 'Offline'}</span>
          </div>
          {ag.map((a) => (
            <div key={a.agent_id} className="sys-row" title={`${a.name ?? a.agent_id}${a.url ? ' · ' + a.url : ''}`}>
              <span className="sys-dot" style={{ background: a.status === 'available' ? '#4caf50' : '#e5484d' }} />
              {agentLabel(a.agent_id).replace(' & Services', '')} Agent
              <span className={`tag ${a.status === 'available' ? 'on' : 'off'}`}>{a.status === 'available' ? 'Online' : 'Offline'}</span>
            </div>
          ))}
          {agents.isError && <div className="sys-row">Agent status unavailable</div>}
          {meta.data && <div className="sys-row" style={{ marginTop: 4, color: '#8ea3c9', fontSize: 12 }}>v{meta.data.version} · {meta.data.agent_transport.toUpperCase()} · {meta.data.fault_library}</div>}
        </div>
      </div>
    </aside>
  );
}

function IncidentPicker() {
  const { activeIncidentId, set } = useApp();
  const incidents = useIncidents();
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const h = (e: MouseEvent) => ref.current && !ref.current.contains(e.target as Node) && setOpen(false);
    document.addEventListener('mousedown', h);
    return () => document.removeEventListener('mousedown', h);
  }, []);
  const list = useMemo(() => {
    const s = q.trim().toLowerCase();
    return (incidents.data?.incidents ?? []).filter((i) => !s || `${i.incident_id} ${i.title ?? ''} ${i.scenario_id ?? ''} ${i.latest_report?.suspected_root_cause ?? ''}`.toLowerCase().includes(s));
  }, [incidents.data, q]);
  return (
    <div ref={ref} style={{ position: 'relative', flex: 1, maxWidth: 560 }}>
      <div style={{ position: 'relative' }}>
        <Search size={17} style={{ position: 'absolute', left: 12, top: 11, color: 'var(--text-faint)' }} />
        <input className="input" style={{ paddingLeft: 38 }} placeholder="Search investigations, scenarios, root causes…" value={q}
               onChange={(e) => { setQ(e.target.value); setOpen(true); }} onFocus={() => setOpen(true)} aria-label="Search incidents" />
      </div>
      {open && (
        <div className="glass strong" style={{ position: 'absolute', top: 46, left: 0, right: 0, zIndex: 30, maxHeight: 380, overflow: 'auto', padding: 6, borderRadius: 14 }}>
          {incidents.isError && <div className="state">{errorText(incidents.error)}</div>}
          {!incidents.isError && list.length === 0 && <div className="state">No incidents{q ? ' match' : ' yet'}.</div>}
          {list.map((i) => (
            <button key={i.incident_id} className="scenario-btn" style={{ marginBottom: 4, background: i.incident_id === activeIncidentId ? 'rgba(34,211,238,.12)' : undefined }}
                    onClick={() => { set({ activeIncidentId: i.incident_id }); setOpen(false); setQ(''); }}>
              <div style={{ minWidth: 0, flex: 1 }}>
                <div style={{ fontWeight: 600, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{i.title ?? i.incident_id}</div>
                <div className="faint mono">{i.incident_id}{i.latest_report?.suspected_root_cause ? ` · ${i.latest_report.suspected_root_cause}` : ''}</div>
              </div>
              {i.latest_report ? <Chip tone="muted">{STATUS_LABEL[i.latest_report.status]}</Chip> : <Chip tone="blue">{i.workflow?.state ?? 'NEW'}</Chip>}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

function Header() {
  const { preview, activeIncidentId } = useApp();
  const health = useHealth();
  const inc = useIncident(activeIncidentId);
  const st = inc.data?.workflow?.state ?? null;
  const running = !!inc.data?.running || (!!st && !TERMINAL_STATES.includes(st) && st !== 'INTERRUPTED');
  const connected = health.isSuccess && !preview;
  return (
    <header className="glass header">
      <IncidentPicker />
      <div className="grow" />
      {activeIncidentId && inc.data && (
        <div style={{ display: 'flex', alignItems: 'center', gap: 8 }} title="Active incident and workflow state">
          <span className="mono muted">{activeIncidentId}</span>
          {running ? <Chip tone="blue" pip><Activity size={13} />{STATE_LABEL[st!] ?? st}</Chip> : st && <Chip tone="muted">{STATE_LABEL[st] ?? st}</Chip>}
        </div>
      )}
      {preview ? (
        <Chip tone="amber" title="Recorded responses of a real backend run — not live">PREVIEW · recorded run</Chip>
      ) : connected ? (
        <Chip tone="green" pip title={`Backend ${health.data?.version}`}><Wifi size={13} />CONNECTED API</Chip>
      ) : (
        <Chip tone="red" title={health.error ? errorText(health.error) : 'checking'}><WifiOff size={13} />{health.isLoading ? 'Connecting…' : 'Backend offline'}</Chip>
      )}
      {CLERK_ENABLED && !preview && <UserMenu />}
    </header>
  );
}

function ModeBanner() {
  const { preview, set } = useApp();
  const health = useHealth();
  const meta = useMeta();
  const nav = useNavigate();
  if (!preview && !CLERK_ENABLED && meta.data?.auth_mode === 'clerk') {
    return (
      <div className="glass mode-banner offline">
        <strong>Sign-in is not configured in this build.</strong>
        <span className="muted">The backend requires Google sign-in (Clerk), but the frontend was built without VITE_CLERK_PUBLISHABLE_KEY. Rebuild with the publishable key.</span>
      </div>
    );
  }
  if (preview) {
    return (
      <div className="glass mode-banner preview">
        <strong>Preview mode.</strong>
        <span className="muted">You are viewing recorded responses of a real backend run (scenario S19, backend ccab69d). Nothing here is live; actions are disabled.</span>
        <button className="btn sm" style={{ marginLeft: 'auto' }} onClick={() => set({ preview: false })}>Use live backend</button>
      </div>
    );
  }
  if (health.isError) {
    return (
      <div className="glass mode-banner offline">
        <strong>Backend not reachable.</strong>
        <span className="muted">{errorText(health.error)} Start it with <span className="mono">uv run python scripts/run_local.py</span>.</span>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
          <button className="btn sm" onClick={() => nav('/settings')}>Settings</button>
          <button className="btn sm" onClick={() => set({ preview: true })}>Open labeled preview</button>
        </div>
      </div>
    );
  }
  return null;
}

export function Shell() {
  const [menu, setMenu] = useState(false);
  const loc = useLocation();
  const reduced = useApp((s) => s.reducedMotion);
  useEffect(() => setMenu(false), [loc.pathname]);
  return (
    <div className={`shell ${reduced ? 'reduced-motion' : ''}`}>
      <div className="backdrop" aria-hidden />
      <Sidebar open={menu} onNavigate={() => setMenu(false)} />
      <main className="main">
        <div className="glass mobile-bar">
          <button className="btn ghost sm" onClick={() => setMenu((m) => !m)} aria-label="Menu"><Menu size={20} /></button>
          <Logo size={30} /><strong>NetCoop AI</strong>
        </div>
        <Header />
        <ModeBanner />
        <Outlet />
      </main>
    </div>
  );
}
