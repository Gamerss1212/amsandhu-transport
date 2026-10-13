"""START_TRADING_AI.exe: the one thing the owner double-clicks.

1. If Trading AI is already running on this computer, open the browser at it and exit (single instance).
2. Otherwise pick a free port from 8000 upward on 127.0.0.1 (never a network-facing address).
3. Start everything: database, data store, risk service, paper broker, agents, research workers, trading loop, and the
   web server with the compiled dashboard.
4. Open the default browser at http://127.0.0.1:<port>.
5. Keep a small console window open that says the local server is running. Closing it (or Ctrl+C, or the Shut down
   button on the page) stops the bots, saves state and closes the database cleanly.

`--selftest` starts the whole system on a free port, exercises it end to end through HTTP like a browser would, prints
a JSON report and exits 0 (pass) or 1 (fail). The release build is accepted only when it passes.
"""

from __future__ import annotations

import argparse
import json
import os
import socket
import sys
import threading
import time
import webbrowser
from pathlib import Path
from typing import Optional

from tradingai import APP_ID, __version__, config

PORT_RANGE = range(config.DEFAULT_PORT, config.DEFAULT_PORT + 100)


# ---------------------------------------------------------------- single instance
class InstanceLock:
    """An OS-level exclusive lock on data/app.lock: released by the OS even if the program crashes."""

    def __init__(self, folder: Path):
        folder.mkdir(parents=True, exist_ok=True)
        self.path = folder / "app.lock"
        self.port_file = folder / "app.port"
        self.fh = None

    def acquire(self) -> bool:
        self.fh = open(self.path, "a+")
        try:
            if os.name == "nt":
                import msvcrt
                self.fh.seek(0)
                msvcrt.locking(self.fh.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                fcntl.flock(self.fh.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            return True
        except OSError:
            self.fh.close()
            self.fh = None
            return False

    def write_port(self, port: int) -> None:
        self.port_file.write_text(str(port), encoding="ascii")

    def running_port(self) -> Optional[int]:
        try:
            return int(self.port_file.read_text(encoding="ascii").strip())
        except (OSError, ValueError):
            return None


def ping(port: int, timeout: float = 1.5) -> Optional[dict]:
    import httpx
    try:
        r = httpx.get(f"http://127.0.0.1:{port}/api/system/ping", timeout=timeout, trust_env=False)
        d = r.json()
        return d if d.get("app") == APP_ID else None
    except Exception:                                        # noqa: BLE001
        return None


def free_port(preferred: Optional[int] = None) -> int:
    for p in ([preferred] if preferred else []) + list(PORT_RANGE):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if os.name != "nt":                              # ignore TIME_WAIT from a copy that just exited
                s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            try:
                s.bind((config.HOST, p))
                return p
            except OSError:
                continue
    raise RuntimeError(f"no free port between {PORT_RANGE.start} and {PORT_RANGE.stop - 1}")


# ---------------------------------------------------------------- server
class Server:
    def __init__(self, home: Optional[str], port: int, offline: bool, token: Optional[str] = None,
                 console: bool = True):
        import uvicorn

        from tradingai.api.server import create_app
        from tradingai.app import App
        self.core = App(home, offline=offline, start_loop=True)
        self.port = port
        self.api = create_app(self.core, token=token, on_shutdown=self.stop)
        cfg = uvicorn.Config(self.api, host=config.HOST, port=port, log_config=None, access_log=False,
                             lifespan="off", ws="websockets", timeout_graceful_shutdown=3)
        self.uv = uvicorn.Server(cfg)
        self.console = console
        self._stopped = threading.Event()

    @property
    def url(self) -> str:
        return f"http://{config.HOST}:{self.port}"

    def run(self) -> None:
        """Blocks until the server stops."""
        try:
            self.uv.run()
        finally:
            self.close()

    def start_background(self) -> threading.Thread:
        self.uv.config.install_signal_handlers = False if hasattr(self.uv.config, "install_signal_handlers") else None
        t = threading.Thread(target=self.uv.run, name="web-server", daemon=True)
        t.start()
        return t

    def wait_ready(self, timeout: float = 30.0) -> bool:
        t0 = time.time()
        while time.time() - t0 < timeout:
            if self.uv.started and ping(self.port):
                return True
            time.sleep(0.2)
        return False

    def stop(self) -> None:
        self.uv.should_exit = True

    def close(self) -> None:
        if self._stopped.is_set():
            return
        self._stopped.set()
        try:
            if self.core.state.state != "SHUTTING_DOWN":
                self.core.shutdown()
        except Exception as e:                               # noqa: BLE001
            print(f"shutdown note: {type(e).__name__}: {e}")


def _console_close_handler(server: Server) -> None:
    """Windows: closing the console window gives the program a few seconds; use them to save state."""
    if os.name != "nt":
        return
    import ctypes
    from ctypes import wintypes

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.DWORD)
    def handler(event):
        if event in (0, 1, 2, 5, 6):                         # Ctrl+C, Ctrl+Break, close, logoff, shutdown
            server.stop()
            server.close()
            return True
        return False
    ctypes.windll.kernel32.SetConsoleCtrlHandler(handler, True)
    _console_close_handler.keep = handler                    # keep a reference so it is not garbage-collected


def banner(url: str, core) -> str:
    bad = [c for c in core.checks if not c["ok"]]
    lines = ["", "  TRADING AI " + __version__, "  " + "=" * 58,
             f"  Local server running at  {url}",
             "  Only this computer can reach it (127.0.0.1).",
             f"  Mode: {core.mode.upper()}   State: {core.state.state}",
             "  Master agent: " + ("ON - it trains, validates and runs 100 paper trading agents by itself"
                                   if core.autopilot.cfg.enabled else "off (press Start System on the dashboard)"),
             f"  Data folder: {core.paths.base}",
             "", "  Keep this window open while you use the dashboard.",
             "  Close it (or press Ctrl+C) to stop everything safely.", "  " + "=" * 58]
    if bad:
        lines += ["  Start-up checks that did not pass:"] + [f"   - {c['name']}: {c['detail']}" for c in bad]
    return "\n".join(lines) + "\n"


# ---------------------------------------------------------------- self-test
def selftest(home: Optional[str], offline: bool) -> int:
    import httpx
    port = free_port()
    srv = Server(home, port, offline=offline, console=False)
    srv.start_background()
    report: dict = {"version": __version__, "port": port, "steps": []}

    def step(name, fn):
        t = time.perf_counter()
        try:
            detail, ok = fn(), True
        except Exception as e:                               # noqa: BLE001
            detail, ok = f"{type(e).__name__}: {e}", False
        report["steps"].append({"step": name, "ok": ok, "detail": detail, "ms": round((time.perf_counter() - t) * 1000)})
        return ok

    c = httpx.Client(base_url=srv.url, timeout=30, trust_env=False)
    tok = {}

    def page():
        r = c.get("/")
        if r.status_code == 503:
            raise RuntimeError("dashboard files missing (frontend not built)")
        r.raise_for_status()
        assert 'name="ta-token"' in r.text, "dashboard page has no session token"
        tok["h"] = {"X-TA-Token": r.text.split('name="ta-token" content="', 1)[1].split('"', 1)[0]}
        return f"{len(r.text)} bytes of HTML"

    def api(path, method="GET", **kw):
        r = c.request(method, path, headers=tok["h"], **kw)
        if r.status_code >= 400:
            raise RuntimeError(f"{path}: HTTP {r.status_code} {r.text[:200]}")
        return r.json()

    def wait_job(jid, timeout=240):
        t0 = time.time()
        while time.time() - t0 < timeout:
            j = api(f"/api/research/jobs/{jid}")
            if j["state"] not in ("queued", "running"):
                return j
            time.sleep(0.5)
        raise TimeoutError("research job did not finish")

    ok = step("server answers on 127.0.0.1", lambda: srv.wait_ready() or (_ for _ in ()).throw(TimeoutError()))
    ok &= step("/health", lambda: (lambda h: f"state {h['state']['state']}, mode {h['mode']}")(
        c.get("/health").json()))
    ok &= step("dashboard page served", page)
    if "h" not in tok:                                       # keep testing the API even without the dashboard
        tok["h"] = {"X-TA-Token": srv.api.state.token}
    ok &= step("API refuses a request without the session token",
               lambda: (c.get("/api/overview").status_code == 401) or (_ for _ in ()).throw(AssertionError()))
    ok &= step("API refuses a foreign Host header",
               lambda: (c.get("/health", headers={"Host": "evil.example"}).status_code == 421) or
               (_ for _ in ()).throw(AssertionError()))
    ok &= step("starts in PAPER mode", lambda: (api("/api/overview")["mode"] == "paper") or
               (_ for _ in ()).throw(AssertionError("not paper")))
    def by_master(j):
        return str(j["meta"].get("by", "")).startswith("master:")

    def autopilot_working():
        ap = api("/api/autopilot")
        assert ap["config"]["enabled"], "the system is off on a fresh install"
        t0 = time.time()
        while time.time() - t0 < 60:
            mine = [j for j in api("/api/research/jobs") if by_master(j)]
            if mine:
                return f"on by default; the master started training by itself: {mine[-1]['title']}"
            time.sleep(1)
        raise TimeoutError("the master agent did not start any training within 60 s")
    ok &= step("master agent on by default and training by itself", autopilot_working)
    ok &= step("live mode refused without arming", lambda: c.post("/api/mode", headers=tok["h"],
                                                                     json={"mode": "live"}).status_code == 403 or
               (_ for _ in ()).throw(AssertionError("live was not refused")))
    ok &= step("instruments and chart (DEMO, simulated)", lambda: (lambda ch: f"{len(ch['bars'])} bars, simulated="
                                                                   f"{ch['simulated']}")(
        api("/api/chart?instrument=DEMO:DEMO-TREND&tf=5m&n=120")))
    ok &= step("bots are created only by the master (owner request refused)", lambda: c.post(
        "/api/bots", headers=tok["h"], json={"instrument_id": "DEMO:DEMO-TREND", "tf": "5m",
                                              "strategy_id": "tsmom.none.flip"}).status_code == 403 or
        (_ for _ in ()).throw(AssertionError("POST /api/bots was not refused")))
    ok &= step("Start System", lambda: api("/api/bot/start", "POST"))

    def probe():
        f = api("/api/fleet")
        have = [a for a in f["agents"] if a["partition"]]
        pick = (next((a for a in have if a.get("fresh")), None) or
                next((a for a in have if a["partition"][0].startswith("DEMO:")), None) or have[0])
        aid = pick["id"]
        p = api(f"/api/fleet/{aid}/probe", "POST")
        assert "not enough history" not in p["reason"], f"{aid} has no data: the pipeline did not run"
        return f"{aid} on {pick['partition'][0]} ({p['strategy_id']} {p['tf']}, shadow): {p['outcome']}: {p['reason'][:90]}"
    ok &= step("an agent's full decision pipeline runs (shadow probe, nothing sent)", probe)

    def decided():
        t0 = time.time()
        while time.time() - t0 < 60:
            d = api("/api/decisions?limit=5")
            if d:
                return f"{d[0]['outcome']}: {d[0]['reason']}"
            time.sleep(0.5)
        raise TimeoutError("no decision written")
    ok &= step("trading loop writes a decision", decided)
    ok &= step("Stop", lambda: api("/api/bot/stop", "POST"))
    def research_recorded():
        mine = [j for j in api("/api/research/jobs") if by_master(j)]
        assert mine, "the master started no training"
        j = wait_job(mine[0]["job_id"])
        n = api("/api/research/experiments?limit=5")["counts"]["experiments"]
        assert n >= 1, "nothing recorded in the research ledger"
        return f"{j['title']}: {j['state']}; {n} experiment(s) in the ledger"
    ok &= step("automatic research finishes and is recorded", research_recorded)
    ok &= step("no manual backtest route", lambda: c.post("/api/research", headers=tok["h"], json={
        "strategy_id": "tsmom.none.flip", "instrument_id": "DEMO:DEMO-TREND"}).status_code in (404, 405) or
        (_ for _ in ()).throw(AssertionError("POST /api/research still exists")))

    def catalog_ok():
        cat = api("/api/catalog")
        assert len(cat["cards"]) == 124 and len(cat["sources"]) == 98 and len(cat["index"]) == 212, \
            (len(cat["cards"]), len(cat["sources"]), len(cat["index"]))
        return f"qualifying {cat['qualifying']['count']}; " + ", ".join(f"{v} {k}" for k, v in cat["research_states"].items())
    ok &= step("strategy catalog: 124 templates, 98 sources, 212 index entries", catalog_ok)

    def fleet_ok():
        f = api("/api/fleet")
        assert f["counts"]["registered"] == 100 and len(f["agents"]) == 100, f["counts"]
        owned = [i for a in f["agents"] for i in a["partition"]]
        assert len(owned) == len(set(owned)), "an instrument has two owners"
        detail = api("/api/fleet/" + f["agents"][0]["id"])
        assert detail["id"] == f["agents"][0]["id"] and detail["role"]["candidates"], detail.get("role")
        return (f"{f['counts']['registered']} agents, {f['counts']['assigned']} with a distinct market, "
                f"{f['counts']['blocked']} blocked with a reason, {f['counts']['validated']} with a validated version; "
                f"master plan v{f['brain']['plan_version']}")
    ok &= step("master agent: exactly 100 trading agents, one owner per market", fleet_ok)

    def learning_ok():
        r = api("/api/learning/replay", "POST")
        assert not r["failed"], r["failed"]
        m = api("/api/learning")["metrics"]
        return f"{m['lessons']} lesson(s); regression replay {r['passed']}/{r['scenarios']} passed"
    ok &= step("learned safeguards: regression replay passes", learning_ok)

    def thermal_ok():
        t = api("/api/system/thermal")
        r = t["reading"] or {}
        w = (t["machine"].get("windows") or {}).get("name") or t["machine"]["os"]
        temp = f"{r['max_temp_c']:.0f} C" if r.get("max_temp_c") is not None else "no temperature reported"
        return f"{w}: sensors via {t['source']}, {temp}, status {t['assessment']['status']}"
    ok &= step("computer temperature sensors read", thermal_ok)

    def caps_ok():
        r = api("/api/roles")
        ids = [x["id"] for x in r["roles"]]
        assert ids == [f"C{n:02d}" for n in range(1, 51)], ids[:3]
        return f"{len(ids)} support services, {r['counts']['unavailable']} unavailable (no feed), model calls 0"
    ok &= step("support services C01-C50", caps_ok)

    def discovery_ok():
        d = api("/api/coverage/discovery")
        if d["offline"]:
            return "offline mode: discovery off, nothing claimed"
        return ", ".join(f"{v} {x['listed']} listed" for v, x in d["venues"].items()) + \
            f"; {d['meme']['tagged_pairs']} meme pairs (unverified tags)"
    ok &= step("market discovery reports its denominators", discovery_ok)

    def daytrade_ok():
        d = api("/api/daytrade")
        assert d["mode"] == "intraday" and set(d["rules"]) == {"XNYS", "CME", "FX", "CRYPTO"}, d
        return "intraday rules for stocks, futures, forex and crypto"
    ok &= step("day-trading rules in force", daytrade_ok)
    ok &= step("page 1 market strip and decision activity", lambda: (
        f"{len(api('/api/market/strip')['items'])} strip item(s); "
        f"{api('/api/activity')['decisions']} decision(s) in the last hour"))

    def pause_ok():
        assert api("/api/controls/pause-entries", "POST", json={"paused": True, "reason": "selftest"})["entries_paused"]
        assert api("/api/controls/pause-entries", "POST", json={"paused": False})["entries_paused"] is None
        return "paused, then resumed"
    ok &= step("pause new entries and resume", pause_ok)

    def assistant_ok():
        a = api("/api/assistant/ask", "POST", json={"text": "What are all the bots doing?"})
        assert a["intent"] == "bots", a
        r = api("/api/assistant/ask", "POST", json={"text": "go live with all my money"})
        assert r["intent"] == "refused" and api("/api/overview")["mode"] == "paper", r
        return a["answer"][:80]
    ok &= step("assistant answers from state and refuses money commands", assistant_ok)
    ok &= step("reconciliation", lambda: (lambda r: r["ok"] or (_ for _ in ()).throw(AssertionError(r)))(
        api("/api/reconcile", "POST")))
    ok &= step("EMERGENCY STOP engages", lambda: api("/api/emergency-stop", "POST", json={"reason": "selftest"}))

    def no_permission():
        f = api("/api/fleet")
        assert f["counts"]["execution_eligible"] == 0, f["counts"]
        assert all(not a["permission"] for a in f["agents"]), "an agent kept its permission"
        return "0 of 100 agents may open trades while the emergency stop is engaged"
    ok &= step("emergency stop removes every agent's permission", no_permission)
    ok &= step("re-arm with the typed phrase", lambda: api("/api/rearm", "POST", json={"phrase": "RE-ARM TRADING"}))
    ok &= step("audit chain verifies", lambda: api("/api/audit/verify")["ok"] or
               (_ for _ in ()).throw(AssertionError("audit chain broken")))

    def ws_hello():
        import websockets.sync.client as wsc
        with wsc.connect(f"ws://127.0.0.1:{port}/ws?token={tok['h']['X-TA-Token']}", open_timeout=10) as w:
            msg = json.loads(w.recv(timeout=10))
            assert msg["topic"] == "hello"
            return "hello received"
    ok &= step("WebSocket live feed", ws_hello)
    srv.stop()
    time.sleep(1.0)
    srv.close()
    report["passed"] = bool(ok)
    print(json.dumps(report, indent=2, default=str))
    return 0 if ok else 1


# ---------------------------------------------------------------- thermal check
def thermal_check(home: str, minutes: float) -> int:
    """Stand-alone thermal check (no server): 1 minute idle, `minutes` of full load on every logical CPU, 1 minute of
    cool-down. Stops by itself at 95 C, or with Ctrl+C. Writes thermal-reports/thermal-check-<time>.txt."""
    from tradingai import hardware as H
    minutes = max(1.0, min(30.0, minutes))
    m = H.machine()
    win = m.get("windows") or {}
    print(f"Trading AI {__version__} - thermal check", flush=True)
    print(f"Computer: {win.get('name', m['os'])} (build {win.get('build', '-')}), {m.get('cpu') or 'CPU not reported'}, "
          f"{m['logical_cpus']} logical CPUs", flush=True)
    print(f"This runs every CPU core at full load for {minutes:g} minute(s), with 1 minute idle before and 1 minute "
          "to cool down after.", flush=True)
    print(f"It stops by itself if the temperature reaches {H.CRIT_C:.0f} C. Press Ctrl+C to stop at any time.\n",
          flush=True)
    sensors = H.Sensors()
    first = sensors.read()
    if sensors.error:
        print(f"Sensors could not be opened: {sensors.error}", flush=True)
    print("Temperature sensors found: " + (", ".join(f"{x['name']} {x['temp_c']:.0f} C" for x in first["sensors"])
                                           or "none (this PC does not report a temperature to Windows)"), flush=True)
    if sensors.missing():
        print("Counters not provided by this Windows: " + ", ".join(sorted(sensors.missing())), flush=True)
    stop = threading.Event()

    def show(x: dict) -> None:
        t = "  n/a" if x["max_temp_c"] is None else f"{x['max_temp_c']:5.1f} C"
        busy = "  -" if x["cpu_load_pct"] is None else f"{x['cpu_load_pct']:3.0f}%"
        speed = "  -" if x["cpu_perf_pct"] is None else f"{x['cpu_perf_pct']:3.0f}%"
        lim = "" if x["passive_limit_pct"] is None or x["passive_limit_pct"] >= 100 else \
            f"  THROTTLED (limit {x['passive_limit_pct']:.0f}%)"
        rate = "" if x["work_rate"] is None else f"  work {x['work_rate']:.0f}/s"
        print(f"[{x['t_s']:6.0f}s] {x['phase']:<8} temp {t}  busy {busy}  speed {speed}{rate}{lim}", flush=True)
    try:
        res = H.run_check(sensors, minutes, stop=stop, progress=show)
    except KeyboardInterrupt:
        stop.set()
        print("Stopped.", flush=True)
        return 1
    path = H.save_report(res, Path(home) / "thermal-reports")
    print("\n" + "=" * 60, flush=True)
    print(f"RESULT: {res['verdict']}", flush=True)
    for r in res["reasons"]:
        print(f"  - {r}", flush=True)
    print(f"\nFull report: {path}", flush=True)
    return 1 if res["verdict"] == "FAIL" else 0


# ---------------------------------------------------------------- main
def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="START_TRADING_AI", description="Start Trading AI on this computer")
    ap.add_argument("--port", type=int, default=None, help="preferred port (default: first free from 8000)")
    ap.add_argument("--home", default=None, help="data folder (default: beside the program)")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    ap.add_argument("--offline", action="store_true", help="no internet: stored and DEMO data only")
    ap.add_argument("--selftest", action="store_true", help="start, test end to end, print a report, exit")
    ap.add_argument("--thermal-check", action="store_true",
                    help="load every CPU core, watch temperature and throttling, write a report, exit")
    ap.add_argument("--minutes", type=float, default=5.0, help="minutes of full load for --thermal-check (1-30)")
    a = ap.parse_args(argv)
    home = a.home or os.environ.get("TRADING_AI_HOME") or str(config.BASE_DIR)
    if a.selftest:
        return selftest(str(Path(home) / "selftest-data") if not a.home else home, a.offline)
    if a.thermal_check:
        return thermal_check(home, a.minutes)

    lock = InstanceLock(Path(home) / "data")
    if not lock.acquire():
        port = lock.running_port()
        if port and ping(port):
            print(f"Trading AI is already running at http://{config.HOST}:{port} - opening it.")
            if not a.no_browser:
                webbrowser.open(f"http://{config.HOST}:{port}")
            return 0
        print("Another copy of Trading AI is starting or did not exit cleanly. Wait a few seconds and try again.")
        time.sleep(4)
        return 2
    port = free_port(a.port)
    print(f"Starting Trading AI {__version__} ...", flush=True)
    srv = Server(home, port, offline=a.offline)
    lock.write_port(port)
    _console_close_handler(srv)

    def opener():
        if srv.wait_ready(60):
            print(banner(srv.url, srv.core), flush=True)
            if not a.no_browser:
                webbrowser.open(srv.url)
        else:
            print("The local server did not answer within 60 seconds. See logs/trading-ai.log.")
    threading.Thread(target=opener, name="browser", daemon=True).start()
    srv.run()
    print("Trading AI stopped. You can close this window.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
