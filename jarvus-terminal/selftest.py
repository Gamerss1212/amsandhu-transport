#!/usr/bin/env python3
"""Check the install: python3 run.py selftest   (or JarvusTerminal.exe selftest)

Offline and self-contained: loads the strategy library, the bots, the volatility gate and the measured results,
checks the database migrations and the credential vault, then starts the app's server on a spare port with a
throw-away data folder and exercises the three pages' routes, sign-in and the protections (local Host only, CSRF
token and the app header on every change). No network, no bots started, no keys needed, nothing traded.
"""

from __future__ import annotations

import json
import os
import socket
import sys
import tempfile
import threading
import urllib.error
import urllib.request

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
FAILS = []


def check(name, cond, detail=""):
    print(("  ok   " if cond else "  FAIL ") + name + (f"   ({detail})" if detail and not cond else ""))
    if not cond:
        FAILS.append(name)


def _port():
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    p = s.getsockname()[1]
    s.close()
    return p


def main() -> int:
    tmp = tempfile.mkdtemp(prefix="jarvus-selftest-")
    os.environ["JARVUS_DATA"] = tmp                        # never touch the real data folder or vault
    os.environ["MAB_SECRETS_DIR"] = os.path.join(tmp, "vault")
    os.environ["MAB_SECRETS_NO_KEYRING"] = "1"
    import config
    config.DATA_DIR = tmp
    config.PORT = _port()
    from engine import library
    import server

    print("\n  Library, bots and models")
    lib = library.library()
    c = lib["counts"]
    check("strategy library loads", c["counted_strategies"] >= 300 and len(lib["strategies"]) == c["counted_strategies"],
          f"{c.get('counted_strategies')}")
    impl = {s["id"] for s in lib["strategies"] if s["impl"] == "implemented"}
    with open(library.REGISTRY, encoding="utf-8") as fh:
        bots = json.load(fh)["bots"]
    check(f"{len(bots)} research bots, each on an implemented strategy", len(bots) >= 300 and all(b["strategy_id"] in impl for b in bots))
    from mab.volgate import HORIZON, Bars, VolGate
    import math
    n = 24 * 120
    closes = [100 * math.exp(0.002 * math.sin(i / 9) + 0.0001 * i) for i in range(n)]
    bars = Bars([i * 3_600_000 for i in range(n)], closes, [x * 1.004 for x in closes], [x * 0.996 for x in closes], closes,
                [1000.0] * n, HORIZON["crypto"])
    r = VolGate().read(bars, n - 1, "crypto")
    check("volatility gate reads a market", r["state"] in ("LOUD", "NORMAL", "QUIET"), str(r))
    res = library.results()
    check("measured strategy results load", bool(res.get("strategies")) and res["strategies"]["runs"] > 0, res.get("strategies_error", ""))
    check("full-system backtest results load", bool(res.get("system")) and res["system"]["runs"] >= 500)
    from mab.data.demo import MARKETS
    check("demo market generator available", len(MARKETS) >= 5)

    print("\n  Database and vault")
    from mab import migrations, secrets_store
    from mab.storage import Storage
    st = Storage(os.path.join(tmp, "check.db"))
    ms = migrations.status(st._conn())
    check("database migrations apply", not ms["pending"] and max(ms["applied"]) == migrations.LATEST, str(ms))
    secrets_store.set_secret("selftest:probe", "value-123")
    check("credential vault encrypts and reads back", secrets_store.get_secret("selftest:probe") == "value-123")
    with open(os.path.join(os.environ["MAB_SECRETS_DIR"], "vault.json"), "rb") as fh:
        check("vault holds no plain text", b"value-123" not in fh.read())
    secrets_store.delete_secret("selftest:probe")
    check("secret store backend", bool(secrets_store.backend_name()), secrets_store.backend_name())

    try:
        import anthropic
        print(f"  ok   AI research assistant SDK (anthropic {anthropic.__version__})")
    except ImportError:
        print("  note AI research assistant SDK not installed (the assistant stays off; everything else works)")

    print("\n  App server (engines not started)")
    server.make_app(tmp, start_engines=False)
    httpd = server.QuietServer(("127.0.0.1", config.PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{config.PORT}"
    jar = {"token": None, "csrf": None}

    def req(path, body=None, headers=None, csrf=True):
        h = {"X-Jarvus": "1", "Content-Type": "application/json"} if body is not None else {}
        if body is not None and csrf and jar["csrf"]:
            h["X-CSRF-Token"] = jar["csrf"]
        if jar["token"]:
            h["Cookie"] = f"jv_session={jar['token']}"
        h.update(headers or {})
        rq = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers=h,
                                    method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(rq, timeout=20) as resp:
                raw, code, hdrs = resp.read(), resp.status, resp.headers
        except urllib.error.HTTPError as e:
            raw, code, hdrs = e.read(), e.code, e.headers
        ck = hdrs.get("Set-Cookie") or ""
        if ck.startswith("jv_session="):
            jar["token"] = ck.split(";", 1)[0].split("=", 1)[1] or None
        try:
            data = json.loads(raw)
        except ValueError:
            return code, raw
        if isinstance(data, dict) and data.get("csrf"):
            jar["csrf"] = data["csrf"]
        return code, data

    code, page = req("/")
    check("the app page loads", code == 200 and b"/js/app.js" in page)
    check("its scripts, chart library and style load", all(req(p)[0] == 200 for p in (
        "/js/app.js", "/js/core.js", "/js/command.js", "/js/connections.js", "/js/intel.js", "/js/charts.js",
        "/vendor/lightweight-charts.standalone.production.js", "/app.css")))
    check("nothing else is served from disk", req("/../server.py")[0] == 404 and req("/config.py")[0] == 404)
    code, d = req("/api/auth/state")
    check("opens without a sign-in page", code == 200 and d.get("signed_in") and bool(jar["token"]))
    code, ov = req("/api/overview")
    check("Command Center data", code == 200 and ov["workspace"]["kind"] == "main" and ov["live_authorization"]["authorized"] is False)
    check("real money is off", ov["live_authorization"]["authorized"] is False and not ov["emergency"])
    code, ap = req("/api/autopilot")
    check("the AI trades by itself (paper money only)", code == 200 and ap["on"] is True and ap["real_money"] is False)
    code, cn = req("/api/connections")
    ids = [x["connection_id"] for x in cn.get("connections", [])] if code == 200 else []
    check("Connections: the simulated paper account exists", "paper-main" in ids)
    check("Connections: providers listed", {"jarvus_paper", "alpaca", "kraken", "ndax"} <= set(cn.get("providers", {})))
    check("no credential in any response", "secret" not in json.dumps(cn.get("connections")).lower().replace("secret_store", ""))
    for p in ("/api/strategies", "/api/markets", "/api/events", "/api/health", "/api/research/jobs", "/api/models",
              "/api/exposure", "/api/positions", "/api/orders", "/api/fills", "/api/watchlists", "/api/accounts"):
        code, _ = req(p)
        check(f"route {p}", code == 200)
    code, bt = req("/api/backtest?strategy=" + lib["strategies"][0]["id"])
    check("backtest summary route", code == 200)
    code, mv = req("/api/money")
    check("Your money (the AI's account) route", code == 200 and mv.get("real_money") in (False, None) and "positions" in mv)
    code, an = req("/api/analysis")
    check("What the AI sees route", code == 200 and isinstance(an.get("markets"), list))
    code, fe = req("/api/fees")
    check("exchange fee levels, NDAX by default", code == 200 and fe.get("current") == "ndax" and len(fe.get("profiles", [])) >= 4)
    code, su = req("/api/startup")
    check("start-with-Windows status", code == 200 and "supported" in su)
    code, pj = req("/api/projection?balance=100&days=90&target=300000")
    check("goal calculator answers from the bundled measurements", code == 200 and pj.get("goal", {}).get("share_reaching") == 0.0
          and 9.0 < pj["goal"]["needed_per_day_pct"] < 9.6, str(pj)[:160])
    code, pj2 = req("/api/projection?balance=100000&days=30")
    check("goal calculator at another balance size", code == 200 and pj2.get("tier", 0) >= 10000)

    print("\n  Protections")
    check("a change without the CSRF token is refused", req("/api/emergency", {"reason": "x"}, csrf=False)[0] == 403)
    check("a change without the app header is refused", req("/api/emergency", {"reason": "x"}, headers={"X-Jarvus": "0"})[0] == 403)
    check("a foreign Host is refused (DNS rebinding)", req("/api/overview", headers={"Host": "evil.example:80"})[0] == 403)
    check("a foreign Origin is refused", req("/api/emergency", {"reason": "x"}, headers={"Origin": "http://evil.example"})[0] == 403)
    code, d = req("/api/live/authorize", {"ack": server.LIVE_ACK, "connections": ["x"], "max_total_allocation": 1,
                                          "daily_loss_limit": 1})
    check("live trading cannot be authorised with the engine stopped", code == 409)
    code, d = req("/api/emergency", {"reason": "selftest"})
    check("EMERGENCY STOP works with the engine stopped", code == 200 and d.get("blocked") is True)
    code, d = req("/api/autopilot", {"on": True})
    check("autopilot never overrides an emergency stop", code == 409)
    check("emergency stop clears", req("/api/emergency/clear", {})[0] == 200)
    httpd.shutdown()

    print()
    if FAILS:
        print(f"  {len(FAILS)} check(s) failed: {', '.join(FAILS)}\n")
        return 1
    print("  Every check passed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
