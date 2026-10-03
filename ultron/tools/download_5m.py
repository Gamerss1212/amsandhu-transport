#!/usr/bin/env python3
"""Download Coinbase 5-minute candles (for the 5m, 15m and 30m councils), resumable, with retries.

  python3 ultron/tools/download_5m.py --out <dir> [--since 2023-10-01] [--coins BTC,ETH,...]
Writes <dir>/<COIN>_5m.csv (timestamp_utc, open, high, low, close, volume), oldest first.
"""

from __future__ import annotations

import argparse
import csv
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "jarvus", "scripts"))
from fetch_ohlcv import http_get, iso  # noqa: E402

GRAN = 300


def download(coin, since, out_dir, log):
    path = os.path.join(out_dir, f"{coin}_5m.csv")
    if os.path.exists(path) and os.path.getsize(path) > 1000:
        log(f"{coin}: already have it")
        return
    end = datetime.now(timezone.utc).replace(second=0, microsecond=0)
    end -= timedelta(minutes=end.minute % 5)
    rows, empty = {}, 0
    while end > since:
        start = max(since, end - timedelta(seconds=GRAN * 300))
        data = None
        for attempt in range(6):
            try:
                data = http_get(f"https://api.exchange.coinbase.com/products/{coin}-USD/candles",
                                {"granularity": GRAN, "start": start.isoformat(), "end": end.isoformat()})
                break
            except Exception as e:                                # noqa: BLE001
                time.sleep(2 ** attempt)
                if attempt == 5:
                    log(f"{coin}: giving up a window at {start:%Y-%m-%d} ({type(e).__name__})")
        if data:
            empty = 0
            for c in data:
                rows[c[0] * 1000] = [c[0] * 1000, float(c[3]), float(c[2]), float(c[1]), float(c[4]), float(c[5])]
        else:
            empty += 1
            if empty >= 20 and rows:                               # before the coin was listed
                break
        end = start
        time.sleep(0.36)
    out = sorted(rows.values())
    with open(path + ".tmp", "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["timestamp_utc", "open", "high", "low", "close", "volume"])
        for r in out:
            w.writerow([iso(r[0])] + r[1:])
    os.replace(path + ".tmp", path)
    log(f"{coin}: {len(out):,} candles from {iso(out[0][0]) if out else '-'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", required=True)
    ap.add_argument("--since", default="2023-10-01")
    ap.add_argument("--coins", default="BTC,ETH,SOL,DOGE,SHIB,PEPE,BONK,WIF,FLOKI")
    ap.add_argument("--threads", type=int, default=3)
    a = ap.parse_args()
    os.makedirs(a.out, exist_ok=True)
    since = datetime.strptime(a.since, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    coins = a.coins.split(",")
    lock = threading.Lock()

    def log(msg):
        with lock:
            print(f"{datetime.now():%H:%M:%S} {msg}", flush=True)

    def worker():
        while True:
            with lock:
                if not coins:
                    return
                c = coins.pop(0)
            download(c, since, a.out, log)
    ts = [threading.Thread(target=worker) for _ in range(a.threads)]
    for t in ts:
        t.start()
    for t in ts:
        t.join()


if __name__ == "__main__":
    main()
