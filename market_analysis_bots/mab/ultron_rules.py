"""The trained ULTRON councils as rule functions, so the Jarvus Terminal's bots can trade them (paper or live).

    ultron("1h")        1 on the 1h bar where the 1h crypto council approves a long entry, else 0
    ultron("4h")        the 4h crypto council, on a 1h chart: 1 on the 1h bar that closes the approved 4h bar
    ultron("1D")        the daily markets council (stocks, ETFs, forex, commodity ETFs) on a 1d chart
    ultron_stop("1h")   the council's stop-loss price for that entry (the entry is a limit 0.1% under the close)
    ultron_edge("1h")   the council's learned edge for that entry, in R

The councils are the same frozen models as the TradingView indicator and the ULTRON app (ultron/assets/councils),
evaluated bar by bar with ultron/core/council.series (parity-checked against the training data). They need numpy;
without it these functions are simply not registered and every other rule keeps working.
"""

from __future__ import annotations

import json
import os
import sys
from datetime import datetime, timedelta, timezone

from mab import expr

HERE = os.path.dirname(os.path.abspath(__file__))
_FROZEN = getattr(sys, "_MEIPASS", None)
if not _FROZEN:
    _REPO = os.path.dirname(os.path.dirname(HERE))
    for _p in (os.path.join(_REPO, "jarvus", "scripts"), os.path.join(_REPO, "ultron", "core"), os.path.join(_REPO, "ultron", "tv")):
        if _p not in sys.path:
            sys.path.append(_p)

try:
    import numpy as np  # noqa: F401
    import council as cn
    import events as _ev
    AVAILABLE = True
except ImportError:                                          # pragma: no cover - numpy missing
    AVAILABLE = False

DAY = 86_400_000
HOUR = 3_600_000
FILES = {"1h": "1h.json", "4h": "4h.json", "1D": "1D_markets.json"}
MAJORS = {"BTC", "ETH", "SOL"}
FEES = {"crypto": (0.002, 0.002), "markets": (0.0005, 0.0005)}        # the costs each council was trained with
SLIP = {"majors": 0.0002, "memes": 0.001, "markets": 0.0002}
# history each council needs: (instrument or None, timeframe) -> bars
NEEDS = {"1h": {(None, "1h"): 1600, ("coinbase:BTC-USD", "1d"): 260},
         "4h": {(None, "1h"): 1700, (None, "1d"): 320, ("coinbase:BTC-USD", "1d"): 260},
         "1D": {(None, "1d"): 700}}
_MODELS = {}


def councils_dir():
    for d in (os.environ.get("ULTRON_COUNCILS"), os.path.join(_FROZEN, "ultron_councils") if _FROZEN else None,
              os.path.join(os.path.dirname(os.path.dirname(HERE)), "ultron", "assets", "councils")):
        if d and os.path.isdir(d):
            return d
    return None


def model(name):
    if name not in _MODELS:
        d = councils_dir()
        if not d:
            raise expr.ExprError("ULTRON council files not found")
        with open(os.path.join(d, FILES[name]), encoding="utf-8") as fh:
            _MODELS[name] = json.load(fh)
    return _MODELS[name]


def _weekend_mt(t_ms):
    dt = datetime.fromtimestamp(t_ms / 1000, timezone.utc)
    dt -= timedelta(hours=6 if _ev.us_dst(dt.date()) else 7)
    return dt.weekday() >= 5


def _btc_bull_by_day(ev):
    """Previous completed UTC day's BTC close vs its 200-day average, from the hub's BTC daily bars."""
    if ev.resolver is None:
        return None
    g = ev.resolver("coinbase", "BTC-USD", "1d")
    if g is None or g.n < 200:
        return None
    out = {}
    for i in range(199, g.n):
        out[g.t[i] // DAY] = g.c[i] > sum(g.c[i - 199:i + 1]) / 200
    return out


def _name_arg(node):
    if len(node.args) != 1 or not isinstance(node.args[0], expr.Str) or node.args[0].v not in FILES:
        raise expr.ExprError('ultron needs one of "1h", "4h", "1D", in quotes')
    return node.args[0].v


def compute(ev, name):
    """{"ok": [...], "stop": [...], "edge": [...]} aligned to the frame, cached on the frame."""
    f = ev.f
    key = "ultron:" + name
    if key in f.cache:
        return f.cache[key]
    n = f.n
    res = {"ok": [0.0] * n, "stop": [None] * n, "edge": [None] * n}
    if not AVAILABLE:
        raise expr.ExprError("ULTRON needs numpy (bundled in the Windows app)")
    m = model(name)
    if name == "1D":
        if f.tf != "1d":
            raise expr.ExprError('ultron("1D") runs on a 1d chart')
        c = f.c
        bull = [None if i < 201 else c[i - 1] > sum(c[i - 201:i - 1]) / 200 for i in range(n)]
        ok, dist, edge, _ = cn.series(m, f.t, f.o, f.h, f.l, f.c, f.v, bull, None, FEES["markets"], SLIP["markets"], "markets",
                                      market=True)
        idx = range(n)
        ref = f.c
    else:
        if f.tf != "1h":
            raise expr.ExprError(f'ultron("{name}") runs on a 1h chart')
        base = f.instrument.split("-")[0].split("/")[0].upper()
        group = "majors" if base in MAJORS else "memes"
        bull_day = _btc_bull_by_day(ev)
        if name == "1h":
            t, o, h, l, c, v = f.t, f.o, f.h, f.l, f.c, f.v
            idx = range(n)
        else:                                                   # 4h bars from the 1h chart (complete buckets only)
            rows = cn.aggregate([[f.t[i], f.o[i], f.h[i], f.l[i], f.c[i], f.v[i]] for i in range(n)], 4 * HOUR)
            if not rows:
                f.cache[key] = res
                return res
            t, o, h, l, c, v = (list(x) for x in zip(*rows))
            pos = {f.t[i]: i for i in range(n)}
            idx = [pos.get(x + 3 * HOUR) for x in t]            # the 1h bar that closes each 4h bar
        size = cn.SIZE[name]
        bull = [None if bull_day is None else bull_day.get(x // DAY - 1) for x in t]
        wk = [_weekend_mt(x + size) for x in t]
        ok, dist, edge, _ = cn.series(m, t, o, h, l, c, v, bull, wk, FEES["crypto"], SLIP[group], group)
        ref = c
    for j, i in enumerate(idx):
        if i is None or not ok[j]:
            continue
        res["ok"][i] = 1.0
        res["stop"][i] = ref[j] * 0.999 - dist[j]
        res["edge"][i] = edge[j]
    f.cache[key] = res
    return res


if AVAILABLE:
    @expr.fn("ultron", 1, 'ultron("1h" | "4h" | "1D"): 1 where the trained ULTRON council approves a long entry')
    def _ultron(ev, node):
        return compute(ev, _name_arg(node))["ok"]

    @expr.fn("ultron_stop", 1, 'ultron_stop("1h"): the ULTRON council\'s stop-loss price for its entry on this bar')
    def _ultron_stop(ev, node):
        return compute(ev, _name_arg(node))["stop"]

    @expr.fn("ultron_edge", 1, 'ultron_edge("1h"): the ULTRON council\'s learned edge (R) for its entry on this bar')
    def _ultron_edge(ev, node):
        return compute(ev, _name_arg(node))["edge"]

    def _warm(node, ctx, asset_type):
        name = node.args[0].v if node.args and isinstance(node.args[0], expr.Str) else "1h"
        return list(NEEDS.get(name, {}).items())

    for _fn in ("ultron", "ultron_stop", "ultron_edge"):
        expr.WARMUP_HOOKS[_fn] = _warm
