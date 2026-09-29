"""Generate bots/registry.json from the strategy catalog.

Every implemented strategy gets at least one bot on each market it targets; bots are spread over
a fixed pool of instruments so that the whole fleet shares a limited number of data series.
Stage tags: "1" (the pilot bot), "10", "50" and "250" (every bot) select the staged roll-out.

    python bots/generate.py
"""

import json
import os
from collections import OrderedDict

HERE = os.path.dirname(os.path.abspath(__file__))
CATALOG = os.path.join(os.path.dirname(os.path.dirname(HERE)), "strategies", "catalog.json")

CRYPTO = [("coinbase", "BTC-USD"), ("coinbase", "ETH-USD"), ("coinbase", "SOL-USD"), ("coinbase", "XRP-USD"),
          ("coinbase", "DOGE-USD"), ("coinbase", "LINK-USD"), ("coinbase", "AVAX-USD"), ("coinbase", "LTC-USD"),
          ("kraken", "XXBTZUSD"), ("kraken", "XETHZUSD"), ("okx", "BTC-USDT"), ("okx", "ETH-USDT")]
STOCKS = ["SPY", "QQQ", "AAPL", "NVDA", "MSFT", "TSLA", "AMZN", "AMD", "META", "IWM", "COIN", "SHOP.TO", "RY.TO"]
ROUND_STEP = {"BTC-USD": 1000, "XXBTZUSD": 1000, "BTC-USDT": 1000, "ETH-USD": 100, "XETHZUSD": 100, "ETH-USDT": 100,
              "SOL-USD": 10, "LTC-USD": 5, "AVAX-USD": 1, "LINK-USD": 1, "XRP-USD": 0.1, "DOGE-USD": 0.01,
              "SPY": 5, "QQQ": 5, "IWM": 5, "AAPL": 5, "NVDA": 5, "MSFT": 5, "TSLA": 5, "AMZN": 5, "AMD": 5, "META": 5,
              "COIN": 5, "SHOP.TO": 5, "RY.TO": 5}
ORDERFLOW_OK = {"coinbase", "okx"}


def main(target=250):
    with open(CATALOG) as fh:
        cat = json.load(fh)
    strats = [s for s in cat["strategies"] if s["implementation_status"] == "implemented"]
    bots = []
    ci = si = 0

    def add(s, venue, sym, extra=None):
        n = len(bots) + 1
        b = OrderedDict(bot_id=f"BOT-{n:03d}", name=f"{s['name']} | {sym}", strategy_id=s["id"], venue=venue,
                        instrument=sym, enabled=True, stages=["250"])
        p = {}
        params = (s.get("definition") or {}).get("params") or {}
        if "step" in params:
            p["step"] = ROUND_STEP.get(sym, 1)
        if "bench" in params:
            b["bench"] = "SPY"
        if "lead" in params:
            p["lead"] = "BTC-USD"
        if p:
            b["params"] = p
        if extra:
            b.update(extra)
        bots.append(b)

    pinned = {  # strategies whose rules name a specific instrument
        "crypto_pair_ratio_reversion": [("coinbase", "ETH-BTC")], "perp_basis_reversion": [("okx", "BTC-USDT-SWAP")],
        "coinbase_premium": [("coinbase", "BTC-USD")], "stablecoin_peg_reversion": [("coinbase", "USDT-USD")],
        "perp_volume_lead": [("okx", "BTC-USDT")], "cme_gap_fill": [("coinbase", "BTC-USD")],
        "mtf_momentum_alignment": [("okx", "BTC-USDT"), ("kraken", "XXBTZUSD")],   # needs 4h bars (not on Coinbase)
    }
    for s in strats:
        data = set(s["data"])
        flow = bool(data & {"trades", "book"})
        if s["key"] in pinned:
            for v, sym in pinned[s["key"]]:
                refs = ["okx:BTC-USDT"] if s["key"] == "coinbase_premium" else None
                add(s, v, sym, {"refs": refs} if refs else None)
            continue
        crypto_insts = [x for x in (s.get("instruments") or []) if x.endswith("-USD") and "crypto" in s["markets"]]
        if crypto_insts:                     # rules written for named coins (the knowledge-pack memecoin set)
            for sym in crypto_insts:
                add(s, "coinbase", sym)
            continue
        if "crypto" in s["markets"]:
            if s["key"] == "lead_lag_catch_up":
                for sym in ("ETH-USD", "SOL-USD"):
                    add(s, "coinbase", sym)
            else:
                pool = [c for c in CRYPTO if c[0] in ORDERFLOW_OK] if flow else CRYPTO
                if s["key"] == "ema_cross_vwap":
                    add(s, "coinbase", "BTC-USD")
                else:
                    add(s, *pool[ci % len(pool)])
                    ci += 1
        if "stock" in s["markets"]:
            insts = s.get("instruments") or []
            sym = insts[0] if insts and insts[0] in STOCKS else STOCKS[si % len(STOCKS)]
            if s["key"] in ("relative_strength_vs_index", "residual_reversion") and sym in ("SPY",):
                sym = "NVDA"
            extra = {"refs": ["yahoo:^VIX"]} if s["key"] == "vix_spike_reversion" else None
            add(s, "yahoo", sym, extra)
            si += 1
    # second pass: more instruments per strategy until the target is reached (same strategy, different market = variant bot)
    k = 0
    while len(bots) < target:
        s = strats[k % len(strats)]
        k += 1
        if s["key"] in pinned or s["key"] == "lead_lag_catch_up" or s.get("instruments"):
            continue
        data = set(s["data"])
        if "crypto" in s["markets"] and (len(bots) % 2 == 0 or "stock" not in s["markets"]):
            pool = [c for c in CRYPTO if c[0] in ORDERFLOW_OK] if data & {"trades", "book"} else CRYPTO
            add(s, *pool[ci % len(pool)])
            ci += 1
        elif "stock" in s["markets"]:
            if data & {"events:fomc", "events:cpi"}:
                continue
            add(s, "yahoo", STOCKS[si % len(STOCKS)], {"refs": ["yahoo:^VIX"]} if s["key"] == "vix_spike_reversion" else None)
            si += 1
    # stages
    fam = {s["id"]: s["family"] for s in strats}
    bots[0]["stages"] = ["1", "10", "50", "250"]
    seen, ten = set(), [bots[0]]
    for b in bots[1:]:
        f = fam[b["strategy_id"]]
        if b["venue"] != "yahoo" and f not in seen and len(ten) < 10:
            seen.add(f)
            ten.append(b)
    for b in ten:
        if "10" not in b["stages"]:
            b["stages"] = ["10", "50", "250"]
    fifty = list(ten)
    for b in bots:
        if len(fifty) >= 50:
            break
        if b not in fifty:
            fifty.append(b)
    for b in fifty:
        if "50" not in b["stages"]:
            b["stages"] = sorted(set(b["stages"]) | {"50", "250"}, key=lambda x: int(x))
    out = {"_comment": "Generated by bots/generate.py from strategies/catalog.json. One bot = one strategy on one instrument.",
           "bots": bots}
    with open(os.path.join(HERE, "registry.json"), "w") as fh:
        json.dump(out, fh, indent=1)
    cov = {}
    for b in bots:
        cov.setdefault(b["strategy_id"], []).append(b["bot_id"])
    with open(os.path.join(HERE, "coverage.json"), "w") as fh:
        json.dump({"strategies_implemented": len(strats), "strategies_with_bots": len(cov), "bots": len(bots),
                   "strategy_to_bots": cov}, fh, indent=1)
    print(f"{len(bots)} bots for {len(cov)} of {len(strats)} implemented strategies; "
          f"stage 10: {sum('10' in b['stages'] for b in bots)}, stage 50: {sum('50' in b['stages'] for b in bots)}")


if __name__ == "__main__":
    main()
