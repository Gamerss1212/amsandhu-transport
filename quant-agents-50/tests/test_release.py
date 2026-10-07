"""The download zip: complete program, none of the owner's data or secrets."""

from __future__ import annotations

import importlib.util
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def load_builder() -> object:
    spec = importlib.util.spec_from_file_location(
        "make_release", ROOT / "scripts" / "make_release.py"
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_the_zip_has_the_whole_program_and_nothing_private(tmp_path: Path) -> None:
    builder = load_builder()
    out, count, digest = builder.build(tmp_path / "release.zip")  # type: ignore[attr-defined]
    names = set(zipfile.ZipFile(out).namelist())
    assert count == len(names) and len(digest) == 64
    top = "QuantAgents-50/"
    for need in (
        "START_HERE.md", "QuantAgents.bat", "QuantAgents.sh", "setup.bat", "daily.bat",
        "status.bat", "setup.sh", "pyproject.toml", "docs/REAL_MONEY.md",
        "src/quantagents/web/index.html", "src/quantagents/web/app.js", "src/quantagents/web/app.css",
        "src/quantagents/data/store.py", "src/quantagents/cli.py", "tests/data/yahoo_spy_2024_03.json",
        "config/default.yaml", "config/us_etfs.example.yaml", ".env.example", "docs/STATUS.md",
    ):  # fmt: skip
        assert top + need in names, need
    try:
        tracked = subprocess.run(
            ["git", "ls-files", "src", "tests"],
            cwd=ROOT,
            capture_output=True,
            text=True,
            check=True,
        ).stdout.split()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("git not available")
    missing = [t for t in tracked if top + t not in names]
    assert missing == [], missing  # every program and test file ships
    for name in names:
        rel = name.removeprefix(top)
        assert rel.split("/")[0] not in {".venv", "data", "state", "runs", "dist"}, name
        assert "__pycache__" not in name and not name.endswith((".pyc", ".zip"))
        assert rel != ".env" and ".egg-info" not in name
    for script in ("setup.sh", "QuantAgents.sh"):
        info = zipfile.ZipFile(out).getinfo(top + script)
        assert (info.external_attr >> 16) & 0o111  # shell scripts stay executable


def test_windows_scripts_use_windows_line_endings() -> None:
    for bat in ROOT.glob("*.bat"):
        data = bat.read_bytes()
        assert data.count(b"\r\n") == data.count(b"\n"), bat.name  # cmd.exe needs CRLF
