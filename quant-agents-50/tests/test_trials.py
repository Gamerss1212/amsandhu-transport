"""Spec section 63 trial registry: every run is logged; real-data variants are counted."""

from __future__ import annotations

from datetime import date
from pathlib import Path

from quantagents.validation.trials import (
    HEADER,
    Trial,
    append_trials,
    data_id,
    logged_variants,
    trial_count,
)


def test_trials_are_appended_and_counted(tmp_path: Path) -> None:
    log = tmp_path / "docs" / "research" / "trials.md"
    assert logged_variants("tsmom", log) == set()
    real = "us.csv 0123456789ab"
    append_trials([], log)
    assert not log.exists()
    append_trials(
        [
            Trial(date(2026, 10, 6), "tsmom", "tsmom_126", "vectorized", real, 0.72, "PASS"),
            Trial(date(2026, 10, 6), "tsmom", "tsmom_63", "", real, 0.5, "variant (counted)"),
            Trial(date(2026, 10, 6), "tsmom", "tsmom_21", "x|y", "synthetic (seed 7)", 1.9, "-"),
            Trial(date(2026, 10, 6), "faber", "faber_10m", "", real, 0.4, "FAIL"),
        ],
        log,
    )
    text = log.read_text(encoding="utf-8")
    assert text.startswith(HEADER)
    assert (
        "| 2026-10-06 | tsmom | tsmom_126 (vectorized) | us.csv 0123456789ab | 0.72 | PASS |"
        in text
    )
    assert "x/y" in text  # a "|" inside a cell cannot break the table
    # synthetic runs are logged but never counted as real-data trials
    assert logged_variants("tsmom", log) == {"tsmom_126", "tsmom_63"}
    # re-running a logged variant adds nothing; a new one adds one
    assert trial_count("tsmom", ["tsmom_126"], log) == 2
    assert trial_count("tsmom", ["tsmom_126", "tsmom_252"], log) == 3
    log.write_text(text.rstrip("\n"), encoding="utf-8")  # no trailing newline
    append_trials([Trial(date(2026, 10, 7), "faber", "faber_8m", "", real, 0.1, "-")], log)
    assert logged_variants("faber", log) == {"faber_10m", "faber_8m"}


def test_data_id_names_the_file_and_its_content(tmp_path: Path) -> None:
    csv = tmp_path / "prices.csv"
    csv.write_text("a", encoding="utf-8")
    first = data_id(str(csv), 7)
    assert first.startswith("prices.csv ") and len(first.split()[1]) == 12
    csv.write_text("b", encoding="utf-8")
    assert data_id(str(csv), 7) != first
    assert data_id(None, 7) == "synthetic (seed 7)"
