"""Time, timeframes and exchange calendars.

UTC epoch milliseconds everywhere internally. Local exchange time only exists inside this
module, where it is derived from explicit rules:

* America/New_York daylight saving (Energy Policy Act of 2005 rules, in force since 2007):
  EDT (UTC-4) from 02:00 local on the second Sunday of March to 02:00 local on the first
  Sunday of November; EST (UTC-5) otherwise. Implemented here rather than via zoneinfo
  because Windows Python ships without the IANA database.
* NYSE full-day holidays and 13:00 early closes, computed from their published rules.
  Unscheduled closures (e.g. national days of mourning) cannot be predicted; the data
  quality layer still catches them as "no bars during an expected session".
* Crypto trades continuously. The platform's crypto trading day is the UTC calendar day.
"""

from __future__ import annotations

import calendar as _cal
from datetime import date, datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple

MINUTE = 60_000
HOUR = 60 * MINUTE
DAY = 24 * HOUR

TIMEFRAMES: Dict[str, int] = {
    "1m": MINUTE, "5m": 5 * MINUTE, "15m": 15 * MINUTE, "30m": 30 * MINUTE,
    "1h": HOUR, "4h": 4 * HOUR, "1d": DAY,
}


def tf_ms(tf: str) -> int:
    try:
        return TIMEFRAMES[tf]
    except KeyError:
        raise ValueError(f"unsupported timeframe {tf!r}; use one of {sorted(TIMEFRAMES)}") from None


def floor_ms(ms: int, tf: str) -> int:
    step = tf_ms(tf)
    return ms - (ms % step)


def to_dt(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc)


def to_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp() * 1000)


# ----------------------------------------------------------------------------- New York time

def _nth_weekday(year: int, month: int, weekday: int, n: int) -> date:
    """n-th (1-based) given weekday (Mon=0) of a month; n=-1 for the last."""
    if n > 0:
        d = date(year, month, 1)
        d += timedelta(days=(weekday - d.weekday()) % 7)
        return d + timedelta(weeks=n - 1)
    last = date(year, month, _cal.monthrange(year, month)[1])
    return last - timedelta(days=(last.weekday() - weekday) % 7)


def ny_offset_hours(utc_ms: int) -> int:
    """UTC offset of New York at a UTC instant: -4 during daylight time, -5 otherwise."""
    dt = to_dt(utc_ms)
    y = dt.year
    # DST starts 02:00 EST (07:00 UTC) on the 2nd Sunday of March,
    # ends 02:00 EDT (06:00 UTC) on the 1st Sunday of November.
    start = datetime.combine(_nth_weekday(y, 3, 6, 2), datetime.min.time(), timezone.utc) + timedelta(hours=7)
    end = datetime.combine(_nth_weekday(y, 11, 6, 1), datetime.min.time(), timezone.utc) + timedelta(hours=6)
    return -4 if start <= dt < end else -5


def ny_local(utc_ms: int) -> datetime:
    """Naive datetime of the New York wall clock at a UTC instant."""
    return (to_dt(utc_ms) + timedelta(hours=ny_offset_hours(utc_ms))).replace(tzinfo=None)


def ny_to_utc_ms(local: datetime) -> int:
    """UTC ms for a New York wall-clock time (for times away from the DST switch hour)."""
    guess = to_ms(local.replace(tzinfo=timezone.utc)) + 5 * HOUR
    off = ny_offset_hours(guess)
    return to_ms(local.replace(tzinfo=timezone.utc)) - off * HOUR


# ----------------------------------------------------------------------------- NYSE calendar

def _easter(year: int) -> date:
    """Anonymous Gregorian computus."""
    a = year % 19
    b, c = divmod(year, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    month = (h + l - 7 * m + 114) // 31
    day = ((h + l - 7 * m + 114) % 31) + 1
    return date(year, month, day)


def _observed(d: date) -> Optional[date]:
    if d.weekday() == 5:
        return d - timedelta(days=1)
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


def nyse_holidays(year: int) -> Dict[date, str]:
    h: Dict[date, str] = {}
    ny = date(year, 1, 1)
    if ny.weekday() == 6:
        h[ny + timedelta(days=1)] = "New Year's Day (observed)"
    elif ny.weekday() != 5:                       # NYSE does not observe a Saturday New Year on the Friday
        h[ny] = "New Year's Day"
    h[_nth_weekday(year, 1, 0, 3)] = "Martin Luther King Jr. Day"
    h[_nth_weekday(year, 2, 0, 3)] = "Washington's Birthday"
    h[_easter(year) - timedelta(days=2)] = "Good Friday"
    h[_nth_weekday(year, 5, 0, -1)] = "Memorial Day"
    if year >= 2022:
        h[_observed(date(year, 6, 19))] = "Juneteenth"
    h[_observed(date(year, 7, 4))] = "Independence Day"
    h[_nth_weekday(year, 9, 0, 1)] = "Labor Day"
    h[_nth_weekday(year, 11, 3, 4)] = "Thanksgiving Day"
    h[_observed(date(year, 12, 25))] = "Christmas Day"
    return h


def nyse_early_closes(year: int) -> Dict[date, str]:
    """13:00 ET closes."""
    e: Dict[date, str] = {}
    j3 = date(year, 7, 3)
    if j3.weekday() < 5 and date(year, 7, 4).weekday() < 5 and j3 not in nyse_holidays(year):
        e[j3] = "Day before Independence Day"
    e[_nth_weekday(year, 11, 3, 4) + timedelta(days=1)] = "Day after Thanksgiving"
    c24 = date(year, 12, 24)
    if c24.weekday() < 5 and c24 not in nyse_holidays(year):
        e[c24] = "Christmas Eve"
    return e


class Session:
    """One trading session, as UTC ms bounds."""
    __slots__ = ("day", "open_ms", "close_ms", "early_close")

    def __init__(self, day: date, open_ms: int, close_ms: int, early_close: bool):
        self.day, self.open_ms, self.close_ms, self.early_close = day, open_ms, close_ms, early_close

    def contains(self, ms: int) -> bool:
        return self.open_ms <= ms < self.close_ms

    def __repr__(self):
        return f"Session({self.day}, {self.open_ms}-{self.close_ms}{', early' if self.early_close else ''})"


class Calendar:
    name = "base"

    def session_for(self, ms: int) -> Optional[Session]:
        raise NotImplementedError

    def is_open(self, ms: int) -> bool:
        s = self.session_for(ms)
        return bool(s and s.contains(ms))

    def trading_day(self, ms: int) -> date:
        raise NotImplementedError


class NYSECalendar(Calendar):
    """US equities regular session, 09:30-16:00 New York time (13:00 on early-close days)."""
    name = "XNYS"

    def is_trading_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in nyse_holidays(d.year)

    def session_on(self, d: date) -> Optional[Session]:
        if not self.is_trading_day(d):
            return None
        early = d in nyse_early_closes(d.year)
        o = ny_to_utc_ms(datetime(d.year, d.month, d.day, 9, 30))
        c = ny_to_utc_ms(datetime(d.year, d.month, d.day, 13 if early else 16, 0))
        return Session(d, o, c, early)

    def session_for(self, ms: int) -> Optional[Session]:
        return self.session_on(ny_local(ms).date())

    def trading_day(self, ms: int) -> date:
        return ny_local(ms).date()

    def next_session(self, ms: int) -> Session:
        d = ny_local(ms).date()
        for k in range(0, 15):
            s = self.session_on(d + timedelta(days=k))
            if s and s.close_ms > ms:
                return s
        raise RuntimeError("no session within 15 days")


def tsx_holidays(year: int) -> Dict[date, str]:
    """Toronto Stock Exchange full-day closures from their recurring rules."""
    h: Dict[date, str] = {}

    def monday_if_weekend(d: date) -> date:
        return d + timedelta(days=(7 - d.weekday()) % 7) if d.weekday() >= 5 else d

    h[monday_if_weekend(date(year, 1, 1))] = "New Year's Day"
    h[_nth_weekday(year, 2, 0, 3)] = "Family Day"
    h[_easter(year) - timedelta(days=2)] = "Good Friday"
    may24 = date(year, 5, 24)
    h[may24 - timedelta(days=may24.weekday())] = "Victoria Day"
    h[monday_if_weekend(date(year, 7, 1))] = "Canada Day"
    h[_nth_weekday(year, 8, 0, 1)] = "Civic Holiday"
    h[_nth_weekday(year, 9, 0, 1)] = "Labour Day"
    h[_nth_weekday(year, 10, 0, 2)] = "Thanksgiving Day"
    xmas, boxing = date(year, 12, 25), date(year, 12, 26)
    if xmas.weekday() == 5:          # Sat: Christmas Mon 27, Boxing Tue 28
        xmas_o, box_o = date(year, 12, 27), date(year, 12, 28)
    elif xmas.weekday() == 6:        # Sun: Christmas Mon 26, Boxing Tue 27
        xmas_o, box_o = date(year, 12, 26), date(year, 12, 27)
    elif xmas.weekday() == 4:        # Fri: Boxing Day falls Sat, observed Mon 28
        xmas_o, box_o = xmas, date(year, 12, 28)
    else:
        xmas_o, box_o = xmas, boxing
    h[xmas_o] = "Christmas Day"
    h[box_o] = "Boxing Day"
    return h


class TSXCalendar(NYSECalendar):
    """Toronto Stock Exchange regular session, 09:30-16:00 Toronto time (same clock as New York).
    Early close at 13:00 on Christmas Eve when it is a trading day. TMX publishes one-off
    changes each year; rules here cover the recurring schedule only."""
    name = "XTSE"

    def is_trading_day(self, d: date) -> bool:
        return d.weekday() < 5 and d not in tsx_holidays(d.year)

    def session_on(self, d: date) -> Optional[Session]:
        if not self.is_trading_day(d):
            return None
        early = d.month == 12 and d.day == 24
        o = ny_to_utc_ms(datetime(d.year, d.month, d.day, 9, 30))
        c = ny_to_utc_ms(datetime(d.year, d.month, d.day, 13 if early else 16, 0))
        return Session(d, o, c, early)


def is_equity(asset_type: str) -> bool:
    return asset_type in ("stock", "etf", "stock_ca", "etf_ca")


class CryptoCalendar(Calendar):
    """24/7. A 'session' is the UTC calendar day; day-trading exits are due at 23:55 UTC."""
    name = "CRYPTO-UTC"
    DAY_END_BUFFER_MS = 5 * MINUTE

    def session_for(self, ms: int) -> Session:
        d = to_dt(ms).date()
        start = to_ms(datetime(d.year, d.month, d.day, tzinfo=timezone.utc))
        return Session(d, start, start + DAY, False)

    def trading_day(self, ms: int) -> date:
        return to_dt(ms).date()


CALENDARS: Dict[str, Calendar] = {"XNYS": NYSECalendar(), "XTSE": TSXCalendar(), "CRYPTO-UTC": CryptoCalendar()}


def calendar_for(asset_type: str) -> Calendar:
    if asset_type in ("stock_ca", "etf_ca"):
        return CALENDARS["XTSE"]
    return CALENDARS["XNYS"] if asset_type in ("stock", "etf") else CALENDARS["CRYPTO-UTC"]


def day_trade_exit_time(asset_type: str, ms: int) -> int:
    """The latest time a day-trading position opened at `ms` may be held."""
    cal = calendar_for(asset_type)
    s = cal.session_for(ms)
    if isinstance(cal, NYSECalendar):
        if s is None or not s.contains(ms):
            s = cal.next_session(ms)
        return s.close_ms - 5 * MINUTE              # flat 5 minutes before the bell
    return s.close_ms - CryptoCalendar.DAY_END_BUFFER_MS
