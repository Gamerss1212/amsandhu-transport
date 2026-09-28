# Staged roll-out and soak test: results

Live paper runs on public feeds (Coinbase, Kraken, OKX, Yahoo), 27-28 September 2026 (UTC), on the build
machine. Each stage started from an empty database. The gates are the ones declared in advance in
`REQUIREMENTS.md` section 4. Raw snapshots: `results/stages/` (system health, event log, counts, recovery checks).

| Stage | Bots | Run | Gate | Result |
|---|---|---|---|---|
| 1 | 1 (1 family) | 2 x 15 min with a full restart in between | a decision for every completed bar; state survives a restart; no unhandled exceptions | **Pass.** 32 of 32 bars evaluated and recorded; after the restart the saved state was readable and positions reconciled against fills; 0 warnings or errors. No entry signal occurred, so no order was placed in this stage (the order path ran live in stage 4). |
| 2 | 10 (9 families) | 30 min | shared data; risk blocks conflicting or duplicate intents; recovery; no unhandled exceptions | **Pass.** 94 of 94 evaluations; 104 requests for 10 series; 0 errors. Shared-data and risk-bypass behaviour are covered by the automated tests. |
| 3 | 50 (9 families) | 30 min | p95 data-to-decision under 5 s; HTTP 429 under 1%; storage under 100 MB/hour | **Pass.** p95 bar close to decision 4.45 s (mostly the wait for the venue to publish the closed bar); 0 of 156 requests rate-limited; database 1.6 MB in 30 min (about 3 MB/hour). |
| 4 | 250 (19 families, 59 shared series) | 125 min soak | at least 95% of scheduled evaluations; a health record per bot per cycle; no cross-bot state corruption; peak memory under 2 GB; errors, recoveries and gaps reported | **Pass.** 3,268 of 3,268 scheduled evaluations (100%); 126 health cycles with 126 records for each of the 250 bots; after the run all 250 saved states were readable and positions reconciled against fills; peak memory 148 MB; 10,446 requests, 0 rate-limited, 0 fetch errors, 0 order-flow gaps, 0 bot errors, 0 auto-disabled bots, 0 dropped events, 0 storage failures; decision p95 15 ms; bar close to decision p95 4.46 s; database 7.8 MB (about 4 MB/hour). |

## What the soak does not show

* **Stocks were closed.** The soak ran on a Sunday evening (UTC), so 26 of the 59 series (the US and Toronto
  stocks, 136 of the 250 bots) reported `market_closed` and made no live decisions. Crypto ran live for the whole
  test. Stock bots at scale in live market hours remain to be observed.
* **Paper, not money.** Every fill was simulated: crypto against the live order book, and stock fills would
  have been synthetic (no free stock order book).
* **The brain in this run was the first version.** It predates regime learning, shadow trades and fee-aware
  priors.

## Trading during the soak (paper)

The brain scored 82 entries and vetoed 79 of them (96%), because the tested strategies lose after retail fees.
Six paper trades closed, all losing: -$376.39 in total, of which $354.97 was fees (94% of the loss). This matches
the batch evaluation (`strategies/results/EVALUATION_REPORT.md`): at retail crypto fees the costs are larger than
what these rules capture. Six trades are far too few to judge any strategy.

## Defect found and fixed

Three of the six trades came from resting orders (stop, limit or bracket entries), which the strategy engine
fills inside the bar. They reached the account **without the fleet brain scoring them and without the portfolio
risk check**, because only market entries went through the intent path. Now a resting entry is accepted only
when it is placed: the brain scores it (it can cancel or resize it), and the risk layer must approve it at its
estimated size; otherwise it is cancelled (`Fleet._accept_resting` in `mab/runtime.py`). The test is
`test_resting_orders_go_through_the_brain_and_the_risk_layer`.
