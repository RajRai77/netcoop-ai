"""Locate and load the NDEP contract files in spec/.

In a source checkout (editable install) the files live in <repo>/spec. In a built
wheel/container they are packaged as netcoop/_spec (see pyproject force-include).
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator, FormatChecker

_PKG = Path(__file__).resolve().parent


def spec_dir() -> Path:
    for candidate in (_PKG / "_spec", _PKG.parents[1] / "spec"):
        if (candidate / "metric_registry.json").is_file():
            return candidate
    raise FileNotFoundError(
        "NDEP spec files not found (looked for netcoop/_spec and <repo>/spec). "
        "Reinstall with `uv sync --locked` from the repository root."
    )


@lru_cache(maxsize=None)
def load_json(name: str) -> dict:
    return json.loads((spec_dir() / name).read_text(encoding="utf-8"))


@lru_cache(maxsize=None)
def validator(schema_name: str) -> Draft202012Validator:
    """Validator for e.g. 'observation' -> spec/observation.schema.json (with format checks)."""
    schema = load_json(f"{schema_name}.schema.json")
    return Draft202012Validator(schema, format_checker=FormatChecker())
