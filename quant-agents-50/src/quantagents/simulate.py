"""Day-by-day paper simulation: the full 25-agent cycle run on consecutive days.

This is the "digital twin" the spec asks for before paper trading (section 54), in its
simplest form: one fresh paper account, one kill switch, one A35 memory, and the real
orchestrator run once per day. Orders decided after a close fill at the next day's open,
exactly as in live paper trading. Nothing here can place a real order.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from datetime import date

import numpy as np

from quantagents.agents.a35_scorekeeper import Scorekeeper
from quantagents.audit import AuditLog
from quantagents.config import AppConfig
from quantagents.execution.paper import PaperAccount
from quantagents.market import MarketData
from quantagents.orchestrator import CycleReport, Orchestrator
from quantagents.registry import Registry
from quantagents.risk.killswitch import KillSwitch
from quantagents.schemas import Message, ScoreSummary


class DayResult(Message):
    as_of: date
    equity: float
    level: str
    regime: str
    transition_alert: bool
    go: tuple[str, ...]
    n_fills: int
    entry_scale: float | None


@dataclass
class SimulationResult:
    days: list[DayResult]
    reports: list[CycleReport]
    account: PaperAccount
    scorekeeper: Scorekeeper
    final_scores: ScoreSummary | None
    kill_switch_engaged: bool
    stats: dict[str, float] = field(default_factory=dict)
    levels: Counter[str] = field(default_factory=Counter)
    blockers: Counter[str] = field(default_factory=Counter)


def blocker(reason: str) -> str:
    """Group a GO-rule reason into a short label (the numbers differ every day)."""
    for prefix, label in (
        ("pooled p", "pooled probability below the GO bar"),
        ("net edge", "expected edge too small for the costs"),
        ("A40 p_no_trade", "A40 no-trade check"),
        ("no volatility", "no volatility forecast"),
        ("no agent", "no agent had a view"),
        ("Tier-1 block", "Tier-1 block (data or reconciliation)"),
    ):
        if reason.startswith(prefix):
            return label
    if "team(s) agree" in reason:
        return "too few teams agree"
    return reason


def run_paper_simulation(
    cfg: AppConfig,
    registry: Registry,
    market: MarketData,
    *,
    days: int,
    end: date | None = None,
    keep_reports: bool = False,
) -> SimulationResult:
    """Run the cycle on the ``days`` trading days ending at ``end`` (default: the last date
    with a following day, so the final orders can still fill)."""
    if days < 1:
        raise ValueError("days must be >= 1")
    last = market.index_of(end) if end is not None else len(market) - 2
    first = last - days + 1
    if first < 1:
        raise ValueError(f"not enough data for {days} days ending {market.dates[last]}")
    account = PaperAccount(cfg.system.capital, cfg.costs)
    scorekeeper = Scorekeeper()
    switch = KillSwitch()
    orchestrator = Orchestrator(
        cfg,
        registry,
        account,
        switch,
        audit=AuditLog(),
        scorekeeper=scorekeeper,
        simulate_next_open=False,
    )
    results: list[DayResult] = []
    reports: list[CycleReport] = []
    levels: Counter[str] = Counter()
    blockers: Counter[str] = Counter()
    for day in market.dates[first : last + 1]:
        report = orchestrator.run_cycle(market, day)
        levels[report.risk.level.value] += 1
        for proposal in report.proposals:
            if not proposal.go:
                blockers.update({blocker(r) for r in proposal.reasons})
        if not cfg.risk.shorting_allowed:
            shorts = sum(p.go and p.direction.value == "short" for p in report.proposals)
            if shorts:
                blockers["GO short skipped: shorting is off"] += shorts
        regime = report.context.regime
        results.append(
            DayResult(
                as_of=day,
                equity=report.equity,
                level=report.risk.level.value,
                regime=regime.label if regime is not None else "n/a",
                transition_alert=report.context.transition_alert,
                go=tuple(p.symbol for p in report.proposals if p.go),
                n_fills=len(report.fills),
                entry_scale=report.stress.entry_scale if report.stress is not None else None,
            )
        )
        if keep_reports:
            reports.append(report)
    equity = np.array([d.equity for d in results])
    returns = equity[1:] / equity[:-1] - 1.0 if len(equity) > 1 else np.empty(0)
    peak = np.maximum.accumulate(equity) if len(equity) else equity
    sd = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0
    stats = {
        "start_equity": float(cfg.system.capital),
        "end_equity": float(equity[-1]) if len(equity) else float(cfg.system.capital),
        "total_return": float(equity[-1] / cfg.system.capital - 1.0) if len(equity) else 0.0,
        "max_drawdown": float(np.max(1.0 - equity / peak)) if len(equity) else 0.0,
        "sharpe": float(np.mean(returns)) / sd * np.sqrt(252.0) if sd > 0 else 0.0,
        "n_fills": float(len(account.ledger.fills)),
        "fees": float(account.ledger.book.fees_paid),
        "days_with_go": float(sum(1 for d in results if d.go)),
        "transition_alert_days": float(sum(d.transition_alert for d in results)),
    }
    final = reports[-1].scores if reports else None
    if final is None and results:
        states = {
            s.id: s.state for s in registry.specs if s.is_signal and s.implementation is not None
        }
        final = scorekeeper.summary(results[-1].as_of, states)
    return SimulationResult(
        days=results,
        reports=reports,
        account=account,
        scorekeeper=scorekeeper,
        final_scores=final,
        kill_switch_engaged=switch.engaged,
        stats=stats,
        levels=levels,
        blockers=blockers,
    )
