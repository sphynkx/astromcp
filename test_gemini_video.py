#!/usr/bin/env python3
"""
test_gemini_video.py

Standalone spike-test script - a quick, synchronous way to try
engine/gemini_client.py directly on the server without going through
Claude/MCP at all. The real, permanent path is the describe_videos_start
/ describe_videos_result MCP tools (app.py) - this script exists for fast
manual iteration (new prompt wording, a new video, combine vs separate)
without a round-trip through a chat session.

Usage:
    python3 test_gemini_video.py [--separate] [url1] [url2] ...

    (defaults to the single video used for this feature's first test if
    no URLs are passed; combine=True unless --separate is given)
"""

import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from engine.gemini_client import describe_videos, default_prompt, is_configured  # noqa: E402

DEFAULT_VIDEO_URL = "https://www.youtube.com/watch?v=C5EKF-HaucM"


def main():
    args = sys.argv[1:]
    combine = True
    if "--separate" in args:
        combine = False
        args.remove("--separate")

    youtube_urls = args or [DEFAULT_VIDEO_URL]

    if not is_configured():
        print("GEMINI_API_KEY (or GOOGLE_API_KEY) is not set - check .env "
              "and that this script's working directory lets python-dotenv "
              "find it.", file=sys.stderr)
        sys.exit(1)

    prompt = default_prompt()
    print(f"Requesting description for {len(youtube_urls)} video(s), "
          f"combine={combine} ...", file=sys.stderr)
    result = describe_videos(youtube_urls, prompt, combine=combine)

    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    if result["mode"] == "combined":
        if not result["available"]:
            print(f"FAILED: {result['reason']}", file=sys.stderr)
            sys.exit(1)
        out_path = Path(f"gemini_video_test_{timestamp}.md")
        out_path.write_text(result["text"], encoding="utf-8")
        print(f"OK - model={result['model']}", file=sys.stderr)
        print(f"Saved full response -> {out_path}", file=sys.stderr)
        print(f"Response length: {len(result['text'])} chars", file=sys.stderr)
        print("\n--- first 2000 chars, for a quick look ---\n", file=sys.stderr)
        print(result["text"][:2000], file=sys.stderr)
    else:  # separate
        for i, video in enumerate(result["videos"]):
            if not video["available"]:
                print(f"[{i}] FAILED ({video['youtube_url']}): {video['reason']}",
                      file=sys.stderr)
                continue
            out_path = Path(f"gemini_video_test_{timestamp}_{i}.md")
            out_path.write_text(video["text"], encoding="utf-8")
            print(f"[{i}] OK ({video['youtube_url']}) -> {out_path} "
                  f"({len(video['text'])} chars)", file=sys.stderr)
        if not result["available"]:
            sys.exit(1)


if __name__ == "__main__":
    main()
