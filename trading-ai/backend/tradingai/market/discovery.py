"""Market discovery and the coverage inventory (owner's specification, revision 13, sections 3 and 5B).

"All markets" is a coverage objective with a measured denominator, never a claim:

* Listings come from the connected public providers only: Coinbase Exchange (every product) and Kraken (every asset
  pair). They are refreshed once a day; a pair that disappears is kept and marked delisted, never silently dropped.
* One shared snapshot of every listed pair's last price and 24-hour volume is taken once a minute from each venue's
  all-markets endpoint (one request per venue, not one per agent). Freshness is the time this software RECEIVED the
  snapshot; those endpoints do not report a per-pair event time.
* Execution eligibility here means paper trading with this software's Coinbase candle feed: online Coinbase USD
  pairs that are not trading-disabled, cancel-only or in auction. Kraken pairs are monitored, not traded.
* Stocks: no exchange listing feed is connected, so the stock inventory is the curated list; every other stock,
  exchange, option, bond and on-chain market is listed as UNCOVERED with the reason.
* Meme coins: a small seed list of well-known centralized-exchange meme assets is tagged by theme. Tags are an
  unverified classification aid (a ticker is not an identity): source "seed list v1", confidence "low". No chain,
  launchpad or DEX is covered (no chain adapter).
"""

from __future__ import annotations

import threading
import time
from decimal import Decimal
from typing import TYPE_CHECKING, Optional

from tradingai.storage.db import dumps, now_ms

if TYPE_CHECKING:
    from tradingai.app import App

COINBASE_PRODUCTS = "https://api.exchange.coinbase.com/products"
COINBASE_STATS = "https://api.exchange.coinbase.com/products/stats"
KRAKEN_PAIRS = "https://api.kraken.com/0/public/AssetPairs"
KRAKEN_TICKER = "https://api.kraken.com/0/public/Ticker"
SNAPSHOT_SECONDS = 60
LISTING_SECONDS = 24 * 3600

# base asset -> themes. A classification aid only: the same ticker can name different tokens on other chains.
MEME_SEED: dict[str, tuple[str, ...]] = {
    "DOGE": ("animal", "internet-culture"), "SHIB": ("animal",), "PEPE": ("character", "internet-culture"),
    "BONK": ("animal", "community"), "WIF": ("animal", "internet-culture"), "FLOKI": ("animal", "celebrity"),
    "MOG": ("internet-culture",), "POPCAT": ("animal", "internet-culture"), "TURBO": ("AI-themed",),
    "BRETT": ("character",), "PENGU": ("animal", "community"), "TRUMP": ("political", "celebrity"),
    "FARTCOIN": ("joke",), "MEW": ("animal",), "PNUT": ("animal", "event-driven"), "MOODENG": ("animal",),
    "GIGA": ("internet-culture",), "SPX": ("parody",), "BOME": ("internet-culture",), "DOG": ("animal",),
}
KRAKEN_ALIASES = {"XDG": "DOGE", "XXDG": "DOGE"}             # Kraken's own asset codes for the same coins
UNCOVERED = [
    ("Stocks beyond the curated list", "no exchange listing or licensed stock feed is connected"),
    ("Options, bonds, credit, rates, swaps", "no data or order adapter for these products"),
    ("Solana, Ethereum, Base, BNB Chain, Arbitrum, Polygon, Avalanche tokens and pools",
     "no chain adapter: on-chain discovery, pool liquidity and DEX routes are not observable"),
    ("Launchpads and bonding curves", "no launchpad adapter"),
    ("Other centralized exchanges", "only Coinbase and Kraken public endpoints are connected"),
]


def _d(x) -> Optional[Decimal]:
    try:
        return Decimal(str(x))
    except Exception:                                         # noqa: BLE001 - a bad field is "unknown", not zero
        return None


class Discovery:
    def __init__(self, app: "App"):
        self.app = app
        self.snap: dict[str, dict] = {}                       # "VENUE:symbol" -> latest snapshot row
        self.version = 0                                      # the shared market-state version
        self.received: dict[str, Optional[int]] = {"COINBASE": None, "KRAKEN": None}
        self.errors: dict[str, str] = {}
        self._thread: Optional[threading.Thread] = None
        self._stop = threading.Event()
        self._lock = threading.Lock()

    # ------------------------------------------------------------------ listings
    def refresh_listings(self) -> dict:
        http, db, t = self.app.md.http, self.app.db, now_ms()
        rows: list[tuple] = []
        try:
            for p in http.get_json(COINBASE_PRODUCTS):
                ok = p.get("status") == "online" and not p.get("trading_disabled") and not p.get("cancel_only") \
                    and not p.get("auction_mode")
                status = "online" if ok else ("disabled" if p.get("status") == "online" else (p.get("status") or
                                                                                               "unknown"))
                rows.append(("COINBASE", p["id"], p.get("base_currency"), p.get("quote_currency"), "spot", status,
                             {"quote_increment": p.get("quote_increment"), "base_increment": p.get("base_increment"),
                              "min_market_funds": p.get("min_market_funds"), "trading_disabled":
                              p.get("trading_disabled"), "fx_stablecoin": p.get("fx_stablecoin")}))
            self.errors.pop("COINBASE listings", None)
        except Exception as e:                                # noqa: BLE001 - a venue outage is visible, not fatal
            self.errors["COINBASE listings"] = f"{type(e).__name__}: {e}"
        try:
            res = http.get_json(KRAKEN_PAIRS).get("result") or {}
            for key, p in res.items():
                rows.append(("KRAKEN", key, p.get("base"), p.get("quote"), "spot", p.get("status") or "unknown",
                             {"altname": p.get("altname"), "wsname": p.get("wsname")}))
            self.errors.pop("KRAKEN listings", None)
        except Exception as e:                                # noqa: BLE001
            self.errors["KRAKEN listings"] = f"{type(e).__name__}: {e}"
        venues = {r[0] for r in rows}
        with db._lock:
            for v, sym, base, quote, kind, status, meta in rows:
                db.execute("INSERT INTO instruments_discovered (venue, symbol, base, quote, kind, status, first_seen, "
                           "last_seen, delisted, meta) VALUES (?,?,?,?,?,?,?,?,NULL,?) ON CONFLICT(venue, symbol) DO "
                           "UPDATE SET base=excluded.base, quote=excluded.quote, status=excluded.status, last_seen="
                           "excluded.last_seen, delisted=NULL, meta=excluded.meta",
                           (v, sym, base, quote, kind, status, t, t, dumps(meta)))
            for v in venues:                                  # listed before, missing now: delisted, kept
                db.execute("UPDATE instruments_discovered SET status='delisted', delisted=? WHERE venue=? AND "
                           "last_seen<? AND delisted IS NULL", (t, v, t))
        self.app.db.set_setting("discovery.listed_at", t)
        out = {v: sum(1 for r in rows if r[0] == v) for v in ("COINBASE", "KRAKEN")}
        self.app.audit("discovery", f"listings refreshed: {out}", data={"errors": self.errors})
        return out

    # ------------------------------------------------------------------ the shared snapshot
    def snapshot(self) -> int:
        http, t = self.app.md.http, now_ms()
        new: dict[str, dict] = {}
        try:
            for sym, s in http.get_json(COINBASE_STATS).items():
                d = s.get("stats_24hour") or {}
                new[f"COINBASE:{sym}"] = {"last": _d(d.get("last")), "open": _d(d.get("open")),
                                          "volume": _d(d.get("volume")), "received": t}
            self.received["COINBASE"] = t
            self.errors.pop("COINBASE snapshot", None)
        except Exception as e:                                # noqa: BLE001
            self.errors["COINBASE snapshot"] = f"{type(e).__name__}: {e}"
        try:
            for sym, s in (http.get_json(KRAKEN_TICKER).get("result") or {}).items():
                new[f"KRAKEN:{sym}"] = {"last": _d((s.get("c") or [None])[0]), "open": _d(s.get("o")),
                                        "volume": _d((s.get("v") or [None, None])[1]), "received": t}
            self.received["KRAKEN"] = t
            self.errors.pop("KRAKEN snapshot", None)
        except Exception as e:                                # noqa: BLE001
            self.errors["KRAKEN snapshot"] = f"{type(e).__name__}: {e}"
        with self._lock:
            self.snap.update(new)
            if new:
                self.version += 1
        if new:
            self.app.bus.publish("market.snapshot", {"version": self.version, "pairs": len(new),
                                                     "errors": dict(self.errors)})
        return len(new)

    def quote(self, venue_symbol: str) -> Optional[dict]:
        with self._lock:
            return self.snap.get(venue_symbol)

    def fresh(self, row: Optional[dict]) -> bool:
        return bool(row and row.get("last") and now_ms() - row["received"] <= 2.5 * SNAPSHOT_SECONDS * 1000)

    # ------------------------------------------------------------------ inventory
    def listed(self, venue: Optional[str] = None) -> list[dict]:
        sql, args = "SELECT * FROM instruments_discovered", ()
        if venue:
            sql, args = sql + " WHERE venue=?", (venue,)
        return self.app.db.query(sql, args)

    @staticmethod
    def execution_eligible(row: dict) -> bool:
        return row["venue"] == "COINBASE" and row["quote"] == "USD" and row["status"] == "online"

    def usd_volume(self, row: dict) -> float:
        q = self.quote(f"{row['venue']}:{row['symbol']}")
        if not q or not q.get("last") or not q.get("volume"):
            return 0.0
        return float(q["last"] * q["volume"])

    def tradable_crypto(self, limit: int) -> list[dict]:
        """Execution-eligible pairs, most liquid first (24-hour USD volume from the shared snapshot)."""
        rows = [r for r in self.listed("COINBASE") if self.execution_eligible(r)]
        rows.sort(key=lambda r: -self.usd_volume(r))
        return rows[:limit]

    def ensure_instrument(self, row: dict) -> str:
        """Register a discovered Coinbase pair in the instrument book (paper trading uses Coinbase candles)."""
        from tradingai.market.instruments import Instrument, MarketType
        from tradingai.market.universe import DataSource
        iid = f"COINBASE:{row['symbol']}"
        if iid not in self.app.book:
            import json
            meta = json.loads(row["meta"] or "{}")
            step = Decimal(str(meta.get("base_increment") or "0.00000001"))
            self.app.book.add(Instrument(iid, MarketType.CRYPTO_SPOT, row["symbol"], "COINBASE", row["quote"],
                                         tick_size=Decimal(str(meta.get("quote_increment") or "0.01")),
                                         quantity_step=step, min_quantity=step, base_asset=row["base"],
                                         quote_asset=row["quote"], calendar="CRYPTO", data_source="coinbase",
                                         exchange="COINBASE", tags=("discovered",)))
            self.app.sources[iid] = DataSource("coinbase", row["symbol"], "public exchange candles (discovered)")
        return iid

    def meme_tags(self, base: Optional[str]) -> Optional[dict]:
        b = (base or "").upper()
        themes = MEME_SEED.get(KRAKEN_ALIASES.get(b, b))
        if not themes:
            return None
        return {"themes": list(themes), "source": "seed list v1 (this software)", "confidence": "low (unverified: a "
                "ticker is not an identity)"}

    def coverage(self) -> dict:
        rows = self.listed()
        venues = {}
        for v in ("COINBASE", "KRAKEN"):
            vr = [r for r in rows if r["venue"] == v]
            live = [r for r in vr if r["status"] != "delisted"]
            fresh = [r for r in live if self.fresh(self.quote(f"{v}:{r['symbol']}"))]
            venues[v] = {"known": len(vr), "listed": len(live), "online": sum(1 for r in live if r["status"] == "online"),
                         "delisted": len(vr) - len(live), "snapshot_fresh": len(fresh),
                         "stale_or_missing": len(live) - len(fresh),
                         "execution_eligible": sum(1 for r in live if self.execution_eligible(r)),
                         "received": self.received.get(v)}
        memes = []
        for r in rows:
            tag = self.meme_tags(r["base"])
            if tag and r["status"] != "delisted":
                q = self.quote(f"{r['venue']}:{r['symbol']}")
                memes.append({"venue": r["venue"], "symbol": r["symbol"], "base": r["base"], "quote": r["quote"],
                              **tag, "fresh": self.fresh(q), "last": None if not q or q["last"] is None else
                              str(q["last"]), "execution_eligible": self.execution_eligible(r)})
        book = self.app.book
        curated = [i for i in self.app.sources if self.app.sources[i].provider != "demo"]
        return {"version": self.version, "listed_at": self.app.db.get_setting("discovery.listed_at"),
                "venues": venues, "errors": dict(self.errors), "offline": self.app.offline,
                "curated": {"instruments": len(curated), "in_book": len(book)},
                "meme": {"tagged_pairs": len(memes), "pairs": sorted(memes, key=lambda m: (m["base"], m["venue"])),
                         "note": "Tags come from a small seed list and are unverified; only centralized-exchange "
                                 "listings are covered (no chain, DEX or launchpad adapter)."},
                "uncovered": [{"market": m, "reason": r} for m, r in UNCOVERED],
                "denominator": "pairs listed by the connected public providers (Coinbase, Kraken); this is not "
                               "every market on Earth"}

    # ------------------------------------------------------------------ background service
    def start(self) -> None:
        if self.app.offline or self._thread is not None:
            return
        self._thread = threading.Thread(target=self._run, name="discovery", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()

    def _run(self) -> None:
        last_listing = self.app.db.get_setting("discovery.listed_at") or 0
        while not self._stop.is_set():
            try:
                if now_ms() - last_listing > LISTING_SECONDS * 1000 or not self.listed():
                    self.refresh_listings()
                    last_listing = now_ms()
                self.snapshot()
                fleet = getattr(self.app, "fleet", None)
                if fleet is not None:
                    fleet.assign()
            except Exception as e:                            # noqa: BLE001 - the service survives and reports
                self.errors["service"] = f"{type(e).__name__}: {e}"
            self._stop.wait(SNAPSHOT_SECONDS)

    def status(self) -> str:
        if self.app.offline:
            return "offline mode: discovery off"
        return f"market-state version {self.version}; " + ", ".join(
            f"{v} {time.strftime('%H:%M:%S', time.gmtime(t / 1000)) if t else 'not yet'}"
            for v, t in self.received.items())
