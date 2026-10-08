"""Futures roll and delivery safety (master prompt sections 133-134).

A continuous futures chart is a research convenience; money is made and lost in real contracts. So this module keeps
two things apart:

* the SIGNAL series: one of four continuous constructions (`continuous()`): "stitched" (raw prices joined at each
  roll, with the gaps), "difference" (back-adjusted by the price gap at each roll), "ratio" (back-adjusted by the price
  ratio), or "raw" per contract;
* the EXECUTION series (`execution_prices()`): for every day, which real contract was held and its real price. A
  backtest fills orders on this series only; an adjusted price is never a fill price.

`delivery_guard()` refuses to carry a physically settled contract into its delivery window, and refuses outright when
the broker gave no first notice date: an unknown date is treated as unsafe, never as "probably fine".

Dates are ISO strings (UTC trading dates). Bars are {contract_month: {date: close}}; prices are Decimals or numbers.
"""

from __future__ import annotations

from datetime import date
from decimal import Decimal
from typing import Dict, List, Optional, Tuple

from mab.instrument_spec import Instrument, Settlement, money

Bars = Dict[str, Dict[str, Decimal]]          # contract month -> {date -> close}


def _d(s: str) -> date:
    return date.fromisoformat(s)


def roll_schedule(expiries: Dict[str, str], dates: List[str], roll_days_before: int = 5,
                  open_interest: Optional[Dict[str, Dict[str, float]]] = None) -> Dict[str, str]:
    """Which contract is the front on each date. Calendar rule: hold the nearest contract until `roll_days_before`
    calendar days before its expiry. With `open_interest`, roll earlier once the next contract's open interest is
    larger (never later than the calendar rule). Rolls only move forward."""
    months = sorted(expiries, key=lambda m: expiries[m])
    out: Dict[str, str] = {}
    i = 0
    for day in sorted(dates):
        while i < len(months) - 1 and (_d(expiries[months[i]]) - _d(day)).days <= roll_days_before:
            i += 1
        if open_interest and i < len(months) - 1:
            cur, nxt = open_interest.get(months[i], {}).get(day), open_interest.get(months[i + 1], {}).get(day)
            if cur is not None and nxt is not None and nxt > cur:
                i += 1
        if _d(day) > _d(expiries[months[i]]):
            raise ValueError(f"{day}: no listed contract left (the last one expired {expiries[months[i]]})")
        out[day] = months[i]
    return out


def execution_prices(bars: Bars, schedule: Dict[str, str]) -> Dict[str, Tuple[str, Decimal]]:
    """{date: (contract, real close)}: what a backtest may fill at. A missing bar is an error, not a fill."""
    out = {}
    for day, m in sorted(schedule.items()):
        if day not in bars.get(m, {}):
            raise KeyError(f"{day}: no {m} bar: the held contract has no price that day")
        out[day] = (m, money(str(bars[m][day])) if not isinstance(bars[m][day], Decimal) else bars[m][day])
    return out


def continuous(bars: Bars, schedule: Dict[str, str], method: str = "difference") -> Dict[str, Decimal]:
    """A continuous SIGNAL series. "stitched": raw front-contract closes. "difference": earlier prices shifted by the
    gap between the new and the old contract on each roll day, so the latest prices are real. "ratio": earlier prices
    scaled by new/old on each roll day (keeps percentage moves; needs positive prices)."""
    if method not in ("stitched", "difference", "ratio"):
        raise ValueError("method must be stitched, difference or ratio")
    ex = execution_prices(bars, schedule)
    days = sorted(ex)
    series = {d: ex[d][1] for d in days}
    if method == "stitched":
        return series
    # walk backwards; at each roll, adjust everything before it
    shift, scale = Decimal(0), Decimal(1)
    out: Dict[str, Decimal] = {}
    for k in range(len(days) - 1, -1, -1):
        d = days[k]
        out[d] = series[d] * scale if method == "ratio" else series[d] + shift
        if k > 0 and ex[days[k - 1]][0] != ex[d][0]:          # a roll happened between days[k-1] and d
            old_m, new_m = ex[days[k - 1]][0], ex[d][0]
            prev = days[k - 1]
            if prev not in bars.get(new_m, {}):
                raise KeyError(f"roll on {prev}: no {new_m} price that day to measure the gap")
            new_px, old_px = money(str(bars[new_m][prev])), money(str(bars[old_m][prev]))
            if method == "ratio":
                if old_px <= 0:
                    raise ValueError("ratio adjustment needs positive prices")
                scale *= new_px / old_px
            else:
                shift += new_px - old_px
    return dict(sorted(out.items()))


def delivery_guard(inst: Instrument, today: str, buffer_days: int = 3) -> Tuple[bool, str]:
    """May a position in `inst` be held through `today`? Section 134: physically settled contracts are closed before
    their delivery window; an unknown first notice date blocks; every contract is closed before its last trading day."""
    if inst.settlement is Settlement.PHYSICAL:
        if not inst.first_notice:
            return False, f"{inst.instrument_id}: physically settled and no first notice date from the broker"
        if (_d(inst.first_notice) - _d(today)).days <= buffer_days:
            return False, f"{inst.instrument_id}: within {buffer_days} days of first notice ({inst.first_notice})"
    if inst.expiry and (_d(inst.expiry) - _d(today)).days <= max(1, buffer_days if inst.settlement
                                                                  is Settlement.PHYSICAL else 1):
        return False, f"{inst.instrument_id}: at or near its last trading day ({inst.expiry})"
    return True, "ok"
