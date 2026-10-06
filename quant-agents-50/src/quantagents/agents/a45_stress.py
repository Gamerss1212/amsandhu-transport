"""A45 Stress & Simulation Agent (Team 9, Phase 3). Spec sections 54, 55 and 62.

Two jobs:

1. Every cycle (step 10, before A49): stress the book as it WOULD be after today's entries.
   Scenarios, each as a percent of equity (positive = loss):
   - gap_down_10: every position gaps 10% against us overnight, straight through its stop
   - stops_gap_through: every stop is hit and fills 50% further away than planned
   - correlation_one_3sigma: every position moves 3 daily sigmas against us at once
   - historical_worst_day / historical_worst_week: the worst 1 and 5 days in the last 3 years,
     replayed on today's book
   - liquidity_crunch: closing everything at 5x A09's estimated cost
   Plus 1-day historical VaR and expected shortfall (99%) and a Monte Carlo: 1,000 paths of
   20 days from a stationary block bootstrap of joint daily returns, giving the chance of a
   daily-limit breach and of hitting the drawdown limit ("ruin") within 20 days.
   Rule: tail loss = the largest of worst day, ES 99% and correlation-one. "Before" is the
   book after today's exits; "after" adds today's entries. If entries would push the tail
   above the daily loss limit, they are scaled down so it stays inside; if the book is
   already over it, new entries are cut to zero. A ruin chance of 5%+ halves entries.
   The orchestrator applies the scale to each entry's FINAL size (after every cap) and
   re-tests the rebuilt book; if it is still over budget, new entries are dropped.
   A45 can only shrink entries. Exits are never touched, and A49 still has the last word.

2. On request (``stress_returns``, CLI ``stress``): Monte Carlo of a strategy's daily returns
   for promotion reviews: chance of a losing year, drawdown distribution, ruin probability.
"""

from __future__ import annotations

import hashlib
import math
from collections.abc import Mapping, Sequence
from typing import ClassVar

import numpy as np
import numpy.typing as npt

from quantagents.agents.base import Agent
from quantagents.config import AppConfig
from quantagents.market import FloatArray, MarketView
from quantagents.regime_models import return_matrix
from quantagents.schemas import ContextReport, Message, StressReport, StressScenario


def seed_from(text: str) -> int:
    """A stable seed from any text (same cycle -> same Monte Carlo paths)."""
    return int.from_bytes(hashlib.sha256(text.encode()).digest()[:8], "big")


def bootstrap_paths(
    n_obs: int, paths: int, days: int, mean_block: float, rng: np.random.Generator
) -> npt.NDArray[np.int64]:
    """Row indices for ``paths`` stationary-bootstrap paths of ``days`` days (blocks of
    geometric length with mean ``mean_block``, wrapping around the sample)."""
    if n_obs < 1 or paths < 1 or days < 1 or mean_block < 1:
        raise ValueError("n_obs, paths, days and mean_block must be positive")
    idx = np.empty((paths, days), dtype=np.int64)
    idx[:, 0] = rng.integers(0, n_obs, size=paths)
    for d in range(1, days):
        jump = rng.random(paths) < 1.0 / mean_block
        idx[:, d] = np.where(jump, rng.integers(0, n_obs, size=paths), (idx[:, d - 1] + 1) % n_obs)
    return idx


def max_drawdown(paths: FloatArray) -> FloatArray:
    """Maximum drawdown (fraction) of each row of daily returns, starting from 1."""
    growth = np.cumprod(1.0 + paths, axis=1)
    growth = np.concatenate([np.ones((paths.shape[0], 1)), growth], axis=1)
    peak = np.maximum.accumulate(growth, axis=1)
    return np.asarray(np.max(1.0 - growth / peak, axis=1), dtype=np.float64)


class StrategyStress(Message):
    n_days: int
    paths: int
    horizon_days: int
    p_losing_year: float
    median_return: float
    worst_5pct_return: float
    worst_1pct_return: float
    median_max_drawdown: float
    p95_max_drawdown: float
    p_ruin: float
    ruin_drawdown: float


def stress_returns(
    returns: Sequence[float] | FloatArray,
    *,
    ruin_drawdown: float,
    paths: int = 2000,
    horizon_days: int = 252,
    mean_block: float = 10.0,
    seed: int = 0,
) -> StrategyStress:
    """Monte Carlo of a daily return series (stationary bootstrap keeps volatility clusters)."""
    r = np.asarray(returns, dtype=np.float64)
    r = r[np.isfinite(r)]
    if len(r) < 20:
        raise ValueError("need at least 20 daily returns")
    rng = np.random.default_rng(seed)
    sims = r[bootstrap_paths(len(r), paths, horizon_days, mean_block, rng)]
    total = np.prod(1.0 + sims, axis=1) - 1.0
    dd = max_drawdown(sims)
    return StrategyStress(
        n_days=len(r),
        paths=paths,
        horizon_days=horizon_days,
        p_losing_year=float(np.mean(total < 0)),
        median_return=float(np.median(total)),
        worst_5pct_return=float(np.quantile(total, 0.05)),
        worst_1pct_return=float(np.quantile(total, 0.01)),
        median_max_drawdown=float(np.median(dd)),
        p95_max_drawdown=float(np.quantile(dd, 0.95)),
        p_ruin=float(np.mean(dd >= ruin_drawdown)),
        ruin_drawdown=ruin_drawdown,
    )


class StressAgent(Agent):
    agent_id = "A45"
    name = "Stress & Simulation Agent"
    kind = "code"
    info_subset = ("positions", "ohlcv", "vol_forecast", "liquidity")

    history: ClassVar[int] = 756
    min_history: ClassVar[int] = 60
    mc_paths: ClassVar[int] = 1000
    mc_days: ClassVar[int] = 20
    mean_block: ClassVar[float] = 5.0
    gap_pct: ClassVar[float] = 10.0
    stop_slip: ClassVar[float] = 0.5
    sigmas: ClassVar[float] = 3.0
    liquidity_multiple: ClassVar[float] = 5.0
    untradable_multiple: ClassVar[float] = 4.0  # A09's worst cost, for unmeasurable holdings
    ruin_cut: ClassVar[float] = 0.05

    def _tail(
        self,
        weights: Mapping[str, float],
        returns: FloatArray,
        symbols: Sequence[str],
        sigma: Mapping[str, float],
    ) -> tuple[float, float, float, float]:
        """(worst day, ES 99%, VaR 99%, correlation-one) in percent of equity for a book."""
        if not any(weights.values()):
            return 0.0, 0.0, 0.0, 0.0
        w = np.array([weights.get(s, 0.0) for s in symbols])
        corr_one = 100.0 * sum(abs(weights[s]) * self.sigmas * sigma.get(s, 0.0) for s in weights)
        if len(returns) == 0:
            return corr_one, corr_one, corr_one, corr_one
        losses = -100.0 * (returns @ w)
        var = float(np.quantile(losses, 0.99))
        es = float(np.mean(losses[losses >= var]))
        return float(np.max(losses)), es, var, corr_one

    def assess(
        self,
        *,
        cycle_id: str,
        view: MarketView,
        before: Mapping[str, float],
        after: Mapping[str, float],
        prices: Mapping[str, float],
        stops: Mapping[str, float],
        equity: float,
        drawdown_pct: float,
        context: ContextReport,
        cfg: AppConfig,
    ) -> StressReport:
        budget = cfg.risk.max_daily_loss_pct
        held = sorted(s for s, q in after.items() if q and s in prices)
        held_before = sorted(s for s, q in before.items() if q and s in prices)
        symbols = sorted(set(held) | set(held_before))
        notes: list[str] = []
        if equity <= 0 or not symbols:
            return StressReport(
                cycle_id=cycle_id,
                equity=equity,
                gross_exposure_pct=0.0,
                scenarios=(),
                var_99_1d_pct=0.0,
                es_99_1d_pct=0.0,
                mc_es_99_20d_pct=0.0,
                p_daily_limit_breach_20d=0.0,
                p_ruin_20d=0.0,
                tail_loss_before_pct=0.0,
                tail_loss_pct=0.0,
                budget_pct=budget,
                entry_scale=1.0,
                notes=("no positions to stress",),
            )

        def weights(book: Mapping[str, float]) -> dict[str, float]:
            return {s: book[s] * prices[s] / equity for s in symbols if book.get(s)}

        w_after, w_before = weights(after), weights(before)
        sigma: dict[str, float] = {}
        for s in symbols:
            forecast = context.vol(s)
            if forecast is not None:
                sigma[s] = forecast.sigma_daily
        log_r = return_matrix(view, symbols, self.history)
        simple = np.expm1(log_r)
        clean = simple[np.all(np.isfinite(simple), axis=1)] if simple.size else simple
        for s in symbols:
            if s not in sigma:
                col = clean[:, symbols.index(s)] if len(clean) else np.empty(0)
                sigma[s] = float(np.std(col, ddof=1)) if len(col) > 2 else 0.05
                notes.append(f"{s}: no A08 forecast, sigma from history")
        if len(clean) < self.min_history:
            notes.append(f"only {len(clean)} clean days of history: historical scenarios skipped")
            clean = clean[:0]

        worst_day, es_1d, var_1d, corr_one = self._tail(w_after, clean, symbols, sigma)
        before_tail = max(self._tail(w_before, clean, symbols, sigma)[i] for i in (0, 1, 3))
        after_tail = max(worst_day, es_1d, corr_one)
        gross = 100.0 * sum(abs(x) for x in w_after.values())

        scenarios = [
            StressScenario(
                name="gap_down_10",
                loss_pct=gross * self.gap_pct / 100.0,
                detail=f"every position gaps {self.gap_pct:g}% against us, through its stop",
            )
        ]
        stop_loss = 0.0
        for s in held:
            qty = after[s]
            stop = stops.get(s)
            if stop is not None and stop > 0:
                per_unit = abs(prices[s] - stop) * (1.0 + self.stop_slip)
            else:
                per_unit = self.sigmas * sigma[s] * prices[s]
            stop_loss += abs(qty) * per_unit
        scenarios.append(
            StressScenario(
                name="stops_gap_through",
                loss_pct=100.0 * stop_loss / equity,
                detail=f"every stop fills {self.stop_slip:.0%} further away than planned",
            )
        )
        scenarios.append(
            StressScenario(
                name="correlation_one_3sigma",
                loss_pct=corr_one,
                detail=f"all positions move {self.sigmas:g} daily sigmas against us together",
            )
        )
        if len(clean):
            w_vec = np.array([w_after.get(s, 0.0) for s in symbols])
            weekly = np.expm1(np.convolve(np.ones(5), np.log1p(clean @ w_vec), mode="valid"))
            scenarios.append(
                StressScenario(
                    name="historical_worst_day",
                    loss_pct=worst_day,
                    detail=f"worst of {len(clean)} days replayed on today's book",
                )
            )
            scenarios.append(
                StressScenario(
                    name="historical_worst_week",
                    loss_pct=float(-100.0 * np.min(weekly)) if len(weekly) else 0.0,
                    detail="worst 5-day stretch replayed on today's book",
                )
            )
        crunch = 0.0
        floor = max(cfg.costs.slippage_bps, 1.0)
        for s in held:
            liq = context.liq(s)
            cost_bps = max(liq.est_cost_bps, floor) if liq is not None else floor
            if liq is not None and liq.tradability <= 0:
                cost_bps = max(cost_bps, self.untradable_multiple * floor)  # cannot price it
            crunch += abs(after[s]) * prices[s] * self.liquidity_multiple * cost_bps / 1e4
        scenarios.append(
            StressScenario(
                name="liquidity_crunch",
                loss_pct=100.0 * crunch / equity,
                detail=f"closing everything at {self.liquidity_multiple:g}x the estimated cost",
            )
        )

        p_breach = p_ruin = mc_es = 0.0
        if len(clean) and w_after:
            rng = np.random.default_rng(seed_from(cycle_id))
            idx = bootstrap_paths(len(clean), self.mc_paths, self.mc_days, self.mean_block, rng)
            w_vec = np.array([w_after.get(s, 0.0) for s in symbols])
            daily = clean[idx] @ w_vec  # paths x days
            total = 100.0 * -(np.prod(1.0 + daily, axis=1) - 1.0)
            cutoff = float(np.quantile(total, 0.99))
            mc_es = float(np.mean(total[total >= cutoff]))
            p_breach = float(np.mean(np.any(-100.0 * daily >= budget, axis=1)))
            room = max(cfg.risk.max_drawdown_pct - drawdown_pct, 0.0)
            p_ruin = float(np.mean(100.0 * max_drawdown(daily) >= room))

        scale = 1.0
        adds = after_tail > before_tail + 1e-12
        if adds and after_tail > budget:
            if before_tail >= budget:
                scale = 0.0
                notes.append(
                    f"book already at {before_tail:.2f}% tail loss (budget {budget:g}%): "
                    "no new entries"
                )
            else:
                scale = (budget - before_tail) / (after_tail - before_tail)
                notes.append(
                    f"entries scaled to {scale:.0%} to keep tail loss within the {budget:g}% "
                    "daily limit"
                )
        if adds and p_ruin >= self.ruin_cut:
            scale = min(scale, 0.5)
            notes.append(f"{p_ruin:.0%} chance of hitting the drawdown limit in 20 days: halved")
        scale = math.floor(max(0.0, min(1.0, scale)) * 100.0) / 100.0
        return StressReport(
            cycle_id=cycle_id,
            equity=equity,
            gross_exposure_pct=gross,
            scenarios=tuple(scenarios),
            var_99_1d_pct=var_1d,
            es_99_1d_pct=es_1d,
            mc_es_99_20d_pct=mc_es,
            p_daily_limit_breach_20d=p_breach,
            p_ruin_20d=p_ruin,
            tail_loss_before_pct=before_tail,
            tail_loss_pct=after_tail,
            budget_pct=budget,
            entry_scale=scale,
            notes=tuple(notes),
        )
