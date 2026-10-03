#!/usr/bin/env python3
"""The volatility gate, trained and measured: will the next hours be LOUD, NORMAL or QUIET?

This is the Jarvus Terminal's gate, moved into Jarvus. Two models (LOUD vs not, QUIET vs not) were fitted on
hourly history with a chronological split (fit 60%, thresholds chosen on the next 20%, measured once on the
last 20%) and ship in ../assets/volgate_model.json:

  crypto (next 12 h; 299,719 hourly rows from 9 coins, 2021-05 to 2026-09; gradient-boosted trees)
      LOUD : test AUC 0.686, flags 5.8% of hours, right 76.2% of the time when it flags (base rate 30.6%)
      QUIET: test AUC 0.700, flags 20.7% of hours, right 59.8% of the time when it flags (base rate 36.3%)
  stock  (next 7 h; 26,086 hourly rows from US stocks/ETFs, 2024-04 to 2026-09; logistic regression)
      LOUD : test AUC 0.637, flags 1.7%, right 68.2% (base 29.0%)   QUIET: AUC 0.647, flags 5.4%, right 59.2% (base 32.9%)

LOUD = the next horizon's range lands in the top third of what that market recently did; QUIET = bottom third.
It never says which way. What to do with it: QUIET -> no new trades (fees are fixed, the range is not);
LOUD -> 0.6x size and a 3-4x ATR stop; NORMAL -> the standard plan.

Every reading prints what held-out testing says about readings like it (the observed rate in that probability
band and how many hours it rests on). Quote that, never the raw model score.

Examples (network needed for live candles; Coinbase hourly is what the model was trained on):
  python3 volgate.py BTC ETH SOL
  python3 volgate.py DOGE --exchange kraken
  python3 volgate.py --stock SPY NVDA            # Yahoo hourly bars, delayed and unofficial
  python3 volgate.py --csv btc_1h.csv            # your own hourly CSV (timestamp,open,high,low,close,volume)
  python3 volgate.py BTC --json

Also prints the trend regime the Terminal's brain used: efficiency ratio over the last 20 hourly closes
(net move / path length; > +0.3 up, < -0.3 down, else sideways) and whether the last 20 bars moved more than
the last 200 (ratio > 1.15 = volatile). Standard library only.
"""

from __future__ import annotations

import argparse
import ast
import csv
import json
import math
import os
import sys
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Dict, List, Optional

HERE = os.path.dirname(os.path.abspath(__file__))
MODEL_PATH = os.path.join(os.environ.get("JARVUS_ASSETS") or os.path.join(getattr(sys, "_MEIPASS", os.path.dirname(HERE)), "assets"),
                          "volgate_model.json")                     # _MEIPASS: inside the packaged Windows app
HORIZON = {"crypto": 12, "stock": 7}
WEEK = 168
NEED_BARS = 420                     # one week of features + two weeks of the hour-of-day profile + warm-up


# ------------------------------------------------------------------ the model (identical to the Terminal's)
def _mean(xs):
    xs = [x for x in xs if x is not None]
    return sum(xs) / len(xs) if xs else None


def _atr_series(h, l, c, n=14):
    out, prev = [None] * len(c), None
    tr = [None] * len(c)
    for i in range(len(c)):
        tr[i] = h[i] - l[i] if i == 0 else max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1]))
        if i + 1 == n:
            prev = sum(tr[:n]) / n
        elif i + 1 > n:
            prev = (prev * (n - 1) + tr[i]) / n
        out[i] = prev
    return out


class Bars:
    """Hourly OHLCV arrays plus the rolling series the features need (computed once, causally)."""

    def __init__(self, t: List[int], o, h, l, c, v, horizon: int = 12):
        self.t, self.o, self.h, self.l, self.c, self.v = t, o, h, l, c, v
        n = len(c)
        self.atr = _atr_series(h, l, c)
        self.lr = [None] + [math.log(c[i] / c[i - 1]) if c[i - 1] and c[i] else None for i in range(1, n)]
        self.bbw = [None] * n
        for i in range(19, n):
            w = c[i - 19:i + 1]
            m = sum(w) / 20
            sd = math.sqrt(sum((x - m) ** 2 for x in w) / 20)
            self.bbw[i] = 4 * sd / m if m else None
        self.r12 = [None] * n
        for i in range(11, n):
            self.r12[i] = (max(h[i - 11:i + 1]) - min(l[i - 11:i + 1])) / c[i] if c[i] else None
        self.r72 = [None] * n
        for i in range(71, n):
            self.r72[i] = (max(h[i - 71:i + 1]) - min(l[i - 71:i + 1])) / c[i] if c[i] else None
        self.horizon = horizon
        self.fwd = [None] * n                     # forward range (a label); features read only finished windows
        for i in range(n - horizon):
            self.fwd[i] = (max(h[i + 1:i + horizon + 1]) - min(l[i + 1:i + horizon + 1])) / c[i] if c[i] else None


def features(b: Bars, i: int) -> Optional[List[float]]:
    """Feature vector at hourly bar i (uses bars up to and including i only)."""
    if i < WEEK + 24 or b.atr[i] is None or not b.c[i]:
        return None
    atr_m = _mean(b.atr[i - WEEK + 1:i + 1])
    bbw_m = _mean(b.bbw[i - WEEK + 1:i + 1])
    vol_m = _mean(b.v[i - WEEK + 1:i + 1])
    r12_m = _mean(b.r12[i - WEEK + 1:i + 1])
    rv24 = [x for x in b.lr[i - 23:i + 1] if x is not None]
    rv168 = [x for x in b.lr[i - WEEK + 1:i + 1] if x is not None]
    if not (atr_m and bbw_m and r12_m and len(rv24) > 10 and len(rv168) > 100) or b.bbw[i] is None or b.r12[i] is None:
        return None
    sd = lambda xs: math.sqrt(sum(x * x for x in xs) / len(xs)) or 1e-12  # noqa: E731
    lg = lambda x: math.log(max(1e-6, x))  # noqa: E731
    hour = (b.t[i] // 3_600_000) % 24
    dow = ((b.t[i] // 86_400_000) + 3) % 7                  # 0 = Monday (1970-01-01 was a Thursday)
    vol6 = sum(b.v[i - 5:i + 1]) / 6
    rv6 = [x for x in b.lr[i - 5:i + 1] if x is not None]
    r72_m = _mean(b.r72[i - WEEK + 1:i + 1])
    H = b.horizon
    same = [b.fwd[j] for j in range(i - H, max(-1, i - 14 * 24 - 1), -1) if b.fwd[j] is not None and (b.t[j] // 3_600_000) % 24 == hour]
    allf = [b.fwd[j] for j in range(max(0, i - 14 * 24), i - H + 1) if b.fwd[j] is not None]
    prof = (sum(same) / len(same)) / (sum(allf) / len(allf)) if same and allf and sum(allf) else 1.0
    v24 = b.v[i - 23:i + 1]
    vw = b.v[i - WEEK + 1:i + 1]
    vm = sum(vw) / len(vw)
    vsd = math.sqrt(sum((x - vm) ** 2 for x in vw) / len(vw)) or 1e-12
    return [1.0,
            lg(b.atr[i] / atr_m), lg(b.bbw[i] / bbw_m), lg((vol6 + 1e-12) / (vol_m + 1e-12)) if vol_m else 0.0,
            lg(sd(rv24) / sd(rv168)), lg(b.r12[i] / r12_m),
            min(6.0, abs(b.c[i] - b.c[i - 12]) / b.atr[i]), min(6.0, (b.h[i] - b.l[i]) / b.atr[i]),
            math.sin(2 * math.pi * hour / 24), math.cos(2 * math.pi * hour / 24), 1.0 if dow >= 5 else 0.0,
            lg(sd(rv6) / sd(rv168)) if len(rv6) >= 4 else 0.0,
            lg(b.r72[i] / r72_m) if (b.r72[i] and r72_m) else 0.0,
            lg(prof), max(-4.0, min(4.0, (sum(v24) / 24 - vm) / vsd))]


def _sig(z):
    return 1.0 / (1.0 + math.exp(-max(-30.0, min(30.0, z))))


def _tree_raw(trees, base, x):
    z = base
    for nodes in trees:
        k = 0
        while True:
            nd = nodes[k]
            if nd[0] < 0:                                   # leaf: [-1, value]
                z += nd[1]
                break
            f, thr, left, right, miss_left = nd
            v = x[f]
            k = (left if miss_left else right) if v is None or v != v else (left if v <= thr else right)
    return z


class VolGate:
    def __init__(self, path: str = MODEL_PATH):
        with open(path, encoding="utf-8") as fh:
            self.model = json.load(fh)
        self._rel = {}
        for asset, m in self.model.items():
            if not isinstance(m, dict):
                continue
            for kind in ("loud", "quiet"):
                r = m.get(f"reliability_{kind}")
                if isinstance(r, str):
                    try:
                        r = ast.literal_eval(r)
                    except (ValueError, SyntaxError):
                        r = None
                if r:
                    self._rel[(asset, kind)] = r

    def evidence(self, asset: str, kind: str, p: Optional[float]) -> Optional[dict]:
        """What the untouched test period says about readings like this one (observed rate in this probability
        band and its sample size, the precision when the gate flags, the base rate)."""
        m = self.model.get(asset) or {}
        rel = self._rel.get((asset, kind))
        if p is None or not rel:
            return None
        band = min(rel, key=lambda r: abs(r["p"] - p))
        test = m.get(f"test_{kind}") or {}
        return {"observed_rate": band.get("actual"), "n": band.get("n"), "band": band.get("p"),
                "precision_when_flagged": test.get("precision"), "flagged_share": test.get("flagged_share"),
                "base_rate": test.get("base_rate"), "auc": test.get("auc"), "period": m.get("period")}

    def read(self, b: Bars, i: int, asset: str = "crypto") -> dict:
        m = self.model.get(asset)
        f = features(b, i) if m else None
        if not m or f is None:
            return {"state": "UNKNOWN", "p_loud": None, "p_quiet": None, "evidence": None}
        if m.get("kind") == "gbm":
            pl = _sig(_tree_raw(m["trees_loud"], m["base_loud"], f))
            pq = _sig(_tree_raw(m["trees_quiet"], m["base_quiet"], f))
        else:
            mu, sd = m["mean"], m["std"]
            x = [f[0]] + [(f[k] - mu[k]) / sd[k] if sd[k] else 0.0 for k in range(1, len(f))]
            pl = _sig(sum(w * v for w, v in zip(m["w_loud"], x)))
            pq = _sig(sum(w * v for w, v in zip(m["w_quiet"], x)))
        state = "LOUD" if pl >= m["t_loud"] else ("QUIET" if pq >= m["t_quiet"] else "NORMAL")
        return {"state": state, "p_loud": round(pl, 4), "p_quiet": round(pq, 4),
                "evidence": {"loud": self.evidence(asset, "loud", pl), "quiet": self.evidence(asset, "quiet", pq)}}


# ------------------------------------------------------------------ trend regime (the brain's definition)
def regime(closes: List[float], n: int = 20, long_n: int = 200) -> Optional[dict]:
    i = len(closes) - 1
    if i < n + 5:
        return None
    move = closes[i] - closes[i - n]
    path = sum(abs(closes[k] - closes[k - 1]) for k in range(i - n + 1, i + 1)) or 1e-12
    er = move / path
    lo = max(1, i - long_n)
    short = sum(abs(closes[k] / closes[k - 1] - 1) for k in range(i - n + 1, i + 1) if closes[k - 1]) / n
    long_ = sum(abs(closes[k] / closes[k - 1] - 1) for k in range(lo, i + 1) if closes[k - 1]) / (i + 1 - lo)
    vr = short / long_ if long_ > 0 else 1.0
    return {"trend": "up" if er > 0.3 else ("down" if er < -0.3 else "sideways"),
            "volatile": vr > 1.15, "efficiency_ratio": round(er, 3), "vol_ratio": round(vr, 3)}


# ------------------------------------------------------------------ data
def _get(url: str, params: dict) -> dict:
    req = urllib.request.Request(url + "?" + urllib.parse.urlencode(params), headers={"User-Agent": "jarvus/6.0"})
    with urllib.request.urlopen(req, timeout=25) as r:
        return json.loads(r.read().decode())


def crypto_bars(symbol: str, exchange: str) -> tuple:
    sys.path.insert(0, HERE)
    from fetch_ohlcv import fetch_candles             # the skill's own fetcher (Coinbase / Kraken / Binance)
    src, rows = fetch_candles(symbol, "1h", NEED_BARS, exchange)
    return src, rows


def stock_bars(symbol: str) -> tuple:
    d = _get(f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}",
             {"interval": "1h", "range": "730d", "includePrePost": "false"})
    res = d["chart"]["result"][0]
    q = res["indicators"]["quote"][0]
    rows = []
    for k, t in enumerate(res.get("timestamp") or []):
        o, h, l, c, v = (q[x][k] for x in ("open", "high", "low", "close", "volume"))
        if None in (o, h, l, c):
            continue
        rows.append([t * 1000, float(o), float(h), float(l), float(c), float(v or 0)])
    return "yahoo (delayed, unofficial)", rows[-NEED_BARS * 2:]


def csv_bars(path: str) -> tuple:
    rows = []
    with open(path, newline="", encoding="utf-8") as fh:
        for r in csv.DictReader(fh):
            ts = r.get("timestamp_utc") or r.get("timestamp") or r.get("time") or r.get("date")
            try:
                t = int(float(ts)) * (1000 if float(ts) < 1e11 else 1)
            except ValueError:
                t = int(datetime.fromisoformat(ts.replace("Z", "+00:00")).replace(tzinfo=timezone.utc).timestamp() * 1000)
            rows.append([t, float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"]), float(r.get("volume") or 0)])
    rows.sort()
    return os.path.basename(path), rows


def read_rows(gate: VolGate, rows: List[list], asset: str) -> dict:
    """Reading at the last COMPLETED hourly bar. The newest row is dropped if its hour is still open."""
    now_ms = datetime.now(timezone.utc).timestamp() * 1000
    if rows and rows[-1][0] + 3_600_000 > now_ms:
        rows = rows[:-1]
    if len(rows) < WEEK + 30:
        return {"state": "UNKNOWN", "why": f"needs at least {WEEK + 30} hourly bars, got {len(rows)}"}
    t, o, h, l, c, v = (list(x) for x in zip(*rows))
    b = Bars(t, o, h, l, c, v, HORIZON[asset])
    out = gate.read(b, len(c) - 1, asset)
    atr = b.atr[-1]
    out.update({"asset": asset, "horizon_hours": HORIZON[asset], "bar_utc": datetime.fromtimestamp(t[-1] / 1000, timezone.utc).strftime("%Y-%m-%d %H:%M"),
                "close": c[-1], "atr_pct": round(atr / c[-1] * 100, 3) if atr and c[-1] else None,
                "regime": regime(c), "bars": len(c)})
    return out


DO = {"LOUD": "trade only A setups, 0.6x size, stop 3-4x ATR, let winners run",
      "NORMAL": "standard plan, stop 2-3x ATR (wider if the cost rule needs it), 1.0x size",
      "QUIET": "no new trades: the coming range is unlikely to pay the fees",
      "UNKNOWN": "no reading: fall back to the manual gate (ATR vs 30d, Bollinger width, RVOL, session)"}


def describe(sym: str, src: str, r: dict) -> str:
    if r.get("state") == "UNKNOWN":
        return f"{sym}  UNKNOWN  ({r.get('why', 'not enough data')})\n      do: {DO['UNKNOWN']}"
    ev = r["evidence"] or {}
    lo, qu = ev.get("loud") or {}, ev.get("quiet") or {}
    pct = lambda x: "?" if x is None else f"{x * 100:.0f}%"  # noqa: E731
    reg = r.get("regime") or {}
    lines = [f"{sym}  {r['state']}  next {r['horizon_hours']}h  (bar {r['bar_utc']} UTC, close {r['close']:g}, hourly ATR {r['atr_pct']}%, data {src})",
             f"      big move followed {pct(lo.get('observed_rate'))} of readings like this in the test period "
             f"({lo.get('n', 0):,} hours; usual {pct(lo.get('base_rate'))})  ·  quiet stretch followed {pct(qu.get('observed_rate'))} "
             f"({qu.get('n', 0):,} hours; usual {pct(qu.get('base_rate'))})"]
    if r["state"] in ("LOUD", "QUIET"):
        k = lo if r["state"] == "LOUD" else qu
        lines.append(f"      when the gate flags {r['state']} it was right {pct(k.get('precision_when_flagged'))} of the time "
                     f"(flags {pct(k.get('flagged_share'))} of hours; test AUC {k.get('auc', 0):.3f})")
    if reg:
        lines.append(f"      trend (20 hourly bars): {reg['trend']}{', volatile' if reg['volatile'] else ', calm'} "
                     f"(efficiency {reg['efficiency_ratio']:+.2f}, vol ratio {reg['vol_ratio']:.2f})  ·  direction is NOT forecast")
    lines.append(f"      do: {DO[r['state']]}")
    return "\n".join(lines)


def main() -> int:
    ap = argparse.ArgumentParser(description="Volatility gate: LOUD / NORMAL / QUIET for the next hours.")
    ap.add_argument("symbols", nargs="*", default=[])
    ap.add_argument("--stock", nargs="*", default=[], help="US stock/ETF tickers (Yahoo hourly)")
    ap.add_argument("--csv", nargs="*", default=[], help="hourly CSV files")
    ap.add_argument("--asset", choices=["crypto", "stock"], default="crypto", help="model for --csv files")
    ap.add_argument("--exchange", default="coinbase", help="coinbase (default, what the model saw), kraken, binance, auto")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    if not (a.symbols or a.stock or a.csv):
        a.symbols = ["BTC", "ETH", "SOL"]
    gate = VolGate()
    out = []
    jobs = [(s, "crypto") for s in a.symbols] + [(s, "stock") for s in a.stock] + [(p, "csv") for p in a.csv]
    for sym, kind in jobs:
        try:
            if kind == "crypto":
                src, rows = crypto_bars(sym if "-" in sym or "/" in sym or sym.upper().endswith(("USD", "USDT")) else sym + "-USD", a.exchange)
                r = read_rows(gate, rows, "crypto")
            elif kind == "stock":
                src, rows = stock_bars(sym.upper())
                r = read_rows(gate, rows, "stock")
            else:
                src, rows = csv_bars(sym)
                r = read_rows(gate, rows, a.asset)
        except SystemExit as e:
            src, r = "none", {"state": "UNKNOWN", "why": str(e).strip()[:300]}
        except Exception as e:                       # noqa: BLE001 - report and keep going
            src, r = "none", {"state": "UNKNOWN", "why": f"{type(e).__name__}: {e}"[:300]}
        out.append({"symbol": sym, "source": src, **r})
        if not a.json:
            print(describe(sym.upper(), src, r))
    if a.json:
        print(json.dumps(out, indent=1, default=str))
    return 0


if __name__ == "__main__":
    sys.exit(main())
