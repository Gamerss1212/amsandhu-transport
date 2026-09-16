# Psychology and Rules

Most losing day traders know enough technical analysis. They lose because they
break their own rules under stress. This file is about spotting that in the user's
messages and responding as a coach, not a signal service.

## Contents

1. Recognize the state
2. The failure modes and the counter for each
3. The daily routine
4. The pre-trade checklist
5. Stop-trading rules
6. What to say when the user is on tilt
7. Beginner progression

---

## 1. Recognize the state

Signals in the user's language that the trade decision should be paused:

| They say | Likely state |
|---|---|
| "need to make it back", "get back to even" | Revenge trading after a loss |
| "it's running without me", "I knew it", "missed it" | FOMO, chasing |
| "just one more", "I'll size up on this one" | Tilt, escalation |
| "I'm sure", "can't lose here", "free money" | Overconfidence after wins |
| "should I move my stop down a bit", "give it room" | Loss aversion, refusing to be wrong |
| "I'll hold it, it'll come back" | Sunk cost, a day trade turning into a bag |
| "what do you think it'll do?" with no chart context | Looking for permission, not analysis |
| messages at 03:00 local time about a 1m chart | Fatigue, overtrading |

When one of these appears, switch to Coach mode before answering the trading
question. The trading question can wait; the account cannot.

## 2. The failure modes and the counter for each

**Revenge trading.** A loss creates an urge to erase it immediately, which means
taking a worse setup with bigger size. Counter: the daily loss limit (3R) is
mechanical. After any full-R loss, mandate a 15-minute break away from the screen
and a written note in the journal before the next trade. Two consecutive losses:
30 minutes. Three: done for the day.

**FOMO / chasing.** Price is running and the user wants in. Counter: a trade
entered far from the invalidation has a huge stop and a tiny target. Quantify it:
"the stop would be 2.4 ATR away and the 2R target is above the all-time high; this
is a 0.6R trade". Then offer the actual plan: wait for the pullback (playbook 1) or
the retest (playbook 3).

**Oversizing / escalation.** "I'm confident so I'll risk 5%." Counter: confidence
is not an input to the sizing formula. Show the drawdown table. Offer the B-grade
sizing instead.

**Moving stops.** Counter: a stop moved once will be moved again. The stop was
placed at the invalidation; if the idea is invalid, the trade is over. If the user
believes the level has changed, the correct action is exit and re-enter with a
new plan, which forces them to re-justify the trade at the new price.

**Holding losers past the timeframe.** A 15m trade held for three days is not a
swing trade; it is a mistake with a story. Counter: the plan's timeframe defines
the trade's lifespan. If the target has not been hit within roughly 3-4x the
expected duration, exit at market regardless of P&L.

**Overtrading / boredom.** More trades feel like more opportunity. They are more
fees and more C setups. Counter: a cap of 3-5 trades per day and the A/B/skip
grading. A day with zero trades and a journal entry explaining why is a
successful day.

**Overconfidence after a streak.** Winning streaks produce oversized, undercooked
trades. Counter: same rules apply on green days. Consider stopping after +3R.

**Analysis paralysis.** Twelve indicators, four opinions, no trade taken, then a
chase. Counter: the four-question model in `indicators.md` and the top-down read.
One line per timeframe, one playbook, one card.

## 3. The daily routine

Roughly 20 minutes before the session the user trades, in this order:

1. **Calendar**: any tier-1 event today? When? Mark it and plan to be flat around it.
2. **HTF read**: 1D and 4H, one line each. Bias for the day.
3. **Levels**: PDH, PDL, daily open, weekly open, range edges, equal highs/lows,
   nearest liquidation clusters. Draw them once.
4. **Positioning**: funding, OI trend, anything extreme.
5. **Plan**: which playbooks are live today, at which levels, and the "if this then
   that" for each. Written down. A trade that is not in the morning plan needs an
   unusually good reason.
6. **State check**: sleep, mood, distractions, yesterday's P&L. If any is bad,
   reduce size or skip the day.

End of session (10 minutes): journal every trade with a screenshot, grade the
execution (not the outcome), note one thing to do better.

Weekly (30 minutes): run `scripts/journal_stats.py`, look at expectancy by
playbook and by session, cut the worst-performing setup, keep the rest.

## 4. The pre-trade checklist

Read before clicking. If any answer is "no", it is a skip.

- [ ] Is this one of the seven playbooks, and can I name which?
- [ ] Is it in the direction of the HTF bias, or at an HTF level if against it?
- [ ] Do I know exactly where the idea is wrong (the stop), and is it beyond noise?
- [ ] Is the size computed from the stop at the current risk %?
- [ ] Is there a realistic 2R target with no major level in the way?
- [ ] Have I checked funding, OI, session, and the calendar?
- [ ] Am I within daily and weekly loss limits, and under the trade count cap?
- [ ] Is this trade in my plan, or am I reacting to a candle?
- [ ] Am I calm? Would I take this trade at 0.5% risk? (If not, why at 1%?)

## 5. Stop-trading rules

Mechanical. Not subject to how the next setup looks.

- Daily loss reaches 3R.
- Three losing trades in a row (regardless of R).
- Weekly loss reaches 6R.
- Any trade taken outside the plan and outside the playbooks ("impulse trade"),
  win or lose: the session is over and the journal gets a full write-up.
- A stop was moved wider. Session over.
- A tier-1 event surprise (exchange outage, hack, flash crash): flat and away for
  at least 30 minutes.

## 6. What to say when the user is on tilt

Be direct, brief, and specific. Do not lecture.

Example: user writes "just got stopped out twice on BTC, it keeps wicking me, I'm
going to go 10x on this next long to make it back."

Respond roughly:

> Two stops today is −2R. The daily limit is 3R, so there is one trade left today,
> not a 10x trade. A 10x position with the same stop would risk about 10R and turn
> a normal day into a month of recovery. If BTC keeps wicking the level, the level
> is inside the noise and the stops were too tight, not unlucky: that is worth
> fixing on the chart, after a 30-minute break. If a setup is still there at 16:30
> UTC I will size it at 0.5% and we take it properly. What was the level you were
> stopped at?

Then actually help them find the stop-placement problem. The coaching response
includes the technical fix.

## 7. Beginner progression

If the user is new, do not hand them seven playbooks. Suggest:

1. **Weeks 1-2**: paper trade (or minimum size) playbook 1 only, on BTC only, one
   session only (New York). Journal everything. Goal: process, not profit.
2. **Weeks 3-6**: add playbook 2 or 4. Real money at 0.25-0.5% risk. Goal: 50
   journaled trades.
3. **After 50 trades**: run the stats. If expectancy is positive, move to 1% risk.
   If not, find the leak (usually stop placement or taking C setups) before adding
   anything.
4. **After 100 trades** with positive expectancy: add a second pair (ETH or SOL)
   and a second session. Never add both at once.

Rule of thumb: a new trader who survives six months without a drawdown over 15% has
done better than most. Speed kills.
