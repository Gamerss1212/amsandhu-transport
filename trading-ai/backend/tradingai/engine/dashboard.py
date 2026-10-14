"""Small, measured summaries for page 1 (specification revision 13, section 8A): the market strip and the decision
activity panel. Every number is read from stored data; nothing here is estimated or smoothed for display.

* Market strip: crypto prices and 24-hour changes come from the shared venue snapshot (market discovery); other
  instruments use their newest completed daily bars (change = last close vs the previous session's close). Each item
  carries its source, basis, timestamp and freshness. Results are cached for 15 seconds.
* Decision activity: counts by outcome over a window, abstention share (NO_TRADE and HOLD out of all decisions),
  signal disagreement (decisions whose strategy signal and agent ensemble pointed opposite ways) and decision latency
  percentiles, all from the decision log.
"""

from __future__ import annotations

import json
import threading
import time
from typing import TYPE_CHECKING, Optional

from tradingai.storage.db import now_ms

if TYPE_CHECKING:
    from tradingai.app import App

STRIP = ["COINBASE:BTC-USD", "COINBASE:ETH-USD", "COINBASE:SOL-USD", "US:AAPL", "US:NVDA", "US:TSLA", "US:MSFT"]
DEMO_STRIP = ["DEMO:DEMO-TREND", "DEMO:DEMO-RANGE", "DEMO:DEMO-VOLATILE"]
MEMES_SHOWN = 3
_cache: dict[str, tuple[float, list]] = {}
_lock = threading.Lock()


def _crypto_item(app: "App", iid: str, label: str, meme: Optional[dict] = None) -> Optional[dict]:
    q = app.discovery.quote(iid)
    if not q or q.get("last") is None:
        return None
    chg = None if not q.get("open") else float(q["last"] / q["open"] - 1)
    return {"instrument_id": iid, "label": label, "price": str(q["last"]), "change": chg, "basis": "24h",
            "as_of": q["received"], "fresh": app.discovery.fresh(q), "source": "Coinbase 24-hour stats (snapshot)",
            "meme": meme}


def _bar_item(app: "App", iid: str) -> Optional[dict]:
    inst = app.book.get(iid)
    try:
        b, st = app.md.bars(iid, "1d", lookback=3, max_age_s=3600)
    except Exception:                                         # noqa: BLE001 - a missing feed shows as unavailable
        return {"instrument_id": iid, "label": inst.symbol, "price": None, "change": None, "basis": "prev close",
                "as_of": None, "fresh": False, "source": app.sources[iid].provider, "meme": None}
    if not len(b):
        return None
    chg = float(b.close[-1] / b.close[-2] - 1) if len(b) >= 2 and b.close[-2] else None
    return {"instrument_id": iid, "label": inst.symbol, "price": f"{float(b.close[-1]):.6g}", "change": chg,
            "basis": "prev close", "as_of": int(b.available_at[-1]), "fresh": bool(st.get("fresh")),
            "source": app.sources[iid].provider + (" (simulated)" if b.simulated else ""), "meme": None,
            "simulated": bool(b.simulated)}


def market_strip(app: "App") -> dict:
    with _lock:
        hit = _cache.get("strip")
        if hit and time.time() - hit[0] < 15:
            return {"items": hit[1], "cached": True}
    items: list[dict] = []
    if app.offline:
        for iid in DEMO_STRIP:
            if iid in app.sources:
                it = _bar_item(app, iid)
                if it:
                    items.append(it)
    else:
        for iid in STRIP:
            if iid not in app.sources:
                continue
            it = _crypto_item(app, iid, app.book.get(iid).symbol) if iid.startswith("COINBASE:") else _bar_item(app, iid)
            if it:
                items.append(it)
        memes = []
        for r in app.discovery.tradable_crypto(400):
            tag = app.discovery.meme_tags(r["base"])
            if tag:
                memes.append((r, tag))
            if len(memes) >= MEMES_SHOWN:
                break
        for r, tag in memes:
            it = _crypto_item(app, f"COINBASE:{r['symbol']}", r["symbol"], meme=tag)
            if it:
                items.append(it)
    with _lock:
        _cache["strip"] = (time.time(), items)
    return {"items": items, "cached": False}


def decision_activity(app: "App", minutes: int = 60) -> dict:
    since = now_ms() - minutes * 60_000
    rows = app.db.query("SELECT ts, outcome, signal, votes, latency FROM decisions WHERE ts>=? ORDER BY ts", (since,))
    counts: dict[str, int] = {}
    lat: list[float] = []
    disagree = 0
    buckets = [0] * 12
    for r in rows:
        counts[r["outcome"]] = counts.get(r["outcome"], 0) + 1
        buckets[min(11, int((r["ts"] - since) / (minutes * 60_000 / 12)))] += 1
        try:
            L = json.loads(r["latency"] or "{}")
            if L.get("total_ms") is not None:
                lat.append(float(L["total_ms"]))
            sig = (json.loads(r["signal"] or "{}") or {}).get("strategy")
            ens = ((json.loads(r["votes"] or "{}") or {}).get("ensemble") or {}).get("score")
            if sig and ens is not None and abs(ens) > 0.1 and (sig > 0) != (ens > 0):
                disagree += 1
        except (ValueError, TypeError, AttributeError):
            continue
    n = len(rows)
    lat.sort()

    def pct(p: float) -> Optional[float]:
        return round(lat[min(len(lat) - 1, int(len(lat) * p))], 1) if lat else None
    return {"window_minutes": minutes, "decisions": n, "by_outcome": counts, "per_bucket": buckets,
            "abstention": None if not n else (counts.get("NO_TRADE", 0) + counts.get("HOLD", 0)) / n,
            "disagreement": None if not n else disagree / n,
            "latency_ms": {"p50": pct(0.5), "p95": pct(0.95) if len(lat) >= 20 else None, "n": len(lat)},
            "definitions": {"abstention": "share of decisions that ended in NO TRADE or HOLD",
                            "disagreement": "share of decisions where the strategy signal and the agent ensemble "
                                            "(|score| > 0.1) pointed in opposite directions",
                            "latency": "time from a completed bar to the finished decision, measured per decision"}}
