import { useEffect, useRef, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { useApp } from '@/state/settings';
import { apiGet, apiSend } from './client';
import { openIncidentStream, type StreamEvent } from './sse';
import type {
  AgentInfo, CreateIncidentResponse, EvaluationFull, EvaluationSummary, EvidenceResponse, Finding, IncidentDetail,
  IncidentListItem, IngestionReport, Meta, Report, Scenario, SourceProfile, Timeline, TopologySnapshot,
} from './types';

const mode = () => (useApp.getState().preview ? 'preview' : 'live');

export const qk = {
  meta: () => [mode(), 'meta'] as const,
  agents: () => [mode(), 'agents'] as const,
  scenarios: () => [mode(), 'scenarios'] as const,
  profiles: () => [mode(), 'profiles'] as const,
  incidents: () => [mode(), 'incidents'] as const,
  incident: (id: string) => [mode(), 'incident', id] as const,
  timeline: (id: string) => [mode(), 'timeline', id] as const,
  topology: (id: string) => [mode(), 'topology', id] as const,
  findings: (id: string, all: boolean) => [mode(), 'findings', id, all] as const,
  evidence: (id: string) => [mode(), 'evidence', id] as const,
  report: (id: string, rev?: number | null) => [mode(), 'report', id, rev ?? 'latest'] as const,
  evaluations: () => [mode(), 'evaluations'] as const,
  evaluation: (name: string) => [mode(), 'evaluation', name] as const,
};

export function useHealth() {
  const preview = useApp((s) => s.preview);
  const apiBase = useApp((s) => s.apiBase);
  return useQuery({
    queryKey: [preview ? 'preview' : 'live', 'health', apiBase],
    queryFn: () => apiGet<{ status: string; version: string; checks?: Record<string, { ok: boolean; detail: string }> }>('/health/ready'),
    refetchInterval: 15000,
    retry: false,
  });
}

export const useMeta = () => useQuery({ queryKey: qk.meta(), queryFn: () => apiGet<Meta>('/api/meta'), retry: false });
export const useAgents = () =>
  useQuery({ queryKey: qk.agents(), queryFn: () => apiGet<{ agents: AgentInfo[] }>('/api/agents'), refetchInterval: 20000, retry: false });
export const useScenarios = () => useQuery({ queryKey: qk.scenarios(), queryFn: () => apiGet<{ scenarios: Scenario[] }>('/api/scenarios') });
export const useProfiles = () => useQuery({ queryKey: qk.profiles(), queryFn: () => apiGet<{ profiles: SourceProfile[] }>('/api/profiles') });
export const useIncidents = () =>
  useQuery({ queryKey: qk.incidents(), queryFn: () => apiGet<{ incidents: IncidentListItem[] }>('/api/incidents'), refetchInterval: 10000 });

export function useIncident(id: string | null) {
  return useQuery({
    queryKey: qk.incident(id ?? ''),
    queryFn: () => apiGet<IncidentDetail>(`/api/incidents/${id}`),
    enabled: !!id,
    // the SSE stream drives refreshes while running; this is a safety net
    refetchInterval: (q) => (q.state.data?.running ? 4000 : false),
  });
}
export const useTimeline = (id: string | null) =>
  useQuery({ queryKey: qk.timeline(id ?? ''), queryFn: () => apiGet<Timeline>(`/api/incidents/${id}/timeline`), enabled: !!id });
export const useTopology = (id: string | null) =>
  useQuery({ queryKey: qk.topology(id ?? ''), queryFn: () => apiGet<{ topology: TopologySnapshot | null }>(`/api/incidents/${id}/topology`), enabled: !!id });
export const useFindings = (id: string | null, all = false) =>
  useQuery({
    queryKey: qk.findings(id ?? '', all),
    queryFn: () => apiGet<{ findings: Finding[] }>(`/api/incidents/${id}/findings${all ? '?all_revisions=true' : ''}`),
    enabled: !!id,
  });
export const useEvidence = (id: string | null) =>
  useQuery({ queryKey: qk.evidence(id ?? ''), queryFn: () => apiGet<EvidenceResponse>(`/api/incidents/${id}/evidence?limit=2000`), enabled: !!id });

export function useReport(id: string | null, revision?: number | null, hasReport = true) {
  return useQuery({
    queryKey: qk.report(id ?? '', revision),
    queryFn: () => apiGet<Report>(`/api/incidents/${id}/report${revision ? `?revision=${revision}` : ''}`),
    enabled: !!id && hasReport,
    retry: false,
  });
}

export const useEvaluations = () => useQuery({ queryKey: qk.evaluations(), queryFn: () => apiGet<{ evaluations: EvaluationSummary[]; note: string }>('/api/evaluations') });
export const useEvaluation = (name: string | null) =>
  useQuery({ queryKey: qk.evaluation(name ?? ''), queryFn: () => apiGet<EvaluationFull>(`/api/evaluations/${name}`), enabled: !!name });

// -- mutations ------------------------------------------------------------------------------

export function useCreateFromScenario() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (scenarioId: string) => apiSend<CreateIncidentResponse>('/api/incidents', { scenario_id: scenarioId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.incidents() }),
  });
}

export function useCreateIncident() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: (body: { data_mode: string; title?: string; topology?: unknown; reference_time?: string }) =>
      apiSend<CreateIncidentResponse>('/api/incidents', body),
    onSuccess: () => qc.invalidateQueries({ queryKey: qk.incidents() }),
  });
}

export function useUploadTelemetry() {
  return useMutation({
    mutationFn: ({ id, text, profile }: { id: string; text: string; profile?: string }) =>
      apiSend<IngestionReport>(`/api/incidents/${id}/telemetry${profile ? `?profile=${encodeURIComponent(profile)}` : ''}`, text,
        profile ? 'text/csv' : 'application/json'),
  });
}

export function useUploadArchive() {
  return useMutation({
    mutationFn: ({ id, text }: { id: string; text: string }) =>
      apiSend<{ archive_ref: string; batches: number }>(`/api/incidents/${id}/archive`, text),
  });
}

export function useDiagnose() {
  const qc = useQueryClient();
  return useMutation({
    mutationFn: ({ id, verification }: { id: string; verification: boolean }) =>
      apiSend<{ incident_id: string; run_id: string; status: string }>(`/api/incidents/${id}/diagnose`, { verification }),
    onSuccess: (_d, v) => {
      qc.invalidateQueries({ queryKey: qk.incident(v.id) });
      qc.invalidateQueries({ queryKey: qk.incidents() });
    },
  });
}

// -- live stream ------------------------------------------------------------------------------

export type StreamStatus = 'idle' | 'connecting' | 'open' | 'reconnecting' | 'ended' | 'error';

/** Subscribes to the incident's SSE stream while a run is in progress and refreshes the
 * affected queries on every REAL backend event. Returns the stream status and the events seen. */
export function useIncidentStream(id: string | null, running: boolean) {
  const qc = useQueryClient();
  const preview = useApp((s) => s.preview);
  const [status, setStatus] = useState<StreamStatus>('idle');
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const idRef = useRef(id);
  useEffect(() => {
    idRef.current = id;
    setEvents([]);
  }, [id]);
  useEffect(() => {
    if (!id || !running || preview) {
      setStatus('idle');
      return;
    }
    const h = openIncidentStream(
      id,
      (e) => {
        if (idRef.current !== id) return;
        setEvents((xs) => [...xs.slice(-200), e]);
        qc.invalidateQueries({ queryKey: qk.timeline(id) });
        if (e.type === 'workflow' || e.type === 'end') qc.invalidateQueries({ queryKey: qk.incident(id) });
        if (e.type === 'challenge') {
          qc.invalidateQueries({ queryKey: qk.evidence(id) });
          qc.invalidateQueries({ queryKey: qk.findings(id, false) });
        }
        if (e.type === 'report' || e.type === 'end') {
          qc.invalidateQueries({ queryKey: [mode(), 'report', id] });
          qc.invalidateQueries({ queryKey: qk.findings(id, false) });
          qc.invalidateQueries({ queryKey: qk.incidents() });
        }
      },
      setStatus,
    );
    return () => h.close();
  }, [id, running, preview, qc]);
  return { status, events };
}
