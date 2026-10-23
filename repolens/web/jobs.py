"""Background jobs for the web page: slow work (search, cloning, model calls) runs in a thread while the page polls
for live progress. In-memory only; the newest MAX_JOBS jobs are kept. Errors shown to the page never contain secrets."""
from __future__ import annotations

import threading
import time
import uuid
from typing import Callable

from ..redact import redact

MAX_JOBS = 50


class JobManager:
    def __init__(self, max_running: int = 2):
        self._jobs: dict[str, dict] = {}
        self._order: list[str] = []
        self._lock = threading.Lock()
        self._slots = threading.BoundedSemaphore(max_running)       # at most this many jobs work at once; others wait

    def active_for(self, owner) -> int:
        """How many of this owner's jobs are still queued or running."""
        return sum(1 for j in list(self._jobs.values()) if j["owner"] == owner and j["status"] in ("queued", "running"))

    def submit(self, kind: str, fn: Callable[[Callable[[str], None]], dict], owner=None) -> str:
        """Start `fn(progress)` in a thread. `progress(msg)` records a line the page will show. Returns the job id.
        A job can only be read back by the `owner` that submitted it."""
        job_id = uuid.uuid4().hex[:12]
        job = {"id": job_id, "kind": kind, "owner": owner, "status": "queued", "progress": [], "result": None, "error": None,
               "created": time.time(), "finished": None}
        with self._lock:
            self._jobs[job_id] = job
            self._order.append(job_id)
            for old in self._order[:-MAX_JOBS]:
                self._jobs.pop(old, None)
            self._order = self._order[-MAX_JOBS:]
        threading.Thread(target=self._run, args=(job, fn), daemon=True).start()
        return job_id

    def _run(self, job: dict, fn) -> None:
        with self._slots:
            job["status"] = "running"
            try:
                job["result"] = fn(lambda msg: job["progress"].append(redact(str(msg))[:300]))
                job["status"] = "done"
            except Exception as e:                                   # noqa: BLE001 - the page must see any failure
                job["error"] = redact(f"{type(e).__name__}: {e}")[:400]
                job["status"] = "error"
            finally:
                job["finished"] = time.time()

    def get(self, job_id: str, since: int = 0, owner=None) -> dict | None:
        """Snapshot for polling: status, progress lines from index `since`, and the result once done.
        Someone else's job looks exactly like a job that does not exist."""
        job = self._jobs.get(job_id)
        if job is None or job["owner"] != owner:
            return None
        lines = job["progress"][since:]
        done = job["status"] in ("done", "error")
        return {"id": job["id"], "kind": job["kind"], "status": job["status"], "progress": lines, "next": since + len(lines),
                "result": job["result"] if done else None, "error": job["error"],
                "seconds": round((job["finished"] or time.time()) - job["created"], 1)}
