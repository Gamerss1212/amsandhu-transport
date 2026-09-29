"""Connect, test and load real brokers. Keys go to the encrypted secret store; nothing here returns them.

Supported:
    kraken  Kraken Pro, spot crypto, quote CAD or USD            fields: key, secret
    ndax    NDAX (Canada), spot crypto, quote CAD                fields: key, secret, user_id
    alpaca  Alpaca, US stocks; environment "paper" or "live"     fields: key, secret

Options (quote currency, environment, NDAX user id) are stored in the fleet database under kv "brokers";
the API key and secret are stored with mab.secrets_store (Windows DPAPI, encrypted for this Windows user).
"""

from __future__ import annotations

import time
from typing import Optional

from mab import secrets_store
from mab.brokers.alpaca import Alpaca
from mab.brokers.base import Broker, BrokerError
from mab.brokers.kraken import Kraken
from mab.brokers.ndax import NDAX

CATALOG = {
    "kraken": {"label": "Kraken Pro", "asset_class": "crypto", "cls": Kraken,
               "options": {"quote": ["CAD", "USD"]},
               "help": "Kraken Pro > Settings > API > Create key. Tick: Query funds, Query open/closed orders & trades, "
                       "Create & modify orders, Cancel/close orders. Do NOT tick withdraw."},
    "ndax": {"label": "NDAX", "asset_class": "crypto", "cls": NDAX, "options": {"quote": ["CAD"]}, "extra": ["user_id"],
             "help": "NDAX > Profile > API Keys. Copy the key, the secret and the User ID shown with it. Trading permission only; "
                     "no withdrawals."},
    "alpaca": {"label": "Alpaca (US stocks)", "asset_class": "stock", "cls": Alpaca, "options": {"environment": ["paper", "live"]},
               "help": "Alpaca dashboard > API keys. Start with a PAPER key: it runs the whole path with no real money."},
}


def _sname(name: str, field: str) -> str:
    return f"broker:{name}:{field}"


def save(storage, name: str, key: str, secret: str, options: Optional[dict] = None) -> dict:
    if name not in CATALOG:
        raise ValueError(f"unknown broker {name}")
    key, secret = (key or "").strip(), (secret or "").strip()
    if not key or not secret:
        raise ValueError("API key and secret are required")
    opts = {}
    for k, allowed in CATALOG[name]["options"].items():
        v = (options or {}).get(k, allowed[0])
        if v not in allowed:
            raise ValueError(f"{k} must be one of {', '.join(allowed)}")
        opts[k] = v
    for k in CATALOG[name].get("extra", []):
        v = str((options or {}).get(k, "")).strip()
        if not v:
            raise ValueError(f"{k.replace('_', ' ')} is required for {CATALOG[name]['label']}")
        opts[k] = v
    secrets_store.set_secret(_sname(name, "key"), key)
    secrets_store.set_secret(_sname(name, "secret"), secret)
    cfg = storage.kv_get("brokers", {}) or {}
    cfg[name] = {"options": opts, "saved": int(time.time() * 1000), "last_test": None}
    storage.kv_set("brokers", cfg)
    return public(storage)


def remove(storage, name: str) -> dict:
    for f in ("key", "secret"):
        secrets_store.delete_secret(_sname(name, f))
    cfg = storage.kv_get("brokers", {}) or {}
    cfg.pop(name, None)
    storage.kv_set("brokers", cfg)
    return public(storage)


def load(storage, name: str, transport=None) -> Optional[Broker]:
    cfg = (storage.kv_get("brokers", {}) or {}).get(name)
    if not cfg:
        return None
    key, secret = secrets_store.get_secret(_sname(name, "key")), secrets_store.get_secret(_sname(name, "secret"))
    if not key or not secret:
        return None
    return CATALOG[name]["cls"](key, secret, transport=transport, **cfg.get("options", {}))


def test(storage, name: str, transport=None) -> dict:
    b = load(storage, name, transport)
    if b is None:
        raise ValueError("save the broker's key and secret first")
    try:
        res = b.test()
        res["real_money"] = bool(getattr(b, "real_money", True))
    except BrokerError as e:
        res = {"ok": False, "error": str(e)}
    cfg = storage.kv_get("brokers", {}) or {}
    if name in cfg:
        cfg[name]["last_test"] = {"time": int(time.time() * 1000), "ok": res.get("ok", False),
                                  "summary": res.get("error") or f"cash {res.get('cash')} {res.get('quote', '')}".strip()}
        storage.kv_set("brokers", cfg)
    return res


def public(storage) -> dict:
    """What the app may show: which brokers are configured, their options and last test. Never keys."""
    cfg = storage.kv_get("brokers", {}) or {}
    return {"secret_store": secrets_store.backend_name(),
            "brokers": {n: {"label": c["label"], "asset_class": c["asset_class"], "help": c["help"],
                            "options": c["options"], "extra": c.get("extra", []),
                            "configured": n in cfg, "saved_options": (cfg.get(n) or {}).get("options"),
                            "last_test": (cfg.get(n) or {}).get("last_test")} for n, c in CATALOG.items()}}
