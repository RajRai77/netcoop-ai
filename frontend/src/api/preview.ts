// Preview mode: serves responses RECORDED from a real backend run (src/preview/recorded-s19.json,
// backend commit ccab69d). Loaded lazily; never shown unless the user enables Preview, and every
// screen labels it. Writes are refused (see client.ts).

type Snapshot = Record<string, unknown> & {
  _recorded: { recorded_at: string; backend_commit: string; incident_id: string; scenario_id: string; note: string };
};

let cache: Promise<Snapshot> | null = null;
export function loadSnapshot(): Promise<Snapshot> {
  if (!cache) cache = import('@/preview/recorded-s19.json').then((m) => m.default as unknown as Snapshot);
  return cache;
}

export async function previewGet<T>(path: string): Promise<T> {
  const s = await loadSnapshot();
  const iid = s._recorded.incident_id;
  const p = path.split('?')[0];
  const table: Record<string, string> = {
    '/api/meta': 'meta',
    '/api/agents': 'agents',
    '/api/scenarios': 'scenarios',
    '/api/incidents': 'incidents',
    '/api/evaluations': 'evaluations',
    '/api/profiles': 'profiles',
    [`/api/incidents/${iid}`]: 'incident',
    [`/api/incidents/${iid}/timeline`]: 'timeline',
    [`/api/incidents/${iid}/topology`]: 'topology',
    [`/api/incidents/${iid}/findings`]: 'findings',
    [`/api/incidents/${iid}/evidence`]: 'evidence',
    [`/api/incidents/${iid}/report`]: 'report',
  };
  if (p === '/health/ready') return { status: 'ready (recorded)', version: 'preview', checks: {} } as T;
  const key = table[p];
  if (!key) throw new Error(`Not part of the recorded preview (${p}). Connect to a backend for this view.`);
  return s[key] as T;
}
