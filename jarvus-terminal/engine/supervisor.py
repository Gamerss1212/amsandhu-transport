"""Process supervisor: one bot engine (fleet) process per workspace, plus the shared research worker pool.

* Each workspace (an account's Main or Demo workspace) has its own folder, database, configuration and fleet
  process. A fleet binds a free local port and requires a per-start random token on every request, so no other
  program or account on this computer can drive it.
* Workspaces marked "autostart" start with Jarvus and are restarted if they stop unexpectedly (at most 5 times an
  hour). The owner's Stop keeps a workspace stopped.
* Budgets: at most MAX_FLEETS fleets at once; research jobs run in the shared pool (at most one per spare CPU core,
  each with a time and memory budget).
* Commands reach a fleet through its database's control queue (they apply within about a second and their result is
  returned); a few safety commands (emergency stop, live revoke) also work while a fleet is stopped, directly on the
  saved state it reads at start.
"""

from __future__ import annotations

import http.client
import json
import multiprocessing
import os
import secrets
import shutil
import sys
import threading
import time
from typing import Dict, Optional

import config

HERE = os.path.dirname(os.path.abspath(__file__))
if getattr(sys, "frozen", False):
    PAYLOAD = config.BUNDLE_DIR
else:
    PAYLOAD = os.path.dirname(os.path.dirname(HERE))
MAB_DIR = os.path.join(PAYLOAD, "market_analysis_bots")
if MAB_DIR not in sys.path:
    sys.path.insert(0, MAB_DIR)

CATALOG = os.path.join(PAYLOAD, "strategies", "catalog.json")
EVENTS = os.path.join(PAYLOAD, "strategies", "data", "events.json")
REGISTRY = os.path.join(MAB_DIR, "bots", "registry.json")
EXAMPLE_CFG = os.path.join(MAB_DIR, "config", "fleet.example.json")
MAX_FLEETS = config.MAX_FLEETS
DEMO_MAP = {"BTC": "DEMO-BTC", "ETH": "DEMO-ETH", "SOL": "DEMO-SOL", "DOGE": "DEMO-DOGE", "PEPE": "DEMO-MEME",
            "SHIB": "DEMO-MEME", "BONK": "DEMO-MEME", "WIF": "DEMO-MEME", "FLOKI": "DEMO-MEME"}


def demo_registry(max_bots: int = 24) -> list:
    """The demo workspace's research fleet: registry crypto bots moved onto the synthetic DEMO markets (only
    strategies that read nothing but their own market's bars)."""
    with open(REGISTRY, encoding="utf-8") as fh:
        reg = json.load(fh)["bots"]
    with open(CATALOG, encoding="utf-8") as fh:
        cat = {s["id"]: s for s in json.load(fh)["strategies"]}
    out, seen = [], set()
    for b in reg:
        base = b["instrument"].split("-")[0]
        d = (cat.get(b["strategy_id"]) or {}).get("definition") or {}
        text = json.dumps(d)
        if b["venue"] != "coinbase" or base not in DEMO_MAP or b.get("refs") or "sym(" in text or "on(" in text:
            continue
        if set(d.get("data") or ["bars"]) - {"bars"} or d.get("timeframe") not in ("1m", "5m", "15m", "1h"):
            continue
        key = (b["strategy_id"], DEMO_MAP[base])
        if key in seen:
            continue
        seen.add(key)
        out.append({"bot_id": "DEMO-" + b["bot_id"].split("-")[-1], "name": b["name"].split("|")[0].strip() +
                    f" | {DEMO_MAP[base]}", "strategy_id": b["strategy_id"], "venue": "demo", "instrument": DEMO_MAP[base],
                    "enabled": True, "stages": ["250"]})
        if len(out) >= max_bots:
            break
    return out


def _exit_with_parent():
    parent = multiprocessing.parent_process()
    if parent is None:
        return
    while True:
        time.sleep(3)
        if not parent.is_alive():
            os._exit(0)


def _run(cfg_path: str, token: str, port_file: str, home: str):
    os.environ["MAB_HOME"] = home
    if MAB_DIR not in sys.path:
        sys.path.insert(0, MAB_DIR)
    import logging
    threading.Thread(target=_exit_with_parent, name="parent-watch", daemon=True).start()
    logging.basicConfig(level=logging.INFO, format="[fleet] %(asctime)s %(levelname)s %(message)s")
    from mab.cli import run_fleet
    run_fleet(stage="250", dashboard=True, port=0, config_path=cfg_path, quiet=True, token=token, port_file=port_file)


class Supervisor:
    def __init__(self, auth, max_fleets: int = MAX_FLEETS, research_workers: Optional[int] = None, start_pool: bool = True):
        self.auth = auth
        self.max_fleets = max_fleets
        self.procs: Dict[str, dict] = {}
        self.lock = threading.RLock()
        self._stores: Dict[str, object] = {}
        self._watchdog = None
        self.pool = None
        self.research_workers = research_workers or config.RESEARCH_WORKERS
        self.start_pool = start_pool

    # ------------------------------------------------------------------ paths and configuration
    def home(self, wid: str) -> str:
        w = self.auth.workspace(wid)
        if w is None:
            raise KeyError(f"unknown workspace {wid}")
        return w["path"]

    def db_path(self, wid: str) -> str:
        return os.path.join(self.home(wid), "data", "mab.db")

    def storage(self, wid: str):
        with self.lock:
            st = self._stores.get(wid)
            if st is None:
                from mab.storage import Storage
                os.makedirs(os.path.dirname(self.db_path(wid)), exist_ok=True)
                st = self._stores[wid] = Storage(self.db_path(wid))
            return st

    def prepare(self, wid: str) -> str:
        w = self.auth.workspace(wid)
        home = w["path"]
        os.makedirs(os.path.join(home, "config"), exist_ok=True)
        os.makedirs(os.path.join(home, "bots"), exist_ok=True)
        cfg_path = os.path.join(home, "config", "fleet.json")
        if os.path.exists(cfg_path):
            with open(cfg_path, encoding="utf-8") as fh:
                cfg = json.load(fh)
        else:
            with open(EXAMPLE_CFG, encoding="utf-8") as fh:
                cfg = json.load(fh)
        demo = w["kind"] == "demo"
        cfg.update({"catalog": CATALOG, "events_file": EVENTS, "bots_file": os.path.join(home, "bots", "registry.json"),
                    "data_dir": os.path.join(home, "data"), "workspace": wid, "demo": demo,
                    "autopilot_default": True})              # the AI trades (paper) from the first start
        if demo:
            cfg.setdefault("paper", {})["latency_ms"] = 50
            with open(cfg["bots_file"], "w", encoding="utf-8") as fh:
                json.dump({"bots": demo_registry()}, fh, indent=1)
        else:
            shutil.copy(REGISTRY, cfg["bots_file"])             # always the registry shipped with this version
        with open(cfg_path, "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=1)
        return cfg_path

    # ------------------------------------------------------------------ lifecycle
    def running(self, wid: str) -> bool:
        p = self.procs.get(wid) or {}
        return p.get("proc") is not None and p["proc"].is_alive()

    def start(self, wid: str, auto: bool = False) -> dict:
        with self.lock:
            if self.running(wid):
                return {"ok": True, "already_running": True}
            alive = sum(1 for k in self.procs if self.running(k))
            if alive >= self.max_fleets:
                raise RuntimeError(f"at most {self.max_fleets} bot engines run at once; stop another workspace first")
            cfg = self.prepare(wid)
            home = self.home(wid)
            token = secrets.token_urlsafe(24)
            port_file = os.path.join(home, "data", "fleet.port")
            try:
                os.remove(port_file)
            except OSError:
                pass
            proc = multiprocessing.get_context("spawn").Process(target=_run, args=(cfg, token, port_file, home),
                                                                  name=f"fleet-{wid}", daemon=True)
            proc.start()
            self.procs[wid] = {"proc": proc, "token": token, "port_file": port_file, "started": time.time(),
                               "restarts": (self.procs.get(wid) or {}).get("restarts", [])}
            if not auto:
                self.auth.set_autostart(wid, True)
            return {"ok": True, "pid": proc.pid}

    def stop(self, wid: str, keep_autostart: bool = False) -> dict:
        if not keep_autostart:
            self.auth.set_autostart(wid, False)
        p = self.procs.get(wid)
        if p is None or not p["proc"].is_alive():
            return {"status": "not running"}
        res = self.command(wid, "stop", {}, wait=3.0)
        p["proc"].join(15)
        if p["proc"].is_alive():
            p["proc"].terminate()
        return res

    def stop_all(self):
        for wid in list(self.procs):
            try:
                self.stop(wid, keep_autostart=True)
            except Exception:                                           # noqa: BLE001
                pass
        if self.pool is not None:
            self.pool.stop()

    def boot(self):
        for w in self.auth.workspaces():
            if w["autostart"]:
                try:
                    self.start(w["workspace_id"], auto=True)
                except Exception as e:                                  # noqa: BLE001
                    print(f"  could not start {w['workspace_id']}: {e}", flush=True)
        if self._watchdog is None:
            self._watchdog = threading.Thread(target=self._watch, name="fleet-watchdog", daemon=True)
            self._watchdog.start()
        if self.start_pool and self.pool is None:
            from mab.research.jobs import Pool
            self.pool = Pool(self.databases, os.path.join(config.DATA_DIR, "research-cache"),
                             max_workers=self.research_workers, timeout_s=config.JOB_TIMEOUT_S,
                             max_memory_mb=config.JOB_MEMORY_MB).start()

    def databases(self):
        out = []
        for w in self.auth.workspaces():
            db = os.path.join(w["path"], "data", "mab.db")
            if os.path.exists(db):
                out.append((w["workspace_id"], db))
        return out

    def _watch(self):
        while True:
            time.sleep(20)
            try:
                for w in self.auth.workspaces():
                    wid = w["workspace_id"]
                    if not w["autostart"] or self.running(wid):
                        continue
                    p = self.procs.setdefault(wid, {"restarts": [], "proc": None})
                    now = time.time()
                    p["restarts"] = [t for t in p.get("restarts", []) if now - t < 3600]
                    if len(p["restarts"]) >= 5:
                        continue
                    p["restarts"].append(now)
                    print(f"  Bot engine for {wid} had stopped; restarting it.", flush=True)
                    self.start(wid, auto=True)
            except Exception as e:                                      # noqa: BLE001
                print(f"  watchdog: {e}", flush=True)

    # ------------------------------------------------------------------ talking to a fleet
    def endpoint(self, wid: str):
        p = self.procs.get(wid)
        if not p or not p["proc"] or not p["proc"].is_alive():
            return None
        try:
            with open(p["port_file"], encoding="utf-8") as fh:
                d = json.load(fh)
            return d["port"], p["token"]
        except (OSError, ValueError, KeyError):
            return None

    def fleet_get(self, wid: str, path: str, timeout: float = 8.0):
        """(status, body bytes) from the running fleet's local API, or None when it is not reachable."""
        ep = self.endpoint(wid)
        if ep is None:
            return None
        port, token = ep
        try:
            c = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
            c.request("GET", path, headers={"Host": f"127.0.0.1:{port}", "Authorization": f"Bearer {token}"})
            r = c.getresponse()
            body = r.read()
            c.close()
            return r.status, body
        except OSError:
            return None

    def command(self, wid: str, cmd: str, args: dict = None, wait: float = 8.0) -> dict:
        st = self.storage(wid)
        if not self.running(wid):
            return {"status": "not_running", "error": "the bot engine for this workspace is stopped; start it first"}
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
            time.sleep(0.2)
        return {"status": "queued", "note": "the engine has not answered yet; it will apply the command shortly",
                "command_id": cid}

    def status(self, wid: str) -> dict:
        p = self.procs.get(wid) or {}
        return {"running": self.running(wid), "pid": p.get("proc").pid if p.get("proc") is not None and self.running(wid) else None,
                "started": p.get("started") if self.running(wid) else None, "restarts_last_hour":
                len([t for t in p.get("restarts", []) if time.time() - t < 3600]),
                "autostart": bool((self.auth.workspace(wid) or {}).get("autostart"))}

    # ------------------------------------------------------------------ safety commands that work while stopped
    def emergency_offline(self, wid: str, reason: str) -> dict:
        st = self.storage(wid)
        e = {"time": int(time.time() * 1000), "reason": reason}
        st.kv_set("emergency", e)
        st.audit("control", f"EMERGENCY STOP while the engine was stopped: {reason}; new entries stay blocked when it "
                 "starts. No orders were working (the engine was not running).", stage="emergency_stop", severity="critical")
        return {"blocked": True, "reason": reason, "entry_orders": [], "engine_running": False}

    def live_revoke_offline(self, wid: str, reason: str) -> dict:
        st = self.storage(wid)
        a = dict(st.kv_get("live_authorization", {}) or {}, authorized=False, revoked=int(time.time() * 1000),
                 revoke_reason=reason)
        st.kv_set("live_authorization", a)
        st.audit("control", f"live trading authorisation revoked while the engine was stopped ({reason})",
                 stage="live_revoked", severity="critical", mode="live")
        return {"revoked": True}
