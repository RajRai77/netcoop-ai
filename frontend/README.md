# NetCoop AI — operator UI

A browser UI for the NetCoop AI diagnosis backend. It shows what the backend stored: validated evidence, the
A2A exchanges between specialist agents, the competing hypotheses, targeted verification and the schema-validated
report. It does not diagnose anything itself and never invents telemetry, agent messages or scores.

React 19 · TypeScript (strict) · Vite 8 · TanStack Query · Zustand · React Flow (`@xyflow/react`) · Lucide icons ·
plain-CSS design system (`src/styles/app.css`): light glass workspace (#F8F9FA / white, primary #1A73E8, success #4CAF50), navy
navigation, and a dark navy landing hero with neon-green accents. Branding uses the supplied NetCoop AI logo
(`src/assets/netcoop-logo.webp`, `netcoop-mark.webp`, made transparent from the original). Fonts (Inter, JetBrains Mono) are bundled via `@fontsource`; nothing
is loaded from a CDN, so the UI works offline.

## Run

```bash
# 1. backend (repo root)
uv sync --locked
uv run python scripts/run_local.py --port 8000          # API + 3 A2A specialist agents

# 2. UI
cd frontend
npm ci
npm run dev                                              # http://localhost:5173
```

The dev server proxies `/api` and `/health` to `VITE_BACKEND_PROXY` (default `http://127.0.0.1:8000`), so the API
base in Settings stays empty. Example for a backend on another port:
`VITE_BACKEND_PROXY=http://127.0.0.1:8010 npm run dev` (PowerShell: `$env:VITE_BACKEND_PROXY='http://127.0.0.1:8010'; npm run dev`).

Without the proxy, start the backend with `--cors-origin http://localhost:5173` and set the API base URL in Settings.
If the backend sets `NETCOOP_API_TOKEN`, enter it in Settings. It is kept in this browser's localStorage and sent as a
Bearer header, including on the SSE stream, which is read with `fetch` rather than `EventSource` so the header can be sent.

`npm run build` produces the static bundle in `dist/`. `npm run preview` serves it on port 4173 with the same proxy.

## Modes (always visible in the header)

| Mode | Source | Writes |
|---|---|---|
| **CONNECTED API** | the running backend | create incident, upload, diagnose |
| **PREVIEW** | `src/preview/recorded-s19.json`: responses recorded from one real backend run of S19 (backend commit `ccab69d`); evidence is truncated to 400 observations, and per-case evaluation results are not included | disabled |
| **Backend offline** | nothing; an explicit offline state with links to Settings and to the labeled preview | disabled |

Preview data is never mixed with live data: query caches are keyed by mode.

## Pages

| Route | Page | Backend endpoints |
|---|---|---|
| `/` | Landing page: what NetCoop AI is, why it is needed, how one investigation flows, capabilities, held-out results with caveats; "View demo incident" runs S19 live (or opens the labeled recording when offline) | health, meta, agents, evaluations |
| `/command` | Command Center: investigation hero with data-source label, 5 KPIs, **agent collaboration & reasoning flow** (incident → 3 specialists → STEaR → verification loop → diagnosis, with stage tracker), topology with affected scope, timeline, competing hypotheses with "why it leads", report summary with "how the system got here" | incident, timeline, topology, findings, report, agents, SSE stream |
| `/incidents` | Incident history: filter by text and status | `GET /api/incidents` |
| `/topology` | Full graph, collapsed or every host; node drill-down (findings, hypotheses, links, impact scope) | topology, findings, report |
| `/agents` | Agent cards (A2A URL, version, skills, metrics) and the exchange timeline; each attempt opens its raw NDEP artifact | `/api/agents`, timeline, `/attempts/{id}` |
| `/evidence` | Observations (search, metric and quality filters, sort), validation issues, derived counter rates; drill-down to the immutable raw record | evidence, `/api/raw-records/{ref}` |
| `/reasoning` | STEaR decision basis, ranking rule, alternatives, verification challenges and their outcomes, all hypotheses with status filter, contradictions and missing discriminators | report |
| `/report` | Revision selector, readable or raw-JSON view, JSON and text export | report `?revision=`, `report.txt` |
| `/scenarios` | Scenario library (create and diagnose, with or without verification); upload of topology JSON, NDEP JSON or profile-mapped CSV telemetry, and an optional archive, showing the backend's ingestion report | scenarios, profiles, meta, incidents POST, telemetry, archive, diagnose |
| `/evaluation` | Recorded benchmark results by method; cases without an acceptable outcome | `/api/evaluations`, `/api/evaluations/{name}` |
| `/settings` | API base, token, connection test, preview toggle, reduce motion, backend versions and readiness | `/health/ready`, `/api/meta` |

Live updates: while a run is in progress the UI reads `GET /api/incidents/{id}/stream`. It handles the `workflow`,
`attempt`, `challenge`, `report` and `end` events, deduplicates by `seq`, attempt id and challenge outcome, reconnects
with `?after=<last seq>` and exponential backoff, and refetches the affected queries.

## What is real and what is not

- **Live (CONNECTED API):** every number, agent card, timeline step, hypothesis, verification request and report comes from the
  running backend. The flow diagram is drawn from persisted workflow events, A2A attempts, challenges and findings; its
  connector lines are measured from the rendered cards; nothing is animated unless the matching stage is actually running.
- **Topology node states:** *Root cause*, *Affected*, *Candidate* come from the report; *Symptom observed* from a present finding;
  *Checked · normal* means a specialist reported on the node without an anomaly; *No findings* means no specialist reported on it.
  The dashed ring is the backend's topology impact scope of the selected cause.
- **Data source label:** `ORG-*` scenarios are built from the organizer's PS sample generator and labeled
  "Organizer data · PS sample generator" (they are the default in the launcher and the landing demo). Other scenarios are
  labeled "Synthetic scenario (NetCoop generator)".
- **Confidence:** the number shown (e.g. "Confidence 0.88") is the report's calibrated `confidence`, with n, interval and
  held-out set in the tooltip and on the report page. The support category is shown separately and never as a percentage.
- **Preview:** a labeled recording of one real S19 run; no writes, no backend calls.
- **Static text:** the landing page's explanations of the approach are descriptive copy, not data.

## Display rules followed

- `confidence_category` is a documented support category (insufficient, ambiguous, moderate, high). It is shown as a
  word with a 4-step meter, labeled "not a probability". No percentages appear anywhere.
- The hypothesis bars show the number of symptom findings each hypothesis explains, relative to the maximum.
- Evaluation numbers are shown exactly as stored. "Acceptable outcome" counts honest abstentions, so it is not called
  accuracy. The page states that the scenarios are synthetic and come from the project's own generator.
- Data mode (`synthetic`, `recorded`, `emulated`, `live`) is shown on every incident.

## Verification (executed on 2026-11-01, Windows 11, Chrome 157 via puppeteer-core)

| Check | Command | Result |
|---|---|---|
| Clean install from lockfile | `npm ci` (fresh copy) | 189 packages, OK |
| Type check | `npx tsc --noEmit` | OK |
| Lint | `npm run lint` (oxlint) | exit 0; only `only-export-components` / `set-state-in-effect` warnings remain |
| Build | `npm run build` | OK |
| S19 golden workflow, live backend | `node scripts/e2e-s19.mjs http://127.0.0.1:5173 docs/e2e-s19` | 18/18 checks passed ([result](docs/e2e-s19/result.json)) |
| Organizer data workflow, live backend | `node scripts/e2e-organizer.mjs http://127.0.0.1:5173 docs/e2e-organizer` | 10/10 checks passed ([result](docs/e2e-organizer/result.json)) |
| Preview and offline modes | `node scripts/e2e-modes.mjs http://127.0.0.1:5173 docs/e2e-modes` | 14/14 checks passed ([result](docs/e2e-modes/result.json)) |
| Basic accessibility | `node scripts/a11y-check.mjs` | 11/11 routes passed |
| Responsive screenshots | `node scripts/screenshots.mjs http://127.0.0.1:5173 <incident> docs/screenshots / /command /incidents …` | 1920×1080, 1536×960, 1366×768 and 390×844; no horizontal overflow |

The S19 test drives the UI: it selects "AP down · needs verification", clicks Run diagnosis, follows the SSE stream
to a terminal state, and checks the following against the backend's own responses for the new incident:
- the first correlation round is ambiguous (AP-2-1 down vs. ACC-2-1:ge1/1 port failure);
- a verification challenge goes over A2A to the infrastructure agent for `device_status` of AP-2-1, and it returns archived observations;
- the QUERY and RESPONSE appear in the UI timeline;
- the final report is DEVICE_DOWN at AP-2-1 with high support;
- the exported JSON is byte-identical to `GET /report`.

The browser scripts need a local Chrome or Edge. They write PNGs; the committed images in `docs/` are a curated
subset converted to WebP to keep the repository small.

## Limitations

- The accessibility check is a scripted basic check (names, labels, headings, focus), not a full WCAG/axe audit.
  Colour contrast and screen-reader flow were not audited.
- The Command Center places the flow and the topology side by side only at 1700 px and wider; below that they stack.
- The topology layout is a simple tree layout from the core. It is readable for campus-sized graphs (around 25 nodes);
  large topologies are not tested.
- The Evidence Explorer loads the first 2000 observations and renders at most 500 rows. It does not page further.
- Preview contains one recorded incident (S19) only. Pages that need other data show an explicit "not in preview" state.
- Only NDEP JSON and profile-mapped CSV uploads are supported, because those are what the backend ingests. There is
  no PCAP, syslog or gNMI input.
- Unused dependencies remain from the previous UI (`framer-motion`, `recharts`, Tailwind/PostCSS). They do not
  affect the bundle and can be removed in a separate change.
- The bundle carries a ~760 kB preview chunk (82 kB gzip). It is lazy-loaded only when preview mode is used.

## Layout

```
src/
  api/        client.ts (fetch, errors, auth) · hooks.ts (queries/mutations) · sse.ts · preview.ts · types.ts
  components/ Shell (sidebar, header, banners) · ui · Topology · Timeline · Reasoning
  pages/      one file per route; useActive.ts loads the active incident
  lib/        labels and formatting
  state/      persisted settings (Zustand)
  preview/    recorded S19 responses (labeled preview only)
  styles/     app.css design tokens and components
  assets/     neon-earth-network.webp (the supplied background)
scripts/      screenshots.mjs · e2e-s19.mjs · e2e-modes.mjs · a11y-check.mjs
docs/         screenshots/, e2e-s19/, e2e-modes/
```
