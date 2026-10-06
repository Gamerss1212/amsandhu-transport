# Phase 7: Full 50-agent system in paper and shadow

**Optional.** The 25-agent core is complete without this phase. These agents are parked in `config/agents.yaml` (`core: false`). Build one only when you have the data it needs and a reason to expect new information; each starts in shadow (spec section 93).

**Agents added:** A20, A32, A42.
**Goal:** all 50 agents run together on live data with simulated orders.
**Spec sections to read:** 17, 18, 22, 65, 66, 77.

## Build

1. A20 stat-arb residuals (needs shorting; FUTURE for small accounts), A32 deep sequence forecaster (GPU optional), A42 strategy evolution (every candidate logged as a trial).
2. Tests for quorum and every step of the degradation ladder.
3. Herding test: clone one agent 10 times; N_eff must not rise.
4. Shadow trading: live data, simulated orders against real quotes, for 60 days. Replay each day through the backtester and compare (section 66).

## Acceptance (spec section 83)

- [ ] All 50 agents registered and healthy
- [ ] Quorum and degradation ladder tested
- [ ] Herding test passes
- [ ] 60 shadow days with live-vs-backtest divergence under 1 standard deviation
