#!/usr/bin/env python3
"""The orchestrator: discover, rank, analyse, commit predictions, attach news.

One scan is a complete pass:
  1. discover every liquid market across the configured venues (cheap, one call each)
  2. pre-rank them and pick the ones worth a candle request
  3. fetch bias and setup timeframes concurrently
  4. run the volatility gate, the structure read, the confluence count and the cost gate
  5. write down what was claimed, with the threshold that will later grade it
  6. attach the headlines that name each asset
"""

from __future__ import annotations

import statistics
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import config
from engine import analysis, learn, marketdata, news, store, universe, volgate


def big_move_threshold(candles: List[dict], horizon_h: int) -> Optional[float]:
    """The forward range, in percent, that would count as a 'big move' for this market.

    Defined as the 67th percentile of this market's own trailing horizon-length ranges,
    so 'big' means big *for this market* rather than big in the abstract. Fixed at
    prediction time so the grading cannot drift afterwards.
    """
    if len(candles) < horizon_h * 3:
        return None
    ranges = []
    for i in range(horizon_h, len(candles)):
        w = candles[i - horizon_h:i]
        op = w[0]["open"]
        if op > 0:
            ranges.append((max(c["high"] for c in w) - min(c["low"] for c in w)) / op * 100)
    if len(ranges) < 20:
        return None
    ranges.sort()
    return ranges[int(len(ranges) * 0.67)]


def scan(deep_n: int = None, fee_tier: str = None, account: float = None,
         write: bool = True) -> Dict[str, object]:
    t0 = time.time()
    deep_n = deep_n or config.DEEP_SCAN_N
    fee_tier = fee_tier or config.DEFAULT_FEE_TIER
    fee_bps = config.FEE_TIERS.get(fee_tier, 26.0)
    account = account or config.DEFAULT_ACCOUNT

    scan_id = store.start_scan() if write else None

    uni = universe.scan()
    assets = universe.dedupe_by_base(uni["markets"])
    chosen = universe.pick_deep(assets, deep_n)

    ltf = marketdata.candles_many(chosen, config.SETUP_TF, config.CANDLES)
    htf = marketdata.candles_many(chosen, config.BIAS_TF, config.CANDLES)

    headlines = news.headlines()
    by_asset = news.match_symbols(headlines["items"], [m["base"] for m in chosen])

    rows: List[dict] = []
    predictions: List[dict] = []
    made_at = store.now_iso()
    resolve_at = (datetime.now(timezone.utc) +
                  timedelta(hours=config.RESOLVE_HORIZON_H)).strftime("%Y-%m-%dT%H:%M:%SZ")

    for m in chosen:
        lc = ltf.get(m["symbol"])
        if not lc:
            rows.append({**m, "error": "no candles available from any venue"})
            continue
        hc = htf.get(m["symbol"])
        gate = volgate.score(lc)
        s_ltf = analysis.structure(lc)
        s_htf = analysis.structure(hc) if hc else None
        if not gate or not s_ltf:
            rows.append({**m, "error": "not enough history to analyse"})
            continue

        sig = analysis.signal(m, s_htf, s_ltf, gate, fee_bps, account)
        thr = big_move_threshold(lc, config.RESOLVE_HORIZON_H)
        calibrated = learn.calibrated_probability(gate["blow_score"])

        row = {
            **m,
            "gate": gate,
            "structure": s_ltf,
            "htf": {"trend": s_htf["trend"], "ema_stack": s_htf["ema_stack"]} if s_htf else None,
            "signal": sig,
            "big_move_threshold_pct": round(thr, 2) if thr else None,
            "calibrated": calibrated,
            "news": by_asset.get(m["base"], [])[:4],
            "tradingview": tradingview_symbol(m),
        }
        rows.append(row)

        predictions.append({
            "made_at": made_at, "resolve_at": resolve_at,
            "symbol": m["symbol"], "venue": m["venue"], "price": m["price"],
            "gate_label": gate["label"], "blow_score": gate["blow_score"],
            "energy": gate["energy"], "expansion": gate["expansion"], "compression": gate["compression"],
            "atr_pct": gate["features"].get("atr_pct"),
            "big_move_threshold": thr,
            "confluence_score": sig["confluence"]["score"], "confluence_max": sig["confluence"]["max"],
            "grade": sig["confluence"]["grade"], "verdict": sig["verdict"],
            "cost_r": sig["confluence"]["cost_r"],
        })

    rows.sort(key=lambda r: -(r.get("gate", {}).get("blow_score") or -1))

    written = 0
    if write and predictions:
        written = store.write_predictions(predictions)
        store.finish_scan(scan_id, uni["total_discovered"], len(chosen), written,
                          f"fee tier {fee_tier}")

    return {
        "generated_at": made_at,
        "elapsed_s": round(time.time() - t0, 2),
        "fee_tier": fee_tier, "fee_bps_per_side": fee_bps, "account": account,
        "universe": {"discovered": uni["total_discovered"], "liquid": uni["passed_liquidity"],
                     "assets_after_dedupe": len(assets), "analysed": len(chosen),
                     "sources": uni["sources"]},
        "markets": rows,
        "news": headlines,
        "predictions_written": written,
        "resolve_horizon_h": config.RESOLVE_HORIZON_H,
        "errors": uni.get("errors", {}),
    }


def tradingview_symbol(m: dict) -> str:
    """Best-effort TradingView symbol for the embedded chart widget."""
    base, quote = m["base"], m["quote"]
    if m["venue"] == "coinbase":
        return f"COINBASE:{base}{quote}"
    if m["kind"] == "perp":
        return f"OKX:{base}{quote}.P"
    return f"OKX:{base}{quote}"


def market_detail(symbol: str, venue: str = "okx", fee_tier: str = None,
                  account: float = None) -> Dict[str, object]:
    """Everything known about one market, including the candles the charts draw."""
    fee_tier = fee_tier or config.DEFAULT_FEE_TIER
    fee_bps = config.FEE_TIERS.get(fee_tier, 26.0)
    uni = universe.scan()
    m = next((x for x in uni["markets"] if x["symbol"] == symbol), None)
    if not m:
        m = {"symbol": symbol, "base": symbol.split("-")[0], "quote": "USDT", "venue": venue,
             "kind": "spot", "price": 0.0, "usd_volume_24h": 0.0, "high24h": 0, "low24h": 0, "open24h": 0}
        m = universe.annotate(m)

    lc = marketdata.candles(symbol, m["venue"], config.SETUP_TF, config.CANDLES)
    hc = marketdata.candles(symbol, m["venue"], config.BIAS_TF, config.CANDLES)
    if not lc:
        return {"error": f"no candles for {symbol} on any venue", "symbol": symbol}

    gate = volgate.score(lc)
    s_ltf = analysis.structure(lc)
    s_htf = analysis.structure(hc) if hc else None
    sig = analysis.signal(m, s_htf, s_ltf, gate, fee_bps, account or config.DEFAULT_ACCOUNT)
    heads = news.headlines()

    return {
        "market": m, "gate": gate, "structure": s_ltf,
        "htf": s_htf, "signal": sig,
        "calibrated": learn.calibrated_probability(gate["blow_score"]) if gate else None,
        "tradingview": tradingview_symbol(m),
        "news": news.match_symbols(heads["items"], [m["base"]]).get(m["base"], [])[:8],
        "candles": [{"t": c["ts"].strftime("%Y-%m-%dT%H:%MZ"), "o": c["open"], "h": c["high"],
                     "l": c["low"], "c": c["close"], "v": c["volume"]} for c in lc[-180:]],
        "history": [dict(r) for r in store.recent_predictions(symbol, 20)],
        "fee_tier": fee_tier,
    }
