# Can the brain be made better? Sixteen changes, tested the honest way

Produced by `python tools/brain_experiments.py --cache DIR --fee-profile ndax` (about 6 minutes). Raw numbers:
`results/brain_experiments_ndax.json`. Nothing here is a live trading result; it is a replay of past candle data.

## Short answer

**No change is supported by enough data to ship, so none was shipped.** Every variant that "won" did it the same way:
it traded less and so paid fewer fees. None can be told apart from simply never trading, and the validation period is
too short to separate the variants from each other with any real confidence. The brain keeps its current settings, and
the tool stays in the repository so the question can be asked again when there is more data.

## Method

* Candidate trades come from the 296 testable registry bots over **2026-06-09 → 2026-09-30** (about 113 days, 13,104
  signals), priced with the NDAX fee profile (`FEE_PROFILES["ndax"]`, see `FEE_PROFILES.md`).
* The period is split in time: **TUNE** = windows that start before 2026-08-10 (first 55%), **VALIDATE** = windows that
  start after (last 45%). 150 random 10-day windows each, 60 random bots per window, identical across variants, so the
  comparison is paired.
* A variant changes one brain setting (or a few). The variant is **chosen on TUNE only**; VALIDATE is where it is judged.
* Account of $10,000, so no order is too small and sizing cannot confound the comparison. Orders are sized as the
  shipped engine sizes them (adaptive slots, fractional US shares, 5% liquidity cap).

## Results (VALIDATE = later data the choice never saw; per 10-day window, on $10,000)

| Variant (what it changes) | TUNE mean | VALIDATE mean | vs current, paired 95% CI | trades |
|---|---|---|---|---|
| deterministic + edge ≥ 0.05 + cost ≤ 0.25 | −0.0006% | **+0.0140%** | +0.0244% [+0.0142, +0.0346] | 15.0 |
| deterministic + edge ≥ 0.10 | −0.0007% | +0.0125% | +0.0229% [+0.0097, +0.0357] | 13.2 |
| deterministic + edge ≥ 0.05 | −0.0008% | +0.0111% | +0.0215% [+0.0117, +0.0315] | 16.0 |
| no weekend entries (crypto) | −0.0009% | +0.0074% | +0.0178% [+0.0079, +0.0273] | 21.4 |
| edge ≥ 0.20 | −0.0012% | +0.0029% | +0.0133% [−0.0027, +0.0290] | 9.3 |
| deterministic + edge ≥ 0 | −0.0016% | +0.0036% | +0.0140% [+0.0068, +0.0214] | 19.2 |
| edge ≥ 0.10 | −0.0023% | +0.0030% | +0.0134% [+0.0015, +0.0259] | 14.3 |
| cost ≤ 0.20 R | −0.0028% | +0.0008% | +0.0112% [+0.0052, +0.0171] | 18.9 |
| cost ≤ 0.15 R | −0.0028% | +0.0063% | +0.0167% [+0.0075, +0.0255] | 16.2 |
| deterministic | −0.0029% | −0.0085% | +0.0019% [−0.0042, +0.0083] | 22.5 |
| cost ≤ 0.25 R | −0.0030% | −0.0045% | +0.0059% [+0.0021, +0.0096] | 21.0 |
| edge ≥ 0.05 | −0.0033% | −0.0005% | +0.0099% [+0.0008, +0.0191] | 17.1 |
| edge ≥ 0 | −0.0036% | −0.0024% | +0.0080% [+0.0022, +0.0140] | 20.0 |
| **current brain** | −0.0040% | **−0.0104%** | (reference) | 23.0 |
| unknown strategies need evidence ≥ 8 | −0.0040% | −0.0088% | +0.0016% [+0.0007, +0.0026] | 22.6 |
| unknown strategies need evidence ≥ 25 | −0.0040% | −0.0110% | −0.0006% [−0.0032, +0.0019] | 22.1 |

The variant that ranked first on TUNE also ranked first on VALIDATE, and the first four are the same on both halves.

## Why this is not a reason to change anything

1. **Nothing beats not trading.** Against "never trade" (exactly 0.0000% every window) the 95% interval of every variant
   includes zero; the best one is +0.0140% [−0.0060, +0.0340], which is about $1.40 per 10 days on $10,000, well inside
   the noise. The current brain's −0.0104% is about −$1 per 10 days.
2. **The wins are fewer trades, not better ones.** The best variants make 13–16 trades a window instead of 23. Average
   result per trade stays around zero or below (−0.025 to +0.015 R). This is the same finding as in `SYSTEM_BACKTEST.md`:
   fees are larger than the edge, so every refused trade is a saved fee.
3. **The intervals in the table are too narrow.** The 150 windows are drawn from only about 40 possible start days, so
   they overlap heavily; the validation half holds roughly five non-overlapping 10-day windows' worth of time. The
   bootstrap treats 150 windows as independent, which they are not. Read every interval as a lower bound on the
   uncertainty.
4. **One market period, one fee profile.** Everything is from the same three summer months and the NDAX fee profile.
   A rule that only helps in one regime is not a finding.

## What this changes for you

Nothing in the running software. The AI keeps refusing most of the signals it sees because trading costs would eat the
expected move (at each venue's own fees it approved about 5 of every 137 signals in `SYSTEM_BACKTEST.md`; at NDAX's
lower fees about 23 per 10-day window here), and the few trades it makes are about break-even. That is the honest
reason your balance can sit flat for hours. If you want to try a stricter brain yourself the settings exist
(`veto_edge`, `cost_veto_r`, `deterministic`, `min_trade_evidence` in `mab/brain.py`), but there is no evidence yet that
they make money, only that they trade less.

## Re-running it

```
python tools/system_backtest.py --cache /tmp/cache --fee-profile ndax    # builds the price-data cache (see SYSTEM_BACKTEST.md)
python tools/brain_experiments.py --cache /tmp/cache --fee-profile ndax --windows 150 --workers 2
```

A variant should be adopted only if (a) it is chosen on TUNE, (b) it beats the current brain on VALIDATE with an
interval that also holds up against "never trade", (c) the validation period holds many more than five independent
windows, and (d) it survives at least one other fee profile. None of the variants above meets (b) to (d).
