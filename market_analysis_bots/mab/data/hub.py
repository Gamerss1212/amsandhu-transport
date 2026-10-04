"""Shared market-data ingestion.

Bots never fetch data. They subscribe to series keyed by (venue, instrument, timeframe); the hub
keeps ONE buffer per key however many bots use it, polls it once per new bar, and hands every
subscriber the same immutable Frame. With 250 bots on 40 distinct series the venues see 40
requests per bar interval, not 250.

Scheduling: a series is polled when its next bar should have completed (last bar open + 2
bar lengths + a short publication delay). If the bar is not there yet it is retried with
growing gaps; the data-quality layer marks the series stale once it is overdue.

Backpressure: one fetch per series can be in flight; due series wait in a bounded queue served
by a fixed worker pool. A series that is already queued is not queued twice (coalescing), and
deferrals are counted.

Recovery: each poll asks for enough bars to cover the time since the last bar held, so gaps
from outages or restarts are refilled; bars the venue revises are replaced (counted).

Order flow: for crypto series whose subscribers need it, recent trade prints are polled and
bucketed per bar by aggressor side, and an order-book snapshot is taken as each bar closes.
Coverage is tracked: when trade ids show missed prints, the affected bars get no order-flow
values (never estimates).
"""

from __future__ import annotations

import logging
import queue
import threading
import time
from typing import Callable, Dict, List, Optional, Set, Tuple

from mab.clock import calendar_for, is_equity, tf_ms
from mab.data.adapters import ADAPTERS, Adapter
from mab.data.quality import SeriesQuality
from mab.frame import Frame
from mab.models import Bar, now_ms
from mab.net import Http, HttpError

log = logging.getLogger("mab.hub")
Key = Tuple[str, str, str]

PUBLISH_DELAY_MS = {"coinbase": 3_000, "kraken": 4_000, "okx": 2_000, "yahoo": 6_000}
KRAKEN_MAX_BARS = 720


class Series:
    def __init__(self, key: Key, asset_type: str, need: int, extended_hours: bool = False):
        self.key = key
        self.venue, self.symbol, self.tf = key
        self.asset_type = asset_type
        self.step = tf_ms(self.tf)
        self.need = max(2, need)
        self.bars: Dict[int, Bar] = {}
        self.times: List[int] = []
        self.quality = SeriesQuality(asset_type, self.tf, extended_hours)
        self.version = 0
        self._frame: Optional[Frame] = None
        self._frame_version = -1
        self.subscribers: Set[str] = set()
        self.orderflow_subs: Set[str] = set()
        self.next_due = 0
        self.in_flight = False
        self.queued = False
        self.backfilled = False
        self.fail_streak = 0
        self.fetches = 0
        self.bars_received = 0
        self.last_new_bar_recv: Optional[int] = None
        self.lock = threading.RLock()
        # order flow
        self.flow: Dict[int, dict] = {}           # bar open time -> {"buy_vol","sell_vol","n_trades","complete"}
        self.book: Dict[int, dict] = {}           # bar open time -> {"bid","ask","bid_depth","ask_depth"}
        self.last_trade_id: Optional[int] = None
        self.flow_since: Optional[int] = None     # first time the trade poller had full coverage
        self.flow_gap_until: int = 0              # bars opening before this time have incomplete prints

    @property
    def maxlen(self) -> int:
        return max(300, int(self.need * 1.25) + 50)

    @property
    def last_time(self) -> Optional[int]:
        return self.times[-1] if self.times else None

    def apply(self, new: List[Bar], replaced: List[Bar]):
        with self.lock:
            for b in replaced:
                self.bars[b.event_time] = b
            for b in new:
                self.bars[b.event_time] = b
            if new:
                self.times = sorted(self.bars)
                if len(self.times) > self.maxlen:
                    for t in self.times[:len(self.times) - self.maxlen]:
                        self.bars.pop(t, None)
                        self.flow.pop(t, None)
                        self.book.pop(t, None)
                    self.times = self.times[len(self.times) - self.maxlen:]
            if new or replaced:
                self.version += 1

    def frame(self) -> Frame:
        with self.lock:
            if self._frame is None or self._frame_version != self.version:
                bars = [self.bars[t] for t in self.times]
                extra = None
                if self.orderflow_subs:
                    extra = {k: [] for k in ("buy_vol", "sell_vol", "n_trades", "bid", "ask", "bid_depth", "ask_depth")}
                    for t in self.times:
                        fl = self.flow.get(t)
                        ok = fl is not None and fl.get("complete")
                        for k in ("buy_vol", "sell_vol", "n_trades"):
                            extra[k].append(fl[k] if ok else None)
                        bk = self.book.get(t)
                        for k in ("bid", "ask", "bid_depth", "ask_depth"):
                            extra[k].append(bk[k] if bk else None)
                self._frame = Frame(self.venue, self.symbol, self.tf, self.asset_type, bars, extra,
                                    self.quality.suspect_times)
                self._frame_version = self.version
            return self._frame

    def status(self, warmup: Optional[int] = None) -> str:
        return self.quality.evaluate_status(self.last_time, len(self.times), warmup if warmup is not None else self.need)

    def to_dict(self) -> dict:
        return {"key": "/".join(self.key), "asset_type": self.asset_type, "bars": len(self.times), "need": self.need,
                "last_bar": self.last_time, "subscribers": len(self.subscribers), "fetches": self.fetches,
                "bars_received": self.bars_received, "orderflow": bool(self.orderflow_subs),
                **self.quality.to_dict()}


class Hub:
    def __init__(self, http: Http, workers: int = 4, storage=None, on_bars: Optional[Callable] = None,
                 queue_limit: int = 256, clock: Callable[[], int] = now_ms):
        self.http = http
        self.adapters: Dict[str, Adapter] = {k: v(http) for k, v in ADAPTERS.items()}
        self.series: Dict[Key, Series] = {}
        self.storage = storage
        self.on_bars = on_bars
        self.q: "queue.Queue[Key]" = queue.Queue(maxsize=queue_limit)
        self.workers = workers
        self.running = False
        self.threads: List[threading.Thread] = []
        self.lock = threading.RLock()
        self.clock = clock
        self.stats = {"polls": 0, "new_bars": 0, "backpressure_deferrals": 0, "fetch_errors": 0,
                      "orderflow_polls": 0, "orderflow_gaps": 0, "book_snapshots": 0, "callback_errors": 0}

    # ------------------------------------------------------------------ subscriptions
    def subscribe(self, venue: str, symbol: str, tf: str, need: int, subscriber: str, asset_type: str,
                  orderflow: bool = False, extended_hours: bool = False) -> Series:
        key = (venue, symbol, tf)
        if venue not in self.adapters:
            raise KeyError(f"unknown venue {venue!r}")
        if not self.adapters[venue].supports(tf):
            raise ValueError(f"{venue} does not publish {tf} bars")
        with self.lock:
            s = self.series.get(key)
            if s is None:
                s = self.series[key] = Series(key, asset_type, need, extended_hours)
            s.need = max(s.need, need)
            if venue == "kraken":
                s.need = min(s.need, KRAKEN_MAX_BARS)
            s.subscribers.add(subscriber)
            if orderflow:
                if venue not in ("coinbase", "okx"):
                    raise ValueError(f"order-flow data is not collected for {venue}")
                s.orderflow_subs.add(subscriber)
            return s

    def unsubscribe(self, subscriber: str):
        with self.lock:
            for k in list(self.series):
                s = self.series[k]
                s.subscribers.discard(subscriber)
                s.orderflow_subs.discard(subscriber)
                if not s.subscribers:
                    del self.series[k]

    def get(self, venue: str, symbol: str, tf: str) -> Optional[Series]:
        return self.series.get((venue, symbol, tf))

    def frame(self, venue: str, symbol: str, tf: str) -> Optional[Frame]:
        s = self.series.get((venue, symbol, tf))
        return s.frame() if s else None

    # ------------------------------------------------------------------ lifecycle
    def start(self):
        if self.running:
            return
        self.running = True
        self.threads = [threading.Thread(target=self._scheduler, name="hub-scheduler", daemon=True)]
        self.threads += [threading.Thread(target=self._worker, name=f"hub-worker-{i}", daemon=True)
                         for i in range(self.workers)]
        self.threads.append(threading.Thread(target=self._flow_loop, name="hub-orderflow", daemon=True))
        for t in self.threads:
            t.start()

    def stop(self, timeout: float = 5.0):
        self.running = False
        for t in self.threads:
            t.join(timeout)

    def _scheduler(self):
        while self.running:
            now = self.clock()
            with self.lock:
                due = [s for s in self.series.values() if not s.in_flight and not s.queued and now >= s.next_due]
            due.sort(key=lambda s: s.next_due)
            for s in due:
                try:
                    s.queued = True
                    self.q.put_nowait(s.key)
                except queue.Full:
                    s.queued = False
                    self.stats["backpressure_deferrals"] += 1
                    break
            time.sleep(0.25)

    def _worker(self):
        while self.running:
            try:
                key = self.q.get(timeout=0.5)
            except queue.Empty:
                continue
            s = self.series.get(key)
            if s is None:
                continue
            s.queued = False
            s.in_flight = True
            try:
                self.refresh(s)
            finally:
                s.in_flight = False

    # ------------------------------------------------------------------ fetching
    def refresh(self, s: Series) -> List[int]:
        """Fetch new bars for one series. Returns the open times of bars added."""
        now = self.clock()
        cal = calendar_for(s.asset_type)
        if is_equity(s.asset_type) and s.backfilled and not cal.is_open(now) and not s.quality.extended_hours:
            today = cal.session_for(now)
            just_closed = today is not None and today.close_ms <= now < today.close_ms + 15 * 60_000 \
                and (s.last_time or 0) + s.step < today.close_ms
            if not just_closed:
                s.quality.evaluate_status(s.last_time, len(s.times), s.need)
                nxt = cal.next_session(now)
                s.next_due = max(nxt.open_ms + s.step + PUBLISH_DELAY_MS["yahoo"], now + 60_000)
                return []
        self.stats["polls"] += 1
        s.fetches += 1
        try:
            bars = self._backfill(s) if not s.backfilled else self._recent(s)
            s.fail_streak = 0
            s.quality.last_fetch_ok = self.clock()
            s.quality.last_fetch_error = None
        except (HttpError, KeyError, ValueError, TypeError) as e:
            s.fail_streak += 1
            self.stats["fetch_errors"] += 1
            s.quality.last_fetch_error = str(e)[:300]
            s.next_due = self.clock() + min(120_000, 5_000 * 2 ** min(s.fail_streak, 5))
            s.quality.evaluate_status(s.last_time, len(s.times), s.need)
            return []
        new, replaced = s.quality.filter_batch(bars, s.bars, s.last_time)
        initial = not s.backfilled
        s.apply(new, replaced)
        s.backfilled = True
        added = [b.event_time for b in new]
        if new:
            s.bars_received += len(new)
            s.last_new_bar_recv = self.clock()
            self.stats["new_bars"] += len(new)
            if self.storage is not None:
                try:
                    self.storage.save_bars(new + replaced)
                except Exception as e:           # storage trouble must not stop data flow
                    log.warning("bar storage failed: %s", e)
        self._schedule_next(s, got_new=bool(new))
        s.quality.evaluate_status(s.last_time, len(s.times), s.need)
        if (new or replaced) and self.on_bars:
            try:
                self.on_bars(s.key, added, [b.event_time for b in replaced], initial)
            except Exception:
                self.stats["callback_errors"] += 1
                log.exception("on_bars callback failed")
        return added

    def _schedule_next(self, s: Series, got_new: bool):
        now = self.clock()
        delay = PUBLISH_DELAY_MS.get(s.venue, 3_000)
        if s.last_time is None:
            s.next_due = now + 30_000
            return
        expected = s.last_time + 2 * s.step + delay
        if expected > now:
            s.next_due = expected
        else:
            # the next bar is due but not published yet: retry, backing off toward a quarter bar
            s.next_due = now + min(max(5_000, s.step // 12), 60_000)

    def _backfill(self, s: Series) -> List[Bar]:
        ad = self.adapters[s.venue]
        need = s.need + 5
        if s.venue == "yahoo":       # one request either way: keep the whole window, so bars dropped as invalid still leave `need`
            return ad.bars(s.symbol, s.tf, limit=10 ** 6, prepost=s.quality.extended_hours)[-s.maxlen:]
        if s.venue == "kraken":
            return ad.bars(s.symbol, s.tf, limit=min(need, KRAKEN_MAX_BARS))
        out: Dict[int, Bar] = {}
        end = None
        for _ in range(40):                                  # hard cap on pages
            batch = ad.bars(s.symbol, s.tf, limit=300, end_ms=end)
            if not batch:
                break
            for b in batch:
                out[b.event_time] = b
            if len(out) >= need:
                break
            oldest = min(b.event_time for b in batch)
            if end is not None and oldest >= end:
                break
            end = oldest if s.venue == "okx" else oldest - 1
        return [out[k] for k in sorted(out)][-need:]

    def _recent(self, s: Series) -> List[Bar]:
        ad = self.adapters[s.venue]
        if s.venue == "yahoo":
            rng = {"1m": "1d", "5m": "5d", "15m": "5d", "30m": "5d", "1h": "1mo", "1d": "3mo"}[s.tf]
            gap_days = ((self.clock() - (s.last_time or 0)) // 86_400_000) if s.last_time else 99
            if gap_days > 4:
                rng = None                                   # long gap: default (maximum) range
            return ad.bars(s.symbol, s.tf, limit=10 ** 6, rng=rng, prepost=s.quality.extended_hours)
        missing = (self.clock() - (s.last_time or 0)) // s.step + 3
        if missing > 300:
            s.backfilled = False                             # long outage: page backwards again
            return self._backfill(s)
        return ad.bars(s.symbol, s.tf, limit=int(max(5, missing)))

    # ------------------------------------------------------------------ order flow
    def _flow_loop(self):
        last_book: Dict[Key, int] = {}
        while self.running:
            with self.lock:
                flows = [s for s in self.series.values() if s.orderflow_subs]
            for s in flows:
                try:
                    self._poll_trades(s)
                    cur_bar = (self.clock() // s.step) * s.step
                    prev_bar = cur_bar - s.step
                    if last_book.get(s.key) != prev_bar and self.clock() - cur_bar < s.step // 2:
                        self._snapshot_book(s, prev_bar)
                        last_book[s.key] = prev_bar
                except (HttpError, KeyError, ValueError) as e:
                    s.quality.counts["orderflow_errors"] = s.quality.counts.get("orderflow_errors", 0) + 1
                    s.flow_gap_until = max(s.flow_gap_until, ((self.clock() // s.step) + 1) * s.step)
                    log.debug("orderflow poll failed for %s: %s", s.key, e)
            time.sleep(2.0 if flows else 1.0)

    def _poll_trades(self, s: Series):
        ad = self.adapters[s.venue]
        trades = ad.trades(s.symbol, limit=1000 if s.venue == "coinbase" else 500)
        self.stats["orderflow_polls"] += 1
        if not trades:
            return
        ids = []
        for t in trades:
            try:
                ids.append(int(t.trade_id))
            except ValueError:
                ids.append(None)
        numeric = all(i is not None for i in ids)
        fresh = [t for t, i in zip(trades, ids) if not numeric or s.last_trade_id is None or i > s.last_trade_id]
        if numeric and s.last_trade_id is not None and fresh:
            if min(int(t.trade_id) for t in fresh) > s.last_trade_id + 1 and s.venue == "coinbase":
                # prints were missed between polls: bars they fall in cannot be complete
                self.stats["orderflow_gaps"] += 1
                gap_end = min(t.event_time for t in fresh)
                s.flow_gap_until = max(s.flow_gap_until, (gap_end // s.step + 1) * s.step)
        if s.flow_since is None:
            first = min(t.event_time for t in trades)
            s.flow_since = (first // s.step + 1) * s.step    # first bar fully covered
        if numeric:
            s.last_trade_id = max(ids)
        now = self.clock()
        with s.lock:
            for t in fresh:
                b = (t.event_time // s.step) * s.step
                fl = s.flow.setdefault(b, {"buy_vol": 0.0, "sell_vol": 0.0, "n_trades": 0, "complete": False})
                fl["buy_vol" if t.side == "buy" else "sell_vol"] += t.size
                fl["n_trades"] += 1
            for b, fl in s.flow.items():
                if not fl["complete"] and b + s.step + 2_000 <= now and b >= (s.flow_since or 10 ** 15) \
                        and b >= s.flow_gap_until:
                    fl["complete"] = True
            s.version += 1 if fresh else 0

    def _snapshot_book(self, s: Series, bar_time: int, levels: int = 10):
        bk = self.adapters[s.venue].book(s.symbol, depth=levels)
        if bk is None or not bk.bids or not bk.asks:
            return
        with s.lock:
            s.book[bar_time] = {"bid": bk.bids[0][0], "ask": bk.asks[0][0],
                                "bid_depth": sum(q for _, q in bk.bids[:levels]),
                                "ask_depth": sum(q for _, q in bk.asks[:levels])}
            s.version += 1
        self.stats["book_snapshots"] += 1

    # ------------------------------------------------------------------ reporting
    def snapshot(self) -> dict:
        with self.lock:
            series = [s.to_dict() for s in self.series.values()]
        counts: Dict[str, int] = {}
        for s in series:
            counts[s["status"]] = counts.get(s["status"], 0) + 1
        return {"series": series, "status_counts": counts, "stats": dict(self.stats), "queue": self.q.qsize(),
                "http": self.http.snapshot()}
