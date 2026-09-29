"""Write results/EVALUATION_REPORT.md from results/evaluation_summary.json(.gz) and catalog.json.

    python strategies/src/report.py
"""

import gzip
import json
import os
import statistics

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
REAL = {"retail_kraken", "base"}


def load():
    p = os.path.join(ROOT, "results", "evaluation_summary.json")
    if os.path.exists(p):
        with open(p) as fh:
            ev = json.load(fh)
    else:
        with gzip.open(p + ".gz", "rt") as fh:
            ev = json.load(fh)
    with open(os.path.join(ROOT, "catalog.json")) as fh:
        cat = json.load(fh)
    return ev, {s["id"]: s for s in cat["strategies"]}


def r(x, d=3):
    return "-" if x is None else f"{x:+.{d}f}"


def main():
    ev, cat = load()
    S = ev["strategies"]
    runs = [(sid, x) for sid, s in S.items() for x in s["runs"]]
    jobs = len({(sid, x["instrument"]) for sid, x in runs})
    crypto_retail = [x for _, x in runs if x["cost"] == "retail_kraken"]
    crypto_low = [x for _, x in runs if x["cost"] == "low_fee_venue"]
    stock = [x for _, x in runs if x["cost"] == "base"]
    prof = lambda xs, n=0: sum(1 for x in xs if (x["full"]["expectancy_r"] or -1) > 0 and (x["full"]["trades"] or 0) >= n)  # noqa: E731
    cands = [(sid, x) for sid, x in runs if x.get("candidate")]
    test_pos = [x for _, x in cands if (x["test"]["expectancy_r"] or -1) > 0]
    avg_full = statistics.mean([x["full"]["expectancy_r"] for _, x in cands if x["full"]["expectancy_r"] is not None]) if cands else None
    avg_test = statistics.mean([x["test"]["expectancy_r"] for _, x in cands if x["test"]["expectancy_r"] is not None]) if cands else None
    gross_pos = sum(1 for _, x in runs if x["cost"] in REAL and ((x.get("gross_full") or {}).get("expectancy_r") or -1) > 0)
    L = ["# Evaluation report\n",
         f"Generated {ev['generated']} (code {ev['code_version']}, experiment {ev['experiment']['experiment_id']}). Protocol: "
         "VALIDATION_METHODOLOGY.md (fixed parameters, chronological 60/20/20 with a one-day embargo, 4 walk-forward folds, "
         "three cost levels, Holm across every test). All numbers are after costs unless marked gross.\n",
         "## Headline\n",
         f"- Strategies evaluated: {len(S)} on {jobs} strategy-instrument pairs; {len(runs):,} cost-level runs, each split into "
         f"train, validation, test, 4 folds and the full period: **{len(runs) * 8:,} backtests** (plus {jobs:,} gross runs).",
         f"- Hypothesis tests counted: {ev['hypothesis_tests']:,}. **Significant after Holm correction: {ev['holm_significant']}.**",
         f"- Deflated Sharpe ratio of the best validation Sharpe: {ev['deflated_sharpe_best_validation']:.3f} (about 0 means the best "
         "result is what luck alone would produce with this many tries).",
         f"- Crypto at Kraken retail fees (0.40% maker / 0.80% taker): {prof(crypto_retail)} of {len(crypto_retail)} runs profitable. "
         f"At a low-fee venue (0.10% taker): {prof(crypto_low)} of {len(crypto_low)}.",
         f"- Stocks with base costs: {prof(stock, 20)} of {len(stock)} runs profitable with 20+ trades.",
         f"- Gross (before any cost) {gross_pos} realistic-cost runs had a positive edge: costs remove most of them.",
         f"- Candidates (positive on train AND validation, 30+ trades, realistic costs): {len(cands)} runs from "
         f"{len({s for s, _ in cands})} strategies. On the untouched test segment {len(test_pos)} of {len(cands)} stayed positive; "
         f"average expectancy {r(avg_full)}R (full period) vs {r(avg_test)}R (test).\n"]
    L.append("## Top 25 runs at realistic costs\n\n| Strategy | Instrument | Trades | R/trade | Gross R | Win % | Net return | "
             "Folds + | Test R (trades) | Holm |\n|---|---|---|---|---|---|---|---|---|---|")
    for x in ev["ranking"][:25]:
        L.append(f"| {x['id']} {x['name']} | {x['instrument']} | {x['trades']} | {r(x['expectancy_r'])} | {r(x['gross_expectancy_r'])} | "
                 f"{100 * (x['win_rate'] or 0):.0f}% | {100 * (x['net_return'] or 0):+.2f}% | {x['folds_positive']} | "
                 f"{r(x['test_expectancy_r'])} ({x['test_trades']}) | {'yes' if x['holm_significant'] else 'no'} |")
    for title, pick in (("Knowledge-pack formalizations (core)", lambda s: any(p["relation"] == "new" for p in s.get("pack_refs", []))
                         and s["family"] != "memecoin"),
                        ("Knowledge-pack memecoin hypotheses (six Coinbase-listed memecoins, 120 days)", lambda s: s["family"] == "memecoin")):
        rows = [(sid, S[sid]) for sid, s in cat.items() if pick(s) and sid in S]
        L.append(f"\n## {title}\n\n| Strategy | Pack id | Best instrument | Trades | R/trade (full) | Gross R | Test R (trades) | "
                 "Candidate |\n|---|---|---|---|---|---|---|---|")
        for sid, s in rows:
            real = [x for x in s["runs"] if x["cost"] in REAL] or s["runs"]
            best = max(real, key=lambda x: x["full"]["expectancy_r"] if x["full"]["expectancy_r"] is not None else -9)
            pid = ", ".join(p["pack_id"] for p in cat[sid].get("pack_refs", []) if p["relation"] == "new")
            L.append(f"| {sid} {s['name']} | {pid} | {best['instrument']} | {best['full']['trades']} | {r(best['full']['expectancy_r'])} | "
                     f"{r((best.get('gross_full') or {}).get('expectancy_r'))} | {r(best['test']['expectancy_r'])} ({best['test']['trades']}) | "
                     f"{'yes' if any(x.get('candidate') for x in s['runs']) else 'no'} |")
    L.append("\n## Reading\n\nThe stock sample is 60 days and the crypto sample 120 days, so each candidate's test segment holds "
             "10-25 trades: single results are noisy. The pattern across all runs is the finding: some rules have a gross edge, "
             "costs remove most of it, and nothing survives correction for the number of ideas tested. Memecoin results use "
             "exchange-listed survivors and are biased upward relative to newly launched tokens.\n")
    if ev.get("errors"):
        L.append(f"\n{len(ev['errors'])} runs failed: " + "; ".join(f"{e['id']} {e['instrument']}: {e['error']}" for e in ev["errors"][:10]))
    with open(os.path.join(ROOT, "results", "EVALUATION_REPORT.md"), "w") as fh:
        fh.write("\n".join(L) + "\n")
    print("\n".join(L[:14]))


if __name__ == "__main__":
    main()
