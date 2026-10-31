// ============================================================
// NetCoop AI — Domain Types
// Mirrors backend NDEP contract (src/netcoop/evidence/models.py)
// and FastAPI responses (src/netcoop/api/app.py)
// ============================================================

// --- Core Primitive Types ---

export type DataMode = 'synthetic' | 'recorded' | 'emulated' | 'live' | 'mock';
export type MeasurementKind = 'gauge' | 'cumulative_counter' | 'derived_rate' | 'interval_summary' | 'state';
export type ValidationStatus = 'passed' | 'quarantined' | 'rejected';
export type FreshnessStatus = 'current' | 'stale' | 'unknown';
export type Polarity = 'present' | 'absent' | 'unknown';
export type TopologyNodeType = 'device' | 'service' | 'ap' | 'segment' | 'host';
export type TopologyNodeRole = 'core' | 'distribution' | 'access' | 'edge' | 'server' | 'client';
export type TopologyLinkType = 'physical' | 'logical' | 'dependency' | 'routing';
export type ServiceKind = 'dns' | 'dhcp' | 'aaa' | 'web' | 'other';

// --- Diagnosis Statuses ---
export type DiagnosisStatus = 
  | 'diagnosed'
  | 'ambiguous'
  | 'insufficient_evidence'
  | 'unknown_fault'
  | 'healthy'
  | 'operational_error';

export type ConfidenceCategory = 
  | 'high_support'
  | 'moderate_support'
  | 'ambiguous'
  | 'insufficient'
  | 'not_applicable';

// --- Workflow States ---
export type WorkflowState =
  | 'NEW'
  | 'VALIDATING'
  | 'DISCOVERING'
  | 'INVESTIGATING'
  | 'CORRELATING'
  | 'VERIFYING'
  | 'DIAGNOSED'
  | 'AMBIGUOUS'
  | 'INSUFFICIENT_EVIDENCE'
  | 'UNKNOWN_FAULT'
  | 'HEALTHY'
  | 'OPERATIONAL_ERROR'
  | 'INTERRUPTED';

// --- Fault Types (from backend knowledge/fault_library) ---
export type FaultType =
  | 'LINK_CONGESTION'
  | 'INTERFACE_DEGRADATION'
  | 'DEVICE_CPU_OVERLOAD'
  | 'DEVICE_DOWN'
  | 'WEAK_WIFI_SIGNAL'
  | 'WIRELESS_INTERFERENCE'
  | 'DNS_FAILURE'
  | 'DHCP_FAILURE'
  | 'PATH_OR_ROUTE_FAILURE'
  | 'UNKNOWN';

// --- Agent IDs ---
export type AgentDomain = 'performance' | 'infrastructure' | 'connectivity';

// --- NDEP Models ---

export interface SourceRef {
  source_id: string;
  data_mode: DataMode;
  source_type: string;
}

export interface Subject {
  device_id?: string;
  interface_id?: string;
  service_id?: string;
  segment_id?: string;
  link_id?: string;
}

export interface TimeWindow {
  start: string; // ISO 8601
  end: string;
}

export interface Measurement {
  metric: string;
  value: boolean | number | string;
  unit: string;
  kind: MeasurementKind;
  window?: TimeWindow;
}

export interface Quality {
  validation: ValidationStatus;
  freshness: FreshnessStatus;
  flags: string[];
}

export interface NormalizedObservation {
  schema_version: string;
  observation_id: string;
  incident_id: string;
  raw_record_ref: string;
  source: SourceRef;
  subject: Subject;
  measurement: Measurement;
  observed_at: string;
  ingested_at: string;
  quality: Quality;
  lineage_group: string;
  metric_registry_version: string;
  transformation_id?: string;
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
  supersedes_finding_id?: string;
}

// --- Topology ---

export interface TopologyNode {
  id: string;
  type: TopologyNodeType;
  role?: TopologyNodeRole;
  label?: string;
  service_kind?: ServiceKind;
  // UI-only enrichment (not from backend directly)
  status?: 'healthy' | 'degraded' | 'failed' | 'unknown';
  impacted?: boolean;
}

export interface TopologyLink {
  id: string;
  from: string;
  to: string;
  type: TopologyLinkType;
  directed?: boolean;
  from_interface?: string;
  to_interface?: string;
  // UI-only
  degraded?: boolean;
}

export interface TopologySnapshot {
  schema_version: string;
  topology_snapshot_id: string;
  kind: 'intended' | 'observed' | 'modeled' | 'synthetic';
  observed_at: string;
  nodes: TopologyNode[];
  links: TopologyLink[];
  limitations: string[];
}

// --- Incidents ---

export interface Incident {
  incident_id: string;
  data_mode: DataMode;
  created_at: string;
  topology_snapshot_id?: string;
  title?: string;
  archive_ref?: string;
  reference_time?: string;
}

export interface IncidentSummary extends Incident {
  workflow?: WorkflowSummary;
  latest_report?: ReportSummary;
}

export interface WorkflowSummary {
  state: WorkflowState;
  run_id: string;
  updated_at: string;
  agent_id?: string;
  detail?: Record<string, unknown>;
}

// --- Reports ---

export interface ReportSummary {
  revision: number;
  status: DiagnosisStatus;
  suspected_root_cause: string | null;
  confidence_category: ConfidenceCategory;
  created_at: string;
}

export interface SupportingEvidence {
  observation_id?: string;
  finding_id?: string;
  description: string;
  metric?: string;
  value?: string | number;
  unit?: string;
}

export interface AlternativeCause {
  fault_type: FaultType | string;
  component?: string;
  reason_excluded: string;
}

export interface RecommendedAction {
  priority: 'high' | 'medium' | 'low';
  action: string;
  target?: string;
}

export interface DiagnosticReport {
  incident_id: string;
  revision: number;
  status: DiagnosisStatus;
  suspected_root_cause: string | null;
  affected_devices: string[];
  affected_scope?: string;
  supporting_evidence: SupportingEvidence[];
  alternative_causes: AlternativeCause[];
  recommended_actions: RecommendedAction[];
  evidence_sources: string[];
  limitations: string[];
  confidence_category: ConfidenceCategory;
  evidence_snapshot_id: string;
  topology_snapshot_id?: string;
  engine_version: string;
  created_at: string;
}

// --- Timeline / Events ---

export type EventKind =
  | 'TASK_STARTED'
  | 'FINDING_SUBMITTED'
  | 'CONTRADICTION_RAISED'
  | 'EVIDENCE_REQUESTED'
  | 'VERIFICATION_OBTAINED'
  | 'TIMEOUT'
  | 'AGENT_FAILED'
  | 'HYPOTHESIS_FORMED'
  | 'STATE_TRANSITION'
  | 'OPERATIONAL_ERROR'
  | 'INTERRUPTED'
  | 'REPORT_GENERATED';

export interface TimelineEvent {
  event_id: string;
  incident_id: string;
  run_id: string;
  kind: EventKind;
  actor: string;
  detail: Record<string, unknown>;
  created_at: string;
}

export interface AgentAttempt {
  attempt_id: string;
  incident_id: string;
  run_id: string;
  agent_id: string;
  task_id: string;
  status: 'pending' | 'running' | 'succeeded' | 'failed' | 'timeout';
  started_at: string;
  finished_at?: string;
  detail: Record<string, unknown>;
}

export interface Challenge {
  challenge_id: string;
  incident_id: string;
  target_agent: string;
  requested_check: string;
  hypothesis_refs: string[];
  finding_refs: string[];
  observation_window?: TimeWindow;
  deadline?: string;
  created_at: string;
  resolved_at?: string;
  result?: 'obtained' | 'unavailable' | 'timeout';
}

// --- Agents ---

export interface AgentStatus {
  agent_id: string;
  transport: 'a2a' | 'in-process';
  url?: string;
  status: 'available' | 'unavailable';
  skills?: string[];
  metrics?: string[];
  name?: string;
  version?: string;
  error?: string;
}

// --- Scenarios ---

export interface ScenarioInfo {
  id: string;
  title: string;
  description?: string;
  fault_type?: FaultType | string;
  data_mode: DataMode;
  tags?: string[];
}

// --- Evaluation ---

export interface EvalMethodSummary {
  cases: number;
  acceptable_outcome: { count: number; of: number };
  exact_cause_on_diagnosable: { count: number; of: number };
  fault_type_on_diagnosable: { count: number; of: number };
  localization_on_diagnosable: { count: number; of: number };
  confident_wrong_all: { count: number; of: number };
  high_support_wrong_all: { count: number; of: number };
  abstained_when_not_diagnosable: { count: number; of: number };
  false_healthy_on_faulty: { count: number; of: number };
  healthy_correct: { count: number; of: number };
  unknown_detected: { count: number; of: number };
  multi_fault_full_recall: { count: number; of: number };
  checks_requested_total: number;
  checks_obtained_total: number;
  seconds_median: number;
  seconds_max: number;
}

export interface EvalCaseResult {
  scenario_id: string;
  method: string;
  status: DiagnosisStatus;
  category: string;
  causes: [string, string][];
  suspected_root_cause: string | null;
  seconds: number;
  checks_requested: number;
  checks_obtained: number;
  new_observations: number;
  truth: [string, string][];
  unmodeled: boolean;
  score: {
    exact_cause: boolean;
    fault_type_correct: boolean;
    localization_correct: boolean;
    any_cause_correct: boolean;
    confident_wrong: boolean;
    high_support_wrong: boolean;
    abstained: boolean;
    false_healthy: boolean;
    healthy_correct: boolean;
    unknown_detected: boolean;
    multi_fault_recall: number | null;
    diagnosable: boolean;
    acceptable: boolean;
  };
}

// --- UI-specific ---

export interface ConnectionStatus {
  connected: boolean;
  checking: boolean;
  version?: string;
  environment?: string;
  agent_transport?: string;
  error?: string;
  last_checked?: string;
}

export interface AppSettings {
  backendUrl: string;
  apiToken?: string;
  useFixtureData: boolean;
  reducedMotion: boolean;
}

// Hypothesis (computed from STEaR engine findings, derived for UI)
export interface HypothesisCandidate {
  id: string;
  fault_type: FaultType | string;
  component: string;
  support_level: 'high_support' | 'moderate_support' | 'ambiguous' | 'insufficient';
  status: 'leading' | 'competing' | 'rejected' | 'unresolved';
  supporting_findings: string[];
  contradicting_findings: string[];
  unexplained_symptoms: string[];
  missing_evidence: string[];
  scope: string[];
}
