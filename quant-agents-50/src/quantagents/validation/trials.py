"""Trial registry (spec section 63): every backtest run is a row in ``docs/research/trials.md``.

A44 uses the count: the more variants of a family have ever been tried on real data, the higher
the bar (DSR, PBO). Re-running the same variant does not add a trial; a new variant always does.
Runs on synthetic data are logged too, but never counted as evidence or as real-data trials.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import date
from pathlib import Path

TRIALS_FILE = Path("docs/research/trials.md")
HEADER = """# Trial log

Every backtest variant ever run counts as a trial (spec section 63). Add one row per run.

| Date | Family | Variant and parameters | Data (file + hash) | Sharpe | Verdict |
|------|--------|------------------------|--------------------|--------|---------|
"""
SYNTHETIC = "synthetic"


def data_id(path: str | None, seed: int) -> str:
    """How a trial names its data: the CSV's name and content hash, or the synthetic seed."""
    if not path:
        return f"{SYNTHETIC} (seed {seed})"
    digest = hashlib.sha256(Path(path).read_bytes()).hexdigest()[:12]
    return f"{Path(path).name} {digest}"


@dataclass(frozen=True)
class Trial:
    day: date
    family: str
    variant: str
    detail: str
    data: str
    sharpe: float
    verdict: str

    def row(self) -> str:
        cells = (
            self.day.isoformat(),
            self.family,
            f"{self.variant} ({self.detail})" if self.detail else self.variant,
            self.data,
            f"{self.sharpe:.2f}",
            self.verdict,
        )
        return "| " + " | ".join(c.replace("|", "/") for c in cells) + " |"


def append_trials(trials: list[Trial], path: Path = TRIALS_FILE) -> None:
    if not trials:
        return
    if not path.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(HEADER, encoding="utf-8")
    text = path.read_text(encoding="utf-8")
    sep = "" if text.endswith("\n") else "\n"
    path.write_text(text + sep + "\n".join(t.row() for t in trials) + "\n", encoding="utf-8")


def logged_variants(family: str, path: Path = TRIALS_FILE) -> set[str]:
    """Distinct variants of ``family`` ever run on real (non-synthetic) data."""
    if not path.exists():
        return set()
    found: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) < 6 or cells[1] != family or not cells[0][:1].isdigit():
            continue
        if cells[3].startswith(SYNTHETIC):
            continue
        found.add(cells[2].split(" ", 1)[0])
    return found


def trial_count(family: str, variants: list[str], path: Path = TRIALS_FILE) -> int:
    """Trials to charge A44 with: this run's variants plus every other one ever tried."""
    return len(logged_variants(family, path) | set(variants))
