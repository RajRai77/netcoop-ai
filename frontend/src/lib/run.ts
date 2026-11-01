import type { Attempt, ChallengeRecord, Finding, Report, Timeline, WorkflowEvent, WorkflowState } from '@/api/types';
import { TERMINAL_STATES } from '@/api/types';

export const SPECIALISTS = ['performance-agent', 'infrastructure-agent', 'connectivity-agent'] as const;

export interface Round { round: number; status: string; competitors: string[]; leader: string | null; causes: string[]; hypotheses: number; at: string }
export interface AgentRun { id: string; investigate: Attempt[]; verify: Attempt[]; present: Finding[]; checked: number; state: 'done' | 'active' | 'failed' | 'idle' }

/** Facts about the latest run, read only from persisted timeline events, A2A attempts, challenges and findings. */
export function runFacts(t: Timeline | undefined, runId: string | null, findings: Finding[] | undefined, running: boolean) {
  const inRun = <T extends { run_id: string }>(x: T) => !runId || x.run_id === runId;
  const events: WorkflowEvent[] = (t?.events ?? []).filter(inRun);
  const attempts = (t?.attempts ?? []).filter(inRun);
  const challenges: ChallengeRecord[] = (t?.challenges ?? []).filter(inRun);
  const seen = new Set(events.map((e) => e.state as WorkflowState));
  const last = events[events.length - 1];
  const terminal = events.find((e) => TERMINAL_STATES.includes(e.state as WorkflowState));
  const rounds: Round[] = events.filter((e) => e.state === 'CORRELATING').map((e) => {
    const d = e.detail as Record<string, unknown>;
    return {
      round: Number(d.round ?? 0), status: String(d.status ?? ''), competitors: (d.competitors as string[]) ?? [],
      leader: (d.leader as string) ?? null, causes: (d.causes as string[]) ?? [], hypotheses: Number(d.hypotheses ?? 0), at: e.at,
    };
  });
  const agents: AgentRun[] = SPECIALISTS.map((id) => {
    const mine = attempts.filter((a) => a.agent_id === id);
    const investigate = mine.filter((a) => a.task_type === 'investigate');
    const verify = mine.filter((a) => a.task_type === 'verify');
    const fs = (findings ?? []).filter((f) => f.agent_id === id);
    const failed = investigate.length > 0 && investigate.every((a) => a.outcome !== 'completed');
    const state = failed ? 'failed' : investigate.some((a) => a.outcome === 'completed') ? 'done' : running && seen.has('INVESTIGATING') ? 'active' : 'idle';
    return { id, investigate, verify, present: fs.filter((f) => f.polarity === 'present'), checked: fs.length, state };
  });
  const verificationObs = challenges.reduce((n, c) => n + (c.outcomes[c.outcomes.length - 1]?.detail.new_observation_ids?.length ?? 0), 0);
  const startedAt = events[0]?.at ?? null;
  const endedAt = terminal?.at ?? (running ? null : last?.at ?? null);
  return { events, attempts, challenges, seen, current: (last?.state ?? null) as WorkflowState | null, terminal, rounds, agents, verificationObs, startedAt, endedAt };
}
export type RunFacts = ReturnType<typeof runFacts>;

/** "H-DEVICE_DOWN-AP-2-1" -> ["DEVICE_DOWN", "AP-2-1"] */
export function splitHyp(h: string): [string, string] {
  const m = /^H-([A-Z_]+)-(.+)$/.exec(h);
  return m ? [m[1], m[2]] : [h, ''];
}

export function leadingCompetitor(r: Report | null | undefined) {
  if (!r?.hypotheses?.length) return null;
  const causeIds = new Set((r.root_causes ?? []).map((c) => c.hypothesis_id));
  return r.hypotheses.find((h) => !causeIds.has(h.hypothesis_id) && h.explained_findings.length > 0) ?? null;
}
