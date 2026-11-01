# NetCoop AI — submission guide

**Repository:** https://github.com/RajRai77/netcoop-ai (branch `gate0-skeleton`) · full documentation: [README.md](README.md)

## Try it in two minutes

1. Install [uv](https://docs.astral.sh/uv/getting-started/installation/) (it fetches Python 3.12 if needed).
2. From the release ZIP (or a clone): `./start.sh` — Windows: `powershell -ExecutionPolicy Bypass -File start.ps1`.
3. Open http://127.0.0.1:8000/ → **Explore Command Center** → **Run diagnosis** (organizer data is preselected).

Self-check without a browser: `uv run python scripts/run_local.py --check` (starts the four processes, runs a real
A2A diagnosis, verifies it, stops; exit code 0 = pass).

Hosted demo: https://netcoop-ai-07i3.onrender.com — sign in with Google (Clerk) when sign-in is enabled
([docs/27](docs/27_AUTHENTICATION.md)); your investigations are private to your account. Status: [docs/26](docs/26_HOSTED_DEPLOYMENT.md).

## What to look at

| In the app | What it shows |
|---|---|
| Command Center → *Agent collaboration & reasoning flow* | three agents working in parallel, STEaR rounds, the verification request, the conclusion |
| Datasets & Upload → **ORG-03-hardware-failure** | the organizer's sample-generator data, diagnosed with a calibrated confidence |
| Datasets & Upload → **ORG-04-schema-drift** | renamed fields, bad units, missing IDs and duplicates, each reported and none coerced |
| Sidebar → **Verification showcase · AP down** (S19) | first round ambiguous → the infrastructure agent is asked for `device_status` of AP-2-1 → diagnosed |
| Agent Collaboration → any card | the raw A2A/NDEP artifact exactly as exchanged |
| Reports → JSON / Export | the PS-format structured JSON report |
| Evaluation | held-out results: **59/60 acceptable outcomes on internally generated synthetic scenarios** (not real-world accuracy) |

## Demo recording workflow (3–5 minutes)

1. `./start.sh`, open http://127.0.0.1:8000/ (landing page: problem, approach, how it works). *(30 s)*
2. **Command Center** → sidebar **Run diagnosis** with *Organizer · hardware failure*. Narrate the flow diagram as it fills:
   three agents in parallel over A2A, STEaR conclusion, data label "Organizer data · PS sample generator", calibrated
   confidence with its basis. *(60 s)*
3. Sidebar → **Verification showcase · AP down** → Run. Show round 1 *ambiguous* (AP down vs switch-port failure), the
   **ASKED TO VERIFY** request to the Infrastructure agent, the returned archived observations, round 2 *diagnosed*. *(75 s)*
4. **Agent Collaboration** → open an exchange to show the raw A2A artifact. **Evidence Explorer** → open an observation to
   show units, quality flags and the raw record. *(45 s)*
5. **Datasets & Upload** → run **ORG-04-schema-drift**; show the reported rejected/duplicate records. *(30 s)*
6. **Reports** → JSON view and **Export JSON**; mention `confidence`, `alternative_causes`, `limitations`. *(30 s)*
7. **Evaluation** → read the caveat line aloud. *(15 s)*

## Release integrity

The release ZIP is built by `uv run python scripts/make_release.py --verify` from a clean commit (tracked files + the
React app built from that commit) and verified from a clean extraction. Its SHA-256 is published next to the file
(`release/*.zip.sha256`) and in the release notes.
