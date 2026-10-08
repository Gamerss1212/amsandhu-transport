"""The research ledger (sections 161, 193-194, 233, 302): every experiment, kept forever, failures included.

A family's trial count (all parameter sets ever run for one generator) is what the Deflated Sharpe Ratio is charged
with, so searching harder makes the bar higher automatically. Statuses: FAILED, WEAK, PROMISING, PAPER_ELIGIBLE.
LIVE_CANDIDATE is set only by research/compare.py from a paper track record, never by a backtest.
"""

from __future__ import annotations

import json
from typing import Optional

from tradingai import __version__
from tradingai.core.ids import new_id
from tradingai.storage.db import Database, dumps, now_ms

STATUS_FOR_VERDICT = {"REJECT": "FAILED", "RESEARCH FURTHER": "WEAK", "PAPER TEST": "PAPER_ELIGIBLE"}


class Ledger:
    def __init__(self, db: Database):
        self.db = db

    def family_trials(self, family: str) -> int:
        r = self.db.one("SELECT COALESCE(SUM(json_array_length(json_extract(params, '$.grid'))), 0) AS n "
                        "FROM experiments WHERE family=?", (family,))
        return int(r["n"] or 0) if r else 0

    def start(self, *, family: str, strategy_id: str, hypothesis: str, instrument: str, tf: str, profile: str,
              seed: int, dataset: dict) -> str:
        eid = new_id("EXP")
        self.db.execute("INSERT INTO experiments (experiment_id, created, family, strategy_id, hypothesis, params, "
                        "dataset, profile, status, code_version, seed, trials_at_run) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)",
                        (eid, now_ms(), family, strategy_id, hypothesis, dumps({"grid": []}),
                         dumps(dict(dataset, instrument=instrument, tf=tf)), profile, "RUNNING", __version__, seed,
                         self.family_trials(family)))
        return eid

    def finish(self, eid: str, result: dict) -> None:
        status = STATUS_FOR_VERDICT.get(result.get("verdict", ""), "FAILED")
        if result.get("status") != "ok":
            status = "FAILED"
        if status == "WEAK" and (result.get("quality") or {}).get("score", 0) >= 50:
            status = "PROMISING"
        reason = "; ".join(f"{c['name']} {c['value']} (need {c['need']})" for c in result.get("checks", [])
                           if not c["passed"]) or result.get("status", "")
        slim = {k: v for k, v in result.items() if k not in ("grid",)}
        params = {"grid": [g["params"] for g in result.get("grid", [])] or [{}], "chosen": result.get("params_chosen")}
        self.db.execute("UPDATE experiments SET params=?, results=?, status=?, reason=?, finished=? WHERE experiment_id=?",
                        (dumps(params), dumps(slim), status, reason[:2000], now_ms(), eid))

    def fail(self, eid: str, why: str) -> None:
        self.db.execute("UPDATE experiments SET status=?, reason=?, finished=? WHERE experiment_id=?",
                        ("FAILED", why[:2000], now_ms(), eid))

    def list(self, limit: int = 100, family: Optional[str] = None) -> list[dict]:
        sql = "SELECT experiment_id, created, finished, family, strategy_id, profile, status, reason, dataset, " \
              "trials_at_run, json_extract(results, '$.quality.score') AS quality, " \
              "json_extract(results, '$.verdict') AS verdict FROM experiments"
        args: tuple = ()
        if family:
            sql += " WHERE family=?"
            args = (family,)
        rows = self.db.query(sql + " ORDER BY created DESC LIMIT ?", args + (limit,))
        for r in rows:
            r["dataset"] = json.loads(r["dataset"]) if r["dataset"] else None
        return rows

    def get(self, eid: str) -> Optional[dict]:
        r = self.db.one("SELECT * FROM experiments WHERE experiment_id=?", (eid,))
        if r:
            for k in ("params", "dataset", "results"):
                r[k] = json.loads(r[k]) if r.get(k) else None
        return r

    def latest_for(self, strategy_id: str, instrument: str) -> Optional[dict]:
        r = self.db.one("SELECT experiment_id FROM experiments WHERE strategy_id=? AND json_extract(dataset, "
                        "'$.instrument')=? AND status!='RUNNING' ORDER BY created DESC LIMIT 1",
                        (strategy_id, instrument))
        return self.get(r["experiment_id"]) if r else None

    def counts(self) -> dict:
        rows = self.db.query("SELECT status, COUNT(*) AS n FROM experiments GROUP BY status")
        total = self.db.one("SELECT COUNT(*) AS n FROM experiments")
        return {"by_status": {r["status"]: r["n"] for r in rows}, "experiments": total["n"] if total else 0}
