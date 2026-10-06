"""A46 Orchestrator: runs the fixed 15-step decision cycle (spec section 12).

Every step is recorded with a status:
- done:     the owning agents ran
- stand-in: a simpler substitute ran because the owner arrives in a later phase
- skipped:  the owner is not built yet and nothing needed to stand in
Agent crashes become abstentions; they never crash the cycle (spec section 18).
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date
from typing import Literal, TypeVar

from quantagents.agents.a01_market_data import MarketDataAgent
from quantagents.agents.a02_data_quality import DataQualityAgent
from quantagents.agents.a03_features import FeatureAgent
from quantagents.agents.a06_regime import RegimeAgent
from quantagents.agents.a07_transition import TransitionAgent
from quantagents.agents.a08_volatility import VolatilityAgent
from quantagents.agents.a09_liquidity import LiquidityAgent
from quantagents.agents.a35_scorekeeper import Scorekeeper
from quantagents.agents.a40_no_trade import NoTradeAgent
from quantagents.agents.a45_stress import StressAgent
from quantagents.agents.a47_aggregator import MetaAggregator
from quantagents.agents.a48_portfolio import PortfolioAgent
from quantagents.agents.base import AgentContext
from quantagents.aggregation import PoolResult, go_decision
from quantagents.audit import AuditLog
from quantagents.bus import MessageBus
from quantagents.config import AppConfig
from quantagents.execution.paper import PaperAccount, reconcile
from quantagents.market import MarketData
from quantagents.registry import VOTING_STATES, Registry
from quantagents.risk.governor import RiskGovernor, RiskInputs
from quantagents.risk.killswitch import KillSwitch
from quantagents.schemas import (
    AgentPrediction,
    Commitment,
    ContextReport,
    DataHealthReport,
    DecisionProposal,
    DegradationLevel,
    Fill,
    HealthAction,
    LiquidityReport,
    MarketSnapshot,
    Message,
    NoTradeVerdict,
    OrderIntent,
    ReconciliationReport,
    RegimeReport,
    RiskVerdict,
    ScoreSummary,
    StressReport,
    TargetPortfolio,
    TradeDecisionRecord,
    TransitionReport,
)
from quantagents.sealing import SealedBox, commitment_hash, new_nonce

StepStatus = Literal["done", "stand-in", "skipped"]
T = TypeVar("T")

STEPS: dict[int, tuple[str, tuple[str, ...]]] = {
    1: ("Open", ("A46",)),
    2: ("Data", ("A01", "A02", "A05")),
    3: ("Prepare", ("A03", "A04")),
    4: ("Context", ("A06", "A07", "A08", "A09", "A10", "A34")),
    5: ("Seal", ("A11-A33", "A40")),
    6: ("Calibrate", ("A35",)),
    7: ("Pool and pre-screen", ("A47",)),
    8: ("Challenge", ("A36", "A37", "A38", "A39", "A40")),
    9: ("Decide", ("A47",)),
    10: ("Construct", ("A48", "A45")),
    11: ("Gate", ("A49",)),
    12: ("Execute", ("A50",)),
    13: ("Record", ("A05", "A46")),
    14: ("Watch", ("A49", "A02", "A50")),
    15: ("Learn", ("A35", "A46")),
}
DEBATE_AGENTS = ("A36", "A37", "A38")


class KillSwitchEvent(Message):
    engaged: bool
    reason: str
    by: str


class StepRecord(Message):
    number: int
    name: str
    owners: tuple[str, ...]
    status: StepStatus
    summary: str


class CycleReport(Message):
    cycle_id: str
    as_of: date
    phase: int
    snapshot: MarketSnapshot
    steps: tuple[StepRecord, ...]
    health: DataHealthReport
    reconciliation: ReconciliationReport
    context: ContextReport
    predictions: tuple[AgentPrediction, ...]
    seal_rejections: dict[str, str]
    context_failures: dict[str, str]
    quorum: float
    no_trade: tuple[NoTradeVerdict, ...]
    proposals: tuple[DecisionProposal, ...]
    target: TargetPortfolio
    intents: tuple[OrderIntent, ...]
    risk: RiskVerdict
    scores: ScoreSummary | None
    stress: StressReport | None
    fills: tuple[Fill, ...]
    records: tuple[TradeDecisionRecord, ...]
    equity: float
    cash: float
    positions: dict[str, float]
    stops: dict[str, float]
    kill_switch_engaged: bool
    audit_head: str


class Orchestrator:
    agent_id = "A46"
    name = "Orchestrator (Chief of Staff)"
    kind = "mixed"

    def __init__(
        self,
        cfg: AppConfig,
        registry: Registry,
        account: PaperAccount,
        kill_switch: KillSwitch,
        *,
        audit: AuditLog | None = None,
        bus: MessageBus | None = None,
        scorekeeper: Scorekeeper | None = None,
        nonce_factory: Callable[[], str] = new_nonce,
        simulate_next_open: bool = True,
    ) -> None:
        self.cfg = cfg
        self.registry = registry
        self.account = account
        self.kill_switch = kill_switch
        self.audit = audit if audit is not None else AuditLog()
        self.bus = bus if bus is not None else MessageBus()
        self.nonce_factory = nonce_factory
        self.simulate_next_open = simulate_next_open
        self.a01, self.a02, self.a03 = MarketDataAgent(), DataQualityAgent(), FeatureAgent()
        self.a06, self.a07 = RegimeAgent(), TransitionAgent()
        self.a08, self.a09 = VolatilityAgent(), LiquidityAgent()
        self.a35 = scorekeeper if scorekeeper is not None else Scorekeeper()
        self.a40, self.a45 = NoTradeAgent(), StressAgent()
        self.a47, self.a48 = MetaAggregator(), PortfolioAgent()
        self.a49 = RiskGovernor(cfg)
        self.signal_agents = registry.signal_agents(cfg.system.phase)

    def _guard(
        self, failures: dict[str, str], agent_id: str, fn: Callable[[], T], fallback: T
    ) -> T:
        """Run a context agent; a crash is recorded and replaced by a safe fallback."""
        try:
            return fn()
        except Exception as exc:  # a failing agent must never crash the cycle (spec section 18)
            failures[agent_id] = f"{type(exc).__name__}: {exc}"
            return fallback

    def run_cycle(self, market: MarketData, as_of: date) -> CycleReport:
        """Run steps 1-15 once, as of the close of ``as_of``. Mutates the paper account."""
        cfg, agg = self.cfg, self.cfg.aggregation
        phase = cfg.system.phase
        account, broker, ledger = self.account, self.account.broker, self.account.ledger
        steps: list[StepRecord] = []
        failures: dict[str, str] = {}

        # 1 Open (A46)
        view = market.view(as_of)
        snapshot = self.a01.snapshot(view)
        sid = snapshot.snapshot_id
        cycle_id = f"C{as_of:%Y%m%d}-{sid[:8]}"
        ts = f"{as_of.isoformat()}T22:00:00Z"

        def publish(agent: str, topic: str, payload: Message) -> None:
            self.bus.publish(
                from_agent=agent,
                topic=topic,
                payload=payload,
                cycle_id=cycle_id,
                snapshot_id=sid,
                ts_utc=ts,
            )

        def step(number: int, status: StepStatus, summary: str) -> None:
            name, owners = STEPS[number]
            record = StepRecord(
                number=number, name=name, owners=owners, status=status, summary=summary
            )
            steps.append(record)
            self.audit.append("step", {"cycle_id": cycle_id, **record.model_dump(mode="json")})

        publish("A01", "data.snapshot", snapshot)
        active = self.registry.active(phase)
        active_ids = {s.id for s in active}
        missing = self.registry.missing(phase)
        shadow_ids = sorted(s.id for s in active if s.state == "shadow")
        step(
            1,
            "done",
            f"cycle {cycle_id}; phase {phase}: {len(active)} agents running"
            + (f" ({len(shadow_ids)} in shadow)" if shadow_ids else "")
            + f", {len(missing)} core agent(s) not built yet, {len(self.registry.parked())} parked; "
            f"kill switch {'ENGAGED' if self.kill_switch.engaged else 'armed'}",
        )

        # 2 Data (A01, A02, A05): earlier orders fill at today's open, then stops are checked
        bars = {s: view.last(s) for s in view.symbols}
        opens = {s: b.open for s, b in bars.items() if math.isfinite(b.open) and b.open > 0}
        early_fills = broker.fill_pending(opens, as_of) + broker.check_stops(bars, as_of)
        for fill in early_fills:
            ledger.record(fill)
            publish("A50", "orders.fills", fill)
        health = self.a02.check(view, sid, cfg.risk)
        recon = reconcile(ledger, broker)
        publish("A02", "data.health", health)
        prices = dict(snapshot.last_close)
        publish("A05", "ledger.state", ledger.state(prices))
        equity = ledger.book.equity(prices)
        daily, weekly, drawdown = account.loss_metrics(as_of, equity)
        step(
            2,
            "done",
            f"data health {health.score_0_100:.0f}/100 ({health.action.value}); blocked: {', '.join(health.blocked_symbols) or 'none'}; reconciliation {'ok' if recon.ok else 'BREAK'}; {len(early_fills)} fill(s) from earlier orders and stops",
        )

        universe = set(cfg.universe.symbols) or set(view.symbols)
        tradable = tuple(
            s for s in view.symbols if s in universe and s not in health.blocked_symbols
        )

        # 3 Prepare (A03; A04 text intake is parked)
        features = self.a03.compute(view, sid, tradable)
        publish("A03", "features.ready", features)
        step(
            3,
            "done",
            f"{len(tradable)} symbol(s) x {max((len(v) for v in features.values.values()), default=0)} causal features",
        )

        # 4 Context (A08 volatility, A06 regime, A09 liquidity, A07 transitions)
        vol_report = self.a08.forecast(view, sid, tradable)
        publish("A08", "context.vol", vol_report)
        regime: RegimeReport | None = None
        if "A06" in active_ids:
            regime = self._guard(
                failures, "A06", lambda: self.a06.classify(view, sid, tradable, features), None
            )
            if regime is not None:
                publish("A06", "context.regime", regime)
        liquidity: tuple[LiquidityReport, ...] = ()
        if "A09" in active_ids:
            reference = equity * cfg.risk.max_position_pct / 100.0
            worst = max(cfg.costs.slippage_bps, 1.0)
            unknown = tuple(
                self.a09.unknown(s, reference, "A09 failed", worst) for s in tradable
            )  # fail safe: unknown liquidity = untradable, at the worst-case cost
            liquidity = self._guard(
                failures,
                "A09",
                lambda: self.a09.assess(
                    view, tradable, vol_report, reference_notional=reference, cfg=cfg
                ),
                unknown,
            )
            for item in liquidity:
                publish("A09", "context.liquidity", item)
        transition: TransitionReport | None = None
        transition_alert = False
        if "A07" in active_ids:
            transition = self._guard(
                failures, "A07", lambda: self.a07.detect(view, sid, tradable, regime), None
            )
            # Fail safe: if the transition detector breaks, assume a transition (risk x 0.5).
            transition_alert = transition.alert if transition is not None else True
            if transition is not None:
                publish("A07", "context.transition", transition)
        context = ContextReport(
            snapshot_id=sid,
            agent_id="A46",
            vol_forecasts=vol_report.vol_forecasts,
            transition_alert=transition_alert,
            novelty_score=vol_report.novelty_score,
            regime=regime,
            transition=transition,
            liquidity=liquidity,
        )
        shocks = [f.symbol for f in context.vol_forecasts if f.shock]
        parts = [
            f"A08 volatility for {len(context.vol_forecasts)} symbol(s), shocks: {', '.join(shocks) or 'none'}"
        ]
        if regime is not None:
            parts.append(
                f"A06 {regime.label} / {regime.vol_label} (P(turbulent) {regime.p_high_vol:.2f}, "
                f"breadth {regime.breadth:.0%})"
            )
        if "A07" in active_ids:
            fired = ", ".join(transition.fired) if transition is not None else "detector failed"
            parts.append(
                f"A07 {'ALERT' if transition_alert else 'no transition'}"
                + (f" ({fired})" if transition_alert else "")
            )
        if liquidity:
            thin = [x.symbol for x in liquidity if x.tradability < 0.5]
            parts.append(f"A09 thin liquidity: {', '.join(thin) or 'none'}")
        if failures:
            parts.append(f"FAILED (safe fallback used): {', '.join(sorted(failures))}")
        step(4, "done", "; ".join(parts))

        # 5 Seal (commit-reveal)
        ctx = AgentContext(cycle_id, sid, view, cfg, features, context, tradable)
        box = SealedBox(cycle_id)
        sealed: dict[str, tuple[list[AgentPrediction], str]] = {}
        seal_failures: dict[str, str] = {}
        for agent in self.signal_agents:
            try:
                predictions = agent.predict(ctx)
            except Exception as exc:  # an agent failure is an abstention, never a cycle crash
                seal_failures[agent.agent_id] = f"{type(exc).__name__}: {exc}"
                continue
            nonce = self.nonce_factory()
            commitment = Commitment(
                agent_id=agent.agent_id,
                cycle_id=cycle_id,
                commit_hash=commitment_hash(predictions, nonce),
            )
            box.commit(commitment)
            publish(agent.agent_id, "signals.commit", commitment)
            sealed[agent.agent_id] = (predictions, nonce)
        box.close()
        for agent_id, (predictions, nonce) in sealed.items():
            if box.reveal(agent_id, predictions, nonce):
                for p in predictions:
                    publish(agent_id, "signals.reveal", p)
        revealed = [p for agent_id in sorted(box.accepted) for p in box.accepted[agent_id]]
        rejections = {**seal_failures, **box.rejected}
        # Shadow agents are sealed and scored but carry no weight and no quorum (spec section 17).
        voters = {
            a.agent_id
            for a in self.signal_agents
            if self.registry.get(a.agent_id).state in VOTING_STATES
        }
        voting = [p for p in revealed if p.agent_id in voters]
        quorum = len(voters & set(box.accepted)) / len(voters) if voters else 0.0
        shadow = sorted({a.agent_id for a in self.signal_agents} - voters)
        step(
            5,
            "done",
            f"{len(box.accepted)}/{len(self.signal_agents)} signal agents sealed and revealed (voting quorum {quorum:.0%}); "
            f"{sum(not p.abstain for p in voting)} directional vote(s)"
            + (f"; shadow (scored, no vote): {', '.join(shadow)}" if shadow else ""),
        )

        # 6 Calibrate (A35 scores matured predictions, then tempers over-confident agents)
        scores: ScoreSummary | None = None
        weights: dict[str, float] | None = None
        n_eff: float | None = None
        calibrated = voting
        if "A35" in active_ids:
            states = {
                s.id: s.state
                for s in self.registry.specs
                if s.is_signal and s.implementation is not None
            }

            def score() -> tuple[int, ScoreSummary, list[AgentPrediction]]:
                newly = self.a35.score_matured(view)
                summary = self.a35.summary(as_of, states, voters=sorted(voters))
                return newly, summary, self.a35.calibrate(voting, summary)

            scored = self._guard(failures, "A35", score, None)
            if scored is not None:
                newly, scores, calibrated = scored
                weights = self.a35.weights(scores)
                n_eff = scores.n_eff
                publish("A35", "governance.scorecards", scores)
                tempered = sorted(
                    {
                        a.agent_id
                        for a, b in zip(voting, calibrated, strict=True)
                        if a.p_up != b.p_up or a.abstain != b.abstain
                    }
                )
                step(
                    6,
                    "done",
                    f"A35 scored {newly} newly matured prediction(s) ({scores.n_scored} scored, "
                    f"{scores.n_pending} waiting); tempered: {', '.join(tempered) or 'none'}; "
                    + (
                        f"N_eff {n_eff:.1f} from forecast correlations"
                        if n_eff is not None
                        else "N_eff stand-in (teams present) until enough overlap"
                    ),
                )
            else:
                step(
                    6,
                    "done",
                    "A35 FAILED: raw probabilities used and A40 counts it as a red flag (fail safe)",
                )
        else:
            step(6, "skipped", "A35 not running in this phase: raw probabilities used")

        # 7 Pool and pre-screen (A47 from Phase 4; equal-weight combiner before)
        two_stage = phase >= agg.two_stage_from_phase and "A47" in active_ids
        pools: dict[str, PoolResult] = {}
        votes_by_symbol: dict[str, list[AgentPrediction]] = {}
        for symbol in tradable:
            votes_by_symbol[symbol] = [p for p in calibrated if p.symbol == symbol]
            pools[symbol] = self.a47.pool(
                symbol,
                votes_by_symbol[symbol],
                cfg,
                two_stage=two_stage,
                n_eff=n_eff,
                weights=weights,
            )

        def sigma(symbol: str) -> float | None:
            forecast = context.vol(symbol)
            return forecast.sigma_daily if forecast is not None else None

        def round_trip(symbol: str) -> float | None:
            """A09's cost estimate as a round trip (fees + estimated slippage, both sides)."""
            liq = context.liq(symbol)
            if liq is None:
                return None
            return 2.0 * (cfg.costs.fee_bps + liq.est_cost_bps) / 1e4

        prelim = {
            s: go_decision(
                pools[s],
                sigma_daily=sigma(s),
                agg=agg,
                costs=cfg.costs,
                phase=phase,
                p_no_trade=None,
                blocks=(),
                round_trip_cost=round_trip(s),
            )
            for s in tradable
        }
        candidates = [s for s in tradable if prelim[s].go]
        combiner = (
            "A47 two-stage log-odds pooling"
            if two_stage
            else "equal-weight combiner standing in for A47 (Phase 4)"
        )
        step(
            7,
            "done" if two_stage else "stand-in",
            f"{combiner}; candidates: {', '.join(candidates) or 'none'}",
        )

        # 8 Challenge (debate layer parked; A40's final verdict)
        verdicts: dict[str, NoTradeVerdict] = {}
        for symbol in tradable:
            verdicts[symbol] = self.a40.verdict(
                cycle_id=cycle_id,
                symbol=symbol,
                health_score=health.score_0_100,
                vol=context.vol(symbol),
                disagreement=pools[symbol].disagreement,
                net_edge=prelim[symbol].net_edge if pools[symbol].n_agents else None,
                drawdown_used=drawdown / cfg.risk.max_drawdown_pct,
                cfg=cfg,
                regime=regime,
                liquidity=context.liq(symbol),
                round_trip_cost=round_trip(symbol),
                regime_failed="A06" in failures,
                scorekeeper_failed="A35" in failures,
            )
            publish("A40", "signals.notrade", verdicts[symbol])
        debate_available = phase >= agg.debate_live_from_phase and all(
            a in active_ids for a in DEBATE_AGENTS
        )
        blocked_by_a40 = [s for s in candidates if verdicts[s].p_no_trade >= agg.max_p_no_trade]
        step(
            8,
            "done" if debate_available else "stand-in",
            (
                "debate ran"
                if debate_available
                else "debate layer not live: every candidate is capped just below major size"
            )
            + f"; A40 blocked: {', '.join(blocked_by_a40) or 'none'}",
        )

        # 9 Decide (A47 writes the DecisionProposal)
        blocks: list[str] = []
        if health.action is not HealthAction.OK:
            blocks.append(f"A02 data health {health.action.value}")
        if not recon.ok:
            blocks.append("A05 reconciliation break")
        proposals: dict[str, DecisionProposal] = {}
        for i, symbol in enumerate(tradable):
            decision = go_decision(
                pools[symbol],
                sigma_daily=sigma(symbol),
                agg=agg,
                costs=cfg.costs,
                phase=phase,
                p_no_trade=verdicts[symbol].p_no_trade,
                blocks=blocks,
                round_trip_cost=round_trip(symbol),
            )
            proposals[symbol] = self.a47.propose(
                decision_id=f"{cycle_id}-D{i:03d}",
                cycle_id=cycle_id,
                pool=pools[symbol],
                decision=decision,
                predictions=votes_by_symbol[symbol],
                cfg=cfg,
            )
            publish("A47" if two_stage else "A46", "decision.proposal", proposals[symbol])
        go_symbols = [s for s, p in proposals.items() if p.go]
        step(
            9,
            "done" if two_stage else "stand-in",
            f"GO: {', '.join(go_symbols) or 'none'}; {len(tradable) - len(go_symbols)} symbol(s) with a reasoned no-trade",
        )

        # 10 Construct (A48 sizes; A45 stresses the result and can only shrink entries)
        atr = {s: features.get(s)["atr_14"] for s in tradable if "atr_14" in features.get(s)}
        max_notional = {x.symbol: x.max_order_notional for x in liquidity} if liquidity else None

        def construct(scale: float) -> tuple[TargetPortfolio, list[OrderIntent]]:
            return self.a48.construct(
                cycle_id=cycle_id,
                proposals=proposals,
                positions=ledger.book.quantities(),
                prices=prices,
                atr=atr,
                equity=equity,
                cfg=cfg,
                debate_available=debate_available,
                max_notional=max_notional,
                risk_scale=scale,
            )

        target, intents = construct(1.0)
        stress: StressReport | None = None
        stress_note = ""
        if "A45" in active_ids:
            held = ledger.book.quantities()

            def books(t: TargetPortfolio) -> tuple[dict[str, float], dict[str, float]]:
                """(book after exits only, book after exits AND new entries)."""
                after = {p.symbol: p.target_qty for p in t.positions}
                return {s: q for s, q in after.items() if s in held}, after

            def stress_test(t: TargetPortfolio, orders: list[OrderIntent]) -> StressReport:
                stops = dict(broker.stops)
                stops.update({i.symbol: i.stop_price for i in orders if i.stop_price is not None})
                base, after = books(t)
                return self.a45.assess(
                    cycle_id=cycle_id,
                    view=view,
                    before=base,
                    after=after,
                    prices=prices,
                    stops=stops,
                    equity=equity,
                    drawdown_pct=drawdown,
                    context=context,
                    cfg=cfg,
                )

            stress = self._guard(failures, "A45", lambda: stress_test(target, intents), None)
            # Fail safe: if the stress test breaks, no new entries this cycle.
            scale = stress.entry_scale if stress is not None else 0.0
            if scale < 1.0 and any(i.stop_price is not None for i in intents):
                target, intents = construct(scale)
                if stress is not None:
                    # Re-check the book that will actually be sent; never trust the estimate.
                    final = self._guard(failures, "A45", lambda: stress_test(target, intents), None)
                    over = final is None or (
                        final.tail_loss_pct > final.budget_pct + 1e-9
                        and final.tail_loss_pct > final.tail_loss_before_pct + 1e-9
                    )
                    if over:
                        target, intents = construct(0.0)
                    stress = stress.model_copy(
                        update={
                            "tail_loss_final_pct": (
                                final.tail_loss_before_pct
                                if over and final is not None
                                else (final.tail_loss_pct if final is not None else None)
                            ),
                            "entry_scale": 0.0 if over else stress.entry_scale,
                        }
                    )
            if stress is not None:
                publish("A45", "risk.stress", stress)
                final_tail = (
                    stress.tail_loss_final_pct
                    if stress.tail_loss_final_pct is not None
                    else stress.tail_loss_pct
                )
                stress_note = (
                    f"; A45 tail loss {final_tail:.2f}% vs {stress.budget_pct:g}% budget, "
                    f"entries x{stress.entry_scale:.2f}"
                )
            else:
                stress_note = "; A45 FAILED: no new entries (fail safe)"
        publish("A48", "portfolio.target", target)
        for intent in intents:
            publish("A48", "orders.intent", intent)
        step(
            10,
            "done",
            f"{len(intents)} order intent(s); {'; '.join(target.notes) or 'no notes'}{stress_note}",
        )

        # 11 Gate (A49 has the last word)
        inputs = RiskInputs(
            equity=equity,
            cash=ledger.book.cash,
            positions=ledger.book.quantities(),
            prices=prices,
            data_health=health.score_0_100,
            quorum=quorum,
            kill_switch_engaged=self.kill_switch.engaged,
            reconciliation_ok=recon.ok,
            daily_loss_pct=daily,
            weekly_loss_pct=weekly,
            drawdown_pct=drawdown,
            transition_alert=context.transition_alert,
            novelty_high=context.novelty_score >= 0.5,
        )
        verdict = self.a49.review(cycle_id, intents, inputs)
        publish("A49", "risk.verdict", verdict)
        if verdict.level is DegradationLevel.HALTED and not self.kill_switch.engaged:
            state = self.kill_switch.engage("; ".join(verdict.level_reasons), by="A49")
            publish(
                "A49",
                "ops.killswitch",
                KillSwitchEvent(engaged=True, reason=state.reason, by=state.by),
            )
        approved = [
            (intent, result)
            for intent, result in zip(intents, verdict.results, strict=True)
            if result.approved_qty > 0
        ]
        step(
            11,
            "done",
            f"level {verdict.level.value} ({'; '.join(verdict.level_reasons)}); {len(approved)}/{len(intents)} intent(s) approved",
        )

        # 12 Execute (A50 paper broker; fills at the next session's open)
        orders = [
            intent.model_copy(update={"qty": result.approved_qty}) for intent, result in approved
        ]
        broker.submit(orders, as_of)
        next_day = market.next_date(as_of)
        exec_fills: list[Fill] = []
        if self.simulate_next_open and next_day is not None:
            next_opens = {s: market.bar(s, next_day).open for s in market.symbols}
            exec_fills = broker.fill_pending(
                {s: o for s, o in next_opens.items() if math.isfinite(o) and o > 0}, next_day
            )
            where = f"filled at the {next_day.isoformat()} open (simulated paper fill)"
        else:
            where = "queued for the next session's open"
        for fill in exec_fills:
            publish("A50", "orders.fills", fill)
        step(
            12,
            "done",
            f"{len(orders)} order(s) sent to the paper broker; {len(exec_fills)} {where}",
        )

        # 13 Record (A05 ledger, A46 trade journal)
        for fill in exec_fills:
            ledger.record(fill)
        recon_after = reconcile(ledger, broker)
        account.record_equity(as_of, equity)
        by_intent = {r.intent_id: r for r in verdict.results}
        snapshot_hash = sid
        records: list[TradeDecisionRecord] = []
        for intent in intents:
            if intent.decision_id is None:
                continue
            proposal = next(p for p in proposals.values() if p.decision_id == intent.decision_id)
            result = by_intent[intent.intent_id]
            fills = tuple(f for f in exec_fills if f.intent_id == intent.intent_id)
            outcome = (
                "filled" if fills else ("queued" if result.approved_qty > 0 else "rejected by A49")
            )
            record = TradeDecisionRecord(
                decision_id=intent.decision_id,
                cycle_id=cycle_id,
                as_of=as_of,
                snapshot_hash=snapshot_hash,
                prediction_ids=proposal.rationale_ids,
                proposal=proposal,
                risk_check_id=result.risk_check_id,
                order=intent,
                fills=fills,
                outcome=outcome,
            )
            records.append(record)
            self.audit.append("trade_decision", record.model_dump(mode="json"))
        step(
            13,
            "done",
            f"{len(records)} trade decision record(s); reconciliation {'ok' if recon_after.ok else 'BREAK'}; equity {equity:,.2f} {cfg.system.base_currency} at the {as_of.isoformat()} close",
        )

        # 14 Watch
        step(
            14,
            "done",
            f"{len(broker.stops)} resting stop(s); {len(broker.pending)} queued order(s); kill switch {'ENGAGED' if self.kill_switch.engaged else 'armed'}",
        )

        # 15 Learn (A35 stores every sealed prediction, raw, for scoring when it matures)
        self.audit.append(
            "predictions",
            {"cycle_id": cycle_id, "predictions": [p.model_dump(mode="json") for p in revealed]},
        )
        if "A35" in active_ids:
            labels = {x.symbol: x.label for x in regime.symbols} if regime is not None else {}

            def learn_now() -> int:
                stored = self.a35.record(revealed, as_of=as_of, voters=voters, regimes=labels)
                for symbol, pool in pools.items():
                    if pool.n_agents:
                        self.a35.record_pooled(symbol, as_of, pool.p_up, agg.decision_horizon_days)
                return stored

            stored = self._guard(failures, "A35", learn_now, None)
            learn = (
                f"A35 stored {stored} sealed prediction(s) for scoring when their horizons mature"
                if stored is not None
                else "A35 FAILED to store predictions; they are still in the audit log"
            )
        else:
            learn = f"{len(revealed)} sealed prediction(s) written to the audit log"
        step(15, "done", learn)

        return CycleReport(
            cycle_id=cycle_id,
            as_of=as_of,
            phase=phase,
            snapshot=snapshot,
            steps=tuple(steps),
            health=health,
            reconciliation=recon_after,
            context=context,
            predictions=tuple(revealed),
            seal_rejections=rejections,
            context_failures=failures,
            quorum=quorum,
            no_trade=tuple(verdicts[s] for s in tradable),
            proposals=tuple(proposals[s] for s in tradable),
            target=target,
            intents=tuple(intents),
            risk=verdict,
            scores=scores,
            stress=stress,
            fills=tuple(early_fills + exec_fills),
            records=tuple(records),
            equity=equity,
            cash=ledger.book.cash,
            positions=ledger.book.quantities(),
            stops=dict(sorted(broker.stops.items())),
            kill_switch_engaged=self.kill_switch.engaged,
            audit_head=self.audit.head,
        )
