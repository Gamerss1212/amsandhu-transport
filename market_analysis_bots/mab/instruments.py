"""Instrument registry: every tradable market the platform knows, with its trading rules.

Crypto instruments are discovered from each venue's public product list (Coinbase, Kraken,
OKX spot and perpetual swaps). Stocks and ETFs are open-ended: any Yahoo Finance symbol can be
added (US listings, or Toronto listings with the ".TO" suffix); a symbol is accepted only after
a chart request for it succeeds. The registry is cached to disk and refreshed daily, so start-up
does not depend on every venue being reachable.
"""

from __future__ import annotations

import json
import os
import threading
import time
from typing import Dict, Iterable, List, Optional, Tuple

from mab.costs import tier_for
from mab.data.adapters import ADAPTERS
from mab.net import Http, HttpError

DEFAULT_STOCKS = ["SPY", "QQQ", "IWM", "DIA", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA", "AMD",
                  "NFLX", "JPM", "XOM", "COIN", "MSTR", "PLTR", "SMCI", "AVGO"]
DEFAULT_CA_STOCKS = ["SHOP.TO", "RY.TO", "TD.TO", "ENB.TO", "CNQ.TO", "XIU.TO"]


class InstrumentRegistry:
    def __init__(self, http: Http, cache_path: Optional[str] = None, max_age_s: float = 86_400):
        self.http = http
        self.cache_path = cache_path
        self.max_age_s = max_age_s
        self.items: Dict[Tuple[str, str], dict] = {}
        self.errors: Dict[str, str] = {}
        self.lock = threading.Lock()
        self.loaded_at = 0.0

    # ------------------------------------------------------------------ load
    def load(self, venues: Iterable[str] = ("coinbase", "kraken", "okx"), stocks: Iterable[str] = (),
             refresh: bool = False) -> dict:
        if not refresh and self._load_cache():
            self.add_stocks(stocks, verify=False)
            return self.summary()
        for v in venues:
            try:
                ad = ADAPTERS[v](self.http)
                rows = ad.instruments()
                if v == "okx":
                    rows += ad.instruments("SWAP")
                for r in rows:
                    r["tier"] = tier_for(r["symbol"], r["asset_type"])
                    self.items[(v, r["symbol"])] = r
                self.errors.pop(v, None)
            except (HttpError, KeyError, ValueError) as e:
                self.errors[v] = str(e)
        self.add_stocks(list(stocks), verify=False)
        self.loaded_at = time.time()
        self._save_cache()
        return self.summary()

    def add_stocks(self, symbols: Iterable[str], verify: bool = True) -> List[str]:
        """Add stock/ETF symbols. With verify=True each is fetched once and rejected if unknown."""
        added = []
        yh = ADAPTERS["yahoo"](self.http)
        for s in symbols:
            s = s.strip().upper()
            if not s:
                continue
            if verify:
                try:
                    meta = yh.chart(s, "1d", rng="5d").get("meta", {})
                    if not meta.get("regularMarketPrice"):
                        raise HttpError("no price")
                except HttpError as e:
                    self.errors[f"yahoo:{s}"] = str(e)
                    continue
            ca = s.endswith(".TO") or s.endswith(".V") or s.endswith(".NE")
            row = yh.instruments([s])[0]
            row["asset_type"] = "stock_ca" if ca else "stock"
            row["calendar"] = "XTSE" if ca else "XNYS"
            row["quote"] = "CAD" if ca else "USD"
            row["tier"] = tier_for(s, row["asset_type"])
            self.items[("yahoo", s)] = row
            added.append(s)
        if added:
            self._save_cache()
        return added

    # ------------------------------------------------------------------ query
    def get(self, venue: str, symbol: str) -> Optional[dict]:
        return self.items.get((venue, symbol))

    def require(self, venue: str, symbol: str) -> dict:
        r = self.get(venue, symbol)
        if r is None:
            if venue == "yahoo":
                added = self.add_stocks([symbol], verify=True)
                if added:
                    return self.items[(venue, symbol.upper())]
            raise KeyError(f"unknown instrument {venue}:{symbol}")
        return r

    def search(self, text: str, limit: int = 50) -> List[dict]:
        t = text.upper()
        return [r for (v, s), r in self.items.items() if t in s.upper()][:limit]

    def summary(self) -> dict:
        by: Dict[str, int] = {}
        for (v, _), r in self.items.items():
            k = f"{v}:{r['asset_type']}"
            by[k] = by.get(k, 0) + 1
        return {"total": len(self.items), "by_venue": by, "errors": dict(self.errors)}

    # ------------------------------------------------------------------ cache
    def _load_cache(self) -> bool:
        if not self.cache_path or not os.path.exists(self.cache_path):
            return False
        try:
            with open(self.cache_path, "r", encoding="utf-8") as fh:
                d = json.load(fh)
            if time.time() - d.get("saved_at", 0) > self.max_age_s:
                return False
            self.items = {(r["venue"], r["symbol"]): r for r in d["items"]}
            self.loaded_at = d["saved_at"]
            return True
        except (OSError, ValueError, KeyError):
            return False

    def _save_cache(self):
        if not self.cache_path:
            return
        os.makedirs(os.path.dirname(os.path.abspath(self.cache_path)), exist_ok=True)
        tmp = self.cache_path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump({"saved_at": time.time(), "items": list(self.items.values())}, fh)
        os.replace(tmp, self.cache_path)
