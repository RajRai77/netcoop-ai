# Provenance of the held-out v3 results

- **Data:** `data/heldout-v3`, seed 20261103. It was generated after knowledge freeze v3. The ground-truth files record the knowledge SHA-256, and the evaluator reports `knowledge_frozen_before_generation: True`.
- **Recorded commit:** `results.json` says `95e3e6e`. The run started 2026-11-01 03:02:51 IST.
- **The run did not use an exact `95e3e6e` snapshot.** The working tree at start also contained uncommitted changes:
  - `src/netcoop/evaluation/runner.py`: a fresh SQLite file per scenario instead of one shared file;
  - `src/netcoop/storage/engine.py`: SQLite `journal_mode=WAL`, `synchronous=FULL`;
  - API/CLI/launcher/config files that the evaluator does not import.
  
  All diagnosis-logic files (`engine/`, `agents/`, `knowledge/`, `evidence/`, `scenarios/`, `ledger.py`, `topology.py`, planner, coordinator) were byte-identical to `95e3e6e` at start.
- **Edits during the run:** `orchestration/coordinator.py` and `orchestration/ports.py` were modified at 03:25:18. Both are top-level imports of the evaluator, so they were loaded at process start. Nothing on the evaluation path reloads modules or starts another Python process (the only subprocess is `git rev-parse`). Even if picked up, neither change could alter v3 outcomes:
  - the stale-topology limitation only fires when the topology is >24 h older than the evidence; v3 topologies share the evidence timestamp;
  - the protocol check is in the A2A port, which the in-process evaluation does not use.
- **Empirical check:** 11 scenarios × 4 methods (44 cases) were replayed with code imported only from a clean `git worktree` at `95e3e6e`, with one fresh SQLite file per scenario created by an external driver. The selection covered:
  - every case where verification changed acceptability;
  - both AP-down cases and all three healthy-coverage cases;
  - all compound and unmodeled cases;
  - the four scenarios with the most verification checks.
  
  **Result: 44/44 identical** in status, support category, root cause, causes, checks requested/obtained, new observations and score.
- **Remaining uncertainty:** the other 49 scenarios were not replayed. Their equivalence rests on the code comparison above, not on a replay.
- **Process fix:** the evaluator now records `code.diagnosis_code_sha256` and `code.uncommitted_changes` in every future `results.json`.
