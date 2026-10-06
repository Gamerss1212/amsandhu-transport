"""A01 data sources: free daily bars for stocks/ETFs and crypto (spec sections 57, 58, 74).

Network code lives only in this package (Phase 1 rule). Each source is two parts:
- a pure parser (``parse_yahoo_chart``, ``parse_ccxt_ohlcv``) that tests feed with recorded files;
- a thin fetcher (``fetch_yahoo``, ``fetch_ccxt``) that does the download.

Every source carries a ``SourceInfo`` record (spec section 74): point-in-time status,
survivorship coverage, adjustment method, timestamp convention and licence. Neither free source is
survivorship-free, so results built on them are labelled "upper bound only" (spec section 58).
Only completed daily bars are kept: a bar for a day that has not closed yet is dropped.
"""

from __future__ import annotations

import csv
import json
import math
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from quantagents.market import FloatArray, as_readonly

SURVIVORSHIP_LABEL = "survivorship-biased: upper bound only"
YAHOO_URL = "https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
USER_AGENT = "Mozilla/5.0 (quantagents research; daily bars)"
US_SESSION_CLOSE = time(16, 15)  # a daily stock bar counts as complete 15 minutes after the close


@dataclass(frozen=True)
class SourceInfo:
    """What a data source does and does not promise (spec section 74)."""

    name: str
    point_in_time: bool
    survivorship_free: bool
    adjustment: str
    timestamps: str
    licence: str

    @property
    def label(self) -> str:
        """The caveat every result built on this source must carry."""
        notes = [] if self.survivorship_free else [SURVIVORSHIP_LABEL]
        if not self.point_in_time:
            notes.append("not point-in-time (history may be restated)")
        return "; ".join(notes) or "point-in-time, survivorship-free"


YAHOO_INFO = SourceInfo(
    name="yahoo_chart_v8",
    point_in_time=False,
    survivorship_free=False,
    adjustment="open/high/low/close split-adjusted; adj_close split- and dividend-adjusted",
    timestamps="exchange-local trading date",
    licence="unofficial public endpoint; research use only",
)


def ccxt_symbol(exchange_id: str, pair: str) -> str:
    """How a crypto pair from an exchange is named in the store: ``BTC/USD`` on kraken is
    ``BTC-USD.KRAKEN``. The exchange tag keeps it apart from Yahoo's ``BTC-USD`` (a different
    source with different prices), so the store never switches sources silently."""
    return f"{pair.replace('/', '-').upper()}.{exchange_id.upper()}"


CCXT_EXCHANGES = frozenset(
    {
        "binance", "binanceus", "bitfinex", "bitstamp", "bybit", "coinbase",
        "coinbaseexchange", "cryptocom", "gemini", "kraken", "kucoin", "ndax", "okx",
    }
)  # fmt: skip


def split_universe(symbols: Sequence[str]) -> tuple[list[str], list[str]]:
    """Which download each universe symbol needs: (Yahoo symbols, CCXT ``exchange:PAIR`` specs).

    ``BTC-USD.KRAKEN`` is a CCXT pair (see ``ccxt_symbol``); everything else, including
    Yahoo's own ``BTC-USD`` and Toronto listings such as ``XIC.TO``, comes from Yahoo.
    """
    yahoo: list[str] = []
    ccxt: list[str] = []
    for symbol in symbols:
        stem, _, tag = symbol.rpartition(".")
        if stem and tag.lower() in CCXT_EXCHANGES and "-" in stem:
            base, _, quote = stem.partition("-")
            ccxt.append(f"{tag.lower()}:{base}/{quote}")
        else:
            yahoo.append(symbol)
    return yahoo, ccxt


def ccxt_info(exchange_id: str) -> SourceInfo:
    return SourceInfo(
        name=f"ccxt:{exchange_id}",
        point_in_time=False,
        survivorship_free=False,
        adjustment="none (spot crypto has no splits or dividends)",
        timestamps="UTC calendar day (candle open 00:00 UTC)",
        licence=f"{exchange_id} public market-data API terms",
    )


@dataclass(frozen=True)
class RawDaily:
    """One symbol's daily bars as the source gave them, plus dividends and splits by date."""

    symbol: str
    dates: tuple[date, ...]
    open: FloatArray
    high: FloatArray
    low: FloatArray
    close: FloatArray
    adj_close: FloatArray
    volume: FloatArray
    dividends: Mapping[date, float] = field(default_factory=dict)
    splits: Mapping[date, float] = field(default_factory=dict)

    def __post_init__(self) -> None:
        n = len(self.dates)
        arrays = (self.open, self.high, self.low, self.close, self.adj_close, self.volume)
        if any(len(a) != n for a in arrays):
            raise ValueError(f"{self.symbol}: arrays and dates differ in length")
        if any(b <= a for a, b in zip(self.dates, self.dates[1:], strict=False)):
            raise ValueError(f"{self.symbol}: dates must be strictly increasing")

    def __len__(self) -> int:
        return len(self.dates)


def _num(x: Any) -> float:
    return float(x) if x is not None else math.nan


def parse_yahoo_chart(
    payload: Mapping[str, Any], symbol: str, *, now: datetime | None = None
) -> RawDaily:
    """Turn a Yahoo v8 chart response into RawDaily.

    Rows with a missing open/high/low/close are dropped (Yahoo pads holidays that way). The
    bar for today (exchange-local) is dropped until the session has closed.
    """
    try:
        res = payload["chart"]["result"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(f"{symbol}: not a Yahoo chart response") from exc
    offset = timedelta(seconds=int(res.get("meta", {}).get("gmtoffset") or 0))
    stamps = res.get("timestamp") or []
    quote = (res.get("indicators", {}).get("quote") or [{}])[0]
    adj = ((res.get("indicators", {}).get("adjclose") or [{}])[0]).get("adjclose") or []
    now_local = (now or datetime.now(UTC)) + offset
    # crypto trades around the clock: its daily bar is only final once the UTC day is over
    always_open = res.get("meta", {}).get("instrumentType") == "CRYPTOCURRENCY"
    cols = {f: list(quote.get(f) or []) for f in ("open", "high", "low", "close", "volume")}
    rows: dict[date, tuple[float, ...]] = {}
    for k, ts in enumerate(stamps):
        day = (datetime.fromtimestamp(int(ts), UTC) + offset).date()
        values = tuple(_num(c[k]) if k < len(c) else math.nan for c in cols.values())
        adj_close = _num(adj[k]) if k < len(adj) else values[3]
        if any(math.isnan(v) for v in values[:4]):
            continue
        if day == now_local.date() and (always_open or now_local.time() < US_SESSION_CLOSE):
            continue  # today's bar is still forming
        if day > now_local.date():
            continue
        rows[day] = (*values[:4], adj_close, 0.0 if math.isnan(values[4]) else values[4])
    events = res.get("events") or {}
    dividends = {
        (datetime.fromtimestamp(int(e["date"]), UTC) + offset).date(): float(e["amount"])
        for e in (events.get("dividends") or {}).values()
    }
    splits = {
        (datetime.fromtimestamp(int(e["date"]), UTC) + offset).date(): float(e["numerator"])
        / float(e["denominator"])
        for e in (events.get("splits") or {}).values()
    }
    return _raw(symbol, rows, dividends, splits)


def _raw(
    symbol: str,
    rows: Mapping[date, Sequence[float]],
    dividends: Mapping[date, float] | None = None,
    splits: Mapping[date, float] | None = None,
) -> RawDaily:
    days = sorted(rows)
    table = np.array([rows[d] for d in days], dtype=np.float64).reshape(len(days), 6)
    return RawDaily(
        symbol=symbol,
        dates=tuple(days),
        open=as_readonly(table[:, 0]),
        high=as_readonly(table[:, 1]),
        low=as_readonly(table[:, 2]),
        close=as_readonly(table[:, 3]),
        adj_close=as_readonly(table[:, 4]),
        volume=as_readonly(table[:, 5]),
        dividends={d: v for d, v in (dividends or {}).items() if d in rows},
        splits={d: v for d, v in (splits or {}).items() if d in rows},
    )


def parse_ccxt_ohlcv(
    rows: Sequence[Sequence[float]], symbol: str, *, now: datetime | None = None
) -> RawDaily:
    """CCXT daily candles ``[ms, open, high, low, close, volume]`` -> RawDaily (UTC days).

    The candle for the current UTC day is dropped: it is not finished. Duplicate days keep the
    last copy (exchanges sometimes repeat the newest candle across pages).
    """
    today = (now or datetime.now(UTC)).date()
    out: dict[date, tuple[float, ...]] = {}
    for r in rows:
        day = datetime.fromtimestamp(float(r[0]) / 1000.0, UTC).date()
        if day >= today:
            continue
        o, h, lo, c, v = (float(x) for x in r[1:6])
        out[day] = (o, h, lo, c, c, v)
    return _raw(symbol, out)


CSV_COLUMNS = ("date", "symbol", "open", "high", "low", "close", "volume")
CSV_OPTIONAL = ("adj_close", "dividend", "split")


def csv_info(path: Path | str, *, adjusted: bool) -> SourceInfo:
    """Provenance for a CSV the owner downloaded: we cannot know more than the owner tells us."""
    return SourceInfo(
        name=f"csv:{Path(path).name}",
        point_in_time=False,
        survivorship_free=False,
        adjustment="adj_close column from the file"
        if adjusted
        else "as in the file (no adj_close column: check splits and dividends yourself)",
        timestamps="trading date as written in the file",
        licence="the owner's download; check the provider's terms",
    )


def read_long_csv(path: Path | str) -> tuple[dict[str, RawDaily], bool]:
    """Read ``date,symbol,open,high,low,close,volume`` (+ optional ``adj_close,dividend,split``).

    Returns one RawDaily per symbol and whether the file had an ``adj_close`` column. Without it,
    adj_close = close (the store then cannot add dividends back; A02 still flags split jumps).
    """
    per_symbol: dict[str, dict[date, tuple[float, ...]]] = {}
    divs: dict[str, dict[date, float]] = {}
    splits: dict[str, dict[date, float]] = {}
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        names = set(reader.fieldnames or ())
        missing = set(CSV_COLUMNS) - names
        if missing:
            raise ValueError(f"{path}: missing columns {sorted(missing)}")
        has_adj = "adj_close" in names
        for line_no, row in enumerate(reader, start=2):
            try:
                day = date.fromisoformat(row["date"].strip())
                o, h, lo, c, v = (float(row[f]) for f in CSV_COLUMNS[2:])
                adj = float(row["adj_close"]) if has_adj and row["adj_close"].strip() else c
                div = float(row.get("dividend") or 0.0)
                split = float(row.get("split") or 1.0)
            except ValueError as exc:
                raise ValueError(f"{path}:{line_no}: {exc}") from exc
            symbol = row["symbol"].strip()
            rows = per_symbol.setdefault(symbol, {})
            if day in rows:
                raise ValueError(f"{path}:{line_no}: duplicate row for {symbol} {day}")
            rows[day] = (o, h, lo, c, adj, v)
            if div:
                divs.setdefault(symbol, {})[day] = div
            if split != 1.0:
                splits.setdefault(symbol, {})[day] = split
    if not per_symbol:
        raise ValueError(f"{path}: no data rows")
    raws = {s: _raw(s, rows, divs.get(s), splits.get(s)) for s, rows in sorted(per_symbol.items())}
    return raws, has_adj


Opener = Callable[[urllib.request.Request], Any]


def _default_open(req: urllib.request.Request) -> Any:
    return urllib.request.urlopen(req, timeout=30)  # fixed https host (YAHOO_URL)


def fetch_yahoo(
    symbol: str, start: date, end: date, *, opener: Opener | None = None
) -> RawDaily:  # pragma: no cover - network; the parser is tested with recorded files
    """Download daily bars, dividends and splits for one stock or ETF (free, no key)."""
    p1 = int(datetime.combine(start, time(0), UTC).timestamp())
    p2 = int(datetime.combine(end + timedelta(days=1), time(0), UTC).timestamp())
    query = urllib.parse.urlencode(
        {
            "period1": p1,
            "period2": p2,
            "interval": "1d",
            "events": "div,split",
            "includeAdjustedClose": "true",
        }
    )
    url = YAHOO_URL.format(symbol=urllib.parse.quote(symbol)) + "?" + query
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with (opener or _default_open)(req) as resp:
        payload = json.load(resp)
    return parse_yahoo_chart(payload, symbol)


def fetch_ccxt(
    exchange_id: str, pair: str, start: date, end: date, *, client: Any = None
) -> RawDaily:  # pragma: no cover - network; the parser is tested with recorded files
    """Download daily candles for one crypto pair through CCXT public endpoints (no API key).

    Pages forward from ``start``. The exchange client trusts the system's proxy and CA settings.
    """
    if client is None:
        import ccxt  # optional [data] extra

        client = getattr(ccxt, exchange_id)({"requests_trust_env": True, "enableRateLimit": True})
    since = int(datetime.combine(start, time(0), UTC).timestamp() * 1000)
    stop = int(datetime.combine(end + timedelta(days=1), time(0), UTC).timestamp() * 1000)
    rows: list[list[float]] = []
    while since < stop:
        page = client.fetch_ohlcv(pair, "1d", since=since, limit=300)
        if not page:
            break
        rows.extend(r for r in page if r[0] < stop)
        nxt = int(page[-1][0]) + 86_400_000
        if nxt <= since:
            break
        since = nxt
    return parse_ccxt_ohlcv(rows, ccxt_symbol(exchange_id, pair))
