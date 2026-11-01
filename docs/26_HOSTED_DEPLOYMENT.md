# 26 — Hosted deployment: Render (API + agents) + Neon (PostgreSQL) + Netlify (React app)

This is a **free-tier demo deployment**. The reference production design remains Docker Compose on one Linux host
(docs/09). Nothing here needs a credit card; nothing is merged to `main`.

```
browser ──HTTPS──> Netlify (static React build, VITE_API_BASE = Render URL)
   └──HTTPS /api, SSE──> Render web service (Dockerfile.render, ONE container, 4 processes)
                           API/coordinator on 0.0.0.0:$PORT  ── also serves the same React app at /
                           3 specialist A2A agents on 127.0.0.1:<dynamic>  (never exposed)
                           └── TLS ──> Neon PostgreSQL (persistent evidence ledger)
```

The Render URL alone is a complete app (React served by the API, same origin). Netlify is optional.

## Measured facts (not assumptions)

| Fact | Source |
|---|---|
| Image builds; only `$PORT` listens on 0.0.0.0, the agents on loopback; `/api` needs the token; React served; smoke diagnosis over A2A passes | CI job `render-image` (Linux, PostgreSQL 17) |
| Memory on Linux after one diagnosis: **407.5 MiB container (cgroup)**; process RSS API 125, agents 99–105 each, launcher 84 MiB (RSS double-counts shared pages) | CI run 41267165838, job `render-image`, public annotations |
| Hosted URLs and hosted smoke test | recorded below only after they were executed |

Status log (append, do not rewrite):

- 2026-11-01: `render-image` CI job green (run 41267165838): image builds; only `$PORT` on 0.0.0.0; agents on 127.0.0.1;
  `/api` returns 401 without the token; React served at `/` and `/command`; smoke diagnosis over A2A passes against
  PostgreSQL 17. Measured 407.5 MiB container memory: fits Render free (512 MB) with ~100 MiB headroom after one
  diagnosis. This is one measurement; heavier runs or uploads may need more, and Render restarts a container that exceeds it.
- 2026-11-01: deployment files committed (`Dockerfile.render`, `render.yaml`, `netlify.toml`). Hosted services not yet
  created: they need the owner's Neon, Render and Netlify accounts.

## Steps for the owner (accounts, ~15 minutes)

### 1. Neon (database)

1. Sign in at <https://console.neon.tech> (GitHub login works) → **New project** → name `netcoop-ai`, Postgres 17, region
   near Render's (e.g. *AWS Asia Pacific (Singapore)*).
2. **Connect** → copy the connection string (`postgresql://USER:PASSWORD@HOST/neondb?sslmode=require`). Keep it secret.
   The app creates its tables itself (migrations run at start).

### 2. Render (API + agents)

1. Sign in at <https://dashboard.render.com> with GitHub and allow access to `RajRai77/netcoop-ai`.
2. **New → Blueprint** → repository `RajRai77/netcoop-ai`, branch **`gate0-skeleton`** → Render reads `render.yaml`.
3. Enter the secret values it asks for:
   - `NETCOOP_DATABASE_URL` = the Neon string from step 1.
   - `NETCOOP_API_TOKEN` = a random value (e.g. `python -c "import secrets;print(secrets.token_hex(24))"`), **or leave it
     empty for a public demo** (then anyone with the URL can create incidents and upload up to 5 MiB per file; data is
     synthetic). Decide this deliberately.
   - `NETCOOP_CORS_ORIGINS` = your Netlify origin from step 3 (e.g. `https://netcoop-ai.netlify.app`); can be added later.
4. Deploy. The first build takes several minutes. Then open `https://<service>.onrender.com/health/ready` → `"ready"`.
   Free instances sleep after ~15 idle minutes; the next request takes up to about a minute.

### 3. Netlify (React app)

1. Sign in at <https://app.netlify.com> with GitHub → **Add new site → Import an existing project** → `RajRai77/netcoop-ai`,
   branch `gate0-skeleton`. `netlify.toml` sets base `frontend`, build command and publish dir.
2. **Site configuration → Environment variables**: `VITE_API_BASE` = `https://<service>.onrender.com` (public URL, not a
   secret). Never put the API token in a `VITE_*` variable: it would be published in the JavaScript.
3. Deploy, then put the Netlify origin into Render's `NETCOOP_CORS_ORIGINS` and redeploy Render.
4. If a token is set: open the site → **Settings** → paste the token → **Save & test connection**. It is stored in that
   browser only.

### 4. Hosted smoke test (run after deployment)

```sh
BASE_URL=https://<service>.onrender.com NETCOOP_API_TOKEN=<token or empty> sh scripts/smoke.sh
```

It creates an incident, runs a real diagnosis over A2A and checks the report (`transport: a2a`, ≥2 contributing agents).
