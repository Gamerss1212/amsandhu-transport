"""What the packaged app does before it serves: find out what already holds the port, open the browser only once the
app answers, and keep a shortcut to the page next to the program.

    probe(port)          None when nothing listens; else {"jarvus": bool, "version": str or None, "pid": int or None}
                         (version None: an older Jarvus, from before /api/version existed)
    wait_ready(port)     True once the app answers (it binds the port first, then loads; the page needs both)
    open_browser(url)    the default browser, with Windows fallbacks; False when none could be started
    free_port(port)      the first free port from `port` on
    listening_pids(port) Windows: the processes listening on the port (to close an older copy, when the owner asks)
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
import webbrowser
from typing import Optional, Set

HOST = "127.0.0.1"
NO_WINDOW = 0x08000000                                  # CREATE_NO_WINDOW: no console flash for helper commands


def _get(url: str, timeout: float = 2.0):
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers={"User-Agent": "jarvus-launcher"}),
                                    timeout=timeout) as r:
            return r.status, r.read(300_000)
    except urllib.error.HTTPError as e:
        return e.code, b""
    except (OSError, ValueError):
        return None


def listening(port: int, host: str = HOST) -> bool:
    try:
        with socket.create_connection((host, port), timeout=1.0):
            return True
    except OSError:
        return False


def probe(port: int, host: str = HOST) -> Optional[dict]:
    if not listening(port, host):
        return None
    r = _get(f"http://{host}:{port}/api/version")
    if r and r[0] == 200:
        try:
            d = json.loads(r[1])
        except ValueError:
            d = {}
        if isinstance(d, dict) and d.get("app") == "jarvus":
            return {"jarvus": True, "version": d.get("version"), "pid": d.get("pid"), "ready": bool(d.get("ready"))}
    r = _get(f"http://{host}:{port}/")
    if r and r[0] == 200 and b"/js/app.js" in r[1]:
        return {"jarvus": True, "version": None, "pid": None, "ready": True}
    return {"jarvus": False, "version": None, "pid": None, "ready": False}


def wait_ready(port: int, timeout: float = 180.0, host: str = HOST, tick=None) -> bool:
    t0 = time.time()
    while time.time() - t0 < timeout:
        p = probe(port, host)
        if p and p["jarvus"] and p["ready"]:
            return True
        if tick:
            tick(time.time() - t0)
        time.sleep(0.4)
    return False


def open_browser(url: str) -> bool:
    if sys.platform == "win32":
        try:
            os.startfile(url)                           # the default browser, as a double-click on a link would
            return True
        except OSError:
            pass
        try:
            subprocess.Popen(["cmd", "/c", "start", "", url], creationflags=NO_WINDOW)
            return True
        except OSError:
            pass
    try:
        return bool(webbrowser.open(url))
    except Exception:                                   # noqa: BLE001 - no browser on this machine
        return False


def free_port(port: int, host: str = HOST, tries: int = 40) -> int:
    for p in range(port, port + tries):
        if listening(p, host):
            continue
        s = socket.socket()
        try:
            s.bind((host, p))
            return p
        except OSError:
            continue
        finally:
            s.close()
    raise OSError(f"no free port between {port} and {port + tries - 1}")


def listening_pids(port: int) -> Set[int]:
    """Windows only: process ids listening on 127.0.0.1/0.0.0.0:port, from netstat (an empty set elsewhere)."""
    if sys.platform != "win32":
        return set()
    try:
        out = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=20,
                             creationflags=NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return set()
    return parse_netstat(out, port) - {os.getpid()}


def parse_netstat(out: str, port: int) -> Set[int]:
    pids = set()
    for line in out.splitlines():
        parts = line.split()
        # Proto  Local Address  Foreign Address  State  PID   (a listening socket's foreign address is 0.0.0.0:0)
        if len(parts) >= 5 and parts[0].upper() == "TCP" and parts[1].endswith(f":{port}") \
                and parts[2] in ("0.0.0.0:0", "[::]:0") and parts[-1].isdigit():
            pids.add(int(parts[-1]))
    return pids


def stop_pids(pids: Set[int]) -> None:
    for pid in pids:
        try:
            subprocess.run(["taskkill", "/PID", str(pid), "/T", "/F"], capture_output=True, timeout=20,
                           creationflags=NO_WINDOW)
        except (OSError, subprocess.SubprocessError):
            pass


def inside_temp(folder: str, temp: Optional[str] = None) -> bool:
    """True when the program runs from the temporary folder (Windows Explorer runs an exe opened inside a zip from
    %TEMP%\\Temp1_<name>.zip\\...; that folder, and the data saved next to the program, can be deleted)."""
    temp = temp if temp is not None else os.environ.get("TEMP") or os.environ.get("TMP") or ""
    if not temp or not folder:
        return False
    f, t = os.path.normcase(os.path.abspath(folder)), os.path.normcase(os.path.abspath(temp))
    return f == t or f.startswith(t.rstrip("\\/") + os.sep)


def write_shortcut(folder: str, url: str, name: str = "Open Jarvus.url") -> Optional[str]:
    """A double-clickable link to the page next to the program (Windows .url file)."""
    path = os.path.join(folder, name)
    try:
        with open(path, "w", encoding="utf-8") as fh:
            fh.write(f"[InternetShortcut]\nURL={url}/\n")
        return path
    except OSError:
        return None
