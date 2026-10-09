"""The backtest report (section 165). Win rate is never reported alone: expectancy, payoff and drawdown sit beside it.

All figures come from the equity curve and the trade list of one run. Returns are per bar; annualization uses the
market's periods per year (crypto trades 365 days, others 252). When the test spans less than a year the annualized
figures are labelled as such.
"""

from __future__ import annotations

import math
from typing import Optional

import numpy as np

from tradingai.backtest.engine import BTResult


def _f(x) -> Optional[float]:
    if x is None:
        return None
    x = float(x)
    return round(x, 6) if math.isfinite(x) else None


def drawdown(equity: np.ndarray) -> tuple[np.ndarray, float, int]:
    peak = np.maximum.accumulate(np.where(equity > 0, equity, 0))
    dd = np.where(peak > 0, equity / np.where(peak > 0, peak, 1) - 1, 0.0)
    under = dd < -1e-12
    longest = cur = 0
    for u in under:
        cur = cur + 1 if u else 0
        longest = max(longest, cur)
    return dd, float(-dd.min()) if len(dd) else 0.0, longest


def report(r: BTResult, ppy: float, regimes: Optional[dict[str, np.ndarray]] = None) -> dict:
    eq, rets = r.equity, r.returns
    n = len(eq)
    cap = float(r.config.get("capital", eq[0] if n else 0))
    final = float(eq[-1]) if n else cap
    total = final / cap - 1 if cap else 0.0
    years = n / ppy if ppy else 0
    dd, mdd, longest = drawdown(eq)
    mu, sd = float(np.mean(rets[1:])) if n > 1 else 0.0, float(np.std(rets[1:], ddof=1)) if n > 2 else 0.0
    downside = rets[1:][rets[1:] < 0]
    dsd = float(np.sqrt(np.mean(downside ** 2))) if len(downside) else 0.0
    sharpe = mu / sd * math.sqrt(ppy) if sd > 0 else None
    sortino = mu / dsd * math.sqrt(ppy) if dsd > 0 else None
    cagr = (final / cap) ** (1 / years) - 1 if years > 0 and final > 0 else (-1.0 if final <= 0 else None)
    tr = r.trades
    nets = np.array([t.net for t in tr]) if tr else np.zeros(0)
    gross = np.array([t.gross for t in tr]) if tr else np.zeros(0)
    wins, losses = nets[nets > 0], nets[nets <= 0]
    rs = np.array([t.r_multiple for t in tr if t.r_multiple is not None])
    streak_w = streak_l = cw = cl = 0
    for x in nets:
        cw, cl = (cw + 1, 0) if x > 0 else (0, cl + 1)
        streak_w, streak_l = max(streak_w, cw), max(streak_l, cl)
    traded_notional = sum(t.qty * (t.entry_px + t.exit_px) for t in tr)
    tail = np.sort(rets[1:])
    var95 = float(-np.quantile(tail, 0.05)) if len(tail) >= 20 else None
    cvar95 = float(-tail[: max(1, int(len(tail) * 0.05))].mean()) if len(tail) >= 20 else None
    costs = r.costs
    out = {
        "bars": n, "years": _f(years), "annualized_note": None if years >= 1 else "test shorter than a year: "
        "annualized figures extrapolate", "start_equity": cap, "end_equity": _f(final),
        "gross_pnl": _f(gross.sum()) if len(gross) else 0.0, "net_pnl": _f(final - cap),
        "total_return": _f(total), "cagr": _f(cagr), "max_drawdown": _f(mdd),
        "sharpe": _f(sharpe), "sortino": _f(sortino),
        "calmar": _f(cagr / mdd) if cagr is not None and mdd > 0 else None,
        "trades": len(tr), "win_rate": _f(len(wins) / len(nets)) if len(nets) else None,
        "loss_rate": _f(len(losses) / len(nets)) if len(nets) else None,
        "avg_win": _f(wins.mean()) if len(wins) else None, "avg_loss": _f(losses.mean()) if len(losses) else None,
        "payoff_ratio": _f(wins.mean() / -losses.mean()) if len(wins) and len(losses) and losses.mean() < 0 else None,
        "profit_factor": _f(wins.sum() / -losses.sum()) if len(losses) and losses.sum() < 0 else None,
        "expectancy": _f(nets.mean()) if len(nets) else None,
        "expectancy_r": _f(rs.mean()) if len(rs) else None,
        "largest_win": _f(nets.max()) if len(nets) else None, "largest_loss": _f(nets.min()) if len(nets) else None,
        "max_consecutive_wins": streak_w, "max_consecutive_losses": streak_l,
        "avg_hold_bars": _f(np.mean([t.bars for t in tr])) if tr else None,
        "exposure": _f(float(np.mean(r.exposure > 0))), "avg_gross_exposure": _f(float(np.mean(r.exposure))),
        "turnover": _f(traded_notional / cap / years) if years > 0 else None,
        "costs": {"fees": _f(costs["fees"]), "spread": _f(costs["spread"]), "slippage": _f(costs["slippage"]),
                  "funding": _f(costs["funding"]),
                  "total": _f(costs["fees"] + costs["spread"] + costs["slippage"] + costs["funding"]),
                  "model": costs.get("model")},
        "time_under_water_bars": longest, "time_under_water_share": _f(float(np.mean(dd < -1e-12))),
        "tail_loss_worst_bar": _f(-tail[0]) if len(tail) else None, "var95_bar": _f(var95), "cvar95_bar": _f(cvar95),
        "ruined": r.ruined, "partial_fills": r.partial_fills, "missed_fills": r.missed_fills, "undersized_signals": r.undersized, "flags": r.flags,
        "exit_reasons": {k: sum(1 for t in tr if t.exit_reason == k) for k in sorted({t.exit_reason for t in tr})},
    }
    if regimes:
        out["by_regime"] = by_regime(r, regimes)
    return out


def by_regime(r: BTResult, regimes: dict[str, np.ndarray]) -> dict:
    """Trades grouped by the regime at their entry bar (labels known at that bar: causal)."""
    out = {}
    for name, labels in regimes.items():
        g: dict[str, list[float]] = {}
        for t in r.trades:
            lab = str(labels[t.entry_bar]) if t.entry_bar < len(labels) else "unknown"
            g.setdefault(lab, []).append(t.net)
        out[name] = {k: {"trades": len(v), "net": round(float(np.sum(v)), 2),
                         "expectancy": round(float(np.mean(v)), 2),
                         "win_rate": round(float(np.mean(np.array(v) > 0)), 4)} for k, v in sorted(g.items())}
    return out
