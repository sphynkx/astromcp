"""
Thin wrapper around google-genai for turning video (YouTube URLs) into
text description via Gemini - see help_texts/video_description.md for the
actual elicitation prompt and why this exists (this service has no native
video/audio input of its own).

Called from app.py's describe_videos_start (submit_job - see engine/jobs.py)
since a real call, especially several videos combined into one request,
can run for minutes; never called synchronously from a route handler.

GEMINI_API_KEY is read directly from the environment here, NOT through
engine/config.py's usual ASTROMCP_*-prefixed pattern - deliberately, so
that google-genai's own Client() can auto-detect it exactly as Google's
own docs describe (the SDK looks for an unprefixed GEMINI_API_KEY or
GOOGLE_API_KEY). Renaming it to fit this project's usual prefix convention
would just mean re-implementing what the SDK already does for free.
"""

import os
import re
from pathlib import Path
from typing import Any, Dict, List, Optional

DEFAULT_MODEL = "gemini-flash-latest"  # alias Google keeps pointed at their
                                        # current flash model - avoids
                                        # hardcoding a dated version that
                                        # goes stale; matches what the user
                                        # already confirmed works via curl.

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


def is_configured() -> bool:
    return bool(os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY"))


_METHODOLOGY_PATH = Path(__file__).resolve().parent.parent / "help_texts" / "video_description.md"


def default_prompt() -> str:
    """Extracts the elicitation prompt from help_texts/video_description.md's
    fenced '## The prompt' block - the single place that prompt's actual
    text lives (see that file's own docstring for why). Shared by
    app.py's describe_videos_start and by the standalone
    test_gemini_video.py script, so neither keeps its own copy to drift
    out of sync with the methodology doc."""
    text = _METHODOLOGY_PATH.read_text(encoding="utf-8")
    match = re.search(r"## The prompt\s*\n.*?```\n(.*?)\n```", text, re.DOTALL)
    if not match:
        raise RuntimeError(
            f"Could not find the fenced prompt block in {_METHODOLOGY_PATH} - "
            f"has the '## The prompt' section been edited/renamed?"
        )
    return match.group(1).strip()


def _strip_outer_fence(text: str) -> str:
    """Gemini sometimes takes 'ответ одним markdown-блоком' literally and
    wraps its whole answer in a ``` fence, on top of the fact that the
    response is already being saved as/treated as markdown - strip that
    outer wrapper if present so downstream consumers (this project's own
    tools, ultimately Claude's own context) get plain markdown content,
    not markdown-fenced-inside-markdown. Leaves the text untouched if no
    such wrapping is present (most responses don't do this) - never
    strips fences that are part of the actual content (the regex only
    matches when the ENTIRE response is one single outer fence, anchored
    at both ends)."""
    match = _FENCE_RE.match(text)
    return match.group(1) if match else text


def _build_contents(youtube_urls: List[str], prompt: str):
    from google.genai import types

    parts = [
        types.Part(file_data=types.FileData(file_uri=url))
        for url in youtube_urls
    ]
    parts.append(types.Part(text=prompt))
    return types.Content(parts=parts)


def _call_gemini(youtube_urls: List[str], prompt: str, model: str) -> Dict[str, Any]:
    """One actual API call - one or more videos, whichever the caller
    already decided to bundle together. Never raises; every failure mode
    comes back as {"available": False, "reason": ...}."""
    try:
        from google import genai
    except ImportError as e:
        return {"available": False,
                "reason": f"google-genai not installed: {e} (pip install -U google-genai)"}

    try:
        client = genai.Client()
        # AFC (automatic function calling) prints an informational
        # "not recommended, use Chat instead" notice on every direct
        # generate_content() call - deliberately left alone rather than
        # set automatic_function_calling=AutomaticFunctionCallingConfig(
        # disable=True): we never pass `tools=`, so AFC has nothing to
        # act on either way - the notice is pure noise with zero
        # behavioral effect here, and the SDK's own issue tracker shows
        # disable=True has its own sharp edges (a second warning if
        # maximum_remote_calls isn't also set; documented cross-call
        # state bleed in mixed tool/no-tool sessions) for no benefit in
        # a call that was never going to use tools regardless.
        response = client.models.generate_content(
            model=model,
            contents=_build_contents(youtube_urls, prompt),
        )
        text = getattr(response, "text", None)
        if not text:
            # A real, documented Gemini behavior: content can come back
            # empty/blocked (safety filters, an age-restricted or
            # region-locked video Gemini couldn't actually fetch, etc.)
            # without raising - report this distinctly from a genuine
            # request failure rather than silently returning "".
            return {
                "available": False,
                "reason": (
                    "Gemini returned no text - possibly blocked or unable "
                    f"to access one of these videos. Raw response: {response!r}"
                ),
            }
        return {"available": True, "text": _strip_outer_fence(text)}
    except Exception as e:
        return {"available": False, "reason": f"{type(e).__name__}: {e}"}


def describe_videos(
    youtube_urls: List[str],
    prompt: str,
    model: str = DEFAULT_MODEL,
    combine: bool = True,
) -> Dict[str, Any]:
    """
    Describe one or more YouTube videos via Gemini.

    combine=True (default): all videos in ONE request (the multi-video
    instruction above is appended to `prompt` automatically whenever
    len(youtube_urls) > 1, so Gemini keeps them in clearly separated
    sections rather than blending the material together). Saves on
    Gemini's own daily call-count quota when processing many videos for
    one person - the user's real use case (a few dozen shorter videos of
    the same subject, combined for one composite picture) is exactly why
    this is the default, not sequential mode.

    combine=False: one separate request per video. Slower and costs more
    quota, but each video gets its own full-size context to itself - if
    combined mode turns out to degrade on a large batch (context-window
    pressure from many long videos at once is a real, untested risk with
    this API - see help_texts/video_description.md), this is the fallback
    to compare against, with no code changes needed, just this one flag.

    Single video (len(youtube_urls) == 1): combine has no effect either
    way, always exactly one request.
    """
    if not is_configured():
        return {
            "available": False,
            "reason": "GEMINI_API_KEY (or GOOGLE_API_KEY) not set in the environment",
        }
    if not youtube_urls:
        return {"available": False, "reason": "youtube_urls is empty"}

    if combine or len(youtube_urls) == 1:
        effective_prompt = prompt
        if len(youtube_urls) > 1:
            effective_prompt += _MULTI_VIDEO_INSTRUCTION.format(n=len(youtube_urls))
        result = _call_gemini(youtube_urls, effective_prompt, model)
        return {
            "mode": "combined",
            "model": model,
            "youtube_urls": youtube_urls,
            **result,
        }

    videos = []
    for url in youtube_urls:
        result = _call_gemini([url], prompt, model)
        videos.append({"youtube_url": url, **result})
    return {
        "mode": "separate",
        "model": model,
        "youtube_urls": youtube_urls,
        "videos": videos,
        "available": any(v["available"] for v in videos),
    }
