"""Market calendars (section 136). Everything inside the system is UTC milliseconds; the exchange's own time zone is
used only to decide sessions, with real time-zone rules (daylight saving included) from the IANA database (`tzdata`
is shipped, because Windows has no IANA database of its own).

* XNYS (US stocks and ETFs): pre-market 04:00, regular 09:30-16:00, after-hours to 20:00 New York time; full-day
  holidays and 13:00 early closes from the exchange's published rules.
* CRYPTO: 24/7 (the venue's maintenance windows are not modelled).
* FX: Sunday 17:00 to Friday 17:00 New York time; Sydney, Tokyo, London and New York sessions in their local time.
* CME (Globex futures): Sunday to Friday 18:00-17:00 New York time with the daily 17:00-18:00 maintenance break.
  Holiday hours are approximated by the NYSE holidays (CME usually halts early on those days); the label says so.
* Equity-index futures expire on the third Friday of March, June, September and December; the roll date used here is
  8 calendar days before expiry (the usual Thursday roll).
"""

from __future__ import annotations

from datetime import date, datetime, time, timedelta, timezone
from functools import lru_cache
from zoneinfo import ZoneInfo

NY = ZoneInfo("America/New_York")
UTC = timezone.utc
SESSIONS_FX = {"sydney": ("Australia/Sydney", 7, 16), "tokyo": ("Asia/Tokyo", 9, 18),
               "london": ("Europe/London", 8, 17), "new_york": ("America/New_York", 8, 17)}


def utc(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=UTC)


def to_ms(dt: datetime) -> int:
    if dt.tzinfo is None:
        raise ValueError("naive datetimes are not compared here: attach a time zone")
    return int(dt.timestamp() * 1000)


# ----------------------------------------------------------------------------- NYSE holidays (published rules)

def _easter(y: int) -> date:
    a, b, c = y % 19, y // 100, y % 100
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    m = (32 + 2 * e + 2 * i - h - k) % 7
    n = (a + 11 * h + 22 * m) // 451
    month, day = divmod(h + m - 7 * n + 114, 31)
    return date(y, month, day + 1)


def _nth_weekday(y: int, month: int, weekday: int, n: int) -> date:
    d = date(y, month, 1)
    d += timedelta(days=(weekday - d.weekday()) % 7)
    return d + timedelta(weeks=n - 1)


def _last_weekday(y: int, month: int, weekday: int) -> date:
    d = date(y, month + 1, 1) - timedelta(days=1) if month < 12 else date(y, 12, 31)
    return d - timedelta(days=(d.weekday() - weekday) % 7)


def _observed(d: date) -> date | None:
    if d.weekday() == 5:
        prev = d - timedelta(days=1)
        return None if (d.month, d.day) == (1, 1) else prev   # NYSE: a Saturday New Year is not observed on Dec 31
    if d.weekday() == 6:
        return d + timedelta(days=1)
    return d


@lru_cache(maxsize=64)
def nyse_holidays(y: int) -> dict[date, str]:
    out: dict[date, str] = {}

    def add(d: date | None, name: str) -> None:
        if d is not None:
            out[d] = name
    add(_observed(date(y, 1, 1)), "New Year's Day")
    add(_nth_weekday(y, 1, 0, 3), "Martin Luther King Jr. Day")
    add(_nth_weekday(y, 2, 0, 3), "Washington's Birthday")
    add(_easter(y) - timedelta(days=2), "Good Friday")
    add(_last_weekday(y, 5, 0), "Memorial Day")
    if y >= 2022:
        add(_observed(date(y, 6, 19)), "Juneteenth")
    add(_observed(date(y, 7, 4)), "Independence Day")
    add(_nth_weekday(y, 9, 0, 1), "Labor Day")
    add(_nth_weekday(y, 11, 3, 4), "Thanksgiving Day")
    add(_observed(date(y, 12, 25)), "Christmas Day")
    return out


@lru_cache(maxsize=64)
def nyse_early_closes(y: int) -> dict[date, str]:
    """13:00 closes: the day before Independence Day, the day after Thanksgiving, Christmas Eve (weekdays only)."""
    hol = nyse_holidays(y)
    out = {}
    for d, name in ((date(y, 7, 3), "day before Independence Day"),
                    (_nth_weekday(y, 11, 3, 4) + timedelta(days=1), "day after Thanksgiving"),
                    (date(y, 12, 24), "Christmas Eve")):
        if d.weekday() < 5 and d not in hol:
            out[d] = name
    return out


def nyse_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in nyse_holidays(d.year)


# ----------------------------------------------------------------------------- sessions

def session(calendar: str, ms: int) -> dict:
    """What is happening at this instant on this calendar: {"open", "session", "trading_date", "minutes_from_open",
    "minutes_to_close", "note"}. `open` means the regular (or continuous) market accepts trades."""
    t = utc(ms)
    if calendar == "CRYPTO":
        day_start = t.replace(hour=0, minute=0, second=0, microsecond=0)
        return {"open": True, "session": "continuous", "trading_date": t.date().isoformat(),
                "minutes_from_open": int((t - day_start).total_seconds() // 60),
                "minutes_to_close": None, "weekend": t.weekday() >= 5, "note": "24/7 (venue maintenance not modelled)"}
    if calendar == "XNYS":
        n = t.astimezone(NY)
        d = n.date()
        out = {"trading_date": d.isoformat(), "minutes_from_open": None, "minutes_to_close": None, "note": ""}
        if not nyse_trading_day(d):
            out.update(open=False, session="closed", note=nyse_holidays(d.year).get(d, "weekend"))
            return out
        close_t = time(13, 0) if d in nyse_early_closes(d.year) else time(16, 0)
        o = datetime.combine(d, time(9, 30), NY)
        c = datetime.combine(d, close_t, NY)
        if n < datetime.combine(d, time(4, 0), NY):
            out.update(open=False, session="closed")
        elif n < o:
            out.update(open=False, session="pre_market", minutes_to_close=None)
        elif n < c:
            out.update(open=True, session="regular", minutes_from_open=int((n - o).total_seconds() // 60),
                       minutes_to_close=int((c - n).total_seconds() // 60),
                       note="early close 13:00" if close_t.hour == 13 else "")
        elif n < datetime.combine(d, time(20, 0), NY) and close_t.hour == 16:
            out.update(open=False, session="after_hours")
        else:
            out.update(open=False, session="closed")
        return out
    if calendar == "FX":
        n = t.astimezone(NY)
        wd, hm = n.weekday(), n.hour * 60 + n.minute
        closed = (wd == 5) or (wd == 4 and hm >= 17 * 60) or (wd == 6 and hm < 17 * 60)
        tags = fx_sessions(ms)
        return {"open": not closed, "session": "closed" if closed else "+".join(tags) or "between_sessions",
                "trading_date": (n + timedelta(hours=7)).date().isoformat(),   # FX value day rolls at 17:00 NY
                "minutes_from_open": None, "minutes_to_close": None,
                "rollover_window": (not closed) and abs(hm - 17 * 60) <= 15,
                "note": "spreads usually widen around the 17:00 New York rollover"}
    if calendar == "CME":
        n = t.astimezone(NY)
        wd, hm = n.weekday(), n.hour * 60 + n.minute
        weekend = (wd == 5) or (wd == 4 and hm >= 17 * 60) or (wd == 6 and hm < 18 * 60)
        maint = (not weekend) and 17 * 60 <= hm < 18 * 60
        hol = nyse_holidays(n.date().year).get(n.date())
        return {"open": not (weekend or maint), "session": "closed" if weekend else "maintenance" if maint else
                ("regular_hours" if nyse_trading_day(n.date()) and 9 * 60 + 30 <= hm < 16 * 60 else "overnight"),
                "trading_date": (n + timedelta(hours=6)).date().isoformat(),   # Globex day starts at 18:00 NY
                "minutes_from_open": None, "minutes_to_close": None,
                "note": f"US holiday ({hol}): CME hours are shortened, check the exchange" if hol else
                "holiday hours approximated by NYSE holidays"}
    raise KeyError(f"unknown calendar {calendar!r}")


def fx_sessions(ms: int) -> list[str]:
    t = utc(ms)
    out = []
    for name, (tz, start, end) in SESSIONS_FX.items():
        local = t.astimezone(ZoneInfo(tz))
        if local.weekday() < 5 and start <= local.hour < end:
            out.append(name)
    return out


# ----------------------------------------------------------------------------- equity-index futures expiry and roll

QUARTER_MONTHS = (3, 6, 9, 12)
MONTH_CODES = {3: "H", 6: "M", 9: "U", 12: "Z"}


def equity_index_expiry(year: int, month: int) -> date:
    """Third Friday of the contract month (moved to the previous trading day if that Friday is a holiday)."""
    if month not in QUARTER_MONTHS:
        raise ValueError("equity-index futures are quarterly: March, June, September, December")
    d = _nth_weekday(year, month, 4, 3)
    while not nyse_trading_day(d):
        d -= timedelta(days=1)
    return d


def equity_index_front(day: date, roll_days_before: int = 8) -> tuple[str, date, date]:
    """(contract month 'YYYY-MM', its expiry, its roll date) of the contract to hold on `day`."""
    y, m = day.year, day.month
    while True:
        q = next((q for q in QUARTER_MONTHS if q >= m), None)
        if q is None:
            y, m = y + 1, 1
            continue
        exp = equity_index_expiry(y, q)
        roll = exp - timedelta(days=roll_days_before)
        if day < roll:
            return f"{y}-{q:02d}", exp, roll
        y, m = (y + 1, 1) if q == 12 else (y, q + 1)


def in_roll_window(day: date, days: int = 8) -> bool:
    """True from the roll date to expiry: a continuous series jumps here, so the paper engine stays flat."""
    for q in QUARTER_MONTHS:
        e = equity_index_expiry(day.year, q)
        if e - timedelta(days=days) <= day <= e:
            return True
    return False
