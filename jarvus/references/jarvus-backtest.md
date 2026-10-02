# Jarvus, backtested (Oct 2026): every rule, 900+ backtests, what was wrong, what changed

Jarvus's own rulebook was turned into code (`scripts/system_test.py`) and replayed on 5.75 years of real Coinbase
hourly candles: **majors** BTC, ETH, SOL and **memecoins** DOGE, SHIB, PEPE, BONK, WIF, FLOKI (about 280,000 candles,
Jan 2021 to Oct 2026). 350 backtests switched each rule off one at a time at three fee levels with 100 random
90-day windows per group; 114 more searched for improvements; 46 tested how robust the winner is; 412 compared the
old and new rules side by side (100 windows each). Results below are after fees and slippage, in R (1R = the
amount a trade risks).

Contents: 1 Short version · 2 How it was tested · 3 Jarvus v6 as written · 4 What each rule is worth ·
5 Problems found and fixed · 6 How the improvement was chosen · 7 v6 vs v6.1 · 8 Compared with just holding ·
9 What this does not show · 10 Re-running it

## 1. Short version

* **Jarvus v6 as written lost money on majors at every fee level**: at NDAX −0.073R per trade over 490 trades
  (t = −3.0, so not bad luck), −15.6% with an 18% drawdown; positive in only **2 of 100** random 90-day windows. On
  memecoins it was close to break-even and still negative: −0.034R, −4.5%, 25 of 100 windows positive.
* **Every protective rule earned its place**: the volatility gate, the weekend rule, the trend/regime rule, BTC
  first, the meme dead zone, the cost gate, the decision engine, the risk caps and limit (maker) entries each cut the
  losses. Taking the same signals with no rules lost everything (−100%).
* **The fix that made the difference: enter only when the gate says LOUD, keep the 4× ATR stop, take profit at 2R
  in one exit, and give the trade 96 hours** (dropping the Signal Card's "exit if +1R is not reached in 8 candles").
  Chosen on 2021–Mar 2025 only, then checked on later data.
* **v6.1 results** at NDAX fees: majors **+0.230R per trade, +23.2%, max drawdown 3.6%**, 106 trades (about 1.5 a
  month), positive in 49 of 100 windows (12 had no trade); memes **+0.186R, +4.2%, drawdown 3.3%**, 152 trades,
  39 of 100 windows positive. On the untouched last nine months: majors +0.172R (10 trades), memes +0.666R (17).
* **Honest size of it:** small and slow. Most of the in-sample gain sits in a period the gate was trained on; the
  later data is thin (26 majors trades, 54 meme trades after Mar 2025: +0.02R and +0.28R on average). Random entries
  under the same rules also made money, so the edge is **when** Jarvus trades (loud volatility inside an uptrend,
  wide stop, time to run), not the pattern that triggers the entry.
* **Six problems in the scripts and rules were found and fixed** (section 5), each with a test that proves it.

## 2. How it was tested

* **Rules, as SKILL.md v6 wrote them:** the playbooks exactly as Jarvus's scripts define them (`ladder.py`: P1
  trend pullback, P3 breakout retest, P4 sweep reclaim, P6 opening-range breakout, RSI(2) dip), the trained gate at
  every hour (QUIET = no trade, LOUD = 0.6× size), M4 no new majors trades Sat/Sun, M0 trend setups only with 1h and
  4h uptrends, bear regime (BTC below its 200-day average: majors take only reversion setups at half size, memes off),
  BTC first for memes (no meme longs while BTC's 4h trend is down), no meme entries 7 PM–midnight MT, cost gate
  (> 0.33R skip, 0.20–0.33R half), the decision engine learning from Jarvus's own closed trades (refused trades
  followed as shadow trades at half weight), 1% risk (0.5% for P4 and memes), daily −3R, 3 losses in a row ends the
  day, 2 majors trades a day, one majors position at a time (BTC/ETH/SOL count as one), 2 meme positions, weekly −6R,
  −5R from the peak = half risk, −10R = a week off, no leverage.
* **Management as the Signal Card said:** limit entry 0.1% under the signal close (valid 3 bars, unfilled = no
  trade), stop 4× ATR, half at +1R then stop to entry + fees, rest at +2R, exit if +1R is not reached within 8
  bars, else a 96-bar limit.
* **Fills, pessimistic:** stop and target touched in one bar = stop; a gap through the stop fills at the open;
  stops and time exits pay taker fee + slippage (2 bps majors, 10 bps memes, doubled on stops); targets are resting
  limits (maker).
* **One account, all coins of a group, in time order**, $10,000 start, compounding.
* **Three periods:** A = Jan 2021 – 19 Mar 2025, B = 20 Mar – 22 Dec 2025, C = 23 Dec 2025 – 1 Oct 2026. The gate was
  fitted on data inside A and its thresholds chosen inside B; **only C is completely unseen by it.** The playbooks were
  written earlier from general knowledge and v5's BTC study (2019–2026), so no period is perfectly untouched for them.

## 3. Jarvus v6 as written

| Group | Fees | Trades | Win | Avg R | t | Return | Max DD | A | B | C |
|---|---|---|---|---|---|---|---|---|---|---|
| majors | NDAX | 490 | 40% | −0.073 | −3.03 | −15.6% | 17.9% | −0.072 (412) | −0.126 (65) | +0.161 (13) |
| majors | low-fee | 1,101 | 48% | −0.035 | −2.17 | −17.1% | 21.1% | −0.032 | −0.071 | +0.088 |
| majors | Kraken Pro $0+ | 86 | 34% | −0.137 | −2.30 | −3.8% | 5.0% | −0.137 (then the engine benched everything) | — | — |
| memes | NDAX | 394 | 43% | −0.034 | −1.15 | −4.5% | 5.1% | −0.027 | −0.043 | −0.045 |
| memes | low-fee | 1,152 | 45% | −0.014 | −0.89 | −7.8% | 8.5% | −0.014 | −0.006 | −0.036 |
| memes | Kraken Pro $0+ | 61 | 36% | −0.143 | −2.26 | −2.5% | 2.9% | −0.143 (then benched) | — | — |

100 random 90-day windows (NDAX, fresh account each time): majors median −2.91%, average −3.21%, positive in 2;
memes median −0.63%, average −1.10%, positive in 25 (17 windows had no trade). Gross edge per trade was only
+0.024R (majors) against 0.097R of costs: the playbooks barely beat random before costs.

## 4. What each rule is worth (rules as written, NDAX fees; each row switches one thing)

| Change | Majors avg R / return | Memes avg R / return |
|---|---|---|
| **as written** | −0.073 / −15.6% | −0.034 / −4.5% |
| no volatility gate | −0.091 / −18.3% | −0.044 / −5.7% |
| no weekend rule | −0.103 / −20.6% | (memes exempt) |
| no trend/regime rule | −0.087 / −30.6% | −0.075 / −16.7% |
| no BTC-first rule | — | −0.043 / −6.2% |
| no meme dead zone | — | −0.061 / −8.6% |
| no cost gate | −0.080 / −19.4% | −0.034 / −4.3% |
| no decision engine | −0.101 / **−45.0%** | −0.043 / −16.2% |
| no risk caps / drawdown protocol | −0.090 / −26.2% | −0.055 / −13.2% |
| market (taker) entries | −0.093 / −21.5% | −0.063 / −9.7% |
| stop 2× ATR | −0.160 / −7.3% | −0.109 / −6.1% |
| stop 3× ATR | −0.100 / −11.1% | −0.051 / −6.6% |
| 80% Mode (half at +0.25R) | −0.082 / −16.8% (58% winners) | −0.069 / −7.9% (56% winners) |
| only P1 trend pullback | −0.186 (18 trades) | −0.097 (18) |
| only P3 breakout retest | −0.061 (219) | −0.018 (297) |
| only P4 sweep reclaim | −0.150 (12) | −0.118 (8) |
| only P6 ORB, before the fix | −0.091 (30) | −0.021 (150) |
| only P6 ORB, fixed | −0.101 (69) | **+0.031 (167)** |
| only RSI(2) dip | −0.150 (108) | −0.210 (18) |
| control: every 12th bar, no rules | −0.116 / −100% | −0.117 / −99.9% |

Same pattern at the low-fee and Kraken levels (Kraken: the engine stops trading within about 90 trades because
everything loses; that is the engine working). Full tables: `assets/system-test-results.md`.

## 5. Problems found, fixed and proved

| # | Problem | Fix | Proof |
|---|---|---|---|
| 1 | `confluence.py` gave the stop-quality point only to stops of 0.5–2.5× ATR, so the 4× ATR stop Jarvus requires scored 0 and a cost-killing 1× ATR stop scored 1 | The point now means: at least 1 ATR from entry **and** costs ≤ 0.20R at the chosen fee level; above 0.33R the verdict is a NO | `selftest.py`: a 3% stop at NDAX (0.15R) earns it; a 1% stop (0.44R) is blocked; the same 3% stop at Kraken Pro's entry tier (0.55R) is blocked |
| 2 | `confluence.py` charged a fixed 0.14R of costs on the reward factor and graded out of 10 with the old thresholds, while SKILL.md scores 11 factors (factor 0 = the gate) | Real cost in R at `--fees`; factor 0 added (`--gate`); SKILL.md thresholds (A+ 10–11, A 9, B 8) | `selftest.py` (eleven factors; QUIET and NORMAL blocked) |
| 3 | `position_size.py` assumed 0.05% fees per side by default, a quarter of NDAX's 0.20%: costs showed as 0.07R on a 2% BTC stop instead of 0.22R | Default `--venue ndax`; venues ndax, kraken, kraken10k, coinbase, low, stock | Same trade now reports 0.219R, matching `decide.py` |
| 4 | `ladder.py`'s opening-range breakout always used the 13:00 UTC bar; from November to March the US market opens at 14:30 UTC, so it fired inside the opening hour itself | The open range is the bar containing the US open (13:00 UTC in US summer time, 14:00 UTC in winter) | `selftest.py` winter case; ORB-only backtests: memes NDAX −0.021R → +0.031R, memes low-fee +0.016R → +0.058R, majors low-fee −0.095R → −0.029R (more trades); the 80% Mode experiment re-run: 79.8% green (was 79.5%), random entries 78.5% (was 78.6%): conclusions unchanged |
| 5 | The Signal Card's "exit if TP1 is not hit within 8 trigger-TF candles" was written for 5-minute triggers with tight stops; with the 4× ATR stop v5 made mandatory, +1R is 4 ATR away and is rarely reached in 8 hours, so most trades were cut early and paid fees for nothing | v6.1: no 8-candle exit; one exit at 2R or after 96 hours | Spot-checked trades (most v6 exits were "time"); v6.1 vs v6 tables below |
| 6 | Trading NORMAL-gate hours lost money in every version tested; random entries in NORMAL+LOUD hours lost −0.125R (majors), in LOUD hours only they made +0.114R | v6.1 enters only on LOUD (NORMAL = wait); `decide.py` and `confluence.py` enforce it (`--allow-normal` restores the old rule) | Sections 6–7 |

## 6. How the improvement was chosen (and why it is believable, and why only a little)

* **Search:** 3 playbook sets × 2 gate rules (as written / LOUD only) × 3 exit styles (as written; half at 1R + 2R
  over 96h; one exit at 2R over 96h) for each group and fee level (114 backtests). **Chosen on period A only.** The
  top choice in A was "LOUD only, 96h" at every fee level in both groups.
* **Then judged on B and C** (later data). At NDAX, "all playbooks, LOUD only, one exit at 2R, 96h": majors A +0.298R
  (80 trades), B −0.076 (16), C +0.172 (10); memes A +0.134 (98), B +0.102 (37), C +0.666 (17).
* **Robustness:** 18 neighbours per group (stop 3/4/5× ATR × 48/96/144h × one exit or half at 1R): 17 of 18 positive
  over the whole period on majors, 18 of 18 on memes; it is not a lucky setting.
* **Not outliers:** without the 5 best trades, majors still average +0.144R and memes +0.125R. Majors positive in 5 of
  6 years (2022, the bear year: 6 trades, −0.17R), memes in 4 of 5 (2023: −0.10R).
* **Random-entry control:** every-12th-bar entries under the same rules made +0.114R (majors) and +0.133R (memes).
  The setups added a little on majors (+0.23 vs +0.11) and nothing on memes. **The edge is the conditions**: a
  LOUD forecast, an uptrend (the M0 and BTC-first rules: removing them from memes cut the result to +0.037R and the
  last period to −0.053R), a stop wide enough for costs, and time for the move.
* **Why only a little:** the gate's LOUD calls in period A are in-sample (it was fitted there), so A flatters every
  LOUD variant. After Mar 2025 the evidence is 26 majors trades averaging about +0.02R and 54 meme trades averaging
  about +0.28R. Promising, not proven. Treat v6.1 as the best-supported rule set, keep journaling, and let the
  decision engine bench it if Abhi's own results turn negative.

## 7. v6 vs v6.1, side by side (same data, same windows)

| Group | Fees | v6 trades / avg R / return / max DD | v6.1 trades / avg R / return / max DD | v6.1 by period A · B · C |
|---|---|---|---|---|
| majors | NDAX | 490 / −0.073 / −15.6% / 17.9% | **106 / +0.230 / +23.2% / 3.6%** | +0.298 (80) · −0.076 (16) · +0.172 (10) |
| majors | low-fee | 1,101 / −0.035 / −17.1% / 21.1% | 106 / +0.277 / +26.3% / 3.8% | +0.342 · −0.020 · +0.228 |
| majors | Kraken Pro $0+ | 86 / −0.137 / −3.8% / 5.0% | 89 / +0.217 / +9.3% / 2.5% | +0.239 · +0.049 · +0.342 |
| memes | NDAX | 394 / −0.034 / −4.5% / 5.1% | **152 / +0.186 / +4.2% / 3.3%** | +0.134 (98) · +0.102 (37) · +0.666 (17) |
| memes | low-fee | 1,152 / −0.014 / −7.8% / 8.5% | 152 / +0.214 / +7.8% / 3.4% | +0.161 · +0.133 · +0.697 |
| memes | Kraken Pro $0+ | 61 / −0.143 / −2.5% / 2.9% | 144 / +0.066 / +1.9% / 2.9% | −0.010 · +0.010 · +0.590 |

100 random 90-day windows each (NDAX, fresh account): **majors** v6 average −3.21%, 2 up / 98 down; v6.1 average
+0.54%, 49 up / 39 flat or down / 12 without a trade (best +5.51%, worst −2.71%). **Memes** v6 average −1.10%, 25
up / 58 down; v6.1 average +0.18%, 39 up / 43 flat or down / 18 without a trade.

v6.1 trades about 1.5 times a month on majors and 2.4 on memes, at 0.6% risk (LOUD size) on majors and 0.3% on
memes. Returns are small because the risk is small and the trades are few: that is the design.

## 8. Compared with just holding (context, not a recommendation)

| Coin | Period | Buy and hold (max drawdown) | Hold only above the 200-day average (max drawdown) |
|---|---|---|---|
| BTC | A (2021 → Mar 2025) | +195% (77%) | +87% (37%) |
| BTC | B | +5% (32%) | 0% (20%) |
| BTC | C | −3% (40%) | +23% (7%) |
| ETH | A / B / C | +181% (79%) / +52% (43%) / −8% (53%) | +189% (32%) / +12% (39%) / +20% (5%) |
| SOL | A / B / C | +245% (96%) / −1% (52%) / −3% (58%) | +115% (59%) / −10% (33%) / +40% (11%) |
| DOGE | A / B / C | −56% (87%) / −22% (58%) / −27% (54%) | +4% (76%) / −28% (38%) / −20% (23%) |

Holding majors through 2021–2025 made far more than any trading rule here, with crushing drawdowns; the 200-day rule
roughly halved the drawdowns. Memecoins lost money held. For growth, a long-term core (DCA, the benchmark active
trading must beat: encyclopedia Part 20) matters more than trading; v6.1 is the careful, small part on top.

## 9. What this does not show

* No order book, no funding, no news: the confluence factors that need a chart read or derivatives data were not
  simulated; tier-1 event blackouts were not applied (hourly granularity).
* Memecoins here are exchange-listed survivors (Coinbase), not new DEX launches; the meme hard-fail list cannot be
  backtested with candles.
* Fills are modelled, not real; slippage is an assumption (2 bps majors, 10 bps memes per side).
* Period C is nine months and v6.1 traded 10 majors and 17 meme trades in it. That is a small sample. The decision
  engine is there for exactly this: if Abhi's own journal turns negative, it benches the setup.

## 10. Re-running it

```
python3 scripts/system_test.py --data DIR --download              # Coinbase hourly history, no keys (~10 min)
python3 scripts/system_test.py --data DIR --version v6.1 --group memes --fees ndax
python3 scripts/system_test.py --data DIR --battery --md report.md # every rule switched off, 3 fee levels, 200 windows
python3 scripts/system_test.py --data DIR --compare --md compare.md   # v6 vs v6.1 with 100 windows each
```
