#!/usr/bin/env python3
"""US stocks: quotes, candles and deep history from Yahoo Finance's public chart API.

No key, no account. One chart request per symbol returns both the bars and the quote
details (price, day high and low, volume, and the current trading period), so the
watchlist is fetched concurrently and cached for a couple of minutes.

Stocks differ from crypto in two ways that matter to every strategy and to the bots:

  * They trade in sessions, 9:30 to 16:00 New York time, with overnight gaps. Hourly
    bars start at :30 and the last one of the day is half an hour long. The session
    table in engine/strategies reads the gaps and handles both markets the same way.
  * A price only moves while the market is open. The bots only open stock trades in
    regular hours, and a stop resting overnight fills at the next open if the stock
    gaps through it, which is exactly how it fills in real life.
"""

from __future__ import annotations

import threading
import time
import urllib.parse
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from typing import Dict, List, Optional

import config
from engine import http

BASE = "https://query1.finance.yahoo.com/v8/finance/chart/"

# our timeframe -> (Yahoo interval, the longest range Yahoo serves at that interval)
TF = {"5m": ("5m", "60d"), "15m": ("15m", "60d"), "1h": ("1h", "730d"), "4h": ("1h", "730d"),
      "1d": ("1d", "10y")}
_TF_SECONDS = {"5m": 300, "15m": 900, "1h": 3600, "1d": 86400}


BASE2 = "https://query2.finance.yahoo.com/v8/finance/chart/"
_gate = threading.Lock()
_last_call = [0.0]
MIN_GAP_S = 0.12            # Yahoo answers bursts with 429s; a small gap between calls avoids them


def _chart(symbol: str, interval: str, rng: str, ttl: float) -> Optional[dict]:
    params = {"interval": interval, "range": rng, "includePrePost": "false"}
    for attempt in range(3):
        host = BASE if attempt % 2 == 0 else BASE2
        cached = http.cache_get(host + symbol + "?" + urllib.parse.urlencode(params), ttl)
        if cached is None:
            with _gate:
                wait = _last_call[0] + MIN_GAP_S - time.time()
                if wait > 0:
                    time.sleep(wait)
                _last_call[0] = time.time()
        d = http.get_json(host + symbol, params, ttl=ttl)
        try:
            return d["chart"]["result"][0]
        except (TypeError, KeyError, IndexError):
            if d is not None:
                return None                              # a real answer with no data: an unknown ticker
            time.sleep(0.6 * (attempt + 1))              # throttled or dropped: back off, try the other host
    return None


def market_open(meta: dict, now: float = None) -> bool:
    """Is the regular session open right now, according to the exchange's own clock?"""
    now = now or time.time()
    try:
        reg = meta["currentTradingPeriod"]["regular"]
        return reg["start"] <= now < reg["end"]
    except (KeyError, TypeError):
        return False


def _bars(res: dict, interval: str) -> List[dict]:
    ts = res.get("timestamp") or []
    q = (res.get("indicators") or {}).get("quote", [{}])[0]
    o, h, l, c, v = (q.get(k) or [] for k in ("open", "high", "low", "close", "volume"))
    out = []
    for i, t in enumerate(ts):
        try:
            row = (o[i], h[i], l[i], c[i])
        except IndexError:
            continue
        if None in row or min(row) <= 0:
            continue
        out.append({"ts": datetime.fromtimestamp(t, tz=timezone.utc), "open": float(o[i]), "high": float(h[i]),
                    "low": float(l[i]), "close": float(c[i]), "volume": float((v[i] if i < len(v) else 0) or 0)})
    # Drop the bar that is still forming, so strategies only ever see closed bars.
    meta = res.get("meta") or {}
    step = _TF_SECONDS.get(interval, 3600)
    if out and market_open(meta) and out[-1]["ts"].timestamp() + step > time.time():
        out.pop()
    return out


def _aggregate_4h(bars: List[dict]) -> List[dict]:
    """Four hourly bars of the same session make one bias bar (Yahoo has no 4h)."""
    out, cur, day = [], None, None
    for b in bars:
        d = b["ts"].date()
        if cur is None or d != day or cur["n"] == 4:
            if cur:
                out.append({k: cur[k] for k in ("ts", "open", "high", "low", "close", "volume")})
            cur = {**b, "n": 1}
            day = d
        else:
            cur["high"] = max(cur["high"], b["high"])
            cur["low"] = min(cur["low"], b["low"])
            cur["close"] = b["close"]
            cur["volume"] += b["volume"]
            cur["n"] += 1
    if cur:
        out.append({k: cur[k] for k in ("ts", "open", "high", "low", "close", "volume")})
    return out


def candles(symbol: str, tf: str = "1h", limit: int = 300) -> Optional[List[dict]]:
    interval, rng = TF.get(tf, ("1h", "730d"))
    if tf in ("1h", "4h") and limit <= 400:
        rng = "180d" if tf == "4h" else "90d"         # enough bars, a tenth of the download
    res = _chart(symbol, interval, rng, ttl=config.CACHE_TTL_CANDLES)
    if not res:
        return None
    bars = _bars(res, interval)
    if tf == "4h":
        bars = _aggregate_4h(bars)
    return bars[-limit:] if bars else None


def deep(symbol: str, tf: str = "1h", want: int = 3000) -> List[dict]:
    interval, rng = TF.get(tf, ("1h", "730d"))
    res = _chart(symbol, interval, rng, ttl=3600)
    bars = _bars(res, interval) if res else []
    return bars[-want:]


def price(symbol: str) -> Optional[float]:
    res = _chart(symbol, "1d", "1d", ttl=4)           # the smallest request that carries the live price
    try:
        px = float(res["meta"]["regularMarketPrice"])
        return px if px > 0 else None
    except (TypeError, KeyError, ValueError):
        return None


def quote(symbol: str) -> Optional[dict]:
    res = _chart(symbol, "1d", "5d", ttl=config.CACHE_TTL_UNIVERSE)
    if not res:
        return None
    m = res.get("meta") or {}
    px = m.get("regularMarketPrice")
    if not px:
        return None
    prev = m.get("chartPreviousClose") or m.get("previousClose") or px
    return {
        "symbol": symbol, "base": symbol, "quote": "USD", "venue": "yahoo", "kind": "stock", "asset": "stock",
        "price": float(px),
        "open24h": float(prev),                         # change is measured from the previous close
        "high24h": float(m.get("regularMarketDayHigh") or px),
        "low24h": float(m.get("regularMarketDayLow") or px),
        "usd_volume_24h": float(m.get("regularMarketVolume") or 0) * float(px),
        "name": m.get("shortName") or m.get("longName") or symbol,
        "exchange": m.get("fullExchangeName") or m.get("exchangeName"),
        "market_open": market_open(m),
    }


def universe_markets(symbols: List[str] = None) -> List[dict]:
    symbols = symbols or config.STOCK_WATCHLIST
    with ThreadPoolExecutor(max_workers=4) as pool:
        got = list(pool.map(quote, symbols))
    return [q for q in got if q]


def session_clock() -> Optional[dict]:
    """The US regular session's start and end (epoch seconds), and whether it is open now."""
    res = _chart("SPY", "1d", "5d", ttl=60)
    try:
        reg = res["meta"]["currentTradingPeriod"]["regular"]
    except (TypeError, KeyError):
        return None
    now = time.time()
    return {"open": reg["start"] <= now < reg["end"], "start": reg["start"], "end": reg["end"]}


def is_open_now() -> bool:
    q = quote("SPY")
    return bool(q and q.get("market_open"))
