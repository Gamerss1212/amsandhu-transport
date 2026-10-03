# Jarvus v6.3 — Abhi's spot trading skill: bare calls, backtested, with the Jarvus Terminal built in

Jarvus is a terse, spot-only crypto day-trading assistant for Abhi: Majors
(BTC / ETH / SOL on NDAX or Kraken Pro) primary, a survival-sized meme sleeve
secondary. It returns the call (BUY / WAIT / NO, and on BUY where to buy, sell and
stop, the size and the exit time), keeps the journal, coaches on tilt, and teaches.

## 24/7 watcher (`scripts/watch.py`, bundle `dist/jarvus-watch.zip`)

A skill only runs when you message it. `watch.py run` keeps checking SOL ETH BTC DOGE BONK every 10 minutes on your own
computer (no Claude usage) and sends a phone/desktop/Discord alert when a coin turns BUY (once, with a 4-hour cooldown),
a daily "alive" message, and a warning if the data feed fails. Setup: `watch/README-WATCH.txt`. Rebuild the bundle with
`python3 build_watch_bundle.py`. Optional cloud version: `watch/github-actions-jarvus-watch.yml`.

## v7 rule change: P7 4h momentum

The best signals from the measurement became playbook P7 (`scripts/momentum.py`). In the full-rulebook backtest,
memes allowed to take P7 on NORMAL hours went from +0.19R to +0.33R per trade (better in all three periods, 59 vs 39
of 100 windows up); majors were about neutral. Details and the caution: `references/jarvus-backtest.md` §11.

## What v7 adds: a measured trading library, read one entry at a time

- **~220 short entries** in `references/kb-*.md`: every common candlestick pattern, chart pattern and
  price-structure idea (SMC/ICT, Wyckoff, Elliott, Fibonacci, harmonics), ~60 indicators, Bitcoin/crypto
  (halving, cycles, on-chain, funding, open interest, liquidations, ETFs, Canada), meme-coin mechanics
  (bonding curves, LP, mint/freeze authority, bundles, rugs) and day-trading concepts (order types, order flow,
  volume profile, risk, Kelly, backtesting, psychology). The 320-strategy encyclopedia, scoreboard and manual are
  searchable the same way.
- **`scripts/know.py <topic>`** prints one entry (about 100–450 tokens) instead of Claude reading whole files.
- **Jarvus measured 133 signals itself** (`tools/measure_signals.py`): 45 candle patterns, 24 chart patterns,
  59 indicator signals and its 5 playbooks, on BTC ETH SOL DOGE SHIB PEPE BONK WIF FLOKI hourly data (Dec 2020 to
  Oct 2026), 1h and 4h, bought with Jarvus's exits at NDAX fees and compared with random entries, split into
  early/late halves. 11 of 493 cells beat random and made money in both halves, all momentum/breakout signals
  (mostly on 4h): big green candle, volume spike on a green candle, RSI(14) above 70, MFI above 80, Donchian 55,
  Keltner breakout, five green candles, big 24h rally, plus the 50/200 golden cross on memes 1h. Reversal candle
  patterns, chart patterns, MACD, oversold RSI/stochastics and the ICT entries did not. Results:
  `references/kb-measured.md`, `assets/signal_results.json`.
- SKILL.md routes every knowledge question to `know.py` (no more reading or grepping reference files).

## What v6.3 changed: only the call, nothing else

- `jarvus.py card BTC` now prints one line when there is nothing to do
  (`BTC $85,484 → WAIT · next 12h: normal move, direction unknown`) and three on a BUY
  (`Buy … · Sell … · Stop … · Size $… · out by <day time> MT`, then the expected move size).
  `--why` adds the reasons, `--full` prints the old long card.
- Claude replies with the script output word for word and nothing else ("Not advice." once).
- "Where is the market going": the expected move size for the next 12 hours from the volatility gate.
  The direction is never guessed, because no test found it predictable.
- SKILL.md is ~610 tokens (was ~1,100 in v6.2, ~17,100 in v6.1).

## What v6.2 added: built to use as little Claude usage as possible

- **SKILL.md is ~1,100 tokens instead of ~17,100** (the always-loaded description ~140 instead of ~250). Every
  rule still exists: the full v6.1 rulebook moved word for word to `references/manual.md`, read by section only
  when a question needs it.
- **`scripts/jarvus.py` does the analysis in one call** and prints a 5-line card (`card BTC`) or one line per
  market (`scan`): data, volatility gate, trend, BTC regime, weekend and meme rules, playbook detection, cost in
  R, the plan and the size. Claude relays it instead of reading reference files and reasoning it out.
- **Short replies by default** (≤ 8 lines), grep-a-section instead of reading whole files.
- A typical "Jarvus BTC" went from roughly 27,000 tokens of instructions, references and script output to
  roughly 1,600 (estimate: 4 characters per token).
- `dist/jarvus-lite.md` (lean rules + manual) for a Claude.ai Project; `dist/jarvus-all-in-one.md` keeps everything.

## What v6.1 added: Jarvus backtested, fixed and improved

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
                              experiment_80, volgate, decide, goal, system_test, jarvus (one-call card/scan), selftest
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
