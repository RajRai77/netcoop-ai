import type { HypothesisStatus, ReportStatus, Subject, SupportCategory, WorkflowState } from '@/api/types';

export const STATUS_LABEL: Record<ReportStatus, string> = {
  diagnosed: 'Diagnosed',
  ambiguous: 'Ambiguous',
  insufficient_evidence: 'Insufficient evidence',
  unknown_fault: 'Unknown fault',
  healthy: 'Healthy',
  operational_error: 'Operational error',
};

export type Tone = 'cyan' | 'green' | 'amber' | 'red' | 'violet' | 'blue' | 'muted' | 'magenta';

export const STATUS_TONE: Record<ReportStatus, Tone> = {
  diagnosed: 'green',
  ambiguous: 'amber',
  insufficient_evidence: 'blue',
  unknown_fault: 'magenta',
  healthy: 'cyan',
  operational_error: 'red',
};

export const SUPPORT_LABEL: Record<SupportCategory, string> = {
  high_support: 'High support',
  moderate_support: 'Moderate support',
  ambiguous: 'Ambiguous',
  insufficient: 'Insufficient',
  not_applicable: 'Not applicable',
};

export const SUPPORT_TONE: Record<SupportCategory, Tone> = {
  high_support: 'green',
  moderate_support: 'cyan',
  ambiguous: 'amber',
  insufficient: 'blue',
  not_applicable: 'muted',
};

/** Qualitative scale (ordered categories, NOT a probability). */
export const SUPPORT_STEPS: SupportCategory[] = ['insufficient', 'ambiguous', 'moderate_support', 'high_support'];

export const HYP_LABEL: Record<HypothesisStatus, string> = { confirmed: 'Confirmed', plausible: 'Plausible', contradicted: 'Ruled out' };
export const HYP_TONE: Record<HypothesisStatus, Tone> = { confirmed: 'green', plausible: 'amber', contradicted: 'muted' };

export const FAULT_LABEL: Record<string, string> = {
  LINK_CONGESTION: 'Link congestion',
  INTERFACE_DEGRADATION: 'Interface degradation',
  LINK_OR_PATH_FAILURE: 'Link / path failure',
  DEVICE_CPU_OVERLOAD: 'Device CPU overload',
  DEVICE_DOWN: 'Device down',
  WEAK_WIFI_SIGNAL: 'Weak Wi-Fi signal',
  WIRELESS_INTERFERENCE: 'Wireless interference',
  DNS_FAILURE: 'DNS failure',
  DHCP_FAILURE: 'DHCP failure',
};
export const faultLabel = (f: string) => FAULT_LABEL[f] ?? f.replace(/_/g, ' ').toLowerCase();

export const AGENT_LABEL: Record<string, string> = {
  'performance-agent': 'Performance',
  'infrastructure-agent': 'Infrastructure',
  'connectivity-agent': 'Connectivity & Services',
  coordinator: 'Coordinator',
};
export const AGENT_TONE: Record<string, Tone> = {
  'performance-agent': 'blue',
  'infrastructure-agent': 'violet',
  'connectivity-agent': 'green',
  coordinator: 'blue',
};
export const AGENT_COLOR: Record<string, string> = {
  'performance-agent': '#1a73e8', 'infrastructure-agent': '#7c4dff', 'connectivity-agent': '#43a047', coordinator: '#1a73e8',
};
export const AGENT_ROLE: Record<string, string> = {
  'performance-agent': 'Latency, loss, jitter, utilization',
  'infrastructure-agent': 'Device, interface, CPU and Wi-Fi state',
  'connectivity-agent': 'Reachability, DNS and DHCP',
};
export const agentLabel = (a: string) => AGENT_LABEL[a] ?? a;

export const STATE_LABEL: Partial<Record<WorkflowState, string>> = {
  NEW: 'Created', VALIDATING: 'Validating evidence', DISCOVERING: 'Discovering agents', INVESTIGATING: 'Specialists investigating',
  CORRELATING: 'Correlating hypotheses', VERIFYING: 'Verifying', INTERRUPTED: 'Interrupted', DIAGNOSED: 'Diagnosed',
  AMBIGUOUS: 'Ambiguous', INSUFFICIENT_EVIDENCE: 'Insufficient evidence', UNKNOWN_FAULT: 'Unknown fault', HEALTHY: 'Healthy',
  OPERATIONAL_ERROR: 'Operational error',
};

export const CLAIM_LABEL: Record<string, string> = {
  HIGH_LATENCY: 'High latency', HIGH_JITTER: 'High jitter', PACKET_LOSS: 'Packet loss', HIGH_LINK_UTILIZATION: 'High link utilization',
  QUEUE_DROPS: 'Queue drops', HIGH_CPU: 'High CPU', HIGH_MEMORY: 'High memory', CRC_ERRORS: 'CRC errors',
  INTERFACE_ERRORS: 'Interface errors', DEVICE_DOWN_STATE: 'Device reported down', DEVICE_DEGRADED_STATE: 'Device degraded',
  INTERFACE_DOWN: 'Interface down', WEAK_SIGNAL: 'Weak signal', LOW_SNR: 'Low SNR', HIGH_WIRELESS_RETRIES: 'High Wi-Fi retries',
  UNREACHABLE: 'Unreachable', DNS_FAILURES: 'DNS failures', DHCP_FAILURES: 'DHCP failures',
  COMMON_UPSTREAM_DEPENDENCY: 'Common upstream (topology)', COMMON_SERVICE_DEPENDENCY: 'Common service (topology)',
};
export const claimLabel = (c: string) => CLAIM_LABEL[c] ?? c;

export function subjectText(s: Subject | undefined | null): string {
  if (!s) return '—';
  if (s.device_id && s.interface_id) return `${s.device_id}:${s.interface_id}`;
  return s.device_id ?? s.service_id ?? s.segment_id ?? s.link_id ?? '—';
}

export function timeOf(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' });
}

export function dateTimeOf(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString([], { year: 'numeric', month: 'short', day: '2-digit', hour: '2-digit', minute: '2-digit' });
}

export function durationBetween(a?: string | null, b?: string | null): string {
  if (!a || !b) return '—';
  const ms = new Date(b).getTime() - new Date(a).getTime();
  if (!Number.isFinite(ms) || ms < 0) return '—';
  if (ms < 1000) return `${ms} ms`;
  const s = ms / 1000;
  return s < 60 ? `${s.toFixed(1)} s` : `${Math.floor(s / 60)}m ${Math.round(s % 60)}s`;
}

export function fmtValue(v: unknown): string {
  if (typeof v === 'number') return Number.isInteger(v) ? v.toLocaleString() : v.toLocaleString(undefined, { maximumFractionDigits: 3 });
  return String(v);
}

export function downloadBlob(name: string, content: string, type: string) {
  const url = URL.createObjectURL(new Blob([content], { type }));
  const a = document.createElement('a');
  a.href = url;
  a.download = name;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 2000);
}

/** Honest data-source label. Only backend facts are used; nothing is called "organizer" or "live" unless it is. */
export function dataSourceLabel(inc: { data_mode: string; scenario_id: string | null }, preview: boolean): string {
  if (preview) return 'Recorded investigation (preview)';
  if (inc.scenario_id) return inc.data_mode === 'synthetic' ? 'Synthetic scenario' : `Scenario (${inc.data_mode})`;
  return ({ recorded: 'Uploaded telemetry (recorded)', emulated: 'Uploaded telemetry (emulated)', synthetic: 'Uploaded telemetry (synthetic)', live: 'Live telemetry' } as Record<string, string>)[inc.data_mode] ?? inc.data_mode;
}

export function clock(ms: number): string {
  if (!Number.isFinite(ms) || ms < 0) return '—';
  const s = Math.round(ms / 1000);
  return `${String(Math.floor(s / 60)).padStart(2, '0')}:${String(s % 60).padStart(2, '0')}`;
}
