#!/usr/bin/env python3
"""Build a single-file Jarvus for pasting into a Claude.ai Project or a chat.

  python3 build_single_file.py

Writes dist/jarvus-all-in-one.md: SKILL.md (frontmatter stripped) followed by every
reference and asset, in reading order. The scripts are not inlined; in a plain chat
they cannot run anyway, and the file says so.
"""
from __future__ import annotations
import os

HERE = os.path.dirname(os.path.abspath(__file__))
ORDER = ["SKILL.md"] + [f"references/{f}" for f in [
    "market-structure.md", "indicators.md", "crypto-market-data.md", "risk-management.md",
    "playbooks.md", "strategy-encyclopedia.md", "probability-and-prediction.md",
    "regimes-and-cycles.md", "altcoins-and-memecoins.md", "execution-and-order-types.md",
    "psychology-and-rules.md", "journal-and-backtesting.md", "worked-examples.md", "glossary.md"]] + \
    [f"assets/{f}" for f in [
    "trade-plan-template.md", "pre-trade-checklist.md", "daily-routine.md",
    "event-calendar-2026.md", "jarvus-clock-mt.md"]]


def main() -> None:
    parts = ["<!-- Jarvus, all-in-one build. Source of truth is the skill folder. -->\n"]
    for rel in ORDER:
        path = os.path.join(HERE, rel)
        if not os.path.exists(path):
            continue
        text = open(path, encoding="utf-8").read()
        if rel == "SKILL.md" and text.startswith("---"):
            text = text[text.index("\n---", 3) + 4:].lstrip("\n")
        parts.append(f"\n\n<!-- ===== {rel} ===== -->\n\n{text.rstrip()}\n")
    parts.append("\n\n<!-- ===== scripts ===== -->\n\n# Bundled scripts\n\n"
                 "The skill folder ships `events.py`, `scan.py`, `fetch_ohlcv.py`, `snapshot.py`, "
                 "`confluence.py`, `position_size.py`, `journal.py`, `journal_stats.py`, `backtest.py`, "
                 "`ladder.py` (the 80% Mode engine), `experiment_80.py` and `selftest.py`. A plain "
                 "claude.ai chat cannot run them or reach exchange APIs, so there ask for the key "
                 "numbers (price, today's high/low, PDH/PDL/PDC, funding) and say which data is missing.\n")
    md = "".join(parts)
    os.makedirs(os.path.join(HERE, "dist"), exist_ok=True)
    out = os.path.join(HERE, "dist", "jarvus-all-in-one.md")
    open(out, "w", encoding="utf-8").write(md)
    print(f"wrote {out} ({len(md):,} chars, ~{len(md)//4:,} tokens)")


if __name__ == "__main__":
    main()
