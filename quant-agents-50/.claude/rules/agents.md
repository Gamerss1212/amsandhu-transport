---
paths:
  - "src/quantagents/agents/**"
  - "src/quantagents/orchestrator.py"
  - "src/quantagents/aggregation.py"
  - "config/agents.yaml"
---

# Agent contract (spec sections 10, 11, 17)

- One module per agent: `src/quantagents/agents/aNN_role.py`, with class attributes `agent_id`, `name`, `kind`, `info_subset`.
- Agents are pure: same inputs, same outputs. No network, no files, no clock, no global state.
- Agents read only the `MarketView`, features and context they are given. Never pass them a full `MarketData`.
- Signal agents (A11-A33) return exactly one `AgentPrediction` per symbol in `ctx.tradable`. Abstaining is allowed and is better than guessing.
- Build predictions with `self.forecast(...)` or `self.abstain(...)`. Keep p_up between about 0.35 and 0.65 for one agent.
- Predictions are sealed (commit-reveal) before anyone sees them. Never read another agent's output inside `predict`.
- Register every agent in `config/agents.yaml`. New agents start in `shadow` (scored, no vote); the owner approves promotion.
- Stop signals can only reduce risk. No agent edits another agent's output, weights or code.
- LLM agents (Phase 6+) never do arithmetic, never see orders or secrets, and cite evidence IDs for every claim.
