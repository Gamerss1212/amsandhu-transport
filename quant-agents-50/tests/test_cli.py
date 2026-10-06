from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest

from quantagents.cli import main
from quantagents.risk.killswitch import RESET_PHRASE


@pytest.fixture
def workdir(tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    shutil.copytree(repo_root / "config", tmp_path / "config")
    monkeypatch.chdir(tmp_path)
    return tmp_path


def set_phase(workdir: Path, phase: int) -> None:
    path = workdir / "config" / "default.yaml"
    text = path.read_text(encoding="utf-8")
    path.write_text(text.replace("  phase: 4 ", f"  phase: {phase} ", 1), encoding="utf-8")


def test_demo_prints_a_full_cycle(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["demo", "--save"]) == 0
    out = capsys.readouterr().out
    assert "The 15 steps" in out and "15. Learn" in out and "GO" in out
    for section in ("Market regime (A06)", "Transition check (A07)", "Liquidity (A09"):
        assert section in out
    assert "Stress test (A45" in out and "Scorekeeper (A35" in out
    assert "Paper trading only" in out
    saved = workdir / "runs" / "demo-2026-09-30"
    assert (saved / "audit.jsonl").exists() and json.loads((saved / "report.json").read_text())[
        "phase"
    ] == 4
    assert main(["audit", "--path", str(saved / "audit.jsonl")]) == 0
    assert main(["demo", "--save"]) == 0  # re-running replaces the saved demo log


def test_agents_config_and_errors(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["agents"]) == 0
    out = capsys.readouterr().out
    assert "A49" in out and "Core: 25 of 25 built" in out and "Parked for later: 25" in out
    assert "built, shadow" in out and "parked" in out
    assert main(["agents", "--core"]) == 0
    assert "parked" not in capsys.readouterr().out.split("Core:")[0]
    assert main(["agents", "--phase", "1"]) == 0
    assert "A11" not in capsys.readouterr().out
    assert main(["config"]) == 0
    assert "Config is valid" in capsys.readouterr().out
    assert main(["backtest", "--strategy", "tsmom", "--variant", "nope"]) == 2
    assert "unknown variant" in capsys.readouterr().err


def test_killswitch_commands(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["killswitch", "status"]) == 0
    assert "armed" in capsys.readouterr().out
    assert main(["killswitch", "engage", "--reason", "testing"]) == 0
    assert main(["killswitch", "status"]) == 0
    assert "ENGAGED: testing" in capsys.readouterr().out
    assert main(["killswitch", "reset", "--confirm", "please"]) == 2
    assert main(["killswitch", "reset", "--confirm", RESET_PHRASE]) == 0


def test_paper_loop_on_csv(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    set_phase(workdir, 3)  # the phase 3 stand-in combiner says GO on 30 Sep
    assert main(["make-data", "--out", "data/prices.csv"]) == 0
    assert main(["cycle", "--data", "data/prices.csv", "--as-of", "2026-09-30"]) == 0
    first = capsys.readouterr().out
    assert "queued for the next session's open" in first
    state = json.loads((workdir / "state" / "paper_account.json").read_text())
    assert state["pending"], "the 30 Sep GO decision should be queued"
    assert main(["cycle", "--data", "data/prices.csv", "--as-of", "2026-10-01"]) == 0
    second = capsys.readouterr().out
    assert "fill(s) from earlier orders and stops" in second
    state = json.loads((workdir / "state" / "paper_account.json").read_text())
    assert state["ledger_fills"]
    assert all(p["decision_date"] != "2026-09-30" for p in state["pending"])
    assert main(["audit"]) == 0
    assert main(["acb"]) == 0
    assert "Informational only" in capsys.readouterr().out
    assert len(list((workdir / "runs" / "cycles").glob("*.json"))) == 2


def test_cycle_keeps_a35_memory(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["make-data", "--out", "data/prices.csv"]) == 0
    assert main(["cycle", "--data", "data/prices.csv", "--as-of", "2026-09-01"]) == 0
    memory = json.loads((workdir / "state" / "scorekeeper.json").read_text())
    assert memory["records"] and all(r["outcome"] is None for r in memory["records"])
    capsys.readouterr()
    assert main(["cycle", "--data", "data/prices.csv", "--as-of", "2026-09-30"]) == 0
    out = capsys.readouterr().out
    memory = json.loads((workdir / "state" / "scorekeeper.json").read_text())
    assert any(r["outcome"] is not None for r in memory["records"])  # 1 Sep has matured
    assert "Scorekeeper (A35" in out


def test_simulate_and_stress(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["simulate", "--days", "12"]) == 0
    out = capsys.readouterr().out
    assert "Paper simulation: 12 trading days" in out and "SYNTHETIC" in out
    assert "Why symbols were not traded" in out and "Risk levels" in out
    assert main(["stress", "--strategy", "sma"]) == 0
    out = capsys.readouterr().out
    assert "A45 Monte Carlo: sma_200" in out and "2x cost stress" in out
    assert "Chance of a losing year" in out
    assert main(["simulate", "--days", "100000"]) == 2


def test_backtest_and_validate(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["backtest", "--strategy", "sma"]) == 0
    assert "Backtest: sma_200" in capsys.readouterr().out
    assert main(["validate", "--strategy", "tsmom"]) == 0
    out = capsys.readouterr().out
    assert "A44 validation" in out and "A39 red team" in out and "6 variant(s)" in out


def test_tampered_audit_log_fails(workdir: Path, capsys: pytest.CaptureFixture[str]) -> None:
    main(["demo", "--save"])
    path = workdir / "runs" / "demo-2026-09-30" / "audit.jsonl"
    lines = path.read_text(encoding="utf-8").splitlines()
    record = json.loads(lines[0])
    record["kind"] = "edited"
    lines[0] = json.dumps(record)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    assert main(["audit", "--path", str(path)]) == 1
    assert "TAMPERED" in capsys.readouterr().out
