#!/usr/bin/env python3
"""Shared statistics over a list of trade R-multiples. Used by journal_stats.py and backtest.py."""

from __future__ import annotations

from typing import Dict, List, Sequence


def summarize(rs: Sequence[float]) -> Dict[str, object]:
    n = len(rs)
    if n == 0:
        return {"n": 0}
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gross_win = sum(wins)
    gross_loss = -sum(losses)
    win_rate = len(wins) / n
    avg_win = gross_win / len(wins) if wins else 0.0
    avg_loss = gross_loss / len(losses) if losses else 0.0
    expectancy = sum(rs) / n
    mean = expectancy
    var = sum((r - mean) ** 2 for r in rs) / n
    sd = var ** 0.5

    # equity curve, drawdown, streaks
    eq = 0.0
    peak = 0.0
    max_dd = 0.0
    cur_loss_streak = 0
    max_loss_streak = 0
    cur_win_streak = 0
    max_win_streak = 0
    for r in rs:
        eq += r
        peak = max(peak, eq)
        max_dd = max(max_dd, peak - eq)
        if r <= 0:
            cur_loss_streak += 1
            cur_win_streak = 0
        else:
            cur_win_streak += 1
            cur_loss_streak = 0
        max_loss_streak = max(max_loss_streak, cur_loss_streak)
        max_win_streak = max(max_win_streak, cur_win_streak)

    return {
        "n": n,
        "win_rate_pct": round(win_rate * 100, 1),
        "avg_win_r": round(avg_win, 3),
        "avg_loss_r": round(-avg_loss, 3),
        "expectancy_r": round(expectancy, 3),
        "total_r": round(sum(rs), 2),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss > 0 else None,
        "std_r": round(sd, 3),
        "max_drawdown_r": round(max_dd, 2),
        "max_loss_streak": max_loss_streak,
        "max_win_streak": max_win_streak,
        "breakeven_win_rate_pct": round(100 * avg_loss / (avg_win + avg_loss), 1) if (avg_win + avg_loss) > 0 else None,
        "sample_warning": "fewer than 50 trades: treat every number here as provisional" if n < 50 else None,
    }


def format_summary(s: Dict[str, object], title: str = "") -> str:
    if s.get("n", 0) == 0:
        return f"{title}: no trades"
    lines = [f"== {title} ==" if title else "== summary =="]
    lines.append(f"trades {s['n']}   win rate {s['win_rate_pct']}%   avg win {s['avg_win_r']:+}R   avg loss {s['avg_loss_r']:+}R")
    lines.append(f"expectancy {s['expectancy_r']:+}R/trade   total {s['total_r']:+}R   profit factor {s['profit_factor']}")
    lines.append(f"max drawdown {s['max_drawdown_r']}R   longest losing streak {s['max_loss_streak']}   "
                 f"std {s['std_r']}R   breakeven win rate {s['breakeven_win_rate_pct']}%")
    if s.get("sample_warning"):
        lines.append("note: " + str(s["sample_warning"]))
    return "\n".join(lines)


def group_by(items: List[dict], key: str) -> Dict[str, List[float]]:
    out: Dict[str, List[float]] = {}
    for it in items:
        k = str(it.get(key) or "unknown")
        out.setdefault(k, []).append(float(it["r_multiple"]))
    return out
