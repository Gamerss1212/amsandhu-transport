"""Venue adapters: one interface over Coinbase, Kraken, OKX and Yahoo Finance.

Every adapter returns records from mab.models, oldest first, and **only completed bars**:
each venue returns the still-forming bar alongside finished ones, and each adapter drops it
by checking the bar's end against the current time. Strategies therefore never see a bar
whose high, low, close or volume can still change (no intrabar repainting).

Aggressor side of trades is normalised to the taker's side ("buy" = buyer lifted the ask).
Coinbase reports the maker's side on its public trades endpoint, so it is inverted here.
"""

from __future__ import annotations

import time
from typing import Dict, List, Optional

from mab.clock import tf_ms
from mab.models import Bar, BookSnapshot, Trade, now_ms
from mab.net import Http, HttpError


def _f(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


class Adapter:
    venue = "base"
    timeframes: Dict[str, object] = {}

    def __init__(self, http: Http):
        self.http = http

    def supports(self, tf: str) -> bool:
        return tf in self.timeframes

    def instruments(self) -> List[dict]:
        raise NotImplementedError

    def bars(self, symbol: str, tf: str, limit: int = 300, end_ms: Optional[int] = None) -> List[Bar]:
        raise NotImplementedError

    def trades(self, symbol: str, limit: int = 500) -> List[Trade]:
        raise NotImplementedError

    def last_price(self, symbol: str) -> Optional[tuple]:
        """(price, time_ms, source) right now: the middle of the best bid and ask."""
        b = self.book(symbol, depth=1)
        if b is None or not b.bids or not b.asks:
            return None
        return (b.bids[0][0] + b.asks[0][0]) / 2.0, b.event_time or now_ms(), f"{self.venue} order book mid"

    def book(self, symbol: str, depth: int = 50) -> Optional[BookSnapshot]:
        raise NotImplementedError

    @staticmethod
    def _complete(bars: List[Bar], tf: str, now: int) -> List[Bar]:
        step = tf_ms(tf)
        out = [b for b in bars if b.event_time + step <= now]
        for b in out:
            b.complete = True
        out.sort(key=lambda b: b.event_time)
        # de-duplicate by open time, keeping the last copy received
        dedup: Dict[int, Bar] = {}
        for b in out:
            dedup[b.event_time] = b
        return [dedup[k] for k in sorted(dedup)]


# ============================================================================ Coinbase

class Coinbase(Adapter):
    venue = "coinbase"
    base = "https://api.exchange.coinbase.com"
    timeframes = {"1m": 60, "5m": 300, "15m": 900, "1h": 3600, "1d": 86400}

    def instruments(self) -> List[dict]:
        out = []
        for p in self.http.get_json(f"{self.base}/products") or []:
            if p.get("status") != "online" or p.get("trading_disabled"):
                continue
            out.append({"venue": self.venue, "symbol": p["id"], "asset_type": "crypto",
                        "base": p.get("base_currency"), "quote": p.get("quote_currency"),
                        "tick_size": _f(p.get("quote_increment"), 0.01),
                        "lot_size": _f(p.get("base_increment"), 1e-8),
                        "min_notional": _f(p.get("min_market_funds"), 1.0),
                        "can_short": False, "calendar": "CRYPTO-UTC"})
        return out

    def bars(self, symbol, tf, limit=300, end_ms=None):
        g = self.timeframes[tf]
        now = now_ms()
        end = end_ms or now
        start = end - min(limit, 300) * g * 1000
        rows = self.http.get_json(f"{self.base}/products/{symbol}/candles",
                                  {"granularity": g, "start": _iso(start), "end": _iso(end)})
        recv = now_ms()
        bars = [Bar(self.venue, symbol, tf, int(r[0]) * 1000, float(r[3]), float(r[2]), float(r[1]),
                    float(r[4]), float(r[5]), recv, "coinbase.rest.candles") for r in rows or []]
        return self._complete(bars, tf, now)[-limit:]

    def trades(self, symbol, limit=500):
        rows = self.http.get_json(f"{self.base}/products/{symbol}/trades", {"limit": min(limit, 1000)})
        recv = now_ms()
        out = []
        for r in rows or []:
            maker = r.get("side")
            out.append(Trade(self.venue, symbol, _parse_iso(r["time"]), float(r["price"]), float(r["size"]),
                             "sell" if maker == "buy" else "buy", str(r["trade_id"]), recv,
                             "coinbase.rest.trades"))
        out.sort(key=lambda t: (t.event_time, t.trade_id))
        return out

    def book(self, symbol, depth=50):
        d = self.http.get_json(f"{self.base}/products/{symbol}/book", {"level": 2})
        if not d:
            return None
        return BookSnapshot(self.venue, symbol, now_ms(),
                            [[float(p), float(s)] for p, s, *_ in d.get("bids", [])[:depth]],
                            [[float(p), float(s)] for p, s, *_ in d.get("asks", [])[:depth]],
                            now_ms(), "coinbase.rest.book.level2", d.get("sequence"))


# ============================================================================ Kraken

_KR_ALIAS = {"XBT": "BTC", "XDG": "DOGE"}


class Kraken(Adapter):
    venue = "kraken"
    base = "https://api.kraken.com/0/public"
    timeframes = {"1m": 1, "5m": 5, "15m": 15, "30m": 30, "1h": 60, "4h": 240, "1d": 1440}

    def _res(self, method, params=None):
        d = self.http.get_json(f"{self.base}/{method}", params)
        if not d or d.get("error"):
            raise HttpError(f"kraken {method}: {d.get('error') if d else 'no response'}")
        return d["result"]

    def instruments(self) -> List[dict]:
        out = []
        for key, p in self._res("AssetPairs").items():
            ws = p.get("wsname") or ""
            if "/" not in ws or p.get("status", "online") != "online":
                continue
            b, q = ws.split("/", 1)
            b, q = _KR_ALIAS.get(b, b), _KR_ALIAS.get(q, q)
            out.append({"venue": self.venue, "symbol": key, "display": f"{b}-{q}", "asset_type": "crypto",
                        "base": b, "quote": q, "tick_size": _f(p.get("tick_size"), 10 ** -int(p.get("pair_decimals", 5))),
                        "lot_size": 10 ** -int(p.get("lot_decimals", 8)), "min_qty": _f(p.get("ordermin")),
                        "min_notional": _f(p.get("costmin")), "can_short": False, "calendar": "CRYPTO-UTC"})
        return out

    def bars(self, symbol, tf, limit=300, end_ms=None):
        now = now_ms()
        res = self._res("OHLC", {"pair": symbol, "interval": self.timeframes[tf]})
        key = next((k for k in res if k != "last"), None)
        recv = now_ms()
        bars = [Bar(self.venue, symbol, tf, int(r[0]) * 1000, float(r[1]), float(r[2]), float(r[3]),
                    float(r[4]), float(r[6]), recv, "kraken.rest.ohlc") for r in (res.get(key) or [])]
        return self._complete(bars, tf, now)[-limit:]

    def trades(self, symbol, limit=500):
        res = self._res("Trades", {"pair": symbol, "count": min(limit, 1000)})
        key = next((k for k in res if k != "last"), None)
        recv = now_ms()
        out = [Trade(self.venue, symbol, int(float(r[2]) * 1000), float(r[0]), float(r[1]),
                     "buy" if r[3] == "b" else "sell", str(r[6]) if len(r) > 6 else f"{r[2]}-{i}",
                     recv, "kraken.rest.trades") for i, r in enumerate(res.get(key) or [])]
        out.sort(key=lambda t: (t.event_time, t.trade_id))
        return out

    def book(self, symbol, depth=50):
        res = self._res("Depth", {"pair": symbol, "count": min(depth, 500)})
        book = next(iter(res.values()), None)
        if not book:
            return None
        return BookSnapshot(self.venue, symbol, now_ms(),
                            [[float(p), float(s)] for p, s, *_ in book.get("bids", [])],
                            [[float(p), float(s)] for p, s, *_ in book.get("asks", [])],
                            now_ms(), "kraken.rest.depth")


# ============================================================================ OKX

class OKX(Adapter):
    venue = "okx"
    base = "https://www.okx.com/api/v5"
    timeframes = {"1m": "1m", "5m": "5m", "15m": "15m", "30m": "30m", "1h": "1H", "4h": "4H", "1d": "1Dutc"}

    def _data(self, path, params=None):
        d = self.http.get_json(f"{self.base}/{path}", params)
        if not d or d.get("code") != "0":
            raise HttpError(f"okx {path}: {d.get('msg') if d else 'no response'}")
        return d.get("data") or []

    def instruments(self, inst_type: str = "SPOT") -> List[dict]:
        out = []
        for p in self._data("public/instruments", {"instType": inst_type}):
            if p.get("state") != "live":
                continue
            out.append({"venue": self.venue, "symbol": p["instId"], "asset_type": "crypto" if inst_type == "SPOT" else "crypto_perp",
                        "base": p.get("baseCcy") or p.get("ctValCcy"), "quote": p.get("quoteCcy") or p.get("settleCcy"),
                        "tick_size": _f(p.get("tickSz")), "lot_size": _f(p.get("lotSz")), "min_qty": _f(p.get("minSz")),
                        "can_short": inst_type == "SWAP", "calendar": "CRYPTO-UTC"})
        return out

    def bars(self, symbol, tf, limit=300, end_ms=None):
        now = now_ms()
        params = {"instId": symbol, "bar": self.timeframes[tf], "limit": str(min(limit, 300))}
        path = "market/candles"
        if end_ms:
            params["after"] = str(end_ms)
            path = "market/history-candles"
        rows = self._data(path, params)
        recv = now_ms()
        bars = []
        for r in rows:
            if len(r) > 8 and r[8] == "0":           # OKX's own "not yet confirmed" flag
                continue
            bars.append(Bar(self.venue, symbol, tf, int(r[0]), float(r[1]), float(r[2]), float(r[3]),
                            float(r[4]), float(r[5]), recv, f"okx.rest.{path.split('/')[1]}"))
        return self._complete(bars, tf, now)[-limit:]

    def trades(self, symbol, limit=500):
        rows = self._data("market/trades", {"instId": symbol, "limit": str(min(limit, 500))})
        recv = now_ms()
        out = [Trade(self.venue, symbol, int(r["ts"]), float(r["px"]), float(r["sz"]), r["side"], str(r["tradeId"]),
                     recv, "okx.rest.trades") for r in rows]
        out.sort(key=lambda t: (t.event_time, t.trade_id))
        return out

    def book(self, symbol, depth=50):
        rows = self._data("market/books", {"instId": symbol, "sz": str(min(depth, 400))})
        if not rows:
            return None
        b = rows[0]
        return BookSnapshot(self.venue, symbol, int(b["ts"]),
                            [[float(x[0]), float(x[1])] for x in b.get("bids", [])],
                            [[float(x[0]), float(x[1])] for x in b.get("asks", [])],
                            now_ms(), "okx.rest.books", int(b.get("seqId", 0) or 0))

    def funding_history(self, swap_id: str, limit: int = 100) -> List[dict]:
        return [{"time": int(r["fundingTime"]), "rate": float(r["fundingRate"]),
                 "realized": float(r.get("realizedRate") or r["fundingRate"])}
                for r in self._data("public/funding-rate-history", {"instId": swap_id, "limit": str(limit)})]

    def open_interest(self, swap_id: str) -> Optional[dict]:
        rows = self._data("public/open-interest", {"instType": "SWAP", "instId": swap_id})
        return {"time": int(rows[0]["ts"]), "oi": float(rows[0]["oi"]), "oi_ccy": float(rows[0]["oiCcy"])} if rows else None


# ============================================================================ Yahoo Finance

class Yahoo(Adapter):
    """US stocks and ETFs, bars only. Regular-session bars unless include_prepost is set."""
    venue = "yahoo"
    base = "https://query1.finance.yahoo.com/v8/finance/chart/"
    timeframes = {"1m": ("1m", "7d"), "5m": ("5m", "60d"), "15m": ("15m", "60d"), "30m": ("30m", "60d"),
                  "1h": ("60m", "730d"), "1d": ("1d", "10y")}

    def instruments(self, symbols: List[str] = None) -> List[dict]:
        out = []
        for s in symbols or []:
            out.append({"venue": self.venue, "symbol": s, "asset_type": "stock", "base": s, "quote": "USD",
                        "tick_size": 0.01, "lot_size": 1.0, "min_qty": 1.0, "can_short": False,
                        "calendar": "XNYS"})
        return out

    def chart(self, symbol: str, tf: str, rng: str = None, period: tuple = None, prepost: bool = False) -> dict:
        interval, default_rng = self.timeframes[tf]
        params = {"interval": interval, "includePrePost": "true" if prepost else "false"}
        if period:
            params["period1"], params["period2"] = int(period[0] / 1000), int(period[1] / 1000)
        else:
            params["range"] = rng or default_rng
        d = self.http.get_json(self.base + symbol, params)
        try:
            return d["chart"]["result"][0]
        except (TypeError, KeyError, IndexError):
            raise HttpError(f"yahoo {symbol}: no chart result") from None

    def bars(self, symbol, tf, limit=300, end_ms=None, rng: str = None, prepost: bool = False):
        now = now_ms()
        res = self.chart(symbol, tf, rng=rng, prepost=prepost)
        recv = now_ms()
        ts = res.get("timestamp") or []
        q = (res.get("indicators") or {}).get("quote", [{}])[0]
        o, h, l, c, v = (q.get(k) or [] for k in ("open", "high", "low", "close", "volume"))
        bars = []
        for i, t in enumerate(ts):
            try:
                row = (o[i], h[i], l[i], c[i])
            except IndexError:
                continue
            if None in row:
                continue
            bars.append(Bar(self.venue, symbol, tf, int(t) * 1000, float(o[i]), float(h[i]), float(l[i]),
                            float(c[i]), float((v[i] if i < len(v) else 0) or 0), recv, "yahoo.chart.v8"))
        if tf == "1d":
            # Yahoo can add a second row for the latest session, stamped with its last trade time (forex at the
            # weekend: Thu 23:00 and Fri 21:29 are both Friday). One bar per local trading day: the session's own
            # time stamp with the newest values, the way the ULTRON councils' training data was built.
            off = int((res.get("meta") or {}).get("gmtoffset") or 0) * 1000
            day: Dict[int, Bar] = {}
            for b in sorted(bars, key=lambda x: x.event_time):
                d = (b.event_time + off) // 86_400_000
                if d in day:
                    b.event_time = day[d].event_time
                day[d] = b
            bars = list(day.values())
        return self._complete(bars, tf, now)[-limit:]

    def trades(self, symbol, limit=500):
        raise HttpError("yahoo: trade prints are not available from free data")

    def book(self, symbol, depth=50):
        raise HttpError("yahoo: quotes and order book are not available from free data")

    def last_price(self, symbol):
        """Latest trade price Yahoo reports for the listing (regular session; delayed for some exchanges)."""
        meta = self.chart(symbol, "1m", rng="1d").get("meta") or {}
        px, t = meta.get("regularMarketPrice"), meta.get("regularMarketTime")
        if not px:
            return None
        return float(px), int(t) * 1000 if t else now_ms(), "yahoo last price"


def _iso(ms: int) -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(ms / 1000))


def _parse_iso(s: str) -> int:
    from datetime import datetime
    s = s.replace("Z", "+00:00")
    if "." in s:
        head, rest = s.split(".", 1)
        frac, tz = rest[:rest.find("+")] if "+" in rest else rest, rest[rest.find("+"):] if "+" in rest else "+00:00"
        s = f"{head}.{frac[:6].ljust(6, '0')}{tz}"
    return int(datetime.fromisoformat(s).timestamp() * 1000)


ADAPTERS = {"coinbase": Coinbase, "kraken": Kraken, "okx": OKX, "yahoo": Yahoo}

from mab.data import demo as _demo  # noqa: E402,F401  (registers the synthetic DEMO venue)
