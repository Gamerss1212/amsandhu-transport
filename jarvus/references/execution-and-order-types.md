# Execution and Order Types

A correct plan executed badly loses money. This file covers how to get into and
out of a position on a crypto exchange without giving away the edge.

## Contents

1. Order types
2. Getting in
3. Getting out
4. Stops that actually work
5. Spot vs perpetuals: what changes
6. Slippage, spread, and liquidity
7. Exchange mechanics to know before the first trade
8. Execution checklist

---

## 1. Order types

| Order | What it does | Use for |
|---|---|---|
| **Market** | Fills now at whatever the book offers | Entries when speed matters (sweep reclaim), all exits at invalidation |
| **Limit** | Rests at a price; fills only there or better; usually pays maker fee | Planned entries at a level, profit targets |
| **Stop-market** | Becomes a market order when price trades through the trigger | The protective stop. The default. |
| **Stop-limit** | Becomes a limit order at the trigger | Almost never for stops: in a fast move the limit may not fill and the position stays open |
| **Take-profit** | The exchange's name for a stop-market or stop-limit on the profit side | Targets when you cannot watch the screen |
| **OCO** (one cancels other) | Pairs a target and a stop; whichever fills cancels the other | The cleanest way to hold a plan on the exchange |
| **Reduce-only** | The order can only shrink the position, never flip it | Every stop and target on a perp. Prevents an accidental reverse position |
| **Post-only** | Rejects the order if it would fill immediately as taker | Ensures maker fee on entries; can miss the fill |
| **Trailing stop** | Stop follows price by a fixed distance or % | Trailing a runner; set the distance from ATR, not a round % |
| **Conditional / trigger** | Places any order when a trigger price hits | Automating "enter on reclaim of X" |
| **TWAP / iceberg** | Splits a large order over time or hides size | Only relevant for size that would move the book |

Mark price vs last price: on perps, stops and liquidations usually trigger on the
**mark price** (an index-based fair value), not the last trade. Set trigger type
to mark price for stops to avoid being wicked out by a single bad print, and
understand that a real move will trigger the stop either way.

## 2. Getting in

Three entry styles, in order of quality:

1. **Limit at the level** (playbooks 1, 2, 3). The plan says "buy the retest of
   64,350". Rest a limit there, stop already placed. Maker fee, no chasing. Cost: it
   may never fill; missing a trade costs nothing.
2. **Confirmation entry** (playbook 4, 7). Wait for the trigger candle to close
   (the reclaim), then market in. Worse price by a few tenths of a percent; higher
   win rate because the trigger is real. Taker fee.
3. **Scaling in** at two or three prices across the zone, with the total size
   equal to the computed size and the stop below the whole zone. Improves average
   price; adds complexity. Only for levels wide enough to justify it.

Never: market buying a green candle because it is moving. That is a C-grade
entry with the worst price, the widest stop, and the smallest target.

Order size precision: exchanges enforce minimum notional and step sizes. Round
the computed size *down* to the nearest step. `position_size.py` gives the exact
units; the exchange decides the rounding.

## 3. Getting out

The plan defines three exits: stop, T1, T2. Place them as orders, not intentions.

- **Stop**: stop-market, reduce-only, trigger on mark price, placed the moment
  the entry fills (or as an OCO with the entry where supported).
- **T1**: limit, reduce-only, for the scale-out portion (a third to a half). When
  it fills, move the stop to breakeven plus fees.
- **T2**: limit, reduce-only, for the remainder; or trail the stop behind each new
  higher low (longs) on the trigger timeframe.
- **Time stop**: if the trade has gone nowhere for roughly 3-4x the expected
  duration of the setup (for a 15m setup, a few hours), exit at market. Dead
  trades tie up mental capital and eventually become losers.

Partial exits at "it looks weak" without a rule are the most common way to turn a
positive-expectancy plan into a negative one. The rule is written down in
advance; the screen does not get a vote.

## 4. Stops that actually work

- **On the exchange, always.** A mental stop is a plan to hold a loser.
- **Beyond the invalidation plus buffer** (see `risk-management.md`), not at a
  round number, not exactly at the level, not where it "feels" right.
- **Stop-market, not stop-limit.** The stop's job is to get out. A limit that does
  not fill defeats the purpose.
- **Mark-price trigger** on perps.
- **Check the liquidation price** is far beyond the stop (3x the stop distance).
- **Move only toward the entry**, and only after T1 or after structure has
  confirmed (a new higher low above entry). Moving to breakeven immediately turns
  good trades into scratches when the first pullback tags entry.
- Widening a stop is the one thing that is never allowed.

If the exchange goes down, the stop goes down with it. That is why size is capped
and why a second venue for a hedge is worth setting up for anyone trading
meaningful size.

## 5. Spot vs perpetuals: what changes

| | Spot | Perp |
|---|---|---|
| Direction | Long only (or short via margin) | Long and short natively |
| Leverage | 1x (or margin, rarely worth it) | Up to 100x+; use ~3-5x max effective |
| Funding | None | Paid/received every 8h (or hourly) |
| Liquidation | None | Yes, at the liquidation price |
| Fees | Usually higher | Usually lower |
| Stops | Available on most exchanges | Available, mark-price triggered |
| Suitable for | Beginners, longs in an uptrend, no time pressure | Shorts, capital efficiency, experienced traders |

A beginner should trade spot for the first 50-100 journaled trades. It removes
liquidation, funding, and the temptation of leverage from the learning process.
The R math is identical.

## 6. Slippage, spread, and liquidity

- **Spread** on BTC/ETH majors is usually a fraction of a basis point during
  liquid hours; on small alts it can be 0.1-0.5%, which is a meaningful share of a
  1% stop.
- **Slippage** is worst in the minutes after a news event, in the Asia session on
  alts, and on weekends. A market order into a thin book can fill 0.2-1% away on a
  small alt. Stops, being market orders, suffer the same.
- **Depth check** before trading an alt: if the size to move price 1% is less than
  ~20x the intended position, the position is too large for that market.
- **Liquid hours**: roughly 07:00-16:00 UTC (London) and 13:30-20:00 UTC (New
  York; an hour later in US winter) for
  majors. Alts follow their community's time zone as well; many Asia-based tokens
  are liveliest 00:00-08:00 UTC.

Fees and slippage together are the reason scalping for 0.2-0.3% moves is a losing
business for almost everyone. The stop distance should be at least 5-10x the
round-trip cost.

## 7. Exchange mechanics to know before the first trade

- **Margin mode**: isolated for day trades. Cross only with a clear reason.
- **Position mode**: one-way vs hedge mode. In hedge mode a "buy" may open a
  separate long instead of closing a short. Know which mode is active.
- **Reduce-only** on every exit order.
- **Leverage setting vs actual leverage**: the leverage slider sets margin
  requirements, not position size. Size still comes from the stop.
- **Funding timestamps** and whether the venue pays hourly or every 8 hours.
- **Insurance fund and ADL** rules: in extreme moves, profitable positions can be
  force-closed. Rare, but it happens on the biggest days.
- **Maintenance margin tiers**: bigger positions get lower max leverage and a
  closer liquidation price.
- **API keys**: trade permission only, never withdrawal; IP-restricted.
- **Withdrawal whitelist and 2FA**: on before any real money.
- **Test with a tiny order** first on any new venue or new order type. Fee
  structure, rounding, and trigger behavior differ between exchanges.

## 8. Execution checklist

- [ ] Entry order type matches the playbook (limit at level, or market on confirmed trigger)
- [ ] Size rounded down to the exchange's step; notional above the minimum
- [ ] Stop-market, reduce-only, mark-price trigger, placed with or immediately after the entry
- [ ] T1 and T2 limit orders placed, reduce-only
- [ ] Liquidation price checked: at least 3x the stop distance away
- [ ] Isolated margin; position mode understood
- [ ] Funding settlement time checked if the trade may run through it
- [ ] Time stop noted in the journal entry
