# Round 2 pre-registration (2026-10-07): three new families, written before any run

**Why this round.** The grid (2026-10-06) found that nothing beat simply holding, and that trend
rules mostly cut drawdowns while giving up return. The trend rules lost return by stepping out
too often. So all three new families **start from holding** and step out less:

| Family | Rule (long-only, no leverage, daily data, trades at the next open) | Variants (first = reported) |
|---|---|---|
| `hold_brake` | Hold every symbol in equal parts. Step out of a symbol only while **both** its close is below its N-day average **and** its M-day return is negative. Step back in as soon as either one recovers. (An altered Faber/SMA filter: two signals must agree before selling.) | `hold_brake_200_252`, `hold_brake_150_126` |
| `inv_vol` | Monthly: weight each symbol by 1 / its 63-day volatility, fully invested (risk parity). The `_trend` variant keeps a symbol's share in cash while its close is below its 200-day average. | `inv_vol_63`, `inv_vol_63_trend` |
| `dd_brake` | Hold every symbol in equal parts. Sell a symbol when its close is X% or more below its highest close of the last 252 days; buy it back on a close above its 50-day average. | `dd_brake_20`, `dd_brake_30` |

**Universes (fixed now):** `data/multi_asset.csv` (the 8 ETFs the paper account uses) and
`data/crypto.csv` (BTC, ETH: what real money would trade). Nothing else.

**How it runs:** `python -m quantagents validate --strategy <family> --data <csv>`, once per family
per universe: 6 runs, 12 trials, all logged in `trials.md`. Costs 0.15% one way, also at 2x.

**Pass bar (unchanged):** the existing A44 checks (Newey-West t, PSR, DSR, PBO, Hansen SPA,
2x costs) and the A39 red team. A family that fails stays failed. No parameter changes after the
run; any new idea needs a new pre-registration and counts as new trials.

**Honest caveat in advance:** the whole research history now holds well over 100 variants on
the same few datasets. Even a PASS here would be weak evidence and would need 30+ paper days
before anyone trusts it.
