"""Build the strategy library deliverables from the authored sources.

    python strategies/src/build.py

Steps: load every family module; assign ids (counted strategies STRAT-###, variants STRAT-V###);
compile each executable definition with the bot platform's engine for each market it targets;
run the automated duplicate review; merge evaluation results if present; write catalog.json,
per-strategy definition files, the source register, markdown docs and the Excel workbook.
"""

import itertools
import json
import os
import re
import sys
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.path.insert(0, os.path.join(os.path.dirname(ROOT), "market_analysis_bots"))

import lib  # noqa: E402
import sources  # noqa: E402
for m in ("f01_trend", "f02_open_gap_levels", "f03_vwap_profile_momentum", "f04_patterns_volume_time",
          "f05_crossasset_crypto_flow_stat", "f06_pack_formalized"):
    __import__(m)
import pack  # noqa: E402  (knowledge pack: validation, dispositions, sources)
pack.register_research_records()
import f07_swing  # noqa: E402,F401  (after the pack records, so every earlier id stays the same)

from mab import expr  # noqa: E402
from mab.strategy import DefinitionError, compile_strategy  # noqa: E402

TODAY = date.today().isoformat()
FAMILY_NAMES = {
    "trend_following": "Trend following", "opening_range": "Opening range & initial balance", "gaps": "Gaps & overnight",
    "reference_levels": "Session levels & reference prices", "vwap": "VWAP & anchored VWAP", "market_profile": "Market / volume profile",
    "momentum": "Momentum & thrust", "mean_reversion": "Mean reversion", "volatility": "Volatility contraction & expansion",
    "candlestick": "Candlestick patterns", "market_structure": "Market structure & chart patterns", "volume": "Volume & money flow",
    "time_of_day": "Time-of-day & calendar", "scheduled_events": "Scheduled events", "cross_asset": "Cross-asset & relative value",
    "crypto_structure": "Crypto derivatives & venue structure", "order_flow": "Order flow & microstructure",
    "statistical": "Statistical & regime", "machine_learning": "Machine learning", "market_making_arbitrage": "Market making & arbitrage",
    "named_systems": "Named multi-screen systems", "memecoin": "Memecoins (knowledge pack)",
    "equity_events": "Equity corporate events (knowledge pack)", "equity_breadth": "Equity breadth & auctions (knowledge pack)",
    "swing": "Swing (hourly, cost-aware; swing lab)"}


def signature(node) -> str:
    """Rule structure with every numeric constant replaced, for duplicate detection."""
    return re.sub(r"(?<![A-Za-z_])-?\d+(\.\d+)?", "#", node.key())


def build():
    counted = [r for r in lib.CATALOG if not r.get("is_variant")]
    variants = [r for r in lib.CATALOG if r.get("is_variant")]
    keys = [r["key"] for r in lib.CATALOG]
    dup_keys = {k for k in keys if keys.count(k) > 1}
    if dup_keys:
        raise SystemExit(f"duplicate keys: {dup_keys}")
    ids = {}
    for i, r in enumerate(counted, 1):
        ids[r["key"]] = f"STRAT-{i:03d}"
    for i, r in enumerate(variants, 1):
        ids[r["key"]] = f"STRAT-V{i:03d}"
    errors, sigs = [], {}
    for r in counted:
        r["id"] = ids[r["key"]]
        for e in r["evidence"]:
            if e["source"] not in sources.S:
                errors.append(f"{r['id']} cites unknown source {e['source']}")
        d = r["definition"]
        if r.get("blocked"):
            r["implementation_status"], r["blocked_reason"] = "blocked", r["blocked"]
        elif d is None:
            r["implementation_status"] = "specified"
        else:
            d["id"] = r["id"]
            d["version"] = "1.0.0"
            ok = True
            for m in r["markets"]:
                try:
                    c = compile_strategy(d, asset_type="stock" if m == "stock" else "crypto")
                    r.setdefault("warmup_bars", {})[m] = max(c.warmup.values())
                    r["references"] = {k: sorted(v) for k, v in c.references.items()}
                    sig = "|".join(sorted(f"{k}:{signature(n)}" for k, n in c.rules.items() if k.startswith(("entry", "filter"))))
                    sig += f"|stop:{d['stop'].get('type')}|order:{d['order'].get('type')}"
                    sigs[r["id"]] = sig
                except (DefinitionError, expr.ExprError, KeyError, ValueError) as e:
                    ok = False
                    errors.append(f"{r['id']} {r['key']} ({m}): {e}")
            r["implementation_status"] = "implemented" if ok else "specified"
        r["evaluation_status"] = "untested"
        r["live_evidence"] = "none"
        r["variants"] = [ids[v["key"]] for v in variants if v["parent"] == r["key"]]
    # knowledge-pack provenance: which pack records each entry covers
    bykey = {r["key"]: r for r in counted}
    for pid in pack.RECORDS:
        kind, what = pack.disposition(pid)
        if kind in ("same", "new"):
            if what not in bykey:
                errors.append(f"pack {pid} maps to unknown key {what}")
                continue
            bykey[what].setdefault("pack_refs", []).append({"pack_id": pid, "relation": kind, "name": pack.RECORDS[pid]["name"],
                                                            "note": pack.SAME.get(pid, ("", ""))[1] if kind == "same" else "formalized here"})
        elif kind == "research":
            key = next((r["key"] for r in counted if r["key"].startswith("pack_" + pid.lower() + "_")), None)
            if key:
                bykey[key].setdefault("pack_refs", []).append({"pack_id": pid, "relation": "research", "name": pack.RECORDS[pid]["name"], "note": what})
    for v in variants:
        v["id"] = ids[v["key"]]
        if v["parent"] not in ids:
            errors.append(f"variant {v['key']} has unknown parent {v['parent']}")
        v["parent_id"] = ids.get(v["parent"])
        v["counted"] = False
    # ---------------------------------------------------------------- duplicate review
    exact = [(a, b) for (a, sa), (b, sb) in itertools.combinations(sigs.items(), 2) if sa == sb]
    byid = {r["id"]: r for r in counted}
    near = []
    for a, b in itertools.combinations([r for r in counted if r.get("references")], 2):
        if a["family"] != b["family"]:
            continue
        sa = set(a["references"]["indicators"]) | set(a["references"]["functions"])
        sb = set(b["references"]["indicators"]) | set(b["references"]["functions"])
        if sa and sb and len(sa & sb) / len(sa | sb) >= 0.75:
            near.append((a["id"], b["id"], round(len(sa & sb) / len(sa | sb), 2)))
    # ---------------------------------------------------------------- evaluation merge
    ev_path = os.path.join(ROOT, "results", "evaluation_summary.json")
    evals = {}
    if os.path.exists(ev_path):
        with open(ev_path) as fh:
            evals = json.load(fh).get("strategies", {})
    elif os.path.exists(ev_path + ".gz"):
        import gzip
        with gzip.open(ev_path + ".gz", "rt") as fh:
            evals = json.load(fh).get("strategies", {})
    sw_path = os.path.join(ROOT, "results", "swing_eval.json")          # the swing strategies' own evaluation
    if os.path.exists(sw_path):
        with open(sw_path) as fh:
            evals.update(json.load(fh).get("strategies", {}))
    keep = ("trades", "win_rate", "expectancy_r", "profit_factor", "net_return", "sharpe", "max_drawdown")
    for r in counted:
        e = evals.get(r["id"])
        if e:
            r["evaluation"] = {"status": e.get("status"), "best_realistic": e.get("best_realistic"),
                               "candidates": e.get("candidates"),
                               "results": [dict(x, metrics={k: x["metrics"].get(k) for k in keep}) for x in e.get("results", [])]}
            r["evaluation_status"] = e.get("status", "backtested")
    return counted, variants, errors, exact, near, byid


def write(counted, variants, errors, exact, near):
    os.makedirs(os.path.join(ROOT, "definitions"), exist_ok=True)
    counts = {
        "counted_strategies": len(counted), "variants_not_counted": len(variants),
        "implemented": sum(1 for r in counted if r["implementation_status"] == "implemented"),
        "blocked": sum(1 for r in counted if r["implementation_status"] == "blocked"),
        "specified_only": sum(1 for r in counted if r["implementation_status"] == "specified"),
        "research_status": {s: sum(1 for r in counted if r["research_status"] == s) for s in ("sourced", "incompletely sourced", "hypothesis")},
        "evaluation_status": {s: sum(1 for r in counted if r["evaluation_status"] == s)
                              for s in ("untested", "backtested", "out-of-sample tested", "paper observed")},
        "families": {f: sum(1 for r in counted if r["family"] == f) for f in FAMILY_NAMES},
        "target": 300, "sources": len(sources.S)}
    cat = {"generated": TODAY, "counts": counts, "status_definitions": {
        "research": ["sourced", "incompletely sourced", "hypothesis"],
        "implementation": ["specified", "implemented", "blocked"],
        "evaluation": ["untested", "backtested", "out-of-sample tested", "paper observed"],
        "live_evidence": ["none", "externally reported", "independently verified"]},
        "strategies": counted, "variants": variants}
    with open(os.path.join(ROOT, "catalog.json"), "w") as fh:
        json.dump(cat, fh, indent=1, default=str)
    for r in counted:
        with open(os.path.join(ROOT, "definitions", f"{r['id']}.json"), "w") as fh:
            json.dump({k: r.get(k) for k in ("id", "key", "name", "family", "subfamily", "hypothesis", "markets", "timeframe",
                                              "data", "definition", "spec", "implementation_status", "blocked_reason",
                                              "research_status", "evidence", "variants")}, fh, indent=1)
    with open(os.path.join(ROOT, "sources.json"), "w") as fh:
        json.dump(list(sources.S.values()), fh, indent=1)
    write_docs(counted, variants, counts, errors, exact, near)
    write_pack_report(counted)
    write_xlsx(counted, variants)
    return counts


def write_pack_report(counted):
    probs = pack.validate()
    summ = pack.summary()
    byk = {r["key"]: r for r in counted}
    L = ["# Knowledge pack import\n",
         f"Pack version {pack.CAT['schema_version']} ({pack.CAT['as_of_utc']}): {len(pack.RECORDS)} records, "
         f"{sum(1 for r in pack.RECORDS.values() if r['counts_as_trading_hypothesis'])} trading hypotheses. "
         "The pack supplies research templates with no performance data; nothing here copies a performance number from it.\n",
         "## Validation\n", "Manifest hashes (derived views `Strategy_Catalogue.md` and `knowledge_base.jsonl` are not stored), unique ids, "
         "every required field and allowed value from the pack's schema, family/parent/source references, null performance and the "
         "published counts:\n", ("**All checks passed.**" if not probs else "\n".join(f"- {p}" for p in probs)) + "\n",
         "## Dispositions\n", "| Disposition | Records | Meaning |", "|---|---|---|",
         f"| same | {len(summ['same'])} | the library already had this strategy; the pack adds provenance to it |",
         f"| new (formalized) | {len(summ['new'])} | written here as executable rules with parameters frozen before testing (PREREGISTRATION_PACK.md) |",
         f"| research (blocked) | {len(summ['research'])} | distinct hypotheses kept in the catalog, blocked on the named missing data |",
         f"| supporting | {len(summ['supporting'])} | model frameworks, execution methods, risk filters; not trading hypotheses |\n"]
    for kind in ("new", "same", "research", "supporting"):
        L.append(f"\n## {kind}\n")
        for pid, what in summ[kind]:
            r = pack.RECORDS[pid]
            tgt = byk.get(what) if kind in ("same", "new") else next((x for x in counted if x["key"].startswith("pack_" + pid.lower() + "_")), None)
            L.append(f"- {pid} {r['name']} -> " + (f"{tgt['id']} {tgt['name']}" if tgt else "") + (f" ({what})" if kind in ("research", "supporting") else ""))
    with open(os.path.join(ROOT, "PACK_IMPORT.md"), "w") as fh:
        fh.write("\n".join(L) + "\n")


def rules_text(r):
    d = r.get("definition")
    if not d:
        return r.get("spec") or ""
    parts = [f"{side} entry: {txt}" for side, txt in d["entry"].items()]
    if d["filters"]:
        parts.append("filters: " + " AND ".join(d["filters"]))
    if d["order"]["type"] != "market":
        parts.append(f"order: {d['order']['type']} " + ", ".join(f"{k}={v}" for k, v in d["order"].items() if k != "type"))
    st = d["stop"]
    parts.append("stop: " + ", ".join(f"{k}={v}" for k, v in st.items()))
    if d["target"]["type"] != "none":
        parts.append("target: " + ", ".join(f"{k}={v}" for k, v in d["target"].items()))
    if d["trail"]["type"] != "none":
        parts.append("trail: " + ", ".join(f"{k}={v}" for k, v in d["trail"].items()))
    for side, txt in (d.get("exit") or {}).items():
        parts.append(f"{side} exit: {txt}")
    if d.get("max_bars"):
        parts.append(f"time stop: {d['max_bars']} bars")
    parts.append(f"max trades/day: {d['max_trades_per_day']}; flat before the session end; risk {d['sizing']['risk_pct']}% per trade")
    return "\n".join(parts)


def write_docs(counted, variants, counts, errors, exact, near):
    L = [f"# Strategy library\n\nGenerated {TODAY}. {counts['counted_strategies']} distinct strategies after duplicate review "
         f"(target was {counts['target']}), {counts['variants_not_counted']} documented variants that are "
         f"not counted, {counts['sources']} sources. {counts['blocked']} of the distinct strategies are blocked: they are real, distinct "
         "hypotheses (most from the research knowledge pack, see PACK_IMPORT.md) that need data this software does not have.\n",
         "| Status | Count |\n|---|---|",
         f"| Implemented (runs on the bot platform) | {counts['implemented']} |",
         f"| Blocked (needs data or engine features that are missing) | {counts['blocked']} |",
         f"| Specified only | {counts['specified_only']} |"]
    for k, v in counts["research_status"].items():
        L.append(f"| Research: {k} | {v} |")
    for k, v in counts["evaluation_status"].items():
        L.append(f"| Evaluation: {k} | {v} |")
    L.append("\nNo strategy here is labelled proven. Statuses are separate on purpose: a strategy can be sourced yet untested, or "
             "backtested yet a hypothesis.\n\n## How strategies are counted\n\nThe distinctness rule (DUPLICATE_REVIEW.md) counts a strategy only if it "
             "differs in market hypothesis, signal construction, reference level, direction logic or required data. Changing a period, threshold, "
             "ticker, timeframe, or swapping one indicator for another in the same template makes a *variant*, listed under its parent and not "
             "counted. Applying that rule honestly produced the count above; BACKLOG.md lists the variants and the ideas rejected or not yet specified. "
             "Knowledge-pack records that describe a strategy already here were mapped to it, not counted again (PACK_IMPORT.md).\n")
    L.append("## Files\n\n- `catalog.json` - every field of every strategy (machine-readable), plus variants\n"
             "- `definitions/STRAT-###.json` - one executable definition per strategy (the bot platform loads these)\n"
             "- `day_trading_strategies.xlsx` - index, full catalog, source register, evaluation results, implementation status\n"
             "- `sources.json`, `SOURCE_REGISTER.md` - verified sources with links and access dates\n"
             "- `TAXONOMY.md`, `DUPLICATE_REVIEW.md`, `BACKLOG.md`, `VALIDATION_METHODOLOGY.md`, `RANKING_METHODOLOGY.md`\n"
             "- `src/` - the authoring sources and this build script (`python strategies/src/build.py`)\n")
    if errors:
        L.append("## Build problems\n\n" + "\n".join(f"- {e}" for e in errors))
    with open(os.path.join(ROOT, "README.md"), "w") as fh:
        fh.write("\n".join(L) + "\n")
    T = ["# Taxonomy\n\nFamily -> subfamily -> strategies. Each strategy also records its *mechanism* (the market behaviour it relies on), "
         "*logic* (continuation, reversal, breakout...) and *anchor* (the reference it compares price with).\n"]
    for fam, title in FAMILY_NAMES.items():
        rs = [r for r in counted if r["family"] == fam]
        if not rs:
            continue
        T.append(f"\n## {title} ({len(rs)})\n")
        for sub in sorted({r["subfamily"] for r in rs}):
            T.append(f"- **{sub}**: " + "; ".join(f"{r['id']} {r['name']}" for r in rs if r["subfamily"] == sub))
    with open(os.path.join(ROOT, "TAXONOMY.md"), "w") as fh:
        fh.write("\n".join(T) + "\n")
    D = ["# Duplicate review\n\n## Rule\n\nTwo candidates are the same strategy (one becomes a variant) when they differ only in:\n"
         "- parameter values (periods, thresholds, multipliers), ticker, market or timeframe;\n"
         "- the choice among interchangeable indicators in the same template (e.g. RSI vs Stochastic vs Williams %R for an oversold reversal);\n"
         "- exit or order-type details while the entry logic is unchanged;\n- the name.\n\n"
         "They are distinct when they differ in the market hypothesis, the signal construction, the reference level or anchor, the direction "
         "logic (continuation vs reversal), or a required data type (e.g. order flow, cross-asset series, event calendars).\n\n"
         "## Automated checks\n\n1. **Exact structure**: every executable rule is parsed, numeric constants are replaced by `#`, and the entry/filter "
         "structures plus stop and order types are compared. Identical structures are flagged.\n"
         "2. **Near duplicates**: within a family, pairs whose indicator/function sets overlap by Jaccard >= 0.75 are flagged for manual review.\n"]
    D.append(f"\n## Results\n\nExact-structure matches: {len(exact)}\n")
    byid = {r["id"]: r for r in counted}
    for a, b in exact:
        D.append(f"- {a} {byid[a]['name']} == {b} {byid[b]['name']}: REVIEW REQUIRED")
    D.append(f"\nNear-duplicate pairs flagged for manual review: {len(near)}\n")
    for a, b, j in near:
        ra, rb = byid[a], byid[b]
        why = ra.get("distinct") or rb.get("distinct") or (
            f"kept separate: anchor '{ra['anchor']}' vs '{rb['anchor']}', logic '{ra['logic']}' vs '{rb['logic']}'")
        D.append(f"- {a} {ra['name']} / {b} {rb['name']} (overlap {j}): {why}")
    D.append(f"\n## Variants recorded (not counted): {len(variants)}\n")
    for v in variants:
        D.append(f"- {v['id']} {v['name']} -> parent {v['parent_id']}: {v['what_changes']}")
    with open(os.path.join(ROOT, "DUPLICATE_REVIEW.md"), "w") as fh:
        fh.write("\n".join(D) + "\n")
    S = ["# Source register\n\nEvery source was looked up on the access date shown; the link is the one returned. `Supports` is the only claim "
         "the catalog attributes to it. Books were verified to exist (publisher or library listing) but were not read in full.\n",
         "| ID | Source | Type | Supports | Link | Accessed | Verification |", "|---|---|---|---|---|---|---|"]
    for s in sources.S.values():
        S.append(f"| {s['id']} | {s['authors']} ({s['year']}). *{s['title']}*. {s['venue']} | {s['type']} | {s['supports']} | "
                 f"{s['url']} | {s['accessed']} | {s['verification']}{'; ' + s['notes'] if s['notes'] else ''} |")
    with open(os.path.join(ROOT, "SOURCE_REGISTER.md"), "w") as fh:
        fh.write("\n".join(S) + "\n")
    B = ["# Backlog\n\n## Variants (documented, not counted)\n"]
    B += [f"- {v['id']} {v['name']} (of {v['parent_id']}): {v['what_changes']}" for v in variants]
    B.append("\n## Blocked strategies (counted, cannot run yet)\n")
    B += [f"- {r['id']} {r['name']}: {r['blocked_reason']}" for r in counted if r["implementation_status"] == "blocked"]
    B.append("\n## Ideas not admitted to the catalog\n\n- Elliott wave counting, Gann angles: no objective, testable definition.\n"
             "- Zig-zag based rules: the indicator repaints (uses future bars).\n"
             "- News/social-sentiment, insider, analyst-revision, on-chain flow, token-unlock strategies: no free machine-readable "
             "real-time data and no source verified in this session; candidates for a later sourced review.\n"
             "- Overnight holds, dividend capture, multi-day swing systems: out of scope (day trading only).\n"
             "- Cross-sectional scanners (top gainers, 52-week-high proximity, in-play ranking over hundreds of symbols): need a universe "
             "scanner; the free Yahoo endpoint would be rate-limited. Specified as future work.\n")
    with open(os.path.join(ROOT, "BACKLOG.md"), "w") as fh:
        fh.write("\n".join(B) + "\n")


def write_xlsx(counted, variants):
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Alignment, Font, PatternFill
        from openpyxl.utils import get_column_letter
    except ImportError:
        print("openpyxl not installed: workbook skipped (pip install openpyxl==3.1.5)")
        return
    wb = Workbook()
    head = Font(bold=True, color="FFFFFF")
    fill = PatternFill("solid", fgColor="2F5597")

    def sheet(ws, header, rows, widths):
        ws.append(header)
        for c in ws[1]:
            c.font, c.fill = head, fill
        for row in rows:
            ws.append(["" if v is None else v for v in row])
        for i, w in enumerate(widths, 1):
            ws.column_dimensions[get_column_letter(i)].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")
        ws.freeze_panes = "A2"
        ws.auto_filter.ref = ws.dimensions

    ws = wb.active
    ws.title = "Index"
    sheet(ws, ["ID", "Name", "Family", "Markets", "Timeframe", "Research", "Implementation", "Evaluation", "Live evidence"],
          [[r["id"], r["name"], FAMILY_NAMES.get(r["family"], r["family"]), ", ".join(r["markets"]), r["timeframe"],
            r["research_status"], r["implementation_status"], r["evaluation_status"], r["live_evidence"]] for r in counted],
          [11, 48, 28, 14, 10, 18, 15, 20, 14])
    ws = wb.create_sheet("Full Catalog")
    sheet(ws, ["ID", "Key", "Name", "Family", "Subfamily", "Mechanism", "Logic", "Anchor", "Hypothesis", "Markets", "Suggested instruments",
               "Timeframe", "Data required", "Exact rules", "Failure modes", "Evidence", "Research status", "Implementation status",
               "Blocked reason", "Evaluation status", "Live evidence", "Variants", "Notes"],
          [[r["id"], r["key"], r["name"], r["family"], r["subfamily"], r["mechanism"], r["logic"], r["anchor"], r["hypothesis"],
            ", ".join(r["markets"]), ", ".join(r.get("instruments") or []), r["timeframe"], ", ".join(r["data"]), rules_text(r),
            "; ".join(r["failure_modes"]), "; ".join(f"{e['source']} ({e['relation']}) {e['note']}" for e in r["evidence"]),
            r["research_status"], r["implementation_status"], r.get("blocked_reason"), r["evaluation_status"], r["live_evidence"],
            ", ".join(r["variants"]), r["notes"]] for r in counted],
          [11, 22, 36, 18, 18, 36, 16, 22, 50, 12, 16, 9, 18, 70, 30, 50, 16, 14, 30, 16, 12, 18, 40])
    ws = wb.create_sheet("Source Register")
    sheet(ws, ["ID", "Authors", "Year", "Title", "Venue", "Type", "Supports", "Link", "Accessed", "Verification", "Notes"],
          [[s["id"], s["authors"], s["year"], s["title"], s["venue"], s["type"], s["supports"], s["url"], s["accessed"],
            s["verification"], s["notes"]] for s in sources.S.values()],
          [9, 28, 6, 50, 30, 14, 60, 50, 11, 24, 30])
    ws = wb.create_sheet("Evaluation Results")
    rows = []
    for r in counted:
        e = r.get("evaluation")
        if not e:
            rows.append([r["id"], r["name"], r["evaluation_status"]] + [None] * 12 + ["not evaluated in this run"])
            continue
        for res in e.get("results", []):
            m = res.get("metrics", {})
            rows.append([r["id"], r["name"], res.get("period"), res.get("instrument"), res.get("tf"), res.get("dataset"),
                         m.get("trades"), m.get("win_rate"), m.get("expectancy_r"), m.get("profit_factor"), m.get("net_return"),
                         m.get("sharpe"), m.get("max_drawdown"), res.get("cost_mult"), res.get("p_value"), res.get("note")])
    sheet(ws, ["ID", "Name", "Period", "Instrument", "TF", "Dataset", "Trades", "Win rate", "Expectancy (R)", "Profit factor",
               "Net return", "Sharpe", "Max drawdown", "Cost x", "p (one-sided)", "Note"], rows,
          [11, 36, 16, 14, 6, 30, 8, 9, 12, 11, 11, 9, 11, 7, 11, 40])
    ws = wb.create_sheet("Implementation Status")
    sheet(ws, ["ID", "Name", "Implementation", "Blocked reason / spec", "Data required", "Warm-up bars", "Indicators used"],
          [[r["id"], r["name"], r["implementation_status"], r.get("blocked_reason") or (r.get("spec") or ""), ", ".join(r["data"]),
            json.dumps(r.get("warmup_bars") or {}), ", ".join((r.get("references") or {}).get("indicators", []))] for r in counted],
          [11, 40, 14, 60, 22, 22, 50])
    ws = wb.create_sheet("Variants (not counted)")
    sheet(ws, ["ID", "Name", "Parent", "What changes"], [[v["id"], v["name"], v["parent_id"], v["what_changes"]] for v in variants],
          [12, 50, 12, 70])
    wb.save(os.path.join(ROOT, "day_trading_strategies.xlsx"))


if __name__ == "__main__":
    counted, variants, errors, exact, near, _ = build()
    counts = write(counted, variants, errors, exact, near)
    print(json.dumps(counts, indent=1))
    print(f"exact duplicates: {len(exact)}; near pairs: {len(near)}")
    for e in errors:
        print("ERROR", e)
