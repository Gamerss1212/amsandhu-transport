#!/usr/bin/env python3
"""Research runs: backtest the whole grid, persist it, and feed the weights back.

This is the loop that makes the swarm mean something. A research run measures every
strategy against every market on deep history, stores the result, and from then on
the live scan weights each strategy's vote by what that measurement showed — with the
control subtracted, so a strategy is only rewarded for beating an entry that had no
thought behind it.

Re-running it later is how the system keeps up: edges decay, regimes change, and a
weight derived from last quarter is a claim about last quarter.
"""

from __future__ import annotations

import json
import time
from typing import Dict, List, Optional

import config
from engine import backtest, marketdata as md, store, strategies as S, universe

SCHEMA = """
CREATE TABLE IF NOT EXISTS research_runs (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at TEXT NOT NULL,
    finished_at TEXT,
    markets INTEGER, strategies INTEGER, combinations INTEGER,
    trades_simulated INTEGER, bars_per_market INTEGER, split REAL,
    fee_bps REAL, stop_atr REAL, target_r REAL,
    beating_control INTEGER, judged INTEGER,
    elapsed_s REAL, notes TEXT
);
CREATE TABLE IF NOT EXISTS research_rows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id INTEGER NOT NULL,
    symbol TEXT NOT NULL, strategy TEXT NOT NULL, grp TEXT,
    trades INTEGER,
    is_n INTEGER, is_expectancy REAL, is_win_rate REAL,
    oos_n INTEGER, oos_expectancy REAL, oos_win_rate REAL,
    oos_profit_factor REAL, oos_max_dd REAL, oos_total_r REAL,
    control_expectancy REAL, excess_over_control REAL, weight REAL
);
CREATE INDEX IF NOT EXISTS idx_rr_run ON research_rows(run_id, symbol);
CREATE INDEX IF NOT EXISTS idx_rr_strategy ON research_rows(strategy);
"""


_INIT_DONE: set = set()


def _init():
    """Create this module's tables, once per database (not on every read: on a busy app
    those calls add up to seconds)."""
    if config.DB_PATH in _INIT_DONE:
        return
    c = store.conn()
    c.executescript(SCHEMA)
    cols = {r[1] for r in c.execute("PRAGMA table_info(research_runs)").fetchall()}
    if "asset" not in cols:                       # databases from before stocks existed
        c.execute("ALTER TABLE research_runs ADD COLUMN asset TEXT NOT NULL DEFAULT 'crypto'")
    c.commit()
    _INIT_DONE.add(config.DB_PATH)


def run(symbols: List[str] = None, bars: int = 3000, split: float = 0.6,
        market_count: int = 14, progress=None, asset: str = "crypto") -> Dict:
    """One full research pass over one asset class. Slow by design; this is the thorough one.

    Crypto and stocks are researched separately because they are different markets with
    different costs: a stock trade costs a fraction of a basis point in commission, a
    crypto taker trade tens of them, and a weight measured under one is wrong for the other.
    """
    _init()
    t0 = time.time()
    c = store.conn()
    fee_bps = config.STOCK_FEE_BPS if asset == "stock" else config.FEE_TIERS.get(config.DEFAULT_FEE_TIER, 26.0)
    cur = c.execute("INSERT INTO research_runs(started_at, split, fee_bps, stop_atr, target_r, asset) "
                    "VALUES(?,?,?,?,?,?)",
                    (store.now_iso(), split, fee_bps, config.STOP_ATR_MULT, config.TARGET_R, asset))
    c.commit()
    run_id = cur.lastrowid

    def say(msg):
        if progress:
            progress(msg)

    say("discovering markets")
    uni = universe.scan()
    assets = [m for m in universe.dedupe_by_base(uni["markets"])
              if (m.get("asset") == "stock") == (asset == "stock")]
    if symbols:
        picks = [m for m in assets if m["symbol"] in symbols or m["base"] in symbols]
    else:
        # majors first so the sample is not only whatever is hot this week, then the
        # most liquid of the rest for breadth
        majors = (("SPY", "QQQ", "AAPL", "MSFT", "NVDA", "AMZN", "META", "TSLA") if asset == "stock"
                  else ("BTC", "ETH", "SOL", "XRP", "DOGE", "ADA", "LINK", "AVAX"))
        picks = [m for m in assets if m["base"] in majors][:8]
        picks += [m for m in assets if m["base"] not in majors][:max(0, market_count - len(picks))]
    picks = picks[:market_count]

    say(f"fetching {bars} bars for {len(picks)} markets")
    deep = md.deep_many(picks, "1h", bars)
    good = [m for m in picks if len(deep.get(m["symbol"]) or []) >= min(1200, bars // 2)]
    say(f"{len(good)} markets have enough history")

    specs = S.all_strategies()
    say(f"backtesting {len(specs)} strategies x {len(good)} markets")
    g = backtest.run_grid(good, deep, specs=specs, split=split, fee_bps=fee_bps)

    say("storing results")
    for r in g["rows"]:
        ins, oos = r.get("in_sample") or {}, r.get("out_sample") or {}
        c.execute(
            "INSERT INTO research_rows(run_id, symbol, strategy, grp, trades, is_n, is_expectancy, "
            "is_win_rate, oos_n, oos_expectancy, oos_win_rate, oos_profit_factor, oos_max_dd, "
            "oos_total_r, control_expectancy, excess_over_control, weight) "
            "VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            (run_id, r["symbol"], r["strategy"], r.get("group"), r["n"],
             ins.get("n"), ins.get("expectancy"), ins.get("win_rate"),
             oos.get("n"), oos.get("expectancy"), oos.get("win_rate"),
             oos.get("profit_factor"), oos.get("max_dd_r"), oos.get("total_r"),
             r.get("control_expectancy"), r.get("excess_over_control"), r.get("weight")))
    c.execute("UPDATE research_runs SET finished_at=?, markets=?, strategies=?, combinations=?, "
              "trades_simulated=?, bars_per_market=?, beating_control=?, judged=?, elapsed_s=? WHERE id=?",
              (store.now_iso(), len(good), len(specs), g["combinations_tested"],
               g["total_trades_simulated"], bars, g.get("strategies_beating_control"),
               g.get("strategies_judged"), round(time.time() - t0, 1), run_id))
    c.commit()
    say("done")

    return {"run_id": run_id, "asset": asset, "markets": len(good), "strategies": len(specs),
            "combinations": g["combinations_tested"], "trades": g["total_trades_simulated"],
            "beating_control": g.get("strategies_beating_control"),
            "judged": g.get("strategies_judged"),
            "elapsed_s": round(time.time() - t0, 1),
            "by_strategy": g["by_strategy"]}


def run_in_child(kwargs: Dict) -> None:
    """Entry point of the separate research process."""
    run(**kwargs)


def run_background(**kwargs):
    """Start a research run in its own process and return it.

    A research run is minutes of pure computation. Run as threads inside the app it would
    compete with the web server for Python's interpreter lock, and every page refresh
    would wait tens of seconds behind it. In its own process it uses its own core and
    the app stays responsive.
    """
    import multiprocessing
    p = multiprocessing.get_context("spawn").Process(target=run_in_child, args=(kwargs,),
                                                     name="jarvus-research", daemon=True)
    p.start()
    return p


def latest_run() -> Optional[Dict]:
    _init()
    r = store.conn().execute(
        "SELECT * FROM research_runs WHERE finished_at IS NOT NULL ORDER BY id DESC LIMIT 1").fetchone()
    return dict(r) if r else None


def latest_runs() -> Dict[str, Dict]:
    """The most recent finished run for each asset class."""
    _init()
    out = {}
    for asset in ("crypto", "stock"):
        r = store.conn().execute(
            "SELECT * FROM research_runs WHERE finished_at IS NOT NULL AND asset=? ORDER BY id DESC LIMIT 1",
            (asset,)).fetchone()
        if r:
            out[asset] = dict(r)
    return out


def weights(run_id: int = None) -> Dict[str, Dict[str, float]]:
    """Per-market strategy weights: the latest crypto run and the latest stock run, together."""
    _init()
    ids = [run_id] if run_id is not None else [r["id"] for r in latest_runs().values()]
    out: Dict[str, Dict[str, float]] = {}
    for rid in ids:
        rows = store.conn().execute(
            "SELECT symbol, strategy, weight FROM research_rows WHERE run_id=? AND weight IS NOT NULL",
            (rid,)).fetchall()
        for r in rows:
            out.setdefault(r["symbol"], {})[r["strategy"]] = r["weight"]
    return out


def leaderboard(run_id: int = None, limit: int = 200) -> List[Dict]:
    """Strategies ranked by how far they beat the control, pooled across markets."""
    _init()
    run = latest_run() if run_id is None else {"id": run_id}
    if not run:
        return []
    rows = store.conn().execute(
        "SELECT strategy, grp, COUNT(*) AS markets, SUM(trades) AS trades, "
        "SUM(COALESCE(oos_n,0)) AS oos_trades, "
        "SUM(COALESCE(oos_expectancy,0)*COALESCE(oos_n,0)) AS e_sum, "
        "SUM(COALESCE(excess_over_control,0)*COALESCE(oos_n,0)) AS x_sum, "
        "SUM(COALESCE(oos_total_r,0)) AS total_r, "
        "AVG(COALESCE(oos_win_rate,0)) AS win_rate, "
        "SUM(CASE WHEN weight > 0 THEN 1 ELSE 0 END) AS markets_weighted "
        "FROM research_rows WHERE run_id=? GROUP BY strategy, grp", (run["id"],)).fetchall()
    out = []
    for r in rows:
        n = r["oos_trades"] or 0
        out.append({
            "strategy": r["strategy"], "group": r["grp"], "markets": r["markets"],
            "trades": r["trades"], "oos_trades": n,
            "oos_expectancy": round(r["e_sum"] / n, 4) if n else None,
            "excess_over_control": round(r["x_sum"] / n, 4) if n else None,
            "total_r": round(r["total_r"] or 0, 2),
            "win_rate": round(r["win_rate"] or 0, 1),
            "markets_weighted": r["markets_weighted"],
            "is_control": r["strategy"].startswith("_control"),
        })
    out.sort(key=lambda e: (e["excess_over_control"] is None, -(e["excess_over_control"] or 0)))
    return out[:limit]


def summary(asset: str = None) -> Dict:
    run = latest_runs().get(asset) if asset else latest_run()
    if not run:
        return {"has_run": False, "asset": asset,
                "note": "No research run yet for this market. Until one exists the swarm votes unweighted: "
                        "every strategy counts the same because none has been measured."}
    lb = leaderboard(run["id"])
    controls = [e for e in lb if e["is_control"]]
    real = [e for e in lb if not e["is_control"]]
    return {
        "has_run": True, "asset": run.get("asset", "crypto"), "run": run, "leaderboard": lb,
        "control_expectancy": max((c["oos_expectancy"] or 0) for c in controls) if controls else None,
        "beating_control": sum(1 for e in real if (e["excess_over_control"] or 0) > 0),
        "judged": sum(1 for e in real if e["excess_over_control"] is not None),
        "note": ("Strategies are ranked by how far they beat a control that buys with no analysis "
                 "at all. In a rising market the control makes money too, so anything that cannot "
                 "clear it is measuring the weather rather than an edge."),
    }
