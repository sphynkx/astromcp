"""
Simple in-memory async job registry for long-running rectif_scan calls.

MCP tool calls are subject to timeouts (client-side and reverse-proxy), and
a full-day scan across many events - especially with technique="solar_return",
whose search is iterative and several times more expensive per event than a
transit/progression/direction lookup - can comfortably exceed those timeouts
even though the server itself keeps working and eventually finishes. Rather
than trying to outrun the timeout, rectif_scan_start hands the work to a
background thread and returns immediately with a job_id; rectif_scan_result
polls for completion.

This is intentionally minimal: an in-process dict plus a thread pool. Jobs
do not survive a service restart and there's no persistence - a deliberate
simplicity trade-off for a single-operator tool, not a general job queue.
"""

import uuid
import threading
import time
import logging
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict

logger = logging.getLogger("astromcp")

_executor = ThreadPoolExecutor(max_workers=4)
_jobs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()


def submit_job(func: Callable, *args, **kwargs) -> str:
    job_id = uuid.uuid4().hex[:12]
    with _lock:
        _jobs[job_id] = {
            "status": "running",
            "result": None,
            "error": None,
            "started_at": time.time(),
            "finished_at": None,
        }

    def _run():
        try:
            result = func(*args, **kwargs)
            with _lock:
                _jobs[job_id]["status"] = "done"
                _jobs[job_id]["result"] = result
                _jobs[job_id]["finished_at"] = time.time()
        except Exception as e:
            logger.exception(f"async job {job_id} failed")
            with _lock:
                _jobs[job_id]["status"] = "error"
                _jobs[job_id]["error"] = str(e)
                _jobs[job_id]["finished_at"] = time.time()

    _executor.submit(_run)
    return job_id


def get_job(job_id: str) -> Dict[str, Any]:
    with _lock:
        job = _jobs.get(job_id)
        if job is None:
            return {"status": "not_found"}
        elapsed = (job.get("finished_at") or time.time()) - job["started_at"]
        out = {"status": job["status"], "elapsed_seconds": round(elapsed, 1)}
        if job["status"] == "done":
            out["result"] = job["result"]
        elif job["status"] == "error":
            out["error"] = job["error"]
        return out
