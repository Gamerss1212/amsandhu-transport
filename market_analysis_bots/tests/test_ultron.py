"""ULTRON councils inside the bot platform: the strategies compile, the rule functions run on real-shaped frames and
their outputs line up (entry only where a stop exists, stop below the entry price)."""

import json
import math
import os
import random

import pytest

from mab import expr
from mab.frame import Frame
from mab.strategy import compile_strategy, evaluate, TradeManager
from mab.costs import BacktestFiller, CostModel

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
pytest.importorskip("numpy")


def _walk(n, step_ms, start_ms, seed, px=100.0):
    rng = random.Random(seed)
    t, o, h, l, c, v = [], [], [], [], [], []
    for i in range(n):
        op = px
        px *= math.exp(rng.gauss(0, 0.012 if step_ms >= 86_400_000 else 0.006))
        t.append(start_ms + i * step_ms)
        o.append(op)
        h.append(max(op, px) * (1 + abs(rng.gauss(0, 0.003))))
        l.append(min(op, px) * (1 - abs(rng.gauss(0, 0.003))))
        c.append(px)
        v.append(abs(rng.gauss(1000, 300)))
    return t, o, h, l, c, v


def _strategies():
    with open(os.path.join(ROOT, "strategies", "catalog.json"), encoding="utf-8") as fh:
        return {s["id"]: s for s in json.load(fh)["strategies"] if s["id"].startswith("STRAT-U")}


def test_ultron_functions_registered():
    assert {"ultron", "ultron_stop", "ultron_edge"} <= set(expr.FUNCS)
    need = expr.warmup_by_series(expr.parse('ultron("4h") > 0'), "1h", "crypto")
    assert need[(None, "1h")] >= 1600 and need[(None, "1d")] >= 300 and ("coinbase:BTC-USD", "1d") in need


@pytest.mark.parametrize("sid", ["STRAT-U01", "STRAT-U02", "STRAT-U03", "STRAT-U04", "STRAT-U05"])
def test_ultron_strategy_runs(sid):
    s = _strategies()[sid]
    d = s["definition"]
    daily = d["timeframe"] == "1d"
    asset = "stock" if daily else "crypto"
    inst = "SPY" if daily else ("BTC-USD" if "MAJORS" in s["name"].upper() or "BTC" in s["name"] else "DOGE-USD")
    step = 86_400_000 if daily else 3_600_000
    start = 1_700_000_000_000 // 86_400_000 * 86_400_000 + (13 * 3_600_000 + 1_800_000 if daily else 0)
    n = 800 if daily else 1800
    cols = _walk(n, step, start, seed=7)
    f = Frame.from_columns("yahoo" if daily else "coinbase", inst, d["timeframe"], asset, *cols)
    dcols = _walk(400, 86_400_000, start - 300 * 86_400_000, seed=11)
    btc_d = Frame.from_columns("coinbase", "BTC-USD", "1d", "crypto", *dcols)
    own_d = Frame.from_columns("coinbase", inst, "1d", "crypto", *dcols)
    resolver = lambda v, sym, tf: btc_d if sym == "BTC-USD" else own_d if tf == "1d" else None   # noqa: E731
    c = compile_strategy(d, {}, asset)
    rs = evaluate(c, f, resolver)
    ent, stop = rs.values["entry_long"], rs.values["stop_long"]
    assert len(ent) == len(stop) == n
    for i in range(n):
        if ent[i]:
            assert stop[i] is not None and stop[i] < f.c[i]
    tm = TradeManager(c, BacktestFiller(CostModel(f.venue, "major")), lambda: 10_000.0)
    for i in range(n):
        tm.on_bar(rs, i)                                       # trade management runs without error
    assert d["order"]["type"] == "market"                       # live trading supports market entries only
