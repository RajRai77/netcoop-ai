"""Start NetCoop AI locally (Windows or Linux, no Docker).

    uv sync --locked
    uv run python scripts/run_local.py            # Ctrl+C to stop
    uv run python scripts/run_local.py --check    # start, smoke-test, stop
    uv run python scripts/run_local.py --help
"""

import sys

try:
    from netcoop.launcher import main
except ImportError as exc:  # not inside the project environment
    print(
        f"NetCoop is not installed in this Python environment ({exc}).\n"
        "From the repository root run:\n"
        "    uv sync --locked\n"
        "    uv run python scripts/run_local.py",
        file=sys.stderr,
    )
    sys.exit(2)

sys.exit(main())
