# Validation methodology

Applies to every evaluation result in `results/` and in the workbook's *Evaluation Results* sheet.

## Principles
1. **Parameters are fixed before data is seen.** Each strategy's parameters are written in its definition; the
   evaluation never searches or tunes them. This removes in-sample optimisation, but not the selection bias of
   choosing which of 127 strategies to trust, which is handled by the multiple-testing steps below.
2. **No look-ahead.** Every indicator is causal (tested: values computed on a truncated history equal values
   computed on the full history, for every registered indicator); decisions use completed bars only; higher
   timeframes are aligned to the last bar that had closed; swing points are published only after confirmation.
3. **Same code as live.** Backtests drive the same `TradeManager` the live bots use.
4. **Costs always on.** Crypto is evaluated at three cost levels: gross (no costs, to show the raw edge), a low-fee
   venue (OKX base-tier fees, not verified for Canadian residents) and **retail Kraken fees (0.40% maker / 0.80%
   taker, the rate Kraken publishes for the lowest tier)**. Stocks: commission-free with regulatory sell fees and
   assumed spreads by liquidity tier, plus a 2x slippage stress.

## Data and splits
- Crypto: Coinbase 5-minute bars (about 120 days) for BTC-USD, ETH-USD, SOL-USD; 15m/1h/4h/1d aggregated from 5m;
  1-minute BTC-USD (14 days); ETH-BTC and USDT-USD (60 days); OKX BTC-USDT and its perpetual swap (30 days).
- Stocks: Yahoo Finance 5-minute bars (the free limit is 60 days) for SPY, QQQ, NVDA, AAPL, TSLA, with hourly and
  daily bars for higher-timeframe rules.
- Each series is split chronologically **train 60% / validation 20% / test 20%**, with a **one-day embargo** after
  each boundary. All strategies are intraday and flat at the end of every session, so no trade can span a boundary
  (purging is automatic).
- **Walk-forward:** the full period is also cut into 4 consecutive folds; the share of folds with a positive net
  return is reported as a stability check.

## Selection and out-of-sample testing
- A (strategy, instrument) pair becomes a **candidate** only if, at the realistic cost level, it had positive
  expectancy on **both** train and validation with at least 30 trades combined.
- The **test** segment is looked at once, for candidates only. A strategy is marked **out-of-sample tested** only
  in that case; otherwise it is **backtested**.

## Multiple testing
- Every (strategy, instrument, cost level) run is one hypothesis. The count is recorded (`hypothesis_tests`).
- p-values: one-sided t-test that the mean per-trade R on train+validation is above zero; **Holm-Bonferroni**
  across all hypotheses (family-wise error 5%).
- The best validation Sharpe ratio is **deflated** (Bailey and Lopez de Prado 2014) for the number of trials.

## Metrics reported
Trades, long/short split, win rate, average win/loss, profit factor, expectancy (currency and R), median R, t-stat,
net and gross return, fees and fee share of gross profit, annualised return, Sharpe, Sortino, max drawdown, Calmar,
worst/best trade, max consecutive losses, average bars held, exposure, trades per day, daily skew, kurtosis, 95% VaR,
average MFE/MAE. Returns are on a fixed capital base (no compounding) with 0.5% risk per trade.

## Separate kinds of evidence (never merged)
- In-sample (train), validation and out-of-sample (test) backtests on historical bars.
- Paper observations from the live fleet (the staged runs), reported separately with their own counts.
- External reports (sources in the register), never presented as our results.

## Known limitations
- 60 days of 5-minute stock data and ~120 days of crypto data are short samples; many strategies trade rarely, so
  their intervals are wide. Results describe these windows, not the future.
- Stock fills use bars plus assumed spreads (no free quotes); crypto backtests use bar prices plus modelled
  slippage, while the live paper engine walks real order books.
- Order-flow strategies cannot be backtested (no free historical trades/books); they are evaluated only by paper
  observation.
