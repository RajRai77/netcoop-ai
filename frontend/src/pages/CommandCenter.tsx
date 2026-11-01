import { useEffect, useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import {
  ArrowRight, BrainCircuit, Calendar, CheckCircle2, Clock, Database, Download, FileText, Layers, ListTree, Network, Play,
  RotateCcw, Share2, ShieldCheck, Users, XCircle,
} from 'lucide-react';
import { useCreateFromScenario, useDiagnose, useScenarios } from '@/api/hooks';
import { errorText } from '@/api/client';
import type { Finding, Hypothesis, Report } from '@/api/types';
import { useApp } from '@/state/settings';
import {
  agentLabel, claimLabel, clock, dataSourceLabel, dateTimeOf, downloadBlob, faultLabel, fmtValue, HYP_LABEL, STATUS_LABEL,
  subjectText, SUPPORT_LABEL,
} from '@/lib/format';
import { leadingCompetitor, runFacts, splitHyp, type RunFacts } from '@/lib/run';
import { Chip, Confidence, Empty, ErrorState, Kpi, Loading, Panel, StatusChip } from '@/components/ui';
import { AgentFlow } from '@/components/AgentFlow';
import { buildTimeline, TimelineList } from '@/components/Timeline';
import { impactScope, nodeStates, TopologyGraph, TopologyLegend } from '@/components/Topology';
import { HypothesisDrawer, HypothesisRow, pickHypotheses, verdictTitle } from '@/components/Reasoning';
import { useActive } from './useActive';

function Welcome() {
  const { set, preview } = useApp();
  const scen = useScenarios();
  const create = useCreateFromScenario();
  const diagnose = useDiagnose();
  const [err, setErr] = useState<string | null>(null);
  const has = (id: string) => !!scen.data?.scenarios.some((s) => s.scenario_id === id);
  const run = async (sid: string) => {
    setErr(null);
    try {
      const r = await create.mutateAsync(sid);
      await diagnose.mutateAsync({ id: r.incident.incident_id, verification: true });
      set({ activeIncidentId: r.incident.incident_id });
    } catch (e) {
      setErr(errorText(e));
    }
  };
  return (
    <section className="glass hero" style={{ gridTemplateColumns: '1fr' }}>
      <div>
        <div className="hero-title"><h1>Start an investigation</h1></div>
        <p className="muted" style={{ maxWidth: 780, fontSize: 15.5 }}>
          Run a scenario, pick an earlier incident from the search bar, or upload your own telemetry. Three specialist agents run
          as separate processes and exchange typed evidence over A2A; everything on this screen is read back from the backend.
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 14 }}>
          <button className="btn primary big" onClick={() => run('ORG-03-hardware-failure')} disabled={!has('ORG-03-hardware-failure') || preview || create.isPending || diagnose.isPending}>
            <Play size={17} />{create.isPending || diagnose.isPending ? 'Starting…' : 'Run organizer data: hardware failure'}
          </button>
          <button className="btn big" onClick={() => run('S19-ap-down-status-in-archive')} disabled={!has('S19-ap-down-status-in-archive') || preview || create.isPending || diagnose.isPending}>
            Verification showcase (S19)
          </button>
          <Link className="btn big" to="/scenarios">Choose a scenario or upload</Link>
          <Link className="btn big" to="/incidents">Earlier investigations</Link>
        </div>
        {err && <div className="err" style={{ marginTop: 12 }}>{err}</div>}
      </div>
    </section>
  );
}

function useElapsed(start: string | null, end: string | null, running: boolean) {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    if (!running) return;
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, [running]);
  if (!start) return null;
  return new Date(end ?? new Date(now).toISOString()).getTime() - new Date(start).getTime();
}

export function CommandCenter() {
  const a = useActive();
  const { preview } = useApp();
  const diagnose = useDiagnose();
  const scenarios = useScenarios();
  const [selNode, setSelNode] = useState<string | null>(null);
  const [openHyp, setOpenHyp] = useState<Hypothesis | null>(null);
  const items = useMemo(() => (a.timeline.data ? buildTimeline(a.timeline.data, a.runId) : []), [a.timeline.data, a.runId]);
  const topo = a.topology.data?.topology ?? null;
  const report = a.report.data ?? null;
  const fData = a.findings.data;
  const findings = useMemo(() => fData?.findings ?? [], [fData]);
  const facts = useMemo(() => runFacts(a.timeline.data, a.runId, findings, a.running), [a.timeline.data, a.runId, findings, a.running]);
  const states = useMemo(() => (topo ? nodeStates(topo, report, findings) : null), [topo, report, findings]);
  const counts = useMemo(() => {
    const m = new Map();
    if (states) for (const s of states.values()) m.set(s, (m.get(s) ?? 0) + 1);
    return m;
  }, [states]);
  const elapsed = useElapsed(facts.startedAt, facts.endedAt, a.running);

  if (!a.id) return <Welcome />;
  if (a.incident.isLoading) return <Loading label="Loading investigation…" />;
  if (a.incident.isError) return <Panel><ErrorState error={a.incident.error} title="Incident unavailable" /></Panel>;
  const d = a.incident.data!;
  const inc = d.incident;
  const agents = a.agents.data?.agents ?? [];
  const online = agents.filter((x) => x.status === 'available').length;
  const devices = topo?.nodes.filter((n) => n.type !== 'segment').length ?? 0;
  const affected = states ? [...states.values()].filter((s) => s === 'cause' || s === 'affected').length : 0;
  const lastRound = facts.rounds[facts.rounds.length - 1];
  const showReport = report && !a.running ? report : null;

  return (
    <>
      <section className="glass strong hero">
        <div style={{ minWidth: 0 }}>
          <div className="hero-title">
            <h1>Investigation: {inc.title ?? inc.incident_id}</h1>
            {a.running ? <Chip tone="blue" pip>In progress</Chip> : report ? <StatusChip status={report.status} /> : <Chip tone="muted">Not diagnosed yet</Chip>}
          </div>
          <div className="hero-meta">
            <span className="mono">{inc.incident_id}</span>
            <span><Calendar size={14} />{dateTimeOf(inc.created_at)}</span>
            <span><Database size={14} />Data: <Chip tone={preview ? 'amber' : 'green'}>{dataSourceLabel(inc, preview, scenarios.data?.scenarios.find((s) => s.scenario_id === inc.scenario_id)?.split)}</Chip></span>
            {inc.scenario_id && <span className="mono">{inc.scenario_id}</span>}
            {a.stream.status === 'open' && <span><span className="live-dot" />Live event stream</span>}
          </div>
          {scenarios.data?.scenarios.find((s) => s.scenario_id === inc.scenario_id)?.split === 'organizer' && (
            <div className="panel-sub" style={{ marginTop: 8, maxWidth: 900 }}>
              Records from the organizer's sample generator, mapped by the declared profile <span className="mono">organizer-colab-json</span>.
              The generator's fault labels (e.g. "hardware failure") are symptom classes; NetCoop reports the root-cause type from its
              fault library that the evidence supports, and leaves <span className="mono">queue_drops</span>, <span className="mono">interface_errors</span> and
              {' '}<span className="mono">status</span> unused because the generator does not define their meaning.
            </div>
          )}
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <button className="btn" disabled={a.running || preview || diagnose.isPending}
                  title={preview ? 'Preview mode is read-only' : 'Run the diagnosis again on the stored evidence (creates a new report revision)'}
                  onClick={() => diagnose.mutate({ id: inc.incident_id, verification: true })}>
            <RotateCcw size={16} />{d.reports.length ? 'Re-run' : 'Run diagnosis'}
          </button>
          {report && <button className="btn" onClick={() => downloadBlob(`${report.incident_id}-r${report.revision}.json`, JSON.stringify(report, null, 2), 'application/json')}><Download size={16} />Export report</button>}
          {report && <Link className="btn primary" to="/report">View full report <ArrowRight size={16} /></Link>}
          {diagnose.isError && <div className="err" style={{ width: '100%' }}>{errorText(diagnose.error)}</div>}
        </div>
      </section>

      <div className="kpis">
        <Kpi icon={<Users size={22} />} tone="green" label="Active agents" value={<>{online}<small>/ {agents.length}</small></>}
             note={<span className="panel-sub">independent A2A processes</span>} title={agents.map((x) => `${x.agent_id}: ${x.status}`).join('\n')} />
        <Kpi icon={<Share2 size={22} />} label="Network devices" value={devices || '—'}
             note={topo ? <span className={affected ? 'c-red' : 'panel-sub'} style={{ fontSize: 12.5, fontWeight: 600 }}>{affected ? `${affected} affected` : 'none affected'}</span> : <span className="panel-sub">no topology</span>}
             title={topo ? `${topo.topology_snapshot_id} · ${topo.nodes.length - devices} logical segments not counted` : undefined} />
        <Kpi icon={<Layers size={22} />} tone="violet" label="Evidence records" value={d.evidence_counts.observations.toLocaleString()}
             note={<span className="panel-sub">{facts.verificationObs ? <b className="c-green">+{facts.verificationObs} from verification</b> : `${d.evidence_counts.findings} findings`}</span>}
             title="Validated observations in the evidence ledger" />
        <Kpi icon={<BrainCircuit size={22} />} tone="amber" label="Current diagnosis"
             value={<span style={{ fontSize: 19 }}>{a.running ? (a.state === 'VERIFYING' ? 'Verifying' : 'Investigating') : report ? STATUS_LABEL[report.status] : '—'}</span>}
             note={a.running && lastRound ? <Chip tone="amber">{lastRound.status.replace(/_/g, ' ')}{lastRound.competitors.length > 1 ? ` (${lastRound.competitors.length} hypotheses)` : ''}</Chip>
               : report ? <div className="chips"><Chip tone={report.confidence_category === 'high_support' ? 'green' : 'amber'}>{SUPPORT_LABEL[report.confidence_category]}</Chip><Confidence r={report} /></div> : undefined}
             title="Support category from documented rules; confidence calibrated on held-out results" />
        <Kpi icon={<Clock size={22} />} label={a.running ? 'Elapsed time' : 'Run time'} value={elapsed != null ? clock(elapsed) : '—'}
             note={<span className="panel-sub">{facts.rounds.length} reasoning round{facts.rounds.length === 1 ? '' : 's'} · {facts.challenges.length} check{facts.challenges.length === 1 ? '' : 's'}</span>} />
      </div>

      <div className="row primary">
        <Panel title="Agent collaboration & reasoning flow" icon={<Users size={19} />}
               sub="Specialists work in parallel; STEaR compares explanations and asks for missing evidence before concluding"
               actions={a.running ? <Chip tone="green" pip>Live</Chip> : <Link className="btn ghost sm" to="/agents">A2A messages</Link>}>
          {a.timeline.isError ? <ErrorState error={a.timeline.error} /> : a.timeline.isLoading ? <Loading /> :
            <AgentFlow detail={d} facts={facts} report={report} running={a.running} />}
        </Panel>
        <Panel title="Network topology" icon={<Network size={19} />}
               sub={topo ? `${topo.nodes.length} nodes · ${topo.links.length} links · ${topo.kind} snapshot` : undefined}
               actions={<>{a.stream.status === 'open' ? <Chip tone="green" pip>Live</Chip> : topo && <Chip tone="muted">Snapshot</Chip>}<Link className="btn ghost sm" to="/topology">Explore</Link></>}>
          {a.topology.isLoading ? <Loading /> : !topo ? <Empty title="No topology snapshot">Localization is limited to measured components; the report states this limitation.</Empty> : (
            <div className="topo-col" style={{ minHeight: 400 }}>
              <div className="topo-wrap">
                <TopologyGraph topo={topo} report={report} findings={findings} selected={selNode} onSelect={setSelNode} compact />
                {showReport && <ScopeCard r={showReport} />}
              </div>
              <TopologyLegend counts={counts} strip />
            </div>
          )}
        </Panel>
      </div>

      <div className="row triple">
        <Panel className="h-secondary" title="Investigation timeline" icon={<ListTree size={19} />}
               sub={a.running ? 'Updating from the live event stream' : `${items.length} persisted steps in the latest run`}
               actions={<Link className="btn ghost sm" to="/agents">All</Link>}>
          {a.timeline.isLoading ? <Loading /> : <TimelineList items={items} incidentId={inc.incident_id} emptyText={d.reports.length ? 'No exchanges recorded.' : 'Run a diagnosis to see the agents collaborate.'} />}
        </Panel>
        <Panel className="h-secondary" title="Competing hypotheses" icon={<BrainCircuit size={19} />}
               sub="Bars show symptoms explained, not probability"
               actions={<Link className="btn ghost sm" to="/reasoning">Reasoning</Link>}>
          {!showReport ? <Empty title={a.running ? 'Correlating…' : 'No hypotheses yet'}>{a.running ? 'Hypotheses are published with the report revision.' : 'Run a diagnosis.'}</Empty>
            : <Hypotheses r={showReport} findings={findings} onOpen={setOpenHyp} />}
        </Panel>
        <Panel className="h-secondary" title="Diagnostic report" icon={<FileText size={19} />}
               sub={showReport ? `Revision ${showReport.revision} · ${dateTimeOf(showReport.generated_at)}` : undefined}
               actions={showReport && <Link className="btn ghost sm" to="/report">Full report</Link>}>
          {a.report.isLoading ? <Loading /> : showReport ? <ReportSummary r={showReport} facts={facts} obs={d.evidence_counts.observations} />
            : <Empty title={a.running ? 'Investigation in progress' : 'No report yet'}>{a.running ? 'The report appears when the coordinator reaches a conclusion.' : 'Run a diagnosis to produce a report.'}</Empty>}
        </Panel>
      </div>
      <HypothesisDrawer h={openHyp} findings={findings} onClose={() => setOpenHyp(null)} />
    </>
  );
}

function ScopeCard({ r }: { r: Report }) {
  const scope = impactScope(r);
  if (!r.root_causes?.length) return null;
  return (
    <div className="scope-card">
      <div className="panel-sub" style={{ fontWeight: 600 }}>Affected scope</div>
      <b>{r.affected_devices.join(', ') || r.root_causes.map((c) => c.location).join(', ')}</b>
      <div className="panel-sub">{scope.size} node{scope.size === 1 ? '' : 's'} in topology impact scope</div>
    </div>
  );
}

function Hypotheses({ r, findings, onOpen }: { r: Report; findings: Finding[]; onOpen: (h: Hypothesis) => void }) {
  const hyps = pickHypotheses(r, 3);
  const max = Math.max(1, ...hyps.map((h) => h.explained_findings.length));
  const causeIds = new Set((r.root_causes ?? []).map((c) => c.hypothesis_id));
  const lead = hyps.find((h) => causeIds.has(h.hypothesis_id));
  const comp = leadingCompetitor(r);
  const fmap = new Map(findings.map((f) => [f.finding_id, f]));
  const sig = [...new Set((lead?.signature_findings ?? []).map((id) => fmap.get(id)).filter(Boolean).map((f) => `${claimLabel(f!.claim)} at ${subjectText(f!.subject)}`))];
  const ruledOut = (r.hypotheses ?? []).filter((h) => h.status === 'contradicted').length;
  return (
    <>
      {hyps.map((h) => <HypothesisRow key={h.hypothesis_id} h={h} max={max} leading={causeIds.has(h.hypothesis_id)} onOpen={() => onOpen(h)} />)}
      {lead && (
        <div className="why">
          <h4>Why {faultLabel(lead.fault_type)} at {lead.location} leads</h4>
          <ul className="ticks">
            {sig.length > 0 && <li><CheckCircle2 size={15} color="#4caf50" />Signature observed: {sig.slice(0, 2).join('; ')}</li>}
            <li><CheckCircle2 size={15} color="#4caf50" />Explains {lead.explained_findings.length} symptom finding{lead.explained_findings.length === 1 ? '' : 's'}
              {comp ? ` vs ${comp.explained_findings.length} for ${faultLabel(comp.fault_type)} (${HYP_LABEL[comp.status].toLowerCase()})` : ''}</li>
            <li><CheckCircle2 size={15} color="#4caf50" />{lead.independent_sources} independent source{lead.independent_sources === 1 ? '' : 's'} agree</li>
            {ruledOut > 0 && <li><XCircle size={15} color="#e5484d" />{ruledOut} alternative{ruledOut === 1 ? '' : 's'} ruled out by observed evidence</li>}
          </ul>
        </div>
      )}
    </>
  );
}

function ReportSummary({ r, facts, obs }: { r: Report; facts: RunFacts; obs: number }) {
  const diag = r.status === 'diagnosed' || r.status === 'healthy';
  const comp = leadingCompetitor(r);
  const seen = new Set<string>();
  const ev = r.supporting_evidence.filter((e) => !e.interpretation.includes('NOT observed')).filter((e) => {
    const k = `${e.metric}|${e.value}`;
    if (seen.has(k)) return false;
    seen.add(k);
    return true;
  }).slice(0, 3);
  const r1 = facts.rounds[0];
  const ch = facts.challenges[facts.challenges.length - 1];
  const out = ch?.outcomes.at(-1);
  const anomalies = facts.agents.reduce((n, x) => n + x.present.length, 0);
  return (
    <div className="stack" style={{ gap: 14 }}>
      <div className={`final-box ${diag ? '' : r.status === 'ambiguous' ? 'amb' : 'neutral'}`}>
        <span className="big-ico">{diag ? <CheckCircle2 size={24} /> : <ShieldCheck size={22} />}</span>
        <div style={{ minWidth: 0, flex: 1 }}>
          <div className="label">{diag ? 'Final diagnosis' : 'Conclusion'}</div>
          <div className="title">{verdictTitle(r)}</div>
        </div>
        <div className="chips" style={{ flexDirection: 'column', alignItems: 'flex-end' }}>
          <Chip tone={r.confidence_category === 'high_support' ? 'green' : 'amber'}>{SUPPORT_LABEL[r.confidence_category]}</Chip>
          <Confidence r={r} />
        </div>
      </div>
      <dl className="kv">
        <dt>Affected</dt><dd>{r.affected_devices.join(', ') || '—'}</dd>
        {ev.length > 0 && <><dt>Primary evidence</dt><dd className="chips">{ev.map((e) => <Chip key={e.observation_id + e.metric} tone="blue">{e.metric} = {fmtValue(e.value)}{['state', 'boolean'].includes(e.unit) ? '' : ' ' + e.unit}</Chip>)}</dd></>}
        {comp && <><dt>Alternative</dt><dd>{faultLabel(comp.fault_type)} at <span className="mono">{comp.location}</span> <Chip tone="muted">{HYP_LABEL[comp.status]}</Chip></dd></>}
      </dl>
      <div>
        <div style={{ fontWeight: 650, marginBottom: 8, fontSize: 13.5 }}>How the system got here</div>
        <ol className="story">
          <li><span>{facts.agents.filter((x) => x.state === 'done').length} specialists analysed {obs.toLocaleString()} observations in parallel and reported {anomalies} anomal{anomalies === 1 ? 'y' : 'ies'}.</span></li>
          {r1 && <li><span>{r1.status === 'ambiguous' && r1.competitors.length > 1
            ? <>STEaR found {r1.competitors.length} explanations that fit equally: {r1.competitors.map((h) => { const [f, l] = splitHyp(h); return `${faultLabel(f)} at ${l}`; }).join(' vs ')}.</>
            : <>STEaR compared {r1.hypotheses} hypotheses; the first round was {r1.status.replace(/_/g, ' ')}.</>}</span></li>}
          {ch && <li><span>It asked the {agentLabel(ch.challenge.target_agent_id)} agent for <b className="mono">{ch.challenge.requested_observation.metric}</b> of <b className="mono">{subjectText(ch.challenge.requested_observation.subject)}</b>
            {out ? `; ${out.outcome === 'obtained' ? `${out.detail.new_observation_ids?.length ?? 0} recorded observations came back` : out.outcome.replace(/_/g, ' ')}.` : '.'}</span></li>}
          <li><span>Conclusion: {verdictTitle(r)} ({SUPPORT_LABEL[r.confidence_category].toLowerCase()}{r.confidence != null ? `; calibrated confidence ${r.confidence.toFixed(2)}, from ${r.confidence_basis?.correct}/${r.confidence_basis?.n} held-out cases` : ''}).</span></li>
        </ol>
      </div>
      {r.recommended_actions.length > 0 && (
        <div>
          <div style={{ fontWeight: 650, marginBottom: 6, fontSize: 13.5 }}>Recommended actions <span className="faint" style={{ fontWeight: 500 }}>· for an operator, nothing is executed</span></div>
          <ol className="list-plain">{r.recommended_actions.slice(0, 3).map((x) => <li key={x}>{x}</li>)}</ol>
        </div>
      )}
    </div>
  );
}
