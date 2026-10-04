#!/usr/bin/env python3
"""Entry point for the packaged app (JarvusTerminal.exe).

Opens the browser once the app answers, explains itself in plain words, and never vanishes silently: anything fatal
is printed and the window waits for a key press. A second launch shows the copy already running instead of failing on
the port, and offers to close an older copy that holds it (see engine/launcher.py).
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


def hold(msg: str = "") -> None:
    if msg:
        print(msg)
    try:
        input("\n  Press Enter to close this window. ")
    except (EOFError, KeyboardInterrupt):
        pass


def _already_running(launcher, config, who, background: bool) -> int:
    """Another Jarvus answers on the port. Same version: show it. Older copy: offer to close it. -> exit code, or
    -1 to go on starting this copy."""
    url = f"http://{config.HOST}:{config.PORT}"
    if who["version"] == config.VERSION:
        if background:
            return 0                                     # started twice at sign-in: the first copy carries on
        print(f"\n  Jarvus is already running. Opening it in your browser: {url}")
        launcher.wait_ready(config.PORT, 60)
        if not launcher.open_browser(url):
            print(f"  Your browser did not open by itself: go to {url}")
        time.sleep(6)
        return 0
    if background:
        return 0
    print("\n  An OLDER copy of Jarvus is running on this computer (in a window, or in the background because")
    print("  it was set to start with Windows). It holds the address this version needs, and it has no ULTRON.")
    pids = {who["pid"]} if who.get("pid") else launcher.listening_pids(config.PORT)
    if not pids:
        hold("\n  Close the other Jarvus (its black window, or Task Manager -> JarvusTerminal -> End task),\n"
             "  then start this one again.")
        return 1
    try:
        input("\n  Press Enter to close the old copy and start this one (its paper trades stay saved in its own\n"
              "  folder), or close this window to keep the old one. ")
    except (EOFError, KeyboardInterrupt):
        return 1
    launcher.stop_pids(pids)
    for _ in range(40):
        if not launcher.listening(config.PORT):
            print("  The old copy is closed.")
            return -1
        time.sleep(0.5)
    hold("\n  The old copy did not close. End it in Task Manager (JarvusTerminal), then start this one again.")
    return 1


def main() -> int:
    args = sys.argv[1:]
    if args and args[0] == "selftest":
        import selftest
        code = selftest.main()
        hold()
        return code
    background = "--background" in args                  # started with Windows: no browser, the AI just trades
    browser = not background and "--no-browser" not in args
    try:
        import config
        import server
        from engine import launcher
    except Exception:                                    # noqa: BLE001
        traceback.print_exc()
        hold("\n  Jarvus could not start: the error above says why.")
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
        print(f"\n  Another program is using port {old}; Jarvus uses port {config.PORT} instead.")
    url = f"http://{config.HOST}:{config.PORT}"
    print()
    print("  " + "=" * 62)
    print("   JARVUS  +  ULTRON BRAIN")
    print("  " + "=" * 62)
    print(f"   {'Running in the background; open' if not browser else 'Opening'} {url}"
          f"{'' if not browser else ' in your browser'}.")
    print("   Keep this window open: closing it stops Jarvus and the bots.")
    print()
    print("   The AI makes all the trades by itself: the bots (46 of them run")
    print("   the ULTRON councils) trade PAPER (simulated) money, the brain")
    print("   sizes and vetoes each trade, exits are automatic and research")
    print("   runs on a schedule. STOP AUTOPILOT on Command pauses new trades.")
    print()
    print("   REAL MONEY is OFF. It needs a connected live account, your")
    print("   separate authorisation (Connections page) with caps, and a")
    print("   typed START LIVE for each live bot.")
    print()
    print(f"   Your data: {config.DATA_DIR}")
    print("   Educational research tool, not financial advice.")
    print("  " + "=" * 62)
    print()
    if not background:
        try:
            from engine import startup
            if startup.adopt():
                print("   Start with Windows was set for another copy of Jarvus: it now starts this one.\n")
        except Exception:                                # noqa: BLE001 - optional convenience
            pass
    if sys.platform == "win32":
        launcher.write_shortcut(config.BASE_DIR, url)    # "Open Jarvus" next to the program, for later

    def open_when_ready():
        port = config.PORT
        if not launcher.wait_ready(port, 180):
            print(f"\n  Jarvus is taking long to start. When it is ready, go to {url}\n", flush=True)
            return
        if launcher.open_browser(url):
            print(f"  Opened in your browser. Closed the tab? Double-click 'Open Jarvus' next to this program,\n"
                  f"  or go to {url}\n", flush=True)
        else:
            print(f"\n  Your browser did not open by itself: go to {url}\n", flush=True)

    if browser:
        threading.Thread(target=open_when_ready, daemon=True).start()
    try:
        server.serve()
    except KeyboardInterrupt:
        print("\n  Stopped.\n")
    except OSError as exc:
        if getattr(exc, "errno", None) in (13, 48, 98, 10013, 10048) or getattr(exc, "winerror", None) in (10013, 10048):
            hold(f"\n  Something is already using port {config.PORT} (is Jarvus already open?).\n"
                 f"  Close the other Jarvus window, or use another port:\n"
                 f"      set JARVUS_PORT=8899   (then start Jarvus again)")
            return 1
        traceback.print_exc()
        hold("\n  Jarvus stopped with a network error.")
        return 1
    except Exception:                                    # noqa: BLE001
        traceback.print_exc()
        hold("\n  Jarvus stopped unexpectedly: the error above says why.")
        return 1
    return 0


if __name__ == "__main__":
    import multiprocessing
    multiprocessing.freeze_support()     # lets the packaged exe start the bot fleet process
    sys.exit(main())
