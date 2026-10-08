"""The 100 logical agents (section 169), in ten groups. Each reads only what the context gives it: completed bars and
features, the regime, data-quality status, and read-only snapshots of risk, execution, research and broker state.

Directional agents (votes=True) feed the ensemble. Everyone else reports metrics and flags for the Live Intelligence
page; data and risk agents may set veto=True, which blocks new entries for that decision (the deterministic risk
service still makes its own decision; agents can never loosen it).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

import numpy as np

from tradingai.agents.base import AGENTS, agent
from tradingai.features import indicators as I
from tradingai.features.registry import FeatureFrame


@dataclass
class AgentContext:
    instrument: Any
    market: str
    tf: str
    bars: Any
    ff: FeatureFrame
    now_ms: int
    htf: Optional[FeatureFrame] = None
    regime: Any = None
    quality: dict = field(default_factory=dict)
    extra_data: dict = field(default_factory=dict)
    risk: dict = field(default_factory=dict)
    execution: dict = field(default_factory=dict)
    research: dict = field(default_factory=dict)
    strategy: dict = field(default_factory=dict)
    broker: dict = field(default_factory=dict)
    ensemble: dict = field(default_factory=dict)
    library: dict = field(default_factory=dict)

    @property
    def data_ts(self) -> Optional[int]:
        return int(self.bars.available_at[-1]) if len(self.bars) else None

    @property
    def step_ms(self) -> int:
        return int(self.bars.step)


def last(x: np.ndarray, k: int = 1) -> float:
    return float(x[-k]) if len(x) >= k else float("nan")


def ok(v: float) -> bool:
    return v == v and abs(v) != float("inf")


def sgn(x: float, dead: float = 0.0) -> int:
    return 0 if not ok(x) or abs(x) <= dead else (1 if x > 0 else -1)


def nodata(msg: str = "not enough bars yet") -> dict:
    return {"status": "abstain", "message": msg}


# ============================================================================ data agents (10)

@agent("D01", "Feed health", "data", "data_quality", horizon_bars=1)
def feed_health(c: AgentContext):
    q = c.quality.get("quality", {})
    stale = bool(q.get("stale")) or not c.quality.get("fresh", True)
    return {"evidence": {"last_bar_age_s": q.get("last_bar_age_s"), "fresh": c.quality.get("fresh"),
                         "error": c.quality.get("error")}, "veto": stale, "flags": ["STALE_DATA"] if stale else [],
            "message": "data is stale: no new entries" if stale else "data fresh"}


@agent("D02", "Missing bars", "data", "data_quality")
def missing_bars(c):
    q = c.quality.get("quality", {})
    g = int(q.get("gaps") or 0)
    return {"evidence": {"gaps": g, "max_gap_bars": q.get("max_gap_bars")}, "flags": ["GAPS"] if g else [],
            "message": f"{g} gap(s)" if g else "no gaps"}


@agent("D03", "Bad ticks", "data", "data_quality")
def bad_ticks(c):
    n = int(c.quality.get("quality", {}).get("suspected_bad_ticks") or 0)
    recent = n > 0 and c.quality.get("quality", {}).get("score", 100) < 100
    return {"evidence": {"suspected": n}, "flags": ["BAD_TICK"] if n else [], "veto": False,
            "message": f"{n} suspected bad tick(s), kept and flagged" if n else "none found", "status": "ok"
            if not recent or n else "ok"}


@agent("D04", "Timestamp validation", "data", "data_quality")
def timestamps(c):
    ts = c.bars.ts
    mono = bool(np.all(np.diff(ts) > 0)) if len(ts) > 1 else True
    future = bool(len(ts) and c.bars.available_at[-1] > c.now_ms + 5_000)
    aligned = bool(np.all(ts % c.step_ms == 0)) if c.tf != "1d" else True
    bad = not mono or future
    return {"evidence": {"monotonic": mono, "future_bar": future, "aligned_to_tf": aligned}, "veto": bad,
            "flags": ["CLOCK_ERROR"] if future else (["TS_ORDER"] if not mono else []),
            "message": "bar times consistent" if not bad else "bar times inconsistent: entries blocked"}


@agent("D05", "Corporate actions", "data", "data_quality", markets=("stock", "etf", "index"))
def corporate_actions(c):
    gp = c.ff.get("gap")
    big = int(np.sum(np.abs(np.nan_to_num(gp)) > 0.2)) if gp is not None else 0
    return {"evidence": {"adjusted_series": c.quality.get("note", ""), "gaps_over_20pct": big},
            "flags": ["UNEXPLAINED_GAP"] if big else [],
            "message": "provider-adjusted for splits and dividends; no unexplained 20% gap" if not big else
            f"{big} gap(s) over 20%: check for an unadjusted corporate action"}


@agent("D06", "Futures roll", "data", "data_quality", markets=("future",))
def futures_roll(c):
    from tradingai.market.calendars import in_roll_window
    d = datetime.fromtimestamp(c.now_ms / 1000, tz=timezone.utc).date()
    eq = "quarterly_roll_rule" in getattr(c.instrument, "tags", ())
    inside = eq and in_roll_window(d)
    return {"evidence": {"roll_rule_known": eq, "in_roll_window": inside}, "veto": inside or not eq,
            "flags": (["ROLL_WINDOW"] if inside else []) + ([] if eq else ["NO_CONTRACT_DATA"]),
            "message": "inside the roll window: stay flat" if inside else (
                "roll calendar known" if eq else "no contract-level data: research only")}


@agent("D07", "Market calendar", "data", "calendar_session", horizon_bars=1)
def calendar_agent(c):
    from tradingai.market.calendars import session
    s = session(c.instrument.calendar or "CRYPTO", c.now_ms)
    return {"evidence": {k: s.get(k) for k in ("open", "session", "trading_date", "minutes_to_close", "note")},
            "veto": not s["open"], "flags": [] if s["open"] else ["MARKET_CLOSED"],
            "message": f"market {s['session']}" + (f" ({s['note']})" if s.get("note") else "")}


@agent("D08", "Symbol mapping", "data", "data_quality")
def symbol_mapping(c):
    return {"evidence": {"instrument_id": c.instrument.instrument_id, "data_provider": c.quality.get("provider"),
                         "provider_symbol": c.quality.get("symbol"), "market_type": c.instrument.market_type.value},
            "message": f"{c.instrument.instrument_id} <- {c.quality.get('provider')}:{c.quality.get('symbol')}"}


@agent("D09", "Data liquidity", "data", "data_quality")
def data_liquidity(c):
    share = float(c.quality.get("quality", {}).get("zero_volume_share") or 0.0)
    return {"evidence": {"zero_volume_share": share}, "flags": ["NO_VOLUME_DATA"] if share > 0.5 else [],
            "message": "volume reported" if share <= 0.5 else "no volume data (FX mid or index): volume features off"}


@agent("D10", "Data provenance", "data", "data_quality")
def provenance(c):
    sim = bool(c.quality.get("simulated"))
    return {"evidence": {"provider": c.quality.get("provider"), "simulated": sim, "note": c.quality.get("note")},
            "flags": ["SIMULATED_DATA"] if sim else [],
            "message": "DEMO / SIMULATED prices" if sim else f"real data from {c.quality.get('provider')}"}


# ============================================================================ market agents (10)

def _regime_vote(c):
    r = c.regime
    if r is None:
        return nodata("no regime yet")
    d = {"trend_up": 1, "trend_down": -1}.get(r.trend, 0)
    return {"direction": d, "score": 0.6 * d, "evidence": {"trend": r.trend, "volatility": r.volatility,
                                                           "character": r.character},
            "message": r.label}


for aid, name, mk in (("M01", "Stock regime", ("stock", "etf")), ("M02", "Crypto regime", ("crypto",)),
                      ("M03", "FX regime", ("fx",)), ("M04", "Futures regime", ("future",)),
                      ("M05", "Index regime", ("index",))):
    agent(aid, name, "market", "regime", votes=True, horizon_bars=5, markets=mk)(_regime_vote)


@agent("M06", "Volatility regime", "market", "volatility")
def vol_regime(c):
    r = c.ff.get("vol_pctrank_20")
    v = last(r) if r is not None else float("nan")
    extreme = ok(v) and v > 95
    return {"evidence": {"vol_percentile": v, "realized_vol_20": last(c.ff["rvol_20"])},
            "flags": ["EXTREME_VOL"] if extreme else [], "message": f"volatility percentile {v:.0f}" if ok(v) else
            "warming up"}


@agent("M07", "Correlation", "market", "cross_asset", requires=("benchmark_close",))
def correlation(c):
    b = c.extra_data["benchmark_close"]
    n = min(len(b), len(c.ff.c))
    r = I.rolling_corr(I.logret(c.ff.c[-n:]), I.logret(b[-n:]), min(60, n - 2))
    return {"evidence": {"corr_60": last(r)}, "message": f"60-bar correlation with the benchmark {last(r):+.2f}"}


@agent("M08", "Breadth", "market", "breadth", requires=("breadth",), markets=("stock", "etf", "index"))
def breadth(c):
    return {}


@agent("M09", "Session", "market", "calendar_session")
def session_agent(c):
    k = c.ff.get("bar_in_session")
    n = last(k) if k is not None else float("nan")
    return {"evidence": {"bar_in_session": n}, "flags": ["SESSION_OPEN_BARS"] if ok(n) and n < 2 and
            c.market in ("stock", "etf", "future") else [], "message": f"bar {n:.0f} of the session" if ok(n) else ""}


@agent("M10", "Macro calendar", "market", "macro", requires=("economic_calendar",))
def macro(c):
    return {}


# ============================================================================ technical agents (10)

@agent("T01", "Trend", "technical", "price_trend", votes=True, horizon_bars=5)
def trend(c):
    e20, e50, e200 = last(c.ff["ema_20"]), last(c.ff["ema_50"]), last(c.ff["ema_200"])
    px = last(c.ff.c)
    if not all(map(ok, (e20, e50, e200))):
        return nodata()
    d = 1 if px > e20 > e50 > e200 else -1 if px < e20 < e50 < e200 else 0
    return {"direction": d, "score": 0.8 * d, "evidence": {"close": px, "ema20": e20, "ema50": e50, "ema200": e200},
            "message": {1: "averages stacked up", -1: "averages stacked down", 0: "averages mixed"}[d]}


@agent("T02", "Momentum", "technical", "price_momentum", votes=True)
def momentum(c):
    r, roc = last(c.ff["rsi_14"]), last(c.ff["roc_10"])
    if not ok(r):
        return nodata()
    d = 1 if r > 55 and roc > 0 else -1 if r < 45 and roc < 0 else 0
    return {"direction": d, "score": (r - 50) / 50, "evidence": {"rsi_14": r, "roc_10": roc},
            "message": f"RSI {r:.0f}, 10-bar change {roc:+.2f}%"}


@agent("T03", "Mean reversion", "technical", "price_reversion", votes=True, horizon_bars=2)
def mean_reversion(c):
    z, r2 = last(c.ff["zscore_20"]), last(c.ff["rsi_2"])
    if not ok(z):
        return nodata()
    d = 1 if z < -2 and r2 < 10 else -1 if z > 2 and r2 > 90 else 0
    return {"direction": d, "score": float(np.clip(-z / 3, -1, 1)) if d else 0.0, "evidence": {"z20": z, "rsi_2": r2},
            "message": f"z-score {z:+.2f}"}


@agent("T04", "Breakout", "technical", "price_trend", votes=True, horizon_bars=3)
def breakout(c):
    b = last(c.ff["donchian_break_20"])
    rv = c.ff.get("relvol_20")
    v = last(rv) if rv is not None else float("nan")
    d = int(b) if ok(b) else 0
    return {"direction": d, "score": 0.7 * d, "evidence": {"donchian_break_20": b, "relvol_20": v},
            "message": "20-bar breakout" if d > 0 else "20-bar breakdown" if d < 0 else "inside the range"}


@agent("T05", "VWAP", "technical", "volume", votes=True, markets=("crypto", "stock", "etf", "future"))
def vwap(c):
    d_ = last(c.ff["vwap_dist_atr"])
    if not ok(d_):
        return nodata()
    d = sgn(d_, 0.25)
    return {"direction": d, "score": float(np.clip(d_ / 3, -1, 1)), "evidence": {"vwap_dist_atr": d_},
            "message": f"{d_:+.2f} ATR from session VWAP"}


@agent("T06", "Volume flow", "technical", "volume", votes=True, markets=("crypto", "stock", "etf", "future"))
def volume_flow(c):
    cm, ob = last(c.ff["cmf_20"]), last(c.ff["obv_slope_20"])
    if not ok(cm):
        return nodata()
    d = 1 if cm > 0.05 and ob > 0 else -1 if cm < -0.05 and ob < 0 else 0
    return {"direction": d, "score": float(np.clip(cm * 5, -1, 1)), "evidence": {"cmf_20": cm, "obv_slope_20": ob},
            "message": f"money flow {cm:+.2f}"}


@agent("T07", "Market profile", "technical", "microstructure", requires=("trades",))
def market_profile(c):
    return {}


@agent("T08", "Order flow", "technical", "microstructure", requires=("trades", "order_book"))
def order_flow(c):
    return {}


@agent("T09", "Volatility breakout", "technical", "volatility", votes=True)
def vol_breakout(c):
    sq, pb = last(c.ff["bb_width_pctrank_20"]), last(c.ff["bb_pctb_20"])
    if not ok(sq):
        return nodata()
    d = (1 if pb > 1 else -1 if pb < 0 else 0) if sq < 20 else 0
    return {"direction": d, "score": 0.6 * d, "evidence": {"bandwidth_pctrank": sq, "pct_b": pb},
            "message": "squeeze breaking out" if d else ("squeeze building" if sq < 20 else "no squeeze")}


@agent("T10", "Statistical arbitrage", "technical", "cross_asset", votes=True, requires=("pair_close",))
def stat_arb(c):
    o = c.extra_data["pair_close"]
    n = min(len(o), len(c.ff.c))
    s = I.zscore(np.log(c.ff.c[-n:] / o[-n:]), min(100, n - 1))
    z = last(s)
    d = 1 if z < -2 else -1 if z > 2 else 0
    return {"direction": d, "score": float(np.clip(-z / 3, -1, 1)) if d else 0.0, "evidence": {"spread_z": z},
            "message": f"pair spread z {z:+.2f}"}


# ============================================================================ crypto agents (10)

for aid, name, req in (("C01", "Funding", ("funding",)), ("C02", "Basis", ("mark_price", "index_price")),
                       ("C03", "Open interest", ("open_interest",)), ("C04", "Liquidations", ("liquidations",)),
                       ("C07", "On-chain validator", ("onchain",))):
    agent(aid, name, "crypto", "derivatives", requires=req, markets=("crypto",))(lambda c: {})


@agent("C05", "Exchange divergence", "crypto", "cross_asset", requires=("other_venue_close",), markets=("crypto",))
def exchange_divergence(c):
    o = c.extra_data["other_venue_close"]
    prem = (last(c.ff.c) / o[-1] - 1) * 10_000 if len(o) else float("nan")
    return {"evidence": {"premium_bps": prem}, "flags": ["VENUE_DIVERGENCE"] if ok(prem) and abs(prem) > 50 else [],
            "message": f"{prem:+.1f} bp versus the other venue" if ok(prem) else "no other venue price"}


@agent("C06", "Weekend regime", "crypto", "calendar_session", markets=("crypto",))
def weekend(c):
    wd = datetime.fromtimestamp(c.now_ms / 1000, tz=timezone.utc).weekday()
    return {"evidence": {"weekday_utc": wd}, "flags": ["WEEKEND"] if wd >= 5 else [],
            "message": "weekend: thinner liquidity" if wd >= 5 else "weekday"}


@agent("C08", "Crypto liquidity risk", "crypto", "volume", markets=("crypto",))
def crypto_liquidity(c):
    rv = last(c.ff["relvol_20"])
    thin = ok(rv) and rv < 0.3
    return {"evidence": {"relvol_20": rv}, "flags": ["THIN_LIQUIDITY"] if thin else [],
            "message": f"relative volume {rv:.2f}" if ok(rv) else "warming up"}


@agent("C09", "Token risk", "crypto", "data_quality", markets=("crypto",))
def token_risk(c):
    base = getattr(c.instrument, "base_asset", None) or c.instrument.symbol
    major = base in ("BTC", "ETH", "SOL", "DEMO-TREND", "DEMO-RANGE", "DEMO-VOLATILE")
    return {"evidence": {"base_asset": base, "major": major}, "flags": [] if major else ["SMALL_CAP_TOKEN"],
            "veto": not major, "message": "major coin" if major else "not a major coin: contract and liquidity "
            "checks need on-chain data (REQUIRES CONNECTION)"}


@agent("C10", "Crypto execution", "crypto", "execution", markets=("crypto",))
def crypto_exec(c):
    cost = c.execution.get("estimated_cost_bps")
    return {"evidence": {"estimated_round_trip_bps": cost}, "message": f"estimated round trip {cost} bp"
            if cost is not None else "no estimate yet"}


# ============================================================================ futures agents (10)

@agent("F01", "Contract", "futures", "data_quality", markets=("future",))
def contract(c):
    i = c.instrument
    return {"evidence": {"root": i.root, "multiplier": str(i.multiplier), "tick_value": str(i.tick_value),
                         "verified_with_broker": i.verified_with_broker, "spec_version": i.spec_version},
            "flags": [] if i.verified_with_broker else ["SPEC_NOT_BROKER_VERIFIED"],
            "message": f"{i.root}: {i.multiplier} per point, tick value {i.tick_value} {i.currency}"}


@agent("F02", "Roll", "futures", "calendar_session", markets=("future",))
def roll(c):
    from tradingai.market.calendars import equity_index_front
    d = datetime.fromtimestamp(c.now_ms / 1000, tz=timezone.utc).date()
    if "quarterly_roll_rule" not in c.instrument.tags:
        return {"status": "abstain", "message": "no roll calendar for this contract"}
    m, exp, rd = equity_index_front(d)
    return {"evidence": {"front": m, "expiry": exp.isoformat(), "roll_date": rd.isoformat(),
                         "days_to_roll": (rd - d).days}, "message": f"front {m}, roll {rd.isoformat()}"}


@agent("F03", "Expiry", "futures", "calendar_session", markets=("future",))
def expiry(c):
    from tradingai.market.calendars import equity_index_front
    if "quarterly_roll_rule" not in c.instrument.tags:
        return {"status": "abstain", "message": "expiry unknown without contract data"}
    d = datetime.fromtimestamp(c.now_ms / 1000, tz=timezone.utc).date()
    _, exp, _ = equity_index_front(d)
    return {"evidence": {"days_to_expiry": (exp - d).days}, "message": f"{(exp - d).days} days to expiry"}


@agent("F04", "Margin", "futures", "risk", requires=("broker_margin",), markets=("future",))
def margin(c):
    return {}


@agent("F05", "Futures basis", "futures", "cross_asset", requires=("index_close",), markets=("future",))
def futures_basis(c):
    ix = c.extra_data["index_close"]
    b = (last(c.ff.c) / ix[-1] - 1) * 100 if len(ix) else float("nan")
    return {"evidence": {"basis_pct": b}, "message": f"futures vs index {b:+.2f}%"}


@agent("F06", "Calendar spread", "futures", "derivatives", requires=("contract_data",), markets=("future",))
def calendar_spread(c):
    return {}


@agent("F07", "Delivery safety", "futures", "risk", markets=("future",))
def delivery(c):
    from tradingai.market.instruments import Settlement
    phys = c.instrument.settlement is Settlement.PHYSICAL
    return {"evidence": {"settlement": c.instrument.settlement.value}, "veto": phys and not c.instrument.first_notice,
            "flags": ["PHYSICAL_DELIVERY"] if phys else [],
            "message": "physically settled: never held into delivery" if phys else "cash settled"}


@agent("F08", "Futures liquidity", "futures", "volume", markets=("future",))
def fut_liquidity(c):
    v = last(c.ff.v)
    return {"evidence": {"last_volume": v}, "message": f"last bar volume {v:,.0f}" if ok(v) else ""}


@agent("F09", "Session reset", "futures", "calendar_session", markets=("future",))
def session_reset(c):
    from tradingai.market.calendars import session
    s = session("CME", c.now_ms)
    maint = s["session"] == "maintenance"
    return {"evidence": {"session": s["session"]}, "veto": maint, "flags": ["MAINTENANCE"] if maint else [],
            "message": f"CME {s['session']}"}


@agent("F10", "Settlement", "futures", "data_quality", markets=("future",))
def settlement(c):
    return {"evidence": {"continuous_series": "continuous_provider_series" in c.instrument.tags},
            "message": "provider continuous series: P&L across rolls is not real; paper trading stays flat in the "
                       "roll window"}


# ============================================================================ forex agents (8)

@agent("X01", "FX session", "forex", "calendar_session", markets=("fx",))
def fx_session(c):
    from tradingai.market.calendars import session
    s = session("FX", c.now_ms)
    return {"evidence": {"session": s["session"], "rollover_window": s.get("rollover_window")},
            "veto": not s["open"], "message": f"FX {s['session']}"}


@agent("X02", "FX spread", "forex", "execution", markets=("fx",))
def fx_spread(c):
    return {"evidence": {"quotes": "reference mid only"}, "flags": ["NO_DEALER_QUOTES"],
            "message": "no dealer bid/ask: costs use a modelled spread (REQUIRES CONNECTION for real quotes)"}


@agent("X03", "Rollover", "forex", "calendar_session", markets=("fx",))
def rollover(c):
    from tradingai.market.calendars import session
    s = session("FX", c.now_ms)
    near = bool(s.get("rollover_window"))
    return {"evidence": {"near_rollover": near}, "veto": near, "flags": ["ROLLOVER"] if near else [],
            "message": "within 15 min of the 17:00 New York rollover: spreads widen" if near else "away from rollover"}


@agent("X04", "Economic event", "forex", "macro", requires=("economic_calendar",), markets=("fx",))
def econ_event(c):
    return {}


@agent("X05", "Currency strength", "forex", "cross_asset", votes=True, requires=("fx_basket",), markets=("fx",))
def currency_strength(c):
    basket: dict = c.extra_data["fx_basket"]
    usd = []
    for pair, close in basket.items():
        if len(close) > 21:
            r = close[-1] / close[-21] - 1
            usd.append(-r if pair.startswith(("EUR", "GBP", "AUD")) else r)
    if not usd:
        return nodata("basket empty")
    s = float(np.mean(usd))
    sym = c.instrument.symbol
    d = -sgn(s, 0.002) if sym.startswith(("EUR", "GBP", "AUD")) else sgn(s, 0.002)
    return {"direction": d, "score": float(np.clip(d * abs(s) * 50, -1, 1)),
            "evidence": {"usd_strength_20": s, "pairs": len(usd)}, "message": f"USD 20-bar strength {s:+.3%}"}


@agent("X06", "Rate differential", "forex", "macro", requires=("rates",), markets=("fx",))
def rate_diff(c):
    return {}


@agent("X07", "FX execution", "forex", "execution", markets=("fx",))
def fx_exec(c):
    return {"evidence": {"min_size_units": str(c.instrument.min_quantity)},
            "message": f"sizes in {c.instrument.min_quantity:,} unit steps"}


@agent("X08", "Dealer divergence", "forex", "execution", requires=("dealer_quotes",), markets=("fx",))
def dealer_div(c):
    return {}


# ============================================================================ research agents (10)

def _research(key: str, fmt):
    def fn(c):
        r = c.research or {}
        if not r:
            return {"status": "abstain", "message": "no research run for this strategy and market yet"}
        v = r.get(key)
        if v is None:
            return {"status": "abstain", "message": f"{key} not computed in the latest run"}
        return {"evidence": {key: v}, "message": fmt(v), "flags": r.get("flags_" + key, [])}
    return fn


agent("R01", "Strategy generator", "research", "research")(lambda c: {
    "evidence": c.library, "message": f"{c.library.get('runnable', 0)} runnable templates "
    f"({c.library.get('distinct_entry_filter_templates', 0)} distinct entry/filter designs)"})
agent("R02", "Backtest", "research", "research")(_research("oos_sharpe", lambda v: f"out-of-sample Sharpe {v:.2f}"))
agent("R03", "Walk-forward", "research", "research")(_research("wf_oos_sharpe", lambda v: f"walk-forward OOS Sharpe {v:.2f}"))
agent("R04", "Monte Carlo", "research", "research")(_research("mc_p95_drawdown", lambda v: f"95th pct drawdown {v:.1%}"))
agent("R05", "Overfit detection", "research", "research")(_research("dsr", lambda v: f"deflated Sharpe {v:.2f}"))
agent("R06", "Parameter stability", "research", "research")(_research("param_stability",
                                                                      lambda v: f"neighbour stability {v:.2f}"))
agent("R07", "Regime robustness", "research", "research")(_research("regimes_positive",
                                                                    lambda v: f"positive in {v} regime(s)"))
agent("R08", "Cost stress", "research", "research")(_research("sharpe_2x_costs", lambda v: f"Sharpe at 2x costs {v:.2f}"))
agent("R09", "Capacity", "research", "research")(_research("capacity_usd", lambda v: f"estimated capacity {v:,.0f}"))
agent("R10", "Experiment auditor", "research", "research")(_research("trials", lambda v: f"{v} trials logged in this family"))


# ============================================================================ risk agents (12)

def _risk(key: str, label: str, flag: str):
    def fn(c):
        r = c.risk or {}
        u = (r.get("usage") or {}).get(key)
        if u is None:
            return {"status": "abstain", "message": "risk state not available"}
        near = u >= 0.8
        return {"evidence": {"usage": u, "limit": (r.get("limits") or {}).get(key)}, "veto": u >= 1.0,
                "flags": [flag] if near else [], "message": f"{label}: {u:.0%} of limit used"}
    return fn


for aid, key, label, flag in (("K01", "position", "Position size", "POSITION_NEAR_LIMIT"),
                              ("K02", "gross_exposure", "Portfolio exposure", "EXPOSURE_NEAR_LIMIT"),
                              ("K03", "correlated_exposure", "Correlated exposure", "CORRELATION_NEAR_LIMIT"),
                              ("K04", "leverage", "Leverage", "LEVERAGE_NEAR_LIMIT"),
                              ("K05", "drawdown", "Drawdown", "DRAWDOWN_NEAR_LIMIT"),
                              ("K06", "loss_streak", "Loss streak", "LOSS_STREAK"),
                              ("K09", "concentration", "Concentration", "CONCENTRATED"),
                              ("K13", "daily_loss", "Daily loss", "DAILY_LOSS_NEAR_LIMIT")):
    agent(aid, f"{label} risk", "risk", "risk")(_risk(key, label, flag))


@agent("K07", "Volatility risk", "risk", "risk")
def vol_risk(c):
    v = last(c.ff["natr_14"])
    return {"evidence": {"natr_14": v}, "flags": ["HIGH_VOL"] if ok(v) and v > 5 else [],
            "message": f"ATR is {v:.2f}% of price" if ok(v) else ""}


@agent("K08", "Liquidity risk", "risk", "risk")
def liq_risk(c):
    lim = (c.risk.get("limits") or {}).get("max_participation")
    return {"evidence": {"max_participation": lim}, "message": f"orders capped at {lim:.0%} of bar volume"
            if lim else "participation limit not set"}


@agent("K10", "Event risk", "risk", "risk", requires=("economic_calendar",))
def event_risk(c):
    return {}


@agent("K11", "Broker risk", "risk", "risk")
def broker_risk(c):
    b = c.broker or {}
    bad = b.get("status") not in (None, "connected", "simulated")
    return {"evidence": {"broker": b.get("broker"), "status": b.get("status"), "environment": b.get("environment")},
            "veto": bad, "flags": ["BROKER_DOWN"] if bad else [], "message": f"{b.get('broker')}: {b.get('status')}"}


@agent("K12", "Kill switch", "risk", "risk", horizon_bars=1)
def kill_switch(c):
    on = bool(c.risk.get("kill_switch"))
    locked = bool(c.risk.get("trading_locked"))
    return {"evidence": {"kill_switch": on, "trading_locked": locked}, "veto": on or locked,
            "flags": (["KILL_SWITCH"] if on else []) + (["TRADING_LOCKED"] if locked else []),
            "message": "STOP ALL TRADING is engaged" if on else ("daily loss lock" if locked else "armed (not engaged)")}


# ============================================================================ execution agents (10)

def _exec(key: str, fmt):
    def fn(c):
        v = (c.execution or {}).get(key)
        if v is None:
            return {"status": "abstain", "message": "no data yet"}
        return {"evidence": {key: v}, "message": fmt(v)}
    return fn


agent("E01", "Order router", "execution", "execution")(_exec("route", lambda v: f"orders go to {v}"))
agent("E02", "Fill monitor", "execution", "execution")(_exec("open_orders", lambda v: f"{v} open order(s)"))
agent("E03", "Spread", "execution", "execution")(_exec("spread_bps", lambda v: f"modelled spread {v} bp"))
agent("E04", "Slippage", "execution", "execution")(_exec("slippage_bps", lambda v: f"modelled slippage {v} bp"))
agent("E05", "Limit order", "execution", "execution")(_exec("limit_offset_bps", lambda v: f"limit {v} bp inside"))
agent("E06", "Market order", "execution", "execution")(_exec("market_ok", lambda v: "market orders allowed" if v else
                                                             "use limit orders"))
agent("E07", "Execution quality", "execution", "execution")(_exec("avg_shortfall_bps",
                                                                  lambda v: f"average shortfall {v} bp"))
agent("E08", "Partial fills", "execution", "execution")(_exec("partial_fills", lambda v: f"{v} partial fill(s) today"))
agent("E09", "Reconciliation", "execution", "execution")(_exec("reconciliation", lambda v: f"reconciliation: {v}"))
agent("E10", "Duplicate-order guard", "execution", "execution")(_exec("duplicates_blocked",
                                                                      lambda v: f"{v} duplicate(s) blocked"))


# ============================================================================ meta agents (10)

def _meta(key: str, fmt):
    def fn(c):
        v = (c.ensemble or {}).get(key)
        if v is None:
            return {"status": "abstain", "message": "computed after the ensemble"}
        return {"evidence": {key: v}, "message": fmt(v)}
    return fn


agent("Z01", "Ensemble", "meta", "meta")(_meta("score", lambda v: f"ensemble score {v:+.2f} (not a probability)"))
agent("Z02", "Conflict resolution", "meta", "meta")(_meta("conflicts", lambda v: f"{len(v)} conflict(s)"))
agent("Z03", "Strategy ranking", "meta", "meta")(lambda c: {"status": "abstain", "message": "ranking needs research runs"}
                                                 if not c.research else {"evidence": {"rank_basis": "OOS score"}})
agent("Z04", "Drift detection", "meta", "meta")(lambda c: _drift(c))
agent("Z05", "Anomaly detection", "meta", "meta")(lambda c: _anomaly(c))
agent("Z06", "Challenger manager", "meta", "meta")(lambda c: {"status": "abstain", "message": "challengers run in paper"})
agent("Z07", "Portfolio allocator", "meta", "meta")(lambda c: {"evidence": {"method": (c.risk or {}).get(
    "allocator", "risk budget per trade")}, "message": "risk-budget sizing"})
agent("Z08", "Health monitor", "meta", "meta")(lambda c: {"evidence": {"quality_score": c.quality.get("quality", {}).get(
    "score")}, "message": f"data quality {c.quality.get('quality', {}).get('score')}/100"})
agent("Z09", "Audit", "meta", "meta")(lambda c: {"message": "every decision is written to the hash-chained audit log"})
agent("Z10", "Master orchestrator", "meta", "meta")(lambda c: {"message": "data -> features -> regime -> strategy -> "
                                                               "ensemble -> risk -> execution"})


def _drift(c):
    r = c.ff.get("ret_1")
    if r is None or len(r) < 400:
        return {"status": "abstain", "message": "needs 400 bars"}
    a, b = np.nanstd(r[-400:-100]), np.nanstd(r[-100:])
    ratio = b / a if a > 0 else float("nan")
    drift = ok(ratio) and (ratio > 2 or ratio < 0.5)
    return {"evidence": {"vol_ratio_recent_vs_prior": ratio}, "flags": ["DRIFT_WARNING"] if drift else [],
            "message": "return distribution shifted" if drift else "no distribution shift"}


def _anomaly(c):
    r = c.ff.get("ret_1")
    if r is None or len(r) < 100:
        return {"status": "abstain", "message": "needs 100 bars"}
    sd = np.nanstd(r[-100:-1])
    z = r[-1] / sd if sd > 0 else 0.0
    bad = abs(z) > 8
    return {"evidence": {"last_return_z": float(z)}, "veto": bad, "flags": ["DATA_ANOMALY"] if bad else [],
            "message": f"last move {z:+.1f} standard deviations" + (": entries paused until confirmed" if bad else "")}


def roster_summary() -> dict:
    by: dict[str, int] = {}
    for a in AGENTS.values():
        by[a.group] = by.get(a.group, 0) + 1
    return {"agents": len(AGENTS), "by_group": by, "voting": sum(1 for a in AGENTS.values() if a.votes),
            "need_external_data": sum(1 for a in AGENTS.values() if a.requires)}
