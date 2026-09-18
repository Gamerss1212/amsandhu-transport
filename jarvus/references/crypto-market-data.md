# Crypto-Specific Market Data

What makes crypto different from stocks or FX is the derivatives layer (perpetual
swaps with funding), transparent positioning data, 24/7 trading, and a heavy
correlation structure between coins. This file explains each data source, how to
read it, and how much to trust it.

## Contents

1. Perpetual swaps and funding rates
2. Open interest
3. Liquidations and liquidation levels
4. Order book and order flow
5. Basis and the futures premium
6. Stablecoins and exchange flows
7. Bitcoin dominance, ETH/BTC, and alt beta
8. Macro correlations
9. Catalysts and the event calendar
10. Where to get the data
11. Trust ranking

---

## 1. Perpetual swaps and funding rates

A **perpetual swap** ("perp") is a futures contract with no expiry. To keep its price
pinned to spot, longs and shorts pay each other a **funding rate**, usually every 8
hours (00:00, 08:00, 16:00 UTC on Binance, Bybit, OKX; some venues hourly).

- **Positive funding**: perp trades above spot; longs pay shorts. The crowd is long.
- **Negative funding**: perp below spot; shorts pay longs. The crowd is short.

Reading it (8-hour rate, BTC/ETH; alts run hotter):

| Funding (8h) | Annualized | Read |
|---|---|---|
| +0.01% | ~11% | Baseline. Neutral. Ignore. |
| +0.03% to +0.05% | 33-55% | Longs are crowded. Trend can continue, but pullbacks get violent. |
| above +0.10% | >100% | Extreme. Long squeezes (cascading liquidations down) are likely on any dip. |
| -0.01% to -0.03% | | Shorts paying. Short squeeze fuel if price holds a level. |
| below -0.05% | | Extreme short crowding. Squeezes up are violent. |

How to use it as a day trader:

- Funding is a **filter**, not a signal. Do not short because funding is high;
  short when funding is high **and** price rejects a level **and** OI is elevated.
  Crowded plus a structural excuse is the pattern.
- Trending markets carry elevated funding for days. "It's extreme so it must
  reverse" has cost people fortunes.
- The **rate of change** matters: funding flipping from negative to strongly
  positive within a day means the short crowd got squeezed and a fresh long crowd
  replaced it; the market is now vulnerable the other way.
- Before settlement, expect some traders to close to avoid paying. Small,
  short-lived, but real.

## 2. Open interest

**Open interest (OI)** is the total notional of open perp/futures positions. It
tells you whether a move is being driven by new positions or by closing ones.

| Price | OI | Interpretation |
|---|---|---|
| Up | Up | New longs. Trend supported by fresh money. Healthy, but building squeeze fuel. |
| Up | Down | Short covering. The rally is forced buying, not conviction. Fades sooner. |
| Down | Up | New shorts. Trend supported. Building short-squeeze fuel. |
| Down | Down | Long liquidation / capitulation. Usually late in a decline. Watch for a base. |

Rules:

- **OI spike into a level** (say, OI up 5% in a few hours while price grinds into
  resistance) means a large, leveraged crowd has just positioned. Whichever way
  price breaks, the losing side will be liquidated and the move will be fast.
- **OI reset** (a sharp drop of 10%+) after a cascade clears the leverage. The
  market is cleaner afterwards and trends that start after a reset are more
  trustworthy.
- Compare OI in **coin terms** across time (dollar OI moves with price and
  misleads).

## 3. Liquidations and liquidation levels

When a leveraged position's margin runs out, the exchange force-closes it with a
market order. Liquidations are **forced flow**: they do not care about price.

- A **long liquidation cascade**: price falls, longs get liquidated, their forced
  sells push price lower, more longs get liquidated. Produces the vertical red
  candles crypto is famous for. Same in reverse for shorts.
- **Liquidation heatmaps** (Coinglass, Hyblock and similar) estimate where clusters
  of liquidation prices sit, based on leverage used at each entry. They are
  **magnets**: price is drawn to large clusters because there is guaranteed flow
  there. Treat a big cluster like a liquidity pool from `market-structure.md`.
- After a cascade, the **reversal is often sharp** because the forced flow is
  exhausted and the book is thin. Cascade lows in an uptrend are good long
  locations once price reclaims the pre-cascade level.
- Watch the **liquidation totals** for the last 1-4 hours. Very large totals
  (hundreds of millions on BTC) mean the leverage is flushed; small totals during
  a big move mean the move is spot-driven and more durable.

## 4. Order book and order flow

- **Depth**: how much size sits within 1-2% of price. Thin depth means slippage and
  wicks. Weekends and the hours after the US close are thin.
- **Walls**: large resting orders. They are visible and can be pulled instantly
  (spoofing). A wall that gets *eaten* and price moves through is a real signal; a
  wall sitting there is not.
- **Imbalance**: bid depth divided by ask depth within a band. Persistent imbalance
  over minutes has mild predictive value; instant readings do not.
- **Aggressive vs passive**: market orders (aggressive) move price; limit orders
  (passive) absorb. CVD (see `indicators.md`) tracks the aggressive side. The
  informative moments are when aggressive flow is large and price does not move
  (absorption) or price moves on little aggressive flow (a thin book, expect a
  retrace).
- **Tape / time and sales**: large prints clustered at a level indicate an active
  participant. Useful for scalping on the 1m; noise on anything higher.

## 5. Basis and the futures premium

- **Basis** = futures price minus spot price. For dated futures (CME, quarterlies)
  the annualized basis is the market's cost of leverage.
- Rising basis alongside rising price means leveraged demand is growing (late-cycle
  behavior when very high, e.g. 20%+ annualized). Basis collapsing toward zero or
  negative (backwardation) happens at panic lows and is a strong contrarian
  bullish read on the multi-day horizon.
- **CME gaps**: CME BTC futures close Friday 21:00 UTC and reopen Sunday 22:00 UTC
  (an hour later in US winter time).
  Whatever spot does over the weekend creates a gap on the CME chart. Gaps fill
  most of the time, often within days, sometimes within hours of the reopen. Not a
  law; a tendency worth knowing when placing weekend and Monday trades.

## 6. Stablecoins and exchange flows

On-chain data is slow (hours to days) and belongs to swing analysis, but it sets the
backdrop for the day:

- **Stablecoin supply** (USDT + USDC market cap) growing: new money entering.
  Shrinking: money leaving. Multi-week trend context.
- **Exchange stablecoin reserves** rising: dry powder on exchanges. Bullish backdrop.
- **Exchange BTC/ETH netflow**: coins flowing *to* exchanges are being positioned to
  sell; flowing *out* are being held. Large single-day inflows (tens of thousands of
  BTC) precede volatility.
- **Whale alerts** (large transfers): mostly noise unless the destination is an
  exchange and the size is unusual.

Do not trade intraday off any of these alone. Use them to lean the bias.

## 7. Bitcoin dominance, ETH/BTC, and alt beta

Almost every altcoin is a leveraged bet on Bitcoin plus a coin-specific story.

- **Beta**: a typical large alt moves 1.5-3x what BTC moves intraday; small caps
  more. If BTC drops 2%, expect your alt to drop 3-6% regardless of its chart.
- **Analyze BTC first**, always, even when the user asks about SOL or a meme coin.
  A pristine alt setup against a BTC breakdown is a losing trade.
- **BTC dominance (BTC.D)** rising: money rotating to BTC, alts underperform. Falling
  with BTC steady or rising: "alt season" conditions, alts outperform. Falling with
  BTC falling: alts are bleeding even harder.
- **ETH/BTC** is the classic risk-appetite gauge within crypto. Rising ETH/BTC
  usually accompanies broad alt strength.
- **BTC ranging quietly** is the best environment for alt day trading: alts move on
  their own catalysts without being dragged. BTC trending hard sucks all volume
  into itself.
- Alts have **token unlocks** (scheduled release of locked supply to insiders and
  investors). Check the unlock calendar; a large unlock (more than ~2% of
  circulating supply) inside the next few days is a headwind.

## 8. Macro correlations

Since 2020 BTC has traded like a high-beta risk asset most of the time.

- **Nasdaq / S&P futures**: positive correlation, strongest during US hours. When
  equities gap down at the US open (13:30 UTC in summer, 14:30 in winter), crypto
  usually follows within minutes.
- **DXY (dollar index)**: inverse. A strong-dollar day is a headwind.
- **US 10-year yield / real yields**: inverse, especially at extremes.
- **Gold**: weak and unstable relationship. Do not lean on it.
- Correlations **break** during crypto-specific events (exchange failure, ETF news,
  regulation) and during liquidation cascades. Check whether today's move is
  "macro" (everything moving together) or "crypto" (BTC moving alone). Trade
  accordingly: macro moves respect macro levels and times; crypto moves respect
  crypto levels.

## 9. Catalysts and the event calendar

Scheduled events with reliable volatility. Times are UTC in US summer time; add one
hour to the New York-linked rows in US winter (early November to mid-March).
`scripts/events.py` holds the verified 2026 dates and converts them.

| Event | When | Effect |
|---|---|---|
| US CPI | monthly, 12:30 (13:30 winter) | Sharp two-way move, then direction. Flat 30 min before, trade the retest after. |
| FOMC decision + presser | 8 meetings/yr, 18:00 + 18:30 (19:00 winter) | Whipsaw. The first move is often reversed. Flat until the presser is over. |
| NFP (US jobs) | usually first Friday, 12:30 (13:30 winter) | Similar to CPI, slightly smaller. |
| US equities open/close | 13:30 / 20:00 (14:30 / 21:00 winter) | Volume spike, correlation spike. |
| Funding settlement | 00:00, 08:00, 16:00 | Minor positioning shifts. |
| Deribit options expiry | daily 08:00; monthly last Friday 08:00 | Monthly expiries pin price toward "max pain" into expiry, then release. |
| CME open/close | Sun 22:00 / Fri 21:00 (one hour later in winter) | Gap creation and fill tendency. |
| Token unlocks | per project | Supply overhang for that alt. |
| Exchange listings (Binance, Coinbase, Upbit) | ad hoc | Spike, then usually fade within hours to days. |
| ETF flow reports | daily, after US close | Next-day sentiment for BTC/ETH. |

Unscheduled: exchange hacks or insolvencies, regulatory actions, large protocol
exploits, major-figure statements. These override every technical level. When
news hits, stand aside for at least 15-30 minutes until the first move and its
retrace are done.

## 10. Where to get the data

`scripts/fetch_ohlcv.py --derivs` pulls funding, open interest, and the
long/short ratio from Binance's public futures endpoints (no key). For the rest,
these are the commonly used free or freemium sources; availability changes, so
verify:

- Funding, OI, liquidations, heatmaps: Coinglass, Coinalyze, Hyblock, Velo
- Order flow / CVD / footprint: TradingView (some), Exocharts, Tensorcharts
- On-chain and exchange flows: CryptoQuant, Glassnode, Arkham
- Calendar: ForexFactory (macro), TokenUnlocks / Tokenomist (unlocks), Deribit (expiry)
- Dominance and market overview: TradingView (BTC.D, TOTAL, TOTAL2), CoinGecko

When the user does not have access to one of these, say which piece of the picture
is missing and reduce confidence accordingly.

## 11. Trust ranking

For intraday decisions, from most to least reliable:

1. Price structure and closes on the setup timeframe
2. Volume and RVOL
3. Session/time context and the scheduled calendar
4. Funding + OI together (positioning)
5. Liquidation clusters (as magnets)
6. CVD and order-book absorption (needs tooling)
7. BTC.D / ETH/BTC (rotation)
8. On-chain flows (background only)
9. Order-book walls, whale alerts, social sentiment (mostly noise, easily faked)
