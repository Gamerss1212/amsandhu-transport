"""Day-trading operating mode (owner's specification, revision 13, "DAY-TRADING OPERATING MODE").

Intraday is the active operating mode. Every candidate has a declared entry window, an end-of-session entry cutoff,
a flattening deadline and, for crypto, a rolling maximum hold. The SAME rules are applied in research (the backtester
calls `masks`) and in paper trading (the orchestrator calls `entry_check` and `exit_due`), so a strategy qualifies
only under the rules it will trade with. A method whose source horizon is longer than a day (daily bars, monthly
portfolio rebalances) produces no trades under these rules and therefore stays research-only; changing its holding
period would not inherit the original method's evidence.

Rules (times are exchange local; the timezone is part of each rule):
  stocks and ETFs (NYSE calendar, America/New_York): entries from 09:35 until 30 minutes before the close
      (15:30, or 12:30 on early-close days); flat by 10 minutes before the close.
  CME futures (America/New_York): entries until 16:15; flat by 16:45, before the 17:00 daily halt.
  forex (America/New_York): entries until 16:30; flat by 16:50, before the 17:00 rollover; closed at the weekend.
  crypto (UTC): rolling maximum hold of 24 hours; daily risk cutoff at 00:00 UTC, no new entries from 23:00 UTC.
A decision is taken at a bar's close and fills at the next bar's open, so "flat by" means: exit now if waiting for the
next bar would cross the deadline.
"""

from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
from typing import Optional
from zoneinfo import ZoneInfo

import numpy as np

from tradingai.market.calendars import nyse_early_closes, session

MODE = "intraday"
NY = ZoneInfo("America/New_York")
CRYPTO_MAX_HOLD_MS = 24 * 3_600_000
RULES = {
    "XNYS": {"timezone": "America/New_York", "entry_window": "09:35 to 30 min before the close",
             "entry_cutoff": "30 min before the close (15:30; 12:30 on early-close days)",
             "flatten": "10 min before the close (15:50; 12:50 on early-close days)", "max_hold": "same session"},
    "CME": {"timezone": "America/New_York", "entry_window": "18:00 to 16:15", "entry_cutoff": "16:15",
            "flatten": "16:45 (before the 17:00 daily halt)", "max_hold": "same Globex session"},
    "FX": {"timezone": "America/New_York", "entry_window": "17:00 to 16:30 (Sunday to Friday)", "entry_cutoff": "16:30",
           "flatten": "16:50 (before the 17:00 rollover)", "max_hold": "same value day"},
    "CRYPTO": {"timezone": "UTC", "entry_window": "00:00 to 23:00", "entry_cutoff": "23:00 (daily risk cutoff 00:00)",
               "flatten": "rolling: 24 hours after entry", "max_hold": "24 hours"},
}
_CME_CUT, _CME_FLAT, _FX_CUT, _FX_FLAT = 16 * 60 + 15, 16 * 60 + 45, 16 * 60 + 30, 16 * 60 + 50


def _ny(ms: int) -> datetime:
    return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).astimezone(NY)


def _deadline(calendar: str, ms: int) -> Optional[int]:
    """The flattening deadline (epoch ms) of the session that contains `ms`; None for crypto or a closed market."""
    if calendar == "XNYS":
        if not session("XNYS", ms)["open"]:
            return None
        d = _ny(ms).date()
        close_t = time(13, 0) if d in nyse_early_closes(d.year) else time(16, 0)
        return int(datetime.combine(d, close_t, NY).timestamp() * 1000) - 600_000
    if calendar in ("CME", "FX"):
        n = _ny(ms)
        hm = n.hour * 60 + n.minute
        day = n.date() if hm < 17 * 60 else n.date() + timedelta(days=1)
        flat = _CME_FLAT if calendar == "CME" else _FX_FLAT
        return int(datetime.combine(day, time(flat // 60, flat % 60), NY).timestamp() * 1000)
    return None


def entry_check(calendar: str, ms: int) -> tuple[bool, str, str]:
    """May a NEW position be opened at this instant? (ok, reason code, detail)."""
    cal = calendar or "CRYPTO"
    if cal == "CRYPTO":
        t = datetime.fromtimestamp(ms / 1000, tz=timezone.utc)
        if t.hour >= 23:
            return False, "ENTRY_CUTOFF", "crypto daily risk cutoff: no new entries 23:00-00:00 UTC"
        return True, "OK", "inside the entry window"
    s = session(cal, ms)
    if not s["open"]:
        return False, "MARKET_CLOSED", f"{cal} session {s.get('session')}"
    if cal == "XNYS":
        if (s["minutes_from_open"] or 0) < 5:
            return False, "OUTSIDE_ENTRY_WINDOW", "first 5 minutes after the open"
        if (s["minutes_to_close"] or 0) <= 30:
            return False, "ENTRY_CUTOFF", "less than 30 minutes before the close"
        return True, "OK", "inside the entry window"
    n = _ny(ms)
    hm = n.hour * 60 + n.minute
    cut = _CME_CUT if cal == "CME" else _FX_CUT
    if cut <= hm < 18 * 60:
        return False, "ENTRY_CUTOFF", f"after the {cut // 60}:{cut % 60:02d} New York entry cutoff"
    return True, "OK", "inside the entry window"


def exit_due(calendar: str, opened_ms: Optional[int], ms: int, bar_ms: int) -> Optional[tuple[str, str]]:
    """Must an open position be closed now? Returns (reason code, detail) or None."""
    cal = calendar or "CRYPTO"
    if cal == "CRYPTO":
        if opened_ms is not None and ms - opened_ms + bar_ms > CRYPTO_MAX_HOLD_MS:
            return "MAX_HOLD", "24-hour maximum hold reached"
        return None
    dl = _deadline(cal, ms)
    if dl is None:
        return "SESSION_FLATTEN", "held outside its session: close at the next open"
    if ms + bar_ms > dl:
        return "SESSION_FLATTEN", "the next decision would come after the flattening deadline"
    if opened_ms is not None and _deadline(cal, opened_ms) not in (None, dl):
        return "SESSION_FLATTEN", "opened in an earlier session"
    return None


_cache: dict[tuple, dict[int, tuple[bool, bool]]] = {}


def masks(ts: np.ndarray, bar_ms: int, calendar: str) -> tuple[np.ndarray, np.ndarray, Optional[int]]:
    """For a backtest: per bar (decision at the bar's close), whether a new entry is blocked and whether a position must
    be closed for the session; plus the rolling maximum hold in ms (crypto). Answers are cached per timestamp, so the
    many slices of one research run reuse them."""
    cal = calendar or "CRYPTO"
    memo = _cache.setdefault((cal, int(bar_ms)), {})
    if len(memo) > 400_000:
        memo.clear()
    n = len(ts)
    no_entry = np.zeros(n, dtype=bool)
    flat = np.zeros(n, dtype=bool)
    for i in range(n):
        t = int(ts[i]) + int(bar_ms)
        v = memo.get(t)
        if v is None:
            v = memo[t] = (not entry_check(cal, t)[0],
                           cal != "CRYPTO" and exit_due(cal, None, t, int(bar_ms)) is not None)
        no_entry[i], flat[i] = v
    return no_entry, flat, CRYPTO_MAX_HOLD_MS if cal == "CRYPTO" else None


def describe() -> dict:
    # only the rules of the markets that are traded; the CME and FX rules stay in the engine but are not shown or used
    return {"mode": MODE, "rules": {k: v for k, v in RULES.items() if k in ("XNYS", "CRYPTO")},
            "note": "Rules apply identically in research and paper trading. Methods with longer source horizons "
                    "(daily bars, monthly portfolios) stay research-only in this mode."}
