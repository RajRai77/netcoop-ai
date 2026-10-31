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

## Results so far (numbers copied from the generated RESULTS.md files)

| held-out run | knowledge | file | D_full acceptable | D_full confident-wrong | D_full high-support-wrong | false healthy (C/D) |
|---|---|---|---|---|---|---|
| v1 (seed 20261101, 60 cases) | fault-library/1, commit 2ff9bca | `eval/results-frozen-2ff9bca/RESULTS.md` | 49/60 | 3/60 | 3/60 | 8/53 |
| v2 (seed 20261102, 60 cases) | fault-library/2, commit 013a6d5 | `eval/results-heldout-v2/RESULTS.md` | 53/60 | 6/60 | 0/60 | 0/56 |
| v3 (seed 20261103, 60 cases; methods A-D only) | fault-library/3, commit 95e3e6e (+ uncommitted persistence-only changes, see `eval/results-heldout-v3/PROVENANCE.md`) | `eval/results-heldout-v3/RESULTS.md` | 59/60 | 1/60 | 0/60 | 0/56 |

On v2, STEaR without verification (C) has 55/60 acceptable vs 53/60 for full (D). D makes 39 exact diagnoses (of 46 diagnosable with
the archive) vs 20 for C (of 22 diagnosable from the upload alone): verification turns many otherwise-abstained incidents into correct
diagnoses but also adds wrong ones. Ablation: removing topology from D drops acceptable outcomes to 36/60. Threshold baseline: 18/60.

**Remaining failure pattern (v2):** five of D's seven failures are an access point down being reported as
`LINK_OR_PATH_FAILURE` on the switch port facing it, with `moderate_support`. The synthetic NMS publishes `device_status` only for
switches, not APs, so the AP-down signature is never observable; both explanations fit, and the engine still picks the confirmed
link failure instead of reporting ambiguity. Candidate rule change (not yet made; would need a v3 held-out set): when the leading
cause is confirmed but an equal-coverage competitor's signature is *unobservable*, report `ambiguous`. The other two failures are
compound faults where only one of two faults was reported (now `moderate_support`, no longer `high_support`).

**Annotation caveat for v1/v2 (found 2026-11-01):** the generator never emitted AP status in v1/v2, yet the ground truth
annotated AP-down faults as diagnosable from NMS data. Their AP-down cases were therefore scored as "diagnosable" although the
evidence could not identify them. The result files are kept unchanged; v3 uses the corrected annotation and a generator in
which the wireless controller reports a failed AP.

**v3 summary (from `eval/results-heldout-v3/RESULTS.md`):** acceptable outcomes A 22/60, B 42/60, C 57/60, D 59/60; confidently wrong A 30, B 4, C 0, D 1; high-support wrong B 1, others 0.
Compared with C on the same cases, verification helped in 3 cases (healthy networks whose unmonitored DNS/DHCP/wireless coverage
was fetched from the archive), harmed 1 (V03-014: a subtle compound fault where C abstained and D reported only the CPU overload,
missing the wireless interference, at `moderate_support`), and made a correct diagnosis more specific in 22 cases where C had
correctly abstained. AP-down: the only two AP-down cases behaved as intended (probes-only -> `ambiguous`, checks unavailable;
full data -> correct `DEVICE_DOWN at AP`). Weaknesses that remain: unmodeled faults are reported as `ambiguous`, never
`unknown_fault` (0/4), because a plausible modeled hypothesis remains unverifiable; compound recall 1/2; C cannot declare
`healthy` when service domains are unmonitored (by design, 1/4). v3 is still synthetic and same-author.
