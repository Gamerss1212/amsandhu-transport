#!/usr/bin/env python3
"""Candle fetching across venues, concurrently, with the unclosed bar handled honestly.

Every venue returns the in-progress candle alongside closed ones. Treating a partial
bar as closed is the most common silent bug in retail tooling: its range, volume and
close are all incomplete, so indicators computed on it flicker and any signal that
depends on a candle close fires early. This module separates the two and the rest of
the app only ever reasons about closed bars.
"""

from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Dict, List, Optional

import config
from engine import http

# our timeframe -> (okx bar, coinbase granularity seconds, kraken minutes)
TF = {
    "5m":  ("5m",  300,   5),
    "15m": ("15m", 900,   15),
    "1h":  ("1H",  3600,  60),
    "4h":  ("4H",  None,  240),
    "1d":  ("1D",  86400, 1440),
}


def _rows_to_candles(rows: List[list]) -> List[dict]:
    return [{"ts": datetime.fromtimestamp(r[0] / 1000, tz=timezone.utc), "open": r[1], "high": r[2],
             "low": r[3], "close": r[4], "volume": r[5]} for r in rows]


def _okx(symbol: str, tf: str, limit: int) -> Optional[List[dict]]:
    bar = TF[tf][0]
    d = http.get_json("https://www.okx.com/api/v5/market/candles",
                      {"instId": symbol, "bar": bar, "limit": str(min(limit, 300))},
                      ttl=config.CACHE_TTL_CANDLES)
    if not d or d.get("code") != "0" or not d.get("data"):
        return None
    rows = []
    for c in d["data"]:
        # c[8] is OKX's confirm flag: "1" closed, "0" still forming.
        if len(c) > 8 and c[8] == "0":
            continue
        rows.append([int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])])
    rows.sort()
    return _rows_to_candles(rows) if rows else None


def _coinbase(symbol: str, tf: str, limit: int) -> Optional[List[dict]]:
    gran = TF[tf][1]
    if gran is None:
        return None
    d = http.get_json(f"https://api.exchange.coinbase.com/products/{symbol}/candles",
                      {"granularity": gran}, ttl=config.CACHE_TTL_CANDLES)
    if not isinstance(d, list) or not d:
        return None
    # coinbase: [time, low, high, open, close, volume], newest first, seconds
    rows = sorted([[int(c[0]) * 1000, float(c[3]), float(c[2]), float(c[1]), float(c[4]), float(c[5])] for c in d])
    now = datetime.now(timezone.utc).timestamp()
    rows = [r for r in rows if r[0] / 1000 + gran <= now]   # drop the forming bar
    return _rows_to_candles(rows[-limit:]) if rows else None


def _kraken(symbol: str, tf: str, limit: int) -> Optional[List[dict]]:
    mins = TF[tf][2]
    if mins is None:
        return None
    base, _, quote = symbol.partition("-")
    pair = ("XBT" if base == "BTC" else base) + ("USD" if quote in ("USDT", "USD", "USDC") else quote)
    d = http.get_json("https://api.kraken.com/0/public/OHLC",
                      {"pair": pair, "interval": mins}, ttl=config.CACHE_TTL_CANDLES)
    if not d or d.get("error") or not d.get("result"):
        return None
    key = next((k for k in d["result"] if k != "last"), None)
    if not key:
        return None
    rows = sorted([[int(c[0]) * 1000, float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[6])]
                   for c in d["result"][key]])
    now = datetime.now(timezone.utc).timestamp()
    rows = [r for r in rows if r[0] / 1000 + mins * 60 <= now]
    return _rows_to_candles(rows[-limit:]) if rows else None


def candles(symbol: str, venue: str, tf: str, limit: int = None) -> Optional[List[dict]]:
    """Closed candles, oldest first. Tries the market's own venue first, then others."""
    limit = limit or config.CANDLES
    order = {"okx": [_okx, _coinbase, _kraken], "coinbase": [_coinbase, _okx, _kraken]}.get(
        venue, [_okx, _coinbase, _kraken])
    for fn in order:
        try:
            got = fn(symbol, tf, limit)
        except Exception:  # noqa: BLE001 - a broken venue is not a broken scan
            got = None
        if got and len(got) >= 60:
            return got
    return None


def candles_many(markets: List[dict], tf: str, limit: int = None) -> Dict[str, Optional[List[dict]]]:
    """Fetch many markets concurrently. Returns {symbol: candles or None}."""
    out: Dict[str, Optional[List[dict]]] = {}

    def work(m: dict):
        return m["symbol"], candles(m["symbol"], m.get("venue", "okx"), tf, limit)

    with ThreadPoolExecutor(max_workers=config.MAX_WORKERS) as pool:
        for sym, c in pool.map(work, markets):
            out[sym] = c
    return out


# =============================================================================
# Deep history, for backtesting
# =============================================================================
# A scan only needs a few hundred bars, but measuring whether a strategy works needs
# thousands. Public endpoints cap a single request at 300 candles, so deep history is
# paged and then cached on disk: refetching years of candles on every backtest would
# be slow, rude to a free API, and pointless since old bars never change.

import csv as _csv
import os as _os
import threading as _threading

_DEEP_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "data", "candles")
_deep_lock = _threading.Lock()


def _cache_path(symbol: str, tf: str) -> str:
    safe = symbol.replace("/", "_").replace(":", "_")
    return _os.path.join(_DEEP_DIR, f"{safe}_{tf}.csv")


def _read_cache(path: str) -> List[dict]:
    if not _os.path.exists(path):
        return []
    try:
        with open(path, newline="", encoding="utf-8") as fh:
            return [{"ts": datetime.fromisoformat(r["ts"]), "open": float(r["open"]),
                     "high": float(r["high"]), "low": float(r["low"]),
                     "close": float(r["close"]), "volume": float(r["volume"])}
                    for r in _csv.DictReader(fh)]
    except Exception:                                   # noqa: BLE001 - a corrupt cache is not fatal
        return []


def _write_cache(path: str, candles: List[dict]) -> None:
    _os.makedirs(_os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", newline="", encoding="utf-8") as fh:
        w = _csv.writer(fh)
        w.writerow(["ts", "open", "high", "low", "close", "volume"])
        for c in candles:
            w.writerow([c["ts"].isoformat(), c["open"], c["high"], c["low"], c["close"], c["volume"]])
    _os.replace(tmp, path)                              # atomic, so a crash cannot truncate the cache


def _okx_paged(symbol: str, tf: str, want: int) -> List[dict]:
    bar = TF[tf][0]
    rows: List[list] = []
    after = None
    while len(rows) < want:
        params = {"instId": symbol, "bar": bar, "limit": "300"}
        if after:
            params["after"] = str(after)
        d = http.get_json("https://www.okx.com/api/v5/market/history-candles", params,
                          ttl=86400 if after else 300)
        if not d or d.get("code") != "0" or not d.get("data"):
            break
        page = d["data"]
        for c in page:
            if len(c) > 8 and c[8] == "0":
                continue
            rows.append([int(c[0]), float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[5])])
        after = int(page[-1][0])
        if len(page) < 300:
            break
        time.sleep(0.12)                                # be polite to a free endpoint
    rows.sort()
    seen, dedup = set(), []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            dedup.append(r)
    return _rows_to_candles(dedup)


def _coinbase_paged(symbol: str, tf: str, want: int) -> List[dict]:
    gran = TF[tf][1]
    if gran is None:
        return []
    rows: List[list] = []
    end = datetime.now(timezone.utc)
    while len(rows) < want:
        n = min(300, want - len(rows))
        start = end - timedelta(seconds=gran * n)
        d = http.get_json(f"https://api.exchange.coinbase.com/products/{symbol}/candles",
                          {"granularity": gran, "start": start.isoformat(), "end": end.isoformat()},
                          ttl=86400)
        if not isinstance(d, list) or not d:
            break
        rows += [[int(c[0]) * 1000, float(c[3]), float(c[2]), float(c[1]), float(c[4]), float(c[5])] for c in d]
        end = start
        if len(d) < n * 0.5:
            break
        time.sleep(0.15)
    rows.sort()
    now = datetime.now(timezone.utc).timestamp()
    rows = [r for r in rows if r[0] / 1000 + gran <= now]
    seen, dedup = set(), []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            dedup.append(r)
    return _rows_to_candles(dedup)


def deep_candles(symbol: str, venue: str, tf: str = "1h", want: int = 3000,
                 use_cache: bool = True) -> List[dict]:
    """Thousands of closed candles, paged from the venue and cached on disk.

    Only the missing tail is fetched when a cache already exists, so the first call
    for a market is slow and every call after it is nearly free.
    """
    path = _cache_path(symbol, tf)
    cached = _read_cache(path) if use_cache else []
    if cached and len(cached) >= want:
        tf_sec = {"5m": 300, "15m": 900, "1h": 3600, "4h": 14400, "1d": 86400}.get(tf, 3600)
        age = (datetime.now(timezone.utc) - cached[-1]["ts"]).total_seconds()
        if age < tf_sec * 3:
            return cached[-want:]

    fetched: List[dict] = []
    for fn in ([_okx_paged, _coinbase_paged] if venue != "coinbase" else [_coinbase_paged, _okx_paged]):
        try:
            fetched = fn(symbol, tf, want)
        except Exception:                               # noqa: BLE001
            fetched = []
        if fetched and len(fetched) >= min(300, want // 4):
            break

    merged = {c["ts"]: c for c in cached}
    merged.update({c["ts"]: c for c in fetched})
    out = [merged[k] for k in sorted(merged)]
    if out and use_cache:
        with _deep_lock:
            _write_cache(path, out)
    return out[-want:]


def deep_many(markets: List[dict], tf: str = "1h", want: int = 3000,
              max_workers: int = None) -> Dict[str, List[dict]]:
    out: Dict[str, List[dict]] = {}

    def work(m):
        return m["symbol"], deep_candles(m["symbol"], m.get("venue", "okx"), tf, want)

    with ThreadPoolExecutor(max_workers=max_workers or max(2, config.MAX_WORKERS // 2)) as pool:
        for sym, c in pool.map(work, markets):
            out[sym] = c
    return out
