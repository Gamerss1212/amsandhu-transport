from __future__ import annotations

import math
from datetime import date
from pathlib import Path

import numpy as np
import pytest

from quantagents.data.synthetic import DEMO_AS_OF, DEMO_END, business_days, synthetic_market
from quantagents.market import Bars, MarketData, as_readonly, load_csv, save_csv


def test_views_are_causal_and_read_only(market: MarketData) -> None:
    view = market.view(DEMO_AS_OF)
    assert view.as_of == DEMO_AS_OF and view.dates[-1] == DEMO_AS_OF
    assert len(view.close("SYN_A")) == market.index_of(DEMO_AS_OF) + 1
    with pytest.raises(ValueError):
        view.close("SYN_A")[0] = 1.0
    assert view.last("SYN_A").close == float(view.close("SYN_A")[-1])
    assert market.next_date(DEMO_AS_OF) == date(2026, 10, 1)
    assert market.next_date(DEMO_END) is None
    assert market.has_date(DEMO_AS_OF) and not market.has_date(date(2026, 10, 3))
    with pytest.raises(KeyError):
        market.view(date(2026, 10, 3))
    with pytest.raises(IndexError):
        market.view_at(len(market))
    assert (
        len(view.open("SYN_A"))
        == len(view.high("SYN_A"))
        == len(view.low("SYN_A"))
        == len(view.volume("SYN_A"))
    )


def test_market_data_validation() -> None:
    bars = Bars.from_arrays(open=[1, 2], high=[1, 2], low=[1, 2], close=[1, 2], volume=[1, 1])
    d1, d2 = date(2026, 1, 1), date(2026, 1, 2)
    with pytest.raises(ValueError, match="increasing"):
        MarketData([d2, d1], {"A": bars})
    with pytest.raises(ValueError, match="at least one date"):
        MarketData([], {"A": bars})
    with pytest.raises(ValueError, match="at least one symbol"):
        MarketData([d1, d2], {})
    with pytest.raises(ValueError, match="bars for"):
        MarketData([d1], {"A": bars})
    with pytest.raises(ValueError, match="same length"):
        Bars.from_arrays(open=[1], high=[1, 2], low=[1, 2], close=[1, 2], volume=[1, 1])
    with pytest.raises(ValueError):
        as_readonly(np.zeros((2, 2)))
    with pytest.raises(KeyError):
        bars.field("vwap")


def test_csv_roundtrip_and_missing_rows(tmp_path: Path, market: MarketData) -> None:
    path = tmp_path / "prices.csv"
    save_csv(market, path)
    loaded = load_csv(path)
    assert loaded.symbols == market.symbols and loaded.dates == market.dates
    assert np.array_equal(loaded.bars("SYN_C").close, market.bars("SYN_C").close)
    gappy = tmp_path / "gappy.csv"
    gappy.write_text(
        "date,symbol,open,high,low,close,volume\n"
        "2026-01-02,AAA,1,1,1,1,10\n2026-01-05,AAA,1,1,1,1,10\n2026-01-05,BBB,2,2,2,2,10\n",
        encoding="utf-8",
    )
    data = load_csv(gappy)
    assert math.isnan(float(data.bars("BBB").close[0])) and data.bars("BBB").close[1] == 2.0


@pytest.mark.parametrize(
    ("content", "message"),
    [
        ("date,symbol,open\n", "missing columns"),
        ("date,symbol,open,high,low,close,volume\n", "no data rows"),
        ("date,symbol,open,high,low,close,volume\n2026-01-02,AAA,x,1,1,1,1\n", ":2:"),
        (
            "date,symbol,open,high,low,close,volume\n2026-01-02,AAA,1,1,1,1,1\n2026-01-02,AAA,1,1,1,1,1\n",
            "duplicate",
        ),
    ],
)
def test_csv_errors_name_the_line(tmp_path: Path, content: str, message: str) -> None:
    path = tmp_path / "bad.csv"
    path.write_text(content, encoding="utf-8")
    with pytest.raises(ValueError, match=message):
        load_csv(path)


def test_synthetic_data_is_deterministic_and_valid() -> None:
    a, b = synthetic_market(seed=3, n_days=300), synthetic_market(seed=3, n_days=300)
    assert all(np.array_equal(a.bars(s).close, b.bars(s).close) for s in a.symbols)
    assert not np.array_equal(
        a.bars("SYN_A").close, synthetic_market(seed=4, n_days=300).bars("SYN_A").close
    )
    for s in a.symbols:
        bars = a.bars(s)
        assert np.all(bars.low <= np.minimum(bars.open, bars.close))
        assert np.all(bars.high >= np.maximum(bars.open, bars.close))
    days = business_days(date(2026, 10, 4), 3)
    assert days == [date(2026, 9, 30), date(2026, 10, 1), date(2026, 10, 2)]
