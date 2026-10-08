"""Move an account from an older QuantAgents folder into this fresh one (after an update).

    python -m quantagents import-from C:\\QuantAgents-50-old

It copies the paper account, the real-money ledger, the decision records, the price store,
the settings file and ``.env`` (never printed). Then it engages the kill switch in the OLD
folder: two copies running at once would trade the same account twice, and two real-money
mirrors would both buy on the same exchange account.

Approvals are not copied: a new version needs the owner's own approval row again in
``docs/STATUS.md`` before real money can run.
"""

from __future__ import annotations

import argparse
import shutil
from datetime import UTC, datetime
from pathlib import Path

from quantagents.risk.killswitch import KillSwitch

COPY_DIRS = ("state", "runs", "data")
COPY_FILES = ("config/my_universe.yaml", ".env")
SKIP_SUFFIXES = (".lock", ".tmp")
PROGRAM = "program"


def _has_account(folder: Path) -> bool:
    return (folder / "state" / "paper_account.json").exists() or any(
        (folder / "runs" / "cycles").glob("*.json")
    )


def import_from(old: Path, new: Path) -> list[str]:
    """Copy ``old``'s account into ``new`` and stop ``old``. Returns what to tell the owner."""
    old, new = old.expanduser().resolve(), new.resolve()
    if (old / PROGRAM / "pyproject.toml").is_file():
        old = old / PROGRAM  # a download from 0.10.0 on keeps everything in program/
    if old == new:
        raise ValueError("that is this folder: give the path of the OLDER QuantAgents folder")
    if not old.is_dir():
        raise ValueError(f"{old} is not a folder")
    if not _has_account(old):
        raise ValueError(f"{old} has no QuantAgents account to bring over (no state or runs)")
    moved = KillSwitch(old / "state" / "kill_switch.json").state()
    if moved.engaged and moved.by == "import":
        raise ValueError(
            f"{old} was already brought over once ({moved.reason}). Import from the folder "
            "you use now, so one account never runs in two places."
        )
    if _has_account(new):
        raise ValueError(
            f"{new} already has its own paper account. Import only into a fresh copy, so two "
            "accounts never mix."
        )
    lines = [f"Bringing your account over from {old}:"]
    for name in COPY_DIRS:
        source = old / name
        if not source.is_dir():
            continue
        count = 0
        for path in sorted(source.rglob("*")):
            if not path.is_file() or path.name.endswith(SKIP_SUFFIXES):
                continue
            target = new / path.relative_to(old)
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
            count += 1
        lines.append(f"  {name}/: {count} file(s)")
    for name in COPY_FILES:
        source = old / name
        if source.is_file():
            target = new / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(source, target)
            lines.append(f"  {name}" + (" (contents not shown)" if name == ".env" else ""))
    when = datetime.now(UTC).strftime("%Y-%m-%d")
    KillSwitch(old / "state" / "kill_switch.json").engage(
        f"account moved to {new} on {when}: this old copy must not trade any more", by="import"
    )
    lines += [
        "The OLD folder is now stopped (its kill switch is engaged), so it cannot trade twice.",
        "Approvals were not copied: to use real money here, switch it on again in this "
        "folder's page (Real money box, step 2).",
    ]
    return lines


def add_parser(sub: argparse._SubParsersAction[argparse.ArgumentParser]) -> None:
    p = sub.add_parser(
        "import-from", help="bring your account over from an older QuantAgents folder"
    )
    p.add_argument("folder", help="the older QuantAgents folder")

    def run(args: argparse.Namespace) -> int:
        print("\n".join(import_from(Path(args.folder), Path.cwd())))
        return 0

    p.set_defaults(func=run)
