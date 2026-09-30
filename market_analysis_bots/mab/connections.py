"""Account connections: create, test, sync, reconnect, disconnect. Credentials go to the encrypted vault and
never come back out of this module except into a provider object in the process that trades.

Each connection is one provider in one environment, fixed when it is created: an Alpaca paper connection and
an Alpaca live connection are separate connections with separate keys, and an order for one can never reach
the other (the execution engine checks the environment on every order).

Providers
    jarvus_paper   the internal simulated account (always available; no credentials)
    alpaca         Alpaca paper or live (API key + secret, or OAuth with your own registered Alpaca OAuth app)
    kraken         Kraken Pro, live only (Kraken has no spot sandbox)
    ndax           NDAX, live only (no sandbox; the adapter follows NDAX's published API and has not been run
                   against a live NDAX account in this build)

Nothing here moves money. "Add funds" opens the provider's own site; balances are whatever the provider
reports, with the time they were fetched.
"""

from __future__ import annotations

import json
import secrets as _rnd
import time
from typing import Callable, Dict, List, Optional

from mab import secrets_store
from mab.execution.base import AuthError, OrderRequest, Provider, ProviderError

PROVIDERS = {
    "jarvus_paper": {
        "label": "Jarvus Paper", "environments": ["paper"], "auth": ["none"], "fields": [], "options": {},
        "asset_classes": ["crypto", "US stocks", "Canadian stocks"],
        "summary": "Simulated account inside Jarvus: live public market data, simulated fills and money. Always available.",
        "eligibility": "none: simulated money only",
        "docs": None},
    "alpaca": {
        "label": "Alpaca", "environments": ["paper", "live"], "auth": ["api_key", "oauth"],
        "fields": ["key", "secret"], "options": {"feed": ["iex", "sip"]},
        "asset_classes": ["US stocks", "crypto"],
        "summary": "US stocks and crypto through Alpaca's official Trading API. Paper is Alpaca's own simulated "
                   "account (separate keys); live is real money.",
        "eligibility": "Paper: anyone can open a paper-only account with an email address. Live: Alpaca decides "
                       "who may open a brokerage account (country of residence, age, identity checks); Jarvus does "
                       "not check or bypass that.",
        "key_help": "Alpaca dashboard -> choose the Paper or Live account -> API keys -> Generate. Paper and live "
                    "keys are different. Alpaca API keys cannot withdraw money.",
        "docs": "https://docs.alpaca.markets/"},
    "kraken": {
        "label": "Kraken Pro", "environments": ["live"], "auth": ["api_key"], "fields": ["key", "secret"],
        "options": {"quote": ["CAD", "USD"]}, "asset_classes": ["crypto"],
        "summary": "Spot crypto through Kraken's official REST API. Kraken offers no spot sandbox: live only.",
        "eligibility": "Kraken decides account eligibility and verification level by country/province; Jarvus "
                       "does not check or bypass that.",
        "key_help": "Kraken Pro -> Settings -> API -> Create key. Tick only: Query funds, Query open/closed orders "
                    "& trades, Create & modify orders, Cancel/close orders. Do NOT tick any Withdraw or Deposit "
                    "permission.",
        "docs": "https://docs.kraken.com/api/"},
    "ndax": {
        "label": "NDAX", "environments": ["live"], "auth": ["api_key"], "fields": ["key", "secret", "user_id"],
        "options": {"quote": ["CAD"]}, "asset_classes": ["crypto"],
        "summary": "Canadian spot crypto through NDAX's WebSocket API. No sandbox: live only. Not yet run "
                   "against a live NDAX account in this build.",
        "eligibility": "NDAX decides eligibility (Canadian residency, identity verification); Jarvus does not "
                       "check or bypass that.",
        "key_help": "NDAX -> Profile -> API Keys. Copy the key, the secret and the User ID shown with it. Trading "
                    "permission only; no withdrawals.",
        "docs": "https://apidoc.ndax.io/"},
}
DEFAULT_TEST_SYMBOL = {"alpaca": "coinbase:BTC-USD", "kraken": "coinbase:BTC-USD", "ndax": "coinbase:BTC-USD"}
MAX_SKEW_WARN_MS, MAX_SKEW_FAIL_MS = 5_000, 30_000


def _now() -> int:
    return int(time.time() * 1000)


def _j(x) -> str:
    return json.dumps(x, default=str)


def _p(x, default=None):
    if not x:
        return default
    try:
        return json.loads(x)
    except ValueError:
        return default


class Connections:
    def __init__(self, storage, workspace: str = "main", transport=None,
                 local: Optional[Dict[str, Provider]] = None):
        self.st = storage
        self.ws = workspace
        self.transport = transport
        self.local: Dict[str, Provider] = dict(local or {})       # in-process providers (the simulated accounts)
        self._cache: Dict[str, Provider] = {}

    # ------------------------------------------------------------------ secrets naming
    def _sname(self, cid: str, field: str) -> str:
        return f"ws:{self.ws}:conn:{cid}:{field}"

    def has_credentials(self, cid: str, provider: str) -> bool:
        if provider == "jarvus_paper":
            return True
        if secrets_store.has(self._sname(cid, "oauth_token")):
            return True
        return all(secrets_store.has(self._sname(cid, f)) for f in PROVIDERS[provider]["fields"] if f != "user_id") \
            and bool(PROVIDERS[provider]["fields"])

    # ------------------------------------------------------------------ records
    def get(self, cid: str) -> Optional[dict]:
        r = self.st.query("SELECT * FROM connections WHERE connection_id=?", (cid,))
        return self._public(r[0]) if r else None

    def _public(self, r: dict) -> dict:
        d = dict(r)
        for k in ("options", "account", "permissions", "capabilities", "last_test"):
            d[k] = _p(d.get(k), {})
        spec = PROVIDERS.get(d["provider"], {})
        d["provider_label"] = spec.get("label", d["provider"])
        d["has_credentials"] = self.has_credentials(d["connection_id"], d["provider"])
        d["real_money"] = d["environment"] == "live"
        d["simulated"] = d["provider"] == "jarvus_paper" or d["environment"] == "demo"
        d["secret_store"] = secrets_store.backend_name() if d["provider"] != "jarvus_paper" else None
        return d

    def list(self) -> List[dict]:
        return [self._public(r) for r in self.st.query("SELECT * FROM connections ORDER BY created")]

    def ensure_defaults(self, demo: bool = False):
        """The simulated account every workspace has (paper, or demo in the demo workspace)."""
        cid, env, label = ("demo-main", "demo", "Demo account (simulated)") if demo else \
            ("paper-main", "paper", "Jarvus Paper (simulated)")
        if self.get(cid) is None:
            t = _now()
            self.st.write("INSERT INTO connections (connection_id, provider, environment, label, auth_method, status,"
                          " options, capabilities, created, updated) VALUES (?,?,?,?,?,?,?,?,?,?)",
                          (cid, "jarvus_paper", env, label, "none", "connected", "{}", "{}", t, t))
            self._audit(cid, env, "connection_created", f"{label} is ready (simulated money)")
        return cid

    def _audit(self, cid, env, stage, summary, severity="info", payload=None):
        try:
            self.st.audit("connection", summary, stage=stage, severity=severity,
                          mode={"live": "live", "paper": "paper", "demo": "demo"}.get(env), connection_id=cid,
                          payload=payload)
        except Exception:                                               # noqa: BLE001
            pass

    def create(self, provider: str, environment: str, credentials: Optional[dict] = None, options: Optional[dict] = None,
               label: str = None) -> dict:
        spec = PROVIDERS.get(provider)
        if spec is None or provider == "jarvus_paper":
            raise ValueError(f"unknown provider {provider!r}")
        if environment not in spec["environments"]:
            raise ValueError(f"{spec['label']} supports: {', '.join(spec['environments'])} (not {environment})")
        creds = {k: str(v).strip() for k, v in (credentials or {}).items() if v not in (None, "")}
        opts = {}
        for k, allowed in spec["options"].items():
            v = (options or {}).get(k, allowed[0])
            if v not in allowed:
                raise ValueError(f"{k} must be one of {', '.join(allowed)}")
            opts[k] = v
        if "user_id" in spec["fields"]:
            uid = creds.pop("user_id", None) or str((options or {}).get("user_id") or "").strip()
            if not uid:
                raise ValueError(f"{spec['label']} needs the User ID shown with the API key")
            opts["user_id"] = uid
        missing = [f for f in spec["fields"] if f != "user_id" and not creds.get(f)]
        if missing:
            raise ValueError(f"{spec['label']} needs: {', '.join(missing)}")
        base = f"{provider}-{environment}"
        cid, n = base, 2
        while self.get(cid) is not None:
            cid, n = f"{base}-{n}", n + 1
        for f in spec["fields"]:
            if f != "user_id":
                secrets_store.set_secret(self._sname(cid, f), creds[f])
        t = _now()
        lab = label or f"{spec['label']} {'Live' if environment == 'live' else 'Paper'}"
        self.st.write("INSERT INTO connections (connection_id, provider, environment, label, auth_method, status, options,"
                      " capabilities, created, updated) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (cid, provider, environment, lab, "api_key", "untested", _j(opts), "{}", t, t))
        self._audit(cid, environment, "connection_created", f"{lab} added (credentials encrypted in the vault; "
                    "they are never shown again)")
        return self.get(cid)

    def create_oauth_pending(self, provider: str, environment: str, label: str = None) -> dict:
        if provider != "alpaca":
            raise ValueError("OAuth is available for Alpaca only")
        base = f"{provider}-{environment}"
        cid, n = base, 2
        while self.get(cid) is not None:
            cid, n = f"{base}-{n}", n + 1
        t = _now()
        self.st.write("INSERT INTO connections (connection_id, provider, environment, label, auth_method, status, options,"
                      " capabilities, created, updated) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (cid, provider, environment, label or f"Alpaca {'Live' if environment == 'live' else 'Paper'} (OAuth)",
                       "oauth", "needs_credentials", "{}", "{}", t, t))
        return self.get(cid)

    # ------------------------------------------------------------------ OAuth (Alpaca, with the owner's OAuth app)
    def oauth_app(self) -> Optional[dict]:
        cid = secrets_store.get_secret(f"ws:{self.ws}:oauth:alpaca:client_id")
        sec = secrets_store.has(f"ws:{self.ws}:oauth:alpaca:client_secret")
        return {"client_id": cid, "configured": bool(cid and sec)} if cid else None

    def set_oauth_app(self, client_id: str, client_secret: str):
        if not client_id or not client_secret:
            raise ValueError("the OAuth app's client id and client secret are both required")
        secrets_store.set_secret(f"ws:{self.ws}:oauth:alpaca:client_id", client_id.strip())
        secrets_store.set_secret(f"ws:{self.ws}:oauth:alpaca:client_secret", client_secret.strip())

    def oauth_start(self, cid: str, redirect_uri: str) -> str:
        from mab.execution.alpaca import oauth_authorize_url
        c = self.get(cid)
        app = self.oauth_app()
        if c is None or c["provider"] != "alpaca":
            raise ValueError("unknown Alpaca connection")
        if not app or not app["configured"]:
            raise ValueError("OAuth needs your own Alpaca OAuth app (client id and secret); Jarvus does not ship one. "
                             "Use API keys instead, or register an app with Alpaca first.")
        state = _rnd.token_urlsafe(24)
        self.st.kv_set(f"oauth_state:{state}", {"connection_id": cid, "redirect_uri": redirect_uri, "time": _now()})
        return oauth_authorize_url(app["client_id"], redirect_uri, state, c["environment"])

    def oauth_finish(self, state: str, code: str) -> dict:
        from mab.execution.alpaca import oauth_exchange
        rec = self.st.kv_get(f"oauth_state:{state}")
        if not rec or _now() - rec["time"] > 15 * 60_000:
            raise ValueError("this sign-in link expired or was not started here; start again")
        self.st.kv_set(f"oauth_state:{state}", None)
        cid = rec["connection_id"]
        cs = secrets_store.get_secret(f"ws:{self.ws}:oauth:alpaca:client_secret")
        tok = oauth_exchange(code, self.oauth_app()["client_id"], cs, rec["redirect_uri"], self.transport)
        secrets_store.set_secret(self._sname(cid, "oauth_token"), tok["access_token"])
        self.st.write("UPDATE connections SET auth_method='oauth', status='untested', updated=? WHERE connection_id=?",
                      (_now(), cid))
        self._cache.pop(cid, None)
        self._audit(cid, self.get(cid)["environment"], "oauth_connected", "Alpaca authorised this connection (OAuth)")
        return self.test(cid)

    # ------------------------------------------------------------------ providers
    def register_local(self, cid: str, provider: Provider):
        self.local[cid] = provider

    def provider(self, cid: str) -> Provider:
        if cid in self.local:
            return self.local[cid]
        if cid in self._cache:
            return self._cache[cid]
        c = self.get(cid)
        if c is None:
            raise ProviderError(f"no connection {cid}")
        if not c.get("enabled", 1):
            raise ProviderError(f"connection {cid} is disconnected")
        if c["provider"] == "jarvus_paper":
            raise ProviderError("the simulated account runs inside the bot process; start the bots to use it")
        g = lambda f: secrets_store.get_secret(self._sname(cid, f))           # noqa: E731
        opts = c.get("options") or {}
        if c["provider"] == "alpaca":
            from mab.execution.alpaca import Alpaca
            tok = g("oauth_token")
            p = Alpaca(c["environment"], g("key"), g("secret"), token=tok, transport=self.transport,
                       stock_feed=opts.get("feed", "iex"))
        elif c["provider"] == "kraken":
            from mab.execution.kraken import Kraken
            p = Kraken(g("key"), g("secret"), quote=opts.get("quote", "CAD"), transport=self.transport)
        elif c["provider"] == "ndax":
            from mab.execution.ndax import NDAX
            p = NDAX(g("key"), g("secret"), user_id=opts.get("user_id", ""), quote=opts.get("quote", "CAD"))
        else:
            raise ProviderError(f"unknown provider {c['provider']}")
        p.connection_id = cid
        self._cache[cid] = p
        return p

    # ------------------------------------------------------------------ test / sync
    def test(self, cid: str, symbol: str = None) -> dict:
        c = self.get(cid)
        if c is None:
            raise ValueError("unknown connection")
        checks = []

        def add(key, label, status, detail=""):
            checks.append({"id": key, "label": label, "status": status, "detail": detail})

        ident, acct = {}, {}
        t0 = time.monotonic()
        try:
            p = self.provider(cid)
            add("credentials", "Credentials present", "pass", "stored encrypted" if c["provider"] != "jarvus_paper" else "none needed")
        except (AuthError, ProviderError) as e:
            add("credentials", "Credentials present", "fail", str(e))
            p = None
        if p is not None:
            try:
                ident = p.authenticate()
                add("auth", "Authentication", "pass", f"account {ident.get('account_id')} ({ident.get('status')})")
            except AuthError as e:
                add("auth", "Authentication", "fail", str(e))
            except ProviderError as e:
                add("auth", "Authentication", "fail", f"could not reach {c['provider_label']}: {e}")
        latency = (time.monotonic() - t0) * 1000
        if p is not None and ident:
            try:
                acct = p.account()
                add("account", "Account readable", "pass", f"{acct.get('currency')} buying power "
                    f"{acct.get('buying_power'):,.2f}" if acct.get("buying_power") is not None else "balances readable")
                add("trading", "Trading permitted", "pass" if acct.get("can_trade", True) else "fail",
                    "" if acct.get("can_trade", True) else "the provider reports trading is blocked on this account")
            except ProviderError as e:
                add("account", "Account readable", "fail", str(e))
            try:
                srv = p.server_time()
                if srv is None:
                    add("clock", "Clock in sync", "skip", "provider publishes no clock")
                else:
                    skew = abs(srv - _now())
                    add("clock", "Clock in sync", "pass" if skew <= MAX_SKEW_WARN_MS else ("warn" if skew <= MAX_SKEW_FAIL_MS else "fail"),
                        f"this computer is {skew / 1000:.1f}s off the provider's clock")
            except ProviderError as e:
                add("clock", "Clock in sync", "warn", str(e))
            sym = symbol or DEFAULT_TEST_SYMBOL.get(c["provider"])
            if sym:
                try:
                    q = p.quote(sym)
                    add("market_data", "Market data", "pass" if (q.get("bid") or q.get("ask")) else "warn",
                        f"{sym.split(':')[-1]} bid {q.get('bid')} / ask {q.get('ask')} ({q.get('source')})")
                except ProviderError as e:
                    add("market_data", "Market data", "warn", str(e))
            perm = (ident.get("permissions") or {})
            add("withdraw", "No withdrawal permission requested", "pass" if perm.get("withdraw") is False else "warn",
                "Jarvus never requests or uses withdrawal permission"
                + ("" if c["provider"] == "alpaca" else "; this provider does not report key permissions, so make sure "
                   "the key you created has no withdraw permission"))
        ok = all(x["status"] in ("pass", "warn", "skip") for x in checks)
        caps = p.capabilities() if p is not None else {}
        res = {"ok": ok, "time": _now(), "checks": checks, "latency_ms": round(latency, 1)}
        self.st.write("UPDATE connections SET status=?, last_test=?, account=?, permissions=?, capabilities=?, last_error=?,"
                      " updated=? WHERE connection_id=?",
                      ("connected" if ok else "error", _j(res), _j({k: ident.get(k) for k in ("account_id", "status", "currency",
                                                                                          "environment", "pattern_day_trader")}),
                       _j(ident.get("permissions") or {}), _j(caps),
                       None if ok else "; ".join(f"{x['label']}: {x['detail']}" for x in checks if x["status"] == "fail"),
                       _now(), cid))
        self._audit(cid, c["environment"], "connection_test", f"{c['label']}: connection test {'passed' if ok else 'FAILED'}",
                    "info" if ok else "warning", res)
        if ok and acct:
            self._snapshot(cid, c, acct, p, latency)
        return res

    def _snapshot(self, cid, c, acct, p, latency):
        t = _now()
        self.st.write("INSERT INTO connection_snapshots (connection_id, ts, equity, cash, buying_power, currency, latency_ms,"
                      " body) VALUES (?,?,?,?,?,?,?,?)", (cid, t, acct.get("equity"), acct.get("cash"), acct.get("buying_power"),
                                                         acct.get("currency"), latency, _j(acct)))
        try:
            pos = p.positions()
            self.st.write("DELETE FROM broker_positions WHERE connection_id=?", (cid,))
            for x in pos:
                self.st.write("INSERT OR REPLACE INTO broker_positions VALUES (?,?,?,?,?,?,?,?)",
                              (cid, x["symbol"], x.get("qty"), x.get("avg_price"), x.get("market_value"),
                               x.get("unrealized_pnl"), t, _j(x)))
        except ProviderError:
            pos = None
        if acct.get("equity") is not None:
            self.st.write("INSERT OR REPLACE INTO account_equity (connection_id, ts, mode, equity, cash, exposure, realized,"
                          " unrealized) VALUES (?,?,?,?,?,?,?,?)",
                          (cid, t, c["environment"], acct.get("equity"), acct.get("cash"), acct.get("exposure"),
                           acct.get("realized_pnl"), acct.get("unrealized_pnl")))
        self.st.write("UPDATE connections SET last_sync=? WHERE connection_id=?", (t, cid))
        return {"account": acct, "positions": pos, "time": t}

    def sync(self, cid: str) -> dict:
        c = self.get(cid)
        if c is None:
            raise ValueError("unknown connection")
        t0 = time.monotonic()
        p = self.provider(cid)
        acct = p.account()
        return self._snapshot(cid, c, acct, p, (time.monotonic() - t0) * 1000)

    def latest(self, cid: str) -> Optional[dict]:
        r = self.st.query("SELECT * FROM connection_snapshots WHERE connection_id=? ORDER BY ts DESC LIMIT 1", (cid,))
        if not r:
            return None
        d = dict(r[0])
        d["body"] = _p(d.get("body"), {})
        return d

    def reconnect(self, cid: str) -> dict:
        self._cache.pop(cid, None)
        self.st.write("UPDATE connections SET enabled=1, updated=? WHERE connection_id=?", (_now(), cid))
        return self.test(cid)

    def disconnect(self, cid: str, active_deployments: int = 0, forget: bool = True) -> dict:
        c = self.get(cid)
        if c is None:
            raise ValueError("unknown connection")
        if c["provider"] == "jarvus_paper":
            raise ValueError("the simulated account is always available and cannot be disconnected")
        if active_deployments:
            raise ValueError(f"{active_deployments} running bot(s) use this connection; stop them first")
        if forget:
            secrets_store.delete_prefix(f"ws:{self.ws}:conn:{cid}:")
        self._cache.pop(cid, None)
        self.st.write("UPDATE connections SET enabled=0, status='disconnected', updated=? WHERE connection_id=?", (_now(), cid))
        self._audit(cid, c["environment"], "disconnected", f"{c['label']} disconnected"
                    + ("; its credentials were deleted from the vault" if forget else ""), "warning")
        return self.get(cid)

    def remove(self, cid: str, active_deployments: int = 0):
        self.disconnect(cid, active_deployments, forget=True)
        self.st.write("DELETE FROM connections WHERE connection_id=?", (cid,))

    def funding(self, cid: str) -> dict:
        c = self.get(cid)
        if c is None:
            raise ValueError("unknown connection")
        if c["provider"] == "jarvus_paper":
            return {"url": None, "label": "Set paper balance", "simulated": True,
                    "note": "simulated money: changing it is never a deposit"}
        try:
            return self.provider(cid).funding()
        except ProviderError as e:
            return {"url": None, "label": None, "note": str(e)}

    def validate_order(self, cid: str, symbol: str, qty: float, price: float) -> dict:
        """A validate-only order where the provider offers one (Kraken): proves the key may trade, sends nothing."""
        p = self.provider(cid)
        if not hasattr(p, "validate"):
            return {"ok": None, "note": "this provider has no validate-only orders"}
        try:
            return p.validate(OrderRequest("jv-validate-" + _rnd.token_hex(4), symbol, "buy", "limit", qty, price, tif="ioc"))
        except ProviderError as e:
            return {"ok": False, "error": str(e)}


def migrate_legacy_brokers(storage, conns: Connections) -> List[str]:
    """Brokers saved by the earlier Live money page (kv "brokers" + per-broker secrets) become connections."""
    old = storage.kv_get("brokers", {}) or {}
    made = []
    for name, cfg in old.items():
        if name not in PROVIDERS or cfg.get("migrated"):
            continue
        key = secrets_store.get_secret(f"broker:{name}:key")
        sec = secrets_store.get_secret(f"broker:{name}:secret")
        if not key or not sec:
            continue
        opts = dict(cfg.get("options") or {})
        env = opts.pop("environment", "live") if name == "alpaca" else "live"
        try:
            c = conns.create(name, env, {"key": key, "secret": sec, "user_id": opts.get("user_id")}, opts)
            made.append(c["connection_id"])
            cfg["migrated"] = c["connection_id"]
        except ValueError:
            continue
    if made:
        storage.kv_set("brokers", old)
    return made
