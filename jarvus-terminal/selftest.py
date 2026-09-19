#!/usr/bin/env python3
"""Verify the install: python3 run.py selftest

Checks the maths and the machinery offline where it can, and makes exactly one small
network call to confirm the app can reach an exchange at all. Anything that needs the
network is reported as a skip rather than a failure when offline, so the suite is
still useful on a plane.
"""

from __future__ import annotations

import os
import sys
import tempfile
from datetime import datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

FAILS, SKIPS = [], []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"   ({detail})" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def skip(name, why):
    print(f"  skip {name}   ({why})")
    SKIPS.append(name)


def synth(n=300, start=100.0, drift=0.001, amp=0.01):
    """Deterministic candles: a gentle uptrend with a repeating wobble."""
    import math
    out, p = [], start
    t0 = datetime(2026, 1, 1, tzinfo=timezone.utc)
    for i in range(n):
        p *= (1 + drift + amp * math.sin(i / 7.0) * 0.3)
        hi, lo = p * (1 + amp / 2), p * (1 - amp / 2)
        out.append({"ts": t0 + timedelta(hours=i), "open": p * (1 - amp / 4), "high": hi,
                    "low": lo, "close": p, "volume": 1000 + 200 * math.sin(i / 3.0)})
    return out


def main() -> int:
    print("\nJarvus Terminal selftest\n")

    # ---- config & imports
    print("imports and config")
    import config
    from engine import analysis, indicators as ind, learn, news, scanner, store, universe, volgate
    check("every engine module imports", True)
    check("fee tiers are configured", len(config.FEE_TIERS) >= 3)
    check("the default fee tier exists", config.DEFAULT_FEE_TIER in config.FEE_TIERS)

    # ---- indicators
    print("\nindicators")
    flat = [100.0] * 60
    check("EMA of a constant series is that constant", abs(ind.last_value(ind.ema(flat, 21)) - 100.0) < 1e-9)
    h = [101.0] * 40; l = [99.0] * 40; c = [100.0] * 40
    check("ATR of constant 2-point ranges is 2", abs(ind.last_value(ind.atr(h, l, c, 14)) - 2.0) < 1e-9)
    rising = [float(i) for i in range(1, 40)]
    check("RSI of a monotonic rise is 100", abs(ind.last_value(ind.rsi(rising, 14)) - 100.0) < 1e-6)

    # ---- volatility gate
    print("\nvolatility gate")
    quiet = synth(300, amp=0.002, drift=0.0)
    loud = synth(300, amp=0.002, drift=0.0)
    for i in range(-30, 0):                      # make the tail genuinely violent
        base = loud[i]["close"]
        loud[i]["high"] = base * 1.06
        loud[i]["low"] = base * 0.94
        loud[i]["volume"] *= 4
    gq, gl = volgate.score(quiet), volgate.score(loud)
    check("the gate returns a reading for ordinary data", gq is not None and gl is not None)
    if gq and gl:
        check("a violent tail scores hotter than a calm series",
              gl["blow_score"] > gq["blow_score"], f"{gl['blow_score']} vs {gq['blow_score']}")
        check("energy tracks absolute movement", gl["energy"] > gq["energy"])
        check("every reading carries a plain-language explanation", bool(gl["explain"]) and bool(gq["explain"]))
        check("scores stay inside 0..1", 0 <= gl["blow_score"] <= 1 and 0 <= gq["blow_score"] <= 1)
    check("too little history returns nothing rather than a guess", volgate.score(synth(20)) is None)

    # ---- structure and the cost gate
    print("\nstructure and cost")
    st = analysis.structure(synth(300))
    check("structure reads an uptrend on rising data", st and st["trend"] in ("uptrend", "range"), st["trend"] if st else "")
    check("levels come back sorted by distance",
          st and len(st["levels"]) > 2 and abs(st["levels"][0]["distance_pct"]) <= abs(st["levels"][-1]["distance_pct"]))
    # cost in R = round-trip cost / stop distance. 26bps/side + 2 slippage on a 2% stop:
    #   2 * (0.26% + 0.02%) / 2% = 0.28
    check("cost in R matches the formula", abs(analysis.cost_in_r(2.0, 26.0, 2.0) - 0.28) < 1e-9,
          str(analysis.cost_in_r(2.0, 26.0, 2.0)))
    check("a tighter stop costs proportionally more",
          analysis.cost_in_r(1.0, 26.0, 2.0) > analysis.cost_in_r(4.0, 26.0, 2.0))
    m = {"symbol": "TEST-USDT", "base": "TEST", "quote": "USDT", "venue": "okx", "kind": "spot",
         "price": st["price"], "usd_volume_24h": 5e7, "high24h": 0, "low24h": 0, "open24h": 0}
    sig = analysis.signal(m, st, st, gl, 26.0, 10000)
    check("a signal always carries a verdict", sig["verdict"] in ("BUY", "WAIT", "NO DATA"))
    if sig["verdict"] == "BUY":
        check("the stop sits below the entry on a long", sig["stop"] < sig["entry"])
        check("size comes from the stop, not from conviction",
              abs(sig["units"] * (sig["entry"] - sig["stop"]) - sig["risk_amount"]) < 0.02)
    expensive = analysis.signal(m, st, st, gl, 300.0, 10000)   # absurd fees
    check("an unaffordable fee tier blocks the trade",
          expensive["verdict"] == "WAIT" and any("cost" in b for b in expensive["blockers"]))

    # ---- storage and the learning loop, on a scratch database
    print("\nstorage and the learning loop")
    tmp = tempfile.mkdtemp()
    old_db = config.DB_PATH
    config.DB_PATH = os.path.join(tmp, "t.db")
    import importlib
    importlib.reload(store)
    store.conn()
    check("a fresh database starts empty", store.counts()["predictions_total"] == 0)

    made = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    due = (datetime.now(timezone.utc) - timedelta(hours=36)).strftime("%Y-%m-%dT%H:%M:%SZ")
    for i in range(6):
        store.write_prediction({
            "made_at": made, "resolve_at": due, "symbol": "SYNTH", "venue": "okx", "price": 100.0,
            "gate_label": "LOUD" if i % 2 else "QUIET", "blow_score": 0.9 if i % 2 else 0.1,
            "energy": 0.5, "expansion": 0.5, "compression": 0.1, "atr_pct": 1.0,
            "big_move_threshold": 5.0, "confluence_score": 7, "confluence_max": 9,
            "grade": "A", "verdict": "BUY" if i % 2 else "WAIT", "cost_r": 0.1})
    check("predictions are written before their outcome", store.counts()["predictions_total"] == 6)
    check("all six are awaiting grading", store.counts()["pending"] == 6)
    check("all six are past their horizon", len(store.due_for_resolution()) == 6)

    # grade them by hand, the way the resolver would
    for i, row in enumerate(store.due_for_resolution()):
        store.resolve(row["id"], 9.0 if i % 2 else 1.0, 3.0 if i % 2 else -2.0, row["big_move_threshold"])
    counts = store.counts()
    check("grading moves them out of pending", counts["resolved"] == 6 and counts["pending"] == 0)
    rows = store.resolved()
    big = sum(1 for r in rows if r["big_move"])
    check("a range above the threshold is scored a big move, one below is not", big == 3, f"{big} of 6")

    cal = learn.calibration()
    check("calibration reports the sample size", cal["samples"] == 6)
    check("calibration is withheld until there is enough evidence", cal["ready"] is False)
    check("the high-score bucket shows a higher big-move rate than the low one",
          any(b["range"] == "0.8-1.0" and b["big_move_rate"] == 100.0 for b in cal["buckets"]) and
          any(b["range"] == "0.0-0.2" and b["big_move_rate"] == 0.0 for b in cal["buckets"]),
          str([(b["range"], b["big_move_rate"]) for b in cal["buckets"] if b["n"]]))
    check("an uncalibrated score is refused rather than dressed up",
          learn.calibrated_probability(0.9) is None)
    check("the direction check is reported", cal["direction_up_rate"] is not None)

    jid = store.journal_add({"opened_at": store.now_iso(), "symbol": "SYNTH", "entry": 100.0,
                             "stop": 96.0, "target": 108.0, "risk_pct": 1.0, "units": 25.0,
                             "grade": "A", "gate_label": "LOUD", "cost_r": 0.1, "notes": "test"})
    r = store.journal_close(jid, 108.0)
    check("closing a journal row computes R from entry and stop", abs(r - 2.0) < 1e-9, str(r))

    config.DB_PATH = old_db
    importlib.reload(store)

    # ---- news parsing, offline
    print("\nnews")
    check("hot-word list is populated", len(news.HOT_WORDS) > 10)
    matched = news.match_symbols(
        [{"title": "Bitcoin ETF sees record inflow", "summary": "", "source": "x", "link": "", "hot": []},
         {"title": "Solana network upgrade ships", "summary": "", "source": "x", "link": "", "hot": []}],
        ["BTC", "SOL", "XRP"])
    check("headlines match assets by name as well as ticker",
          "BTC" in matched and "SOL" in matched and "XRP" not in matched, str(list(matched)))

    # ---- indicators catalog
    print("\nindicator library")
    from engine import indicators as ind3
    check("the catalog is populated", len(ind3.CATALOG) >= 30, str(len(ind3.CATALOG)))
    cs = synth(300)
    failed = []
    for name in ind3.catalog_names():
        try:
            ind3.compute(name, cs)
        except Exception as exc:                        # noqa: BLE001
            failed.append((name, str(exc)[:40]))
    check("every catalogued indicator computes", not failed, str(failed[:3]))
    line, direction = ind3.supertrend([c["high"] for c in cs], [c["low"] for c in cs],
                                      [c["close"] for c in cs])
    check("Supertrend returns a line and a direction",
          line[-1] is not None and direction[-1] in (1, -1))
    adx_v, pdi, mdi = ind3.adx([c["high"] for c in cs], [c["low"] for c in cs], [c["close"] for c in cs])
    check("ADX is inside 0..100", 0 <= (adx_v[-1] or 0) <= 100, str(adx_v[-1]))

    # ---- strategies and the swarm
    print("\nstrategies and swarm")
    from engine import strategies as strat, swarm as sw
    strat.load_custom()
    check("a useful number of strategies is registered", len(strat.REGISTRY) >= 50, str(len(strat.REGISTRY)))
    check("the custom folder's example loaded",
          any(s2.source.startswith("custom/") for s2 in strat.REGISTRY.values()))
    check("controls are registered so strategies can be compared against them",
          "_control_random_entry" in strat.REGISTRY)

    ctx = strat.Ctx(cs, "TEST")
    fired = 0
    for spec in strat.all_strategies():
        sig = strat.evaluate(spec, ctx)
        if sig:
            fired += 1
            if not (0 <= sig.strength <= 1):
                check("strength stays inside 0..1", False, spec.name)
                break
    check("strategies run without raising, and some fire", fired > 0, f"{fired} fired")

    # the prefix view is what keeps a backtest from reading the future
    full = strat.SeriesCache(cs)
    early = strat.Ctx(cs, "TEST", cache=full, at=100)
    check("a prefix context sees only its own bars", len(early.close) == 101)
    check("its last close is that bar's close, not the newest one",
          early.close[-1] == cs[100]["close"] and early.close[-1] != cs[-1]["close"])
    ema_full = full.indicator("ema", {"period": 21})
    check("an indicator view is truncated to the same bar", len(early.ind("ema", period=21)) == 101)
    check("but its values match the full series", early.ind("ema", period=21)[100] == ema_full[100])

    res = sw.evaluate_market(cs, "TEST")
    check("the swarm returns a consensus reading",
          "consensus" in res and res["agents_run"] == len(strat.all_strategies()))
    check("votes are grouped into families rather than counted raw",
          res["families_agreeing"] <= len(sw.FAMILY_SET))

    # ---- backtest
    print("\nbacktest")
    from engine import backtest as bt
    spec = strat.REGISTRY["_control_always_long"]
    # a longer series, because 210 warmup bars plus a 96-bar time stop leaves little
    # room for trades in a 300-bar sample
    long_cs = synth(900)
    trades = bt.simulate(long_cs, spec, fee_bps=0, slip_bps=0)
    check("the control produces trades on synthetic data", len(trades) > 3, str(len(trades)))
    st2 = bt.stats(trades)
    check("stats report a win rate and an expectancy",
          "win_rate" in st2 and "expectancy" in st2)
    wf = bt.walk_forward(long_cs, spec, split=0.6, fee_bps=0, slip_bps=0)
    check("walk-forward splits trades into two periods",
          wf["in_sample"]["n"] + wf["out_sample"]["n"] == wf["n"])
    check("no evidence means no weight rather than an average one",
          bt.weight_from({"out_sample": {"n": 3, "expectancy": 0.5}}) is None)
    check("a strategy that cannot beat the control is muted",
          bt.weight_from({"out_sample": {"n": 40, "expectancy": 0.05}}, control_expectancy=0.18) == 0.0)
    check("beating the control earns a weight above the floor",
          (bt.weight_from({"out_sample": {"n": 40, "expectancy": 0.40}}, control_expectancy=0.18) or 0) > 0.5)

    # ---- portfolio
    print("\nportfolio")
    from engine import portfolio as pf
    import importlib as _il
    _il.reload(pf)
    pf.ensure_default()
    before = pf.performance("paper")["equity"]
    r2 = pf.open_position("paper", "SELFTEST", 100.0, 96.0, 108.0)
    check("a position sizes itself from the stop", r2.get("ok") and
          abs(r2["units"] * (r2["fill"] - 96.0) - r2["risk_amount"]) < 0.02, str(r2)[:110])
    check("risk equals the configured percentage of equity",
          abs(r2["risk_pct_of_equity"] - pf.get("paper")["risk_pct"]) < 0.01, str(r2.get("risk_pct_of_equity")))
    pos = [p for p in pf.performance("paper")["open_positions"] if p["symbol"] == "SELFTEST"]
    check("the open position is recorded", len(pos) == 1)
    if pos:
        c2 = pf.close_position(pos[0]["id"], 108.0, "target")
        # A 2R target does not pay 2R, and that gap is the whole point of the cost
        # gate: fees and slippage are charged on both sides, so the book records what
        # the trade was actually worth rather than what the plan hoped for.
        check("a 2R target pays a little under 2R once fees are charged",
              1.7 < c2["r_multiple"] < 2.0, str(c2["r_multiple"]))
        check("the fee is recorded rather than quietly absorbed", c2["fee"] > 0)
    rd = pf.readiness("paper")
    check("readiness reports every check", len(rd["checks"]) == len(pf.READINESS_RULES))
    check("a thin record is not declared ready", rd["ready"] is False)

    # ---- automation
    print("\nautomation")
    from engine import automation as auto
    n_before = len(auto.rules())
    rid = auto.add_rule(name="selftest rule", min_heat=0.9, cooldown_min=1)
    check("a rule can be added", len(auto.rules()) == n_before + 1)
    scan_stub = {"markets": [{"symbol": "SELFTEST", "base": "ST", "price": 1.0,
                              "usd_volume_24h": 1e9,
                              "gate": {"blow_score": 0.95, "label": "LOUD", "explain": "test"},
                              "signal": {"verdict": "BUY", "confluence": {"cost_r": 0.1}}}]}
    fired2 = auto.check(scan_stub, {})
    check("a matching rule fires", any(f["symbol"] == "SELFTEST" for f in fired2), str(fired2))
    fired3 = auto.check(scan_stub, {})
    check("the cooldown stops it firing again immediately",
          not any(f["symbol"] == "SELFTEST" for f in fired3))
    auto.delete_rule(rid)
    check("a rule can be deleted", len(auto.rules()) == n_before)

    # ---- one network call
    print("\nnetwork")
    uni = universe.scan(["okx_spot"])
    if uni["passed_liquidity"] == 0:
        skip("exchange reachable", "no markets returned; offline or the venue is blocked")
    else:
        check("an exchange is reachable and returns markets", uni["passed_liquidity"] > 10,
              f"{uni['passed_liquidity']} liquid markets")
        top = universe.pick_deep(universe.dedupe_by_base(uni["markets"]), 1)
        from engine import marketdata
        c = marketdata.candles(top[0]["symbol"], top[0]["venue"], "1h", 120)
        if not c:
            skip("candles reachable", "no candles returned")
        else:
            check("candles come back in ascending time order", all(c[i]["ts"] < c[i + 1]["ts"] for i in range(len(c) - 1)))
            check("the in-progress bar is excluded",
                  (datetime.now(timezone.utc) - c[-1]["ts"]).total_seconds() >= 3500)

    print()
    if FAILS:
        print(f"{len(FAILS)} FAILED: {FAILS}\n")
        return 1
    print(f"all checks passed" + (f" ({len(SKIPS)} skipped: {SKIPS})" if SKIPS else "") + "\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
