#!/usr/bin/env python3
"""Entry point for the packaged program (START_TRADING_AI.exe): Jarvus is a website on this computer.

Double-click: it starts quietly (no app window) and opens http://127.0.0.1:8787 in the browser once it answers. Shut
it down from the website (Shut down, top right). What it has to say goes to logs/jarvus.log; the few things that need
the owner (an older copy holds the address, it cannot start) appear as small Windows message boxes. Started from a
console (python desktop.py), the same messages print there instead. A second launch shows the copy already running
instead of failing on the port, and offers to close an older copy that holds it (see engine/launcher.py).
"""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback

if getattr(sys, "frozen", False):
    sys.path.insert(0, getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable))))
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

WINDOWLESS = sys.stdout is None                          # the packaged website build has no console window
DIALOGS = os.environ.get("JARVUS_NO_DIALOGS") != "1"     # tests switch the message boxes off


def _box(msg: str, title: str, flags: int) -> int:
    """A Windows message box (0 when there is none to show)."""
    if not (WINDOWLESS and DIALOGS and sys.platform == "win32"):
        return 0
    try:
        import ctypes
        return ctypes.windll.user32.MessageBoxW(None, msg, title, flags | 0x00010000 | 0x00040000)  # foreground, on top
    except Exception:                                    # noqa: BLE001
        return 0


def tell(msg: str, error: bool = False) -> None:
    print(msg, flush=True)
    _box(msg.strip(), "Jarvus", 0x10 if error else 0x40)  # error / information icon


def ask(msg: str) -> bool:
    """Yes or no from the owner: a message box without a console, Enter / close the window with one."""
    print(msg, flush=True)
    if WINDOWLESS:
        return _box(msg.strip(), "Jarvus", 0x04 | 0x20) == 6   # Yes / No with a question icon; 6 = Yes
    try:
        input("\n  Press Enter for yes, or close this window for no. ")
        return True
    except (EOFError, KeyboardInterrupt):
        return False


def hold(msg: str = "") -> None:
    """A fatal message: shown, then (with a console) the window waits so it can be read."""
    if msg:
        tell(msg, error=True)
    if WINDOWLESS:
        return
    try:
        input("\n  Press Enter to close this window. ")
    except (EOFError, KeyboardInterrupt):
        pass


def _log_to_file(folder: str) -> None:
    """Without a console, everything printed goes to logs/jarvus.log beside the program (kept under ~2 MB)."""
    try:
        os.makedirs(folder, exist_ok=True)
        path = os.path.join(folder, "jarvus.log")
        if os.path.exists(path) and os.path.getsize(path) > 2_000_000:
            os.replace(path, path + ".old")
        sys.stdout = sys.stderr = open(path, "a", encoding="utf-8", buffering=1)
    except OSError:
        pass


def _already_running(launcher, config, who, background: bool) -> int:
    """Another Jarvus answers on the port. Same version: show it. Older copy: offer to close it. -> exit code, or
    -1 to go on starting this copy."""
    url = f"http://{config.HOST}:{config.PORT}"
    if who["version"] == config.VERSION:
        if background:
            return 0                                     # started twice at sign-in: the first copy carries on
        print(f"\n  Jarvus is already running. Opening it in your browser: {url}", flush=True)
        launcher.wait_ready(config.PORT, 60)
        if not launcher.open_browser(url):
            tell(f"Jarvus is already running. Open {url} in your browser.")
        elif not WINDOWLESS:
            time.sleep(6)
        return 0
    if background:
        return 0
    pids = {who["pid"]} if who.get("pid") else launcher.listening_pids(config.PORT)
    old = ("An OLDER copy of Jarvus is running on this computer (maybe in the background, because it was set to "
           "start with Windows). It holds the address this version needs, and it has no ULTRON.")
    if not pids:
        hold(f"\n  {old}\n\n  Close it (Task Manager -> START_TRADING_AI -> End task), then start this one again.")
        return 1
    if not ask(f"\n  {old}\n\n  Close the old copy and start this one? Its paper trades stay saved in its own folder."):
        return 1
    launcher.stop_pids(pids)
    for _ in range(40):
        if not launcher.listening(config.PORT):
            print("  The old copy is closed.", flush=True)
            return -1
        time.sleep(0.5)
    hold("\n  The old copy did not close. End it in Task Manager (START_TRADING_AI), then start this one again.")
    return 1


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "selftest":
        if WINDOWLESS:                                   # no console: the report goes to a file next to the program
            path = os.path.join(os.path.dirname(os.path.abspath(sys.executable)), "selftest-report.txt")
            sys.stdout = sys.stderr = open(path, "w", encoding="utf-8", buffering=1)
        import selftest
        code = selftest.main()
        if WINDOWLESS:
            tell("Every check passed." if code == 0 else "Some checks failed: see selftest-report.txt next to the "
                 "program.", error=code != 0)
        else:
            hold()
        return code
    background = "--background" in args                  # started with Windows: no browser, the AI just trades
    browser = not background and "--no-browser" not in args
    try:
        import config
        if WINDOWLESS:
            _log_to_file(config.LOG_DIR)
        import server
        from engine import launcher
    except Exception:                                    # noqa: BLE001
        traceback.print_exc()
        hold(f"Jarvus could not start.\n\n{traceback.format_exc(limit=1).strip()[-600:]}")
        return 1
    os.makedirs(config.DATA_DIR, exist_ok=True)
    who = launcher.probe(config.PORT)
    if who and who["jarvus"]:
        code = _already_running(launcher, config, who, background)
        if code >= 0:
            return code
    elif who:                                            # another program has the port: use the next free one
        old = config.PORT
        config.PORT = launcher.free_port(old + 1)
        print(f"\n  Another program is using port {old}; Jarvus uses port {config.PORT} instead.", flush=True)
    url = f"http://{config.HOST}:{config.PORT}"
    print(f"\n  {time.strftime('%Y-%m-%d %H:%M:%S')}  JARVUS + ULTRON starting: {url}"
          f"{' (in the background, no browser)' if background else ''}")
    print("  The bots trade PAPER (simulated) money by themselves. REAL MONEY is OFF until you connect a live account,")
    print("  authorise it with caps (Connections page) and type START LIVE for each live bot.")
    print("  Stop Jarvus with Shut down (top right of the website)" + ("." if WINDOWLESS else " or Ctrl-C here."))
    print(f"  Your data: {config.DATA_DIR}\n  Educational research tool, not financial advice.\n", flush=True)
    if launcher.inside_temp(config.BASE_DIR) and not background:
        tell("Jarvus is running from a TEMPORARY folder (opened straight from the zip?). Windows may delete it, with "
             "your paper trades and settings.\n\nShut it down (top right of the website), right-click the zip -> "
             "Extract All..., and start START_TRADING_AI.exe from the extracted folder.", error=True)
    if not background:
        try:
            from engine import startup
            if startup.adopt():
                print("  Start with Windows was set for another copy of Jarvus: it now starts this one.", flush=True)
        except Exception:                                # noqa: BLE001 - optional convenience
            pass
    if sys.platform == "win32":
        launcher.write_shortcut(config.BASE_DIR, url)    # "Open Jarvus" next to the program, for later

    def open_when_ready():
        port = config.PORT
        if not launcher.wait_ready(port, 180):
            tell(f"Jarvus is taking long to start. When it is ready, open {url} in your browser.")
            return
        if launcher.open_browser(url):
            print(f"  Opened {url} in your browser. Closed the tab? Double-click 'Open Jarvus' next to the program.",
                  flush=True)
        else:
            tell(f"Jarvus is running. Open {url} in your browser.")

    if browser:
        threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        server.serve()
        print(f"  {time.strftime('%Y-%m-%d %H:%M:%S')}  Jarvus shut down.", flush=True)
    except KeyboardInterrupt:
        print("\n  Stopped.\n")
    except OSError as exc:
        if getattr(exc, "errno", None) in (13, 48, 98, 10013, 10048) or getattr(exc, "winerror", None) in (10013, 10048):
            hold(f"Something else is already using port {config.PORT} (is Jarvus already open?). Close the other "
                 f"Jarvus, or set JARVUS_PORT=8899 and start Jarvus again.")
            return 1
        traceback.print_exc()
        hold(f"Jarvus stopped with a network error: {exc}")
        return 1
    except Exception as exc:                             # noqa: BLE001
        traceback.print_exc()
        hold(f"Jarvus stopped unexpectedly: {type(exc).__name__}: {exc}\n\nDetails: {config.LOG_DIR}\\jarvus.log")
        return 1
    return 0


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()     # lets the packaged exe start the bot fleet process
    sys.exit(main())
