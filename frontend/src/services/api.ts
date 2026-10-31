// ============================================================
// NetCoop AI — API Service Layer
// Typed integration layer for FastAPI backend
// Switch between fixture mode and live mode via settings
// ============================================================

import type {
  AgentStatus,
  DiagnosticReport,
  EvalCaseResult,
  EvalMethodSummary,
  Finding,
  IncidentSummary,
  NormalizedObservation,
  ScenarioInfo,
  TimelineEvent,
  TopologySnapshot,
  AgentAttempt,
  Challenge,
} from '@/types';

// ---- Config ----

export function getBackendUrl(): string {
  return localStorage.getItem('netcoop_backend_url') || 'http://localhost:8000';
}

export function getApiToken(): string | null {
  return localStorage.getItem('netcoop_api_token') || null;
}

export function isFixtureMode(): boolean {
  return localStorage.getItem('netcoop_fixture_mode') !== 'false';
}

// ---- HTTP Client ----

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const url = `${getBackendUrl()}${path}`;
  const token = getApiToken();
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string> || {}),
  };
  if (token) {
    headers['Authorization'] = `Bearer ${token}`;
  }
  const res = await fetch(url, { ...options, headers });
  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: { message: res.statusText } }));
    throw new ApiError(res.status, body?.error?.message || res.statusText, body?.error?.code);
  }
  return res.json();
}

export class ApiError extends Error {
  constructor(
    public readonly status: number,
    message: string,
    public readonly code?: string,
  ) {
    super(message);
    this.name = 'ApiError';
  }
}

// ---- Health ----

export async function checkHealth(): Promise<{
  status: string;
  version: string;
  checks?: Record<string, { ok: boolean; detail: string }>;
}> {
  return request('/health/ready');
}

export async function getMeta(): Promise<{
  version: string;
  environment: string;
  metric_registry_version: string;
  detector_rules: string;
  fault_library: string;
  agent_transport: string;
  auth_required: boolean;
  max_upload_bytes: number;
}> {
  return request('/api/meta');
}

// ---- Agents ----

export async function getAgents(): Promise<{ agents: AgentStatus[] }> {
  return request('/api/agents');
}

// ---- Scenarios ----

export async function getScenarios(): Promise<{ scenarios: ScenarioInfo[] }> {
  return request('/api/scenarios');
}

// ---- Incidents ----

export async function listIncidents(limit = 50): Promise<{ incidents: IncidentSummary[] }> {
  return request(`/api/incidents?limit=${limit}`);
}

export async function getIncident(id: string): Promise<{
  incident: IncidentSummary;
  evidence_counts: Record<string, number>;
  workflow: unknown;
  running: boolean;
  reports: unknown[];
}> {
  return request(`/api/incidents/${id}`);
}

export async function createIncident(body: {
  data_mode?: string;
  title?: string;
  topology?: unknown;
  scenario_id?: string;
  reference_time?: string;
}): Promise<{ incident: IncidentSummary; ingestions: unknown[] }> {
  return request('/api/incidents', {
    method: 'POST',
    body: JSON.stringify(body),
  });
}

export async function uploadTelemetry(
  incidentId: string,
  payload: string | Uint8Array,
  profile?: string,
): Promise<unknown> {
  const url = `${getBackendUrl()}/api/incidents/${incidentId}/telemetry${profile ? `?profile=${profile}` : ''}`;
  const token = getApiToken();
  const headers: Record<string, string> = {};
  if (token) headers['Authorization'] = `Bearer ${token}`;
  const res = await fetch(url, {
    method: 'POST',
    headers,
    body: typeof payload === 'string' ? payload : payload,
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    throw new ApiError(res.status, body?.error?.message || res.statusText);
  }
  return res.json();
}

export async function startDiagnosis(
  incidentId: string,
  opts?: { verification?: boolean; max_rounds?: number; total_budget?: number },
): Promise<{ incident_id: string; run_id: string; status: string }> {
  return request(`/api/incidents/${incidentId}/diagnose`, {
    method: 'POST',
    body: JSON.stringify(opts || {}),
  });
}

// ---- Evidence ----

export async function getEvidence(
  incidentId: string,
  opts?: { limit?: number; offset?: number; metric?: string },
): Promise<{
  incident_id: string;
  limit: number;
  offset: number;
  observations: NormalizedObservation[];
  derived_rates: unknown[];
  issues: unknown[];
}> {
  const params = new URLSearchParams();
  if (opts?.limit) params.set('limit', String(opts.limit));
  if (opts?.offset) params.set('offset', String(opts.offset));
  if (opts?.metric) params.set('metric', opts.metric);
  return request(`/api/incidents/${incidentId}/evidence?${params}`);
}

export async function getFindings(
  incidentId: string,
  allRevisions?: boolean,
): Promise<{ findings: Finding[] }> {
  return request(`/api/incidents/${incidentId}/findings${allRevisions ? '?all_revisions=true' : ''}`);
}

// ---- Timeline ----

export async function getTimeline(incidentId: string): Promise<{
  events: TimelineEvent[];
  attempts: AgentAttempt[];
  challenges: Challenge[];
}> {
  return request(`/api/incidents/${incidentId}/timeline`);
}

// ---- Topology ----

export async function getTopology(incidentId: string): Promise<{ topology: TopologySnapshot | null }> {
  return request(`/api/incidents/${incidentId}/topology`);
}

// ---- Report ----

export async function getReport(
  incidentId: string,
  revision?: number,
): Promise<DiagnosticReport> {
  return request(`/api/incidents/${incidentId}/report${revision !== undefined ? `?revision=${revision}` : ''}`);
}

// ---- Profiles ----

export async function getProfiles(): Promise<{ profiles: unknown[] }> {
  return request('/api/profiles');
}

// ---- Evaluation (results are loaded from bundled fixture) ----

export async function getEvalResults(): Promise<{
  methods: Record<string, EvalMethodSummary>;
  cases: EvalCaseResult[];
  meta: {
    git_commit: string;
    platform: string;
    generated_by: string;
  };
}> {
  // Eval results are always from the frozen results file — never live
  const res = await fetch('/eval-results.json');
  return res.json();
}
