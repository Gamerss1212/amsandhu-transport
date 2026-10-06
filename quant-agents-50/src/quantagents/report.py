"""Plain-text reports for people. Short lines, no jargon without a word of explanation."""

from __future__ import annotations

from collections.abc import Iterable

from quantagents.agents.a45_stress import StrategyStress
from quantagents.backtest.engine import BacktestResult
from quantagents.backtest.event import EventResult
from quantagents.orchestrator import CycleReport
from quantagents.registry import AgentSpec, Registry
from quantagents.schemas import ContextReport, ScoreSummary, StressReport
from quantagents.simulate import SimulationResult
from quantagents.validation.leakage import RedTeamReport
from quantagents.validation.stats import ValidationReport

DISCLAIMER = (
    "Paper trading only. Synthetic or historical results say nothing certain about the future. "
    "Not financial advice."
)


def _rule(title: str) -> str:
    return f"\n{title}\n{'-' * len(title)}"


def format_cycle_report(report: CycleReport, *, currency: str = "CAD") -> str:
    lines = [
        f"QuantAgents-50 decision cycle {report.cycle_id}",
        f"As of the {report.as_of.isoformat()} close | phase {report.phase} | paper trading | "
        f"kill switch {'ENGAGED' if report.kill_switch_engaged else 'armed'}",
        _rule("The 15 steps"),
    ]
    for s in report.steps:
        lines.append(f"{s.number:>2}. {s.name:<20} {s.status:<9} {s.summary}")

    if report.context_failures:
        lines.append(
            "Agent failures (safe fallback used): "
            + "; ".join(f"{k}: {v}" for k, v in sorted(report.context_failures.items()))
        )
    lines.extend(format_context(report.context))

    lines.append(_rule("Sealed predictions (P(up) on each agent's own horizon; - = abstained)"))
    agents = sorted({p.agent_id for p in report.predictions})
    lines.append("symbol   " + "".join(f"{a:<14}" for a in agents))
    for symbol in sorted({p.symbol for p in report.predictions}):
        cells = []
        for a in agents:
            match = [p for p in report.predictions if p.symbol == symbol and p.agent_id == a]
            if not match or match[0].abstain:
                cells.append(f"{'-':<14}")
            else:
                p = match[0]
                cells.append(f"{p.direction.value} {p.p_up:.3f}".ljust(14))
        lines.append(f"{symbol:<9}" + "".join(cells))
    if report.seal_rejections:
        lines.append(
            "rejected or failed: "
            + "; ".join(f"{k}: {v}" for k, v in report.seal_rejections.items())
        )

    lines.append(_rule("Decisions (A47 rules + A40 no-trade check)"))
    no_trade = {v.symbol: v for v in report.no_trade}
    for prop in report.proposals:
        head = f"{prop.symbol:<7} {'GO' if prop.go else 'no trade':<9}"
        stats = (
            f"P(up) {prop.pooled_p:.3f}, teams agree {prop.teams_agree}, "
            f"net edge {prop.net_edge:+.2%}, A40 {no_trade[prop.symbol].p_no_trade:.2f}"
        )
        why = "" if prop.go else f" | why: {'; '.join(prop.reasons)}"
        lines.append(f"{head} {prop.direction.value:<5} {stats}{why}")

    if report.stress is not None:
        lines.extend(format_stress(report.stress))

    lines.append(_rule("Orders and the risk gate (A49 has the last word)"))
    if not report.intents:
        lines.append("No order intents this cycle.")
    for intent, result in zip(report.intents, report.risk.results, strict=True):
        stop = f", stop {intent.stop_price:.2f}" if intent.stop_price else ""
        lines.append(
            f"{intent.side.value.upper()} {intent.qty:g} {intent.symbol} near {intent.ref_price:.2f}{stop} "
            f"-> {result.reason} (approved {result.approved_qty:g})"
        )
    lines.append(f"Risk level: {report.risk.level.value} ({'; '.join(report.risk.level_reasons)})")

    lines.append(_rule("Fills (paper)"))
    if not report.fills:
        lines.append("No fills this cycle.")
    for f in report.fills:
        lines.append(
            f"{f.fill_id} {f.side.value.upper()} {f.qty:g} {f.symbol} at {f.price:.2f} on "
            f"{f.trade_date.isoformat()} (fee {f.fee:.2f}, {f.kind})"
        )

    lines.append(_rule("Account"))
    held = ", ".join(f"{s} {q:g}" for s, q in report.positions.items()) or "none"
    lines.append(
        f"Equity at the close: {report.equity:,.2f} {currency} | cash now: {report.cash:,.2f} {currency}"
    )
    lines.append(
        f"Positions: {held} | stops: {', '.join(f'{s} {v:.2f}' for s, v in report.stops.items()) or 'none'}"
    )
    lines.append(
        f"Reconciliation: {'ok' if report.reconciliation.ok else 'BREAK ' + '; '.join(report.reconciliation.diffs)}"
    )
    lines.append(f"Audit chain head: {report.audit_head[:16]}...")
    if report.scores is not None:
        lines.extend(format_scores(report.scores))
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def format_context(context: ContextReport) -> list[str]:
    """Team 2's shared picture of the market: regime, transitions, liquidity."""
    lines: list[str] = []
    regime = context.regime
    if regime is not None:
        lines.append(_rule("Market regime (A06)"))
        lines.append(
            f"{regime.label} / {regime.vol_label}: P(turbulent) {regime.p_high_vol:.2f} "
            f"(5 days ago {regime.p_high_vol_prev:.2f}), P(risk-on) {regime.p_risk_on:.2f}, "
            f"P(crisis) {regime.p_crisis:.2f}, breadth {regime.breadth:.0%}, "
            f"confidence {regime.confidence:.2f}"
        )
        lines.append(
            "Symbols: "
            + ", ".join(f"{x.symbol} {x.label} ({x.p_trending:.2f})" for x in regime.symbols)
        )
        lines.extend(f"Method: {m}" for m in regime.methods)
    transition = context.transition
    if transition is not None:
        state = "ALERT: system risk halved" if transition.alert else "no transition"
        lines.append(_rule(f"Transition check (A07): {state}"))
        for d in transition.detectors:
            mark = "FIRED" if d.fired else ("ok" if d.ran else "n/a")
            lines.append(f"[{mark:<5}] {d.name}: {d.detail}")
    elif context.transition_alert:
        lines.append(_rule("Transition check (A07): ALERT (detector failed, fail-safe)"))
    if context.liquidity:
        lines.append(_rule("Liquidity (A09; estimates from daily bars)"))
        lines.append(
            f"{'symbol':<8} {'ADV':>14} {'impact':>9} {'cost':>9} {'tradable':>9} {'max order':>12}"
        )
        for x in context.liquidity:
            lines.append(
                f"{x.symbol:<8} {x.adv_notional:>14,.0f} {x.impact_bps:>7.1f}bp "
                f"{x.est_cost_bps:>7.1f}bp {x.tradability:>9.2f} {x.max_order_notional:>12,.0f}"
            )
    return lines


def format_stress(stress: StressReport) -> list[str]:
    lines = [_rule("Stress test (A45; percent of equity, positive = loss)")]
    if not stress.scenarios:
        lines.append("No positions to stress.")
        return lines
    for sc in stress.scenarios:
        lines.append(f"{sc.name:<24} {sc.loss_pct:>7.2f}%  {sc.detail}")
    lines.append(
        f"1-day VaR 99% {stress.var_99_1d_pct:.2f}% | ES 99% {stress.es_99_1d_pct:.2f}% | "
        f"20-day Monte Carlo ES 99% {stress.mc_es_99_20d_pct:.2f}%"
    )
    lines.append(
        f"Next 20 days: P(a day breaks the daily loss limit) {stress.p_daily_limit_breach_20d:.1%}, "
        f"P(hit the drawdown limit) {stress.p_ruin_20d:.1%}"
    )
    lines.append(
        f"Tail loss {stress.tail_loss_before_pct:.2f}% -> {stress.tail_loss_pct:.2f}% with today's "
        f"entries (budget {stress.budget_pct:g}%); entries x{stress.entry_scale:.2f}"
        + (
            f"; re-checked after scaling: {stress.tail_loss_final_pct:.2f}%"
            if stress.tail_loss_final_pct is not None
            else ""
        )
    )
    lines.extend(f"Note: {n}" for n in stress.notes)
    return lines


def format_scores(scores: ScoreSummary) -> list[str]:
    lines = [
        _rule("Scorekeeper (A35; only matured predictions count)"),
        f"{scores.n_records} prediction(s) stored, {scores.n_scored} scored, "
        f"{scores.n_pending} waiting for their horizon",
    ]
    rows = [c for c in scores.cards if c.n_scored or c.n_pending]
    if rows:
        lines.append(
            f"{'agent':<6} {'state':<8} {'scored':>6} {'indep':>6} {'hit':>6} {'Brier':>7} "
            f"{'skill':>7} {'t':>6} {'temp':>5} {'weight':>6}"
        )
    for c in rows:
        hit = f"{c.hit_rate:.0%}" if c.hit_rate is not None else "-"
        b = f"{c.brier:.4f}" if c.brier is not None else "-"
        sk = f"{c.brier_skill:+.3f}" if c.brier_skill is not None else "-"
        t = f"{c.skill_t:+.1f}" if c.skill_t is not None else "-"
        lines.append(
            f"{c.agent_id:<6} {c.state:<8} {c.n_scored:>6} {c.effective_n:>6.0f} {hit:>6} {b:>7} "
            f"{sk:>7} {t:>6} {c.temperature:>5.2f} {c.weight:>6.2f}"
        )
    if scores.pooled_brier is not None:
        skill = (
            f", skill {scores.pooled_brier_skill:+.3f}"
            if scores.pooled_brier_skill is not None
            else ""
        )
        lines.append(
            f"Pooled forecast: Brier {scores.pooled_brier:.4f} on {scores.pooled_n} matured{skill}"
        )
    lines.append(
        "indep = independent outcomes (overlapping forecasts counted once). Skill above 0 beats "
        "guessing the base rate; t of 2+ means it is probably not luck. Temp below 1 = toned down."
    )
    lines.extend(f"Note: {n}" for n in scores.notes)
    return lines


def format_strategy_stress(name: str, s: StrategyStress, cost_note: str) -> str:
    lines = [
        _rule(f"A45 Monte Carlo: {name} ({s.paths:,} simulated years from {s.n_days} days)"),
        f"Chance of a losing year: {s.p_losing_year:.0%}",
        f"Median year {s.median_return:+.1%} | worst 5% {s.worst_5pct_return:+.1%} | "
        f"worst 1% {s.worst_1pct_return:+.1%}",
        f"Max drawdown: median {s.median_max_drawdown:.1%}, bad case (95th pct) {s.p95_max_drawdown:.1%}",
        f"Chance of a {s.ruin_drawdown:.0%}+ drawdown within a year (ruin line): {s.p_ruin:.1%}",
        cost_note,
    ]
    return "\n".join(lines)


def format_simulation(sim: SimulationResult, currency: str = "CAD") -> str:
    st = sim.stats
    first, last = sim.days[0].as_of, sim.days[-1].as_of
    lines = [
        f"Paper simulation: {len(sim.days)} trading days, {first.isoformat()} to {last.isoformat()}",
        "The full 25-agent cycle ran once per day; orders filled at the next open.",
        _rule("Result"),
        f"Equity {st['start_equity']:,.2f} -> {st['end_equity']:,.2f} {currency} "
        f"({st['total_return']:+.2%}) | max drawdown {st['max_drawdown']:.2%} | "
        f"Sharpe {st['sharpe']:.2f}",
        f"Fills {st['n_fills']:.0f} | fees {st['fees']:,.2f} | days with a GO "
        f"{st['days_with_go']:.0f} | A07 transition-alert days {st['transition_alert_days']:.0f}",
        "Risk levels: " + ", ".join(f"{k} {v}" for k, v in sorted(sim.levels.items())),
        f"Kill switch: {'ENGAGED' if sim.kill_switch_engaged else 'never fired'}",
    ]
    if sim.blockers:
        lines.append(_rule("Why symbols were not traded (symbol-days, a day can have several)"))
        lines.extend(f"{n:>5}  {label}" for label, n in sim.blockers.most_common(6))
    lines += [
        _rule("Last 10 days"),
    ]
    for d in sim.days[-10:]:
        scale = f"x{d.entry_scale:.2f}" if d.entry_scale is not None else "-"
        lines.append(
            f"{d.as_of.isoformat()} equity {d.equity:>10,.2f} | {d.level:<9} | {d.regime:<8} | "
            f"alert {'yes' if d.transition_alert else 'no ':<3} | GO {', '.join(d.go) or '-':<12} | "
            f"fills {d.n_fills} | A45 {scale}"
        )
    if sim.final_scores is not None:
        lines.extend(format_scores(sim.final_scores))
    held = ", ".join(f"{s} {q:g}" for s, q in sim.account.ledger.book.quantities().items())
    lines.append("")
    lines.append(f"Open positions at the end: {held or 'none'}")
    lines.append("")
    lines.append(DISCLAIMER)
    return "\n".join(lines)


def format_backtest(result: BacktestResult) -> str:
    m = result.metrics
    lines = [
        f"Backtest: {result.name} ({result.dates[0].isoformat()} to {result.dates[-1].isoformat()})",
        f"Costs: {result.cost_rate:.2%} per unit traded (fees + slippage), fills at the next open",
        f"Total return {m['total_return']:+.2%} | CAGR {m['cagr']:+.2%} | volatility {m['ann_vol']:.2%}",
        f"Sharpe {m['sharpe']:.2f} | max drawdown {m['max_drawdown']:.2%} | "
        f"avg daily turnover {m['avg_daily_turnover']:.3f} | invested on {m['exposure_days_pct']:.0f}% of days",
    ]
    return "\n".join(lines)


def format_event_backtest(result: EventResult, currency: str) -> str:
    m, c = result.metrics, result.costs
    lines = [
        f"Event-driven backtest: {result.name} ({result.dates[0].isoformat()} to "
        f"{result.dates[-1].isoformat()}), {result.capital:,.0f} {currency} start",
        f"Costs: fee {c.fee_bps:g} bp + slippage {c.slippage_bps:g} bp + square-root impact; "
        f"orders capped at {c.max_adv_participation:.0%} of daily traded value; fills at the next open",
        f"End value {result.equity[-1]:,.0f} {currency} | total return {m['total_return']:+.2%} | "
        f"CAGR {m['cagr']:+.2%} | Sharpe {m['sharpe']:.2f} | max drawdown {m['max_drawdown']:.2%}",
        f"Orders {m['orders']:.0f} | partial fills {m['partial_fills']:.0f} | rejected "
        f"{m['rejections']:.0f} | unfunded top-ups {m['unfunded']:.0f} | fees "
        f"{m['fees_paid']:,.2f} {currency} | average impact {m['avg_impact_bps']:.1f} bp",
    ]
    return "\n".join(lines)


def format_validation(report: ValidationReport, red_team: RedTeamReport | None = None) -> str:
    lines = [_rule(f"A44 validation: {report.strategy} -> {report.verdict}")]
    for c in report.checks:
        lines.append(f"[{'PASS' if c.passed else 'FAIL'}] {c.name}: {c.detail}")
    lines.append(
        f"Sharpe {report.metrics['sharpe']:.2f} (95% bootstrap interval "
        f"{report.metrics['sharpe_ci_low']:.2f} to {report.metrics['sharpe_ci_high']:.2f})"
    )
    lines.extend(f"Note: {n}" for n in report.notes)
    if red_team is not None:
        lines.append(
            _rule(
                f"A39 red team: {red_team.strategy} -> {'PASS' if red_team.passed else 'BLOCKED'}"
            )
        )
        lines.append(f"Tests: {', '.join(red_team.tests_run)}")
        if not red_team.findings:
            lines.append("No findings.")
        lines.extend(f"[{f.severity}] {f.test}: {f.detail}" for f in red_team.findings)
    return "\n".join(lines)


def format_registry(
    registry: Registry, phase: int | None = None, *, core_only: bool = False
) -> str:
    specs: Iterable[AgentSpec] = registry.specs if phase is None else registry.scheduled(phase)
    if core_only:
        specs = [s for s in specs if s.core]
    lines = [f"{'id':<4} {'name':<40} {'team':<30} {'tier':<4} {'phase':<5} status"]
    for s in specs:
        if s.implementation:
            status = f"built, {s.state}"
        else:
            status = "to build (core)" if s.core else "parked"
        lines.append(f"{s.id:<4} {s.name:<40} {s.team:<30} {s.tier:<4} {s.phase:<5} {status}")
    core = registry.core()
    built_core = sum(1 for s in core if s.implementation)
    lines.append("")
    lines.append(
        f"Core: {built_core} of {len(core)} built. Parked for later: {len(registry.parked())} "
        "(optional; build one with /new-agent when you have the data it needs)."
    )
    lines.append("Shadow = sealed and scored by A35, but no vote until the owner promotes it.")
    return "\n".join(lines)
