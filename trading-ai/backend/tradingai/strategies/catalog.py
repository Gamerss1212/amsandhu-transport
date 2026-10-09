"""The owner's 80-template strategy catalog (ST001-ST080) and its 47-source register, from
docs/specs/AI_Trading_System_Master_Prompt.md (revision 3, October 9 2026), mapped onto this software.

The card text, evidence labels (R research-supported family, C documented construction, H hypothesis) and source
access labels (A abstract, P paper text, M mechanics, B bibliographic) are the specification's own; this software has
not re-read or replicated those papers. What this module adds is the honest mapping to what is implemented here:

* which strategy generators (single-instrument templates) or portfolio templates implement the card, or
* the reason code that blocks it (missing data feeds, unsupported products, permissions), and
* at runtime, what this installation's own research ledger says (kept separate from the published evidence).

Lifecycle labels follow the specification: documented -> specified -> implemented -> evaluated -> paper_eligible ->
live_eligible, plus suspended. live_eligible is never reached in this build: no broker adapter is verified.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Optional

_DATA = Path(__file__).with_name("data")

# card id -> (implementations, blocking reason code or None, note). "P:" marks a portfolio template.
MAP: dict[str, tuple[list[str], Optional[str], str]] = {
    "ST001": (["P:ST001", "P:ST001-E", "tsmom"], None, "multi-asset portfolio (futures+FX, and an ETF variant) plus a "
              "single-instrument version; provider continuous futures series, not real contract rolls"),
    "ST002": (["sma_cross", "ema_cross", "triple_ma", "ma_slope"], None, "completed-bar crossovers, tested per market"),
    "ST003": (["donchian_trend", "donchian_breakout"], None, "channel from prior completed bars, trailing-channel exit"),
    "ST004": (["P:ST004"], None, "six ETFs ranked by trailing return; each slot held only while it beats short "
              "Treasuries (SHY)"),
    "ST005": (["P:ST005", "vol_scaled_trend", "vol_target_hold"], None, "lagged-volatility scaling capped at 1.0 "
              "(never adds leverage)"),
    "ST006": (["trend_pullback"], None, "pullback to the fast average inside a slow-average trend"),
    "ST007": ([], "INSUFFICIENT_DATA", "needs point-in-time valuation data (book values, real exchange rates, yields)"),
    "ST008": ([], "FUNDING_UNFAVORABLE", "needs forward points, broker financing, futures curves and yields: not "
              "connected"),
    "ST009": (["P:ST009"], None, "12-1 momentum on seven large US stocks: survivorship-biased, capped at RESEARCH "
              "FURTHER"),
    "ST010": (["P:ST010"], None, "nine SPDR sector ETFs, top k by trailing return, cash when not positive"),
    "ST011": ([], "INSUFFICIENT_DATA", "needs point-in-time accounting data (book equity, filing dates)"),
    "ST012": ([], "INSUFFICIENT_DATA", "needs timestamped earnings / free-cash-flow data"),
    "ST013": ([], "INSUFFICIENT_DATA", "needs point-in-time profitability, growth and safety fields"),
    "ST014": ([], "INSUFFICIENT_DATA", "needs point-in-time operating profitability"),
    "ST015": ([], "INSUFFICIENT_DATA", "needs point-in-time asset growth"),
    "ST016": ([], "BORROW_UNAVAILABLE", "needs leverage and shorting; the long-only adaptation is ST017"),
    "ST017": (["P:ST017"], None, "lowest lagged-volatility SPDR sectors, equally weighted"),
    "ST018": (["P:ST018"], None, "weekly, long-only adaptation; size-based news proxy; survivorship-biased stock part"),
    "ST019": (["earnings_drift"], "INSUFFICIENT_DATA", "needs timestamped earnings-surprise data (not connected)"),
    "ST020": ([], "INSUFFICIENT_DATA", "needs verified deal terms and timelines"),
    "ST021": (["orb", "initial_balance_breakout"], None, "frozen opening range, later completed-bar break, session "
              "deadline"),
    "ST022": (["first_hour_momentum"], None, "first half-hour (incl. overnight) predicts the last half-hour; intraday "
              "history from the free provider is short"),
    "ST023": (["vwap_reclaim", "price_above_vwap", "anchored_vwap_trend"], None, "session VWAP from the provider's "
              "volume; crypto volume is venue-specific"),
    "ST024": (["vwap_reversion", "vwap_rejection", "vwap_band_breakout"], None, "standardized VWAP deviation"),
    "ST025": (["prior_session_breakout"], None, "regular-session prior high/low"),
    "ST026": (["failed_breakout"], None, "added for this catalog: range known before the excursion, completed-bar "
              "re-entry"),
    "ST027": (["gap_continuation"], None, "gap classified from prior close and the opening bar"),
    "ST028": (["gap_fade"], None, "small gaps against the trend"),
    "ST029": (["squeeze_breakout", "vol_compression"], None, "band-width compression then a frozen breakout level"),
    "ST030": (["orderbook_imbalance"], "INSUFFICIENT_DATA", "needs synchronized order-book depth (no depth feed)"),
    "ST031": (["structure_break"], None, "added for this catalog: swings confirmed k bars later, never repainting"),
    "ST032": (["sweep_reclaim"], None, "added for this catalog: known level, minimum ATR excursion, same-bar reclaim, "
              "bounded holding time"),
    "ST033": (["pairs_zscore"], "BORROW_UNAVAILABLE", "equity pairs need shorting (not in the paper engine); the "
              "rolling-beta z-score adaptation runs only for shortable markets (FX, futures)"),
    "ST034": (["pairs_zscore", "ratio_momentum"], "RELATIONSHIP_BROKEN", "cointegration diagnostics are not "
              "implemented; the z-score adaptation is research only"),
    "ST035": ([], "INSUFFICIENT_DATA", "needs a broad equity universe with sector betas and shorting"),
    "ST036": ([], "INSUFFICIENT_DATA", "needs a broad equity universe for PCA factors and shorting"),
    "ST037": ([], "PERMISSION_MISSING", "creation/redemption needs authorized-participant access"),
    "ST038": ([], "INSUFFICIENT_DATA", "needs verified share ratios, conversion rights and both listings"),
    "ST039": (["carry_filter"], "FUNDING_UNFAVORABLE", "needs forward points or the broker's financing schedule"),
    "ST040": (["P:ST040"], None, "five currencies against USD, long strongest / short weakest; no carry in returns"),
    "ST041": ([], "INSUFFICIENT_DATA", "needs price-level and inflation data with release lags"),
    "ST042": ([], "INSUFFICIENT_DATA", "needs a dollar state variable and carry data"),
    "ST043": ([], "INSUFFICIENT_DATA", "needs simultaneous executable bid/ask for three pairs (only reference mids)"),
    "ST044": (["asian_range_breakout", "london_open_momentum", "ny_overlap_continuation"], None,
              "exchange-aware FX session ranges"),
    "ST045": (["P:ST045", "tsmom"], None, "BTC/ETH/SOL long/flat with volatility sizing (spot shorting unavailable)"),
    "ST046": (["P:ST046"], None, "three coins only: too small a cross-section; capped at RESEARCH FURTHER"),
    "ST047": (["basis_convergence"], "PRODUCT_UNSUPPORTED", "needs dated crypto futures; Kraken derivatives are not "
              "available to Canadian residents"),
    "ST048": (["funding_reversion", "funding_momentum"], "PRODUCT_UNSUPPORTED", "needs perpetual contracts and funding "
              "feeds; not available here"),
    "ST049": (["cross_venue_spread"], "PERMISSION_MISSING", "signal research only: execution needs pre-positioned "
              "inventory on two venues"),
    "ST050": ([], "INSUFFICIENT_DATA", "needs order-book depth for three pairs"),
    "ST051": ([], "INSUFFICIENT_DATA", "needs crypto ETF and futures holdings/settlement data"),
    "ST052": (["liquidation_reversal"], "INSUFFICIENT_DATA", "needs attributable liquidation and open-interest feeds"),
    "ST053": ([], "INSUFFICIENT_DATA", "needs contract-month curves"),
    "ST054": ([], "INSUFFICIENT_DATA", "needs timestamped inventory releases and curves"),
    "ST055": (["calendar_spread"], "INSUFFICIENT_DATA", "needs individual contract months"),
    "ST056": ([], "INSUFFICIENT_DATA", "needs crude and product contract months with units"),
    "ST057": ([], "INSUFFICIENT_DATA", "needs soybean complex contract months"),
    "ST058": ([], "INSUFFICIENT_DATA", "needs contract-month pairs over many seasons"),
    "ST059": ([], "INSUFFICIENT_DATA", "needs contract-month data for related commodities"),
    "ST060": ([], "PRODUCT_UNSUPPORTED", "needs bonds/rate futures with DV01 data"),
    "ST061": ([], "PRODUCT_UNSUPPORTED", "needs three-point curve instruments with DV01"),
    "ST062": ([], "PRODUCT_UNSUPPORTED", "needs cash Treasuries, deliverable baskets, repo"),
    **{f"ST{n:03d}": ([], "PRODUCT_UNSUPPORTED", "options: no option chains, Greeks or option-order adapter here")
       for n in range(63, 75)},
    **{f"ST{n:03d}": ([], "PRODUCT_UNSUPPORTED", "bonds/credit: no issue-level bond data or bond trading adapter")
       for n in range(75, 81)},
}

STATES = ["documented", "specified", "implemented", "evaluated", "paper_eligible", "live_eligible", "suspended"]


def load() -> dict:
    cat = json.loads((_DATA / "catalog_st.json").read_text(encoding="utf-8"))
    src = json.loads((_DATA / "sources.json").read_text(encoding="utf-8"))
    return {"groups": cat["groups"], "cards": cat["cards"], "sources": src}


def implementation(card_id: str) -> dict:
    impl, block, note = MAP.get(card_id, ([], "INSUFFICIENT_DATA", "not mapped"))
    return {"implementations": impl, "blocked": block, "mapping_note": note,
            "portfolio": [i[2:] for i in impl if i.startswith("P:")],
            "generators": [i for i in impl if not i.startswith("P:")]}


def view(ledger_rows: list[dict], retired: set[str], deployed: set[str]) -> list[dict]:
    """Every card with its mapping, lifecycle state and this installation's own evidence."""
    from tradingai.strategies.library import specs
    lib = specs()
    data = load()
    by_strategy: dict[str, list[dict]] = {}
    for r in ledger_rows:
        by_strategy.setdefault(r["strategy_id"], []).append(r)
    out = []
    for c in data["cards"]:
        m = implementation(c["id"])
        template_ids = [sid for g in m["generators"] for sid in lib if sid.split(".")[0] == g]
        runs = [r for sid in m["portfolio"] for r in by_strategy.get(sid, [])]
        runs += [r for sid in template_ids for r in by_strategy.get(sid, [])]
        verdicts: dict[str, int] = {}
        for r in runs:
            verdicts[r["verdict"] or r["status"]] = verdicts.get(r["verdict"] or r["status"], 0) + 1
        best = max(runs, key=lambda r: (r["verdict"] == "PAPER TEST", r["verdict"] == "RESEARCH FURTHER",
                                        r["quality"] or 0), default=None)
        runnable = bool(m["portfolio"]) or any(lib[s].runnable for s in template_ids)
        if any(k in retired for k in [c["id"]] + template_ids):
            state = "suspended"
        elif verdicts.get("PAPER TEST") or any(k in deployed for k in template_ids + m["portfolio"]):
            state = "paper_eligible"
        elif runs:
            state = "evaluated"
        elif runnable and not m["blocked"]:
            state = "implemented"
        elif m["implementations"]:
            state = "specified"
        else:
            state = "documented"
        out.append(dict(c, **m, templates=len(template_ids), state=state, runs=len(runs), verdicts=verdicts,
                        best=None if best is None else {k: best.get(k) for k in (
                            "experiment_id", "strategy_id", "verdict", "quality", "instrument", "tf", "created")}))
    return out
