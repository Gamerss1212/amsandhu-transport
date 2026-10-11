"""The intraday operating rules (engine/daytrade.py) and their identical use in research and paper trading."""

import time
from datetime import datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import numpy as np
import pytest

from tradingai.app import App
from tradingai.backtest.engine import BTConfig, run
from tradingai.data.bars import Bars
from tradingai.engine import daytrade as DT

NY = ZoneInfo("America/New_York")
H, M15 = 3_600_000, 900_000


def ny(y, mo, d, h, mi):
    return int(datetime(y, mo, d, h, mi, tzinfo=NY).timestamp() * 1000)


def test_stock_entry_window_and_cutoff():
    assert DT.entry_check("XNYS", ny(2026, 10, 7, 9, 32))[1] == "OUTSIDE_ENTRY_WINDOW"
    assert DT.entry_check("XNYS", ny(2026, 10, 7, 10, 0))[0]
    assert DT.entry_check("XNYS", ny(2026, 10, 7, 15, 45))[1] == "ENTRY_CUTOFF"
    assert DT.entry_check("XNYS", ny(2026, 10, 10, 11, 0))[1] == "MARKET_CLOSED"         # Saturday
    assert DT.entry_check("XNYS", ny(2026, 11, 27, 12, 45))[1] == "ENTRY_CUTOFF"         # early close 13:00


def test_stock_flatten_deadline_depends_on_the_bar_size():
    assert DT.exit_due("XNYS", None, ny(2026, 10, 7, 14, 0), H) is None                  # next decision 15:00
    assert DT.exit_due("XNYS", None, ny(2026, 10, 7, 15, 0), H)[0] == "SESSION_FLATTEN"  # next would be 16:00
    assert DT.exit_due("XNYS", None, ny(2026, 10, 7, 15, 30), M15) is None               # 15:45 is in time
    assert DT.exit_due("XNYS", None, ny(2026, 10, 7, 15, 40), M15)[0] == "SESSION_FLATTEN"
    held_overnight = DT.exit_due("XNYS", ny(2026, 10, 6, 11, 0), ny(2026, 10, 7, 10, 0), M15)
    assert held_overnight and "earlier session" in held_overnight[1]


def test_futures_and_fx_cutoffs_and_crypto_max_hold():
    assert DT.entry_check("CME", ny(2026, 10, 7, 16, 20))[1] == "ENTRY_CUTOFF"
    assert DT.entry_check("CME", ny(2026, 10, 7, 19, 0))[0]                               # after the 18:00 restart
    assert DT.exit_due("CME", None, ny(2026, 10, 7, 16, 30), M15) is None
    assert DT.exit_due("CME", None, ny(2026, 10, 7, 16, 31), M15)[0] == "SESSION_FLATTEN"
    assert DT.entry_check("FX", ny(2026, 10, 7, 16, 35))[1] == "ENTRY_CUTOFF"
    now = ny(2026, 10, 7, 12, 0)
    assert DT.exit_due("CRYPTO", now - 22 * H, now, H) is None
    assert DT.exit_due("CRYPTO", now - 23 * H - 1, now, H)[0] == "MAX_HOLD"
    assert DT.entry_check("CRYPTO", ny(2026, 10, 7, 19, 30))[1] == "ENTRY_CUTOFF"        # 23:30 UTC


def stock_bars(sessions=20, minutes=15):
    rng = np.random.default_rng(5)
    per = 390 // minutes
    t0 = ny(2024, 1, 2, 9, 30)
    days = [t0 + d * 86_400_000 for d in range(sessions + 10) if datetime.fromtimestamp((t0 + d * 86_400_000) / 1000, NY).weekday() < 5][:sessions]
    ts = np.concatenate([d + np.arange(per) * minutes * 60_000 for d in days])
    c = 100 * np.cumprod(1 + rng.normal(0, 0.002, len(ts)))
    o = np.r_[100.0, c[:-1]]
    return Bars("US:SPY", f"{minutes}m", ts, o, np.maximum(o, c) * 1.001, np.minimum(o, c) * 0.999, c,
                np.full(len(ts), 1e6))


@pytest.fixture(scope="module")
def book():
    from tradingai.market.universe import build
    return build()[0]


def test_backtest_closes_every_stock_trade_inside_its_session(book):
    bars = stock_bars()
    inst = book.get("US:SPY")
    res = run(bars, np.ones(len(bars)), inst, BTConfig(exit_model="flip", day_trading=True, fixed_qty=10))
    assert res.trades and any("intraday rules applied" in f for f in res.flags)
    for t in res.trades:
        e = datetime.fromtimestamp(t.entry_ts / 1000, NY)
        x = datetime.fromtimestamp(t.exit_ts / 1000, NY)
        assert e.date() == x.date(), (e, x)                            # never held overnight
        assert (e.hour, e.minute) >= (9, 45) and (x.hour, x.minute) <= (15, 50)
    plain = run(bars, np.ones(len(bars)), inst, BTConfig(exit_model="flip", fixed_qty=10))
    assert len(plain.trades) < len(res.trades)                           # without the rules it holds for days


def test_daily_bars_produce_no_intraday_trades(book):
    rng = np.random.default_rng(1)
    ts = np.array([ny(2024, 1, 2, 9, 30) + d * 86_400_000 for d in range(300)])
    c = 100 * np.cumprod(1 + rng.normal(0, 0.01, 300))
    o = np.r_[100.0, c[:-1]]
    bars = Bars("US:SPY", "1d", ts, o, np.maximum(o, c), np.minimum(o, c), c, np.full(300, 1e6))
    res = run(bars, np.ones(300), book.get("US:SPY"), BTConfig(exit_model="flip", day_trading=True, fixed_qty=10))
    assert res.trades == []                                             # a daily method stays research-only


def test_crypto_backtest_respects_the_24_hour_hold(book):
    rng = np.random.default_rng(2)
    n = 24 * 30
    ts = ny(2024, 1, 2, 0, 0) + np.arange(n) * H
    c = 100 * np.cumprod(1 + rng.normal(0, 0.004, n))
    o = np.r_[100.0, c[:-1]]
    bars = Bars("COINBASE:BTC-USD", "1h", ts, o, np.maximum(o, c), np.minimum(o, c), c, np.full(n, 1e6))
    res = run(bars, np.ones(n), book.get("COINBASE:BTC-USD"), BTConfig(exit_model="flip", day_trading=True,
                                                                         fixed_qty=1))
    assert res.trades and all(t.exit_ts - t.entry_ts <= 24 * H for t in res.trades)
    assert any(t.exit_reason == "max hold" for t in res.trades)


@pytest.fixture()
def app(tmp_path):
    a = App(str(tmp_path / "home"), offline=True, start_loop=False)
    a.autopilot.cfg.enabled = False
    yield a
    a.shutdown()


def test_paper_entry_is_refused_after_the_cutoff(app, monkeypatch):
    from tradingai.engine import orchestrator as O
    monkeypatch.setattr(O.Strategy, "generate_signal", lambda self: O.Signal(1, 0, "tsmom.none.flip"))
    monkeypatch.setattr(O.daytrade, "entry_check", lambda cal, ms: (False, "ENTRY_CUTOFF", "test cutoff"))
    bot = app.create_bot("DEMO:DEMO-TREND", "1h", "tsmom.none.flip", signal_mode="strategy")
    rec = app.orch.decide(app.bots[bot["bot_id"]], "paper")
    assert rec["outcome"] == "NO_TRADE" and rec["reason"].startswith("ENTRY_CUTOFF")


def test_sweep_closes_a_position_past_its_maximum_hold(app, monkeypatch):
    app.paper.submit_order(client_order_id="T-OPEN", instrument_id="DEMO:DEMO-TREND", side="buy", qty=Decimal("1"))
    app.paper.process()
    assert app.paper.get_positions().get("DEMO:DEMO-TREND", 0) > 0
    opened = app.position_opened_at("DEMO:DEMO-TREND")
    assert opened is not None
    assert app.daytrade_sweep() == []                                   # just opened: nothing due
    monkeypatch.setattr(app, "position_opened_at", lambda iid: int(time.time() * 1000) - 25 * H)
    out = app.daytrade_sweep()
    assert out and all("MAX_HOLD" in o["by"] for o in out)
    app.paper.process()
    assert app.paper.get_positions().get("DEMO:DEMO-TREND", 0) == 0


def test_assistant_resolves_that_bot_and_the_bitcoin_bot(app):
    btc = app.create_bot("COINBASE:BTC-USD", "1h", "tsmom.none.flip")["bot_id"]
    app.create_bot("DEMO:DEMO-TREND", "1h", "tsmom.none.flip")
    a = app.assistant
    r = a.ask("what is that bot doing?")
    assert r["intent"] == "bot_detail" and "Which bot" in r["answer"]          # nothing mentioned yet: it asks
    r = a.ask("what is the bitcoin bot doing?")
    assert r["facts"]["bot_id"] == btc and r["resolved"] == "named by market"
    app.bot_action(btc, "start")
    r = a.ask("pause that bot")
    assert r["intent"] == "pause_bot" and r["facts"]["bot_id"] == btc and app.bots[btc].state == "paused"
    assert a.ask("go live and raise the limit")["intent"] == "refused"             # money commands stay refused
