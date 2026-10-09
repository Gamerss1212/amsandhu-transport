"""Backtest every implementable template of the owner's 80-template catalog on real data, with the same research
engine the app uses (results go into the app's research ledger, counted as trials).

    python scripts/catalog_batch.py <home folder>
"""

import sys
import time

sys.path.insert(0, __file__.rsplit("/scripts/", 1)[0] + "/backend")

from tradingai.app import App                                  # noqa: E402
from tradingai.research.portfolio import PORTFOLIOS            # noqa: E402
from tradingai.strategies.library import specs                 # noqa: E402

DAILY = ["CME:ES", "COMEX:GC", "NYMEX:CL", "CBOT:ZN", "FX:EURUSD", "COINBASE:BTC-USD", "US:SPY", "US:QQQ", "US:GLD"]
PLAN = {   # card -> generator -> (instrument, timeframe) list, chosen by each card's native horizon
    "ST001": {"tsmom": [(i, "1d") for i in DAILY]},
    "ST002": {"sma_cross": [(i, "1d") for i in DAILY], "ema_cross": [(i, "1d") for i in DAILY[:6]]},
    "ST003": {"donchian_trend": [(i, "1d") for i in DAILY]},
    "ST006": {"trend_pullback": [("US:SPY", "1h"), ("COINBASE:BTC-USD", "1h"), ("FX:EURUSD", "1h"), ("US:QQQ", "1d")]},
    "ST021": {"orb": [("US:SPY", "15m"), ("US:QQQ", "15m"), ("CME:ES", "15m")]},
    "ST022": {"first_hour_momentum": [("US:SPY", "30m"), ("US:QQQ", "30m")]},
    "ST023": {"price_above_vwap": [("US:SPY", "15m"), ("COINBASE:BTC-USD", "1h")]},
    "ST024": {"vwap_reversion": [("US:SPY", "15m"), ("COINBASE:BTC-USD", "1h")]},
    "ST025": {"prior_session_breakout": [("US:SPY", "15m"), ("CME:ES", "15m")]},
    "ST026": {"failed_breakout": [("COINBASE:BTC-USD", "1h"), ("COINBASE:ETH-USD", "1h"), ("US:SPY", "1h"),
                                  ("FX:EURUSD", "1h"), ("US:SPY", "1d")]},
    "ST027": {"gap_continuation": [("US:SPY", "15m"), ("US:QQQ", "15m")]},
    "ST028": {"gap_fade": [("US:SPY", "15m"), ("US:QQQ", "15m")]},
    "ST029": {"squeeze_breakout": [("COINBASE:BTC-USD", "1h"), ("US:SPY", "1h"), ("FX:EURUSD", "1h")]},
    "ST031": {"structure_break": [("COINBASE:BTC-USD", "1h"), ("COINBASE:ETH-USD", "4h"), ("US:SPY", "1h"),
                                  ("FX:EURUSD", "1h"), ("US:SPY", "1d"), ("CME:ES", "1d")]},
    "ST032": {"sweep_reclaim": [("COINBASE:BTC-USD", "1h"), ("COINBASE:ETH-USD", "1h"), ("US:SPY", "1h"),
                                ("FX:EURUSD", "1h"), ("US:QQQ", "1d")]},
    "ST044": {"asian_range_breakout": [("FX:EURUSD", "1h"), ("FX:GBPUSD", "1h")],
              "london_open_momentum": [("FX:EURUSD", "1h"), ("FX:USDJPY", "1h")]},
    "ST045": {"tsmom": [("COINBASE:BTC-USD", "1d"), ("COINBASE:ETH-USD", "1d"), ("COINBASE:SOL-USD", "1d")]},
}
LOOKBACK = {"15m": 2000, "30m": 1200, "1h": 5000, "4h": 3000, "1d": 2500}


def template(gen: str) -> str:
    lib = specs()
    for filt in ("none", "session", "trend200", "adx", "vol_band", "relvol"):
        for exit_ in ("flip", "atr_bracket", "time", "trail"):
            sid = f"{gen}.{filt}.{exit_}"
            if sid in lib and lib[sid].runnable:
                return sid
    raise KeyError(gen)


def wait(app, jid):
    while app.jobs.view(jid)["state"] in ("queued", "running"):
        time.sleep(0.2)
    return app.jobs.view(jid, with_result=True)


def main(home):
    app = App(home, offline=False, start_loop=False, autopilot=False)
    t0 = time.time()
    for sid in PORTFOLIOS:
        j = wait(app, app.submit_portfolio(sid, by="catalog-batch")["job_id"])
        print(f"{time.time() - t0:7.0f}s PORTFOLIO {sid:8s} {j['state']:8s} {j.get('result') or j.get('error')}",
              flush=True)
    for card, gens in PLAN.items():
        for gen, targets in gens.items():
            sid = template(gen)
            for iid, tf in targets:
                try:
                    j = wait(app, app.submit_research(sid, iid, tf, "STANDARD", LOOKBACK[tf], by="catalog-batch")
                             ["job_id"])
                    res = j.get("result") or {}
                    print(f"{time.time() - t0:7.0f}s {card} {sid:34s} {iid:18s} {tf:4s} {j['state']:8s} "
                          f"{res.get('verdict') or res.get('status') or j.get('error')}", flush=True)
                except ValueError as e:
                    print(f"{card} {sid} {iid} {tf}: {e}", flush=True)
    app.shutdown()


if __name__ == "__main__":
    main(sys.argv[1])
