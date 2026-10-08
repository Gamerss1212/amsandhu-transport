"""Bars: one instrument's OHLCV as numpy columns, with the rule that makes look-ahead impossible to forget.

`ts` is each bar's OPEN time (UTC ms). A bar is only known once it has closed: `available_at = ts + step`. Every
consumer (features, strategies, agents, the backtester) asks `upto(t)` for the bars known at time t.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field

import numpy as np

TF_MS = {"1m": 60_000, "5m": 300_000, "15m": 900_000, "30m": 1_800_000, "1h": 3_600_000, "4h": 14_400_000,
         "1d": 86_400_000}
INTRADAY = ("1m", "5m", "15m", "30m", "1h", "4h")


@dataclass
class Bars:
    instrument_id: str
    tf: str
    ts: np.ndarray                     # int64 open time, ms
    open: np.ndarray
    high: np.ndarray
    low: np.ndarray
    close: np.ndarray
    volume: np.ndarray
    simulated: bool = False
    source: str = ""
    meta: dict = field(default_factory=dict)

    def __post_init__(self) -> None:
        n = len(self.ts)
        for name in ("open", "high", "low", "close", "volume"):
            a = getattr(self, name)
            if len(a) != n:
                raise ValueError(f"{name} has {len(a)} values, ts has {n}")
            setattr(self, name, np.asarray(a, dtype=np.float64))
        self.ts = np.asarray(self.ts, dtype=np.int64)
        if n > 1 and np.any(np.diff(self.ts) <= 0):
            raise ValueError("bar times must be strictly increasing")

    @property
    def step(self) -> int:
        return TF_MS[self.tf]

    def __len__(self) -> int:
        return len(self.ts)

    @property
    def available_at(self) -> np.ndarray:
        """When each bar became known: its session close when the provider's session is shorter than the bar
        (US daily bars close at 16:00 New York, not 24 hours after the open), else open + step."""
        av = self.meta.get("avail")
        if av is not None and len(av) == len(self.ts):
            return np.asarray(av, dtype=np.int64)
        return self.ts + self.step

    def upto(self, t_ms: int) -> "Bars":
        """Only the bars that had CLOSED by t_ms."""
        n = int(np.searchsorted(self.available_at, t_ms, side="right"))
        return self.slice(0, n)

    def slice(self, a: int, b: int) -> "Bars":
        meta = dict(self.meta)
        if meta.get("avail") is not None and len(meta["avail"]) == len(self.ts):
            meta["avail"] = np.asarray(meta["avail"])[a:b]
        return Bars(self.instrument_id, self.tf, self.ts[a:b], self.open[a:b], self.high[a:b], self.low[a:b],
                    self.close[a:b], self.volume[a:b], self.simulated, self.source, meta)

    def window(self, start_ms: int | None, end_ms: int | None) -> "Bars":
        a = 0 if start_ms is None else int(np.searchsorted(self.ts, start_ms, side="left"))
        b = len(self) if end_ms is None else int(np.searchsorted(self.ts, end_ms, side="left"))
        return self.slice(a, b)

    def sha256(self) -> str:
        h = hashlib.sha256()
        for a in (self.ts, self.open, self.high, self.low, self.close, self.volume):
            h.update(np.ascontiguousarray(a).tobytes())
        return h.hexdigest()

    def to_rows(self) -> list[dict]:
        return [{"t": int(t), "o": float(o), "h": float(h), "l": float(lo), "c": float(c), "v": float(v)}
                for t, o, h, lo, c, v in zip(self.ts, self.open, self.high, self.low, self.close, self.volume)]

    @staticmethod
    def empty(instrument_id: str, tf: str) -> "Bars":
        z = np.zeros(0)
        return Bars(instrument_id, tf, np.zeros(0, dtype=np.int64), z, z, z, z, z)


def resample(b: Bars, tf: str, now_ms: int | None = None) -> Bars:
    """Aggregate to a higher timeframe. A higher-timeframe bar is emitted only if it is complete (its last source bar
    has closed by `now_ms`), so a 1h bar never appears while its hour is still running (section 245)."""
    step = TF_MS[tf]
    if step < b.step or step % b.step:
        raise ValueError(f"cannot resample {b.tf} to {tf}")
    if not len(b):
        return Bars.empty(b.instrument_id, tf)
    bucket = (b.ts // step) * step
    starts = np.flatnonzero(np.r_[True, bucket[1:] != bucket[:-1]])
    ends = np.r_[starts[1:], len(b)]
    keep = []
    for s, e in zip(starts, ends):
        complete_at = bucket[s] + step
        last_close = b.ts[e - 1] + b.step
        if now_ms is None:
            ok = last_close >= complete_at
        else:
            ok = complete_at <= now_ms
        if ok:
            keep.append((s, e))
    if not keep:
        return Bars.empty(b.instrument_id, tf)
    s_idx = np.array([k[0] for k in keep])
    e_idx = np.array([k[1] for k in keep])
    hi = np.array([b.high[s:e].max() for s, e in keep])
    lo = np.array([b.low[s:e].min() for s, e in keep])
    vol = np.array([b.volume[s:e].sum() for s, e in keep])
    return Bars(b.instrument_id, tf, bucket[s_idx], b.open[s_idx], hi, lo, b.close[e_idx - 1], vol, b.simulated,
                b.source, dict(b.meta, resampled_from=b.tf))
