"""Daily candles for the markets council (stocks, ETFs, forex, commodity ETFs) from Yahoo Finance's public chart API.

Rows match ultron/tools/download_markets.py exactly: [t_ms at 00:00 UTC of the trading date, open, high, low, close,
volume], split-adjusted, oldest first. A daily bar counts as final once the next UTC day is 2 hours old (every
exchange in the list has closed by then).
"""

from __future__ import annotations

import json
import time
import urllib.parse
import urllib.request

DAY = 86_400_000
# TradingView ticker -> Yahoo symbol (the 28 markets the council was trained on)
YAHOO = {"SPY": "SPY", "QQQ": "QQQ", "IWM": "IWM", "DIA": "DIA", "AAPL": "AAPL", "MSFT": "MSFT", "NVDA": "NVDA",
         "AMZN": "AMZN", "GOOGL": "GOOGL", "META": "META", "TSLA": "TSLA", "JPM": "JPM", "AMD": "AMD", "NFLX": "NFLX",
         "XIU": "XIU.TO", "RY": "RY.TO", "TD": "TD.TO", "ENB": "ENB.TO", "SHOP": "SHOP.TO", "CNQ": "CNQ.TO",
         "EURUSD": "EURUSD=X", "GBPUSD": "GBPUSD=X", "USDJPY": "USDJPY=X", "USDCAD": "USDCAD=X", "AUDUSD": "AUDUSD=X",
         "GLD": "GLD", "SLV": "SLV", "USO": "USO"}


def fetch_daily(name, days=900, now_ms=None):
    """-> (final_rows, live_row or None). live_row is today's unfinished bar (for the paper broker's stops/targets)."""
    now_ms = now_ms or int(time.time() * 1000)
    sym = YAHOO[name]
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(sym)}?period1={int(now_ms / 1000) - days * 86400}"
           f"&period2={int(now_ms / 1000)}&interval=1d&includeAdjustedClose=false")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=30) as r:
        res = json.load(r)["chart"]["result"][0]
    off = int(res["meta"].get("gmtoffset", 0))
    q = res["indicators"]["quote"][0]
    rows = {}
    for k, t in enumerate(res.get("timestamp") or []):
        o, h, l, c, v = (q[x][k] for x in ("open", "high", "low", "close", "volume"))
        if None in (o, h, l, c) or min(o, h, l, c) <= 0:
            continue
        d = (t + off) // 86400 * 86400 * 1000
        rows[d] = [d, o, max(h, o, c), min(l, o, c), c, v or 0]
    out = sorted(rows.values())
    final = [r for r in out if r[0] + DAY + 2 * 3_600_000 <= now_ms]
    live = out[-1] if out and out[-1][0] + DAY + 2 * 3_600_000 > now_ms else None
    return final, live


def weekly(rows):
    """Daily rows -> completed weekly bars (weeks start Monday, as in training); the current week is dropped unless
    its last trading day is already in (a Friday bar, or the next bar is in a new week)."""
    out, cur, k_cur = [], None, None
    for r in rows:
        k = (r[0] // DAY + 3) // 7
        if k != k_cur:
            if cur is not None:
                out.append(cur)
            k_cur, cur = k, [((k * 7) - 3) * DAY, r[1], r[2], r[3], r[4], r[5]]
        else:
            cur[2], cur[3], cur[4], cur[5] = max(cur[2], r[2]), min(cur[3], r[3]), r[4], cur[5] + r[5]
    if cur is not None and (rows[-1][0] // DAY + 3) % 7 == 4:              # the last bar is a Friday: week complete
        out.append(cur)
    return out
