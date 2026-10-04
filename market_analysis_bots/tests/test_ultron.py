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


def test_research_job_feeds_the_council_its_other_history(monkeypatch, tmp_path):
    """The walk-forward research job (needed to approve a version for live) loads the warm-up and the series the
    council reads besides its own chart: the BTC daily trend and the coin's daily bars."""
    from mab.models import Bar, now_ms
    from mab.research import data as D, worker
    asked = []

    def fake_fetch(venue, sym, tf, days, cache_dir=None, **kw):
        asked.append((venue, sym, tf, days))
        step = 86_400_000 if tf == "1d" else 3_600_000
        n = days * 86_400_000 // step
        end = now_ms() // step * step
        cols = _walk(n, step, end - n * step, seed=len(asked))
        bars = [Bar(venue, sym, tf, *row) for row in zip(*cols)]
        return bars, {"fingerprint": f"{sym}{tf}{n}"}

    monkeypatch.setattr(D, "fetch", fake_fetch)
    cache = SimpleQueue()
    d = dict(_strategies()["STRAT-U03"]["definition"], id="STRAT-U03")
    res, _, _ = worker.walk_forward(None, cache, {"definition": d, "venue": "coinbase", "instrument": "BTC-USD",
                                                  "days": 180, "draws": 5}, str(tmp_path), lambda f, m: None)
    got = {(v, s, tf): days for v, s, tf, days in asked}
    assert got[("coinbase", "BTC-USD", "1h")] >= 180 + 1700 / 24              # the window plus the council's warm-up
    assert ("coinbase", "BTC-USD", "1d") in got
    assert set(res["segments"]) >= {"train", "validation", "test"} and "checks" in res


def test_4h_council_does_not_wait_for_the_exchange_to_publish_the_daily_bar(monkeypatch):
    """Just after midnight UTC the hourly chart has closed the day before the daily feed shows it: the council builds
    that day from the hourly bars, so it sees the same daily history as with the published bar."""
    from mab import ultron_rules
    import council as cn
    day, hour = 86_400_000, 3_600_000
    start = 1_700_000_000_000 // day * day
    cols = _walk(24 * 95, hour, start, seed=3)
    rows = cn.aggregate([list(r) for r in zip(*cols)], day)
    early = _walk(300, day, start - 300 * day, seed=53)
    full = [list(a) + [r[k] for r in rows] for k, a in enumerate(early)]
    seen = {}
    real = cn.series

    def spy(*a, **kw):
        seen[len(seen)] = [list(x) for x in kw["htf"]]
        return real(*a, **kw)

    monkeypatch.setattr(cn, "series", spy)
    for daily in (full, [c[:-1] for c in full]):                 # published, and not published yet
        g = Frame.from_columns("coinbase", "BTC-USD", "1d", "crypto", *daily)
        f = Frame.from_columns("coinbase", "BTC-USD", "1h", "crypto", *cols)
        ultron_rules.compute(expr.Evaluator(f, lambda v, s, t: g), "4h")
    assert seen[0] == seen[1] and seen[1][0][-1] == rows[-1][0]


def test_daily_backfill_still_warms_up_when_some_bars_are_invalid():
    """Yahoo forex history has bad bars (high below low...); the back-fill keeps enough good ones for the council."""
    from mab.data.hub import Hub
    from mab.models import Bar, now_ms
    from mab.net import Http
    day = 86_400_000
    end = now_ms() // day * day

    class Yahoo:
        def supports(self, tf):
            return True

        def bars(self, symbol, tf, limit=300, prepost=False, **kw):
            out = []
            for k in range(1200, 0, -1):
                t, px = end - k * day, 1.1 + 0.001 * (k % 17)
                hi, lo = (px * 0.99, px * 1.01) if k % 25 == 0 else (px * 1.01, px * 0.99)   # every 25th is impossible
                out.append(Bar("yahoo", symbol, tf, t, px, hi, lo, px, 0.0))
            return out

    h = Hub(Http())
    h.adapters["yahoo"] = Yahoo()
    s = h.subscribe("yahoo", "EURUSD=X", "1d", 705, "bot", "forex")
    h.refresh(s)
    assert len(s.times) >= 705 and s.status() != "warming"


class SimpleQueue:
    def cache_get(self, key):
        return None


def test_live_record_judged_at_the_fees_paid():
    from types import SimpleNamespace
    from mab.runtime import Fleet
    rows = [{"cost": "retail_kraken", "candidate": True, "test": {"expectancy_r": -0.1, "trades": 15}},
            {"cost": "ndax", "candidate": True, "test": {"expectancy_r": 0.5, "trades": 15}}]
    fleet = SimpleNamespace(fee_profile="ndax", _evaluation_rows=lambda sid: rows)
    br = SimpleNamespace(venue="coinbase", c=SimpleNamespace(id="STRAT-U01"))
    assert Fleet._eval_cost_key(fleet, br) == "ndax"
    fleet.fee_profile = "kraken"
    assert Fleet._eval_cost_key(fleet, br) == "retail_kraken"
    assert Fleet._eval_cost_key(fleet, SimpleNamespace(venue="yahoo", c=br.c)) == "base"


def test_yahoo_weekend_forex_snapshot_is_not_an_extra_day():
    """Seen on EURUSD=X on a Sunday: Friday's session as 'Thu 23:00' plus a second row stamped with the last trade time
    'Fri 21:29'. That is one day, not two: one bar at the session's time with the newest values (as in training)."""
    from mab.data.adapters import Yahoo
    wed, thu, fri_snap = 1790809200, 1790895600, 1790976540           # Wed 23:00, Thu 23:00, Fri 21:29 UTC

    class Http:
        def get_json(self, url, params=None):
            return {"chart": {"result": [{"meta": {"gmtoffset": 3600}, "timestamp": [wed, thu, fri_snap],
                                          "indicators": {"quote": [{"open": [1.1327, 1.12488, 1.12435],
                                                                    "high": [1.134, 1.1251, 1.1265],
                                                                    "low": [1.131, 1.1247, 1.1238],
                                                                    "close": [1.1327, 1.12499, 1.12575],
                                                                    "volume": [0, 0, 0]}]}}]}}

    bars = Yahoo(Http()).bars("EURUSD=X", "1d", limit=10)
    assert [b.event_time // 1000 for b in bars] == [wed, thu]
    assert bars[-1].close == 1.12575 and bars[-1].open == 1.12435


def test_forex_is_not_stale_over_the_weekend(monkeypatch):
    from mab.data import quality
    from mab.data.quality import SeriesQuality
    day, hour = 86_400_000, 3_600_000
    fri_session = 1790895600000                                     # Thu 23:00 UTC: Friday's forex session
    sun_noon = fri_session + 2 * day + 13 * hour                    # Sunday 12:00 UTC, market shut
    monkeypatch.setattr(quality, "now_ms", lambda: sun_noon)
    assert SeriesQuality("forex", "1d").evaluate_status(fri_session, 800, 705) == "ok"
    assert SeriesQuality("crypto", "1d").evaluate_status(fri_session, 800, 705) == "stale"
    monkeypatch.setattr(quality, "now_ms", lambda: sun_noon + 3 * day)          # Wednesday: really stale
    assert SeriesQuality("forex", "1d").evaluate_status(fri_session, 800, 705) == "stale"
