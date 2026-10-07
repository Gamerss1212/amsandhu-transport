"""The research grid, its new strategies, the noise panels and the runner."""

from __future__ import annotations

import shutil
from collections import Counter
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from quantagents.backtest import library
from quantagents.backtest.grid import BENCHMARK, research_grid
from quantagents.backtest.strategies import strategy_grid
from quantagents.cli import main
from quantagents.config import AppConfig
from quantagents.data.synthetic import block_bootstrap_market
from quantagents.market import MarketData, save_csv
from quantagents.research import format_report, run_research, write_variants_csv
from quantagents.validation.leakage import RedTeamAuditor
from quantagents.validation.trials import logged_variants
from tests.helpers import path_market, wavy_market


def test_the_grid_is_the_pre_registered_one() -> None:
    grid = research_grid()
    assert len(grid) == 87
    assert len({v.name for v in grid}) == 87
    counts = Counter(v.family for v in grid)
    assert counts == {
        "tsmom": 6,
        "tsmom_blend": 12,
        "sma": 5,
        "sma_cross": 4,
        "faber": 4,
        "xs_mom": 24,
        "dual_mom": 6,
        "rsi2": 12,
        "vol_target": 10,
        "donchian": 3,
        "buy_and_hold": 1,
    }
    assert grid[-1].name == BENCHMARK


@pytest.mark.parametrize("family", ["sma_cross", "dual_mom", "donchian"])
def test_new_families_pass_the_red_team(family: str, market: MarketData) -> None:
    for variant in [v for v in research_grid() if v.family == family]:
        report = RedTeamAuditor(probes=3, window=20).audit(
            variant.factory, market, name=variant.name
        )
        assert report.passed and report.findings == (), (variant.name, report.findings)


def test_sma_cross_and_dual_momentum_follow_their_rules() -> None:
    market = wavy_market(("UP", "SLIDE", "DOWN"), n=400, drifts=(0.001, -0.0005, -0.002))
    view = market.view_at(399)
    assert library.sma_cross(50, 200)(market)(view) == {"UP": 1 / 3}
    assert library.dual_momentum(252, 1)(market)(view) == {"UP": 1.0}
    two = library.dual_momentum(252, 2)(market)(view)
    assert two == {"UP": 0.5}  # the second slot (SLIDE) is falling, so it stays in cash
    with pytest.raises(ValueError, match="fast < slow"):
        library.sma_cross(200, 50)


def test_donchian_buys_breakouts_and_sells_breakdowns() -> None:
    flat = [100.0 + 0.5 * ((-1) ** k) for k in range(80)]
    up = [flat[-1] * 1.01**k for k in range(1, 11)]
    down = [up[-1] * 0.97**k for k in range(1, 15)]
    market = path_market(flat + up + down, spread=0.001)
    strategy = library.donchian(20, 10)(market)
    held = [strategy(market.view_at(t)) for t in range(30, len(market))]
    first = next(i for i, w in enumerate(held) if w) + 30
    assert 80 <= first <= 82  # bought as the breakout cleared the 20-day high
    assert held[-1] == {}  # sold after a close below the 10-day low
    with pytest.raises(ValueError, match="at least 2"):
        library.donchian(1, 1)


def test_noise_panels_keep_daily_moves_but_shuffle_time() -> None:
    real = wavy_market(("AAA", "BBB"), n=300, drifts=(0.001, -0.001))
    a = block_bootstrap_market(real, seed=1)
    b = block_bootstrap_market(real, seed=1)
    c = block_bootstrap_market(real, seed=2)
    assert a.dates == real.dates and a.symbols == real.symbols
    assert np.array_equal(a.bars("AAA").close, b.bars("AAA").close)  # deterministic per seed
    assert not np.array_equal(a.bars("AAA").close, c.bars("AAA").close)
    real_moves = np.round(real.bars("AAA").close[1:] / real.bars("AAA").close[:-1], 12)
    new_moves = np.round(a.bars("AAA").close[1:] / a.bars("AAA").close[:-1], 12)
    assert set(new_moves.tolist()) <= set(real_moves.tolist())  # every day is a real day
    for s in a.symbols:
        bars = a.bars(s)
        assert np.all(bars.high >= np.maximum(bars.open, bars.close) - 1e-9)
        assert np.all(bars.low <= np.minimum(bars.open, bars.close) + 1e-9)
    with pytest.raises(ValueError, match="at least 3"):
        block_bootstrap_market(wavy_market(n=2), seed=1)


@pytest.fixture
def two_universes(tmp_path: Path, market: MarketData) -> dict[str, str]:
    first = tmp_path / "one.csv"
    save_csv(market, first)
    second = tmp_path / "two.csv"
    save_csv(MarketData(market.dates, {s: market.bars(s) for s in market.symbols[:3]}), second)
    return {"one": str(first), "two": str(second)}


def test_the_runner_judges_the_grid_as_one_experiment(
    two_universes: dict[str, str], tmp_path: Path
) -> None:
    trials = tmp_path / "trials.md"
    messages: list[str] = []
    report = run_research(
        two_universes,
        cfg=AppConfig(),
        noise=2,
        jobs=1,
        families=["tsmom", "faber"],
        run_date=date(2026, 10, 6),
        trials_path=trials,
        progress=messages.append,
    )
    k = 6 + 4 + 1  # tsmom + faber + the benchmark
    assert report.real_trials == 2 * k
    assert report.backtests == 2 * k * (2 + 2) + 3 * 2
    assert any("backtests done" in m for m in messages)
    for u in report.universes:
        assert len(u.variants) == k
        assert 0 <= u.pbo <= 1 and 0 <= u.spa_bh.p_value <= 1
        assert len(u.noise_best) == len(u.noise_excess) == 2
        assert 0 < u.noise_excess_p <= 1
        assert u.best != BENCHMARK and u.finalist is not None
        assert len(u.finalist.checks) == 6
        assert u.labels  # the data's caveats travel with the result
    text = format_report(report)
    assert "## one" in text and "## two" in text and "Finalist:" in text
    write_variants_csv(report, tmp_path / "grid.csv")
    assert len((tmp_path / "grid.csv").read_text().splitlines()) == 1 + 2 * k
    assert "tsmom_126@one" in logged_variants("tsmom", trials)
    assert "noise_control" in trials.read_text()


def test_research_cli_runs_in_parallel(
    two_universes: dict[str, str],
    tmp_path: Path,
    repo_root: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    shutil.copytree(repo_root / "config", tmp_path / "config")
    monkeypatch.chdir(tmp_path)
    argv = ["research", "--universe", f"one={two_universes['one']}", "--noise", "1", "--jobs", "2"]
    assert main([*argv, "--families", "sma", "--report", "out/grid.md"]) == 0
    out = capsys.readouterr().out
    assert "one: best" in out and "backtests" in out
    assert (tmp_path / "out" / "grid.md").exists() and (tmp_path / "out" / "grid.csv").exists()
    assert main(["research", "--universe", "nameonly"]) == 2
    assert main(["research", "--universe", "x=missing.csv"]) == 2


@pytest.mark.parametrize("family", ["hold_brake", "inv_vol", "dd_brake"])
def test_round2_families_pass_the_red_team(family: str, market: MarketData) -> None:
    for name, factory in strategy_grid(family, AppConfig()):
        report = RedTeamAuditor(probes=3, window=20).audit(factory, market, name=name)
        assert report.passed and report.findings == (), (name, report.findings)


def test_round2_rules() -> None:
    market = wavy_market(("UP", "SLIDE", "DOWN"), n=400, drifts=(0.001, -0.0005, -0.002))
    view = market.view_at(399)
    # SLIDE and DOWN are both below their average and down on the year
    assert library.hold_brake(200, 252)(market)(view) == {"UP": 1 / 3}
    weights = library.inverse_vol(63)(market)(view)
    assert set(weights) == {"UP", "SLIDE", "DOWN"} and sum(weights.values()) == pytest.approx(1)
    trend = library.inverse_vol(63, trend_sma=200)(market)(view)
    assert set(trend) == {"UP"} and trend["UP"] == pytest.approx(weights["UP"])
    up = [100.0 * 1.002**k for k in range(300)]
    crash = [up[-1] * 0.98**k for k in range(1, 21)]
    rebound = [crash[-1] * 1.02**k for k in range(1, 61)]
    path = path_market(up + crash + rebound, spread=0.001)
    brake = library.drawdown_brake(0.20)(path)
    held = [bool(brake(path.view_at(t))) for t in range(260, len(path))]
    assert held[0] and not held[300 + 12 - 260] and held[-1]  # out after -20%, back in later
    with pytest.raises(ValueError, match="between 0 and 1"):
        library.drawdown_brake(1.5)
