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


def test_the_developer_zip_has_the_whole_program_and_nothing_private(tmp_path: Path) -> None:
    builder = load_builder()
    out, count, digest = builder.build(tmp_path / "release.zip", full=True)  # type: ignore[attr-defined]
    names = set(zipfile.ZipFile(out).namelist())
    assert count == len(names) and len(digest) == 64
    top = "QuantAgents-50/"
    for need in (
        "START_HERE.md", "QuantAgents.bat", "QuantAgents.sh", "setup.bat", "daily.bat",
        "setup.sh", "pyproject.toml", "docs/REAL_MONEY.md",
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


def test_the_owners_zip_has_only_what_running_needs(tmp_path: Path) -> None:
    builder = load_builder()
    out, count, _ = builder.build(tmp_path / "owner.zip")  # type: ignore[attr-defined]
    top = "QuantAgents-50/"
    names = {n.removeprefix(top) for n in zipfile.ZipFile(out).namelist()}
    assert count == len(names)
    assert {n for n in names if not n.startswith("program/")} == {
        "QuantAgents.bat",
        "START_HERE.md",
    }
    top += "program/"  # one file to double-click; everything else sits in program/
    names = {n.removeprefix("program/") for n in names if n.startswith("program/")}
    outside_src = {n for n in names if not n.startswith(("src/", "config/"))}
    assert outside_src == {
        "QuantAgents.sh", "setup.bat", "setup.sh", "daily.bat", "daily.sh",
        ".env.example", "pyproject.toml",
        "docs/REAL_MONEY.md", "docs/schedule.md", "docs/STATUS.md",
    }  # fmt: skip
    assert "src/quantagents/web/index.html" in names and "config/agents.yaml" in names
    assert not any(n.startswith(("tests/", ".claude/")) or "SPEC" in n for n in names)
    with zipfile.ZipFile(out) as zf:
        status = zf.read(top + "docs/STATUS.md").decode("utf-8")
        launcher = zf.read("QuantAgents-50/QuantAgents.bat").decode("utf-8")
    assert "## Human approvals" in status and "| (none yet) | | |" in status
    assert 'if exist "program\\pyproject.toml" cd /d "%~dp0program"' in launcher
    for script in ("setup.sh", "QuantAgents.sh", "daily.sh"):
        info = zipfile.ZipFile(out).getinfo(top + script)
        assert (info.external_attr >> 16) & 0o111


def test_windows_scripts_use_windows_line_endings() -> None:
    for bat in ROOT.glob("*.bat"):
        data = bat.read_bytes()
        assert data.count(b"\r\n") == data.count(b"\n"), bat.name  # cmd.exe needs CRLF
