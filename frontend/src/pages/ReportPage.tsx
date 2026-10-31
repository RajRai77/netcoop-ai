import { useState } from 'react';
import { Download, FileJson, FileText, ShieldCheck } from 'lucide-react';
import { apiText, errorText } from '@/api/client';
import { useApp } from '@/state/settings';
import { dateTimeOf, downloadBlob, fmtValue, STATUS_LABEL } from '@/lib/format';
import { Chip, Empty, ErrorState, Json, Loading, Panel, Tabs } from '@/components/ui';
import { ReportVerdict } from '@/components/Reasoning';
import { useActive } from './useActive';

export default function ReportPage() {
  const [rev, setRev] = useState<number | null>(null);
  const a = useActive(rev);
  const preview = useApp((s) => s.preview);
  const [view, setView] = useState<'readable' | 'json'>('readable');
  const [err, setErr] = useState<string | null>(null);
  const r = a.report.data;
  if (!a.id) return <Panel><Empty title="No active incident" /></Panel>;
  if (!a.hasReport) return <Panel><Empty title={a.running ? 'Report pending' : 'No report yet'}>Run a diagnosis to produce a report.</Empty></Panel>;
  if (a.report.isLoading) return <Loading />;
  if (a.report.isError || !r) return <Panel><ErrorState error={a.report.error} /></Panel>;
  const revisions = a.incident.data?.reports ?? [];
  const txt = async () => {
    setErr(null);
    try {
      downloadBlob(`${r.incident_id}-r${r.revision}.txt`, await apiText(`/api/incidents/${r.incident_id}/report.txt?revision=${r.revision}`), 'text/plain');
    } catch (e) {
      setErr(errorText(e));
    }
  };
  return (
    <>
      <div className="page-head">
        <div><h1>Diagnostic report</h1><p>Schema-validated NDEP report {r.schema_version} · {r.incident_id}</p></div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, flexWrap: 'wrap', alignItems: 'center' }}>
          <select className="select" style={{ width: 300 }} value={r.revision} onChange={(e) => setRev(Number(e.target.value))} aria-label="Report revision">
            {revisions.map((x) => <option key={x.revision} value={x.revision}>Revision {x.revision} · {STATUS_LABEL[x.status]} · {dateTimeOf(x.created_at)}</option>)}
          </select>
          <Tabs value={view} onChange={setView} items={[{ id: 'readable', label: 'Readable' }, { id: 'json', label: 'JSON' }]} />
          <button className="btn" onClick={() => downloadBlob(`${r.incident_id}-r${r.revision}.json`, JSON.stringify(r, null, 2), 'application/json')}><FileJson size={16} />Export JSON</button>
          <button className="btn" onClick={txt} disabled={preview} title={preview ? 'Not in the recorded preview' : undefined}><FileText size={16} />Text</button>
        </div>
      </div>
      {err && <div className="err">{err}</div>}
      {view === 'json' ? <Panel title="Raw JSON" icon={<FileJson size={19} />}><Json value={r} /></Panel> : (
        <>
          <Panel title="Conclusion" icon={<ShieldCheck size={19} />} sub={`Generated ${dateTimeOf(r.generated_at)} · data mode ${r.data_mode} · ${r.transport === 'a2a' ? 'specialists over A2A' : r.transport}`}>
            <ReportVerdict r={r} />
          </Panel>
          <div className="cols-2">
            <Panel title="Recommended actions" sub="For a human operator · nothing is executed automatically">
              <ul className="list-plain">{r.recommended_actions.map((x) => <li key={x}>{x}</li>)}</ul>
            </Panel>
            <Panel title="Limitations" sub="What this report cannot claim">
              <ul className="list-plain">{r.limitations.map((x) => <li key={x}>{x}</li>)}</ul>
            </Panel>
          </div>
          <div className="cols-2">
            <Panel title="Alternative causes"><ul className="list-plain">{r.alternative_causes.map((x) => <li key={x}>{x}</li>)}</ul></Panel>
            <Panel title="Coverage" sub="Which specialists contributed">
              <dl className="kv">
                <dt>Configured</dt><dd>{r.coverage?.agents_configured?.join(', ') ?? '—'}</dd>
                <dt>Responded</dt><dd>{r.coverage?.agents_responded?.join(', ') ?? '—'}</dd>
                <dt>Failed</dt><dd>{Object.keys(r.coverage?.agents_failed ?? {}).length ? Object.entries(r.coverage!.agents_failed!).map(([k, v]) => `${k}: ${v}`).join('; ') : 'none'}</dd>
                <dt>Snapshot</dt><dd className="mono">{r.evidence_snapshot_id}</dd>
                <dt>Topology</dt><dd className="mono">{r.topology_snapshot_id ?? 'none'}</dd>
                <dt>Knowledge</dt><dd className="mono">{Object.values(r.knowledge_versions ?? {}).join(' · ')}</dd>
              </dl>
            </Panel>
          </div>
          <Panel title={`Supporting evidence (${r.supporting_evidence.length})`} icon={<Download size={19} />} sub="Every value is a stored observation; click through in the Evidence Explorer">
            <div className="table-wrap" style={{ maxHeight: 460 }}>
              <table className="t">
                <thead><tr><th>Metric</th><th style={{ textAlign: 'right' }}>Value</th><th>Unit</th><th>Interpretation</th><th>Observation</th></tr></thead>
                <tbody>{r.supporting_evidence.map((e, i) => (
                  <tr key={i}>
                    <td>{e.metric}</td><td className="mono" style={{ textAlign: 'right' }}>{fmtValue(e.value)}</td><td className="muted">{e.unit}</td>
                    <td>{e.interpretation.includes('NOT observed') ? <Chip tone="muted">checked · not observed</Chip> : null} {e.interpretation}</td>
                    <td className="mono faint" style={{ fontSize: 11.5 }}>{e.observation_id}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          </Panel>
        </>
      )}
    </>
  );
}
