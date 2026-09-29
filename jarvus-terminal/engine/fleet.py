"""Bridge between the Jarvus window and the bot fleet (package `mab`).

* Fleet: runs the bots in their own process (so their work never slows the window), starts them
  by itself (autopilot) and restarts them if they stop; commands (pause, resume, emergency stop,
  balance changes, enable/disable a bot, live-money controls) go through the fleet's control queue.
* Library and results: the strategy catalog and every measured result, served to the app.
* Brokers: API keys are saved to the encrypted secret store and tested here; the app never gets
  them back.

Money: paper by default. Real-money orders exist only in mab.live, which stays off until the owner
arms it in the app (a tested broker, limits, and the typed acknowledgement).
"""

from __future__ import annotations

import json
import multiprocessing
import os
import shutil
import sys
import time

import config

HERE = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    PAYLOAD = config.BUNDLE_DIR
    MAB_DIR = os.path.join(PAYLOAD, "market_analysis_bots")
else:
    PAYLOAD = os.path.dirname(os.path.dirname(HERE))            # repository root
    MAB_DIR = os.path.join(PAYLOAD, "market_analysis_bots")
    if MAB_DIR not in sys.path:
        sys.path.insert(0, MAB_DIR)

CATALOG = os.path.join(PAYLOAD, "strategies", "catalog.json")
EVENTS = os.path.join(PAYLOAD, "strategies", "data", "events.json")
REGISTRY = os.path.join(MAB_DIR, "bots", "registry.json")
EXAMPLE_CFG = os.path.join(MAB_DIR, "config", "fleet.example.json")
HOME = os.path.join(config.DATA_DIR, "fleet")                    # writable: database, config, bots
PORT = 8765

_proc = None
_catalog = None


# ------------------------------------------------------------------ library
def catalog() -> dict:
    global _catalog
    if _catalog is None:
        with open(CATALOG, encoding="utf-8") as fh:
            _catalog = json.load(fh)
        with open(os.path.join(os.path.dirname(CATALOG), "sources.json"), encoding="utf-8") as fh:
            _catalog["_sources"] = {s["id"]: s for s in json.load(fh)}
    return _catalog


def library() -> dict:
    c = catalog()
    rows = []
    for s in c["strategies"]:
        ev = s.get("evaluation") or {}
        best = ev.get("best_realistic") or {}
        rows.append({"id": s["id"], "name": s["name"], "family": s["family"], "markets": s["markets"],
                     "tf": s["timeframe"], "research": s["research_status"], "impl": s["implementation_status"],
                     "eval": s["evaluation_status"], "best_r": best.get("expectancy_r"), "best_inst": best.get("instrument"),
                     "gross_r": best.get("gross_expectancy_r"), "trades": best.get("trades"),
                     "variants": len(s.get("variants") or [])})
    return {"counts": c["counts"], "generated": c.get("generated"), "strategies": rows}


def strategy(sid: str) -> dict:
    c = catalog()
    s = next((x for x in c["strategies"] if x["id"] == sid), None)
    if s is None:
        return {"error": "unknown strategy"}
    out = dict(s)
    out["sources"] = [dict(c["_sources"].get(e["source"], {"id": e["source"]}), relation=e["relation"], note=e["note"])
                      for e in s.get("evidence", [])]
    out["variant_rows"] = [v for v in c.get("variants", []) if v.get("parent_id") == sid]
    return out


# ------------------------------------------------------------------ fleet process
def _prepare(balance: float = None) -> str:
    os.makedirs(os.path.join(HOME, "config"), exist_ok=True)
    os.makedirs(os.path.join(HOME, "bots"), exist_ok=True)
    cfg_path = os.path.join(HOME, "config", "fleet.json")
    if os.path.exists(cfg_path):
        with open(cfg_path, encoding="utf-8") as fh:
            cfg = json.load(fh)
    else:
        with open(EXAMPLE_CFG, encoding="utf-8") as fh:
            cfg = json.load(fh)
    cfg.update({"catalog": CATALOG, "events_file": EVENTS, "bots_file": os.path.join(HOME, "bots", "registry.json"),
                "data_dir": os.path.join(HOME, "data")})
    if balance:
        cfg.setdefault("account", {})["balance"] = float(balance)
    with open(cfg_path, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, indent=1)
    shutil.copy(REGISTRY, cfg["bots_file"])                         # always the registry shipped with this version
    return cfg_path


def _exit_with_parent():
    """The bots never outlive Jarvus: if the window's process dies (crash, force-kill), the fleet exits too,
    instead of running on unseen and holding its port so the next start fails. Its state is saved after
    every decision, so nothing is lost."""
    parent = multiprocessing.parent_process()
    if parent is None:
        return
    while True:
        time.sleep(3)
        if not parent.is_alive():
            os._exit(0)


def _run(cfg_path: str, stage: str):
    os.environ["MAB_HOME"] = HOME
    if MAB_DIR not in sys.path:
        sys.path.insert(0, MAB_DIR)
    import logging
    import threading
    threading.Thread(target=_exit_with_parent, name="parent-watch", daemon=True).start()
    logging.basicConfig(level=logging.INFO, format="[fleet] %(asctime)s %(levelname)s %(message)s")
    from mab.cli import run_fleet
    run_fleet(stage=stage, dashboard=True, port=PORT, config_path=cfg_path, quiet=False)


def start(stage: str = "250", balance: float = None, auto: bool = False) -> dict:
    global _proc
    if running():
        return {"ok": True, "already_running": True, "dashboard": f"http://127.0.0.1:{PORT}/"}
    cfg = _prepare(balance)
    # a fresh interpreter ("spawn", the Windows default everywhere): forking a process that already
    # runs threads (the Jarvus bots) can copy a held lock into the child and freeze it
    _proc = multiprocessing.get_context("spawn").Process(target=_run, args=(cfg, str(stage)), name="mab-fleet", daemon=True)
    _proc.start()
    if not auto:
        _save_autopilot({"enabled": True, "stage": str(stage)})
    return {"ok": True, "pid": _proc.pid, "stage": stage, "dashboard": f"http://127.0.0.1:{PORT}/"}


# ------------------------------------------------------------------ autopilot
# The fleet runs by itself: it starts when Jarvus starts and is restarted if it ever stops
# unexpectedly. Only the Stop button turns this off (Start turns it back on).
_AUTOPILOT = os.path.join(HOME, "autopilot.json")
_restarts: list = []
_watchdog = None


def _load_autopilot() -> dict:
    try:
        with open(_AUTOPILOT, encoding="utf-8") as fh:
            return {"enabled": True, "stage": "250", **json.load(fh)}
    except (OSError, ValueError):
        return {"enabled": True, "stage": "250"}


def _save_autopilot(d: dict):
    os.makedirs(HOME, exist_ok=True)
    with open(_AUTOPILOT, "w", encoding="utf-8") as fh:
        json.dump(d, fh)


def boot():
    """Called once when Jarvus starts: start the fleet if autopilot is on, and watch over it."""
    global _watchdog
    ap = _load_autopilot()
    if ap["enabled"]:
        which = "all" if ap["stage"] == "250" else f"the stage-{ap['stage']}"
        print(f"  Autopilot: starting {which} bots (paper money).", flush=True)
        start(ap["stage"], auto=True)
    if _watchdog is None:
        import threading
        _watchdog = threading.Thread(target=_watch, name="fleet-watchdog", daemon=True)
        _watchdog.start()


def _watch():
    while True:
        time.sleep(30)
        try:
            ap = _load_autopilot()
            if not ap["enabled"] or running():
                continue
            now = time.time()
            _restarts[:] = [t for t in _restarts if now - t < 3600]
            if len(_restarts) >= 5:                      # something keeps failing: stop retrying for a while
                continue
            _restarts.append(now)
            print("  Autopilot: the fleet had stopped; restarting it.", flush=True)
            start(ap["stage"], auto=True)
        except Exception as e:                            # noqa: BLE001
            print(f"  Autopilot watchdog: {e}", flush=True)


def running() -> bool:
    return _proc is not None and _proc.is_alive()


def _storage():
    if MAB_DIR not in sys.path:
        sys.path.insert(0, MAB_DIR)
    from mab.storage import Storage
    return Storage(os.path.join(HOME, "data", "mab.db"))


def _money_offline(cmd: str, amount: float) -> dict:
    """Change the saved paper account while the fleet is not running (it carries on from it)."""
    cfg_path = _prepare()
    with open(cfg_path, encoding="utf-8") as fh:
        a = json.load(fh).get("account", {})
    os.makedirs(os.path.join(HOME, "data"), exist_ok=True)
    from mab.account import Account
    st = _storage()
    state = st.kv_get("account")
    acc = Account.from_state(state) if state else Account(a.get("balance", 100_000.0), a.get("slots", 20),
                                                          a.get("currency", "USD"))
    if not state:
        st.save_cash_flow(acc.flows[0])
    try:
        rec = getattr(acc, cmd)(float(amount), "set in Jarvus while the fleet was stopped")
    except ValueError as e:
        return {"error": str(e)}
    st.save_cash_flow(rec)
    st.kv_set("account", acc.to_state())
    return {"status": "done", "result": rec, "account": acc.summary()}


COMMANDS = {"pause", "resume", "emergency_stop", "clear_emergency", "set_balance", "deposit", "withdraw", "stop",
            "enable_bot", "disable_bot", "live_status", "live_eligibility", "live_arm", "live_disarm", "live_close_all",
            "set_fee_profile"}


def fee_profiles() -> dict:
    from mab.costs import FEE_PROFILE_LABELS
    cur = "venue"
    if os.path.exists(os.path.join(HOME, "data", "mab.db")):
        cur = _storage().kv_get("fee_profile", "venue") or "venue"
    return {"current": cur, "profiles": [{"name": k, "label": v} for k, v in FEE_PROFILE_LABELS.items()]}


def command(cmd: str, args: dict = None, wait: float = 6.0) -> dict:
    if cmd not in COMMANDS:
        return {"error": "command not allowed"}
    if cmd in ("set_balance", "deposit", "withdraw"):
        try:
            amount = float((args or {}).get("amount"))
        except (TypeError, ValueError):
            return {"error": "type an amount"}
        if not 0 < amount <= 1e12:
            return {"error": "the amount must be more than 0"}
        if not running():
            return _money_offline(cmd, amount)
    if cmd == "set_fee_profile" and not running():         # saved now; the fleet applies it when it starts
        from mab.costs import FEE_PROFILE_LABELS
        name = str((args or {}).get("profile") or "")
        if name not in FEE_PROFILE_LABELS:
            return {"error": "unknown fee profile"}
        _db_storage().kv_set("fee_profile", name)
        return {"status": "done", "result": {"profile": name, "label": FEE_PROFILE_LABELS[name]}}
    if cmd == "live_disarm" and not running():
        return {"status": "done", "result": _live_offline().disarm((args or {}).get("reason") or "owner")}
    if cmd.startswith("live_") and not running():
        return {"error": "start the bots first: live trading runs inside the fleet"}
    if not os.path.exists(os.path.join(HOME, "data", "mab.db")):
        return {"error": "the fleet has not been started yet"}
    st = _storage()
    cid = st.command(cmd, args or {})
    t_end = time.time() + wait
    while time.time() < t_end:
        r = st.command_result(cid)
        if r and r["status"] != "pending":
            try:
                res = json.loads(r["result"]) if r["result"] else None
            except ValueError:
                res = r["result"]
            out = {"status": r["status"], "result": res}
            if r["status"] == "failed":
                out["error"] = str(res)
            return out
        time.sleep(0.25)
    return {"status": "queued", "note": "applies when the fleet is running"}


def stop() -> dict:
    global _proc
    ap = _load_autopilot()
    _save_autopilot({**ap, "enabled": False})                # the operator stopped it: stay stopped
    res = command("stop", wait=3.0) if running() else {"status": "not running"}
    if _proc is not None:
        _proc.join(15)
        if _proc.is_alive():
            _proc.terminate()
        _proc = None
    return res


def status() -> dict:
    out = {"running": running(), "dashboard": f"http://127.0.0.1:{PORT}/", "home": HOME, "autopilot": _load_autopilot()}
    db = os.path.join(HOME, "data", "mab.db")
    if os.path.exists(db):
        try:
            st = _storage()
            r = st.query("SELECT body FROM system_health ORDER BY time DESC LIMIT 1")
            if r:
                h = json.loads(r[0]["body"])
                out.update({k: h.get(k) for k in ("bots", "bot_states", "series", "series_status", "account", "paused",
                                                   "emergency", "completed_evaluations", "scheduled_evaluations",
                                                   "latency_ms_p95", "time")})
            # pause and emergency are written the moment a command applies; the health snapshot lags
            out["paused"] = bool(st.kv_get("paused", False))
            out["emergency"] = st.kv_get("emergency", None)
            # the saved account is written on every fill, balance change and health check, so it is
            # never older than the health snapshot (and a balance change shows at once)
            acct = st.kv_get("account")
            if acct:
                from mab.account import Account
                out["account"] = Account.from_state(acct).summary()
            out["live_armed"] = bool((st.kv_get("live", {}) or {}).get("armed"))
            out["fee_profile"] = st.kv_get("fee_profile", "venue") or "venue"
        except Exception as e:                                          # noqa: BLE001
            out["error"] = str(e)
    return out


# ------------------------------------------------------------------ brokers and real money
def _db_storage():
    os.makedirs(os.path.join(HOME, "data"), exist_ok=True)
    return _storage()


def _live_offline():
    from mab.live import LiveExecutor
    return LiveExecutor(_db_storage(), None)


def brokers() -> dict:
    from mab import broker_setup
    return broker_setup.public(_db_storage())


def broker_save(name: str, key: str, secret: str, options: dict = None) -> dict:
    from mab import broker_setup
    return broker_setup.save(_db_storage(), name, key, secret, options)


def broker_test(name: str) -> dict:
    from mab import broker_setup
    return broker_setup.test(_db_storage(), name)


def broker_remove(name: str) -> dict:
    from mab import broker_setup
    st = _db_storage()
    cfg = st.kv_get("live", {}) or {}
    if cfg.get("armed") and cfg.get("broker") == name:
        raise ValueError("disarm live trading before removing the broker it uses")
    return broker_setup.remove(st, name)


def live() -> dict:
    """Live-money status from the state the fleet saves on every change (no command round trip)."""
    ex = _live_offline()
    out = ex.status()
    out["armed"] = bool(ex.cfg.get("armed"))              # the saved switch; the fleet holds the broker itself
    out["fleet_running"] = running()
    return out


# ------------------------------------------------------------------ results (what was measured)
_results = None


def results() -> dict:
    """Digest of every measurement shipped with this build: strategy runs, full-system runs, volatility gate."""
    global _results
    if _results is not None:
        return _results
    import gzip
    import statistics
    out = {"strategies": None, "system": None, "volgate": None}
    ev_path = os.path.join(PAYLOAD, "strategies", "results", "evaluation_summary.json")
    try:
        if os.path.exists(ev_path):
            with open(ev_path, encoding="utf-8") as fh:
                ev = json.load(fh)
        else:
            with gzip.open(ev_path + ".gz", "rt", encoding="utf-8") as fh:
                ev = json.load(fh)
        runs = [(sid, x) for sid, s in ev["strategies"].items() for x in s["runs"]]

        def prof(xs, n=0):
            return sum(1 for x in xs if (x["full"]["expectancy_r"] or -1) > 0 and (x["full"]["trades"] or 0) >= n)
        by = {c: [x for _, x in runs if x["cost"] == c] for c in ("retail_kraken", "low_fee_venue", "base")}
        cands = [x for _, x in runs if x.get("candidate")]
        tv = [x["test"]["expectancy_r"] for x in cands if x["test"]["expectancy_r"] is not None]
        fv = [x["full"]["expectancy_r"] for x in cands if x["full"]["expectancy_r"] is not None]
        out["strategies"] = {
            "generated": ev.get("generated"), "strategies": len(ev["strategies"]),
            "pairs": len({(sid, x["instrument"]) for sid, x in runs}), "runs": len(runs), "backtests": len(runs) * 8,
            "tests": ev.get("hypothesis_tests"), "holm": ev.get("holm_significant"),
            "dsr": ev.get("deflated_sharpe_best_validation"),
            "crypto_retail": [prof(by["retail_kraken"]), len(by["retail_kraken"])],
            "crypto_low_fee": [prof(by["low_fee_venue"]), len(by["low_fee_venue"])],
            "stocks": [prof(by["base"], 20), len(by["base"])],
            "gross_positive": sum(1 for _, x in runs if x["cost"] in ("retail_kraken", "base")
                                  and ((x.get("gross_full") or {}).get("expectancy_r") or -1) > 0),
            "candidates": len(cands), "candidate_strategies": len({s for s, x in runs if x.get("candidate")}),
            "candidates_test_positive": sum(1 for v in tv if v > 0),
            "candidates_avg_full": statistics.mean(fv) if fv else None,
            "candidates_avg_test": statistics.mean(tv) if tv else None,
            "top": [{k: x.get(k) for k in ("id", "name", "instrument", "trades", "expectancy_r", "gross_expectancy_r",
                                           "win_rate", "test_expectancy_r", "test_trades", "holm_significant")}
                    for x in ev.get("ranking", [])[:15]]}
    except (OSError, ValueError, KeyError) as e:
        out["strategies_error"] = str(e)
    try:
        with open(os.path.join(MAB_DIR, "results", "system_backtest_summary.json"), encoding="utf-8") as fh:
            out["system"] = json.load(fh)
    except (OSError, ValueError):
        pass
    try:
        with open(os.path.join(MAB_DIR, "results", "system_backtest_profiles.json"), encoding="utf-8") as fh:
            prof = json.load(fh)
        from mab.costs import FEE_PROFILE_LABELS
        out["fee_profiles"] = [{"profile": k, "label": FEE_PROFILE_LABELS.get(k, k), "runs": v["runs"],
                                "none": v["arms"]["none"]["return"]["mean"], "gates": v["arms"]["gates"]["return"]["mean"],
                                "brain": v["arms"]["brain"]["return"]["mean"],
                                "brain_positive": v["arms"]["brain"]["return"]["share_positive"],
                                "brain_trades": v["arms"]["brain"]["trades"]["mean"],
                                "brain_avg_r": (v["arms"]["brain"]["avg_r"] or {}).get("mean")}
                               for k, v in prof.items()]
        order = ["venue", "coinbase", "kraken", "ndax", "low_fee"]
        out["fee_profiles"].sort(key=lambda r: order.index(r["profile"]) if r["profile"] in order else 9)
    except (OSError, ValueError, KeyError):
        pass
    try:
        import gzip as _gz
        with _gz.open(os.path.join(PAYLOAD, "strategies", "results", "swing_lab.json.gz"), "rt", encoding="utf-8") as fh:
            lab = json.load(fh)
        rows = []
        for sc, groups in lab["scenarios"].items():
            for g, lst in groups.items():
                for r in lst:
                    if r.get("config"):
                        rows.append({"scenario": sc, "group": g, "setup": r["setup"], "config": r["config"],
                                     "train": r["train"]["mean"], "validation": r["validation"]["mean"],
                                     "test": r["test"]["mean"], "test_n": r["test"]["n"], "test_gross": r["test_gross"]["mean"],
                                     "test_cost": r["test_cost_r"], "survivor": r["survivor"],
                                     "holm": bool(r.get("holm_significant"))})
        out["swing_lab"] = {"generated": lab["generated"], "cuts": lab["cuts"], "configs_per_setup": lab["configs_per_setup"],
                            "rows": rows}
    except (OSError, ValueError, KeyError):
        pass
    try:
        from mab.volgate import MODEL_PATH
        with open(MODEL_PATH, encoding="utf-8") as fh:
            vg = json.load(fh)
        out["volgate"] = {a: {"horizon_hours": m["horizon_hours"], "rows": m["rows"], "period": m["period"],
                              "kind": m.get("kind"), "loud": m["test_loud"], "quiet": m["test_quiet"]}
                          for a, m in vg.items() if a in ("crypto", "stock")}
        out["volgate"]["generated"] = vg.get("generated")
    except (OSError, ValueError, KeyError):
        pass
    _results = out
    return out
