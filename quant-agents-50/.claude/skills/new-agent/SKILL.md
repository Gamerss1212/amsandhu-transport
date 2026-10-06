---
name: new-agent
description: Use when building a parked roster agent (core false in config/agents.yaml), or when proposing agent #51 or later. The 25-agent core is already built.
argument-hint: "[agent id, e.g. A17]"
---

# Build agent $0

## Steps

1. Read the agent's roster entry: `grep -n "\*\*$0 ·" docs/SPEC.md`, its entry in `config/agents.yaml`, and spec section 93.
2. Confirm with the owner that the data it needs exists (text, fundamentals, options, intraday...). If not, stop.
   Parked agents are optional: build one only when it can bring new information.
3. Write the contract tests first (new file `tests/test_<id>.py`):
   - output validates against its schema in `src/quantagents/schemas.py`
   - signal agents return exactly one prediction per symbol in `ctx.tradable`
   - same inputs give the same outputs
   - it abstains when there is not enough history
   - it reads only what its `info_subset` declares
4. Create `src/quantagents/agents/<id>_<role>.py` (lower case, e.g. `a17_range.py`) from the template below.
5. Register it in `config/agents.yaml`: set `implementation`, `state: shadow` and `phase: 4` (so it runs
   beside the core without changing the runtime phase). Leave `core: false`.
   New agents start in shadow: sealed and scored by A35, no vote (spec section 17). Only the owner promotes.
6. Signal agents (A11-A33) join the cycle through the registry. Nothing else to wire.
   `tests/test_no_lookahead.py` picks it up automatically; it must pass.
7. Run `/verify`. For a signal agent, ask the `red-team` subagent to look for look-ahead.

## Template for a signal agent

```python
class RangeAuctionAgent(SignalAgent):
    agent_id = "A17"
    name = "Range & Auction Agent"
    kind = "stat"
    info_subset = ("ohlcv",)
    horizon_bars = 5

    def predict(self, ctx: AgentContext) -> list[AgentPrediction]:
        out: list[AgentPrediction] = []
        for symbol in ctx.tradable:
            f = ctx.features.get(symbol)
            if "zscore_20" not in f or "er_20" not in f:
                out.append(self.abstain(ctx, symbol, "insufficient history"))
                continue
            if f["er_20"] > 0.3:  # trending, not ranging: stay out
                out.append(self.abstain(ctx, symbol, "not a range"))
                continue
            score = max(-1.0, min(1.0, -f["zscore_20"] / 2.0))  # fade stretches inside a range
            out.append(self.forecast(ctx, symbol, 0.5 + 0.06 * score, "stretched inside a range"))
        return out
```

Keep any single agent's p_up between about 0.35 and 0.65. New features go in `src/quantagents/features.py` with a causality test.
