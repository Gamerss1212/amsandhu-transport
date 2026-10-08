"""Performance metrics computed from closed trades and daily equity.

All returns are after fees and modelled slippage. Returns are measured against a fixed
capital base (no compounding) so strategies with different trade counts stay comparable;
risk per trade is a fixed fraction of that base.
"""

from __future__ import annotations

import math
import random
from collections import OrderedDict
from datetime import datetime, timezone
from typing import Dict, List, Optional, Sequence


def _mean(x):
    return sum(x) / len(x) if x else None


def _std(x, ddof=1):
    if len(x) <= ddof:
        return None
    m = sum(x) / len(x)
    return math.sqrt(sum((v - m) ** 2 for v in x) / (len(x) - ddof))


def _skew(x):
    s = _std(x, 0)
    if not s or len(x) < 3:
        return None
    m = sum(x) / len(x)
    return sum(((v - m) / s) ** 3 for v in x) / len(x)


def _kurt(x):
    s = _std(x, 0)
    if not s or len(x) < 4:
        return None
    m = sum(x) / len(x)
    return sum(((v - m) / s) ** 4 for v in x) / len(x)


def daily_pnl(trades: Sequence, day_of) -> "OrderedDict[str, float]":
    d: Dict[str, float] = {}
    for t in trades:
        k = day_of(t.exit_time)
        d[k] = d.get(k, 0.0) + t.pnl
    return OrderedDict(sorted(d.items()))


def utc_day(ms: int) -> str:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).strftime("%Y-%m-%d")


def max_drawdown(equity: Sequence[float]) -> float:
    peak, dd = -float("inf"), 0.0
    for v in equity:
        peak = max(peak, v)
        if peak > 0:
            dd = max(dd, (peak - v) / peak)
    return dd


def compute(trades: Sequence, capital: float, days: Sequence[str], periods_per_year: int,
            bars_total: int = 0, bars_in_market: int = 0) -> dict:
    """`days` = every trading day in the evaluated period (days without trades count as 0)."""
    n = len(trades)
    pnl = [t.pnl for t in trades]
    rs = [t.r for t in trades if t.r is not None]
    wins = [p for p in pnl if p > 0]
    losses = [p for p in pnl if p <= 0]
    gross_profit, gross_loss = sum(wins), -sum(losses)
    fees = sum(t.fees for t in trades)
    gross_before_fees = sum(pnl) + fees
    dp = daily_pnl(trades, utc_day)
    daily = [dp.get(d, 0.0) / capital for d in days]
    # A cash account cannot lose more than it has: once equity reaches 0 the account is RUINED and stays at 0, so
    # net_return never goes below -100% and max_drawdown never above 100%. The per-trade statistics (expectancy,
    # win rate) still describe every trade the rules produced; net_pnl_uncapped keeps the plain sum for reference.
    eq, acc, ruin_day = [], capital, None
    for d in days:
        if ruin_day is None:
            acc += dp.get(d, 0.0)
            if acc <= 0:
                acc, ruin_day = 0.0, d
        eq.append(acc)
    mu, sd = _mean(daily), _std(daily)
    downside = [min(0.0, v) for v in daily]
    dsd = math.sqrt(sum(v * v for v in downside) / len(downside)) if downside else None
    total_ret = -1.0 if ruin_day is not None else sum(pnl) / capital
    years = len(days) / periods_per_year if days else 0
    mdd = max_drawdown([capital] + eq)
    streak = worst = 0
    for p in pnl:
        streak = streak + 1 if p <= 0 else 0
        worst = max(worst, streak)
    r_mean, r_sd = _mean(rs), _std(rs)
    t_stat = (r_mean / (r_sd / math.sqrt(len(rs)))) if (rs and r_sd) else None
    long_n = sum(1 for t in trades if t.side > 0)
    out = {
        "trades": n, "long_trades": long_n, "short_trades": n - long_n,
        "win_rate": len(wins) / n if n else None,
        "avg_win": _mean(wins), "avg_loss": _mean(losses),
        "profit_factor": (gross_profit / gross_loss) if gross_loss else (None if not gross_profit else float("inf")),
        "expectancy": _mean(pnl), "expectancy_r": r_mean, "median_r": sorted(rs)[len(rs) // 2] if rs else None,
        "r_std": r_sd, "t_stat_r": t_stat,
        "net_pnl": -capital if ruin_day is not None else sum(pnl), "net_pnl_uncapped": sum(pnl),
        "ruined": ruin_day is not None, "ruin_day": ruin_day, "net_return": total_ret, "gross_return_before_fees": gross_before_fees / capital,
        "fees": fees, "fee_share_of_gross": (fees / gross_before_fees) if gross_before_fees > 0 else None,
        "annualized_return": (total_ret / years) if years else None,
        "sharpe": (mu / sd * math.sqrt(periods_per_year)) if (sd and mu is not None) else None,
        "sortino": (mu / dsd * math.sqrt(periods_per_year)) if (dsd and mu is not None) else None,
        "max_drawdown": mdd,
        "calmar": ((total_ret / years) / mdd) if (years and mdd) else None,
        "worst_trade_r": min(rs) if rs else None, "best_trade_r": max(rs) if rs else None,
        "max_consecutive_losses": worst,
        "avg_bars_held": _mean([t.bars for t in trades]),
        "exposure": (bars_in_market / bars_total) if bars_total else None,
        "trades_per_day": n / len(days) if days else None,
        "days": len(days), "skew_daily": _skew(daily), "kurtosis_daily": _kurt(daily),
        "var95_daily": sorted(daily)[int(0.05 * len(daily))] if len(daily) >= 20 else None,
        "avg_mfe_r": _mean([t.mfe_r for t in trades]), "avg_mae_r": _mean([t.mae_r for t in trades]),
    }
    return {k: (round(v, 6) if isinstance(v, float) and math.isfinite(v) else v) for k, v in out.items()}


def bootstrap_ci(values: Sequence[float], stat=_mean, n: int = 2000, alpha: float = 0.05, seed: int = 7):
    """Percentile bootstrap confidence interval (resampling trades with replacement)."""
    if len(values) < 5:
        return None
    rnd = random.Random(seed)
    vals = list(values)
    k = len(vals)
    stats = sorted(stat([vals[rnd.randrange(k)] for _ in range(k)]) for _ in range(n))
    return (stats[int(alpha / 2 * n)], stats[int((1 - alpha / 2) * n) - 1])


# ---------------------------------------------------------------- multiple testing

def norm_cdf(x: float) -> float:
    return 0.5 * (1 + math.erf(x / math.sqrt(2)))


def norm_ppf(p: float) -> float:
    """Acklam's rational approximation of the standard normal quantile (|error| < 1.2e-9)."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02,
         -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01,
         -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00,
         4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    pl = 0.02425
    if p <= 0 or p >= 1:
        raise ValueError("p must be in (0, 1)")
    if p < pl:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > 1 - pl:
        q = math.sqrt(-2 * math.log(1 - p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5]) / ((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p - 0.5
    r = q * q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q / (((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)


def p_value_from_t(t: Optional[float]) -> Optional[float]:
    """One-sided p-value for mean > 0 (normal approximation; adequate for n >= 30)."""
    if t is None:
        return None
    return 1 - norm_cdf(t)


def holm(pvals: Dict[str, Optional[float]], alpha: float = 0.05) -> Dict[str, dict]:
    """Holm-Bonferroni step-down over every hypothesis tested, including the losers."""
    items = sorted(((p, k) for k, p in pvals.items() if p is not None))
    m = len(items)
    out = {}
    still = True
    for rank, (p, k) in enumerate(items):
        thresh = alpha / (m - rank)
        rej = still and p <= thresh
        if not rej:
            still = False
        out[k] = {"p": p, "holm_threshold": thresh, "significant": rej, "adjusted_p": min(1.0, p * (m - rank))}
    for k, p in pvals.items():
        if p is None:
            out[k] = {"p": None, "holm_threshold": None, "significant": False, "adjusted_p": None}
    return out


def deflated_sharpe(sr: float, n_obs: int, n_trials: int, sr_var_trials: float, skew: float = 0.0,
                    kurt: float = 3.0) -> Optional[float]:
    """Bailey & Lopez de Prado (2014) deflated Sharpe ratio: probability that the true Sharpe
    exceeds the maximum expected from `n_trials` unskilled trials. sr in per-period units."""
    if n_obs < 3 or n_trials < 1:
        return None
    emc = 0.5772156649
    if n_trials > 1 and sr_var_trials > 0:
        sr0 = math.sqrt(sr_var_trials) * ((1 - emc) * norm_ppf(1 - 1 / n_trials) + emc * norm_ppf(1 - 1 / (n_trials * math.e)))
    else:
        sr0 = 0.0
    denom = math.sqrt(max(1e-12, 1 - skew * sr + (kurt - 1) / 4 * sr * sr))
    return norm_cdf((sr - sr0) * math.sqrt(n_obs - 1) / denom)
