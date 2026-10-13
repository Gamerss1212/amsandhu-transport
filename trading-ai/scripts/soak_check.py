"""Soak and paper-trading check on live market data: run the whole program (online, paper mode) for a while and sample
what it really does; send one paper round trip on a live crypto price through the real order path.

    python scripts/soak_check.py <home folder> [--minutes 30] [--json out.json]

The home folder should hold trained agents (scripts/train_agents.py). Paper only: nothing is sent to a real broker.
"""

from __future__ import annotations

import argparse
import json
import os
import resource
import sys
import time
from decimal import Decimal
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from tradingai.app import App                                   # noqa: E402
from tradingai.core.ids import new_id                           # noqa: E402
from tradingai.risk.service import OrderRequest                 # noqa: E402
from tradingai.strategies.library import MARKET_OF             # noqa: E402


def rss_mb() -> float:
    try:
        with open("/proc/self/status") as fh:
            for line in fh:
                if line.startswith("VmRSS:"):
                    return round(int(line.split()[1]) / 1024, 1)
    except OSError:
        pass
    return round(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss / 1024, 1)


def paper_round_trip(app: App, iid: str = "COINBASE:BTC-USD") -> dict:
    """One small paper buy then sell on a live price, through the risk service, the order authority and the paper
    broker exactly as an agent's order would go (no agent: this is an integration check)."""
    inst = app.book.get(iid)
    out: dict = {"instrument": iid}
    q = app.quote(iid)
    if q is None:
        return dict(out, ok=False, why="no live price")
    acct = app.paper.get_balance()
    qty = (Decimal("50") / Decimal(str(q["price"]))).quantize(inst.quantity_step)
    results = []
    for side, reduces in (("buy", False), ("sell", True)):
        bars, st = app.md.bars(iid, "1h", lookback=3)
        snap = app.risk_snapshot(inst, bars, st, "paper")
        req = OrderRequest(client_order_id="", instrument_id=iid, market=MARKET_OF.get(inst.market_type, "crypto"),
                           side=side, quantity=qty, reference_price=Decimal(str(q["price"])), limit_price=None,
                           multiplier=inst.multiplier, environment="paper", account_id=acct.account_id_masked,
                           reduces_position=reduces, quantity_step=inst.quantity_step)
        res = app.oms.place(decision_id=new_id("SOAK"), req=req, snapshot=snap, broker=app.paper,
                            broker_symbol=inst.symbol, mode="paper", strategy_id=None, decided_at=time.time())
        t0 = time.time()
        while time.time() - t0 < 30:
            app.paper.process()
            o = app.paper.get_order(res["client_order_id"])
            if o is not None and o.status in ("FILLED", "REJECTED", "CANCELLED"):
                break
            time.sleep(0.5)
        o = app.paper.get_order(res["client_order_id"])
        fill = app.db.one("SELECT price, fee FROM fills WHERE client_order_id=?", (res["client_order_id"],))
        results.append({"side": side, "risk": res["risk"]["reason"], "status": o.status if o else res.get("status"),
                        "quote": str(q["price"]), "fill": fill["price"] if fill else None,
                        "fee": fill["fee"] if fill else None,
                        "slippage_bps": None if not fill else round(
                            (float(fill["price"]) / float(q["price"]) - 1) * 1e4 * (1 if side == "buy" else -1), 2)})
    rec = app.reconcile()
    ok = all(r["status"] == "FILLED" for r in results) and rec["ok"] and \
        app.paper.get_positions().get(iid, Decimal(0)) == 0
    return dict(out, ok=ok, qty=str(qty), legs=results, reconcile_ok=rec["ok"],
                ledger_invariant=rec.get("paper_invariant", {}).get("ok"))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("home")
    ap.add_argument("--minutes", type=float, default=30)
    ap.add_argument("--json", default=None)
    a = ap.parse_args()
    t_start = time.time()
    app = App(a.home, offline=False, start_loop=True)
    samples = []
    try:
        print(f"state {app.state.state}; checks failed: {[c['name'] for c in app.checks if not c['ok']]}", flush=True)
        time.sleep(20)
        rt = paper_round_trip(app)
        print("paper round trip:", json.dumps(rt), flush=True)
        cpu0, t0 = os.times(), time.time()
        while time.time() - t_start < a.minutes * 60:
            time.sleep(60)
            c = app.fleet.counts()
            m = app.fleet.metrics
            cpu = os.times()
            errs = sum(len(x.errors) for x in app.fleet.agents.values())
            s = {"t_min": round((time.time() - t_start) / 60, 1), "state": app.state.state,
                 "assigned": c["assigned"], "data_ready": c["data_ready"], "market_closed": c["market_closed"],
                 "validated": c["validated"], "eligible": c["execution_eligible"], "cycles": m["cycles"],
                 "last_cycle_ms": m["last_cycle_ms"], "missed_deadlines": m["missed_deadlines"],
                 "agent_errors": errs, "rss_mb": rss_mb(),
                 "cpu_pct_1core": round(100 * ((cpu.user + cpu.system) - (cpu0.user + cpu0.system)) /
                                        max(1e-9, time.time() - t0), 1),
                 "decisions": app.db.one("SELECT COUNT(*) AS n FROM decisions")["n"],
                 "mistakes": app.db.one("SELECT COUNT(*) AS n FROM mistakes")["n"],
                 "doing": app.fleet.doing[:90]}
            cpu0, t0 = cpu, time.time()
            samples.append(s)
            print(json.dumps(s), flush=True)
        reg = app.learning.replay_all("soak check")
        rec = app.reconcile()
        summary = {"minutes": round((time.time() - t_start) / 60, 1), "paper_round_trip": rt, "samples": samples,
                   "regression": {"passed": reg["passed"], "scenarios": reg["scenarios"], "failed": reg["failed"]},
                   "reconcile_ok": rec["ok"], "audit_ok": app.db.verify_audit()[0],
                   "max_cycle_ms": max((x["last_cycle_ms"] or 0) for x in samples) if samples else None,
                   "missed_deadlines": samples[-1]["missed_deadlines"] if samples else None,
                   "rss_first_last_mb": [samples[0]["rss_mb"], samples[-1]["rss_mb"]] if samples else None}
        print("summary:", json.dumps({k: v for k, v in summary.items() if k != "samples"}), flush=True)
        if a.json:
            Path(a.json).write_text(json.dumps(summary, indent=1, default=str))
    finally:
        app.shutdown()
    return 0


if __name__ == "__main__":
    sys.exit(main())
