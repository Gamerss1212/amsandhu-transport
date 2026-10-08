"""Market data service: one call returns quality-checked, completed bars for any instrument and timeframe.

    md.bars("COINBASE:BTC-USD", "5m", lookback=500) -> (Bars, status)

1. Read what is stored (Parquet via DuckDB).
2. If the newest stored bar is older than one bar, fetch only the missing range from the instrument's provider
   (incremental update; identical periods are never downloaded twice).
3. Check quality, store, and remember provenance.
4. Offline or the provider failing: serve what is stored and say so (`status["fresh"] = False`, the reason given).
   Nothing is ever filled in or invented.

Timeframes a provider lacks (Coinbase has no 30m or 4h) are resampled from a finer stored timeframe, completed bars
only.
"""

from __future__ import annotations

import threading
import time
from typing import Optional

from tradingai.core.logs import get
from tradingai.data import quality
from tradingai.data.bars import TF_MS, Bars, resample
from tradingai.data.net import Http
from tradingai.data.providers.coinbase import Coinbase
from tradingai.data.providers.demo import Demo
from tradingai.data.providers.kraken import Kraken
from tradingai.data.providers.yahoo import Yahoo
from tradingai.market.instruments import InstrumentBook
from tradingai.market.universe import DataSource
from tradingai.storage.marketstore import MarketStore

log = get("data")
RESAMPLE_FROM = {"30m": "15m", "4h": "1h", "1h": "15m"}
DEFAULT_HISTORY_BARS = 1500


class MarketData:
    def __init__(self, store: MarketStore, book: InstrumentBook, sources: dict[str, DataSource],
                 http: Optional[Http] = None, offline: bool = False):
        self.store, self.book, self.sources = store, book, sources
        self.http = http or Http(min_interval={"query1.finance.yahoo.com": 0.35, "api.kraken.com": 1.0,
                                               "api.exchange.coinbase.com": 0.15})
        self.providers = {"coinbase": Coinbase(self.http), "kraken": Kraken(self.http), "yahoo": Yahoo(self.http),
                          "demo": Demo()}
        self.offline = offline
        self._locks: dict[tuple[str, str], threading.Lock] = {}
        self._mem: dict[tuple[str, str], tuple[float, Bars, dict, int]] = {}    # (time, bars, status, history)
        self._backfilled: set[tuple] = set()
        self.status_by_series: dict[str, dict] = {}

    def _lock(self, key: tuple[str, str]) -> threading.Lock:
        return self._locks.setdefault(key, threading.Lock())

    def bars(self, instrument_id: str, tf: str, lookback: int = 500, *, refresh: bool = True,
             max_age_s: float = 5.0) -> tuple[Bars, dict]:
        inst = self.book.get(instrument_id)
        src = self.sources[instrument_id]
        prov = self.providers[src.provider]
        key = (instrument_id, tf)
        with self._lock(key):
            cached = self._mem.get(key)
            if cached and time.time() - cached[0] < max_age_s and cached[3] >= lookback:
                b, st = cached[1], cached[2]
                return b.slice(max(0, len(b) - lookback), len(b)), st
            native = tf in prov.timeframes
            if not native:
                base_tf = RESAMPLE_FROM.get(tf)
                if base_tf is None or base_tf not in prov.timeframes:
                    raise ValueError(f"{src.provider} has no {tf} data for {instrument_id}")
                need = lookback * (TF_MS[tf] // TF_MS[base_tf]) + 2
                base, st = self.bars(instrument_id, base_tf, need, refresh=refresh, max_age_s=max_age_s)
                b = resample(base, tf, int(time.time() * 1000))
                st = dict(st, resampled_from=base_tf)
            else:
                b, st = self._native(inst.calendar or "CRYPTO", src, instrument_id, tf, lookback, refresh)
            self._mem[key] = (time.time(), b, st, max(lookback, DEFAULT_HISTORY_BARS))
            self.status_by_series[f"{instrument_id}|{tf}"] = st
            return b.slice(max(0, len(b) - lookback), len(b)), st

    def _native(self, calendar: str, src: DataSource, instrument_id: str, tf: str, lookback: int,
                refresh: bool) -> tuple[Bars, dict]:
        prov = self.providers[src.provider]
        now = int(time.time() * 1000)
        step = TF_MS[tf]
        want_from = now - (max(lookback, DEFAULT_HISTORY_BARS) + 5) * step * (3 if calendar in ("XNYS", "CME") else 1)
        status: dict = {"provider": src.provider, "symbol": src.symbol, "simulated": prov.simulated,
                        "note": src.note, "fresh": True, "error": None}
        if prov.simulated:                               # DEMO is generated, not stored
            b = prov.fetch(instrument_id, src.symbol, tf, want_from)
        else:
            last = self.store.last_ts(src.provider, src.symbol, tf)
            first = self.store.first_ts(src.provider, src.symbol, tf)
            bf = (src.provider, src.symbol, tf, want_from // (step * 100))
            if refresh and not self.offline and first is not None and first > want_from + 2 * step and \
                    bf not in self._backfilled:
                self._backfilled.add(bf)                 # older history asked for: one attempt per window
                try:
                    older = prov.fetch(instrument_id, src.symbol, tf, want_from)
                    if len(older):
                        self.store.write(src.provider, src.symbol, older,
                                         transforms="adjusted (Yahoo adjclose)" if older.meta.get("adjusted") else "")
                except Exception as e:                   # noqa: BLE001
                    log.warning(f"history backfill failed for {instrument_id} {tf}: {e}")
            if refresh and not self.offline and (last is None or last + 2 * step <= now):
                start = want_from if last is None else last
                try:
                    fresh = prov.fetch(instrument_id, src.symbol, tf, start)
                    if len(fresh):
                        self.store.write(src.provider, src.symbol, fresh,
                                         transforms="adjusted (Yahoo adjclose)" if fresh.meta.get("adjusted") else "")
                except Exception as e:                   # noqa: BLE001 - reported, never hidden
                    status.update(fresh=False, error=f"{type(e).__name__}: {e}")
                    log.warning(f"data refresh failed for {instrument_id} {tf}: {e}")
            elif self.offline:
                status.update(fresh=False, error="offline mode: serving stored data only")
            b = self.store.read(instrument_id, src.provider, src.symbol, tf, start_ms=want_from)
        b, rep = quality.check(b, continuous=calendar in ("CRYPTO",))
        status["quality"] = rep.as_dict()
        if rep.stale:
            status["fresh"] = False
        b.simulated = prov.simulated
        return b, status

    def last_price(self, instrument_id: str, tf: str = "1m") -> tuple[Optional[float], Optional[int], dict]:
        """The latest completed bar's close and when it closed. Never a guessed price."""
        tf = tf if tf in self.providers[self.sources[instrument_id].provider].timeframes else "1d"
        b, st = self.bars(instrument_id, tf, lookback=2)
        if not len(b):
            return None, None, st
        return float(b.close[-1]), int(b.available_at[-1]), st
