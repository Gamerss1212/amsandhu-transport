"""Import layer for the research knowledge pack (strategies/knowledge_pack, version 2.0.0).

The pack holds 320 records (302 trading hypotheses, 18 supporting methods) as research templates:
every performance field is null and the exact thresholds are left to pre-registration. This module

1. validates the pack: manifest hashes, unique ST### ids, required fields and allowed values from the
   pack's own schema, family / parent / source references, null performance, and the published counts;
2. records a disposition for every record, decided by reading it against this library:
     same       the library already holds this strategy (the pack adds provenance to that entry)
     new        formalized here as a new executable strategy (f06_pack_formalized.py, parameters frozen
                in PREREGISTRATION_PACK.md before any test was run)
     research   a distinct hypothesis that cannot be tested with the data this software has; kept as a
                blocked catalog entry with the concrete missing input
     supporting not a trading hypothesis under the pack's count policy (model frameworks, execution
                methods, risk filters); listed separately, never counted
3. registers the pack's 77 sources (as PK-S##) so catalog entries can cite them.

Performance is never copied from the pack (it has none). Sources establish mechanics and context only.
"""

import hashlib
import json
import os
import re

from lib import st
import sources

HERE = os.path.dirname(os.path.abspath(__file__))
PACK = os.path.join(os.path.dirname(HERE), "knowledge_pack")
# derived views the pack itself marks as renderings of strategy_catalog.json; not stored here
DERIVED = {"Strategy_Catalogue.md", "knowledge_base.jsonl"}

MEMES = ["DOGE-USD", "SHIB-USD", "PEPE-USD", "BONK-USD", "WIF-USD", "FLOKI-USD"]

# ---------------------------------------------------------------- dispositions (pack id -> decision)
SAME = {
    "ST001": ("ema_cross_vwap", "fast/slow average cross; this library's version adds a session-VWAP filter"),
    "ST002": ("ema_ribbon_pullback", "pullback to a trend average"), "ST003": ("vwap_reclaim", ""),
    "ST005": ("relative_strength_vs_index", "residual strength vs a benchmark"), "ST006": ("roc_ignition", "return burst"),
    "ST007": ("macd_hist_turn", ""), "ST008": ("adx_trend_start", ""), "ST010": ("late_day_high_breakout", "late-session continuation"),
    "ST011": ("orb_breakout", ""), "ST012": ("prior_day_breakout", ""), "ST013": ("donchian_breakout", ""),
    "ST014": ("bb_squeeze_breakout", ""), "ST015": ("nr7_breakout", "the inside-bar trigger is already recorded as a variant of NR7"), "ST016": ("nr7_breakout", ""), "ST017": ("premarket_high_break", ""),
    "ST018": ("gap_and_go", ""), "ST019": ("triangle_breakout", ""), "ST020": ("keltner_breakout", "ATR band breakout"),
    "ST021": ("vwap_band_reversion", ""), "ST022": ("bollinger_fade", ""), "ST024": ("turtle_soup", "failed range break"),
    "ST025": ("gap_fade_to_close", ""), "ST026": ("prior_day_rejection", ""), "ST027": ("ten_am_reversal", "opening impulse reversal"),
    "ST028": ("volume_climax_reversal", ""), "ST029": ("residual_reversion", ""), "ST030": ("range_box_reversion", ""),
    "ST034": ("residual_reversion", "sector residual; same mechanism"), "ST037": ("crypto_pair_ratio_reversion", "single-leg ETH/BTC ratio"),
    "ST040": ("lead_lag_catch_up", ""), "ST047": ("closing_imbalance", ""), "ST049": ("listing_announcement", ""),
    "ST050": ("tod_seasonality", ""), "ST051": ("microprice_queue", "queue imbalance"), "ST053": ("trade_imbalance_persistence", ""),
    "ST054": ("cvd_divergence", ""), "ST055": ("absorption", ""), "ST057": ("microprice_queue", "microprice"),
    "ST060": ("value_area_acceptance_breakout", ""), "ST061": ("cross_exchange_arbitrage", ""), "ST062": ("triangular_arbitrage", ""),
    "ST064": ("funding_carry", ""), "ST071": ("avellaneda_stoikov_mm", ""), "ST072": ("avellaneda_stoikov_mm", "volatility-adaptive quoting is part of the model"),
    "ST074": ("grid_trading", ""), "ST091": ("bull_flag", ""), "ST092": ("double_bottom", ""), "ST093": ("head_and_shoulders", ""),
    "ST094": ("pin_bar_at_level", ""), "ST095": ("engulfing_at_swing", ""), "ST096": ("fib_retracement", ""),
    "ST097": ("fvg_fill_continuation", ""), "ST100": ("harmonic_patterns", "combined Wyckoff/harmonic/Elliott family counted once"),
}
NEW = {  # pack id -> key of the formalized strategy in f06_pack_formalized.py
    "ST004": "range_breakout_retest", "ST009": "tsmom_vol_scaled",
    "ST023": "rsi_extreme_recovery", "ST045": "fomc_post_reaction", "ST098": "sweep_structure_shift",
    "ST099": "order_block_retest",
    "ST181": "meme_breadth_momentum", "ST182": "meme_leader_pullback", "ST183": "meme_laggard_breakout",
    "ST186": "meme_leader_follower_lag", "ST222": "meme_btc_riskon", "ST223": "meme_resilient_rebound",
    "ST224": "meme_residual_reversion", "ST225": "meme_squeeze_release", "ST227": "meme_session_handover",
    "ST229": "meme_aftershock_reclaim", "ST233": "meme_native_ratio_breakout", "ST234": "meme_nested_compression_breakout",
    "ST239": "meme_midpoint_acceptance", "ST271": "meme_relative_momentum_leader",
}
BRAIN = {"ST081": "the Fleet Brain allocates among strategies by regime and abstains (benching) when evidence is negative",
         "ST082": "the Fleet Brain scores every candidate entry and vetoes or resizes it (a meta-label filter)",
         "ST083": "the Fleet Brain uses the uncertainty of each estimate (Thompson sampling, 95% benching bound)"}
# why a distinct hypothesis cannot be tested here, by pack family (research dispositions)
BLOCK_BY_FAMILY = {
    "relative": "needs simultaneous two-leg or basket execution with short legs; the engine trades one instrument per bot",
    "event": "needs a licensed event feed (earnings surprises, consensus, filings, auction or halt data) with receipt times",
    "orderflow": "needs a sequenced L2/L3 order-book feed; the free venues give periodic snapshots only",
    "arbitrage": "needs prefunded inventory on several venues and synchronized multi-leg execution",
    "making": "needs queue/latency modelling and two-sided quoting, which the paper engine does not simulate",
    "patterns": "needs an objective pattern grammar that is not yet specified",
    "launch_discovery": "needs launchpad creation events, bonding-curve state and decoded swaps (on-chain history not connected)",
    "graduation": "needs launchpad migration events and pool state history (on-chain, not connected)",
    "quote_liquidity": "needs executable DEX pool depth and quote history (not connected)",
    "holder_flow": "needs point-in-time holder balances and wallet clustering (on-chain, not connected)",
    "wallet_follow": "needs labelled wallet histories (on-chain, not connected)",
    "flow_momentum": "needs deduplicated swap-level flow history; exchange aggressor flow is captured live only",
    "flow_reversal": "needs swap-level flow and trade-size cohorts over time (not connected)",
    "social_events": "needs a social / announcement feed with receipt times (not connected)",
    "narrative_rotation": "needs point-in-time narrative membership and flow data beyond the six exchange-listed memecoins",
    "crosspool": "needs synchronized multi-pool DEX quotes (not connected)",
    "cex_events": "needs exchange listing, deposit and withdrawal status history (not connected)",
    "perpetual_flow": "needs open-interest, funding and liquidation history at intraday resolution (not connected)",
    "market_regime": "needs chain activity, network cost or depth data beyond exchange price bars",
    "intraday_structure": "needs transaction-derived bars or launch/migration anchors from on-chain data",
    "supply_events": "needs unlock / supply event feeds (not connected)",
    "recovery_events": "needs operational status feeds (transfers, routers, pools) with timestamps",
    "funding_basis": "needs funding/basis history and hedged derivative legs (not connected)",
    "relative_value_meme": "needs hedgeable short legs or float estimates for memecoins",
    "liquidity_provision": "needs AMM liquidity-position simulation (fees, ranges, impermanent loss)",
    "onchain_microstructure": "needs block-level reserve and transaction data (on-chain, not connected)",
    "equity_microevents": "needs primary filings / corporate-event data with receipt times (licensed feed)",
    "equity_breadth": "needs point-in-time constituent breadth or auction imbalance data (not free)",
}
FAMILY_MAP = {  # pack family -> this library's family
    "trend": "trend_following", "breakout": "volatility", "reversion": "mean_reversion", "relative": "cross_asset",
    "event": "scheduled_events", "orderflow": "order_flow", "arbitrage": "market_making_arbitrage",
    "making": "market_making_arbitrage", "ml": "machine_learning", "patterns": "market_structure",
    "equity_microevents": "equity_events", "equity_breadth": "equity_breadth",
}


def family_of(rec) -> str:
    return "memecoin" if rec["memecoin_specific"] else FAMILY_MAP.get(rec["family"], rec["family"])


# ---------------------------------------------------------------- load and validate
def _load(name):
    with open(os.path.join(PACK, name), encoding="utf-8") as fh:
        return json.load(fh)


CAT = _load("strategy_catalog.json")
REG = _load("source_registry.json")
SCHEMA = _load("strategy_catalog.schema.json")
COUNTS = _load("catalogue_counts.json")
MANIFEST = _load("manifest.json")
RECORDS = {r["id"]: r for r in CAT["strategies"]}


def validate() -> list:
    problems = []
    for f in MANIFEST["files"]:
        p = os.path.join(PACK, f["filename"])
        if f["filename"] in DERIVED:
            continue
        if not os.path.exists(p):
            problems.append(f"missing pack file {f['filename']}")
            continue
        with open(p, "rb") as fh:
            if hashlib.sha256(fh.read()).hexdigest() != f["sha256"]:
                problems.append(f"hash mismatch {f['filename']}")
    item = SCHEMA["properties"]["strategies"]["items"]
    req, props = item["required"], item["properties"]
    fams = set(props["family"]["enum"])
    src_ids = {s["id"] for s in REG["sources"]}
    ids = [r["id"] for r in CAT["strategies"]]
    if len(ids) != len(set(ids)):
        problems.append("duplicate strategy ids")
    names = [r["name"] for r in CAT["strategies"]]
    if len(names) != len(set(names)):
        problems.append("duplicate strategy names")
    for r in CAT["strategies"]:
        missing = [k for k in req if k not in r]
        extra = [k for k in r if k not in props]
        if missing or extra:
            problems.append(f"{r.get('id')}: missing {missing} extra {extra}")
        if not re.fullmatch(props["id"]["pattern"].strip("^$"), r["id"]):
            problems.append(f"{r['id']}: bad id")
        if r["family"] not in fams or r["family"] not in CAT["families"]:
            problems.append(f"{r['id']}: unknown family {r['family']}")
        if r["status"] != props["status"]["const"]:
            problems.append(f"{r['id']}: status {r['status']}")
        if r["expected_win_rate"] is not None or r["expected_return"] is not None:
            problems.append(f"{r['id']}: performance field is not null")
        for s in r["source_ids"]:
            if s not in src_ids:
                problems.append(f"{r['id']}: unknown source {s}")
        if r["concept_parent_id"] and r["concept_parent_id"] not in RECORDS:
            problems.append(f"{r['id']}: unknown parent {r['concept_parent_id']}")
    hyp = sum(1 for r in CAT["strategies"] if r["counts_as_trading_hypothesis"])
    meme = sum(1 for r in CAT["strategies"] if r["memecoin_specific"])
    for k, v in (("records", len(ids)), ("trading_hypotheses", hyp), ("supporting_records", len(ids) - hyp),
                 ("memecoin_specific_records", meme), ("sources", len(src_ids)), ("families", len(CAT["families"]))):
        if COUNTS.get(k) != v:
            problems.append(f"count {k}: pack says {COUNTS.get(k)}, found {v}")
    return problems


def disposition(pid: str):
    r = RECORDS[pid]
    if not r["counts_as_trading_hypothesis"]:
        return ("supporting", BRAIN.get(pid, "model framework / execution method / risk filter; not a trading hypothesis"))
    if pid in NEW:
        return ("new", NEW[pid])
    if pid in SAME:
        return ("same", SAME[pid][0])
    return ("research", BLOCK_BY_FAMILY.get(r["family"], "required data is not connected"))


# ---------------------------------------------------------------- sources and catalog entries
for s in REG["sources"]:
    sid = "PK-" + s["id"]
    sources.S[sid] = {"id": sid, "title": s["title"], "authors": "", "year": None, "venue": s["source_type"],
                      "url": s["url"], "type": s["source_type"], "supports": s["supported_scope"],
                      "accessed": s["reviewed_utc_date"], "verification": f"knowledge pack review depth: {s['access_depth']}",
                      "notes": "Imported from the research knowledge pack (v2.0.0); " + s["refresh_policy"]}


def pack_evidence(pid, relation="context"):
    r = RECORDS[pid]
    return [("PK-" + s, relation, "pack " + pid + ": " + r["source_relationship"][:160]) for s in r["source_ids"]]


def _spec(r) -> str:
    return (f"Setup: {r['setup']} Entry: {r['entry_rule']} Exit: {r['exit_and_invalidation']} "
            f"Parameters to pre-register: {', '.join(r['parameters_to_pre_register'])}.")


def register_research_records():
    """Catalog entries for the distinct pack hypotheses that cannot be tested here (blocked)."""
    for pid, r in RECORDS.items():
        kind, why = disposition(pid)
        if kind != "research":
            continue
        key = "pack_" + pid.lower() + "_" + re.sub(r"[^a-z0-9]+", "_", r["name"].lower()).strip("_")[:40]
        st(key, r["name"], family_of(r), r["family"].replace("_", " "),
           mech=r["setup"], logic=r["record_type"].replace("_", " "), hyp=r["entry_rule"].split(" Evaluate only")[0],
           markets=("crypto",) if (r["memecoin_specific"] or all(m.startswith("crypto") for m in r["markets"])) else
           (("stock",) if all(m == "stocks" for m in r["markets"]) else ("stock", "crypto")),
           data=tuple(x.strip() for x in r["data_requirements"].split(";")[:4]),
           blocked=why, spec=_spec(r), ev=pack_evidence(pid), research="hypothesis",
           fail=r["failure_modes"], anchor=r["candidate_regime"],
           notes=f"Knowledge pack {pid} ({r['evidence_grade']}; {r['eligibility_profile']})."
                 + (f" Concept parent: {r['concept_parent_id']}." if r["concept_parent_id"] else ""))


def summary() -> dict:
    out = {"same": [], "new": [], "research": [], "supporting": []}
    for pid in RECORDS:
        kind, what = disposition(pid)
        out[kind].append((pid, what))
    return out
