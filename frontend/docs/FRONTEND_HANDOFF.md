# Frontend handoff

Current state, run instructions, page map, verification results and limitations are in [../README.md](../README.md).
The backend contract the UI follows is [docs/25_FRONTEND_INTEGRATION.md](../../docs/25_FRONTEND_INTEGRATION.md),
with [docs/openapi.json](../../docs/openapi.json).

## Rules for changes

- The UI only shows what the backend returned. Do not add client-side diagnosis, scores, simulated agent messages or
  "live" data.
- `confidence_category` is a support category, not a probability. Never render it as a percentage.
- Preview data (`src/preview/recorded-s19.json`) must stay labeled PREVIEW and must never be mixed with live responses.
  If you re-record it, record from a real backend run and update `_recorded` (commit, time, incident).
- Types in `src/api/types.ts` mirror real responses. When the backend schema changes, update the types first, then run
  `npx tsc --noEmit`.
- Before committing, run the checks in the README's verification table. The S19 end-to-end test needs the real backend
  and the dev server running.

## Previous UI

The earlier mock-driven UI, its README and the previous version of this document were replaced on 2026-11-01. A copy is kept
outside the repository (`netcoop-ai-frontend-backup-20261101-042334/`), and the tracked files remain in git history
(commit `538e59c`).
