"""`quantagents data ...` commands, offline: the downloaders are replaced by recorded files."""

from __future__ import annotations

import json
import shutil
from dataclasses import replace
from datetime import date
from pathlib import Path

import pytest

from quantagents.cli import main
from quantagents.data import sources
from quantagents.data.sources import RawDaily
from quantagents.data.store import meta_path

DATA = Path(__file__).parent / "data"


def recorded(name: str, symbol: str) -> RawDaily:
    return sources.parse_yahoo_chart(json.loads((DATA / name).read_text("utf-8")), symbol)


@pytest.fixture
def offline(
    tmp_path: Path, repo_root: Path, monkeypatch: pytest.MonkeyPatch
) -> list[tuple[str, str]]:
    shutil.copytree(repo_root / "config", tmp_path / "config")
    monkeypatch.chdir(tmp_path)
    calls: list[tuple[str, str]] = []

    def fake_yahoo(symbol: str, start: date, end: date) -> RawDaily:
        calls.append(("yahoo", symbol))
        if symbol == "NOPE":
            raise ValueError("no data for NOPE")
        return recorded("yahoo_spy_2024_03.json", symbol)

    def fake_ccxt(exchange: str, pair: str, start: date, end: date) -> RawDaily:
        calls.append((exchange, pair))
        rows = json.loads((DATA / "ccxt_kraken_btcusd_2024_10.json").read_text("utf-8"))
        return sources.parse_ccxt_ohlcv(rows, sources.ccxt_symbol(exchange, pair))

    monkeypatch.setattr(sources, "fetch_yahoo", fake_yahoo)
    monkeypatch.setattr(sources, "fetch_ccxt", fake_ccxt)
    return calls


def test_fetch_list_benchmark(
    offline: list[tuple[str, str]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["data", "list"]) == 0
    assert "empty" in capsys.readouterr().out

    assert main(["data", "fetch", "--yahoo", "SPY", "--ccxt", "kraken:BTC/USD"]) == 0
    out = capsys.readouterr().out
    assert "SPY: stored 23 days 2024-03-01 to 2024-04-03, 1 dividends" in out
    assert "BTC-USD.KRAKEN: stored 10 days" in out
    assert "survivorship-biased: upper bound only" in out
    assert offline == [("yahoo", "SPY"), ("kraken", "BTC/USD")]

    assert main(["data", "list"]) == 0
    out = capsys.readouterr().out
    assert "SPY" in out and "BTC-USD.KRAKEN" in out and "2 symbols, 2 snapshots" in out

    assert main(["data", "benchmark", "--symbol", "SPY"]) == 0
    out = capsys.readouterr().out
    assert "PASS" in out and "1 dividends" in out and "yahoo_chart_v8" in out


def test_fetch_reports_failures(
    offline: list[tuple[str, str]], capsys: pytest.CaptureFixture[str]
) -> None:
    assert main(["data", "fetch", "--yahoo", "NOPE", "SPY", "--ccxt", "krakenBTC"]) == 1
    out = capsys.readouterr().out
    assert "NOPE: FAILED (no data for NOPE)" in out
    assert "krakenBTC: FAILED (write it as exchange:PAIR" in out
    assert "SPY: stored" in out  # one bad symbol does not stop the rest
    assert main(["data", "fetch"]) == 2
    assert "Nothing to fetch" in capsys.readouterr().out


def test_benchmark_fails_on_a_bad_snapshot(
    offline: list[tuple[str, str]],
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_dividends(symbol: str, start: date, end: date) -> RawDaily:
        return replace(recorded("yahoo_spy_2024_03.json", symbol), dividends={})

    monkeypatch.setattr(sources, "fetch_yahoo", no_dividends)
    assert main(["data", "fetch", "--yahoo", "SPY"]) == 0
    capsys.readouterr()
    assert main(["data", "benchmark", "--symbol", "SPY"]) == 1
    assert "FAIL" in capsys.readouterr().out
    assert main(["data", "benchmark", "--symbol", "QQQ"]) == 2  # never stored


def test_export_writes_csv_and_caveats(
    offline: list[tuple[str, str]], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert main(["data", "fetch", "--yahoo", "SPY", "--ccxt", "kraken:BTC/USD"]) == 0
    capsys.readouterr()
    assert main(["data", "export", "--out", "data/mixed.csv"]) == 0
    out = capsys.readouterr().out
    assert "Wrote data/mixed.csv: 2 symbols" in out
    assert "Missing days:" in out and "separate files" in out
    meta = json.loads(meta_path(tmp_path / "data" / "mixed.csv").read_text("utf-8"))
    assert meta["symbols"]["SPY"]["source"] == "yahoo_chart_v8"
    assert any("survivorship-biased" in label for label in meta["labels"])
    assert meta["missing_days"]["SPY"] > 0  # SPY does not trade on weekends; BTC does

    assert main(["data", "export", "--out", "data/spy.csv", "--symbols", "SPY"]) == 0
    assert "Missing days" not in capsys.readouterr().out
    assert main(["data", "export", "--out", "x.csv", "--as-of-ingest", "2000-01-01"]) == 2
    assert "no snapshot" in capsys.readouterr().err


def test_import_owner_csv_and_labels_on_results(
    offline: list[tuple[str, str]], capsys: pytest.CaptureFixture[str], tmp_path: Path
) -> None:
    assert main(["make-data", "--out", "data/own.csv"]) == 0
    assert main(["data", "import", "--csv", "data/own.csv"]) == 0
    out = capsys.readouterr().out
    assert "SYN_A: stored" in out and "csv:own.csv" in out
    assert "No adj_close column" in out

    # a CSV with no sidecar gets the safe default caveat on every result
    assert main(["backtest", "--data", "data/own.csv", "--engine", "event"]) == 0
    out = capsys.readouterr().out
    assert "source not recorded; survivorship-biased: upper bound only" in out
    assert "Event-driven backtest" in out and "unfunded top-ups" in out
    assert main(["cycle", "--data", "data/own.csv"]) == 0
    assert "nothing can trade" not in capsys.readouterr().out  # SYN_* are in the universe

    # an exported CSV carries its sources' caveats
    assert main(["data", "export", "--out", "data/prices.csv", "--start", "2026-01-02"]) == 0
    capsys.readouterr()
    assert main(["backtest", "--data", "data/prices.csv"]) == 2  # too short for the warmup
    out = capsys.readouterr().out
    assert "not point-in-time" in out
    assert main(["cycle", "--data", "data/prices.csv", "--state", "state/x.json"]) == 0
    out = capsys.readouterr().out
    assert "nothing can trade" not in out  # SYN_* again
    assert main(["data", "fetch", "--yahoo", "SPY"]) == 0
    assert main(["data", "export", "--out", "data/spy.csv", "--symbols", "SPY"]) == 0
    capsys.readouterr()
    assert main(["cycle", "--data", "data/spy.csv", "--state", "state/y.json"]) == 0
    out = capsys.readouterr().out
    assert "none of this file's symbols (SPY)" in out and "nothing can trade" in out
