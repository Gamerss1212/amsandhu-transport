"""Phase 1 data layer: source parsers, the append-only store and the buy-and-hold benchmark.

Every test runs offline from small recorded files in ``tests/data`` (never the network).
"""

from __future__ import annotations

import copy
import hashlib
import json
import math
from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np
import pytest

from quantagents.data.benchmark import (
    TOLERANCE_PER_YEAR,
    annual_gaps,
    buy_and_hold_benchmark,
    cagr,
    rebuilt_total_return,
)
from quantagents.data.sources import (
    SURVIVORSHIP_LABEL,
    YAHOO_INFO,
    RawDaily,
    SourceInfo,
    ccxt_info,
    parse_ccxt_ohlcv,
    parse_yahoo_chart,
)
from quantagents.data.store import BarStore, adjusted_market
from quantagents.market import as_readonly

DATA = Path(__file__).parent / "data"
T0 = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


def payload(name: str) -> dict[str, Any]:
    loaded: dict[str, Any] = json.loads((DATA / name).read_text(encoding="utf-8"))
    return loaded


def spy() -> RawDaily:
    return parse_yahoo_chart(payload("yahoo_spy_2024_03.json"), "SPY")


def nvda() -> RawDaily:
    return parse_yahoo_chart(payload("yahoo_nvda_2024_06.json"), "NVDA")


def btc() -> RawDaily:
    rows = json.loads((DATA / "ccxt_kraken_btcusd_2024_10.json").read_text(encoding="utf-8"))
    return parse_ccxt_ohlcv(rows, "BTC-USD")


def tiny(symbol: str, days: list[date], closes: list[float]) -> RawDaily:
    c = as_readonly(np.array(closes, dtype=np.float64))
    return RawDaily(
        symbol=symbol,
        dates=tuple(days),
        open=c,
        high=c,
        low=c,
        close=c,
        adj_close=c,
        volume=as_readonly(np.ones(len(days))),
    )


# ---------------------------------------------------------------- sources


def test_yahoo_parser_reads_local_trading_dates_and_dividends() -> None:
    raw = spy()
    assert len(raw) == 23
    assert raw.dates[0] == date(2024, 3, 1)
    assert raw.dates[-1] == date(2024, 4, 3)
    assert raw.dividends == {date(2024, 3, 15): pytest.approx(1.595)}
    assert raw.splits == {}
    # the adjustment factor steps down across the ex-dividend date by about dividend / close
    factor = np.asarray(raw.adj_close) / np.asarray(raw.close)
    k = raw.dates.index(date(2024, 3, 15))
    assert factor[k - 1] / factor[k] == pytest.approx(1 - 1.595 / raw.close[k - 1], abs=1e-5)
    assert np.ptp(factor[:k]) < 1e-6
    assert np.ptp(factor[k:]) < 1e-6


def test_yahoo_parser_reads_splits() -> None:
    raw = nvda()
    assert raw.splits == {date(2024, 6, 10): 10.0}
    assert raw.dividends == {date(2024, 6, 11): pytest.approx(0.01)}
    # Yahoo's close is already split-adjusted: no 10x jump across the split date
    k = raw.dates.index(date(2024, 6, 10))
    assert 0.8 < raw.close[k] / raw.close[k - 1] < 1.2


def test_yahoo_parser_drops_padded_and_unfinished_bars() -> None:
    data = copy.deepcopy(payload("yahoo_spy_2024_03.json"))
    quote = data["chart"]["result"][0]["indicators"]["quote"][0]
    quote["close"][5] = None  # Yahoo pads holidays with nulls
    full = parse_yahoo_chart(data, "SPY")
    assert len(full) == 22

    last = full.dates[-1]
    # 10:00 New York time on the last day: the session is still open, so that bar is dropped
    during = datetime(last.year, last.month, last.day, 14, 0, tzinfo=UTC)
    assert parse_yahoo_chart(data, "SPY", now=during).dates[-1] < last
    after = datetime(last.year, last.month, last.day, 21, 0, tzinfo=UTC)
    assert parse_yahoo_chart(data, "SPY", now=after).dates[-1] == last
    # a "now" before the data starts drops everything after it (no future bars)
    early = datetime(2024, 3, 5, 21, 0, tzinfo=UTC)
    assert parse_yahoo_chart(data, "SPY", now=early).dates[-1] == date(2024, 3, 5)


def test_yahoo_parser_keeps_todays_crypto_bar_out_until_the_utc_day_ends() -> None:
    data = copy.deepcopy(payload("yahoo_spy_2024_03.json"))
    data["chart"]["result"][0]["meta"].update({"instrumentType": "CRYPTOCURRENCY", "gmtoffset": 0})
    full = parse_yahoo_chart(data, "BTC-USD")
    last = full.dates[-1]
    evening = datetime(last.year, last.month, last.day, 23, 0, tzinfo=UTC)
    assert parse_yahoo_chart(data, "BTC-USD", now=evening).dates[-1] < last  # still forming
    next_day = evening + timedelta(hours=2)
    assert parse_yahoo_chart(data, "BTC-USD", now=next_day).dates[-1] == last


def test_yahoo_parser_rejects_other_payloads() -> None:
    with pytest.raises(ValueError, match="not a Yahoo chart"):
        parse_yahoo_chart({"chart": {"result": None}}, "SPY")
    with pytest.raises(ValueError, match="not a Yahoo chart"):
        parse_yahoo_chart({}, "SPY")


def test_yahoo_parser_without_adjclose_uses_close() -> None:
    data = copy.deepcopy(payload("yahoo_spy_2024_03.json"))
    del data["chart"]["result"][0]["indicators"]["adjclose"]
    raw = parse_yahoo_chart(data, "SPY")
    assert np.array_equal(raw.adj_close, raw.close)


def test_ccxt_parser_utc_days_and_unfinished_candle() -> None:
    raw = btc()
    assert len(raw) == 10
    assert raw.dates[0] == date(2024, 10, 16)
    assert np.array_equal(raw.adj_close, raw.close)  # no corporate actions in spot crypto
    rows = json.loads((DATA / "ccxt_kraken_btcusd_2024_10.json").read_text(encoding="utf-8"))
    on_last_day = datetime(2024, 10, 25, 18, 0, tzinfo=UTC)
    assert parse_ccxt_ohlcv(rows, "BTC-USD", now=on_last_day).dates[-1] == date(2024, 10, 24)


def test_ccxt_parser_keeps_the_last_copy_of_a_repeated_candle() -> None:
    rows = json.loads((DATA / "ccxt_kraken_btcusd_2024_10.json").read_text(encoding="utf-8"))
    repeated = [*rows, [rows[-1][0], 1.0, 2.0, 0.5, 1.5, 9.0]]
    raw = parse_ccxt_ohlcv(repeated, "BTC-USD")
    assert len(raw) == 10
    assert raw.close[-1] == 1.5


def test_raw_daily_validates_shape_and_order() -> None:
    days = [date(2024, 1, 2), date(2024, 1, 3)]
    with pytest.raises(ValueError, match="differ in length"):
        replace(tiny("X", days, [1.0, 2.0]), close=as_readonly(np.ones(3)))
    with pytest.raises(ValueError, match="strictly increasing"):
        tiny("X", [days[1], days[0]], [1.0, 2.0])


def test_source_labels_say_what_the_data_cannot_promise() -> None:
    assert SURVIVORSHIP_LABEL in YAHOO_INFO.label
    assert "not point-in-time" in YAHOO_INFO.label
    assert SURVIVORSHIP_LABEL in ccxt_info("kraken").label
    clean = SourceInfo("vendor", True, True, "none", "UTC", "paid")
    assert clean.label == "point-in-time, survivorship-free"


# ---------------------------------------------------------------- store


def sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_store_round_trips_a_snapshot(tmp_path: Path) -> None:
    store = BarStore(tmp_path)
    raw = nvda()
    store.append(raw, YAHOO_INFO, ingested_at=T0)
    back, info = store.raw("NVDA")
    assert info == YAHOO_INFO
    assert back.dates == raw.dates
    for f in ("open", "high", "low", "close", "adj_close", "volume"):
        assert np.array_equal(getattr(back, f), getattr(raw, f))
    assert back.dividends == raw.dividends
    assert back.splits == raw.splits
    assert store.symbols() == ["NVDA"]
    assert store.vintages() == [("NVDA", T0, 10)]


def test_store_is_append_only_and_reads_by_vintage(tmp_path: Path) -> None:
    store = BarStore(tmp_path)
    old = spy()
    first = store.append(old, YAHOO_INFO, ingested_at=T0)
    before = sha(first)
    # the source later restates history (e.g. a new dividend re-adjusts every adj_close)
    restated = replace(old, adj_close=as_readonly(np.asarray(old.adj_close) * 0.99))
    second = store.append(restated, YAHOO_INFO, ingested_at=T0 + timedelta(days=1))

    assert first != second
    assert sha(first) == before  # the old file is untouched
    assert sorted(p.name for p in store.bars_dir.iterdir()) == sorted([first.name, second.name])
    assert len(store.vintages("SPY")) == 2

    then, _ = store.raw("SPY", as_of_ingest=T0 + timedelta(hours=1))
    now, _ = store.raw("SPY")
    assert np.array_equal(then.adj_close, old.adj_close)
    assert np.array_equal(now.adj_close, restated.adj_close)
    with pytest.raises(KeyError, match="no snapshot"):
        store.raw("SPY", as_of_ingest=T0 - timedelta(seconds=1))


def test_store_never_overwrites(tmp_path: Path) -> None:
    store = BarStore(tmp_path)
    store.append(spy(), YAHOO_INFO, ingested_at=T0)
    with pytest.raises(FileExistsError, match="never overwrites"):
        store.append(spy(), YAHOO_INFO, ingested_at=T0)
    # different content at the same instant would mix two snapshots: refused too
    changed = replace(spy(), volume=as_readonly(np.asarray(spy().volume) + 1.0))
    with pytest.raises(FileExistsError, match="mixes snapshots"):
        store.append(changed, YAHOO_INFO, ingested_at=T0)
    assert len(list(store.bars_dir.iterdir())) == 1


def test_store_rejects_empty_snapshots(tmp_path: Path) -> None:
    empty = tiny("X", [], [])
    with pytest.raises(ValueError, match="nothing to store"):
        BarStore(tmp_path).append(empty, YAHOO_INFO)


def test_empty_store(tmp_path: Path) -> None:
    store = BarStore(tmp_path)
    assert store.vintages() == []
    assert store.symbols() == []
    with pytest.raises(ValueError, match="store is empty"):
        store.load()


def test_store_load_gives_an_adjusted_panel_with_sources(tmp_path: Path) -> None:
    store = BarStore(tmp_path)
    store.append(spy(), YAHOO_INFO, ingested_at=T0)
    store.append(btc(), ccxt_info("kraken"), ingested_at=T0)
    market, sources = store.load()
    assert market.symbols == ("BTC-USD", "SPY")
    assert sources["SPY"] == YAHOO_INFO
    assert sources["BTC-USD"].name == "ccxt:kraken"
    raw = spy()
    k = market.index_of(raw.dates[0])
    assert market.bars("SPY").close[k] == pytest.approx(raw.adj_close[0])
    # BTC trades every day, SPY does not: SPY has NaN on weekends (A02 flags those)
    assert math.isnan(market.bars("SPY").close[market.index_of(date(2024, 10, 19))])

    one, _ = store.load(["SPY"], start=date(2024, 3, 4), end=date(2024, 3, 8))
    assert one.dates[0] == date(2024, 3, 4)
    assert one.dates[-1] == date(2024, 3, 8)
    assert one.symbols == ("SPY",)


def test_adjusted_market_scales_every_price_by_the_same_factor() -> None:
    raw = spy()
    market = adjusted_market({"SPY": raw})
    bars = market.bars("SPY")
    factor = np.asarray(raw.adj_close) / np.asarray(raw.close)
    assert np.allclose(bars.open, np.asarray(raw.open) * factor)
    assert np.allclose(bars.low, np.asarray(raw.low) * factor)
    assert np.array_equal(bars.volume, raw.volume)
    with pytest.raises(ValueError, match="no bars"):
        adjusted_market({"SPY": raw}, start=date(2030, 1, 1))


def test_adjusted_market_keeps_raw_prices_when_adj_close_is_missing() -> None:
    raw = tiny("X", [date(2024, 1, 2), date(2024, 1, 3)], [10.0, 11.0])
    broken = replace(raw, adj_close=as_readonly(np.array([math.nan, 11.0])))
    assert adjusted_market({"X": broken}).bars("X").close[0] == 10.0


# ---------------------------------------------------------------- benchmark


def test_benchmark_passes_on_recorded_spy_and_nvda() -> None:
    for raw in (spy(), nvda()):
        report = buy_and_hold_benchmark(raw)
        assert report.passed, report
        assert report.dividends == 1
        assert report.tolerance == TOLERANCE_PER_YEAR
        # the backtester route is exact: A43 at zero cost equals the adjusted price change
        assert report.backtester_total == pytest.approx(report.adjusted_from_open_total, abs=1e-12)


def test_benchmark_catches_a_missing_dividend() -> None:
    raw = spy()
    report = buy_and_hold_benchmark(replace(raw, dividends={}))
    assert not report.passed
    assert report.cagr_gap_rebuilt < -TOLERANCE_PER_YEAR


def test_benchmark_catches_a_bad_adjustment() -> None:
    raw = spy()
    adj = np.asarray(raw.adj_close).copy()
    adj[:10] *= 0.98  # a 2% error in the source's adjustment
    report = buy_and_hold_benchmark(replace(raw, adj_close=as_readonly(adj)))
    assert not report.passed


def test_benchmark_needs_enough_bars_and_finite_prices() -> None:
    days = [date(2024, 1, 2), date(2024, 1, 3)]
    with pytest.raises(ValueError, match="at least 3"):
        buy_and_hold_benchmark(tiny("X", days, [1.0, 2.0]))
    three = [*days, date(2024, 1, 4)]
    with pytest.raises(ValueError, match="non-finite"):
        buy_and_hold_benchmark(tiny("X", three, [1.0, 2.0, math.inf]))


def test_rebuilt_return_compounds_dividends() -> None:
    raw = tiny("X", [date(2024, 1, 2), date(2024, 1, 3), date(2024, 1, 4)], [10.0, 10.0, 10.0])
    with_div = replace(raw, dividends={date(2024, 1, 3): 1.0})
    assert rebuilt_total_return(with_div, 0, 2) == pytest.approx(0.1)
    assert rebuilt_total_return(raw, 0, 2) == 0.0


def test_cagr() -> None:
    assert cagr(0.21, 504) == pytest.approx(0.1)
    assert cagr(-1.0, 252) == -1.0
    assert cagr(0.1, 0) == -1.0


def test_annual_gaps_are_tiny_on_good_data() -> None:
    gaps = annual_gaps(spy())
    assert [y for y, _ in gaps] == [2024]
    assert all(abs(g) < 1e-4 for _, g in gaps)
    one_day = tiny("X", [date(2023, 12, 29), date(2024, 1, 2)], [1.0, 1.0])
    assert annual_gaps(one_day) == []


def test_file_names_are_safe_on_every_system() -> None:
    from quantagents.data.store import safe_name

    assert safe_name("BTC-USD.KRAKEN") == "BTC-USD.KRAKEN"
    assert safe_name('X:Y*?<>|"\\/Z') == "X_Y" + "_" * 8 + "Z"
    assert safe_name("") == "_"


def test_symbols_sharing_a_file_safe_name_stay_apart(tmp_path: Path) -> None:
    store = BarStore(tmp_path)
    days = [date(2024, 1, 2), date(2024, 1, 3)]
    store.append(tiny("A/B", days, [1.0, 2.0]), YAHOO_INFO, ingested_at=T0)
    store.append(tiny("A_B", days, [5.0, 6.0]), YAHOO_INFO, ingested_at=T0 + timedelta(hours=1))
    assert store.raw("A/B")[0].close.tolist() == [1.0, 2.0]
    assert store.raw("A_B")[0].close.tolist() == [5.0, 6.0]
    assert store.snapshot_time("A/B") == T0
    with pytest.raises(KeyError):
        store.raw("C:D")


def test_reading_a_symbol_opens_one_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    store = BarStore(tmp_path)
    for k in range(5):
        store.append(spy(), YAHOO_INFO, ingested_at=T0 + timedelta(days=k))
        store.append(btc(), ccxt_info("kraken"), ingested_at=T0 + timedelta(days=k))
    (store.bars_dir / "junk.parquet").write_bytes(b"not a snapshot")  # ignored by name
    opened: list[int] = []
    real_query = BarStore._query

    def counting(self: BarStore, sql: str, params: Any = (), files: Any = None) -> Any:
        opened.append(len(self._files()) if files is None else len(files))
        return real_query(self, sql, params, files)

    monkeypatch.setattr(BarStore, "_query", counting)
    raw, _ = store.raw("SPY", as_of_ingest=T0 + timedelta(days=2, hours=1))
    assert opened == [1] and len(raw) == 23


def test_crypto_from_an_exchange_never_clashes_with_yahoo() -> None:
    from quantagents.data.sources import ccxt_symbol

    assert ccxt_symbol("kraken", "BTC/USD") == "BTC-USD.KRAKEN"
    assert ccxt_symbol("coinbase", "eth/cad") == "ETH-CAD.COINBASE"
