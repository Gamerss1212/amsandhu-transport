#!/usr/bin/env python3
"""ULTRON Watch: the fully automatic successor of Jarvus Watch. Watches the market 24/7 and alerts your phone,
computer or Discord. Uses no Claude usage, reads public prices only and never places an order.

What it watches (the setups that held up on unseen data, see ultron/tv/BACKTEST_ALL.md):
  every hour   1h and 4h crypto councils (50 trained agents) on BTC ETH SOL DOGE SHIB PEPE BONK WIF FLOKI
  every day    the daily markets council on 28 stocks, ETFs, forex pairs, gold, silver and oil (after the close)
  Radar        VERY LOUD: a big move is very likely in the next 12 hours (BTC, ETH, SOL by default)
What it tells you, for every trade, start to finish:
  BUY (limit price, first and final target, stop, size, when to cancel) -> SELL HALF, move the stop to breakeven
  -> SELL (target, stop, breakeven or time limit). It follows each plan on a paper account so it knows when.

  ultron_watch setup          make your private phone-alert topic (or reuse the one from Jarvus Watch)
  ultron_watch test           send a test alert
  ultron_watch run            watch 24/7 (the default when you double-click UltronWatch.exe)
  ultron_watch once           one check, then exit (for the free GitHub cloud version)
  ultron_watch status         what it is watching and the open plans
Options: --account 5000  --fees ndax|kraken|coinbase  --radar majors|all|off  --no-desktop  --no-heartbeat  --state DIR
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
if not getattr(sys, "_MEIPASS", None):
    ROOT = os.path.dirname(os.path.dirname(HERE))
    for p in (os.path.join(ROOT, "jarvus", "scripts"), os.path.join(ROOT, "ultron", "core"), os.path.join(ROOT, "ultron", "tv")):
        sys.path.insert(0, p)

import engine as en  # noqa: E402
import watch as wt  # noqa: E402

STATE_DIR = os.path.join(os.path.expanduser("~"), ".ultron-watch")
HOUR = 3_600_000
RADAR_COOLDOWN_H = 12
FAIL_ALERT_AFTER = 3                           # hourly scans in a row with no data at all


def now_ms():
    return int(time.time() * 1000)


def say(msg):
    print(f"[{datetime.now():%a %H:%M}] {msg}", flush=True)


class Watch:
    def __init__(self, a):
        self.a = a
        self.desktop = not a.no_desktop
        self.e = en.Engine(a.state, notify=self.on_trade)
        s = self.e.s
        if not s["history"] and not s["orders"] and not s["positions"] and abs(s["balance0"] - a.account) > 0.01:
            self.e.reset_account(a.account)                         # first run: size plans for your account
        if a.fees and a.fees != s["fees"]:
            self.e.set_fees(a.fees)
        s.setdefault("watch", {"radar": {}, "fails": 0, "heartbeat": 0})

    # ---------------------------------------------------------------- alerts
    def on_trade(self, kind, title, body):
        pri, tag = ("high", "chart_with_upwards_trend") if kind == "buy" else ("default", "moneybag")
        wt.notify("ULTRON " + title, body, priority=pri, tags=tag, desktop=self.desktop)

    def radar(self):
        if self.a.radar == "off":
            return
        coins = en.COINS if self.a.radar == "all" else ["BTC", "ETH", "SOL"]
        w = self.e.s["watch"]["radar"]
        for coin in coins:
            v = self.e.s["views"].get(f"{coin}|1h") or {}
            if v.get("very_loud") and now_ms() - w.get(coin, 0) >= RADAR_COOLDOWN_H * HOUR and now_ms() - v.get("t", 0) < 2 * HOUR:
                w[coin] = now_ms()
                trend = "uptrend" if v.get("up") and v.get("upH") else "no clear uptrend"
                wt.notify(f"ULTRON Radar: {coin} VERY LOUD",
                          f"A big move is very likely in the next 12 hours (VERY LOUD calls were right about 9 in 10 times on "
                          f"unseen data). Direction unknown; {trend}. Price {en.jv.px(v.get('price', 0))}. Use a wide stop "
                          "and small size if you trade it.", priority="default", tags="zap", desktop=self.desktop)

    def health(self):
        w = self.e.s["watch"]
        errs = self.e.status.get("errors") or []
        all_failed = bool(errs) and all(c in errs[0] for c in en.COINS)
        w["fails"] = w["fails"] + 1 if all_failed else 0
        if w["fails"] == FAIL_ALERT_AFTER:
            wt.notify("ULTRON Watch can't read the market", f"No data for {w['fails']} checks in a row. Check the internet "
                      "connection; I'll keep trying.", priority="high", tags="warning", desktop=self.desktop)
        if not self.a.no_heartbeat and now_ms() - w.get("heartbeat", 0) >= 24 * HOUR:
            w["heartbeat"] = now_ms()
            snap = self.e.snapshot()
            pnl = snap["equity"] - snap["balance0"]
            wt.notify("ULTRON Watch is alive", f"Watching 9 coins (1h + 4h) and 28 markets (daily). Open plans: "
                      f"{len(snap['positions'])} in trade, {len(snap['orders'])} waiting to fill. Paper result since start "
                      f"{pnl:+,.2f} ({snap['closed']} closed trades).", desktop=False)

    # ---------------------------------------------------------------- one check / forever
    def check(self, scan=True):
        if scan:
            self.e.scan()
            self.radar()
            self.print_scan()
        self.e.tick()
        self.health()
        self.e.save()

    def print_scan(self):
        v = self.e.s["views"]
        parts = []
        for coin in en.COINS:
            x = v.get(f"{coin}|1h") or {}
            g = {"L": "LOUD", "Q": "quiet", "N": "normal", "U": "warming"}.get(x.get("gate"), "?")
            if x.get("very_loud"):
                g = "VERY LOUD"
            parts.append(f"{coin} {g}")
        say("checked · " + " · ".join(parts))
        s = self.e.s
        if s["orders"] or s["positions"]:
            say("open plans: " + ", ".join(f"{p['coin']} in trade" for p in s["positions"]) +
                (", " if s["positions"] and s["orders"] else "") + ", ".join(f"{o['coin']} buy order waiting" for o in s["orders"]))

    def run(self):
        say("ULTRON Watch is on. Watching 9 coins every hour and 28 markets once a day. Leave this window open "
            "(minimise it). Close it or press Ctrl+C to stop.")
        cfg = wt.settings()
        if not (cfg["topic"] or cfg["webhook"]):
            say("No phone alerts yet: you will only see alerts on this computer. Run SETUP-ALERTS (or 'setup') to add your phone.")
        next_scan = 0.0
        while True:
            try:
                t = time.time()
                due = t >= next_scan
                self.check(scan=due)
                if due:
                    next_scan = (int(time.time() // 3600) + 1) * 3600 + 120     # 2 minutes after each hour closes
                time.sleep(60)
            except KeyboardInterrupt:
                say("Stopped.")
                return 0
            except Exception as ex:                                       # noqa: BLE001
                say(f"error ({type(ex).__name__}: {ex}); retrying in a minute")
                time.sleep(60)

    def status(self):
        snap = self.e.snapshot()
        print(f"Paper account {snap['equity']:,.2f} (started {snap['balance0']:,.2f}) · fees {snap['fees']} · "
              f"{snap['closed']} closed trades" + (f", {snap['win']:.0f}% won" if snap["win"] is not None else ""))
        for p in snap["positions"]:
            print(f"  IN TRADE  {p['coin']:7s} entry {en.jv.px(p['entry'])} · stop {en.jv.px(p['stop'])} · target "
                  f"{en.jv.px(p['target'])}" + (" · half sold, stop at breakeven" if p.get("moved") else ""))
        for o in snap["orders"]:
            print(f"  WAITING   {o['coin']:7s} limit buy {en.jv.px(o['limit'])} until {en.mt_str(o['expires'])}")
        for d in snap["decisions"][-5:]:
            print(f"  decision  {d['coin']:7s} {d['agent']}: {d['why']}")
        return 0


def main():
    ap = argparse.ArgumentParser(description="ULTRON Watch: fully automatic AI market watcher with phone alerts.")
    ap.add_argument("cmd", nargs="?", default="run", choices=["setup", "test", "once", "run", "status"])
    ap.add_argument("--account", type=float, default=1000.0, help="your account size: sizes every plan")
    ap.add_argument("--fees", default="ndax", choices=sorted(en.FEES), help="your crypto exchange")
    ap.add_argument("--radar", default="majors", choices=["majors", "all", "off"], help="VERY LOUD alerts")
    ap.add_argument("--state", default=STATE_DIR)
    ap.add_argument("--no-desktop", action="store_true", help="no pop-up on this computer")
    ap.add_argument("--no-heartbeat", action="store_true", help="no daily 'alive' message")
    a = ap.parse_args()
    if a.cmd == "setup":
        return wt.setup()
    if a.cmd == "test":
        wt.notify("ULTRON test", "If you can read this, alerts work. A real one looks like:\nBUY SOL (1h crypto)\n"
                  "Buy (limit) 121.07 · sell half at 122.07, rest at 129.07 · stop 117.07\nSize $180 (1.49 SOL) · "
                  "cancel if not filled by Sat 12:00 MT", desktop=not a.no_desktop)
        cfg = wt.settings()
        if not (cfg["topic"] or cfg["webhook"]):
            print("No phone or chat channel yet: run setup first.")
        return 0
    w = Watch(a)
    if a.cmd == "status":
        return w.status()
    if a.cmd == "once":
        w.check(scan=True)
        return w.status()
    return w.run()


if __name__ == "__main__":
    sys.exit(main())
