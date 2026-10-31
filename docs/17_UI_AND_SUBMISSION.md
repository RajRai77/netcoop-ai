# Browser UI, truthful demonstration and hackathon submission

## Minimal functional browser journey (additional user requirement)

1. Landing page shows platform status, **explicit data mode label** and no fake 'live campus network' claims.
2. Upload supported telemetry/manifest or select a clearly documented recorded/synthetic scenario.
3. Start case; see case ID and actual workflow/task states.
4. View each specialist's real A2A contributions, structured finding IDs and evidence references.
5. If ambiguous, view selected verification request and whether additional data was truly obtained.
6. View graph/affected components when topology exists; otherwise explicit topology-missing limitation.
7. Download JSON report satisfying schema and human-readable explanation; inspect alternatives/limitations.

**No requirement for fancy UI animation.** The original PS permits a CLI. The user additionally wants public deployment, so a small robust browser UI is prioritized over a large SPA.

## Required report sections

Probable root cause or absence, confidence **category**, affected devices/segments if identifiable, supporting evidence with units + source references, alternative causes, recommended manual checks/actions, limitations, time/snapshot/version and data provenance.

## 3–5 minute official demo — recommended sequence

- Architecture at a glance and *actually running* service health.
- Run one normal or simple scenario and demonstrate true specialist tasks and JSON output.
- Run one ambiguous congestion/interface case with **real targeted verification** or honest abstention.
- Run one incompatible-unit/malformed input and show typed error or quarantined data.
- Briefly show agent unavailability handling and clean rerun.
- End with honest scorecard, limitations and deployment URL/repository/test command.

Recording must show true execution, not edited stand-ins presented as live system results. Include original PS deliverables: GitHub repository, architecture README and test instructions, sample data/scenarios, 3–5 minute video, runnable CLI or dashboard.

## Release checklist

- [ ] Original PS mandatory acceptance proof
- [ ] JSON report passes schema with evidence IDs and documented confidence category
- [ ] >=2 independent A2A agent processes and real message exchange
- [ ] Demo mode/source visibly identified (synthetic, recorded, emulated or authorized live)
- [ ] Reproducible run commands and tests documented
- [ ] `docker compose` clean-server smoke / restart persistence / TLS verified
- [ ] No unauthenticated arbitrary probe endpoint or exposed DB
- [ ] Demonstration video 3–5 min and GitHub repository ready
- [ ] Research claims and benchmark scores supported by actual test output
