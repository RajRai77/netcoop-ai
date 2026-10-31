import { useMemo, useState } from 'react';
import { Link } from 'react-router-dom';
import { Activity, BrainCircuit, FileSearch, Network, Play, RotateCcw, Router, ShieldCheck, Users } from 'lucide-react';
import { useCreateFromScenario, useDiagnose, useScenarios } from '@/api/hooks';
import { errorText } from '@/api/client';
import type { Hypothesis } from '@/api/types';
import { useApp } from '@/state/settings';
import { dateTimeOf, durationBetween, STATUS_LABEL, SUPPORT_LABEL } from '@/lib/format';
import { Chip, Empty, ErrorState, Kpi, Lifecycle, Loading, Panel, StatusChip } from '@/components/ui';
import { buildTimeline, TimelineList } from '@/components/Timeline';
import { nodeStates, TopologyGraph, TopologyLegend } from '@/components/Topology';
import { HypothesisDrawer, HypothesisRow, pickHypotheses, ReportActions, ReportVerdict } from '@/components/Reasoning';
import { useActive } from './useActive';

function Welcome() {
  const { set, preview } = useApp();
  const scen = useScenarios();
  const create = useCreateFromScenario();
  const diagnose = useDiagnose();
  const [err, setErr] = useState<string | null>(null);
  const golden = scen.data?.scenarios.find((s) => s.scenario_id === 'S19-ap-down-status-in-archive');
  const run = async () => {
    setErr(null);
    try {
      const r = await create.mutateAsync('S19-ap-down-status-in-archive');
      await diagnose.mutateAsync({ id: r.incident.incident_id, verification: true });
      set({ activeIncidentId: r.incident.incident_id });
    } catch (e) {
      setErr(errorText(e));
    }
  };
  return (
    <section className="glass hero" style={{ gridTemplateColumns: '1fr' }}>
      <div>
        <div className="hero-title"><h1>No incident selected</h1></div>
        <p className="muted" style={{ maxWidth: 760, fontSize: 15.5 }}>
          Pick a scenario in the launcher and run a diagnosis, choose an incident from the search bar, or upload telemetry.
          Three specialist agents run as separate processes and exchange NDEP evidence over A2A; every number on this
          screen is read back from the backend's evidence ledger.
        </p>
        <div style={{ display: 'flex', gap: 10, flexWrap: 'wrap', marginTop: 14 }}>
          <button className="btn primary big" onClick={run} disabled={!golden || preview || create.isPending || diagnose.isPending}>
            <Play size={17} />Run the AP-down verification scenario (S19)
          </button>
          <Link className="btn big" to="/scenarios">Browse scenarios</Link>
          <Link className="btn big" to="/incidents">Incident history</Link>
        </div>
        {err && <div className="err" style={{ marginTop: 12 }}>{err}</div>}
      </div>
    </section>
  );
}

export function CommandCenter() {
  const a = useActive();
  const { preview } = useApp();
  const diagnose = useDiagnose();
  const [selNode, setSelNode] = useState<string | null>(null);
  const [openHyp, setOpenHyp] = useState<Hypothesis | null>(null);
  const items = useMemo(() => (a.timeline.data ? buildTimeline(a.timeline.data, a.runId) : []), [a.timeline.data, a.runId]);
  const topo = a.topology.data?.topology ?? null;
  const report = a.report.data ?? null;
  const findings = a.findings.data?.findings;
  const counts = useMemo(() => {
    const m = new Map();
    if (topo) for (const s of nodeStates(topo, report, findings).values()) m.set(s, (m.get(s) ?? 0) + 1);
    return m;
  }, [topo, report, findings]);

  if (!a.id) return <Welcome />;
  if (a.incident.isLoading) return <Loading label="Loading incident…" />;
  if (a.incident.isError) return <Panel><ErrorState error={a.incident.error} title="Incident unavailable" /></Panel>;
  const d = a.incident.data!;
  const inc = d.incident;
  const agents = a.agents.data?.agents ?? [];
  const online = agents.filter((x) => x.status === 'available').length;
  const devices = topo?.nodes.filter((n) => n.type !== 'segment').length ?? 0;
  const present = (findings ?? []).filter((f) => f.polarity === 'present').length;
  const hyps = report ? pickHypotheses(report) : [];
  const maxExpl = Math.max(1, ...hyps.map((h) => h.explained_findings.length));
  const causeIds = new Set((report?.root_causes ?? []).map((c) => c.hypothesis_id));
  const firstEvent = a.timeline.data?.events.find((e) => e.run_id === a.runId);
  const lastEvent = [...(a.timeline.data?.events ?? [])].reverse().find((e) => e.run_id === a.runId);

  return (
    <>
      <section className="glass strong hero">
        <div style={{ minWidth: 0 }}>
          <div className="hero-title">
            <h1>{inc.title ?? 'Incident'}</h1>
            <span className="hero-id">{inc.incident_id}</span>
            {report && !a.running && <StatusChip status={report.status} />}
            {a.running && <Chip tone="blue" pip>Investigation in progress</Chip>}
            {!report && !a.running && <Chip tone="muted">Not diagnosed yet</Chip>}
          </div>
          <div className="hero-meta">
            <span>Data mode <b>{inc.data_mode}</b></span>
            {inc.scenario_id && <span>Scenario <b>{inc.scenario_id}</b></span>}
            <span>Created <b>{dateTimeOf(inc.created_at)}</b></span>
            {firstEvent && lastEvent && <span>Last run <b>{durationBetween(firstEvent.at, lastEvent.at)}</b></span>}
            {report && <span>Affected <b>{report.affected_devices.join(', ') || '—'}</b></span>}
            {a.stream.status === 'open' && <span style={{ display: 'inline-flex', alignItems: 'center', gap: 6 }}><span className="live-dot" />live stream</span>}
          </div>
          <div style={{ marginTop: 14 }}>
            <Lifecycle seen={a.seenStates} current={a.state} running={a.running} />
          </div>
        </div>
        <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap', justifyContent: 'flex-end' }}>
          <button className="btn" disabled={a.running || preview || diagnose.isPending}
                  title={preview ? 'Preview mode is read-only' : 'Run the diagnosis again on the stored evidence (creates a new report revision)'}
                  onClick={() => diagnose.mutate({ id: inc.incident_id, verification: true })}>
            <RotateCcw size={16} />{d.reports.length ? 'Re-run diagnosis' : 'Run diagnosis'}
          </button>
          {report && <ReportActions r={report} />}
          {diagnose.isError && <div className="err" style={{ width: '100%' }}>{errorText(diagnose.error)}</div>}
        </div>
      </section>

      <div className="kpis">
        <Kpi icon={<Users size={24} />} value={`${online}`} unit={`/ ${agents.length || 3}`} label="Specialist agents online (A2A)"
             title={agents.map((x) => `${x.agent_id}: ${x.status}`).join('\n')} />
        <Kpi icon={<Router size={24} />} tone="violet" value={devices || '—'} label={topo ? 'Network nodes in topology' : 'No topology snapshot'}
             title={topo ? topo.topology_snapshot_id + ' (' + topo.kind + ') · excludes logical segments' : undefined} />
        <Kpi icon={<FileSearch size={24} />} tone="green" value={d.evidence_counts.findings} unit={'· ' + present + ' anomalies'}
             label={'Findings from ' + d.evidence_counts.observations.toLocaleString() + ' observations'} />
        <Kpi icon={<ShieldCheck size={24} />} tone="amber"
             value={report ? <span style={{ fontSize: 21 }}>{SUPPORT_LABEL[report.confidence_category]}</span> : a.running ? '…' : '—'}
             label={report ? `${STATUS_LABEL[report.status]} · revision ${report.revision}` : 'No report yet'}
             title="Support category from documented rules — not a probability" />
      </div>

      <div className="row primary">
        <Panel className="h-primary" title="Agent collaboration" icon={<Activity size={19} />}
               sub={a.running ? 'Updating from the live event stream' : `${items.length} recorded exchanges in the latest run`}
               actions={<Link className="btn ghost sm" to="/agents">All exchanges</Link>}>
          {a.timeline.isError ? <ErrorState error={a.timeline.error} /> : a.timeline.isLoading ? <Loading /> :
            <TimelineList items={items} incidentId={inc.incident_id} emptyText={d.reports.length ? 'No exchanges recorded.' : 'Run a diagnosis to see the agents collaborate.'} />}
        </Panel>
        <Panel className="h-primary" title="Network topology" icon={<Network size={19} />}
               sub={topo ? `${topo.nodes.length} nodes · ${topo.links.length} links · ${topo.kind} snapshot` : undefined}
               actions={<Link className="btn ghost sm" to="/topology">Explore</Link>}>
          {a.topology.isLoading ? <Loading /> : !topo ? <Empty title="No topology snapshot">Localization is limited to measured components; the report states this limitation.</Empty> : (
            <div className="topo-col">
              <div className="topo-wrap">
                <TopologyGraph topo={topo} report={report} findings={findings} selected={selNode} onSelect={setSelNode} compact />
              </div>
              <TopologyLegend counts={counts} strip />
            </div>
          )}
        </Panel>
      </div>

      <div className="row secondary">
        <Panel className="h-secondary" title="Competing hypotheses" icon={<BrainCircuit size={19} />}
               sub="STEaR ranking · bars show symptoms explained, not probability"
               actions={<Link className="btn ghost sm" to="/reasoning">Reasoning</Link>}>
          {!report ? <Empty title={a.running ? 'Correlating…' : 'No hypotheses yet'}>{a.running ? 'Hypotheses appear when the first report revision is written.' : 'Run a diagnosis.'}</Empty> :
            hyps.length === 0 ? <Empty title="No candidate explanation">{report.decision_basis?.[0]}</Empty> :
              hyps.map((h) => <HypothesisRow key={h.hypothesis_id} h={h} max={maxExpl} leading={causeIds.has(h.hypothesis_id)} onOpen={() => setOpenHyp(h)} />)}
        </Panel>
        <Panel className="h-secondary" title={report && !a.running ? 'Diagnostic conclusion' : 'Diagnostic report'} icon={<ShieldCheck size={19} />}
               sub={report ? `Revision ${report.revision} · generated ${dateTimeOf(report.generated_at)}` : undefined}>
          {a.report.isLoading ? <Loading /> : report ? (
            <>
              {a.running && <div className="mode-banner" style={{ border: '1px solid var(--border)', marginBottom: 12 }}>A new run is in progress — this is the previous revision.</div>}
              <ReportVerdict r={report} compact />
              {report.verification?.challenges.length ? (
                <div className="panel-sub" style={{ marginTop: 12 }}>
                  Verification: {report.verification.challenges.length} targeted check(s), {report.verification.challenges.filter((c) => c.outcome === 'obtained').length} returned new evidence · stopped: {report.verification.stopped_because}
                </div>
              ) : null}
              <div className="cols-2" style={{ marginTop: 14, gap: 14 }}>
                <div>
                  <div style={{ fontWeight: 620, marginBottom: 6 }}>Recommended next actions</div>
                  <ul className="list-plain">{report.recommended_actions.slice(0, 3).map((x) => <li key={x}>{x}</li>)}</ul>
                </div>
                <div>
                  <div style={{ fontWeight: 620, marginBottom: 6 }}>Limitations <span className="faint">({report.limitations.length})</span></div>
                  <ul className="list-plain">{report.limitations.slice(0, 3).map((x) => <li key={x} className="muted">{x}</li>)}</ul>
                  {report.limitations.length > 3 && <Link to="/report" className="panel-sub">All limitations →</Link>}
                </div>
              </div>
            </>
          ) : <Empty title={a.running ? 'Investigation in progress' : 'No report yet'}>{a.running ? 'The report appears when the coordinator reaches a conclusion.' : 'Run a diagnosis to produce a report.'}</Empty>}
        </Panel>
      </div>
      <HypothesisDrawer h={openHyp} findings={findings} onClose={() => setOpenHyp(null)} />
    </>
  );
}
