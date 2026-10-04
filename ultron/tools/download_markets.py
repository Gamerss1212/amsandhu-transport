#!/usr/bin/env python3
"""Download daily candles for the ULTRON markets council (stocks, ETFs, forex, commodity ETFs) from Yahoo Finance.

  python3 ultron/tools/download_markets.py --out <dir> [--since 2005-01-01]
Writes <dir>/<NAME>_1d.csv (timestamp_utc = 00:00 UTC of the trading date, open, high, low, close, volume), oldest
first, split-adjusted like TradingView's default chart. NAME is the TradingView ticker (EURUSD=X -> EURUSD, RY.TO -> RY).
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
import urllib.request
from datetime import datetime, timezone

DAY = 86_400
# Yahoo symbol -> TradingView ticker
MARKETS = {
    "SPY": "SPY", "QQQ": "QQQ", "IWM": "IWM", "DIA": "DIA",                                   # US index ETFs
    "AAPL": "AAPL", "MSFT": "MSFT", "NVDA": "NVDA", "AMZN": "AMZN", "GOOGL": "GOOGL", "META": "META",
    "TSLA": "TSLA", "JPM": "JPM", "AMD": "AMD", "NFLX": "NFLX",                               # US large caps
    "XIU.TO": "XIU", "RY.TO": "RY", "TD.TO": "TD", "ENB.TO": "ENB", "SHOP.TO": "SHOP", "CNQ.TO": "CNQ",   # Canada
    "EURUSD=X": "EURUSD", "GBPUSD=X": "GBPUSD", "USDJPY=X": "USDJPY", "USDCAD=X": "USDCAD", "AUDUSD=X": "AUDUSD",
    "GLD": "GLD", "SLV": "SLV", "USO": "USO",                                                 # gold, silver, oil
}


def fetch(sym, since):
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.request.quote(sym)}?period1={since}"
           f"&period2={int(time.time())}&interval=1d&includeAdjustedClose=false")
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    for attempt in range(5):
        try:
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.load(r)["chart"]["result"][0]
        except Exception:                                                  # noqa: BLE001
            time.sleep(2 ** attempt)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--since", default="2005-01-01")
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    since = int(datetime.strptime(a.since, "%Y-%m-%d").replace(tzinfo=timezone.utc).timestamp())
    for sym, name in MARKETS.items():
        res = fetch(sym, since)
        if not res or "timestamp" not in res:
            print(f"{name}: no data")
            continue
        off = int(res["meta"].get("gmtoffset", 0))
        q = res["indicators"]["quote"][0]
        rows = {}
        for k, t in enumerate(res["timestamp"]):
            o, h, l, c, v = (q[x][k] for x in ("open", "high", "low", "close", "volume"))
            if None in (o, h, l, c) or min(o, h, l, c) <= 0:
                continue
            day = (t + off) // DAY * DAY                                    # the trading date in the exchange's zone
            rows[day] = [day, o, max(h, o, c), min(l, o, c), c, v or 0]
        out = sorted(rows.values())[:-1]                                   # drop today's unfinished bar
        with open(os.path.join(a.out, f"{name}_1d.csv"), "w", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["timestamp_utc", "open", "high", "low", "close", "volume"])
            for r in out:
                w.writerow([datetime.fromtimestamp(r[0], timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")] + r[1:])
        print(f"{name}: {len(out):,} days from {datetime.fromtimestamp(out[0][0], timezone.utc):%Y-%m-%d}", flush=True)
        time.sleep(0.5)


if __name__ == "__main__":
    main()
