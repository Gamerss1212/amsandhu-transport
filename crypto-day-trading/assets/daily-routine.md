# Daily Routine

Twenty minutes before the session. Ten minutes after. Thirty minutes once a week.
The routine is what makes the playbooks work; skipping it is how "I know all this"
turns into "I lost anyway".

## Pre-session (20 minutes)

1. **Calendar** (2 min): `python3 scripts/events.py` for tier-1 releases (CPI /
   NFP 08:30 New York, FOMC 14:00 New York, converted to UTC), plus options expiry,
   token unlocks for anything I trade, exchange maintenance. Write the times. Plan to be flat 30 min before and 15-30 min after.
2. **Data** (3 min):
   ```bash
   python3 scripts/scan.py --symbols BTC,ETH,SOL --derivs
   python3 scripts/fetch_ohlcv.py --symbol BTCUSDT --interval 1d --limit 200 --out /tmp/btc_1d.csv
   python3 scripts/fetch_ohlcv.py --symbol BTCUSDT --interval 4h --limit 300 --out /tmp/btc_4h.csv
   python3 scripts/fetch_ohlcv.py --symbol BTCUSDT --interval 15m --limit 500 --out /tmp/btc_15m.csv
   python3 scripts/snapshot.py /tmp/btc_1d.csv /tmp/btc_4h.csv /tmp/btc_15m.csv
   ```
3. **HTF read** (3 min): 1D and 4H, one line each: trend, EMA stack, last swing
   high/low, distance to the 21 and 200 EMA. Bias for the day.
4. **Levels** (3 min): PDH, PDL, daily open, weekly open, range edges, equal
   highs/lows, nearest liquidation clusters if available. Draw them once.
5. **Positioning** (2 min): funding, OI trend, long/short ratio, basis. Anything
   extreme? Which side is crowded?
6. **Regime guess** (1 min): trend / range / chop / compression, and which
   playbooks that makes live.
7. **Plan** (5 min): for each live playbook, the level, the trigger, the stop, the
   target, and the "if this then that". Written down. This is the list of trades
   allowed today. Anything else needs a written exception before entry.
8. **State check** (1 min): sleep, mood, distractions, yesterday's P&L. Any of them
   bad: half size or skip the day.

## During the session

- Trade only from the plan. Max 3-5 trades.
- Log each trade with `journal.py add` before sending the order; `journal.py close` after.
- After a full-R loss: 15 minutes away from the screen. After two: 30 minutes.
  After three, or −3R: done for the day.
- After +3R: consider stopping. Euphoria trades cost as much as tilt trades.
- Re-run the scan after the London open and after the US open; the regime can
  change at either.

## Post-session (10 minutes)

1. Close every journal row: exit, execution grade (process, not outcome),
   mistake tag, one sentence of notes, screenshot link.
2. Grade the day on process: did I follow the plan? How many exceptions?
3. One thing to do better tomorrow. One, not five.

## Weekly (30 minutes)

```bash
python3 scripts/journal.py stats
```

1. Rule breaks first: unplanned trades, moved stops, oversized trades, limit
   breaches. Until these are near zero, nothing else matters.
2. Expectancy overall and by playbook, session, pair, grade. Cut the worst
   playbook if it is negative over 20+ trades. Do more of the best.
3. Most common mistake tag: pick it as next week's single focus.
4. Re-read the three biggest losses. Most are rule breaks, not bad setups.
5. Adjust risk per the drawdown protocol: −5R from peak → 0.5%; −10R → stop and
   review; back to 1% only after a new equity high.
