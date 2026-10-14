"""Start JARVIS (the voice assistant) together with the Trading AI, so one double-click runs everything.

JARVIS lives in the `jarvis` folder beside START_TRADING_AI.exe and needs Node.js and Claude Code on this computer.
When they are missing the Trading AI runs on its own and says what is missing. JARVIS is only ever started for an
interactive start (not when Windows starts the program at log-in), is never started twice, and is stopped with the
Trading AI. Nothing here can change how the Trading AI trades: JARVIS talks to it through the read and ask tokens only.
"""
from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path
from typing import Callable, Optional

BRIDGE_PORT = 8787                                   # JARVIS's bridge (jarvis/bridge/server.mjs)


def bridge_running(port: int = BRIDGE_PORT) -> bool:
    try:
        with socket.create_connection(("127.0.0.1", port), timeout=0.5):
            return True
    except OSError:
        return False


def status(base: Path, *, which: Callable[[str], Optional[str]] = shutil.which,
           running: Callable[[], bool] = bridge_running) -> dict:
    """What would happen if JARVIS were started now, in words the owner can act on."""
    bat = base / "jarvis" / "START_JARVIS.bat"
    if not bat.exists():
        return {"state": "absent", "note": "JARVIS is not in this folder."}
    if running():
        return {"state": "running", "note": "JARVIS is running."}
    missing = [name for name, exe in (("Node.js", "node"), ("Claude Code", "claude")) if not which(exe)]
    if missing:
        return {"state": "not_installed",
                "note": f"JARVIS needs {' and '.join(missing)} on this computer (see docs/JARVIS.md). "
                        "The trading software works without it."}
    return {"state": "ready", "note": "JARVIS can start."}


def start(base: Path, *, popen: Callable = subprocess.Popen, **kw) -> tuple[dict, Optional[subprocess.Popen]]:
    """Start JARVIS in its own window (minimised once installed). Returns (status, process or None)."""
    st = status(base, **kw)
    if st["state"] != "ready":
        return st, None
    if os.name != "nt":
        return {"state": "off", "note": "JARVIS starts by itself only on Windows."}, None
    folder = base / "jarvis"
    first_run = not (folder / "node_modules").exists()
    info = subprocess.STARTUPINFO()
    info.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    info.wShowWindow = 1 if first_run else 7         # first run: show the install; later: minimised, not focused
    env = dict(os.environ, TA_LAUNCHED="1")
    proc = popen(["cmd.exe", "/c", str(folder / "START_JARVIS.bat")], cwd=str(folder), env=env,
                 creationflags=subprocess.CREATE_NEW_CONSOLE, startupinfo=info)
    note = ("JARVIS is installing (first run, a few minutes); his window opens when ready."
            if first_run else "JARVIS is starting; his window opens in a few seconds.")
    return {"state": "starting", "note": note}, proc


def stop(proc: Optional[subprocess.Popen], *, run: Callable = subprocess.run) -> None:
    """Stop JARVIS and everything it started (his bridge and screen server)."""
    if proc is None or proc.poll() is not None:
        return
    try:
        if os.name == "nt":
            run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True, timeout=10)
        else:
            proc.terminate()
    except (OSError, subprocess.SubprocessError):
        pass
