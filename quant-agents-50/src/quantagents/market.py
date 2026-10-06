"""Point-in-time market data.

Agents never receive a ``MarketData`` object. They receive a ``MarketView`` that ends at
the as-of date and exposes read-only arrays, so look-ahead is impossible by construction.
"""

from __future__ import annotations

import csv
import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from pathlib import Path

import numpy as np
import numpy.typing as npt

FloatArray = npt.NDArray[np.float64]
FIELDS: tuple[str, ...] = ("open", "high", "low", "close", "volume")


def as_readonly(values: npt.ArrayLike) -> FloatArray:
    """Copy values into a one-dimensional, read-only float64 array."""
    arr = np.array(values, dtype=np.float64)
    if arr.ndim != 1:
        raise ValueError("price arrays must be one-dimensional")
    arr.setflags(write=False)
    return arr


@dataclass(frozen=True, slots=True)
class Bar:
    open: float
    high: float
    low: float
    close: float
    volume: float

    def is_finite(self) -> bool:
        return all(
            math.isfinite(x) for x in (self.open, self.high, self.low, self.close, self.volume)
        )


@dataclass(frozen=True)
class Bars:
    """One symbol's OHLCV history. Arrays are read-only and share one length."""

    open: FloatArray
    high: FloatArray
    low: FloatArray
    close: FloatArray
    volume: FloatArray

    @classmethod
    def from_arrays(
        cls,
        *,
        open: npt.ArrayLike,
        high: npt.ArrayLike,
        low: npt.ArrayLike,
        close: npt.ArrayLike,
        volume: npt.ArrayLike,
    ) -> Bars:
        bars = cls(
            as_readonly(open),
            as_readonly(high),
            as_readonly(low),
            as_readonly(close),
            as_readonly(volume),
        )
        n = len(bars.close)
        if any(len(a) != n for a in (bars.open, bars.high, bars.low, bars.volume)):
            raise ValueError("open, high, low, close and volume must have the same length")
        return bars

    def field(self, name: str) -> FloatArray:
        match name:
            case "open":
                return self.open
            case "high":
                return self.high
            case "low":
                return self.low
            case "close":
                return self.close
            case "volume":
                return self.volume
            case _:
                raise KeyError(f"unknown field {name!r}")

    def __len__(self) -> int:
        return len(self.close)


class MarketData:
    """A rectangular panel of daily bars. Missing values are NaN (A02 catches them)."""

    def __init__(self, dates: Sequence[date], bars: Mapping[str, Bars]) -> None:
        if not dates:
            raise ValueError("market data needs at least one date")
        if any(b <= a for a, b in pairwise(dates)):
            raise ValueError("dates must be strictly increasing")
        if not bars:
            raise ValueError("market data needs at least one symbol")
        for symbol, series in bars.items():
            if len(series) != len(dates):
                raise ValueError(f"{symbol}: {len(series)} bars for {len(dates)} dates")
        self._dates: tuple[date, ...] = tuple(dates)
        self._index: dict[date, int] = {d: i for i, d in enumerate(self._dates)}
        self._bars: dict[str, Bars] = dict(sorted(bars.items()))

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(self._bars)

    @property
    def dates(self) -> tuple[date, ...]:
        return self._dates

    def __len__(self) -> int:
        return len(self._dates)

    def index_of(self, day: date) -> int:
        try:
            return self._index[day]
        except KeyError:
            raise KeyError(f"no bar dated {day.isoformat()}") from None

    def has_date(self, day: date) -> bool:
        return day in self._index

    def bars(self, symbol: str) -> Bars:
        return self._bars[symbol]

    def bar(self, symbol: str, day: date) -> Bar:
        i = self.index_of(day)
        b = self._bars[symbol]
        return Bar(
            float(b.open[i]),
            float(b.high[i]),
            float(b.low[i]),
            float(b.close[i]),
            float(b.volume[i]),
        )

    def next_date(self, day: date) -> date | None:
        i = self.index_of(day)
        return self._dates[i + 1] if i + 1 < len(self._dates) else None

    def view(self, as_of: date) -> MarketView:
        return MarketView(self, self.index_of(as_of))

    def view_at(self, index: int) -> MarketView:
        if not 0 <= index < len(self._dates):
            raise IndexError(index)
        return MarketView(self, index)


class MarketView:
    """Causal window of a MarketData ending at ``as_of`` (inclusive). Read-only."""

    __slots__ = ("_data", "_end")

    def __init__(self, data: MarketData, end_index: int) -> None:
        self._data = data
        self._end = end_index

    @property
    def as_of(self) -> date:
        return self._data.dates[self._end]

    @property
    def dates(self) -> tuple[date, ...]:
        return self._data.dates[: self._end + 1]

    @property
    def symbols(self) -> tuple[str, ...]:
        return self._data.symbols

    def __len__(self) -> int:
        return self._end + 1

    def series(self, symbol: str, field: str) -> FloatArray:
        return self._data.bars(symbol).field(field)[: self._end + 1]

    def open(self, symbol: str) -> FloatArray:
        return self.series(symbol, "open")

    def high(self, symbol: str) -> FloatArray:
        return self.series(symbol, "high")

    def low(self, symbol: str) -> FloatArray:
        return self.series(symbol, "low")

    def close(self, symbol: str) -> FloatArray:
        return self.series(symbol, "close")

    def volume(self, symbol: str) -> FloatArray:
        return self.series(symbol, "volume")

    def last(self, symbol: str) -> Bar:
        return self._data.bar(symbol, self.as_of)


def load_csv(path: Path | str) -> MarketData:
    """Load long-format CSV with columns date,symbol,open,high,low,close,volume.

    Dates are the union over symbols; a symbol missing a date gets NaN, which the
    data-quality agent (A02) flags and blocks.
    """
    rows: dict[str, dict[date, tuple[float, ...]]] = {}
    with Path(path).open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"date", "symbol", *FIELDS}
        missing = required - set(reader.fieldnames or ())
        if missing:
            raise ValueError(f"{path}: missing columns {sorted(missing)}")
        for line_no, row in enumerate(reader, start=2):
            try:
                day = date.fromisoformat(row["date"].strip())
                values = tuple(float(row[f]) for f in FIELDS)
            except ValueError as exc:
                raise ValueError(f"{path}:{line_no}: {exc}") from exc
            per_symbol = rows.setdefault(row["symbol"].strip(), {})
            if day in per_symbol:
                raise ValueError(f"{path}:{line_no}: duplicate row for {row['symbol']} {day}")
            per_symbol[day] = values
    if not rows:
        raise ValueError(f"{path}: no data rows")
    all_dates = sorted({d for per_symbol in rows.values() for d in per_symbol})
    nan_row = (math.nan,) * len(FIELDS)
    bars: dict[str, Bars] = {}
    for symbol, per_symbol in rows.items():
        table = np.array([per_symbol.get(d, nan_row) for d in all_dates], dtype=np.float64)
        bars[symbol] = Bars.from_arrays(
            open=table[:, 0],
            high=table[:, 1],
            low=table[:, 2],
            close=table[:, 3],
            volume=table[:, 4],
        )
    return MarketData(all_dates, bars)


def save_csv(data: MarketData, path: Path | str) -> None:
    """Write long-format CSV that ``load_csv`` can read back."""
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.writer(handle)
        writer.writerow(["date", "symbol", *FIELDS])
        for i, day in enumerate(data.dates):
            for symbol in data.symbols:
                b = data.bars(symbol)
                writer.writerow(
                    [day.isoformat(), symbol, *(repr(float(b.field(f)[i])) for f in FIELDS)]
                )
