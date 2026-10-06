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

- [ ] 100% branch coverage on risk logic (the gate already enforces it)
- [ ] Chaos tests pass
- [ ] 30 paper days with zero A49 breaches and no reconciliation break
- [ ] Kill switch tested this week
