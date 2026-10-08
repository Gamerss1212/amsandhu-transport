"""Where things live and the few settings that are not risk limits (risk limits live in risk/limits.py).

Running from source, the writable folders sit in the project folder. Running as START_TRADING_AI.exe, the program
lives in _internal/ beside the exe (read-only) and everything the app writes (data/, logs/, exports/) is written
beside the exe, so an update that replaces _internal/ keeps the owner's data.
"""

from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

FROZEN = bool(getattr(sys, "frozen", False))
if FROZEN:
    BASE_DIR = Path(sys.executable).resolve().parent
    BUNDLE_DIR = Path(getattr(sys, "_MEIPASS", BASE_DIR))
else:
    BASE_DIR = Path(__file__).resolve().parents[2]          # trading-ai/
    BUNDLE_DIR = BASE_DIR

HOST = "127.0.0.1"                                          # never 0.0.0.0 unless the owner changes it on purpose
DEFAULT_PORT = 8000


@dataclass
class Paths:
    base: Path
    data: Path = field(init=False)
    logs: Path = field(init=False)
    exports: Path = field(init=False)
    market: Path = field(init=False)
    db: Path = field(init=False)
    duck: Path = field(init=False)
    secrets: Path = field(init=False)
    backups: Path = field(init=False)

    def __post_init__(self) -> None:
        self.data = self.base / "data"
        self.logs = self.base / "logs"
        self.exports = self.base / "exports"
        self.market = self.data / "market"                  # partitioned Parquet: market=/symbol=/tf=/year=
        self.db = self.data / "app.sqlite3"                 # orders, fills, positions, audit, research ledger
        self.duck = self.data / "analytics.duckdb"          # DuckDB catalog over the Parquet files
        self.secrets = self.data / "secrets"
        self.backups = self.data / "backups"

    def ensure(self) -> "Paths":
        for p in (self.data, self.logs, self.exports, self.market, self.secrets, self.backups):
            p.mkdir(parents=True, exist_ok=True)
        return self


def paths(base: str | os.PathLike | None = None) -> Paths:
    root = Path(base or os.environ.get("TRADING_AI_HOME") or BASE_DIR)
    return Paths(root)


def frontend_dir() -> Path:
    """The compiled React app (frontend/dist), bundled into _internal/frontend in the Windows build."""
    for p in (BUNDLE_DIR / "frontend" / "dist", BUNDLE_DIR / "frontend_dist", BASE_DIR / "frontend" / "dist"):
        if (p / "index.html").is_file():
            return p
    return BUNDLE_DIR / "frontend" / "dist"


def resource(*parts: str) -> Path:
    """A read-only file shipped with the program (contract specs, holiday rules ...)."""
    return Path(__file__).resolve().parent.joinpath(*parts)
