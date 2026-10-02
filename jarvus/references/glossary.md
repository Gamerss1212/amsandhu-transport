# Glossary

Quick definitions of terms a user may use. Longer treatment lives in the other
reference files.

**ADL (auto-deleveraging)**: an exchange forcibly closing profitable positions to
cover a bankrupt counterparty when the insurance fund is insufficient.

**Alt / altcoin**: any cryptocurrency other than Bitcoin. Higher beta to BTC.

**Anchored VWAP**: VWAP calculated from a chosen candle (a major swing) rather than
the session open.

**Ask / bid**: lowest sell offer / highest buy bid. The gap is the spread.

**ATR (average true range)**: average candle range over N periods; the volatility
unit used for stops and targets.

**Basis**: futures price minus spot price. Annualized, it is the cost of leverage.

**Bear / bull trap**: a breakdown (breakout) that reverses quickly, trapping the
traders who chased it. Same mechanism as a liquidity sweep.

**Beta**: how much an asset moves relative to a benchmark (for alts, relative to
BTC).

**BOS (break of structure)**: price closing beyond the prior swing in the trend
direction. Continuation.

**BTC.D (Bitcoin dominance)**: BTC's share of total crypto market cap.

**Candle close**: the price at the end of the candle's period. Closes confirm;
wicks tease.

**CHoCH (change of character)**: price closing beyond the most recent swing
against the trend. First warning of reversal.

**CME gap**: the difference between CME Bitcoin futures' Friday close and Sunday
reopen. Tends to fill.

**Cross / isolated margin**: whether all account equity backs a position (cross) or
only the margin assigned to it (isolated).

**CVD (cumulative volume delta)**: running total of market buy volume minus market
sell volume. Shows aggression.

**Deviation**: a brief move outside a range that closes back inside. Failed
breakout.

**DXY**: US dollar index. Inversely correlated with crypto most of the time.

**Engulfing**: candle whose body fully covers the prior candle's body in the
opposite direction.

**Equal highs / lows (EQH / EQL)**: two or more swings at nearly the same price.
Liquidity magnets.

**Expectancy**: average R per trade. The scoreboard.

**Fair value gap (FVG) / imbalance**: three-candle gap where price moved too fast
to trade at intermediate prices. Often partially filled.

**Funding rate**: periodic payment between perp longs and shorts to pin the perp
to spot. Positive means longs pay.

**HH / HL / LH / LL**: higher high, higher low, lower high, lower low. Trend
definitions.

**HTF / LTF**: higher / lower timeframe.

**Liquidation**: forced closure of a leveraged position whose margin is exhausted.

**Liquidity (in the structural sense)**: a cluster of resting stop orders that
large players can trade into.

**Liquidity sweep / stop hunt**: a spike through a liquidity pool followed by a
close back inside.

**Maker / taker**: limit order that adds liquidity / market order that removes it.
Taker fees are higher.

**Max pain**: the strike price at which the most options expire worthless. Price
sometimes gravitates toward it into expiry.

**Measured move**: projecting the length of a prior leg or the height of a range
from a breakout point to estimate a target.

**OI (open interest)**: total notional of open derivative positions.

**Order block**: the last opposing candle before an impulsive move that broke
structure. Used as a pullback zone.

**PDH / PDL**: prior day high / low. Tier-1 intraday levels.

**Perp (perpetual swap)**: a futures contract with no expiry, kept near spot by
funding.

**Pin bar**: candle with a long wick and small body; rejection.

**Profit factor**: gross wins divided by gross losses.

**R / R multiple**: the initial risk on a trade, and outcomes measured in units of
it.

**Range**: price bounded between a ceiling and a floor with overlapping swings.

**Retest**: price returning to a broken level to confirm it as the opposite kind
of level.

**RVOL (relative volume)**: current volume divided by average volume.

**Scalp**: a very short trade for a small move. Fee-sensitive; usually a bad
business for retail.

**Slippage**: difference between the expected and actual fill price.

**Squeeze (short / long)**: a sharp move forced by the losing side closing or being
liquidated. Also: a Bollinger squeeze, a volatility contraction.

**Swing high / low**: a local extreme with lower highs (higher lows) on both sides.

**Tier-1 event**: scheduled data release with reliable volatility (CPI, FOMC, NFP).

**Token unlock**: scheduled release of previously locked tokens to insiders. Supply
overhang.

**VWAP**: volume weighted average price for the session.

**Walk-forward**: backtesting method that tunes on one window and tests on the
next, repeatedly.

**Wick**: the part of a candle beyond its body. A wick through a level that closes
back is rejection.


## More terms (from the Jarvus Terminal and its knowledge pack)

**Cost in R**: round-trip trading costs (fees both ways + slippage) divided by the stop distance. Above 0.33R Jarvus refuses the trade; 0.20-0.33R means half size.

**Volatility gate**: a trained forecast of whether the next 12 hours (crypto) or 7 hours (stocks) will move a lot (LOUD), little (QUIET) or normally. Says nothing about direction. `scripts/volgate.py`.

**Brain**: the Jarvus Terminal's decision layer that took, resized or refused every bot signal from costs, the volatility gate and measured results. `references/decision-engine.md`, `scripts/decide.py`.

**Shadow trade**: a refused trade followed anyway on paper, to learn what refusing it was worth.

**Holm correction**: a way to raise the bar for significance when many strategies are tested at once, so that luck across many tries is not mistaken for an edge.

**Deflated Sharpe ratio**: a Sharpe ratio adjusted for how many strategies were tried and for non-normal returns; near 0 means the best result is what luck alone would produce.

**Walk-forward / chronological split**: testing on data that comes after the data used to build or choose the rule, never shuffled; with an embargo gap so information cannot leak across the boundary.

**Candidate (strategy)**: in the Terminal's protocol, a strategy-market pair positive on both the training and validation periods with 30+ trades; only candidates were looked at on the untouched test period.

**Time-weighted return**: performance that ignores deposits and withdrawals by chaining the returns between them.

**Alpha**: Expected return beyond an explicitly chosen benchmark or model; not a synonym for a profitable-looking chart.

**Adverse selection**: Receiving a fill just before the market moves against that position, often because the counterparty has better information or timing.

**Bid**: The highest currently displayed offer to buy on the specified book or consolidated feed.

**Basis point**: One hundredth of a percentage point; 100 basis points equals 1 percent.

**Borrow locate**: A broker's required process for establishing a basis to expect shares can be borrowed where applicable; not an eternal guarantee of borrow availability.

**Borrow recall**: A demand to return borrowed securities, which can force a short position to be closed.

**Buying power**: Broker-calculated available capacity under account, margin and house rules; not the same as cash balance.

**Capacity**: The capital or order size a strategy can absorb before its costs and market impact materially change results.

**Cointegration**: A statistical relationship in which a combination of nonstationary series can be stationary under a specified model and sample.

**Colocation**: Locating trading infrastructure near exchange systems to reduce communication latency; access and cost are institutional constraints.

**Corporate action**: An issuer event that changes securities, ownership, distributions or symbol/quantity conventions.

**Counterparty risk**: Risk that an exchange, broker, clearing entity, issuer or other contractual counterparty fails to meet its obligations.

**Cross margin**: A venue arrangement sharing collateral across eligible positions; exact netting and liquidation rules are product-specific.

**Day order**: An order whose validity ends under the venue's definition of the trading day/session.

**Delisting bias**: Excluding securities or tokens that later disappeared, potentially overstating historical results.

**Dollar-neutral**: Long and short notionals balance; this does not necessarily make a portfolio beta-neutral or risk-free.

**Embargo**: A deliberate exclusion interval in a validation design to limit information contamination; its placement and length need justification.

**Event-driven backtest**: A simulation that processes timestamped data, decisions, orders, acknowledgments and fills in causal order.

**Fill**: An actual or explicitly simulated execution of all or part of an order.

**FOK**: Fill-or-kill order instruction: execute the required entire quantity immediately under supported rules or cancel.

**Free float**: Shares considered available for public trading under a data provider's definition; updates and corporate actions matter.

**GTC**: Good-till-cancelled instruction, subject to venue expiration and corporate-action policies.

**Hidden liquidity**: Orders or portions not fully displayed in the visible order book; absence from L2 is not proof of absence.

**Hedge ratio**: The quantity or notional relation chosen to offset a defined exposure; units and estimation method must be explicit.

**Information interval**: The time range of observations needed to form a feature or realize a label; overlapping intervals can contaminate validation.

**IOC**: Immediate-or-cancel instruction: execute available quantity immediately under supported rules and cancel the remainder.

**Isolated margin**: Collateral assigned to a particular position or product under venue-specific rules.

**Latency**: Delay between observation, receipt, decision, submission, arrival and execution; these are separate intervals.

**Legging risk**: Exposure created when a multi-leg trade executes incompletely or at different times.

**Lookahead bias**: Using information in a historical decision that was unavailable at that decision's real time.

**Mark price**: A venue-defined valuation reference often used for derivative risk calculations; it differs from last trade and executable bid/ask.

**Market impact**: The effect of an order's own trading on available prices and subsequent market behavior.

**Market regime**: An operational classification of conditions such as trend, range, volatility or liquidity, estimated causally with uncertainty.

**MEV**: Value obtainable from transaction ordering or inclusion in blockchain systems; can change swap outcomes and hedge timing.

**NBBO**: US national best bid and offer under the applicable consolidated quote rules; it is not an entire depth book or a universal crypto quote.

**OCO**: One-cancels-other linkage between orders; supported behavior and cancellation races depend on the venue or client implementation.

**Open interest**: Outstanding derivative contracts or positions under a venue's counting convention, distinct from trading volume.

**Overfitting**: Selecting a model that explains sample-specific noise and fails to generalize.

**Paper trading**: Simulated order execution against a broker or local test environment; it does not establish real market fills.

**Point-in-time data**: Data representing what was actually known and available at the historical decision time.

**Post-only**: An instruction intended to avoid immediately taking liquidity; it may reject or adjust depending on venue rules.

**Purging**: Removing training observations whose information/outcome intervals contaminate an evaluation period.

**Queue priority**: The order-ranking rule governing which resting orders execute first at a price; not universally simple FIFO.

**R multiple**: PnL divided by a predeclared initial planned risk amount; state whether PnL and risk include costs.

**Reduce-only**: An order restriction intended to reduce an existing derivative exposure without increasing it, under exact venue semantics.

**Repainting**: Historical-looking indicator values or signals differing from what was observable in real time; causes and severity vary.

**Residual**: The difference between an observed value and a fitted model's prediction; it is not necessarily mean reverting.

**Risk of ruin**: Probability of crossing a specified capital-loss or insolvency threshold under a model; assumptions dominate the estimate.

**Round trip**: An entry and subsequent exit of a defined exposure; partial fills and reversals require consistent grouping.

**Shadow trading**: Producing and logging proposed actions alongside live markets without placing those orders.

**Short interest**: Outstanding short positions measured under the reporting system's schedule; usually not a live tape of every short trade.

**Spread capture**: Earning differences between purchase and sale quotes; inventory losses and adverse selection can outweigh it.

**Stationarity**: A statistical property of a process under a specified definition; a historical test does not guarantee future stability.

**Stop-limit**: A triggered order that becomes a limit order; price control creates non-execution risk.

**Survivorship bias**: Evaluating only instruments or strategies that remain observable/successful and omitting historical failures.

**Taker**: An execution removing existing liquidity under venue rules, typically with a corresponding fee classification.

**Tick size**: Minimum permitted price increment for a given instrument and price tier.

**Time stop**: A maximum holding deadline even if no price-based exit has triggered.

**Turnover**: Trading activity relative to capital under a specified definition; one-way and two-way definitions differ.

**Walk-forward evaluation**: Repeated fitting on preceding data and evaluation on later data, with results aggregated from evaluation segments only.

**Memecoin**: An informal category of crypto assets associated with memes, cultural themes, attention, or communities; the label does not define transfer behavior, value, or legal treatment.

**Token deployment identity**: A chain/network and specific contract or mint, distinguished from a ticker, logo, wrapped representation, and native asset.

**Bonding curve**: A protocol-defined relationship between traded quantities or state and price; parameters, real reserves, and virtual reserves must be distinguished.

**Graduation**: A launch platform's transition criterion or event, often associated with migration to another trading venue; not a guarantee of success or safety.

**Migration**: Movement of trading state or liquidity to another pool or protocol, requiring identity and accounting reconciliation.

**Virtual reserves**: Pricing quantities used by some protocols that need not correspond to transferable assets actually held in a vault.

**Economic float**: A defined estimate of supply available for economic trading after explicit exclusions; often uncertain and different from reported total supply.

**Mint authority**: A capability to create additional token units where supported; its presence and revocation are only part of the authority graph.

**Freeze authority**: A capability to restrict token-account activity under the relevant program, distinct from general market illiquidity.

**Permanent delegate**: A mint-level privileged capability in the documented Solana extension, distinct from an ordinary holder-granted allowance.

**Transfer hook**: Custom logic invoked during token transfer under a supporting token system; it may alter route requirements or reject transfers.

**Transfer tax**: An informal label for token-level deductions or charges during movement; exact computation and recipients are contract-specific.

**Proxy upgrade**: A change to the implementation used behind a stable contract address; previously reviewed behavior may no longer apply.

**Authority graph**: A representation of owners, roles, delegates, upgrade controls, timelocks, and dependent programs that can affect an asset.

**LP lock**: A restriction on withdrawing specified liquidity rights under particular conditions; coverage, unlock time, and revocability must be verified.

**Honeypot token**: A colloquial description of a token that attracts purchases while restricting or making sales uneconomic; a scanner result is conditional evidence.

**Rug pull**: An informal description of abrupt value extraction or abandonment harming holders; mechanisms differ and a heuristic flag is not a legal finding.

**Sybil activity**: Activity from multiple identities or addresses that may be controlled by one actor; raw address counts do not establish independent participants.

**Wallet cluster**: Addresses grouped by an explicitly stated heuristic or verified label, with uncertainty and historical availability retained.

**Copy trading**: Following another participant's observable trades; follower prices, delays, costs, and inventory risks differ from the source trader's.

**Wallet baiting**: Behavior designed to make a wallet appear attractive to followers before unfavorable trades or inventory exits; discussed here as a defensive risk.

**Wash-trading candidate**: Activity flagged as possibly circular or non-economic by a stated method; not automatically proof of intentional manipulation.

**Economic swap**: One intended exchange of assets by an initiating trader, potentially implemented through multiple pool-level instructions.

**Pool leg**: An individual interaction within a route; several legs can belong to one economic swap.

**Executable exit capacity**: The inventory that can be sold within stated cost and state assumptions, unlike market capitalization or a displayed last price.

**Quote impact**: The expected change in average execution economics caused by trade size under the quoted state, using a declared reference.

**Slippage tolerance**: A bound embedded in an execution request, often expressed through minimum output; not a prediction or guaranteed realized cost.

**Priority fee**: An optional transaction scheduling payment under the applicable chain rules, distinct from swap fees and other tips.

**Transaction tip**: An additional payment associated with certain submission paths or services; account for its actual conditions and currency.

**Bundle**: A group of transactions submitted with service-specific sequencing and execution semantics; acknowledgement and final settlement are separate states.

**Finality policy**: The explicit rule governing when observations or transactions are treated as sufficiently settled and how reversals are handled.

**Point-in-time universe**: The assets and eligibility information actually available at each historical decision time, including later failures.

**Graduation bias**: Selection bias caused by studying only launches that reached a later platform milestone.

**Attention conversion**: An operational comparison between measured attention and subsequent purchasing activity; generally an association, not identified causality.

**Paid visibility**: Advertising or promoted placement that must be tagged separately from organic participation and security evidence.

**Active liquidity**: Capital available at the current price under a pool's range or bin mechanics, distinct from all assets deposited in the pool.

**Price bin**: A discrete price region or point used by some liquidity protocols, with protocol-specific allocation and fee behavior.

**LP markout**: A measurement of how execution prices compare with later references from the liquidity provider's perspective, used to study adverse selection.

**Hypothesis lineage**: An explicit link between a contextual variant and its broader parent concept, preventing variants from being mistaken for independent discoveries.
