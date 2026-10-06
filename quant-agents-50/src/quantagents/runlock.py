"""One run at a time: a scheduled run and a menu click must never overlap.

Two overlapping real-money runs would each see the same gap to the target and both buy it. A
lock file, created only if it does not exist yet, stops the second run. A lock older than an
hour is left over from a crash and is taken over: any order that crashed run left behind is
settled by the next run before it trades (``execution/live.py``).
"""

from __future__ import annotations

import os
import time
from datetime import UTC, datetime
from pathlib import Path

STALE_AFTER_SECONDS = 3600.0


class RunLock:
    def __init__(self, path: Path, stale_after: float = STALE_AFTER_SECONDS) -> None:
        self.path = path
        self.stale_after = stale_after
        self.held = False

    def _create(self) -> bool:
        try:
            fd = os.open(self.path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        except FileExistsError:
            return False
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            handle.write(
                f"pid {os.getpid()} since {datetime.now(UTC).isoformat(timespec='seconds')}\n"
            )
        return True

    def acquire(self) -> bool:
        """True if this run now holds the lock; False if another run is still going."""
        self.path.parent.mkdir(parents=True, exist_ok=True)
        if not self._create():
            try:
                age = time.time() - self.path.stat().st_mtime
            except OSError:
                age = 0.0
            if age < self.stale_after:
                return False
            self.path.unlink(missing_ok=True)  # left by a crash
            if not self._create():
                return False
        self.held = True
        return True

    def release(self) -> None:
        if self.held:
            self.path.unlink(missing_ok=True)
            self.held = False
