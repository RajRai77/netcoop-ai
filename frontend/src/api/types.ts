// Types for the NetCoop backend API (docs/25_FRONTEND_INTEGRATION.md, docs/openapi.json,
// spec/*.schema.json). Field names match real responses recorded from the backend.

export type DataMode = 'synthetic' | 'recorded' | 'emulated' | 'live' | 'mock';
export type ReportStatus = 'diagnosed' | 'ambiguous' | 'insufficient_evidence' | 'unknown_fault' | 'healthy' | 'operational_error';
export type SupportCategory = 'high_support' | 'moderate_support' | 'ambiguous' | 'insufficient' | 'not_applicable';
export type Polarity = 'present' | 'absent' | 'unknown';
export type HypothesisStatus = 'confirmed' | 'plausible' | 'contradicted';
export type WorkflowState =
  | 'NEW' | 'VALIDATING' | 'DISCOVERING' | 'INVESTIGATING' | 'CORRELATING' | 'VERIFYING' | 'INTERRUPTED'
  | 'DIAGNOSED' | 'AMBIGUOUS' | 'INSUFFICIENT_EVIDENCE' | 'UNKNOWN_FAULT' | 'HEALTHY' | 'OPERATIONAL_ERROR';

export const TERMINAL_STATES: WorkflowState[] = [
  'DIAGNOSED', 'AMBIGUOUS', 'INSUFFICIENT_EVIDENCE', 'UNKNOWN_FAULT', 'HEALTHY', 'OPERATIONAL_ERROR',
];

export interface Meta {
  version: string;
  environment: string;
  metric_registry_version: string;
  detector_rules: string;
  fault_library: string;
  agent_transport: 'a2a' | 'in-process' | 'none';
  auth_required: boolean;
  auth_mode?: 'none' | 'token' | 'clerk';
  max_upload_bytes: number;
  uploads_archive_enabled: boolean;
}

export interface AgentInfo {
  agent_id: string;
  transport: string;
  url: string | null;
  status: 'available' | 'unavailable';
  skills?: string[];
  metrics?: string[];
  name?: string;
  version?: string;
  error?: string;
}

export interface Scenario {
  scenario_id: string;
  title: string;
  data_mode: DataMode;
  tags: string[];
  split: string | null;
  telemetry_profile: string | null;
  reference_time: string | null;
  limitations: string[];
  source_description: string;
  has_archive: boolean;
}

export interface Incident {
  incident_id: string;
  data_mode: DataMode;
  topology_snapshot_id: string | null;
  title: string | null;
  created_at: string;
  archive_ref: string | null;
  scenario_id: string | null;
  reference_time: string | null;
}

export interface WorkflowPointer { state: WorkflowState; run_id: string; at: string }

export interface IncidentListItem extends Incident {
  workflow: WorkflowPointer | null;
  latest_report: { revision: number; status: ReportStatus; suspected_root_cause: string | null; confidence_category: SupportCategory } | null;
}

export interface ReportRevision { revision: number; status: ReportStatus; created_at: string; evidence_snapshot_id: string }

export interface IncidentDetail {
  incident: Incident;
  evidence_counts: { raw_records: number; observations: number; issues: number; ingestions: number; findings: number };
  workflow: WorkflowPointer | null;
  running: boolean;
  reports: ReportRevision[];
}

export interface Subject {
  device_id?: string;
  interface_id?: string;
  service_id?: string;
  segment_id?: string;
  link_id?: string;
}

export interface Observation {
  schema_version: string;
  observation_id: string;
  incident_id: string;
  raw_record_ref: string;
  source: { source_id: string; data_mode: DataMode; source_type: string };
  subject: Subject;
  measurement: { metric: string; value: number | string | boolean; unit: string; kind: string; window?: { start: string; end: string } };
  observed_at: string;
  ingested_at: string;
  quality: { validation: 'passed' | 'quarantined' | 'rejected'; freshness: 'current' | 'stale' | 'unknown'; flags: string[] };
  lineage_group: string;
  metric_registry_version: string;
  transformation_id: string | null;
}

export interface DerivedRate {
  derived_id: string;
  subject_key: string;
  metric: string;
  rate_metric: string;
  value: number;
  unit: string;
  window_start: string;
  window_end: string;
  input_observation_ids: string[];
  lineage_groups: string[];
}

export interface StoredIssue {
  ingestion_id: string;
  raw_id: string | null;
  code: string;
  severity: 'reject' | 'quarantine' | 'warning';
  record_index: number | null;
  measurement_index: number | null;
  message: string;
}

export interface EvidenceResponse {
  incident_id: string;
  limit: number;
  offset: number;
  observations: Observation[];
  derived_rates: DerivedRate[];
  issues: StoredIssue[];
}

export interface Finding {
  schema_version: string;
  finding_id: string;
  incident_id: string;
  agent_id: string;
  claim: string;
  polarity: Polarity;
  subject: Subject;
  observation_refs: string[];
  rule_or_model_version: string;
  created_at: string;
  caveats: string[];
  supersedes_finding_id: string | null;
}

export interface WorkflowEvent {
  seq: number;
  run_id: string;
  state: WorkflowState;
  actor: string;
  at: string;
  detail: Record<string, unknown>;
}

export interface Attempt {
  attempt_id: string;
  task_id: string;
  attempt_no: number;
  incident_id: string;
  run_id: string;
  agent_id: string;
  task_type: 'discover' | 'investigate' | 'verify';
  transport: string;
  outcome: string;
  started_at: string;
  finished_at: string;
  detail: {
    a2a_task_id?: string;
    a2a_message_id?: string;
    a2a_context_id?: string;
    a2a_task_state?: number;
    a2a_artifact_ids?: string[];
    agent_url?: string;
    request_sha256?: string;
    response_sha256?: string;
    request_bytes?: number;
    findings_stored?: string[];
    findings_unchanged?: string[];
    findings_rejected?: string[];
    error?: string | null;
    response_text?: string | null;
    result?: Record<string, unknown>;
    skills?: string[] | null;
    metrics?: string[] | null;
    [k: string]: unknown;
  };
}

export interface ChallengeDoc {
  schema_version: string;
  challenge_id: string;
  incident_id: string;
  target_agent_id: string;
  hypothesis_ids: string[];
  finding_refs: string[];
  question_type: string;
  requested_observation: { metric: string; subject: Subject; window: { start: string; end: string } };
  authorization_scope: string;
  deadline_at: string;
  note?: string;
}

export interface ChallengeOutcome {
  outcome: 'obtained' | 'no_new_evidence' | 'unavailable' | 'refused' | 'failed';
  at: string;
  detail: { new_observation_ids?: string[]; note?: string | null; claim?: string; decides?: string[]; [k: string]: unknown };
}

export interface ChallengeRecord { challenge: ChallengeDoc; run_id: string; created_at: string; outcomes: ChallengeOutcome[] }

export interface Timeline { events: WorkflowEvent[]; attempts: Attempt[]; challenges: ChallengeRecord[] }

export interface TopologyNode { id: string; type: 'device' | 'service' | 'ap' | 'segment' | 'host'; role?: string; label?: string; service_kind?: string }
export interface TopologyLink { id: string; from: string; to: string; type: 'physical' | 'logical' | 'dependency' | 'routing'; directed?: boolean; from_interface?: string; to_interface?: string }
export interface TopologySnapshot {
  schema_version: string;
  topology_snapshot_id: string;
  kind: string;
  observed_at: string;
  nodes: TopologyNode[];
  links: TopologyLink[];
  limitations: string[];
}

export interface Hypothesis {
  hypothesis_id: string;
  fault_type: string;
  location: string;
  location_subject: Subject;
  status: HypothesisStatus;
  rank: number | null;
  explained_findings: string[];
  signature_findings: string[];
  contradictions: string[];
  missing_discriminators: { claim: string; subject: Subject }[];
  temporal_issues: string[];
  independent_lineage_groups: number;
  independent_sources: number;
  impact_scope: string[];
  reasons: string[];
}

export interface VerificationChallenge {
  challenge_id: string;
  target_agent_id: string;
  metric: string;
  claim: string;
  subject: Subject;
  decides: string[];
  new_observation_ids: string[];
  outcome: ChallengeOutcome['outcome'];
  note: string | null;
}

export interface ConfidenceBasis {
  method: 'empirical_heldout' | 'none';
  reason?: string;
  calibration_version?: string;
  conclusion?: string;
  n?: number;
  correct?: number;
  wilson_95?: [number, number];
  estimator?: string;
  set?: string;
  evaluation_method?: string;
  meaning?: string;
  caveats?: string[];
}
export interface Report {
  schema_version: string;
  incident_id: string;
  revision: number;
  status: ReportStatus;
  suspected_root_cause: string | null;
  /** 1.2.0: calibrated on a held-out set for this (status, category); null when no calibration applies. */
  confidence?: number | null;
  confidence_category: SupportCategory;
  confidence_basis?: ConfidenceBasis;
  affected_devices: string[];
  supporting_evidence: { observation_id: string; finding_id: string; metric: string; value: number | string | boolean; unit: string; interpretation: string }[];
  alternative_causes: string[];
  recommended_actions: string[];
  evidence_sources: string[];
  limitations: string[];
  evidence_snapshot_id: string;
  topology_snapshot_id: string | null;
  engine_version: string;
  data_mode: DataMode;
  generated_at: string;
  run_id?: string;
  transport?: 'a2a' | 'in-process';
  root_causes?: { hypothesis_id: string; fault_type: string; location: string; support: string; affected_scope?: string[] }[];
  hypotheses?: Hypothesis[];
  verification?: { enabled: boolean; rounds?: number; budget?: number; checks_used?: number; stopped_because?: string | null; challenges: VerificationChallenge[] };
  coverage?: { agents_configured?: string[]; agents_available?: string[]; agents_responded?: string[]; agents_failed?: Record<string, string>; per_agent?: Record<string, Record<string, unknown>> };
  agent_contributions?: Record<string, string[]>;
  unexplained_symptoms?: string[];
  decision_basis?: string[];
  knowledge_versions?: Record<string, string>;
  explanation?: string;
}

export interface Issue {
  code: string;
  severity: 'reject' | 'quarantine' | 'warning';
  message: string;
  record_index: number | null;
  record_id: string | null;
  measurement_index: number | null;
  path: string | null;
}

export interface IngestionReport {
  ingestion_id: string;
  incident_id: string;
  batch_id: string | null;
  received_at: string;
  metric_registry_version: string;
  counts: Record<'records' | 'accepted' | 'quarantined' | 'partially_rejected' | 'rejected' | 'duplicate' | 'conflict', number>;
  observations_added: number;
  records: { record_index: number; record_id: string | null; raw_id: string; status: string; observation_ids: string[] }[];
  issues: Issue[];
}

export interface CreateIncidentResponse { incident: Incident; ingestions: IngestionReport[] }

export interface SourceProfile { profile_id: string; version: string; description?: string; format: 'csv' | 'json-records'; source: { source_id: string; data_mode: DataMode; source_type: string } }

export interface RawRecord {
  raw_id: string; incident_id: string; content_hash: string;
  source: { source_id: string; data_mode: DataMode; source_type: string };
  source_schema: string; source_record_id: string | null; batch_id: string | null; received_at: string; content: string;
}

export interface Rate { count: number; of: number }
export type MethodSummary = Record<string, Rate | number>;
export interface EvaluationSummary {
  name: string;
  git_commit: string | null;
  knowledge: { detector_rules: string; fault_library: string; sha256?: Record<string, string> } | null;
  platform: string | null;
  transport: string | null;
  sets: Record<string, { scenarios: number; knowledge_frozen_before_generation: boolean | null; summary: Record<string, MethodSummary> }>;
}
export interface EvaluationCase {
  scenario_id: string; method: string; status: ReportStatus; category: string; causes: [string, string][];
  suspected_root_cause: string | null; seconds: number; checks_requested: number; checks_obtained: number;
  new_observations: number; truth: [string, string][]; unmodeled: boolean; score: Record<string, boolean | number | null>;
}
export interface EvaluationFull {
  git_commit: string | null;
  code?: { diagnosis_code_sha256: string; uncommitted_changes: string[] | null } | null;
  knowledge: EvaluationSummary['knowledge'];
  platform: string | null;
  transport: string | null;
  sets: Record<string, { scenarios: number; knowledge_frozen_before_generation: boolean | null; summary: Record<string, MethodSummary>; cases: Record<string, EvaluationCase[]> }>;
}

export interface ApiErrorBody {
  error?: { code: string; message: string; issues?: Issue[] };
  detail?: unknown;
}
