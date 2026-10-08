"""Provider interface: fetch completed bars for one provider symbol. Unfinished bars are always dropped."""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

import numpy as np

from tradingai.data.bars import TF_MS, Bars


class Provider(ABC):
    name: str = ""
    simulated: bool = False
    timeframes: tuple[str, ...] = ()

    @abstractmethod
    def fetch(self, instrument_id: str, symbol: str, tf: str, start_ms: int, end_ms: int | None = None) -> Bars:
        """Bars with open time in [start_ms, end_ms), completed ones only."""

    @staticmethod
    def complete_only(b: Bars, now_ms: int | None = None) -> Bars:
        now = now_ms if now_ms is not None else int(time.time() * 1000)
        keep = b.available_at <= now
        if keep.all():
            return b
        idx = np.flatnonzero(keep)
        return b.slice(0, int(idx[-1]) + 1) if len(idx) else b.slice(0, 0)


def from_rows(instrument_id: str, tf: str, rows: list[tuple], source: str, simulated: bool = False) -> Bars:
    """rows: (ts_ms, open, high, low, close, volume); sorted and de-duplicated here."""
    if not rows:
        return Bars.empty(instrument_id, tf)
    rows = sorted({r[0]: r for r in rows}.values(), key=lambda r: r[0])
    a = np.array(rows, dtype=np.float64)
    return Bars(instrument_id, tf, a[:, 0].astype(np.int64), a[:, 1], a[:, 2], a[:, 3], a[:, 4], a[:, 5],
                simulated=simulated, source=source)
