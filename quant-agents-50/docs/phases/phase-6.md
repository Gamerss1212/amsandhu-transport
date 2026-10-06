# Phase 6: LLM and debate layer (47 agents)

**Optional.** The 25-agent core is complete without this phase. These agents are parked in `config/agents.yaml` (`core: false`). Build one only when you have the data it needs and a reason to expect new information; each starts in shadow (spec section 93).

**Agents added:** A18, A25, A26, A30, A36, A37, A38.
**Goal:** language models add judgment on text and debate major trades, without touching math or orders.
**Spec sections to read:** 14, 20, 36, 37, 72.

## Build

1. **LLM client:** temperature 0, cached responses, strict JSON output, a per-cycle cost cap from config, evidence IDs required for every claim, no access to orders or secrets.
2. **Prompt-injection test suite:** outside text is data, never instructions. A04 strips embedded instructions.
3. **Debate (section 14):** A36 bull, A37 bear, A38 pre-mortem, A39 red-team check, A40 final no-trade. Time-boxed and cost-capped. Outcomes: PROCEED, REDUCE, DEFER, REJECT.
4. **Quant-only mode:** when the LLM is down or over budget, no major trades.
5. Once debate is live, A48 lifts the cap below major size only for debated trades.

## Owner does

- Creates an LLM API key with a monthly spending limit and puts it in `.env`.

## Acceptance (spec section 83)

- [ ] Injection test suite: 100% caught
- [ ] Debate is time-boxed and cost-capped
- [ ] LLM evaluation uses only data after the model's training cutoff
- [ ] Quant-only mode tested
