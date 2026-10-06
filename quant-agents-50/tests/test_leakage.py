"""Spec section 59 leakage tests: time shift and duplicate timestamps (Phase 1)."""

from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import replace
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from quantagents.backtest.engine import Strategy
from quantagents.backtest.strategies import buy_and_hold, tsmom
from quantagents.data.sources import parse_ccxt_ohlcv, parse_yahoo_chart, read_long_csv
from quantagents.market import MarketData, MarketView, load_csv
from quantagents.validation.leakage import RedTeamAuditor, delayed, time_shift_test

DATA = Path(__file__).parent / "data"


def peeks_two_bars_ahead(market: MarketData) -> Strategy:
    """A broken strategy: its 'signal' is the move two days later (mis-timed future data)."""
    close = market.bars("SYN_A").close
    open_ = market.bars("SYN_A").open

    def strategy(view: MarketView) -> Mapping[str, float]:
        k = len(view) - 1
        if k + 2 >= len(market):
            return {}
        return {"SYN_A": 1.0} if close[k + 2] > open_[k + 2] else {}

    return strategy


def test_delayed_strategy_sees_older_data(market: MarketData) -> None:
    seen: list[int] = []

    def factory(_: MarketData) -> Strategy:
        def strategy(view: MarketView) -> Mapping[str, float]:
            seen.append(len(view))
            return {}

        return strategy

    late = delayed(factory, 2)(market)
    assert late(market.view_at(10)) == {}
    assert seen == [9]  # 11 bars visible, 2 hidden
    assert late(market.view_at(1)) == {}  # nothing to see yet: flat
    assert seen == [9]
    with pytest.raises(ValueError, match="lag"):
        delayed(factory, 0)


def test_time_shift_passes_honest_strategies(market: MarketData) -> None:
    for factory in (buy_and_hold(), tsmom(63)):
        result = time_shift_test(factory, market)
        assert result.finding is None, result
        assert result.days == len(market) - 261


def test_time_shift_catches_mis_timed_inputs(market: MarketData) -> None:
    result = time_shift_test(peeks_two_bars_ahead, market)
    assert result.finding is not None
    assert result.finding.severity == "critical"
    assert result.delayed_annual > result.original_annual
    assert result.t_stat >= 3


def test_red_team_runs_the_time_shift(market: MarketData) -> None:
    report = RedTeamAuditor().audit(peeks_two_bars_ahead, market, name="broken")
    assert "time_shift" in report.tests_run
    assert any(f.test == "time_shift" for f in report.findings)
    assert not report.passed
    honest = RedTeamAuditor().audit(tsmom(63), market, name="tsmom")
    assert honest.passed and "time_shift" in honest.tests_run
    off = RedTeamAuditor(time_shift=False).audit(tsmom(63), market, name="tsmom")
    assert "time_shift" not in off.tests_run


def test_time_shift_reports_a_backtest_it_cannot_run(market: MarketData) -> None:
    def factory(_: MarketData) -> Strategy:
        # out of bounds on one day the probes do not look at
        return lambda view: {"SYN_A": 2.0} if len(view) == 300 else {}

    report = RedTeamAuditor().audit(factory, market, name="sometimes too big")
    shift = [f for f in report.findings if f.test == "time_shift"]
    assert shift and "could not run" in shift[0].detail


# ---------------------------------------------------------------- duplicate timestamps


def test_market_data_refuses_duplicate_dates(market: MarketData) -> None:
    dates = list(market.dates)
    dates[5] = dates[4]
    with pytest.raises(ValueError, match="strictly increasing"):
        MarketData(dates, {s: market.bars(s) for s in market.symbols})


def test_csv_readers_refuse_duplicate_rows(tmp_path: Path) -> None:
    path = tmp_path / "dup.csv"
    path.write_text(
        "date,symbol,open,high,low,close,volume\n2024-01-02,X,1,1,1,1,1\n2024-01-02,X,2,2,2,2,2\n",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate row"):
        load_csv(path)
    with pytest.raises(ValueError, match="duplicate row"):
        read_long_csv(path)


def test_sources_collapse_repeated_timestamps_to_one_bar() -> None:
    rows = json.loads((DATA / "ccxt_kraken_btcusd_2024_10.json").read_text(encoding="utf-8"))
    raw = parse_ccxt_ohlcv([*rows, *rows], "BTC-USD")
    assert len(raw.dates) == len(set(raw.dates)) == 10
    chart = json.loads((DATA / "yahoo_spy_2024_03.json").read_text(encoding="utf-8"))
    res = chart["chart"]["result"][0]
    res["timestamp"][3] = res["timestamp"][2] + 60  # two stamps on one trading day
    once = parse_yahoo_chart(chart, "SPY")
    assert len(once.dates) == len(set(once.dates)) == 22
    with pytest.raises(ValueError, match="strictly increasing"):
        replace(once, dates=(once.dates[0], *once.dates[:-1]))


def test_long_csv_reader_reads_optional_columns(tmp_path: Path) -> None:
    path = tmp_path / "prices.csv"
    path.write_text(
        "date,symbol,open,high,low,close,volume,adj_close,dividend,split\n"
        "2024-01-02,X,10,11,9,10,100,9.5,,\n"
        "2024-01-03,X,10,11,9,10,100,10,0.5,\n"
        "2024-01-04,X,5,6,4,5,200,5,,2\n",
        encoding="utf-8",
    )
    raws, adjusted = read_long_csv(path)
    assert adjusted
    x = raws["X"]
    assert x.dates == (date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4))
    assert np.array_equal(x.adj_close, [9.5, 10.0, 5.0])
    assert x.dividends == {date(2024, 1, 3): 0.5}
    assert x.splits == {date(2024, 1, 4): 2.0}
    bad = tmp_path / "bad.csv"
    bad.write_text("date,symbol,open\n2024-01-02,X,1\n", encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns"):
        read_long_csv(bad)
    empty = tmp_path / "empty.csv"
    empty.write_text("date,symbol,open,high,low,close,volume\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no data rows"):
        read_long_csv(empty)
    broken = tmp_path / "broken.csv"
    broken.write_text("date,symbol,open,high,low,close,volume\n2024-13-02,X,1,1,1,1,1\n", "utf-8")
    with pytest.raises(ValueError, match=r"broken\.csv:2"):
        read_long_csv(broken)
