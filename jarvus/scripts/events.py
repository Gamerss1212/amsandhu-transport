#!/usr/bin/env python3
"""Scheduled-event awareness: tier-1 macro releases, session opens, funding, CME hours.

  python3 events.py                 # what is coming up, from now
  python3 events.py --now 2026-10-14T11:00:00Z --hours 72

Used by snapshot.py and scan.py to warn when a tier-1 release is close. Dates for
FOMC decisions come from federalreserve.gov, CPI and Employment Situation dates from
bls.gov (2026 schedules, verified 2026-09-16). Times are converted to UTC with US
daylight-saving rules applied, because 08:30 New York is 12:30 UTC in summer and
13:30 UTC in winter. Update the lists each December; if a year is missing, the
script says so instead of guessing.
"""

from __future__ import annotations

import argparse
from datetime import date, datetime, timedelta, timezone
from typing import List, Tuple

# ----------------------------------------------------------- source data ---
# FOMC: the DECISION day (second day of the meeting). Statement 14:00 ET, presser 14:30 ET.
FOMC_DECISIONS = {
    2026: ["01-28", "03-18", "04-29", "06-17", "07-29", "09-16", "10-28", "12-09"],
    2027: ["01-27", "03-17", "04-28", "06-09", "07-28", "09-15", "10-27", "12-08"],
}
# CPI and Employment Situation (NFP): 08:30 ET.
CPI_RELEASES = {2026: ["01-13", "02-13", "03-11", "04-10", "05-12", "06-10", "07-14", "08-12", "09-11", "10-14", "11-10", "12-10"]}
NFP_RELEASES = {2026: ["01-09", "02-11", "03-06", "04-03", "05-08", "06-05", "07-02", "08-07", "09-04", "10-02", "11-06", "12-04"]}


# ----------------------------------------------------------- DST helpers ---

def _nth_sunday(year: int, month: int, n: int) -> date:
    d = date(year, month, 1)
    first_sunday = d + timedelta(days=(6 - d.weekday()) % 7)
    return first_sunday + timedelta(weeks=n - 1)


def _last_sunday(year: int, month: int) -> date:
    d = date(year, month + 1, 1) - timedelta(days=1) if month < 12 else date(year, 12, 31)
    return d - timedelta(days=(d.weekday() + 1) % 7)


def us_dst(d: date) -> bool:
    """US daylight time: second Sunday of March to first Sunday of November."""
    return _nth_sunday(d.year, 3, 2) <= d < _nth_sunday(d.year, 11, 1)


def uk_dst(d: date) -> bool:
    """British Summer Time: last Sunday of March to last Sunday of October."""
    return _last_sunday(d.year, 3) <= d < _last_sunday(d.year, 10)


def et_to_utc(d: date, hour: int, minute: int = 0) -> datetime:
    offset = 4 if us_dst(d) else 5
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc) + timedelta(hours=offset)


def london_to_utc(d: date, hour: int, minute: int = 0) -> datetime:
    offset = 1 if uk_dst(d) else 0
    return datetime(d.year, d.month, d.day, hour, minute, tzinfo=timezone.utc) - timedelta(hours=offset)


# ---------------------------------------------------------------- events ---

def tier1_events(year: int) -> List[Tuple[datetime, str, str]]:
    """(utc_datetime, name, tier) for one year. Empty list if the year is not loaded."""
    out = []
    for md in FOMC_DECISIONS.get(year, []):
        d = date(year, int(md[:2]), int(md[3:]))
        out.append((et_to_utc(d, 14, 0), "FOMC rate decision (presser 30 min later)", "tier1"))
    for md in CPI_RELEASES.get(year, []):
        d = date(year, int(md[:2]), int(md[3:]))
        out.append((et_to_utc(d, 8, 30), "US CPI", "tier1"))
    for md in NFP_RELEASES.get(year, []):
        d = date(year, int(md[:2]), int(md[3:]))
        out.append((et_to_utc(d, 8, 30), "US Employment Situation (NFP)", "tier1"))
    return out


def recurring_events(now: datetime, hours: float) -> List[Tuple[datetime, str, str]]:
    """Session opens/closes, funding, CME hours, daily close within the window."""
    out = []
    day = now.date() - timedelta(days=1)
    end = now + timedelta(hours=hours)
    while datetime(day.year, day.month, day.day, tzinfo=timezone.utc) <= end:
        wd = day.weekday()
        out.append((datetime(day.year, day.month, day.day, tzinfo=timezone.utc), "daily close/open + funding (00:00 UTC)", "clock"))
        out.append((datetime(day.year, day.month, day.day, 8, tzinfo=timezone.utc), "funding settlement + Deribit expiry (08:00 UTC)", "clock"))
        out.append((datetime(day.year, day.month, day.day, 16, tzinfo=timezone.utc), "funding settlement (16:00 UTC)", "clock"))
        if wd < 5:
            out.append((london_to_utc(day, 8, 0), "London open", "session"))
            out.append((et_to_utc(day, 9, 30), "US equities open", "session"))
            out.append((et_to_utc(day, 16, 0), "US equities close", "session"))
        if wd == 4:
            out.append((et_to_utc(day, 17, 0), "CME closes for the weekend", "session"))
        if wd == 6:
            out.append((et_to_utc(day, 18, 0), "CME reopens (weekend gap set)", "session"))
        day += timedelta(days=1)
    return [e for e in out if now <= e[0] <= end]


def upcoming(now: datetime, hours: float = 48.0) -> List[dict]:
    evs = []
    for y in (now.year, now.year + 1):
        evs += tier1_events(y)
    evs = [e for e in evs if now <= e[0] <= now + timedelta(hours=hours)]
    evs += recurring_events(now, hours)
    evs.sort(key=lambda e: e[0])
    return [{"utc": e[0].strftime("%Y-%m-%d %H:%M"), "in_minutes": int((e[0] - now).total_seconds() // 60),
             "event": e[1], "tier": e[2]} for e in evs]


def next_tier1(now: datetime) -> dict:
    evs = [e for y in (now.year, now.year + 1) for e in tier1_events(y) if e[0] >= now - timedelta(minutes=45)]
    if not evs:
        return {"loaded": False, "note": f"no tier-1 calendar loaded for {now.year}; check bls.gov and federalreserve.gov"}
    evs.sort(key=lambda e: e[0])
    e = evs[0]
    mins = int((e[0] - now).total_seconds() // 60)
    return {"loaded": True, "event": e[1], "utc": e[0].strftime("%Y-%m-%d %H:%M"), "in_minutes": mins,
            "inside_no_trade_window": -45 <= mins <= 30,
            "warning": (f"{e[1]} at {e[0].strftime('%H:%M')} UTC is {abs(mins)} min {'away' if mins >= 0 else 'ago'}: "
                        "no new trades from 30 min before until the first move and its retrace are done")
            if -45 <= mins <= 30 else None}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--now", help="ISO UTC, e.g. 2026-10-14T11:00:00Z")
    ap.add_argument("--hours", type=float, default=48)
    a = ap.parse_args()
    now = datetime.strptime(a.now, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc) if a.now else datetime.now(timezone.utc)
    print(f"now {now.strftime('%Y-%m-%d %H:%M')} UTC  (US {'EDT, UTC-4' if us_dst(now.date()) else 'EST, UTC-5'}; "
          f"London {'BST, UTC+1' if uk_dst(now.date()) else 'GMT, UTC+0'})")
    t1 = next_tier1(now)
    if t1.get("loaded"):
        print(f"next tier-1: {t1['event']} at {t1['utc']} UTC ({t1['in_minutes']} min)")
        if t1["warning"]:
            print("WARNING: " + t1["warning"])
    else:
        print("WARNING: " + t1["note"])
    print(f"\nnext {a.hours:g} hours:")
    for e in upcoming(now, a.hours):
        h, m = divmod(e["in_minutes"], 60)
        print(f"  {e['utc']} UTC  (+{h:>2}h{m:02d})  [{e['tier']:<7}] {e['event']}")


if __name__ == "__main__":
    try:
        main()
    except BrokenPipeError:
        pass
