"""Evaluation protocol (see strategies/VALIDATION_METHODOLOGY.md).

* Parameters are fixed in the strategy definitions before any data is seen; nothing is optimised.
* Each dataset is split chronologically: train 60% | validation 20% | test 20%, with a one-day
  embargo between segments (intraday strategies are flat at the end of every session, so no
  trade spans a boundary). Walk-forward: the full period is also cut into 4 consecutive folds
  and the share of positive folds is reported.
* Candidate selection uses train + validation only; the test segment is looked at once, for
  the selected candidates, and that is what "out-of-sample tested" means.
* Every (strategy, instrument, cost level) run is a separate hypothesis test and is counted;
  p-values (one-sided t on per-trade R) are Holm-adjusted across all of them, and the best
  Sharpe is deflated for the number of trials.
* Costs: gross (0x), low-fee venue, and retail venue; stocks use commission-free fees plus
  regulatory sell fees and assumed spreads, with a 2x slippage stress.
"""

from __future__ import annotations

import hashlib
import json
import math
import subprocess
import time
from typing import Callable, Dict, List, Optional

from mab import backtest, metrics as M
from mab.clock import DAY
from mab.frame import Frame
from mab.strategy import compile_strategy, evaluate as eval_rules

SPLITS = (("train", 0.0, 0.6), ("validation", 0.6, 0.8), ("test", 0.8, 1.0))


def code_version() -> str:
    try:
        return subprocess.check_output(["git", "rev-parse", "--short", "HEAD"], stderr=subprocess.DEVNULL).decode().strip()
    except Exception:
        return "unknown"


def boundaries(frame: Frame) -> Dict[str, tuple]:
    t0, t1 = frame.t[0], frame.t[-1] + frame.step
    span = t1 - t0
    out = {}
    for name, a, b in SPLITS:
        s = t0 + int(span * a) + (DAY if a > 0 else 0)          # one-day embargo after the previous segment
        e = t0 + int(span * b)
        out[name] = (s, e)
    return out


def folds(frame: Frame, k: int = 4) -> List[tuple]:
    t0, t1 = frame.t[0], frame.t[-1] + frame.step
    w = (t1 - t0) // k
    return [(t0 + i * w + (DAY if i else 0), t0 + (i + 1) * w) for i in range(k)]


def run_one(definition: dict, frame: Frame, venue: str, cost_mult: float, resolver=None, events=None,
            asset_type: str = "crypto", params: Optional[dict] = None, can_short: bool = True) -> dict:
    c = compile_strategy(definition, params, asset_type)
    rs = eval_rules(c, frame, resolver, events)                  # rules computed once, reused by every segment
    out = {"segments": {}, "folds": []}
    for name, (s, e) in boundaries(frame).items():
        r = backtest.run(c, frame, venue, cost_mult=cost_mult, start=s, end=e, period=name, rs=rs, can_short=can_short)
        out["segments"][name] = {"metrics": r.metrics, "r": [t.r for t in r.trades if t.r is not None],
                                 "start": s, "end": e, "skipped": r.skipped}
    for s, e in folds(frame):
        r = backtest.run(c, frame, venue, cost_mult=cost_mult, start=s, end=e, period="fold", rs=rs, can_short=can_short)
        out["folds"].append({"trades": r.metrics["trades"], "net_return": r.metrics["net_return"],
                             "expectancy_r": r.metrics["expectancy_r"]})
    full = backtest.run(c, frame, venue, cost_mult=cost_mult, period="full", rs=rs, can_short=can_short)
    out["full"] = {"metrics": full.metrics, "r": [t.r for t in full.trades if t.r is not None]}
    out["cost"] = full.cost
    out["strategy_version"] = c.version_hash
    return out


def t_p(rs: List[float]):
    n = len(rs)
    if n < 10:
        return None, None
    m = sum(rs) / n
    sd = math.sqrt(sum((x - m) ** 2 for x in rs) / (n - 1)) if n > 1 else 0.0
    if sd == 0:
        return None, None
    t = m / (sd / math.sqrt(n))
    return t, M.p_value_from_t(t)


def experiment_id(spec: dict) -> str:
    return "EXP-" + hashlib.sha256(json.dumps(spec, sort_keys=True, default=str).encode()).hexdigest()[:10]
