# Altcoins and Memecoins

Most of the user's questions will be about coins other than Bitcoin, because that
is where the excitement is. Everything in the other reference files applies, plus
the adjustments here. Alts are where accounts blow up fastest, so the risk rules
get stricter, not looser.

## Contents

1. Alts are leveraged BTC plus a story
2. Tiers and how to treat each
3. Liquidity and why it decides everything
4. Catalysts that move alts
5. Memecoins specifically
6. Screening a pair before trading it
7. Risk adjustments for alts
8. Rotation: when alts work and when they do not

---

## 1. Alts are leveraged BTC plus a story

Over any intraday window, the largest driver of an alt's price is Bitcoin. A typical
large-cap alt has an intraday beta of 1.5-3 to BTC; small caps and memes 3-6. The
coin-specific "story" (a listing, an unlock, a narrative) adds or subtracts on
top.

Practical rules:

- **Read BTC first**, every time. An alt long into a BTC breakdown is a losing
  trade with a nice-looking chart.
- **Alts lag by minutes**: BTC makes the move, alts follow. On a BTC sweep-and-
  reclaim, the alt entry is often still available a few candles later.
- **Alt/BTC pairs** (ETH/BTC, SOL/BTC) show relative strength. An alt making higher
  lows against BTC while BTC chops is the one that will run first when BTC moves.
- **BTC dominance rising** means alt longs are fighting the tide.

## 2. Tiers and how to treat each

| Tier | Examples (illustrative) | Beta to BTC | Liquidity | How to trade |
|---|---|---|---|---|
| Majors | ETH, SOL, BNB, XRP | 1.2-2.5 | deep on all venues | All seven playbooks apply; slightly wider ATR buffers |
| Large caps | top ~50 by cap | 2-3 | good on top venues, thin elsewhere | Trend and sweep playbooks; avoid Asia-session breakouts |
| Mid/small caps | top 50-300 | 3-5 | thin; spreads matter | Only with a clear catalyst; half size; spot preferred |
| Memes | DOGE, SHIB, PEPE and the week's new ones | 4-10+ | anything from deep to nonexistent | See section 5; quarter size; expect to be wrong often |
| New launches / low float | days old | undefined | can vanish | Not day trading. Speculation with money you can lose entirely |

## 3. Liquidity and why it decides everything

An alt's liquidity determines slippage on entry, slippage on the stop, and whether
the stop will fill anywhere near its price.

Check, before trading a pair:

- **24h volume** on the venue you will use (not aggregated). Below a few million
  dollars, day trading with meaningful size is impractical.
- **Order book depth** within 1% of price. The position should be under ~5% of
  that depth.
- **Spread**. Above 0.1% and a 1% stop has lost 10% of its R to spread alone.
- **Wick behavior**: pull up the 5m chart. If ordinary candles have wicks of 1-2%,
  stop placement needs buffers that make 2R targets unreachable. Skip.

Thin alts also get **manipulated** more easily: spoofed walls, coordinated pumps,
and stop hunts at obvious levels are the norm rather than the exception.

## 4. Catalysts that move alts

- **Exchange listings** (Binance, Coinbase, Upbit especially): sharp spike on the
  announcement, often faded within hours to days. The high-probability trade is
  usually *not* buying the announcement candle but shorting the exhaustion or buying
  the retrace to pre-announcement structure, once that structure holds.
- **Token unlocks**: scheduled release of locked supply. Unlocks over ~1-2% of
  circulating supply create a sell-side overhang for days before and after. Check
  the unlock calendar before any multi-hour alt long.
- **Mainnet launches, upgrades, airdrops**: "buy the rumor, sell the news" is a
  real base rate here. Price often tops on or just before the event.
- **Narratives** (AI, RWA, L2s, memes, whatever the month's theme is): rotate
  capital between sectors. A narrative pump lasts days to weeks; the first day is
  the strongest and the reversal is brutal. Trade the pullbacks within the
  narrative's trend, never the fourth day's breakout.
- **Funding and OI on the alt itself**: alts reach funding extremes far more often
  than BTC (0.1%+ per 8h is common during a pump). An alt with +0.15% funding,
  soaring OI, and a first lower high on the 1H is a prime squeeze-down candidate.
- **Token burns, buybacks, treasury moves**: minor unless enormous.
- **Founder / team drama, exploits, depegs**: unscheduled and overriding. Flat and
  away.

## 5. Memecoins specifically

Memes have no fundamentals, so they are pure flow and attention. That makes them
*more* technical, not less, on the intraday horizon, but with these differences:

- **Volume is the whole story.** A meme with rising volume is alive; one with
  fading volume is dying, and dying memes rarely resurrect the same week. Trade
  only the live ones.
- **Beta cuts both ways.** A 5% BTC dip is a 20-40% meme drawdown. Position size
  must reflect the actual ATR (often 10-20% daily), which means very small
  notional.
- **Round-trip time is short.** Meme trends on the 15m chart last hours. Take T1
  fast, trail hard.
- **Social signals lead by minutes, not days.** By the time a meme is trending on
  social feeds, the first leg is done. Useful mainly as a "which ones are alive
  today" filter.
- **Manipulation is the baseline.** Assume every wall is fake and every round
  number will be swept.
- **On-chain memes** (DEX-only tokens): rug risk, sandwich bots, honeypot
  contracts, no stops. Not day trading. If the user insists, the only risk rule
  that matters is "money you are fine never seeing again", and the skill should
  say so plainly.

Playbooks that work on memes: #1 (pullback to 21 EMA / VWAP on the 5m-15m in a
strong volume trend), #4 (sweeps of obvious lows during a live trend), #7 (VWAP
reclaims). Playbooks that get killed on memes: #2 (range fades: memes do not
respect ranges; they leave them at 30% per hour), #5 (funding is always extreme).

## 6. Screening a pair before trading it

Run `scripts/scan.py --symbols X,Y,Z --derivs` and then check, for any pair that
flags:

1. BTC's state (from the same scan). Aligned or at least not opposed?
2. 24h volume on the venue and the spread.
3. ATR% on the setup timeframe. If a normal stop is 3-5% away, is the 2R target
   realistic within the session?
4. Funding on the alt. Extreme in the direction of the planned trade is a red flag.
5. Unlock or event calendar for that token in the next 72 hours.
6. Is there a reason this coin and not BTC/ETH? If the same setup exists on a
   major, take the major. Alts are for when they offer something the majors do not
   (relative strength, a catalyst, a cleaner level).

## 7. Risk adjustments for alts

- Risk per trade: **0.5%** on large caps, **0.25%** on small caps and memes,
  regardless of how good it looks.
- Effective leverage: **spot or ≤ 2x**. Alt wicks liquidate 5x positions routinely.
- Stop buffer: **0.5 ATR** minimum (vs 0.3 on majors) because wicks are wider.
- Correlated exposure: two alt longs plus a BTC long is one position at 3x the
  intended risk. Count them as one.
- Max concurrent alt positions: **2**.
- Time stop: shorter. Alt setups that do not work within an hour or two on the
  15m usually do not work.
- Never hold an alt day trade through a token unlock or a major BTC event.

## 8. Rotation: when alts work and when they do not

| BTC state | Alts | Tactics |
|---|---|---|
| Quiet range, low ATR | Best environment. Alts move on their own stories. | Trade alt setups normally (with alt risk sizing) |
| Strong trend up | Alts lag at first, then catch up violently ("alt season" if sustained) | Buy alt pullbacks once BTC pauses; watch BTC.D for the rotation |
| Strong trend down | Alts fall 2-3x as much | No alt longs. Alt shorts on bounces into resistance, small |
| Volatile chop, high ATR | Alts get whipsawed; stops everywhere | Stand aside or trade BTC only |
| Post-cascade recovery | Beaten-down alts bounce hardest | Sweep-reversal longs on the alts with the best relative strength |

The question "which alt will pump?" has no honest answer. The answerable version
is "which alts are showing relative strength and a valid setup right now, and is
BTC letting them run?" That is what the scanner is for.
