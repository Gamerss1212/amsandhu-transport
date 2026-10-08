"""Kraken public OHLC (no key): GET /0/public/OHLC. Kraken returns at most the latest 720 bars per interval."""

from __future__ import annotations

from tradingai.data.bars import Bars
from tradingai.data.net import Http
from tradingai.data.providers.base import Provider, from_rows

INTERVAL = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}


class Kraken(Provider):
    name = "kraken"
    timeframes = tuple(INTERVAL)

    def __init__(self, http: Http):
        self.http = http

    def fetch(self, instrument_id: str, symbol: str, tf: str, start_ms: int, end_ms: int | None = None) -> Bars:
        d = self.http.get_json("https://api.kraken.com/0/public/OHLC",
                               params={"pair": symbol, "interval": INTERVAL[tf], "since": start_ms // 1000})
        if d.get("error"):
            raise ValueError(f"kraken: {', '.join(d['error'])}")
        key = next(k for k in d["result"] if k != "last")
        rows = [(int(r[0]) * 1000, float(r[1]), float(r[2]), float(r[3]), float(r[4]), float(r[6]))
                for r in d["result"][key]]
        rows = [r for r in rows if r[0] >= start_ms and (end_ms is None or r[0] < end_ms)]
        return self.complete_only(from_rows(instrument_id, tf, rows, f"kraken:{symbol}"))
