import { useMemo, useState } from 'react';
import { Bot, Users } from 'lucide-react';
import { useAgents } from '@/api/hooks';
import { AGENT_TONE, agentLabel } from '@/lib/format';
import { Chip, Empty, ErrorState, Loading, Panel, toneVar } from '@/components/ui';
import { buildTimeline, TimelineList, type TlKind } from '@/components/Timeline';
import { useActive } from './useActive';

export default function AgentsPage() {
  const agents = useAgents();
  const a = useActive();
  const [agent, setAgent] = useState('all');
  const [kind, setKind] = useState<'all' | TlKind>('all');
  const [allRuns, setAllRuns] = useState(false);
  const items = useMemo(() => (a.timeline.data ? buildTimeline(a.timeline.data, allRuns ? null : a.runId) : []), [a.timeline.data, a.runId, allRuns]);
  const shown = items.filter((i) => (agent === 'all' || i.from === agent || i.to === agent) && (kind === 'all' || i.kind === kind));
  const attempts = a.timeline.data?.attempts ?? [];
  return (
    <>
      <div className="page-head">
        <div><h1>Agent collaboration</h1><p>Specialists discovered live over A2A, and every persisted exchange of the active incident.</p></div>
      </div>
      <div className="cols-3">
        {agents.isLoading ? <Panel><Loading /></Panel> : agents.isError ? <Panel><ErrorState error={agents.error} /></Panel> :
          (agents.data?.agents ?? []).map((ag) => {
            const mine = attempts.filter((x) => x.agent_id === ag.agent_id);
            const tone = AGENT_TONE[ag.agent_id] ?? 'cyan';
            return (
              <Panel key={ag.agent_id} title={agentLabel(ag.agent_id)} icon={<Bot size={19} />} sub={ag.name}
                     actions={<Chip tone={ag.status === 'available' ? 'green' : 'red'} pip>{ag.status}</Chip>}>
                <dl className="kv">
                  <dt>Transport</dt><dd>{ag.transport.toUpperCase()} <span className="faint mono">{ag.url ?? ''}</span></dd>
                  <dt>Version</dt><dd>{ag.version ?? '—'}</dd>
                  <dt>Skills</dt><dd className="chips">{(ag.skills ?? []).map((s) => <Chip key={s} tone={tone}>{s}</Chip>)}</dd>
                  <dt>Domain</dt><dd className="mono" style={{ fontSize: 12, color: toneVar(tone) }}>{(ag.metrics ?? []).join(' · ') || ag.error}</dd>
                  <dt>This incident</dt><dd>{mine.filter((x) => x.task_type === 'investigate').length} investigate · {mine.filter((x) => x.task_type === 'verify').length} verify task(s)</dd>
                </dl>
              </Panel>
            );
          })}
      </div>
      <Panel title="Exchange timeline" icon={<Users size={19} />}
             sub={a.id ? `${shown.length} of ${items.length} items${allRuns ? ' across all runs' : ' in the latest run'}` : 'No active incident'}
             actions={<>
               <select className="select" style={{ width: 200 }} value={agent} onChange={(e) => setAgent(e.target.value)} aria-label="Filter by agent">
                 <option value="all">All agents</option><option value="coordinator">Coordinator</option>
                 {(agents.data?.agents ?? []).map((x) => <option key={x.agent_id} value={x.agent_id}>{agentLabel(x.agent_id)}</option>)}
               </select>
               <select className="select" style={{ width: 170 }} value={kind} onChange={(e) => setKind(e.target.value as typeof kind)} aria-label="Filter by type">
                 <option value="all">All types</option>
                 {(['STATE', 'FINDINGS', 'HYPOTHESES', 'QUERY', 'RESPONSE', 'FAILED', 'CONCLUSION'] as TlKind[]).map((k) => <option key={k}>{k}</option>)}
               </select>
               <label className="check"><input type="checkbox" checked={allRuns} onChange={(e) => setAllRuns(e.target.checked)} />All runs</label>
             </>}>
        {!a.id ? <Empty title="No active incident" /> : a.timeline.isLoading ? <Loading /> : a.timeline.isError ? <ErrorState error={a.timeline.error} /> : (
          <div style={{ maxHeight: 'calc(100vh - 420px)', minHeight: 320, display: 'flex' }}>
            <div style={{ flex: 1, minWidth: 0 }}><TimelineList items={shown} incidentId={a.id} /></div>
          </div>
        )}
      </Panel>
    </>
  );
}
