#!/usr/bin/env python3
"""Fetch OHLCV candles (and optionally derivatives context) from public exchange APIs.

No API keys. Standard library only. Tries exchanges in order until one answers,
because Binance is geo-blocked in some regions and every exchange has outages.

Examples:
  python3 fetch_ohlcv.py --symbol BTCUSDT --interval 15m --limit 500 --out btc_15m.csv
  python3 fetch_ohlcv.py --symbol SOL/USDT --interval 4h --exchange kraken
  python3 fetch_ohlcv.py --symbol ETHUSDT --derivs          # funding, OI, long/short ratio (Binance futures)

Output CSV columns: timestamp_utc,open,high,low,close,volume  (oldest first).
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

USER_AGENT = "crypto-day-trading-skill/1.0"
TIMEOUT = 20

# interval -> (binance, coinbase_seconds, kraken_minutes)
INTERVALS: Dict[str, Tuple[Optional[str], Optional[int], Optional[int]]] = {
    "1m": ("1m", 60, 1),
    "5m": ("5m", 300, 5),
    "15m": ("15m", 900, 15),
    "30m": ("30m", None, 30),
    "1h": ("1h", 3600, 60),
    "4h": ("4h", None, 240),
    "6h": ("6h", 21600, None),
    "1d": ("1d", 86400, 1440),
    "1w": ("1w", None, 10080),
}

STABLE_QUOTES = {"USDT", "USDC", "USD", "BUSD", "FDUSD", "TUSD", "DAI"}


def parse_symbol(raw: str) -> Tuple[str, str]:
    """'BTCUSDT' / 'BTC/USDT' / 'BTC-USD' / 'btc' -> ('BTC', 'USDT')."""
    s = raw.upper().replace(" ", "")
    for sep in ("/", "-", "_", ":"):
        if sep in s:
            base, quote = s.split(sep, 1)
            return base, quote
    for q in sorted(STABLE_QUOTES, key=len, reverse=True):
        if s.endswith(q) and len(s) > len(q):
            return s[: -len(q)], q
    if s.endswith("BTC") and len(s) > 3:
        return s[:-3], "BTC"
    return s, "USDT"


def http_get(url: str, params: Optional[dict] = None):
    if params:
        url = url + "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
    with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))


def iso(ms: float) -> str:
    return datetime.fromtimestamp(ms / 1000.0, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


# ---------------------------------------------------------------- binance ---

def fetch_binance(base: str, quote: str, interval: str, limit: int) -> List[list]:
    b_int = INTERVALS[interval][0]
    if b_int is None:
        raise ValueError(f"binance does not support {interval}")
    symbol = base + ("USDT" if quote == "USD" else quote)
    rows: List[list] = []
    end_time: Optional[int] = None
    remaining = limit
    while remaining > 0:
        params = {"symbol": symbol, "interval": b_int, "limit": min(1000, remaining)}
        if end_time is not None:
            params["endTime"] = end_time
        data = http_get("https://api.binance.com/api/v3/klines", params)
        if not data:
            break
        batch = [[k[0], float(k[1]), float(k[2]), float(k[3]), float(k[4]), float(k[5])] for k in data]
        rows = batch + rows
        remaining -= len(batch)
        end_time = batch[0][0] - 1
        if len(batch) < params["limit"]:
            break
        time.sleep(0.2)
    return rows[-limit:]


# --------------------------------------------------------------- coinbase ---

def fetch_coinbase(base: str, quote: str, interval: str, limit: int) -> List[list]:
    gran = INTERVALS[interval][1]
    if gran is None:
        raise ValueError(f"coinbase does not support {interval}")
    q = "USD" if quote in ("USDT", "USD", "BUSD", "FDUSD") else quote
    product = f"{base}-{q}"
    rows: List[list] = []
    end = datetime.now(timezone.utc)
    remaining = limit
    while remaining > 0:
        n = min(300, remaining)
        start = end - timedelta(seconds=gran * n)
        params = {"granularity": gran, "start": start.isoformat(), "end": end.isoformat()}
        data = http_get(f"https://api.exchange.coinbase.com/products/{product}/candles", params)
        if not data:
            break
        # coinbase: [time, low, high, open, close, volume], newest first
        batch = sorted([[c[0] * 1000, float(c[3]), float(c[2]), float(c[1]), float(c[4]), float(c[5])] for c in data])
        rows = batch + rows
        remaining -= len(batch)
        end = start
        if len(batch) < n * 0.5:  # sparse history; stop paging
            break
        time.sleep(0.25)
    # de-duplicate on timestamp
    seen = set()
    dedup = []
    for r in rows:
        if r[0] not in seen:
            seen.add(r[0])
            dedup.append(r)
    return dedup[-limit:]


# ----------------------------------------------------------------- kraken ---

def fetch_kraken(base: str, quote: str, interval: str, limit: int) -> List[list]:
    k_int = INTERVALS[interval][2]
    if k_int is None:
        raise ValueError(f"kraken does not support {interval}")
    b = "XBT" if base == "BTC" else base
    q = "USD" if quote in ("USDT", "USD", "BUSD", "FDUSD") else quote
    data = http_get("https://api.kraken.com/0/public/OHLC", {"pair": b + q, "interval": k_int})
    if data.get("error"):
        raise RuntimeError("kraken: " + "; ".join(data["error"]))
    result = data["result"]
    key = next(k for k in result if k != "last")
    rows = [[c[0] * 1000, float(c[1]), float(c[2]), float(c[3]), float(c[4]), float(c[6])] for c in result[key]]
    rows.sort()
    return rows[-limit:]


FETCHERS = {"binance": fetch_binance, "coinbase": fetch_coinbase, "kraken": fetch_kraken}


def fetch_candles(symbol: str, interval: str, limit: int, exchange: str) -> Tuple[str, List[list]]:
    base, quote = parse_symbol(symbol)
    order = [exchange] if exchange in FETCHERS else ["binance", "coinbase", "kraken"]
    errors = []
    for name in order:
        try:
            rows = FETCHERS[name](base, quote, interval, limit)
            if rows:
                return name, rows
            errors.append(f"{name}: empty response")
        except Exception as exc:  # noqa: BLE001 - we want to keep trying
            errors.append(f"{name}: {exc}")
    raise SystemExit("all exchanges failed:\n  " + "\n  ".join(errors))


# ------------------------------------------------------------ derivatives ---

def _derivs_binance(base: str, quote: str) -> dict:
    sym = base + ("USDT" if quote in ("USD", "USDT") else quote)
    out: dict = {"symbol": sym, "source": "binance-futures"}
    p = http_get("https://fapi.binance.com/fapi/v1/premiumIndex", {"symbol": sym})
    out["mark_price"] = float(p["markPrice"])
    out["index_price"] = float(p["indexPrice"])
    out["funding_rate_8h_pct"] = float(p["lastFundingRate"]) * 100
    out["next_funding_utc"] = iso(p["nextFundingTime"])
    try:
        hist = http_get("https://fapi.binance.com/fapi/v1/fundingRate", {"symbol": sym, "limit": 9})
        out["funding_history_8h_pct"] = [round(float(h["fundingRate"]) * 100, 4) for h in hist]
    except Exception as exc:  # noqa: BLE001
        out["funding_history_error"] = str(exc)
    try:
        oi = http_get("https://fapi.binance.com/fapi/v1/openInterest", {"symbol": sym})
        out["open_interest_coins"] = float(oi["openInterest"])
        out["open_interest_usd"] = out["open_interest_coins"] * out["mark_price"]
    except Exception as exc:  # noqa: BLE001
        out["oi_error"] = str(exc)
    try:
        oih = http_get("https://fapi.binance.com/futures/data/openInterestHist",
                       {"symbol": sym, "period": "1h", "limit": 25})
        vals = [float(x["sumOpenInterest"]) for x in oih]
        _oi_changes(out, vals)
    except Exception as exc:  # noqa: BLE001
        out["oi_hist_error"] = str(exc)
    try:
        ls = http_get("https://fapi.binance.com/futures/data/globalLongShortAccountRatio",
                      {"symbol": sym, "period": "1h", "limit": 1})
        if ls:
            out["long_short_account_ratio"] = float(ls[0]["longShortRatio"])
    except Exception as exc:  # noqa: BLE001
        out["long_short_error"] = str(exc)
    return out


def _derivs_okx(base: str, quote: str) -> dict:
    q = "USDT" if quote in ("USD", "USDT") else quote
    inst = f"{base}-{q}-SWAP"
    out: dict = {"symbol": inst, "source": "okx-swap"}
    fr = http_get("https://www.okx.com/api/v5/public/funding-rate", {"instId": inst})
    if fr.get("code") != "0" or not fr.get("data"):
        raise RuntimeError(f"okx funding: {fr.get('msg') or 'no data'}")
    d0 = fr["data"][0]
    out["funding_rate_8h_pct"] = float(d0["fundingRate"]) * 100
    out["next_funding_utc"] = iso(float(d0["fundingTime"]))
    tk = http_get("https://www.okx.com/api/v5/market/ticker", {"instId": inst})
    idx = http_get("https://www.okx.com/api/v5/market/index-tickers", {"instId": f"{base}-{q}"})
    if tk.get("data") and idx.get("data"):
        out["mark_price"] = float(tk["data"][0]["last"])
        out["index_price"] = float(idx["data"][0]["idxPx"])
    try:
        hist = http_get("https://www.okx.com/api/v5/public/funding-rate-history", {"instId": inst, "limit": 9})
        out["funding_history_8h_pct"] = [round(float(h["realizedRate"]) * 100, 4) for h in reversed(hist.get("data", []))]
    except Exception as exc:  # noqa: BLE001
        out["funding_history_error"] = str(exc)
    try:
        oi = http_get("https://www.okx.com/api/v5/public/open-interest", {"instType": "SWAP", "instId": inst})
        out["open_interest_coins"] = float(oi["data"][0]["oiCcy"])
        out["open_interest_usd"] = float(oi["data"][0]["oiUsd"])
    except Exception as exc:  # noqa: BLE001
        out["oi_error"] = str(exc)
    try:
        oih = http_get("https://www.okx.com/api/v5/rubik/stat/contracts/open-interest-volume", {"ccy": base, "period": "1H"})
        rows = sorted(oih.get("data", []), key=lambda r: float(r[0]))[-25:]
        _oi_changes(out, [float(r[1]) for r in rows])
    except Exception as exc:  # noqa: BLE001
        out["oi_hist_error"] = str(exc)
    try:
        ls = http_get("https://www.okx.com/api/v5/rubik/stat/contracts/long-short-account-ratio", {"ccy": base, "period": "1H"})
        rows = sorted(ls.get("data", []), key=lambda r: float(r[0]))
        if rows:
            out["long_short_account_ratio"] = float(rows[-1][1])
    except Exception as exc:  # noqa: BLE001
        out["long_short_error"] = str(exc)
    return out


def _derivs_bybit(base: str, quote: str) -> dict:
    sym = base + ("USDT" if quote in ("USD", "USDT") else quote)
    out: dict = {"symbol": sym, "source": "bybit-linear"}
    tk = http_get("https://api.bybit.com/v5/market/tickers", {"category": "linear", "symbol": sym})
    if tk.get("retCode") != 0 or not tk["result"]["list"]:
        raise RuntimeError(f"bybit: {tk.get('retMsg')}")
    t = tk["result"]["list"][0]
    out["mark_price"] = float(t["markPrice"])
    out["index_price"] = float(t["indexPrice"])
    out["funding_rate_8h_pct"] = float(t["fundingRate"]) * 100
    out["next_funding_utc"] = iso(float(t["nextFundingTime"]))
    out["open_interest_coins"] = float(t["openInterest"])
    out["open_interest_usd"] = float(t["openInterestValue"])
    try:
        oih = http_get("https://api.bybit.com/v5/market/open-interest",
                       {"category": "linear", "symbol": sym, "intervalTime": "1h", "limit": 25})
        rows = sorted(oih["result"]["list"], key=lambda r: int(r["timestamp"]))
        _oi_changes(out, [float(r["openInterest"]) for r in rows])
    except Exception as exc:  # noqa: BLE001
        out["oi_hist_error"] = str(exc)
    return out


def _oi_changes(out: dict, vals: List[float]) -> None:
    if len(vals) >= 2 and vals[0]:
        out["oi_change_24h_pct"] = (vals[-1] / vals[0] - 1) * 100
    if len(vals) >= 5 and vals[-5]:
        out["oi_change_4h_pct"] = (vals[-1] / vals[-5] - 1) * 100


DERIV_SOURCES = {"binance": _derivs_binance, "okx": _derivs_okx, "bybit": _derivs_bybit}


def fetch_derivs(symbol: str, exchange: str = "auto") -> dict:
    """Funding, open interest, and positioning from the first venue that answers.

    Binance and Bybit block some regions (HTTP 451 / CloudFront country block);
    OKX usually answers. All venues are perp markets so the numbers are comparable
    in spirit, but the level of funding differs by venue: say which one the data
    came from.
    """
    base, quote = parse_symbol(symbol)
    order = [exchange] if exchange in DERIV_SOURCES else ["binance", "okx", "bybit"]
    errors = []
    for name in order:
        try:
            out = DERIV_SOURCES[name](base, quote)
            out["fetched_utc"] = iso(time.time() * 1000)
            if "mark_price" in out and "index_price" in out and out["index_price"]:
                out["basis_pct"] = (out["mark_price"] / out["index_price"] - 1) * 100
            if "funding_rate_8h_pct" in out:
                out["funding_annualized_pct"] = out["funding_rate_8h_pct"] * 3 * 365
            out["errors_from_other_venues"] = errors
            return out
        except Exception as exc:  # noqa: BLE001
            errors.append(f"{name}: {exc}")
    return {"symbol": symbol, "source": None, "fetched_utc": iso(time.time() * 1000),
            "error": "no derivatives venue reachable", "errors": errors}


def interpret_derivs(d: dict) -> List[str]:
    notes = []
    f = d.get("funding_rate_8h_pct")
    if f is not None:
        if f > 0.10:
            notes.append(f"funding {f:+.3f}%/8h: EXTREME long crowding, long-squeeze risk on any dip")
        elif f > 0.03:
            notes.append(f"funding {f:+.3f}%/8h: longs crowded, pullbacks likely violent")
        elif f < -0.05:
            notes.append(f"funding {f:+.3f}%/8h: EXTREME short crowding, short-squeeze fuel")
        elif f < -0.01:
            notes.append(f"funding {f:+.3f}%/8h: shorts paying, mild squeeze potential")
        else:
            notes.append(f"funding {f:+.3f}%/8h: neutral")
    c24 = d.get("oi_change_24h_pct")
    if c24 is not None:
        if abs(c24) >= 5:
            notes.append(f"open interest {c24:+.1f}% in 24h: large positioning change, expect a fast move when a level breaks")
        else:
            notes.append(f"open interest {c24:+.1f}% in 24h: stable")
    ratio = d.get("long_short_account_ratio")
    if ratio is not None:
        la = ratio / (1 + ratio) * 100
        notes.append(f"long/short account ratio {ratio:.2f} (~{la:.0f}% of accounts long)")
    b = d.get("basis_pct")
    if b is not None:
        notes.append(f"perp basis {b:+.3f}% vs index" + (" (perp at a premium: leveraged longs paying up)" if b > 0.05 else
                     " (perp at a discount: leveraged shorts pressing)" if b < -0.05 else ""))
    if d.get("source") is None:
        notes.append("NO DERIVATIVES DATA: every venue failed; treat positioning as unknown and lower confidence")
    return notes


# ------------------------------------------------------------------- main ---

def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--symbol", default="BTCUSDT")
    ap.add_argument("--interval", default="15m", choices=sorted(INTERVALS))
    ap.add_argument("--limit", type=int, default=500)
    ap.add_argument("--exchange", default="auto", choices=["auto", "binance", "coinbase", "kraken", "okx", "bybit"],
                    help="candles: binance/coinbase/kraken; --derivs: binance/okx/bybit")
    ap.add_argument("--out", help="CSV path (default: print to stdout)")
    ap.add_argument("--derivs", action="store_true", help="fetch funding / OI / long-short instead of candles")
    ap.add_argument("--json", action="store_true", help="emit JSON instead of CSV for candles")
    args = ap.parse_args()

    if args.derivs:
        d = fetch_derivs(args.symbol, args.exchange)
        d["interpretation"] = interpret_derivs(d)
        text = json.dumps(d, indent=2)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
            print(f"wrote {args.out}", file=sys.stderr)
        else:
            print(text)
        return

    source, rows = fetch_candles(args.symbol, args.interval, args.limit, args.exchange)
    header = ["timestamp_utc", "open", "high", "low", "close", "volume"]
    records = [[iso(r[0]), r[1], r[2], r[3], r[4], r[5]] for r in rows]

    if args.json:
        payload = {"symbol": args.symbol, "interval": args.interval, "source": source,
                   "candles": [dict(zip(header, r)) for r in records]}
        text = json.dumps(payload)
        if args.out:
            with open(args.out, "w", encoding="utf-8") as fh:
                fh.write(text)
        else:
            print(text)
    else:
        fh = open(args.out, "w", newline="", encoding="utf-8") if args.out else sys.stdout
        w = csv.writer(fh)
        w.writerow(header)
        w.writerows(records)
        if args.out:
            fh.close()

    last = records[-1]
    print(f"{source}: {len(records)} x {args.interval} candles for {args.symbol}, "
          f"{records[0][0]} -> {last[0]}, last close {last[4]}", file=sys.stderr)


if __name__ == "__main__":
    main()
