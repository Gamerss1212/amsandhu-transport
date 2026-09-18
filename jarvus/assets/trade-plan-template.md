# Trade Plan Card

Fill every line. A blank line is a reason not to trade.

```
## {PAIR} · {timeframe} · {YYYY-MM-DD HH:MM} UTC · data: {source} ({live | pasted | stale})

HTF bias      : {1D trend and structure} · {4H trend, where price sits vs 21/200 EMA}
Regime        : {trend day | range day | volatile chop | compression} because {evidence}
Setup         : {playbook name and number}
Grade         : {A | B}  ->  risk {1% | 0.5%}
Verdict       : {LONG | SHORT | WAIT | NO TRADE}

Trigger       : {exact condition that must print before entry}
Entry         : {price or zone}  ({limit at level | market on confirmed trigger})
Stop          : {price}  ({invalidation level} +/- {buffer in ATR})  = {stop %}
Invalidation  : {the structural reason the idea is wrong if the stop is hit}
Targets       : T1 {price} ({level}, {R}, take {fraction}) · T2 {price} ({level}, {R})
Size          : {units} ({notional}, {leverage}x) from position_size.py
R:R           : {net R to T2 after fees}
Time stop     : {exit if not at T1 within N candles / by HH:MM UTC}

Context       : funding {x}% · OI {trend} · session {name} · {minutes} to {next event}
Confidence    : {low | medium | high}. Pro: {..}. Con: {..}.
What kills it : {level, event, or data change that flips the verdict}
```

## Scenario map (for Analyze mode, or alongside a WAIT verdict)

```
Bull case (~{p}%): {what needs to happen} -> {targets}
Bear case (~{p}%): {what needs to happen} -> {targets}
Chop (~{p}%): {range} until {time / event}
Deciding level: {above X | below Y}
What changes the odds: {evidence that would move the probabilities}
```
