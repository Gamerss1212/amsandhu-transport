"""The local web app: double-click ``QuantAgents.bat`` and your browser opens it.

    python -m quantagents --config config/my_universe.yaml app

Everything the text menu does, as buttons on one page: run today, the dashboard and
scoreboard, the automatic daily run, stop and resume, your symbols, the real-money checks and
bringing an account over from an older folder.

It runs on this computer only, and it adds no new powers: every button runs an ordinary
``quantagents`` command. It cannot raise a limit, switch on real money or show your keys.

Safety:
- it listens on 127.0.0.1 only, and refuses a request whose Host is not this app (so another
  website cannot reach it by renaming itself, "DNS rebinding");
- every request carries a random key that only this page knows; a website you visit cannot
  read it, and a request from another site's page (its Origin) is refused;
- the page cannot be shown inside another site's frame (no hidden clicks);
- STOP always works, even while another job runs.
"""

from __future__ import annotations

import argparse
import contextlib
import io
import json
import platform
import re
import secrets
import threading
import time
import urllib.request
import webbrowser
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from http import HTTPStatus
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

import yaml

from quantagents import __version__, envfile, migrate, ops
from quantagents.config import AppConfig, ExecutionMode, load_config
from quantagents.data.sources import split_universe
from quantagents.execution import live
from quantagents.execution.paper import PaperAccount
from quantagents.menu import Shell, _shell, is_scheduled, schedule_for, set_schedule
from quantagents.risk.killswitch import RESET_PHRASE, KillSwitch
from quantagents.watchdog import check as watchdog_check

APP = "QuantAgents"
DEFAULT_PORT = 8765
WEB_DIR = Path(__file__).with_name("web")
KEY_HEADER = "X-QuantAgents-Key"
SYMBOL = re.compile(r"^[A-Z0-9][A-Z0-9.\-^=]{0,24}$")
MAX_SYMBOLS = 30
PRESETS: dict[str, dict[str, Any]] = {
    "us_etfs": {
        "label": "8 US-listed ETFs (stocks, bonds, gold, commodities, property)",
        "universe": {
            "asset_class": "US_equities",
            "symbols": ["SPY", "EFA", "EEM", "TLT", "IEF", "GLD", "DBC", "VNQ"],
        },
    },
    "crypto_cad": {
        "label": "Crypto on Kraken, in CAD (BTC and ETH) - use its own folder",
        "universe": {"asset_class": "crypto_spot", "symbols": ["BTC-CAD.KRAKEN", "ETH-CAD.KRAKEN"]},
    },
}
Run = Callable[[list[str]], int]
JOBS: dict[str, tuple[str, list[str]]] = {
    "run_today": ("Today's paper trading day", ["daily"]),
    "doctor": ("Install check", ["doctor"]),
    "live_check": ("Real money: what is still needed", ["live", "check"]),
    "live_preview": ("Real money: preview (nothing is sent)", ["live", "sync", "--dry-run"]),
    "live_test_order": ("Real money: tiny test order", ["live", "test-order"]),
}


@dataclass
class Job:
    id: str
    label: str
    output: io.StringIO = field(default_factory=io.StringIO)
    code: int | None = None
    started: float = field(default_factory=time.time)
    ended: float | None = None

    def view(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "label": self.label,
            "done": self.code is not None,
            "code": self.code,
            "output": self.output.getvalue(),
            "seconds": round((self.ended or time.time()) - self.started),
        }


class Jobs:
    """One background command at a time (a second daily run must never overlap the first)."""

    def __init__(self, run: Run) -> None:
        self._run = run
        self._lock = threading.Lock()
        self._jobs: dict[str, Job] = {}
        self.current: Job | None = None

    def busy(self) -> bool:
        return self.current is not None and self.current.code is None

    def start(self, label: str, argv: list[str]) -> Job | None:
        with self._lock:
            if self.busy():
                return None
            job = Job(secrets.token_hex(6), label)
            self._jobs[job.id] = job
            self.current = job
        threading.Thread(target=self._work, args=(job, argv), daemon=True).start()
        return job

    def _work(self, job: Job, argv: list[str]) -> None:
        envfile.load()  # a line just added to .env counts (values are never shown)
        try:
            with contextlib.redirect_stdout(job.output), contextlib.redirect_stderr(job.output):
                code = self._run(argv)
        except BaseException as exc:  # a job must always finish, whatever the command did
            job.output.write(f"\nerror: {type(exc).__name__}: {exc}\n")
            code = 1
        job.ended = time.time()
        job.code = code

    def get(self, job_id: str) -> Job | None:
        return self._jobs.get(job_id)


def _universe_text(symbols: list[str], asset_class: str) -> str:
    return f"{asset_class}: {', '.join(symbols)}"


def write_symbols(config: Path, symbols: list[str], asset_class: str, runs_dir: Path) -> str:
    """Put a new symbol list into the settings file. Only ``universe`` (and, for crypto, the
    unit size) changes; every other setting is kept exactly as the owner wrote it."""
    clean = [s.strip().upper() for s in symbols if s.strip()]
    if not clean:
        raise ValueError("type at least one symbol")
    if len(clean) > MAX_SYMBOLS:
        raise ValueError(f"at most {MAX_SYMBOLS} symbols in one folder")
    bad = [s for s in clean if not SYMBOL.match(s)]
    if bad:
        raise ValueError(f"these do not look like symbols: {', '.join(bad)}")
    clean = list(dict.fromkeys(clean))
    yahoo, crypto = split_universe(clean)
    if yahoo and crypto:
        raise ValueError(
            "stocks and crypto need separate folders (crypto trades on weekends, stocks do not). "
            "Unzip a second copy of QuantAgents for crypto."
        )
    last = ops.cycle_records(runs_dir)
    before = set(last[-1].get("snapshot", {}).get("last_close", {})) if last else set()
    if before and not before & set(clean):
        raise ValueError(
            f"this folder's paper account already trades {', '.join(sorted(before))}. One folder "
            "holds one paper account: for a completely different list, use a second copy."
        )
    raw: dict[str, Any] = {}
    if config.exists():
        loaded = yaml.safe_load(config.read_text(encoding="utf-8"))
        raw = loaded if isinstance(loaded, dict) else {}
    universe = dict(raw.get("universe") or {})
    universe["symbols"] = clean
    universe["asset_class"] = "crypto_spot" if crypto else asset_class or "US_equities"
    raw["universe"] = universe
    if crypto:
        raw["risk"] = {**dict(raw.get("risk") or {}), "quantity_step": 0.0001}
    AppConfig.model_validate(raw)  # never write a file that would not load
    header = (
        "# Your QuantAgents settings. Written by the app; edit by hand if you like.\n"
        "# Every setting not written here keeps its default (config/default.yaml).\n"
    )
    config.parent.mkdir(parents=True, exist_ok=True)
    tmp = config.with_name(config.name + ".tmp")
    tmp.write_text(header + yaml.safe_dump(raw, sort_keys=False), encoding="utf-8")
    tmp.replace(config)
    return _universe_text(clean, universe["asset_class"])


@dataclass
class App:
    """Everything one running web app needs. Paths are relative to the project folder."""

    config: str
    folder: Path
    run: Run
    shell: Shell = _shell
    system: str = field(default_factory=platform.system)
    data: Path = Path("data/prices.csv")
    token: str = field(default_factory=lambda: secrets.token_urlsafe(24))
    port: int = 0
    stop_server: Callable[[], None] = lambda: None
    jobs: Jobs = field(init=False)

    def __post_init__(self) -> None:
        self.jobs = Jobs(self.run)

    def cfg(self) -> AppConfig:
        path = Path(self.config)
        return load_config(path if path.exists() else None)

    # ---- reading -------------------------------------------------------------------------

    def status(self) -> dict[str, Any]:
        out: dict[str, Any] = {
            "app": APP,
            "version": __version__,
            "folder": str(self.folder),
            "config": self.config,
            "reset_phrase": RESET_PHRASE,
            "presets": {k: v["label"] for k, v in PRESETS.items()},
            "errors": [],
        }
        try:
            cfg = self.cfg()
        except ValueError as exc:
            out["errors"].append(f"Your settings file {self.config} has a problem: {exc}")
            cfg = AppConfig()
        s = cfg.system
        symbols = list(cfg.universe.symbols)
        out["mode"] = s.execution_mode.value
        out["currency"] = s.base_currency
        out["symbols"] = symbols
        out["synthetic"] = bool(symbols) and all(x.startswith("SYN_") for x in symbols)
        switch = KillSwitch(live.KILL_FILE).state()
        out["kill"] = {
            "engaged": switch.engaged,
            "reason": switch.reason,
            "by": switch.by,
            "at": switch.at_utc,
        }
        sched = schedule_for(cfg, self.folder)
        try:
            on = is_scheduled(sched, self.folder, self.system, self.shell)
        except Exception:  # an odd scheduler must not break the page
            on = False
        out["schedule"] = {"on": on, "words": sched.words}
        cycles = ops.cycle_records(live.RUNS_DIR)
        out["paper_days"] = len({str(c["as_of"]) for c in cycles})
        out["days_needed"] = ops.PAPER_DAYS_NEEDED
        out["halted"] = sum(1 for c in cycles if c.get("risk", {}).get("level") == "HALTED")
        out["breaks"] = sum(1 for c in cycles if not c.get("reconciliation", {}).get("ok", True))
        out["account"] = self._account(cfg, cycles)
        out["series"] = [
            {
                "date": d,
                "paper": round(p * 100, 4),
                "hold": None if h is None else round(h * 100, 4),
            }
            for d, p, h in ops.score_series(
                cycles, self.data, out["account"].get("start") or s.capital
            )
        ]
        out["last_cycle"] = self._last_cycle(cycles)
        out["last_daily"] = ops.last_daily_lines(live.RUNS_DIR / "daily.log")
        try:
            out["watchdog"] = (
                watchdog_check(
                    runs_dir=live.RUNS_DIR,
                    state_file=live.STATE_FILE,
                    data=self.data if self.data.exists() else None,
                    today=datetime.now(UTC).date(),
                )
                if cycles
                else []
            )
        except Exception as exc:
            out["watchdog"] = [f"could not check: {exc}"]
        gates = live.gates(
            cfg,
            status_file=live.STATUS_FILE,
            kill_file=live.KILL_FILE,
            runs_dir=live.RUNS_DIR,
            today=datetime.now(UTC).date(),
            ccxt_installed=live.has_ccxt(),
        )
        out["live"] = {
            "on": s.execution_mode is ExecutionMode.LIVE,
            "armed": all(g.ok for g in gates),
            "budget": cfg.live.budget,
            "gates": [{"name": g.name, "ok": g.ok, "detail": g.detail} for g in gates],
            "mirror": live.mirror_summary(live.STATE_FILE),
        }
        job = self.jobs.current
        out["job"] = job.view() if job is not None and job.code is None else None
        return out

    def _account(self, cfg: AppConfig, cycles: list[dict[str, Any]]) -> dict[str, Any]:
        if not live.STATE_FILE.exists():
            return {"exists": False}
        account = PaperAccount.load_or_new(live.STATE_FILE, cfg.system.capital, cfg.costs)
        last = cycles[-1] if cycles else {}
        prices = {
            str(k): float(v) for k, v in last.get("snapshot", {}).get("last_close", {}).items()
        }
        book = account.ledger.book
        equity = book.equity(prices) if prices else book.cash
        peak = max([account.capital, equity, *(e for _, e in account.equity_history)])
        positions = [
            {
                "symbol": sym,
                "qty": qty,
                "value": qty * prices[sym] if sym in prices else None,
                "weight": qty * prices[sym] / equity if sym in prices and equity else None,
            }
            for sym, qty in sorted(book.quantities().items())
            if qty
        ]
        return {
            "exists": True,
            "equity": equity,
            "start": account.capital,
            "return": equity / account.capital - 1.0,
            "cash": book.cash,
            "drawdown": max(0.0, 1 - equity / peak),
            "fees": book.fees_paid,
            "positions": positions,
            "fills": len(account.ledger.fills),
            "pending": len(account.broker.pending),
            "scoreboard": ops.scoreboard(cycles, self.data, equity / account.capital - 1.0),
        }

    @staticmethod
    def _last_cycle(cycles: list[dict[str, Any]]) -> dict[str, Any] | None:
        if not cycles:
            return None
        last = cycles[-1]
        no_trade = {str(v.get("symbol")): v for v in last.get("no_trade", [])}
        decisions = [
            {
                "symbol": p.get("symbol"),
                "go": bool(p.get("go")),
                "direction": p.get("direction"),
                "p_up": p.get("pooled_p"),
                "teams": p.get("teams_agree"),
                "why": "; ".join(p.get("reasons", [])) if not p.get("go") else "",
                "p_no_trade": no_trade.get(str(p.get("symbol")), {}).get("p_no_trade"),
            }
            for p in last.get("proposals", [])
        ]
        return {
            "as_of": last.get("as_of"),
            "ran": last["_ran"].strftime("%Y-%m-%d %H:%M UTC"),
            "level": last.get("risk", {}).get("level"),
            "health": last.get("health", {}).get("score_0_100"),
            "decisions": decisions,
            "intents": len(last.get("intents", [])),
        }

    # ---- doing -----------------------------------------------------------------------------

    def act(self, body: dict[str, Any]) -> tuple[HTTPStatus, dict[str, Any]]:
        action = str(body.get("action", ""))
        if action == "stop":  # always allowed, even while a job runs: stopping only cuts risk
            KillSwitch(live.KILL_FILE).engage("stopped from the app", by="human")
            return HTTPStatus.OK, {"message": "Stopped. Nothing new will trade until you resume."}
        if action == "resume":
            try:
                KillSwitch(live.KILL_FILE).reset(str(body.get("phrase", "")).strip(), by="human")
            except PermissionError:
                return HTTPStatus.BAD_REQUEST, {
                    "error": f"Not resumed: type the exact phrase {RESET_PHRASE}."
                }
            return HTTPStatus.OK, {"message": "Resumed. Trading may continue on the next day."}
        if action in JOBS:
            if action == "live_test_order" and body.get("confirm") != "YES":
                return HTTPStatus.BAD_REQUEST, {"error": "Type YES to send the real test order."}
            label, argv = JOBS[action]
            job = self.jobs.start(label, ["--config", self.config, *argv])
            if job is None:
                return HTTPStatus.CONFLICT, {"error": "Another job is still running. Wait for it."}
            return HTTPStatus.OK, {"job": job.id, "label": label}
        if self.jobs.busy():
            return HTTPStatus.CONFLICT, {"error": "Another job is still running. Wait for it."}
        if action in ("schedule_on", "schedule_off"):
            cfg = self.cfg()
            lines = set_schedule(
                action == "schedule_on",
                schedule_for(cfg, self.folder),
                self.folder,
                self.system,
                self.shell,
            )
            return HTTPStatus.OK, {"message": " ".join(lines)}
        if action == "symbols":
            preset = PRESETS.get(str(body.get("preset", "")))
            if preset is not None:
                symbols, asset = preset["universe"]["symbols"], preset["universe"]["asset_class"]
            else:
                text = str(body.get("symbols", ""))
                symbols, asset = re.split(r"[\s,;]+", text), "US_equities"
            try:
                saved = write_symbols(Path(self.config), symbols, asset, live.RUNS_DIR)
            except ValueError as exc:
                return HTTPStatus.BAD_REQUEST, {"error": f"Not saved: {exc}"}
            return HTTPStatus.OK, {"message": f"Saved. Your symbols are now {saved}."}
        if action == "import":
            old = Path(str(body.get("path", "")).strip().strip('"').strip("'"))
            if not str(old) or str(old) == ".":
                return HTTPStatus.BAD_REQUEST, {"error": "Type the path of the older folder."}
            try:
                lines = migrate.import_from(old, self.folder)
            except (OSError, ValueError) as exc:
                return HTTPStatus.BAD_REQUEST, {"error": f"Not imported: {exc}"}
            off = set_schedule(False, schedule_for(self.cfg(), old), old, self.system, self.shell)
            return HTTPStatus.OK, {"message": "\n".join([*lines, f"Old folder: {' '.join(off)}"])}
        if action == "quit":
            threading.Thread(target=self.stop_server, daemon=True).start()
            return HTTPStatus.OK, {"message": "The app is closing. You can close this tab."}
        return HTTPStatus.BAD_REQUEST, {"error": f"unknown action {action!r}"}


class Handler(BaseHTTPRequestHandler):
    server_version = "QuantAgents"
    app: App  # set on the subclass made per server

    def log_message(self, format: str, *args: Any) -> None:  # quiet console
        return

    # ---- safety ----------------------------------------------------------------------------

    def _host_ok(self) -> bool:
        host = self.headers.get("Host", "")
        return host in {f"127.0.0.1:{self.app.port}", f"localhost:{self.app.port}"}

    def _origin_ok(self) -> bool:
        origin = self.headers.get("Origin")
        allowed = {f"http://127.0.0.1:{self.app.port}", f"http://localhost:{self.app.port}"}
        return origin is None or origin in allowed

    def _key_ok(self) -> bool:
        return secrets.compare_digest(self.headers.get(KEY_HEADER, ""), self.app.token)

    def _send(self, status: HTTPStatus, body: bytes, kind: str) -> None:
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header(
            "Content-Security-Policy",
            "default-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; "
            "form-action 'none'",
        )
        self.end_headers()
        self.wfile.write(body)

    def _json(self, status: HTTPStatus, data: dict[str, Any]) -> None:
        self._send(status, json.dumps(data, default=str).encode("utf-8"), "application/json")

    # ---- routes ----------------------------------------------------------------------------

    def do_GET(self) -> None:
        if not self._host_ok():
            self._json(HTTPStatus.FORBIDDEN, {"error": "wrong host"})
            return
        path = self.path.split("?", 1)[0]
        if path == "/api/ping":
            self._json(HTTPStatus.OK, {"app": APP, "folder": str(self.app.folder)})
            return
        if path in ("/", "/index.html"):
            page = (WEB_DIR / "index.html").read_text(encoding="utf-8")
            page = page.replace("__KEY__", self.app.token).replace("__VERSION__", __version__)
            self._send(HTTPStatus.OK, page.encode("utf-8"), "text/html; charset=utf-8")
            return
        if path in ("/app.js", "/app.css"):
            kind = "text/javascript" if path.endswith(".js") else "text/css"
            body = (WEB_DIR / path.lstrip("/")).read_bytes()
            self._send(HTTPStatus.OK, body, f"{kind}; charset=utf-8")
            return
        if not path.startswith("/api/"):
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        if not self._key_ok():
            self._json(HTTPStatus.FORBIDDEN, {"error": "missing key: reload the page"})
            return
        if path == "/api/status":
            try:
                self._json(HTTPStatus.OK, self.app.status())
            except Exception as exc:  # show the problem on the page instead of a blank screen
                self._json(
                    HTTPStatus.INTERNAL_SERVER_ERROR, {"error": f"{type(exc).__name__}: {exc}"}
                )
            return
        if path.startswith("/api/job/"):
            job = self.app.jobs.get(path.rsplit("/", 1)[-1])
            if job is None:
                self._json(HTTPStatus.NOT_FOUND, {"error": "no such job"})
            else:
                self._json(HTTPStatus.OK, job.view())
            return
        self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})

    def do_POST(self) -> None:
        if not (self._host_ok() and self._origin_ok() and self._key_ok()):
            self._json(HTTPStatus.FORBIDDEN, {"error": "refused: not from this app's page"})
            return
        if self.path != "/api/action":
            self._json(HTTPStatus.NOT_FOUND, {"error": "not found"})
            return
        try:
            length = min(int(self.headers.get("Content-Length", "0")), 64_000)
            body = json.loads(self.rfile.read(length) or b"{}")
            if not isinstance(body, dict):
                raise ValueError("body must be an object")
        except ValueError:
            self._json(HTTPStatus.BAD_REQUEST, {"error": "bad request"})
            return
        try:
            status, data = self.app.act(body)
        except Exception as exc:
            status, data = (
                HTTPStatus.INTERNAL_SERVER_ERROR,
                {"error": f"{type(exc).__name__}: {exc}"},
            )
        self._json(status, data)


def make_server(app: App, port: int) -> ThreadingHTTPServer:
    """A server on 127.0.0.1 only. ``port`` 0 picks a free port (tests)."""
    handler = type("BoundHandler", (Handler,), {"app": app})
    server = ThreadingHTTPServer(("127.0.0.1", port), handler)
    server.daemon_threads = True
    app.port = server.server_address[1]
    app.stop_server = server.shutdown
    return server


def _running_here(port: int, folder: Path) -> bool:
    """True if this folder's app already runs on ``port`` (then just open the browser)."""
    try:
        direct = urllib.request.build_opener(urllib.request.ProxyHandler({}))  # never via a proxy
        with direct.open(f"http://127.0.0.1:{port}/api/ping", timeout=1) as reply:
            data = json.loads(reply.read())
    except Exception:
        return False
    return bool(data.get("app") == APP and data.get("folder") == str(folder))


def serve(config: str, *, port: int = DEFAULT_PORT, open_browser: bool = True) -> int:
    from quantagents.cli import main  # late import: cli imports this module

    folder = Path.cwd().resolve()
    for candidate in range(port, port + 20):
        if _running_here(candidate, folder):
            url = f"http://127.0.0.1:{candidate}/"
            print(f"QuantAgents is already running for this folder: {url}")
            if open_browser:
                webbrowser.open(url)
            return 0
        app = App(config=config, folder=folder, run=main)
        try:
            server = make_server(app, candidate)
        except OSError:
            continue  # that port is used by something else
        url = f"http://127.0.0.1:{app.port}/"
        print(
            f"\nQuantAgents is running at {url}\n"
            "It is only reachable from this computer.\n"
            "Keep this window open while you use it; close it (or press Ctrl+C) to stop the app.\n"
            "The automatic daily run does not need this window.\n"
        )
        if open_browser:
            threading.Timer(0.5, webbrowser.open, args=(url,)).start()
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            pass
        finally:
            server.server_close()
        print("QuantAgents stopped.")
        return 0
    print(f"No free port between {port} and {port + 19}. Close other programs and try again.")
    return 1


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser("app", help="the local web app in your browser (what QuantAgents.bat opens)")
    p.add_argument("--port", type=int, default=DEFAULT_PORT)
    p.add_argument("--no-browser", action="store_true", help="do not open the browser")

    def run(args: argparse.Namespace) -> int:
        return serve(
            args.config or "config/default.yaml", port=args.port, open_browser=not args.no_browser
        )

    p.set_defaults(func=run)
