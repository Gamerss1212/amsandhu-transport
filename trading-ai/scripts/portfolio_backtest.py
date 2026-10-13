"""Walk-forward backtest of the master agent's whole selection process, for each of the 100 agents and for the combined
portfolio, broken down by market regime (bull, bear, sideways, volatile).

For every agent the master's protocol is replayed fold by fold, so every traded bar is out of sample:
  1. History before the fold is split 75/25.
  2. Each of the role's 3 candidates gets its parameters fitted on the first 75% (best Sharpe net of costs).
  3. The candidate with the best Sharpe on the last 25% is chosen (the in-sample validation).
  4. The chosen candidate and its parameters trade the next, unseen fold.
Signals are computed causally on the full history; every backtest applies the app's cost model (fees, spread,
slippage, funding where applicable) and the intraday rules.
"GATED" also skips a fold when the chosen candidate lost money in its own validation window, or traded fewer than 3
times there. It is a simple in-sample proxy for the research gate.

    python scripts/portfolio_backtest.py <home folder> [--workers 4] [--report docs/PORTFOLIO_BACKTEST_REPORT.md]

The home folder must hold the master's assignment (run scripts/train_agents.py first); nothing here places orders.
"""

from __future__ import annotations

import argparse
import json
import math
import multiprocessing as mp
import sys
import time
from collections import defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from tradingai.app import App                                   # noqa: E402
from tradingai.engine import master as M                        # noqa: E402
from tradingai.strategies.library import MARKET_OF             # noqa: E402

FOLDS = 6
FIRST = 0.30                       # the first 30% of each history is only ever in-sample
HISTORY = {"1h": 20_000, "15m": 20_000}
BENCH = {"crypto": "COINBASE:BTC-USD", "stock": "US:SPY", "etf": "US:SPY", "future": "US:SPY", "fx": "FX:EURUSD"}


def _wf(task: tuple) -> dict:
    """The master's protocol, walked forward over one agent's history (runs in a worker process)."""
    aid, role, candidates, bars, inst, calendar, market = task
    from tradingai.features.registry import FeatureFrame
    from tradingai.research.engine import PROFILES, _bt, _grid, _sharpe, _signal
    from tradingai.strategies.library import specs
    t0 = time.time()
    sp = specs()
    n = len(bars)
    ppy = FeatureFrame(bars, calendar, market).ppy
    cands = []
    for sid in candidates:
        grid = _grid(sp[sid], PROFILES["STANDARD"]["grid"])
        cands.append((sid, grid, [_signal(sp[sid], bars, calendar, market, p) for p in grid]))
    first = int(n * FIRST)
    wlen = max(50, (n - first) // FOLDS)
    rets = np.zeros(n)
    gated = np.zeros(n)
    covered = np.zeros(n, dtype=bool)
    folds, costs = [], {"fees": 0.0, "spread": 0.0, "slippage": 0.0, "funding": 0.0, "gross": 0.0, "trades": 0}
    gcosts = dict(costs)
    for f in range(FOLDS):
        lo, hi = first + f * wlen, (first + (f + 1) * wlen if f < FOLDS - 1 else n)
        if hi - lo < 20:
            continue
        fit = int(lo * 0.75)
        best = None
        for sid, grid, sigs in cands:
            fit_sh = [_sharpe(_bt(sp[sid], bars.slice(0, fit), s[:fit], inst, ppy, p).returns, ppy)
                      for s, p in zip(sigs, grid)]
            j = int(np.argmax(fit_sh))
            v = _bt(sp[sid], bars.slice(fit, lo), sigs[j][fit:lo], inst, ppy, grid[j])
            vs = _sharpe(v.returns, ppy)
            if best is None or vs > best["val_sharpe"]:
                best = {"sid": sid, "params": grid[j], "sig": sigs[j], "val_sharpe": vs,
                        "val_return": float(v.equity[-1] / v.equity[0] - 1), "val_trades": len(v.trades)}
        r = _bt(sp[best["sid"]], bars.slice(lo, hi), best["sig"][lo:hi], inst, ppy, best["params"])
        trade_it = best["val_return"] > 0 and best["val_trades"] >= 3
        rets[lo:hi] = r.returns
        covered[lo:hi] = True
        c = {k: float(r.costs[k]) for k in ("fees", "spread", "slippage", "funding")}
        c["gross"] = float(sum(t.gross for t in r.trades))
        c["trades"] = len(r.trades)
        for k, v in c.items():
            costs[k] += v
            if trade_it:
                gcosts[k] += v
        if trade_it:
            gated[lo:hi] = r.returns
        folds.append({"fold": f, "from": int(bars.ts[lo]), "to": int(bars.ts[hi - 1]), "chosen": best["sid"],
                      "params": best["params"], "val_sharpe": round(best["val_sharpe"], 3),
                      "val_trades": best["val_trades"], "traded_when_gated": trade_it,
                      "oos_return": round(float(r.equity[-1] / r.equity[0] - 1), 5), "oos_trades": len(r.trades)})
    return {"agent": aid, "role": role, "market": market, "iid": inst.instrument_id, "ts": bars.ts[covered],
            "rets": rets[covered], "gated": gated[covered], "folds": folds, "costs": costs, "gated_costs": gcosts,
            "bars": n, "start": int(bars.ts[0]), "end": int(bars.ts[-1]), "runtime": round(time.time() - t0, 1)}


# ---------------------------------------------------------------- daily aggregation and regimes
def daily(ts: np.ndarray, rets: np.ndarray) -> dict[int, float]:
    """Compound bar returns into UTC-day returns (day number = days since 1970-01-01)."""
    out: dict[int, float] = {}
    days = (ts // 86_400_000).astype(np.int64)
    for d in np.unique(days):
        m = days == d
        out[int(d)] = float(np.prod(1 + rets[m]) - 1)
    return out


def regimes(bars) -> dict[int, str]:
    """Causal daily regime label: each day is labelled from closes up to the PREVIOUS day only.
    volatile: 20-day volatility above 1.5x its trailing one-year median; otherwise bull / bear when the 20-day move is
    beyond half of one 20-day standard deviation, else sideways."""
    close = np.asarray(bars.close, dtype=float)
    days = (np.asarray(bars.ts) // 86_400_000).astype(np.int64)
    lr = np.r_[np.nan, np.diff(np.log(close))]
    out: dict[int, str] = {}
    vols = []
    for i in range(21, len(close)):
        prev = i - 1                                   # information available before day i opens
        vol20 = float(np.nanstd(lr[prev - 19:prev + 1], ddof=1))
        vols.append(vol20)
        r20 = close[prev] / close[prev - 20] - 1
        hist = vols[-252:]
        med = float(np.median(hist)) if len(hist) >= 60 else None
        if med and vol20 > 1.5 * med:
            lab = "volatile"
        elif r20 > 0.5 * vol20 * math.sqrt(20):
            lab = "bull"
        elif r20 < -0.5 * vol20 * math.sqrt(20):
            lab = "bear"
        else:
            lab = "sideways"
        out[int(days[i])] = lab
    return out


def stats(r: list[float], periods: float = 365.0) -> dict:
    a = np.asarray(r, dtype=float)
    if len(a) == 0:
        return {"days": 0}
    eq = np.cumprod(1 + a)
    peak = np.maximum.accumulate(np.r_[1.0, eq])[1:]
    sd = float(np.std(a, ddof=1)) if len(a) > 2 else 0.0
    return {"days": int(len(a)), "total_return": float(eq[-1] - 1), "mean_daily_bp": float(np.mean(a) * 1e4),
            "sharpe": float(np.mean(a) / sd * math.sqrt(periods)) if sd > 0 else None,
            "max_drawdown": float(np.max(1 - eq / peak)), "up_days": float(np.mean(a > 0)),
            "worst_day": float(np.min(a)), "best_day": float(np.max(a))}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("home")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--report", default=str(ROOT / "docs" / "PORTFOLIO_BACKTEST_REPORT.md"))
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    t0 = time.time()
    app = App(a.home, offline=False, start_loop=False)
    try:
        tasks, data_rows = [], []
        for aid, ag in sorted(app.fleet.agents.items()):
            if not ag.partition:
                data_rows.append({"agent": aid, "error": "no market assigned"})
                continue
            role = M.ROLES[ag.role]
            iid = ag.partition[0]
            try:
                bars, st = app.md.bars(iid, role.tf, lookback=HISTORY[role.tf], max_age_s=0)
            except Exception as e:                      # noqa: BLE001
                data_rows.append({"agent": aid, "iid": iid, "error": f"{type(e).__name__}: {e}"})
                continue
            inst = app.book.get(iid)
            market = MARKET_OF.get(inst.market_type, "crypto")
            data_rows.append({"agent": aid, "iid": iid, "tf": role.tf, "bars": len(bars), "provider": st.get("provider"),
                              "start": int(bars.ts[0]) if len(bars) else None,
                              "end": int(bars.ts[-1]) if len(bars) else None})
            print(f"  data {aid} {iid} {role.tf}: {len(bars)} bars", flush=True)
            if len(bars) >= 400:
                tasks.append((aid, ag.role, role.candidates, bars, inst, inst.calendar or "CRYPTO", market))
        bench = {}
        for mk, iid in BENCH.items():
            if iid not in bench:
                b, _ = app.md.bars(iid, "1d", lookback=2000, max_age_s=0)
                bench[iid] = {"regime": regimes(b), "close": dict(zip((np.asarray(b.ts) // 86_400_000).astype(int).tolist(),
                                                                     np.asarray(b.close, float).tolist())),
                              "bars": len(b)}
        print(f"walk-forward: {len(tasks)} agents on {a.workers} worker(s)", flush=True)
        res: dict[str, dict] = {}
        with ProcessPoolExecutor(max_workers=a.workers, mp_context=mp.get_context("spawn")) as ex:
            futs = [ex.submit(_wf, t) for t in tasks]
            for k, f in enumerate(as_completed(futs), 1):
                try:
                    r = f.result()
                except Exception as e:                  # noqa: BLE001
                    print(f"  failed: {type(e).__name__}: {e}", flush=True)
                    continue
                res[r["agent"]] = r
                print(f"  [{k}/{len(tasks)}] {r['agent']} {r['iid']}: {len(r['folds'])} folds, "
                      f"OOS {float(np.prod(1 + r['rets']) - 1):+.2%} ({r['runtime']}s)", flush=True)
        summary = summarise(res, bench, data_rows, time.time() - t0)
        if a.json:
            Path(a.json).write_text(json.dumps(summary, indent=1, default=str))
        Path(a.report).write_text(render(summary))
        print(f"report written to {a.report}", flush=True)
    finally:
        app.shutdown()
    return 0


def summarise(res: dict, bench: dict, data_rows: list, secs: float) -> dict:
    per_agent, sleeves, gsleeves = [], {}, {}
    for aid, r in sorted(res.items()):
        d = daily(r["ts"], r["rets"])
        g = daily(r["ts"], r["gated"])
        sleeves[aid], gsleeves[aid] = d, g
        c = r["costs"]
        cost = c["fees"] + c["spread"] + c["slippage"] + c["funding"]
        per_agent.append({"agent": aid, "role": r["role"], "iid": r["iid"], "market": r["market"],
                          "oos_days": len(d), "oos": stats(list(d.values())), "gated": stats(list(g.values())),
                          "folds": r["folds"], "trades": c["trades"], "gross_pnl": c["gross"], "costs": cost,
                          "cost_breakdown": {k: c[k] for k in ("fees", "spread", "slippage", "funding")},
                          "gated_folds": sum(1 for f in r["folds"] if f["traded_when_gated"]),
                          "chosen": sorted({f["chosen"] for f in r["folds"]})})

    def combine(group: dict[str, dict[int, float]]) -> dict[int, float]:
        days = sorted({d for s in group.values() for d in s})
        out = {}
        for d in days:
            xs = [s[d] for s in group.values() if d in s]
            out[d] = float(np.mean(xs))                 # equal weight across the sleeves covering that day
        return out
    port, gport = combine(sleeves), combine(gsleeves)
    by_role = {}
    for role in M.ROLES:
        mem = {a: s for a, s in sleeves.items() if res[a]["role"] == role}
        gmem = {a: s for a, s in gsleeves.items() if res[a]["role"] == role}
        if not mem:
            continue
        bmk = BENCH[M.ROLES[role].market]
        rd, gd = combine(mem), combine(gmem)
        by_role[role] = {"agents": len(mem), "benchmark": bmk, "all": stats(list(rd.values())),
                         "gated": stats(list(gd.values())), "regimes": by_regime(rd, bench[bmk]["regime"]),
                         "gated_regimes": by_regime(gd, bench[bmk]["regime"])}
    combined = {"all": stats(list(port.values())), "gated": stats(list(gport.values())),
                "first_day": min(port) if port else None, "last_day": max(port) if port else None,
                "by_spy_regime": by_regime(port, bench["US:SPY"]["regime"]),
                "by_btc_regime": by_regime(port, bench["COINBASE:BTC-USD"]["regime"]),
                "gated_by_spy_regime": by_regime(gport, bench["US:SPY"]["regime"]),
                "gated_by_btc_regime": by_regime(gport, bench["COINBASE:BTC-USD"]["regime"])}
    bh = {}
    for iid in ("US:SPY", "COINBASE:BTC-USD"):
        cl = bench[iid]["close"]
        ds = [d for d in sorted(cl) if combined["first_day"] and combined["first_day"] <= d <= combined["last_day"]]
        if len(ds) > 1:
            bh[iid] = {"from": ds[0], "to": ds[-1], "return": cl[ds[-1]] / cl[ds[0]] - 1}
    tot_cost = sum(x["costs"] for x in per_agent)
    tot_gross = sum(x["gross_pnl"] for x in per_agent)
    return {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "runtime_s": round(secs),
            "agents_tested": len(res), "data": data_rows, "per_agent": per_agent, "by_role": by_role,
            "combined": combined, "buy_and_hold": bh, "regime_days": {
                k: dict(sorted(_count(v["regime"], combined).items())) for k, v in bench.items()},
            "costs": {"total": tot_cost, "gross": tot_gross,
                      "breakdown": {k: sum(x["cost_breakdown"][k] for x in per_agent)
                                    for k in ("fees", "spread", "slippage", "funding")}}}


def _count(reg: dict[int, str], combined: dict) -> dict:
    lo, hi = combined.get("first_day"), combined.get("last_day")
    out: dict = defaultdict(int)
    for d, lab in reg.items():
        if lo and lo <= d <= hi:
            out[lab] += 1
    return out


def by_regime(series: dict[int, float], reg: dict[int, str]) -> dict:
    """Group day returns by the benchmark's regime. A day the benchmark did not trade (weekend, holiday) takes the
    most recent earlier label, which uses only information from before that day."""
    import bisect
    keys = sorted(reg)
    groups: dict[str, list] = defaultdict(list)
    for d, r in series.items():
        lab = reg.get(d)
        if lab is None:
            i = bisect.bisect_right(keys, d) - 1
            lab = reg[keys[i]] if i >= 0 and d - keys[i] <= 5 else "unlabelled"
        groups[lab].append(r)
    return {k: stats(v) for k, v in sorted(groups.items())}


def pct(x, nd=1):
    return "-" if x is None else f"{x * 100:+.{nd}f}%"


def dd(x, nd=1):
    return "-" if x is None else f"{x * 100:.{nd}f}%"


def num(x, nd=2):
    return "-" if x is None else f"{x:.{nd}f}"


def day(d):
    return "-" if d is None else datetime.fromtimestamp(d * 86400, timezone.utc).strftime("%Y-%m-%d")


def regime_table(title: str, rg: dict) -> list[str]:
    L = [f"**{title}**", "", "| Regime | Days | Return over those days | Mean per day | Sharpe (ann.) | Up days | Worst day |",
         "|---|---|---|---|---|---|---|"]
    for k in ("bull", "bear", "sideways", "volatile", "unlabelled"):
        s = rg.get(k)
        if not s or not s.get("days"):
            continue
        L.append(f"| {k} | {s['days']} | {pct(s['total_return'])} | {s['mean_daily_bp']:+.1f} bp | {num(s['sharpe'])} | "
                 f"{s['up_days'] * 100:.0f}% | {pct(s['worst_day'], 2)} |")
    return L + [""]


def render(s: dict) -> str:
    c = s["combined"]
    a, g = c["all"], c["gated"]
    L = ["# Portfolio backtest report (walk-forward, by market regime)", "",
         f"Generated {s['generated']} by `scripts/portfolio_backtest.py`, using the app's own backtester and cost model "
         f"on real market data. The run took {s['runtime_s'] // 60} minutes. {s['agents_tested']} agents had enough "
         "history to test.", "",
         "## Method", "",
         "- **No look-ahead.** Each agent's history is walked forward in "
         f"{FOLDS} folds after the first {int(FIRST * 100)}%.",
         "  - Before each fold, the 3 candidates of the agent's role are fitted on the first 75% of the history so far.",
         "  - The best candidate is chosen on the remaining 25% (validation).",
         "  - That choice then trades the next fold, which it has never seen.",
         "  - Signals are computed causally, and orders fill at the next bar.",
         "- **Costs.** Every backtest includes the app's cost model for its market: fees, spread, slippage and funding.",
         "  - Funding is zero for spot crypto, because the agents hold no perpetual futures.",
         "  - FX swap is not modelled. FX positions are always closed before the daily rollover, under the intraday "
         "rules.",
         "  - Futures are flat in roll windows.",
         "- **Intraday rules** apply in every backtest: entry windows, flat before the close, and a 24-hour maximum hold "
         "for crypto.",
         "- **Portfolio.** Each agent is a sleeve with equal capital, rebalanced daily among the sleeves that have "
         "out-of-sample data that day.",
         "  - Inside its sleeve, an agent risks 1% of the sleeve per trade (stop-based exits) or targets 15% "
         "volatility (signal exits).",
         "  - Day returns are compounded from bar returns, by UTC day.",
         "- **ALL** trades every fold with the chosen candidate.",
         "- **GATED** skips a fold when the chosen candidate lost money in its own validation window, or traded fewer than "
         "3 times there. This uses in-sample information only.",
         "- **Regimes.** Each day is labelled from a benchmark's daily closes up to the previous day:",
         "  - **volatile**: 20-day volatility is above 1.5 times its one-year median;",
         "  - **bull** or **bear**: the 20-day move is beyond half of one 20-day standard deviation;",
         "  - **sideways**: everything else.",
         "  - Benchmarks: BTC for crypto, SPY for stocks, ETFs and index futures, EUR/USD for FX.",
         "",
         "## Combined portfolio (all agents with out-of-sample data)", "",
         f"Out-of-sample period: {day(c['first_day'])} to {day(c['last_day'])}.", "",
         "| Variant | Days | Total return | Sharpe (ann., 365 d) | Max drawdown | Up days | Worst day |",
         "|---|---|---|---|---|---|---|"]
    for name, x in (("ALL", a), ("GATED", g)):
        if x.get("days"):
            L.append(f"| {name} | {x['days']} | {pct(x['total_return'])} | {num(x['sharpe'])} | "
                     f"{dd(x['max_drawdown'])} | {x['up_days'] * 100:.0f}% | {pct(x['worst_day'], 2)} |")
    bh = s["buy_and_hold"]
    if bh:
        L += ["", "For comparison, buy and hold over the same dates: " + "; ".join(
            f"{k.split(':')[1]} {pct(v['return'])} ({day(v['from'])} to {day(v['to'])})" for k, v in bh.items()) + "."]
    co = s["costs"]
    L += ["", f"Trading costs over all sleeves: {co['total']:,.0f} (fees {co['breakdown']['fees']:,.0f}, spread "
          f"{co['breakdown']['spread']:,.0f}, slippage {co['breakdown']['slippage']:,.0f}, funding "
          f"{co['breakdown']['funding']:,.0f}), against gross trading P&L of {co['gross']:,.0f}. All amounts are in "
          "account currency, on each sleeve's own 100,000 of backtest capital.", ""]
    if co["gross"] > 0 and co["total"] > co["gross"]:
        L += [f"**Costs were {co['total'] / co['gross']:.1f} times the gross trading profit.** Before costs the "
              "agents made a little money in total; after costs they lost it. This is the main reason the research gate "
              "rejects every version.", ""]
    L += regime_table("Combined ALL, by US equity regime (SPY)", c["by_spy_regime"])
    L += regime_table("Combined ALL, by crypto regime (BTC)", c["by_btc_regime"])
    L += regime_table("Combined GATED, by US equity regime (SPY)", c["gated_by_spy_regime"])
    L += ["## Each role, by its own market's regime", ""]
    for role, x in s["by_role"].items():
        L += [f"### {M.ROLES[role].label} ({x['agents']} agents, benchmark {x['benchmark']})", "",
              f"ALL: {x['all'].get('days', 0)} days, {pct(x['all'].get('total_return'))}, Sharpe "
              f"{num(x['all'].get('sharpe'))}, max drawdown {dd(x['all'].get('max_drawdown'))}. GATED: "
              f"{pct(x['gated'].get('total_return'))}, Sharpe {num(x['gated'].get('sharpe'))}, max drawdown "
              f"{dd(x['gated'].get('max_drawdown'))}.", ""]
        L += regime_table("ALL by regime", x["regimes"])
    L += ["## Every agent (out of sample)", "",
          "| Agent | Market | Candidates chosen across folds | OOS days | OOS return | Sharpe | Max DD | Trades | Costs / gross "
          "P&L | Folds traded when gated | GATED return |", "|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in s["per_agent"]:
        o, gg = x["oos"], x["gated"]
        ratio = (f"{x['costs'] / x['gross_pnl']:.0%}" if x["gross_pnl"] > 0 else
                 ("gross loss" if x["gross_pnl"] < 0 else "-"))
        L.append(f"| {x['agent']} | {x['iid']} | {', '.join(c_.split('.')[0] for c_ in x['chosen'])} | {o.get('days', 0)} | "
                 f"{pct(o.get('total_return'))} | {num(o.get('sharpe'))} | {dd(o.get('max_drawdown'))} | {x['trades']} | "
                 f"{ratio} | {x['gated_folds']}/{len(x['folds'])} | {pct(gg.get('total_return'))} |")
    missing = [d for d in s["data"] if d.get("error") or (d.get("bars") or 0) < 400]
    if missing:
        L += ["", "## Not tested", "", "| Agent | Market | Why |", "|---|---|---|"]
        for d in missing:
            L.append(f"| {d['agent']} | {d.get('iid', '-')} | {d.get('error') or str(d.get('bars')) + ' bars (need 400)'} |")
    L += ["", "## Reading this honestly", "",
          "- This is a backtest of past data under stated assumptions. It is not a forecast and not a promise of "
          "returns.",
          "- Live fills can be worse than the cost model, especially for small coins and at the open.",
          "- The 15-minute agents have only about 60 days of data, so their numbers rest on few trades.",
          "- Regime labels are a reporting device. A short window may contain few days of a given regime, and the day "
          "counts are shown so the sample size is visible. Days the benchmark did not trade (weekends, holidays) take "
          "the previous trading day's label.",
          "- The live system is stricter than ALL. An agent trades only after its own research run passes every gate "
          "(PAPER TEST), and in paper only.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
