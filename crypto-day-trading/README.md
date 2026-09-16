# crypto-day-trading — a Claude skill

A drop-in skill that teaches Claude a professional crypto day-trading process:
market structure, indicators, derivatives data (funding, open interest,
liquidations), seven concrete setups, strict risk management, honest probabilistic
forecasting, journaling, and backtesting. It ships with Python tools (standard
library only, no API keys) that fetch live candles and positioning data, build a
market snapshot, size positions, keep a journal, scan multiple pairs, and
backtest rules.

It does not "predict" the market. Nobody can. It teaches Claude to find
positive-expectancy setups, size them so no single trade matters, and say "no
trade" when that is the honest answer.

About win rates: no file delivers a "real 85% win rate". Win rate is a dial (tiny
targets and wide stops hit 85% and lose money). The encyclopedia's Part 0 explains
the math and Part 2 gives the High-Probability Program: A-grade confluence only,
partial at 1R, one session, three trades a day. Executed, that produces 55-65% of
trades closing green with winners larger than losers, which is a professional
result.

## What's inside

```
crypto-day-trading/
├── SKILL.md                      the core instructions Claude reads (workflow, rules, output format)
├── references/                   the curriculum, loaded as needed
│   ├── market-structure.md       swings, trends, ranges, liquidity, sweeps, order blocks, sessions
│   ├── indicators.md             EMA, VWAP, RSI, MACD, ATR, Bollinger, volume, CVD
│   ├── crypto-market-data.md     funding, OI, liquidations, order flow, basis, on-chain, macro, catalysts
│   ├── risk-management.md        sizing, R multiples, stops, expectancy, limits, leverage, fees
│   ├── playbooks.md              seven day-trading setups with context/trigger/stop/target/invalidation
│   ├── probability-and-prediction.md  scenario maps, EV, base rates, calibration
│   ├── regimes-and-cycles.md     trend/range/chop/compression days, volatility regimes, cycle phase
│   ├── altcoins-and-memecoins.md alt beta, liquidity, catalysts, memes, alt risk rules
│   ├── execution-and-order-types.md  order types, entries, exits, stops that work, spot vs perps
│   ├── psychology-and-rules.md   tilt, FOMO, revenge trading, routine, stop-trading rules
│   ├── journal-and-backtesting.md  what to log, metrics, honest backtesting, overfitting
│   ├── worked-examples.md        six full interactions on live data
│   ├── strategy-encyclopedia.md  175 strategies in one format + win-rate truth + confluence scoring + decision table
│   └── glossary.md
├── scripts/                      Python 3.8+, standard library only
│   ├── fetch_ohlcv.py            candles from Binance/Coinbase/Kraken; --derivs from Binance/OKX/Bybit
│   ├── snapshot.py               multi-timeframe structure + indicators + setup flags + clock
│   ├── scan.py                   the same across many pairs in one call
│   ├── confluence.py             ten-factor confluence score and grade for a candidate trade
│   ├── position_size.py          size from the stop; leverage, liquidation, fee drag, R:R
│   ├── journal.py                log plans before the outcome, close after, review
│   ├── journal_stats.py          expectancy, profit factor, drawdown, per-playbook/session/grade
│   ├── backtest.py               pessimistic rule backtester with two sample strategies
│   ├── events.py                 verified 2026 FOMC/CPI/NFP dates, DST-aware, sessions, funding, CME
│   ├── indicators.py, tradestats.py   shared math
│   └── selftest.py               run this after installing
├── assets/
│   ├── trade-plan-template.md, pre-trade-checklist.md, daily-routine.md
│   ├── journal-template.csv, sample-journal.csv
│   └── event-calendar-2026.md
└── evals/evals.json              test prompts
```

## Install

### Claude Code (CLI, desktop, web)

Copy the folder into a skills directory. Claude picks it up automatically.

```bash
# for one project
mkdir -p .claude/skills && cp -r crypto-day-trading .claude/skills/
# or for every project
mkdir -p ~/.claude/skills && cp -r crypto-day-trading ~/.claude/skills/
python3 ~/.claude/skills/crypto-day-trading/scripts/selftest.py
```

Then ask anything trading-related ("what do you think of BTC?", "size a SOL short
for me", "review my journal") or type `/crypto-day-trading`.

### Claude.ai (web and desktop apps)

Option A, as a skill: build the package and upload it under Settings →
Capabilities → Skills (the exact menu name may differ by plan).

```bash
python3 build_single_file.py            # writes dist/crypto-day-trading.skill and dist/crypto-day-trading-all-in-one.md
```

Option B, as a Project: create a Project, paste the contents of `SKILL.md` into
the project instructions, and upload `dist/crypto-day-trading-all-in-one.md`
(every reference file in one document) as project knowledge. The scripts cannot
run inside a plain chat, so in this mode paste in current prices or a screenshot
and Claude will reason from those, or use Claude Code for live data.

### Claude API / your own app

Put `SKILL.md` in the system prompt and the reference files in context (or make
them retrievable). Expose the scripts as tools if your harness can execute Python.
The skill's Python tools are plain CLIs with `--json` output, so they wrap into
tool definitions directly.

## Quick start (Claude Code)

```
> what do you think of BTC right now?
> give me a long setup on ETH, 5,000 account, 1% risk, I trade perps on OKX
> should I long SOL here?
> scan BTC ETH SOL XRP DOGE for setups
> size this: entry 64200 stop 63550 target 65600, 10k account
> here are my trades (paste csv) — review my week
> does buying the pullback to the 21 EMA actually work? backtest it on BTC 15m
> explain funding rates like I'm new
```

## Manual tool use

```bash
cd crypto-day-trading/scripts
python3 scan.py --symbols BTC,ETH,SOL --derivs
python3 fetch_ohlcv.py --symbol BTCUSDT --interval 15m --limit 500 --out /tmp/btc_15m.csv
python3 snapshot.py /tmp/btc_15m.csv
python3 position_size.py --account 10000 --risk-pct 1 --entry 64200 --stop 63550 --target 65600
python3 journal.py init && python3 journal.py add --symbol BTCUSDT --playbook 1-trend-pullback --entry 64350 --stop 63780 --target 65900 --account 10000
python3 journal.py close --id 1 --exit 65100 --execution-grade 4
python3 journal.py stats
python3 backtest.py /tmp/btc_15m.csv --strategy ema_pullback --split 0.7
python3 events.py
```

Binance is geo-blocked in some regions; the fetcher falls back to Coinbase and
Kraken for candles and to OKX/Bybit for derivatives automatically.

## Maintaining it

- `scripts/events.py` holds the 2026 tier-1 calendar. Add next year's FOMC (federalreserve.gov), CPI and Employment Situation (bls.gov) dates each December.
- `references/playbooks.md` is where to add or retire setups. Keep the same structure (context, trigger, stop, target, invalidation, skip-when).
- `scripts/backtest.py` shows how to add a mechanical strategy: one function that returns a signal, registered in `STRATEGIES`.
- Run `python3 scripts/selftest.py` after any change.

## Disclaimer

Educational software. Not financial advice. Crypto is volatile; leveraged trading
can lose more than the margin posted. Most retail day traders lose money. The
skill's whole design is to make the user slower, smaller, and more selective.
