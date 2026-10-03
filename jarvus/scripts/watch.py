#!/usr/bin/env python3
"""Jarvus watcher: looks at the market all day and alerts you when the rules say BUY. No Claude usage.

  python3 watch.py setup                 # once: makes a private phone-alert topic and tells you how to subscribe
  python3 watch.py test                  # sends one test alert to every channel you set up
  python3 watch.py once [--dry-run]      # one check of every coin, prints (and alerts on) any BUY
  python3 watch.py run                   # keeps checking every 10 minutes until you close it (Ctrl+C)

Options: --coins SOL,ETH,BTC,DOGE,BONK · --account 1000 · --fees ndax · --every 10 (minutes)
         --state PATH (where it remembers what it already told you) · --no-heartbeat

It runs the same rules as `jarvus.py card` (v7) on completed candles, so it only changes its mind when an hour or
a 4-hour candle closes. It tells you ONCE when a coin turns BUY (and not again for 4 hours), once a day that it is
still alive, and once if the data feed keeps failing. It never places an order: you click buy/sell yourself.

Alert channels (any mix; none needed to see alerts in this window):
  phone   ntfy app (free): topic in env JARVUS_NTFY_TOPIC or in ~/.jarvus/watch.json (made by `setup`);
          JARVUS_NTFY_URL points at your own ntfy server (default https://ntfy.sh)
  chat    JARVUS_WEBHOOK_URL: a Discord (or Slack-style) webhook
  desktop a pop-up on this computer (Windows, Mac, Linux), plus a beep
The topic and webhook are secrets: they live in environment variables or the config file (owner-only), are never
printed in logs, and never go in chat or source control. Messages contain only the plan (coin, prices, size).
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import subprocess
import sys
import time
import urllib.request
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import jarvus as jv  # noqa: E402

CONFIG = os.path.join(os.path.expanduser("~"), ".jarvus", "watch.json")
STATE = os.path.join(os.path.expanduser("~"), ".jarvus", "watch_state.json")
COOLDOWN_H = 4
HEARTBEAT_H = 24
FAIL_ALERT_AFTER = 6                                  # consecutive cycles in which every coin failed


# ------------------------------------------------------------------ config and state
def load_json(path, default):
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, ValueError):
        return default


def save_json(path, obj, private=False):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = path + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(obj, fh)
    if private:
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
    os.replace(tmp, path)


def settings():
    cfg = load_json(CONFIG, {})
    return {"topic": os.environ.get("JARVUS_NTFY_TOPIC") or cfg.get("ntfy_topic"),
            "ntfy_url": (os.environ.get("JARVUS_NTFY_URL") or cfg.get("ntfy_url") or "https://ntfy.sh").rstrip("/"),
            "webhook": os.environ.get("JARVUS_WEBHOOK_URL") or cfg.get("webhook_url")}


# ------------------------------------------------------------------ sending (never logs the topic or the URL)
def _post(url, data, headers):
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=15) as r:
        return r.status


def send_phone(cfg, title, body, priority="default", tags=""):
    if not cfg["topic"]:
        return None
    h = {"Title": title.encode("utf-8").decode("latin-1", "ignore"), "Priority": priority, "Tags": tags,
         "Content-Type": "text/plain; charset=utf-8"}
    try:
        return _post(f"{cfg['ntfy_url']}/{cfg['topic']}", body.encode("utf-8"), h) < 300
    except Exception as e:                                           # noqa: BLE001
        return f"phone alert failed ({type(e).__name__})"


def send_chat(cfg, title, body):
    if not cfg["webhook"]:
        return None
    try:
        payload = json.dumps({"content": f"**{title}**\n{body}", "text": f"{title}\n{body}"}).encode("utf-8")
        return _post(cfg["webhook"], payload, {"Content-Type": "application/json"}) < 300
    except Exception as e:                                           # noqa: BLE001
        return f"chat alert failed ({type(e).__name__})"


def send_desktop(title, body):
    """Best-effort pop-up + beep. Returns None when this system has no way to show one."""
    try:
        if sys.platform.startswith("win"):
            t, b = title.replace("'", ""), body.replace("'", "").replace("\n", " | ")
            ps = ("Add-Type -AssemblyName System.Windows.Forms; $n = New-Object System.Windows.Forms.NotifyIcon; "
                  "$n.Icon = [System.Drawing.SystemIcons]::Information; $n.Visible = $true; "
                  f"$n.ShowBalloonTip(20000, '{t}', '{b}', 'Info'); [console]::beep(880,300); Start-Sleep -Seconds 21; $n.Dispose()")
            subprocess.Popen(["powershell", "-NoProfile", "-WindowStyle", "Hidden", "-Command", ps],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, creationflags=0x08000000)  # no console flash
        elif sys.platform == "darwin":
            esc = lambda s: s.replace("\\", "").replace('"', "'")    # noqa: E731
            subprocess.Popen(["osascript", "-e", f'display notification "{esc(body)}" with title "{esc(title)}" sound name "Glass"'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        else:
            subprocess.Popen(["notify-send", title, body], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        return True
    except Exception:                                                # noqa: BLE001
        return None


def notify(title, body, priority="default", tags="", desktop=True):
    cfg = settings()
    print(f"\a[{datetime.now():%a %H:%M}] {title}\n{body}\n", flush=True)
    res = {"phone": send_phone(cfg, title, body, priority, tags), "chat": send_chat(cfg, title, body)}
    if desktop:
        res["desktop"] = send_desktop(title, body)
    for k, v in res.items():
        if isinstance(v, str):
            print(f"  ({v})", flush=True)
    return res


# ------------------------------------------------------------------ the decision to alert
def buy_message(r):
    """The alert text: only the plan. A limit order that has to fill within 3 hours (that is how it was backtested)."""
    coin = r["sym"].split("-")[0]
    cancel = (r["mt"] + timedelta(hours=3)).strftime("%a %H:%M")
    return (f"{coin} ${jv.px(r['close'])} → BUY\n"
            f"Buy (limit) {jv.px(r['entry'])} · Sell {jv.px(r['target'])} · Stop {jv.px(r['stop'])}\n"
            f"Size ${r['notional']:,.0f} · cancel if not filled by {cancel} MT · out by "
            f"{(r['mt'] + timedelta(hours=96)):%a %H:%M} MT\n"
            f"Setup {', '.join(r['setups'])} · next 12h: {jv.move(r)}, direction unknown")


def should_alert(state_coin, verdict, now_ms):
    """Alert on the turn from not-BUY to BUY, and not again within the cooldown."""
    if verdict != "BUY":
        return False
    if state_coin.get("was_buy"):
        return False
    return now_ms - state_coin.get("last_alert_ms", 0) >= COOLDOWN_H * 3_600_000


def cycle(coins, account, fees, state, dry_run=False, desktop=True, evaluate=None):
    """Check every coin once. Returns (results, errors). Updates `state` in place."""
    evaluate = evaluate or jv.evaluate
    jv._BTC.clear()                                    # BTC's 200-day / 4h readings must be fresh every cycle
    now_ms = int(time.time() * 1000)
    results, errors = [], 0
    for c in coins:
        try:
            r = evaluate(c, account, fees)
        except (Exception, SystemExit) as e:           # noqa: BLE001  one bad coin must not stop the rest
            errors += 1
            print(f"[{datetime.now():%H:%M}] {c}: no data ({type(e).__name__})", flush=True)
            continue
        results.append(r)
        st = state.setdefault("coins", {}).setdefault(r["sym"], {})
        if should_alert(st, r["verdict"], now_ms):
            if dry_run:
                print("(dry run, would alert)\n" + buy_message(r) + "\n")
            else:
                notify(f"Jarvus BUY {r['sym'].split('-')[0]}", buy_message(r), priority="high", tags="chart_with_upwards_trend",
                       desktop=desktop)
            st["last_alert_ms"] = now_ms
        st["was_buy"] = r["verdict"] == "BUY"
        st["verdict"] = r["verdict"]
    return results, errors


def heartbeat_text(results, coins):
    if not results:
        return "Jarvus is running but could not read any market data."
    nb = sum(r["verdict"] == "BUY" for r in results)
    return (f"Jarvus is watching {len(results)} of {len(coins)} coins. "
            + ("BUY now: " + ", ".join(r["sym"].split("-")[0] for r in results if r["verdict"] == "BUY")
               if nb else "No buys right now. I'll alert you when one appears."))


def run(args):
    coins = [c.strip().upper() for c in args.coins.split(",") if c.strip()]
    state = load_json(args.state, {})
    fails = 0
    print(f"Jarvus is watching {', '.join(coins)} every {args.every} min. Close this window or press Ctrl+C to stop.", flush=True)
    while True:
        results, errors = cycle(coins, args.account, args.fees, state, desktop=not args.no_desktop)
        now_ms = int(time.time() * 1000)
        fails = fails + 1 if not results else 0
        if fails == FAIL_ALERT_AFTER:
            notify("Jarvus can't read the market", f"No data for {fails} checks in a row. Check the internet connection; "
                   "I'll keep trying.", priority="high", tags="warning", desktop=not args.no_desktop)
        if not args.no_heartbeat and now_ms - state.get("last_heartbeat_ms", 0) >= HEARTBEAT_H * 3_600_000:
            notify("Jarvus is alive", heartbeat_text(results, coins), desktop=False)
            state["last_heartbeat_ms"] = now_ms
        save_json(args.state, state)
        try:
            time.sleep(args.every * 60)
        except KeyboardInterrupt:
            print("Stopped.")
            return 0


# ------------------------------------------------------------------ commands
def setup():
    cfg = load_json(CONFIG, {})
    if not cfg.get("ntfy_topic"):
        cfg["ntfy_topic"] = "jarvus-" + secrets.token_urlsafe(18).replace("_", "x").replace("-", "y")
        save_json(CONFIG, cfg, private=True)
        made = "Made your private alert topic."
    else:
        made = "You already have a private alert topic."
    print(made + "\nOn your phone: install the free 'ntfy' app, tap +, choose 'Subscribe to topic', and type this topic "
          "exactly (keep it private: anyone with it can read your alerts):\n\n    " + cfg["ntfy_topic"] +
          "\n\n(also saved in " + CONFIG + ")\nThen run:  python watch.py test\n"
          "Alerts go through the public ntfy.sh server and contain only the plan (coin, prices, size).\n"
          "To use Discord instead, set the environment variable JARVUS_WEBHOOK_URL to a Discord webhook URL.")
    return 0


def main():
    ap = argparse.ArgumentParser(description="Jarvus watcher: alerts you when the rules say BUY.")
    ap.add_argument("cmd", choices=["setup", "test", "once", "run"])
    ap.add_argument("--coins", default=",".join(jv.BEST5))
    ap.add_argument("--account", type=float, default=1000.0)
    ap.add_argument("--fees", default="ndax")
    ap.add_argument("--every", type=float, default=10.0, help="minutes between checks (run)")
    ap.add_argument("--state", default=STATE)
    ap.add_argument("--dry-run", action="store_true", help="once: print what it would alert, send nothing")
    ap.add_argument("--no-heartbeat", action="store_true")
    ap.add_argument("--no-desktop", action="store_true", help="skip the pop-up on this computer")
    a = ap.parse_args()
    if a.cmd == "setup":
        return setup()
    if a.cmd == "test":
        res = notify("Jarvus test", "If you can read this, alerts work. A real one looks like:\n"
                     "SOL $121.19 → BUY\nBuy (limit) 121.07 · Sell 129.47 · Stop 116.87", desktop=not a.no_desktop)
        cfg = settings()
        if not (cfg["topic"] or cfg["webhook"]):
            print("No phone or chat channel yet: run  python watch.py setup")
        return 0
    if a.cmd == "once":
        coins = [c.strip().upper() for c in a.coins.split(",") if c.strip()]
        state = load_json(a.state, {})
        results, errors = cycle(coins, a.account, a.fees, state, dry_run=a.dry_run, desktop=not a.no_desktop)
        if not a.dry_run:
            save_json(a.state, state)
        for r in results:
            print(jv.short(r, why=False, scan=True))
        return 0 if results else 1
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
