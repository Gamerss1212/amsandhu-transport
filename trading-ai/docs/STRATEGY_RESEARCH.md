# Strategy research: what the evidence says (crypto and stocks)

Compiled 2026-10-13 from web searches made for this release. Every source below was returned by those searches; most
were read as abstracts, publisher or working-paper pages and secondary summaries, not full papers. Figures marked
**(secondary)** come from a summary of the paper, not the paper itself, and should be checked against the original
before being relied on. Nothing here promises a profit: published results describe past samples, usually before
costs that a small retail account actually pays, and many effects weakened after publication.

## 1. How to read published strategy evidence

| Lesson | Evidence | What this software does about it |
|---|---|---|
| Most published effects fail careful replication | Hou, Xue and Zhang (Review of Financial Studies 2020) re-tested 452 anomalies with microcaps controlled: 65% fail a t-value of 1.96, 82% fail the stricter multiple-testing hurdle of 2.78; survivors are much smaller than originally reported. [1] | A strategy must pass held-out tests here, not just have a citation. |
| Testing many ideas inflates the best result | Harvey, Liu and Zhu (Review of Financial Studies 2016) argue a new factor should clear t ≈ 3.0, not 2.0, because hundreds have been tried. [2] Bailey and López de Prado's Deflated Sharpe Ratio corrects the Sharpe ratio for the number of trials and non-normal returns; the Probability of Backtest Overfitting (CSCV) estimates how often the in-sample winner falls in the bottom half out-of-sample. [3][4] | Every backtest is logged as a trial; the Deflated Sharpe gate (≥ 0.95) charges all trials in a family, and PBO ≤ 0.2 is required. |
| Technical rules found on one sample often vanish later | Sullivan, Timmermann and White (Journal of Finance 1999) applied a data-snooping-robust bootstrap to the moving-average and range-break rules of Brock, Lakonishok and LeBaron; summaries agree the rules' profitability did not hold on the later 10-year sample **(secondary; summaries differ in detail)**. [5] | Rules are judged on a final test window touched once, plus walk-forward. |
| Retail day trading usually loses | Barber, Lee, Liu, Odean and Zhang (Review of Asset Pricing Studies 2020), Taiwan 1992-2006: 97% of day traders are likely to lose money in future day trading; 74% of day-trading volume comes from traders with a history of losses. [6] | Default is to stay in cash until a strategy qualifies; costs are modelled on every trade. |
| Costs decide what survives | Frazzini, Israel and Moskowitz measured real institutional execution costs ($1.7 trillion of trades, 1998-2016) and found them far below academic estimates for large managers, while short-term reversal was the strategy most constrained by trading costs. [7] Crypto spreads range from under 1 basis point on BTC at peak hours to over 50 basis points on a small coin with $80k daily volume **(vendor education page, illustrative)**. [8] | Fees, half-spread, volatility- and size-based slippage and a volume participation cap are charged in every backtest and paper fill; results are re-run at 1.25×-3× costs. |

## 2. Strategy families compared

"Horizon" is the holding period in the evidence. This build runs **intraday** (positions closed the same session, crypto
held 24 hours at most), so families whose evidence is monthly can only be tested here in a shorter form, which does
not inherit the published evidence.

| Family | Main evidence | Markets in the evidence | Horizon | Reported performance | Drawdowns and failure modes | Liquidity, fees, slippage |
|---|---|---|---|---|---|---|
| Time-series momentum / trend following | Moskowitz, Ooi and Pedersen (JFE 2012): significant time-series momentum in all 58 liquid futures studied; returns persist 1-12 months then partly reverse; diversified portfolio earns abnormal returns and does best in extreme markets. [9] Hurst, Ooi and Pedersen (JPM 2017): positive returns and low correlation to traditional assets in every decade since 1880 across 67 markets, positions scaled to 10% volatility. [10] | Futures: equity indices, bonds, currencies, commodities | 1-12 months | Positive in every decade in the century-long sample [10] | Critics attribute much of it to volatility scaling rather than momentum itself (Kim, Tse and Wald) [9]; whipsaw losses in trendless periods | Needs liquid futures; low turnover, so costs matter less than for intraday rules |
| Crypto time-series momentum | Liu and Tsyvinski (RFS 2021): strong time-series momentum in cryptocurrency returns; investor-attention proxies forecast returns; little exposure to stock-market factors. [11] | BTC, ETH, XRP and broader coins | Days to weeks | Significant in-sample predictability [11] | Crypto regimes change fast; 2022-style crashes | Large coins only are cheap to trade |
| Crypto trend following (practitioner and preprint) | Rozario et al. (arXiv 2009.12155) report 255% walk-forward annualised returns for crypto trend following but optimise parameters to maximise Sharpe; check for tuning leakage. [12] A Quantpedia study of Bitcoin breakout and reversion rules reports lower drawdowns than buy-and-hold over Feb 2022 - Aug 2024. [13] | Crypto | Hours to weeks | Preprint claims; not peer reviewed | Overfitting risk explicitly flagged above | Fees and spreads on small coins can erase edges |
| Cross-sectional stock momentum | Jegadeesh and Titman (JF 1993): buying past 3-12-month winners and selling losers earned significant returns over 3-12-month holds, partly reversing in years 2-3. [14] Daniel and Moskowitz (JFE 2016): momentum crashes, partly forecastable, after market declines with high volatility and sharp rebounds; volatility-scaled momentum roughly doubles alpha and Sharpe. [15] | US stocks | 3-12 months | About 1.49% a month for a 12-month/3-month decile spread **(secondary blog figure)** [14] | Crashes in rebounds [15] | Many stocks, monthly rebalancing; shorting needed for the long-short form |
| Crypto short-term reversal vs momentum | IRFA 2021 (3,600+ coins, daily): low-return coins outperform next day, attributed to illiquidity; the largest coins show daily momentum instead. [16] Fičura (2023): weekly reversal only in small, illiquid coins; large liquid coins show weekly momentum. [17] | Crypto | 1 day to 1 week | Significant in their samples [16][17] | Reversal lives where costs are highest | Small coins: spreads and slippage can exceed the effect |
| Stock short-term reversal | Lehmann (1990): prior-week losers beat prior-week winners. Conrad, Gultekin and Kaul attribute much of it to bid-ask bounce; de Groot, Huij and Zhou report 30-50 basis points a week net of costs only when restricted to large caps with lower turnover **(secondary)**. [18] | US stocks | 1 week | See left | Bid-ask bounce makes gross figures misleading | Most cost-constrained family [7] |
| Pairs / relative value | Gatev, Goetzmann and Rouwenhorst (RFS 2006), 1962-2002: up to 11% annualised excess return for self-financing pairs portfolios, robust to conservative cost estimates. [19] A 2004-2009 replication (US, Japan, Hong Kong, China) found no consistent positive excess return, though profitable in turmoil. [19] | US stocks | Days to weeks | Up to 11% a year historically [19] | Decay after publication; relationships break | Needs shorting and borrow; this build has no borrow data, so pairs are research-only |
| Volatility management | Moreira and Muir (JF 2017): scaling exposure down when volatility is high raised alphas and Sharpe ratios across factors. Later work reports failure out of sample (Cederburg et al.) and after costs (Barroso and Detzel). [20] | Equity factors, currencies | Monthly rebalance | Higher Sharpe in sample [20] | Out-of-sample and cost failures [20] | Turnover rises with frequent rescaling |
| Intraday momentum (index ETFs) | Gao, Han, Li and Zhou (JFE 2018), SPY 1993-2013: the first half-hour return predicts the last half-hour return; stronger on volatile, high-volume, recession and macro-news days; also in ten other active ETFs. [21] Earlier draft: R² about 0.02 **(secondary)**. [21] | SPY and 10 ETFs | Same day (last half-hour) | Statistically significant but small R² | Weak signal; costs per trade matter | Very liquid ETFs only |
| Bitcoin intraday momentum | Shen, Urquhart and Wang: Bitcoin's first half-hour (volume-based clock) predicts the last half-hour; strongest in high-volume or high-volatility sessions; gains especially in downturns. [22] | Bitcoin | Intraday | Economic gains reported [22] | Needs a defined "session" for a 24/7 market | Liquid BTC only |
| Opening-range breakout | Zarattini and Aziz (SSRN 2023), QQQ 2016-2023: a 5-minute ORB rule beat buy-and-hold only with leverage. [23] A follow-up with Barbon on 7,000+ stocks reports 1,637% total return for a top-20 stocks-in-play version **(secondary)**. An independent replication on five index CFDs reproduced the gross result but found it indistinguishable from zero, four of five negative, after costs **(single non-peer-reviewed blog)**. [23] | QQQ, US stocks | Same day | Disputed after costs | Commission-only cost models; no out-of-sample period in the original | Leverage and spreads decide the result |
| Funding-rate and basis carry (crypto) | He, Manela, Ross and von Wachter (arXiv 2212.06888) explain perpetual funding and no-arbitrage bounds; Gornall, Rinaldi and Xiao (preliminary, 2024) find perpetuals reduced drawdowns of basis arbitrage by more than half versus expiring futures, which lost heavily when the basis blew out in crises. [24] No peer-reviewed realised-return study was found. | Crypto perpetuals and spot | Days to months | No verified return figures found | Basis blow-outs; exchange counterparty risk | Needs derivatives access; perpetual futures are not available to Canadian residents on Kraken, so this build cannot trade it |

## 3. What the 100 agents are given, and why

Each agent gets one market and one strategy family. The family is chosen from the evidence above, limited to what this
build can trade intraday with the data it has:

| Agents | Market | Family | Why |
|---|---|---|---|
| 3 | BTC, ETH, SOL (1h) | Trend / time-series momentum | Crypto time-series momentum [11]; large coins show momentum [16][17]; Bitcoin intraday momentum [22] |
| 22 | Next most liquid Coinbase USD pairs (1h) | Trend / momentum | Large, liquid coins show momentum, not reversal [16][17] |
| 15 | Further liquid Coinbase USD pairs (1h) | Mean reversion | Reversal is documented in less liquid coins [16][17], but it is the most cost-sensitive family, so these agents must pass the cost-stress gates |
| 15 | Index and sector ETFs (15m) | Intraday momentum (first half-hour, noise-band) and opening-range breakout | Gao et al. on SPY and active ETFs [21]; ORB on QQQ [23] |
| 17 | Large US stocks (15m/1h) | Opening-range and volatility breakouts | Stocks-in-play ORB [23] |
| 17 | Large US stocks (1h) | Short-term mean reversion | Reversal survives costs only in large caps with low turnover [18] |
| 5 | EUR/USD, GBP/USD, USD/JPY, USD/CAD, AUD/USD (1h) | Session momentum and trend | Currency time-series momentum [9] |
| 6 | Equity-index futures ES, MES, NQ, MNQ, YM, RTY (15m) | Opening-range and initial-balance breakouts | Intraday momentum in index products [21] |

Not given to any agent:
- **Monthly cross-sectional momentum and volatility-managed portfolios:** their evidence is monthly; the intraday rules make them research-only.
- **Pairs trading:** needs shorting and borrow data.
- **Funding and basis carry:** needs perpetual futures access, which this build does not have.

## 4. Costs and execution assumptions used in every test here

- Fees per venue profile, half the modelled spread, slippage that grows with volatility and order size, and fills
  capped at a share of the bar's volume (partial fills carry over). Exits at stops gap at the open when the bar opens
  beyond the stop.
- Futures: contract multipliers; continuous series forced flat in roll windows.
- FX: quote-to-account conversion. FX overnight financing is not modelled; under the intraday rules positions are
  closed before the 17:00 New York rollover, so no swap is charged in practice.
- Crypto: spot only, so there is no funding cost. Perpetual funding is not modelled because perpetuals are not traded.
- Every result is re-run at 1.25×, 1.5×, 2× and 3× costs, and must still hold at 2×.

## Sources

1. Hou, Xue and Zhang, "Replicating Anomalies", RFS 33(5), 2020: https://ideas.repec.org/a/oup/rfinst/v33y2020i5p2019-2133..html ; NBER w23394: https://www.nber.org/papers/w23394.pdf
2. Harvey, Liu and Zhu, "...and the Cross-Section of Expected Returns", RFS 29(1), 2016: https://nber.org/papers/w20592 ; https://papers.ssrn.com/abstract=2513152
3. Bailey and López de Prado, "The Deflated Sharpe Ratio", JPM 40(5), 2014: https://papers.ssrn.com/abstract=2460551
4. Bailey, Borwein, López de Prado and Zhu, "The Probability of Backtest Overfitting", J. Computational Finance 20(4), 2017: https://papers.ssrn.com/abstract=2326253 ; R package vignette: https://cran.hafro.is/web/packages/pbo/vignettes/pbo.html
5. Sullivan, Timmermann and White, "Data-Snooping, Technical Trading Rule Performance, and the Bootstrap", JF 1999: https://www.fmg.ac.uk/publications/discussion-papers/data-snooping-technical-trading-rule-performance-and-bootstrap ; https://researchonline.lse.ac.uk/id/eprint/119144
6. Barber, Lee, Liu, Odean and Zhang, "Learning, Fast or Slow", RAPS 10(1), 2020: https://ideas.repec.org/a/oup/rasset/v10y2020i1p61-93..html ; working paper: https://faculty.haas.berkeley.edu/odean/papers/day%20traders/day%20trading%20and%20learning%20110217.pdf
7. Frazzini, Israel and Moskowitz, "Trading Costs": https://conference.nber.org/conf_papers/f68262/f68262.pdf ; summary: https://alphaarchitect.com/surprise-the-size-value-and-momentum-anomalies-survive-after-trading-costs/
8. Spread and slippage in crypto (vendor education): https://blofin.com/academy/education/hidden-fees-trading
9. Moskowitz, Ooi and Pedersen, "Time Series Momentum", JFE 104, 2012: https://papers.ssrn.com/abstract=2089463 ; https://fairmodel.econ.yale.edu/ec439/jpde.pdf
10. Hurst, Ooi and Pedersen, "A Century of Evidence on Trend-Following Investing", JPM 44(1), 2017: https://www.aqr.com/Insights/Research/Journal-Article/A-Century-of-Evidence-on-Trend-Following-Investing ; https://alphaarchitect.com/trend-following-is-everywhere/
11. Liu and Tsyvinski, "Risks and Returns of Cryptocurrency", RFS 34(6), 2021: https://ideas.repec.org/a/oup/rfinst/v34y2021i6p2689-2727..html ; NBER w24877: https://www.nber.org/system/files/working_papers/w24877/w24877.pdf
12. Rozario et al., "A Decade of Evidence of Trend Following Investing in Cryptocurrencies": https://ar5iv.labs.arxiv.org/html/2009.12155
13. Quantpedia, "Revisiting Trend-following and Mean-reversion Strategies in Bitcoin": https://quantpedia.com/revisiting-trend-following-and-mean-reversion-strategies-in-bitcoin/
14. Jegadeesh and Titman, "Returns to Buying Winners and Selling Losers", JF 1993: https://knowledge.wharton.upenn.edu/article/recognizing-an-investing-signal-that-defied-wisdom-and-endured/ ; monthly figure (secondary): https://investment-fiduciary.com/2025/03/09/returns-to-buying-winners-and-selling-losers/
15. Daniel and Moskowitz, "Momentum Crashes", JFE 122(2), 2016: https://www.nber.org/papers/w20439
16. "Up or down? Short-term reversal, momentum, and liquidity effects in cryptocurrency markets", IRFA 78, 2021: https://earsiv.medeniyet.edu.tr/items/23a96c9f-3952-4bdf-aec5-abafb3aaab70
17. Fičura, "Impact of size and volume on cryptocurrency momentum and reversal", FFA Working Papers 5:003, 2023: https://ideas.repec.org/p/prg/jnlwps/v5y2023id5.003.html
18. Short-term reversal evidence and costs (Lehmann 1990; Conrad, Gultekin and Kaul; de Groot, Huij and Zhou): https://alphaarchitect.com/quantitative-momentum-research-short-term-return-reversal/ ; https://quantpedia.com/strategies/short-term-reversal-in-stocks
19. Gatev, Goetzmann and Rouwenhorst, "Pairs Trading: Performance of a Relative-Value Arbitrage Rule", RFS 2006: https://ideas.repec.org:443/p/nbr/nberwo/7032.html ; replication thesis: https://thesis.eur.nl/pub/8530/Cummins,%20R.L.%20%28299180%29.pdf
20. Moreira and Muir, "Volatility-Managed Portfolios", JF 72(4), 2017: https://www.nber.org/papers/22208 ; critiques discussed in DeMiguel, Martín-Utrera and Uppal (JF 2024): https://lbsresearch.london.edu/id/eprint/3716/1/The%20Journal%20of%20Finance%20-%202024%20-%20DeMIGUEL%20-%20A%20Multifactor%20Perspective%20on%20Volatility%E2%80%90Managed%20Portfolios.pdf
21. Gao, Han, Li and Zhou, "Market Intraday Momentum", JFE 2018: https://profiles.wustl.edu/en/publications/market-intraday-momentum/ ; https://alphaarchitect.com/2014/08/attention-prop-traders-the-first-half-hour-of-trading-predicts-the-last-half-hour/
22. Shen, Urquhart and Wang, "Bitcoin intraday time series momentum": https://research.birmingham.ac.uk/en/publications/bitcoin-intraday-time-series-momentum/
23. Zarattini and Aziz, "Can Day Trading Really Be Profitable?", SSRN 4416622, 2023: https://papers.ssrn.com/abstract=4416622 ; summary: https://www.cxoadvisory.com/technical-trading/day-trading-with-an-opening-range-breakout-strategy ; independent cost replication (blog): https://www.mql5.com/en/blogs/post/776235
24. He, Manela, Ross and von Wachter, "Fundamentals of Perpetual Futures": https://arxiv.org/html/2212.06888v5 ; Gornall, Rinaldi and Xiao (preliminary): https://afajof.org/management/viewp.php?n=186844
