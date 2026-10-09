"""Portfolio (multi-asset) research for the catalog templates that are defined on a universe, not one chart:
time-series momentum across assets (ST001), relative + absolute momentum (ST004), volatility-managed exposure (ST005),
cross-sectional equity momentum (ST009), sector rotation (ST010), low volatility (ST017), short-term reversal (ST018),
currency momentum (ST040), crypto time-series and cross-sectional momentum (ST045, ST046).

Method, the same for every template:
* Daily closes (provider-adjusted where the provider adjusts) aligned by trading day; gaps are forward-filled for at
  most 5 days and an instrument contributes nothing before its first real bar.
* Weights are decided at a rebalance close using only closes up to that day, and take effect at the NEXT day's close
  (one full day of delay). Costs are charged on every change of weight, per instrument, from the same cost model the
  backtester and paper broker use. Gross exposure is capped at 1.0: no leverage.
* Parameters are chosen on the first 70% of rebalance dates only; the last 30% is held out and reported separately.
  Every parameter set counts as a trial for the deflated Sharpe ratio, together with earlier trials of the family.
* Benchmarks: an equal-weight, monthly rebalanced holding of the same universe, and cash.
* Verdicts: PAPER TEST only if every required gate passes; reason codes say why not.

These are adaptations of published families (the catalog's evidence labels say which); the code here does not
replicate any paper's exact method or sample.
"""

from __future__ import annotations

import math
import threading
import time
from dataclasses import dataclass, field
from itertools import product
from typing import Callable, Optional

import numpy as np

from tradingai.backtest.costs import default_for
from tradingai.core.reasons import code_for
from tradingai.market.instruments import Instrument, MarketType
from tradingai.research import stats as S

DAY = 86_400_000
A = np.ndarray


@dataclass
class PortfolioSpec:
    sid: str                     # catalog id, e.g. "ST004"; variants carry a suffix ("ST001-E")
    name: str
    universe: list[str]
    rebalance: str               # "M" month-end or "W" week-end
    fn: Callable[..., A]
    params: dict
    grid: dict
    long_only: bool = True
    note: str = ""
    limitations: list[str] = field(default_factory=list)
    max_verdict: str = "PAPER TEST"          # survivorship-biased universes are capped at RESEARCH FURTHER
    cash_proxy: Optional[str] = None


PORTFOLIOS: dict[str, PortfolioSpec] = {}


def portfolio(sid, name, universe, rebalance, params, grid, **kw):
    def deco(fn):
        PORTFOLIOS[sid] = PortfolioSpec(sid, name, list(universe), rebalance, fn, dict(params), dict(grid), **kw)
        return fn
    return deco


# ---------------------------------------------------------------------------------------------- helpers
def _ret(c: A, t: int, n: int) -> A:
    """n-day return to day t for every column (NaN where history is missing)."""
    if t - n < 0:
        return np.full(c.shape[1], np.nan)
    with np.errstate(divide="ignore", invalid="ignore"):
        return c[t] / c[t - n] - 1


def _vol(r: A, t: int, n: int, ppy: float) -> A:
    if t - n < 1:
        return np.full(r.shape[1], np.nan)
    w = r[t - n + 1:t + 1]
    ok = np.isfinite(w).sum(axis=0) >= int(n * 0.8)
    v = np.nanstd(w, axis=0, ddof=1) * math.sqrt(ppy)
    return np.where(ok, v, np.nan)


def _cap_gross(w: A, cap: float = 1.0) -> A:
    w = np.nan_to_num(w)
    g = np.abs(w).sum()
    return w * (cap / g) if g > cap else w


def _top(score: A, k: int, mask: Optional[A] = None) -> A:
    s = np.where(np.isfinite(score) & (mask if mask is not None else True), score, -np.inf)
    idx = [i for i in np.argsort(-s)[:k] if np.isfinite(s[i])]
    w = np.zeros(len(score))
    if idx:
        w[idx] = 1.0 / len(idx)
    return w


# ---------------------------------------------------------------------------------------------- templates
FUT_FX = ["CME:ES", "CME:NQ", "CBOT:YM", "CME:RTY", "COMEX:GC", "NYMEX:CL", "CBOT:ZN", "FX:EURUSD", "FX:GBPUSD",
          "FX:USDJPY", "FX:USDCAD", "FX:AUDUSD"]
ETF_ASSETS = ["US:SPY", "US:EFA", "US:EEM", "US:TLT", "US:IEF", "US:GLD", "US:DBC", "US:VNQ"]
SECTORS = ["US:XLK", "US:XLF", "US:XLV", "US:XLY", "US:XLP", "US:XLI", "US:XLB", "US:XLU", "US:XLE"]
STOCKS = ["US:AAPL", "US:MSFT", "US:NVDA", "US:AMZN", "US:TSLA", "US:JPM", "US:XOM"]
CRYPTO = ["COINBASE:BTC-USD", "COINBASE:ETH-USD", "COINBASE:SOL-USD"]
FXP = ["FX:EURUSD", "FX:GBPUSD", "FX:USDJPY", "FX:USDCAD", "FX:AUDUSD"]


def _tsmom(c, r, t, ppy, lookback, target, long_only):
    sig = np.sign(_ret(c, t, lookback))
    if long_only:
        sig = np.where(sig > 0, 1.0, 0.0)
    vol = _vol(r, t, 63, ppy)
    n = max(1, int(np.isfinite(vol).sum()))
    with np.errstate(divide="ignore", invalid="ignore"):
        w = sig * (target / math.sqrt(n)) / vol
    w = np.clip(np.nan_to_num(w), -2.0 / n, 2.0 / n)
    return _cap_gross(w)


@portfolio("ST001", "Time-series momentum, futures and FX (long/short, volatility-scaled)", FUT_FX, "M",
           {"lookback": 252, "target": 0.10}, {"lookback": [126, 189, 252], "target": [0.10]}, long_only=False,
           note="sign of each instrument's trailing return, sized by 63-day volatility, monthly",
           limitations=["provider continuous futures series: contract rolls appear as price jumps (no real roll "
                        "or roll yield modelled)", "FX uses reference mid prices; financing/carry not modelled",
                        "excess return over cash not computed (no risk-free series): uses total price return"])
def st001(c, r, t, ppy, lookback=252, target=0.10):
    return _tsmom(c, r, t, ppy, lookback, target, long_only=False)


@portfolio("ST001-E", "Time-series momentum, ETF asset-class proxies (long/flat, volatility-scaled)", ETF_ASSETS, "M",
           {"lookback": 252, "target": 0.10}, {"lookback": [126, 189, 252], "target": [0.10]},
           note="adaptation: ETFs instead of futures, long or flat (no ETF shorting in this paper engine)",
           limitations=["long/flat adaptation of a long/short source design"])
def st001e(c, r, t, ppy, lookback=252, target=0.10):
    return _tsmom(c, r, t, ppy, lookback, target, long_only=True)


def _dual(c, t, lookback, k, risky_n):
    risky = _ret(c, t, lookback)[:risky_n]
    safe = _ret(c, t, lookback)[risky_n]
    w = np.zeros(c.shape[1])
    pick = _top(risky, k)
    for i in np.nonzero(pick)[0]:
        if np.isfinite(safe) and risky[i] > safe:
            w[i] = pick[i]
        else:
            w[risky_n] += pick[i]                 # the absolute filter failed: that slot goes to the cash proxy
    return w


DUAL = ["US:SPY", "US:EFA", "US:EEM", "US:QQQ", "US:GLD", "US:TLT", "US:SHY"]


@portfolio("ST004", "Relative momentum with an absolute-trend filter (dual momentum)", DUAL, "M",
           {"lookback": 252, "k": 1}, {"lookback": [126, 252], "k": [1, 2]}, cash_proxy="US:SHY",
           note="hold the k strongest of six ETFs by trailing return, only while each beats short Treasuries (SHY); "
                "otherwise hold SHY")
def st004(c, r, t, ppy, lookback=252, k=1):
    return _dual(c, t, lookback, k, len(DUAL) - 1)


@portfolio("ST005", "Volatility-managed dual momentum", DUAL, "M",
           {"lookback": 252, "k": 1, "target": 0.10}, {"lookback": [126, 252], "k": [1], "target": [0.08, 0.12]},
           cash_proxy="US:SHY",
           note="ST004's holdings scaled by target volatility / their own lagged 21-day volatility, capped at 1.0",
           limitations=["volatility management applied to an ETF rotation, not the source's factor portfolios"])
def st005(c, r, t, ppy, lookback=252, k=1, target=0.10):
    w = _dual(c, t, lookback, k, len(DUAL) - 1)
    if t < 22:
        return w
    pr = np.nansum(np.nan_to_num(r[t - 20:t + 1]) * w, axis=1)
    v = float(np.std(pr, ddof=1) * math.sqrt(ppy)) if len(pr) > 2 else 0.0
    return w * (min(1.0, target / v) if v > 0 else 1.0)


@portfolio("ST009", "Cross-sectional equity momentum (12-1), long-only", STOCKS, "M",
           {"lookback": 252, "skip": 21, "k": 2}, {"lookback": [252], "skip": [21], "k": [2, 3]},
           note="rank returns from 12 months to 1 month before the decision; hold the top k equally weighted",
           limitations=["SURVIVORSHIP BIAS: today's large companies, no point-in-time membership or delistings",
                        "long-only adaptation (the source ranks winners minus losers)", "seven stocks only"],
           max_verdict="RESEARCH FURTHER")
def st009(c, r, t, ppy, lookback=252, skip=21, k=2):
    if t - lookback < 0:
        return np.zeros(c.shape[1])
    with np.errstate(divide="ignore", invalid="ignore"):
        score = c[t - skip] / c[t - lookback] - 1
    return _top(score, k)


@portfolio("ST010", "Sector rotation with an absolute filter", SECTORS, "M",
           {"lookback": 126, "k": 3}, {"lookback": [63, 126, 252], "k": [2, 3]},
           note="hold the k strongest SPDR sectors by trailing return, each only while its return is positive")
def st010(c, r, t, ppy, lookback=126, k=3):
    s = _ret(c, t, lookback)
    w = _top(s, k, s > 0)
    return np.where(w > 0, 1.0 / k, 0.0)                  # an unfilled slot stays in cash


@portfolio("ST017", "Long-only low-volatility sector portfolio", SECTORS, "M",
           {"window": 126, "k": 4}, {"window": [63, 126, 252], "k": [3, 4]},
           note="hold the k sectors with the lowest lagged realized volatility, equally weighted")
def st017(c, r, t, ppy, window=126, k=4):
    v = _vol(r, t, window, ppy)
    return _top(-v, k)


@portfolio("ST018", "Short-term reversal, long-only (weekly)", STOCKS + SECTORS, "W",
           {"lookback": 5, "k": 3, "max_move": 0.15}, {"lookback": [5, 10], "k": [2, 3, 4], "max_move": [0.15]},
           note="buy the k weakest names of the last week; skip moves larger than 15% (likely news)",
           limitations=["long-only adaptation; no news data, so the news exclusion is a size proxy",
                        "SURVIVORSHIP BIAS in the stock part of the universe"], max_verdict="RESEARCH FURTHER")
def st018(c, r, t, ppy, lookback=5, k=3, max_move=0.15):
    s = _ret(c, t, lookback)
    return _top(-s, k, np.abs(s) < max_move)


@portfolio("ST040", "Cross-sectional currency momentum (long/short vs USD)", FXP, "M",
           {"lookback": 126, "k": 1}, {"lookback": [63, 126, 252], "k": [1, 2]}, long_only=False,
           note="currencies ranked by trailing return against USD; long the strongest k, short the weakest k",
           limitations=["reference mid prices; no financing (carry) in returns", "five currencies only"])
def st040(c, r, t, ppy, lookback=126, k=1):
    rr = _ret(c, t, lookback)
    inv = np.array([1.0, 1.0, -1.0, -1.0, 1.0])       # USDJPY and USDCAD quote USD first: invert to get the currency
    cur = rr * inv
    if not np.isfinite(cur).all():
        return np.zeros(len(cur))
    order = np.argsort(-cur)
    w = np.zeros(len(cur))
    for i in order[:k]:
        w[i] += 0.5 / k * inv[i]
    for i in order[-k:]:
        w[i] -= 0.5 / k * inv[i]
    return w


@portfolio("ST045", "Crypto time-series momentum (long/flat, volatility-scaled, weekly)", CRYPTO, "W",
           {"lookback": 28, "target": 0.30}, {"lookback": [14, 28, 56], "target": [0.30]},
           note="each coin held only while its trailing return is positive, sized by its own 30-day volatility",
           limitations=["spot long/flat: shorting is not available for spot crypto here", "three coins"])
def st045(c, r, t, ppy, lookback=28, target=0.30):
    sig = np.where(_ret(c, t, lookback) > 0, 1.0, 0.0)
    vol = _vol(r, t, 30, ppy)
    n = max(1, int(np.isfinite(vol).sum()))
    with np.errstate(divide="ignore", invalid="ignore"):
        w = sig * (target / math.sqrt(n)) / vol
    return _cap_gross(np.clip(np.nan_to_num(w), 0, 1.0 / n * 2))


@portfolio("ST046", "Crypto cross-sectional momentum (long-only, weekly)", CRYPTO, "W",
           {"lookback": 21, "k": 1}, {"lookback": [7, 21, 42], "k": [1]},
           note="hold the coin with the strongest trailing return, only while that return is positive",
           limitations=["three coins: too small a cross-section for the source's portfolio sorts",
                        "long-only (no spot shorting)"], max_verdict="RESEARCH FURTHER")
def st046(c, r, t, ppy, lookback=21, k=1):
    s = _ret(c, t, lookback)
    return _top(s, k, s > 0)


# ---------------------------------------------------------------------------------------------- data
def cost_rate(inst: Instrument, price: float) -> float:
    """One-way cost as a fraction of notional, from the shared cost model (fees + half spread + a slippage share)."""
    cm = default_for(inst)
    if inst.market_type is MarketType.FX_OTC:
        spread = cm.half_spread_pips * cm.pip / price if price > 0 else 0.0
        return spread + 0.00005
    if inst.market_type in (MarketType.FUTURE, MarketType.FX_FUTURE):
        notional = price * float(inst.multiplier)
        return (cm.fee_per_contract / notional if notional > 0 else 0) + cm.half_spread_ticks * float(inst.tick_size) / \
            price + 0.0001
    return cm.commission_pct + cm.half_spread_bps / 1e4 + 0.0002


def load_panel(md, book, universe: list[str], lookback: int = 4000) -> dict:
    series = {}
    status = {}
    for iid in universe:
        b, st = md.bars(iid, "1d", lookback=lookback, max_age_s=3600)
        if len(b) < 252:                                             # one retry: providers fail transiently
            time.sleep(1.0)
            b, st = md.bars(iid, "1d", lookback=lookback, max_age_s=0)
        status[iid] = {"bars": len(b), "provider": st.get("provider"), "fresh": st.get("fresh"), "error": st.get("error")}
        if len(b):
            keys = (b.ts + 6 * 3_600_000) // DAY                     # trading day (handles 23:00 UTC FX labels)
            series[iid] = dict(zip(keys.tolist(), b.close.tolist()))
    days = sorted(set().union(*[set(s) for s in series.values()])) if series else []
    if not days:
        raise ValueError("no daily data for this universe")
    if not any(book.get(i).market_type is MarketType.CRYPTO_SPOT for i in universe):
        days = [d for d in days if (d + 4) % 7 < 5]                  # drop weekends unless the universe trades 24/7
    T, N = len(days), len(universe)
    c = np.full((T, N), np.nan)
    for j, iid in enumerate(universe):
        s = series.get(iid, {})
        last, age = np.nan, 99
        for t, d in enumerate(days):
            if d in s:
                last, age = s[d], 0
            else:
                age += 1
            c[t, j] = last if age <= 5 else np.nan
    with np.errstate(divide="ignore", invalid="ignore"):
        r = np.vstack([np.full((1, N), np.nan), c[1:] / c[:-1] - 1])
    return {"days": np.array(days), "c": c, "r": r, "status": status}


def rebalance_days(days: A, freq: str) -> list[int]:
    out = []
    for t in range(len(days) - 1):
        d0, d1 = days[t], days[t + 1]
        if freq == "M":
            y0 = time.gmtime(d0 * 86400)
            y1 = time.gmtime(d1 * 86400)
            if (y0.tm_year, y0.tm_mon) != (y1.tm_year, y1.tm_mon):
                out.append(t)
        else:
            if (d0 + 3) // 7 != (d1 + 3) // 7:                         # ISO weeks start on Monday
                out.append(t)
    return out


# ---------------------------------------------------------------------------------------------- simulation
def simulate(spec: PortfolioSpec, panel: dict, costs: A, params: dict, ppy: float, cost_mult: float = 1.0,
             start: int = 0, end: Optional[int] = None) -> dict:
    c, r = panel["c"], np.nan_to_num(panel["r"])
    T = len(c) if end is None else end
    rb = set(t for t in rebalance_days(panel["days"], spec.rebalance) if start <= t < T - 1)
    w = np.zeros(c.shape[1])
    pending = None
    eq = [1.0]
    rets, turn, cost_paid, n_rb, weights_last = [], 0.0, 0.0, 0, None
    for t in range(start + 1, T):
        pr = float(np.sum(w * r[t]))
        gross = 1 + pr
        if gross > 0 and np.abs(w).sum() > 0:
            w = w * (1 + r[t]) / gross
        day_cost = 0.0
        if pending is not None:                                      # decided yesterday, executed at today's close
            dw = np.abs(pending - w)
            day_cost = float(np.sum(dw * costs)) * cost_mult
            turn += float(dw.sum())
            w = pending
            pending = None
            n_rb += 1
        net = (1 + pr) * (1 - day_cost) - 1
        rets.append(net)
        cost_paid += day_cost * eq[-1]
        eq.append(eq[-1] * (1 + net))
        if t in rb:
            target = np.nan_to_num(spec.fn(c, panel["r"], t, ppy, **params))
            if spec.long_only:
                target = np.clip(target, 0, None)
            pending = _cap_gross(target)
            weights_last = (int(panel["days"][t]), pending.copy())
    rets_a = np.array(rets)
    return {"returns": rets_a, "equity": np.array(eq), "turnover": turn, "costs": cost_paid, "rebalances": n_rb,
            "weights_last": weights_last}


def metrics(rets: A, eq: A, ppy: float) -> dict:
    if len(rets) < 3:
        return {"days": len(rets)}
    yrs = len(rets) / ppy
    tot = float(eq[-1] / eq[0] - 1)
    sd = float(np.std(rets, ddof=1))
    peak = np.maximum.accumulate(eq)
    mdd = float(np.max(1 - eq / peak))
    return {"days": len(rets), "years": round(yrs, 2), "total_return": round(tot, 4),
            "cagr": round((eq[-1] / eq[0]) ** (1 / yrs) - 1, 4) if yrs > 0 and eq[-1] > 0 else None,
            "vol": round(sd * math.sqrt(ppy), 4), "sharpe": round(float(np.mean(rets)) / sd * math.sqrt(ppy), 3)
            if sd > 0 else None, "max_drawdown": round(mdd, 4)}


def run_portfolio(spec: PortfolioSpec, panel: dict, book, *, trials_so_far: int = 0, seed: int = 7,
                  progress: Optional[Callable[[float, str], None]] = None,
                  cancel: Optional[threading.Event] = None) -> dict:
    t0 = time.time()
    step = progress or (lambda f, m: None)
    insts = [book.get(i) for i in spec.universe]
    ppy = 365.0 if all(i.market_type is MarketType.CRYPTO_SPOT for i in insts) else 252.0
    last_px = [float(panel["c"][np.isfinite(panel["c"][:, j]), j][-1]) if np.isfinite(panel["c"][:, j]).any() else 0.0
               for j in range(len(insts))]
    costs = np.array([cost_rate(i, p) if p > 0 else 0.001 for i, p in zip(insts, last_px)])
    short = [iid for iid, st in panel["status"].items() if (st.get("bars") or 0) < 252]
    if len(short) > len(spec.universe) * 0.2 or (spec.cash_proxy and spec.cash_proxy in short):
        return {"status": "insufficient_data", "reason_codes": ["INSUFFICIENT_DATA"], "data": panel["status"],
                "missing": short, "note": "a portfolio is not evaluated on a partial universe"}
    rb = rebalance_days(panel["days"], spec.rebalance)
    min_rb = 24 if spec.rebalance == "M" else 52
    if len(rb) < 2 * min_rb:
        return {"status": "insufficient_data", "rebalances": len(rb), "needed": 2 * min_rb,
                "data": panel["status"], "reason_codes": ["INSUFFICIENT_DATA"]}
    split_t = rb[int(len(rb) * 0.7)]
    keys, vals = list(spec.grid), list(product(*spec.grid.values()))
    grid = [dict(spec.params, **dict(zip(keys, v))) for v in vals] or [dict(spec.params)]
    step(0.05, f"{len(grid)} parameter set(s) on the first 70%")
    ins = []
    for i, p in enumerate(grid):
        if cancel is not None and cancel.is_set():
            raise RuntimeError("cancelled")
        s = simulate(spec, panel, costs, p, ppy, end=split_t + 1)
        m = metrics(s["returns"], s["equity"], ppy)
        ins.append((m.get("sharpe") or -9, i, m))
        step(0.05 + 0.4 * (i + 1) / len(grid), f"in-sample {i + 1}/{len(grid)}")
    ins.sort(key=lambda x: -x[0])
    best = grid[ins[0][1]]
    step(0.5, "held-out period, costs and benchmark")
    full = simulate(spec, panel, costs, best, ppy)
    out = simulate(spec, panel, costs, best, ppy, start=split_t)
    out2x = simulate(spec, panel, costs, best, ppy, cost_mult=2.0, start=split_t)
    ew = PortfolioSpec("EW", "equal weight", spec.universe, "M", lambda c, r, t, ppy: np.where(
        np.isfinite(c[t]), 1.0, 0.0) / max(1, np.isfinite(c[t]).sum()), {}, {})
    bench_out = simulate(ew, panel, costs, {}, ppy, start=split_t)
    bench_full = simulate(ew, panel, costs, {}, ppy)
    m_out, m_full = metrics(out["returns"], out["equity"], ppy), metrics(full["returns"], full["equity"], ppy)
    m_2x, m_bench = metrics(out2x["returns"], out2x["equity"], ppy), metrics(bench_out["returns"], bench_out["equity"], ppy)
    trials = trials_so_far + len(grid)
    step(0.8, "statistics")
    st: dict = {"trials_charged": trials}
    try:
        st.update(psr=round(S.probabilistic_sharpe_ratio(out["returns"]), 4),
                  dsr=round(S.deflated_sharpe_ratio(out["returns"], max(trials, 1)), 4),
                  newey_west_t=round(S.newey_west_tstat(out["returns"]), 3),
                  sharpe_ci95=[round(x, 3) for x in S.bootstrap_sharpe_interval(
                      out["returns"], samples=300, mean_block=20, seed=seed, periods_per_year=int(ppy))])
    except ValueError as e:
        st["error"] = str(e)
    held_rb = sum(1 for t in rb if t >= split_t)
    checks = [
        {"name": "held-out rebalances", "value": held_rb, "need": f">= {min_rb}", "passed": held_rb >= min_rb,
         "required": True},
        {"name": "held-out net return positive", "value": m_out.get("total_return"), "need": "> 0",
         "passed": (m_out.get("total_return") or 0) > 0, "required": True},
        {"name": "deflated Sharpe (held-out)", "value": st.get("dsr"), "need": ">= 0.95",
         "passed": (st.get("dsr") or 0) >= 0.95, "required": True},
        {"name": "held-out Sharpe at 2x costs", "value": m_2x.get("sharpe"), "need": "> 0",
         "passed": (m_2x.get("sharpe") or 0) > 0, "required": True},
        {"name": "beats equal-weight holding (held-out Sharpe)", "value": m_out.get("sharpe"),
         "need": f">= {m_bench.get('sharpe')}", "passed": (m_out.get("sharpe") or -9) >= (m_bench.get("sharpe") or 0),
         "required": False},
        {"name": "shallower drawdown than equal weight (held-out)", "value": m_out.get("max_drawdown"),
         "need": f"<= {m_bench.get('max_drawdown')}",
         "passed": (m_out.get("max_drawdown") or 1) <= (m_bench.get("max_drawdown") or 1), "required": False},
    ]
    for c in checks:
        c["code"] = None if c["passed"] else code_for(c["name"])
    passed = all(c["passed"] for c in checks if c["required"])
    promising = (m_out.get("total_return") or 0) > 0 and (m_2x.get("sharpe") or 0) > 0 and held_rb >= min_rb
    verdict = "PAPER TEST" if passed else ("RESEARCH FURTHER" if promising else "REJECT")
    if verdict == "PAPER TEST" and spec.max_verdict != "PAPER TEST":
        verdict = spec.max_verdict
    codes = sorted({c["code"] for c in checks if c["code"] and c["required"]})
    if spec.max_verdict != "PAPER TEST":
        codes.append("SOURCE_METHOD_UNVERIFIED")
    qual = round(max(0.0, min(100.0, 50 + 25 * (m_out.get("sharpe") or 0) - 50 * (m_out.get("max_drawdown") or 0)
                              + 20 * ((st.get("dsr") or 0) - 0.5))), 1)
    wl = full["weights_last"]
    step(1.0, "done")
    return {
        "status": "ok", "kind": "portfolio", "verdict": verdict, "reason_codes": codes, "strategy_id": spec.sid,
        "beats_benchmark": bool(checks[4]["passed"]), "deployable_universe": None,
        "name": spec.name, "universe": spec.universe, "rebalance": spec.rebalance, "params_chosen": best,
        "grid": [{"params": grid[i], "in_sample_sharpe": m.get("sharpe")} for _, i, m in ins],
        "in_sample": ins[0][2], "test": dict(m_out, trades=held_rb), "full": m_full, "cost_2x_test": m_2x,
        "benchmark_test": m_bench, "benchmark_full": metrics(bench_full["returns"], bench_full["equity"], ppy),
        "walk_forward": {"oos_sharpe": m_out.get("sharpe")}, "cost_stress": {"2.0x": {"sharpe": m_2x.get("sharpe")}},
        "turnover_per_year": round(full["turnover"] / max(1e-9, len(full["returns"]) / ppy), 2),
        "costs_paid_fraction": round(full["costs"], 4), "statistics": st, "checks": checks,
        "quality": {"score": qual, "note": "50 + 25*held-out Sharpe - 50*held-out drawdown + 20*(DSR-0.5), clipped"},
        "weights_now": {"as_of_day": wl[0], "weights": {spec.universe[j]: round(float(x), 4) for j, x in
                                                        enumerate(wl[1]) if abs(x) > 1e-6}} if wl else None,
        "equity_curve": [[int(panel["days"][min(i, len(panel["days"]) - 1)]) * DAY, round(float(v), 5)]
                         for i, v in list(enumerate(full["equity"]))[::max(1, len(full["equity"]) // 400)]],
        "benchmark_curve": [[int(panel["days"][min(i, len(panel["days"]) - 1)]) * DAY, round(float(v), 5)]
                            for i, v in list(enumerate(bench_full["equity"]))[::max(1, len(bench_full["equity"]) // 400)]],
        "split_day": int(panel["days"][split_t]) * DAY, "note": spec.note, "limitations": spec.limitations,
        "data": panel["status"], "reproducibility": {
            "start": int(panel["days"][0]) * DAY, "end": int(panel["days"][-1]) * DAY, "days": len(panel["days"]),
            "seed": seed, "simulated_data": False, "costs_one_way": {spec.universe[j]: round(float(x), 6)
                                                                    for j, x in enumerate(costs)},
            "execution": "decided at a rebalance close, filled at the next day's close"},
        "runtime_s": round(time.time() - t0, 2),
        "language_note": "Results describe past data under the stated assumptions. They are not a promise of future "
                         "returns.",
    }
