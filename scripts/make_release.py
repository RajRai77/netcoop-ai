"""Build and verify the submission ZIP.

    uv run python scripts/make_release.py            # build release/netcoop-ai-<commit>.zip (+ .sha256)
    uv run python scripts/make_release.py --verify   # ...and verify it from a clean extraction

Contents: `git archive` of HEAD (tracked files only, so no .env, local data or untracked files) plus the React
app built from the same commit (frontend/dist) so no Node.js is needed to run it. Refuses to build from a dirty
working tree. --verify extracts into an empty temporary folder, runs `uv sync --locked` and the launcher's own
end-to-end check (API + three A2A agents + React app), and scans the archive for secret-like content.
"""

from __future__ import annotations

import argparse
import hashlib
import io
import re
import shutil
import subprocess
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "release"
SECRET = re.compile(rb"(?i)(postgres(ql)?://[^\s:@/]+:[^\s@/]{6,}@(?!host\b|HOST\b|USER)|-----BEGIN [A-Z ]*PRIVATE KEY|ghp_[0-9A-Za-z]{30,}|sk-[0-9A-Za-z]{30,})")


def sh(cmd: list[str], cwd: Path = ROOT, **kw) -> str:
    print("$", " ".join(cmd), flush=True)
    return subprocess.run(cmd, cwd=cwd, check=True, text=True, capture_output=kw.pop("capture", False), **kw).stdout or ""


def build() -> Path:
    dirty = subprocess.run(["git", "status", "--porcelain", "--untracked-files=no"], cwd=ROOT, text=True,
                           capture_output=True, check=True).stdout.strip()
    if dirty:
        raise SystemExit(f"working tree has uncommitted changes; commit first:\n{dirty}")
    commit = sh(["git", "rev-parse", "--short=12", "HEAD"], capture=True).strip()
    npm = shutil.which("npm") or shutil.which("npm.cmd")
    if not npm:
        raise SystemExit("npm is required to build the React app for the release")
    sh([npm, "ci", "--no-audit", "--no-fund"], cwd=ROOT / "frontend")
    sh([npm, "run", "build"], cwd=ROOT / "frontend")
    OUT.mkdir(exist_ok=True)
    prefix = f"netcoop-ai-{commit}/"
    zpath = OUT / f"netcoop-ai-{commit}.zip"
    archive = subprocess.run(["git", "archive", "--format=zip", f"--prefix={prefix}", "HEAD"], cwd=ROOT,
                             capture_output=True, check=True).stdout
    with zipfile.ZipFile(io.BytesIO(archive)) as src, zipfile.ZipFile(zpath, "w", zipfile.ZIP_DEFLATED) as dst:
        for info in src.infolist():
            dst.writestr(info, src.read(info))
        dist = ROOT / "frontend" / "dist"
        for f in sorted(p for p in dist.rglob("*") if p.is_file()):
            dst.write(f, prefix + "frontend/dist/" + f.relative_to(dist).as_posix())
        dst.writestr(prefix + "RELEASE.txt",
                     f"NetCoop AI release\ncommit: {sh(['git', 'rev-parse', 'HEAD'], capture=True).strip()}\n"
                     "contents: git archive of the commit + frontend/dist built from it\n"
                     "run: ./start.sh  (Windows: powershell -ExecutionPolicy Bypass -File start.ps1)\n")
    digest = hashlib.sha256(zpath.read_bytes()).hexdigest()
    (OUT / f"{zpath.name}.sha256").write_text(f"{digest}  {zpath.name}\n", encoding="utf-8")
    print(f"built {zpath.relative_to(ROOT)} ({zpath.stat().st_size / 1e6:.1f} MB)\nSHA-256 {digest}")
    return zpath


def verify(zpath: Path) -> None:
    with zipfile.ZipFile(zpath) as z:
        names = z.namelist()
        bad = [n for n in names if re.search(r"(^|/)(\.env|.*\.db|node_modules/|\.venv/)", n) and not n.endswith(".env.example")]
        if bad:
            raise SystemExit(f"release contains files that must not ship: {bad[:5]}")
        hits = [n for n in names if not n.endswith("/") and SECRET.search(z.read(n))]
        if hits:
            raise SystemExit(f"secret-like content in: {hits}")
        print(f"archive: {len(names)} entries, no .env / databases / node_modules, no secret-like content")
        tmp = Path(tempfile.mkdtemp(prefix="netcoop-release-"))
        z.extractall(tmp)
    root = next(tmp.iterdir())
    assert (root / "frontend" / "dist" / "index.html").is_file(), "prebuilt React app missing"
    uv = shutil.which("uv") or "uv"
    sh([uv, "sync", "--locked"], cwd=root)
    sh([uv, "run", "python", "scripts/run_local.py", "--check", "--port", "auto", "--data-dir", str(tmp / "data")], cwd=root)
    print(f"VERIFIED: clean extraction at {root} installs from the lockfile and passes the end-to-end check")


def main() -> int:
    p = argparse.ArgumentParser()
    p.add_argument("--verify", action="store_true")
    p.add_argument("--zip", help="verify an existing ZIP instead of building")
    a = p.parse_args()
    z = Path(a.zip) if a.zip else build()
    if a.verify or a.zip:
        verify(z)
    return 0


if __name__ == "__main__":
    sys.exit(main())
