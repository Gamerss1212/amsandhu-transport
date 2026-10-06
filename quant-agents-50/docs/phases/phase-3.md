# Phase 3: Risk, execution and paper trading

**Core agents in this phase:** A05, A09, A39, A45, A48, A49, A50. **All built and tested.**
**Goal:** 30 days of daily paper trading with zero risk breaches.
**Spec sections to read:** 18, 44-53, 62, 65, 77, 78, 93.

## Already in the kit

- A49 risk governor with 100% branch coverage, and the kill switch.
- A48 sizing, A50 paper broker (next-open fills, stops, gaps), A05 ledger and reconciliation, A39 red team.
- A09 liquidity: square-root impact, a 1%-of-daily-value cap per order, worst-case cost when unmeasurable.
- A45 stress: six scenarios, VaR and ES, a 20-day Monte Carlo; it shrinks new entries to stay inside the daily loss limit, then re-checks the book actually sent.
- `python -m quantagents cycle --data <csv>` runs one paper day; `simulate --days 120` runs many in a row.
- `python -m quantagents stress --strategy tsmom` runs A45's Monte Carlo and the 2x-cost stress on a strategy.

## Build

1. **Chaos tests:** stale data, duplicate fills, a dropped broker, a corrupted kill-switch file (crashing agents are already covered for A06, A07, A09, A11 and A45).
2. **Watchdog:** a small separate script that checks the last cycle time and data staleness, and engages the kill switch if needed.
3. **Real data:** a CSV from the owner's data source (point in time, adjusted, no survivorship bias). Check that A02 passes it.
4. **Paper broker adapter (optional):** IBKR paper through `ib_async`, or Alpaca paper. Keys live in `.env` (the owner adds them). Paper endpoints only.
5. **Daily schedule:** run the cycle after the close every trading day (Windows Task Scheduler or cron) for 30 trading days.

## Owner does

- Approves the schedule. Creates paper-account keys if a broker paper account is used: trade-only, withdrawals disabled.

## Acceptance (spec section 83)

- [x] 100% branch coverage on risk logic (the gate already enforces it)
- [x] Chaos tests pass (`tests/test_chaos.py`: stale data, duplicate fills, dropped broker, corrupted kill switch)
- [ ] 30 paper days with zero A49 breaches and no reconciliation break (needs about six weeks of calendar time on the owner's PC; see `docs/schedule.md`)
- [ ] Kill switch tested this week (automated tests pass; the owner tests it by hand each week of the paper run)

## Built (2026-10-06)

- Chaos: the cycle survives a broker that drops before the open or at submit. It records a
  reconciliation break, engages the kill switch and sends nothing. A02 blocks a stale feed (a last
  bar that copies the one before).
- Watchdog: `quantagents watchdog` and `scripts/watchdog.py`. It can only engage the switch.
- Daily run: `quantagents daily` (fetch, export, cycle, watchdog), and it never runs a day twice.
  Schedule guide: `docs/schedule.md`.
- Real data through A02: the 8-ETF universe (`config/us_etfs.example.yaml`) scored 100/100
  with nothing blocked. Across 3,608 sampled days of real history in three universes, A02
  blocked nothing (no false split or stale alarms).
- Broker paper adapter (optional): not built. It needs the owner's paper-account keys in `.env`.
