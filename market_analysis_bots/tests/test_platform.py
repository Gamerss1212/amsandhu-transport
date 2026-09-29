"""Automated tests: indicator references, causality, rule language, trade manager, paper broker,
account, risk, storage, and the failure scenarios required before scaling (network failure,
stale data, duplicate / out-of-order bars, restart, corrupt state, invalid config, storage
failure, risk breach). No network access is used.

    python -m pytest tests -q
"""

import json
import math
import os
import random
import sqlite3
import sys
import urllib.error

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from mab import expr, indicators as I  # noqa: E402
from mab.account import Account  # noqa: E402
from mab.broker import PaperBroker  # noqa: E402
from mab.live import LiveExecutor  # noqa: E402
from mab.clock import MINUTE, nyse_holidays, ny_to_utc_ms, tsx_holidays  # noqa: E402
from mab.data.quality import SeriesQuality  # noqa: E402
from mab.frame import Frame  # noqa: E402
from mab.models import Bar, BookSnapshot, OrderIntent, now_ms  # noqa: E402
from mab.net import Http, HttpError  # noqa: E402
from mab.risk import RiskLimits, RiskManager  # noqa: E402
from mab.storage import Storage, StorageError  # noqa: E402
from mab.strategy import DefinitionError, TradeManager, compile_strategy, evaluate  # noqa: E402
from mab.costs import BacktestFiller, CostModel  # noqa: E402
from mab import backtest  # noqa: E402
from datetime import datetime


# ------------------------------------------------------------------ synthetic data
def crypto_bars(n=3000, tf="5m", seed=1, start=1_780_000_000_000):
    rnd = random.Random(seed)
    step = {"1m": 60_000, "5m": 300_000}[tf]
    start -= start % step
    p, out = 100.0, []
    for i in range(n):
        o = p
        c = max(1.0, o * (1 + rnd.gauss(0, 0.004)))
        h = max(o, c) * (1 + abs(rnd.gauss(0, 0.002)))
        l = min(o, c) * (1 - abs(rnd.gauss(0, 0.002)))
        out.append(Bar("test", "TST", tf, start + i * step, o, h, l, c, rnd.uniform(10, 100), 0, "synthetic"))
        p = c
    return out


def stock_bars(days=30, seed=2):
    rnd = random.Random(seed)
    out, p, d = [], 100.0, datetime(2026, 7, 6)
    from datetime import timedelta
    k = 0
    while k < days:
        if d.weekday() < 5 and d.date() not in nyse_holidays(d.year):
            t0 = ny_to_utc_ms(datetime(d.year, d.month, d.day, 9, 30))
            for j in range(78):
                o = p
                c = o * (1 + rnd.gauss(0, 0.002))
                out.append(Bar("yahoo", "TST", "5m", t0 + j * 300_000, o, max(o, c) * 1.001, min(o, c) * 0.999, c,
                               rnd.uniform(1e4, 1e5), 0, "synthetic"))
                p = c
            k += 1
        d += timedelta(days=1)
    return out


@pytest.fixture(scope="module")
def cf():
    return Frame("test", "TST", "5m", "crypto", crypto_bars())


@pytest.fixture(scope="module")
def sf():
    return Frame("yahoo", "TST", "5m", "stock", stock_bars())


# ------------------------------------------------------------------ indicators vs naive references
def naive_sma(x, n):
    return [None if i < n - 1 else sum(x[i - n + 1:i + 1]) / n for i in range(len(x))]


def naive_ema(x, n):
    out, prev = [None] * len(x), None
    for i in range(len(x)):
        if i == n - 1:
            prev = sum(x[:n]) / n
            out[i] = prev
        elif i >= n:
            prev = prev + 2 / (n + 1) * (x[i] - prev)
            out[i] = prev
    return out


def naive_rsi(x, n):
    out = [None] * len(x)
    g = [max(x[i] - x[i - 1], 0) for i in range(1, len(x))]
    l_ = [max(x[i - 1] - x[i], 0) for i in range(1, len(x))]
    ag, al = sum(g[:n]) / n, sum(l_[:n]) / n
    out[n] = 100 - 100 / (1 + ag / al) if al else 100.0
    for i in range(n + 1, len(x)):
        ag = (ag * (n - 1) + g[i - 1]) / n
        al = (al * (n - 1) + l_[i - 1]) / n
        out[i] = 100 - 100 / (1 + ag / al) if al else 100.0
    return out


def close_all(a, b, tol=1e-9):
    for u, v in zip(a, b):
        if u is None or v is None:
            assert u is None and v is None
        else:
            assert abs(u - v) <= tol * max(1.0, abs(v)), (u, v)


def test_reference_sma_ema_rsi(cf):
    ev = expr.Evaluator(cf)
    close_all(ev.series(expr.parse("sma(close,20)")), naive_sma(cf.c, 20))
    close_all(ev.series(expr.parse("ema(close,20)")), naive_ema(cf.c, 20))
    close_all(ev.series(expr.parse("rsi(close,14)")), naive_rsi(cf.c, 14))


def test_reference_bollinger_atr_donchian(cf):
    ev = expr.Evaluator(cf)
    up = ev.series(expr.parse("bb(close,20,2).upper"))
    for i in range(19, cf.n, 97):
        w = cf.c[i - 19:i + 1]
        m = sum(w) / 20
        sd = math.sqrt(sum((v - m) ** 2 for v in w) / 20)
        assert abs(up[i] - (m + 2 * sd)) < 1e-9
    dn = ev.series(expr.parse("donchian(20).upper"))
    for i in range(19, cf.n, 97):
        assert dn[i] == max(cf.h[i - 19:i + 1])
    tr = [cf.h[0] - cf.l[0]] + [max(cf.h[i] - cf.l[i], abs(cf.h[i] - cf.c[i - 1]), abs(cf.l[i] - cf.c[i - 1]))
                                 for i in range(1, cf.n)]
    a = ev.series(expr.parse("atr(14)"))
    prev = sum(tr[:14]) / 14
    assert abs(a[13] - prev) < 1e-12
    for i in range(14, 300):
        prev = prev + (tr[i] - prev) / 14
        assert abs(a[i] - prev) < 1e-9


def test_against_ta_library_when_available(cf):
    ta = pytest.importorskip("ta")
    pd = pytest.importorskip("pandas")
    df = pd.DataFrame({"h": cf.h, "l": cf.l, "c": cf.c, "v": cf.v})
    ev = expr.Evaluator(cf)
    pairs = [("macd(close,12,26,9).line", ta.trend.macd(df.c)), ("adx(14).adx", ta.trend.adx(df.h, df.l, df.c, 14)),
             ("cci(20)", ta.trend.cci(df.h, df.l, df.c, 20)), ("mfi(14)", ta.volume.money_flow_index(df.h, df.l, df.c, df.v, 14))]
    for e, ref in pairs:
        mine = ev.series(expr.parse(e))
        ref = list(ref)
        errs = [abs(a - b) / max(1e-9, abs(b)) for a, b in zip(mine[1000:], ref[1000:]) if a is not None and b == b and abs(b) > 1e-6]
        assert errs and max(errs) < 1e-6, e


# ------------------------------------------------------------------ no look-ahead: values never depend on later bars
@pytest.mark.parametrize("name", sorted(I.REGISTRY))
def test_indicator_is_causal(name, cf, sf):
    spec = I.REGISTRY[name]
    f = sf if name in ("premarket",) else cf
    cut = f.n - 137
    short = Frame(f.venue, f.instrument, f.tf, f.asset_type,
                  [Bar(f.venue, f.instrument, f.tf, f.t[i], f.o[i], f.h[i], f.l[i], f.c[i], f.v[i], 0, "") for i in range(cut)])
    full = I.compute(name, f, f.c if spec.series_input else None)
    part = I.compute(name, short, short.c if spec.series_input else None)
    for out in spec.outputs:
        a, b = full[out][:cut], part[out]
        for i in range(cut):
            if a[i] is None or b[i] is None:
                assert a[i] == b[i], (name, out, i)
            elif isinstance(a[i], float):
                assert abs(a[i] - b[i]) <= 1e-9 * max(1.0, abs(a[i])), (name, out, i, a[i], b[i])


def test_buffer_length_independence(cf):
    """Live buffers hold `stable` warm-up bars; the last value must match the full-history value."""
    for e in ("ema(close,20)", "rsi(close,14)", "atr(14)", "adx(14).adx", "macd(close,12,26,9).hist"):
        node = expr.parse(e)
        need = expr.warmup_bars(node, "5m")
        full = expr.Evaluator(cf).series(node)[-1]
        tail = expr.Evaluator(cf.tail(need + 5)).series(node)[-1]
        assert abs(full - tail) <= 1e-3 * max(1.0, abs(full)), (e, full, tail, need)


# ------------------------------------------------------------------ rule language
def test_rule_parsing_and_three_valued_logic(cf):
    ev = expr.Evaluator(cf)
    v = ev.series(expr.parse("sma(close,50) > 0 and close > 0"))
    assert v[10] is None and v[60] == 1.0
    v = ev.series(expr.parse("sma(close,50) > 0 or close > 0"))
    assert v[10] == 1.0
    with pytest.raises(expr.ExprError):
        expr.parse("close[-1] > 0")
    with pytest.raises(expr.ExprError):
        expr.parse("nosuch(close,3) > 1")
    with pytest.raises(expr.ExprError):
        expr.parse("ema(close,20).upper > 1")


def test_multi_timeframe_alignment_uses_completed_bars(cf):
    from mab.expr import align
    hourly = Frame("test", "TST", "1h", "crypto", [
        Bar("test", "TST", "1h", t - t % 3_600_000, 1, 1, 1, float(k), 1, 0, "") for k, t in enumerate(range(cf.t[0], cf.t[-1], 3_600_000))])
    vals = align(cf, hourly, hourly.c)
    for i in range(cf.n):
        if vals[i] is not None:
            j = int(vals[i])
            assert hourly.t[j] + hourly.step <= cf.t[i] + cf.step


# ------------------------------------------------------------------ trade manager, backtest, restart
DEF = {"id": "T-1", "name": "t", "timeframe": "5m", "direction": "both",
       "entry": {"long": "cross_above(ema(close,9), ema(close,21))", "short": "cross_below(ema(close,9), ema(close,21))"},
       "stop": {"type": "atr", "mult": 2.0, "n": 14}, "target": {"type": "r", "r": 2.0}, "max_trades_per_day": 50}


def test_backtest_deterministic(cf):
    c = compile_strategy(DEF)
    a = backtest.run(c, cf, "okx")
    b = backtest.run(c, cf, "okx")
    assert a.metrics == b.metrics and a.metrics["trades"] > 10


def test_restart_does_not_double_process(cf):
    c = compile_strategy(DEF)
    rs = evaluate(c, cf)
    tm = TradeManager(c, BacktestFiller(CostModel("okx")), lambda: 10_000.0)
    for i in range(1000):
        tm.on_bar(rs, i)
    st = json.loads(json.dumps(tm.state()))
    tm2 = TradeManager(c, BacktestFiller(CostModel("okx")), lambda: 10_000.0)
    tm2.restore(st)
    assert tm2.on_bar(rs, 999) == []                     # already processed bar: ignored
    assert (tm2.pos is None) == (tm.pos is None)
    for i in range(1000, 1500):
        a1, a2 = tm.on_bar(rs, i), tm2.on_bar(rs, i)
        assert [x["action"] for x in a1] == [x["action"] for x in a2]


def test_invalid_config_rejected():
    with pytest.raises(DefinitionError):
        compile_strategy({"id": "x", "name": "x", "timeframe": "5m", "entry": {"long": "rsi(close,) < 3"}})
    with pytest.raises(DefinitionError):
        compile_strategy({"id": "x", "name": "x", "timeframe": "5m", "entry": {"long": "close > 0"}, "stop": {"type": "bogus"}})
    with pytest.raises(DefinitionError):
        compile_strategy({"id": "x", "name": "x", "timeframe": "5m", "direction": "long", "entry": {"short": "close > 0"}})


def test_stop_checked_before_target_same_bar():
    bars = [Bar("t", "X", "5m", 1_780_000_000_000 + i * 300_000, 100, 100.5, 99.5, 100, 1, 0, "") for i in range(40)]
    bars.append(Bar("t", "X", "5m", bars[-1].event_time + 300_000, 100, 100.1, 99.9, 100.05, 1, 0, ""))
    bars.append(Bar("t", "X", "5m", bars[-1].event_time + 300_000, 100, 110, 90, 100, 1, 0, ""))   # hits both
    f = Frame("t", "X", "5m", "crypto", bars)
    c = compile_strategy({"id": "s", "name": "s", "timeframe": "5m", "direction": "long", "entry": {"long": "bar_in_session() == 40"},
                          "stop": {"type": "pct", "pct": 1.0}, "target": {"type": "r", "r": 1.0}})
    r = backtest.run(c, f, "okx", cost_mult=0.0)
    assert r.trades and r.trades[0].exit_reason.startswith("stop")


# ------------------------------------------------------------------ data quality: duplicates, out of order, stale
def test_duplicate_revised_and_late_bars():
    q = SeriesQuality("crypto", "1m")
    t0 = (now_ms() // MINUTE - 100) * MINUTE
    mk = lambda k, c=1.0: Bar("v", "X", "1m", t0 + k * MINUTE, c, c, c, c, 1, 0, "")
    known = {}
    new, rep = q.filter_batch([mk(0), mk(1), mk(1), mk(3)], known, None)
    assert [b.event_time for b in new] == [t0, t0 + MINUTE, t0 + 3 * MINUTE] and q.counts["duplicate"] == 1
    known = {b.event_time: b for b in new}
    new, rep = q.filter_batch([mk(2), mk(3, 1.1)], known, t0 + 3 * MINUTE)
    assert [b.event_time for b in new] == [t0 + 2 * MINUTE] and q.counts["late_fill"] == 1
    assert len(rep) == 1 and q.counts["revised"] == 1
    bad = Bar("v", "X", "1m", t0, 1, 0.5, 1, 1, 1, 0, "")
    new, _ = q.filter_batch([bad], {}, None)
    assert not new and q.counts.get("impossible") == 1


def test_stale_series_detected():
    q = SeriesQuality("crypto", "1m")
    assert q.evaluate_status(now_ms() - 30 * MINUTE, 500, 100) == "stale"
    assert q.evaluate_status(now_ms() - 2 * MINUTE, 500, 100) == "ok"
    assert q.evaluate_status(now_ms() - 2 * MINUTE, 50, 100) == "warming"


# ------------------------------------------------------------------ network failure: bounded retries, circuit breaker
def test_network_failure_breaker():
    calls = {"n": 0}

    def opener(req, timeout=0):
        calls["n"] += 1
        raise urllib.error.URLError("down")
    h = Http(opener=opener, max_retries=1, breaker_threshold=2, breaker_cooldown_s=60)
    for _ in range(2):
        with pytest.raises(HttpError):
            h.get_json("https://example.test/x")
    assert h.breaker_open("example.test")
    n = calls["n"]
    with pytest.raises(HttpError):
        h.get_json("https://example.test/x")
    assert calls["n"] == n                                # breaker open: no new request sent
    assert h.snapshot()["example.test"]["breaker_rejections"] == 1


# ------------------------------------------------------------------ paper broker: book walk, partial fill, rejections
class FakeAdapter:
    def __init__(self, book):
        self._b = book

    def book(self, symbol, depth=50):
        return self._b


class FakeHub:
    def __init__(self, book):
        self.adapters = {"coinbase": FakeAdapter(book)}


def test_paper_broker_partial_fill_and_rejections():
    book = BookSnapshot("coinbase", "X", now_ms(), [[99.9, 1.0]], [[100.0, 0.5], [100.2, 0.5], [101.0, 5.0]])
    acct = Account(100_000)
    pb = PaperBroker(FakeHub(book), acct, latency_ms=0, max_slippage_bps=50)
    inst = {"venue": "coinbase", "symbol": "X", "asset_type": "crypto", "lot_size": 0.0001, "min_notional": 1.0, "can_short": False}
    res = pb.execute(OrderIntent("i1", "b", "s", "X", "coinbase", "buy", "market", 2.0), 100.0, inst)
    assert res["status"] == "partially_filled" and abs(res["filled_qty"] - 1.0) < 1e-9
    assert abs(res["avg_price"] - 100.1) < 1e-9                   # walked two levels, stopped at the 50 bps limit
    res = pb.execute(OrderIntent("i2", "b", "s", "X", "coinbase", "sell", "market", 0.5), 100.0, inst)
    assert res["status"] == "rejected" and "short" in res["reason"]
    res = pb.execute(OrderIntent("i3", "b", "s", "X", "coinbase", "buy", "market", 0.001), 100.0, inst)
    assert res["status"] == "rejected" and "minimum" in res["reason"]


def test_live_trading_is_off_until_armed(tmp_path):
    st = Storage(str(tmp_path / "t.db"))
    ex = LiveExecutor(st, broker=object(), eligible=lambda b: (True, ""))
    assert not ex.armed and not ex.handles("any-bot")
    assert ex.check("any-bot") == (False, "live trading is not armed")


# ------------------------------------------------------------------ account: customizable balance, TWR
def test_balance_changes_are_not_performance():
    a = Account(10_000)
    a.apply_fill("b", "v", "X", "buy", 10, 100, 0.0)
    a.mark("v", "X", 110)
    assert abs(a.twr() - 0.01) < 1e-9
    a.deposit(5_000)
    a.set_balance(50_000)
    assert abs(a.twr() - 0.01) < 1e-9 and abs(a.equity() - 50_000) < 1e-6
    a.withdraw(1_000)
    assert abs(a.twr() - 0.01) < 1e-9
    with pytest.raises(ValueError):
        a.withdraw(10 ** 9)


# ------------------------------------------------------------------ risk breaches
def ctx(**k):
    base = {"equity": 100_000, "positions": [], "gross": 0.0, "net_by_instrument": {}, "paused": False, "emergency": False,
            "bot_enabled": True, "data_status": "ok", "price_age_ms": 1000, "bar_ms": 60_000, "ref_price": 100.0}
    base.update(k)
    return base


def test_risk_checks():
    rm = RiskManager(RiskLimits(max_instrument_exposure_pct=25))
    i = lambda iid, side="buy", q=10.0, ro=False: OrderIntent(iid, "B1", "S", "X", "v", side, "market", q, reduce_only=ro)
    assert rm.check(i("a"), ctx()).approved
    assert not rm.check(i("a"), ctx()).approved                                  # duplicate intent
    assert not rm.check(i("b"), ctx(data_status="stale")).approved
    assert not rm.check(i("c"), ctx(paused=True)).approved
    assert rm.check(i("d", ro=True), ctx(paused=True, emergency=True)).approved   # exits always allowed
    d = rm.check(i("e", q=1000), ctx())                                          # 100k notional > 25k cap: reduced
    assert d.approved and abs(d.adjusted_quantity * 100 - 25_000) < 1e-6
    opp = [{"bot_id": "B2", "venue": "v", "instrument": "X", "qty": -5}]
    assert not rm.check(i("f"), ctx(positions=opp)).approved                     # conflicting position
    ev = rm.on_equity(100_000, "2026-01-01")
    ev = rm.on_equity(96_000, "2026-01-01")
    assert any(e["kind"] == "daily_loss_halt" for e in ev)
    assert not rm.check(i("g"), ctx()).approved
    ev = rm.on_equity(80_000, "2026-01-02")
    assert any(e["kind"] == "drawdown_kill_switch" for e in ev)


# ------------------------------------------------------------------ storage: failure, corrupt state, backup/restore
def test_storage_failure_and_corrupt_state(tmp_path):
    st = Storage(str(tmp_path / "t.db"))
    st.save_bot_states({"B1": {"tm": {"pos": None}}})
    st.write("INSERT OR REPLACE INTO bot_state VALUES (?,?,?)", ("B2", "{not json", 0))
    states = st.load_bot_states()
    assert states["B1"]["tm"]["pos"] is None and states["B2"]["corrupt"]

    def boom():
        raise sqlite3.OperationalError("disk I/O error")
    st.fail_hook = boom
    with pytest.raises(StorageError):
        st.event("info", "x", "y")
    st.fail_hook = None
    p = st.backup(str(tmp_path / "bk"))
    assert os.path.exists(p) and st.check() == "ok"


def test_fleet_stops_entries_when_storage_fails(tmp_path):
    from mab.runtime import Fleet
    fl = Fleet({"data_dir": str(tmp_path / "d")}, {}, [], str(tmp_path))
    fl._save(lambda: (_ for _ in ()).throw(StorageError("full")))
    assert fl.storage_ok is False and len(fl.unsaved) == 1


# ------------------------------------------------------------------ calendars
def test_calendars():
    from datetime import date
    h = nyse_holidays(2026)
    assert date(2026, 4, 3) in h and date(2026, 6, 19) in h and date(2026, 11, 26) in h
    t = tsx_holidays(2026)
    assert date(2026, 12, 28) in t and date(2026, 8, 3) in t
