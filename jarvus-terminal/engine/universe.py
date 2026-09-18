#!/usr/bin/env python3
"""Market discovery: build the list of everything tradeable, then cheaply pre-rank it.

Two passes exist because they cost very different amounts. The universe pass is one
request per venue and returns every market with its 24h summary, so it can cover
thousands of markets for free. The deep pass needs a candle request per market, so
only the most promising handful can afford it. This module does the first pass and
decides who earns the second.
"""

from __future__ import annotations

from typing import Dict, List

import config
from engine import http


def _f(v, default=0.0) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def _okx(inst_type: str) -> List[dict]:
    d = http.get_json("https://www.okx.com/api/v5/market/tickers",
                      {"instType": inst_type}, ttl=config.CACHE_TTL_UNIVERSE)
    if not d or d.get("code") != "0":
        return []
    out = []
    for t in d.get("data", []):
        inst = t["instId"]
        parts = inst.split("-")
        if len(parts) < 2:
            continue
        base, quote = parts[0], parts[1]
        if quote not in config.QUOTE_WHITELIST:
            continue
        last = _f(t.get("last"))
        if last <= 0:
            continue
        out.append({
            "symbol": inst, "base": base, "quote": quote,
            "venue": "okx", "kind": "perp" if inst.endswith("SWAP") else "spot",
            "price": last,
            "open24h": _f(t.get("open24h")), "high24h": _f(t.get("high24h")), "low24h": _f(t.get("low24h")),
            "usd_volume_24h": _f(t.get("volCcy24h")),
        })
    return out


def _coinbase() -> List[dict]:
    products = http.get_json("https://api.exchange.coinbase.com/products", ttl=config.CACHE_TTL_UNIVERSE)
    stats = http.get_json("https://api.exchange.coinbase.com/products/stats", ttl=config.CACHE_TTL_UNIVERSE)
    if not products or not isinstance(stats, dict):
        return []
    out = []
    for p in products:
        if p.get("status") != "online" or p.get("trading_disabled"):
            continue
        quote = p.get("quote_currency", "")
        if quote not in config.QUOTE_WHITELIST:
            continue
        s = stats.get(p["id"])
        if not s:
            continue
        s = s.get("stats_24hour", s)
        last = _f(s.get("last"))
        vol_base = _f(s.get("volume"))
        if last <= 0:
            continue
        out.append({
            "symbol": p["id"], "base": p.get("base_currency", ""), "quote": quote,
            "venue": "coinbase", "kind": "spot", "price": last,
            "open24h": _f(s.get("open")), "high24h": _f(s.get("high")), "low24h": _f(s.get("low")),
            "usd_volume_24h": vol_base * last,
        })
    return out


LOADERS = {"okx_spot": lambda: _okx("SPOT"), "okx_swap": lambda: _okx("SWAP"), "coinbase": _coinbase}


def annotate(m: dict) -> dict:
    """Add the cheap movement metrics that the pre-rank is built from."""
    price, hi, lo, op = m["price"], m["high24h"], m["low24h"], m["open24h"]
    m["range_24h_pct"] = ((hi - lo) / price * 100) if price and hi > lo else 0.0
    m["change_24h_pct"] = ((price - op) / op * 100) if op else 0.0
    # Where in its own 24h range price is sitting: 100 = at the high, 0 = at the low.
    m["position_in_range_pct"] = ((price - lo) / (hi - lo) * 100) if hi > lo else 50.0
    return m


def prerank_score(m: dict) -> float:
    """Cheap 'is something happening here' score, from 24h summary data only.

    This is NOT the volatility gate. It is a triage filter whose only job is to pick
    which markets deserve a candle request. The real gate runs on candles afterwards.
    """
    rng = m["range_24h_pct"]
    chg = abs(m["change_24h_pct"])
    # Liquidity is a gate, not a score: below the floor the market is untradeable at
    # any size and its volatility is noise rather than opportunity.
    if m["usd_volume_24h"] < config.MIN_USD_VOLUME_24H:
        return -1.0
    # Range dominates; a large directional change on a small range is usually a gap.
    return rng + 0.5 * chg


def scan(venues: List[str] | None = None) -> Dict[str, object]:
    venues = venues or config.UNIVERSE_VENUES
    markets: List[dict] = []
    sources: Dict[str, int] = {}
    for v in venues:
        loader = LOADERS.get(v)
        if not loader:
            continue
        got = loader()
        sources[v] = len(got)
        markets += got

    # Deduplicate: the same base/quote can exist on several venues. Keep the most liquid.
    best: Dict[str, dict] = {}
    for m in markets:
        m = annotate(m)
        key = f"{m['base']}/{m['quote']}/{m['kind']}"
        if key not in best or m["usd_volume_24h"] > best[key]["usd_volume_24h"]:
            best[key] = m
    unique = list(best.values())
    for m in unique:
        m["prerank"] = prerank_score(m)

    liquid = [m for m in unique if m["prerank"] >= 0]
    liquid.sort(key=lambda m: m["prerank"], reverse=True)
    return {"markets": liquid, "total_discovered": len(unique), "passed_liquidity": len(liquid),
            "sources": sources, "errors": http.last_errors()}


def dedupe_by_base(markets: List[dict]) -> List[dict]:
    """Collapse the same asset listed several times (spot and perp, or two venues).

    The headline movers list is about assets, not listings; showing AR spot, AR perp
    and AR on a second venue as three separate rows buries the other movers. The most
    liquid listing wins and keeps the others as alternates.
    """
    best: Dict[str, dict] = {}
    for m in markets:
        key = m["base"]
        if key not in best or m["usd_volume_24h"] > best[key]["usd_volume_24h"]:
            if key in best:
                m.setdefault("alternates", []).append(best[key]["symbol"])
                m["alternates"] += best[key].get("alternates", [])
            best[key] = m
        else:
            best[key].setdefault("alternates", []).append(m["symbol"])
    return sorted(best.values(), key=lambda m: m["prerank"], reverse=True)


def pick_deep(markets: List[dict], n: int | None = None) -> List[dict]:
    """The top n by pre-rank, plus the always-include majors, without duplicates."""
    n = n or config.DEEP_SCAN_N
    chosen: List[dict] = []
    seen = set()
    by_symbol = {m["symbol"]: m for m in markets}
    for sym in config.ALWAYS_INCLUDE:
        m = by_symbol.get(sym)
        if m and sym not in seen:
            chosen.append(m)
            seen.add(sym)
    for m in markets:
        if len(chosen) >= n:
            break
        if m["symbol"] not in seen:
            chosen.append(m)
            seen.add(m["symbol"])
    return chosen
