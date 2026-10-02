# Knowledge base: day trading, order flow, risk, strategy families, psychology, testing

One entry per `### `. Strategy families point to the 320-strategy encyclopedia (`know.py` finds those too).

### What day trading is
aka: day trading, daytrading, intraday, scalping vs swing, trading styles, swing trading, position trading
What: scalping = seconds–minutes; day trading = in and out the same day; swing = days–weeks; position = weeks–months. Shorter = more trades, more fees, more noise.
Evidence: large studies of retail day traders (e.g. Barber, Lee, Liu & Odean on Taiwan; Chague, De-Losso & Giovannetti on Brazil) found the great majority lose money. Jarvus's own tests: pure intraday lost after fees in every test; 4×ATR stops with up to 96-hour holds survived.

### Jarvus playbooks
id: p1_trend_pullback, p3_breakout_retest, p4_sweep_reclaim, p6_orb · aka: playbooks, p1, p3, p4, p6, trend pullback, breakout retest, sweep reclaim, orb, opening range breakout
What: Jarvus's mechanical setups (rules in `scripts/ladder.py`): P1 pullback to the 21 EMA in an uptrend, P3 retest of a broken level, P4 sweep of a low that closes back above, P6 opening-range breakout (US open), plus the RSI(2) dip. Live, they count only with the gate LOUD and the other v6.1 rules.

### Order types
aka: order types, market order, limit order, stop order, stop limit, stop loss order, oco, trailing stop, post only, ioc, fok, reduce only
What: market = fill now at any price (taker); limit = your price or better (maker if it rests); stop = becomes a market order at a trigger; stop-limit = becomes a limit (may not fill in a crash); OCO = one cancels the other; post-only = rejected if it would take.
Jarvus: limit entries (maker fee), stops that rest on the exchange. More: execution-and-order-types.md §1.

### Maker vs taker fees
aka: maker, taker, fees, trading fees, fee tiers, cost in r
What: maker = your resting order adds liquidity (cheaper); taker = you hit an existing order. Cost in R = round-trip cost % ÷ stop distance %. Jarvus refuses trades above 0.33R and halves size at 0.20–0.33R.

### Spread, slippage and liquidity
aka: spread, bid ask spread, slippage, liquidity, market depth, thin market
What: spread = gap between best bid and ask; slippage = fill worse than expected; liquidity = how much can trade without moving price. All three are hidden costs that grow in small coins and fast markets.

### Order book and depth
aka: order book, depth chart, bids, asks, walls, spoofing, iceberg orders, dom, ladder, level 2
What: resting buy and sell orders. Big "walls" can be pulled (spoofing); icebergs hide size. Useful for execution, unreliable for direction.

### Tape reading and time and sales
aka: tape reading, time and sales, prints, aggressive buyers, aggressive sellers
What: watching executed trades: who is hitting whom, how big, how fast. A scalper's tool; needs low latency and low fees to matter.

### Delta, CVD and footprint charts
aka: delta, cvd, cumulative volume delta, footprint, footprint chart, order flow, absorption, exhaustion, imbalance order flow
What: delta = aggressive buys − aggressive sells per bar; CVD = running total; footprint = volume at each price inside a bar. Absorption = heavy aggression with no price progress (a passive wall soaking it up). Exhaustion = aggression fading at an extreme.
Note: crypto CVD differs by venue; spot vs perp CVD disagreeing is common.

### Volume profile and market profile
aka: volume profile, vpvr, vrvp, poc, point of control, value area, vah, val, hvn, lvn, market profile, tpo, initial balance, auction market theory
What: volume (or time) traded at each price. POC = most traded price; value area = ~70% of volume (VAH/VAL); high-volume nodes attract and hold price, low-volume nodes are crossed fast. Auction theory: price moves to find two-sided trade, then rotates.
Use: as levels, like support/resistance. Not measured by Jarvus.

### Multi-timeframe analysis
aka: multi timeframe, mtf, top down analysis, higher timeframe, htf, ltf
What: trend and bias from the higher timeframe, setup from the middle, trigger from the lower. Most bad trades fight the higher timeframe.
Jarvus: P1/P3/P6 need both the 1h and 4h trends up.

### Market regimes
aka: regime, trending market, ranging market, chop, choppy, volatility regime, trend day, range day
What: trend, range, chop or compression. Trend tools fail in ranges and range tools fail in trends; deciding the regime comes before choosing a playbook.
More: regimes-and-cycles.md.

### The volatility gate
aka: volatility gate, gate, loud, quiet, normal, will it move, volgate
What: Jarvus's trained model of how big the next 12 hours will be (crypto). LOUD calls were right about 76% of the time in held-out testing (base rate 31%). It forecasts size, never direction. Jarvus enters only on LOUD.

### Risk per trade and position sizing
aka: position size, position sizing, risk per trade, 1% rule, how much to buy, lot size
What: size = (account × risk %) ÷ stop distance. Risk 0.5–1% per trade means 10 losers in a row cost about 10%, not the account.
Jarvus: 1% × 0.6 (LOUD) for majors, 0.3% memes, hard cap 1%. `scripts/position_size.py`.

### R multiples and expectancy
aka: r multiple, r, expectancy, edge, profit factor, average win, average loss, payoff ratio, risk reward, rr, r:r
What: R = the amount risked. Expectancy = win% × average win (R) − loss% × average loss (R). Profit factor = gross wins ÷ gross losses. A 40% win rate at 2R wins makes +0.2R per trade before costs.

### Win rate vs payoff
aka: win rate, high win rate, 80 percent win rate, accuracy, hit rate
What: win rate alone means nothing: 90% wins of +1% with one −20% loss loses money. Jarvus built an "80% green" exit ladder: random entries got the same 79% and it lost after fees (grep `## 80% MODE` in manual.md).

### Drawdown and risk of ruin
aka: drawdown, max drawdown, risk of ruin, recovery math, losing streak
What: a 50% loss needs +100% to recover. Losing streaks of 8–10 are normal at a 40% win rate over hundreds of trades. Risk of ruin rises fast above 2% per trade.
Jarvus: stop for the day at −3R or 3 losses in a row.

### Kelly criterion
aka: kelly, kelly criterion, optimal f, fractional kelly
What: the bet size that maximizes long-run growth given a known edge. Real edges are uncertain, so full Kelly overbets; traders use a quarter or less, and only after 50+ logged trades.

### Correlation and concentration
aka: correlation, diversification, correlated positions, btc beta
What: BTC, ETH and SOL move together; three longs are close to one big bet. Jarvus counts them as one position.

### Leverage and liquidation math
aka: leverage, 10x, 100x, liquidation price, margin call, isolated margin, cross margin
What: at 10× leverage a ~10% move against you wipes the position (less after fees and maintenance margin). Leverage does not change the edge, only how fast you are ruined. Jarvus: spot only.

### Stop-losses
aka: stop loss, stops, where to put a stop, stop hunting, mental stop, hard stop, trailing stop
What: the price that proves the idea wrong, plus a buffer. Too tight = stopped by noise and eaten by fees. Never widen a stop after entry.
Jarvus: 4× ATR(1h), resting on the exchange.

### Taking profit and exits
aka: take profit, targets, exit strategy, scaling out, partial profits, trailing exit, time stop
What: fixed R targets, scaling out, trailing stops or time stops. Jarvus's backtest: one exit at 2R with a 96-hour limit beat partial ladders after fees.

### Trend following
aka: trend following, trend trading, momentum trading, ride the trend
What: buy strength, cut losers, let winners run; low win rate, big winners. One of the best documented strategy families across markets.
More: strategy encyclopedia Part 3. Jarvus measured: momentum signals on 4h beat random entries (kb-measured.md).

### Mean reversion
aka: mean reversion, reversion, fade, buy the dip, counter trend
What: buy stretched lows and sell stretched highs, expecting a return to the average. High win rate, occasional big losses when the stretch becomes a trend.
More: strategy encyclopedia Part 4.

### Breakout trading
aka: breakout, breakouts, breakout trading, fakeout, false breakout, failed breakout
What: buy when price leaves a range or level. Many breakouts fail; filters are volume, a retest, a compression before, and the higher-timeframe trend.
More: strategy encyclopedia Part 5.

### Scalping
aka: scalping, scalp, scalper
What: many tiny trades for small gains. Fees and spread dominate: at retail spot fees a 1-ATR scalp on BTC costs about 0.6R per trade, which no measured edge covers.

### Grid trading and DCA
aka: grid bot, grid trading, dca, dollar cost averaging, martingale, averaging down
What: grid = buy and sell orders at fixed steps in a range (profits in ranges, holds bags in trends). DCA = buying a fixed amount on a schedule (an investing method, not trading). Martingale/averaging down without a stop is how accounts blow up.

### Arbitrage and market making
aka: arbitrage, arb, funding arbitrage, triangular arbitrage, market making, cash and carry arbitrage
What: profit from price differences or from capturing the spread. Real arbitrage needs speed, capital on several venues and low fees; retail-visible "arbs" are usually transfer delays or withdrawal risk.

### News and event trading
aka: news trading, trading the news, cpi trading, fomc trading, listing pump, listing trade
What: trading reactions to scheduled (CPI, FOMC) or surprise news (listings, hacks, lawsuits). First moves are fast and often reverse; spreads widen.
Jarvus: no new trade 30 minutes either side of a tier-1 event.

### Pairs and relative value
aka: pairs trading, relative value, eth btc trade, spread trade, rotation trade
What: long one asset against another (e.g. ETH vs BTC). Needs shorting or a ratio product; spot-only traders approximate it by rotating holdings.

### Copy trading and signal groups
aka: copy trading, signal group, signals, paid signals, vip group, discord signals
What: following someone else's trades. Results shown are selected after the fact; fills are worse than the leader's; many groups profit from subscriptions or pumping their bags.

### Prop firms and funded accounts
aka: prop firm, funded account, ftmo, evaluation, challenge
What: pay a fee to pass a trading evaluation and trade the firm's money for a profit split. Most participants fail evaluations, and the fees are the firms' main revenue. Crypto prop firms often use simulated execution.

### Backtesting the right way
aka: backtest, backtesting, how to backtest, overfitting, curve fitting, look ahead bias, survivorship bias, data snooping, walk forward, out of sample, p hacking
What: test rules on data they were not built on (out-of-sample, walk-forward), include fees and slippage, use only data available at the time (no look-ahead), include dead coins (survivorship), and count how many ideas you tried (data snooping).
Jarvus: `backtest.py`, `system_test.py`; every measured number in this knowledge base follows these rules.

### API keys and connecting an exchange
aka: api key, api keys, connect exchange, connect kraken, connect ndax, broker connection, bot trading, automate, go live with a bot
What: an exchange API key lets software read balances or place orders. Rules Jarvus keeps: trade-only or read-only keys, never withdrawal permission; keys live in the computer's secure storage or environment variables, never in chat, files or code; real-money orders stay off until Abhi authorizes them in a separate step.
More: live-trading-and-brokers.md.

### Paper trading and going live
aka: paper trading, demo account, simulated trading, go live, real money
What: practice with fake money first, then tiny real size; real fills, fees and emotions differ. Jarvus: paper by default; real orders only after a separate, explicit authorization.

### Trading journal and review
aka: journal, trade journal, review, trade log, statistics, track record
What: log setup, entry, stop, target, size, reason and emotions before the order; review every 20 trades; judge expectancy over 50–100 trades, never one week.
Jarvus: `journal.py add|close`, `journal_stats.py`.

### Trading psychology
aka: psychology, fomo, revenge trading, make it back, get back to even, win it back, double down, all in, tilt, overtrading, fear, greed, discipline, loss aversion, confirmation bias, sunk cost, gamblers fallacy, euphoria
What: the usual killers: FOMO (chasing), revenge (making it back), tilt (rule-breaking after losses), overtrading (boredom), moving stops (hope). Rules decided before the trade beat feelings during it.
Jarvus: coach first, trade second (`python3 scripts/know.py "coach mode"`).

### Daily routine
aka: routine, trading routine, morning routine, pre market, checklist, pre trade checklist
What: check the calendar and the gate, mark levels, define the plan before the session, trade only the plan, journal, stop at the daily limit.
More: assets/daily-routine.md, assets/pre-trade-checklist.md.

### Probability and prediction
aka: can you predict the market, predict crypto, forecast, prediction, random walk, efficient market, is trading gambling
What: short-term direction in liquid crypto is close to unpredictable (Jarvus's direction model: AUC about 0.51, where 0.50 is a coin flip). Volatility is predictable. Edges, where they exist, are small and come from costs, risk control and selectivity.
More: probability-and-prediction.md.

### Stocks vs crypto
aka: stocks, stock market, equities, pdt rule, pattern day trader, market hours, earnings
What: stocks trade set hours with opening gaps, earnings and regulation; US day traders under $25K face the pattern-day-trader rule (a FINRA rule; check the current version). Crypto runs 24/7 with no circuit breakers. Jarvus's stock gate is trained separately (7h horizon).

### Strategy encyclopedia
aka: all strategies, every strategy, list strategies, strategy list, strategy encyclopedia, 320 strategies
What: 320 strategies with rules and notes in `references/strategy-encyclopedia.md`; measured ones in `strategy-scoreboard.md`; 259 untested ideas in `strategy-library-untested.md`. Ask `know.py <strategy name>` for any one, or `know.py list strategies`.
