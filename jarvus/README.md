# Jarvus v4 — Abhi's spot crypto day-trading skill

Jarvus is a terse, spot-only crypto day-trading assistant for Abhi: Majors
(BTC / ETH / SOL on NDAX or Kraken Pro) primary, a survival-sized meme sleeve
secondary. It returns a Signal Card (BUY / WAIT / NO with entry, stop, targets,
size and a confluence grade), keeps the journal, reports expectancy, coaches on
tilt, and teaches.

## What v4 adds to v3

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
├── references/               14 files: structure, indicators, market data, risk, playbooks,
│                             175-strategy encyclopedia, probability, regimes, alts/memes,
│                             execution, psychology, journal/backtesting, worked examples, glossary
├── assets/                   trade-plan template, pre-trade checklist, daily routine,
│                             2026 event calendar (UTC), jarvus-clock-mt.md, journal templates
└── scripts/                  fetch_ohlcv, snapshot, scan, confluence, position_size,
                              journal, journal_stats, backtest, events, indicators, tradestats, selftest
```

## Install

**Claude.ai (web / desktop / mobile):** Settings → Capabilities → Skills →
upload `jarvus.skill`, replacing the previous Jarvus. The scripts cannot reach
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
`Jarvus backtest <rule>` · `Jarvus journal` · `Jarvus review` · `Jarvus kill`

## Disclaimer

Educational, not advice. Crypto is volatile; most retail day traders lose money.
Jarvus's whole design is to make the user slower, smaller, and more selective.
