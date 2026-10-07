"""Read the owner's ``.env`` file into the environment (spec section 72: secrets stay out of code).

Only the owner writes ``.env``; it is never committed and never put in a release zip. Values
are loaded into ``os.environ`` and are never printed: callers only learn which names were set.
A name that is already in the environment wins over the file.
"""

from __future__ import annotations

import contextlib
import os
from collections.abc import MutableMapping
from pathlib import Path

ENV_FILE = Path(".env")


def parse(text: str) -> dict[str, str]:
    """``NAME=value`` lines; blank lines, ``#`` comments and ``export`` prefixes are fine."""
    out: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, _, value = line.removeprefix("export ").partition("=")
        name, value = name.strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        if name.isidentifier():
            out[name] = value
    return out


def load(path: Path = ENV_FILE, environ: MutableMapping[str, str] | None = None) -> list[str]:
    """Copy ``path``'s non-empty values into the environment. Returns the names set."""
    env = os.environ if environ is None else environ
    try:
        values = parse(path.read_text(encoding="utf-8-sig"))
    except OSError:  # no .env (the normal case for paper trading) or unreadable
        return []
    loaded = [name for name, value in values.items() if value and name not in env]
    for name in loaded:
        env[name] = values[name]
    return loaded


def update(path: Path, changes: dict[str, str | None]) -> None:
    """Set (or, with ``None``, remove) names in ``path``, keeping every other line as it is.

    Used only when the owner saves keys or switches real money on or off in the app. Values
    are written, never read back to the screen. On macOS and Linux the file is made private.
    """
    try:
        lines = path.read_text(encoding="utf-8-sig").splitlines()
    except OSError:
        lines = []
    done: set[str] = set()
    out: list[str] = []
    for raw in lines:
        stripped = raw.strip().removeprefix("export ")
        name = stripped.partition("=")[0].strip() if "=" in stripped else ""
        if name in changes and not raw.lstrip().startswith("#"):
            value = changes[name]
            if value is not None and name not in done:
                out.append(f"{name}={value}")
            done.add(name)
            continue
        out.append(raw)
    out += [f"{n}={v}" for n, v in changes.items() if v is not None and n not in done]
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text("\n".join(out) + "\n", encoding="utf-8")
    with contextlib.suppress(OSError):
        os.chmod(tmp, 0o600)
    tmp.replace(path)
