# Jarvus v6.1 — Abhi's spot trading skill, with the Jarvus Terminal built in, backtested

Jarvus is a terse, spot-only crypto day-trading assistant for Abhi: Majors
(BTC / ETH / SOL on NDAX or Kraken Pro) primary, a survival-sized meme sleeve
secondary. It returns a Signal Card (BUY / WAIT / NO with entry, stop, targets,
size and a confluence grade), keeps the journal, reports expectancy, coaches on
tilt, and teaches.

## What v6.1 adds: Jarvus backtested, fixed and improved

Jarvus's whole rulebook was turned into code (`scripts/system_test.py`) and replayed on 5.75 years of
Coinbase hourly data for BTC, ETH, SOL and six memecoins (900+ backtests; `references/jarvus-backtest.md`,
full tables in `assets/system-test-results.md`).

- **As written, v6 lost money** on majors at every fee level (NDAX: −0.073R per trade, t −3.0, up in 2 of
  100 random 90-day windows) and was slightly negative on memecoins. Every protective rule cut the losses.
- **Six problems fixed, each proved by a test:** confluence's stop-quality point rewarded tight stops (now
  judged on cost in R); confluence used a fixed 0.14R cost and the old 10-factor grading (now real costs, 11
  factors); `position_size.py` assumed 0.05% fees (now NDAX 0.20% by default); the ORB setup used the wrong
  hour from November to March; the Signal Card's 8-candle time stop cut 4× ATR trades before they could work;
  NORMAL-gate trading lost money in every version.
- **v6.1 rules:** enter only when the gate says LOUD, stop 4× ATR, one exit at 2R, up to 96 hours (plus every
  existing protective rule). Chosen on 2021 to Mar 2025, then checked on later data: majors +0.230R per
  trade, +23.2%, max drawdown 3.6%; memes +0.186R. Small and slow, thin after Mar 2025, and said so.

## What v6 added: the whole Jarvus Terminal

The Terminal (a desktop program with 311 bots, a learning brain, a trained volatility gate and paper
trading at live prices, Sept–Oct 2026) is retired. Everything it knew and measured, and the way it
decided, now lives in this skill:

- **`scripts/volgate.py`** — the Terminal's trained volatility gate (crypto next 12h, stocks next 7h):
  LOUD / NORMAL / QUIET with what held-out testing says about each reading, plus the trend regime.
  Identical readings to the Terminal (checked by `selftest.py`).
- **`scripts/decide.py`** — the Terminal's brain for one trade: cost gate, QUIET, bench, learned edge
  (from the measured strategy results plus Abhi's own journal), size multiplier. TAKE / RESIZE / SKIP.
- **`scripts/goal.py`** — the goal calculator: required daily return and the measured outcome spread of
  the whole system at five fee levels and five account sizes.
- **`references/terminal-evidence.md`** — every measurement: 146 strategies (0 significant after
  correction), the swing lab, 3,000 full-system replays, results by fee level and by account size
  ($100 → $10M), brain experiments, the gate's test results, live paper running, verified fees.
- **`references/decision-engine.md`**, **`any-balance-and-goals.md`**, **`live-trading-and-brokers.md`**.
- **`references/strategy-scoreboard.md`** — 146 strategies with exact rules and every measured run;
  **`strategy-library-untested.md`** — 259 more ideas and the data each would need.
- The knowledge pack: **`handbook-day-trading.md`**, **`handbook-memecoins.md`**, its 77 sources, its
  glossary (merged), its memecoin screening thresholds; the **`rule-language.md`** indicator registry.
- **Fees corrected:** Kraken Pro's entry tier is 0.40% maker / 0.80% taker (Sept 2026), not 0.16/0.26;
  the cost table and venue advice are updated (NDAX by default).

Rebuild the generated scoreboard from the repository with `python3 jarvus/tools/build_scoreboard.py`.

## What v4 added to v3

v4 keeps every v3 rule (honesty rules, Majors gates M0–M3, meme hard-fail list,
meme score, Gate 0 kill switch, staged validation, Mountain Time session rules)
and absorbs the entire `crypto-day-trading` skill (Sept 2026 build):

- **10 operating principles** (higher timeframe first, structure before
  indicators, stop before entry, size from the stop, minimum 2R, BTC first,
  score before plan, "no trade" is an answer, regime decides, journal first)
- **10-factor confluence score** → A+ / A / B / skip → risk 1% / 1% / 0.5% / 0
- **7 playbooks** in full (trend pullback, range edge fade, breakout-retest,
  liquidity-sweep reversal, funding/OI fade, ORB, VWAP reclaim) with the
  v3 setups (ORB, VWAP 2σ fade, sweep reversal, CME gap) mapped onto them
- **Regime classification** (trend / range / chop / compression) and the
  playbook × regime table
- **Hard no-trade conditions**, full **risk chapter** (3R day / 6R week /
  3R concurrent, drawdown protocol, scaling, quarter-Kelly ceiling, custody)
- A **cost-in-R rule** for spot fees (round trip ≤ 20% of 1R)
- **Coach mode** (tilt recognition, mechanical stop-trading rules, how to
  respond), the daily routine and pre-trade checklist
- **Probability language** (low / medium / high calibrated), scenario maps,
  base rates, the "85% win rate" truth and the High-Probability Program
- **Encyclopedia mode**: 175 strategies across 15 families, strategies that
  lose and why, decision table by regime / session / experience
- **12 Python tools** (candles, derivatives, snapshot, scan, confluence, sizing,
  journal, stats, backtest, events, selftest) — standard library only
- A **Mountain Time clock** (`assets/jarvus-clock-mt.md`) so every UTC time in
  the curriculum maps to Edmonton

Adaptations made for Abhi: spot only (short-side setups become flat / sell /
wait), perps data is information only, Canadian venues and their fees, all
times in MT, risk 0.5–1% with a fixed 1% cap until 50 logged trades.

## Layout

```
jarvus/
├── SKILL.md                  the core Claude reads (v3 rules + absorbed curriculum)
├── references/               the v5 curriculum (structure, indicators, market data, risk, playbooks,
│                             320-strategy encyclopedia, probability, regimes, alts/memes, execution,
│                             psychology, journal/backtesting, worked examples, glossary) + v6:
│                             terminal-evidence, decision-engine, strategy-scoreboard,
│                             strategy-library-untested, any-balance-and-goals,
│                             live-trading-and-brokers, handbooks, sources, rule-language
├── assets/                   templates, checklist, routine, 2026 event calendar, MT clock, journals,
│                             volgate_model.json, strategy_scoreboard.json, projection_inputs.json,
│                             memecoin-screening-rules.json
└── scripts/                  fetch_ohlcv, snapshot, scan, confluence, position_size, journal,
                              journal_stats, backtest, events, indicators, tradestats, ladder,
                              experiment_80, volgate, decide, goal, system_test, selftest
```

## Install

**Claude.ai (web / desktop / mobile):** Settings → Capabilities → Skills →
upload `jarvus.skill` (or press **Save skill** on the file card), replacing the previous Jarvus. The scripts cannot reach
exchange APIs from a plain chat sandbox, so in chat paste current numbers or use
`Jarvus screen`; Claude reasons from what it can see.

**AI Trading project (as knowledge):** upload `jarvus-all-in-one.md` (every file
in one document) as project knowledge and paste `SKILL.md` into the project
instructions.

**Claude Code / Desktop / Cowork (live data):**
```bash
mkdir -p ~/.claude/skills && cp -r jarvus ~/.claude/skills/
python3 ~/.claude/skills/jarvus/scripts/selftest.py
```

## Commands

`Jarvus` · `Jarvus BTC|ETH|SOL` · `Jarvus map <coin>` · `Jarvus check <address>` ·
`Jarvus scan [majors|memes]` · `Jarvus screen` · `Jarvus size <entry> <stop> <target>` ·
`Jarvus events` · `Jarvus routine` · `Jarvus teach <topic>` · `Jarvus what about <strategy>` ·
`Jarvus backtest <rule>` · `Jarvus journal` · `Jarvus review` · `Jarvus kill` ·
`Jarvus gate [coins]` · `Jarvus decide <entry> <stop> [target]` · `Jarvus goal <balance> [goal] [days]` ·
`Jarvus scoreboard <strategy|market>` · `Jarvus fees` · `Jarvus live` · `Jarvus system test`

## Disclaimer

Educational, not advice. Crypto is volatile; most retail day traders lose money.
Jarvus's whole design is to make the user slower, smaller, and more selective.
