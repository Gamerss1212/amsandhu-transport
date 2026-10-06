"""Command line: `quantagents <command>` (or `python -m quantagents <command>`).

Run from the repo root. Everything is paper trading; no command can send a real order.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import date
from pathlib import Path

import numpy as np

from quantagents import __version__
from quantagents.agents.a35_scorekeeper import Scorekeeper
from quantagents.agents.a45_stress import stress_returns
from quantagents.audit import AuditLog, read_records, verify_chain
from quantagents.backtest.engine import Backtester
from quantagents.backtest.event import EventBacktester, EventCosts
from quantagents.backtest.strategies import DEFAULT_VARIANT, strategy_grid
from quantagents.config import AppConfig, load_config
from quantagents.data import commands as data_commands
from quantagents.data.store import data_labels
from quantagents.data.synthetic import DEMO_AS_OF, synthetic_market
from quantagents.execution.paper import PaperAccount
from quantagents.lots import acb_report
from quantagents.market import MarketData, load_csv, save_csv
from quantagents.orchestrator import Orchestrator
from quantagents.registry import Registry
from quantagents.report import (
    DISCLAIMER,
    format_backtest,
    format_cycle_report,
    format_event_backtest,
    format_registry,
    format_simulation,
    format_strategy_stress,
    format_validation,
)
from quantagents.risk.killswitch import RESET_PHRASE, KillSwitch
from quantagents.simulate import run_paper_simulation
from quantagents.validation.leakage import RedTeamAuditor
from quantagents.validation.stats import StatisticalValidator

STATE_DIR = Path("state")
RUNS_DIR = Path("runs")
ACCOUNT_FILE = STATE_DIR / "paper_account.json"
KILL_FILE = STATE_DIR / "kill_switch.json"
SCORES_FILE = STATE_DIR / "scorekeeper.json"


def _config(args: argparse.Namespace) -> AppConfig:
    path = Path(args.config) if args.config else Path("config/default.yaml")
    return load_config(path if path.exists() else None)


def _market(args: argparse.Namespace, cfg: AppConfig) -> MarketData:
    if getattr(args, "data", None):
        _data_note(args.data)
        return load_csv(args.data)
    return synthetic_market(seed=cfg.system.seed)


def _universe_note(cfg: AppConfig, market: MarketData) -> None:
    """Say so plainly when the config's universe leaves nothing in the file to trade."""
    wanted = set(cfg.universe.symbols)
    if wanted and not wanted & set(market.symbols):
        print(
            f"Note: none of this file's symbols ({', '.join(market.symbols[:8])}) are in "
            f"universe.symbols in the config ({', '.join(sorted(wanted)[:8])}), so nothing can "
            "trade. Put your symbols there, or use [] to trade every symbol in the file.\n"
        )


def _data_note(path: str) -> None:
    """Every result on real data carries its source's caveats (spec sections 58, 74)."""
    for label in data_labels(path):
        print(f"Data {Path(path).name}: {label}")
    print()


def cmd_demo(args: argparse.Namespace) -> int:
    cfg = _config(args)
    market = synthetic_market(seed=cfg.system.seed)
    as_of = date.fromisoformat(args.as_of)
    account = PaperAccount(cfg.system.capital, cfg.costs)
    audit_path = RUNS_DIR / f"demo-{as_of.isoformat()}" / "audit.jsonl" if args.save else None
    if audit_path is not None and audit_path.exists():
        audit_path.unlink()
    orchestrator = Orchestrator(
        cfg, Registry.load(), account, KillSwitch(), audit=AuditLog(audit_path)
    )
    report = orchestrator.run_cycle(market, as_of)
    print("Demo on SYNTHETIC data (fake symbols SYN_A..SYN_F) with a fresh 10,000 paper account.\n")
    print(format_cycle_report(report, currency=cfg.system.base_currency))
    if audit_path is not None:
        (audit_path.parent / "report.json").write_text(
            report.model_dump_json(indent=2), encoding="utf-8"
        )
        print(f"\nSaved the report and audit log to {audit_path.parent}")
    return 0


def cmd_cycle(args: argparse.Namespace) -> int:
    cfg = _config(args)
    _data_note(args.data)
    market = load_csv(args.data)
    _universe_note(cfg, market)
    as_of = date.fromisoformat(args.as_of) if args.as_of else market.dates[-1]
    state = Path(args.state)
    scores_path = state.with_name(SCORES_FILE.name)
    account = PaperAccount.load_or_new(state, cfg.system.capital, cfg.costs)
    scorekeeper = Scorekeeper.load_or_new(scores_path)
    orchestrator = Orchestrator(
        cfg,
        Registry.load(),
        account,
        KillSwitch(KILL_FILE),
        audit=AuditLog(RUNS_DIR / "audit.jsonl"),
        scorekeeper=scorekeeper,
        simulate_next_open=False,
    )
    report = orchestrator.run_cycle(market, as_of)
    account.save(state)
    scorekeeper.save(scores_path)
    out = RUNS_DIR / "cycles" / f"{report.cycle_id}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
    print(format_cycle_report(report, currency=cfg.system.base_currency))
    print(f"\nSaved account state to {state}, A35 memory to {scores_path}, report to {out}")
    return 0


def cmd_simulate(args: argparse.Namespace) -> int:
    cfg = _config(args)
    market = _market(args, cfg)
    _universe_note(cfg, market)
    end = date.fromisoformat(args.end) if args.end else None
    sim = run_paper_simulation(cfg, Registry.load(), market, days=args.days, end=end)
    if not getattr(args, "data", None):
        print("SYNTHETIC data (fake symbols): this shows the machinery working, not an edge.\n")
    print(format_simulation(sim, currency=cfg.system.base_currency))
    return 0


def cmd_stress(args: argparse.Namespace) -> int:
    cfg = _config(args)
    market = _market(args, cfg)
    variants = dict(strategy_grid(args.strategy, cfg))
    name = args.variant or DEFAULT_VARIANT[args.strategy]
    if name not in variants:
        raise KeyError(f"unknown variant {name!r}; choose from {sorted(variants)}")
    base = Backtester(cfg.costs.one_way_cost).run(market, variants[name](market), name=name)
    doubled = Backtester(2 * cfg.costs.one_way_cost).run(market, variants[name](market), name=name)
    result = stress_returns(
        base.returns, ruin_drawdown=cfg.risk.max_drawdown_pct / 100.0, seed=cfg.system.seed
    )
    note = (
        f"2x cost stress: Sharpe {base.metrics['sharpe']:.2f} -> {doubled.metrics['sharpe']:.2f}, "
        f"total return {base.metrics['total_return']:+.1%} -> {doubled.metrics['total_return']:+.1%}"
    )
    print(format_backtest(base))
    print(format_strategy_stress(name, result, note))
    print(f"\n{DISCLAIMER}")
    return 0


def cmd_backtest(args: argparse.Namespace) -> int:
    cfg = _config(args)
    market = _market(args, cfg)
    variants = dict(strategy_grid(args.strategy, cfg))
    name = args.variant or DEFAULT_VARIANT[args.strategy]
    if name not in variants:
        raise KeyError(f"unknown variant {name!r}; choose from {sorted(variants)}")
    if args.engine == "event":
        event = EventBacktester(EventCosts.from_config(cfg), cfg.system.capital).run(
            market, variants[name](market), name=name
        )
        print(format_event_backtest(event, cfg.system.base_currency))
    else:
        result = Backtester(cfg.costs.one_way_cost).run(market, variants[name](market), name=name)
        print(format_backtest(result))
    print(f"\n{DISCLAIMER}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    cfg = _config(args)
    market = _market(args, cfg)
    grid = strategy_grid(args.strategy, cfg)
    chosen = args.variant or DEFAULT_VARIANT[args.strategy]
    engine = Backtester(cfg.costs.one_way_cost)
    results = {name: engine.run(market, factory(market), name=name) for name, factory in grid}
    if chosen not in results:
        raise KeyError(f"unknown variant {chosen!r}; choose from {sorted(results)}")
    stressed = Backtester(2 * cfg.costs.one_way_cost).run(
        market, dict(grid)[chosen](market), name=chosen
    )
    matrix = np.column_stack([r.returns for r in results.values()]) if len(results) > 1 else None
    notes = [f"{len(grid)} variant(s) tried in this family; every one counts as a trial."]
    if not getattr(args, "data", None):
        notes.append("Synthetic data: a PASS or FAIL here proves nothing about real markets.")
    report = StatisticalValidator(cfg.validation).validate(
        results[chosen].returns,
        strategy=chosen,
        n_trials=len(grid),
        trial_matrix=matrix,
        stressed_returns=stressed.returns,
        notes=notes,
        seed=cfg.system.seed,
    )
    red_team = RedTeamAuditor(max_gross=cfg.risk.max_gross_exposure_pct / 100.0).audit(
        dict(grid)[chosen], market, name=chosen
    )
    print(format_backtest(results[chosen]))
    print(format_validation(report, red_team))
    print(f"\n{DISCLAIMER}")
    return 0


def cmd_agents(args: argparse.Namespace) -> int:
    print(format_registry(Registry.load(), args.phase, core_only=args.core))
    return 0


def cmd_killswitch(args: argparse.Namespace) -> int:
    switch = KillSwitch(KILL_FILE)
    if args.action == "engage":
        state = switch.engage(args.reason or "manual stop", by="human")
        print(f"Kill switch ENGAGED: {state.reason}")
    elif args.action == "reset":
        switch.reset(args.confirm or "", by="human")
        print("Kill switch reset. Trading may resume on the next cycle.")
    else:
        state = switch.state()
        print(
            f"Kill switch {'ENGAGED' if state.engaged else 'armed (not engaged)'}"
            + (f": {state.reason} (by {state.by} at {state.at_utc})" if state.engaged else "")
        )
        if state.engaged:
            print(f"To reset after review: quantagents killswitch reset --confirm {RESET_PHRASE}")
    return 0


def cmd_config(args: argparse.Namespace) -> int:
    cfg = _config(args)
    s, r = cfg.system, cfg.risk
    print("Config is valid.")
    print(
        f"Phase {s.phase} | mode {s.execution_mode.value} | autonomy {s.autonomy_level} | capital {s.capital:,.0f} {s.base_currency}"
    )
    print(
        f"Risk per trade {r.max_risk_per_trade_pct}% (major at {r.major_trade_risk_pct}%) | daily {r.max_daily_loss_pct}% | weekly {r.max_weekly_loss_pct}% | drawdown {r.max_drawdown_pct}%"
    )
    print(
        f"Leverage {'on' if r.leverage_allowed else 'off'} | shorting {'on' if r.shorting_allowed else 'off'} | universe {', '.join(cfg.universe.symbols)}"
    )
    return 0


def cmd_make_data(args: argparse.Namespace) -> int:
    cfg = _config(args)
    save_csv(synthetic_market(seed=cfg.system.seed), args.out)
    print(f"Wrote synthetic prices to {args.out} (fake symbols, for testing only)")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    ok, message = verify_chain(read_records(Path(args.path)))
    print(("OK: " if ok else "TAMPERED: ") + message)
    return 0 if ok else 1


def cmd_acb(args: argparse.Namespace) -> int:
    cfg = _config(args)
    account = PaperAccount.load_or_new(Path(args.state), cfg.system.capital, cfg.costs)
    print(json.dumps(acb_report(account.ledger.fills).model_dump(mode="json"), indent=2))
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="quantagents", description="QuantAgents-50 starter kit (paper trading only)."
    )
    parser.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    parser.add_argument("--config", help="config YAML (default: config/default.yaml)")
    sub = parser.add_subparsers(dest="command", required=True)

    p = sub.add_parser("demo", help="run one decision cycle on synthetic data")
    p.add_argument("--as-of", default=DEMO_AS_OF.isoformat())
    p.add_argument("--save", action="store_true", help="save the report and audit log under runs/")
    p.set_defaults(func=cmd_demo)

    p = sub.add_parser("cycle", help="run one paper-trading cycle on your CSV data")
    p.add_argument("--data", required=True, help="CSV: date,symbol,open,high,low,close,volume")
    p.add_argument("--as-of", help="defaults to the last date in the file")
    p.add_argument("--state", default=str(ACCOUNT_FILE))
    p.set_defaults(func=cmd_cycle)

    p = sub.add_parser("simulate", help="run the full cycle day by day on a fresh paper account")
    p.add_argument("--days", type=int, default=120, help="trading days to simulate")
    p.add_argument("--end", help="last decision date (default: the second-to-last date)")
    p.add_argument("--data", help="CSV data (default: synthetic)")
    p.set_defaults(func=cmd_simulate)

    for name, func, text in (
        ("backtest", cmd_backtest, "backtest a strategy (A43)"),
        (
            "validate",
            cmd_validate,
            "backtest every variant, then run A44 statistics and the A39 red team",
        ),
        ("stress", cmd_stress, "A45 Monte Carlo and 2x-cost stress of a strategy"),
    ):
        p = sub.add_parser(name, help=text)
        p.add_argument("--strategy", default="tsmom", choices=sorted(DEFAULT_VARIANT))
        p.add_argument("--variant", help="one named variant (default: the family's preset)")
        p.add_argument("--data", help="CSV data (default: synthetic)")
        if name == "backtest":
            p.add_argument(
                "--engine",
                choices=["vector", "event"],
                default="vector",
                help="vector: fast screening; event: orders, partial fills, impact, ADV cap",
            )
        p.set_defaults(func=func)

    p = sub.add_parser("agents", help="list the agent roster (25 core + 25 parked)")
    p.add_argument("--phase", type=int, help="only agents switched on by this phase")
    p.add_argument("--core", action="store_true", help="only the 25-agent core")
    p.set_defaults(func=cmd_agents)

    p = sub.add_parser("killswitch", help="status, engage or reset the kill switch")
    p.add_argument("action", choices=["status", "engage", "reset"])
    p.add_argument("--reason")
    p.add_argument("--confirm", help=f"type {RESET_PHRASE} to reset")
    p.set_defaults(func=cmd_killswitch)

    p = sub.add_parser("config", help="validate the config and print a summary")
    p.set_defaults(func=cmd_config)

    p = sub.add_parser("make-data", help="write synthetic prices to a CSV")
    p.add_argument("--out", default="data/synthetic.csv")
    p.set_defaults(func=cmd_make_data)

    p = sub.add_parser("audit", help="verify the audit log hash chain")
    p.add_argument("--path", default=str(RUNS_DIR / "audit.jsonl"))
    p.set_defaults(func=cmd_audit)

    data_commands.add_parser(sub)

    p = sub.add_parser("acb", help="adjusted cost base report from paper fills (not tax advice)")
    p.add_argument("--state", default=str(ACCOUNT_FILE))
    p.set_defaults(func=cmd_acb)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result: int = args.func(args)
    except (ValueError, KeyError, LookupError, FileNotFoundError, PermissionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    return result
