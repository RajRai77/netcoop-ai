import { useMemo, useState } from 'react';
import { BrainCircuit, SearchCheck } from 'lucide-react';
import type { Hypothesis, HypothesisStatus } from '@/api/types';
import { agentLabel, claimLabel, faultLabel, HYP_LABEL, HYP_TONE, subjectText } from '@/lib/format';
import { Chip, Empty, ErrorState, Loading, Panel, Tabs } from '@/components/ui';
import { HypothesisDrawer, HypothesisRow, verdictTitle } from '@/components/Reasoning';
import { runFacts, splitHyp } from '@/lib/run';
import { useActive } from './useActive';

export default function ReasoningPage() {
  const a = useActive();
  const r = a.report.data;
  const [filter, setFilter] = useState<'all' | HypothesisStatus>('all');
  const [q, setQ] = useState('');
  const [open, setOpen] = useState<Hypothesis | null>(null);
  const hyps = useMemo(() => (r?.hypotheses ?? []).filter((h) =>
    (filter === 'all' || h.status === filter) &&
    (!q || `${h.fault_type} ${h.location} ${faultLabel(h.fault_type)}`.toLowerCase().includes(q.toLowerCase()))), [r, filter, q]);
  const max = Math.max(1, ...(r?.hypotheses ?? []).map((h) => h.explained_findings.length));
  const causeIds = new Set((r?.root_causes ?? []).map((c) => c.hypothesis_id));
  const counts = (s: HypothesisStatus) => (r?.hypotheses ?? []).filter((h) => h.status === s).length;
  const facts = useMemo(() => runFacts(a.timeline.data, a.runId, a.findings.data?.findings, a.running), [a.timeline.data, a.runId, a.findings.data, a.running]);

  if (!a.id) return <Panel><Empty title="No active incident" /></Panel>;
  if (a.report.isLoading) return <Loading />;
  if (!a.hasReport || !r) return <Panel><Empty title={a.running ? 'Reasoning in progress' : 'No report yet'}>Hypotheses are written with each report revision.</Empty></Panel>;
  if (a.report.isError) return <Panel><ErrorState error={a.report.error} /></Panel>;
  const v = r.verification;
  return (
    <>
      <div className="page-head">
        <div><h1>STEaR reasoning</h1><p>Spatio-temporal, topology-constrained comparison of competing explanations · revision {r.revision} · {r.engine_version}</p></div>
      </div>
      <div className="row secondary">
        <Panel title="Decision basis" icon={<BrainCircuit size={19} />} sub={verdictTitle(r)}>
          <ul className="list-plain">{(r.decision_basis ?? []).map((b) => <li key={b}>{b}</li>)}</ul>
          {(r.unexplained_symptoms?.length ?? 0) > 0 && <div className="panel-sub" style={{ marginTop: 10 }}>{r.unexplained_symptoms!.length} symptom finding(s) remain unexplained.</div>}
          <div style={{ marginTop: 14, fontWeight: 620 }}>Ranking rule</div>
          <p className="muted" style={{ margin: '4px 0 0', fontSize: 13.5 }}>
            Confirmed signature › more symptoms explained › more independent sources › fewer missing discriminators ›
            fewer temporal issues › more specific location. The order is lexicographic; there are no probabilities.
          </p>
          <div style={{ marginTop: 14, fontWeight: 620 }}>Alternatives considered</div>
          <ul className="list-plain">{r.alternative_causes.map((x) => <li key={x}>{x}</li>)}</ul>
        </Panel>
        <Panel title="Targeted verification" icon={<SearchCheck size={19} />}
               sub={v?.enabled ? `${v.challenges.length} check(s) · ${v.rounds ?? 0} round(s) · budget ${v.checks_used ?? 0}/${v.budget ?? '—'} · stopped: ${v.stopped_because ?? '—'}` : 'Verification disabled for this run'}>
          {!v?.challenges.length ? <Empty title="No verification challenge was needed or possible" /> : v.challenges.map((c) => (
            <div key={c.challenge_id} className="hyp" style={{ gridTemplateColumns: '1fr auto', cursor: 'default' }}>
              <div>
                <div className="hyp-name">{agentLabel(c.target_agent_id)} · {c.metric} for <span className="mono">{subjectText(c.subject)}</span></div>
                <div className="panel-sub">Decides {claimLabel(c.claim)} for {c.decides.join(', ')}</div>
                <div className="panel-sub">{c.note}</div>
              </div>
              <div style={{ textAlign: 'right' }}>
                <Chip tone={c.outcome === 'obtained' ? 'green' : 'amber'}>{c.outcome.replace(/_/g, ' ')}</Chip>
                <div className="panel-sub">{c.new_observation_ids.length} new observation(s)</div>
              </div>
            </div>
          ))}
          {facts.rounds.length > 0 && (
            <div style={{ marginTop: 16 }}>
              <div style={{ fontWeight: 650, marginBottom: 8 }}>What changed, round by round</div>
              <ol className="story">
                {facts.rounds.map((rd, i) => {
                  const chBefore = facts.challenges.filter((c) => c.created_at > rd.at && (!facts.rounds[i + 1] || c.created_at < facts.rounds[i + 1].at));
                  return (
                    <li key={rd.at}><span>
                      <b>Round {rd.round + 1}: {rd.status.replace(/_/g, ' ')}</b> · {rd.hypotheses} hypotheses · {rd.competitors.length} still competing
                      {rd.status === 'ambiguous' && rd.competitors.length > 1 && <div className="panel-sub">Tied: {rd.competitors.map((h) => { const [f, l] = splitHyp(h); return `${faultLabel(f)} at ${l}`; }).join(' vs ')}</div>}
                      {rd.causes.length > 0 && <div className="panel-sub">Selected: {rd.causes.map((h) => { const [f, l] = splitHyp(h); return `${faultLabel(f)} at ${l}`; }).join(' + ')}</div>}
                      {chBefore.map((c) => (
                        <div key={c.challenge.challenge_id} className="panel-sub">→ asked {agentLabel(c.challenge.target_agent_id)} for {c.challenge.requested_observation.metric} of {subjectText(c.challenge.requested_observation.subject)}:
                          {' '}{c.outcomes.at(-1)?.outcome.replace(/_/g, ' ') ?? 'pending'}{c.outcomes.at(-1)?.detail.new_observation_ids?.length ? ` (${c.outcomes.at(-1)!.detail.new_observation_ids!.length} observations)` : ''}</div>
                      ))}
                    </span></li>
                  );
                })}
              </ol>
            </div>
          )}
        </Panel>
      </div>
      <Panel title="All hypotheses" icon={<BrainCircuit size={19} />} sub={`${hyps.length} shown · top 40 stored per report revision`}
             actions={<>
               <input className="input" style={{ width: 220 }} placeholder="Filter fault or location…" value={q} onChange={(e) => setQ(e.target.value)} aria-label="Filter hypotheses" />
               <Tabs value={filter} onChange={setFilter} items={[
                 { id: 'all', label: `All (${r.hypotheses?.length ?? 0})` },
                 { id: 'confirmed', label: `${HYP_LABEL.confirmed} (${counts('confirmed')})` },
                 { id: 'plausible', label: `${HYP_LABEL.plausible} (${counts('plausible')})` },
                 { id: 'contradicted', label: `${HYP_LABEL.contradicted} (${counts('contradicted')})` },
               ]} />
             </>}>
        {hyps.length === 0 ? <Empty title="No hypotheses match" /> : (
          <div className="cols-2" style={{ gap: 8 }}>
            {hyps.map((h) => <HypothesisRow key={h.hypothesis_id} h={h} max={max} leading={causeIds.has(h.hypothesis_id)} onOpen={() => setOpen(h)} />)}
          </div>
        )}
        <div className="chips" style={{ marginTop: 12 }}>
          {(['confirmed', 'plausible', 'contradicted'] as HypothesisStatus[]).map((s) => <Chip key={s} tone={HYP_TONE[s]}>{HYP_LABEL[s]}: {s === 'confirmed' ? 'signature observed' : s === 'plausible' ? 'fits, signature not observed' : 'contradicted by observed evidence'}</Chip>)}
        </div>
      </Panel>
      <HypothesisDrawer h={open} findings={a.findings.data?.findings} onClose={() => setOpen(null)} />
    </>
  );
}
