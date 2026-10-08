"""Data-quality checks run on every batch before a bar reaches a strategy (sections 222, 227, 250, 312).

Nothing is silently deleted. Each problem is classified and counted; only impossible bars (high below low, non-positive
prices, NaN) are excluded, and the report says how many. An extreme move is flagged as a suspected bad tick only when it
reverses on the next bar; a move that sticks is real and is kept.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

import numpy as np

from tradingai.data.bars import Bars


@dataclass
class QualityReport:
    rows: int
    excluded: int = 0
    duplicates: int = 0
    gaps: int = 0
    max_gap_bars: int = 0
    suspected_bad_ticks: list[int] = field(default_factory=list)
    zero_volume_share: float = 0.0
    stale: bool = False
    last_bar_age_s: float | None = None
    issues: list[str] = field(default_factory=list)

    @property
    def score(self) -> int:
        """0-100, for the data-health panel: 100 means no issue found."""
        s = 100
        s -= min(40, self.excluded * 5)
        s -= min(20, len(self.suspected_bad_ticks) * 5)
        s -= min(20, self.gaps)
        s -= 30 if self.stale else 0
        return max(0, s)

    def as_dict(self) -> dict:
        return {"rows": self.rows, "excluded": self.excluded, "duplicates": self.duplicates, "gaps": self.gaps,
                "max_gap_bars": self.max_gap_bars, "suspected_bad_ticks": len(self.suspected_bad_ticks),
                "zero_volume_share": round(self.zero_volume_share, 4), "stale": self.stale,
                "last_bar_age_s": self.last_bar_age_s, "score": self.score, "issues": self.issues}


def check(b: Bars, *, continuous: bool, stale_after_bars: float = 3.0, now_ms: int | None = None) -> tuple[Bars, QualityReport]:
    """Return the usable bars and a report. `continuous`: the market trades around the clock (crypto), so any missing
    bar is a gap; for session markets gaps between sessions are expected and not counted."""
    rep = QualityReport(rows=len(b))
    if not len(b):
        rep.issues.append("no data")
        rep.stale = True
        return b, rep
    ok = (np.isfinite(b.open) & np.isfinite(b.high) & np.isfinite(b.low) & np.isfinite(b.close)
          & (b.low > 0) & (b.high >= b.low) & (b.high >= np.maximum(b.open, b.close) - 1e-12)
          & (b.low <= np.minimum(b.open, b.close) + 1e-12) & (b.volume >= 0))
    rep.excluded = int((~ok).sum())
    if rep.excluded:
        rep.issues.append(f"{rep.excluded} impossible bar(s) excluded (high<low, non-positive or missing prices)")
        idx = np.flatnonzero(ok)
        b = Bars(b.instrument_id, b.tf, b.ts[idx], b.open[idx], b.high[idx], b.low[idx], b.close[idx],
                 b.volume[idx], b.simulated, b.source,
                 dict(b.meta, avail=np.asarray(b.meta["avail"])[idx]) if b.meta.get("avail") is not None else
                 dict(b.meta))
    if len(b) > 1:
        d = np.diff(b.ts)
        if continuous:
            missing = d // b.step - 1
            rep.gaps = int((missing > 0).sum())
            rep.max_gap_bars = int(missing.max()) if len(missing) else 0
            if rep.gaps:
                rep.issues.append(f"{rep.gaps} gap(s) in a 24/7 market (largest {rep.max_gap_bars} bars)")
        r = np.diff(np.log(b.close))
        if len(r) > 30:
            med = np.median(np.abs(r))
            mad = med if med > 0 else np.mean(np.abs(r)) + 1e-12
            big = np.flatnonzero(np.abs(r) > 15 * mad)
            for i in big:
                if i + 1 < len(r) and np.sign(r[i + 1]) == -np.sign(r[i]) and abs(r[i + 1]) > 0.7 * abs(r[i]):
                    rep.suspected_bad_ticks.append(int(b.ts[i + 1]))
            if rep.suspected_bad_ticks:
                rep.issues.append(f"{len(rep.suspected_bad_ticks)} spike(s) that reversed at once: suspected bad "
                                  "ticks (kept, flagged; strategies skip signals on them)")
    rep.zero_volume_share = float((b.volume == 0).mean()) if len(b) else 0.0
    now = now_ms if now_ms is not None else int(time.time() * 1000)
    age = (now - int(b.available_at[-1])) / 1000
    rep.last_bar_age_s = round(age, 1)
    if continuous and age > stale_after_bars * b.step / 1000:
        rep.stale = True
        rep.issues.append(f"stale: newest bar closed {age / 60:.0f} min ago")
    return b, rep
