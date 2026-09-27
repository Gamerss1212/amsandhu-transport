#!/usr/bin/env python3
"""Entry point for the packaged build (the .exe or the Mac/Linux binary).

Differs from run.py only in what it does around the server: it opens a browser,
explains itself in plain language, and refuses to vanish silently if something
fails. A double-clicked window that closes instantly is the worst possible error
message, so anything fatal is printed and the window waits for a keypress.
"""

from __future__ import annotations

import os
import sys
import threading
import time
import traceback
import webbrowser

if getattr(sys, "frozen", False):
    sys.path.insert(0, getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(sys.executable))))
else:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def hold(msg: str = "") -> None:
    """Keep a double-clicked console window open long enough to read."""
    if msg:
        print(msg)
    try:
        input("\n  Press Enter to close this window. ")
    except (EOFError, KeyboardInterrupt):
        pass


def main() -> int:
    try:
        import config
        from engine import automation, portfolio, store
        import server
    except Exception:                                    # noqa: BLE001
        traceback.print_exc()
        hold("\n  Jarvus could not start: the error above says why.")
        return 1

    os.makedirs(config.DATA_DIR, exist_ok=True)
    url = f"http://{config.HOST}:{config.PORT}"

    print()
    print("  " + "=" * 60)
    print("   JARVUS TERMINAL")
    print("  " + "=" * 60)
    print(f"   Opening {url} in your browser.")
    print("   Keep this window open. Closing it stops Jarvus and the bots.")
    print()
    print("   AUTOPILOT: the seven Jarvus bots and the 250-bot fleet start by")
    print("   themselves and decide everything on their own (what to trade,")
    print("   how much, when to get out), with practice money only. They")
    print("   restart by themselves; only the Stop buttons turn them off.")
    print()
    print(f"   Your data is saved in: {config.DATA_DIR}")
    print("   Drop your own strategy .py files in a 'strategies' folder")
    print("   next to this program and they load on the next start.")
    print()
    print("   Educational research tool, not financial advice.")
    print("  " + "=" * 60)
    print()

    def open_later():
        time.sleep(1.6)                                  # let the port bind first
        try:
            webbrowser.open(url)
        except Exception:                                # noqa: BLE001 - headless is fine
            pass

    threading.Thread(target=open_later, daemon=True).start()

    try:
        # server.serve() does this setup and reports what it loaded, so do not
        # duplicate the announcement here.
        store.conn()
        portfolio.ensure_default()
        automation.seed_default_rules()
        server.serve()
    except KeyboardInterrupt:
        print("\n  Stopped.\n")
    except OSError as exc:
        if getattr(exc, "errno", None) in (48, 98, 10048):
            hold(f"\n  Something is already using port {config.PORT}.\n"
                 f"  Either close the other Jarvus window, or set a different port:\n"
                 f"      set JARVUS_PORT=8899   (Windows)\n"
                 f"      export JARVUS_PORT=8899  (Mac/Linux)")
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
    multiprocessing.freeze_support()     # lets the packaged exe start the research process
    sys.exit(main())
