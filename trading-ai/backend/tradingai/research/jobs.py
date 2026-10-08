"""Research jobs in the background (sections 191-192, 251-253): a small worker pool that never blocks trading or the
page. Each job reports real progress (the stage it is in), can be cancelled, and writes its result to the ledger."""

from __future__ import annotations

import threading
import time
import traceback
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, Optional

from tradingai.core.events import EventBus
from tradingai.core.ids import new_id
from tradingai.core.logs import get

log = get("research")


class Jobs:
    def __init__(self, bus: EventBus, workers: int = 2):
        self.bus = bus
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="research")
        self.jobs: dict[str, dict] = {}
        self.cancel_flags: dict[str, threading.Event] = {}
        self._lock = threading.Lock()

    def submit(self, title: str, fn: Callable[[Callable[[float, str], None], threading.Event], dict],
               meta: Optional[dict] = None) -> dict:
        jid = new_id("JOB")
        ev = threading.Event()
        job = {"job_id": jid, "title": title, "state": "queued", "progress": 0.0, "stage": "waiting for a worker",
               "created": int(time.time() * 1000), "started": None, "finished": None, "result": None,
               "error": None, "meta": meta or {}}
        with self._lock:
            self.jobs[jid] = job
            self.cancel_flags[jid] = ev

        def progress(frac: float, stage: str) -> None:
            job["progress"], job["stage"] = round(float(frac), 3), stage
            self.bus.publish("research.progress", {k: job[k] for k in ("job_id", "title", "progress", "stage",
                                                                       "state")})

        def work():
            job["state"], job["started"] = "running", int(time.time() * 1000)
            try:
                job["result"] = fn(progress, ev)
                job["state"] = "cancelled" if ev.is_set() else "done"
                job["progress"] = 1.0 if job["state"] == "done" else job["progress"]
            except Exception as e:                          # noqa: BLE001 - reported to the page, never hidden
                job["state"] = "cancelled" if type(e).__name__ == "Cancelled" else "failed"
                job["error"] = f"{type(e).__name__}: {e}"
                if job["state"] == "failed":
                    log.error(f"research job {jid} failed: {traceback.format_exc(limit=3)}")
            job["finished"] = int(time.time() * 1000)
            self.bus.publish("research.done", {k: job[k] for k in ("job_id", "title", "state", "error")},
                             severity="warning" if job["state"] == "failed" else "info")
        self.pool.submit(work)
        return self.view(jid)

    def cancel(self, jid: str) -> bool:
        ev = self.cancel_flags.get(jid)
        if ev is None:
            return False
        ev.set()
        return True

    def view(self, jid: str, with_result: bool = False) -> Optional[dict]:
        j = self.jobs.get(jid)
        if j is None:
            return None
        out = {k: v for k, v in j.items() if k != "result"}
        if with_result:
            out["result"] = j["result"]
        return out

    def list(self) -> list[dict]:
        return [self.view(j) for j in sorted(self.jobs, key=lambda k: self.jobs[k]["created"], reverse=True)][:50]

    def shutdown(self) -> None:
        for ev in self.cancel_flags.values():
            ev.set()
        self.pool.shutdown(wait=False, cancel_futures=True)
