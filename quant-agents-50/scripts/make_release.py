#!/usr/bin/env python3
"""Build the download: one zip of the project, ready to unzip and run setup.

    python scripts/make_release.py              # writes dist/QuantAgents-50-v<version>.zip
    python scripts/make_release.py --out PATH   # somewhere else

Only the project's own files go in: no .venv, no caches, and none of your data, paper account,
logs or secrets (``data/``, ``state/``, ``runs/`` and ``.env`` are always left out).
"""

from __future__ import annotations

import argparse
import hashlib
import re
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TOP = "QuantAgents-50"
# your own data, account, logs and builds: left out only at the top of the project
# (src/quantagents/data/ and tests/data/ are part of the program and always go in)
TOP_LEVEL_NEVER = {".venv", "venv", "data", "state", "runs", "dist", "build"}
ANYWHERE_NEVER = {".git", "__pycache__", ".pytest_cache", ".mypy_cache", ".ruff_cache",
                  ".hypothesis", "htmlcov"}  # fmt: skip
NEVER_FILES = re.compile(r"(^\.env$|^\.env\.(?!example$)|\.pyc$|^\.coverage|\.egg-info|\.zip$)")


def version() -> str:
    match = re.search(r'^version = "([^"]+)"', (ROOT / "pyproject.toml").read_text("utf-8"), re.M)
    if match is None:
        raise SystemExit("no version in pyproject.toml")
    return match.group(1)


def project_files() -> list[Path]:
    """Files git knows about (tracked or new, not ignored), or a careful walk without git."""
    try:
        listed = subprocess.run(
            ["git", "ls-files", "-co", "--exclude-standard"],
            cwd=ROOT, capture_output=True, text=True, check=True,
        ).stdout.splitlines()  # fmt: skip
        candidates = [ROOT / name for name in listed]
    except (OSError, subprocess.CalledProcessError):
        candidates = [p for p in ROOT.rglob("*") if p.is_file()]
    keep: list[Path] = []
    for path in candidates:
        rel = path.relative_to(ROOT)
        if not path.is_file() or rel.parts[0] in TOP_LEVEL_NEVER:
            continue
        if set(rel.parts[:-1]) & ANYWHERE_NEVER:
            continue
        if any(NEVER_FILES.search(part) for part in rel.parts):
            continue
        keep.append(path)
    return sorted(keep)


def build(out: Path) -> tuple[Path, int, str]:
    out.parent.mkdir(parents=True, exist_ok=True)
    files = project_files()
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=9) as zf:
        for path in files:
            rel = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(f"{TOP}/{rel}", date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            mode = 0o755 if rel.endswith(".sh") else 0o644
            info.external_attr = (0o100000 | mode) << 16
            zf.writestr(info, path.read_bytes())
    digest = hashlib.sha256(out.read_bytes()).hexdigest()
    return out, len(files), digest


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", help="zip path (default dist/QuantAgents-50-v<version>.zip)")
    args = parser.parse_args(argv)
    out = Path(args.out) if args.out else ROOT / "dist" / f"{TOP}-v{version()}.zip"
    path, count, digest = build(out)
    print(f"Wrote {path} ({count} files, {path.stat().st_size / 1e6:.1f} MB)")
    print(f"SHA-256 {digest}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
