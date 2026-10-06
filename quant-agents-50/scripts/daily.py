#!/usr/bin/env python3
"""Standalone daily run for the task scheduler: the same as `python -m quantagents daily`.

Run from the project folder after the close, for example:

    python scripts/daily.py --config config/my_universe.yaml daily --yahoo SPY EFA TLT --out data/prices.csv

Exit code 0 = all steps fine, 1 = a step failed (see runs/daily.log).
"""

from __future__ import annotations

import sys

from quantagents.cli import main

if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
