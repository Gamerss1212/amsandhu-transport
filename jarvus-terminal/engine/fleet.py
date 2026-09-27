"""Bridge between Jarvus Terminal and the market-analysis bot platform (package `mab`).

* Library: the strategy catalog (strategies/catalog.json) with statuses, rules, sources and
  measured results, served to the Library tab.
* Fleet: starts the bot fleet in its own process (so its work never slows the Jarvus window),
  with its dashboard on http://127.0.0.1:8765, and sends it commands (pause, resume, emergency
  stop, balance changes, stop) through the fleet's control queue.

Paper trading only. The fleet process has no code path that can place a real order.
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


def _run(cfg_path: str, stage: str):
    os.environ["MAB_HOME"] = HOME
    if MAB_DIR not in sys.path:
        sys.path.insert(0, MAB_DIR)
    import logging
    logging.basicConfig(level=logging.INFO, format="[fleet] %(asctime)s %(levelname)s %(message)s")
    from mab.cli import run_fleet
    run_fleet(stage=stage, dashboard=True, port=PORT, config_path=cfg_path, quiet=False)


def start(stage: str = "250", balance: float = None) -> dict:
    global _proc
    if running():
        return {"ok": True, "already_running": True, "dashboard": f"http://127.0.0.1:{PORT}/"}
    cfg = _prepare(balance)
    _proc = multiprocessing.Process(target=_run, args=(cfg, str(stage)), name="mab-fleet", daemon=True)
    _proc.start()
    return {"ok": True, "pid": _proc.pid, "stage": stage, "dashboard": f"http://127.0.0.1:{PORT}/"}


def running() -> bool:
    return _proc is not None and _proc.is_alive()


def _storage():
    if MAB_DIR not in sys.path:
        sys.path.insert(0, MAB_DIR)
    from mab.storage import Storage
    return Storage(os.path.join(HOME, "data", "mab.db"))


def command(cmd: str, args: dict = None, wait: float = 6.0) -> dict:
    allowed = {"pause", "resume", "emergency_stop", "clear_emergency", "set_balance", "deposit", "withdraw", "stop"}
    if cmd not in allowed:
        return {"error": "command not allowed"}
    if not os.path.exists(os.path.join(HOME, "data", "mab.db")):
        return {"error": "the fleet has not been started yet"}
    st = _storage()
    cid = st.command(cmd, args or {})
    t_end = time.time() + wait
    while time.time() < t_end:
        r = st.command_result(cid)
        if r and r["status"] != "pending":
            return {"status": r["status"], "result": json.loads(r["result"]) if r["result"] else None}
        time.sleep(0.25)
    return {"status": "queued", "note": "applies when the fleet is running"}


def stop() -> dict:
    global _proc
    res = command("stop", wait=3.0) if running() else {"status": "not running"}
    if _proc is not None:
        _proc.join(15)
        if _proc.is_alive():
            _proc.terminate()
        _proc = None
    return res


def status() -> dict:
    out = {"running": running(), "dashboard": f"http://127.0.0.1:{PORT}/", "home": HOME}
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
        except Exception as e:                                          # noqa: BLE001
            out["error"] = str(e)
    return out
