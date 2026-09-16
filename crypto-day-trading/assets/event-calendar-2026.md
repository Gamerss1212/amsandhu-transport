# Tier-1 Event Calendar 2026

Verified 2026-09-16 against federalreserve.gov (FOMC) and bls.gov (CPI, Employment
Situation). `scripts/events.py` holds the same dates and prints what is coming up.
Rule: no new trades from 30 minutes before a tier-1 release until the first move
and its retrace are done (usually 15-30 minutes after). Flat through FOMC pressers.

US times are New York local. UTC is one hour later in US winter time (before
March 8 and from November 1, 2026).

## FOMC rate decisions (statement 14:00 NY, press conference 14:30 NY)

| Date | UTC | Notes |
|---|---|---|
| Jan 28 (Wed) | 19:00 | |
| Mar 18 (Wed) | 18:00 | with economic projections (dot plot) |
| Apr 29 (Wed) | 18:00 | |
| Jun 17 (Wed) | 18:00 | with projections |
| Jul 29 (Wed) | 18:00 | |
| Sep 16 (Wed) | 18:00 | with projections |
| Oct 28 (Wed) | 18:00 | |
| Dec 9 (Wed) | 19:00 | with projections |

2027: Jan 27, Mar 17, Apr 28, Jun 9, Jul 28, Sep 15, Oct 27, Dec 8.

## US CPI (08:30 NY)

| Reference month | Release | UTC |
|---|---|---|
| Dec 2025 | Jan 13 | 13:30 |
| Jan | Feb 13 | 13:30 |
| Feb | Mar 11 | 12:30 |
| Mar | Apr 10 | 12:30 |
| Apr | May 12 | 12:30 |
| May | Jun 10 | 12:30 |
| Jun | Jul 14 | 12:30 |
| Jul | Aug 12 | 12:30 |
| Aug | Sep 11 | 12:30 |
| Sep | Oct 14 | 12:30 |
| Oct | Nov 10 | 13:30 |
| Nov | Dec 10 | 13:30 |

## US Employment Situation / nonfarm payrolls (08:30 NY)

| Reference month | Release | UTC |
|---|---|---|
| Dec 2025 | Jan 9 | 13:30 |
| Jan | Feb 11 | 13:30 |
| Feb | Mar 6 | 13:30 |
| Mar | Apr 3 | 12:30 |
| Apr | May 8 | 12:30 |
| May | Jun 5 | 12:30 |
| Jun | Jul 2 | 12:30 |
| Jul | Aug 7 | 12:30 |
| Aug | Sep 4 | 12:30 |
| Sep | Oct 2 | 12:30 |
| Oct | Nov 6 | 13:30 |
| Nov | Dec 4 | 13:30 |

## Recurring (every day unless noted, fixed UTC)

| UTC | Event |
|---|---|
| 00:00 | Daily candle close/open on most exchanges; funding settlement |
| 08:00 | Funding settlement; Deribit daily options expiry (monthly expiry: last Friday of the month) |
| 16:00 | Funding settlement |
| 07:00 (08:00 in UK winter) | London open |
| 13:30 (14:30 in US winter) | US equities open |
| 20:00 (21:00 in US winter) | US equities close |
| Fri 21:00 (22:00 winter) | CME Bitcoin futures close for the weekend |
| Sun 22:00 (23:00 winter) | CME reopens; the weekend gap is set |

## Second-tier US data worth knowing (08:30 NY unless noted)

PPI (day after or near CPI), retail sales (mid-month), PCE (last week of the month,
the Fed's preferred inflation gauge), jobless claims (every Thursday), ISM
manufacturing (first business day, 10:00 NY), ISM services (third business day,
10:00 NY), GDP (end of month, quarterly). These move price less reliably than the
tier-1 releases but PCE and ISM can. Check a macro calendar (for example
ForexFactory) for the exact dates each week.

## Crypto-specific, per asset

- Token unlocks: check TokenUnlocks / Tokenomist for anything held overnight.
- Exchange listings and delistings: unscheduled; treat as news.
- ETF flow reports: published after the US close; set next-day sentiment.
- Protocol upgrades and mainnet dates: from the project's own channels.
