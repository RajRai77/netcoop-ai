# Evaluation methodology

**Results are generated, not typed:** `uv run python scripts/evaluate.py` writes `eval/results/results.json` (every case, every method) and renders `eval/results/RESULTS.md` from it. Any number quoted elsewhere must be traceable to that file and the commit it records.

## Data

| set | where | size | how it was used |
|---|---|---|---|
| dev | `data/scenarios/` (committed) | 17 hand-specified scenarios on a 2x2 campus | **Used during development.** Two engine/model fixes were made after seeing dev failures (service kinds for DNS/DHCP localization; interface-degradation contradiction rule + "unexplainable symptoms -> unknown_fault"). Dev numbers are therefore optimistic. |
| held-out | `data/heldout/` (regenerated: `scripts/generate_scenarios.py --heldout`, seed 20261101) | 60 randomized scenarios on a 3x3 campus | Generated **after** the knowledge freeze (commit `20b551b`, fingerprint fix `2ff9bca`). Each ground-truth file records the SHA-256 of the canonical knowledge JSON; the evaluator reports whether they still match. |

All data are **synthetic** (`data_mode = synthetic`). Ground truth comes from the generator's injected faults; the generator propagates effects with its own tree logic, not the engine's topology module. **Caveat:** the same team wrote the generator and the engine, so this is an internal-consistency and robustness evaluation, not an independent benchmark. No organizer dataset was available at the time of writing.

Held-out variation: fault type and location, severity (12 % "subtle" cases with sub-threshold signatures), onset time, compound faults (2 concurrent), unmodeled faults, transient spikes, malformed/stale/unknown-device records, and the information condition:
`full` (everything uploaded), `probes+archive` (only end-to-end probes uploaded; device data only in the recorded archive), `probes-only` (nothing else exists), `signature-in-archive` (everything except the fault's signature source).

## Methods (same initial observations for all)

| method | description |
|---|---|
| `A_threshold` | Centralized threshold alerting: highest-priority fired detector names the cause at its own subject. |
| `B_centralized` | STEaR hypothesis engine without topology and without temporal checks; no verification. |
| `C_stear_noverify` | STEaR with topology and temporal checks; no active verification. |
| `D_full` | C + bounded evidence-seeking verification (max 2 rounds, 6 checks; agents may only return recorded archive data). |
| `D_full_no_topology`, `D_full_no_temporal` | Ablations of D. |

Specialists run in-process for evaluation speed. The same specialist code and NDEP payloads run over real A2A in `tests/integration/test_a2a_agents.py`, which asserts identical status, cause, support category and affected devices for representative scenarios.

## Metrics

- `acceptable_outcome`: correct cause when the data allow it (exact set of fault type + location); an abstention (`ambiguous` / `insufficient_evidence` / `unknown_fault`) when they do not; `healthy` for healthy cases; an abstention for unmodeled faults.
- `exact_cause_on_diagnosable`, `fault_type_on_diagnosable`, `localization_on_diagnosable`: over cases whose signature data were available to that method (initial upload for A-C; upload + archive for D).
- `confident_wrong_all`: status `diagnosed` with a wrong cause set (the most harmful error).
- `high_support_wrong_all`: wrong while labelled `high_support`.
- `abstained_when_not_diagnosable`, `false_healthy_on_faulty`, `healthy_correct`, `unknown_detected`, `multi_fault_full_recall`.
- Cost: `checks_requested_total`, `checks_obtained_total`; latency: per-incident wall-clock seconds on the machine recorded in the results (includes ingestion-free coordination; not an SLO).

Support categories are documented decision rules (`docs/05`, `src/netcoop/engine/stear.py`); **no probabilities are produced or calibrated**. Calibration metrics (Brier/ECE) are therefore not applicable.

## Known limitations of this evaluation

- Synthetic data from one generator family; real campus telemetry would differ (noise, missingness, naming).
- Detector thresholds were chosen by the developers; they were frozen before the held-out set was generated but were not fitted on independent data.
- The archive represents recorded collector history; no live read-only collectors were exercised.
- Single run per scenario (deterministic); latency measured on a developer laptop.
