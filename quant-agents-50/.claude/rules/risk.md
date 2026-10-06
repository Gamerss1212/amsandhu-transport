---
paths:
  - "src/quantagents/risk/**"
  - "src/quantagents/execution/**"
  - "src/quantagents/sizing.py"
  - "src/quantagents/agents/a48_portfolio.py"
  - "config/default.yaml"
---

# Rules for risk, sizing and execution code

- Tests first. Every new branch in `src/quantagents/risk/` needs a test; the coverage gate requires 100%.
- A49 may only shrink or reject an order. It never grows one and never creates one.
- Risk-reducing orders (closing or shrinking a position) are always allowed.
- Read every limit from `RiskConfig`. Never hard-code a number that limits risk.
- Never raise a limit, the autonomy level, the execution mode or `live_trading_approved`. Propose the change to the owner instead.
- No LLM calls, ML models or network calls in the risk path.
- Orders fill at the next session's open, never at the close that produced the signal.
- The ledger (A05) and the broker (A50) keep separate books; reconciliation compares them every cycle.
- Ask the `risk-reviewer` subagent to review before committing.
