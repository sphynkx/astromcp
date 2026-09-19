"""
Append-only session-notes log, kept deliberately separate in PURPOSE
(though not in location) from the curated help_texts/rectification.md
and its siblings.

Those files are authored and reviewed by a human before being trusted
as standing rules - that's what makes "this is binding operating
procedure" in rectification.md mean something. This module exists for
the narrower, humbler case: an LLM client discovers something real
mid-session (a real bug in this codebase, a real empirical limitation
of a technique/parameter combination, a methodological refinement
worth testing again) and wants a future session of itself to see it
without rediscovering it from scratch - without being able to rewrite
the rules that exist specifically to keep it honest across sessions.

The notes file lives inside help_texts/ itself (not a separate
directory) so it needs no change to engine/help.py at all: get_help()
already globs help_texts/*.md and serves any topic found there, so a
note becomes readable as help("session_notes") the moment this file
exists - no code change, no restart. It is excluded from version
control via .gitignore (LLM-written, not source) while every other
file in help_texts/ stays tracked and human-curated as before.

Deliberately append-only: no edit or delete entry point is exposed
here or via any MCP tool. Promoting a note into rectification.md is a
deliberate human step (read the note, decide it's right, fold it in by
hand, discussed explicitly rather than automated) - not something this
module ever does on its own. When the log grows large, the fix is to
read it, fold anything still useful into rectification.md, and replace
this file with a fresh one by hand - not to add an automated
edit/delete tool that would let a future session quietly rewrite or
drop an earlier one's findings.
"""

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict

# Same directory get_help()/list_help_topics() already scan - see this
# module's own docstring for why that means no change to help.py is
# needed for this file to become readable.
NOTES_DIR = Path(__file__).resolve().parent.parent / "help_texts"
NOTES_FILE = NOTES_DIR / "session_notes.md"

# The topic name a client requests via help() to read this file back -
# kept in sync with NOTES_FILE's actual name rather than duplicated.
NOTES_TOPIC = NOTES_FILE.stem

_HEADER = (
    "# Session notes (LLM-written)\n\n"
    "Append-only log written by an MCP client via `rectif_note_append`, "
    "read back via `help(\"session_notes\")`. Raw field notes from real "
    "sessions - NOT reviewed or curated the way the rest of help_texts/ "
    "is, and not binding methodology on its own. If a note here turns "
    "out to matter across more than one case, it gets folded into "
    "help_texts/rectification.md by hand, as a deliberate, explicitly-"
    "discussed edit - not automatically. This file has no edit or "
    "delete tool by design (see engine/notes.py's own docstring), and "
    "is gitignored rather than committed (see .gitignore).\n"
)

# Housekeeping threshold only - nothing here truncates automatically.
# Past this point, a human should read the file, fold what's still
# useful into rectification.md, and start a fresh one.
_WARN_BYTES = 200_000


def append_note(text: str, tag: str = "") -> Dict[str, Any]:
    """
    Append a single dated (and optionally tagged) entry to NOTES_FILE,
    creating the file with a standing header on first use. Returns a
    small confirmation dict, not the file's full content - read that
    back via help("session_notes") instead.
    """
    text = (text or "").strip()
    if not text:
        raise ValueError("note text must not be empty")

    NOTES_DIR.mkdir(parents=True, exist_ok=True)

    if not NOTES_FILE.is_file():
        NOTES_FILE.write_text(_HEADER, encoding="utf-8")

    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    tag_part = f" [{tag.strip()}]" if tag and tag.strip() else ""
    entry = f"\n## {timestamp}{tag_part}\n\n{text}\n"

    # Opened, appended, and closed within this call only - never held open
    # across requests, so concurrent callers each get a fresh handle and
    # the file is safe to edit by hand between calls.
    with NOTES_FILE.open("a", encoding="utf-8") as f:
        f.write(entry)

    file_size = NOTES_FILE.stat().st_size
    result: Dict[str, Any] = {
        "status": "appended",
        "file": str(NOTES_FILE.relative_to(NOTES_DIR.parent)),
        "bytes_written": len(entry.encode("utf-8")),
        "file_size_bytes": file_size,
    }
    if file_size > _WARN_BYTES:
        result["warning"] = (
            f"session_notes.md is now {file_size} bytes, over the "
            f"{_WARN_BYTES}-byte housekeeping threshold. Consider reading "
            "it (help(\"session_notes\")), folding anything still useful "
            "into help_texts/rectification.md by hand, and replacing "
            "this file with a fresh one - this module has no auto-trim."
        )
    return result
