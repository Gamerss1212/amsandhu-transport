#!/usr/bin/env python3
"""Multi-timeframe market snapshot from OHLCV CSV files.

  python3 snapshot.py btc_1d.csv btc_4h.csv btc_15m.csv
  python3 snapshot.py btc_15m.csv --json snapshot.json --swing-n 3

Each CSV must have columns timestamp_utc,open,high,low,close,volume (what
fetch_ohlcv.py writes). The timeframe is detected from the candle spacing. Output is
a human summary plus (optionally) a JSON file with trend, swings, levels,
indicators, setup flags, and clock context, so Claude reasons from real numbers
instead of inventing them.

The last candle in a live feed is usually still forming. The script detects that,
reports it, and computes candle-based signals (RVOL, sweeps, reclaims) on the last
CLOSED candle while still using the live price for distances.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import indicators as ind  # noqa: E402
import events  # noqa: E402


# ------------------------------------------------------------------ loading ---

def parse_ts(s: str) -> datetime:
    s = s.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return datetime.strptime(s, fmt).replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    v = float(s)  # epoch seconds or milliseconds
    if v > 1e12:
        v /= 1000.0
    return datetime.fromtimestamp(v, tz=timezone.utc)


def load_csv(path: str) -> Dict[str, list]:
    with open(path, newline="", encoding="utf-8") as fh:
        rows = list(csv.DictReader(fh))
    if not rows:
        raise SystemExit(f"{path}: empty")
    cols = {c.lower().strip(): c for c in rows[0].keys()}
    ts_col = next((cols[c] for c in ("timestamp_utc", "timestamp", "time", "date", "open_time", "datetime") if c in cols), None)
    if ts_col is None:
        raise SystemExit(f"{path}: no timestamp column (need timestamp_utc)")
    for k in ("open", "high", "low", "close"):
        if k not in cols:
            raise SystemExit(f"{path}: missing column {k}")
    data: Dict[str, list] = {"ts": [], "open": [], "high": [], "low": [], "close": [], "volume": []}
    for r in rows:
        data["ts"].append(parse_ts(r[ts_col]))
        for k in ("open", "high", "low", "close"):
            data[k].append(float(r[cols[k]]))
        vol = r.get(cols.get("volume", ""), "") if "volume" in cols else ""
        data["volume"].append(float(vol) if vol not in ("", None) else 0.0)
    order = sorted(range(len(data["ts"])), key=lambda i: data["ts"][i])
    return {k: [v[i] for i in order] for k, v in data.items()}


def detect_timeframe_seconds(ts: List[datetime]) -> float:
    if len(ts) < 3:
        return 0.0
    diffs = sorted((ts[i + 1] - ts[i]).total_seconds() for i in range(len(ts) - 1))
    return diffs[len(diffs) // 2]


def tf_label(seconds: float) -> str:
    mins = seconds / 60
    if mins <= 0:
        return "?"
    if mins < 60:
        return f"{int(mins)}m"
    if mins < 1440:
        return f"{int(mins // 60)}h"
    if mins < 10080:
        return f"{int(mins // 1440)}d"
    return f"{int(mins // 10080)}w"


# -------------------------------------------------------------------- clock ---

def session_label(dt: datetime) -> str:
    h = dt.hour
    if h < 7:
        return "asia"
    if h < 13:
        return "london"
    if h < 16:
        return "london-new york overlap"
    if h < 21:
        return "new york"
    return "late us / pre-asia"


def minutes_until(now: datetime, hour: int, minute: int = 0) -> int:
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if target <= now:
        target += timedelta(days=1)
    return int((target - now).total_seconds() // 60)


def clock(now: datetime) -> dict:
    wd = now.weekday()
    today = now.date()
    us_open = events.et_to_utc(today, 9, 30)
    us_data = events.et_to_utc(today, 8, 30)
    us_close = events.et_to_utc(today, 16, 0)
    ldn_open = events.london_to_utc(today, 8, 0)
    cme_close_fri = events.et_to_utc(today, 17, 0)   # Friday 17:00 ET
    cme_open_sun = events.et_to_utc(today, 18, 0)    # Sunday 18:00 ET
    cme_closed = (wd == 4 and now >= cme_close_fri) or wd == 5 or (wd == 6 and now < cme_open_sun)

    def mins(target: datetime) -> int:
        while target <= now:
            target += timedelta(days=1)
        return int((target - now).total_seconds() // 60)

    t1 = events.next_tier1(now)
    return {
        "now_utc": now.strftime("%Y-%m-%d %H:%M"),
        "weekday": now.strftime("%A"),
        "session": session_label(now),
        "us_dst": events.us_dst(today),
        "us_open_utc": us_open.strftime("%H:%M"),
        "minutes_to_daily_close": minutes_until(now, 0),
        "minutes_to_london_open": mins(ldn_open),
        "minutes_to_us_data": mins(us_data),
        "minutes_to_us_open": mins(us_open),
        "minutes_to_us_close": mins(us_close),
        "minutes_to_next_funding": min(minutes_until(now, 0), minutes_until(now, 8), minutes_until(now, 16)),
        "weekend": wd >= 5,
        "cme_closed": cme_closed,
        "next_tier1": t1,
    }


# ----------------------------------------------------------------- analysis ---

def r(v, nd=2):
    return None if v is None else round(v, nd)


def analyze(data: Dict[str, list], swing_n: int, now: Optional[datetime] = None) -> dict:
    now = now or datetime.now(timezone.utc)
    ts, o, h, l, c, v = (data[k] for k in ("ts", "open", "high", "low", "close", "volume"))
    n = len(c)
    tf_sec = detect_timeframe_seconds(ts)
    tf = tf_label(tf_sec)
    intraday = tf.endswith("m") or tf.endswith("h")
    price = c[-1]
    in_progress = tf_sec > 0 and now < ts[-1] + timedelta(seconds=tf_sec)
    k = n - 2 if (in_progress and n >= 2) else n - 1  # index of the last CLOSED candle

    out: dict = {
        "timeframe": tf, "candles": n, "price": price,
        "first_candle_utc": ts[0].strftime("%Y-%m-%dT%H:%MZ"),
        "last_candle_open_utc": ts[-1].strftime("%Y-%m-%dT%H:%MZ"),
        "last_candle_in_progress": in_progress,
        "data_age_minutes": int((now - ts[-1]).total_seconds() // 60),
    }
    if out["data_age_minutes"] > 2 * max(tf_sec, 60) / 60:
        out["stale_warning"] = f"data is {out['data_age_minutes']} minutes old; refetch before acting"

    atr14 = ind.atr(h, l, c, 14)
    a = ind.last_value(atr14)
    out["atr14"] = r(a, 6)
    out["atr14_pct"] = r(a / price * 100, 3) if a else None

    # moving averages
    ema_series = {p: ind.ema(c, p) for p in (9, 21, 50, 200)}
    emas: dict = {}
    for p, series in ema_series.items():
        e = ind.last_value(series)
        emas[f"ema{p}"] = r(e, 6)
        emas[f"ema{p}_distance_atr"] = r((price - e) / a, 2) if (e is not None and a) else None
    out["ema"] = emas
    e21, e50, e200 = emas.get("ema21"), emas.get("ema50"), emas.get("ema200")
    if None not in (e21, e50, e200):
        out["ema_stack"] = ("bullish (21 > 50 > 200)" if e21 > e50 > e200 else
                            "bearish (21 < 50 < 200)" if e21 < e50 < e200 else "mixed / ranging")
    elif None not in (e21, e50):
        out["ema_stack"] = ("21 above 50 (no 200 yet)" if e21 > e50 else "21 below 50 (no 200 yet)")
    else:
        out["ema_stack"] = "insufficient data"
    out["price_vs_ema200"] = None if e200 is None else ("above" if price > e200 else "below")

    # momentum
    rsi14 = ind.rsi(c, 14)
    out["rsi14"] = r(ind.last_value(rsi14), 1)
    _, _, m_hist = ind.macd(c)
    hist_now, hist_prev = m_hist[k], (m_hist[k - 1] if k >= 1 else None)
    out["macd_hist"] = r(hist_now, 6)
    out["macd_hist_direction"] = (None if hist_now is None or hist_prev is None
                                  else ("rising" if hist_now > hist_prev else "falling"))

    # bollinger
    bb_mid, bb_up, bb_lo, bb_w = ind.bollinger(c, 20, 2.0)
    w_now = ind.last_value(bb_w)
    bb = {"upper": r(ind.last_value(bb_up), 6), "middle": r(ind.last_value(bb_mid), 6), "lower": r(ind.last_value(bb_lo), 6),
          "bandwidth_pct": r(w_now * 100, 3) if w_now else None,
          "bandwidth_percentile_100": r(ind.percentile_rank(bb_w, w_now, 100), 0) if w_now else None}
    out["bollinger"] = bb

    # volume (on the last closed candle; an in-progress candle has partial volume)
    rvol = ind.relative_volume(v, 20)
    out["rvol_last_closed"] = r(rvol[k], 2) if rvol[k] is not None else None
    out["rvol_in_progress"] = r(rvol[-1], 2) if (in_progress and rvol[-1] is not None) else None

    # session VWAP (intraday only): reset at 00:00 UTC
    vw = None
    if intraday:
        flags_ = [i == 0 or ts[i].date() != ts[i - 1].date() for i in range(n)]
        vw = ind.vwap(h, l, c, v, flags_)
        vw_now = ind.last_value(vw)
        out["session_vwap"] = r(vw_now, 6)
        out["price_vs_vwap"] = None if vw_now is None else ("above" if price > vw_now else "below")
        out["vwap_distance_atr"] = r((price - vw_now) / a, 2) if (vw_now and a) else None

    # swings & trend (only candles up to the last closed one can be swings)
    sh, sl = ind.swing_points(h[:k + 1], l[:k + 1], swing_n)
    out["swing_highs"] = [{"t": ts[i].strftime("%m-%d %H:%M"), "price": h[i]} for i in sh[-5:]]
    out["swing_lows"] = [{"t": ts[i].strftime("%m-%d %H:%M"), "price": l[i]} for i in sl[-5:]]
    out["trend"] = ind.classify_trend(h, l, sh, sl)
    last_sh = h[sh[-1]] if sh else None
    last_sl = l[sl[-1]] if sl else None
    out["last_swing_high"] = last_sh
    out["last_swing_low"] = last_sl
    if last_sh is not None and last_sl is not None and last_sh != last_sl:
        out["position_in_swing_pct"] = r((price - last_sl) / (last_sh - last_sl) * 100, 1)
    if a:
        tol = 0.15 * a
        out["equal_highs"] = [r(x, 6) for x in ind.equal_levels([h[i] for i in sh[-8:]], tol)]
        out["equal_lows"] = [r(x, 6) for x in ind.equal_levels([l[i] for i in sl[-8:]], tol)]

    # RSI divergence on the last two swings
    div = []
    if len(sh) >= 2 and rsi14[sh[-1]] is not None and rsi14[sh[-2]] is not None:
        if h[sh[-1]] > h[sh[-2]] and rsi14[sh[-1]] < rsi14[sh[-2]]:
            div.append("bearish RSI divergence (higher high, lower RSI)")
    if len(sl) >= 2 and rsi14[sl[-1]] is not None and rsi14[sl[-2]] is not None:
        if l[sl[-1]] < l[sl[-2]] and rsi14[sl[-1]] > rsi14[sl[-2]]:
            div.append("bullish RSI divergence (lower low, higher RSI)")
    out["rsi_divergence"] = div

    # recent range
    look = min(k + 1, 60)
    seg_h, seg_l = h[k + 1 - look:k + 1], l[k + 1 - look:k + 1]
    rng_hi, rng_lo = max(seg_h), min(seg_l)
    out["recent_range"] = {"candles": look, "high": rng_hi, "low": rng_lo,
                           "height_atr": r((rng_hi - rng_lo) / a, 2) if a else None,
                           "price_position_pct": r((price - rng_lo) / (rng_hi - rng_lo) * 100, 1) if rng_hi != rng_lo else None}

    # daily levels
    if intraday:
        days: Dict[str, dict] = {}
        for i in range(n):
            d = ts[i].date().isoformat()
            day = days.setdefault(d, {"open": o[i], "high": h[i], "low": l[i], "close": c[i]})
            day["high"] = max(day["high"], h[i]); day["low"] = min(day["low"], l[i]); day["close"] = c[i]
        keys = sorted(days)
        if len(keys) >= 2:
            pd_ = days[keys[-2]]
            out["prior_day"] = {"date": keys[-2], "high": pd_["high"], "low": pd_["low"], "close": pd_["close"]}
        td = days[keys[-1]]
        out["today"] = {"date": keys[-1], "open": td["open"], "high": td["high"], "low": td["low"]}
    elif tf.endswith("d") and n >= 2:
        out["prior_day"] = {"date": ts[-2].date().isoformat(), "high": h[-2], "low": l[-2], "close": c[-2]}
        out["today"] = {"date": ts[-1].date().isoformat(), "open": o[-1], "high": h[-1], "low": l[-1]}

    # last closed candle anatomy
    body = abs(c[k] - o[k]); rng_ = h[k] - l[k]
    out["last_closed_candle"] = {
        "time": ts[k].strftime("%Y-%m-%d %H:%M"), "open": o[k], "high": h[k], "low": l[k], "close": c[k], "volume": v[k],
        "direction": "up" if c[k] >= o[k] else "down",
        "body_pct_of_range": r(body / rng_ * 100, 0) if rng_ else None,
        "upper_wick": r(h[k] - max(o[k], c[k]), 6), "lower_wick": r(min(o[k], c[k]) - l[k], 6),
    }

    # key levels sorted by distance
    levels: List[dict] = []

    def add(name, val):
        if val is not None and val > 0:
            levels.append({"level": name, "price": r(val, 6), "distance_pct": r((val - price) / price * 100, 2),
                           "distance_atr": r((val - price) / a, 2) if a else None})

    for p in (21, 50, 200):
        add(f"ema{p}", emas.get(f"ema{p}"))
    add("session_vwap", out.get("session_vwap"))
    if "prior_day" in out:
        add("prior_day_high", out["prior_day"]["high"]); add("prior_day_low", out["prior_day"]["low"]); add("prior_day_close", out["prior_day"]["close"])
    if "today" in out:
        add("today_open", out["today"]["open"]); add("today_high", out["today"]["high"]); add("today_low", out["today"]["low"])
    add("last_swing_high", last_sh); add("last_swing_low", last_sl)
    add(f"range{look}_high", rng_hi); add(f"range{look}_low", rng_lo)
    add("bb_upper", bb["upper"]); add("bb_lower", bb["lower"])
    for x in out.get("equal_highs", []):
        add("equal_highs", x)
    for x in out.get("equal_lows", []):
        add("equal_lows", x)
    levels.sort(key=lambda d: abs(d["distance_pct"]))
    out["levels_by_distance"] = levels

    out["flags"] = setup_flags(out, data, k, a, ema_series, vw, sh, sl, bb_up, bb_lo, rvol)
    return out


def setup_flags(s: dict, d: dict, k: int, a: Optional[float], ema_series: dict, vw, sh, sl, bb_up, bb_lo, rvol) -> List[str]:
    """Mechanical pre-screen for the playbooks. A flag is a reason to LOOK, never a signal."""
    if not a or k < 2:
        return []
    o, h, l, c = d["open"], d["high"], d["low"], d["close"]
    price = s["price"]
    flags: List[str] = []
    stack = s.get("ema_stack", "")
    e21 = ema_series[21][k]
    trend = s.get("trend")

    if s["bollinger"].get("bandwidth_percentile_100") is not None and s["bollinger"]["bandwidth_percentile_100"] <= 15:
        flags.append("SQUEEZE: Bollinger bandwidth in bottom 15% of last 100 candles (playbook 3/6: wait for the break + retest)")
    if e21 is not None:
        dist = (price - e21) / a
        if abs(dist) > 2:
            flags.append(f"STRETCHED: price {dist:+.1f} ATR from 21 EMA; chasing here is a C setup")
        if abs(dist) <= 0.5:
            if stack.startswith("bullish") and trend in ("uptrend", "unknown", "range"):
                flags.append("PULLBACK TO VALUE (long): price within 0.5 ATR of 21 EMA in a bullish stack (playbook 1)")
            if stack.startswith("bearish") and trend in ("downtrend", "unknown", "range"):
                flags.append("PULLBACK TO VALUE (short): price within 0.5 ATR of 21 EMA in a bearish stack (playbook 1)")

    rr = s["recent_range"]
    if rr["height_atr"] and rr["height_atr"] >= 2.5:
        if abs(price - rr["high"]) <= 0.3 * a:
            flags.append(f"AT RANGE HIGH {rr['high']}: fade with rejection (playbook 2) or wait for break + retest (playbook 3)")
        if abs(price - rr["low"]) <= 0.3 * a:
            flags.append(f"AT RANGE LOW {rr['low']}: fade with rejection (playbook 2) or wait for break + retest (playbook 3)")

    # liquidity sweeps on the last closed candle
    pools_low = list(s.get("equal_lows", []))
    pools_high = list(s.get("equal_highs", []))
    if "prior_day" in s:
        pools_low.append(s["prior_day"]["low"]); pools_high.append(s["prior_day"]["high"])
    if len(sl) >= 2:
        pools_low.append(l[sl[-2]])
    if len(sh) >= 2:
        pools_high.append(h[sh[-2]])
    for lvl in pools_low:
        if lvl and l[k] < lvl - 0.05 * a and c[k] > lvl and l[k - 1] >= lvl - 0.05 * a:
            flags.append(f"SWEEP OF LOWS at {lvl}: last closed candle wicked below and closed back above (playbook 4 long candidate)")
            break
    for lvl in pools_high:
        if lvl and h[k] > lvl + 0.05 * a and c[k] < lvl and h[k - 1] <= lvl + 0.05 * a:
            flags.append(f"SWEEP OF HIGHS at {lvl}: last closed candle wicked above and closed back below (playbook 4 short candidate)")
            break

    # VWAP reclaim / loss (intraday timeframes up to 1h; a 4h session VWAP has too few candles to mean much)
    tf_ok = s["timeframe"].endswith("m") or s["timeframe"] in ("1h",)
    if tf_ok and vw is not None and vw[k] is not None and vw[k - 1] is not None:
        if c[k - 1] < vw[k - 1] and c[k] > vw[k]:
            flags.append("VWAP RECLAIM: last closed candle closed back above session VWAP (playbook 7 long)")
        if c[k - 1] > vw[k - 1] and c[k] < vw[k]:
            flags.append("VWAP LOSS: last closed candle closed below session VWAP (playbook 7 short if VWAP is falling)")

    # structure events
    if len(sh) >= 1 and len(sl) >= 1:
        prev_sh = h[sh[-1]] if sh[-1] < k else (h[sh[-2]] if len(sh) >= 2 else None)
        prev_sl = l[sl[-1]] if sl[-1] < k else (l[sl[-2]] if len(sl) >= 2 else None)
        if prev_sh is not None and c[k] > prev_sh:
            flags.append(f"CLOSE ABOVE SWING HIGH {prev_sh}: " + ("break of structure up (expect pullback; playbook 1/3)" if trend != "downtrend" else "change of character up in a downtrend (first warning, not a reversal)"))
        if prev_sl is not None and c[k] < prev_sl:
            flags.append(f"CLOSE BELOW SWING LOW {prev_sl}: " + ("break of structure down (expect bounce; playbook 1/3 short)" if trend != "uptrend" else "change of character down in an uptrend (first warning, not a reversal)"))

    if rvol[k] is not None and rvol[k] >= 1.5:
        flags.append(f"RVOL {rvol[k]:.1f}x on the last closed candle: participation (validates breaks/sweeps)")
    for dv in s.get("rsi_divergence", []):
        flags.append("DIVERGENCE: " + dv + " (tighten targets; look for structure confirmation)")
    if bb_up[k] is not None and c[k - 1] > bb_up[k - 1] and c[k] <= bb_up[k] and not stack.startswith("bullish"):
        flags.append("CLOSE BACK INSIDE UPPER BAND: mean-reversion short candidate if range (playbook 2)")
    if bb_lo[k] is not None and c[k - 1] < bb_lo[k - 1] and c[k] >= bb_lo[k] and not stack.startswith("bearish"):
        flags.append("CLOSE BACK INSIDE LOWER BAND: mean-reversion long candidate if range (playbook 2)")
    return flags


# ------------------------------------------------------------------ output ---

def summarize(s: dict) -> str:
    tf = s["timeframe"]
    prog = " (last candle IN PROGRESS)" if s["last_candle_in_progress"] else ""
    L = [f"[{tf}] {s['candles']} candles, last open {s['last_candle_open_utc']}{prog}, price {s['price']}, "
         f"ATR14 {s['atr14']} ({s['atr14_pct']}%)"]
    if s.get("stale_warning"):
        L.append("  WARNING: " + s["stale_warning"])
    e = s["ema"]
    L.append(f"  trend: {s['trend'].upper()} | EMA stack: {s['ema_stack']} | price {s['price_vs_ema200']} 200 EMA | "
             f"{e.get('ema21_distance_atr')} ATR from 21 EMA | RSI14 {s['rsi14']} | MACD hist {s['macd_hist_direction']}")
    L.append(f"  RVOL last closed {s['rvol_last_closed']}" + (f" (in-progress candle {s['rvol_in_progress']})" if s.get("rvol_in_progress") is not None else ""))
    if s.get("last_swing_high") is not None:
        L.append(f"  last swing high {s['last_swing_high']}  last swing low {s['last_swing_low']}  (price at {s.get('position_in_swing_pct')}% of that swing)")
    if s.get("equal_highs") or s.get("equal_lows"):
        L.append(f"  equal highs {s.get('equal_highs')}  equal lows {s.get('equal_lows')}  <- liquidity pools")
    rr = s["recent_range"]
    L.append(f"  last {rr['candles']} closed candles: {rr['low']} - {rr['high']} ({rr['height_atr']} ATR tall), price at {rr['price_position_pct']}%")
    bb = s["bollinger"]
    L.append(f"  bollinger {bb['lower']} / {bb['middle']} / {bb['upper']}, bandwidth percentile {bb['bandwidth_percentile_100']}")
    if "session_vwap" in s:
        L.append(f"  session VWAP {s['session_vwap']} (price {s['price_vs_vwap']}, {s['vwap_distance_atr']} ATR away)")
    if "prior_day" in s:
        pd_ = s["prior_day"]; td = s["today"]
        L.append(f"  PDH {pd_['high']}  PDL {pd_['low']}  PDC {pd_['close']}  | today open {td['open']} high {td['high']} low {td['low']}")
    lc = s["last_closed_candle"]
    L.append(f"  last closed candle {lc['time']}: {lc['direction']} body {lc['body_pct_of_range']}% of range, "
             f"wicks up {lc['upper_wick']} / down {lc['lower_wick']}")
    L.append("  nearest levels: " + ", ".join(f"{lv['level']} {lv['price']} ({lv['distance_pct']:+}%)" for lv in s["levels_by_distance"][:7]))
    if s["flags"]:
        L.append("  FLAGS:")
        L.extend("    - " + f for f in s["flags"])
    else:
        L.append("  FLAGS: none (nothing mechanical is lining up on this timeframe)")
    return "\n".join(L)


def clock_summary(ck: dict) -> str:
    bits = [f"CLOCK {ck['now_utc']} UTC, {ck['weekday']}, session: {ck['session']} "
            f"(US open is {ck['us_open_utc']} UTC {'in summer time' if ck['us_dst'] else 'in winter time'})",
            f"  daily close in {ck['minutes_to_daily_close']} min | London open in {ck['minutes_to_london_open']} min | "
            f"US data (08:30 NY) in {ck['minutes_to_us_data']} min | US open in {ck['minutes_to_us_open']} min | "
            f"next funding in {ck['minutes_to_next_funding']} min"]
    t1 = ck.get("next_tier1", {})
    if t1.get("loaded"):
        bits.append(f"  next tier-1 event: {t1['event']} at {t1['utc']} UTC ({t1['in_minutes']} min)")
        if t1.get("warning"):
            bits.append("  WARNING: " + t1["warning"])
    else:
        bits.append("  WARNING: " + t1.get("note", "no tier-1 calendar loaded"))
    if ck["weekend"]:
        bits.append("  WEEKEND: thin liquidity, larger wicks, less follow-through; reduce size or skip")
    if ck["cme_closed"]:
        bits.append("  CME closed: a weekend gap is forming on CME BTC futures")
    return "\n".join(bits)


def tf_minutes(tf: str) -> int:
    unit = tf[-1]
    num = int(tf[:-1]) if tf[:-1].isdigit() else 0
    return num * {"m": 1, "h": 60, "d": 1440, "w": 10080}.get(unit, 1)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv", nargs="+", help="one or more OHLCV CSV files (any timeframes)")
    ap.add_argument("--swing-n", type=int, default=3, help="fractal width for swing detection")
    ap.add_argument("--json", help="write full snapshot JSON here")
    ap.add_argument("--now", help="override 'now' (ISO UTC) for reproducible tests")
    a = ap.parse_args()

    now = parse_ts(a.now) if a.now else datetime.now(timezone.utc)
    snaps = []
    for path in a.csv:
        s = analyze(load_csv(path), a.swing_n, now)
        s["file"] = path
        snaps.append(s)
    snaps.sort(key=lambda s: -tf_minutes(s["timeframe"]))

    ck = clock(now)
    print(clock_summary(ck))
    print()
    for s in snaps:
        print(summarize(s))
        print()
    if a.json:
        with open(a.json, "w", encoding="utf-8") as fh:
            json.dump({"generated_utc": now.isoformat(), "clock": ck, "timeframes": snaps}, fh, indent=2, default=str)
        print(f"json written to {a.json}")


if __name__ == "__main__":
    main()
