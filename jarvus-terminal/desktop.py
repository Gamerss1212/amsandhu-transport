#!/usr/bin/env python3
"""Entry point for the packaged app (JarvusTerminal.exe).

Opens the browser, explains itself in plain words, and never vanishes silently: anything fatal is
printed and the window waits for a key press.
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
    if msg:
        print(msg)
    try:
        input("\n  Press Enter to close this window. ")
    except (EOFError, KeyboardInterrupt):
        pass


def main() -> int:
    try:
        import config
        import server
    except Exception:                                    # noqa: BLE001
        traceback.print_exc()
        hold("\n  Jarvus could not start: the error above says why.")
        return 1
    os.makedirs(config.DATA_DIR, exist_ok=True)
    url = f"http://{config.HOST}:{config.PORT}"
    print()
    print("  " + "=" * 62)
    print("   JARVUS")
    print("  " + "=" * 62)
    print(f"   Opening {url} in your browser.")
    print("   Keep this window open: closing it stops Jarvus and the bots.")
    print()
    print("   AUTOPILOT: the bots start by themselves and decide everything")
    print("   (what to trade, how much, when to get out) with PAPER money.")
    print("   They restart by themselves; only Stop (Settings) turns them off.")
    print()
    print("   REAL MONEY is OFF. It can only be turned on in the app (Live")
    print("   money page): a tested broker, your limits and a typed")
    print("   acknowledgement.")
    print()
    print(f"   Your data: {config.DATA_DIR}")
    print("   Educational research tool, not financial advice.")
    print("  " + "=" * 62)
    print()

    def open_later():
        time.sleep(1.6)                                  # let the port bind first
        try:
            webbrowser.open(url)
        except Exception:                                # noqa: BLE001
            pass

    threading.Thread(target=open_later, daemon=True).start()
    try:
        server.serve()
    except KeyboardInterrupt:
        print("\n  Stopped.\n")
    except OSError as exc:
        if getattr(exc, "errno", None) in (48, 98, 10048):
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
