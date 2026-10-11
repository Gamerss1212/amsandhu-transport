# Backtested strategies — qualifying list

Updated October 10, 2026 (America/Edmonton). Companion to AI_Trading_System_Master_Prompt.md, revision 13.

**Qualifying strategies: 0.**

No configuration passed the complete development and separate validation requirements. Losing and untested strategies are excluded; the qualifying list is empty.

## Completed evidence

| Batch | Market and scope | Base configurations | Positive full-year base configurations | Qualifying models |
| --- | --- | ---: | ---: | ---: |
| 01 | Six crypto spot pairs; four variants; 5/15 minutes | 48 | 0 | 0 |
| 02 | Same six spot pairs; six paired variants; 15 minutes | 36 | 0 | 0 |
| 03 | BTC, ETH, SOL perpetual futures; two long/short variants; 15 minutes | 6 | 0 | 0 |

Development dates: calendar 2025. Base costs: 0.10% fee plus 0.02% adverse slippage per side. These are experiment assumptions, not measured account costs. Higher-cost and extra-delay checks are included. A positive development result, profitable-before-cost result, or smaller loss does not qualify.

Batch 02 separate-validation status: NOT_OPENED. Batch 03 separate-validation status: NOT_OPENED. No model selection was made using 2026 prices. When development gates fail, 2026 validation remains unopened. No prospective or live result is claimed.

## Requirements for additions

Each entry must preserve exact rules, versions, tested markets, point-in-time data, costs, sizing, trade counts and drawdown, plus an appropriately independent evaluation period and explicit execution limits. Count all related trials. Retain failed results inside the master prompt; do not lower gates or increase leverage to fill this list. Historical qualification does not guarantee future profits or authorize live trading.

Stock strategies, on-chain meme launches, and the other research cards remain untested in these batches. Futures funding rates were observed historically; the funding-price approximation and incomplete liquidation model limit interpretation. Full code, data hashes, results and limitations are embedded in the master prompt.

Attribution: Binance Vision. Derived research outputs: CC BY-NC-SA 4.0, subject to https://github.com/binance/binance-public-data/blob/master/TERMS_AND_CONDITIONS.md . Personal non-production research only.
