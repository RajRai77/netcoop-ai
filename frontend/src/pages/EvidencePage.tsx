import { useMemo, useState } from 'react';
import { Database } from 'lucide-react';
import { apiGet } from '@/api/client';
import { useEvidence } from '@/api/hooks';
import type { Observation, RawRecord } from '@/api/types';
import { fmtValue, subjectText, timeOf } from '@/lib/format';
import { Chip, Drawer, Empty, ErrorState, Json, Loading, Panel, Tabs } from '@/components/ui';
import { useActive } from './useActive';

type Tab = 'observations' | 'issues' | 'rates';
// rejected and quarantined records first; warnings (e.g. stale samples) after
const SEV_ORDER: Record<string, number> = { reject: 0, quarantine: 1, warning: 2 };

export default function EvidencePage() {
  const { id } = useActive();
  const ev = useEvidence(id);
  const [tab, setTab] = useState<Tab>('observations');
  const [q, setQ] = useState('');
  const [metric, setMetric] = useState('all');
  const [quality, setQuality] = useState('all');
  const [sort, setSort] = useState<'time' | 'metric'>('time');
  const [open, setOpen] = useState<Observation | null>(null);
  const [raw, setRaw] = useState<RawRecord | string | null>(null);
  const data = ev.data;
  const metrics = useMemo(() => [...new Set((data?.observations ?? []).map((o) => o.measurement.metric))].sort(), [data]);
  const rows = useMemo(() => {
    const s = q.trim().toLowerCase();
    const r = (data?.observations ?? []).filter((o) =>
      (metric === 'all' || o.measurement.metric === metric) &&
      (quality === 'all' || (quality === 'stale' ? o.quality.freshness === 'stale' : o.quality.validation === quality)) &&
      (!s || `${o.observation_id} ${subjectText(o.subject)} ${o.source.source_id} ${o.measurement.metric} ${o.raw_record_ref}`.toLowerCase().includes(s)));
    return sort === 'metric' ? [...r].sort((a, b) => a.measurement.metric.localeCompare(b.measurement.metric) || a.observed_at.localeCompare(b.observed_at)) : r;
  }, [data, q, metric, quality, sort]);
  const show = async (o: Observation) => {
    setOpen(o);
    setRaw(null);
    try {
      setRaw(await apiGet<RawRecord>(`/api/raw-records/${o.raw_record_ref}`));
    } catch (e) {
      setRaw(`Raw record not available: ${(e as Error).message}`);
    }
  };
  if (!id) return <Panel><Empty title="No active incident" /></Panel>;
  const shownRows = rows.slice(0, 500);
  return (
    <>
      <div className="page-head">
        <div><h1>Evidence explorer</h1><p>Validated observations with units, quality flags and provenance back to the immutable raw record.</p></div>
        <div style={{ marginLeft: 'auto' }}>
          <Tabs value={tab} onChange={setTab} items={[
            { id: 'observations', label: `Observations ${data ? `(${data.observations.length})` : ''}` },
            { id: 'issues', label: `Validation issues ${data ? `(${data.issues.length})` : ''}` },
            { id: 'rates', label: `Counter rates ${data ? `(${data.derived_rates.length})` : ''}` },
          ]} />
        </div>
      </div>
      <Panel title={tab === 'observations' ? 'Observations' : tab === 'issues' ? 'Validation issues' : 'Derived counter rates'} icon={<Database size={19} />}
             sub={tab === 'observations' && data ? `${rows.length} match${rows.length > 500 ? ' · first 500 shown' : ''}${data.observations.length >= 2000 ? ' · first 2000 observations loaded' : ''}` : undefined}
             actions={tab === 'observations' && <>
               <input className="input" style={{ width: 240 }} placeholder="Search id, subject, source…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Search observations" />
               <select className="select" style={{ width: 200 }} value={metric} onChange={(e) => setMetric(e.target.value)} aria-label="Metric">
                 <option value="all">All metrics</option>{metrics.map((m) => <option key={m}>{m}</option>)}
               </select>
               <select className="select" style={{ width: 150 }} value={quality} onChange={(e) => setQuality(e.target.value)} aria-label="Quality">
                 <option value="all">All quality</option><option value="passed">Passed</option><option value="quarantined">Quarantined</option><option value="stale">Stale</option>
               </select>
               <select className="select" style={{ width: 140 }} value={sort} onChange={(e) => setSort(e.target.value as typeof sort)} aria-label="Sort">
                 <option value="time">By time</option><option value="metric">By metric</option>
               </select>
             </>}>
        {ev.isLoading ? <Loading /> : ev.isError ? <ErrorState error={ev.error} /> : !data ? null : tab === 'observations' ? (
          shownRows.length === 0 ? <Empty title="No observations match" /> : (
            <div className="table-wrap" style={{ maxHeight: 'calc(100vh - 330px)' }}>
              <table className="t">
                <thead><tr><th>Observed</th><th>Subject</th><th>Metric</th><th style={{ textAlign: 'right' }}>Value</th><th>Unit</th><th>Source</th><th>Quality</th></tr></thead>
                <tbody>{shownRows.map((o) => (
                  <tr key={o.observation_id} className="click" onClick={() => show(o)}>
                    <td className="mono nowrap">{timeOf(o.observed_at)}</td>
                    <td className="mono">{subjectText(o.subject)}</td>
                    <td>{o.measurement.metric}</td>
                    <td className="mono" style={{ textAlign: 'right' }}>{fmtValue(o.measurement.value)}</td>
                    <td className="muted">{o.measurement.unit}</td>
                    <td className="muted">{o.source.source_id}</td>
                    <td><div className="chips">
                      <Chip tone={o.quality.validation === 'passed' ? 'green' : 'amber'}>{o.quality.validation}</Chip>
                      {o.quality.freshness !== 'current' && <Chip tone="amber">{o.quality.freshness}</Chip>}
                      {o.transformation_id && <Chip tone="blue" title={o.transformation_id}>converted</Chip>}
                    </div></td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )
        ) : tab === 'issues' ? (
          data.issues.length === 0 ? <Empty title="No validation issues" /> : (
            <div className="table-wrap" style={{ maxHeight: 'calc(100vh - 330px)' }}>
              <table className="t">
                <thead><tr><th>Severity</th><th>Code</th><th>Record</th><th>Message</th></tr></thead>
                <tbody>{[...data.issues].sort((x, y) => (SEV_ORDER[x.severity] ?? 3) - (SEV_ORDER[y.severity] ?? 3)).map((i, k) => (
                  <tr key={k}>
                    <td><Chip tone={i.severity === 'reject' ? 'red' : i.severity === 'quarantine' ? 'amber' : 'muted'}>{i.severity}</Chip></td>
                    <td className="mono">{i.code}</td>
                    <td className="mono faint">{i.record_index ?? '—'}{i.measurement_index != null ? `.${i.measurement_index}` : ''}</td>
                    <td>{i.message}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )
        ) : data.derived_rates.length === 0 ? <Empty title="No derived counter rates" /> : (
          <div className="table-wrap" style={{ maxHeight: 'calc(100vh - 330px)' }}>
            <table className="t">
              <thead><tr><th>Window end</th><th>Subject</th><th>Rate</th><th style={{ textAlign: 'right' }}>Value</th><th>Inputs (lineage)</th></tr></thead>
              <tbody>{data.derived_rates.map((r) => (
                <tr key={r.derived_id}>
                  <td className="mono nowrap">{timeOf(r.window_end)}</td><td className="mono">{r.subject_key}</td><td>{r.rate_metric}</td>
                  <td className="mono" style={{ textAlign: 'right' }}>{fmtValue(r.value)} {r.unit}</td>
                  <td className="mono faint" style={{ fontSize: 11.5 }}>{r.input_observation_ids.join(' → ')}</td>
                </tr>
              ))}</tbody>
            </table>
          </div>
        )}
      </Panel>
      <Drawer open={!!open} onClose={() => setOpen(null)} title={open ? `${open.measurement.metric} = ${fmtValue(open.measurement.value)} ${open.measurement.unit}` : ''}
              sub={open && `${subjectText(open.subject)} · ${open.observation_id}`}>
        {open && (
          <div className="stack" style={{ gap: 12 }}>
            <dl className="kv">
              <dt>Observed</dt><dd>{open.observed_at}</dd><dt>Ingested</dt><dd>{open.ingested_at}</dd>
              <dt>Source</dt><dd>{open.source.source_id} ({open.source.source_type}, {open.source.data_mode})</dd>
              <dt>Lineage group</dt><dd className="mono">{open.lineage_group}</dd>
              <dt>Quality flags</dt><dd>{open.quality.flags.join(', ') || '—'}</dd>
              <dt>Transformation</dt><dd className="mono">{open.transformation_id ?? 'none (value as received)'}</dd>
            </dl>
            <div style={{ fontWeight: 620 }}>Normalized observation (NDEP)</div>
            <Json value={open} />
            <div style={{ fontWeight: 620 }}>Immutable raw record</div>
            {raw === null ? <Loading /> : typeof raw === 'string' ? <div className="err">{raw}</div> : (
              <>
                <div className="panel-sub">{raw.source_schema} · content hash <span className="mono">{raw.content_hash.slice(0, 16)}…</span>{raw.batch_id ? ` · batch ${raw.batch_id}` : ''}</div>
                <Json value={(() => { try { return JSON.parse(raw.content); } catch { return raw.content; } })()} />
              </>
            )}
          </div>
        )}
      </Drawer>
    </>
  );
}
