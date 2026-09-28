"""
Gemini-backed video description: turns YouTube videos into text (this
service has no native video/audio input - see help_texts/video_description.md
for the prompt and the reasoning). Run as a submit_job job by app.py's
describe_videos_start; never called synchronously from a route handler.

Shape of a batch (run_batch):
  - The URL list is split into "units" - one request each. Default is one
    video per unit (group_size=1): a long video's description alone runs
    ~1 KB of text per minute of video, so several long videos cannot share
    one response. group_size>1 (max 10, Gemini's per-request video cap)
    is for short clips only.
  - Every finished unit is stored immediately (kv, compressed, 30-day TTL)
    keyed by video ids + prompt hash. Re-submitting the same URLs is
    therefore free: finished units come back as "cached" without touching
    Gemini. That is also how an interrupted or quota-limited batch resumes.
  - Transient failures are retried with backoff. Enough consecutive
    failures ("circuit breaker") stop the batch instead of burning more
    requests; whatever wasn't attempted is reported as "deferred".
  - Local guards against the free tier's daily caps (see config.py).
  - Text is read back in pages (read_unit_page) - full text, no
    summarizing; pages exist because one MCP tool result can't carry a
    multi-hour batch.

GEMINI_API_KEY is read from the environment by google-genai itself (it
auto-detects the unprefixed GEMINI_API_KEY / GOOGLE_API_KEY), which is why
it isn't routed through config.py's ASTROMCP_* settings.
"""

import hashlib
import logging
import os
import random
import re
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from . import config
from . import jobs

logger = logging.getLogger("astromcp")

DEFAULT_MODEL = "gemini-flash-latest"  # alias Google keeps on its current
                                        # flash model - no dated version to go stale

MAX_GROUP_SIZE = 10          # Gemini's documented per-request video cap
DEFAULT_PAGE_CHARS = 100_000
MAX_PAGE_CHARS = 150_000     # tool results are capped near 1 MB; Cyrillic can
                             # cost up to ~6 bytes/char if a serializer escapes it
# Static-mode video costs about 100 tokens/second at default media
# resolution (Gemini video docs); the prompt itself is ~1.5K tokens.
_TOKENS_PER_VIDEO_SECOND = 100.0
_PROMPT_TOKENS_ESTIMATE = 1500

_sleep = time.sleep  # patched in tests

_FENCE_RE = re.compile(r"^\s*```(?:markdown)?\s*\n(.*)\n```\s*$", re.DOTALL)

_MULTI_VIDEO_INSTRUCTION = """

ВАЖНО: тебе передано {n} отдельных видео (в указанном порядке). Это может
быть один и тот же человек в разных ситуациях/настроениях/обстановке, или
разные фрагменты одной темы - в любом случае НЕ смешивай их в единый
пересказ. Для КАЖДОГО видео сделай полностью самостоятельный раздел (по
всей структуре, описанной выше - обстановка, участники, хроника с
таймкодами), с явным заголовком вида "## Видео N" (нумерация в порядке
получения, начиная с 1), прежде чем переходить к следующему видео.
"""

_METHODOLOGY_PATH = Path(__file__).resolve().parent.parent / "help_texts" / "video_description.md"


def is_configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


def default_prompt() -> str:
    """The elicitation prompt, read from help_texts/video_description.md's
    fenced '## The prompt' block - the one place its text lives."""
    text = _METHODOLOGY_PATH.read_text(encoding="utf-8")
    match = re.search(r"## The prompt\s*\n.*?```\n(.*?)\n```", text, re.DOTALL)
    if not match:
        raise RuntimeError(
            f"Could not find the fenced prompt block in {_METHODOLOGY_PATH} - "
            f"has the '## The prompt' section been edited/renamed?"
        )
    return match.group(1).strip()


def _strip_outer_fence(text: str) -> str:
    """Gemini sometimes reads "answer as one markdown block" literally and
    wraps the whole reply in a ``` fence. Strip that wrapper - only when the
    ENTIRE text is one fence, anchored at both ends; fences inside the
    content are never touched."""
    match = _FENCE_RE.match(text)
    return match.group(1) if match else text


# --------------------------------------------------------------------------
# errors
# --------------------------------------------------------------------------

class GeminiCallError(Exception):
    """kind:
      transient     - 500/502/503/504, network trouble: retry, and counts
                      toward the circuit breaker
      quota_minute  - 429 that looks per-minute: wait, retry
      quota_daily   - 429 that looks per-day: stop the whole batch
      fatal         - 401/403/404 (bad key, retired model, ...): every unit
                      would fail the same way, stop the whole batch
      permanent     - anything else (e.g. 400 for one bad/private video):
                      this unit fails, the batch continues
    """

    def __init__(self, kind: str, message: str, code: Optional[int] = None,
                 retry_after: Optional[float] = None):
        super().__init__(message)
        self.kind = kind
        self.message = message
        self.code = code
        self.retry_after = retry_after


def _classify(exc: Exception) -> GeminiCallError:
    """Best-effort mapping of a google-genai exception to a GeminiCallError.
    The daily-vs-minute 429 split is a HEURISTIC on the message text (Google
    doesn't expose the exhausted quota as a field); when in doubt it errs
    toward 'minute', i.e. retry rather than abort."""
    text = f"{type(exc).__name__}: {exc}"
    code = getattr(exc, "code", None)
    if not isinstance(code, int):
        m = re.search(r"\b([45]\d\d)\b", str(exc)[:40])
        code = int(m.group(1)) if m else None

    retry_after = None
    m = (re.search(r"retry in ([\d.]+)\s*s", text, re.I)
         or re.search(r"retryDelay['\"]?\s*:\s*['\"]([\d.]+)s", text))
    if m:
        try:
            retry_after = float(m.group(1))
        except ValueError:
            pass

    if code == 429:
        daily = re.search(r"per\s*day|PerDay|daily", text, re.I)
        return GeminiCallError("quota_daily" if daily else "quota_minute", text, code, retry_after)
    if code in (500, 502, 503, 504) or code is None:
        return GeminiCallError("transient", text, code, retry_after)
    if code in (401, 403, 404):
        return GeminiCallError("fatal", text, code)
    return GeminiCallError("permanent", text, code)


# --------------------------------------------------------------------------
# daily budget (local counters - asking Gemini would itself cost a request)
# --------------------------------------------------------------------------

def _pacific_day() -> str:
    """Gemini's per-day quotas reset at midnight Pacific time (rate-limits
    docs). The 8 h/day YouTube cap's day boundary isn't documented; this
    assumes the same one."""
    try:
        from zoneinfo import ZoneInfo
        now = datetime.now(ZoneInfo("America/Los_Angeles"))
    except Exception:
        now = datetime.now(timezone(timedelta(hours=-8)))
    return now.strftime("%Y-%m-%d")


_BUDGET_TTL = 3 * 86400


def _budget_add(requests: int = 0, video_seconds: float = 0.0) -> None:
    day = _pacific_day()
    if requests:
        jobs.kv_hincr("gemini_budget", day, "requests", requests, _BUDGET_TTL)
    if video_seconds:
        jobs.kv_hincr("gemini_budget", day, "video_seconds", video_seconds, _BUDGET_TTL)


def budget_snapshot() -> Dict[str, Any]:
    """Today's (Pacific-day) usage as THIS service counted it. Requests are
    exact for calls made through this service - failed attempts included,
    since reports say Gemini counts 503s against the quota; video hours are
    an estimate from prompt-token usage. Calls made elsewhere with the same
    key/project (AI Studio, other scripts) are invisible here - Google's
    own usage dashboard (delayed ~15 min) is the authority."""
    day = _pacific_day()
    h = jobs.kv_hgetall("gemini_budget", day)
    return {
        "pacific_day": day,
        "requests_counted": int(h.get("requests", 0)),
        "video_hours_estimated": round(h.get("video_seconds", 0.0) / 3600.0, 2),
        "limits": {
            "daily_video_hours": config.GEMINI_DAILY_VIDEO_HOURS or None,
            "daily_requests": config.GEMINI_DAILY_REQUESTS or None,
        },
    }


def _budget_exceeded() -> Optional[str]:
    snap = budget_snapshot()
    if config.GEMINI_DAILY_VIDEO_HOURS and snap["video_hours_estimated"] >= config.GEMINI_DAILY_VIDEO_HOURS:
        return (f"daily video budget reached (~{snap['video_hours_estimated']} h of "
                f"{config.GEMINI_DAILY_VIDEO_HOURS} h, Pacific day {snap['pacific_day']})")
    if config.GEMINI_DAILY_REQUESTS and snap["requests_counted"] >= config.GEMINI_DAILY_REQUESTS:
        return (f"daily request budget reached ({snap['requests_counted']} of "
                f"{config.GEMINI_DAILY_REQUESTS}, Pacific day {snap['pacific_day']})")
    return None


# --------------------------------------------------------------------------
# the actual API calls - the only functions that touch google-genai
# --------------------------------------------------------------------------

def _build_contents(youtube_urls: List[str], prompt: str):
    from google.genai import types

    parts = [types.Part(file_data=types.FileData(file_uri=url)) for url in youtube_urls]
    parts.append(types.Part(text=prompt))
    return types.Content(parts=parts)


def _generate_once(youtube_urls: List[str], prompt: str, model: str) -> Dict[str, Any]:
    """One streaming request. Streaming (generate_content_stream) because
    Gemini's docs recommend it for long videos - a non-streaming request
    that hits backend retries can outlive the connection/auth window and
    surface as a 401 or timeout. Raises raw SDK exceptions; the caller
    classifies them."""
    from google import genai

    # The SDK's "automatic function calling ... not recommended" notice is
    # deliberately left alone: we never pass tools=, so AFC has nothing to
    # act on, and explicitly disabling it has documented sharp edges of its
    # own for zero benefit here.
    client = genai.Client()
    parts: List[str] = []
    usage = None
    for chunk in client.models.generate_content_stream(
        model=model, contents=_build_contents(youtube_urls, prompt)
    ):
        piece = getattr(chunk, "text", None)
        if piece:
            parts.append(piece)
        um = getattr(chunk, "usage_metadata", None)
        if um is not None:
            usage = um
    return {
        "text": "".join(parts),
        "prompt_tokens": getattr(usage, "prompt_token_count", None),
    }


def _generate_probe(model: str) -> None:
    """Smallest possible real generation request - answers only "is this
    model taking requests right now". Costs one request against RPM/RPD
    (there is no free capacity endpoint that I could find - see
    help_texts/video_description.md); success means "no error", the
    reply's content is irrelevant."""
    from google import genai
    from google.genai import types

    client = genai.Client()
    client.models.generate_content(
        model=model,
        contents="Ответь одним словом: ok",
        config=types.GenerateContentConfig(max_output_tokens=64),
    )


def _generate_with_retry(youtube_urls: List[str], prompt: str, model: str) -> Dict[str, Any]:
    """Runs _generate_once with the retry policy. Every attempt - failed
    ones too - is counted as a request in the daily budget. Raises
    GeminiCallError when out of attempts or on a non-retryable error."""
    attempts = max(1, config.GEMINI_MAX_ATTEMPTS)
    last: Optional[GeminiCallError] = None
    for attempt in range(1, attempts + 1):
        _budget_add(requests=1)
        try:
            return _generate_once(youtube_urls, prompt, model)
        except Exception as exc:  # noqa: BLE001 - classified below
            err = exc if isinstance(exc, GeminiCallError) else _classify(exc)
            last = err
            if err.kind in ("transient", "quota_minute") and attempt < attempts:
                base = config.GEMINI_RETRY_BASE_SECONDS * (2 ** (attempt - 1))
                delay = err.retry_after if err.retry_after else base
                delay += random.uniform(0, 0.2) * delay
                logger.warning("gemini: %s (attempt %d/%d), retrying in %.0fs: %s",
                               err.kind, attempt, attempts, delay, err.message[:200])
                _sleep(delay)
                continue
            raise err
    raise last  # unreachable, keeps type-checkers quiet


# --------------------------------------------------------------------------
# batch planning / storage
# --------------------------------------------------------------------------

def _video_id(url: str) -> str:
    m = re.search(r"(?:[?&]v=|youtu\.be/|/shorts/|/live/|/embed/)([A-Za-z0-9_-]{6,})", url)
    return m.group(1) if m else hashlib.sha1(url.encode("utf-8")).hexdigest()[:12]


def _prompt_hash(prompt: str) -> str:
    return hashlib.sha1(prompt.encode("utf-8")).hexdigest()[:10]


def _plan_units(youtube_urls: List[str], group_size: int, prompt_hash: str) -> List[Dict[str, Any]]:
    seen = set()
    unique: List[str] = []
    for url in youtube_urls:
        vid = _video_id(url)
        if vid in seen:
            continue
        seen.add(vid)
        unique.append(url)
    group_size = max(1, min(int(group_size), MAX_GROUP_SIZE))
    units = []
    for i in range(0, len(unique), group_size):
        urls = unique[i:i + group_size]
        ids = [_video_id(u) for u in urls]
        ids_key = ids[0] if len(ids) == 1 else hashlib.sha1("+".join(ids).encode()).hexdigest()[:16]
        units.append({"index": len(units), "urls": urls, "cache_key": f"{prompt_hash}:{ids_key}"})
    return units


def _ttl() -> int:
    return max(1, config.VIDEO_CACHE_TTL_DAYS) * 86400


def _entry(unit: Dict[str, Any], status: str, **extra: Any) -> Dict[str, Any]:
    return {"unit_index": unit["index"], "youtube_urls": unit["urls"],
            "cache_key": unit["cache_key"], "status": status, **extra}


class _Breaker:
    """Shared by a batch's workers. Trips on a fatal/daily-quota error
    immediately, or after N consecutive units that failed even after
    retries; any success resets the streak."""

    def __init__(self, threshold: int):
        self.threshold = max(1, threshold)
        self.consecutive = 0
        self.reason: Optional[str] = None
        self.lock = threading.Lock()

    def trip(self, reason: str) -> None:
        with self.lock:
            if self.reason is None:
                self.reason = reason

    def success(self) -> None:
        with self.lock:
            self.consecutive = 0

    def failure(self, reason: str) -> None:
        with self.lock:
            self.consecutive += 1
            if self.consecutive >= self.threshold and self.reason is None:
                self.reason = f"gemini busy/unavailable - {self.consecutive} units in a row failed; last: {reason}"


def _process_unit(unit: Dict[str, Any], prompt: str, model: str, breaker: _Breaker) -> Dict[str, Any]:
    effective_prompt = prompt
    if len(unit["urls"]) > 1:
        effective_prompt += _MULTI_VIDEO_INSTRUCTION.format(n=len(unit["urls"]))
    try:
        out = _generate_with_retry(unit["urls"], effective_prompt, model)
    except GeminiCallError as err:
        reason = f"{err.kind}: {err.message[:400]}"
        if err.kind == "quota_daily":
            breaker.trip(f"daily quota exhausted - {err.message[:200]}")
        elif err.kind == "fatal":
            breaker.trip(f"non-retryable error, every unit would fail the same way - {err.message[:200]}")
        elif err.kind in ("transient", "quota_minute"):
            breaker.failure(reason)
        return _entry(unit, "failed", reason=reason)

    text = _strip_outer_fence(out.get("text") or "")
    if not text.strip():
        # Documented Gemini behavior: blocked/unfetchable content can come
        # back as an empty reply without an error. Not transient - retrying
        # the same video the same way won't change it.
        return _entry(unit, "failed",
                      reason="empty response - blocked by a safety filter, or the video wasn't accessible")

    prompt_tokens = out.get("prompt_tokens")
    est_seconds = (max(prompt_tokens - _PROMPT_TOKENS_ESTIMATE, 0) / _TOKENS_PER_VIDEO_SECOND
                   if isinstance(prompt_tokens, (int, float)) else 0.0)
    jobs.kv_set("video_text", unit["cache_key"], {
        "text": text, "model": model, "youtube_urls": unit["urls"],
        "created_at": time.time(), "prompt_tokens": prompt_tokens,
        "est_video_seconds": est_seconds,
    }, ttl_seconds=_ttl(), compress=True)
    _budget_add(video_seconds=est_seconds)
    breaker.success()
    return _entry(unit, "done", model=model, text_length=len(text),
                  est_video_seconds=round(est_seconds))


def _save_progress(job_id: Optional[str], phase: str, total: int,
                   entries: Dict[int, Dict[str, Any]], aborted: Optional[str]) -> None:
    if not job_id:
        return
    counts = {"done": 0, "cached": 0, "failed": 0}
    for e in entries.values():
        if e["status"] in counts:
            counts[e["status"]] += 1
    jobs.kv_set("video_progress", job_id, {
        "phase": phase, "units_total": total, "units_finished": len(entries),
        **counts, "aborted": aborted, "updated_at": time.time(),
    }, ttl_seconds=3 * 86400)


def run_batch(
    youtube_urls: List[str],
    prompt: str,
    model: str = DEFAULT_MODEL,
    group_size: int = 1,
    probe: bool = True,
    refresh: bool = False,
) -> Dict[str, Any]:
    """The job body. Returns a small INDEX (per-unit status), never the
    text itself - read text with read_unit_page.

    probe: with 2+ units left to run, first send one tiny real request; if
    the model is refusing right now, stop before touching any video. Costs
    one request from the daily budget; skipped for a single unit (there the
    real request is its own probe and a failed attempt costs the same).
    refresh: ignore cached results and re-describe.
    """
    if not is_configured():
        return {"available": False,
                "reason": "GEMINI_API_KEY (or GOOGLE_API_KEY) not set in the environment"}
    if not youtube_urls:
        return {"available": False, "reason": "youtube_urls is empty"}

    job_id = jobs.current_job_id()
    units = _plan_units(youtube_urls, group_size, _prompt_hash(prompt))
    entries: Dict[int, Dict[str, Any]] = {}
    pending: List[Dict[str, Any]] = []
    for unit in units:
        cached = None if refresh else jobs.kv_get("video_text", unit["cache_key"])
        if cached:
            entries[unit["index"]] = _entry(unit, "cached", model=cached.get("model"),
                                            text_length=len(cached.get("text", "")))
        else:
            pending.append(unit)

    breaker = _Breaker(config.GEMINI_BREAKER_THRESHOLD)
    _save_progress(job_id, "starting", len(units), entries, None)

    if len(pending) >= 2 and probe:
        _save_progress(job_id, "probe", len(units), entries, None)
        _budget_add(requests=1)
        try:
            _generate_probe(model)
        except Exception as exc:  # noqa: BLE001
            err = _classify(exc)
            breaker.trip(f"probe failed, no video was sent - {err.kind}: {err.message[:300]}")

    lock = threading.Lock()
    todo = iter(pending)

    def worker() -> None:
        while True:
            with lock:
                if breaker.reason:
                    return
                over = _budget_exceeded()
                if over:
                    breaker.trip(over)
                    return
                unit = next(todo, None)
                if unit is None:
                    return
            entry = _process_unit(unit, prompt, model, breaker)
            with lock:
                entries[unit["index"]] = entry
                _save_progress(job_id, "running", len(units), entries, breaker.reason)

    if pending and not breaker.reason:
        _save_progress(job_id, "running", len(units), entries, None)
        n_workers = max(1, min(config.GEMINI_CONCURRENCY, len(pending)))
        if n_workers == 1:
            worker()
        else:
            threads = [threading.Thread(target=worker, daemon=True) for _ in range(n_workers)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

    for unit in units:
        if unit["index"] not in entries:
            entries[unit["index"]] = _entry(unit, "deferred", reason=breaker.reason or "not started")

    ordered = [entries[i] for i in range(len(units))]
    summary = {s: sum(1 for e in ordered if e["status"] == s)
               for s in ("done", "cached", "failed", "deferred")}
    _save_progress(job_id, "finished", len(units), entries, breaker.reason)
    return {
        "available": (summary["done"] + summary["cached"]) > 0,
        "model": model,
        "group_size": max(1, min(int(group_size), MAX_GROUP_SIZE)),
        "summary": summary,
        "aborted": breaker.reason,
        "units": ordered,
    }


# --------------------------------------------------------------------------
# reading results
# --------------------------------------------------------------------------

def read_unit_text(entry: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Stored record ({text, model, ...}) for a done/cached unit's index
    entry, or None if it has expired/was evicted."""
    return jobs.kv_get("video_text", entry["cache_key"])


def read_unit_page(entry: Dict[str, Any], offset: int = 0,
                   limit: Optional[int] = None) -> Dict[str, Any]:
    """One page of a unit's full text. Pages end on a line break when one
    is available in the second half of the window, so they don't cut a
    timestamped line in two; next_offset is where to continue (None at the
    end)."""
    record = read_unit_text(entry)
    if record is None:
        return {"error": "text no longer stored (expired or evicted) - re-submit the same "
                         "URLs with describe_videos_start(refresh=True) to regenerate",
                "unit_index": entry["unit_index"]}
    text = record["text"]
    total = len(text)
    limit = max(1, min(int(limit or DEFAULT_PAGE_CHARS), MAX_PAGE_CHARS))
    offset = max(0, min(int(offset or 0), total))
    end = min(offset + limit, total)
    if end < total:
        cut = text.rfind("\n", offset + limit // 2, end)
        if cut != -1:
            end = cut + 1
    return {
        "unit_index": entry["unit_index"],
        "youtube_urls": entry["youtube_urls"],
        "model": record.get("model"),
        "total_length": total,
        "offset": offset,
        "next_offset": end if end < total else None,
        "text": text[offset:end],
    }


def result_view(job: Dict[str, Any], job_id: str, unit_index: Optional[int] = None,
                offset: int = 0, limit: Optional[int] = None) -> Dict[str, Any]:
    """What describe_videos_result returns. `job` is jobs.get_job(job_id)."""
    status = job.get("status")
    if status in ("not_found", "error"):
        return job
    if status != "done":
        return {**job, "progress": jobs.kv_get("video_progress", job_id)}

    result = job.get("result") or {}
    units = result.get("units")
    if not units:
        return {"status": "done", **result}

    if unit_index is None and len(units) == 1:
        unit_index = 0
    if unit_index is None:
        return {
            "status": "done", "model": result.get("model"), "summary": result.get("summary"),
            "aborted": result.get("aborted"),
            "units": [{k: v for k, v in u.items() if k != "cache_key"} for u in units],
            "hint": "pass unit_index (and offset/next_offset for long texts) to read a unit's full text",
        }
    if not (0 <= unit_index < len(units)):
        return {"status": "done", "error": f"unit_index out of range (0..{len(units) - 1})"}

    entry = units[unit_index]
    if entry["status"] not in ("done", "cached"):
        # "status" stays the JOB's status; the unit's own outcome goes in
        # "unit_status" so a failed unit can't masquerade as a failed job.
        return {"status": "done", "unit_status": entry["status"], "aborted": result.get("aborted"),
                **{k: v for k, v in entry.items() if k not in ("cache_key", "status")}}
    return {"status": "done", **read_unit_page(entry, offset, limit)}
