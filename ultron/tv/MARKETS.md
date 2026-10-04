# Day trading every market: what matters, what ULTRON covers

Plain-language guide for a Canadian retail trader. Times are Mountain Time (Edmonton). The ULTRON numbers come from
our own walk-forward tests (`README.md`). Fees and spreads vary by broker; the "typical" figures here are rough
guides, so check your own.

## The five rules that hold in every market

1. **Direction is close to a coin flip on short timeframes. Volatility is not.** In our BTC hourly tests, "which way
   next" scored about 0.51 AUC (0.50 = coin flip), while "will the next 12 bars move big" scored about 0.72. On the
   untouched test, ULTRON's LOUD calls were right about 70–87% of the time on the 5m–4h crypto councils (base rate
   about 33%). ULTRON uses volatility to decide *when* to trade, and
   never claims to know *which way*.
2. **Cost in R decides whether a strategy can work at all.** Cost in R = round-trip cost ÷ stop distance. A 0.4%
   round trip against a 0.5% stop costs 0.8R per trade, and almost no edge survives that. This is why ULTRON's 5m and
   15m crypto councils found nothing after fees, and why its stops are wide (4× ATR, wider on fast charts).
3. **Size from the stop, never from conviction.** Size = (account × risk %) ÷ stop distance. Risk 0.25–1% per trade.
4. **Payoff beats win rate.** A 40% win rate at 2:1 makes money; a 90% win rate with one big loser can lose it all.
5. **Most day traders lose.** Large studies of real accounts:
   - Taiwan: fewer than 1% of day traders earned predictable profits after fees (Barber, Lee, Liu & Odean).
   - Brazil: 97% of people who day-traded futures for more than 300 days lost money (Chague, De-Losso & Giovannetti,
     "Day Trading for a Living?").

   Paper-trade first. Expect small, slow edges, not 10× months.

## Market by market

| Market | When it trades (MT) | Busiest, most tradable hours (MT) | What moves it | Typical cost per side | ULTRON |
|---|---|---|---|---|---|
| **Crypto** (BTC, ETH, SOL) | 24/7 | 6:00–10:00 (London/NY overlap); weekends thin | BTC trend, US macro data, ETF flows, funding and liquidations | 0.1–0.6% (NDAX 0.2%) | **Trained on 5m–1D** (see README) |
| **Meme coins** | 24/7 | same as crypto, in bursts | BTC direction × 4–10, hype, listings, unlocks | 0.2–0.6% + wide spreads | Trained with the crypto councils; off in bear regimes |
| **US stocks** | 7:30–14:00 (pre-market from 2:00, after-hours to 18:00) | 7:30–8:30 open, 13:00–14:00 close; lunch is slow | earnings, guidance, 6:30 data (CPI, jobs), 12:00 Fed days, sector moves | spread 0.01–0.05% on large caps; commission varies by broker | **Trained on daily charts** (AAPL, MSFT, NVDA, AMZN, GOOGL, META, TSLA, JPM, AMD, NFLX) |
| **Index ETFs** (SPY, QQQ, IWM, DIA) | as US stocks | open and close | macro data, Fed, mega-cap earnings | ~0.01% spread | **Trained on daily charts** |
| **Canadian stocks** (TSX) | 7:30–14:00 | open and close | banks, energy, oil price, Bank of Canada | spread 0.02–0.1% | **Trained on daily charts** (XIU, RY, TD, ENB, SHOP, CNQ) |
| **Forex** (EURUSD, GBPUSD, USDJPY, USDCAD, AUDUSD) | 24/5: Sun 15:00 – Fri 15:00 | 1:00–10:00 (London), 6:00–10:00 (overlap) | central banks, rate gaps, CPI and jobs data | 0.5–2 pips spread (EURUSD 1 pip ≈ 0.01%) | **Trained on daily charts** |
| **Gold / silver** (GLD, SLV) | as US stocks (futures nearly 24/5) | 6:00–11:00 | real interest rates, USD, fear | ~0.01–0.05% | **Trained on daily charts** |
| **Oil** (USO) | as US stocks (futures nearly 24/5) | 7:30–10:00; Wednesdays 8:30 (inventory report) | OPEC+, inventories, geopolitics | ~0.05% | **Trained on daily charts** |
| **Index futures** (ES, NQ) | Sun 16:00 – Fri 15:00, daily break 15:00–16:00 | 7:30–9:00 | macro data, Fed | 1 tick + commission; leverage is high | Not trained; use SPY/QQQ daily instead |

## Session habits worth knowing

- **US open (7:30 MT):** the first 30–60 minutes carry the most volume and the widest ranges; gaps from overnight
  news get filled or extended here. Spreads are widest in the first minutes.
- **Data releases (6:30 MT) and Fed decisions (12:00 MT):** volatility jumps instantly; stops can slip. Avoid
  opening new trades in the 30 minutes before and after.
- **Lunch (10:00–11:30 MT):** volume dries up, false breakouts are common.
- **Crypto weekends:** in our tests the models had no edge on weekends, so ULTRON skips new BTC/ETH/SOL trades then.
- **Forex Friday close / Sunday open:** gaps over the weekend; spreads widen at the Sunday open.

## Canada-specific notes (check with your broker or a tax professional)

- **Spot only, no leverage, is the safe default.** Offshore crypto perpetual futures are not available to Canadian
  retail; margin and CFDs multiply losses.
- **Day trading in a TFSA can make the gains taxable.** The CRA can treat frequent trading as carrying on a
  business. The same applies to frequent trading in a regular account: profits may be taxed as business income
  rather than capital gains.
- **Currency conversion** on US stocks can cost more than the commission (often 1–2% at some brokers). A USD account
  avoids converting on every trade.
- **US brokers** apply pattern-day-trader rules to margin accounts. Check the current rule if you use one.

## What ULTRON covers today, and why

| Market | Timeframes with a trained council | Why not more |
|---|---|---|
| Crypto (9 coins) | 5m, 15m, 30m, 1h, 2h, 4h, 1D | 5m and 15m found no edge after fees, so they stay flat by default |
| Stocks, ETFs, forex, gold, silver, oil (28 markets) | 1D | Free intraday history for these markets only goes back about 2 years, too short for an honest walk-forward test. On intraday charts the table says so and the council stays flat |
| Anything else | none | Runs only if you switch on "Also run on markets it was not trained on" (untested) |

Every number in the README comes from the trained model files, never typed by hand. The untouched test period
(since Dec 2025) was never used to choose anything.
