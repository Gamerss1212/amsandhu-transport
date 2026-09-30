"""Versions and promotions: every strategy definition and every model that can trade is versioned, and nothing
reaches live trading without an evaluation and the owner's explicit approval.

Strategy versions   research -> live_approved -> retired. Paper and demo trading may use any version (no money is
                    at risk); LIVE requires live_approved, which requires a finished walk-forward evaluation of that
                    exact version whose checks pass (or the owner's typed acceptance of the failed checks, recorded).
Model versions      the brain: "learning" keeps learning on paper; snapshots are frozen versions (candidate); a
                    candidate becomes the live "champion" only after a forward comparison (brain_eval) and the
                    owner's approval. Live deployments use the champion and never change by themselves.
                    The volatility gate: shipped, evaluated offline on held-out data; registered read-only.
Every change is a row in `promotions` and an audit event.
"""

from __future__ import annotations

import hashlib
import json
import time
from typing import List, Optional

ACCEPT_TEXT = "I ACCEPT THE FAILED CHECKS"


def now_ms() -> int:
    return int(time.time() * 1000)


class Registry:
    def __init__(self, storage):
        self.st = storage

    # ------------------------------------------------------------------ strategies
    def register_strategy(self, strategy_id: str, definition: dict, version_hash: str, source: str = "catalog",
                          notes: str = "") -> dict:
        self.st.write("INSERT OR IGNORE INTO strategy_versions (strategy_id, version_hash, definition, source, created,"
                      " status, notes) VALUES (?,?,?,?,?,?,?)", (strategy_id, version_hash, json.dumps(definition),
                                                                 source, now_ms(), "research", notes))
        return self.strategy(strategy_id, version_hash)

    def strategy(self, strategy_id: str, version_hash: str) -> Optional[dict]:
        r = self.st.query("SELECT * FROM strategy_versions WHERE strategy_id=? AND version_hash=?", (strategy_id, version_hash))
        if not r:
            return None
        d = dict(r[0])
        d["definition"] = json.loads(d["definition"])
        return d

    def status(self, strategy_id: str, version_hash: str) -> str:
        r = self.st.query("SELECT status FROM strategy_versions WHERE strategy_id=? AND version_hash=?",
                          (strategy_id, version_hash))
        return r[0]["status"] if r else "unregistered"

    def strategies(self, status: str = None) -> List[dict]:
        q = "SELECT strategy_id, version_hash, source, created, status, evaluation_job, approved_by, approved, notes FROM strategy_versions"
        return self.st.query(q + (" WHERE status=?" if status else "") + " ORDER BY created DESC", (status,) if status else ())

    def approve_live(self, strategy_id: str, version_hash: str, job: dict, approver: str, accept: str = "",
                     note: str = "") -> dict:
        s = self.strategy(strategy_id, version_hash)
        if s is None:
            raise ValueError("this strategy version is not registered")
        if not job or job.get("state") != "done" or job.get("kind") != "walk_forward":
            raise ValueError("approve after a finished walk-forward evaluation of this version")
        res = job.get("result") or {}
        if res.get("strategy_version") != version_hash:
            raise ValueError("that evaluation was of a different version of this strategy")
        if not res.get("passes") and accept.strip().upper() != ACCEPT_TEXT:
            failed = [k.replace("_", " ") for k, v in (res.get("checks") or {}).items() if not v]
            raise ValueError("the evaluation did not pass (" + ", ".join(failed) + f"). To approve anyway type: {ACCEPT_TEXT}")
        self.st.write("UPDATE strategy_versions SET status='live_approved', evaluation_job=?, approved_by=?, approved=?, notes=?"
                      " WHERE strategy_id=? AND version_hash=?", (job["job_id"], approver, now_ms(),
                                                                 note or ("checks passed" if res.get("passes") else
                                                                          "approved with failed checks accepted by the owner"),
                                                                 strategy_id, version_hash))
        self._promotion("strategy", f"{strategy_id}@{version_hash}", s["status"], "live_approved",
                        {"job": job["job_id"], "passes": res.get("passes"), "checks": res.get("checks")}, approver, note)
        return self.strategy(strategy_id, version_hash)

    def retire_strategy(self, strategy_id: str, version_hash: str, approver: str, note: str = "") -> dict:
        s = self.strategy(strategy_id, version_hash)
        if s is None:
            raise ValueError("unknown strategy version")
        self.st.write("UPDATE strategy_versions SET status='retired' WHERE strategy_id=? AND version_hash=?",
                      (strategy_id, version_hash))
        self._promotion("strategy", f"{strategy_id}@{version_hash}", s["status"], "retired", None, approver, note)
        return self.strategy(strategy_id, version_hash)

    # ------------------------------------------------------------------ models
    def models(self, model: str = None) -> List[dict]:
        q = "SELECT model, version, created, source, status, metrics, approved_by, approved, notes FROM model_versions"
        rows = self.st.query(q + (" WHERE model=?" if model else "") + " ORDER BY created DESC", (model,) if model else ())
        for r in rows:
            r["metrics"] = json.loads(r["metrics"] or "{}")
        return rows

    def champion(self, model: str) -> Optional[dict]:
        r = self.st.query("SELECT * FROM model_versions WHERE model=? AND status='champion' ORDER BY approved DESC LIMIT 1",
                          (model,))
        return dict(r[0]) if r else None

    def snapshot_brain(self, brain, note: str = "") -> dict:
        state = brain.to_state()
        blob = json.dumps(state, default=str)
        version = "brain-" + hashlib.sha256(blob.encode()).hexdigest()[:10]
        s = brain.summary()
        metrics = {k: s.get(k) for k in ("trades_learned", "win_rate", "avg_r", "brier", "shadow_trades", "shadow_avg_r",
                                          "benched_now", "vetoed", "approved")}
        self.st.write("INSERT OR IGNORE INTO model_versions (model, version, created, source, status, metrics, blob, notes)"
                      " VALUES (?,?,?,?,?,?,?,?)", ("brain", version, now_ms(), "snapshot of the learning brain",
                                                     "candidate", json.dumps(metrics, default=str), blob, note))
        self.st.audit("research", f"brain snapshot {version} frozen as a candidate ({metrics.get('trades_learned')} trades "
                      "learned)", stage="model_snapshot", payload={"version": version, "metrics": metrics})
        return {"model": "brain", "version": version, "metrics": metrics}

    def promote_brain(self, version: str, job: dict, approver: str, accept: str = "", note: str = "") -> dict:
        r = self.st.query("SELECT * FROM model_versions WHERE model='brain' AND version=?", (version,))
        if not r:
            raise ValueError("unknown brain version")
        if not job or job.get("state") != "done" or job.get("kind") != "brain_eval" or \
                (job.get("result") or {}).get("candidate") != version:
            raise ValueError("promote after a finished forward comparison (brain_eval) of this version")
        rec = (job.get("result") or {}).get("recommendation", "")
        if not rec.startswith("candidate better") and accept.strip().upper() != ACCEPT_TEXT:
            raise ValueError(f"the comparison says: {rec}. To promote anyway type: {ACCEPT_TEXT}")
        old = self.champion("brain")
        if old:
            self.st.write("UPDATE model_versions SET status='retired' WHERE model='brain' AND version=?", (old["version"],))
        self.st.write("UPDATE model_versions SET status='champion', approved_by=?, approved=?, notes=? WHERE model='brain' AND"
                      " version=?", (approver, now_ms(), note or rec, version))
        self._promotion("model", f"brain@{version}", r[0]["status"], "champion",
                        {"job": job["job_id"], "recommendation": rec, "previous": old and old["version"]}, approver, note)
        return self.champion("brain")

    def register_volgate(self, vg) -> Optional[dict]:
        if not getattr(vg, "version", None):
            return None
        m = vg.model
        metrics = {a: {"loud": m[a].get("test_loud"), "quiet": m[a].get("test_quiet"), "period": m[a].get("period"),
                       "kind": m[a].get("kind")} for a in ("crypto", "stock") if a in m}
        self.st.write("INSERT OR IGNORE INTO model_versions (model, version, created, source, status, metrics, notes) VALUES"
                      " (?,?,?,?,?,?,?)", ("volgate", vg.version, now_ms(), "shipped with this build (trained offline)",
                                           "champion", json.dumps(metrics, default=str),
                                           "evaluated once on the most recent 20% of its data (held out)"))
        return self.champion("volgate")

    def promotions(self, limit: int = 100) -> List[dict]:
        rows = self.st.query("SELECT * FROM promotions ORDER BY id DESC LIMIT ?", (limit,))
        for r in rows:
            r["evaluation"] = json.loads(r["evaluation"] or "null")
        return rows

    def _promotion(self, obj, oid, frm, to, evaluation, approver, note):
        self.st.write("INSERT INTO promotions (ts, object, object_id, from_status, to_status, evaluation, approved_by, note)"
                      " VALUES (?,?,?,?,?,?,?,?)", (now_ms(), obj, oid, frm, to, json.dumps(evaluation, default=str),
                                                     approver, note))
        self.st.audit("research", f"{obj} {oid}: {frm} -> {to} (approved by {approver})", stage="promotion",
                      severity="warning", payload={"object": obj, "id": oid, "from": frm, "to": to,
                                                   "evaluation": evaluation, "note": note})
