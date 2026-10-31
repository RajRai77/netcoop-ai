"""Regenerate the synthetic scenario sets (deterministic).

    uv run python scripts/generate_scenarios.py            # dev set -> data/scenarios
    uv run python scripts/generate_scenarios.py --heldout  # held-out set -> data/heldout
"""

import argparse
import sys
from pathlib import Path

from netcoop.scenarios.catalog import DEV_SCENARIOS
from netcoop.scenarios.generator import write_scenario

ROOT = Path(__file__).resolve().parents[1]


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--heldout", action="store_true")
    p.add_argument("--out", default=None)
    p.add_argument("--seed", type=int, default=20261101, help="held-out seed (v1: 20261101, v2: 20261102)")
    args = p.parse_args()
    if args.heldout:
        from netcoop.scenarios.heldout import heldout_specs

        out = Path(args.out or ROOT / "data" / "heldout")
        specs, split = heldout_specs(seed=args.seed), "heldout"
    else:
        out = Path(args.out or ROOT / "data" / "scenarios")
        specs, split = DEV_SCENARIOS, "dev"
    for spec in specs:
        d = write_scenario(out, spec, split)
        print(f"wrote {d.relative_to(ROOT) if d.is_relative_to(ROOT) else d}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
