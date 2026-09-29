#!/usr/bin/env python3
"""Check the install: python3 run.py selftest

Offline and self-contained: loads the library, the bots, the volatility gate and the measured results,
then starts the app's server on a spare port with a throw-away data folder and exercises every route,
including the protections (local Host only, the app header on every change). No network, no bots
started, no keys needed.
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
    os.environ["JARVUS_DATA"] = tmp                        # never touch the real data folder
    import config
    config.DATA_DIR = tmp
    config.PORT = _port()
    from engine import fleet
    fleet.HOME = os.path.join(tmp, "fleet")
    fleet._AUTOPILOT = os.path.join(fleet.HOME, "autopilot.json")
    import server

    print("\n  Library, bots and models")
    lib = fleet.library()
    c = lib["counts"]
    check("strategy library loads", c["counted_strategies"] >= 300 and len(lib["strategies"]) == c["counted_strategies"],
          f"{c.get('counted_strategies')}")
    impl = {s["id"] for s in lib["strategies"] if s["impl"] == "implemented"}
    with open(fleet.REGISTRY, encoding="utf-8") as fh:
        bots = json.load(fh)["bots"]
    check("every bot runs an implemented strategy", bots and all(b["strategy_id"] in impl for b in bots), f"{len(bots)} bots")
    check("every implemented strategy has a bot", impl <= {b["strategy_id"] for b in bots})
    from mab.volgate import HORIZON, Bars, VolGate
    import math
    n = 24 * 120
    closes = [100 * math.exp(0.002 * math.sin(i / 9) + 0.0001 * i) for i in range(n)]
    bars = Bars([i * 3_600_000 for i in range(n)], closes, [x * 1.004 for x in closes], [x * 0.996 for x in closes], closes,
                [1000.0] * n, HORIZON["crypto"])
    r = VolGate().read(bars, n - 1, "crypto")
    check("volatility gate reads a market", r["state"] in ("LOUD", "NORMAL", "QUIET"), str(r))
    res = fleet.results()
    check("strategy test results load", bool(res.get("strategies")) and res["strategies"]["runs"] > 0, res.get("strategies_error", ""))
    check("full-system backtest results load", bool(res.get("system")) and res["system"]["runs"] >= 500)
    check("volatility gate accuracy loads", bool(res.get("volgate")) and "crypto" in res["volgate"])
    check("swing lab results load", bool(res.get("swing_lab")) and len(res["swing_lab"]["rows"]) > 50)
    check("fee-level comparison loads", len(res.get("fee_profiles") or []) >= 2)
    from mab import secrets_store
    check("secret store available", bool(secrets_store.backend_name()), secrets_store.backend_name())

    print("\n  App server")
    httpd = server.QuietServer(("127.0.0.1", config.PORT), server.Handler)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{config.PORT}"

    def req(path, body=None, headers=None):
        h = {"X-Jarvus": "1", "Content-Type": "application/json"} if body is not None else {}
        h.update(headers or {})
        rq = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(), headers=h,
                                    method="POST" if body is not None else "GET")
        try:
            with urllib.request.urlopen(rq, timeout=20) as resp:
                raw = resp.read()
                return resp.status, (json.loads(raw) if resp.headers.get("Content-Type", "").startswith("application/json") else raw)
        except urllib.error.HTTPError as e:
            raw = e.read()
            try:
                return e.code, json.loads(raw)
            except ValueError:
                return e.code, raw

    code, page = req("/")
    check("the app page loads", code == 200 and b"Jarvus" in page and b"app.js" in page)
    check("its script and style load", req("/app.js")[0] == 200 and req("/app.css")[0] == 200)
    check("nothing else is served from disk", req("/../server.py")[0] == 404 and req("/config.py")[0] == 404)
    code, st = req("/api/status")
    check("status", code == 200 and st.get("running") is False and "autopilot" in st)
    code, b = req("/api/f/bots")
    check("bots list works with the fleet stopped", code == 200 and len(b) == len([x for x in bots if x.get("enabled", True)]))
    code, s = req("/api/f/summary")
    check("fleet summary works with the fleet stopped", code == 200 and s.get("offline") is True)
    for p in ("brain", "trades", "events", "tickers", "equity", "positions", "series"):
        code, _ = req("/api/f/" + p)
        check(f"fleet view {p}", code == 200)
    check("unknown fleet view refused", req("/api/f/../../etc")[0] == 404)
    code, lib2 = req("/api/library")
    check("library route", code == 200 and len(lib2["strategies"]) == c["counted_strategies"])
    code, one = req("/api/library/" + lib["strategies"][0]["id"])
    check("one strategy with its sources", code == 200 and "definition" in one and "sources" in one)
    check("results route", req("/api/results")[0] == 200)
    code, br = req("/api/brokers")
    check("brokers listed, no keys configured", code == 200 and set(br["brokers"]) == {"kraken", "ndax", "alpaca"}
          and not any(x["configured"] for x in br["brokers"].values()))
    code, lv = req("/api/live")
    check("real money is off by default", code == 200 and lv["armed"] is False)

    print("\n  Protections")
    code, _ = req("/api/command", {"command": "pause"}, headers={"X-Jarvus": "0"})
    check("a change without the app header is refused", code == 403)
    code, _ = req("/api/status", headers={"Host": "evil.example:80"})
    check("a foreign Host is refused (DNS rebinding)", code == 403)
    code, _ = req("/api/command", {"command": "pause"}, headers={"Origin": "http://evil.example"})
    check("a foreign Origin is refused", code == 403)
    code, j = req("/api/command", {"command": "rm_rf"})
    check("unknown commands are refused", "error" in j)

    print("\n  Paper money and brokers (fleet stopped)")
    code, j = req("/api/command", {"command": "set_balance", "args": {"amount": 25000}})
    check("set the paper balance while stopped", j.get("status") == "done" and abs(j["account"]["equity"] - 25000) < 1e-6, str(j))
    code, j = req("/api/command", {"command": "deposit", "args": {"amount": 5000}})
    check("add paper money", j.get("status") == "done" and abs(j["account"]["equity"] - 30000) < 1e-6, str(j))
    code, j = req("/api/command", {"command": "set_balance", "args": {"amount": -5}})
    check("a negative amount is refused", "error" in j)
    code, fees = req("/api/fees")
    check("fee profiles listed, each bot's own exchange by default", code == 200 and fees["current"] == "venue"
          and {"ndax", "kraken", "low_fee"} <= {p["name"] for p in fees["profiles"]})
    code, j = req("/api/command", {"command": "set_fee_profile", "args": {"profile": "ndax"}})
    check("choose NDAX fees while stopped", j.get("status") == "done" and req("/api/fees")[1]["current"] == "ndax", str(j))
    code, j = req("/api/command", {"command": "set_fee_profile", "args": {"profile": "free"}})
    check("unknown fee profiles are refused", "error" in j)
    code, j = req("/api/broker/save", {"name": "kraken", "key": "", "secret": ""})
    check("a broker needs a key and a secret", code == 400 and "required" in j.get("error", ""))
    code, j = req("/api/broker/save", {"name": "nope", "key": "a", "secret": "b"})
    check("unknown brokers are refused", code == 400)
    code, j = req("/api/command", {"command": "live_arm", "args": {"broker": "kraken", "ack": "x"}})
    check("real money cannot be armed while the bots are stopped", "error" in j)
    code, j = req("/api/command", {"command": "live_disarm", "args": {}})
    check("disarm always works", j.get("status") == "done" and j["result"]["armed"] is False)
    httpd.shutdown()

    print()
    if FAILS:
        print(f"  {len(FAILS)} check(s) failed: {', '.join(FAILS)}\n")
        return 1
    print("  Every check passed.\n")
    return 0


if __name__ == "__main__":
    sys.exit(main())
