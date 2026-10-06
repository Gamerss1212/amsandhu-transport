# Phase 8: Micro-live (real money, owner approval required)

**Stop.** Claude does not start this phase until the owner adds this row under "Human approvals" in `docs/STATUS.md`:
`YYYY-MM-DD | Approve Phase 8 micro-live | <owner name>`

**Spec sections to read:** 2, 51, 65, 72, 75, 78.

## Preconditions (all of them)

- Phases 0-7 accepted.
- Every strategy used passed A44, A39 and the paper and shadow gates in section 65.
- Kill switch tested this week; watchdog running.

## Owner does (Claude never does these)

1. Opens the brokerage account and turns on 2FA.
2. Creates **trade-only** API keys with **withdrawals disabled** and an IP allow-list, and puts them in `.env`.
3. Edits `config/default.yaml` by hand: `execution_mode: live`, `autonomy_level: 3`, `live_trading_approved: true`, and sets `capital` to the micro-live amount (1-5% of capital, or the minimum lot).
4. Sets the approval environment variable named in `src/quantagents/config.py` in the terminal that runs the bot.

## Claude does

- Builds the live broker adapter behind the same interface as the paper broker. Keys come only from the environment and never appear in logs.
- Reconciles with the broker every cycle; any break halts trading.
- Adds alerts (email or Telegram) for fills, limits at 75% and 100%, and halts.
- Keeps paper and live keys separate.

## Canada notes (re-verify before use; not legal or tax advice)

- IBKR Canada blocks API orders on Canadian-listed products; US-listed products work.
- Questrade API trading is for partner developers; retail accounts get data only.
- Kraken and Coinbase operate in Canada as CSA restricted dealers; NDAX is an investment dealer.
- Keep every fill; use `python -m quantagents acb` for adjusted cost base and superficial-loss flags; keep records 6 years.

## Acceptance (spec section 65)

- [ ] 60 days and 50 trades at micro size
- [ ] Zero A49 breaches; slippage within the cost model
- [ ] The owner reviews and signs the results in STATUS
