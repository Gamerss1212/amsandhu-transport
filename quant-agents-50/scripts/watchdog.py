#!/usr/bin/env python3
"""Standalone watchdog for the task scheduler: the same as `python -m quantagents watchdog`.

Run from the project folder, on its own schedule (for example an hour after the daily cycle):

    python scripts/watchdog.py --data data/prices.csv

Exit code 0 = all clear, 1 = a problem was found and the kill switch was engaged.
"""

from __future__ import annotations

import sys

from quantagents.cli import main

if __name__ == "__main__":
    sys.exit(main(["watchdog", *sys.argv[1:]]))
