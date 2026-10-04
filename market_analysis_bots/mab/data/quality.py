"""Data-quality controls. Run on every batch before any bar reaches a strategy.

Checks and what each does when it fires:

| Check | Action |
|---|---|
| schema: missing or non-finite field | bar rejected, counted |
| impossible prices: <= 0, high < low, open/close outside [low, high] | bar rejected, counted |
| future timestamp beyond clock tolerance | bar rejected, counted |
| incomplete bar (end time in the future) | bar rejected (adapters already drop these; this is a second guard) |
| duplicate event (same open time) | idempotent: the later copy replaces the earlier, counted |
| out-of-order / late event | accepted only if it fills a known gap, otherwise ignored, counted |
| outside the regular session (stocks) | dropped unless the subscription asked for extended hours |
| extreme jump versus the previous close | bar kept but marked suspect; bots on that series skip the bar |
| gap (missing bars inside a session) | counted; strategies that need contiguous data read `gap_ratio` |
| stale series (no new bar when one was due) | series status becomes `stale`; bots report `data_unavailable` |

Series status is one of: `ok`, `warming` (not enough history yet), `stale`, `market_closed`,
`suspect`, `unavailable` (fetches failing). Only `ok` lets a bot evaluate.
"""

from __future__ import annotations

import math
from typing import Dict, List, Optional, Tuple

from mab.clock import calendar_for, tf_ms, is_equity
from mab.models import Bar, now_ms

CLOCK_TOLERANCE_MS = 120_000


def jump_limit(asset_type: str, tf: str) -> float:
    """Largest single-bar close-to-close move accepted without flagging, as a fraction."""
    base = 0.25 if asset_type.startswith("crypto") else 0.15
    return base * (1.0 if tf in ("1m", "5m") else 1.5)


def validate_bar(b: Bar, now: int) -> Optional[str]:
    for k in ("open", "high", "low", "close", "volume"):
        v = getattr(b, k)
        if v is None or not isinstance(v, (int, float)) or math.isnan(v) or math.isinf(v):
            return f"schema: {k} missing or not finite"
    if min(b.open, b.high, b.low, b.close) <= 0:
        return "impossible: non-positive price"
    if b.volume < 0:
        return "impossible: negative volume"
    if b.high < b.low:
        return "impossible: high below low"
    eps = 1e-9 * max(1.0, b.high)
    if not (b.low - eps <= b.open <= b.high + eps and b.low - eps <= b.close <= b.high + eps):
        return "impossible: open/close outside the bar's range"
    if b.event_time > now + CLOCK_TOLERANCE_MS:
        return "timestamp: bar opens in the future"
    if b.event_time + tf_ms(b.timeframe) > now + CLOCK_TOLERANCE_MS:
        return "incomplete: bar has not closed yet"
    return None


class SeriesQuality:
    """Running quality state for one (venue, instrument, timeframe) series."""

    def __init__(self, asset_type: str, tf: str, extended_hours: bool = False):
        self.asset_type = asset_type
        self.tf = tf
        self.extended_hours = extended_hours
        self.counts: Dict[str, int] = {}
        self.last_issue: Optional[str] = None
        self.status = "warming"
        self.last_fetch_ok: Optional[int] = None
        self.last_fetch_error: Optional[str] = None
        self.suspect_times: set = set()

    def _count(self, k: str, n: int = 1):
        self.counts[k] = self.counts.get(k, 0) + n

    def filter_batch(self, bars: List[Bar], known: Dict[int, Bar], last_time: Optional[int]) -> Tuple[List[Bar], List[Bar]]:
        """Return (new_bars_in_order, replaced_duplicates). Never mutates `known`."""
        now = now_ms()
        cal = calendar_for(self.asset_type)
        out: List[Bar] = []
        replaced: List[Bar] = []
        seen_in_batch = set()
        prev_close = known[last_time].close if (last_time is not None and last_time in known) else None
        for b in sorted(bars, key=lambda x: x.event_time):
            why = validate_bar(b, now)
            if why:
                self._count(why.split(":")[0])
                self.last_issue = why
                continue
            if is_equity(self.asset_type) and not self.extended_hours and not cal.is_open(b.event_time):
                self._count("outside_session")
                continue
            if b.event_time in seen_in_batch:
                self._count("duplicate")
                continue
            seen_in_batch.add(b.event_time)
            if b.event_time in known:
                old = known[b.event_time]
                if (old.open, old.high, old.low, old.close, old.volume) != (b.open, b.high, b.low, b.close, b.volume):
                    self._count("revised")          # the venue corrected a bar it had already sent
                    replaced.append(b)
                else:
                    self._count("duplicate")
                continue
            if last_time is not None and b.event_time < last_time:
                self._count("late_fill")            # fills an earlier gap; accepted
            if prev_close:
                move = abs(b.close / prev_close - 1)
                if move > jump_limit(self.asset_type, self.tf):
                    self._count("suspect_jump")
                    self.suspect_times.add(b.event_time)
                    self.last_issue = f"suspect: {move:.1%} move in one bar"
            prev_close = b.close
            out.append(b)
        return out, replaced

    def gaps(self, times: List[int]) -> int:
        """Missing bars between consecutive bars of the same session."""
        step = tf_ms(self.tf)
        cal = calendar_for(self.asset_type)
        n = 0
        for a, b in zip(times, times[1:]):
            if b - a > step:
                if is_equity(self.asset_type):
                    sa, sb = cal.session_for(a), cal.session_for(b)
                    if sa is None or sb is None or sa.day != sb.day:
                        continue                    # overnight: not a gap
                n += (b - a) // step - 1
        return n

    def evaluate_status(self, last_time: Optional[int], history: int, warmup: int) -> str:
        now = now_ms()
        step = tf_ms(self.tf)
        cal = calendar_for(self.asset_type)
        if last_time is None:
            self.status = "unavailable" if self.last_fetch_error else "warming"
            return self.status
        if is_equity(self.asset_type) and not cal.is_open(now) and not self.extended_hours:
            # outside the session nothing new is due; data is not stale, the market is shut
            self.status = "market_closed"
            return self.status
        grace = max(90_000, step // 2)
        due = last_time + 2 * step + grace          # the bar after the last one should have closed by now
        if self.asset_type == "forex" and any((d + 3) % 7 == 5 for d in range(last_time // 86_400_000, now // 86_400_000 + 1)):
            due += 2 * 86_400_000                   # forex shuts from Friday to Sunday evening (UTC): no bars due then
        if now > due:
            self.status = "stale"
        elif history < warmup:
            self.status = "warming"
        elif last_time in self.suspect_times:
            self.status = "suspect"
        else:
            self.status = "ok"
        return self.status

    def to_dict(self) -> dict:
        return {"status": self.status, "counts": dict(self.counts), "last_issue": self.last_issue,
                "last_fetch_ok": self.last_fetch_ok, "last_fetch_error": self.last_fetch_error}
