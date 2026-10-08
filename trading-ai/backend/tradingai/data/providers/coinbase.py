"""Coinbase Exchange public candles (no key): GET /products/{id}/candles, at most 300 per request.
Native granularities: 1m, 5m, 15m, 1h, 6h, 1d; 30m and 4h are built from 15m and 1h by the pipeline."""

from __future__ import annotations

import time
from datetime import datetime, timezone

from tradingai.data.bars import TF_MS, Bars
from tradingai.data.net import Http
from tradingai.data.providers.base import Provider, from_rows

GRAN = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}
URL = "https://api.exchange.coinbase.com/products/{sym}/candles"


class Coinbase(Provider):
    name = "coinbase"
    timeframes = tuple(GRAN)

    def __init__(self, http: Http):
        self.http = http

    def fetch(self, instrument_id: str, symbol: str, tf: str, start_ms: int, end_ms: int | None = None) -> Bars:
        if tf not in GRAN:
            raise ValueError(f"coinbase has no {tf} candles")
        g = GRAN[tf]
        end = end_ms or int(time.time() * 1000)
        rows: list[tuple] = []
        t = start_ms
        while t < end:
            chunk_end = min(end, t + 300 * g * 1000)
            iso = lambda ms: datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()   # noqa: E731
            data = self.http.get_json(URL.format(sym=symbol), params={"granularity": g, "start": iso(t),
                                                                       "end": iso(chunk_end)})
            for r in data or []:                       # [time, low, high, open, close, volume], newest first
                ts = int(r[0]) * 1000
                if start_ms <= ts < end:
                    rows.append((ts, float(r[3]), float(r[2]), float(r[1]), float(r[4]), float(r[5])))
            t = chunk_end
        return self.complete_only(from_rows(instrument_id, tf, rows, f"coinbase:{symbol}"))
