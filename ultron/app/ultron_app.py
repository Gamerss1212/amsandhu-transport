#!/usr/bin/env python3
"""ULTRON — autonomous paper-trading terminal. 50 trained agents, one learned brain, runs 24/7.

Double-click and leave it open. Every hour Ultron's 50 agents read 9 crypto markets; the brain approves or refuses
every signal; approved ones become paper trades that Ultron manages by itself (limit entry, stop-loss, target,
96-hour limit). It pops up when it buys or sells so you can copy the trade on your exchange if you choose.
Paper money only: it does not connect to any exchange account.

  python ultron_app.py            (Windows build: Ultron.exe)
  python ultron_app.py --minimized
"""

from __future__ import annotations

import json
import math
import os
import queue
import random
import socket
import sys
import threading
import time
from datetime import datetime

FROZEN = getattr(sys, "frozen", False)
HERE = os.path.dirname(os.path.abspath(__file__))
if not FROZEN:
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "core"))
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "jarvus", "scripts"))

DATA = os.path.join(os.path.expanduser("~"), ".ultron")
os.makedirs(DATA, exist_ok=True)
if sys.stdout is None or sys.stderr is None:
    try:
        lp = os.path.join(DATA, "ultron.log")
        if os.path.exists(lp) and os.path.getsize(lp) > 2_000_000:
            os.replace(lp, lp + ".old")
        sys.stdout = sys.stderr = open(lp, "a", encoding="utf-8", buffering=1)
    except OSError:
        pass

import tkinter as tk                                              # noqa: E402
import tkinter.font as tkfont                                     # noqa: E402

import engine as en                                               # noqa: E402
import jarvus as jv                                               # noqa: E402
import watch as wt                                                # noqa: E402

VERSION = "1.0"
PORT = 47392
W0, H0 = 1440, 900
C = {"bg": "#EDF1F7", "panel": "#FFFFFF", "line": "#D9E0EB", "line2": "#E9EEF5", "text": "#0A1426", "muted": "#56657C",
     "dim": "#97A3B6", "blue": "#1F5BFF", "blue2": "#5B8CFF", "blue3": "#A9C2FF", "bluel": "#E8EFFF", "green": "#0E9F63",
     "greenl": "#E3F6EC", "red": "#E2474D", "redl": "#FDECEC", "amber": "#C98A0B", "amberl": "#FFF4DD", "ink": "#0B1F4D"}
FAM_COLOR = {"candle": "#1F5BFF", "chart": "#7A5CFF", "indicator": "#0EA5B7", "playbook": "#E07A1F"}
WHEN = {"any": "any time", "loud": "big moves", "trend": "uptrends", "loudtrend": "big moves + uptrend"}


def now_ms():
    return int(time.time() * 1000)


def hhmm(ms):
    return datetime.fromtimestamp(ms / 1000).strftime("%H:%M")


def mix(a, b, t):
    a, b = a.lstrip("#"), b.lstrip("#")
    ca = [int(a[i:i + 2], 16) for i in (0, 2, 4)]
    cb = [int(b[i:i + 2], 16) for i in (0, 2, 4)]
    return "#" + "".join(f"{max(0, min(255, round(x * t + y * (1 - t)))):02X}" for x, y in zip(ca, cb))


def money(v, sign=False):
    s = f"{abs(v):,.2f}"
    return (("+" if v >= 0 else "−") if sign else ("−" if v < 0 else "")) + "$" + s


# ------------------------------------------------------------------ Windows helpers (no-ops elsewhere)
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
            winreg.SetValueEx(key, "Ultron", 0, winreg.REG_SZ, target)
        else:
            try:
                winreg.DeleteValue(key, "Ultron")
            except FileNotFoundError:
                pass
        winreg.CloseKey(key)
        return True
    except Exception:                                             # noqa: BLE001
        return False


def chime(kind):
    if not sys.platform.startswith("win"):
        return
    try:
        import winsound
        for f, d in {"buy": [(880, 90), (1175, 90), (1568, 200)], "sell": [(1568, 110), (1175, 110), (880, 220)]}[kind]:
            winsound.Beep(f, d)
    except Exception:                                             # noqa: BLE001
        pass


# ------------------------------------------------------------------ the window
class App:
    def __init__(self, root, minimized=False, demo=None):
        self.root, self.demo = root, demo
        self.q = queue.Queue()
        self.cfg = wt.load_json(os.path.join(DATA, "app.json"), {})
        for k, v in (("sound", True), ("awake", True), ("startup", False), ("welcomed", False), ("coin", "BTC")):
            self.cfg.setdefault(k, v)
        self.overlay, self.hover, self.banner, self.entry, self.toast = None, None, None, None, None
        self.phase = 0.0
        sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
        self.S = max(0.55, min(sw * 0.97 / W0, (sh - 70) / H0, 1.6))
        root.title("ULTRON")
        root.configure(bg=C["bg"])
        root.geometry(f"{int(W0 * self.S)}x{int(H0 * self.S)}")
        root.minsize(int(W0 * self.S * 0.8), int(H0 * self.S * 0.8))
        root.protocol("WM_DELETE_WINDOW", lambda: self.set_overlay("close"))
        self.cv = tk.Canvas(root, width=W0 * self.S, height=H0 * self.S, bg=C["bg"], highlightthickness=0, bd=0)
        self.cv.pack(fill="both", expand=True)
        self.fonts()
        self.icon()
        if demo:
            self.eng = DemoEngine()
        else:
            self.eng = en.Engine(DATA, notify=lambda k, t, b: self.q.put(("alert", k, t, b)))
            self.eng.start()
        self.model = self.eng.model
        self.backtest = self.load_backtest()
        if not self.cfg["welcomed"] and not demo:
            self.overlay = "welcome"
        if demo in ("settings", "proof", "agents", "welcome"):
            self.overlay = demo
        set_awake(self.cfg["awake"])
        self.vortex_init()
        if minimized:
            root.after(300, root.iconify)
        self.draw()
        root.after(33, self.animate)
        root.after(250, self.pump)
        root.after(1000, self.tick)

    # ---------------------------------------------------------- setup
    def fonts(self):
        fam = set(tkfont.families())
        pick = lambda *n: next((x for x in n if x in fam), "TkDefaultFont")        # noqa: E731
        sans = pick("Segoe UI Variable Text", "Segoe UI", "Inter", "Helvetica Neue", "DejaVu Sans")
        semi = pick("Segoe UI Semibold", sans)
        mono = pick("Cascadia Mono", "Cascadia Code", "Consolas", "JetBrains Mono", "DejaVu Sans Mono")
        S = self.S
        F = lambda f, px, w="normal": tkfont.Font(family=f, size=-max(7, round(px * S)), weight=w)   # noqa: E731
        self.f = {"logo": F(sans, 17, "bold"), "sub": F(mono, 9), "lab": F(mono, 9), "labb": F(mono, 9, "bold"),
                  "num": F(mono, 21, "bold"), "numM": F(mono, 15, "bold"), "numS": F(mono, 12, "bold"), "mono": F(mono, 11),
                  "monoS": F(mono, 10), "body": F(sans, 12), "bodyS": F(sans, 11), "bodyB": F(semi, 12), "h": F(sans, 22, "bold"),
                  "clock": F(mono, 18, "bold"), "big": F(mono, 30, "bold"), "btn": F(semi, 12), "agent": F(mono, 10, "bold")}

    def icon(self):
        try:
            import base64
            self._icon = tk.PhotoImage(data=base64.b64encode(make_png(64)).decode())
            self.root.iconphoto(True, self._icon)
        except Exception:                                         # noqa: BLE001
            pass

    def load_backtest(self):
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(HERE)
        try:
            with open(os.path.join(base, "assets", "ultron_backtest.json"), encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            return None

    def save_cfg(self):
        wt.save_json(os.path.join(DATA, "app.json"), self.cfg)

    # ---------------------------------------------------------- loop
    def pump(self):
        try:
            while True:
                m = self.q.get_nowait()
                if m[0] == "alert":
                    self.alert(*m[1:])
                elif m[0] == "show":
                    self.front()
        except queue.Empty:
            pass
        self.root.after(250, self.pump)

    def tick(self):
        self.draw()
        self.root.after(1000, self.tick)

    def alert(self, kind, title, body):
        self.banner = (kind, title, body, time.time())
        self.front()
        if self.cfg["sound"]:
            threading.Thread(target=chime, args=("buy" if kind == "buy" else "sell",), daemon=True).start()

        def send():
            cfg = wt.settings()
            wt.send_desktop(f"ULTRON · {title}", body)
            wt.send_phone(cfg, f"ULTRON · {title}", body, priority="high", tags="robot")
            wt.send_chat(cfg, f"ULTRON · {title}", body)
        threading.Thread(target=send, daemon=True).start()
        self.draw()

    def front(self):
        try:
            self.root.deiconify()
            self.root.lift()
            self.root.attributes("-topmost", True)
            self.root.after(2500, lambda: self.root.attributes("-topmost", False))
        except tk.TclError:
            pass

    # ---------------------------------------------------------- primitives (logical 1440x900 coordinates)
    def rr(self, x1, y1, x2, y2, r, fill, outline=None, width=1, tag=None):
        r = max(0.5, min(r, (x2 - x1) / 2, (y2 - y1) / 2))
        pts = [x1 + r, y1, x1 + r, y1, x2 - r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y1 + r, x2, y2 - r, x2, y2 - r,
               x2, y2, x2 - r, y2, x2 - r, y2, x1 + r, y2, x1 + r, y2, x1, y2, x1, y2 - r, x1, y2 - r, x1, y1 + r,
               x1, y1 + r, x1, y1]
        return self.cv.create_polygon(pts, smooth=True, splinesteps=12, fill=fill, outline=outline or fill, width=width, tags=tag)

    def t(self, x, y, s, font, color, anchor="nw", width=None, tag=None, justify="left"):
        kw = {"width": width * self.S} if width else {}
        return self.cv.create_text(x, y, text=s, font=self.f[font], fill=color, anchor=anchor, tags=tag, justify=justify, **kw)

    def tw(self, s, font):
        return self.f[font].measure(s) / self.S

    def bind(self, tag, key, action):
        self.cv.tag_bind(tag, "<Button-1>", lambda e: action())
        self.cv.tag_bind(tag, "<Enter>", lambda e: self._hover(key))
        self.cv.tag_bind(tag, "<Leave>", lambda e: self._hover(None))

    def _hover(self, key):
        if self.hover != key:
            self.hover = key
            self.cv.configure(cursor="hand2" if key else "")
            self.draw()

    def button(self, key, x1, y1, x2, y2, label, kind="primary", action=None, font="btn"):
        fill, fg, line = {"primary": (C["blue"], "#FFFFFF", C["blue"]), "ghost": (C["panel"], C["text"], C["line"]),
                          "danger": (C["red"], "#FFFFFF", C["red"]), "soft": (C["bluel"], C["blue"], C["bluel"])}[kind]
        if self.hover == key:
            fill = mix(fill, "#000000", 0.9) if kind in ("primary", "danger") else mix(fill, C["blue"], 0.92)
        tag = f"b_{key}"
        self.rr(x1, y1, x2, y2, 8, fill, line, 1, tag)
        self.t((x1 + x2) / 2, (y1 + y2) / 2, label, font, fg, "center", tag=tag)
        self.bind(tag, key, action or (lambda: None))

    def panel(self, x1, y1, x2, y2, num, title, right=None, right_kind="blue"):
        self.rr(x1, y1, x2, y2, 10, C["panel"], C["line"])
        self.t(x1 + 14, y1 + 12, f"{num:02d}", "labb", C["blue"])
        self.t(x1 + 38, y1 + 12, title, "labb", C["text"])
        if right:
            w = self.tw(right, "lab") + 16
            fill, fg = {"blue": (C["bluel"], C["blue"]), "green": (C["greenl"], C["green"]), "amber": (C["amberl"], C["amber"]),
                        "red": (C["redl"], C["red"])}[right_kind]
            self.rr(x2 - 14 - w, y1 + 9, x2 - 14, y1 + 27, 5, fill)
            self.t(x2 - 14 - w / 2, y1 + 18, right, "lab", fg, "center")
        self.cv.create_line(x1 + 1, y1 + 36, x2 - 1, y1 + 36, fill=C["line2"])

    # ---------------------------------------------------------- the screen
    def draw(self):
        if self.entry is not None and self.overlay != "settings":
            self.entry.destroy()
            self.entry = None
        self.cv.delete("all")
        snap = self.eng.snapshot()
        self.snap = snap
        self.header(snap)
        self.stream(snap)
        self.kpis(snap)
        self.core_panel(14, 168, 520, 548, snap)
        self.chart_panel(530, 168, 1426, 548, snap)
        self.profit_panel(14, 558, 474, 708, snap)
        self.trace_panel(484, 558, 944, 708, snap)
        self.exec_panel(954, 558, 1426, 708, snap)
        self.ledger(14, 718, 1426, 888, snap)
        self.draw_banner()
        if self.overlay:
            self.draw_overlay(self.overlay)
        if self.toast and time.time() - self.toast[1] < 2.5:
            w = self.tw(self.toast[0], "bodyB") + 40
            self.rr(W0 / 2 - w / 2, H0 - 70, W0 / 2 + w / 2, H0 - 38, 16, C["ink"])
            self.t(W0 / 2, H0 - 54, self.toast[0], "bodyB", "#FFFFFF", "center")
        self.cv.scale("all", 0, 0, self.S, self.S)
        self.vortex_items()

    def header(self, s):
        self.rr(14, 12, 50, 48, 8, C["blue"])
        for k in range(4):
            a = k * math.pi / 4
            self.cv.create_line(32 - 10 * math.cos(a), 30 - 10 * math.sin(a), 32 + 10 * math.cos(a), 30 + 10 * math.sin(a),
                                fill="#FFFFFF", width=2)
        self.t(62, 12, "ULTRON", "logo", C["text"])
        self.t(62 + self.tw("ULTRON", "logo") + 8, 17, "/ AUTONOMOUS TERMINAL", "sub", C["muted"])
        self.t(62, 36, "50 AGENTS · ONE BRAIN · PAPER ACCOUNT", "sub", C["dim"])
        st = s["status"]
        if st.get("errors"):
            chip, cc = "● RECONNECTING", "amber"
        elif st.get("state") == "scanning":
            chip, cc = "● AGENTS READING THE MARKET", "blue"
        elif st.get("state") == "starting":
            chip, cc = "● STARTING", "blue"
        else:
            chip, cc = "● AUTOPILOT · PAPER", "green"
        w = self.tw(chip, "labb") + 22
        fill, fg = {"blue": (C["bluel"], C["blue"]), "green": (C["greenl"], C["green"]), "amber": (C["amberl"], C["amber"])}[cc]
        self.rr(1060 - w, 17, 1060, 41, 6, fill)
        self.t(1060 - w / 2, 29, chip, "labb", fg, "center")
        self.t(1286, 12, datetime.now().strftime("%H:%M:%S"), "clock", C["text"], "ne")
        up = int((now_ms() - s["started"]) / 1000)
        self.t(1286, 36, f"RUNNING {up // 86400}d {up % 86400 // 3600:02d}:{up % 3600 // 60:02d}", "sub", C["dim"], "ne")
        self.button("proof", 1300, 14, 1362, 44, "PROOF", "soft", lambda: self.set_overlay("proof"), "labb")
        self.button("set", 1368, 14, 1426, 44, "⚙", "ghost", lambda: self.set_overlay("settings"), "bodyB")

    def stream(self, s):
        y = 58
        self.rr(14, y, 1426, y + 26, 6, C["panel"], C["line"])
        self.rr(16, y + 2, 126, y + 24, 5, C["blue"])
        self.t(71, y + 13, "MARKET STREAM", "labb", "#FFFFFF", "center")
        x = 138
        for coin in en.COINS:
            m = s["market"].get(coin) or {}
            px, chg = m.get("price"), m.get("chg24")
            self.t(x, y + 13, coin, "labb", C["text"], "w")
            x += self.tw(coin, "labb") + 6
            txt = jv.px(px) if px else "…"
            self.t(x, y + 13, txt, "lab", C["muted"], "w")
            x += self.tw(txt, "lab") + 4
            if chg is not None:
                ct = f"{chg:+.1f}%"
                self.t(x, y + 13, ct, "lab", C["green"] if chg >= 0 else C["red"], "w")
                x += self.tw(ct, "lab")
            x += 14
        st = s["status"]
        nxt = st.get("next_scan")
        right = f"NEXT SCAN {max(0, int((nxt - now_ms()) / 1000)) // 60:02d}:{max(0, int((nxt - now_ms()) / 1000)) % 60:02d}" if nxt \
            else "FIRST SCAN…"
        self.t(1416, y + 13, right, "labb", C["blue"], "e")

    def kpis(self, s):
        y, h = 92, 66
        eq, b0 = s["equity"], s["balance0"]
        pnl = eq - b0
        c = s["counts"]
        boxes = [("SYSTEM BALANCE", money(eq), f"PAPER · STARTED {money(b0)}", C["text"]),
                 ("COMBINED P&L", money(pnl, True), f"{pnl / b0 * 100:+.2f}% THIS ACCOUNT", C["green"] if pnl >= 0 else C["red"]),
                 ("WIN RATE", f"{s['win']:.1f}%" if s["win"] is not None else "—", f"{s['closed']} CLOSED TRADES", C["text"]),
                 ("SIGNALS PROCESSED", f"{c['signals']:,}", f"{c['approved']} APPROVED · {c['refused']} REFUSED", C["text"]),
                 ("ACTIVE AGENTS", f"{len(self.model['agents']):02d} / 50", "ALL TRAINED · WALK-FORWARD", C["blue"]),
                 ("OPEN TRADES", f"{len(s['positions'])}", f"{len(s['orders'])} ORDERS WAITING", C["text"])]
        w = (1412 - 5 * 10) / 6
        for k, (lab, val, sub, col) in enumerate(boxes):
            x = 14 + k * (w + 10)
            self.rr(x, y, x + w, y + h, 10, C["panel"], C["line"])
            self.t(x + 14, y + 10, lab, "lab", C["muted"])
            self.t(x + 14, y + 25, val, "num", col)
            self.t(x + 14, y + 52, sub, "lab", C["dim"])

    # ---------------------------------------------------------- 01 the core (vortex)
    def vortex_init(self):
        rng = random.Random(3)
        self.parts = [(rng.random(), rng.random() * 2 * math.pi, 0.55 + rng.random() * 0.6, rng.random()) for _ in range(150)]

    def core_panel(self, x1, y1, x2, y2, s):
        c = s["counts"]
        thr = self.model["params"]["theta"]
        self.panel(x1, y1, x2, y2, 1, "THE CORE  ·  ULTRON BRAIN", "LEARNING" if not self.demo else "LEARNING")
        self.core_box = (x1 + 10, y1 + 44, x2 - 10, y2 - 64)
        bx = self.core_box
        self.t(bx[0] + 6, bx[1] + 4, "HIERARCHICAL EDGE MODEL", "lab", C["dim"])
        self.t(bx[0] + 6, bx[1] + 18, f"{len(self.model['stats']):,} LEARNED CELLS", "lab", C["dim"])
        p = self.model["params"]
        lines = [f"THRESHOLD {thr:+.2f}R", f"SHRINK {p['shrink']:.0f}", f"GATE {p['gate_rule'].upper()}"]
        for k, ln in enumerate(lines):
            self.t(bx[2] - 6, bx[1] + 4 + k * 14, ln, "lab", C["dim"], "ne")
        app = c["approved"]
        tot = app + c["refused"]
        tiles = [("DECISIONS", f"{tot:,}"), ("APPROVED", f"{app:,}"), ("LEARNED", f"{c['learned']:,}"),
                 ("FOLLOWING", f"{s['shadows']:,}")]
        w = (x2 - x1 - 20 - 30) / 4
        for k, (lab, val) in enumerate(tiles):
            x = x1 + 10 + k * (w + 10)
            self.rr(x, y2 - 56, x + w, y2 - 10, 8, C["bg"], C["line2"])
            self.t(x + 10, y2 - 50, lab, "lab", C["muted"])
            self.t(x + 10, y2 - 35, val, "numM", C["blue"] if lab == "APPROVED" else C["text"])

    def vortex_items(self):
        """Create the animated vortex items (after scaling, in screen pixels)."""
        self.v_lines, self.v_dots = [], []
        if not hasattr(self, "core_box") or self.overlay in ("proof", "agents"):
            return
        for k in range(3):
            self.v_lines.append(self.cv.create_line(0, 0, 1, 1, fill=[C["blue"], C["blue2"], C["blue3"]][k], width=max(1, self.S * 1.6),
                                                    smooth=True, tags="vortex"))
        for _ in self.parts:
            self.v_dots.append(self.cv.create_oval(0, 0, 0, 0, fill=C["blue2"], outline="", tags="vortex"))
        self.vortex_frame()

    def vortex_frame(self):
        if not self.v_lines:
            return
        S = self.S
        x1, y1, x2, y2 = self.core_box
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2 + 6
        hh = (y2 - y1) * 0.40
        rmax = min((x2 - x1) * 0.30, 120)
        ph = self.phase * 2 * math.pi
        for k, item in enumerate(self.v_lines):
            pts = []
            for i in range(90):
                u = i / 89
                yy = -1 + 2 * u
                r = rmax * (0.18 + 0.82 * (1 - u) ** 1.25) * (1 + 0.06 * math.sin(ph * 2 + u * 9))
                a = u * 13 + ph * (1.6 - u * 0.8) + k * 2 * math.pi / 3
                pts += [(cx + r * math.cos(a)) * S, (cy + yy * hh + r * 0.22 * math.sin(a)) * S]
            self.cv.coords(item, *pts)
        for (u0, a0, rf, sp), item in zip(self.parts, self.v_dots):
            u = (u0 + self.phase * (0.25 + sp * 0.35)) % 1.0
            yy = -1 + 2 * u
            r = rmax * rf * (0.18 + 0.82 * (1 - u) ** 1.25)
            a = a0 + u * 13 + ph * (1.6 - u * 0.8)
            x, y = cx + r * math.cos(a), cy + yy * hh + r * 0.22 * math.sin(a)
            z = math.sin(a)
            d = 1.2 + 1.3 * (z + 1) / 2
            self.cv.coords(item, (x - d) * S, (y - d) * S, (x + d) * S, (y + d) * S)

    def animate(self):
        self.phase = (self.phase + 0.0035) % 1000.0
        try:
            self.vortex_frame()
        except tk.TclError:
            pass
        self.root.after(33, self.animate)

    # ---------------------------------------------------------- 02 market chart
    def chart_panel(self, x1, y1, x2, y2, s):
        coin = self.cfg["coin"]
        m = s["market"].get(coin) or {}
        held = [p for p in s["positions"] if p["coin"] == coin]
        self.panel(x1, y1, x2, y2, 2, f"{coin} / USD", "IN A TRADE" if held else "LIVE · 1H", "green" if held else "blue")
        # coin tabs
        tx = x1 + 150
        for c in en.COINS:
            w = self.tw(c, "labb") + 16
            on = c == coin
            tag = f"tab_{c}"
            self.rr(tx, y1 + 9, tx + w, y1 + 27, 5, C["blue"] if on else (C["bluel"] if self.hover == tag else C["panel"]),
                    C["blue"] if on else C["line"], tag=tag)
            self.t(tx + w / 2, y1 + 18, c, "labb", "#FFFFFF" if on else C["muted"], "center", tag=tag)
            self.bind(tag, tag, lambda c2=c: self.pick_coin(c2))
            tx += w + 6
        price = m.get("price")
        self.t(x1 + 16, y1 + 46, jv.px(price) if price else "…", "big", C["text"])
        chg = m.get("chg24")
        if chg is not None:
            self.t(x1 + 20 + self.tw(jv.px(price), "big"), y1 + 62, f"{chg:+.2f}% 24H", "monoS", C["green"] if chg >= 0 else C["red"])
        rows = (m.get("candles") or [])[-84:]
        cx1, cy1, cx2, cy2 = x1 + 16, y1 + 96, x2 - 70, y2 - 44
        vy2 = y2 - 14
        if len(rows) < 5:
            self.t((x1 + x2) / 2, (y1 + y2) / 2, "Waiting for the first market read…", "body", C["dim"], "center")
            return
        lines = []
        for p in held:
            lines += [(p["entry"], C["blue"], "ENTRY"), (p["stop"], C["red"], "STOP"), (p["target"], C["green"], "TARGET")]
        for o in s["orders"]:
            if o["coin"] == coin:
                lines += [(o["limit"], C["blue2"], "LIMIT")]
        lo = min([r[3] for r in rows] + [v for v, _, _ in lines])
        hi = max([r[2] for r in rows] + [v for v, _, _ in lines])
        pad = (hi - lo) * 0.06 or 1
        lo, hi = lo - pad, hi + pad
        Y = lambda v: cy2 - (v - lo) / (hi - lo) * (cy2 - cy1)                     # noqa: E731
        for k in range(5):
            v = lo + (hi - lo) * k / 4
            yy = Y(v)
            self.cv.create_line(cx1, yy, cx2, yy, fill=C["line2"], dash=(2, 4))
            self.t(cx2 + 8, yy, jv.px(v), "lab", C["dim"], "w")
        n = len(rows)
        step = (cx2 - cx1) / n
        vmax = max(r[5] for r in rows) or 1
        for i, r in enumerate(rows):
            x = cx1 + step * (i + 0.5)
            up = r[4] >= r[1]
            col = C["green"] if up else C["red"]
            self.cv.create_line(x, Y(r[2]), x, Y(r[3]), fill=col)
            yo, yc = Y(r[1]), Y(r[4])
            self.cv.create_rectangle(x - step * 0.32, min(yo, yc), x + step * 0.32, max(yo, yc) + 0.6, fill=col, outline=col)
            vh = (r[5] / vmax) * 26
            self.cv.create_rectangle(x - step * 0.32, vy2 - vh, x + step * 0.32, vy2, fill=mix(col, C["panel"], 0.28), outline="")
        for v, col, lab in lines:
            yy = Y(v)
            self.cv.create_line(cx1, yy, cx2, yy, fill=col, dash=(5, 3), width=1.4)
            self.rr(cx2 + 2, yy - 9, cx2 + 66, yy + 9, 4, col)
            self.t(cx2 + 34, yy, f"{lab}", "lab", "#FFFFFF", "center")
        last = rows[-1][4]
        self.rr(cx2 + 2, Y(last) - 9, cx2 + 66, Y(last) + 9, 4, C["ink"])
        self.t(cx2 + 34, Y(last), jv.px(last), "lab", "#FFFFFF", "center")
        self.t(cx1, y2 - 12, f"{hhmm(rows[0][0])}", "lab", C["dim"], "sw")
        self.t(cx2, y2 - 12, f"{hhmm(rows[-1][0])}", "lab", C["dim"], "se")

    def pick_coin(self, c):
        self.cfg["coin"] = c
        self.save_cfg()
        self.draw()

    # ---------------------------------------------------------- 03 profit, 04 decisions, 05 executions
    def profit_panel(self, x1, y1, x2, y2, s):
        pnl = s["equity"] - s["balance0"]
        self.panel(x1, y1, x2, y2, 3, "COMBINED PROFIT", f"{len(s['positions'])} OPEN", "blue")
        self.t(x1 + 16, y1 + 44, money(pnl, True), "numM", C["green"] if pnl >= 0 else C["red"])
        pts = [(t, v) for t, v in s["curve"]][-400:]
        gx1, gy1, gx2, gy2 = x1 + 16, y1 + 72, x2 - 16, y2 - 14
        self.cv.create_line(gx1, gy2, gx2, gy2, fill=C["line2"])
        if len(pts) < 2:
            self.t((gx1 + gx2) / 2, (gy1 + gy2) / 2, "the curve starts with the first hour", "lab", C["dim"], "center")
            return
        vs = [v for _, v in pts] + [s["balance0"]]
        lo, hi = min(vs), max(vs)
        if hi - lo < 1e-9:
            hi, lo = hi + 1, lo - 1
        t0, t1 = pts[0][0], pts[-1][0] or 1
        X = lambda t: gx1 + (t - t0) / max(1, t1 - t0) * (gx2 - gx1)              # noqa: E731
        Y = lambda v: gy2 - (v - lo) / (hi - lo) * (gy2 - gy1)                     # noqa: E731
        yb = Y(s["balance0"])
        self.cv.create_line(gx1, yb, gx2, yb, fill=C["line"], dash=(2, 3))
        poly = [gx1, gy2] + [c for t, v in pts for c in (X(t), Y(v))] + [gx2, gy2]
        self.cv.create_polygon(poly, fill=C["bluel"], outline="")
        self.cv.create_line(*[c for t, v in pts for c in (X(t), Y(v))], fill=C["blue"], width=2, smooth=True)

    def trace_panel(self, x1, y1, x2, y2, s):
        d = s["decisions"]
        self.panel(x1, y1, x2, y2, 4, "DECISION TRACE", f"{s['counts']['approved']} APPROVED", "green")
        bx1, bx2, by = x1 + 16, x2 - 16, y1 + 66
        n = 60
        w = (bx2 - bx1) / n
        recent = d[-n:]
        for i in range(n):
            x = bx1 + i * w
            if i < n - len(recent):
                self.cv.create_line(x + w / 2, by - 2, x + w / 2, by + 2, fill=C["line"])
                continue
            e = recent[i - (n - len(recent))]
            hgt = 10 + min(16, abs(e.get("m", 0)) * 60)
            self.cv.create_rectangle(x + 1, by - hgt / 2, x + w - 1, by + hgt / 2, fill=C["blue"] if e["ok"] else C["line"], outline="")
        self.t(bx1, y1 + 44, "EVERY SIGNAL, APPROVED (BLUE) OR REFUSED", "lab", C["dim"])
        yy = y1 + 88
        for e in reversed(d[-4:]):
            col = C["blue"] if e["ok"] else C["muted"]
            self.t(bx1, yy, hhmm(e["t"]), "lab", C["dim"])
            self.t(bx1 + 44, yy, f"{e['agent']:<8}{e['coin']:<6}", "labb", col)
            self.t(bx1 + 160, yy, e["why"][:44], "lab", col)
            yy += 14
        if not d:
            self.t((x1 + x2) / 2, y1 + 104, "Decisions appear after the first hourly scan", "lab", C["dim"], "center")

    def exec_panel(self, x1, y1, x2, y2, s):
        ex = s["execs"]
        self.panel(x1, y1, x2, y2, 5, "EXECUTION STREAM", f"{len(ex)} EVENTS", "blue")
        yy = y1 + 46
        if not ex:
            self.t((x1 + x2) / 2, (y1 + y2) / 2 + 10, "Ultron's paper orders, fills and exits appear here", "lab", C["dim"], "center")
        kc = {"ORDER": C["blue"], "FILL": C["ink"], "SELL": C["green"], "CANCEL": C["dim"]}
        for e in reversed(ex[-7:]):
            col = kc.get(e["kind"], C["muted"])
            if e["kind"] == "SELL" and "(-" in e["text"]:
                col = C["red"]
            self.t(x1 + 16, yy, hhmm(e["t"]), "lab", C["dim"])
            self.rr(x1 + 58, yy - 1, x1 + 108, yy + 13, 3, mix(col, C["panel"], 0.12))
            self.t(x1 + 83, yy + 6, e["kind"], "lab", col, "center")
            self.t(x1 + 116, yy, f"{e['coin']:<6}", "labb", C["text"])
            self.t(x1 + 164, yy, e["text"][:46], "lab", C["muted"])
            yy += 15

    # ---------------------------------------------------------- 06 the fifty
    def ledger(self, x1, y1, x2, y2, s):
        ag = self.model["agents"]
        self.panel(x1, y1, x2, y2, 6, "THE FIFTY  ·  AGENT LEDGER", "VIEW ALL 50 →", "blue")
        self.cv.create_rectangle(x2 - 130, y1 + 6, x2 - 10, y1 + 30, fill="", outline="", tags="allag")
        self.bind("allag", "allag", lambda: self.set_overlay("agents"))
        live = s["agent_live"]
        active = {o["cid"] for o in s["orders"]} | {p["cid"] for p in s["positions"]}
        feat = sorted(ag, key=lambda a: (a["id"] not in active, -(live.get(a["id"], [0, 0])[0]), -a["avg_r"]))[:8]
        w = (x2 - x1 - 20 - 7 * 10) / 8
        for k, a in enumerate(feat):
            x = x1 + 10 + k * (w + 10)
            on = a["id"] in active
            self.rr(x, y1 + 44, x + w, y2 - 10, 8, C["bluel"] if on else C["bg"], C["blue"] if on else C["line2"])
            col = FAM_COLOR.get(a["family"], C["blue"])
            self.cv.create_oval(x + 10, y1 + 54, x + 30, y1 + 74, fill=mix(col, C["panel"], 0.18), outline=col)
            self.t(x + 20, y1 + 64, a["name"][0], "labb", col, "center")
            self.t(x + 36, y1 + 53, a["name"], "agent", C["text"])
            self.t(x + 36, y1 + 66, ("TRADING" if on else a["group"].upper() + " · " + a["tf"].upper()), "lab",
                   C["blue"] if on else C["dim"])
            self.t(x + 10, y1 + 82, a["label"][:26], "lab", C["muted"])
            sp = a.get("spark") or []
            if len(sp) >= 2:
                sx1, sx2, sy1, sy2 = x + 10, x + w - 10, y1 + 100, y1 + 128
                lo, hi = min(sp + [0]), max(sp + [0])
                hi = hi if hi > lo else lo + 1
                pts = [c for i, v in enumerate(sp) for c in (sx1 + i / (len(sp) - 1) * (sx2 - sx1), sy2 - (v - lo) / (hi - lo) * (sy2 - sy1))]
                self.cv.create_line(*pts, fill=C["green"] if sp[-1] >= 0 else C["red"], width=1.5)
            lv = live.get(a["id"])
            right = f"{lv[1] / lv[0]:+.2f}R LIVE" if lv else f"{a['avg_r']:+.2f}R HIST"
            self.t(x + 10, y2 - 26, right, "labb", C["green"] if (lv[1] if lv else a["avg_r"]) >= 0 else C["red"])
            self.t(x + w - 10, y2 - 26, f"{a['signals']}", "lab", C["dim"], "ne")

    # ---------------------------------------------------------- banner + overlays
    def draw_banner(self):
        b = self.banner
        if not b or time.time() - b[3] > 45:
            return
        kind, title, body, _ = b
        col = C["blue"] if kind == "buy" else (C["green"] if "+" in body.split("(")[-1] else C["red"])
        w = max(self.tw(body, "body") + 220, 520)
        x1, x2 = W0 / 2 - w / 2, W0 / 2 + w / 2
        self.rr(x1, 168, x2, 236, 12, col)
        self.t(x1 + 20, 178, "ULTRON " + ("BOUGHT (PAPER)" if kind == "buy" else "SOLD (PAPER)"), "labb", "#FFFFFF")
        self.t(x1 + 20, 194, title, "h", "#FFFFFF")
        self.t(x1 + 20 + self.tw(title, "h") + 16, 204, body, "body", "#FFFFFF")
        self.button("bclose", x2 - 50, 178, x2 - 14, 202, "✕", "ghost", lambda: self.clear_banner(), "bodyB")

    def clear_banner(self):
        self.banner = None
        self.draw()

    def set_overlay(self, ov):
        if self.overlay == "settings" and ov != "settings":
            self.commit_balance()
        self.overlay = ov
        if ov is None and not self.cfg["welcomed"]:
            self.cfg["welcomed"] = True
            self.save_cfg()
        self.draw()

    def modal(self, w, h, title):
        self.cv.create_rectangle(0, 0, W0, H0, fill="#0A1426", stipple="gray50", outline="", tags="veil")
        self.cv.tag_bind("veil", "<Button-1>", lambda e: None)
        x1, y1 = (W0 - w) / 2, (H0 - h) / 2
        self.rr(x1, y1, x1 + w, y1 + h, 14, C["panel"], C["line"])
        self.t(x1 + 24, y1 + 20, title, "h", C["text"])
        self.button("mclose", x1 + w - 52, y1 + 18, x1 + w - 20, y1 + 46, "✕", "ghost", lambda: self.set_overlay(None), "bodyB")
        return x1, y1

    def draw_overlay(self, ov):
        if ov == "welcome":
            x, y = self.modal(620, 360, "Ultron is on autopilot")
            lines = ["50 trained agents read 9 crypto markets every hour, day and night.",
                     "One brain approves or refuses every signal, sizes the trades and manages them: limit entry, "
                     "stop-loss, target and a 96-hour limit. It learns from every signal as it finishes.",
                     "It trades a PAPER account (no real money). When it buys or sells it pops up with a sound, so you can "
                     "copy the trade on your exchange if you want to.",
                     "Leave this window open (minimise it). Settings: paper balance, fees, start with Windows, phone alerts."]
            yy = y + 66
            for s in lines:
                self.cv.create_oval(x + 26, yy + 6, x + 34, yy + 14, fill=C["blue"], outline="")
                tid = self.t(x + 46, yy, s, "body", C["muted"], width=540)
                bb = self.cv.bbox(tid)
                yy += (bb[3] - bb[1]) / self.S + 12 if bb else 40
            self.button("go", x + 24, y + 300, x + 596, y + 340, "Start autopilot", "primary", lambda: self.set_overlay(None))
        elif ov == "close":
            x, y = self.modal(520, 200, "Keep Ultron running?")
            self.t(x + 24, y + 66, "If you quit, Ultron stops trading and can't alert you.", "body", C["muted"])
            self.button("min", x + 24, y + 110, x + 496, y + 150, "Keep running (minimise)", "primary", self.minimise)
            self.button("quit", x + 200, y + 158, x + 320, y + 184, "Quit Ultron", "ghost", self.quit, "bodyS")
        elif ov == "settings":
            self.draw_settings()
        elif ov == "proof":
            self.draw_proof()
        elif ov == "agents":
            self.draw_agents()

    def minimise(self):
        self.overlay = None
        self.root.iconify()
        self.draw()

    def quit(self):
        try:
            self.eng.save()
        except Exception:                                         # noqa: BLE001
            pass
        self.root.destroy()

    def draw_settings(self):
        x, y = self.modal(640, 560, "Settings")
        s = self.snap
        self.t(x + 24, y + 70, "PAPER BALANCE", "lab", C["muted"])
        self.rr(x + 24, y + 88, x + 400, y + 128, 8, C["bg"], C["line"])
        self.t(x + 38, y + 108, "$", "numM", C["muted"], "w")
        if self.entry is None:
            self.entry = tk.Entry(self.root, font=self.f["numM"], bg=C["bg"], fg=C["text"], relief="flat", highlightthickness=0,
                                  bd=0, insertbackground=C["text"])
            self.entry.insert(0, f"{s['balance0']:,.0f}")
            self.entry.bind("<Return>", lambda e: self.commit_balance(force=True))
        self.cv.create_window(x + 58, y + 108, window=self.entry, anchor="w", width=320 * self.S)
        self.button("reset", x + 412, y + 88, x + 616, y + 128, "Start fresh with this", "soft", lambda: self.commit_balance(True), "bodyS")
        self.t(x + 24, y + 134, "Starting fresh clears the paper account's trades. The brain keeps everything it learned.", "bodyS", C["dim"])
        self.t(x + 24, y + 168, "YOUR EXCHANGE (FEES USED)", "lab", C["muted"])
        for k, (key, lab) in enumerate((("ndax", "NDAX"), ("kraken", "Kraken"), ("coinbase", "Coinbase"))):
            bx = x + 24 + k * 200
            self.button(f"fee_{key}", bx, y + 186, bx + 190, y + 222, lab, "primary" if s["fees"] == key else "ghost",
                        lambda k2=key: self.set_fees(k2))
        toggles = [("startup", "Start Ultron when Windows starts"), ("awake", "Keep the computer awake"), ("sound", "Sound on trades")]
        if not sys.platform.startswith("win"):
            toggles = toggles[1:]
        yy = y + 246
        for key, lab in toggles:
            tag = f"tg_{key}"
            self.t(x + 24, yy + 12, lab, "body", C["text"], "w", tag=tag)
            on = self.cfg[key]
            self.rr(x + 560, yy, x + 612, yy + 26, 13, C["blue"] if on else C["line"], tag=tag)
            kx = x + 599 if on else x + 573
            self.cv.create_oval(kx - 10, yy + 3, kx + 10, yy + 23, fill="#FFFFFF", outline="", tags=tag)
            self.cv.create_rectangle(x + 20, yy - 6, x + 620, yy + 32, fill="", outline="", tags=tag)
            self.bind(tag, tag, lambda k2=key: self.toggle(k2))
            yy += 44
        topic = wt.settings()["topic"]
        self.t(x + 24, yy + 10, "PHONE ALERTS (FREE NTFY APP)", "lab", C["muted"])
        if topic:
            self.t(x + 24, yy + 30, "Subscribe to this topic in the ntfy app:", "bodyS", C["muted"])
            self.t(x + 24, yy + 50, topic, "mono", C["blue"])
            self.button("ptest", x + 412, yy + 30, x + 616, yy + 66, "Send test", "soft", self.phone_test, "bodyS")
        else:
            self.button("pset", x + 24, yy + 30, x + 260, yy + 66, "Set up phone alerts", "soft", self.phone_setup, "bodyS")
        self.t(x + 24, y + 530, f"ULTRON {VERSION} · paper only · model trained {self.model.get('trained', '?')}", "lab", C["dim"])

    def commit_balance(self, force=False):
        if self.entry is None:
            return
        try:
            v = float(self.entry.get().replace("$", "").replace(",", "").strip())
        except ValueError:
            return
        if force and 10 <= v <= 1e9:
            self.eng.reset_account(v)
            self.toast = (f"Paper account restarted with {money(v)}", time.time())
            self.draw()

    def set_fees(self, k):
        self.eng.set_fees(k)
        self.draw()

    def toggle(self, k):
        self.cfg[k] = not self.cfg[k]
        if k == "awake":
            set_awake(self.cfg[k])
        if k == "startup" and not set_startup(self.cfg[k]):
            self.cfg[k] = False
        self.save_cfg()
        self.draw()

    def phone_setup(self):
        c = wt.load_json(wt.CONFIG, {})
        if not c.get("ntfy_topic"):
            import secrets
            c["ntfy_topic"] = "ultron-" + secrets.token_urlsafe(18).replace("_", "x").replace("-", "y")
            wt.save_json(wt.CONFIG, c, private=True)
        self.draw()

    def phone_test(self):
        threading.Thread(target=lambda: wt.send_phone(wt.settings(), "ULTRON · test", "Alerts work."), daemon=True).start()
        self.toast = ("Test alert sent", time.time())
        self.draw()

    def draw_proof(self):
        x, y = self.modal(980, 640, "Proof: how Ultron was trained and tested")
        b = self.backtest
        if not b:
            self.t(x + 24, y + 80, "No backtest file bundled.", "body", C["muted"])
            return
        m = b["metrics"]
        self.t(x + 24, y + 62, "Walk-forward: every quarter since 2022 the brain picked its 50 agents using only data that already "
               "existed, then traded the next quarter. Results after fees (NDAX) on a $10,000 paper account.", "bodyS", C["muted"],
               width=930)
        cols = ["PERIOD", "TRADES", "AVG R", "WIN", "RETURN", "MAX DRAWDOWN"]
        xs = [x + 24, x + 300, x + 420, x + 540, x + 660, x + 800]
        yy = y + 112
        for cx, c in zip(xs, cols):
            self.t(cx, yy, c, "lab", C["dim"])
        names = [("dev", "Development 2022 – Mar 2025"), ("B", "Validation Mar – Dec 2025"), ("C", "Test since Dec 2025 (untouched)"),
                 ("all", "All")]
        for key, lab in names:
            yy += 26
            r = m[key]
            vals = [lab, f"{r['n']}", f"{r['avg_r']:+.3f}", f"{r['win']:.0f}%", f"{r['ret']:+.2f}%", f"{r['mdd']:.2f}%"]
            for cx, v in zip(xs, vals):
                self.t(cx, yy, v, "mono" if cx != xs[0] else "bodyS", C["text"] if key != "C" else C["blue"])
        yy += 40
        self.t(x + 24, yy, "EXTREME TESTS", "lab", C["dim"])
        for k, v in b["stress"].items():
            yy += 22
            self.t(x + 24, yy, k, "bodyS", C["text"])
            self.t(x + 300, yy, f"{v['n']}", "mono", C["text"])
            self.t(x + 420, yy, f"{v['avg_r']:+.3f}", "mono", C["text"])
            self.t(x + 660, yy, f"{v['ret']:+.2f}%", "mono", C["text"])
            self.t(x + 800, yy, f"{v['mdd']:.2f}%", "mono", C["text"])
        w = b["windows"]
        bo = b.get("bootstrap") or {}
        yy += 36
        self.t(x + 24, yy, f"{w['n']} random 90-day windows: median {w['median']:+.2f}%, middle 80% between {w['p10']:+.2f}% and "
               f"{w['p90']:+.2f}%, positive in {w['positive']} of {w['n']}.", "bodyS", C["text"], width=930)
        if bo:
            yy += 26
            self.t(x + 24, yy, f"{bo['n']:,} reshuffles of the trades: 90% of outcomes between {bo['ret_p5']:+.1f}% and "
                   f"{bo['ret_p95']:+.1f}%; worst-case drawdown (95th percentile) {bo['dd_p95']:.1f}%.", "bodyS", C["text"], width=930)
        yy += 30
        self.t(x + 24, yy, f"Improvement loop: {b['iterations']} changes tried one at a time, {b['kept']} kept (each had to improve "
               "development without hurting validation; the test period was never used to choose anything).", "bodyS", C["text"],
               width=930)
        self.t(x + 24, y + 600, "Past results on historical data, after costs. Not a forecast and not financial advice. Full report: "
               "docs/BACKTEST.md", "lab", C["dim"])

    def draw_agents(self):
        x, y = self.modal(1240, 760, "The fifty agents")
        ag = self.model["agents"]
        live = self.snap["agent_live"]
        cols = 2
        per = math.ceil(len(ag) / cols)
        colw = 1192 / cols
        hdr = ["AGENT", "SIGNAL", "MARKETS", "WHEN", "SIGNALS", "AVG R", "LIVE"]
        offs = [0, 74, 300, 380, 460, 520, 580]
        for c in range(cols):
            for o, hname in zip(offs, hdr):
                self.t(x + 24 + c * colw + o, y + 64, hname, "lab", C["dim"])
        for i, a in enumerate(ag):
            c, r = divmod(i, per)
            yy = y + 84 + r * 25
            bx = x + 24 + c * colw
            col = FAM_COLOR.get(a["family"], C["blue"])
            self.cv.create_oval(bx - 2, yy + 3, bx + 6, yy + 11, fill=col, outline="")
            lv = live.get(a["id"])
            vals = [a["name"], a["label"][:32], f"{a['group']} {a['tf']}", WHEN.get(a["variant"], a["variant"]), f"{a['signals']}",
                    f"{a['avg_r']:+.2f}", f"{lv[1] / lv[0]:+.2f} ({lv[0]})" if lv else "—"]
            for o, v in zip(offs, vals):
                self.t(bx + o + (10 if o == 0 else 0), yy, v, "agent" if o == 0 else "lab", C["text"] if o < 300 else C["muted"])


# ------------------------------------------------------------------ preview data (screenshots only)
class DemoEngine:
    def __init__(self):
        base = os.path.dirname(HERE)
        with open(os.path.join(base, "assets", "ultron_model.json"), encoding="utf-8") as fh:
            self.model = json.load(fh)
        rng = random.Random(5)
        t = now_ms() - 120 * 3_600_000
        px = 84000.0
        cand = []
        for i in range(120):
            o = px
            px *= 1 + rng.gauss(0.0004, 0.006)
            cand.append([t + i * 3_600_000, o, max(o, px) * (1 + abs(rng.gauss(0, 0.002))), min(o, px) * (1 - abs(rng.gauss(0, 0.002))),
                         px, abs(rng.gauss(400, 150))])
        self.market = {c: {"price": p, "chg24": rng.gauss(0.5, 2)} for c, p in
                       zip(en.COINS, [px, 2679, 121.2, 0.0932, 0.0000124, 0.0000098, 0.0000037, 0.82, 0.000071])}
        self.market["BTC"]["candles"] = cand
        eq = [[now_ms() - (300 - i) * 900_000, 10_000 + i * 2.1 + 40 * math.sin(i / 17)] for i in range(300)]
        ag = self.model["agents"]
        dec = [{"t": now_ms() - (60 - i) * 600_000, "agent": ag[i % len(ag)]["name"], "cid": ag[i % len(ag)]["id"],
                "coin": en.COINS[i % 9], "ok": i % 7 == 0, "why": "approved: learned edge +0.21R" if i % 7 == 0 else
                "waiting for a LOUD (big-move) period", "m": 0.05 + (i % 5) * 0.03} for i in range(60)]
        a0 = ag[0]
        pos = [{"id": "BTC-1", "cid": a0["id"], "agent": a0["name"], "coin": "BTC", "group": "majors", "entry": px * 0.993,
                "stop": px * 0.96, "target": px * 1.06, "units": 0.002, "size": 1.0, "risk_amt": 60.0, "m": 0.2}]
        ex = [{"t": now_ms() - 3_000_000, "kind": "ORDER", "coin": "BTC", "agent": a0["name"], "px": px * 0.993,
               "text": f"limit buy {jv.px(px * 0.993)} · stop {jv.px(px * 0.96)} · target {jv.px(px * 1.06)}"},
              {"t": now_ms() - 2_400_000, "kind": "FILL", "coin": "BTC", "agent": a0["name"], "px": px * 0.993,
               "text": f"bought 0.002 @ {jv.px(px * 0.993)}"},
              {"t": now_ms() - 9_000_000, "kind": "SELL", "coin": "SOL", "agent": ag[3]["name"], "px": 124.1,
               "text": "sold @ 124.10 · target hit · +118.20 (+1.97R)"}]
        self.snap = {"equity": eq[-1][1], "balance0": 10_000.0, "cash": 9_800.0, "fees": "ndax", "orders": [], "positions": pos,
                     "history": [{"r": 1.97}, {"r": -1.0}, {"r": 1.95}], "decisions": dec, "execs": ex, "curve": eq,
                     "counts": {"signals": 4211, "approved": 38, "refused": 4173, "learned": 3890}, "win": 66.7, "closed": 3,
                     "status": {"state": "watching", "next_scan": now_ms() + 1_500_000, "errors": []}, "market": self.market,
                     "agent_live": {a0["id"]: [2, 2.9]}, "started": now_ms() - 3 * 86400_000 - 7_000_000, "shadows": 92}

    def snapshot(self):
        return self.snap

    def save(self):
        pass

    def reset_account(self, v):
        pass

    def set_fees(self, k):
        self.snap["fees"] = k


# ------------------------------------------------------------------ icon + single instance
def make_png(n):
    import struct
    import zlib
    rows = []
    c = (n - 1) / 2
    rad = n * 0.2
    for y in range(n):
        row = bytearray([0])
        for x in range(n):
            dx, dy = x - c, y - c
            qx, qy = max(abs(dx) - (n / 2 - rad - 1), 0), max(abs(dy) - (n / 2 - rad - 1), 0)
            alpha = max(0.0, min(1.0, 0.5 - (math.hypot(qx, qy) - rad)))
            r, g, b = 31, 91, 255
            ang = math.atan2(dy, dx)
            dist = math.hypot(dx, dy) / (n / 2)
            arm = min(abs(math.sin(2 * ang)), abs(math.cos(2 * ang)))
            k = max(0.0, 1 - arm * 6) * (1 if 0.12 < dist < 0.62 else 0)
            k = max(k, 1.0 if dist < 0.12 else 0.0)
            r, g, b = r + (255 - r) * k, g + (255 - g) * k, b + (255 - b) * k
            row += bytes([int(r), int(g), int(b), int(alpha * 255)])
        rows.append(bytes(row))

    def chunk(tag, data):
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", n, n, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(b"".join(rows), 9)) + chunk(b"IEND", b""))


def make_ico(path):
    import struct
    sizes = [16, 24, 32, 48, 64, 128, 256]
    imgs = [make_png(s) for s in sizes]
    off = 6 + 16 * len(sizes)
    dirs = b""
    for s, data in zip(sizes, imgs):
        dirs += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(data), off)
        off += len(data)
    with open(path, "wb") as fh:
        fh.write(struct.pack("<HHH", 0, 1, len(sizes)) + dirs + b"".join(imgs))


def claim_instance(q):
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
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("Ultron.Terminal")
        except Exception:                                         # noqa: BLE001
            pass
    boot = queue.Queue()
    if not demo and not claim_instance(boot):
        return 0
    root = tk.Tk()
    app = App(root, minimized="--minimized" in args, demo=demo)

    def relay():
        try:
            while True:
                app.q.put(boot.get_nowait())
        except queue.Empty:
            pass
        root.after(500, relay)
    relay()
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
