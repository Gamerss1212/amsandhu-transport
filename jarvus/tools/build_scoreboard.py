#!/usr/bin/env python3
"""Build Jarvus's strategy scoreboard from the Jarvus Terminal's measured results (run from the repository root).

    python3 jarvus/tools/build_scoreboard.py

Reads strategies/catalog.json, strategies/results/evaluation_summary.json(.gz) and swing_eval.json and writes:
  jarvus/assets/strategy_scoreboard.json          compact numbers that scripts/decide.py looks up
  jarvus/references/strategy-scoreboard.md         the 153 tested strategies: exact rules + every measured run
  jarvus/references/strategy-library-untested.md   the 259 catalogued ideas that could not be tested, and why
Not shipped inside the skill (a build tool).
"""

from __future__ import annotations

import gzip
import json
import os
from collections import defaultdict

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
STRAT = os.path.join(ROOT, "strategies")
OUT = os.path.join(ROOT, "jarvus")
R_CLIP = 3.0


def load(path):
    if not os.path.exists(path) and os.path.exists(path + ".gz"):
        with gzip.open(path + ".gz", "rt") as fh:
            return json.load(fh)
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def rr(x):
    return None if x is None else round(max(-R_CLIP * 3, min(R_CLIP * 3, x)), 3)


def fmt(x, n=None):
    if x is None:
        return "—"
    s = f"{x:+.2f}"
    return s if n is None else f"{s} ({n})"


def rules_text(d: dict) -> list:
    out = []
    ent = d.get("entry") or {}
    for side in ("long", "short"):
        if ent.get(side):
            out.append(f"entry {side}: `{ent[side]}`")
    if d.get("filters"):
        out.append("filters: " + " and ".join(f"`{f}`" for f in d["filters"]))
    o = d.get("order") or {}
    if o.get("type") and o["type"] != "market":
        out.append(f"order: {o['type']}" + "".join(f" {k} `{o[k]}`" for k in ("long", "short") if o.get(k))
                   + (f", expires after {o['ttl_bars']} bars" if o.get("ttl_bars") else ""))
    s = d.get("stop") or {}
    if s.get("type") == "atr":
        out.append(f"stop: {s.get('mult')}x ATR({s.get('n', 14)})")
    elif s.get("type") == "pct":
        out.append(f"stop: {s.get('pct')}%")
    elif s.get("type") == "level":
        out.append("stop: level " + ", ".join(f"{k} `{s[k]}`" for k in ("long", "short") if s.get(k))
                   + (f" + {s['buffer_atr']} ATR buffer" if s.get("buffer_atr") else ""))
    t = d.get("target") or {}
    if t.get("type") == "r":
        out.append(f"target: {t.get('r')}R")
    elif t.get("type") == "level":
        out.append("target: level " + ", ".join(f"{k} `{t[k]}`" for k in ("long", "short") if t.get(k)))
    tr = d.get("trail") or {}
    if tr.get("type") == "atr":
        out.append(f"trail: {tr.get('mult')}x ATR" + (f" after +{tr['activate_r']}R" if tr.get("activate_r") else ""))
    elif tr.get("type") == "level":
        out.append("trail: level " + ", ".join(f"{k} `{tr[k]}`" for k in ("long", "short") if tr.get(k)))
    ex = d.get("exit") or {}
    for side in ("long", "short"):
        if ex.get(side):
            out.append(f"exit {side}: `{ex[side]}`")
    if d.get("max_bars"):
        out.append(f"time stop: {d['max_bars']} bars")
    if d.get("max_trades_per_day"):
        out.append(f"max {d['max_trades_per_day']} trades/day")
    return out


def main():
    cat = load(os.path.join(STRAT, "catalog.json"))["strategies"]
    ev = load(os.path.join(STRAT, "results", "evaluation_summary.json"))
    sw = load(os.path.join(STRAT, "results", "swing_eval.json"))
    runs_by = defaultdict(list)
    for src in (ev, sw):
        for sid, s in src["strategies"].items():
            runs_by[sid].extend(s.get("runs", []))
    tested = [s for s in cat if s.get("definition") and runs_by.get(s["id"])]
    implemented_untested = [s for s in cat if s.get("definition") and not runs_by.get(s["id"])]
    blocked = [s for s in cat if not s.get("definition")]

    board = {"generated": ev.get("generated"), "swing_generated": sw.get("generated"),
             "about": "Jarvus Terminal batch evaluation: fixed parameters, chronological 60/20/20 split with a one-day "
                      "embargo, 4 walk-forward folds, Holm correction. R per trade, full period. crypto: retail = Kraken "
                      "entry tier 0.40%/0.80%, low = 0.08%/0.10% low-fee venue, gross = no costs; stocks: base = "
                      "commission-free + spread + regulatory fees, stress = 2x slippage. test = untouched last 20%, "
                      "looked at only for candidates (positive on train and validation, 30+ trades).",
             "hypothesis_tests": ev.get("hypothesis_tests"), "holm_significant": ev.get("holm_significant"),
             "strategies": {}}
    for s in tested:
        d = s["definition"]
        per = {}
        for r in runs_by[s["id"]]:
            inst = r["instrument"]
            e = per.setdefault(inst, {"venue": r.get("venue"), "tf": r.get("tf"),
                                      "asset": "stock" if r.get("venue") == "yahoo" else "crypto"})
            full = r.get("full") or {}
            key = {"retail_kraken": "retail", "low_fee_venue": "low", "base": "base", "stress_2x": "stress"}.get(r["cost"], r["cost"])
            e[key] = [rr(full.get("expectancy_r")), full.get("trades", 0)]
            g = r.get("gross_full") or {}
            if g.get("trades"):
                e["gross"] = [rr(g.get("expectancy_r")), g.get("trades", 0)]
            if key in ("retail", "base"):
                e["folds"] = f"{r.get('folds_positive')}/{r.get('folds')}"
                e["candidate"] = bool(r.get("candidate"))
                if r.get("candidate"):
                    te = r.get("test") or {}
                    e["test"] = [rr(te.get("expectancy_r")), te.get("trades", 0)]
                e["win_rate"] = round(full.get("win_rate") or 0, 3)
        board["strategies"][s["id"]] = {"name": s["name"], "family": s["family"], "tf": d.get("timeframe"),
                                        "direction": d.get("direction"), "markets": s.get("markets"), "runs": per}
    with open(os.path.join(OUT, "assets", "strategy_scoreboard.json"), "w", encoding="utf-8") as fh:
        json.dump(board, fh, separators=(",", ":"))

    # ------------------------------------------------------------------ the readable scoreboard
    fams = defaultdict(list)
    for s in tested:
        fams[s["family"]].append(s)
    L = ["# Strategy scoreboard: every strategy the Terminal could test, its exact rules, and what it measured",
         "",
         f"Source: the Jarvus Terminal's batch evaluation (generated {ev.get('generated')}; swing set {sw.get('generated')}). "
         f"{len(tested)} strategies with executable rules, {sum(len(v['runs']) for v in board['strategies'].values())} strategy-market pairs, "
         f"{ev.get('hypothesis_tests')} + {sw.get('hypothesis_tests')} hypothesis tests. **Significant after Holm correction: "
         f"{ev.get('holm_significant')} and {sw.get('holm_significant')}.** Read every positive number below as a lead to test, not an edge.",
         "",
         "**How it was measured** (`terminal-evidence.md` has the full protocol): parameters fixed before any data was seen; "
         "crypto = Coinbase 5-minute bars, about 120 days to late Sept 2026 (BTC, ETH, SOL; 1-minute BTC for 14 days; memecoins "
         "DOGE, SHIB, PEPE, BONK, FLOKI, WIF); stocks = Yahoo 5-minute bars, 60 days (SPY, QQQ, NVDA, AAPL, TSLA); swing set = "
         "Coinbase hourly, up to 5.5 years. Chronological 60/20/20 split with a one-day embargo, 4 walk-forward folds. Risk 0.5% "
         "per trade on fixed capital.",
         "",
         "**Columns** (R per trade over the full period, number of trades in brackets): `gross` = no costs at all · `low` = a "
         "low-fee crypto venue (0.08% maker / 0.10% taker) · `retail` = Kraken Pro entry tier (0.40% / 0.80%) · for stocks "
         "`net` = commission-free broker with spread and regulatory fees, `2x slip` = slippage doubled · `folds` = walk-forward "
         "folds with a positive net result · `test` = the untouched last 20%, shown only for candidates (positive on train AND "
         "validation with 30+ trades), because the protocol looks at it once and only for them.",
         "",
         "**NDAX (0.20% flat) and other fee levels:** net R is linear in the fee for the same trades, so estimate "
         "`R(fee) = low + (retail - low) x (taker - 0.10%) / 0.70%` (NDAX: low + 0.14 x (retail - low)). "
         "`scripts/decide.py --strategy <id or name>` does this for you. Coinbase Advanced's entry tier (1.20% taker) is worse "
         "than the retail column.",
         "",
         "**The rule language** (`rule-language.md`): `ema(close,21)`, `vwap()`, `atr(14)`, `rsi(close,2)`, `cross_above(a,b)`, "
         "`highest(high,20)[1]` (the previous bar's value), `session_high()`, `or_high(15)` (opening range), `pdh()` (prior "
         "day high) and so on, evaluated on completed bars only.",
         "",
         "## Contents", ""]
    for fam in sorted(fams):
        L.append(f"- [{fam.replace('_', ' ')}](#{fam.replace('_', '-')}) ({len(fams[fam])})")
    L += ["", "## The best runs at realistic costs (picked from every tested pair, so optimistic by construction)", "",
          "| Strategy | Market | Trades | Net R | Gross R | Folds + | Test R (trades) |", "|---|---|---|---|---|---|---|"]
    rank = []
    for sid, b in board["strategies"].items():
        for inst, e in b["runs"].items():
            k = "retail" if e["asset"] == "crypto" else "base"
            if e.get(k) and e[k][1] >= 30:
                rank.append((e[k][0], sid, b["name"], inst, e))
    rank.sort(key=lambda x: -(x[0] or -9))
    for r, sid, name, inst, e in rank[:30]:
        k = "retail" if e["asset"] == "crypto" else "base"
        L.append(f"| {sid} {name} | {inst} | {e[k][1]} | {fmt(e[k][0])} | {fmt((e.get('gross') or [None])[0])} | "
                 f"{e.get('folds', '—')} | {fmt(*(e['test'])) if e.get('test') else '—'} |")
    L += ["", "Crypto rows in that table are rare because at retail fees almost nothing on crypto is positive: "
          f"{sum(1 for v in board['strategies'].values() for e in v['runs'].values() if e['asset'] == 'crypto' and e.get('retail') and (e['retail'][0] or 0) > 0 and e['retail'][1] >= 20)} "
          "crypto pairs were positive at Kraken retail fees with 20+ trades. "
          f"At the low-fee level: {sum(1 for v in board['strategies'].values() for e in v['runs'].values() if e['asset'] == 'crypto' and e.get('low') and (e['low'][0] or 0) > 0 and e['low'][1] >= 20)}. "
          f"Gross (before any cost): {sum(1 for v in board['strategies'].values() for e in v['runs'].values() if e['asset'] == 'crypto' and e.get('gross') and (e['gross'][0] or 0) > 0 and e['gross'][1] >= 20)}. "
          "Fees, not ideas, decide crypto day trading.", ""]
    for fam in sorted(fams):
        L += [f"## {fam.replace('_', ' ')}", ""]
        for s in sorted(fams[fam], key=lambda x: x["id"]):
            d = s["definition"]
            b = board["strategies"][s["id"]]
            L.append(f"### {s['id']} {s['name']}")
            L.append(f"*{d.get('timeframe')} · {d.get('direction')} · {', '.join(s.get('markets') or [])}* — {s.get('mechanism', '').strip()}")
            L.append("")
            L.append("Rules: " + " · ".join(rules_text(d)))
            L.append("")
            crypto = {k: v for k, v in b["runs"].items() if v["asset"] == "crypto"}
            stock = {k: v for k, v in b["runs"].items() if v["asset"] == "stock"}
            if crypto:
                L += ["| Crypto | gross | low | retail | folds | test |", "|---|---|---|---|---|---|"]
                for inst, e in sorted(crypto.items()):
                    L.append(f"| {inst} | {fmt(*(e.get('gross') or [None, None]))} | {fmt(*(e.get('low') or [None, None]))} | "
                             f"{fmt(*(e.get('retail') or [None, None]))} | {e.get('folds', '—')} | {fmt(*e['test']) if e.get('test') else '—'} |")
                L.append("")
            if stock:
                L += ["| Stock | gross | net | 2x slip | folds | test |", "|---|---|---|---|---|---|"]
                for inst, e in sorted(stock.items()):
                    L.append(f"| {inst} | {fmt(*(e.get('gross') or [None, None]))} | {fmt(*(e.get('base') or [None, None]))} | "
                             f"{fmt(*(e.get('stress') or [None, None]))} | {e.get('folds', '—')} | {fmt(*e['test']) if e.get('test') else '—'} |")
                L.append("")
    if implemented_untested:
        L += ["## Implemented but not batch-tested", "",
              "Rules exist but they need data a backtest cannot get (live order flow), so they were only observed on paper.", ""]
        for s in implemented_untested:
            L.append(f"- **{s['id']} {s['name']}** ({s['family'].replace('_', ' ')}, {s['definition'].get('timeframe')}): "
                     + " · ".join(rules_text(s["definition"])))
        L.append("")
    with open(os.path.join(OUT, "references", "strategy-scoreboard.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(L) + "\n")

    # ------------------------------------------------------------------ the untested library
    U = ["# The untested library: ideas the Terminal catalogued but could not test",
         "",
         f"{len(blocked)} catalogued strategy ideas (from the strategy research and the 320-record knowledge pack, "
         "`handbook-day-trading.md` and `handbook-memecoins.md`) that have no measured result, each with the data it would "
         "need. **None of them is evidence of anything.** Use them as hypotheses: if Abhi wants one, make it mechanical, "
         "find the data, and backtest it (`Jarvus backtest`) before a cent goes near it.",
         "", "## Why they are untested", ""]
    why = defaultdict(int)
    for s in blocked:
        why[(s.get("blocked") or "not specified").split(";")[0].split(" (")[0]] += 1
    for k, n in sorted(why.items(), key=lambda x: -x[1])[:25]:
        U.append(f"- {n} × {k}")
    U += ["", "## By family", ""]
    fb = defaultdict(list)
    for s in blocked:
        fb[s["family"]].append(s)
    for fam in sorted(fb):
        U += [f"### {fam.replace('_', ' ')} ({len(fb[fam])})", ""]
        for s in sorted(fb[fam], key=lambda x: x["id"]):
            mech = (s.get("mechanism") or "").strip().rstrip(".")
            hyp = (s.get("hypothesis") or "").strip()
            ref = ""
            if s.get("pack_refs"):
                ref = " [" + ", ".join(p.get("pack_id", "") for p in s["pack_refs"] if p.get("pack_id")) + "]"
            U.append(f"- **{s['id']} {s['name']}**{ref}: {mech}. {hyp} *Needs: {s.get('blocked') or 'unspecified data'}.*")
        U.append("")
    with open(os.path.join(OUT, "references", "strategy-library-untested.md"), "w", encoding="utf-8") as fh:
        fh.write("\n".join(U) + "\n")
    print(f"tested {len(tested)}, implemented-untested {len(implemented_untested)}, blocked {len(blocked)}; "
          f"pairs {sum(len(v['runs']) for v in board['strategies'].values())}")


if __name__ == "__main__":
    main()
