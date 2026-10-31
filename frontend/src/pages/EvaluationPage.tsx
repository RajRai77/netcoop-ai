import { useMemo, useState } from 'react';
import { FlaskConical, TriangleAlert } from 'lucide-react';
import { useEvaluation, useEvaluations } from '@/api/hooks';
import type { EvaluationCase, MethodSummary, Rate } from '@/api/types';
import { useApp } from '@/state/settings';
import { STATUS_LABEL } from '@/lib/format';
import { Chip, Empty, ErrorState, Loading, Panel } from '@/components/ui';

const METHOD: Record<string, { label: string; desc: string }> = {
  A_threshold: { label: 'Threshold', desc: 'Per-metric thresholds, no fusion' },
  B_centralized: { label: 'Centralized', desc: 'One rule engine over all data, no specialists' },
  C_stear_noverify: { label: 'STEaR, no verify', desc: 'Specialists + topology/temporal reasoning, no evidence-seeking' },
  D_full: { label: 'STEaR full', desc: 'Specialists + reasoning + targeted verification' },
  D_full_no_topology: { label: 'Full − topology', desc: 'Ablation: topology removed' },
  D_full_no_temporal: { label: 'Full − temporal', desc: 'Ablation: temporal ordering removed' },
};

const ROWS: { key: string; label: string; good: 'high' | 'low'; hint: string }[] = [
  { key: 'acceptable_outcome', label: 'Acceptable outcome', good: 'high', hint: 'Correct cause when diagnosable, or an honest abstention when not. Not root-cause accuracy.' },
  { key: 'exact_cause_on_diagnosable', label: 'Exact cause (diagnosable cases)', good: 'high', hint: 'Fault type and location both match, on cases where the data can identify the cause' },
  { key: 'localization_on_diagnosable', label: 'Localization (diagnosable)', good: 'high', hint: 'Location matches' },
  { key: 'abstained_when_not_diagnosable', label: 'Abstained when not diagnosable', good: 'high', hint: 'Said "ambiguous/insufficient" when the data cannot decide' },
  { key: 'confident_wrong_all', label: 'Confident but wrong', good: 'low', hint: 'Reported a diagnosis that does not match ground truth' },
  { key: 'high_support_wrong_all', label: 'High support but wrong', good: 'low', hint: 'The worst failure: strongest category, wrong answer' },
  { key: 'false_healthy_on_faulty', label: 'Called healthy on a faulty case', good: 'low', hint: 'Missed fault' },
  { key: 'healthy_correct', label: 'Healthy correctly', good: 'high', hint: 'No false alarm on healthy cases' },
  { key: 'multi_fault_full_recall', label: 'Multi-fault full recall', good: 'high', hint: 'All simultaneous faults found' },
];

const isRate = (v: unknown): v is Rate => !!v && typeof v === 'object' && 'count' in (v as object);

export default function EvaluationPage() {
  const list = useEvaluations();
  const preview = useApp((s) => s.preview);
  const names = list.data?.evaluations.map((e) => e.name) ?? [];
  const [picked, setPicked] = useState<string | null>(null);
  const name = picked ?? (names.includes('results-heldout-v3') ? 'results-heldout-v3' : names[names.length - 1] ?? null);
  const ev = list.data?.evaluations.find((e) => e.name === name);
  const full = useEvaluation(preview ? null : name);
  const [setKey, setSetKey] = useState<string | null>(null);
  const sets = ev ? Object.keys(ev.sets) : [];
  const sk = setKey && sets.includes(setKey) ? setKey : sets.find((s) => s.startsWith('heldout')) ?? sets[0];
  const set = ev && sk ? ev.sets[sk] : null;
  const methods = set ? Object.keys(set.summary) : [];
  const best = (key: string, good: 'high' | 'low') => {
    const vals = methods.map((m) => set!.summary[m][key]).filter(isRate).map((r) => r.count / Math.max(1, r.of));
    return vals.length ? (good === 'high' ? Math.max(...vals) : Math.min(...vals)) : null;
  };
  const failures = useMemo(() => {
    const cases = full.data?.sets[sk ?? '']?.cases;
    if (!cases) return null;
    return Object.entries(cases).flatMap(([m, cs]) => cs.filter((c) => !c.score.acceptable).map((c) => ({ ...c, method: m }))) as EvaluationCase[];
  }, [full.data, sk]);
  const [fm, setFm] = useState('D_full');

  if (list.isLoading) return <Loading />;
  if (list.isError) return <Panel><ErrorState error={list.error} /></Panel>;
  if (!ev || !set) return <Panel><Empty title="No evaluation results on this backend" /></Panel>;
  const shownFailures = (failures ?? []).filter((f) => f.method === fm);
  return (
    <>
      <div className="page-head">
        <div><h1>Evaluation</h1><p>Recorded benchmark results served by the backend. Synthetic, internally generated data.</p></div>
        <div style={{ marginLeft: 'auto', display: 'flex', gap: 8, flexWrap: 'wrap' }}>
          <select className="select" style={{ width: 240 }} value={name ?? ''} onChange={(e) => { setPicked(e.target.value); setSetKey(null); }} aria-label="Result set">
            {names.map((n) => <option key={n}>{n}</option>)}
          </select>
          {sets.length > 1 && <select className="select" style={{ width: 150 }} value={sk} onChange={(e) => setSetKey(e.target.value)} aria-label="Scenario set">{sets.map((s) => <option key={s}>{s}</option>)}</select>}
        </div>
      </div>
      <div className="mode-banner" role="note" style={{ position: 'static' }}>
        <TriangleAlert size={18} />
        <div><b>How to read this.</b> {list.data?.note} Scenarios come from the project's own generator, and the generator and engine share authors, so this is not an independent benchmark. "Acceptable outcome" counts honest abstentions as acceptable, so it is <b>not</b> root-cause accuracy. Nothing here is a calibrated probability.</div>
      </div>
      <Panel title={`${sk} · ${set.scenarios} scenarios`} icon={<FlaskConical size={19} />}
             sub={`${name} · commit ${ev.git_commit?.slice(0, 7) ?? '—'} · ${ev.knowledge?.fault_library ?? ''} · ${ev.knowledge?.detector_rules ?? ''} · knowledge frozen before generation: ${set.knowledge_frozen_before_generation == null ? 'not recorded' : set.knowledge_frozen_before_generation ? 'yes' : 'no'}`}>
        <div className="table-wrap">
          <table className="t">
            <thead><tr><th>Metric</th>{methods.map((m) => <th key={m} style={{ textAlign: 'right' }} title={METHOD[m]?.desc}>{METHOD[m]?.label ?? m}</th>)}</tr></thead>
            <tbody>
              {ROWS.filter((r) => methods.some((m) => isRate(set.summary[m][r.key]))).map((r) => {
                const b = best(r.key, r.good);
                return (
                  <tr key={r.key}>
                    <td title={r.hint}><div style={{ fontWeight: r.key === 'acceptable_outcome' ? 680 : 520 }}>{r.label}</div><div className="faint" style={{ fontSize: 12 }}>{r.hint}</div></td>
                    {methods.map((m) => {
                      const v = set.summary[m][r.key];
                      if (!isRate(v)) return <td key={m} className="faint" style={{ textAlign: 'right' }}>—</td>;
                      const top = b != null && v.of > 0 && v.count / v.of === b;
                      return <td key={m} className="mono" style={{ textAlign: 'right', color: top ? (r.good === 'high' ? 'var(--green)' : 'var(--cyan)') : undefined, fontWeight: top ? 700 : 500 }}>{v.count}/{v.of}</td>;
                    })}
                  </tr>
                );
              })}
              <tr><td><div>Verification checks obtained / requested</div><div className="faint" style={{ fontSize: 12 }}>Recorded observations returned by agents</div></td>
                {methods.map((m) => <td key={m} className="mono" style={{ textAlign: 'right' }}>{num(set.summary[m], 'checks_obtained_total')}/{num(set.summary[m], 'checks_requested_total')}</td>)}</tr>
              <tr><td><div>Median / max seconds per case</div><div className="faint" style={{ fontSize: 12 }}>Platform: {ev.platform ?? '—'}</div></td>
                {methods.map((m) => <td key={m} className="mono" style={{ textAlign: 'right' }}>{num(set.summary[m], 'seconds_median')} / {num(set.summary[m], 'seconds_max')}</td>)}</tr>
            </tbody>
          </table>
        </div>
        <div className="panel-sub" style={{ marginTop: 10 }}>Transport: {ev.transport ?? '—'}. Best value per row highlighted.</div>
      </Panel>
      <Panel title="Cases without an acceptable outcome" icon={<TriangleAlert size={19} />}
             sub={preview ? 'Per-case results are not part of the recorded preview' : failures ? `${shownFailures.length} for ${METHOD[fm]?.label ?? fm}` : undefined}
             actions={!preview && <select className="select" style={{ width: 200 }} value={fm} onChange={(e) => setFm(e.target.value)} aria-label="Method">{methods.map((m) => <option key={m} value={m}>{METHOD[m]?.label ?? m}</option>)}</select>}>
        {preview ? <Empty title="Connect to a backend to list per-case results" /> : full.isLoading ? <Loading /> : full.isError ? <ErrorState error={full.error} /> :
          shownFailures.length === 0 ? <Empty title="Every case had an acceptable outcome for this method" /> : (
            <div className="table-wrap" style={{ maxHeight: 420 }}>
              <table className="t">
                <thead><tr><th>Scenario</th><th>Ground truth</th><th>Reported</th><th>Status</th><th>Category</th><th>Diagnosable</th></tr></thead>
                <tbody>{shownFailures.map((c) => (
                  <tr key={c.scenario_id}>
                    <td className="mono">{c.scenario_id}{c.unmodeled && <> <Chip tone="violet" title="Fault type not in the fault library">unmodeled</Chip></>}</td>
                    <td className="mono">{c.truth.map(([f, l]) => `${f} @ ${l}`).join('; ') || 'healthy'}</td>
                    <td className="mono">{c.causes.map(([f, l]) => `${f} @ ${l}`).join('; ') || '—'}</td>
                    <td>{STATUS_LABEL[c.status] ?? c.status}</td>
                    <td>{c.category}</td>
                    <td>{c.score.diagnosable ? 'yes' : 'no'}</td>
                  </tr>
                ))}</tbody>
              </table>
            </div>
          )}
      </Panel>
    </>
  );
}

function num(s: MethodSummary, k: string) {
  const v = s[k];
  return typeof v === 'number' ? v : '—';
}
