#!/usr/bin/env python3
"""Build distributable versions of the skill.

  python3 build_single_file.py

Writes:
  dist/crypto-day-trading-all-in-one.md   SKILL.md + every reference and asset in one Markdown file,
                                          for pasting/uploading into a Claude.ai Project or a system prompt
  dist/crypto-day-trading.skill           zip of the skill folder for uploading as a custom skill
"""

from __future__ import annotations

import os
import zipfile

HERE = os.path.dirname(os.path.abspath(__file__))
DIST = os.path.join(HERE, "dist")
NAME = "crypto-day-trading"

ORDER = [
    "SKILL.md",
    "references/market-structure.md",
    "references/indicators.md",
    "references/crypto-market-data.md",
    "references/risk-management.md",
    "references/playbooks.md",
    "references/probability-and-prediction.md",
    "references/regimes-and-cycles.md",
    "references/altcoins-and-memecoins.md",
    "references/execution-and-order-types.md",
    "references/psychology-and-rules.md",
    "references/journal-and-backtesting.md",
    "references/worked-examples.md",
    "references/glossary.md",
    "assets/trade-plan-template.md",
    "assets/pre-trade-checklist.md",
    "assets/daily-routine.md",
    "assets/event-calendar-2026.md",
]


def build_markdown() -> str:
    parts = ["<!-- crypto-day-trading: all-in-one build. Source of truth is the skill folder. -->\n"]
    for rel in ORDER:
        path = os.path.join(HERE, rel)
        with open(path, encoding="utf-8") as fh:
            text = fh.read()
        if rel == "SKILL.md" and text.startswith("---"):
            # drop the YAML frontmatter; it is for the skill loader, not for a project document
            end = text.index("\n---", 3)
            text = text[end + 4:].lstrip("\n")
        parts.append(f"\n\n<!-- ===== {rel} ===== -->\n\n{text.rstrip()}\n")
    parts.append("\n\n<!-- ===== scripts ===== -->\n\n"
                 "# Bundled scripts\n\nThe skill folder ships Python tools (fetch_ohlcv.py, snapshot.py, scan.py, "
                 "position_size.py, journal.py, journal_stats.py, backtest.py, events.py). In an environment that "
                 "cannot run them, ask the user for current prices, today's high/low, yesterday's high/low/close, "
                 "funding, and open interest, and say which of these you do not have.\n")
    return "".join(parts)


def build_skill_zip() -> str:
    os.makedirs(DIST, exist_ok=True)
    out = os.path.join(DIST, f"{NAME}.skill")
    skip_dirs = {"dist", "__pycache__", ".git", "evals"}
    with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
        for root, dirs, files in os.walk(HERE):
            dirs[:] = [d for d in dirs if d not in skip_dirs]
            for f in files:
                if f.endswith((".pyc", ".skill")) or f == "build_single_file.py":
                    continue
                full = os.path.join(root, f)
                rel = os.path.relpath(full, HERE)
                zf.write(full, os.path.join(NAME, rel))
    return out


def main() -> None:
    os.makedirs(DIST, exist_ok=True)
    md = build_markdown()
    md_path = os.path.join(DIST, f"{NAME}-all-in-one.md")
    with open(md_path, "w", encoding="utf-8") as fh:
        fh.write(md)
    zip_path = build_skill_zip()
    print(f"wrote {md_path} ({len(md):,} chars, ~{len(md) // 4:,} tokens)")
    print(f"wrote {zip_path} ({os.path.getsize(zip_path):,} bytes)")


if __name__ == "__main__":
    main()
