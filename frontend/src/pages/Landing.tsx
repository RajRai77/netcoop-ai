import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import {
  ArrowRight, BadgeCheck, BrainCircuit, Database, FileCheck2, FlaskConical, Gauge, GitCompareArrows, Layers, Network, Play,
  SearchCheck, Server, ShieldCheck, Sparkles, Users, Zap,
} from 'lucide-react';
import { errorText } from '@/api/client';
import { useAgents, useCreateFromScenario, useDiagnose, useEvaluations, useHealth, useMeta } from '@/api/hooks';
import type { Rate } from '@/api/types';
import { useApp } from '@/state/settings';
import { agentLabel } from '@/lib/format';
import { Logo } from '@/components/ui';
import { CLERK_ENABLED } from '@/auth/session';
import { GoogleButton, LandingAuth, UserMenu } from '@/auth/clerk';

const DEMO = 'ORG-03-hardware-failure';
const SHOWCASE = 'S19-ap-down-status-in-archive';

export default function Landing() {
  const nav = useNavigate();
  const { set, preview } = useApp();
  const health = useHealth();
  const agents = useAgents();
  const meta = useMeta();
  const create = useCreateFromScenario();
  const diagnose = useDiagnose();
  const [err, setErr] = useState<string | null>(null);
  const live = health.isSuccess && !preview;
  const busy = create.isPending || diagnose.isPending;

  const demo = async (sid: string = DEMO) => {
    setErr(null);
    if (!live) {
      set({ preview: true, activeIncidentId: 'INC-b2e30992c4e04543' });
      nav('/command');
      return;
    }
    try {
      const r = await create.mutateAsync(sid);
      await diagnose.mutateAsync({ id: r.incident.incident_id, verification: true });
      set({ activeIncidentId: r.incident.incident_id, selectedScenarioId: sid });
      nav('/command');
    } catch (e) {
      setErr(errorText(e));
    }
  };

  return (
    <div className="landing">
      <div className="l-dark">
        <div className="l-wrap">
          <nav className="l-nav" aria-label="Site">
            <Link to="/" className="brand"><Logo size={44} /><div><div className="brand-name">NetCoop <b>AI</b></div></div></Link>
            <div style={{ flex: 1 }} />
            <a className="link" href="#why">Why</a>
            <a className="link" href="#how">How it works</a>
            <a className="link" href="#capabilities">Capabilities</a>
            <a className="link" href="#evidence">Results</a>
            {CLERK_ENABLED ? (
              <LandingAuth
                signedIn={<><Link className="btn glassy sm" to="/command">Command Center <ArrowRight size={15} /></Link><div className="on-dark"><UserMenu /></div></>}
                signedOut={<GoogleButton label="Sign in" className="btn glassy sm" />} />
            ) : <Link className="btn glassy sm" to="/command">Command Center <ArrowRight size={15} /></Link>}
          </nav>

          <section className="l-hero">
            <div>
              <span className="l-kicker"><Sparkles size={14} />Multi-agent network fault diagnosis</span>
              <h1 style={{ display: 'flex', alignItems: 'center', gap: 18 }}><Logo size={84} /><span>NetCoop <span className="acc">AI</span></span></h1>
              <div className="l-tag">Evidence-Seeking Federated Network Diagnosis</div>
              <p className="l-lead">
                Independent specialist agents analyse your telemetry in parallel, a topology-aware reasoner weighs competing
                explanations, and when the evidence is tied it asks for the one observation that decides — before it concludes.
              </p>
              <div className="l-ctas">
                {CLERK_ENABLED && live ? (
                  <LandingAuth
                    signedOut={<><GoogleButton label="Continue with Google" className="btn neon big" />
                      <button className="btn glassy big" onClick={() => { set({ preview: true, activeIncidentId: 'INC-b2e30992c4e04543' }); nav('/command'); }}>View recorded demo</button></>}
                    signedIn={<><button className="btn neon big" onClick={() => demo()} disabled={busy}>
                      <Play size={17} />{busy ? 'Starting investigation…' : 'Diagnose organizer data (live run)'}</button>
                      <Link className="btn glassy big" to="/command">Open Command Center</Link></>} />
                ) : (
                  <>
                    <button className="btn neon big" onClick={() => demo()} disabled={busy}>
                      <Play size={17} />{busy ? 'Starting investigation…' : live ? 'Diagnose organizer data (live run)' : 'View demo incident (recorded)'}
                    </button>
                    <Link className="btn glassy big" to="/scenarios">Start investigation</Link>
                    <Link className="btn glassy big" to="/command">Explore Command Center</Link>
                  </>
                )}
              </div>
              {err && <div className="err" style={{ marginTop: 12, maxWidth: 560 }}>{err}</div>}
              <div className="l-facts">
                <span><b>3 specialists</b>independent A2A processes</span>
                <span><b>No LLM in the loop</b>deterministic, testable rules</span>
                <span><b>Organizer data</b>PS sample generator, mapped by a declared profile</span>
                <span><b>Calibrated confidence</b>measured on held-out cases</span>
              </div>
            </div>

            <div className="l-panel" aria-label="How one investigation flows">
              <h3><BrainCircuit size={16} />One investigation, end to end</h3>
              <div className="l-flow">
                <div className="l-step"><span className="n" style={{ background: '#0f2a5c' }}><Zap size={17} /></span><div><b>Incident &amp; telemetry</b><span>validated with units, timestamps and provenance</span></div></div>
                <div className="l-agents">
                  {[['Performance', Gauge, '#1a73e8'], ['Infrastructure', Server, '#7c4dff'], ['Connectivity', Network, '#43a047']].map(([n, I, c]) => {
                    const Icon = I as typeof Gauge;
                    return <div key={n as string} className="l-step"><span className="n" style={{ background: c as string }}><Icon size={17} /></span><div><b style={{ fontSize: 13 }}>{n as string}</b><span>agent</span></div></div>;
                  })}
                </div>
                <div className="l-step"><span className="n" style={{ background: '#0f2a5c' }}><GitCompareArrows size={17} /></span><div><b>STEaR reasoner</b><span>competing hypotheses, constrained by topology and time</span></div></div>
                <div className="l-step" style={{ borderStyle: 'dashed', borderColor: 'rgba(57,255,136,.35)' }}><span className="n" style={{ background: '#c2185b' }}><SearchCheck size={17} /></span><div><b>Verification loop</b><span>asks an agent for the missing, discriminating observation</span></div></div>
                <div className="l-step"><span className="n" style={{ background: '#2e9e44' }}><ShieldCheck size={17} /></span><div><b>Evidence-backed diagnosis</b><span>cause, scope, support category, alternatives, limitations</span></div></div>
              </div>
              <div className="l-live">
                {preview ? <span>Recorded preview mode (no backend)</span> : health.isSuccess ? (
                  <>
                    <span className="live-dot" />Backend online{meta.data ? ` · v${meta.data.version} · ${meta.data.agent_transport.toUpperCase()}` : ''}
                    {agents.data && <span>· {agents.data.agents.filter((a) => a.status === 'available').length}/{agents.data.agents.length} agents: {agents.data.agents.map((a) => agentLabel(a.agent_id).replace(' & Services', '')).join(', ')}</span>}
                  </>
                ) : <span>Backend not reachable — the demo opens the labeled recorded run instead</span>}
              </div>
            </div>
          </section>
        </div>
      </div>

      <section className="l-section" id="why">
        <div className="l-wrap">
          <div className="l-eyebrow">Why NetCoop AI</div>
          <h2 className="l-h2">Alerts tell you something is wrong. Not why.</h2>
          <div className="l-grid g2">
            <div className="l-problem bad">
              <h3>The problem</h3>
              <p className="muted" style={{ margin: 0, lineHeight: 1.6 }}>
                Network faults are distributed and ambiguous. A dead access point, a failed switch port and an upstream outage can
                produce the same symptoms. Dashboards show thresholds crossing; the root cause is left to the operator, and the
                data needed to decide is often in another system.
              </p>
            </div>
            <div className="l-problem good">
              <h3>The NetCoop AI approach</h3>
              <p className="muted" style={{ margin: 0, lineHeight: 1.6 }}>
                Specialists for performance, infrastructure and connectivity each examine their own evidence. A reasoner compares
                every explanation against the topology and the timeline, notices when two fit equally well, and requests the
                specific observation that separates them. If the data cannot decide, it says so.
              </p>
            </div>
          </div>
          <div className="l-grid g5">
            {[
              [Users, 'Multi-agent collaboration', 'Three independent agents exchange typed findings over the A2A protocol.'],
              [FileCheck2, 'Evidence-backed reasoning', 'Each finding links to validated observations and the raw records behind them.'],
              [Network, 'Topology-aware diagnosis', 'Explanations must fit the network graph: dependencies and impact scope.'],
              [SearchCheck, 'Verification before conclusion', 'Ties are broken by asking for evidence, not by guessing.'],
              [BadgeCheck, 'Auditable reports', 'Schema-validated JSON with cause, scope, alternatives and limitations.'],
            ].map(([I, t, d]) => {
              const Icon = I as typeof Users;
              return <div key={t as string} className="l-card"><span className="l-ico"><Icon size={21} /></span><h3>{t as string}</h3><p>{d as string}</p></div>;
            })}
          </div>
        </div>
      </section>

      <section className="l-section alt" id="how">
        <div className="l-wrap">
          <div className="l-eyebrow">How it works</div>
          <h2 className="l-h2">From telemetry to a diagnosis you can check</h2>
          <div className="l-howto">
            {[
              [Database, 'Telemetry arrives', 'NDEP JSON or vendor CSV. Units, timestamps and freshness are validated; bad records are quarantined, never coerced.'],
              [Users, 'Specialists analyse in parallel', 'Performance, Infrastructure and Connectivity agents return findings with observation references.'],
              [GitCompareArrows, 'STEaR builds hypotheses', 'Every fault explanation is scored on symptoms explained, independent sources and contradictions.'],
              [SearchCheck, 'Missing evidence is requested', 'If explanations tie, the agent that owns the discriminating data is asked for it.'],
              [ShieldCheck, 'Evidence-backed diagnosis', 'Cause, affected scope, support category, alternatives and recommended actions.'],
            ].map(([I, t, d], i) => {
              const Icon = I as typeof Users;
              return <div key={t as string} className="l-how"><div className="n"><Icon size={22} /></div><h4>{i + 1}. {t as string}</h4><p>{d as string}</p></div>;
            })}
          </div>
        </div>
      </section>

      <section className="l-section" id="capabilities">
        <div className="l-wrap">
          <div className="l-eyebrow">Product</div>
          <h2 className="l-h2">Everything the backend does, visible</h2>
          <div className="l-grid g3">
            {[
              ['/agents', Users, 'Agent collaboration', 'Every A2A task, finding and verification request, with the raw message exchanged.'],
              ['/topology', Network, 'Network topology', 'Root cause, affected devices and impact scope on the real topology snapshot.'],
              ['/evidence', Layers, 'Evidence lineage', 'Normalised observations with quality flags, traced back to immutable raw records.'],
              ['/reasoning', SearchCheck, 'Verification workflow', 'Which hypotheses were tied, what was asked, what came back and what it changed.'],
              ['/report', FileCheck2, 'Diagnostic report', 'Revisioned, schema-validated report with JSON and text export.'],
              ['/scenarios', FlaskConical, 'Scenarios & upload', 'Run documented scenarios or upload your own topology and telemetry.'],
            ].map(([to, I, t, d]) => {
              const Icon = I as typeof Users;
              return <Link key={t as string} to={to as string} className="l-card"><span className="l-ico g"><Icon size={21} /></span><h3>{t as string} <ArrowRight size={15} style={{ verticalAlign: -2 }} /></h3><p>{d as string}</p></Link>;
            })}
          </div>
        </div>
      </section>

      <Results />

      <div className="l-dark">
        <div className="l-wrap l-cta">
          <Logo size={64} />
          <h2 style={{ marginTop: 14 }}>See a full investigation</h2>
          <p style={{ color: '#aebfe0', margin: '10px auto 0', maxWidth: 660 }}>Diagnose the organizer's sample telemetry, or run the verification showcase: the evidence is first ambiguous, the system asks the infrastructure agent for the AP status, and concludes.</p>
          <div className="l-ctas" style={{ justifyContent: 'center' }}>
            {CLERK_ENABLED && live ? (
              <LandingAuth signedOut={<GoogleButton label="Continue with Google" className="btn neon big" />}
                signedIn={<><button className="btn neon big" onClick={() => demo()} disabled={busy}><Play size={17} />Diagnose organizer data</button>
                  <button className="btn glassy big" onClick={() => demo(SHOWCASE)} disabled={busy}>Verification showcase</button></>} />
            ) : (
              <>
                <button className="btn neon big" onClick={() => demo()} disabled={busy}><Play size={17} />Diagnose organizer data</button>
                <button className="btn glassy big" onClick={() => demo(SHOWCASE)} disabled={busy || !live}>Verification showcase</button>
              </>
            )}
            <Link className="btn glassy big" to="/command">Enter Command Center <ArrowRight size={16} /></Link>
          </div>
        </div>
        <div className="l-wrap l-foot">NetCoop AI · scenario data is synthetic and labeled as such · no network changes are ever made</div>
      </div>
    </div>
  );
}

const METHODS: [string, string][] = [['A_threshold', 'Threshold rules'], ['B_centralized', 'Centralized engine'], ['C_stear_noverify', 'STEaR, no verification'], ['D_full', 'NetCoop AI (full)']];

function Results() {
  const ev = useEvaluations();
  const r = ev.data?.evaluations.find((e) => e.name === 'results-heldout-v3');
  const set = r ? Object.values(r.sets)[0] : null;
  return (
    <section className="l-section alt" id="evidence">
      <div className="l-wrap">
        <div className="l-eyebrow">Measured, with caveats</div>
        <h2 className="l-h2">Held-out benchmark: acceptable outcomes</h2>
        <p className="l-p">
          An acceptable outcome is the correct cause when the data can identify it, or an honest abstention when it cannot.
          It is not root-cause accuracy. The scenarios are synthetic and come from the project's own generator.
        </p>
        {set ? (
          <div className="l-bench">
            {METHODS.map(([k, label]) => {
              const v = set.summary[k]?.acceptable_outcome as Rate | undefined;
              return (
                <div key={k} className={`l-card ${k === 'D_full' ? 'best' : ''}`}>
                  <div className="muted" style={{ fontSize: 13.5, fontWeight: 600 }}>{label}</div>
                  <div className="v" style={{ color: k === 'D_full' ? 'var(--success-ink)' : undefined }}>{v ? `${v.count}/${v.of}` : '—'}</div>
                </div>
              );
            })}
          </div>
        ) : <p className="l-p">{ev.isError ? 'Results unavailable while the backend is offline.' : 'Loading results…'}</p>}
        <div style={{ marginTop: 18 }}><Link to="/evaluation" className="btn">Full evaluation and limitations <ArrowRight size={15} /></Link></div>
      </div>
    </section>
  );
}
