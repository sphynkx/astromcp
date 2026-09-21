"""
Async job registry for long-running pipeline / scan calls.

Storage:
  - Redis (ASTROMCP_REDIS_URL) — persistent, survives restarts, 3-day TTL.
  - In-memory fallback — when Redis unavailable. Jobs lost on restart.

Retrieval modes:
  - get_job(id)              — full result (can be tens of MB)
  - get_job_status(id)       — lightweight: status + section list, no payload
  - get_job_section(id, key) — one top-level key of the result dict
  - iter_job_sections(id)    — generator yielding (section_name, data) pairs
                               for NDJSON streaming
"""

import json
import logging
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable, Dict, Iterator, Optional, Tuple

from . import config

logger = logging.getLogger("astromcp")

_redis = None
_memory_jobs: Dict[str, Dict[str, Any]] = {}
_lock = threading.Lock()
_executor = ThreadPoolExecutor(max_workers=4)

_REDIS_KEY_PREFIX = "astromcp:job:"
_REDIS_RESULT_TTL = 86400 * 3


def _init_redis():
    global _redis
    url = config.REDIS_URL
    if not url:
        logger.info("jobs: no REDIS_URL — in-memory storage (lost on restart)")
        return
    try:
        import redis as _redis_lib
        _redis = _redis_lib.Redis.from_url(url, decode_responses=False)
        _redis.ping()
        logger.info("jobs: Redis connected at %s", url)
    except Exception as e:
        logger.warning("jobs: Redis unavailable (%s) — in-memory fallback", e)
        _redis = None

_init_redis()


# --- storage helpers ---

def _rkey(job_id: str) -> str:
    return f"{_REDIS_KEY_PREFIX}{job_id}"

def _store(job_id: str, data: dict):
    if _redis is not None:
        _redis.set(_rkey(job_id),
                   json.dumps(data, ensure_ascii=False, default=str).encode("utf-8"),
                   ex=_REDIS_RESULT_TTL)
    else:
        with _lock:
            _memory_jobs[job_id] = data

def _load(job_id: str) -> Optional[dict]:
    if _redis is not None:
        raw = _redis.get(_rkey(job_id))
        return json.loads(raw) if raw else None
    else:
        with _lock:
            return _memory_jobs.get(job_id)

def _list_ids() -> list:
    if _redis is not None:
        keys = _redis.keys(f"{_REDIS_KEY_PREFIX}*")
        plen = len(_REDIS_KEY_PREFIX)
        return [k.decode("utf-8")[plen:] if isinstance(k, bytes) else k[plen:] for k in keys]
    else:
        with _lock:
            return list(_memory_jobs.keys())


# --- public API ---

def run_blocking(func: Callable, *args, **kwargs):
    """
    Submit synchronous, CPU-bound work (chart construction, a
    movements_scan sweep, anything that touches kerykeion/pyswisseph
    directly) to the SAME bounded thread pool submit_job's background
    jobs use, and return a concurrent.futures.Future.

    Why this exists: every @mcp.custom_route handler in app.py is a
    plain `async def` — Starlette/uvicorn route, not an MCP tool call.
    The MCP tool-call path (the official mcp.server.fastmcp.FastMCP
    dispatcher) already runs synchronous tool functions in a thread via
    anyio, so tools called over the MCP protocol were never the problem.
    But a synchronous function called DIRECTLY inside a hand-written
    `async def` custom_route handler blocks the entire event loop for
    the call's whole duration — on a full-day movements_scan sweep
    that's minutes, during which the server can't answer ANY other
    request, including trivially cheap ones like GET /astro/jobs. That
    was confirmed directly: with a heavy /astro/movements_scan call in
    flight, even /astro/jobs (a dict lookup, no astrology at all)
    stopped responding until the blocking call finished - restarting
    nginx/raising its timeouts didn't help, because the bottleneck was
    never "waited too long for a response", it was "the process could
    not produce a response to anything at all".

    Every custom_route handler that calls into engine/ synchronous code
    (build_full_report, build_natal_chart_svg, run_rectification_pipeline
    called synchronously, rectif_movements_scan, fetch_photo_as_data_uri)
    must go through this — see app.py's route handlers for the pattern:
        result = await asyncio.wrap_future(run_blocking(some_sync_func, **kwargs))

    Deliberately reuses submit_job's own _executor (bounded at
    max_workers=4) rather than asyncio.to_thread's separate default
    executor, so there is exactly ONE place controlling how much
    CPU-bound astrology work runs at once across both background jobs
    and synchronous REST calls - not two uncoordinated pools each free
    to saturate the box independently.
    """
    return _executor.submit(func, *args, **kwargs)


def submit_job(func: Callable, *args, **kwargs) -> str:
    job_id = uuid.uuid4().hex[:12]
    _store(job_id, {
        "status": "running", "result": None, "error": None,
        "started_at": time.time(), "finished_at": None,
    })
    def _run():
        try:
            result = func(*args, **kwargs)
            started = (_load(job_id) or {}).get("started_at", time.time())
            _store(job_id, {"status": "done", "result": result, "error": None,
                            "started_at": started, "finished_at": time.time()})
            logger.info("job %s completed", job_id)
        except Exception as e:
            logger.exception("job %s failed", job_id)
            started = (_load(job_id) or {}).get("started_at", time.time())
            _store(job_id, {"status": "error", "result": None, "error": str(e),
                            "started_at": started, "finished_at": time.time()})
    _executor.submit(_run)
    return job_id


def get_job(job_id: str) -> Dict[str, Any]:
    """Full result — may be tens of MB."""
    data = _load(job_id)
    if data is None:
        return {"status": "not_found"}
    elapsed = (data.get("finished_at") or time.time()) - data.get("started_at", time.time())
    out: Dict[str, Any] = {"status": data["status"], "elapsed_seconds": round(elapsed, 1)}
    if data["status"] == "done":
        out["result"] = data["result"]
    elif data["status"] == "error":
        out["error"] = data["error"]
    return out


def get_job_status(job_id: str) -> Dict[str, Any]:
    """Lightweight — no payload, just status + section list."""
    data = _load(job_id)
    if data is None:
        return {"status": "not_found"}
    elapsed = (data.get("finished_at") or time.time()) - data.get("started_at", time.time())
    out: Dict[str, Any] = {"status": data["status"], "elapsed_seconds": round(elapsed, 1)}
    if data["status"] == "done":
        result = data.get("result")
        if isinstance(result, dict):
            out["available_sections"] = list(result.keys())
            out["events_count"] = result.get("events_count")
            out["summary"] = result.get("summary")
    elif data["status"] == "error":
        out["error"] = data["error"]
    return out


def get_job_section(job_id: str, section: str) -> Dict[str, Any]:
    """One top-level key of the result."""
    data = _load(job_id)
    if data is None:
        return {"status": "not_found"}
    if data["status"] != "done":
        elapsed = (data.get("finished_at") or time.time()) - data.get("started_at", time.time())
        out = {"status": data["status"], "elapsed_seconds": round(elapsed, 1)}
        if data["status"] == "error":
            out["error"] = data["error"]
        return out
    result = data.get("result")
    if not isinstance(result, dict):
        return {"status": "done", "error": "result is not a dict"}
    if section not in result:
        return {"status": "done", "error": f"unknown section '{section}'",
                "available_sections": list(result.keys())}
    return {"status": "done", "section": section, "data": result[section]}


def iter_job_sections(job_id: str) -> Iterator[Tuple[str, Any]]:
    """Yield (section_name, section_data) pairs for streaming."""
    data = _load(job_id)
    if data is None or data["status"] != "done":
        return
    result = data.get("result")
    if not isinstance(result, dict):
        return
    for key, value in result.items():
        yield key, value


def delete_job(job_id: str) -> Dict[str, Any]:
    """
    Remove a job's stored result (from Redis, or the in-memory fallback).

    Idempotent: deleting a job_id that doesn't exist (or was already
    deleted, or already expired via the 3-day TTL) returns
    {"deleted": False} rather than raising - safe to retry or to call
    speculatively when cleaning up a batch of job_ids.
    """
    existed = _load(job_id) is not None
    if _redis is not None:
        _redis.delete(_rkey(job_id))
    else:
        with _lock:
            _memory_jobs.pop(job_id, None)
    return {"job_id": job_id, "deleted": existed}


def list_jobs() -> Dict[str, Any]:
    ids = _list_ids()
    jobs = []
    for jid in sorted(ids):
        data = _load(jid)
        if data is None:
            continue
        elapsed = (data.get("finished_at") or time.time()) - data.get("started_at", time.time())
        jobs.append({"job_id": jid, "status": data["status"], "elapsed_seconds": round(elapsed, 1)})
    return {"jobs": jobs, "count": len(jobs)}
