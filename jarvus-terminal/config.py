#!/usr/bin/env python3
"""Jarvus configuration: where things live and which address the app uses."""

from __future__ import annotations

import os
import sys

# Running from source, everything sits next to this file. Running as the packaged program (START_TRADING_AI.exe), the
# code and the read-only payload live in _internal/ beside the exe, and everything the app writes (data/, logs/) is
# written beside the exe too, so it survives updates of _internal/.
FROZEN = getattr(sys, "frozen", False)
if FROZEN:
    BASE_DIR = os.path.dirname(os.path.abspath(sys.executable))   # beside the .exe
    BUNDLE_DIR = getattr(sys, "_MEIPASS", BASE_DIR)               # read-only payload
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    BUNDLE_DIR = BASE_DIR
DATA_DIR = os.environ.get("JARVUS_DATA") or os.path.join(BASE_DIR, "data")
LOG_DIR = os.environ.get("JARVUS_LOGS") or os.path.join(BASE_DIR, "logs")
EXE_NAME = "START_TRADING_AI.exe"                                 # the one file the owner opens (Windows build)
WEB_DIR = os.path.join(BUNDLE_DIR, "web")

# This computer only: the app controls the bots and receives broker keys, so it never listens on a network.
HOST = "127.0.0.1"
PORT = int(os.environ.get("JARVUS_PORT", "8787"))
# Which build is running: a second launch reads it from /api/version to tell "already open" from "an older copy".
VERSION = "2026.10.04-ultron"

# Resource budgets (environment variables; see .env.example). Research jobs run in separate processes, each with a
# wall-clock and memory limit, so heavy analysis never slows the bots or the page.
def _int(name, default):
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


MAX_FLEETS = _int("JARVUS_MAX_FLEETS", 4)                        # bot engines running at once (one per workspace)
RESEARCH_WORKERS = _int("JARVUS_RESEARCH_WORKERS", 0) or None    # 0 = CPU cores - 1
JOB_TIMEOUT_S = _int("JARVUS_JOB_TIMEOUT_S", 900)                # per research job
JOB_MEMORY_MB = _int("JARVUS_JOB_MEMORY_MB", 1500)               # per research job
