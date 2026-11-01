import { useLayoutEffect, useRef, useState, type ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { Activity, BrainCircuit, CheckCircle2, CircleDashed, Gauge, Loader2, Network, Search, Server, ShieldCheck, XCircle, Zap } from 'lucide-react';
import type { IncidentDetail, Report } from '@/api/types';
import { AGENT_COLOR, AGENT_ROLE, agentLabel, claimLabel, faultLabel, subjectText, SUPPORT_LABEL } from '@/lib/format';
import { splitHyp, type RunFacts } from '@/lib/run';
import { verdictTitle } from './Reasoning';

type Key = 'inc' | 'performance-agent' | 'infrastructure-agent' | 'connectivity-agent' | 'stear' | 'verify' | 'final';
type Status = 'done' | 'active' | 'failed' | 'idle';

const AGENT_ICON: Record<string, typeof Gauge> = { 'performance-agent': Gauge, 'infrastructure-agent': Server, 'connectivity-agent': Network };

function StateIcon({ s }: { s: Status }) {
  if (s === 'done') return <CheckCircle2 size={18} className="state-ico" color="#4caf50" aria-label="done" />;
  if (s === 'active') return <Loader2 size={18} className="state-ico" color="#1a73e8" style={{ animation: 'spin 1s linear infinite' }} aria-label="in progress" />;
  if (s === 'failed') return <XCircle size={18} className="state-ico" color="#e5484d" aria-label="failed" />;
  return <CircleDashed size={18} className="state-ico" color="#a3b0c2" aria-label="not started" />;
}

/** Incident → three specialists (parallel, over A2A) → STEaR → targeted verification loop → diagnosis.
 * Every value shown is read from the persisted run (events, A2A attempts, challenges, findings, report). */
export function AgentFlow({ detail, facts, report, running }: { detail: IncidentDetail; facts: RunFacts; report: Report | null; running: boolean }) {
  const nav = useNavigate();
  const box = useRef<HTMLDivElement>(null);
  const refs = useRef<Partial<Record<Key, HTMLElement | null>>>({});
  const [wires, setWires] = useState<{ d: string; cls: string; label?: { x: number; y: number; text: string } }[]>([]);
  const cur = facts.current;
  const verifying = cur === 'VERIFYING';
  const correlating = cur === 'CORRELATING';
  const done = !!facts.terminal;
  const ch = facts.challenges;
  const lastCh = ch[ch.length - 1];
  const target = lastCh?.challenge.target_agent_id;
  const firstRound = facts.rounds[0];
  const lastRound = facts.rounds[facts.rounds.length - 1];
  const reportIsThisRun = done && !!report;
  const val = facts.events.find((e) => e.state === 'VALIDATING')?.detail as Record<string, unknown> | undefined;

  const st: Record<Key, Status> = {
    inc: facts.seen.has('VALIDATING') ? 'done' : running ? 'active' : 'idle',
    'performance-agent': facts.agents[0].state, 'infrastructure-agent': facts.agents[1].state, 'connectivity-agent': facts.agents[2].state,
    stear: correlating ? 'active' : facts.rounds.length ? 'done' : 'idle',
    verify: verifying ? 'active' : ch.length ? (ch.every((c) => c.outcomes.at(-1)?.outcome === 'obtained') ? 'done' : 'failed') : 'idle',
    final: reportIsThisRun ? 'done' : running ? 'idle' : report ? 'done' : 'idle',
  };

  useLayoutEffect(() => {
    const el = box.current;
    if (!el) return;
    const calc = () => {
      const b = el.getBoundingClientRect();
      const r = (k: Key) => {
        const n = refs.current[k];
        if (!n) return null;
        const x = n.getBoundingClientRect();
        return { l: x.left - b.left, r: x.right - b.left, t: x.top - b.top, bt: x.bottom - b.top, cx: x.left - b.left + x.width / 2, cy: x.top - b.top + x.height / 2 };
      };
      const curve = (x1: number, y1: number, x2: number, y2: number) => { const m = (x1 + x2) / 2; return `M${x1},${y1} C${m},${y1} ${m},${y2} ${x2},${y2}`; };
      const cls = (a: Status, b: Status, live: boolean) => (live ? 'wire on flowing' : a === 'done' && (b === 'done' || b === 'failed') ? 'wire ok' : 'wire');
      const out: typeof wires = [];
      const inc = r('inc'), stear = r('stear'), verify = r('verify'), fin = r('final');
      for (const k of ['performance-agent', 'infrastructure-agent', 'connectivity-agent'] as const) {
        const a = r(k);
        if (!a || !inc || !stear) continue;
        out.push({ d: curve(inc.r, inc.cy, a.l, a.cy), cls: cls(st.inc, st[k], st[k] === 'active') });
        out.push({ d: curve(a.r, a.cy, stear.l, stear.cy), cls: cls(st[k], st.stear, correlating) });
      }
      if (stear && verify) out.push({ d: `M${stear.cx},${stear.t} L${verify.cx},${verify.bt}`, cls: ch.length ? 'wire ask' : 'wire', });
      if (verify && target) {
        const a = r(target as Key);
        if (a) {
          const d = `M${verify.l},${verify.cy} C${verify.l - 30},${verify.cy} ${a.r + 30},${a.cy - 10} ${a.r},${a.cy - 10}`;
          out.push({ d, cls: verifying ? 'wire ask flowing' : 'wire ask' });
        }
      }
      if (stear && fin) out.push({ d: curve(stear.r, stear.cy, fin.l, fin.cy), cls: cls(st.stear, st.final, false) });
      setWires(out);
    };
    calc();
    const ro = new ResizeObserver(calc);
    ro.observe(el);
    return () => ro.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [JSON.stringify(st), target, ch.length, verifying, correlating, facts.rounds.length]);

  const reg = (k: Key) => (n: HTMLElement | null) => { refs.current[k] = n; };
  const c = detail.evidence_counts;
  const node = (k: Key, cls: string, onClick: () => void, children: ReactNode, badge?: ReactNode) => (
    <button key={k} ref={reg(k)} className={`fnode ${st[k]} ${cls}`} onClick={onClick}>{badge}{children}</button>
  );

  return (
    <div>
      <div className="flow" ref={box}>
        <svg className="wires" aria-hidden>
          {wires.map((w, i) => <path key={i} d={w.d} className={w.cls} />)}
          {wires.filter((w) => w.label).map((w, i) => <text key={`l${i}`} x={w.label!.x} y={w.label!.y} textAnchor="middle" className="wire-label">{w.label!.text}</text>)}
        </svg>

        <div className="flow-col">
          {node('inc', '', () => nav('/evidence'), (
            <>
              <div className="fnode-head"><span className="fnode-ico" style={{ background: '#0b1f45' }}><Zap size={17} /></span>
                <span className="fnode-title">Incident</span><StateIcon s={st.inc} /></div>
              <div className="fnode-sub">{detail.incident.title ?? detail.incident.incident_id}</div>
              <div className="fnode-stat" style={{ display: 'grid', gap: 2 }}>
                <span><b>{c.observations.toLocaleString()}</b> observations</span>
                {val && <span><b>{String(val.passed ?? 0)}</b> passed · <b>{String(val.stale ?? 0)}</b> stale · <b>{String(val.quarantined ?? 0)}</b> quarantined</span>}
              </div>
            </>
          ))}
        </div>

        <div className="flow-col agents">
          {facts.agents.map((ag) => {
            const Icon = AGENT_ICON[ag.id] ?? Activity;
            const claims = [...new Set(ag.present.map((f) => `${claimLabel(f.claim)} @ ${subjectText(f.subject)}`))];
            const stored = ag.investigate.reduce((n, x) => n + (x.detail.findings_stored?.length ?? 0), 0);
            return node(ag.id as Key, '', () => nav('/agents'), (
              <>
                <div className="fnode-head">
                  <span className="fnode-ico" style={{ background: AGENT_COLOR[ag.id] }}><Icon size={17} /></span>
                  <span style={{ minWidth: 0 }}><span className="fnode-title">{agentLabel(ag.id)} Agent</span></span>
                  <StateIcon s={ag.state} />
                </div>
                <div className="fnode-sub">
                  {ag.state === 'idle' ? AGENT_ROLE[ag.id] : ag.state === 'active' ? `Analysing: ${AGENT_ROLE[ag.id].toLowerCase()}…` :
                    claims.length ? claims.slice(0, 2).join(' · ') + (claims.length > 2 ? ` · +${claims.length - 2}` : '') : 'No anomaly in its domain'}
                </div>
                {ag.state !== 'idle' && (
                  <div className="fnode-stat">
                    <span><b>{ag.present.length}</b> anomal{ag.present.length === 1 ? 'y' : 'ies'}</span>
                    <span><b>{ag.checked}</b> findings</span>
                    <span>{ag.investigate.length + ag.verify.length} A2A task{ag.investigate.length + ag.verify.length === 1 ? '' : 's'}{stored ? '' : ''}</span>
                  </div>
                )}
              </>
            ), target === ag.id && ch.length ? <span className="fnode-badge" style={{ color: 'var(--magenta)', borderColor: 'rgba(194,24,91,.35)' }}>ASKED TO VERIFY</span> : undefined);
          })}
        </div>

        <div className="flow-col" style={{ gap: 26 }}>
          {node('verify', 'verify', () => nav('/reasoning'), (
            <>
              <div className="fnode-head"><span className="fnode-ico" style={{ background: ch.length ? '#c2185b' : '#a3b0c2' }}><Search size={16} /></span>
                <span className="fnode-title">Verification check</span><StateIcon s={st.verify} /></div>
              <div className="fnode-sub">
                {lastCh ? <>Asked {agentLabel(lastCh.challenge.target_agent_id)} for <b className="mono">{lastCh.challenge.requested_observation.metric}</b> of <b className="mono">{subjectText(lastCh.challenge.requested_observation.subject)}</b>
                  {lastCh.outcomes.at(-1) ? <> → {lastCh.outcomes.at(-1)!.outcome === 'obtained' ? `${lastCh.outcomes.at(-1)!.detail.new_observation_ids?.length ?? 0} recorded observations returned` : lastCh.outcomes.at(-1)!.outcome.replace(/_/g, ' ')}</> : ' …'}</>
                  : verifying ? 'Choosing the observation that best separates the explanations…'
                  : done ? (report?.verification?.enabled === false ? 'Disabled for this run' : 'Not needed: the evidence was already decisive') : 'Runs only if explanations are still tied'}
              </div>
              {ch.length > 1 && <div className="fnode-stat"><span><b>{ch.length}</b> checks</span></div>}
            </>
          ))}
          {node('stear', '', () => nav('/reasoning'), (
            <>
              <div className="fnode-head"><span className="fnode-ico" style={{ background: '#0b1f45' }}><BrainCircuit size={17} /></span>
                <span className="fnode-title">STEaR Reasoner</span><StateIcon s={st.stear} /></div>
              <div className="fnode-sub">Topology- and time-aware comparison of competing explanations</div>
              {firstRound && (
                <div className="fnode-stat" style={{ display: 'grid', gap: 2 }}>
                  {facts.rounds.map((r) => (
                    <span key={r.at}>Round {r.round + 1}: <b style={{ color: r.status === 'diagnosed' ? 'var(--success-ink)' : r.status === 'ambiguous' ? '#a15c00' : undefined }}>{r.status.replace(/_/g, ' ')}</b>
                      {r.status === 'ambiguous' && r.competitors.length ? ` · ${r.competitors.length} tied` : ''}</span>
                  ))}
                  {lastRound && <span><b>{lastRound.hypotheses}</b> hypotheses compared</span>}
                </div>
              )}
            </>
          ))}
        </div>

        <div className="flow-col">
          {node('final', `final ${report && report.status !== 'diagnosed' && report.status !== 'healthy' ? 'amb' : ''}`, () => nav('/report'), (
            <>
              <div className="fnode-head"><span className="fnode-ico" style={{ background: st.final === 'done' ? '#4caf50' : '#a3b0c2' }}><ShieldCheck size={17} /></span>
                <span className="fnode-title">{running ? 'Diagnosis' : 'Final diagnosis'}</span><StateIcon s={running ? 'idle' : st.final} /></div>
              {running ? <div className="fnode-sub">Concluded only after the reasoning (and any verification) finishes</div>
                : report ? (
                  <>
                    <div className="verdict-mini">{report.root_causes?.length ? report.root_causes.map((r) => <div key={r.hypothesis_id}>{r.fault_type}<div className="mono" style={{ fontSize: 13 }}>@ {r.location}</div></div>) : verdictTitle(report)}</div>
                    <div className="fnode-stat"><span className={`chip t-${report.confidence_category === 'high_support' ? 'green' : 'amber'}`}>{SUPPORT_LABEL[report.confidence_category]}</span></div>
                  </>
                ) : <div className="fnode-sub">Not diagnosed yet</div>}
            </>
          ))}
        </div>
      </div>
      <Stages facts={facts} running={running} report={report} />
      {firstRound?.status === 'ambiguous' && firstRound.competitors.length > 0 && (
        <div className="panel-sub" style={{ marginTop: 10 }}>
          Round 1 tie: {firstRound.competitors.map((h) => { const [f, l] = splitHyp(h); return `${faultLabel(f)} at ${l}`; }).join(' vs ')}
        </div>
      )}
      <style>{'@keyframes spin{to{transform:rotate(360deg)}}'}</style>
    </div>
  );
}

function Stages({ facts, running }: { facts: RunFacts; running: boolean; report: Report | null }) {
  const s = facts.seen;
  const cur = facts.current;
  const done = !!facts.terminal;
  const steps: { label: string; state: 'done' | 'now' | 'skip' | '' }[] = [
    { label: 'Collect & analyse', state: s.has('CORRELATING') ? 'done' : ['VALIDATING', 'DISCOVERING', 'INVESTIGATING'].includes(cur ?? '') && running ? 'now' : '' },
    { label: 'Form hypotheses', state: s.has('CORRELATING') && (s.has('VERIFYING') || done) && cur !== 'CORRELATING' ? 'done' : cur === 'CORRELATING' ? 'now' : '' },
    { label: s.has('VERIFYING') || !done ? 'Seek missing evidence' : 'Seek missing evidence · not needed', state: cur === 'VERIFYING' ? 'now' : s.has('VERIFYING') ? 'done' : done ? 'skip' : '' },
    { label: done ? `Conclude · ${facts.terminal!.state.toLowerCase().replace(/_/g, ' ')}` : 'Conclude', state: done ? 'done' : '' },
  ];
  return (
    <div className="stages" aria-label="Investigation stages">
      {steps.map((st, i) => (
        <span key={st.label} style={{ display: 'contents' }}>
          {i > 0 && <span className="stage-sep" />}
          <span className={`stage ${st.state}`}><i>{st.state === 'done' ? '✓' : i + 1}</i>{st.label}</span>
        </span>
      ))}
    </div>
  );
}
