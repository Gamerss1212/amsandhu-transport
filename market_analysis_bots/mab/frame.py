"""Frame: one instrument's completed bars as columns, plus the session facts every
session-aware indicator needs.

Built identically for backtests, replays and live evaluation, so an indicator computed on a
Frame gives the same number in all three. A Frame is immutable once built; the live hub
builds a new one each time a series gains a bar.

Session columns
---------------
* `sess`        session id (the session's date as an ordinal), or -1 for a bar outside any session
* `bar_in_sess` 0 for the session's first bar
* `sess_open`, `sess_close`  session bounds in UTC ms
* `tod`         minutes since local midnight at the bar's OPEN (New York for stocks, UTC for crypto)
* `dow`         weekday of the session day, Monday = 0

Stocks use the NYSE regular session (09:30-16:00 New York, 13:00 on early-close days).
Crypto uses the UTC calendar day.
"""

from __future__ import annotations

from datetime import date
from typing import Dict, List, Optional, Sequence

from mab.clock import NYSECalendar, calendar_for, ny_local, tf_ms, to_dt, is_equity
from mab.models import Bar

ORDERFLOW_COLUMNS = ("buy_vol", "sell_vol", "n_trades", "bid", "ask", "bid_depth", "ask_depth")


class Frame:
    __slots__ = ("venue", "instrument", "tf", "asset_type", "step", "t", "o", "h", "l", "c", "v",
                 "sess", "bar_in_sess", "sess_open", "sess_close", "tod", "dow", "dom", "month", "day",
                 "extra", "suspect", "cache", "n")

    def __init__(self, venue: str, instrument: str, tf: str, asset_type: str, bars: Sequence[Bar],
                 extra: Optional[Dict[str, List]] = None, suspect: Optional[set] = None):
        self.venue, self.instrument, self.tf, self.asset_type = venue, instrument, tf, asset_type
        self.step = tf_ms(tf)
        self.t = [b.event_time for b in bars]
        self.o = [b.open for b in bars]
        self.h = [b.high for b in bars]
        self.l = [b.low for b in bars]
        self.c = [b.close for b in bars]
        self.v = [b.volume for b in bars]
        self.n = len(bars)
        self.extra = dict(extra or {})       # optional aligned columns: order flow, funding, ...
        self.suspect = set(suspect or ())
        self.cache: Dict[str, object] = {}
        self._sessions()

    @classmethod
    def from_columns(cls, venue, instrument, tf, asset_type, t, o, h, l, c, v, extra=None):
        bars = [Bar(venue, instrument, tf, int(t[i]), o[i], h[i], l[i], c[i], v[i], 0, "columns")
                for i in range(len(t))]
        return cls(venue, instrument, tf, asset_type, bars, extra)

    # ------------------------------------------------------------------ sessions
    def _sessions(self):
        n = self.n
        self.sess = [-1] * n
        self.bar_in_sess = [0] * n
        self.sess_open = [0] * n
        self.sess_close = [0] * n
        self.tod = [0] * n
        self.dow = [0] * n
        self.dom = [0] * n
        self.month = [0] * n
        self.day = [0] * n                   # local calendar date ordinal of every bar (incl. extended hours)
        cal = calendar_for(self.asset_type)
        stock = isinstance(cal, NYSECalendar)
        day_cache: Dict[date, object] = {}
        prev_sess, k = None, 0
        for i, t in enumerate(self.t):
            if stock:
                loc = ny_local(t)
                d = loc.date()
                s = day_cache.get(d, 0)
                if s == 0:
                    s = day_cache[d] = cal.session_on(d)
                inside = s is not None and s.contains(t)
            else:
                loc = to_dt(t).replace(tzinfo=None)
                d = loc.date()
                s = day_cache.get(d, 0)
                if s == 0:
                    s = day_cache[d] = cal.session_for(t)
                inside = True
            self.tod[i] = loc.hour * 60 + loc.minute
            self.dow[i] = d.weekday()
            self.dom[i] = d.day
            self.month[i] = d.month
            self.day[i] = d.toordinal()
            if inside:
                sid = d.toordinal()
                self.sess[i] = sid
                self.sess_open[i], self.sess_close[i] = s.open_ms, s.close_ms
                k = k + 1 if sid == prev_sess else 0
                self.bar_in_sess[i] = k
                prev_sess = sid
            else:
                self.sess[i] = -1
                self.bar_in_sess[i] = -1

    # ------------------------------------------------------------------ helpers
    def col(self, name: str) -> List:
        base = {"open": self.o, "high": self.h, "low": self.l, "close": self.c, "volume": self.v, "time": self.t}
        if name in base:
            return base[name]
        key = "src:" + name
        if key in self.cache:
            return self.cache[key]
        if name == "hl2":
            out = [(a + b) / 2 for a, b in zip(self.h, self.l)]
        elif name == "hlc3":
            out = [(a + b + c) / 3 for a, b, c in zip(self.h, self.l, self.c)]
        elif name == "ohlc4":
            out = [(a + b + c + d) / 4 for a, b, c, d in zip(self.o, self.h, self.l, self.c)]
        elif name in self.extra:
            out = self.extra[name]
        elif name in ORDERFLOW_COLUMNS:
            out = [None] * self.n            # not available: never estimated silently
        else:
            raise KeyError(f"unknown price source {name!r}")
        self.cache[key] = out
        return out

    def has(self, column: str) -> bool:
        col = self.extra.get(column)
        return bool(col) and any(x is not None for x in col)

    @property
    def last_time(self) -> Optional[int]:
        return self.t[-1] if self.n else None

    def end_time(self, i: int) -> int:
        return self.t[i] + self.step

    def tail(self, n: int) -> "Frame":
        """A frame holding only the last n bars (used to prove buffer-length independence)."""
        k = max(0, self.n - n)
        bars = [Bar(self.venue, self.instrument, self.tf, self.t[i], self.o[i], self.h[i], self.l[i],
                    self.c[i], self.v[i], 0, "tail") for i in range(k, self.n)]
        extra = {name: col[k:] for name, col in self.extra.items()}
        return Frame(self.venue, self.instrument, self.tf, self.asset_type, bars, extra, self.suspect)

    def bars_per_year(self) -> float:
        per_day = (390 * 60_000 if is_equity(self.asset_type) else 1440 * 60_000) / self.step
        return per_day * (252 if is_equity(self.asset_type) else 365)
