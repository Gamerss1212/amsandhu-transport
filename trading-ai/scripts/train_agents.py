"""Train and validate all 100 trading agents on real market data, exactly as the master agent does inside the app.

For every agent the master's role gives three candidate templates. Each candidate gets one STANDARD research run on the
agent's own market and bar size (the app's research engine: fit on the first 60%, validation on the next 20%, held-out
test on the last 20%, walk-forward, Monte Carlo, cost stress, Deflated Sharpe, PBO). The master then chooses the version
with the best VALIDATION Sharpe and records it; only a PAPER TEST verdict may trade (paper only).

    python scripts/train_agents.py <home folder> [--workers 4] [--report docs/AGENT_TRAINING_REPORT.md]

Runs go into that home's research ledger and agent-version table. Nothing here places orders.
"""

from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import sys
import time
from collections import Counter, defaultdict
from concurrent.futures import ProcessPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from tradingai.app import App                                   # noqa: E402
from tradingai.engine import master as M                        # noqa: E402
from tradingai.research.engine import PROFILES, _grid           # noqa: E402
from tradingai.storage.db import now_ms                         # noqa: E402
from tradingai.strategies.library import MARKET_OF, specs      # noqa: E402


def _work(task: tuple) -> tuple:
    """One STANDARD research run in a worker process (same function the app's research job calls)."""
    key, sid, bars, inst, calendar, market, trials = task
    from tradingai.research.engine import run_research
    from tradingai.strategies.library import specs as _specs
    t0 = time.time()
    try:
        res = run_research(_specs()[sid], bars, inst, calendar, market, profile="STANDARD", trials_so_far=trials, seed=7)
    except Exception as e:                                      # noqa: BLE001 - reported per run
        res = {"status": "error", "error": f"{type(e).__name__}: {e}"}
    for k in ("equity_curve", "test_trades"):                   # the ledger keeps the metrics; the report needs no curve
        res.pop(k, None)
    return key, res, round(time.time() - t0, 1)


def fmt(x, nd=2, pct=False):
    if x is None:
        return "-"
    try:
        return f"{float(x) * 100:.{nd}f}%" if pct else f"{float(x):.{nd}f}"
    except (TypeError, ValueError):
        return str(x)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("home")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--report", default=str(ROOT / "docs" / "AGENT_TRAINING_REPORT.md"))
    ap.add_argument("--json", default=None, help="also write the raw summary here")
    ap.add_argument("--previous", default=None, help="summary JSON of an earlier pass, reported for the record")
    a = ap.parse_args()
    t_start = time.time()
    app = App(a.home, offline=False, start_loop=False)
    try:
        app.autopilot.cfg.enabled = True
        listed = app.discovery.refresh_listings()
        snap = app.discovery.snapshot()
        app.fleet.assign()
        print(f"discovery: {listed}; {snap} pairs in the snapshot; {len(app.fleet.owner)} instruments owned", flush=True)
        sp = specs()

        # ---- data: one documented dataset per agent (provider, bars, range, SHA-256)
        data: dict[str, dict] = {}
        for aid, ag in sorted(app.fleet.agents.items()):
            if not ag.partition:
                data[aid] = {"error": "no market assigned"}
                continue
            iid, tf = ag.partition[0], M.ROLES[ag.role].tf
            try:
                bars, st = app.md.bars(iid, tf, lookback=M.LOOKBACK[tf], max_age_s=0)
            except Exception as e:                              # noqa: BLE001
                data[aid] = {"iid": iid, "tf": tf, "error": f"{type(e).__name__}: {e}"}
                continue
            data[aid] = {"iid": iid, "tf": tf, "bars": bars, "provider": st.get("provider"),
                         "simulated": bars.simulated, "n": len(bars)}
            if len(bars):
                data[aid].update(start=int(bars.ts[0]), end=int(bars.ts[-1]), sha256=bars.sha256())
            print(f"  data {aid} {iid} {tf}: {len(bars)} bars from {st.get('provider')}", flush=True)

        # ---- research: 3 candidates per agent, trials charged per family in a fixed order (multiple testing)
        base: dict[str, int] = {}
        tasks = []
        for aid, d in sorted(data.items()):
            if "bars" not in d or d["n"] < 400:
                continue
            inst = app.book.get(d["iid"])
            market = MARKET_OF.get(inst.market_type, "crypto")
            for sid in M.ROLES[app.fleet.agents[aid].role].candidates:
                fam = sp[sid].family
                if fam not in base:
                    base[fam] = app.ledger.family_trials(fam)
                tasks.append(((aid, sid), sid, d["bars"], inst, inst.calendar or "CRYPTO", market, base[fam]))
                base[fam] += len(_grid(sp[sid], PROFILES["STANDARD"]["grid"]))
        print(f"research: {len(tasks)} STANDARD runs on {a.workers} worker(s)", flush=True)
        runs: dict[tuple, dict] = {}
        with ProcessPoolExecutor(max_workers=a.workers, mp_context=mp.get_context("spawn")) as ex:
            futs = [ex.submit(_work, t) for t in tasks]
            for k, f in enumerate(as_completed(futs), 1):
                (aid, sid), res, secs = f.result()
                d = data[aid]
                if res.get("status") == "ok":
                    eid = app.ledger.start(family=sp[sid].family, strategy_id=sid, hypothesis=sp[sid].economic_hypothesis,
                                           instrument=d["iid"], tf=d["tf"], profile="STANDARD", seed=7,
                                           dataset={"provider": d["provider"], "bars": d["n"], "start": d["start"],
                                                    "end": d["end"], "sha256": d["sha256"],
                                                    "simulated": d["simulated"]})
                    app.ledger.finish(eid, res)
                    res["experiment_id"] = eid
                else:                                           # as in the app: the master skips it for 12 hours
                    app.fleet.unavailable[f"{aid}|{sid}"] = now_ms() + M.DAY // 2
                runs[(aid, sid)] = dict(res, runtime=secs)
                print(f"  [{k}/{len(tasks)}] {aid} {sid} {d['iid']} {d['tf']}: "
                      f"{res.get('verdict') or res.get('status')} ({secs}s)", flush=True)

        # ---- the master chooses each agent's version (validation Sharpe; only PAPER TEST may trade)
        for aid, d in sorted(data.items()):
            if "bars" in d and d["n"] < 400:
                for sid in M.ROLES[app.fleet.agents[aid].role].candidates:
                    app.fleet.unavailable[f"{aid}|{sid}"] = now_ms() + M.DAY // 2
            app.fleet._choose_version(app.fleet.agents[aid])
        app.fleet._save()
        summary = build_summary(app, data, runs, time.time() - t_start)
        if a.previous:
            prev = json.loads(Path(a.previous).read_text())
            summary["previous"] = {"generated": prev["generated"], "counts": prev["counts"],
                                   "bars": dict(Counter(f"{x['tf']} {x['bars']}" for x in prev["agents"]))}
        if a.json:
            Path(a.json).write_text(json.dumps(summary, indent=1, default=str))
        Path(a.report).write_text(render(summary))
        print(f"report written to {a.report}", flush=True)
        c = summary["counts"]
        print(json.dumps(c, indent=1), flush=True)
    finally:
        app.shutdown()
    return 0


def build_summary(app: App, data: dict, runs: dict, secs: float) -> dict:
    agents = []
    for aid, ag in sorted(app.fleet.agents.items()):
        role = M.ROLES[ag.role]
        d = data.get(aid, {})
        vers = app.fleet.versions(aid)
        latest = vers[-1] if vers else None
        cands = []
        for sid in role.candidates:
            r = runs.get((aid, sid)) or {}
            cands.append({"sid": sid, "status": r.get("status"), "verdict": r.get("verdict"),
                          "val_sharpe": (r.get("validation") or {}).get("sharpe"),
                          "test_sharpe": (r.get("test") or {}).get("sharpe"),
                          "test_return": (r.get("test") or {}).get("total_return"),
                          "test_dd": (r.get("test") or {}).get("max_drawdown"),
                          "test_trades": (r.get("test") or {}).get("trades"),
                          "wf_sharpe": (r.get("walk_forward") or {}).get("oos_sharpe"),
                          "dsr": (r.get("statistics") or {}).get("dsr"), "pbo": (r.get("statistics") or {}).get("pbo"),
                          "reason_codes": r.get("reason_codes"), "error": r.get("error"),
                          "experiment_id": r.get("experiment_id"), "runtime": r.get("runtime")})
        agents.append({"agent": aid, "role": ag.role, "role_label": role.label, "tf": role.tf,
                       "iid": d.get("iid") or (ag.partition[0] if ag.partition else None),
                       "provider": d.get("provider"), "bars": d.get("n"), "start": d.get("start"), "end": d.get("end"),
                       "sha256": d.get("sha256"), "data_error": d.get("error"),
                       "version": None if not latest else {k: latest[k] for k in ("version", "status", "strategy_id",
                                                                                  "reason")},
                       "candidates": cands})
    verdicts = Counter(c["verdict"] or c["status"] or "not run" for x in agents for c in x["candidates"])
    status = Counter((x["version"] or {}).get("status", "no version") for x in agents)
    by_role = defaultdict(Counter)
    for x in agents:
        by_role[x["role"]][(x["version"] or {}).get("status", "no version")] += 1
    return {"generated": datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"), "runtime_s": round(secs),
            "counts": {"agents": len(agents), "with_market": sum(1 for x in agents if x["iid"]),
                       "runs": sum(1 for x in agents for c in x["candidates"] if c["status"]),
                       "run_verdicts": dict(verdicts), "version_status": dict(status)},
            "by_role": {k: dict(v) for k, v in by_role.items()}, "agents": agents}


def render(s: dict) -> str:
    def day(ms):
        return "-" if not ms else datetime.fromtimestamp(ms / 1000, timezone.utc).strftime("%Y-%m-%d")
    c = s["counts"]
    L = [
        "# Agent training report (100 agents)",
        "",
        f"Generated {s['generated']} by `scripts/train_agents.py`, using the app's own research engine on real market "
        f"data. The run took {s['runtime_s'] // 60} minutes.",
        "",
        "## Method",
        "",
        "- **Datasets.** Each agent trains on its own market and bar size, using up to "
        f"{M.LOOKBACK['1h']:,} hourly or {M.LOOKBACK['15m']:,} 15-minute bars.",
        "  - The data comes from public sources: Coinbase for crypto, Yahoo Finance for stocks, ETFs, FX and futures.",
        "  - The provider, bar count, date range and SHA-256 of every dataset are listed below and stored in the research "
        "ledger.",
        "- **Objective.** Each of the role's 3 candidate templates gets one STANDARD research run.",
        "  - Parameters are fitted on the first 60% of the bars (TRAIN), using the Sharpe ratio net of modelled costs.",
        "  - The master chooses the candidate with the best VALIDATION Sharpe (the next 20%).",
        "  - The last 20% is a held-out TEST that is never used for any choice.",
        "  - Walk-forward refits are judged out of sample.",
        "- **Costs.** Fees, spread, slippage and funding are taken from the app's cost model for each market. Day-trading "
        "rules apply: entries only inside session windows, and every position is flat before the close or the 24-hour "
        "crypto limit.",
        "- **Gate.** A version may trade (in paper only) only if its research verdict is PAPER TEST. That verdict requires "
        "all of the following:",
        "  - at least 30 test trades;",
        "  - Deflated Sharpe ≥ 0.95, charged for every trial run in the strategy family so far;",
        "  - PBO ≤ 0.2;",
        "  - a walk-forward ratio ≥ 0.5;",
        "  - 2x-cost survival;",
        "  - a placebo percentile ≥ 95.",
        "",
        "  Anything else is recorded as a rejected version, and the agent stays in cash.",
        "- **Multiple testing.** Trials are charged per family, in a fixed order (A001 to A100). Later agents in a "
        "crowded family therefore face a stricter Deflated Sharpe hurdle. This is deliberate.",
        "",
        "## Results",
        "",
        f"- Agents: {c['agents']}; with a market: {c['with_market']}; research runs completed: {c['runs']}.",
        "- Run verdicts: " + ", ".join(f"{k}: {v}" for k, v in sorted(c["run_verdicts"].items())) + ".",
        "- Agent versions after training: " + ", ".join(f"{k}: {v}" for k, v in sorted(c["version_status"].items())) +
        ". \"active\" means the agent may trade in paper; \"rejected\" and \"no version\" mean it stays in cash.",
        "",
        "| Role | " + " | ".join(sorted({k for v in s["by_role"].values() for k in v})) + " |",
        "|---|" + "---|" * len({k for v in s["by_role"].values() for k in v}),
    ]
    keys = sorted({k for v in s["by_role"].values() for k in v})
    for role in M.ROLES:
        v = s["by_role"].get(role, {})
        L.append(f"| {M.ROLES[role].label} | " + " | ".join(str(v.get(k, 0)) for k in keys) + " |")
    if s.get("previous"):
        pv = s["previous"]
        L += ["", "## Earlier pass (kept on record)", "",
              f"A first pass on {pv['generated']} used shorter windows (5,000 hourly or 2,000 15-minute bars). Its results "
              "were:",
              "",
              "- Run verdicts: " + ", ".join(f"{k}: {v}" for k, v in sorted(pv["counts"]["run_verdicts"].items())) + ".",
              "- Versions: " + ", ".join(f"{k}: {v}" for k, v in sorted(pv["counts"]["version_status"].items())) + ".",
              "- Most runs had fewer than 30 trades in the held-out test, so they could never pass.",
              "",
              "The master now trains on the longest history the engine accepts. The first pass's trials stay in the "
              "ledger, so this pass faces a stricter Deflated Sharpe hurdle, not a looser one. No gate was changed."]
    L += ["", "## Every agent", "",
          "The \"chosen\" row is the candidate the master picked by validation Sharpe. The test columns are the held-out "
          "last 20%. Test return and max drawdown are on the backtest's own capital (1% risk per trade).", "",
          "| Agent | Market (bar) | Data | Chosen | Val. Sharpe | Test Sharpe | Test return | Test max DD | Test trades | "
          "WF OOS Sharpe | DSR | PBO | Verdict | Version |",
          "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for x in s["agents"]:
        v = x["version"] or {}
        ch = next((c for c in x["candidates"] if c["sid"] == v.get("strategy_id")), None)
        if ch is None:
            ok = [c for c in x["candidates"] if c["val_sharpe"] is not None]
            ch = max(ok, key=lambda c: c["val_sharpe"]) if ok else None
        data = (f"{x['provider']} {x['bars']} bars {day(x['start'])} to {day(x['end'])}" if x.get("bars") else
                (x.get("data_error") or "no data"))
        if ch is None:
            L.append(f"| {x['agent']} | {x['iid'] or '-'} ({x['tf']}) | {data} | - | - | - | - | - | - | - | - | - | "
                     f"not trained | {v.get('status', 'no version')} |")
            continue
        L.append(f"| {x['agent']} | {x['iid']} ({x['tf']}) | {data} | {ch['sid']} | {fmt(ch['val_sharpe'])} | "
                 f"{fmt(ch['test_sharpe'])} | {fmt(ch['test_return'], 1, True)} | {fmt(ch['test_dd'], 1, True)} | "
                 f"{ch['test_trades'] if ch['test_trades'] is not None else '-'} | {fmt(ch['wf_sharpe'])} | "
                 f"{fmt(ch['dsr'])} | {fmt(ch['pbo'])} | {ch['verdict'] or ch['status']} | "
                 f"{('v' + str(v['version']) + ' ' + v['status']) if v else 'no version'} |")
    L += ["", "## Dataset fingerprints", "", "| Agent | Market | SHA-256 (first 16) |", "|---|---|---|"]
    for x in s["agents"]:
        if x.get("sha256"):
            L.append(f"| {x['agent']} | {x['iid']} {x['tf']} | `{x['sha256'][:16]}` |")
    L += ["", "## Reading this honestly", "",
          "- These are backtests on past data under stated cost assumptions. They are not a forecast and not a promise "
          "of returns.",
          "- An agent that is rejected stays in cash. That is the intended result when the evidence is not strong enough.",
          "- Data windows are short for 15-minute bars (the free provider keeps about 60 days), so those agents have "
          "few test trades. Most of them cannot pass the 30-trade minimum.",
          "- The app retrains every agent on fresh data every 7 days. A newer version must first beat the active one in "
          "shadow on bars it was not trained on.", ""]
    return "\n".join(L)


if __name__ == "__main__":
    sys.exit(main())
