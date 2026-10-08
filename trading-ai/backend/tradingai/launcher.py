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
    ok &= step("live mode refused without arming", lambda: c.post("/api/mode", headers=tok["h"],
                                                                     json={"mode": "live"}).status_code == 403 or
               (_ for _ in ()).throw(AssertionError("live was not refused")))
    ok &= step("instruments and chart (DEMO, simulated)", lambda: (lambda ch: f"{len(ch['bars'])} bars, simulated="
                                                                   f"{ch['simulated']}")(
        api("/api/chart?instrument=DEMO:DEMO-TREND&tf=5m&n=120")))
    bot = {}
    ok &= step("create a paper bot", lambda: bot.update(api("/api/bots", "POST", json={
        "instrument_id": "DEMO:DEMO-TREND", "tf": "5m", "strategy_id": "tsmom.none.flip"})) or bot["bot_id"])
    ok &= step("START BOT", lambda: api("/api/bot/start", "POST"))

    def decided():
        t0 = time.time()
        while time.time() - t0 < 60:
            d = api("/api/decisions?limit=5")
            if d:
                return f"{d[0]['outcome']}: {d[0]['reason']}"
            time.sleep(0.5)
        raise TimeoutError("no decision written")
    ok &= step("trading loop writes a decision", decided)
    ok &= step("STOP BOT", lambda: api("/api/bot/stop", "POST"))
    ok &= step("backtest (FAST research job on DEMO 1h)", lambda: (lambda j: f"{j['state']}: {j['result']}")(
        wait_job(api("/api/research", "POST", json={"strategy_id": "tsmom.none.flip", "instrument_id":
                                                    "DEMO:DEMO-TREND", "tf": "1h", "profile": "FAST",
                                                    "lookback": 2000})["job_id"])))
    ok &= step("reconciliation", lambda: (lambda r: r["ok"] or (_ for _ in ()).throw(AssertionError(r)))(
        api("/api/reconcile", "POST")))
    ok &= step("EMERGENCY STOP engages", lambda: api("/api/emergency-stop", "POST", json={"reason": "selftest"}))
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


# ---------------------------------------------------------------- main
def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="START_TRADING_AI", description="Start Trading AI on this computer")
    ap.add_argument("--port", type=int, default=None, help="preferred port (default: first free from 8000)")
    ap.add_argument("--home", default=None, help="data folder (default: beside the program)")
    ap.add_argument("--no-browser", action="store_true", help="do not open the browser")
    ap.add_argument("--offline", action="store_true", help="no internet: stored and DEMO data only")
    ap.add_argument("--selftest", action="store_true", help="start, test end to end, print a report, exit")
    a = ap.parse_args(argv)
    home = a.home or os.environ.get("TRADING_AI_HOME") or str(config.BASE_DIR)
    if a.selftest:
        return selftest(str(Path(home) / "selftest-data") if not a.home else home, a.offline)

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
    print(f"Starting Trading AI {__version__} ...")
    srv = Server(home, port, offline=a.offline)
    lock.write_port(port)
    _console_close_handler(srv)

    def opener():
        if srv.wait_ready(60):
            print(banner(srv.url, srv.core))
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
