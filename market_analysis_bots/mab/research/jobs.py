"""Research job queue and worker pool: parallel, bounded, cached, and never in the way of trading.

* Jobs are rows in the workspace database (research_jobs): queued -> running -> done | failed | canceled.
* The pool runs each job in its own process (a fresh interpreter), at most `max_workers` at once, by priority
  then age. Each job has a wall-time budget and a memory budget; a job that exceeds either is stopped and marked
  failed with the reason. The bots run in a different process, so research never slows them down.
* Results are cached by (job kind, exact specification, code version, data fingerprint): the same question
  asked of the same data is answered from the cache.
* Progress is written by the worker (fraction and a short message) and shown live.
"""

from __future__ import annotations

import hashlib
import json
import logging
import multiprocessing
import os
import secrets
import threading
import time
from typing import Callable, Dict, List, Optional, Tuple

from mab import __version__
from mab.hardware import cpu_percent, describe, process_rss_mb

log = logging.getLogger("mab.research")

KINDS = {"walk_forward": "Walk-forward evaluation of a strategy on a market (train/validation/test, folds, baselines)",
         "gate_drift": "Volatility gate drift: recent precision and feature shift against its held-out test",
         "brain_eval": "Candidate brain vs approved brain on trades that closed after the candidate was frozen"}
CODE_VERSION = f"mab {__version__} research-1"


def now_ms() -> int:
    return int(time.time() * 1000)


def spec_hash(kind: str, spec: dict, fingerprint: str = "") -> str:
    body = json.dumps({"kind": kind, "spec": spec, "code": CODE_VERSION, "data": fingerprint}, sort_keys=True, default=str)
    return hashlib.sha256(body.encode()).hexdigest()[:24]


class JobQueue:
    def __init__(self, storage):
        self.st = storage

    @staticmethod
    def _row(r: dict) -> dict:
        d = dict(r)
        for k in ("spec", "result"):
            if d.get(k):
                try:
                    d[k] = json.loads(d[k])
                except ValueError:
                    pass
        return d

    def submit(self, kind: str, spec: dict, priority: int = 5, requested_by: str = "owner") -> dict:
        if kind not in KINDS:
            raise ValueError(f"unknown job kind {kind!r}; choose one of {', '.join(KINDS)}")
        if not isinstance(spec, dict):
            raise ValueError("the job specification must be an object")
        blob = json.dumps(spec, default=str)
        if len(blob) > 200_000:
            raise ValueError("job specification too large")
        jid = "J-" + secrets.token_hex(5).upper()
        self.st.write("INSERT INTO research_jobs (job_id, kind, spec, spec_hash, state, priority, created, requested_by,"
                      " progress, message) VALUES (?,?,?,?,?,?,?,?,?,?)",
                      (jid, kind, blob, spec_hash(kind, spec), "queued", int(priority), now_ms(), requested_by, 0.0,
                       "waiting for a worker"))
        self.st.audit("research", f"research job {jid} queued: {KINDS[kind].split(':')[0].split('(')[0].strip()}",
                      stage="job_queued", payload={"job_id": jid, "kind": kind, "spec": spec, "by": requested_by})
        return self.get(jid)

    def get(self, jid: str) -> Optional[dict]:
        r = self.st.query("SELECT * FROM research_jobs WHERE job_id=?", (jid,))
        return self._row(r[0]) if r else None

    def list(self, limit: int = 50, states: Optional[List[str]] = None) -> List[dict]:
        q = "SELECT * FROM research_jobs"
        a: list = []
        if states:
            q += " WHERE state IN (%s)" % ",".join("?" * len(states))
            a += states
        rows = self.st.query(q + " ORDER BY created DESC LIMIT ?", tuple(a + [limit]))
        out = []
        for r in rows:
            d = self._row(r)
            if isinstance(d.get("result"), dict):                    # keep listings small
                res = d["result"]
                d["result"] = {k: res.get(k) for k in ("verdict", "passes", "status", "recommendation", "strategy_id",
                                                       "summary", "data_quality") if k in res}
            out.append(d)
        return out

    def counts(self) -> Dict[str, int]:
        return {r["state"]: r["n"] for r in self.st.query("SELECT state, COUNT(*) AS n FROM research_jobs GROUP BY state")}

    def cancel(self, jid: str) -> dict:
        j = self.get(jid)
        if j is None:
            raise ValueError("unknown job")
        if j["state"] in ("queued", "running"):
            self.st.write("UPDATE research_jobs SET state='canceled', finished=?, message=? WHERE job_id=? AND state IN "
                          "('queued','running')", (now_ms(), "canceled by the owner", jid))
        return self.get(jid)

    def claim(self, worker: str) -> Optional[dict]:
        """Atomically take the next queued job."""
        with self.st.wlock:
            c = self.st._conn()
            c.execute("BEGIN IMMEDIATE")
            try:
                r = c.execute("SELECT job_id FROM research_jobs WHERE state='queued' ORDER BY priority, created LIMIT 1").fetchone()
                if r is None:
                    c.execute("COMMIT")
                    return None
                c.execute("UPDATE research_jobs SET state='running', started=?, worker=?, message=? WHERE job_id=?",
                          (now_ms(), worker, "starting", r[0]))
                c.execute("COMMIT")
            except Exception:
                c.execute("ROLLBACK")
                raise
        return self.get(r[0])

    def progress(self, jid: str, frac: float, msg: str):
        self.st.write("UPDATE research_jobs SET progress=?, message=? WHERE job_id=? AND state='running'",
                      (round(max(0.0, min(1.0, frac)), 3), msg[:300], jid))

    def finish(self, jid: str, result: dict, cached: bool = False, cpu_s: float = None, peak_mb: float = None):
        self.st.write("UPDATE research_jobs SET state='done', finished=?, progress=1.0, message=?, result=?, cached=?,"
                      " cpu_s=?, peak_mb=? WHERE job_id=? AND state='running'",
                      (now_ms(), "done (from cache)" if cached else "done", json.dumps(result, default=str), int(cached),
                       cpu_s, peak_mb, jid))
        j = self.get(jid)
        if j:
            res = j.get("result") or {}
            self.st.audit("research", f"research job {jid} finished: {res.get('verdict') or res.get('summary') or 'done'}"
                          + (" (cached)" if cached else ""), stage="job_done",
                          payload={"job_id": jid, "kind": j["kind"], "cached": cached,
                                   "verdict": res.get("verdict"), "passes": res.get("passes")})

    def fail(self, jid: str, error: str):
        self.st.write("UPDATE research_jobs SET state='failed', finished=?, message=?, error=? WHERE job_id=? AND state IN "
                      "('running','queued')", (now_ms(), error[:300], error[:4000], jid))
        self.st.audit("research", f"research job {jid} failed: {error[:200]}", stage="job_failed", severity="warning",
                      payload={"job_id": jid, "error": error[:2000]})

    def cache_get(self, key: str) -> Optional[dict]:
        r = self.st.query("SELECT result FROM research_cache WHERE spec_hash=?", (key,))
        if not r:
            return None
        self.st.write("UPDATE research_cache SET hits = hits + 1 WHERE spec_hash=?", (key,))
        return json.loads(r[0]["result"])

    def cache_put(self, key: str, kind: str, result: dict, fingerprint: str):
        self.st.write("INSERT OR REPLACE INTO research_cache (spec_hash, kind, result, created, code_version, data_fingerprint,"
                      " hits) VALUES (?,?,?,?,?,?,0)", (key, kind, json.dumps(result, default=str), now_ms(), CODE_VERSION,
                                                         fingerprint))


# ----------------------------------------------------------------------------- the pool

def _child(db_path: str, jid: str, cache_dir: str, env: dict):
    os.environ.update(env or {})
    from mab.research import worker
    worker.main(db_path, jid, cache_dir)


class Pool:
    """Runs queued jobs from one or more workspace databases in separate processes, within budgets."""

    def __init__(self, databases: Callable[[], List[Tuple[str, str]]], cache_dir: str, max_workers: int = None,
                 timeout_s: float = 900.0, max_memory_mb: float = 1500.0, poll_s: float = 1.0, env: dict = None):
        cpu = os.cpu_count() or 2
        self.max_workers = max(1, min(int(max_workers or max(1, cpu - 1)), cpu))
        self.databases = databases
        self.cache_dir = cache_dir
        self.timeout_s, self.max_mem = timeout_s, max_memory_mb
        self.poll_s = poll_s
        self.env = env or {}
        self.running: Dict[str, dict] = {}                 # job id -> {proc, start, db, peak}
        self.lock = threading.Lock()
        self.thread: Optional[threading.Thread] = None
        self.stop_evt = threading.Event()
        self.finished = 0
        self.failed = 0
        self.ctx = multiprocessing.get_context("spawn")

    def start(self):
        if self.thread is None:
            self.thread = threading.Thread(target=self._loop, name="research-pool", daemon=True)
            self.thread.start()
        return self

    def stop(self):
        self.stop_evt.set()
        with self.lock:
            for jid, r in list(self.running.items()):
                if r["proc"].is_alive():
                    r["proc"].terminate()
                self._queue(r["db"]).fail(jid, "stopped: the program was closing")

    def _queue(self, db: str) -> JobQueue:
        from mab.storage import Storage
        return JobQueue(Storage(db))

    def _loop(self):
        while not self.stop_evt.is_set():
            try:
                self.tick()
            except Exception as e:                                      # noqa: BLE001
                log.warning("research pool: %s", e)
            self.stop_evt.wait(self.poll_s)

    def tick(self):
        with self.lock:
            for jid, r in list(self.running.items()):
                p = r["proc"]
                q = self._queue(r["db"])
                mem = process_rss_mb(p.pid) if p.is_alive() else None
                if mem:
                    r["peak"] = max(r["peak"], mem)
                if not p.is_alive():
                    p.join(0.1)
                    j = q.get(jid)
                    if j and j["state"] == "running":
                        q.fail(jid, f"the worker stopped unexpectedly (exit code {p.exitcode})")
                        self.failed += 1
                    else:
                        self.finished += 1
                        if j and j.get("peak_mb") is None:
                            q.st.write("UPDATE research_jobs SET peak_mb=? WHERE job_id=?", (round(r["peak"], 1), jid))
                    del self.running[jid]
                    continue
                if time.time() - r["start"] > self.timeout_s:
                    p.terminate()
                    q.fail(jid, f"time budget exceeded ({self.timeout_s:.0f}s); stopped")
                    self.failed += 1
                    del self.running[jid]
                elif mem and mem > self.max_mem:
                    p.terminate()
                    q.fail(jid, f"memory budget exceeded ({mem:.0f} MB > {self.max_mem:.0f} MB); stopped")
                    self.failed += 1
                    del self.running[jid]
                else:
                    q.st.write("UPDATE research_jobs SET peak_mb=? WHERE job_id=?", (round(r["peak"], 1), jid))
            for ws, db in self.databases():
                while len(self.running) < self.max_workers:
                    q = self._queue(db)
                    j = q.claim(f"pool-{os.getpid()}")
                    if j is None:
                        break
                    p = self.ctx.Process(target=_child, args=(db, j["job_id"], self.cache_dir, self.env),
                                         name=f"research-{j['job_id']}", daemon=True)
                    p.start()
                    self.running[j["job_id"]] = {"proc": p, "start": time.time(), "db": db, "peak": 0.0, "workspace": ws}

    def status(self) -> dict:
        with self.lock:
            run = [{"job_id": k, "seconds": round(time.time() - v["start"], 1), "peak_mb": round(v["peak"], 1),
                    "pid": v["proc"].pid, "workspace": v["workspace"]} for k, v in self.running.items()]
        return {"max_workers": self.max_workers, "running": run, "busy": len(run), "finished": self.finished,
                "failed": self.failed, "timeout_s": self.timeout_s, "max_memory_mb": self.max_mem,
                "cpu_percent": cpu_percent(), "hardware": describe(self.max_workers)}
