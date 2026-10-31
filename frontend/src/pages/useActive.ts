import { useMemo } from 'react';
import { useAgents, useFindings, useIncident, useIncidentStream, useReport, useTimeline, useTopology } from '@/api/hooks';
import { TERMINAL_STATES } from '@/api/types';
import { useApp } from '@/state/settings';

/** Everything the incident views need, for the active incident. All values come from the API. */
export function useActive(revision?: number | null) {
  const id = useApp((s) => s.activeIncidentId);
  const incident = useIncident(id);
  const state = incident.data?.workflow?.state ?? null;
  const running = !!incident.data?.running || (!!state && !TERMINAL_STATES.includes(state) && state !== 'INTERRUPTED');
  const stream = useIncidentStream(id, running);
  const timeline = useTimeline(id);
  const topology = useTopology(id);
  const findings = useFindings(id);
  const hasReport = (incident.data?.reports.length ?? 0) > 0;
  const report = useReport(id, revision, hasReport);
  const agents = useAgents();
  const runId = incident.data?.workflow?.run_id ?? null;
  const seenStates = useMemo(
    () => new Set((timeline.data?.events ?? []).filter((e) => !runId || e.run_id === runId).map((e) => e.state as string)),
    [timeline.data, runId],
  );
  return { id, incident, state, running, stream, timeline, topology, findings, report, hasReport, agents, runId, seenStates };
}
