"""Ultron's live engine: the trained councils (1h and 4h crypto, 25 agents each), a paper account, fully automatic.

Every hour, just after a candle closes, it downloads each coin's recent hourly (and daily) candles from Coinbase and
asks the 1h council about the newest completed hour, and the 4h council when a 4-hour candle has just closed
(ultron/core/council.py: the same rules as the TradingView indicator). An approved trade becomes a paper limit order
(0.1% under the close, valid 3 bars) with the council's stop and a target at 2R; the paper broker checks 5-minute
candles every minute for fills, stops, targets and the time limit (96 bars). Paper money only: this version has no
real-exchange connection.
"""

from __future__ import annotations

import json
import os
import sys
import threading
import time
from datetime import datetime, timedelta, timezone

HERE = os.path.dirname(os.path.abspath(__file__))
_ROOT = getattr(sys, "_MEIPASS", None)
if not _ROOT:
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(HERE)), "jarvus", "scripts"))
    sys.path.insert(0, os.path.join(os.path.dirname(HERE), "tv"))
sys.path.insert(0, HERE)


import events as evmod  # noqa: E402
import jarvus as jv  # noqa: E402
import council as cn  # noqa: E402
import markets as mk  # noqa: E402
from brain import Book  # noqa: E402
from fetch_ohlcv import fetch_coinbase  # noqa: E402

HOUR = 3_600_000
COINS = ["BTC", "ETH", "SOL", "DOGE", "SHIB", "PEPE", "BONK", "WIF", "FLOKI"]
MAJORS = {"BTC", "ETH", "SOL"}
FEES = {"ndax": (0.002, 0.002), "kraken": (0.004, 0.008), "coinbase": (0.006, 0.012)}
SLIP = {"majors": 0.0002, "memes": 0.001, "markets": 0.0002}
FEES_MKT = (0.0005, 0.0005)                    # stocks / ETFs / forex: 0.05% per side, as trained
# Exit style per council: (sell-part level in R, part sold, final target in R). The high-win-rate "Auto" style where it
# passed the untouched test (1h crypto, daily markets); the trained 2R where Auto did not (4h). See ultron/tv/BACKTEST_ALL.md.
EXITS = {"1h": (0.5, 0.5, 2.0), "4h": (0.0, 0.0, 2.0), "1D_markets": (0.0, 0.0, 0.5)}
ORDER_BARS = 3
HOLD_H = 96
COUNCILS = ("1h", "4h")                    # the crypto councils that passed the untouched test
MARKETS_COUNCIL = "1D_markets"              # daily council for 28 stocks, ETFs, forex pairs, gold, silver, oil


def now_ms():
    return int(time.time() * 1000)


def load_councils():
    """-> ({tf: council model}, one combined model for the screen: 50 agents with unique ids and names)."""
    base = _ROOT or os.path.dirname(HERE)
    cs, agents = {}, []
    for k, tf in enumerate(COUNCILS):
        with open(os.path.join(base, "assets", "councils", f"{tf}.json"), encoding="utf-8") as fh:
            m = json.load(fh)
        for j, a in enumerate(m["agents"]):
            a["uid"] = f"{tf}:{a['id']}"
            if k:
                a["name"] = NAMES[25 * k + j] if 25 * k + j < len(NAMES) else f"{a['name']}-{tf}"
            agents.append(dict(a, id=a["uid"], tf=({"1h": "4h", "4h": "1D"}[tf] if a["htf"] else tf), council=tf))
        cs[tf] = m
    try:
        with open(os.path.join(base, "assets", "councils", f"{MARKETS_COUNCIL}.json"), encoding="utf-8") as fh:
            m = json.load(fh)
        for a in m["agents"]:
            a["uid"] = f"{MARKETS_COUNCIL}:{a['id']}"
            a["name"] = a["name"] + "-M"
        cs[MARKETS_COUNCIL] = m
    except OSError:
        pass
    first = cs[COUNCILS[0]]
    combined = {"agents": agents, "params": first["params"], "trained": first["trained"],
                "stats": {f"{a['id']}|{r}": v for a in agents for r, v in a["edges"].items()}, "councils": list(COUNCILS)}
    return cs, combined


NAMES = ["ORION", "VEGA", "NOVA", "ATLAS", "LYRA", "TITAN", "AEGIS", "HELIOS", "SIRIUS", "KEPLER", "POLARIS", "RIGEL", "CYGNUS", "DRACO", "PULSAR", "QUASAR", "ZENITH", "AURORA", "BOREAS", "CALYPSO", "CASSINI", "CEPHEUS", "ELARA", "EOS", "GAIA", "HALO", "HERMES", "HYDRA", "HYPERION", "ICARUS", "JUNO", "MIRA", "NYX", "OBERON", "PALLAS", "PHOEBE", "RHEA", "SELENE", "SPICA", "TALOS", "TETHYS", "THEIA", "TRITON", "VESTA", "ZEPHYR", "ARGUS", "ALTAIR", "DENEB", "ANTARES", "CASTOR", "POLLUX", "IOTA", "SIGMA", "OMEGA", "KAPPA"]


def parse_key(s):
    p = s.split("|")
    if p[0] == "fleet":
        return ("fleet",)
    if p[0] == "fam":
        return ("fam", p[1], p[2])
    cid = "|".join(p[1:5])
    if p[0] == "a":
        return ("a", cid)
    if p[0] == "ag":
        return ("ag", cid, p[5])
    b = {"True": True, "False": False}.get(p[6])
    return ("agr", cid, p[5], b)


def key_str(k):
    return "|".join(map(str, k))


def weekend_mt(t_ms):
    dt = datetime.fromtimestamp(t_ms / 1000, timezone.utc)
    dt = dt - timedelta(hours=6 if evmod.us_dst(dt.date()) else 7)
    return dt.weekday() >= 5


class Engine:
    """All state lives in self.s (saved as JSON). The UI reads snapshot(); it never touches internals."""

    def __init__(self, data_dir, fetch=None, notify=None):
        self.data_dir = data_dir
        os.makedirs(data_dir, exist_ok=True)
        self.path = os.path.join(data_dir, "state.json")
        self.fetch = fetch or fetch_coinbase
        self.notify = notify or (lambda kind, title, body: None)
        self.lock = threading.RLock()
        self.councils, self.model = load_councils()
        self.agents = {a["id"]: a for a in self.model["agents"]}
        if MARKETS_COUNCIL in self.councils:
            for a in self.councils[MARKETS_COUNCIL]["agents"]:
                self.agents[a["uid"]] = dict(a, id=a["uid"], tf="1D", council=MARKETS_COUNCIL)
        self.params = self.model["params"]
        self.s = self._load()
        self.stop_flag = threading.Event()
        self.wake = threading.Event()
        self.status = {"state": "starting", "last_scan": None, "next_scan": None, "errors": []}
        self.market = {}          # coin -> {"price", "chg24", "candles": [[t,o,h,l,c,v]...] (last 120 1h)}
        self.thread = None

    # ------------------------------------------------------------ persistence
    def _load(self):
        try:
            with open(self.path, encoding="utf-8") as fh:
                s = json.load(fh)
        except (OSError, ValueError):
            s = {}
        s.setdefault("balance0", 10_000.0)
        s.setdefault("cash", s["balance0"])
        s.setdefault("fees", "ndax")
        s.setdefault("orders", [])
        s.setdefault("positions", [])
        s.setdefault("history", [])
        s.setdefault("shadows", [])
        s.setdefault("decisions", [])
        s.setdefault("execs", [])
        s.setdefault("equity", [])
        s.setdefault("last_bar", {})
        s.setdefault("last_fire", {})
        s.setdefault("views", {})
        s.setdefault("mkt_day", "")
        s.setdefault("counts", {"signals": 0, "approved": 0, "refused": 0, "learned": 0})
        s.setdefault("agent_live", {})
        s.setdefault("started", now_ms())
        return s

    def save(self):
        with self.lock:
            tmp = self.path + ".tmp"
            with open(tmp, "w", encoding="utf-8") as fh:
                json.dump(self.s, fh, separators=(",", ":"))
            os.replace(tmp, self.path)

    # ------------------------------------------------------------ account
    def equity(self):
        with self.lock:
            eq = self.s["cash"]
            for p in self.s["positions"]:
                px = (self.market.get(p["coin"]) or {}).get("price") or p["entry"]
                eq += p["units"] * px
            for o in self.s["orders"]:
                eq += o["reserved"]
            return eq

    def reset_account(self, balance):
        with self.lock:
            self.s.update(balance0=float(balance), cash=float(balance), orders=[], positions=[], history=[], execs=[],
                          equity=[[now_ms(), float(balance)]], started=now_ms(), agent_live={})
            self.s["counts"].update(approved=0, refused=0)
        self.save()

    def set_fees(self, fees):
        with self.lock:
            self.s["fees"] = fees if fees in FEES else "ndax"
        self.save()

    def log(self, key, item, cap=300):
        with self.lock:
            self.s[key] = (self.s[key] + [item])[-cap:]

    # ------------------------------------------------------------ the loop
    def start(self):
        self.thread = threading.Thread(target=self.run, daemon=True)
        self.thread.start()

    def run(self):
        next_scan, next_tick = 0.0, 0.0
        while not self.stop_flag.is_set():
            t = time.time()
            try:
                if t >= next_tick:
                    next_tick = t + 60
                    self.tick()
                if t >= next_scan or self.wake.is_set():
                    self.wake.clear()
                    self.status["state"] = "scanning"
                    self.scan()
                    # next scan: 2 minutes after the next hour closes
                    nxt = (int(time.time() // 3600) + 1) * 3600 + 120
                    next_scan = nxt
                    self.status.update(state="watching", last_scan=now_ms(), next_scan=nxt * 1000)
                    self.save()
            except Exception as e:                                  # noqa: BLE001
                self.status["errors"] = (self.status["errors"] + [f"{datetime.now():%H:%M} {type(e).__name__}: {e}"[:140]])[-5:]
                print("engine error:", repr(e), flush=True)
            self.stop_flag.wait(1.0)

    # ------------------------------------------------------------ hourly: agents -> brain -> orders
    def scan(self):
        jv._BTC.clear()
        bull = jv.btc_regime().get("bull")
        errors = []
        for coin in COINS:
            try:
                self.scan_coin(coin, bull)
            except Exception as e:                                  # noqa: BLE001
                errors.append(coin)
                print(f"scan {coin}: {type(e).__name__}: {e}", flush=True)
        if MARKETS_COUNCIL in self.councils:
            today = datetime.now(timezone.utc)
            if today.hour >= 2 and self.s["mkt_day"] != today.strftime("%Y-%m-%d"):
                for sym in self.councils[MARKETS_COUNCIL].get("symbols", []):
                    if sym not in mk.YAHOO:
                        continue
                    try:
                        self.scan_market(sym)
                    except Exception as e:                          # noqa: BLE001
                        errors.append(sym)
                        print(f"scan {sym}: {type(e).__name__}: {e}", flush=True)
                with self.lock:
                    self.s["mkt_day"] = today.strftime("%Y-%m-%d")
        self.status["errors"] = [f"no data: {', '.join(errors)}"] if errors else []

    def scan_market(self, sym):
        """Once a day, after every exchange has closed: the daily markets council on the newest final daily bar."""
        final, live = mk.fetch_daily(sym, 900)
        if len(final) < 400:
            raise ValueError("not enough daily candles")
        last_t = final[-1][0]
        self.market.setdefault(sym, {})["price"] = (live or final[-1])[4]
        with self.lock:
            if self.s["last_bar"].get("M|" + sym) == last_t:
                return
            self.s["last_bar"]["M|" + sym] = last_t
        c = [r[4] for r in final]
        bull = c[-2] > sum(c[-201:-1]) / 200                          # previous day's close vs its 200-day average
        friday = (last_t // (24 * HOUR) + 3) % 7 == 4                 # the week's bar closed with this day
        with self.lock:
            lf = self.s["last_fire"].setdefault(f"{MARKETS_COUNCIL}|{sym}", {})
        dec, info = cn.evaluate(self.councils[MARKETS_COUNCIL], sym, final, mk.weekly(final), bull, False, FEES_MKT,
                                SLIP["markets"], lf, "markets", htf_end=friday)
        with self.lock:
            self.s["views"][f"{sym}|1D"] = dict(info, t=now_ms())
            self.s["counts"]["signals"] += info["firing"]
        if dec:
            self.consider(dec, sym, "markets", MARKETS_COUNCIL)

    def scan_coin(self, coin, bull):
        rows = self.fetch(coin, "USD", "1h", 1600)
        if rows and rows[-1][0] + HOUR > now_ms():
            rows = rows[:-1]                                         # the current hour is still open
        if len(rows) < 1100:
            raise ValueError("not enough candles")
        last_t = rows[-1][0]
        self.market.setdefault(coin, {})
        self.market[coin].update(candles=rows[-120:], price=self.market[coin].get("price") or rows[-1][4],
                                 chg24=(rows[-1][4] / rows[-25][4] - 1) * 100)
        with self.lock:
            if self.s["last_bar"].get(coin) == last_t:
                return                                               # this hour was already handled
            self.s["last_bar"][coin] = last_t
        group = "majors" if coin in MAJORS else "memes"
        fees = FEES[self.s["fees"]]
        jobs = [("1h", rows, cn.aggregate(rows, 4 * HOUR))]
        if (last_t + HOUR) % (4 * HOUR) == 0:                        # a 4-hour candle closed with this hour
            daily = self.fetch(coin, "USD", "1d", 300)
            daily = [r for r in daily if r[0] + 24 * HOUR <= last_t + HOUR]
            jobs.append(("4h", cn.aggregate(rows, 4 * HOUR), daily))
        for tf, bars, hbars in jobs:
            if len(bars) < 300 or len(hbars) < 60:
                continue
            with self.lock:
                lf = self.s["last_fire"].setdefault(f"{tf}|{coin}", {})
            dec, info = cn.evaluate(self.councils[tf], coin, bars, hbars, bull, weekend_mt(bars[-1][0] + cn.SIZE[tf]), fees,
                                    SLIP[group], lf, group)
            with self.lock:
                self.s["views"][f"{coin}|{tf}"] = dict(info, t=now_ms())
                self.s["counts"]["signals"] += info["firing"]
            if dec:
                self.consider(dec, coin, group, tf)
            elif info["firing"]:
                self.log("decisions", {"t": now_ms(), "agent": f"{tf} council", "cid": "", "coin": coin, "ok": False,
                                       "why": info["why"], "m": 0.0})
                with self.lock:
                    self.s["counts"]["refused"] += 1

    def consider(self, dec, coin, group, tf):
        a = self.agents[f"{tf}:{dec['agent']['id']}"]
        take, why = True, f"approved: learned edge {dec['m']:+.2f}R"
        params = self.councils[tf]["params"]
        mkt = group == "markets"
        book = Book(params)                                          # crypto and markets keep separate position limits
        with self.lock:
            for p in self.s["positions"] + self.s["orders"]:
                if (p["group"] == "markets") == mkt:
                    book.opened(p["coin"], p["group"])
            day = (dec["t_dec"] - 6 * HOUR) // (24 * HOUR)
            closed_today = [x for x in self.s["history"] if (x["closed"] - 6 * HOUR) // (24 * HOUR) == day
                            and (x["group"] == "markets") == mkt]
            book.day = day
            book.day_r = sum(x["r"] * x["size"] for x in closed_today)
            streak = 0
            for x in closed_today:
                streak = streak + 1 if x["r"] < 0 else 0
            book.streak = streak
        ok, why2 = book.can_open(coin, group, day)
        if not ok:
            take, why = False, why2
        self.log("decisions", {"t": now_ms(), "agent": a["name"], "cid": a["id"], "coin": coin, "ok": take, "why": why,
                               "m": round(dec["m"], 3)})
        with self.lock:
            self.s["counts"]["approved" if take else "refused"] += 1
        if not take:
            return
        fmk, ftk = self.fees_for(group)
        eq = self.equity()
        risk_pct = (params["risk_major"] if group in ("majors", "markets") else params["risk_meme"]) * dec["size"]
        risk_amt = eq * risk_pct
        entry, stop_dist = dec["entry"], dec["stop_dist"]
        r1, frac, tgt = EXITS.get(tf, (0.0, 0.0, 2.0))
        stop, target = entry - stop_dist, entry + tgt * stop_dist
        tp1 = entry + r1 * stop_dist if r1 else None
        units = risk_amt / stop_dist
        if units * entry > self.s["cash"] * 0.98:
            units = self.s["cash"] * 0.98 / entry
        if units <= 0:
            return
        reserved = units * entry * (1 + fmk)
        order_ms = 5 * 24 * HOUR if mkt else dec["order_ms"]          # markets: 3 trading days
        hold_ms = int(96 * 7 / 5) * 24 * HOUR if mkt else dec["hold_ms"]  # markets: 96 trading days
        order = {"id": f"{coin}-{tf}-{dec['t_dec']}", "cid": a["id"], "agent": a["name"], "coin": coin, "group": group,
                 "limit": entry, "stop": stop, "target": target, "units": units, "size": dec["size"], "risk_amt": risk_amt,
                 "reserved": reserved, "placed": now_ms(), "expires": dec["t_dec"] + order_ms, "hold_ms": hold_ms,
                 "tp1": tp1, "frac": frac, "council": tf, "m": round(dec["m"], 3)}
        with self.lock:
            self.s["cash"] -= reserved
            self.s["orders"].append(order)
        self.log("execs", {"t": now_ms(), "kind": "ORDER", "coin": coin, "agent": a["name"], "px": entry,
                           "text": f"{tf} council · limit buy {jv.px(entry)} · stop {jv.px(stop)} · "
                                   + (f"sell half {jv.px(tp1)}, rest " if tp1 else "") + f"target {jv.px(target)}"})
        self.notify("buy", f"BUY {coin}", f"Limit {jv.px(entry)} · " + (f"Half at {jv.px(tp1)} · " if tp1 else "")
                    + f"Sell {jv.px(target)} · Stop {jv.px(stop)} · {a['name']} ({tf})")

    def fees_for(self, group):
        return FEES_MKT if group == "markets" else FEES[self.s["fees"]]

    # ------------------------------------------------------------ every minute: the paper broker
    def tick(self):
        with self.lock:
            coins = sorted({o["coin"] for o in self.s["orders"]} | {p["coin"] for p in self.s["positions"]})
            since = {}
            for x in self.s["orders"]:
                since[x["coin"]] = min(since.get(x["coin"], now_ms()), x["placed"])
            for x in self.s["positions"]:
                since[x["coin"]] = min(since.get(x["coin"], now_ms()), x["checked"])
        quotes = {}
        for coin in COINS:
            try:
                rows = self.fetch(coin, "USD", "5m", 40)
            except Exception:                                         # noqa: BLE001
                continue
            if rows:
                quotes[coin] = rows
                self.market.setdefault(coin, {})["price"] = rows[-1][4]
        for coin in [x for x in coins if x in COINS]:
            rows = quotes.get(coin)
            gap_h = (now_ms() - since.get(coin, now_ms())) / HOUR
            if gap_h > 3:                                             # the app was off: catch up on hourly candles
                try:
                    rows = self.fetch(coin, "USD", "1h", min(300, int(gap_h) + 3)) + (rows or [])
                except Exception:                                     # noqa: BLE001
                    pass
            if rows:
                self.broker(coin, rows)
        if now_ms() - getattr(self, "_mkt_tick", 0) >= 15 * 60_000:
            self._mkt_tick = now_ms()
            for sym in [x for x in coins if x in mk.YAHOO]:
                try:
                    final, live = mk.fetch_daily(sym, 30)
                except Exception:                                     # noqa: BLE001
                    continue
                rows = final[-10:] + ([live] if live else [])
                if rows:
                    self.market.setdefault(sym, {})["price"] = rows[-1][4]
                    self.broker(sym, rows)
        eq = self.equity()
        with self.lock:
            last = self.s["equity"][-1][0] if self.s["equity"] else 0
            if now_ms() - last >= 15 * 60_000:
                self.s["equity"] = (self.s["equity"] + [[now_ms(), round(eq, 2)]])[-3000:]
        if coins:
            self.save()

    def broker(self, coin, rows):
        with self.lock:
            for o in list(self.s["orders"]):
                if o["coin"] != coin:
                    continue
                mk_, tk_ = self.fees_for(o["group"])
                fill = None
                for r in rows:
                    if r[0] < o["placed"]:                         # only candles that began after the order existed
                        continue
                    if r[0] >= o["expires"]:
                        break
                    if r[1] <= o["limit"]:
                        fill = (r[0], r[1])
                        break
                    if r[3] <= o["limit"]:
                        fill = (r[0], o["limit"])
                        break
                if fill:
                    px = fill[1]
                    cost = o["units"] * px * (1 + mk_)
                    self.s["orders"].remove(o)
                    self.s["cash"] += o["reserved"] - cost
                    pos = {k: o[k] for k in ("id", "cid", "agent", "coin", "group", "stop", "target", "units", "size", "risk_amt", "m")}
                    pos.update(entry=px, opened=fill[0], expires=fill[0] + o.get("hold_ms", HOLD_H * HOUR), cost=cost, checked=fill[0],
                               units0=o["units"], stop0=o["stop"], realized=0.0, moved=False, tp1=o.get("tp1"),
                               frac=o.get("frac", 0.0), be=px * (1 + mk_ + tk_ + SLIP[o["group"]]))
                    self.s["positions"].append(pos)
                    self.log("execs", {"t": now_ms(), "kind": "FILL", "coin": coin, "agent": o["agent"], "px": px,
                                       "text": f"bought {o['units']:.6g} @ {jv.px(px)}"})
                elif now_ms() >= o["expires"]:
                    self.s["orders"].remove(o)
                    self.s["cash"] += o["reserved"]
                    self.log("execs", {"t": now_ms(), "kind": "CANCEL", "coin": coin, "agent": o["agent"], "px": o["limit"],
                                       "text": "limit not filled in 3 bars: cancelled"})
            for p in list(self.s["positions"]):
                if p["coin"] != coin:
                    continue
                mk_, tk_ = self.fees_for(p["group"])
                sl = SLIP[p["group"]]
                out = None
                for r in rows:
                    if r[0] < p["checked"]:
                        continue
                    if r[3] <= p["stop"]:                            # pessimistic: the stop first, as in the backtest
                        out = ("breakeven" if p.get("moved") else "stop", min(r[1], p["stop"]) * (1 - 2 * sl), tk_)
                        break
                    if p.get("tp1") and not p.get("moved") and r[2] >= p["tp1"]:
                        self.partial(p, p["tp1"], mk_)
                    if r[2] >= p["target"]:
                        out = ("target", p["target"], mk_)
                        break
                    if r[0] >= p["expires"]:
                        out = ("time", r[1] * (1 - sl), tk_)
                        break
                p["checked"] = rows[-1][0]
                if out:
                    self.close(p, *out)

    def partial(self, p, px, fee):
        """First target hit: sell the planned part, move the stop to breakeven (entry + fees)."""
        u = p["units"] * p["frac"]
        proceeds = u * px * (1 - fee)
        p["units"] -= u
        p["realized"] = p.get("realized", 0.0) + proceeds
        p["moved"] = True
        p["stop"] = max(p["stop"], p["be"])
        self.s["cash"] += proceeds
        self.log("execs", {"t": now_ms(), "kind": "SELL", "coin": p["coin"], "agent": p["agent"], "px": px,
                           "text": f"sold {p['frac'] * 100:.0f}% @ {jv.px(px)} · first target · stop moved to breakeven {jv.px(p['stop'])}"})
        self.notify("sell", f"SELL HALF {p['coin']}", f"First target {jv.px(px)} hit · stop now at breakeven {jv.px(p['stop'])}")

    def close(self, p, reason, px, fee):
        proceeds = p["units"] * px * (1 - fee)
        pnl = proceeds + p.get("realized", 0.0) - p["cost"]
        risk = p.get("units0", p["units"]) * (p["entry"] - p.get("stop0", p["stop"]))
        r = pnl / risk if risk > 0 else 0.0
        self.s["positions"].remove(p)
        self.s["cash"] += proceeds
        rec = dict(p, exit=reason, exit_px=px, closed=now_ms(), pnl=round(pnl, 2), r=round(r, 3))
        self.s["history"] = (self.s["history"] + [rec])[-1000:]
        al = self.s["agent_live"].setdefault(p["cid"], [0, 0.0])
        al[0] += 1
        al[1] += r
        word = {"target": "target hit", "stop": "stop-loss hit", "time": "time limit reached",
                "breakeven": "breakeven stop (part already sold)"}[reason]
        self.log("execs", {"t": now_ms(), "kind": "SELL", "coin": p["coin"], "agent": p["agent"], "px": px,
                           "text": f"sold @ {jv.px(px)} · {word} · {pnl:+,.2f} ({r:+.2f}R)"})
        self.notify("sell", f"SELL {p['coin']}", f"{word} · {pnl:+,.2f} ({r:+.2f}R)")

    def close_now(self, pid):
        """User asked to close a paper trade at the current price."""
        with self.lock:
            for p in list(self.s["positions"]):
                if p["id"] == pid:
                    px = (self.market.get(p["coin"]) or {}).get("price") or p["entry"]
                    self.close(p, "time", px, self.fees_for(p["group"])[1])
        self.save()

    # ------------------------------------------------------------ learning from every signal
    def resolve_shadows(self):
        """The councils are frozen snapshots of training (as in the TradingView indicator): nothing to re-learn live."""

    # ------------------------------------------------------------ what the UI reads
    def snapshot(self):
        with self.lock:
            s = self.s
            hist = s["history"]
            wins = sum(1 for x in hist if x["r"] > 0)
            return {"equity": self.equity(), "balance0": s["balance0"], "cash": s["cash"], "fees": s["fees"],
                    "orders": [dict(o) for o in s["orders"]], "positions": [dict(p) for p in s["positions"]],
                    "history": hist[-200:], "decisions": s["decisions"][-60:], "execs": s["execs"][-60:],
                    "curve": list(s["equity"]), "counts": dict(s["counts"]), "win": (wins / len(hist) * 100) if hist else None,
                    "closed": len(hist), "status": dict(self.status), "market": {k: dict(v) for k, v in self.market.items()},
                    "agent_live": dict(s["agent_live"]), "started": s["started"], "shadows": 0, "views": dict(s["views"])}
