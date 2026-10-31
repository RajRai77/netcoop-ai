import { useMemo, useState } from 'react';
import { Network } from 'lucide-react';
import { claimLabel, faultLabel, HYP_LABEL, HYP_TONE } from '@/lib/format';
import { Chip, Empty, ErrorState, Loading, Panel } from '@/components/ui';
import { type NodeState, NODE_COLOR, NODE_LABEL, nodeStates, TopologyGraph, TopologyLegend } from '@/components/Topology';
import { useActive } from './useActive';

export default function TopologyPage() {
  const a = useActive();
  const [sel, setSel] = useState<string | null>(null);
  const [full, setFull] = useState(false);
  const topo = a.topology.data?.topology ?? null;
  const report = a.report.data ?? null;
  const fData = a.findings.data;
  const findings = useMemo(() => fData?.findings ?? [], [fData]);
  const states = useMemo(() => (topo ? nodeStates(topo, report, findings) : new Map<string, NodeState>()), [topo, report, findings]);
  const counts = useMemo(() => {
    const m = new Map();
    for (const s of states.values()) m.set(s, (m.get(s) ?? 0) + 1);
    return m;
  }, [states]);
  const node = topo?.nodes.find((n) => n.id === sel);
  const atNode = findings.filter((f) => sel && (f.subject.device_id === sel || f.subject.service_id === sel || f.subject.segment_id === sel));
  const hypsAt = (report?.hypotheses ?? []).filter((h) => sel && h.location.split(':')[0] === sel);
  const links = topo?.links.filter((l) => sel && (l.from === sel || l.to === sel)) ?? [];
  const inScope = (report?.root_causes ?? []).filter((c) => sel && (c.affected_scope ?? []).includes(sel));

  if (!a.id) return <Panel><Empty title="No active incident">Select an incident first.</Empty></Panel>;
  return (
    <>
      <div className="page-head">
        <div><h1>Network topology</h1><p>Snapshot {topo?.topology_snapshot_id ?? '—'} · node colours come from the latest report and findings.</p></div>
        <label className="check" style={{ marginLeft: 'auto' }}><input type="checkbox" checked={full} onChange={(e) => setFull(e.target.checked)} />Show every host and segment</label>
      </div>
      <div className="row primary" style={{ gridTemplateColumns: 'minmax(0, 8fr) minmax(0, 4fr)' }}>
        <Panel title="Topology graph" icon={<Network size={19} />} sub={topo ? `${topo.nodes.length} nodes · ${topo.links.length} links · ${topo.kind}` : undefined}>
          {a.topology.isLoading ? <Loading /> : a.topology.isError ? <ErrorState error={a.topology.error} /> : !topo ? <Empty title="No topology snapshot" /> : (
            <div className="topo-col" style={{ height: 'calc(100vh - 330px)', minHeight: 420 }}>
              <div className="topo-wrap"><TopologyGraph topo={topo} report={report} findings={findings} selected={sel} onSelect={setSel} compact={!full} /></div>
              <TopologyLegend counts={counts} strip />
            </div>
          )}
        </Panel>
        <Panel title={node ? node.id : 'Node details'} sub={node ? `${node.type}${node.role ? ' · ' + node.role : ''}${node.service_kind ? ' · ' + node.service_kind : ''}` : 'Select a node in the graph'}>
          {!node ? <Empty title="Nothing selected">Click a node to see the findings, hypotheses and links attached to it.</Empty> : (
            <div className="stack" style={{ gap: 14 }}>
              <div><Chip tone="muted"><span style={{ width: 8, height: 8, borderRadius: 4, background: NODE_COLOR[states.get(node.id) ?? 'healthy'] }} />{NODE_LABEL[states.get(node.id) ?? 'healthy']}</Chip></div>
              {inScope.length > 0 && <div className="muted" style={{ fontSize: 13.5 }}>Inside the impact scope of {inScope.map((c) => `${faultLabel(c.fault_type)} at ${c.location}`).join(', ')}.</div>}
              <div>
                <div style={{ fontWeight: 620, marginBottom: 6 }}>Findings at this node ({atNode.length})</div>
                {atNode.length === 0 ? <div className="faint">No specialist finding references this node.</div> : (
                  <ul className="list-plain">{atNode.map((f) => (
                    <li key={f.finding_id}><b>{claimLabel(f.claim)}</b> <Chip tone={f.polarity === 'present' ? 'amber' : f.polarity === 'absent' ? 'green' : 'muted'}>{f.polarity}</Chip>
                      <div className="faint" style={{ fontSize: 12.5 }}>{f.agent_id} · {f.observation_refs.length} observation(s){f.subject.interface_id ? ` · ${f.subject.interface_id}` : ''}</div></li>
                  ))}</ul>
                )}
              </div>
              <div>
                <div style={{ fontWeight: 620, marginBottom: 6 }}>Hypotheses located here ({hypsAt.length})</div>
                {hypsAt.length === 0 ? <div className="faint">None.</div> : (
                  <ul className="list-plain">{hypsAt.map((h) => <li key={h.hypothesis_id}>{faultLabel(h.fault_type)} <span className="mono faint">{h.location}</span> <Chip tone={HYP_TONE[h.status]}>{HYP_LABEL[h.status]}</Chip></li>)}</ul>
                )}
              </div>
              <div>
                <div style={{ fontWeight: 620, marginBottom: 6 }}>Links ({links.length})</div>
                <ul className="list-plain">{links.map((l) => <li key={l.id} className="mono" style={{ fontSize: 12.5 }}>{l.from}{l.from_interface ? `:${l.from_interface}` : ''} → {l.to} <span className="faint">({l.type})</span></li>)}</ul>
              </div>
            </div>
          )}
        </Panel>
      </div>
      {topo?.limitations.length ? <div className="panel-sub">Topology limitations: {topo.limitations.join(' · ')}</div> : null}
    </>
  );
}
