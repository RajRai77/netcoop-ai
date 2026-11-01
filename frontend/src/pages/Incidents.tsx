import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { ListTree } from 'lucide-react';
import { useIncidents } from '@/api/hooks';
import { useApp } from '@/state/settings';
import { dateTimeOf, STATE_LABEL, STATUS_LABEL, SUPPORT_LABEL } from '@/lib/format';
import { Chip, Empty, ErrorState, Loading, Panel, StatusChip } from '@/components/ui';
import type { ReportStatus } from '@/api/types';

export default function Incidents() {
  const q = useIncidents();
  const { set, activeIncidentId } = useApp();
  const nav = useNavigate();
  const [text, setText] = useState('');
  const [status, setStatus] = useState<'all' | ReportStatus | 'none'>('all');
  const rows = useMemo(() => {
    const s = text.trim().toLowerCase();
    return (q.data?.incidents ?? []).filter((i) =>
      (!s || `${i.incident_id} ${i.title ?? ''} ${i.scenario_id ?? ''} ${i.latest_report?.suspected_root_cause ?? ''}`.toLowerCase().includes(s)) &&
      (status === 'all' || (status === 'none' ? !i.latest_report : i.latest_report?.status === status)));
  }, [q.data, text, status]);
  return (
    <>
      <div className="page-head">
        <div><h1>Incidents</h1><p>Every incident stored in the evidence ledger, newest first. Selecting one makes it the active incident.</p></div>
      </div>
      <Panel title="Incident history" icon={<ListTree size={19} />} sub={q.data ? `${rows.length} of ${q.data.incidents.length}` : undefined}
             actions={<>
               <input className="input" style={{ width: 280 }} placeholder="Filter…" value={text} onChange={(e) => setText(e.target.value)} aria-label="Filter incidents" />
               <select className="select" style={{ width: 210 }} value={status} onChange={(e) => setStatus(e.target.value as typeof status)} aria-label="Filter by status">
                 <option value="all">All statuses</option>
                 <option value="none">Not diagnosed</option>
                 {(Object.keys(STATUS_LABEL) as ReportStatus[]).map((s) => <option key={s} value={s}>{STATUS_LABEL[s]}</option>)}
               </select>
             </>}>
        {q.isLoading ? <Loading /> : q.isError ? <ErrorState error={q.error} /> : rows.length === 0 ? <Empty title="No incidents">Create one from a scenario or an upload.</Empty> : (
          <div className="table-wrap">
            <table className="t">
              <thead><tr><th>Incident</th><th>Scenario</th><th>Data mode</th><th>Created</th><th>Workflow</th><th>Latest result</th><th>Support</th></tr></thead>
              <tbody>
                {rows.map((i) => (
                  <tr key={i.incident_id} className="click" onClick={() => { set({ activeIncidentId: i.incident_id }); nav('/command'); }}
                      style={i.incident_id === activeIncidentId ? { background: 'rgba(34,211,238,.08)' } : undefined}>
                    <td><div style={{ fontWeight: 600 }}>{i.title ?? '—'}</div><div className="mono faint">{i.incident_id}</div></td>
                    <td className="mono">{i.scenario_id ?? 'upload'}</td>
                    <td><Chip tone="muted">{i.data_mode}</Chip></td>
                    <td className="nowrap">{dateTimeOf(i.created_at)}</td>
                    <td>{i.workflow ? STATE_LABEL[i.workflow.state] ?? i.workflow.state : 'not run'}</td>
                    <td>{i.latest_report ? <div><StatusChip status={i.latest_report.status} /><div className="muted" style={{ fontSize: 12.5, marginTop: 4 }}>{i.latest_report.suspected_root_cause ?? ''}</div></div> : <span className="faint">—</span>}</td>
                    <td>{i.latest_report ? SUPPORT_LABEL[i.latest_report.confidence_category] : '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Panel>
    </>
  );
}
