# Phase 5: Expanded signals and machine learning (40 agents)

**Optional.** The 25-agent core is complete without this phase. These agents are parked in `config/agents.yaml` (`core: false`). Build one only when you have the data it needs and a reason to expect new information; each starts in shadow (spec section 93).

**Agents added:** A04, A14, A17, A19, A22, A24, A27, A28, A29, A31, A33, A34, A41.
**Goal:** more independent information, each agent proving its value in shadow mode first.
**Spec sections to read:** 15, 17, 25, 29-36, 40-42, 61, 67, Appendix A.

## Build (one agent at a time with `/new-agent`)

- **ML:** A31 gradient boosting (LightGBM or XGBoost) with purged CV and an embargo; A33 meta-labeling; A34 novelty and drift (PSI, KS test, Mahalanobis), which halves ML weights when markets look unusual.
- **Signals:** A17 range, A19 pairs and cointegration, A22 equity factors, A24 events, A27 crowd sentiment, A28 positioning, A29 on-chain (crypto only), A14 intraday (only with intraday data).
- **Text and research:** A04 text intake and sanitizer; A41 hypothesis generator (LLM, research only, never trades).
- From this phase, 3 teams must agree for a GO (`go_min_teams_agree_from_phase5`).

## Acceptance (spec section 83)

- [ ] Each new agent shows incremental value in shadow mode, or stays in sandbox
- [ ] Drift monitors are live
