"""Read the owner's ``.env`` file into the environment (spec section 72: secrets stay out of code).

Only the owner writes ``.env``; it is never committed and never put in a release zip. Values
are loaded into ``os.environ`` and are never printed: callers only learn which names were set.
A name that is already in the environment wins over the file.
"""

from __future__ import annotations

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
