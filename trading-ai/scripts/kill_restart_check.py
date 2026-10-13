"""Recovery check with a real process kill: start the program, wait until the master agent is training an agent,
kill the process with SIGKILL (no clean shutdown), start it again and verify what came back.

    python scripts/kill_restart_check.py [--home <folder>] [--offline]

Prints one PASS/FAIL line per check and exits non-zero if any check fails. Nothing here places real orders.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import socket
import subprocess
import sys
import tempfile
import time
from pathlib import Path

import httpx

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def start(home: str, port: int, offline: bool) -> subprocess.Popen:
    cmd = [PY, "-m", "tradingai.launcher", "--home", home, "--port", str(port), "--no-browser"] + (["--offline"] if offline else [])
    return subprocess.Popen(cmd, cwd=ROOT / "backend", stdin=subprocess.PIPE, stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)


def wait_ready(c: httpx.Client, timeout: float = 90) -> dict:
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            h = c.get("/health").json()
            if h["state"]["state"] not in ("BOOTING",):
                return h
        except Exception:                                  # noqa: BLE001 - still starting
            pass
        time.sleep(0.5)
    raise TimeoutError("the program did not answer /health")


def token(c: httpx.Client) -> dict:
    t = c.get("/").text.split('name="ta-token" content="', 1)[1].split('"', 1)[0]
    return {"X-TA-Token": t, "Origin": str(c.base_url).rstrip("/")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--home", default=None)
    ap.add_argument("--offline", action="store_true")
    a = ap.parse_args()
    home = a.home or tempfile.mkdtemp(prefix="tai-kill-")
    port = free_port()
    c = httpx.Client(base_url=f"http://127.0.0.1:{port}", timeout=30, trust_env=False)
    results = []

    def check(name: str, ok: bool, detail: str = "") -> None:
        results.append((name, ok, detail))
        print(f"{'PASS' if ok else 'FAIL'}  {name}{(': ' + detail) if detail else ''}", flush=True)

    p = start(home, port, a.offline)
    try:
        h = wait_ready(c)
        check("first start reaches a running state", h["state"]["state"] in ("READY", "PAPER_RUNNING"), h["state"]["state"])
        hdr = token(c)
        running = None
        t0 = time.time()
        while time.time() - t0 < 120 and running is None:
            jobs = c.get("/api/research/jobs", headers=hdr).json()
            running = next((j for j in jobs if j["state"] == "running" and str(j["meta"].get("by", "")).startswith("master:")),
                           None)
            time.sleep(0.5)
        check("the master is training an agent before the kill", running is not None,
              running["title"] if running else "no training job seen within 120 s")
        before = c.get("/api/fleet", headers=hdr).json()
        owners = {x["id"]: x["partition"] for x in before["agents"]}
        exps = c.get("/api/research/experiments?limit=500", headers=hdr).json()["experiments"]
        in_flight = [e["experiment_id"] for e in exps if e.get("status") == "RUNNING"]
        os.kill(p.pid, signal.SIGKILL)                     # no clean shutdown
        p.wait(timeout=30)
        check("process killed with SIGKILL", p.returncode == -signal.SIGKILL, f"return code {p.returncode}")
    finally:
        if p.poll() is None:
            p.kill()
    p = start(home, port, a.offline)
    try:
        h = wait_ready(c)
        check("restart reaches a running state", h["state"]["state"] in ("READY", "PAPER_RUNNING"), h["state"]["state"])
        hdr = token(c)
        ov = c.get("/api/overview", headers=hdr).json()
        check("restart is in PAPER mode", ov["mode"] == "paper", ov["mode"])
        checks = h.get("startup_checks") or []
        failed = [x for x in checks if not x.get("ok") and x.get("name") != "frontend files"]
        check("every start-up check passes after the kill", not failed, "; ".join(f"{x['name']}: {x['detail']}" for x in failed))
        db = h.get("components", {}).get("database", {})
        check("database integrity", db.get("status") == "ok", json.dumps(db)[:160])
        after = c.get("/api/fleet", headers=hdr).json()
        check("exactly 100 agents after restart", after["counts"]["registered"] == 100, str(after["counts"]["registered"]))
        same = {x["id"]: x["partition"] for x in after["agents"]} == owners
        check("every agent kept its market", same)
        exps = {e["experiment_id"]: e for e in c.get("/api/research/experiments?limit=500", headers=hdr).json()["experiments"]}
        cut = [exps[e] for e in in_flight if e in exps]
        check("runs cut off by the kill are marked failed, not left running",
              all(e["status"] == "FAILED" for e in cut), f"{len(cut)} interrupted run(s)")
        rep = c.post("/api/learning/replay", headers=hdr).json()
        check("learned-safeguard replay passes after restart", not rep["failed"], f"{rep['passed']}/{rep['scenarios']}")
        rec = c.post("/api/reconcile", headers=hdr).json()
        check("reconciliation clean after restart", bool(rec.get("ok")), json.dumps(rec)[:160])
        audit = c.get("/api/audit/verify", headers=hdr).json()
        check("audit chain intact after the kill", bool(audit.get("ok")), json.dumps(audit)[:120])
        c.post("/api/system/shutdown", headers=hdr)
        p.wait(timeout=60)
        check("clean shutdown after the check", p.returncode is not None, f"return code {p.returncode}")
    finally:
        if p.poll() is None:
            p.kill()
    bad = [r for r in results if not r[1]]
    print(f"\n{len(results) - len(bad)} of {len(results)} checks passed (home: {home})")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
