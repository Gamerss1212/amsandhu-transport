"""Replay: re-run a bot's strategy over recorded bars and compare with what it logged live.

Because live evaluation and replay use the same Frame, indicator engine, rule language and
TradeManager, a replay over the same bars must reproduce the same entry/no-entry decisions
bar by bar. Any mismatch is reported (it would point to data that changed after the decision,
e.g. a venue revising a bar, or to a code or config version change).
"""

from __future__ import annotations

import json
import os
import time
from typing import Optional

from mab.frame import Frame
from mab.models import Bar
from mab.strategy import TradeManager, compile_strategy, evaluate


def replay_bot(cfg: dict, bot_id: str, days: float = 2.0) -> dict:
    from mab.cli import _storage, load_bots, load_strategies
    from mab.costs import BacktestFiller, CostModel, tier_for
    st = _storage(cfg)
    bots = {b["bot_id"]: b for b in load_bots(cfg)}
    b = bots[bot_id]
    d = load_strategies(cfg)[b["strategy_id"]]
    start = int((time.time() - days * 86400) * 1000)
    rows = st.load_bars(b["venue"], b["instrument"], d["timeframe"])
    if not rows:
        return {"bot_id": bot_id, "error": "no stored bars for this series (bars are kept 14 days)"}
    asset = "stock" if b["venue"] == "yahoo" else "crypto"
    if b["instrument"].endswith(".TO"):
        asset = "stock_ca"
    bars = [Bar(r["venue"], r["instrument"], r["tf"], r["t"], r["o"], r["h"], r["l"], r["c"], r["v"], r["recv"], r["prov"])
            for r in rows]
    f = Frame(b["venue"], b["instrument"], d["timeframe"], asset, bars)
    params = {k: v for k, v in (b.get("params") or {}).items() if k in (d.get("params") or {})}
    c = compile_strategy(d, params, asset)
    rs = evaluate(c, f)
    tm = TradeManager(c, BacktestFiller(CostModel(b["venue"], tier_for(b["instrument"], asset))), lambda: 10_000.0)
    logged = {s["bar_time"]: s for s in st.query(
        "SELECT bar_time, action, reason FROM signals WHERE bot_id=? AND bar_time>=?", (bot_id, start))}
    compared = mismatches = 0
    details = []
    for i, t in enumerate(f.t):
        if t < start or t not in logged:
            continue
        side, why = tm.entry_check(rs, i)
        want_entry = logged[t]["action"] in ("enter_long", "enter_short")
        got_entry = side is not None
        compared += 1
        if want_entry != got_entry and "blocked" not in (logged[t]["reason"] or ""):
            mismatches += 1
            if len(details) < 20:
                details.append({"bar_time": t, "logged": logged[t], "replayed": why})
    return {"bot_id": bot_id, "strategy": c.id, "bars": f.n, "decisions_compared": compared,
            "entry_signal_mismatches": mismatches, "examples": details,
            "note": "compares whether the entry rule fired on each logged bar; position-dependent actions "
                    "(holds, exits) depend on fills and are not re-simulated here"}
