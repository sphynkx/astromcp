"""
Tests for engine/gemini_client.py's batch logic - retry, circuit breaker,
probe, daily budget, per-unit cache/resume, pagination - against a FAKE
generator, so they need neither network nor the google-genai package.

    python3 -m unittest discover -s tests -v

What this does NOT cover: the two functions that actually touch google-genai
(_generate_once, _generate_probe) and how the real SDK's exceptions look -
_classify is tested against exception shapes matching what real failed runs
showed ("ServerError: 503 UNAVAILABLE ...", "ClientError: 404 NOT_FOUND ..."),
not against the SDK itself.
"""

import os
import sys
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("GEMINI_API_KEY", "fake-key-for-tests")

from engine import config, jobs  # noqa: E402
from engine import gemini_client as gc  # noqa: E402


class FakeAPIError(Exception):
    def __init__(self, code, message):
        super().__init__(f"{code} {message}")
        self.code = code


def ok(text="### Хроника\n[00:01] строка\n", prompt_tokens=6000):
    return {"text": text, "prompt_tokens": prompt_tokens}


URLS = [f"https://www.youtube.com/watch?v=vid{i:08d}" for i in range(6)]


class Base(unittest.TestCase):
    def setUp(self):
        jobs._memory_kv.clear()
        jobs._memory_hash.clear()
        self._saved = {k: getattr(config, k) for k in (
            "GEMINI_CONCURRENCY", "GEMINI_MAX_ATTEMPTS", "GEMINI_RETRY_BASE_SECONDS",
            "GEMINI_BREAKER_THRESHOLD", "GEMINI_DAILY_VIDEO_HOURS", "GEMINI_DAILY_REQUESTS")}
        config.GEMINI_CONCURRENCY = 1
        config.GEMINI_MAX_ATTEMPTS = 3
        config.GEMINI_RETRY_BASE_SECONDS = 30.0
        config.GEMINI_BREAKER_THRESHOLD = 3
        config.GEMINI_DAILY_VIDEO_HOURS = 8.0
        config.GEMINI_DAILY_REQUESTS = 0
        self.sleeps = []
        self._orig = (gc._generate_once, gc._generate_probe, gc._sleep)
        gc._sleep = self.sleeps.append
        self.calls = []
        gc._generate_probe = lambda model: self.calls.append("probe")

    def tearDown(self):
        gc._generate_once, gc._generate_probe, gc._sleep = self._orig
        for k, v in self._saved.items():
            setattr(config, k, v)

    def gen(self, fn):
        def wrapped(urls, prompt, model):
            self.calls.append(tuple(urls))
            return fn(urls, prompt, model)
        gc._generate_once = wrapped

    def run_batch(self, urls, **kw):
        return gc.run_batch(urls, "PROMPT", **kw)


class Retry(Base):
    def test_transient_then_success(self):
        seq = iter([FakeAPIError(503, "UNAVAILABLE high demand"), FakeAPIError(503, "UNAVAILABLE"), None])

        def fn(u, p, m):
            r = next(seq)
            if r:
                raise r
            return ok()
        self.gen(fn)
        res = self.run_batch(URLS[:1])
        self.assertEqual(res["summary"]["done"], 1)
        self.assertEqual(len(self.sleeps), 2)
        self.assertGreaterEqual(self.sleeps[0], 30.0)
        self.assertGreaterEqual(self.sleeps[1], 60.0)          # exponential
        self.assertEqual(gc.budget_snapshot()["requests_counted"], 3)  # failed attempts count

    def test_retry_after_from_message_is_honored(self):
        seq = iter([FakeAPIError(429, "RESOURCE_EXHAUSTED. Please retry in 12.5s."), None])

        def fn(u, p, m):
            r = next(seq)
            if r:
                raise r
            return ok()
        self.gen(fn)
        self.run_batch(URLS[:1])
        self.assertTrue(12.5 <= self.sleeps[0] <= 12.5 * 1.21)

    def test_permanent_error_not_retried_and_batch_continues(self):
        def fn(u, p, m):
            if "vid00000001" in u[0]:
                raise FakeAPIError(400, "INVALID_ARGUMENT video is private")
            return ok()
        self.gen(fn)
        res = self.run_batch(URLS[:3], probe=False)
        self.assertEqual([e["status"] for e in res["units"]], ["done", "failed", "done"])
        self.assertEqual(self.sleeps, [])
        self.assertIsNone(res["aborted"])


class Breaker(Base):
    def test_consecutive_failures_stop_batch(self):
        config.GEMINI_MAX_ATTEMPTS = 1
        self.gen(lambda u, p, m: (_ for _ in ()).throw(FakeAPIError(503, "UNAVAILABLE")))
        res = self.run_batch(URLS, probe=False)
        self.assertEqual([e["status"] for e in res["units"]],
                         ["failed"] * 3 + ["deferred"] * 3)
        self.assertIn("gemini busy", res["aborted"])
        self.assertEqual(len(self.calls), 3)  # 4th..6th never sent

    def test_success_resets_streak(self):
        config.GEMINI_MAX_ATTEMPTS = 1
        pattern = iter([503, 503, None, 503, 503, None])

        def fn(u, p, m):
            c = next(pattern)
            if c:
                raise FakeAPIError(c, "UNAVAILABLE")
            return ok()
        self.gen(fn)
        res = self.run_batch(URLS, probe=False)
        self.assertIsNone(res["aborted"])
        self.assertEqual(res["summary"]["done"], 2)

    def test_fatal_error_stops_immediately(self):
        self.gen(lambda u, p, m: (_ for _ in ()).throw(FakeAPIError(404, "NOT_FOUND model no longer available")))
        res = self.run_batch(URLS, probe=False)
        self.assertEqual(res["summary"], {"done": 0, "cached": 0, "failed": 1, "deferred": 5})
        self.assertIn("non-retryable", res["aborted"])

    def test_daily_quota_stops_immediately(self):
        self.gen(lambda u, p, m: (_ for _ in ()).throw(
            FakeAPIError(429, "RESOURCE_EXHAUSTED GenerateRequestsPerDayPerProjectPerModel-FreeTier")))
        res = self.run_batch(URLS, probe=False)
        self.assertEqual(res["summary"]["deferred"], 5)
        self.assertIn("daily quota", res["aborted"])
        self.assertEqual(self.sleeps, [])  # not retried

    def test_empty_response_fails_unit_without_tripping(self):
        self.gen(lambda u, p, m: ok(text="   "))
        res = self.run_batch(URLS[:4], probe=False)
        self.assertEqual(res["summary"]["failed"], 4)
        self.assertIsNone(res["aborted"])


class Probe(Base):
    def test_failed_probe_sends_no_video(self):
        gc._generate_probe = lambda model: (_ for _ in ()).throw(FakeAPIError(503, "UNAVAILABLE"))
        self.gen(lambda u, p, m: ok())
        res = self.run_batch(URLS[:3])
        self.assertEqual(self.calls, [])
        self.assertEqual(res["summary"]["deferred"], 3)
        self.assertIn("probe failed", res["aborted"])
        self.assertEqual(gc.budget_snapshot()["requests_counted"], 1)

    def test_probe_ok_then_videos(self):
        self.gen(lambda u, p, m: ok())
        res = self.run_batch(URLS[:3])
        self.assertEqual(self.calls[0], "probe")
        self.assertEqual(res["summary"]["done"], 3)

    def test_no_probe_for_single_unit(self):
        self.gen(lambda u, p, m: ok())
        self.run_batch(URLS[:1])
        self.assertNotIn("probe", self.calls)

    def test_probe_can_be_disabled(self):
        self.gen(lambda u, p, m: ok())
        self.run_batch(URLS[:3], probe=False)
        self.assertNotIn("probe", self.calls)

    def test_no_probe_when_everything_cached(self):
        self.gen(lambda u, p, m: ok())
        self.run_batch(URLS[:3])
        self.calls.clear()
        self.run_batch(URLS[:3])
        self.assertEqual(self.calls, [])


class CacheResume(Base):
    def test_resume_only_redoes_missing(self):
        state = {"fail": True}

        def fn(u, p, m):
            if state["fail"] and "vid00000002" in u[0]:
                raise FakeAPIError(400, "INVALID_ARGUMENT")
            return ok(text=f"text for {u[0][-11:]}")
        self.gen(fn)
        first = self.run_batch(URLS[:4], probe=False)
        self.assertEqual([e["status"] for e in first["units"]], ["done", "done", "failed", "done"])
        self.calls.clear()
        state["fail"] = False
        second = self.run_batch(URLS[:4], probe=False)
        self.assertEqual([e["status"] for e in second["units"]], ["cached", "cached", "done", "cached"])
        self.assertEqual(len(self.calls), 1)

    def test_refresh_ignores_cache(self):
        self.gen(lambda u, p, m: ok())
        self.run_batch(URLS[:2], probe=False)
        self.calls.clear()
        res = self.run_batch(URLS[:2], probe=False, refresh=True)
        self.assertEqual(res["summary"]["done"], 2)
        self.assertEqual(len(self.calls), 2)

    def test_different_prompt_is_a_different_cache_entry(self):
        self.gen(lambda u, p, m: ok())
        gc.run_batch(URLS[:1], "PROMPT A")
        self.calls.clear()
        res = gc.run_batch(URLS[:1], "PROMPT B")
        self.assertEqual(res["summary"]["done"], 1)

    def test_duplicate_urls_collapsed(self):
        self.gen(lambda u, p, m: ok())
        res = self.run_batch([URLS[0], URLS[0], URLS[1]], probe=False)
        self.assertEqual(len(res["units"]), 2)

    def test_fence_wrapped_reply_is_unwrapped(self):
        self.gen(lambda u, p, m: ok(text="```markdown\n### A\nline\n```"))
        res = self.run_batch(URLS[:1])
        page = gc.read_unit_page(res["units"][0])
        self.assertEqual(page["text"], "### A\nline")


class Grouping(Base):
    def test_group_size_makes_units_and_adds_instruction(self):
        seen = []
        self.gen(lambda u, p, m: (seen.append((len(u), "Видео N" in p)), ok())[1])
        res = self.run_batch(URLS[:5], group_size=2, probe=False)
        self.assertEqual(len(res["units"]), 3)
        self.assertEqual(seen, [(2, True), (2, True), (1, False)])

    def test_group_size_clamped_to_10(self):
        self.gen(lambda u, p, m: ok())
        urls = [f"https://youtu.be/abcdefg{i:04d}" for i in range(12)]
        res = self.run_batch(urls, group_size=50, probe=False)
        self.assertEqual([len(e["youtube_urls"]) for e in res["units"]], [10, 2])


class Budget(Base):
    def test_video_hour_budget_defers_rest(self):
        config.GEMINI_DAILY_VIDEO_HOURS = 1.0
        # ~3600 s each -> (361500-1500)/100 = 3600 s = 1 h
        self.gen(lambda u, p, m: ok(prompt_tokens=361500))
        res = self.run_batch(URLS[:4], probe=False)
        self.assertEqual(res["summary"]["done"], 1)
        self.assertEqual(res["summary"]["deferred"], 3)
        self.assertIn("daily video budget", res["aborted"])
        snap = gc.budget_snapshot()
        self.assertEqual(snap["video_hours_estimated"], 1.0)

    def test_request_budget(self):
        config.GEMINI_DAILY_REQUESTS = 2
        self.gen(lambda u, p, m: ok())
        res = self.run_batch(URLS[:5], probe=False)
        self.assertEqual(res["summary"]["done"], 2)
        self.assertIn("request budget", res["aborted"])

    def test_disabled_when_zero(self):
        config.GEMINI_DAILY_VIDEO_HOURS = 0
        self.gen(lambda u, p, m: ok(prompt_tokens=10_000_000))
        res = self.run_batch(URLS[:3], probe=False)
        self.assertEqual(res["summary"]["done"], 3)

    def test_budget_resets_on_a_new_pacific_day(self):
        self.gen(lambda u, p, m: ok(prompt_tokens=361500))
        config.GEMINI_DAILY_VIDEO_HOURS = 1.0
        orig = gc._pacific_day
        gc._pacific_day = lambda: "2026-01-01"
        try:
            self.run_batch(URLS[:1], probe=False)
            gc._pacific_day = lambda: "2026-01-02"
            res = self.run_batch(URLS[1:2], probe=False)
        finally:
            gc._pacific_day = orig
        self.assertEqual(res["summary"]["done"], 1)


class Concurrency(Base):
    def test_parallel_workers_finish_everything_once(self):
        config.GEMINI_CONCURRENCY = 3
        self.gen(lambda u, p, m: (time.sleep(0.01), ok(text=u[0]))[1])
        res = self.run_batch(URLS, probe=False)
        self.assertEqual(res["summary"]["done"], 6)
        self.assertEqual(sorted(self.calls), sorted((u,) for u in URLS))
        for e in res["units"]:
            self.assertEqual(gc.read_unit_page(e)["text"], e["youtube_urls"][0])


class Pagination(Base):
    def make(self, text):
        self.gen(lambda u, p, m: ok(text=text))
        return self.run_batch(URLS[:1])["units"][0]

    def test_pages_reassemble_exactly(self):
        text = "\n".join(f"[{i:05d}] " + "слово " * 8 for i in range(3000))
        entry = self.make(text)
        out, offset, pages = [], 0, 0
        while offset is not None:
            page = gc.read_unit_page(entry, offset, 20_000)
            self.assertLessEqual(len(page["text"]), 20_000)
            self.assertEqual(page["offset"], offset)
            out.append(page["text"])
            offset = page["next_offset"]
            pages += 1
        self.assertEqual("".join(out), text)
        self.assertGreater(pages, 5)

    def test_pages_break_on_line_boundaries(self):
        text = "\n".join(f"line {i:05d}" for i in range(5000))
        entry = self.make(text)
        page = gc.read_unit_page(entry, 0, 1000)
        self.assertTrue(page["text"].endswith("\n"))

    def test_limit_is_clamped(self):
        entry = self.make("x" * (gc.MAX_PAGE_CHARS + 5000))
        page = gc.read_unit_page(entry, 0, 10_000_000)
        self.assertEqual(len(page["text"]), gc.MAX_PAGE_CHARS)
        self.assertIsNotNone(page["next_offset"])

    def test_no_newline_falls_back_to_hard_cut(self):
        entry = self.make("y" * 5000)
        page = gc.read_unit_page(entry, 0, 1000)
        self.assertEqual(len(page["text"]), 1000)

    def test_offset_past_end(self):
        entry = self.make("abc")
        page = gc.read_unit_page(entry, 99)
        self.assertEqual(page["text"], "")
        self.assertIsNone(page["next_offset"])


class ResultView(Base):
    def job(self, res):
        return {"status": "done", "result": res}

    def test_single_unit_returns_text_directly(self):
        self.gen(lambda u, p, m: ok(text="hello"))
        res = self.run_batch(URLS[:1])
        view = gc.result_view(self.job(res), "j")
        self.assertEqual(view["text"], "hello")

    def test_multi_unit_returns_index_without_cache_keys(self):
        self.gen(lambda u, p, m: ok())
        res = self.run_batch(URLS[:3], probe=False)
        view = gc.result_view(self.job(res), "j")
        self.assertEqual(len(view["units"]), 3)
        self.assertNotIn("cache_key", view["units"][0])
        self.assertIn("hint", view)

    def test_unit_index_reads_text_and_bounds_checked(self):
        self.gen(lambda u, p, m: ok(text=u[0]))
        res = self.run_batch(URLS[:3], probe=False)
        self.assertEqual(gc.result_view(self.job(res), "j", 2)["text"], URLS[2])
        self.assertIn("out of range", gc.result_view(self.job(res), "j", 9)["error"])

    def test_failed_unit_reports_reason_and_aborted(self):
        self.gen(lambda u, p, m: (_ for _ in ()).throw(FakeAPIError(404, "NOT_FOUND")))
        res = self.run_batch(URLS[:3], probe=False)
        view = gc.result_view(self.job(res), "j", 0)
        self.assertEqual(view["status"], "done")          # the JOB is done...
        self.assertEqual(view["unit_status"], "failed")   # ...this unit isn't
        self.assertIn("reason", view)
        self.assertIsNotNone(view["aborted"])

    def test_expired_text_gives_actionable_error(self):
        self.gen(lambda u, p, m: ok())
        res = self.run_batch(URLS[:1])
        jobs._memory_kv.clear()
        view = gc.result_view(self.job(res), "j")
        self.assertIn("refresh=True", view["error"])

    def test_running_job_shows_progress(self):
        jobs.kv_set("video_progress", "j", {"phase": "running", "done": 2})
        view = gc.result_view({"status": "running", "elapsed_seconds": 5.0}, "j")
        self.assertEqual(view["progress"]["done"], 2)


class Classify(unittest.TestCase):
    def test_shapes_seen_in_real_runs(self):
        c = gc._classify(Exception("503 UNAVAILABLE. {'error': {'code': 503, 'message': 'high demand'}}"))
        self.assertEqual((c.kind, c.code), ("transient", 503))
        c = gc._classify(Exception("404 NOT_FOUND. {'error': {'message': 'no longer available to new users'}}"))
        self.assertEqual((c.kind, c.code), ("fatal", 404))

    def test_no_code_is_transient(self):
        self.assertEqual(gc._classify(ConnectionError("reset")).kind, "transient")

    def test_429_split(self):
        self.assertEqual(gc._classify(FakeAPIError(429, "quota metric PerMinute")).kind, "quota_minute")
        self.assertEqual(gc._classify(FakeAPIError(429, "GenerateRequestsPerDay")).kind, "quota_daily")

    def test_retry_delay_field(self):
        c = gc._classify(FakeAPIError(429, "{'retryDelay': '34s'}"))
        self.assertEqual(c.retry_after, 34.0)


class RealJobPath(Base):
    def test_through_submit_job_with_progress(self):
        self.gen(lambda u, p, m: ok())
        job_id = jobs.submit_job(gc.run_batch, URLS[:3], "PROMPT", gc.DEFAULT_MODEL, 1, False, False)
        for _ in range(200):
            job = jobs.get_job(job_id)
            if job["status"] != "running":
                break
            time.sleep(0.02)
        self.assertEqual(job["status"], "done")
        self.assertEqual(job["result"]["summary"]["done"], 3)
        prog = jobs.kv_get("video_progress", job_id)
        self.assertEqual((prog["phase"], prog["done"]), ("finished", 3))
        self.assertIsNone(jobs.current_job_id())


class RedisPaths(unittest.TestCase):
    def setUp(self):
        try:
            import fakeredis
        except ImportError:
            self.skipTest("fakeredis not installed")
        self.saved = jobs._redis
        jobs._redis = fakeredis.FakeRedis()

    def tearDown(self):
        jobs._redis = self.saved

    def test_kv_roundtrip_compressed_and_plain(self):
        big = {"text": "Привет, мир! " * 5000}
        jobs.kv_set("t", "a", big, ttl_seconds=100, compress=True)
        jobs.kv_set("t", "b", {"x": 1}, ttl_seconds=100)
        self.assertEqual(jobs.kv_get("t", "a"), big)
        self.assertEqual(jobs.kv_get("t", "b"), {"x": 1})
        stored = jobs._redis.get(jobs._KV_PREFIX + "t:a")
        self.assertLess(len(stored), len(big["text"].encode()) // 5)  # actually compressed
        self.assertGreater(jobs._redis.ttl(jobs._KV_PREFIX + "t:a"), 0)
        self.assertIsNone(jobs.kv_get("t", "missing"))

    def test_counters(self):
        jobs.kv_hincr("c", "d", "requests", 1, 100)
        jobs.kv_hincr("c", "d", "requests", 2, 100)
        jobs.kv_hincr("c", "d", "video_seconds", 90.5, 100)
        self.assertEqual(jobs.kv_hgetall("c", "d"), {"requests": 3.0, "video_seconds": 90.5})

    def test_full_batch_over_redis(self):
        gen_orig = gc._generate_once
        probe_orig = gc._generate_probe
        gc._generate_once = lambda u, p, m: ok(text="из редиса\nвторая строка")
        gc._generate_probe = lambda m: None
        try:
            res = gc.run_batch(URLS[:3], "P", probe=True)
            again = gc.run_batch(URLS[:3], "P")
        finally:
            gc._generate_once, gc._generate_probe = gen_orig, probe_orig
        self.assertEqual(res["summary"]["done"], 3)
        self.assertEqual(again["summary"]["cached"], 3)
        self.assertEqual(gc.read_unit_page(again["units"][1])["text"], "из редиса\nвторая строка")


class MemoryTTL(unittest.TestCase):
    def test_expiry(self):
        jobs._memory_kv.clear()
        jobs.kv_set("t", "k", {"a": 1}, ttl_seconds=1)
        self.assertEqual(jobs.kv_get("t", "k"), {"a": 1})
        full = jobs._KV_PREFIX + "t:k"
        exp, raw = jobs._memory_kv[full]
        jobs._memory_kv[full] = (time.time() - 1, raw)
        self.assertIsNone(jobs.kv_get("t", "k"))


if __name__ == "__main__":
    unittest.main()
