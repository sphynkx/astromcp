"""
Loads help/methodology text from the help_texts/ directory at the project
root (a sibling of engine/, not inside it - deliberately not named "docs/"
to avoid confusion with human-facing documentation like README.md; these
files are guidance for an LLM client, read on demand via the `help` tool).

Adding a new topic is just adding a new help_texts/<topic>.md file - no
code change needed, and it's automatically listed in the overview topic's
"available topics" output.
"""

from pathlib import Path
from typing import List

HELP_DIR = Path(__file__).resolve().parent.parent / "help_texts"


def list_help_topics() -> List[str]:
    if not HELP_DIR.is_dir():
        return []
    return sorted(p.stem for p in HELP_DIR.glob("*.md"))


def get_help(topic: str = "overview") -> str:
    topic = (topic or "overview").strip().lower()
    path = HELP_DIR / f"{topic}.md"
    if path.is_file():
        return path.read_text(encoding="utf-8")

    topics = list_help_topics()
    topics_list = "\n".join(f"- {t}" for t in topics) if topics else "(none found)"
    return (
        f"No help topic named '{topic}'.\n\n"
        f"Available topics:\n{topics_list}\n\n"
        f"Call help() with no arguments for the overview."
    )
