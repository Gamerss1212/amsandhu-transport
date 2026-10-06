"""Phone alerts through Telegram (Phase 8: fills, budget use and halts).

Optional. It works only when the owner has put ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` in
``.env``. A failed alert never stops trading and never prints the token: the error text could
hold the request URL, which contains it.
"""

from __future__ import annotations

import os
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping

TOKEN_ENV = "TELEGRAM_BOT_TOKEN"
CHAT_ENV = "TELEGRAM_CHAT_ID"


def _post(url: str, data: bytes) -> None:  # pragma: no cover - network
    with urllib.request.urlopen(urllib.request.Request(url, data=data), timeout=10) as reply:
        reply.read()


def configured(env: Mapping[str, str] | None = None) -> bool:
    env = os.environ if env is None else env
    return bool(env.get(TOKEN_ENV) and env.get(CHAT_ENV))


def send(
    text: str,
    *,
    env: Mapping[str, str] | None = None,
    post: Callable[[str, bytes], None] = _post,
) -> bool:
    """Send ``text`` to the owner's Telegram chat. True if it was sent."""
    env = os.environ if env is None else env
    token, chat = env.get(TOKEN_ENV, ""), env.get(CHAT_ENV, "")
    if not (token and chat):
        return False
    data = urllib.parse.urlencode({"chat_id": chat, "text": f"QuantAgents: {text}"[:4000]})
    try:
        post(f"https://api.telegram.org/bot{token}/sendMessage", data.encode("utf-8"))
    except Exception:  # an alert must never break a trading run
        return False
    return True
