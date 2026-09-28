#!/usr/bin/env python3
"""
tests/test_gemini_video.py

Manual live check, not a unit test (unittest discovery imports this file but
finds nothing to run): runs engine/gemini_client.run_batch on the server
without going through Claude/MCP - for trying a new prompt wording, a new
video, or group_size. Same code, same cache and same daily budget as the
describe_videos_* MCP tools. The offline logic tests are
tests/test_gemini_batch.py.

Usage (from anywhere; .env is read from the project root):
    python3 tests/test_gemini_video.py [--group N] [--no-probe] [--refresh] [--model NAME] url [url ...]

Each finished video's text is written to gemini_video_<timestamp>_<unit>.md
in the current directory (the store keeps a copy too - a second run of the
same URLs is a cache hit and doesn't call Gemini at all).
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from engine import gemini_client as gc  # noqa: E402

DEFAULT_VIDEO_URL = "https://www.youtube.com/watch?v=C5EKF-HaucM"


def main():
    # Loaded here, not at import time, so merely importing this module (as
    # unittest discovery does) never touches the environment.
    from dotenv import load_dotenv
    load_dotenv(PROJECT_ROOT / ".env")

    ap = argparse.ArgumentParser()
    ap.add_argument("urls", nargs="*")
    ap.add_argument("--group", type=int, default=1)
    ap.add_argument("--no-probe", action="store_true")
    ap.add_argument("--refresh", action="store_true")
    ap.add_argument("--model", default=gc.DEFAULT_MODEL)
    args = ap.parse_args()

    if not gc.is_configured():
        print("GEMINI_API_KEY (or GOOGLE_API_KEY) is not set - check "
              f"{PROJECT_ROOT / '.env'}", file=sys.stderr)
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
