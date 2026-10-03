#!/usr/bin/env python3
"""Jarvus — the desktop app. Watches the market around the clock and tells you when to buy and when to sell.

Double-click and leave it open. Every 10 minutes it runs Jarvus's backtested v7 rules (scripts/jarvus.py) on
SOL, ETH, BTC, DOGE and BONK. When one turns BUY it pops up with a sound and shows the whole plan: buy price
(limit), sell price (target), stop-loss, size and when to cancel. Tap "I bought it" and it watches the trade
every minute and tells you when to sell (target reached, stop hit, or time up). It never places orders.

  python jarvus_app.py              # run (Windows build: Jarvus.exe)
  python jarvus_app.py --minimized  # how Windows starts it at login
"""

from __future__ import annotations

import json
import math
import os
import queue
import socket
import sys
import threading
import time
from datetime import datetime, timedelta

FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, getattr(sys, "_MEIPASS", None) or os.path.join(os.path.dirname(HERE), "scripts"))

DATA = os.path.join(os.path.expanduser("~"), ".jarvus")
CFG_PATH = os.path.join(DATA, "app.json")
LOG_PATH = os.path.join(DATA, "app.log")
os.makedirs(DATA, exist_ok=True)
if sys.stdout is None or sys.stderr is None:                     # windowed exe: keep a small log instead
    try:
        if os.path.exists(LOG_PATH) and os.path.getsize(LOG_PATH) > 1_000_000:
            os.replace(LOG_PATH, LOG_PATH + ".old")
        sys.stdout = sys.stderr = open(LOG_PATH, "a", encoding="utf-8", buffering=1)
    except OSError:
        pass

import tkinter as tk                                              # noqa: E402
import tkinter.font as tkfont                                     # noqa: E402

import jarvus as jv                                               # noqa: E402
import watch as wt                                                # noqa: E402
from fetch_ohlcv import fetch_coinbase                            # noqa: E402

VERSION = "1.0"
COINS = ["SOL", "ETH", "BTC", "DOGE", "BONK"]
NAMES = {"SOL": "Solana", "ETH": "Ethereum", "BTC": "Bitcoin", "DOGE": "Dogecoin", "BONK": "Bonk"}
COIN_COLOR = {"SOL": "#9B5CFF", "ETH": "#6E8BFF", "BTC": "#F7931A", "DOGE": "#D4B44A", "BONK": "#FF8A3D"}
MAJORS = {"SOL", "ETH", "BTC"}
SCAN_EVERY = 600            # seconds between market checks
POS_EVERY = 60              # seconds between price checks on open trades
SIGNAL_VALID_H = 3          # the limit order is valid this long (as backtested)
HOLD_H = 96
PORT = 47391                # single-instance lock (localhost only)
FEES = [("ndax", "NDAX"), ("kraken", "Kraken"), ("coinbase", "Coinbase")]

C = {"bg": "#090C11", "card": "#111620", "card2": "#151B27", "line": "#222A39", "text": "#ECF1F8", "muted": "#8D97AB",
     "dim": "#586176", "green": "#2EE07A", "green_d": "#0E2A1B", "green_b": "#1F7A47", "red": "#FF5470",
     "red_d": "#2A0F17", "amber": "#FFB547", "blue": "#5AA9FF", "blue_d": "#0F1E33", "chip": "#1A2130"}


# ------------------------------------------------------------------ small helpers
def now_ms():
    return int(time.time() * 1000)


def clock(ms=None, with_day=False):
    d = datetime.fromtimestamp((ms or now_ms()) / 1000)
    s = d.strftime("%I:%M %p").lstrip("0")
    if with_day and d.date() != datetime.now().date():
        s = d.strftime("%a ") + s
    return s


def load_cfg():
    cfg = wt.load_json(CFG_PATH, {})
    cfg.setdefault("account", 1000.0)
    cfg.setdefault("fees", "ndax")
    cfg.setdefault("sound", True)
    cfg.setdefault("awake", True)
    cfg.setdefault("startup", False)
    cfg.setdefault("welcomed", False)
    cfg.setdefault("coins", {})
    cfg.setdefault("signals", {})
    cfg.setdefault("positions", [])
    cfg.setdefault("history", [])
    return cfg


PLAIN = [("gate QUIET", "The market is quiet: no big move expected"),
         ("gate NORMAL", "No big move expected in the next 12 hours"),
         ("gate UNKNOWN", "Not enough data to read the market"),
         ("weekend", "Weekend: Jarvus doesn't start BTC, ETH or SOL trades"),
         ("no playbook", "No buy setup on the chart right now"),
         ("BTC below", "Bitcoin is in a long downtrend: meme coins are off"),
         ("BTC 4h", "Bitcoin is falling short-term: meme coins wait"),
         ("7 PM", "Meme coins are off between 7 PM and midnight"),
         ("cost", "Fees would eat too much of this trade")]


def plain(why):
    out = []
    for w in why:
        for k, v in PLAIN:
            if w.startswith(k) and v not in out:
                out.append(v)
                break
    return out or ["Waiting for the right moment"]


def serial(r):
    """A jarvus.evaluate() result made JSON-safe."""
    d = {k: v for k, v in r.items() if k != "mt"}
    d["mt"] = r["mt"].isoformat() if isinstance(r.get("mt"), datetime) else r.get("mt")
    return d


# ------------------------------------------------------------------ Windows niceties (no-ops elsewhere)
def set_awake(on):
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | (0x00000001 if on else 0))
        except Exception:                                         # noqa: BLE001
            pass


def set_startup(on):
    if not sys.platform.startswith("win"):
        return False
    try:
        import winreg
        key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\CurrentVersion\Run", 0, winreg.KEY_SET_VALUE)
        if on:
            target = f'"{sys.executable}" --minimized' if FROZEN else \
                f'"{sys.executable.replace("python.exe", "pythonw.exe")}" "{os.path.abspath(__file__)}" --minimized'
            winreg.SetValueEx(key, "Jarvus", 0, winreg.REG_SZ, target)
        else:
            try:
                winreg.DeleteValue(key, "Jarvus")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception as e:                                        # noqa: BLE001
        print("startup setting failed:", type(e).__name__)
        return False


def chime(kind="buy"):
    notes = {"buy": [(784, 110), (1047, 110), (1319, 220)], "sell": [(1319, 140), (988, 140), (784, 260)]}[kind]
    if sys.platform.startswith("win"):
        try:
            import winsound
            for f, d in notes:
                winsound.Beep(f, d)
        except Exception:                                         # noqa: BLE001
            pass


# ------------------------------------------------------------------ the engine (background thread)
class Engine(threading.Thread):
    def __init__(self, out_q, get_settings, get_positions):
        super().__init__(daemon=True)
        self.q, self.get_settings, self.get_positions = out_q, get_settings, get_positions
        self.force = threading.Event()
        self.next_scan = 0.0
        self.next_pos = 0.0

    def run(self):
        while True:
            t = time.time()
            if self.force.is_set() or t >= self.next_scan:
                self.force.clear()
                self.next_scan = t + SCAN_EVERY
                self.q.put(("scanning", self.next_scan))
                self.scan()
            if t >= self.next_pos and self.get_positions():
                self.next_pos = t + POS_EVERY
                self.check_positions()
            self.force.wait(1.0)

    def scan(self):
        account, fees = self.get_settings()
        jv._BTC.clear()
        results, errors = [], []
        for c in COINS:
            try:
                results.append(jv.evaluate(c, account, fees))
            except (Exception, SystemExit) as e:                  # noqa: BLE001
                errors.append(c)
                print(f"{datetime.now():%m-%d %H:%M} {c}: {type(e).__name__}: {str(e)[:120]}")
        self.q.put(("scan", results, errors, now_ms(), self.next_scan))

    def check_positions(self):
        out = {}
        for p in self.get_positions():
            base, since = p["coin"], p.get("checked_ms", p["opened_ms"])
            try:
                age_min = (now_ms() - since) / 60000
                if age_min <= 1400:
                    rows = fetch_coinbase(base, "USD", "5m", int(age_min / 5) + 3)
                    rows = [r for r in rows if r[0] + 300_000 > since]
                else:
                    rows = fetch_coinbase(base, "USD", "1h", min(300, int(age_min / 60) + 3))
                    rows = [r for r in rows if r[0] + 3_600_000 > since]
                if rows:
                    out[p["id"]] = (rows[-1][4], max(r[2] for r in rows), min(r[3] for r in rows), now_ms())
            except Exception as e:                                # noqa: BLE001
                print(f"{datetime.now():%m-%d %H:%M} price {base}: {type(e).__name__}")
        self.q.put(("prices", out))


# ------------------------------------------------------------------ the window
class App:
    W, H = 440, 760

    def __init__(self, root, minimized=False, demo=None):
        self.root, self.demo = root, demo
        self.cfg = load_cfg()
        self.q = queue.Queue()
        self.page = "main"
        self.overlay = None              # None | "welcome" | "close" | ("why", coin)
        self.hover = None
        self.scan_state = {"busy": True, "next": time.time() + 5, "last": None, "errors": [], "results": {}}
        self.phase = 0.0
        self.entry = None
        self.selected = None
        self.lock = threading.Lock()
        self.dot_color = C["green"]
        self.toast = None
        self.radar = (0, 0, 0)

        root.title("Jarvus")
        root.configure(bg=C["bg"])
        self.s = max(1.0, root.winfo_fpixels("1i") / 96.0)
        h = min(self.H, int((root.winfo_screenheight() - 90) / self.s))
        self.Hh = h
        root.geometry(f"{int(self.W * self.s)}x{int(h * self.s)}")
        root.resizable(False, False)
        root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.cv = tk.Canvas(root, width=self.W * self.s, height=h * self.s, bg=C["bg"], highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        self.fonts()
        self.icon()
        if not self.cfg["welcomed"] and not demo:
            self.overlay = "welcome"
        set_awake(self.cfg["awake"])
        if demo:
            self.load_demo(demo)
        else:
            self.engine = Engine(self.q, self.settings, self.open_positions)
            self.engine.start()
        if minimized:
            root.after(300, root.iconify)
        self.draw()
        root.after(40, self.animate)
        root.after(200, self.pump)
        root.after(1000, self.tick)

    # ---------------------------------------------------------- setup
    def fonts(self):
        fam = set(tkfont.families())
        pick = lambda *names: next((n for n in names if n in fam), "TkDefaultFont")   # noqa: E731
        base = pick("Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue", "DejaVu Sans")
        semi = pick("Segoe UI Semibold", "Segoe UI Variable Display Semib", base)
        disp = pick("Segoe UI Variable Display", "Segoe UI", "Inter", base)
        mono = pick("Cascadia Mono", "Consolas", "DejaVu Sans Mono")
        F = lambda f, s, w="normal": tkfont.Font(family=f, size=s, weight=w)       # noqa: E731
        self.f = {"logo": F(disp, 13, "bold"), "pill": F(semi, 9), "h0": F(disp, 30, "bold"), "h1": F(disp, 19, "bold"),
                  "h2": F(semi, 12), "body": F(base, 10), "small": F(base, 9), "tiny": F(base, 8), "num": F(disp, 17, "bold"),
                  "numS": F(semi, 11), "btn": F(semi, 11), "label": F(semi, 8), "mono": F(mono, 11, "bold")}

    def icon(self):
        try:
            png = make_png(64)
            import base64
            self._icon = tk.PhotoImage(data=base64.b64encode(png).decode())
            self.root.iconphoto(True, self._icon)
        except Exception:                                         # noqa: BLE001
            pass

    def settings(self):
        with self.lock:
            return float(self.cfg["account"]), self.cfg["fees"]

    def open_positions(self):
        with self.lock:
            return [dict(p) for p in self.cfg["positions"] if not p.get("exit")]

    def save(self):
        with self.lock:
            wt.save_json(CFG_PATH, self.cfg)

    # ---------------------------------------------------------- engine messages
    def pump(self):
        try:
            while True:
                msg = self.q.get_nowait()
                if msg[0] == "scanning":
                    self.scan_state.update(busy=True, next=msg[1])
                elif msg[0] == "scan":
                    self.on_scan(*msg[1:])
                elif msg[0] == "prices":
                    self.on_prices(msg[1])
                elif msg[0] == "show":
                    self.bring_front()
                self.draw()
        except queue.Empty:
            pass
        self.root.after(200, self.pump)

    def on_scan(self, results, errors, ts, nxt):
        self.scan_state.update(busy=False, last=ts, next=nxt, errors=errors)
        t = now_ms()
        held = {p["coin"] for p in self.open_positions()}
        for sym, s in list(self.cfg["signals"].items()):
            if t >= s["expires_ms"]:
                del self.cfg["signals"][sym]
        for r in results:
            coin = r["sym"].split("-")[0]
            self.scan_state["results"][coin] = r
            st = self.cfg["coins"].setdefault(coin, {})
            if r["verdict"] == "BUY" and coin not in held and coin not in self.cfg["signals"]:
                block = self.blocked(coin)
                if block:
                    st["blocked"] = block
                elif wt.should_alert(st, "BUY", t):
                    self.cfg["signals"][coin] = {"plan": serial(r), "created_ms": t, "expires_ms": t + SIGNAL_VALID_H * 3_600_000}
                    st["last_alert_ms"] = t
                    self.selected = coin
                    self.alert(f"BUY {coin}", f"Buy {jv.px(r['entry'])} · Sell {jv.px(r['target'])} · Stop {jv.px(r['stop'])}",
                               wt.buy_message(r), "buy")
            else:
                st.pop("blocked", None)
            st["was_buy"] = r["verdict"] == "BUY"
        self.save()

    def blocked(self, coin):
        """Jarvus's account rules that the scan itself can't know: open trades, trades today, losing streak."""
        today = datetime.now().date()
        opened = self.open_positions()
        if coin in MAJORS and any(p["coin"] in MAJORS for p in opened):
            return "Already holding one of BTC, ETH, SOL"
        if coin not in MAJORS and sum(p["coin"] not in MAJORS for p in opened) >= 2:
            return "Already holding 2 meme coins"
        todays = [p for p in self.cfg["positions"] + self.cfg["history"]
                  if datetime.fromtimestamp(p["opened_ms"] / 1000).date() == today]
        if coin in MAJORS and sum(p["coin"] in MAJORS for p in todays) >= 2:
            return "2 BTC/ETH/SOL trades today already"
        closed_today = [h for h in self.cfg["history"] if datetime.fromtimestamp(h["closed_ms"] / 1000).date() == today]
        if len(closed_today) >= 3 and all(h["exit"] == "stop" for h in closed_today[-3:]):
            return "3 losses in a row today: done until tomorrow"
        return None

    def on_prices(self, prices):
        for p in self.cfg["positions"]:
            got = prices.get(p["id"])
            if not got or p.get("exit"):
                continue
            last, hi, lo, ts = got
            p["last"], p["checked_ms"] = last, ts
            p["hi"], p["lo"] = max(p.get("hi", hi), hi), min(p.get("lo", lo), lo)
            reason = None
            if lo <= p["stop"]:
                reason = "stop"
            elif hi >= p["target"]:
                reason = "target"
            elif now_ms() >= p["expires_ms"]:
                reason = "time"
            if reason:
                p["exit"], p["exit_ms"] = reason, now_ms()
                px = {"stop": p["stop"], "target": p["target"], "time": last}[reason]
                p["exit_px"] = px
                pct = (px / p["entry"] - 1) * 100
                words = {"target": f"Target reached ({pct:+.1f}%)", "stop": f"Stop-loss hit ({pct:+.1f}%)",
                         "time": f"96 hours are up ({pct:+.1f}%)"}[reason]
                self.alert(f"SELL {p['coin']}", words, f"SELL {p['coin']} now. {words}. Price {jv.px(last)}.", "sell")
        self.save()

    def alert(self, title, short, long, kind):
        if self.demo:
            return
        self.bring_front(flash=True)
        if self.cfg["sound"]:
            threading.Thread(target=chime, args=(kind,), daemon=True).start()
        threading.Thread(target=self._send, args=(f"Jarvus · {title}", short, long), daemon=True).start()

    @staticmethod
    def _send(title, short, long):
        cfg = wt.settings()
        wt.send_desktop(title, short)
        wt.send_phone(cfg, title, long, priority="high", tags="rotating_light")
        wt.send_chat(cfg, title, long)

    def bring_front(self, flash=False):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(2500, lambda: self.root.attributes("-topmost", False))
        except tk.TclError:
            pass

    # ---------------------------------------------------------- user actions
    def act(self, name, *arg):
        if name == "bought":
            coin = arg[0]
            s = self.cfg["signals"].pop(coin, None)
            if s:
                p = s["plan"]
                t = now_ms()
                self.cfg["positions"].append({"id": f"{coin}-{t}", "coin": coin, "entry": p["entry"], "stop": p["stop"],
                                              "target": p["target"], "units": p["units"], "notional": p["notional"],
                                              "opened_ms": t, "expires_ms": t + HOLD_H * 3_600_000, "last": p["close"]})
                if not self.demo:
                    self.engine.next_pos = 0
        elif name == "skip":
            self.cfg["signals"].pop(arg[0], None)
        elif name == "sold":
            pid = arg[0]
            for p in list(self.cfg["positions"]):
                if p["id"] == pid:
                    self.cfg["positions"].remove(p)
                    p.setdefault("exit", "manual")
                    p["closed_ms"] = now_ms()
                    self.cfg["history"] = (self.cfg["history"] + [p])[-200:]
        elif name == "select":
            self.selected = arg[0]
            if arg[0] not in self.cfg["signals"]:
                self.overlay = ("why", arg[0])
        elif name == "page":
            self.commit_entry()
            self.page = arg[0]
        elif name == "fees":
            self.cfg["fees"] = arg[0]
            self.rescan()
        elif name == "toggle":
            k = arg[0]
            self.cfg[k] = not self.cfg[k]
            if k == "awake":
                set_awake(self.cfg[k])
            if k == "startup" and not set_startup(self.cfg[k]):
                self.cfg[k] = False
        elif name == "overlay":
            self.overlay = arg[0]
            if arg[0] is None:
                self.cfg["welcomed"] = True
        elif name == "minimize":
            self.overlay = None
            self.root.iconify()
        elif name == "quit":
            self.save()
            self.root.destroy()
            return
        elif name == "phone_setup":
            self.make_topic()
            self.page = "phone"
        elif name == "phone_test":
            threading.Thread(target=self._send, args=("Jarvus · test", "Alerts work. A real one: BUY SOL · Buy 121.07 · Sell 129.47 · Stop 116.87",
                                                      "Alerts work. A real one looks like:\nSOL $121.19 → BUY\nBuy (limit) 121.07 · Sell 129.47 · Stop 116.87"),
                             daemon=True).start()
            self.toast = ("Test alert sent", time.time())
        elif name == "phone_copy":
            self.root.clipboard_clear()
            self.root.clipboard_append(wt.settings()["topic"] or "")
            self.toast = ("Copied", time.time())
        elif name == "phone_off":
            c = wt.load_json(wt.CONFIG, {})
            c.pop("ntfy_topic", None)
            wt.save_json(wt.CONFIG, c, private=True)
            self.page = "settings"
        elif name == "refresh":
            self.rescan()
        self.save()
        self.draw()

    def make_topic(self):
        c = wt.load_json(wt.CONFIG, {})
        if not c.get("ntfy_topic"):
            import secrets
            c["ntfy_topic"] = "jarvus-" + secrets.token_urlsafe(18).replace("_", "x").replace("-", "y")
            wt.save_json(wt.CONFIG, c, private=True)

    def rescan(self):
        if not self.demo:
            self.engine.force.set()

    def commit_entry(self):
        if self.entry is not None:
            try:
                v = float(self.entry.get().replace("$", "").replace(",", "").strip())
                if 10 <= v <= 100_000_000 and v != self.cfg["account"]:
                    self.cfg["account"] = v
                    self.rescan()
            except ValueError:
                pass

    def on_close(self):
        self.overlay = "close"
        self.draw()

    # ---------------------------------------------------------- timing
    def tick(self):
        self.draw()
        self.root.after(1000, self.tick)

    def animate(self):
        self.phase = (self.phase + 0.04) % 1.0
        s = self.s
        for k in range(3):
            items = self.cv.find_withtag(f"ring{k}")
            if items:
                ph = (self.phase + k / 3) % 1.0
                cx, cy, r0 = self.radar
                r = r0 * (0.35 + 0.65 * ph)
                self.cv.coords(items[0], (cx - r) * s, (cy - r) * s, (cx + r) * s, (cy + r) * s)
                self.cv.itemconfigure(items[0], outline=mix(C["green"], C["bg"], 0.15 + 0.85 * ph))
        dot = self.cv.find_withtag("live")
        if dot:
            self.cv.itemconfigure(dot[0], fill=mix(self.dot_color, C["card"], 0.5 + 0.5 * math.cos(self.phase * 2 * math.pi) * 0.5))
        self.root.after(40, self.animate)

    # ---------------------------------------------------------- drawing primitives (logical 96-dpi pixels)
    def rr(self, x1, y1, x2, y2, r, fill, outline="", width=1, tag=None):
        r = min(r, (x2 - x1) / 2, (y2 - y1) / 2)
        pts = [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r, x2, y2 - r,
               x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r,
               x1, y1 + r, x1, y1]
        return self.cv.create_polygon(pts, smooth=True, splinesteps=20, fill=fill, outline=outline or fill, width=width,
                                      tags=tag)

    def t(self, x, y, text, font, color, anchor="nw", width=None, tag=None, justify="left"):
        kw = {"width": width * self.s} if width else {}
        return self.cv.create_text(x, y, text=text, font=self.f[font], fill=color, anchor=anchor, tags=tag, justify=justify, **kw)

    def button(self, key, x1, y1, x2, y2, label, kind="primary", action=None, font="btn"):
        hov = self.hover == key
        fill, fg, line = {"primary": (C["green"], "#06210F", C["green"]), "ghost": (C["card2"], C["text"], C["line"]),
                          "danger": (C["red"], "#2A0710", C["red"]), "quiet": (C["bg"], C["muted"], C["bg"]),
                          "blue": (C["blue"], "#061629", C["blue"])}[kind]
        if hov:
            fill = mix(fill, "#FFFFFF", 0.85) if kind != "quiet" else C["card"]
        tag = f"b_{key}"
        self.rr(x1, y1, x2, y2, (y2 - y1) / 2 if y2 - y1 < 44 else 12, fill, line, 1, tag)
        self.t((x1 + x2) / 2, (y1 + y2) / 2, label, font, fg, "center", tag=tag)
        self.bind(tag, key, action)

    def bind(self, tag, key, action):
        self.cv.tag_bind(tag, "<Button-1>", lambda e: action() if action else None)
        self.cv.tag_bind(tag, "<Enter>", lambda e: self._hover(key))
        self.cv.tag_bind(tag, "<Leave>", lambda e: self._hover(None))

    def _hover(self, key):
        if self.hover != key:
            self.hover = key
            self.cv.configure(cursor="hand2" if key else "")
            self.draw()

    # ---------------------------------------------------------- the screen
    def draw(self):
        cv = self.cv
        if self.entry is not None and self.page != "settings":
            self.entry.destroy()
            self.entry = None
        cv.delete("all")
        self.radar = (0, 0, 0)
        W, H = self.W, self.Hh
        if self.page == "main":
            self.draw_main(W, H)
        elif self.page == "settings":
            self.draw_settings(W, H)
        elif self.page == "phone":
            self.draw_phone(W, H)
        if self.overlay:
            self.draw_overlay(W, H)
        toast = self.toast
        if toast and time.time() - toast[1] < 2.2:
            w = self.f["small"].measure(toast[0]) / self.s + 32
            self.rr(W / 2 - w / 2, H - 92, W / 2 + w / 2, H - 62, 15, C["text"])
            self.t(W / 2, H - 77, toast[0], "small", C["bg"], "center")
        cv.scale("all", 0, 0, self.s, self.s)

    def header(self, W, sub=None):
        self.rr(20, 22, 50, 52, 9, C["card2"], C["line"])
        self.cv.create_oval(28, 30, 42, 44, outline=C["green"], width=2)
        self.cv.create_oval(33, 35, 37, 39, fill=C["green"], outline="")
        self.t(60, 37, "JARVUS", "logo", C["text"], "w")
        ss = self.scan_state
        if self.demo:
            label, self.dot_color = "Watching", C["green"]
        elif ss["errors"] and len(ss["errors"]) == len(COINS):
            label, self.dot_color = "Offline · retrying", C["amber"]
        elif ss["busy"]:
            label, self.dot_color = "Checking the market…", C["blue"]
        else:
            left = max(0, int(ss["next"] - time.time()))
            label, self.dot_color = f"Watching · next check {left // 60}:{left % 60:02d}", C["green"]
        w = self.f["pill"].measure(label) / self.s + 36
        self.rr(W - 20 - w, 24, W - 20, 50, 13, C["card"], C["line"])
        self.cv.create_oval(W - 20 - w + 12, 33, W - 20 - w + 20, 41, fill=self.dot_color, outline="", tags="live")
        self.t(W - 20 - w + 27, 37, label, "pill", C["muted"], "w")

    def draw_main(self, W, H):
        self.header(W)
        y = 68
        exits = [p for p in self.cfg["positions"] if p.get("exit")]
        holds = [p for p in self.cfg["positions"] if not p.get("exit")]
        sigs = self.cfg["signals"]
        sel = self.selected if self.selected in sigs else (next(iter(sigs)) if sigs else None)
        if exits:
            y = self.card_sell(exits[0], y, W)
        elif sel:
            y = self.card_buy(sel, sigs[sel], y, W)
        elif not holds:
            y = self.card_quiet(y, W)
        for p in holds[:2]:
            y = self.card_hold(p, y, W)
        y = self.markets(y + 6, W, H)
        if H - 60 - y >= 112 and not sigs and not exits:
            self.how(y + 16, W)
        # footer
        self.button("settings", 20, H - 46, 118, H - 18, "⚙  Settings", "quiet", lambda: self.act("page", "settings"), "small")
        self.t(W - 20, H - 32, "Not advice · you place the orders", "tiny", C["dim"], "e")

    def card_quiet(self, y, W):
        h = 196
        self.rr(20, y, W - 20, y + h, 18, C["card"], C["line"])
        cx, cy = W / 2, y + 62
        self.radar = (cx, cy, 44)
        for k in range(3):
            self.cv.create_oval(cx, cy, cx, cy, outline=C["green"], width=1.5, tags=f"ring{k}")
        self.cv.create_oval(cx - 6, cy - 6, cx + 6, cy + 6, fill=C["green"], outline="")
        ss = self.scan_state
        if not ss["last"] and not self.demo:
            title, sub = "Reading the market…", "First check takes about 20 seconds."
        elif ss["errors"] and len(ss["errors"]) == len(COINS):
            title, sub = "Can't reach the market", "Check your internet. Jarvus keeps trying every 10 minutes."
        else:
            title = "Nothing to buy right now"
            sub = "Jarvus is watching 5 coins around the clock. When it's time, you'll hear a sound and see the plan here."
        self.t(W / 2, y + 122, title, "h1", C["text"], "center")
        self.t(W / 2, y + 160, sub, "small", C["muted"], "center", width=W - 90, justify="center")
        return y + h + 12

    def card_buy(self, coin, s, y, W):
        p = s["plan"]
        h = 332
        self.rr(20, y, W - 20, y + h, 18, C["green_d"], C["green_b"], 1.5)
        self.t(40, y + 20, "TIME TO BUY", "label", C["green"])
        self.t(40, y + 34, f"{coin}", "h0", C["text"])
        self.t(W - 40, y + 26, NAMES[coin], "small", C["muted"], "ne")
        self.t(W - 40, y + 46, f"${jv.px(p['close'])}", "h2", C["text"], "ne")
        rows = [("Buy at", p["entry"], "limit order", C["text"]),
                ("Sell at", p["target"], f"take profit  {(p['target'] / p['entry'] - 1) * 100:+.1f}%", C["green"]),
                ("Stop at", p["stop"], f"stop-loss  {(p['stop'] / p['entry'] - 1) * 100:+.1f}%", C["red"])]
        yy = y + 86
        for label, val, note, col in rows:
            self.rr(36, yy, W - 36, yy + 44, 12, C["bg"], C["line"])
            self.t(52, yy + 22, label, "body", C["muted"], "w")
            self.t(W - 52, yy + 22, jv.px(val), "num", col, "e")
            self.t(140, yy + 22, note, "tiny", C["dim"], "w")
            yy += 50
        self.t(W / 2, yy + 8, f"Size ${p['notional']:,.0f}   ·   cancel if not filled by {clock(s['expires_ms'], True)}",
               "small", C["muted"], "n")
        by = y + h - 54
        self.button("bought", 36, by, W / 2 + 40, by + 40, "I bought it", "primary", lambda: self.act("bought", coin))
        self.button("skip", W / 2 + 50, by, W - 36, by + 40, "Skip", "ghost", lambda: self.act("skip", coin))
        return y + h + 12

    def card_hold(self, p, y, W):
        h = 150
        last = p.get("last") or p["entry"]
        pct = (last / p["entry"] - 1) * 100
        self.rr(20, y, W - 20, y + h, 18, C["card"], C["line"])
        self.t(40, y + 20, "HOLDING", "label", C["blue"])
        self.t(40, y + 36, p["coin"], "h1", C["text"])
        self.t(W - 40, y + 22, f"${jv.px(last)}", "h2", C["text"], "ne")
        self.t(W - 40, y + 46, f"{pct:+.2f}%", "small", C["green"] if pct >= 0 else C["red"], "ne")
        x1, x2, by = 40, W - 40, y + 92
        lo, hi = p["stop"], p["target"]
        f = min(1, max(0, (last - lo) / (hi - lo))) if hi > lo else 0.5
        fe = (p["entry"] - lo) / (hi - lo)
        self.rr(x1, by - 3, x2, by + 3, 3, C["chip"])
        mid = x1 + (x2 - x1) * fe
        bar_to = x1 + (x2 - x1) * f
        self.rr(min(mid, bar_to), by - 3, max(mid, bar_to) + 0.1, by + 3, 3, C["green"] if f >= fe else C["red"])
        self.cv.create_line(mid, by - 8, mid, by + 8, fill=C["dim"], width=1)
        self.cv.create_oval(bar_to - 7, by - 7, bar_to + 7, by + 7, fill=C["text"], outline=C["bg"], width=2)
        self.t(x1, by + 14, f"Stop {jv.px(lo)}", "tiny", C["red"])
        self.t(x2, by + 14, f"Sell {jv.px(hi)}", "tiny", C["green"], "ne")
        left_h = max(0, (p["expires_ms"] - now_ms()) / 3_600_000)
        self.t(W / 2, by + 14, f"{left_h:.0f}h left", "tiny", C["dim"], "n")
        self.button(f"sold_{p['id']}", W - 132, y + h - 26, W - 40, y + h - 6, "I sold it", "ghost",
                    lambda pid=p["id"]: self.act("sold", pid), "tiny")
        return y + h + 12

    def card_sell(self, p, y, W):
        good = p["exit"] == "target"
        h = 212
        col, dark = (C["green"], C["green_d"]) if good else (C["red"], C["red_d"])
        self.rr(20, y, W - 20, y + h, 18, dark, col, 1.5)
        self.t(40, y + 22, "TIME TO SELL", "label", col)
        self.t(40, y + 38, f"SELL {p['coin']}", "h0", C["text"])
        pct = (p["exit_px"] / p["entry"] - 1) * 100
        why = {"target": "Your target was reached", "stop": "Your stop-loss was hit", "time": "96 hours are up",
               "manual": ""}[p["exit"]]
        self.t(40, y + 92, f"{why}  ·  {pct:+.1f}%", "h2", col)
        self.t(40, y + 116, f"Bought at {jv.px(p['entry'])}  ·  now {jv.px(p.get('last') or p['exit_px'])}", "small", C["muted"])
        self.button(f"sold_{p['id']}", 36, y + h - 56, W - 36, y + h - 16, "I sold it", "primary" if good else "danger",
                    lambda: self.act("sold", p["id"]))
        return y + h + 12

    def how(self, y, W):
        self.t(24, y, "HOW IT WORKS", "label", C["dim"])
        steps = [("1", "You get an alert", "sound + pop-up"), ("2", "You place orders", "buy · sell · stop"),
                 ("3", "Jarvus says sell", "when it's time")]
        w = (W - 40 - 16) / 3
        for k, (n, a, b) in enumerate(steps):
            x = 20 + k * (w + 8)
            self.rr(x, y + 18, x + w, y + 92, 14, C["card"], C["line"])
            self.cv.create_oval(x + 12, y + 30, x + 32, y + 50, fill=C["chip"], outline="")
            self.t(x + 22, y + 40, n, "label", C["green"], "center")
            self.t(x + 12, y + 58, a, "small", C["text"], width=w - 20)
            self.t(x + 12, y + 76, b, "tiny", C["dim"], width=w - 20)

    def markets(self, y, W, H):
        self.t(24, y, "MARKETS", "label", C["dim"])
        ss = self.scan_state
        if ss["last"]:
            self.t(W - 24, y, f"checked {clock(ss['last'])}", "tiny", C["dim"], "ne")
        y += 20
        rowh = 50
        room = H - 60 - y
        rows = COINS if room >= rowh * len(COINS) else COINS[:max(1, int(room // rowh))]
        self.rr(20, y, W - 20, y + rowh * len(rows), 16, C["card"], C["line"])
        held = {p["coin"] for p in self.cfg["positions"]}
        for k, coin in enumerate(rows):
            ry = y + k * rowh
            tag = f"row_{coin}"
            if self.hover == tag:
                self.rr(22, ry + 2, W - 22, ry + rowh - 2, 14, C["card2"], tag=tag)
            if k:
                self.cv.create_line(36, ry, W - 36, ry, fill=C["line"])
            self.cv.create_oval(36, ry + 10, 66, ry + 40, fill=mix(COIN_COLOR[coin], C["card"], 0.22), outline="", tags=tag)
            self.t(51, ry + 25, coin[0], "h2", COIN_COLOR[coin], "center", tag=tag)
            self.t(78, ry + 9, NAMES[coin], "h2", C["text"], tag=tag)
            r = ss["results"].get(coin)
            sub = f"{coin} · {jv.move(r)}" if r else coin
            self.t(78, ry + 28, sub, "tiny", C["dim"], tag=tag)
            price = f"${jv.px(r['close'])}" if r else "—"
            self.t(W - 124, ry + 25, price, "numS", C["text"], "e", tag=tag)
            if coin in held:
                chip, cf, cb = "Holding", C["blue"], C["blue_d"]
            elif coin in self.cfg["signals"]:
                chip, cf, cb = "BUY", "#06210F", C["green"]
            elif r and r["verdict"] == "NO":
                chip, cf, cb = "Off", C["dim"], C["chip"]
            else:
                chip, cf, cb = "Wait", C["muted"], C["chip"]
            self.rr(W - 108, ry + 13, W - 38, ry + 37, 12, cb, tag=tag)
            self.t(W - 73, ry + 25, chip, "label", cf, "center", tag=tag)
            self.bind(tag, tag, lambda c=coin: self.act("select", c))
        return y + rowh * len(rows)

    # ---------------------------------------------------------- settings
    def draw_settings(self, W, H):
        self.button("back", 16, 22, 96, 52, "‹  Back", "quiet", lambda: self.act("page", "main"), "body")
        self.t(W / 2, 37, "Settings", "h2", C["text"], "center")
        y = 72
        self.t(24, y, "YOUR BALANCE", "label", C["dim"])
        self.rr(20, y + 18, W - 20, y + 70, 14, C["card"], C["line"])
        self.t(40, y + 44, "$", "num", C["muted"], "w")
        if self.entry is None:
            self.entry = tk.Entry(self.root, font=self.f["num"], bg=C["card"], fg=C["text"], insertbackground=C["text"],
                                  relief="flat", highlightthickness=0, bd=0)
            self.entry.insert(0, f"{self.cfg['account']:,.0f}")
            self.entry.bind("<Return>", lambda e: (self.commit_entry(), self.save(), self.draw()))
            self.entry.bind("<FocusOut>", lambda e: (self.commit_entry(), self.save()))
        self.cv.create_window(60, y + 44, window=self.entry, anchor="w", width=(W - 160) * self.s)
        self.t(W - 40, y + 44, "sizes every trade", "tiny", C["dim"], "e")
        y += 92
        self.t(24, y, "YOUR EXCHANGE", "label", C["dim"])
        self.rr(20, y + 18, W - 20, y + 62, 14, C["card"], C["line"])
        seg = (W - 48) / len(FEES)
        for k, (key, label) in enumerate(FEES):
            x1 = 24 + k * seg
            on = self.cfg["fees"] == key
            tag = f"fee_{key}"
            if on:
                self.rr(x1 + 2, y + 22, x1 + seg - 2, y + 58, 11, C["card2"], C["line"], tag=tag)
            self.t(x1 + seg / 2, y + 40, label, "btn", C["text"] if on else C["muted"], "center", tag=tag)
            self.cv.create_rectangle(x1, y + 20, x1 + seg, y + 60, fill="", outline="", tags=tag)
            self.bind(tag, tag, lambda k2=key: self.act("fees", k2))
        y += 84
        self.t(24, y, "RUNNING 24/7", "label", C["dim"])
        toggles = [("startup", "Start Jarvus when Windows starts", sys.platform.startswith("win")),
                   ("awake", "Keep the computer awake", True), ("sound", "Play a sound on alerts", True)]
        toggles = [t for t in toggles if t[2]]
        self.rr(20, y + 18, W - 20, y + 18 + 52 * len(toggles), 14, C["card"], C["line"])
        for k, (key, label, _) in enumerate(toggles):
            ty = y + 18 + 52 * k
            if k:
                self.cv.create_line(36, ty, W - 36, ty, fill=C["line"])
            tag = f"tg_{key}"
            self.t(40, ty + 26, label, "body", C["text"], "w", tag=tag)
            on = self.cfg[key]
            self.rr(W - 84, ty + 14, W - 40, ty + 38, 12, C["green"] if on else C["chip"], tag=tag)
            kx = W - 52 if on else W - 72
            self.cv.create_oval(kx - 9, ty + 17, kx + 9, ty + 35, fill="#FFFFFF" if on else C["muted"], outline="", tags=tag)
            self.cv.create_rectangle(24, ty + 2, W - 24, ty + 50, fill="", outline="", tags=tag)
            self.bind(tag, tag, lambda k2=key: self.act("toggle", k2))
        y += 18 + 52 * len(toggles) + 22
        self.t(24, y, "PHONE ALERTS", "label", C["dim"])
        self.rr(20, y + 18, W - 20, y + 72, 14, C["card"], C["line"])
        on = bool(wt.settings()["topic"])
        self.t(40, y + 45, "On — alerts also go to your phone" if on else "Get alerts on your phone too", "body", C["text"], "w")
        self.button("phone", W - 128, y + 30, W - 36, y + 60, "Manage" if on else "Set up", "ghost",
                    lambda: self.act("phone_setup"), "small")
        self.t(W / 2, H - 30, f"Jarvus {VERSION} · v7 rules · checks every 10 minutes · never places orders", "tiny", C["dim"], "center")

    def draw_phone(self, W, H):
        self.button("back", 16, 22, 96, 52, "‹  Back", "quiet", lambda: self.act("page", "settings"), "body")
        self.t(W / 2, 37, "Phone alerts", "h2", C["text"], "center")
        topic = wt.settings()["topic"] or ""
        y = 80
        steps = ["Install the free app “ntfy” on your phone.", "Tap  +  then “Subscribe to topic”.",
                 "Type this name exactly, then tap Subscribe:"]
        for k, s in enumerate(steps):
            self.cv.create_oval(24, y + k * 40, 48, y + 24 + k * 40, fill=C["card2"], outline=C["line"])
            self.t(36, y + 12 + k * 40, str(k + 1), "small", C["text"], "center")
            self.t(60, y + 12 + k * 40, s, "body", C["text"], "w")
        y += 132
        self.rr(20, y, W - 20, y + 64, 14, C["card"], C["green_b"], 1.5)
        self.t(W / 2, y + 32, topic, "mono", C["green"], "center")
        y += 80
        self.button("copy", 20, y, W / 2 - 6, y + 42, "Copy name", "ghost", lambda: self.act("phone_copy"))
        self.button("test", W / 2 + 6, y, W - 20, y + 42, "Send test", "primary", lambda: self.act("phone_test"))
        y += 64
        self.t(W / 2, y, "Keep this name private: anyone who has it can read your alerts.\nAlerts go through the free ntfy.sh "
               "service and contain only the plan (coin and prices).", "tiny", C["muted"], "n", width=W - 60, justify="center")
        self.button("off", W / 2 - 70, H - 64, W / 2 + 70, H - 36, "Turn phone alerts off", "quiet", lambda: self.act("phone_off"), "tiny")

    # ---------------------------------------------------------- overlays
    def draw_overlay(self, W, H):
        self.cv.create_rectangle(0, 0, W, H, fill="#000000", stipple="gray50", outline="", tags="veil")
        self.cv.tag_bind("veil", "<Button-1>", lambda e: None)
        ov = self.overlay
        if ov == "welcome":
            h = 330
            y = (H - h) / 2
            self.rr(28, y, W - 28, y + h, 20, C["card"], C["line"])
            self.t(W / 2, y + 34, "Jarvus is watching", "h1", C["text"], "center")
            lines = ["Leave this app open. It checks the market every 10 minutes, day and night.",
                     "When it's time to buy, it pops up with a sound and shows the plan: buy price, sell price and stop-loss.",
                     "Tap “I bought it” and Jarvus watches the trade and tells you when to sell."]
            yy = y + 72
            for s in lines:
                self.cv.create_oval(48, yy + 5, 56, yy + 13, fill=C["green"], outline="")
                tid = self.t(68, yy, s, "body", C["muted"], width=W - 124)
                bb = self.cv.bbox(tid)
                yy += (bb[3] - bb[1]) / self.s + 14 if bb else 40
            self.t(W / 2, y + h - 92, f"Balance ${self.cfg['account']:,.0f} · {dict(FEES)[self.cfg['fees']]} fees · change in Settings",
                   "tiny", C["dim"], "center")
            self.button("ok", 48, y + h - 66, W - 48, y + h - 24, "Start watching", "primary", lambda: self.act("overlay", None))
        elif ov == "close":
            h = 196
            y = (H - h) / 2
            self.rr(28, y, W - 28, y + h, 20, C["card"], C["line"])
            self.t(W / 2, y + 32, "Keep watching?", "h1", C["text"], "center")
            self.t(W / 2, y + 62, "If you quit, Jarvus can't tell you when to buy or sell.", "small", C["muted"], "n",
                   width=W - 100, justify="center")
            self.button("min", 48, y + h - 66, W - 48, y + h - 26, "Keep watching (minimise)", "primary", lambda: self.act("minimize"))
            self.button("quit", W / 2 - 60, y + h - 22, W / 2 + 60, y + h - 2, "Quit Jarvus", "quiet", lambda: self.act("quit"), "tiny")
        elif isinstance(ov, tuple) and ov[0] == "why":
            coin = ov[1]
            r = self.scan_state["results"].get(coin)
            blocked = self.cfg["coins"].get(coin, {}).get("blocked")
            reasons = ([blocked] if blocked else []) + (plain(r["why"]) if r else ["Not checked yet"])
            held = [p for p in self.cfg["positions"] if p["coin"] == coin]
            h = 150 + 30 * len(reasons)
            y = (H - h) / 2
            self.rr(28, y, W - 28, y + h, 20, C["card"], C["line"])
            self.t(52, y + 26, NAMES[coin], "h1", C["text"])
            if r:
                self.t(W - 52, y + 32, f"${jv.px(r['close'])}", "h2", C["text"], "ne")
            if held:
                status = "You're holding this. Jarvus tells you when to sell."
                reasons = []
            else:
                status = "Why Jarvus isn't buying:" if (r and r["verdict"] != "BUY") or blocked else "Waiting for the next check"
            self.t(52, y + 70, status, "small", C["muted"])
            yy = y + 98
            for s in reasons:
                self.cv.create_oval(54, yy + 5, 60, yy + 11, fill=C["amber"], outline="")
                self.t(70, yy, s, "body", C["text"], width=W - 130)
                yy += 30
            if r:
                self.t(52, yy + 4, f"Next 12 hours: {jv.move(r)}. Direction can't be predicted.", "tiny", C["dim"])
            self.button("close_why", W / 2 - 60, y + h - 50, W / 2 + 60, y + h - 16, "OK", "ghost", lambda: self.act("overlay", None))

    # ---------------------------------------------------------- preview data (for screenshots only)
    def load_demo(self, which):
        t = now_ms()
        prices = {"SOL": 121.19, "ETH": 2679.0, "BTC": 84628.0, "DOGE": 0.09316, "BONK": 0.00000365}
        res = {}
        for c, px in prices.items():
            res[c] = {"sym": f"{c}-USD", "close": px, "gate": "NORMAL", "verdict": "WAIT", "why": ["gate NORMAL: trade only on LOUD",
                      "no playbook fired in the last 3 hours"], "mt": datetime.now()}
        self.scan_state.update(busy=False, last=t - 120_000, next=time.time() + 452, results=res)
        self.cfg.update(signals={}, positions=[], history=[], welcomed=True)
        if which in ("buy", "both"):
            p = {"sym": "SOL-USD", "close": 121.19, "entry": 121.07, "stop": 116.87, "target": 129.47, "notional": 173.0,
                 "risk_amt": 6.0, "units": 1.43, "verdict": "BUY", "gate": "LOUD", "setups": ["P7"], "mt": datetime.now().isoformat()}
            self.cfg["signals"]["SOL"] = {"plan": p, "created_ms": t, "expires_ms": t + 3 * 3_600_000}
            res["SOL"].update(gate="LOUD", verdict="BUY")
        if which in ("hold", "both", "sell"):
            self.cfg["positions"].append({"id": "BTC-1", "coin": "BTC", "entry": 83900.0, "stop": 80950.0, "target": 89800.0,
                                          "units": 0.002, "notional": 168.0, "opened_ms": t - 20 * 3_600_000,
                                          "expires_ms": t + 76 * 3_600_000, "last": 84628.0})
        if which == "sell":
            p = self.cfg["positions"][0]
            p.update(exit="target", exit_px=89800.0, last=89812.0)
        if which == "welcome":
            self.overlay = "welcome"
        if which == "why":
            self.overlay = ("why", "ETH")
        if which in ("settings", "phone"):
            self.page = which


# ------------------------------------------------------------------ colour + icon helpers
def mix(a, b, t):
    """Blend colour a toward b: t=1 → a, t=0 → b."""
    a, b = a.lstrip("#"), b.lstrip("#")
    ca = [int(a[i:i + 2], 16) for i in (0, 2, 4)]
    cb = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{round(x * t + y * (1 - t)):02X}" for x, y in zip(ca, cb))


def make_png(n):
    """The Jarvus mark (a radar on a dark rounded square) as a PNG, drawn pixel by pixel (no image libraries)."""
    import struct
    import zlib
    rows = []
    c = (n - 1) / 2
    rad = n * 0.22
    for y in range(n):
        row = bytearray([0])
        for x in range(n):
            dx, dy = x - c, y - c
            # rounded square mask with soft edge
            qx, qy = max(abs(dx) - (n / 2 - rad - 1), 0), max(abs(dy) - (n / 2 - rad - 1), 0)
            d = math.hypot(qx, qy) - rad
            alpha = max(0.0, min(1.0, 0.5 - d))
            r, g, b = 15, 20, 30
            dist = math.hypot(dx, dy) / (n / 2)
            for ring, w in ((0.62, 0.075), (0.38, 0.07)):
                k = max(0.0, 1 - abs(dist - ring) / w)
                r, g, b = r + (46 - r) * k, g + (224 - g) * k, b + (122 - b) * k
            k = max(0.0, min(1.0, (0.16 - dist) / 0.04 + 0.5))
            r, g, b = r + (46 - r) * k, g + (224 - g) * k, b + (122 - b) * k
            row += bytes([int(r), int(g), int(b), int(alpha * 255)])
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def make_ico(path):
    import struct
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [make_png(s) for s in sizes]
    head = struct.pack("<HHH", 0, 1, len(sizes))
    off = 6 + 16 * len(sizes)
    dirs = b""
    for s, data in zip(sizes, imgs):
        dirs += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), off)
        off += len(data)
    with open(path, "wb") as fh:
        fh.write(head + dirs + b"".join(imgs))


# ------------------------------------------------------------------ single instance
def claim_instance(q):
    """True if this is the only Jarvus running; otherwise asks the running one to come to the front."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        srv.bind(("127.0.0.1", PORT))
    except OSError:
        try:
            with socket.create_connection(("127.0.0.1", PORT), timeout=2) as s:
                s.sendall(b"show")
        except OSError:
            pass
        return False
    srv.listen(2)

    def serve():
        while True:
            try:
                conn, _ = srv.accept()
                with conn:
                    if conn.recv(16) == b"show":
                        q.put(("show",))
            except OSError:
                return
    threading.Thread(target=serve, daemon=True).start()
    return True


def main():
    args = sys.argv[1:]
    if "--make-ico" in args:
        make_ico(args[args.index("--make-ico") + 1])
        return 0
    demo = args[args.index("--demo") + 1] if "--demo" in args else None
    if sys.platform.startswith("win"):
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Jarvus.App")
        except Exception:                                         # noqa: BLE001
            pass
    q_boot = queue.Queue()
    if not demo and not claim_instance(q_boot):
        return 0
    root = tk.Tk()
    app = App(root, minimized="--minimized" in args, demo=demo)
    if not demo:
        def relay():
            try:
                while True:
                    app.q.put(q_boot.get_nowait())
            except queue.Empty:
                pass
            root.after(500, relay)
        relay()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
