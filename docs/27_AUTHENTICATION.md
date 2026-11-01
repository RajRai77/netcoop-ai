# 27 — Authentication: Google sign-in with Clerk, verified sessions, per-user isolation

## What a visitor experiences (Clerk mode)

1. `/` (landing page) is public. It shows live backend/agent status from the public catalog endpoints.
2. **Continue with Google** goes straight to Google's account chooser (Clerk `signIn.sso`, strategy `oauth_google`);
   if that cannot start, Clerk's own sign-in dialog opens. After Google, `/sso-callback` completes the sign-in and lands
   on `/command`.
3. Every API call and the live SSE stream automatically carry the current Clerk session token. Nobody types a token.
4. Refreshing keeps the session (Clerk). The header avatar menu (Clerk `UserButton`) and Settings → Account offer
   **Sign out**; signing out or switching accounts clears cached results, the active incident and open streams.

## Server-side rules (src/netcoop/api/auth.py, src/netcoop/api/app.py)

| Mode (`NETCOOP_AUTH_MODE`) | Accepts | Intended for |
|---|---|---|
| `clerk` | a Clerk **session** token in `Authorization: Bearer`, verified with the official `clerk-backend-api` SDK | hosted, multi-user |
| `token` | one static `NETCOOP_API_TOKEN` (constant-time compare) | CI, CLI, Compose, single operator |
| `none` | everything | local development only; **refused when `NETCOOP_ENV=production`** |

Unset `NETCOOP_AUTH_MODE` = `token` if `NETCOOP_API_TOKEN` is set, else `none` (the behaviour before Clerk).

Clerk verification, per request:
- signature RS256 against the instance keys: by default the instance's **public** JWKS
  (`<issuer>/.well-known/jwks.json`, cached 1 h, refetched once per minute at most for an unknown key id); or JWKS via
  `CLERK_SECRET_KEY`; or a configured PEM `CLERK_JWT_KEY`. No secret is required;
  `exp`/`nbf` with 5 s skew, authorized party `azp` ∈ `CLERK_AUTHORIZED_PARTIES` (default: `RENDER_EXTERNAL_URL` plus
  `NETCOOP_CORS_ORIGINS`) — done by the SDK;
- **issuer**: the SDK does not check `iss`, so NetCoop requires it to equal the instance's frontend-API URL, derived
  from the publishable key (`pk_…` encodes it) or set as `CLERK_ISSUER`;
- only session tokens (no machine/API-key/OAuth tokens), `sub` must be a user (`user_…`) and `sid` must be present;
- only the `Authorization` header is used. Clerk's `__session` cookie is **not** accepted, so state-changing requests
  cannot be forged cross-site;
- the static `NETCOOP_API_TOKEN` is never accepted in Clerk mode;
- incomplete Clerk configuration stops the API at start-up (fail closed), it never falls back to open access.

Public in Clerk mode: `/health/live`, `/health/ready`, the React app, and the non-personal catalog
`/api/meta`, `/api/agents` (status), `/api/evaluations` (recorded results). Everything else needs a verified session.

## Data isolation

- Migration `0003` adds `incidents.owner_id` (the verified Clerk `sub`). It is set only from the session, never from
  the request body (`owner_id` in JSON is rejected, 422).
- One dependency enforces ownership for every route with an `{incident_id}`: detail, evidence, findings, timeline,
  topology, attempts, report, report.txt, telemetry and archive uploads, diagnosis and the SSE stream. `GET
  /api/incidents` lists only the caller's incidents; `/api/raw-records/{id}` checks the record's incident.
  Another user's incident and a non-existent one both return **404**, so ids cannot be probed.
- Records created before Clerk mode (or in token/none mode) have no owner and are **not visible to any signed-in user**.
  Packaged scenarios are shared definitions; each run creates the caller's own incident.
- Inference, A2A messages and evidence provenance are unchanged; ownership is only an access rule.

## Owner checklist (needs your Clerk and, for production, Google Cloud access)

**Deployed configuration (2026-11-01):** Clerk development instance `uncommon-gar-47.clerk.accounts.dev`, Google enabled.
`Dockerfile.render` carries only its public values (`NETCOOP_AUTH_MODE=clerk`, the publishable key,
`CLERK_AUTHORIZED_PARTIES=https://netcoop-ai-07i3.onrender.com`); sessions are verified with the instance's public
JWKS, so no Clerk secret is stored anywhere. Render environment variables override these defaults.

**A. Development instance — works with the Render URL** (Clerk shows a small "Development mode" badge)
1. <https://dashboard.clerk.com> → **Create application** → name *NetCoop AI* → enable **Google** only (Clerk's shared
   development OAuth credentials are used; no Google Cloud setup needed) → Create.
2. **API keys**: copy the **Publishable key** (`pk_test_…`) and the **Secret key** (`sk_test_…`).
3. Render → service → **Environment**: set
   `NETCOOP_AUTH_MODE=clerk`, `VITE_CLERK_PUBLISHABLE_KEY=pk_test_…`, `CLERK_SECRET_KEY=sk_test_…`
   (optional `CLERK_AUTHORIZED_PARTIES=https://netcoop-ai-07i3.onrender.com`; it defaults to the service URL).
   Keep `NETCOOP_DATABASE_URL`. `NETCOOP_API_TOKEN` can stay; Clerk mode ignores it.
4. Deploy the branch that contains this feature (Render rebuilds; the publishable key is passed as a Docker build
   argument because `Dockerfile.render` declares `ARG VITE_CLERK_PUBLISHABLE_KEY`).

**B. Production instance — requires a domain you own** (Clerk production needs DNS records on your domain, which an
`onrender.com` subdomain cannot provide)
1. Clerk → **Production** → add your domain (e.g. `netcoop.example.org`) and create the DNS records Clerk lists.
2. Google Cloud Console → APIs & Services → **OAuth consent screen**: External, app name, support email, authorized
   domain = your domain → **Publish app**. Then **Credentials → Create OAuth client ID → Web application**; authorized
   redirect URI = the one Clerk shows under *Configure → SSO connections → Google → Use custom credentials*.
3. Paste the Google client ID/secret into that Clerk screen. Use the production `pk_live_…`/`sk_live_…` keys in Render and
   point your domain at the Render service (Render custom domain).

**C. Netlify (only if used):** set `VITE_CLERK_PUBLISHABLE_KEY` and `VITE_API_BASE` in Netlify; add the Netlify origin to
Render's `NETCOOP_CORS_ORIGINS` (it then also becomes an authorized party).

**D. Verify:** open the site in a private window → Continue with Google → land on `/command` → Run diagnosis (S19) →
Export report → reload (still signed in) → sign out; sign in with a second Google account and confirm the first account's
investigation is not listed.

## Rollback

Remove `NETCOOP_AUTH_MODE` and `VITE_CLERK_PUBLISHABLE_KEY` in Render and redeploy (the frontend must be rebuilt
without the key, otherwise it would keep sending Clerk tokens to a token-mode backend). The previous release is tagged
`pre-clerk-auth-2026-11-01`. Migration 0003 is additive (one nullable column) and needs no rollback.
