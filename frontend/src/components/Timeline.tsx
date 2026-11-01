import { useMemo, useState } from 'react';
import type { Attempt, ChallengeRecord, Timeline, WorkflowEvent } from '@/api/types';
import { AGENT_TONE, agentLabel, claimLabel, faultLabel, STATE_LABEL, subjectText, timeOf, type Tone } from '@/lib/format';
import { Drawer, Json, toneVar } from './ui';
import { apiGet } from '@/api/client';

export type TlKind = 'STATE' | 'FINDINGS' | 'HYPOTHESES' | 'QUERY' | 'RESPONSE' | 'FAILED' | 'CONCLUSION';
export interface TlItem {
  key: string;
  at: string;
  from: string;
  to?: string;
  kind: TlKind;
  title: string;
  body?: string;
  mono?: string;
  tone: Tone;
  raw: { type: 'event'; value: WorkflowEvent } | { type: 'attempt'; value: Attempt } | { type: 'challenge'; value: ChallengeRecord };
}

const KIND_TONE: Record<TlKind, Tone> = {
  STATE: 'blue', FINDINGS: 'cyan', HYPOTHESES: 'violet', QUERY: 'magenta', RESPONSE: 'green', FAILED: 'red', CONCLUSION: 'green',
};

const shortHyp = (h: string) => {
  const m = /^H-([A-Z_]+)-(.+)$/.exec(h);
  return m ? `${faultLabel(m[1])} @ ${m[2]}` : h;
};

/** Builds timeline items strictly from persisted backend records (events, A2A attempts, challenges). */
export function buildTimeline(t: Timeline, runId?: string | null): TlItem[] {
  const items: TlItem[] = [];
  const inRun = <T extends { run_id: string }>(x: T) => !runId || x.run_id === runId;
  for (const e of t.events.filter(inRun)) {
    const d = e.detail as Record<string, unknown>;
    if (e.state === 'VALIDATING') {
      items.push({ key: `e${e.seq}`, at: e.at, from: 'coordinator', kind: 'STATE', tone: 'blue', raw: { type: 'event', value: e },
        title: 'Evidence validated',
        body: `${d.observations ?? 0} observations · ${d.passed ?? 0} passed · ${d.quarantined ?? 0} quarantined · ${d.stale ?? 0} stale · ${d.rejected_issues ?? 0} rejections` });
    } else if (e.state === 'DISCOVERING') {
      const av = (d.available as string[]) ?? [];
      const un = Object.keys((d.unavailable as Record<string, string>) ?? {});
      items.push({ key: `e${e.seq}`, at: e.at, from: 'coordinator', kind: un.length ? 'FAILED' : 'STATE', tone: un.length ? 'red' : 'blue',
        raw: { type: 'event', value: e }, title: 'A2A agent discovery',
        body: `${av.length} available${un.length ? ` · unavailable: ${un.map(agentLabel).join(', ')}` : ''}`, mono: av.map(agentLabel).join(' · ') });
    } else if (e.state === 'CORRELATING') {
      const comp = (d.competitors as string[]) ?? [];
      const causes = (d.causes as string[]) ?? [];
      items.push({ key: `e${e.seq}`, at: e.at, from: 'coordinator', kind: 'HYPOTHESES', tone: 'violet', raw: { type: 'event', value: e },
        title: `STEaR round ${d.round}: ${String(d.status).replace(/_/g, ' ')}`,
        body: causes.length ? `Leading: ${causes.map(shortHyp).join(' + ')}` : d.leader ? `Leading candidate: ${shortHyp(String(d.leader))}` : 'No surviving explanation',
        mono: `${d.hypotheses} hypotheses · ${d.present_symptoms} symptoms · ${comp.length} competing` });
    } else if (['DIAGNOSED', 'AMBIGUOUS', 'INSUFFICIENT_EVIDENCE', 'UNKNOWN_FAULT', 'HEALTHY', 'OPERATIONAL_ERROR'].includes(e.state)) {
      items.push({ key: `e${e.seq}`, at: e.at, from: 'coordinator', kind: e.state === 'OPERATIONAL_ERROR' ? 'FAILED' : 'CONCLUSION',
        tone: e.state === 'OPERATIONAL_ERROR' ? 'red' : 'green', raw: { type: 'event', value: e },
        title: `${STATE_LABEL[e.state]}${d.revision ? ` · report revision ${d.revision}` : ''}`,
        body: d.suspected_root_cause ? String(d.suspected_root_cause) : (d.error as string) ?? undefined,
        mono: d.confidence_category ? String(d.confidence_category).replace(/_/g, ' ') : undefined });
    } else if (e.state === 'INTERRUPTED') {
      items.push({ key: `e${e.seq}`, at: e.at, from: 'coordinator', kind: 'FAILED', tone: 'amber', raw: { type: 'event', value: e },
        title: 'Run interrupted', body: String(d.reason ?? '') });
    }
  }
  for (const a of t.attempts.filter(inRun)) {
    if (a.task_type !== 'investigate') continue;
    const ok = a.outcome === 'completed';
    const stored = a.detail.findings_stored?.length ?? 0;
    const same = a.detail.findings_unchanged?.length ?? 0;
    items.push({ key: a.attempt_id, at: a.finished_at, from: a.agent_id, to: 'coordinator', kind: ok ? 'FINDINGS' : 'FAILED',
      tone: ok ? AGENT_TONE[a.agent_id] ?? 'cyan' : 'red', raw: { type: 'attempt', value: a },
      title: ok ? `${stored} new finding${stored === 1 ? '' : 's'}${same ? ` · ${same} unchanged` : ''}` : `Task ${a.outcome}`,
      body: ok ? undefined : a.detail.error ?? undefined,
      mono: `${a.transport.toUpperCase()} task ${a.detail.a2a_task_id?.slice(0, 8) ?? '—'} · attempt ${a.attempt_no}` });
  }
  for (const c of t.challenges.filter(inRun)) {
    const ro = c.challenge.requested_observation;
    items.push({ key: `q-${c.challenge.challenge_id}`, at: c.created_at, from: 'coordinator', to: c.challenge.target_agent_id, kind: 'QUERY',
      tone: 'magenta', raw: { type: 'challenge', value: c },
      title: `Requests ${ro.metric} for ${subjectText(ro.subject)}`,
      body: `To decide: ${c.challenge.hypothesis_ids.map(shortHyp).join(' vs ')}`, mono: c.challenge.authorization_scope });
    const o = c.outcomes[c.outcomes.length - 1];
    if (o) {
      const n = o.detail.new_observation_ids?.length ?? 0;
      items.push({ key: `r-${c.challenge.challenge_id}-${o.at}`, at: o.at, from: c.challenge.target_agent_id, to: 'coordinator',
        kind: o.outcome === 'obtained' ? 'RESPONSE' : 'FAILED', tone: o.outcome === 'obtained' ? 'green' : 'amber', raw: { type: 'challenge', value: c },
        title: o.outcome === 'obtained' ? `Returned ${n} recorded observation${n === 1 ? '' : 's'}` : `Check ${o.outcome.replace(/_/g, ' ')}`,
        body: o.detail.claim ? `Evidence for: ${claimLabel(String(o.detail.claim))}` : undefined,
        mono: o.detail.note ? String(o.detail.note).slice(0, 120) : undefined });
    }
  }
  return items.sort((x, y) => x.at.localeCompare(y.at) || x.key.localeCompare(y.key));
}

export function TimelineList({ items, incidentId, emptyText = 'No activity recorded yet.' }: { items: TlItem[]; incidentId: string; emptyText?: string }) {
  const [open, setOpen] = useState<TlItem | null>(null);
  const [full, setFull] = useState<unknown>(null);
  const show = async (it: TlItem) => {
    setOpen(it);
    setFull(null);
    if (it.raw.type === 'attempt') {
      try {
        setFull(await apiGet(`/api/incidents/${incidentId}/attempts/${it.raw.value.attempt_id}`));
      } catch {
        setFull(it.raw.value);
      }
    } else setFull(it.raw.value);
  };
  const artifact = useMemo(() => {
    const d = (full as Attempt | null)?.detail;
    if (!d?.response_text) return null;
    try {
      return JSON.parse(d.response_text);
    } catch {
      return d.response_text;
    }
  }, [full]);
  if (!items.length) return <div className="state">{emptyText}</div>;
  return (
    <>
      <div className="tl" role="list">
        {items.map((it) => (
          <div className="tl-item" key={it.key} role="listitem">
            <div className="tl-time">{timeOf(it.at)}</div>
            <div className="tl-node" style={{ background: toneVar(it.tone) }} />
            <button className={`tl-card ${it.kind === 'CONCLUSION' ? 'conclusion' : ''}`} onClick={() => show(it)} style={{ textAlign: 'left', color: 'inherit', font: 'inherit' }}>
              <div className="tl-head">
                <span className="from" style={{ color: toneVar(AGENT_TONE[it.from] ?? 'blue') }}>{agentLabel(it.from)}</span>
                {it.to && <><span className="faint">→</span><span className="muted">{agentLabel(it.to)}</span></>}
                <span className="tl-kind" style={{ color: toneVar(KIND_TONE[it.kind]), borderColor: toneVar(KIND_TONE[it.kind]) }}>{it.kind}</span>
              </div>
              <div style={{ fontWeight: 560, marginTop: 3, fontSize: 14 }}>{it.title}</div>
              {(it.body || it.mono) && (
                <div className="tl-body">
                  {it.body && <div>{it.body}</div>}
                  {it.mono && <div className="mono">{it.mono}</div>}
                </div>
              )}
            </button>
          </div>
        ))}
      </div>
      <Drawer open={!!open} onClose={() => setOpen(null)} title={open?.title ?? ''}
              sub={open && `${agentLabel(open.from)}${open.to ? ` → ${agentLabel(open.to)}` : ''} · ${timeOf(open.at)} · persisted ${open.raw.type}`}>
        {artifact != null && (
          <>
            <div className="panel-sub" style={{ margin: '4px 0 8px' }}>NDEP AgentResult artifact exactly as returned over A2A</div>
            <Json value={artifact} />
            <div className="panel-sub" style={{ margin: '14px 0 8px' }}>Attempt record</div>
          </>
        )}
        {full ? <Json value={artifact != null ? { ...(full as Attempt), detail: { ...(full as Attempt).detail, response_text: '(shown above)' } } : full} /> : <div className="state">Loading…</div>}
      </Drawer>
    </>
  );
}
