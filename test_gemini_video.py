#!/usr/bin/env python3
"""
test_gemini_video.py

Quick synchronous way to run engine/gemini_client.run_batch on the server
without going through Claude/MCP - for trying a new prompt wording, a new
video, or group_size. The permanent path is the describe_videos_* MCP tools;
this uses the same code, the same cache and the same daily budget.

Usage:
    python3 test_gemini_video.py [--group N] [--no-probe] [--refresh] [--model NAME] url [url ...]

Each finished video's text is written to gemini_video_<timestamp>_<unit>.md
(the store keeps a copy too - a second run of the same URLs is a cache hit
and calls Gemini not at all).
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

from dotenv import load_dotenv

load_dotenv()

from engine import gemini_client as gc  # noqa: E402

DEFAULT_VIDEO_URL = "https://www.youtube.com/watch?v=C5EKF-HaucM"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--group", type=int, default=1)
    ap.add_argument("--no-probe", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--model", default=gc.DEFAULT_MODEL)
    args = ap.parse_args()

    if not gc.is_configured():
        print("GEMINI_API_KEY (or GOOGLE_API_KEY) is not set - check .env and the "
              "working directory python-dotenv searches from.", file=sys.stderr)
        sys.exit(1)

    urls = args.urls or [DEFAULT_VIDEO_URL]
    print(f"budget before: {gc.budget_snapshot()}", file=sys.stderr)
    result = gc.run_batch(urls, gc.default_prompt(), model=args.model, group_size=args.group,
                          probe=not args.no_probe, refresh=args.refresh)
    if "units" not in result:
        print(f"FAILED: {result.get('reason')}", file=sys.stderr)
        sys.exit(1)

    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    for entry in result["units"]:
        tag = f"[{entry['unit_index']}] {entry['status']:8s} {', '.join(entry['youtube_urls'])}"
        if entry["status"] in ("done", "cached"):
            record = gc.read_unit_text(entry)
            out = Path(f"gemini_video_{stamp}_{entry['unit_index']}.md")
            out.write_text(record["text"], encoding="utf-8")
            print(f"{tag} -> {out} ({len(record['text'])} chars)", file=sys.stderr)
        else:
            print(f"{tag}: {entry.get('reason')}", file=sys.stderr)
    print(f"summary: {result['summary']}", file=sys.stderr)
    if result["aborted"]:
        print(f"stopped early: {result['aborted']}", file=sys.stderr)
    print(f"budget after: {gc.budget_snapshot()}", file=sys.stderr)
    sys.exit(0 if result["available"] else 1)


if __name__ == "__main__":
    main()
