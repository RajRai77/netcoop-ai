import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { PlugZap, Server, Settings2 } from 'lucide-react';
import { apiGet, errorText } from '@/api/client';
import { useHealth, useMeta } from '@/api/hooks';
import type { Meta } from '@/api/types';
import { useApp } from '@/state/settings';
import { Chip, Panel } from '@/components/ui';
import { CLERK_ENABLED } from '@/auth/session';
import { AccountPanel } from '@/auth/clerk';

export default function SettingsPage() {
  const s = useApp();
  const qc = useQueryClient();
  const health = useHealth();
  const meta = useMeta();
  const [base, setBase] = useState(s.apiBase);
  const [token, setToken] = useState(s.apiToken);
  const [test, setTest] = useState<{ ok: boolean; text: string } | null>(null);
  const [testing, setTesting] = useState(false);

  const save = () => {
    s.set({ apiBase: base.trim().replace(/\/+$/, ''), apiToken: token.trim() });
    qc.invalidateQueries();
  };
  const runTest = async () => {
    save();
    setTesting(true);
    setTest(null);
    try {
      const h = await apiGet<{ status: string; version: string }>('/health/ready');
      const m = await apiGet<Meta>('/api/meta');
      setTest({ ok: true, text: `Health: ${h.status} · backend ${m.version} (${m.environment}) · agent transport ${m.agent_transport} · auth ${m.auth_required ? 'required' : 'not required'}` });
    } catch (e) {
      setTest({ ok: false, text: errorText(e) });
    } finally {
      setTesting(false);
    }
  };
  const m = meta.data;
  return (
    <>
      <div className="page-head"><div><h1>Settings</h1><p>Backend connection and display preferences. Stored in this browser only.</p></div></div>
      <div className="cols-2">
        {CLERK_ENABLED ? (
          <Panel title="Account" icon={<PlugZap size={19} />}
                 actions={health.isSuccess ? <Chip tone="green" pip>Backend connected</Chip> : <Chip tone="red" pip>Backend offline</Chip>}>
            <AccountPanel />
          </Panel>
        ) : (
        <Panel title="Backend connection" icon={<PlugZap size={19} />}
               actions={s.preview ? <Chip tone="amber" pip>Preview</Chip> : health.isSuccess ? <Chip tone="green" pip>Connected</Chip> : <Chip tone="red" pip>Offline</Chip>}>
          <div className="stack" style={{ gap: 12 }}>
            <label className="field">API base URL
              <input className="input" value={base} onChange={(e) => setBase(e.target.value)} placeholder="empty = same origin (Vite proxy)" />
            </label>
            <label className="field">Bearer token (only if the backend sets NETCOOP_API_TOKEN)
              <input className="input" type="password" autoComplete="off" value={token} onChange={(e) => setToken(e.target.value)} placeholder="not set" />
            </label>
            <div className="panel-sub">The token is kept in this browser's localStorage and sent only to the API base above. Do not use a shared machine for production tokens.</div>
            <div style={{ display: 'flex', gap: 8, flexWrap: 'wrap' }}>
              <button className="btn primary" onClick={runTest} disabled={testing || s.preview}><PlugZap size={16} />{testing ? 'Testing…' : 'Save & test connection'}</button>
              <button className="btn" onClick={save}>Save</button>
            </div>
            {test && <div className={test.ok ? 'ok-box' : 'err'} role="status">{test.text}</div>}
          </div>
        </Panel>
        )}
        <Panel title="Mode & display" icon={<Settings2 size={19} />}>
          <div className="stack" style={{ gap: 14 }}>
            <label className="check">
              <input type="checkbox" checked={s.preview} onChange={(e) => s.set({ preview: e.target.checked })} />
              Recorded preview (no backend)
            </label>
            <div className="panel-sub">
              Preview shows the stored responses of one real backend run of scenario S19 (backend commit ccab69d). It is labeled PREVIEW
              everywhere, refuses writes, and is never mixed with live data.
            </div>
            <label className="check">
              <input type="checkbox" checked={s.reducedMotion} onChange={(e) => s.set({ reducedMotion: e.target.checked })} />
              Reduce motion
            </label>
          </div>
        </Panel>
      </div>
      <div className="cols-2">
        <Panel title="Connected backend" icon={<Server size={19} />} sub={s.preview ? 'Recorded values' : undefined}>
          {m ? (
            <dl className="kv">
              <dt>Version</dt><dd>{m.version} · {m.environment}</dd>
              <dt>Agent transport</dt><dd>{m.agent_transport}</dd>
              <dt>Metric registry</dt><dd className="mono">{m.metric_registry_version}</dd>
              <dt>Detector rules</dt><dd className="mono">{m.detector_rules}</dd>
              <dt>Fault library</dt><dd className="mono">{m.fault_library}</dd>
              <dt>Auth</dt><dd>{m.auth_required ? 'Bearer token required' : 'not required'}</dd>
              <dt>Upload limit</dt><dd>{Math.round(m.max_upload_bytes / 1048576)} MiB · archive uploads {m.uploads_archive_enabled ? 'enabled' : 'disabled'}</dd>
              {health.data?.checks && <><dt>Readiness</dt><dd className="chips">{Object.entries(health.data.checks).map(([k, v]) => <Chip key={k} tone={v.ok ? 'green' : 'red'} title={v.detail}>{k}</Chip>)}</dd></>}
            </dl>
          ) : <div className="muted">{meta.isError ? errorText(meta.error) : 'Loading…'}</div>}
        </Panel>
        <Panel title="Running locally" icon={<Server size={19} />}>
          <ol className="list-plain">
            <li>Backend (repo root): <code className="mono">uv run python scripts/run_local.py --port 8000</code></li>
            <li>UI: <code className="mono">cd frontend &amp;&amp; npm ci &amp;&amp; npm run dev</code> → http://localhost:5173. The dev server proxies <code className="mono">/api</code> and <code className="mono">/health</code> to <code className="mono">VITE_BACKEND_PROXY</code> (default http://127.0.0.1:8000), so leave the API base empty.</li>
            <li>Cross-origin instead of the proxy: start the backend with <code className="mono">--cors-origin http://localhost:5173</code> and set the API base above.</li>
            <li>Docker Compose: the reverse proxy serves the API; see docs/09_DEPLOYMENT_AND_OPERATIONS.md.</li>
          </ol>
        </Panel>
      </div>
    </>
  );
}
