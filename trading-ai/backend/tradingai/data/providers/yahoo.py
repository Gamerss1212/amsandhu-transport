"""Yahoo Finance chart data (no key; unofficial, can change or rate-limit). Stocks, ETFs, FX reference mids, index
levels and continuous futures. Daily bars are split- and dividend-adjusted with Yahoo's adjusted close.
Intraday history is limited by Yahoo: 1m for about 7 days, 5m-30m for about 60 days, 1h for about 730 days."""

from __future__ import annotations

import time

import numpy as np

from tradingai.data.bars import TF_MS, Bars
from tradingai.data.net import Http
from tradingai.data.providers.base import Provider, from_rows

INTERVAL = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "60m", "1d": "1d"}
MAX_DAYS = {"1m": 7, "5m": 59, "15m": 59, "30m": 59, "1h": 729, "1d": 365 * 30}


class Yahoo(Provider):
    name = "yahoo"
    timeframes = tuple(INTERVAL)

    def __init__(self, http: Http):
        self.http = http

    def fetch(self, instrument_id: str, symbol: str, tf: str, start_ms: int, end_ms: int | None = None) -> Bars:
        now = int(time.time() * 1000)
        end = end_ms or now
        start = max(start_ms, end - MAX_DAYS[tf] * 86_400_000)
        d = self.http.get_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}",
                               params={"interval": INTERVAL[tf], "period1": start // 1000, "period2": end // 1000,
                                       "includePrePost": "false", "events": "div,splits"})
        res = (d.get("chart") or {}).get("result")
        if not res:
            err = (d.get("chart") or {}).get("error") or {}
            raise ValueError(f"yahoo {symbol}: {err.get('description') or 'no data'}")
        r = res[0]
        ts = r.get("timestamp") or []
        q = r["indicators"]["quote"][0]
        o, h, lo, c, v = (np.array([x if x is not None else np.nan for x in q.get(k) or []], dtype=float)
                          for k in ("open", "high", "low", "close", "volume"))
        adj = None
        if tf == "1d" and r["indicators"].get("adjclose"):
            adj = np.array([x if x is not None else np.nan for x in r["indicators"]["adjclose"][0]["adjclose"]])
        rows = []
        for i, t in enumerate(ts):
            if any(np.isnan(x[i]) for x in (o, h, lo, c)):
                continue
            k = adj[i] / c[i] if adj is not None and not np.isnan(adj[i]) and c[i] else 1.0
            rows.append((int(t) * 1000, o[i] * k, h[i] * k, lo[i] * k, c[i] * k, 0.0 if np.isnan(v[i]) else v[i]))
        b = from_rows(instrument_id, tf, rows, f"yahoo:{symbol}")
        b.meta["adjusted"] = adj is not None
        tz = (r.get("meta") or {}).get("exchangeTimezoneName")
        b.meta["exchange_tz"] = tz
        if tf == "1d" and tz == "America/New_York" and not symbol.endswith("=F") and not symbol.endswith("=X"):
            b.meta["avail"] = us_session_close(b.ts)       # a US daily bar is known at the closing bell
        return self.complete_only(b, now)


def us_session_close(ts: np.ndarray) -> np.ndarray:
    """16:00 New York on each bar's date (13:00 on early-close days), in UTC ms."""
    from datetime import datetime, time as dtime, timezone
    from tradingai.market.calendars import NY, nyse_early_closes
    out = np.empty(len(ts), dtype=np.int64)
    for i, t in enumerate(ts):
        d = datetime.fromtimestamp(int(t) / 1000, tz=timezone.utc).astimezone(NY).date()
        close = dtime(13, 0) if d in nyse_early_closes(d.year) else dtime(16, 0)
        out[i] = int(datetime.combine(d, close, NY).timestamp() * 1000)
    return out
