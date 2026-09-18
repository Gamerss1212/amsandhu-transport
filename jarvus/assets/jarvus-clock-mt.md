# Jarvus Clock — Mountain Time (Edmonton)

Every reference file in this skill quotes times in UTC (US summer). Abhi works in
Mountain Time: **MDT = UTC−6** (second Sunday of March → first Sunday of November),
**MST = UTC−7** the rest of the year. New-York-linked events (data releases, US
open/close, FOMC, old CME hours) keep the same MT clock time all year because they
shift with US daylight saving; UTC-fixed events (daily close, funding settlements)
move one hour earlier in MT during winter.

| Event | UTC summer / winter | MT (year-round unless noted) |
|---|---|---|
| Daily candle close/open · funding settlement · Asia session starts | 00:00 | 6:00 PM MDT / 5:00 PM MST |
| Asia session | 00:00–07:00 | 6 PM–1 AM MDT / 5 PM–midnight MST |
| London open (first real directional attempt; sweeps the Asia high/low) | 07:00 / 08:00 UK winter | ~1:00 AM |
| Funding settlement · Deribit daily expiry (monthly: last Friday) | 08:00 | 2:00 AM MDT / 1:00 AM MST |
| CPI / NFP (tier-1; 08:30 New York) | 12:30 / 13:30 | 6:30 AM |
| **US equities open · ORB window · Nasdaq correlation spike** | 13:30 / 14:30 | **7:30 AM** |
| **London / New York overlap (best liquidity, trends, breakouts)** | 13:30–16:00 / 14:30–17:00 | **7:30–10:00 AM** |
| High-Probability Program session (first 3 hours of NY) | 13:30–16:30 | 7:30–10:30 AM |
| Funding settlement · London close · lull begins | 16:00 | 10:00 AM MDT / 9:00 AM MST |
| FOMC decision (14:00 NY) · press conference (14:30 NY) | 18:00 / 19:00 · 18:30 / 19:30 | 12:00 PM · 12:30 PM |
| US equities close (volume drains) | 20:00 / 21:00 | 2:00 PM |
| Late US session (thin) | 19:00–24:00 | 1:00–6:00 PM |
| Dead zone (v3 rule: avoid) | — | 7:00 PM–12:00 AM |
| Old CME weekend close (legacy — see note) | Fri 21:00 / 22:00 | Fri 3:00 PM |
| Old CME weekend reopen (legacy) | Sun 22:00 / 23:00 | Sun 4:00 PM |

**CME note.** Abhi's Sept 2026 research says CME crypto futures went 24/7 on
May 29 2026, which erodes the weekend-gap edge. The bundled `scripts/events.py`
and the references still print the old weekend close/reopen. Treat the gap fill as
a decaying bias, pair it with a real trigger, and verify the current CME schedule
before leaning on it.

**Rules in MT**
- Best trading window: 7:30 AM–2:00 PM MT. Momentum from the first 2 hours, reversal
  tendency in the last 2 hours.
- Flat from 30 minutes before a tier-1 release until the first move and its retrace
  are done (usually 15–30 minutes after). Flat through the whole FOMC presser.
- Confluence factor 7 (session) scores a point only for 7:30–10:00 AM MT or the
  first 90 minutes after 7:30 AM; not late US, not Asia, not weekend.
- `python3 scripts/events.py` prints the next tier-1 release, session opens, funding
  and CME times in UTC; subtract 6 (MDT) or 7 (MST) hours.
