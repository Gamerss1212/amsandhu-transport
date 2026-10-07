"""Switch real money on or off from the app: one explicit step by the owner (Phase 8).

Before, switching on meant editing three files by hand. Now the owner does it on the page:
1. ``save_keys``: the Kraken key and secret go into ``.env`` (never shown again, never printed).
2. ``switch_on``: the owner types their name, a budget and the approval phrase. Only then
   are the live settings written to the config, the phrase to ``.env`` and the dated
   approval row to ``docs/STATUS.md``.
3. ``switch_off``: back to paper in one click (always allowed; it only lowers risk).

Every gate in ``live.py`` still applies at order time (Kraken crypto only, a fresh paper
decision that A49 did not halt, the kill switch armed, reconciliation with the exchange).
The app cannot switch on without the owner's typed phrase: nothing here runs by itself.
"""

from __future__ import annotations

import os
import re
from datetime import date
from pathlib import Path
from typing import Any

from quantagents import envfile
from quantagents.config import LIVE_APPROVAL_ENV, LIVE_APPROVAL_TOKEN, load_config
from quantagents.execution.live import KEY_ENV, SECRET_ENV, Venue, venue
from quantagents.settings_file import read_raw, update_config

MAX_BUDGET = 1000.0  # micro-live (Phase 8); a bigger budget is an edit by hand, on purpose
NAME = re.compile(r"^[A-Za-z][A-Za-z .'\-]{1,59}$")
KEY = re.compile(r"^[A-Za-z0-9+/=_\-.:]{8,512}$")
APPROVALS = "## Human approvals"


def keys_saved() -> bool:
    return bool(os.environ.get(KEY_ENV) and os.environ.get(SECRET_ENV))


def save_keys(env_path: Path, key: str, secret: str) -> str:
    """Store the exchange keys in ``.env``. The values are never returned or printed."""
    key, secret = key.strip(), secret.strip()
    if not (KEY.match(key) and KEY.match(secret)):
        raise ValueError(
            "those do not look like Kraken API keys (copy them again from Kraken, without spaces)"
        )
    envfile.update(env_path, {KEY_ENV: key, SECRET_ENV: secret})
    os.environ[KEY_ENV], os.environ[SECRET_ENV] = key, secret
    return "Keys saved in .env in this folder. They are hidden from now on."


def add_approval_row(status_file: Path, day: date, name: str) -> None:
    """Add the owner's dated row to the Human approvals table in ``docs/STATUS.md``."""
    row = f"| {day.isoformat()} | Approve Phase 8 micro-live | {name} |"
    text = status_file.read_text(encoding="utf-8") if status_file.exists() else ""
    lines = text.splitlines()
    if APPROVALS not in lines:
        lines += ["", APPROVALS, "", "| Date | Decision | Owner |", "|---|---|---|", row]
    else:
        i = lines.index(APPROVALS) + 1
        while i < len(lines) and not lines[i].startswith("|"):
            i += 1
        last = i
        while last < len(lines) and lines[last].startswith("|"):
            if lines[last].startswith("| (none yet)"):
                lines[last] = row
                break
            last += 1
        else:
            lines.insert(last, row)
    status_file.parent.mkdir(parents=True, exist_ok=True)
    status_file.write_text("\n".join(lines) + "\n", encoding="utf-8")


def switch_on(
    *,
    config: Path,
    env_path: Path,
    status_file: Path,
    name: str,
    budget: Any,
    phrase: str,
    today: date,
) -> list[str]:
    """Write the owner's approval. Every check happens before any file is changed."""
    if phrase.strip() != LIVE_APPROVAL_TOKEN:
        raise ValueError(f"type the approval phrase exactly: {LIVE_APPROVAL_TOKEN}")
    name = " ".join(name.split())
    if not NAME.match(name):
        raise ValueError("type your name (letters and spaces)")
    try:
        amount = float(budget)
    except (TypeError, ValueError):
        raise ValueError("the budget must be a number, for example 100") from None
    if not 0 < amount <= MAX_BUDGET:
        raise ValueError(
            f"the budget must be above 0 and at most {MAX_BUDGET:,.0f} (start small; Phase 8 is "
            "a micro-size test)"
        )
    if not keys_saved():
        raise ValueError("save your Kraken keys first (step 1)")
    where = venue(load_config(config if config.exists() else None).universe.symbols)
    if not isinstance(where, Venue):
        raise ValueError(f"this folder cannot trade for real: {where}")

    def change(raw: dict[str, Any]) -> None:
        system = dict(raw.get("system") or {})
        system.update(execution_mode="live", autonomy_level=3, live_trading_approved=True)
        raw["system"] = system
        raw["live"] = {**dict(raw.get("live") or {}), "budget": amount}

    before = os.environ.get(LIVE_APPROVAL_ENV)
    os.environ[LIVE_APPROVAL_ENV] = LIVE_APPROVAL_TOKEN  # the config needs it to load
    try:
        update_config(config, change)
    except Exception:
        if before is None:
            os.environ.pop(LIVE_APPROVAL_ENV, None)
        else:
            os.environ[LIVE_APPROVAL_ENV] = before
        raise
    envfile.update(env_path, {LIVE_APPROVAL_ENV: LIVE_APPROVAL_TOKEN})
    add_approval_row(status_file, today, name)
    return [
        f"Real money is switched ON by {name}: budget {amount:,.2f} {where.quote} on {where.exchange}.",
        "From the next daily run, the paper portfolio is copied to Kraken. Press 'Preview real "
        "orders' now to see what it would do. The red STOP button stops everything.",
    ]


def switch_off(*, config: Path, env_path: Path) -> list[str]:
    """Back to paper: the live settings are removed and the phrase is taken out of ``.env``."""

    def change(raw: dict[str, Any]) -> None:
        system = {
            k: v
            for k, v in dict(raw.get("system") or {}).items()
            if k not in ("execution_mode", "autonomy_level", "live_trading_approved")
        }
        if system:
            raw["system"] = system
        else:
            raw.pop("system", None)

    if config.exists() or read_raw(config):
        update_config(config, change)
    envfile.update(env_path, {LIVE_APPROVAL_ENV: None})
    os.environ.pop(LIVE_APPROVAL_ENV, None)
    return [
        "Real money is switched OFF. The program is back to paper trading.",
        "Coins the mirror bought stay on Kraken as they are; sell them on the Kraken website if "
        "you want cash. Your keys stay saved (delete the key on Kraken to stop them working).",
    ]
