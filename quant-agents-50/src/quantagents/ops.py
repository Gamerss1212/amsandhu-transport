"""Everyday operations: ``quantagents status`` (one-screen dashboard) and ``quantagents doctor``.

Both only read files. Neither can trade, change a limit or reset the kill switch.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from dataclasses import dataclass, field
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

from quantagents.config import AppConfig, ExecutionMode, load_config
from quantagents.execution.live import mirror_summary
from quantagents.execution.paper import PaperAccount
from quantagents.market import load_csv
from quantagents.risk.killswitch import RESET_PHRASE, KillSwitch
from quantagents.validation.trials import TRIALS_FILE
from quantagents.watchdog import check as watchdog_check

PAPER_DAYS_NEEDED = 30  # Phase 3 acceptance


def cycle_records(runs_dir: Path) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for path in (runs_dir / "cycles").glob("*.json"):
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if isinstance(data, dict) and "as_of" in data:
            data["_ran"] = datetime.fromtimestamp(path.stat().st_mtime, UTC)
            out.append(data)
    return sorted(out, key=lambda d: (str(d["as_of"]), d["_ran"]))


def last_daily_lines(log: Path) -> list[str]:
    if not log.exists():
        return []
    lines = log.read_text(encoding="utf-8", errors="replace").splitlines()
    starts = [i for i, line in enumerate(lines) if line.startswith("=== daily run")]
    if not starts:
        return []
    block = lines[starts[-1] :]
    return [block[0].removeprefix("=== daily run ").strip()] + [
        line.removeprefix("--- ") for line in block if line.startswith("--- ")
    ]


def hold_return(cycles: list[dict[str, Any]], data: Path | None) -> tuple[float, int, str] | None:
    """Return of holding the first paper day's symbols in equal parts, first day to newest.

    Uses the data file when it covers both days (its prices are adjusted the same way end to
    end); otherwise the closes saved in the two cycle records. No fees, no rebalancing.
    """
    first, last = cycles[0], cycles[-1]
    start, end = date.fromisoformat(str(first["as_of"])), date.fromisoformat(str(last["as_of"]))
    begin = {str(k): float(v) for k, v in first.get("snapshot", {}).get("last_close", {}).items()}
    if data is not None and data.exists():
        try:
            market = load_csv(data)
            if market.has_date(start) and market.has_date(end):
                i, j = market.index_of(start), market.index_of(end)
                ratios = [
                    float(market.bars(s).close[j] / market.bars(s).close[i])
                    for s in sorted(begin)
                    if s in market.symbols
                ]
                if ratios:
                    return sum(ratios) / len(ratios) - 1.0, len(ratios), data.name
        except (OSError, ValueError, KeyError):
            pass  # fall back to the closes saved with the cycles
    now = {str(k): float(v) for k, v in last.get("snapshot", {}).get("last_close", {}).items()}
    ratios = [now[s] / p for s, p in sorted(begin.items()) if s in now and p > 0]
    if not ratios:
        return None
    return sum(ratios) / len(ratios) - 1.0, len(ratios), "the cycle records"


def score_series(
    cycles: list[dict[str, Any]], data: Path | None, capital: float
) -> list[tuple[str, float, float | None]]:
    """Per paper day: (date, paper return, return of holding the first day's symbols equally).

    Paper comes from each cycle's equity. Holding uses the data file when it has every day
    (consistent adjusted prices), otherwise the closes saved with the cycles.
    """
    by_day: dict[str, dict[str, Any]] = {}
    for record in cycles:  # sorted oldest first, so a re-run of a day replaces it
        by_day[str(record["as_of"])] = record
    days = sorted(by_day)
    if not days or capital <= 0:
        return []
    symbols = sorted(by_day[days[0]].get("snapshot", {}).get("last_close", {}))
    closes: dict[str, dict[str, float]] = {
        d: {
            str(k): float(v) for k, v in by_day[d].get("snapshot", {}).get("last_close", {}).items()
        }
        for d in days
    }
    if data is not None and data.exists():
        try:
            market = load_csv(data)
            if all(market.has_date(date.fromisoformat(d)) for d in days):
                closes = {
                    d: {
                        s: float(market.bars(s).close[market.index_of(date.fromisoformat(d))])
                        for s in symbols
                        if s in market.symbols
                    }
                    for d in days
                }
        except (OSError, ValueError, KeyError):
            pass  # keep the closes saved with the cycles
    start = closes[days[0]]
    out: list[tuple[str, float, float | None]] = []
    for d in days:
        paper = float(by_day[d].get("equity", capital)) / capital - 1.0
        ratios = [
            closes[d][s] / start[s] for s in symbols if s in closes[d] and start.get(s, 0) > 0
        ]
        out.append((d, paper, sum(ratios) / len(ratios) - 1.0 if ratios else None))
    return out


def scoreboard(cycles: list[dict[str, Any]], data: Path | None, paper: float) -> str | None:
    """One honest line: the paper account against simply holding the same symbols."""
    if not cycles:
        return None
    hold = hold_return(cycles, data)
    if hold is None:
        return None
    held, n, source = hold
    days = len({str(c["as_of"]) for c in cycles})
    gap = (paper - held) * 100.0
    verdict = "ahead of" if gap > 0.005 else "behind" if gap < -0.005 else "level with"
    return (
        f"Scoreboard since {cycles[0]['as_of']} ({days} paper day{'s' if days != 1 else ''}): "
        f"paper {paper:+.2%} vs holding the same {n} symbol{'s' if n != 1 else ''} in equal parts "
        f"{held:+.2%} (no fees; prices from {source}). Paper is {verdict} holding"
        + (f" by {abs(gap):.2f} points." if verdict != "level with" else ".")
    )


def status_report(
    cfg: AppConfig,
    *,
    config_path: str,
    state_file: Path,
    kill_file: Path,
    runs_dir: Path,
    data: Path | None,
    today: date,
) -> list[str]:
    s = cfg.system
    lines = [
        f"QuantAgents status ({datetime.now(UTC):%Y-%m-%d %H:%M} UTC)",
        "",
        f"Mode: {s.execution_mode.value} | phase {s.phase} | autonomy {s.autonomy_level} | "
        f"live trading: {'APPROVED' if s.live_trading_approved else 'not approved'}",
        f"Config: {config_path} | universe: {', '.join(cfg.universe.symbols) or '(every symbol in the file)'}",
    ]
    if cfg.universe.symbols and all(x.startswith("SYN_") for x in cfg.universe.symbols):
        lines.append(
            "  Note: that is the synthetic demo universe. Real symbols go in your own config."
        )
    switch = KillSwitch(kill_file).state()
    lines.append(
        f"Kill switch: ENGAGED - {switch.reason} (by {switch.by}, {switch.at_utc})"
        if switch.engaged
        else "Kill switch: armed (not engaged)"
    )
    if switch.engaged:
        lines.append(f"  After review: quantagents killswitch reset --confirm {RESET_PHRASE}")

    cycles = cycle_records(runs_dir)
    last = cycles[-1] if cycles else None
    prices = {
        str(k): float(v) for k, v in (last or {}).get("snapshot", {}).get("last_close", {}).items()
    }
    lines += ["", "Paper account"]
    if not state_file.exists():
        lines.append(f"  No paper account yet ({state_file} appears after the first cycle).")
    else:
        account = PaperAccount.load_or_new(state_file, s.capital, cfg.costs)
        book = account.ledger.book
        equity = (
            book.equity(prices)
            if prices
            else (account.equity_history[-1][1] if account.equity_history else book.cash)
        )
        peak = max([account.capital, equity, *(e for _, e in account.equity_history)])
        lines.append(
            f"  Equity {equity:,.2f} {s.base_currency} (start {account.capital:,.0f}, "
            f"{equity / account.capital - 1:+.2%}) | cash {book.cash:,.2f} | "
            f"drawdown {max(0.0, 1 - equity / peak):.2%} from peak | fees paid {book.fees_paid:,.2f}"
        )
        board = scoreboard(cycles, data, equity / account.capital - 1.0)
        if board:
            lines.append(f"  {board}")
        positions = {k: v for k, v in book.quantities().items() if v}
        if not positions:
            lines.append("  No open positions.")
        for symbol, qty in sorted(positions.items()):
            price = prices.get(symbol)
            value = f"{qty * price:,.2f} ({qty * price / equity:.1%})" if price else "price unknown"
            lines.append(f"  {symbol}: {qty:g} units, value {value}")
        lines.append(
            f"  Fills so far: {len(account.ledger.fills)} | pending orders: {len(account.broker.pending)}"
        )

    lines += ["", "Cycles"]
    if last is None:
        lines.append("  No paper cycle has run yet.")
    else:
        risk = last.get("risk", {})
        go = sum(1 for p in last.get("proposals", []) if p.get("go"))
        lines.append(
            f"  Last: as of {last['as_of']} (ran {last['_ran']:%Y-%m-%d %H:%M} UTC) | level "
            f"{risk.get('level', '?')} | GO {go} | order intents {len(last.get('intents', []))} | "
            f"data health {last.get('health', {}).get('score_0_100', '?')}"
        )
        days = {str(c["as_of"]) for c in cycles}
        halted = sum(1 for c in cycles if c.get("risk", {}).get("level") == "HALTED")
        breaks = sum(1 for c in cycles if not c.get("reconciliation", {}).get("ok", True))
        lines.append(
            f"  Paper days: {len(days)} of {PAPER_DAYS_NEEDED} for Phase 3 | halted cycles: "
            f"{halted} | reconciliation breaks: {breaks}"
        )
    daily = last_daily_lines(runs_dir / "daily.log")
    if daily:
        lines.append(f"  Last daily run {daily[0]}: " + "; ".join(daily[1:]))
    problems = (
        watchdog_check(runs_dir=runs_dir, state_file=state_file, data=data, today=today)
        if cycles or data
        else []
    )
    lines += [
        "",
        "Watchdog (check only, nothing engaged): " + ("all clear" if not problems else ""),
    ]
    lines += [f"  - {p}" for p in problems]
    real = 0
    if TRIALS_FILE.exists():
        rows = [
            r for r in TRIALS_FILE.read_text(encoding="utf-8").splitlines() if r.startswith("| 20")
        ]
        real = sum(1 for r in rows if "| synthetic" not in r)
    lines += [
        "",
        f"Research: {real} real-data trial rows in {TRIALS_FILE}. Strategies passing every check: none so far.",
    ]
    lines += ["", "Real money"]
    if s.execution_mode is ExecutionMode.LIVE:
        lines.append(
            f"  Live mode is ON in the config (budget {cfg.live.budget:,.2f}); every daily run "
            "tries a real-money sync. `quantagents live check` shows each gate."
        )
    else:
        lines.append("  OFF: paper only. `quantagents live check` shows what turning it on needs.")
    mirror = mirror_summary(state_file)
    if mirror:
        lines.append(f"  {mirror}")
    lines += ["", "Not financial advice."]
    return lines


@dataclass
class DoctorReport:
    ok: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def lines(self) -> list[str]:
        out = [f"[ok]    {m}" for m in self.ok]
        out += [f"[warn]  {m}" for m in self.warnings]
        out += [f"[ERROR] {m}" for m in self.errors]
        verdict = (
            "Everything needed is in place." if not self.errors else "Fix the errors above first."
        )
        return [*out, "", verdict]


def doctor(
    *, config_path: str | None, folders: tuple[str, ...] = ("data", "state", "runs")
) -> DoctorReport:
    r = DoctorReport()
    v = sys.version_info
    (r.ok if v >= (3, 11) else r.errors).append(
        f"Python {v.major}.{v.minor}.{v.micro} (3.11 or newer needed)"
    )
    for module, why, required in (
        ("numpy", "maths", True),
        ("pydantic", "messages", True),
        ("yaml", "config files", True),
        ("duckdb", "the data store", False),
        ("pyarrow", "the data store", False),
        ("ccxt", "crypto downloads", False),
    ):
        if importlib.util.find_spec(module) is not None:
            r.ok.append(f"{module} installed ({why})")
        elif required:
            r.errors.append(f"{module} missing ({why}): python -m pip install -e .")
        else:
            r.warnings.append(f'{module} missing ({why}): python -m pip install -e ".[data]"')
    path = Path(config_path) if config_path else Path("config/default.yaml")
    try:
        cfg = load_config(path if path.exists() else None)
    except Exception as exc:  # a broken config must be reported, not crash the doctor
        r.errors.append(f"config {path} is invalid: {exc}")
        return r
    r.ok.append(
        f"config {path} valid: {cfg.system.execution_mode.value} mode, risk per trade "
        f"{cfg.risk.max_risk_per_trade_pct}%, daily loss limit {cfg.risk.max_daily_loss_pct}%"
    )
    if cfg.system.live_trading_approved or cfg.system.execution_mode.value == "live":
        r.warnings.append("live trading settings are on: only the owner may do this (Phase 8)")
    if all(s.startswith("SYN_") for s in cfg.universe.symbols):
        r.warnings.append(
            "the universe is the synthetic demo (SYN_A...): copy config/us_etfs.example.yaml to "
            "config/my_universe.yaml for real symbols"
        )
    for folder in folders:
        try:
            Path(folder).mkdir(parents=True, exist_ok=True)
            probe = Path(folder) / ".write_test"
            probe.write_text("ok", encoding="utf-8")
            probe.unlink()
            r.ok.append(f"folder {folder}/ is writable")
        except OSError as exc:
            r.errors.append(f"folder {folder}/ is not writable ({exc})")
    switch = KillSwitch(Path("state/kill_switch.json")).state()
    if switch.engaged:
        r.warnings.append(f"kill switch ENGAGED: {switch.reason}")
    else:
        r.ok.append("kill switch armed (not engaged)")
    return r
