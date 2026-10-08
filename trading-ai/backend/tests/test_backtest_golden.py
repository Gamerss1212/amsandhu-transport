"""Golden backtests (sections 207, 285): tiny datasets whose answers are worked out by hand. The engine must match
them exactly before any long backtest is trusted."""

from __future__ import annotations

from decimal import Decimal

import numpy as np
import pytest

from tradingai.backtest.costs import CostModel
from tradingai.backtest.engine import BTConfig, run
from tradingai.data.bars import Bars
from tradingai.market.instruments import Instrument, MarketType, Settlement

DAY = 86_400_000
ZERO = dict(half_spread_bps=0.0, half_spread_ticks=0.0, slippage_model="fixed", slippage_bps=0.0,
            participation_cap=1.0)


def bars(o, h, lo, c, v=None):
    n = len(c)
    return Bars("T:X", "1d", np.arange(n, dtype=np.int64) * DAY, np.array(o, float), np.array(h, float),
                np.array(lo, float), np.array(c, float), np.array(v if v is not None else [1e9] * n, float))


def stock():
    return Instrument("US:X", MarketType.STOCK, "X", "US", "USD", quantity_step=Decimal(1), min_quantity=Decimal(1))


def es():
    return Instrument("CME:ES", MarketType.FUTURE, "ES", "CME", "USD", multiplier=Decimal(50), tick_size=Decimal("0.25"),
                      settlement=Settlement.CASH, root="ES")


def flat_bars(n, px=100.0):
    return bars([px] * n, [px + 1] * n, [px - 1] * n, [px] * n)


def test_ten_bars_known_entry_exit_and_commission():
    #             0    1    2    3    4    5    6    7    8    9
    o = [100, 100, 100, 101, 102, 103, 104, 105, 106, 107]
    c = [100, 100, 100, 102, 103, 104, 105, 106, 107, 108]
    b = bars(o, [x + 2 for x in c], [x - 2 for x in o], c)
    sig = np.array([0, 0, 1, 1, 1, 1, 0, 0, 0, 0], float)      # long from bar 2's close, flat at bar 6's close
    cm = CostModel("stock", commission_pct=0.001, **ZERO)
    r = run(b, sig, stock(), BTConfig(capital=10_000, fixed_qty=10, cost=cm))
    assert len(r.trades) == 1
    t = r.trades[0]
    assert (t.entry_px, t.exit_px, t.qty) == (101.0, 105.0, 10.0)       # next-bar opens, never the signal close
    fees = 10 * 101 * 0.001 + 10 * 105 * 0.001                            # 1.01 + 1.05
    assert t.fees == pytest.approx(fees)
    assert t.net == pytest.approx(10 * 4 - fees)                          # 37.94
    assert r.equity[-1] == pytest.approx(10_000 + 10 * 4 - fees)
    assert t.exit_reason == "signal"


def test_futures_pnl_uses_the_multiplier():
    o = [5000.0, 5000.0, 5000.0, 5010.25, 5010.25]
    b = bars(o, [x + 1 for x in o], [x - 1 for x in o], o)
    sig = np.array([1, 1, 1, 0, 0], float)
    cm = CostModel("future", fee_per_contract=2.25, **ZERO)
    r = run(b, sig, es(), BTConfig(capital=100_000, fixed_qty=2, cost=cm, flat_in_roll_window=False))
    t = r.trades[0]
    assert (t.entry_px, t.exit_px) == (5000.0, 5010.25)
    assert t.net == pytest.approx(10.25 * 50 * 2 - 4 * 2.25)             # 1025 - 9 = 1016
    assert r.equity[-1] == pytest.approx(100_000 + 1016)


def test_stop_fills_at_the_stop_and_a_gap_fills_at_the_open():
    n = 30
    b = flat_bars(n)                                                       # ATR(14) = 2.0 exactly
    lo = b.low.copy()
    lo[22] = 95.0                                                          # stop = 100 - 2 * 2 = 96: hit on bar 22
    b = bars(b.open, b.high, lo, b.close)
    sig = np.zeros(n)
    sig[20:] = 1
    r = run(b, sig, stock(), BTConfig(fixed_qty=1, exit_model="atr_bracket", cost=CostModel("stock", **ZERO)))
    t = r.trades[0]
    assert t.entry_px == 100.0 and t.exit_reason == "stop" and t.exit_px == pytest.approx(96.0)
    o, lo2 = b.open.copy(), b.low.copy()
    o[22], lo2[22] = 90.0, 89.0                                            # gapped below the stop
    g = bars(o, np.maximum(b.high, o), lo2, b.close)
    t2 = run(g, sig, stock(), BTConfig(fixed_qty=1, exit_model="atr_bracket", cost=CostModel("stock", **ZERO))).trades[0]
    assert t2.exit_px == pytest.approx(90.0)                               # worse than the stop: the open


def test_stop_and_target_in_one_bar_assumes_the_stop():
    n = 30
    b = flat_bars(n)
    h, lo = b.high.copy(), b.low.copy()
    h[22], lo[22] = 120.0, 80.0                                            # target 108 and stop 96 both inside
    b = bars(b.open, h, lo, b.close)
    sig = np.zeros(n)
    sig[20:] = 1
    t = run(b, sig, stock(), BTConfig(fixed_qty=1, exit_model="atr_bracket",
                                      cost=CostModel("stock", **ZERO))).trades[0]
    assert t.exit_reason == "stop" and t.exit_px == pytest.approx(96.0)


def test_no_reentry_after_a_stop_until_the_signal_resets():
    n = 40
    b = flat_bars(n)
    lo = b.low.copy()
    lo[22] = 95.0
    b = bars(b.open, b.high, lo, b.close)
    sig = np.zeros(n)
    sig[20:] = 1                                                           # the signal never resets
    r = run(b, sig, stock(), BTConfig(fixed_qty=1, exit_model="atr_bracket", cost=CostModel("stock", **ZERO)))
    assert len(r.trades) == 1


def test_partial_fills_respect_the_volume_cap():
    n = 25
    b = flat_bars(n)
    b = bars(b.open, b.high, b.low, b.close, [100.0] * n)                  # 10% cap = 10 shares a bar
    sig = np.zeros(n)
    sig[15:] = 1
    cm = CostModel("stock", half_spread_bps=0.0, slippage_model="fixed", participation_cap=0.10)
    r = run(b, sig, stock(), BTConfig(fixed_qty=35, cost=cm))
    assert r.partial_fills >= 3
    assert r.trades[0].qty == 35                                           # built up over 4 bars


def test_ledger_identity_spot_and_margin():
    rng = np.random.default_rng(3)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 400)))
    o = np.r_[c[0], c[:-1]]
    b = bars(o, np.maximum(o, c) * 1.003, np.minimum(o, c) * 0.997, c)
    sig = np.sign(np.sin(np.arange(400) / 9.0))
    for inst, short in ((stock(), False), (es(), True)):
        r = run(b, sig, inst, BTConfig(capital=1e6, cost=CostModel("x", commission_pct=0.0005, half_spread_bps=1.0),
                                       allow_short=short, flat_in_roll_window=False))
        assert r.equity[-1] == pytest.approx(1e6 + sum(t.net for t in r.trades), abs=1e-6)


def test_no_lookahead_future_bars_do_not_change_earlier_trades():
    rng = np.random.default_rng(5)
    c = 100 * np.exp(np.cumsum(rng.normal(0, 0.01, 300)))
    o = np.r_[c[0], c[:-1]]
    b = bars(o, np.maximum(o, c) * 1.002, np.minimum(o, c) * 0.998, c)
    sig = np.sign(np.sin(np.arange(300) / 7.0))
    full = run(b, sig, stock(), BTConfig(exit_model="atr_bracket")).trades
    cut = 200
    part = run(b.slice(0, cut), sig[:cut], stock(), BTConfig(exit_model="atr_bracket")).trades
    done_before = [t for t in full if t.exit_ts < b.ts[cut - 1]]
    assert [(t.entry_ts, t.exit_ts, t.net) for t in done_before] == \
        [(t.entry_ts, t.exit_ts, t.net) for t in part if t.exit_ts < b.ts[cut - 1]]
