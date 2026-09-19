#!/usr/bin/env python3
"""The agent swarm: every strategy evaluated against every market, concurrently.

One "agent" is one strategy looking at one market on one timeframe. With 64
strategies across 40 markets that is 2,560 independent evaluations per scan, which
is what "analyses thousands of possibilities" means here — a real count of real
evaluations, not a figure of speech.

The part that matters is not the fan-out, it is what happens to the answers.
Sixty-four opinions are worthless if they are simply added up, for two reasons:

  1. **They are not independent.** A dozen of these strategies are different
     spellings of "price is above a rising moving average". Counting them as a
     dozen votes turns one idea into twelve and manufactures false agreement, so
     votes are grouped by family first and each family gets one weighted say.

  2. **They have not earned equal weight.** A strategy that has never been tested
     should not outvote one with a measured record. Weights come from each
     strategy's own backtest on that market where one exists, and until it does the
     consensus says plainly that it is running unweighted.

So the swarm is a way of asking a lot of questions at once and then being careful
about how much each answer counts.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from typing import Dict, List, Optional

import config
from engine import strategies as S


# Families that tend to fire together. Grouping caps how much one idea can vote.
FAMILY = {
    "trend": "trend", "composite": "trend",
    "breakout": "breakout", "volatility": "breakout",
    "mean-reversion": "mean-reversion",
    "momentum": "momentum",
    "volume": "volume",
    "structure": "structure",
}


def evaluate_market(candles: List[dict], symbol: str, meta: Dict = None,
                    htf_candles: List[dict] = None,
                    weights: Dict[str, float] = None,
                    specs: List[S.StrategySpec] = None) -> Dict:
    """Run every enabled strategy against one market and fold the answers together."""
    specs = specs if specs is not None else S.all_strategies()
    ctx = S.Ctx(candles, symbol, meta, htf_candles)
    weights = weights or {}

    fired: List[Dict] = []
    for spec in specs:
        sig = S.evaluate(spec, ctx)
        if sig and sig.direction == "long":
            w = weights.get(spec.name)
            fired.append({
                "strategy": spec.name, "group": spec.group, "family": FAMILY.get(spec.group, spec.group),
                "strength": round(sig.strength, 3), "reason": sig.reason,
                "stop_hint": sig.stop_hint, "tags": sig.tags,
                "weight": round(w, 3) if w is not None else None,
                "proven": w is not None,
            })

    # Fold to one vote per family: the best member carries it, the rest add a little.
    by_family: Dict[str, List[Dict]] = {}
    for f in fired:
        by_family.setdefault(f["family"], []).append(f)

    family_scores: Dict[str, float] = {}
    for fam, members in by_family.items():
        members.sort(key=lambda m: -(m["strength"] * (m["weight"] if m["weight"] is not None else 1.0)))
        best = members[0]
        score = best["strength"] * (best["weight"] if best["weight"] is not None else 1.0)
        # corroboration inside a family is worth something, but sharply less each time
        for k, extra in enumerate(members[1:], start=1):
            score += 0.25 / k * extra["strength"] * (extra["weight"] if extra["weight"] is not None else 1.0)
        family_scores[fam] = round(min(2.0, score), 3)

    # Agreement across *different* families is the signal worth having.
    families_agreeing = len(family_scores)
    consensus = round(sum(family_scores.values()) / max(1, len(FAMILY_SET)), 4)
    any_proven = any(f["proven"] for f in fired)

    return {
        "symbol": symbol,
        "agents_run": len(specs),
        "agents_fired": len(fired),
        "families_agreeing": families_agreeing,
        "family_scores": family_scores,
        "consensus": consensus,
        "weighted": any_proven,
        "signals": sorted(fired, key=lambda f: -f["strength"])[:12],
        "top_reasons": [f["reason"] for f in sorted(fired, key=lambda f: -f["strength"])[:3]],
    }


FAMILY_SET = set(FAMILY.values())


def run(markets: List[Dict], candles_by_symbol: Dict[str, List[dict]],
        htf_by_symbol: Dict[str, List[dict]] = None,
        weights_by_symbol: Dict[str, Dict[str, float]] = None,
        max_workers: int = None) -> Dict:
    """Fan the whole grid out across a thread pool."""
    t0 = time.time()
    htf_by_symbol = htf_by_symbol or {}
    weights_by_symbol = weights_by_symbol or {}
    specs = S.all_strategies()

    jobs = [(m, candles_by_symbol.get(m["symbol"])) for m in markets]
    jobs = [(m, c) for m, c in jobs if c and len(c) >= 60]

    def work(item):
        m, c = item
        return evaluate_market(c, m["symbol"], m, htf_by_symbol.get(m["symbol"]),
                               weights_by_symbol.get(m["symbol"]), specs)

    results: List[Dict] = []
    if jobs:
        with ThreadPoolExecutor(max_workers=max_workers or config.MAX_WORKERS) as pool:
            results = list(pool.map(work, jobs))

    results.sort(key=lambda r: (-r["families_agreeing"], -r["consensus"]))
    total_evals = sum(r["agents_run"] for r in results)
    return {
        "results": results,
        "by_symbol": {r["symbol"]: r for r in results},
        "strategies_loaded": len(specs),
        "markets_evaluated": len(results),
        "total_evaluations": total_evals,
        "total_signals": sum(r["agents_fired"] for r in results),
        "elapsed_s": round(time.time() - t0, 2),
        "any_weighted": any(r["weighted"] for r in results),
    }


def roster() -> List[Dict]:
    """Every loaded strategy, for the UI's enable/disable panel."""
    return [{"name": s.name, "group": s.group, "family": FAMILY.get(s.group, s.group),
             "description": s.description, "source": s.source, "enabled": s.enabled}
            for s in sorted(S.REGISTRY.values(), key=lambda x: (x.group, x.name))]


def set_enabled(names: Dict[str, bool]) -> int:
    changed = 0
    for n, on in names.items():
        spec = S.REGISTRY.get(n)
        if spec is not None and spec.enabled != bool(on):
            spec.enabled = bool(on)
            changed += 1
    return changed
