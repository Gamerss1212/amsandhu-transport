"""Write the two owner-facing spreadsheets: every strategy, and every bot's measured power.

    python scripts/export_lists.py            # writes docs/ALL_STRATEGIES.xlsx and docs/BOT_POWER.xlsx

Nothing here is invented. The strategy list is read from the strategy library in the code (backend/tradingai/strategies)
and the research-card catalogue; the bot list is read from the master agent's roster (engine/master.py), and each bot's
results are read from docs/AGENT_TRAINING_REPORT.md, which `scripts/train_agents.py` wrote from real market data.
Run `train_agents.py` again first if you want the numbers refreshed.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

from openpyxl import Workbook
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend"))

from tradingai.engine.master import PLAN, ROLES                        # noqa: E402
from tradingai.strategies import library as L                          # noqa: E402

DOCS = ROOT / "docs"
FONT = "Arial"
HEAD_FILL = PatternFill("solid", fgColor="1F3864")
HEAD_FONT = Font(name=FONT, bold=True, color="FFFFFF", size=10)
BODY = Font(name=FONT, size=10)
BOLD = Font(name=FONT, size=10, bold=True)
TITLE = Font(name=FONT, size=14, bold=True)
TRADABLE = {"crypto", "stock"}                  # the only markets this software trades (market/policy.py)
EVIDENCE = {"R": "research-supported", "C": "documented construction", "H": "hypothesis"}


# ----------------------------------------------------------------------------------------------- helpers

def table(ws, headers: list[str], rows: list[list], widths: list[int], wrap: set[int] = frozenset(),
          formats: dict[int, str] | None = None) -> None:
    """A filterable table with a frozen header. `wrap`: 0-based columns that wrap; `formats`: column -> number format."""
    ws.append(headers)
    for c in range(1, len(headers) + 1):
        cell = ws.cell(row=1, column=c)
        cell.font, cell.fill = HEAD_FONT, HEAD_FILL
        cell.alignment = Alignment(wrap_text=True, vertical="center")
        ws.column_dimensions[get_column_letter(c)].width = widths[c - 1]
    ws.row_dimensions[1].height = 32
    for r in rows:
        ws.append(r)
    for row in ws.iter_rows(min_row=2, max_row=ws.max_row):
        for i, cell in enumerate(row):
            cell.font = BODY
            cell.alignment = Alignment(wrap_text=i in wrap, vertical="top")
            if formats and i in formats and cell.value not in (None, ""):
                cell.number_format = formats[i]
    ws.freeze_panes = "B2"
    ws.auto_filter.ref = f"A1:{get_column_letter(len(headers))}{max(ws.max_row, 2)}"


def read_me(ws, title: str, lines: list[str]) -> None:
    ws.column_dimensions["A"].width = 120
    ws["A1"] = title
    ws["A1"].font = TITLE
    for i, text in enumerate(lines, start=3):
        c = ws.cell(row=i, column=1, value=text)
        c.font = BOLD if text.endswith(":") else BODY
        c.alignment = Alignment(wrap_text=True, vertical="top")
    ws.sheet_view.showGridLines = False


def fraction(text: str) -> float | None:
    t = text.strip()
    if t in ("", "-"):
        return None
    return float(t.rstrip("%")) / 100 if t.endswith("%") else float(t)


# ----------------------------------------------------------------------------------------------- bots

def parse_report() -> dict[str, dict]:
    """agent id -> the row of docs/AGENT_TRAINING_REPORT.md's 'Every agent' table."""
    out: dict[str, dict] = {}
    for line in (DOCS / "AGENT_TRAINING_REPORT.md").read_text(encoding="utf-8").splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) != 14 or not re.fullmatch(r"A\d{3}", cells[0]):
            continue
        (agent, market, data, chosen, val, test, ret, dd, trades, wf, dsr, pbo, verdict, version) = cells
        out[agent] = dict(market=market, data=data, chosen=chosen, val=fraction(val), test=fraction(test),
                          ret=fraction(ret), dd=fraction(dd), trades=int(trades), wf=fraction(wf),
                          dsr=fraction(dsr), pbo=fraction(pbo), verdict=verdict, version=version)
    return out


def agent_roles() -> dict[str, str]:
    return {f"A{n:03d}": role for role, lo, hi, _ in PLAN for n in range(lo, hi + 1)}


def group_name(role_key: str) -> str:
    return "Meme coins" if role_key.startswith("meme") else ("Crypto" if ROLES[role_key].market == "crypto" else "US stocks")


def bots_workbook() -> tuple[Workbook, dict]:
    report, roles = parse_report(), agent_roles()
    if len(report) != 100:
        raise SystemExit(f"expected 100 agents in AGENT_TRAINING_REPORT.md, found {len(report)}")
    rows, passed = [], 0
    for agent in sorted(report):
        r, role = report[agent], ROLES[roles[agent]]
        market, bar = re.match(r"(.+?) \((\w+)\)$", r["market"]).groups()
        allowed = r["verdict"] == "PAPER TEST"
        passed += allowed
        rows.append([agent, group_name(roles[agent]), role.label, market.split(":", 1)[-1], bar, role.family,
                     "\n".join(role.candidates), r["chosen"], r["val"], r["test"], r["ret"], r["dd"], r["trades"],
                     r["wf"], r["dsr"], r["pbo"], r["verdict"], "Yes, paper only" if allowed else "No - stays in cash",
                     r["version"], r["data"], role.why])
    wb = Workbook()
    ws = wb.active
    ws.title = "Read me"
    read_me(ws, "Bot power: what each of the 100 trading bots has measured", [
        "What 'power' means here:",
        "A bot's power is its measured result: what its chosen strategy earned on real market data it never saw while being tuned "
        "(the last 20% of the history, called the test). Nothing on the Bots sheet is a promise about the future.",
        "",
        f"The honest summary: {passed} of 100 bots passed the quality gate, so every bot stays in cash and none may trade.",
        "A bot may trade (in paper only) when its verdict is PAPER TEST, which needs ALL of: at least 30 test trades, Deflated Sharpe "
        "(DSR) of at least 0.95, PBO of at most 0.2, walk-forward ratio of at least 0.5, survival at twice the modelled costs, and a "
        "placebo percentile of at least 95. Real money stays off whatever a bot scores.",
        "",
        "Columns on the Bots sheet:",
        "Agent: A001 to A100.   Group / Role: what kind of market and idea the bot is built for.   Instrument: what it trades.   Bar: its candle size.",
        "Candidate strategies: the three strategies the master agent tried for this role.   Chosen: the one with the best Validation Sharpe.",
        "Validation Sharpe / Test Sharpe: risk-adjusted return after costs on the middle 20% / last 20% of the history. Above 0 is good; "
        "a Sharpe near 1 or higher is strong; negative means it lost money.",
        "Test return / Test max drawdown: what the chosen strategy earned and its deepest fall on the test data, risking 1% per trade.",
        "Test trades: how many trades the test had; under 30 is too few to tell skill from luck. "
        f"{sum(1 for r in rows if r[9] is not None and r[9] > 3 and r[12] < 30)} bots show a test Sharpe above 3 on fewer than 30 trades: "
        "that is luck on a handful of trades, not power (their DSR is far below 0.95).",
        "Walk-forward Sharpe: out-of-sample Sharpe from re-fitting step by step.   DSR: the chance the edge is real after charging for every "
        "strategy tried (needs 0.95).   PBO: the chance the best choice was overfitted (needs 0.2 or less).",
        "Training data: where the history came from and how long it is.",
        "",
        "Source: docs/AGENT_TRAINING_REPORT.md, written by scripts/train_agents.py on 2026-10-14 from Coinbase (crypto and meme coins) "
        "and Yahoo Finance (US stocks). This file is made by scripts/export_lists.py.",
    ])
    ws = wb.create_sheet("Bots (100)")
    pct = "0.0%;-0.0%"
    table(ws, ["Agent", "Group", "Role", "Instrument", "Bar", "Idea", "Candidate strategies", "Chosen strategy",
               "Validation Sharpe", "Test Sharpe", "Test return", "Test max drawdown", "Test trades", "Walk-forward Sharpe",
               "DSR (needs 0.95)", "PBO (needs 0.2 or less)", "Verdict", "Allowed to trade?", "Version",
               "Training data", "Why this role"],
          rows, [8, 11, 30, 14, 6, 26, 32, 28, 11, 10, 11, 12, 9, 12, 11, 12, 18, 20, 12, 44, 60], wrap={6, 20},
          formats={8: "0.00", 9: "0.00", 10: pct, 11: pct, 13: "0.00", 14: "0.00", 15: "0.00"})
    ws2 = wb.create_sheet("By role (8)")
    ws2.append(["Role", "Bots", "Bots with a positive test Sharpe", "Average test Sharpe", "Bots cleared to trade"])
    for c in range(1, 6):
        ws2.cell(row=1, column=c).font, ws2.cell(row=1, column=c).fill = HEAD_FONT, HEAD_FILL
        ws2.cell(row=1, column=c).alignment = Alignment(wrap_text=True, vertical="center")
    ws2.row_dimensions[1].height = 32
    # plain numbers, counted here from the same rows as the Bots sheet, so any viewer shows them without recalculating
    by_role = defaultdict(list)
    for row in rows:
        by_role[row[2]].append(row)
    for key in ROLES:
        group = by_role[ROLES[key].label]
        sharpes = [r[9] for r in group if r[9] is not None]
        ws2.append([ROLES[key].label, len(group), sum(1 for v in sharpes if v > 0),
                    round(sum(sharpes) / len(sharpes), 2) if sharpes else None,
                    sum(1 for r in group if r[16] == "PAPER TEST")])
    every = [r[9] for r in rows if r[9] is not None]
    ws2.append(["All bots", len(rows), sum(1 for v in every if v > 0), round(sum(every) / len(every), 2), passed])
    for row in ws2.iter_rows(min_row=2, max_row=ws2.max_row):
        for cell in row:
            cell.font = BOLD if row[0].value == "All bots" else BODY
        row[3].number_format = "0.00"
    for col, w in zip("ABCDE", (34, 8, 20, 16, 16)):
        ws2.column_dimensions[col].width = w
    ws2.cell(row=ws2.max_row + 2, column=1,
             value="Counted from the Bots (100) sheet. A positive test Sharpe on its own proves little: most of these bots had few "
                   "test trades and none passed the Deflated Sharpe check.").font = BODY
    return wb, {"bots": len(rows), "passed": passed}


# ----------------------------------------------------------------------------------------------- strategies

def strategies_workbook() -> tuple[Workbook, dict]:
    specs = L.specs()
    summary = L.summary()
    roles = agent_roles()
    report = parse_report()
    can_use: dict[str, list[str]] = defaultdict(list)
    chosen_by: dict[str, list[str]] = defaultdict(list)
    for agent, role_key in roles.items():
        for sid in ROLES[role_key].candidates:
            can_use[sid].append(agent)
        chosen_by[report[agent]["chosen"]].append(agent)
    rows = []
    for sid, s in sorted(specs.items(), key=lambda kv: (kv[1].family, kv[0])):
        markets = ", ".join(s.supported_markets)
        evidence = "; ".join(f"{k} ({EVIDENCE.get(k, k)}): {t}" for k, t in s.research_sources)
        rows.append([sid, s.family, s.risk_class, s.description, s.entry_rules, s.exit_rules, s.stop_rules, markets,
                     ", ".join(s.supported_timeframes),
                     "Yes" if TRADABLE & set(s.supported_markets) else "No",
                     "Yes" if s.runnable else "No - " + ", ".join(s.required_data),
                     len(can_use.get(sid, [])), ", ".join(chosen_by.get(sid, [])),
                     ", ".join(f"{k}={v}" for k, v in s.parameters.items()), evidence])
    cards = json.loads((ROOT / "backend/tradingai/strategies/data/catalog_st.json").read_text(encoding="utf-8"))
    groups = cards["groups"]
    card_rows = [[c["id"], c["name"], groups.get(c["group"], c["group"]),
                  ", ".join(f"{k} ({EVIDENCE.get(k, k)})" for k in c.get("evidence_labels", [])),
                  c.get("markets_text", ""), c.get("scope_text", ""), c.get("card", ""), ", ".join(c.get("sources", []))]
                 for c in cards["cards"]]
    wb = Workbook()
    ws = wb.active
    ws.title = "Read me"
    tradable = sum(1 for r in rows if r[9] == "Yes")
    read_me(ws, "Every strategy in the Trading AI", [
        "What is in this file:",
        f"Sheet 'Strategies ({len(rows)})': every strategy the software can build and test: {summary['base_generators']} base signal ideas, each combined with "
        f"{len(summary['filters'])} entry filters and {len(summary['exit_models'])} exit rules "
        f"({summary['dropped_as_near_duplicates']} near-duplicates were dropped; {summary['runnable']} of {summary['templates_total']} run without extra data).",
        f"Sheet 'Research ideas ({len(card_rows)})': the written research cards (ST001 and up) from your specification, covering every market in the research. "
        "They are ideas to test, not strategies that trade.",
        "",
        "Important:",
        "The software trades only US stocks and crypto (including meme coins). Strategies built for forex, futures or options appear here so the list is "
        f"complete; the column 'Trades US stocks or crypto?' says which ones can be used ({tradable} of {len(rows)} can).",
        "Having a strategy in this list does not make it profitable. All 100 bots were trained and tested on real data and none passed the quality gate, "
        "so none is trading. See BOT_POWER.xlsx for the measured results, and STRATEGY_RESEARCH.md and CATALOG_BACKTEST_REPORT.md for the research.",
        "",
        "Columns on the Strategies sheet:",
        "ID: generator.filter.exit.   Family: the kind of idea (trend, mean reversion, breakout...).   Risk class: low, medium or high.",
        "What it does / Entry / Exit / Stop: the rules in plain words.   Markets / Bar sizes: where it is built to work.",
        "Bots that can use it: how many of the 100 bots list it as one of their three candidates.   Picked by: the bots that chose it after training.",
        "Standard settings: the default numbers (for example fast=20, slow=100).   Evidence: R = research-supported, C = documented construction, H = hypothesis.",
        "",
        "Source: backend/tradingai/strategies (library.py, data/catalog_st.json). This file is made by scripts/export_lists.py.",
    ])
    ws = wb.create_sheet(f"Strategies ({len(rows)})")
    table(ws, ["ID", "Family", "Risk class", "What it does", "Entry rule", "Exit rule", "Stop rule", "Markets built for",
               "Bar sizes", "Trades US stocks or crypto?", "Runs without extra data?", "Bots that can use it", "Picked by (after training)",
               "Standard settings", "Evidence"],
          rows, [34, 14, 9, 70, 50, 34, 30, 28, 22, 14, 16, 10, 22, 22, 60], wrap={3, 14})
    ws = wb.create_sheet(f"Research ideas ({len(card_rows)})")
    table(ws, ["ID", "Name", "Group", "Evidence", "Markets", "Time scale", "Description", "Sources"],
          card_rows, [9, 44, 34, 24, 40, 22, 90, 16], wrap={1, 4, 6})
    return wb, {"strategies": len(rows), "cards": len(card_rows), "tradable": tradable}


def main() -> int:
    wb, info = strategies_workbook()
    wb.save(DOCS / "ALL_STRATEGIES.xlsx")
    print("ALL_STRATEGIES.xlsx", info)
    wb, info = bots_workbook()
    wb.save(DOCS / "BOT_POWER.xlsx")
    print("BOT_POWER.xlsx", info)
    return 0


if __name__ == "__main__":
    sys.exit(main())
