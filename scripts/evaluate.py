"""Run the reproducible evaluation (baselines, NetCoop, ablations) and save results.

    uv run python scripts/evaluate.py                    # dev + held-out sets -> eval/results/
    uv run python scripts/evaluate.py --sets dev         # only the dev set
    uv run python scripts/evaluate.py --out eval-ci

Writes results.json (every case) and RESULTS.md (rendered from results.json).
"""

import argparse
import json
import sys
from pathlib import Path

from netcoop.evaluation.runner import evaluate, to_markdown

ROOT = Path(__file__).resolve().parents[1]
SETS = {"dev": ROOT / "data" / "scenarios", "heldout": ROOT / "data" / "heldout"}


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--sets", nargs="*", default=["dev", "heldout"], choices=sorted(SETS))
    p.add_argument("--out", default=str(ROOT / "eval" / "results"))
    args = p.parse_args()
    sets = {s: SETS[s] for s in args.sets if SETS[s].is_dir()}
    missing = sorted(set(args.sets) - set(sets))
    if missing:
        print(f"skipping missing sets {missing} (generate with scripts/generate_scenarios.py [--heldout])")
    res = evaluate(sets)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    (out / "results.json").write_text(json.dumps(res, indent=1, default=list), encoding="utf-8")
    (out / "RESULTS.md").write_text(to_markdown(res), encoding="utf-8")
    print(f"wrote {out / 'results.json'} and {out / 'RESULTS.md'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
