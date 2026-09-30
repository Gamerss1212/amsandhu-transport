"""History for research: downloaded from the same public sources the bots use, cached on disk, and validated.

Validation (reported with every result, never silently repaired):
* missing bars inside the period (gaps; for stocks only inside trading sessions),
* duplicated bars (same open time: the later copy is kept, counted),
* out-of-order bars (sorted, counted),
* impossible values (non-positive prices, high below low, open/close outside the range: dropped, counted),
* staleness: how old the newest bar is when the data was fetched.
The dataset fingerprint (source, first and last bar, count, content hash) is part of every cache key, so a result is
reused only for exactly the same data.
"""

from __future__ import annotations

import gzip
import hashlib
import json
import os
import time
from typing import List, Optional, Tuple

from mab.clock import tf_ms
from mab.data.adapters import ADAPTERS
from mab.data.quality import validate_bar
from mab.frame import Frame
from mab.models import Bar, now_ms

PAGE = {"coinbase": 300, "kraken": 720, "okx": 100, "yahoo": 5000, "demo": 1000}


def _cache_path(cache_dir: str, venue: str, symbol: str, tf: str) -> str:
    safe = f"{venue}_{symbol}_{tf}".replace("/", "-").replace(":", "-")
    return os.path.join(cache_dir, safe + ".json.gz")


def fetch(venue: str, symbol: str, tf: str, days: int, cache_dir: Optional[str] = None, http=None,
          max_age_s: float = 3600) -> Tuple[List[Bar], dict]:
    """(bars oldest first, quality report). Downloads page by page, newest first, until `days` are covered."""
    step = tf_ms(tf)
    want_from = now_ms() - days * 86_400_000
    path = _cache_path(cache_dir, venue, symbol, tf) if cache_dir else None
    if path and os.path.exists(path) and time.time() - os.path.getmtime(path) < max_age_s:
        with gzip.open(path, "rt", encoding="utf-8") as fh:
            d = json.load(fh)
        if d.get("from", 1e30) <= want_from + step:
            bars = [Bar(venue, symbol, tf, *row, provenance=d.get("source", venue)) for row in d["rows"]]
            bars = [b for b in bars if b.event_time >= want_from]
            return bars, dict(d["quality"], cached=True)
    if http is None:
        from mab.net import Http
        http = Http()
    ad = ADAPTERS[venue](http)
    if not ad.supports(tf):
        raise ValueError(f"{venue} has no {tf} bars")
    got: List[Bar] = []
    end = now_ms()
    pages = 0
    if venue == "yahoo":
        rng = "60d" if tf in ("5m", "15m") else ("730d" if tf == "1h" else "7d" if tf == "1m" else "5y")
        got = ad.bars(symbol, tf, limit=100_000, rng=rng)
        pages = 1
    else:
        while end > want_from and pages < 400:
            chunk = ad.bars(symbol, tf, limit=PAGE.get(venue, 300), end_ms=end)
            pages += 1
            if not chunk:
                break
            got.extend(chunk)
            first = min(b.event_time for b in chunk)
            if first >= end:
                break
            end = first
    bars, q = clean(got, tf)
    bars = [b for b in bars if b.event_time >= want_from]
    q.update({"pages": pages, "source": getattr(bars[0], "provenance", venue) if bars else venue, "cached": False,
              "requested_days": days})
    if path and bars:
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with gzip.open(path, "wt", encoding="utf-8") as fh:
            json.dump({"from": bars[0].event_time, "source": q["source"], "quality": q,
                       "rows": [[b.event_time, b.open, b.high, b.low, b.close, b.volume] for b in bars]}, fh)
    return bars, q


def clean(bars: List[Bar], tf: str) -> Tuple[List[Bar], dict]:
    step = tf_ms(tf)
    now = now_ms()
    q = {"received": len(bars), "invalid": 0, "duplicates": 0, "out_of_order": 0, "gaps": 0, "missing_bars": 0,
         "invalid_reasons": {}}
    prev = None
    for b in bars:
        if prev is not None and b.event_time < prev:
            q["out_of_order"] += 1
        prev = b.event_time
    by = {}
    for b in bars:
        why = validate_bar(b, now)
        if why:
            q["invalid"] += 1
            k = why.split(":")[0]
            q["invalid_reasons"][k] = q["invalid_reasons"].get(k, 0) + 1
            continue
        if b.event_time in by:
            q["duplicates"] += 1
        by[b.event_time] = b
    out = [by[t] for t in sorted(by)]
    crypto = not out or not out[0].instrument or out[0].venue != "yahoo"
    for a, b in zip(out, out[1:]):
        gap = (b.event_time - a.event_time) // step - 1
        if gap > 0 and (crypto or gap * step < 12 * 3_600_000):   # stock gaps across nights/weekends are not missing
            q["gaps"] += 1
            q["missing_bars"] += gap
    q["bars"] = len(out)
    q["first"] = out[0].event_time if out else None
    q["last"] = out[-1].event_time if out else None
    q["newest_age_s"] = round((now - (out[-1].event_time + step)) / 1000, 1) if out else None
    q["fingerprint"] = fingerprint(out)
    q["verdict"] = verdict(q, step)
    return out, q


def fingerprint(bars: List[Bar]) -> str:
    h = hashlib.sha256()
    for b in bars:
        h.update(f"{b.event_time}:{b.open:.10g}:{b.high:.10g}:{b.low:.10g}:{b.close:.10g}".encode())
    return h.hexdigest()[:16]


def verdict(q: dict, step: int) -> str:
    if not q["bars"]:
        return "no data"
    problems = []
    if q["bars"] and q["missing_bars"] / max(1, q["bars"]) > 0.02:
        problems.append(f"{q['missing_bars']} missing bars ({100 * q['missing_bars'] / q['bars']:.1f}%)")
    if q["invalid"]:
        problems.append(f"{q['invalid']} invalid bars dropped")
    if q["newest_age_s"] is not None and q["newest_age_s"] > max(3 * step / 1000, 86_400 * 3):
        problems.append(f"newest bar is {q['newest_age_s'] / 3600:.1f} h old")
    return "ok" if not problems else "; ".join(problems)


def frame(bars: List[Bar], asset_type: str) -> Frame:
    b0 = bars[0]
    return Frame(b0.venue, b0.instrument, b0.timeframe, asset_type, bars)
