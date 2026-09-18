#!/usr/bin/env python3
"""Candle fetching across venues, concurrently, with the unclosed bar handled honestly.

Every venue returns the in-progress candle alongside closed ones. Treating a partial
bar as closed is the most common silent bug in retail tooling: its range, volume and
close are all incomplete, so indicators computed on it flicker and any signal that
depends on a candle close fires early. This module separates the two and the rest of
the app only ever reasons about closed bars.
"""

from __future__ import annotations

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
