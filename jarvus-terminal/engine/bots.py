#!/usr/bin/env python3
"""The bots: six automated traders that scan, decide, trade and learn on their own.

Press Run once. From then on, every five minutes the bots scan every liquid market,
run all 66 strategies against each one, pick out the setups that match their own
playbook, **backtest those exact setups on that coin's last 1,500 hours using the exact
exits they will trade with**, and buy only what passes. Every fifteen seconds they check
every open position against the live price and sell at the stop, the target or the time
limit. They keep running across restarts until you press Stop.

This is practice money: real live prices, real fees and real slippage, no real funds.

The rule every bot trades by, and why
-------------------------------------
Measured walk-forward on 15 markets x 3,300 hours (each decision made using only data
from before it):

  * Taking every strategy signal lost money after fees, in every exit style tried.
    The strategies on their own were no better than buying at random.
  * The bots' full rule, at 10bps slippage: skip any trade where fees would eat more
    than 20% of the risk, then take a signal **only when that strategy had made at
    least +0.15R per trade on that same coin over its previous 1,500 hours (12+
    trades) and beaten random buying there**. Result: +0.22R per trade over 675
    trades, positive in all three test windows (+0.15R, +0.27R, +0.19R). Random
    buying made -0.26R, +0.21R and +0.17R over the same windows.
  * The edge came mostly from volatile small coins (+0.30R); on majors it was +0.07R
    and negative in the latest window. One 75-day period, 15 markets chosen while they
    were busy. A filter that keeps the bots out of what has stopped working, not a
    guarantee of profit.
  * Holding up to 4 days beat day-length holds. Exits within 24 hours lost money even
    with the filter, because fees and forced exits cut the winners short. So the
    default hold is up to 96 hours; it can be shortened, and the Bots tab says what
    that costs.

That filter is the bots' main defence, and it is re-checked before every single trade.

On top of it the bots learn from their own closed trades: a strategy that keeps losing
for them gets benched, a coin that keeps losing gets avoided, and a bot on a losing
streak cuts its own risk. Learning only ever makes them more careful. Nothing here ever
raises risk above what you set, adds to a loser, or martingales.
"""

from __future__ import annotations

import json
import os
import statistics
import threading
import time
import traceback
from collections import Counter
from datetime import datetime, timedelta, timezone
from typing import Callable, Dict, List, Optional, Tuple

import config
from engine import automation, backtest, broker as B, learn, marketdata, portfolio, research, store
from engine import strategies as S
from engine import swarm

SCHEMA = """
CREATE TABLE IF NOT EXISTS bots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key TEXT UNIQUE NOT NULL,
    name TEXT NOT NULL,
    enabled INTEGER NOT NULL DEFAULT 1,
    starting_cash REAL NOT NULL,
    cash REAL NOT NULL,
    created_at TEXT NOT NULL,
    overrides TEXT
);
CREATE TABLE IF NOT EXISTS bot_positions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    bot_id INTEGER NOT NULL,
    symbol TEXT NOT NULL, venue TEXT, base TEXT,
    opened_at TEXT NOT NULL,
    entry REAL NOT NULL,
    units_initial REAL NOT NULL, units_open REAL NOT NULL,
    stop REAL NOT NULL, initial_stop REAL NOT NULL, target REAL, atr REAL,
    risk_amount REAL NOT NULL, fees REAL NOT NULL DEFAULT 0,
    highest REAL, partial_done INTEGER NOT NULL DEFAULT 0,
    policy TEXT, lead_strategy TEXT, strategies TEXT, gate_label TEXT,
    score REAL, why TEXT, verification TEXT,
    last_price REAL,
    closed_at TEXT, exit_reason TEXT, pnl REAL, r_multiple REAL
);
CREATE INDEX IF NOT EXISTS idx_bp_open ON bot_positions(closed_at, bot_id);
CREATE TABLE IF NOT EXISTS bot_fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    position_id INTEGER NOT NULL, bot_id INTEGER NOT NULL, ts TEXT NOT NULL,
    side TEXT NOT NULL, units REAL NOT NULL, price REAL NOT NULL, fee REAL NOT NULL, reason TEXT
);
CREATE INDEX IF NOT EXISTS idx_bf_pos ON bot_fills(position_id);
CREATE TABLE IF NOT EXISTS bot_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL, bot TEXT, kind TEXT NOT NULL, symbol TEXT,
    message TEXT NOT NULL, data TEXT
);
CREATE INDEX IF NOT EXISTS idx_bl_id ON bot_log(id DESC);
"""

ALL = "*"

# Each bot is one playbook: which strategy families it listens to and how many of its
# own strategies must agree. Everything else is shared and adjustable.
BOT_DEFS: List[Dict] = [
    {"key": "trend", "name": "Trend Rider", "families": ["trend"], "min_signals": 2,
     "playbook": "Buys pullbacks and continuations in markets already trending up, when at least "
                 "two of its 16 trend strategies agree."},
    {"key": "breakout", "name": "Breakout Hunter", "families": ["breakout"], "min_signals": 2,
     "gates": ["LOUD", "COILED"],
     "playbook": "Waits for a market to coil tight or start moving hard, then buys the break when "
                 "two of its 16 breakout strategies fire."},
    {"key": "dip", "name": "Dip Buyer", "families": ["mean-reversion"], "min_signals": 1,
     "playbook": "Buys sharp, oversold dips in markets whose bigger trend is not down, betting on "
                 "the snap back."},
    {"key": "momentum", "name": "Momentum", "families": ["momentum"], "min_signals": 2,
     "playbook": "Buys when momentum turns up (MACD, RSI, rate of change) and two of its 8 momentum "
                 "strategies agree."},
    {"key": "smart", "name": "Smart Money", "families": ["structure", "volume"], "min_signals": 2,
     "playbook": "Trades liquidity sweeps, order blocks, fair-value gaps and volume absorption, the "
                 "footprints large traders leave."},
    {"key": "swarm", "name": "Swarm Captain", "families": ALL, "min_signals": 3,
     "min_families": 3, "min_consensus": 0.30,
     "playbook": "Only trades when at least three different strategy families agree at once, across "
                 "all 66 strategies."},
]
BOT_BY_KEY = {b["key"]: b for b in BOT_DEFS}

COMMON_RULE = ("Before every trade it backtests the strategies that fired on that coin's last 1,500 "
               "hours using the exact exits it will trade with, and only buys if they made at least "
               "+0.15R per trade there and beat random buying.")

# Shared defaults. Every one of these is chosen from a measurement in the module docstring
# or from the existing risk model; none is a guess dressed up as a setting.
SHARED_DEFAULTS: Dict = {
    "risk_pct": 1.0,              # of the bot's own equity, lost if the stop is hit
    "max_positions": 3,           # per bot
    "max_position_pct": 40.0,     # largest single position, % of the bot's equity
    "stop_atr": 4.0,              # wide stops are what survive retail fees
    "target_r": 2.0,
    "max_hold_h": 96,             # measured: 4-day holds beat 24h holds after fees
    "partial_r": 0.0,             # take part profit at this R (0 = off; measured worse)
    "partial_frac": 0.5,
    "trail_atr": 0.0,             # trail the stop after the partial (0 = off)
    "max_cost_r": 0.20,           # round-trip fees as a share of the risk
    "min_volume_usd": 10_000_000,
    "gates": ["LOUD", "COILED", "NORMAL"],
    "avoid_htf_downtrend": True,
    "verify": True,
    "verify_bars": 1500,
    "verify_min_trades": 12,
    "verify_min_edge": 0.15,
    "verify_beat_control": True,
    "cooldown_h": 6,              # after a trade on a coin, per bot
    "max_trades_per_day": 6,
    "daily_loss_limit_pct": 4.0,  # of the bot's equity; stops new trades until 00:00 UTC
    "loss_streak": 4,
    "loss_streak_pause_h": 12,
}

# Hard bounds. Settings outside these are clamped, so a typo cannot bet the account.
LIMITS: Dict[str, Tuple[float, float]] = {
    "risk_pct": (0.05, 3.0), "max_positions": (1, 8), "max_position_pct": (5, 100),
    "stop_atr": (1.0, 10.0), "target_r": (0.5, 10.0), "max_hold_h": (2, 720),
    "partial_r": (0.0, 5.0), "partial_frac": (0.1, 0.9), "trail_atr": (0.0, 10.0),
    "max_cost_r": (0.02, 0.5), "min_volume_usd": (0, 5e9), "verify_bars": (400, 3000),
    "verify_min_trades": (3, 100), "verify_min_edge": (-1.0, 2.0), "cooldown_h": (0, 168),
    "max_trades_per_day": (1, 50), "daily_loss_limit_pct": (0.5, 20.0),
    "loss_streak": (2, 20), "loss_streak_pause_h": (1, 168),
}

GLOBAL_DEFAULTS: Dict = {
    "running": False,
    "practice_money": 10_000.0,
    "scan_interval_s": 300,
    "manage_interval_s": 15,
    "max_bots_per_coin": 2,
    "auto_research_h": 24,
    "shared": {},
}

SETTINGS_PATH = os.path.join(config.DATA_DIR, "bots.json")
LEARN_PRIOR_N = 8          # shrink every learned average toward zero by this many trades


# =============================================================================
# settings
# =============================================================================

def _clamp(key: str, value):
    if key in LIMITS and isinstance(value, (int, float)) and not isinstance(value, bool):
        lo, hi = LIMITS[key]
        value = max(lo, min(hi, value))
        if key in ("max_positions", "max_trades_per_day", "loss_streak", "verify_bars",
                   "verify_min_trades", "max_hold_h"):
            value = int(value)
    return value


def load_settings() -> Dict:
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as fh:
            got = json.load(fh)
    except Exception:                                        # noqa: BLE001
        got = {}
    out = {**GLOBAL_DEFAULTS, **{k: v for k, v in got.items() if k in GLOBAL_DEFAULTS}}
    out["shared"] = {k: _clamp(k, v) for k, v in (got.get("shared") or {}).items() if k in SHARED_DEFAULTS}
    return out


def save_settings(patch: Dict) -> Dict:
    cur = load_settings()
    for k, v in (patch or {}).items():
        if k == "shared" and isinstance(v, dict):
            cur["shared"].update({kk: _clamp(kk, vv) for kk, vv in v.items() if kk in SHARED_DEFAULTS})
        elif k in GLOBAL_DEFAULTS:
            cur[k] = v
    cur["scan_interval_s"] = int(max(120, min(3600, cur["scan_interval_s"])))
    cur["manage_interval_s"] = int(max(5, min(120, cur["manage_interval_s"])))
    cur["max_bots_per_coin"] = int(max(1, min(6, cur["max_bots_per_coin"])))
    os.makedirs(os.path.dirname(SETTINGS_PATH), exist_ok=True)
    tmp = SETTINGS_PATH + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        json.dump(cur, fh, indent=2)
    os.replace(tmp, SETTINGS_PATH)
    return cur


def bot_config(bot_row: Dict, settings: Dict = None) -> Dict:
    """Shared defaults, then your shared settings, then the bot's playbook, then its own overrides."""
    settings = settings or load_settings()
    d = BOT_BY_KEY.get(bot_row["key"], {})
    cfg = {**SHARED_DEFAULTS, **settings.get("shared", {})}
    for k in ("families", "min_signals", "min_families", "min_consensus", "gates"):
        if k in d:
            cfg[k] = d[k]
    try:
        over = json.loads(bot_row.get("overrides") or "{}")
    except (TypeError, ValueError):
        over = {}
    for k, v in over.items():
        if k in SHARED_DEFAULTS or k in ("min_signals", "min_families", "min_consensus"):
            cfg[k] = _clamp(k, v)
    cfg.setdefault("families", ALL)
    cfg.setdefault("min_signals", 2)
    return cfg


def policy_of(cfg: Dict) -> Dict:
    return {k: cfg[k] for k in ("stop_atr", "target_r", "max_hold_h", "partial_r", "partial_frac", "trail_atr")}


# =============================================================================
# the exit policy, shared by the backtest and the live position manager
# =============================================================================

def policy_exit(candles: List[dict], j0: int, entry: float, atr: float, pol: Dict,
                fee: float, slip: float):
    """Walk forward from the entry bar applying the exact exits a bot trades with.

    Pessimistic like the rest of the backtester: the stop is checked before anything
    else in a bar, a gap through the stop fills at the open, and a trade still open
    when the data ends is marked out at the close.
    Returns (exit_index, r_after_all_costs, reason).
    """
    risk = pol["stop_atr"] * atr
    if risk <= 0:
        return None
    stop = entry - risk
    target = entry + pol["target_r"] * risk
    pr, pf, trail = pol.get("partial_r") or 0, pol.get("partial_frac", 0.5), pol.get("trail_atr") or 0
    n = len(candles)
    last = min(n - 1, j0 + int(pol["max_hold_h"]) - 1)
    frac, gross, exit_notional, partial, highest = 1.0, 0.0, 0.0, False, entry
    j, reason = j0, "time"
    while j <= last:
        c = candles[j]
        if c["low"] <= stop:
            px = min(c["open"], stop) * (1 - slip)
            gross += frac * (px - entry)
            exit_notional += frac * px
            frac = 0.0
            reason = "stop" if stop <= entry - risk + 1e-12 else "protected stop"
            break
        if pr and not partial and c["high"] >= entry + pr * risk:
            px = entry + pr * risk
            gross += pf * (px - entry)
            exit_notional += pf * px
            frac -= pf
            partial = True
            stop = max(stop, entry * (1 + 2 * (fee + slip)))       # breakeven after costs
        if c["high"] >= target:
            gross += frac * (target - entry)
            exit_notional += frac * target
            frac = 0.0
            reason = "target"
            break
        highest = max(highest, c["high"])
        if partial and trail:
            stop = max(stop, highest - trail * atr)
        j += 1
    if frac > 0:
        j = min(j, last)
        px = candles[j]["close"] * (1 - slip)
        gross += frac * (px - entry)
        exit_notional += frac * px
    return j, (gross - fee * (entry + exit_notional)) / risk, reason


# =============================================================================
# verification: backtest the firing strategies on this coin before trading it
# =============================================================================

class Verifier:
    """Per-coin, per-strategy backtests with the bots' own exit policy, cached per hour.

    A strategy's history on a coin only changes when a new hourly candle closes, so the
    expensive walk is done at most once per strategy per coin per hour and every bot
    that asks in between reads the same answer.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._trades: Dict[tuple, List[tuple]] = {}
        self._series: Dict[tuple, S.SeriesCache] = {}
        self.backtests_run = 0
        self.bars_walked = 0

    def _candles(self, symbol: str, venue: str, want: int) -> List[dict]:
        return marketdata.deep_candles(symbol, venue, "1h", want)

    def check(self, symbol: str, venue: str, names: List[str], pol: Dict, cfg: Dict,
              fee: float, slip: float) -> Dict:
        want = int(cfg["verify_bars"]) + 260
        candles = self._candles(symbol, venue, want)
        n = len(candles)
        if n < 600:
            return {"ok": False, "reason": f"only {n} hours of history, need 600+ to verify", "per": {}}
        last_ts = candles[-1]["ts"]
        pkey = json.dumps(pol, sort_keys=True) + f"|{fee:.6f}|{slip:.6f}"
        start = n - int(cfg["verify_bars"])

        with self._lock:
            sc = self._series.get((symbol, last_ts))
            if sc is None:
                # drop older snapshots of this coin before adding the new one
                for k in [k for k in self._series if k[0] == symbol]:
                    self._series.pop(k, None)
                for k in [k for k in self._trades if k[0] == symbol and k[3] != last_ts]:
                    self._trades.pop(k, None)
                sc = S.SeriesCache(candles)
                self._series[(symbol, last_ts)] = sc
                # Coins rotate in and out of the top 40 all day. Keep the most recent 60
                # so memory stays flat however long the bots run.
                while len(self._series) > 60:
                    old_sym = next(iter(self._series))[0]
                    for k in [k for k in self._series if k[0] == old_sym]:
                        self._series.pop(k, None)
                    for k in [k for k in self._trades if k[0] == old_sym]:
                        self._trades.pop(k, None)

        exit_fn = lambda cs, j0, e, a: policy_exit(cs, j0, e, a, pol, fee, slip)

        def past(name: str) -> List[float]:
            key = (symbol, name, pkey, last_ts)
            with self._lock:
                tr = self._trades.get(key)
            if tr is None:
                spec = S.REGISTRY.get(name)
                if spec is None:
                    return []
                raw = backtest.simulate(candles, spec, cache=sc, exit_fn=exit_fn)
                tr = [(t["i"], t["i"] + t["bars"], t["r"]) for t in raw]
                with self._lock:
                    self._trades[key] = tr
                    self.backtests_run += 1
                    self.bars_walked += n
            # only trades that started inside the window and had already finished
            return [r for i, j, r in tr if i >= start and j < n - 1]

        ctrl = past("_control_random_entry")
        ctrl_mean = statistics.fmean(ctrl) if ctrl else None
        per = {}
        for name in names:
            rs = past(name)
            mean = statistics.fmean(rs) if rs else None
            ok = (len(rs) >= cfg["verify_min_trades"] and mean is not None and mean >= cfg["verify_min_edge"]
                  and (not cfg["verify_beat_control"] or ctrl_mean is None or mean > ctrl_mean))
            per[name] = {"n": len(rs), "exp": round(mean, 3) if mean is not None else None,
                         "win": round(100 * sum(1 for r in rs if r > 0) / len(rs), 1) if rs else None,
                         "ok": ok}
        passed = {k: v for k, v in per.items() if v["ok"]}
        lead = max(passed, key=lambda k: passed[k]["exp"]) if passed else None
        return {"ok": bool(passed), "lead": lead, "per": per, "hours": int(cfg["verify_bars"]),
                "control_exp": round(ctrl_mean, 3) if ctrl_mean is not None else None,
                "control_n": len(ctrl)}


# =============================================================================
# the ledger
# =============================================================================

def _init():
    c = store.conn()
    c.executescript(SCHEMA)
    c.commit()


def ensure_bots(practice_money: float = None) -> List[Dict]:
    """Create the six bots the first time, splitting the practice money evenly."""
    _init()
    c = store.conn()
    have = {r["key"] for r in c.execute("SELECT key FROM bots").fetchall()}
    missing = [d for d in BOT_DEFS if d["key"] not in have]
    if missing:
        money = practice_money if practice_money is not None else load_settings()["practice_money"]
        shares = _split(money, len(BOT_DEFS))
        for d in missing:
            each = shares[BOT_DEFS.index(d)]
            c.execute("INSERT INTO bots(key, name, enabled, starting_cash, cash, created_at, overrides) "
                      "VALUES(?,?,?,?,?,?,?)", (d["key"], d["name"], 1, each, each, store.now_iso(), "{}"))
        c.commit()
    return all_bots()


def _split(money: float, n: int) -> List[float]:
    """Split to the cent so the bots add back up to exactly what was entered."""
    cents = int(round(money * 100))
    base, extra = divmod(cents, n)
    return [(base + (1 if i < extra else 0)) / 100.0 for i in range(n)]


def all_bots() -> List[Dict]:
    _init()
    order = {d["key"]: i for i, d in enumerate(BOT_DEFS)}
    rows = [dict(r) for r in store.conn().execute("SELECT * FROM bots").fetchall()]
    return sorted(rows, key=lambda r: order.get(r["key"], 99))


def open_positions(bot_id: int = None) -> List[Dict]:
    _init()
    q = "SELECT * FROM bot_positions WHERE closed_at IS NULL"
    args: tuple = ()
    if bot_id is not None:
        q += " AND bot_id=?"
        args = (bot_id,)
    return [dict(r) for r in store.conn().execute(q + " ORDER BY id", args).fetchall()]


def closed_positions(bot_id: int = None, limit: int = 5000) -> List[Dict]:
    _init()
    q = "SELECT * FROM bot_positions WHERE closed_at IS NOT NULL"
    args: tuple = ()
    if bot_id is not None:
        q += " AND bot_id=?"
        args = (bot_id,)
    return [dict(r) for r in store.conn().execute(q + " ORDER BY closed_at, id LIMIT ?", args + (limit,)).fetchall()]


def log(kind: str, message: str, bot: str = None, symbol: str = None, data: Dict = None) -> None:
    _init()
    c = store.conn()
    c.execute("INSERT INTO bot_log(ts, bot, kind, symbol, message, data) VALUES(?,?,?,?,?,?)",
              (store.now_iso(), bot, kind, symbol, message, json.dumps(data, default=str) if data else None))
    c.execute("DELETE FROM bot_log WHERE id < (SELECT COALESCE(MAX(id),0) - 5000 FROM bot_log)")
    c.commit()


def feed(limit: int = 120, kinds: List[str] = None) -> List[Dict]:
    _init()
    q = "SELECT * FROM bot_log"
    args: list = []
    if kinds:
        q += f" WHERE kind IN ({','.join('?' * len(kinds))})"
        args += kinds
    q += " ORDER BY id DESC LIMIT ?"
    args.append(limit)
    return [dict(r) for r in store.conn().execute(q, args).fetchall()]


def _equity(bot: Dict, opens: List[Dict]) -> float:
    return bot["cash"] + sum(p["units_open"] * (p["last_price"] or p["entry"]) for p in opens)


def performance(rows: List[Dict], starting: float) -> Dict:
    """Closed-trade statistics in the same shape the readiness gate reads."""
    rs = [r["r_multiple"] for r in rows if r["r_multiple"] is not None]
    pnls = [r["pnl"] or 0.0 for r in rows]
    n = len(rs)
    wins = [r for r in rs if r > 0]
    losses = [r for r in rs if r <= 0]
    gw, gl = sum(wins), -sum(losses)
    curve, run, peak, dd = [], starting, starting, 0.0
    for r in rows:
        run += r["pnl"] or 0.0
        curve.append({"t": r["closed_at"], "equity": round(run, 2)})
        peak = max(peak, run)
        dd = max(dd, (peak - run) / peak * 100 if peak else 0.0)
    return {
        "closed_count": n,
        "win_rate": round(100 * len(wins) / n, 1) if n else None,
        "expectancy_r": round(sum(rs) / n, 4) if n else None,
        "total_r": round(sum(rs), 2),
        "avg_win_r": round(gw / len(wins), 3) if wins else None,
        "avg_loss_r": round(-gl / len(losses), 3) if losses else None,
        "profit_factor": round(gw / gl, 2) if gl > 0 else None,
        "total_pnl": round(sum(pnls), 2),
        "total_fees": round(sum(r["fees"] or 0 for r in rows), 2),
        "max_drawdown_pct": round(dd, 2),
        "equity_curve": curve[-300:],
    }


# =============================================================================
# learning from the bots' own trades
# =============================================================================

def learning() -> Dict:
    """What the bots have learned from every trade they have closed.

    Every average is shrunk toward zero by LEARN_PRIOR_N imaginary break-even trades,
    so three lucky losses cannot bench a good strategy and three lucky wins cannot
    crown a bad one. Learning only ever makes the bots more careful.
    """
    rows = closed_positions()
    bots = {b["id"]: b for b in all_bots()}

    def table(keyfn) -> Dict[str, Dict]:
        groups: Dict[str, List[float]] = {}
        for r in rows:
            k = keyfn(r)
            if k and r["r_multiple"] is not None:
                groups.setdefault(k, []).append(r["r_multiple"])
        out = {}
        for k, rs in groups.items():
            out[k] = {"n": len(rs), "mean": round(statistics.fmean(rs), 3),
                      "shrunk": round(sum(rs) / (len(rs) + LEARN_PRIOR_N), 3),
                      "win": round(100 * sum(1 for x in rs if x > 0) / len(rs), 1)}
        return out

    by_strategy = table(lambda r: r["lead_strategy"])
    by_coin = table(lambda r: r["base"])
    by_state = table(lambda r: r["gate_label"])
    by_bot = table(lambda r: bots.get(r["bot_id"], {}).get("name"))

    benched = sorted(k for k, v in by_strategy.items() if v["n"] >= 10 and v["shrunk"] < -0.15)
    avoid_coins = sorted(k for k, v in by_coin.items() if v["n"] >= 6 and v["shrunk"] < -0.20)
    avoid_states = sorted(k for k, v in by_state.items() if v["n"] >= 15 and v["shrunk"] < -0.15)

    risk_mult: Dict[int, float] = {}
    for bid in bots:
        recent = [r["r_multiple"] for r in rows if r["bot_id"] == bid and r["r_multiple"] is not None][-20:]
        if len(recent) >= 8:
            m = statistics.fmean(recent)
            risk_mult[bid] = 0.25 if m < -0.25 else 0.5 if m < 0 else 1.0
        else:
            risk_mult[bid] = 1.0
    return {"trades": len(rows), "by_strategy": by_strategy, "by_coin": by_coin, "by_state": by_state,
            "by_bot": by_bot, "benched": benched, "avoid_coins": avoid_coins, "avoid_states": avoid_states,
            "risk_mult": risk_mult}


# =============================================================================
# the engine
# =============================================================================

def _now() -> datetime:
    return datetime.now(timezone.utc)


def _age_h(iso: str) -> float:
    return (_now() - store.parse_iso(iso)).total_seconds() / 3600.0


def _day_start_iso() -> str:
    return _now().strftime("%Y-%m-%dT00:00:00Z")


def _fmt(px: float) -> str:
    if px is None:
        return "?"
    a = abs(px)
    return f"{px:,.0f}" if a >= 1000 else f"{px:.2f}" if a >= 1 else f"{px:.4f}" if a >= 0.01 else f"{px:.3g}"


class Engine:
    """Two threads: one scans and opens trades on an interval, one manages open trades
    every few seconds. The manager runs even while the bots are stopped, because a
    stopped bot must still honour the stops on what it already holds."""

    def __init__(self, scan_fn: Callable[[], Dict], broker: B.PaperBroker = None):
        self.scan_fn = scan_fn
        self.broker = broker or B.PaperBroker()
        self.verifier = Verifier()
        self._lock = threading.RLock()
        self._wake = threading.Event()
        self._halt = threading.Event()
        self._threads: List[threading.Thread] = []
        self.cycle_busy = False
        self.cycles = 0
        self.last_cycle_at: Optional[str] = None
        self.next_cycle_at: float = 0.0
        self.last_error: Optional[str] = None
        self.last_summary: Dict = {}
        self.bot_status: Dict[str, str] = {}
        self._benched_seen: set = set()
        self._research_thread: Optional[threading.Thread] = None
        self.started_at = store.now_iso()

    # -- lifecycle -----------------------------------------------------------
    def boot(self):
        ensure_bots()
        self._benched_seen = set(learning()["benched"])
        # keep counting scans across restarts rather than starting again at 1
        self.cycles = store.conn().execute("SELECT COUNT(*) FROM bot_log WHERE kind='cycle'").fetchone()[0]
        if not any(t.is_alive() for t in self._threads):
            self._threads = [threading.Thread(target=self._cycle_loop, name="bots-cycle", daemon=True),
                             threading.Thread(target=self._manage_loop, name="bots-manage", daemon=True)]
            for t in self._threads:
                t.start()
        if load_settings()["running"]:
            log("system", "Bots resumed automatically: they were running when the app last closed.")
            self._wake.set()

    def run(self) -> Dict:
        was = load_settings()["running"]
        save_settings({"running": True})
        if not was:
            n = sum(1 for b in all_bots() if b["enabled"])
            log("system", f"Bots started. {n} bots are now scanning every market and will trade on "
                          f"their own. Practice money only.")
        self.next_cycle_at = 0
        self._wake.set()
        return self.status()

    def stop(self) -> Dict:
        save_settings({"running": False})
        log("system", "Bots stopped. No new trades will be opened. Open positions are still managed "
                      "to their stops and targets; use Close all to exit them now.")
        return self.status()

    def shutdown(self):
        self._halt.set()
        self._wake.set()

    # -- loops ---------------------------------------------------------------
    def _cycle_loop(self):
        while not self._halt.is_set():
            st = load_settings()
            if st["running"] and time.time() >= self.next_cycle_at:
                self.next_cycle_at = time.time() + st["scan_interval_s"]
                try:
                    self.cycle()
                    self.last_error = None
                except Exception:                            # noqa: BLE001 - a bad cycle must not end the loop
                    self.last_error = traceback.format_exc(limit=3).strip().splitlines()[-1]
                    log("error", f"Cycle failed: {self.last_error}. Trying again next cycle.")
            self._wake.wait(timeout=2.0)
            self._wake.clear()

    def _manage_loop(self):
        while not self._halt.is_set():
            try:
                if open_positions():
                    self.manage()
            except Exception:                                # noqa: BLE001
                self.last_error = traceback.format_exc(limit=3).strip().splitlines()[-1]
            self._halt.wait(timeout=load_settings()["manage_interval_s"])

    # -- one scan-and-decide pass --------------------------------------------
    def cycle(self, scan: Dict = None) -> Dict:
        t0 = time.time()
        self.cycle_busy = True
        try:
            st = load_settings()
            scan = scan or self.scan_fn()
            markets = [m for m in scan.get("markets", []) if not m.get("error")]

            try:
                automation.check(scan, {m["symbol"]: m.get("swarm") for m in markets if m.get("swarm")})
            except Exception:                                # noqa: BLE001
                pass
            try:
                learn.resolve_due(40)
            except Exception:                                # noqa: BLE001
                pass
            learned = learning()
            self._announce_learning(learned)
            summary = self._decide(markets, st, learned)
            self._maybe_research(st)            # after deciding, so it never delays a trade

            sw = scan.get("swarm") or {}
            summary.update({
                "markets_discovered": (scan.get("universe") or {}).get("discovered"),
                "markets_analysed": len(markets),
                "strategy_checks": sw.get("total_evaluations"),
                "elapsed_s": round(time.time() - t0, 1),
                "at": store.now_iso(),
            })
            self.cycles += 1
            self.last_cycle_at = summary["at"]
            self.last_summary = summary
            opened = summary["opened"]
            reasons = ", ".join(f"{k} ({v})" for k, v in summary["top_reasons"][:4]) or "none"
            log("cycle",
                f"Scan {self.cycles}: {summary['markets_discovered'] or '?'} markets found, "
                f"{len(markets)} analysed, {summary['strategy_checks'] or 0:,} strategy checks, "
                f"{summary['setups']} setups matched a playbook, {summary['backtests']} backtests run, "
                f"{len(opened)} trade{'s' if len(opened) != 1 else ''} opened"
                + (f" ({', '.join(opened)})" if opened else "") + f". Most common reasons to pass: {reasons}.",
                data={k: v for k, v in summary.items() if k != "per_bot"})
            return summary
        finally:
            self.cycle_busy = False

    def _bot_blocker(self, bot: Dict, cfg: Dict, learned: Dict) -> Optional[str]:
        """Reasons a bot may not open anything this cycle, before it looks at a single chart."""
        if not bot["enabled"]:
            return "switched off"
        opens = open_positions(bot["id"])
        if len(opens) >= cfg["max_positions"]:
            return f"holding its maximum of {cfg['max_positions']} positions"
        c = store.conn()
        today = _day_start_iso()
        n_today = c.execute("SELECT COUNT(*) FROM bot_positions WHERE bot_id=? AND opened_at>=?",
                            (bot["id"], today)).fetchone()[0]
        if n_today >= cfg["max_trades_per_day"]:
            return f"reached its {cfg['max_trades_per_day']} trades for today"
        # today's result: closed trades + what is open right now
        closed_today = c.execute("SELECT COALESCE(SUM(pnl),0) FROM bot_positions WHERE bot_id=? AND closed_at>=?",
                                 (bot["id"], today)).fetchone()[0]
        unreal = sum(p["units_open"] * ((p["last_price"] or p["entry"]) - p["entry"]) for p in opens)
        eq = _equity(bot, opens)
        if closed_today + unreal <= -cfg["daily_loss_limit_pct"] / 100.0 * eq:
            return (f"hit its daily loss limit ({cfg['daily_loss_limit_pct']:.1f}%); "
                    f"it starts again at 00:00 UTC")
        recent = [r for r in closed_positions(bot["id"])][-cfg["loss_streak"]:]
        if (len(recent) == cfg["loss_streak"] and all((r["r_multiple"] or 0) < 0 for r in recent)
                and _age_h(recent[-1]["closed_at"]) < cfg["loss_streak_pause_h"]):
            until = store.parse_iso(recent[-1]["closed_at"]) + timedelta(hours=cfg["loss_streak_pause_h"])
            return f"lost {cfg['loss_streak']} in a row, cooling off until {until.strftime('%H:%M')} UTC"
        if bot["cash"] < 10:
            return "out of cash"
        return None

    def _screen(self, bot: Dict, cfg: Dict, m: Dict, learned: Dict) -> Tuple[Optional[str], List[Dict]]:
        """Does this market match this bot's playbook? Returns (reason_not, its_signals)."""
        gate, stc, sw = m.get("gate") or {}, m.get("structure") or {}, m.get("swarm") or {}
        if not stc.get("atr") or not stc.get("price"):
            return "no data", []
        if (m.get("usd_volume_24h") or 0) < cfg["min_volume_usd"]:
            return "too little volume", []
        if gate.get("label") not in cfg["gates"]:
            return f"{(gate.get('label') or 'no').lower()} market", []
        if gate.get("label") in learned["avoid_states"]:
            return f"learned: {gate.get('label')} setups lose", []
        if cfg["avoid_htf_downtrend"] and ((m.get("htf") or {}).get("trend") == "downtrend"):
            return "bigger trend is down", []
        if (m.get("base") or "") in learned["avoid_coins"]:
            return "learned: this coin loses", []
        stop_pct = cfg["stop_atr"] * stc["atr"] / stc["price"]
        slip = B.slippage_for(m.get("usd_volume_24h"))
        cost_r = 2 * (self.broker.fee_bps + slip) / 10000.0 / stop_pct if stop_pct else 99
        if cost_r > cfg["max_cost_r"]:
            return "fees too high for the stop", []
        fams = cfg["families"]
        mine = [f for f in (sw.get("fired_all") or [])
                if f["f"] != "control" and (fams == ALL or f["f"] in fams)
                and f.get("w") != 0 and f["s"] not in learned["benched"]]
        if len(mine) < cfg["min_signals"]:
            return "not enough of its signals", []
        if cfg.get("min_families") and (sw.get("families_agreeing") or 0) < cfg["min_families"]:
            return "too few families agree", []
        if cfg.get("min_consensus") and (sw.get("consensus") or 0) < cfg["min_consensus"]:
            return "consensus too weak", []
        mine.sort(key=lambda f: -f["st"] * (f["w"] if f.get("w") is not None else 1.0))
        return None, mine[:8]

    def _decide(self, markets: List[Dict], st: Dict, learned: Dict) -> Dict:
        bots = all_bots()
        reasons: Counter = Counter()
        per_bot: Dict[str, Dict] = {}
        setups: List[Tuple[Dict, Dict, Dict, List[Dict]]] = []

        for bot in bots:
            cfg = bot_config(bot, st)
            block = self._bot_blocker(bot, cfg, learned)
            per_bot[bot["key"]] = {"blocked": block, "matched": 0, "verified": 0, "best_miss": None}
            if block:
                self.bot_status[bot["key"]] = block[0].upper() + block[1:] + "."
                continue
            held = {p["base"] for p in open_positions(bot["id"])}
            for m in markets:
                if m.get("base") in held:
                    reasons["already holding it"] += 1
                    continue
                why, mine = self._screen(bot, cfg, m, learned)
                if why:
                    reasons[why] += 1
                    continue
                if self._cooling(bot["id"], m.get("base"), cfg["cooldown_h"]):
                    reasons["cooling down after a recent trade"] += 1
                    continue
                setups.append((bot, cfg, m, mine))
                per_bot[bot["key"]]["matched"] += 1

        # Verify each coin once for the union of strategies any bot wants to know about.
        fee = self.broker.fee_bps / 10000.0
        backtests_before = self.verifier.backtests_run
        verdicts: Dict[tuple, Dict] = {}
        wanted: Dict[tuple, set] = {}
        for bot, cfg, m, mine in setups:
            if not cfg["verify"]:
                continue
            key = (m["symbol"], json.dumps(policy_of(cfg), sort_keys=True),
                   json.dumps({k: cfg[k] for k in ("verify_bars", "verify_min_trades", "verify_min_edge",
                                                   "verify_beat_control")}, sort_keys=True))
            wanted.setdefault(key, set()).update(f["s"] for f in mine)
        # cheapest-first: coins wanted by the most bots
        for key, names in sorted(wanted.items(), key=lambda kv: -len(kv[1]))[:24]:
            sym = key[0]
            m = next(x for (_, _, x, _) in setups if x["symbol"] == sym)
            cfg = next(c for (_, c, x, _) in setups if x["symbol"] == sym)
            slip = B.slippage_for(m.get("usd_volume_24h")) / 10000.0
            try:
                verdicts[key] = self.verifier.check(sym, m.get("venue", "okx"), sorted(names),
                                                    json.loads(key[1]), {**cfg, **json.loads(key[2])}, fee, slip)
            except Exception as exc:                          # noqa: BLE001
                verdicts[key] = {"ok": False, "reason": f"backtest failed: {exc}", "per": {}}

        candidates: Dict[str, List[Dict]] = {}
        for bot, cfg, m, mine in setups:
            names = [f["s"] for f in mine]
            if cfg["verify"]:
                key = (m["symbol"], json.dumps(policy_of(cfg), sort_keys=True),
                       json.dumps({k: cfg[k] for k in ("verify_bars", "verify_min_trades", "verify_min_edge",
                                                       "verify_beat_control")}, sort_keys=True))
                v = verdicts.get(key)
                if v is None:
                    reasons["not verified this cycle"] += 1
                    continue
                per = {k: v["per"][k] for k in names if k in v.get("per", {})}
                passed = {k: x for k, x in per.items() if x["ok"]}
                if not passed:
                    reasons["failed its backtest"] += 1
                    best = max(per.items(), key=lambda kv: (kv[1]["exp"] if kv[1]["exp"] is not None else -9),
                               default=None)
                    miss = per_bot[bot["key"]]["best_miss"]
                    if best and best[1]["exp"] is not None and (miss is None or best[1]["exp"] > miss["exp"]):
                        b1, ce = best[1], v.get("control_exp")
                        if b1["n"] < cfg["verify_min_trades"]:
                            why = f"only {b1['n']} past trades, needs {cfg['verify_min_trades']}"
                        elif b1["exp"] < cfg["verify_min_edge"]:
                            why = f"under the +{cfg['verify_min_edge']:.2f}R bar"
                        elif ce is not None and b1["exp"] <= ce:
                            why = f"random buying did better there ({ce:+.2f}R)"
                        else:
                            why = "did not pass"
                        per_bot[bot["key"]]["best_miss"] = {"symbol": m["base"], "strategy": best[0],
                                                            "exp": b1["exp"], "n": b1["n"], "why": why}
                    continue
                lead = max(passed, key=lambda k: passed[k]["exp"])
                edge = passed[lead]["exp"]
                ver = {"lead": lead, "edge": edge, "n": passed[lead]["n"], "win": passed[lead]["win"],
                       "passed": sorted(passed), "control_exp": v.get("control_exp"), "hours": v.get("hours")}
            else:
                lead, edge, ver = names[0], 0.0, {"lead": names[0], "edge": None, "skipped": True}
            per_bot[bot["key"]]["verified"] += 1
            strength = sum(f["st"] * (f["w"] if f.get("w") is not None else 1.0) for f in mine[:4])
            heat = (m.get("gate") or {}).get("blow_score") or 0.0
            score = (0.5 + max(0.0, edge or 0.0)) * (0.5 + heat) * (1 + 0.1 * strength)
            candidates.setdefault(bot["key"], []).append(
                {"bot": bot, "cfg": cfg, "m": m, "mine": mine, "lead": lead, "ver": ver, "score": round(score, 4)})

        # Open the best candidates, respecting slots and how many bots may share a coin.
        opened: List[str] = []
        coin_count = Counter(p["base"] for p in open_positions())
        for bot in bots:
            cands = sorted(candidates.get(bot["key"], []), key=lambda c: -c["score"])
            cfg = bot_config(bot, st)
            slots = cfg["max_positions"] - len(open_positions(bot["id"]))
            took = 0
            for c in cands:
                if took >= slots:
                    break
                base = c["m"].get("base")
                if coin_count[base] >= st["max_bots_per_coin"]:
                    reasons["other bots already hold it"] += 1
                    continue
                res = self._open(c, learned)
                if res.get("ok"):
                    took += 1
                    coin_count[base] += 1
                    opened.append(f"{bot['name']}: {base}")
                else:
                    reasons[res.get("reason", "order failed")] += 1
            pb = per_bot[bot["key"]]
            if pb["blocked"]:
                continue
            if took:
                self.bot_status[bot["key"]] = f"Opened {took} trade{'s' if took > 1 else ''} this scan."
            elif pb["verified"]:
                self.bot_status[bot["key"]] = "Found a verified setup but had no room for it."
            elif pb["matched"]:
                bm = pb["best_miss"]
                self.bot_status[bot["key"]] = (
                    f"{pb['matched']} setup{'s' if pb['matched'] != 1 else ''} matched its playbook; none passed "
                    f"the backtest" + (f" (closest: {bm['symbol']} with {bm['strategy']} at {bm['exp']:+.2f}R over "
                                       f"{bm['n']} trades, but {bm['why']})" if bm else "") + ". Waiting.")
            else:
                self.bot_status[bot["key"]] = "No market matches its playbook right now. Waiting."

        return {"setups": len(setups), "backtests": self.verifier.backtests_run - backtests_before,
                "verified": sum(len(v) for v in candidates.values()), "opened": opened,
                "top_reasons": reasons.most_common(8), "per_bot": per_bot}

    def _cooling(self, bot_id: int, base: str, hours: float) -> bool:
        if not hours:
            return False
        since = (_now() - timedelta(hours=hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
        row = store.conn().execute(
            "SELECT 1 FROM bot_positions WHERE bot_id=? AND base=? AND (closed_at IS NULL OR closed_at>=?) LIMIT 1",
            (bot_id, base, since)).fetchone()
        return row is not None

    # -- orders ----------------------------------------------------------------
    def _open(self, c: Dict, learned: Dict) -> Dict:
        bot, cfg, m, ver = c["bot"], c["cfg"], c["m"], c["ver"]
        stc = m["structure"]
        px = self.broker.price(m["symbol"], m.get("venue", "okx")) or m.get("price")
        if not px:
            return {"ok": False, "reason": "no live price"}
        atr = stc["atr"] * (px / stc["price"]) if stc.get("price") else stc["atr"]
        with self._lock:
            bot = next(b for b in all_bots() if b["id"] == bot["id"])        # fresh cash
            opens = open_positions(bot["id"])
            eq = _equity(bot, opens)
            mult = learned["risk_mult"].get(bot["id"], 1.0)
            stop = px - cfg["stop_atr"] * atr
            if stop <= 0:
                return {"ok": False, "reason": "stop below zero"}
            risk_amt = eq * cfg["risk_pct"] / 100.0 * mult
            units = risk_amt / (px - stop)
            notional = min(units * px, eq * cfg["max_position_pct"] / 100.0, bot["cash"] * 0.98)
            if notional < 10:
                return {"ok": False, "reason": "not enough cash"}
            units = notional / px
            slip_bps = B.slippage_for(m.get("usd_volume_24h"))
            fill = self.broker.buy(units, px, slip_bps)
            entry = fill["avg_price"]
            stop = entry - cfg["stop_atr"] * atr
            target = entry + cfg["target_r"] * (entry - stop)
            risk_amount = units * (entry - stop)
            why = (f"{len(c['mine'])} of its strategies fired, led by {c['lead']}. "
                   + (f"Backtest on this coin's last {ver.get('hours')}h: {c['lead']} made {ver['edge']:+.2f}R per "
                      f"trade over {ver['n']} trades ({ver['win']:.0f}% winners)"
                      + (f" vs random buying at {ver['control_exp']:+.2f}R" if ver.get("control_exp") is not None
                         else "") + ". " if ver.get("edge") is not None else "Backtest check is switched off. ")
                   + f"Market is {(m.get('gate') or {}).get('label', '?')}."
                   + (f" Risk cut to {mult:.0%} after recent losses." if mult < 1 else ""))
            con = store.conn()
            cur = con.execute(
                "INSERT INTO bot_positions(bot_id, symbol, venue, base, opened_at, entry, units_initial, units_open, "
                "stop, initial_stop, target, atr, risk_amount, fees, highest, policy, lead_strategy, strategies, "
                "gate_label, score, why, verification, last_price) VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
                (bot["id"], m["symbol"], m.get("venue", "okx"), m.get("base"), store.now_iso(), entry, units, units,
                 stop, stop, target, atr, risk_amount, fill["fee"], entry,
                 json.dumps({**policy_of(cfg), "slip_bps": slip_bps}),
                 c["lead"], json.dumps([f["s"] for f in c["mine"]]), (m.get("gate") or {}).get("label"),
                 c["score"], why, json.dumps(ver), px))
            pid = cur.lastrowid
            con.execute("INSERT INTO bot_fills(position_id, bot_id, ts, side, units, price, fee, reason) "
                        "VALUES(?,?,?,?,?,?,?,?)", (pid, bot["id"], store.now_iso(), "buy", units, entry,
                                                     fill["fee"], "entry"))
            con.execute("UPDATE bots SET cash=cash-? WHERE id=?", (fill["cost"] + fill["fee"], bot["id"]))
            con.commit()
        log("enter",
            f"{bot['name']} bought {m.get('base')} at {_fmt(entry)} (${notional:,.0f}). Stop {_fmt(stop)}, "
            f"target {_fmt(target)}, risking ${risk_amount:,.2f}. {why}",
            bot=bot["name"], symbol=m["symbol"],
            data={"position_id": pid, "entry": entry, "stop": stop, "target": target, "units": units})
        return {"ok": True, "position_id": pid}

    def _sell(self, p: Dict, units: float, fill: Dict, reason: str) -> Dict:
        """Record a sale. Closes the position when nothing is left."""
        con = store.conn()
        units = min(units, p["units_open"])
        con.execute("INSERT INTO bot_fills(position_id, bot_id, ts, side, units, price, fee, reason) "
                    "VALUES(?,?,?,?,?,?,?,?)", (p["id"], p["bot_id"], store.now_iso(), "sell", units,
                                                 fill["avg_price"], fill["fee"], reason))
        con.execute("UPDATE bots SET cash=cash+? WHERE id=?",
                    (units * fill["avg_price"] - fill["fee"], p["bot_id"]))
        left = p["units_open"] - units
        if left <= p["units_initial"] * 1e-9:
            fills = con.execute("SELECT side, units, price, fee FROM bot_fills WHERE position_id=?",
                                (p["id"],)).fetchall()
            bought = sum(f["units"] * f["price"] for f in fills if f["side"] == "buy")
            sold = sum(f["units"] * f["price"] for f in fills if f["side"] == "sell")
            fees = sum(f["fee"] for f in fills)
            pnl = sold - bought - fees
            r = pnl / p["risk_amount"] if p["risk_amount"] else 0.0
            con.execute("UPDATE bot_positions SET units_open=0, fees=?, closed_at=?, exit_reason=?, pnl=?, "
                        "r_multiple=?, last_price=? WHERE id=?",
                        (fees, store.now_iso(), reason, round(pnl, 4), round(r, 4), fill["avg_price"], p["id"]))
            con.commit()
            return {"closed": True, "pnl": pnl, "r": r, "fees": fees}
        con.execute("UPDATE bot_positions SET units_open=?, fees=fees+? WHERE id=?", (left, fill["fee"], p["id"]))
        con.commit()
        return {"closed": False, "left": left}

    def _exit_log(self, p: Dict, res: Dict, reason: str, px: float):
        bot = next((b for b in all_bots() if b["id"] == p["bot_id"]), {"name": "?"})
        words = {"stop": "hit its stop", "protected stop": "hit its raised stop", "target": "reached its target",
                 "time": "ran out of time", "close all": "closed on request"}.get(reason, reason)
        held = _age_h(p["opened_at"])
        log("exit",
            f"{bot['name']} sold {p['base']} at {_fmt(px)}: {words}. {res['r']:+.2f}R, "
            f"{'+' if res['pnl'] >= 0 else '-'}${abs(res['pnl']):,.2f} after ${res['fees']:,.2f} fees. "
            f"Held {held:.0f}h.", bot=bot["name"], symbol=p["symbol"],
            data={"position_id": p["id"], "r": res["r"], "pnl": res["pnl"], "reason": reason})

    def manage(self, prices: Dict[str, float] = None) -> Dict:
        """Check every open position against the live price and act on it."""
        rows = open_positions()
        if not rows:
            return {"checked": 0}
        if prices is None:
            prices = {}
            for sym, venue in {(p["symbol"], p["venue"]) for p in rows}:
                prices[sym] = self.broker.price(sym, venue or "okx")
        fee_rate = self.broker.fee_bps / 10000.0
        closed = 0
        with self._lock:
            for p in open_positions():
                try:
                    closed += self._manage_one(p, prices.get(p["symbol"]), fee_rate)
                except Exception:                            # noqa: BLE001 - one bad row must not stall the rest
                    self.last_error = traceback.format_exc(limit=2).strip().splitlines()[-1]
            store.conn().commit()
        return {"checked": len(rows), "closed": closed}

    def _manage_one(self, p: Dict, px: Optional[float], fee_rate: float) -> int:
        """Stop, partial, target, time limit and trailing for one position. Returns 1 if it closed."""
        pol = json.loads(p["policy"] or "{}") or policy_of(SHARED_DEFAULTS)
        if not px:
            # No live price. If that lasts well past the time limit, close at the
            # last known price rather than hold a practice trade forever.
            if _age_h(p["opened_at"]) >= pol.get("max_hold_h", 96) + 6 and (p["last_price"] or p["entry"]):
                last = p["last_price"] or p["entry"]
                fill = self.broker.sell(p["units_open"], last, pol.get("slip_bps"))
                res = self._sell(p, p["units_open"], fill, "time")
                self._exit_log(p, res, "time", fill["avg_price"])
                return 1
            return 0
        risk_u = p["entry"] - p["initial_stop"]
        sb = pol.get("slip_bps")

        hit = self.broker.check_stop(p["stop"], p["units_open"], px, sb)
        if hit:
            reason = "stop" if p["stop"] <= p["initial_stop"] + 1e-12 else "protected stop"
            res = self._sell(p, p["units_open"], hit, reason)
            self._exit_log(p, res, reason, hit["avg_price"])
            return 1

        highest = max(p["highest"] or p["entry"], px)
        stop = p["stop"]
        if pol.get("partial_r") and not p["partial_done"] and px >= p["entry"] + pol["partial_r"] * risk_u:
            units = p["units_open"] * pol.get("partial_frac", 0.5)
            fill = self.broker.sell(units, px, sb)
            self._sell(p, units, fill, "partial")
            stop = max(stop, p["entry"] * (1 + 2 * (fee_rate + (sb if sb is not None else 0) / 10000.0)))
            store.conn().execute("UPDATE bot_positions SET partial_done=1, stop=? WHERE id=?", (stop, p["id"]))
            store.conn().commit()
            bot = next((b for b in all_bots() if b["id"] == p["bot_id"]), {"name": "?"})
            log("manage", f"{bot['name']} took {pol.get('partial_frac', 0.5):.0%} profit on {p['base']} at "
                          f"{_fmt(px)} and moved the stop to breakeven.", bot=bot["name"], symbol=p["symbol"])
            p = dict(store.conn().execute("SELECT * FROM bot_positions WHERE id=?", (p["id"],)).fetchone())

        if p["target"] and px >= p["target"]:
            fill = self.broker.sell(p["units_open"], p["target"], sb)
            res = self._sell(p, p["units_open"], fill, "target")
            self._exit_log(p, res, "target", fill["avg_price"])
            return 1
        if _age_h(p["opened_at"]) >= pol.get("max_hold_h", 96):
            fill = self.broker.sell(p["units_open"], px, sb)
            res = self._sell(p, p["units_open"], fill, "time")
            self._exit_log(p, res, "time", fill["avg_price"])
            return 1
        if pol.get("trail_atr") and p["partial_done"] and p["atr"]:
            stop = max(stop, highest - pol["trail_atr"] * p["atr"])
        store.conn().execute("UPDATE bot_positions SET last_price=?, highest=?, stop=? WHERE id=?",
                             (px, highest, stop, p["id"]))
        return 0

    def close_all(self, reason: str = "close all") -> Dict:
        n = 0
        with self._lock:
            for p in open_positions():
                px = self.broker.price(p["symbol"], p["venue"] or "okx") or p["last_price"] or p["entry"]
                fill = self.broker.sell(p["units_open"], px, json.loads(p["policy"] or "{}").get("slip_bps"))
                res = self._sell(p, p["units_open"], fill, reason)
                self._exit_log(p, res, reason, fill["avg_price"])
                n += 1
        return {"closed": n}

    def reset(self, practice_money: float = None) -> Dict:
        """Wipe the practice record and start again with fresh money."""
        with self._lock:
            money = float(practice_money or load_settings()["practice_money"])
            save_settings({"practice_money": money})
            con = store.conn()
            con.execute("DELETE FROM bot_fills")
            con.execute("DELETE FROM bot_positions")
            con.execute("DELETE FROM bot_log")
            shares = _split(money, len(BOT_DEFS))
            for d, each in zip(BOT_DEFS, shares):
                con.execute("UPDATE bots SET starting_cash=?, cash=? WHERE key=?", (each, each, d["key"]))
            each = shares[0]
            con.commit()
        self._benched_seen = set()
        log("system", f"Practice account reset to ${money:,.0f} (${each:,.0f} per bot).")
        return self.status()

    def set_bot(self, key: str, enabled: bool = None, overrides: Dict = None) -> Dict:
        con = store.conn()
        row = con.execute("SELECT * FROM bots WHERE key=?", (key,)).fetchone()
        if not row:
            return {"error": "no such bot"}
        if enabled is not None:
            con.execute("UPDATE bots SET enabled=? WHERE key=?", (1 if enabled else 0, key))
        if overrides is not None:
            clean = {k: _clamp(k, v) for k, v in overrides.items()
                     if k in SHARED_DEFAULTS or k in ("min_signals", "min_families", "min_consensus")}
            con.execute("UPDATE bots SET overrides=? WHERE key=?", (json.dumps(clean), key))
        con.commit()
        return {"ok": True}

    # -- self-maintenance --------------------------------------------------------
    def _announce_learning(self, learned: Dict):
        new = set(learned["benched"]) - self._benched_seen
        for s in sorted(new):
            v = learned["by_strategy"][s]
            log("learn", f"Learned: {s} has lost {v['mean']:+.2f}R per trade over {v['n']} bot trades, so every "
                         f"bot stops using it until it is re-measured.", data=v)
        back = self._benched_seen - set(learned["benched"])
        for s in sorted(back):
            log("learn", f"Learned: {s} has recovered and is back in use.")
        self._benched_seen = set(learned["benched"])

    def _maybe_research(self, st: Dict):
        hours = st.get("auto_research_h") or 0
        if not hours or (self._research_thread and self._research_thread.is_alive()):
            return
        last = research.latest_run()
        if last and last.get("finished_at") and _age_h(last["finished_at"]) < hours:
            return

        def go():
            log("research", "Re-measuring every strategy on every major market (deep backtest). "
                            "This runs in the background and takes a few minutes.")
            try:
                r = research.run(market_count=12, bars=3000)
                log("research", f"Research finished: {r.get('beating_control', '?')} of {r.get('judged', '?')} "
                                f"strategies beat random buying. Strategy weights updated for every bot.")
            except Exception as exc:                          # noqa: BLE001
                log("error", f"Research run failed: {exc}")
        self._research_thread = threading.Thread(target=go, name="bots-research", daemon=True)
        self._research_thread.start()

    # -- reporting ---------------------------------------------------------------
    def status(self) -> Dict:
        st = load_settings()
        bots = all_bots()
        learned = learning()
        opens = open_positions()
        closed = closed_positions()
        cards, total_eq, total_start = [], 0.0, 0.0
        for b in bots:
            bo = [p for p in opens if p["bot_id"] == b["id"]]
            bc = [p for p in closed if p["bot_id"] == b["id"]]
            eq = _equity(b, bo)
            total_eq += eq
            total_start += b["starting_cash"]
            perf = performance(bc, b["starting_cash"])
            d = BOT_BY_KEY.get(b["key"], {})
            cfg = bot_config(b, st)
            cards.append({
                "key": b["key"], "name": b["name"], "enabled": bool(b["enabled"]),
                "playbook": d.get("playbook", ""), "rule": COMMON_RULE,
                "families": cfg["families"], "min_signals": cfg["min_signals"],
                "starting_cash": b["starting_cash"], "cash": round(b["cash"], 2), "equity": round(eq, 2),
                "return_pct": round((eq / b["starting_cash"] - 1) * 100, 2) if b["starting_cash"] else 0.0,
                "open": len(bo), "risk_mult": learned["risk_mult"].get(b["id"], 1.0),
                "status": self.bot_status.get(b["key"]) or ("Waiting for the first scan." if st["running"]
                                                            else "Stopped."),
                "overrides": json.loads(b.get("overrides") or "{}"),
                **{k: perf[k] for k in ("closed_count", "win_rate", "expectancy_r", "profit_factor",
                                        "total_pnl", "total_fees", "max_drawdown_pct", "equity_curve")},
            })
        names = {b["id"]: b["name"] for b in bots}
        positions = []
        for p in opens:
            last = p["last_price"] or p["entry"]
            risk_u = p["entry"] - p["initial_stop"]
            positions.append({
                "id": p["id"], "bot": names.get(p["bot_id"]), "symbol": p["symbol"], "base": p["base"],
                "entry": p["entry"], "last": last, "stop": p["stop"], "target": p["target"],
                "units": p["units_open"], "value": round(p["units_open"] * last, 2),
                "pnl": round(p["units_open"] * (last - p["entry"]) - (p["fees"] or 0), 2),
                "r_now": round((last - p["entry"]) / risk_u, 2) if risk_u else None,
                "opened_at": p["opened_at"], "age_h": round(_age_h(p["opened_at"]), 1),
                "why": p["why"], "lead": p["lead_strategy"], "state": p["gate_label"],
            })
        overall = performance(closed, total_start)
        ready = []
        for name, test, why in portfolio.READINESS_RULES:
            try:
                ok = bool(test(overall))
            except Exception:                                 # noqa: BLE001
                ok = False
            ready.append({"check": name, "passed": ok, "why": why})
        recent = [{**r, "bot": names.get(r["bot_id"])} for r in closed[-40:]][::-1]
        return {
            "running": st["running"], "practice": True,
            "cycle_busy": self.cycle_busy, "cycles": self.cycles, "last_cycle_at": self.last_cycle_at,
            "next_cycle_in_s": max(0, int(self.next_cycle_at - time.time())) if st["running"] else None,
            "last_error": self.last_error, "last_summary": {k: v for k, v in self.last_summary.items()
                                                            if k != "per_bot"},
            "totals": {"starting": round(total_start, 2), "equity": round(total_eq, 2),
                       "pnl": round(total_eq - total_start, 2),
                       "return_pct": round((total_eq / total_start - 1) * 100, 2) if total_start else 0.0,
                       "open_positions": len(opens),
                       "total_fees": round(overall["total_fees"] + sum(p["fees"] or 0 for p in opens), 2),
                       **{k: overall[k] for k in ("closed_count", "win_rate", "expectancy_r", "profit_factor",
                                                  "max_drawdown_pct", "equity_curve")}},
            "bots": cards, "positions": positions, "recent": recent,
            "feed": feed(150),
            "learning": {
                **{k: learned[k] for k in ("trades", "benched", "avoid_coins", "avoid_states")},
                "by_strategy": sorted(({"name": k, **v} for k, v in learned["by_strategy"].items()),
                                      key=lambda x: -x["n"])[:30],
                "by_coin": sorted(({"name": k, **v} for k, v in learned["by_coin"].items()),
                                  key=lambda x: -x["n"])[:30]},
            "readiness": {"checks": ready, "passed": sum(c["passed"] for c in ready), "total": len(ready)},
            "verifier": {"backtests_run": self.verifier.backtests_run, "bars_walked": self.verifier.bars_walked},
            "settings": st, "defaults": SHARED_DEFAULTS, "limits": LIMITS,
            "research_running": bool(self._research_thread and self._research_thread.is_alive()),
        }


ENGINE: Optional[Engine] = None


def get_engine(scan_fn: Callable = None) -> Optional[Engine]:
    global ENGINE
    if ENGINE is None and scan_fn is not None:
        ENGINE = Engine(scan_fn)
    return ENGINE
