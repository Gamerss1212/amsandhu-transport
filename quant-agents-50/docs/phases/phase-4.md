# Phase 4: Context, aggregation and scoring (completes the 25-agent core)

**Core agents in this phase:** A06, A07, A13, A15, A35, A47. **All built and tested.**
`phase: 4` is the default in `config/default.yaml`, so all 25 core agents run every cycle.
**Goal:** agents are scored, calibrated and pooled by skill and independence, on real data.
**Spec sections to read:** 12-17, 27, 28, 43, 67, 79, 81, 93.

## Already in the kit

- A06 regime (mixture + sticky HMM checked by BIC, volatility vs its norm, breadth, crisis odds).
- A07 transition alert (Bayesian change points, volatility breakout, correlation jump, regime jump, liquidity drain). An alert puts A49 in REDUCED.
- A13 breakouts and A15 trend exhaustion, both in **shadow** (scored, no vote).
- A35 scorekeeper: scores matured predictions only, counts overlapping forecasts honestly, tempers over-confident agents, proposes weights, reports promotion readiness.
- A47 two-stage pooling with A35's calibration, weights and N_eff.

## Build

1. Run 60+ paper days on real data so A35 has matured predictions to score.
2. Review A35's scorecards with the owner. A shadow agent is ready for a promotion review only when A35 says so (200+ scored, 30+ independent outcomes, skill t-stat 2+).
3. If the owner approves, change that agent's `state` to `probation` in `config/agents.yaml` and log the approval in `docs/STATUS.md`.
4. Optional: replace A06's turbulence vote with a full Gaussian HMM fit by EM if A35 shows the current one adds nothing.

## Acceptance (spec section 83)

- [ ] All outputs are schema-valid
- [ ] Brier score tracked per agent
- [ ] Pooled Brier at least as good as the best single agent
