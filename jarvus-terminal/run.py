#!/usr/bin/env python3
"""Jarvus launcher (from source).

    python3 run.py                 start the app and open it in the browser
    python3 run.py --port 9000     use another port
    python3 run.py --no-browser    do not open a browser
    python3 run.py selftest        check the install

No pip install. Python 3.9+ is the only requirement.
"""

from __future__ import annotations

import argparse
import multiprocessing
import os
import sys
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("cmd", nargs="?", default="serve", choices=["serve", "selftest"])
    ap.add_argument("--port", type=int)
    ap.add_argument("--no-browser", action="store_true")
    a = ap.parse_args()
    if a.cmd == "selftest":
        import selftest
        sys.exit(selftest.main())
    import config
    if a.port:
        config.PORT = a.port
    import server
    if not a.no_browser:
        try:
            webbrowser.open(f"http://{config.HOST}:{config.PORT}")
        except Exception:                                    # noqa: BLE001 - headless machines have no browser
            pass
    server.serve()


if __name__ == "__main__":
    multiprocessing.freeze_support()
    main()
