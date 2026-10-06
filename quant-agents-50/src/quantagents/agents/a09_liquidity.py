"""A09 Liquidity & Microstructure Analyst (Team 2, Phase 3). Spec sections 30 and 53.

Daily bars only (no order book yet), so every number is an estimate:
- traded value: median of close x volume over 20 days (ADV, in currency)
- impact: square-root law, impact = 0.8 x daily vol x sqrt(order / ADV)
- est_cost_bps (one way) = the configured slippage + the impact of the reference order
  (the largest position the risk limits allow)
- tradability: 1 when that cost is within the configured slippage, falling to 0 at 4x it
- max_order_notional: ``max_adv_participation_pct`` of ADV
- information only: the Corwin-Schultz / Abdi-Ranaldo high-low spread proxy and its ratio to
  its 1-year norm, plus Amihud illiquidity. Tested on data with a constant true spread, the
  proxy still reached 2.3x its norm 5% of the time, so it does not drive decisions.

Effects (all can only reduce risk): A48 caps entries at max_order_notional, A40 flags thin
liquidity, and the GO rule's cost hurdle uses this cost when it is above the config cost.
Unknown liquidity counts as untradable. Replace with real quotes when an L1 feed exists.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from typing import ClassVar

import numpy as np

from quantagents.agents.base import Agent
from quantagents.config import AppConfig
from quantagents.features import abdi_ranaldo_spread, amihud_illiquidity, corwin_schultz_spread
from quantagents.market import FloatArray, MarketView
from quantagents.schemas import ContextReport, LiquidityReport


def spread_proxy(high: FloatArray, low: FloatArray, close: FloatArray, n: int) -> FloatArray:
    """Average of the two high-low spread estimators where both exist (else whichever does)."""
    cs = corwin_schultz_spread(high, low, close, n)
    ar = abdi_ranaldo_spread(high, low, close, n)
    both = np.vstack([cs, ar])
    counts = np.sum(np.isfinite(both), axis=0)
    total = np.nansum(both, axis=0)
    out = np.full(len(close), np.nan)
    ok = counts > 0
    out[ok] = total[ok] / counts[ok]
    return out


class LiquidityAgent(Agent):
    agent_id = "A09"
    name = "Liquidity & Microstructure Analyst"
    kind = "stat"
    info_subset = ("ohlcv", "vol_forecast")

    window: ClassVar[int] = 20
    history: ClassVar[int] = 252
    impact_coef: ClassVar[float] = 0.8
    worst_multiple: ClassVar[float] = 4.0  # tradability reaches 0 at 4x the assumed cost

    def unknown(
        self, symbol: str, reference: float, why: str, assumed_bps: float
    ) -> LiquidityReport:
        """Unknown liquidity: untradable, and priced at the worst cost A09 can report."""
        return LiquidityReport(
            symbol=symbol,
            spread_bps=0.0,
            spread_ratio=1.0,
            adv_notional=0.0,
            amihud=None,
            impact_bps=0.0,
            est_cost_bps=self.worst_multiple * assumed_bps,
            tradability=0.0,
            max_order_notional=0.0,
            reference_notional=reference,
            detail=f"unknown liquidity ({why}): treated as untradable",
        )

    def assess_symbol(
        self,
        view: MarketView,
        symbol: str,
        context: ContextReport,
        *,
        reference_notional: float,
        cfg: AppConfig,
    ) -> LiquidityReport:
        n = self.window
        tail = self.history + 2 * n
        assumed = max(cfg.costs.slippage_bps, 1.0)
        h = np.ascontiguousarray(view.high(symbol)[-tail:])
        lo = np.ascontiguousarray(view.low(symbol)[-tail:])
        c = np.ascontiguousarray(view.close(symbol)[-tail:])
        v = np.ascontiguousarray(view.volume(symbol)[-tail:])
        if len(c) < n + 2:
            return self.unknown(symbol, reference_notional, f"{len(c)} bars", assumed)
        traded = c[-n:] * v[-n:]
        traded = traded[np.isfinite(traded)]
        adv = float(np.median(traded)) if len(traded) else 0.0
        if adv <= 0:
            return self.unknown(symbol, reference_notional, "no traded value", assumed)
        forecast = context.vol(symbol)
        if forecast is not None:
            sigma = forecast.sigma_daily
        else:
            with np.errstate(divide="ignore", invalid="ignore"):
                r = np.diff(np.log(c[-(n + 1) :]))
            r = r[np.isfinite(r)]
            sigma = float(np.std(r, ddof=1)) if len(r) > 2 else math.nan
        if not (math.isfinite(sigma) and sigma > 0):
            return self.unknown(symbol, reference_notional, "no volatility estimate", assumed)
        # Information only (see the module docstring).
        proxy = spread_proxy(h, lo, c, n)
        history = proxy[np.isfinite(proxy)][-self.history :]
        spread_bps, spread_ratio = 0.0, 1.0
        if math.isfinite(float(proxy[-1])) and len(history):
            spread_bps = 1e4 * float(proxy[-1])
            typical = float(np.median(history))
            spread_ratio = float(proxy[-1]) / typical if typical > 0 else 1.0
        amihud = float(amihud_illiquidity(c, v, n)[-1])
        impact_bps = 1e4 * self.impact_coef * sigma * math.sqrt(max(reference_notional, 0.0) / adv)
        est = assumed + impact_bps
        span = (self.worst_multiple - 1.0) * assumed
        tradability = min(1.0, max(0.0, 1.0 - (est - assumed) / span))
        cap = cfg.risk.max_adv_participation_pct / 100.0 * adv
        return LiquidityReport(
            symbol=symbol,
            spread_bps=spread_bps,
            spread_ratio=spread_ratio,
            adv_notional=adv,
            amihud=amihud if math.isfinite(amihud) else None,
            impact_bps=impact_bps,
            est_cost_bps=est,
            tradability=tradability,
            max_order_notional=cap,
            reference_notional=reference_notional,
            detail=(
                f"impact {impact_bps:.1f} bps for {reference_notional:,.0f} vs ADV "
                f"{adv:,.0f}; cost {est:.1f} bps vs {assumed:.1f} assumed; "
                f"spread proxy {spread_ratio:.1f}x its norm (information only)"
            ),
        )

    def assess(
        self,
        view: MarketView,
        symbols: Sequence[str],
        context: ContextReport,
        *,
        reference_notional: float,
        cfg: AppConfig,
    ) -> tuple[LiquidityReport, ...]:
        return tuple(
            self.assess_symbol(view, s, context, reference_notional=reference_notional, cfg=cfg)
            for s in symbols
        )
