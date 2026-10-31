"""Write the live OpenAPI document of the NetCoop API to docs/openapi.json (for frontend integration).

    uv run python scripts/export_openapi.py
"""

import json
import sys
from pathlib import Path

from netcoop.api.app import create_app
from netcoop.config import Settings

ROOT = Path(__file__).resolve().parents[1]

if __name__ == "__main__":
    doc = create_app(Settings(database_url=None, resume_on_start=False)).openapi()
    out = ROOT / "docs" / "openapi.json"
    out.write_text(json.dumps(doc, indent=1, sort_keys=True), encoding="utf-8", newline="\n")
    print(f"wrote {out} ({len(doc['paths'])} paths)")
    sys.exit(0)
