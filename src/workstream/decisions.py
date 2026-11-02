"""DECISIONS.md: settled judgment calls, each a `## Dnnn (date, who): the call` entry.

Workers propose decisions in their evidence as P1, P2, ...; `ws settle` alone numbers them.
That is what lets parallel workers run without ever fighting over an id. `relevant` is what
keeps a worker from reading the whole log: the entries that name this task, something it
cites, a file it touches or a task it builds on, plus whatever the user decided.
"""

from __future__ import annotations

import re
from pathlib import Path

ENTRY_RE = re.compile(r"^## (D(\d+))\s*(?:\(([^)]*)\))?\s*:?\s*(.*)$", re.MULTILINE)
USER = "user"
OPEN_MARK = "**Open.**"
HEADER = "# Decisions\n\nSettled judgment calls. Append, never rewrite.\n\n---\n"


def parse(text: str) -> list[dict]:
    """[{id, number, date, who, title, text}], in file order."""
    matches = list(ENTRY_RE.finditer(text))
    entries = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        when, _, who = (match[3] or "").partition(",")
        entries.append({"id": match[1], "number": int(match[2]), "date": when.strip(),
                        "who": who.strip(), "title": match[4].strip(),
                        "text": text[match.start():end].rstrip()})
    return entries


def next_number(entries: list[dict]) -> int:
    return max((e["number"] for e in entries), default=0) + 1


def _mentions(text: str, needle: str) -> bool:
    return re.search(rf"(?<![\w/.-]){re.escape(needle)}(?![\w-])", text) is not None


def relevant(entries: list[dict], task: dict) -> list[dict]:
    """The entries this task should know. A user's call applies to everything. A template entry
    nobody filled in isn't a decision."""
    builds_on = set(task.get("blockedBy", []))
    needles = [task["id"], *task.get("findings", []), *task.get("files", [])]
    return [e for e in entries if "{{" not in e["text"]
            and (e["who"] == USER or e["who"] in builds_on
                 or any(_mentions(e["text"], n) for n in needles))]


def is_open(text: str) -> bool:
    return OPEN_MARK in text


def render_entry(number: int, date: str, who: str, title: str, body: str) -> str:
    """One entry. Closed, unless its author marked it open for someone to settle."""
    ending = "" if is_open(body) else " **Closed.**"
    return f"## D{number:03d} ({date}, {who}): {title}\n\n{body.strip()}{ending}\n"


def append(path: Path, entries: list[str]) -> None:
    """Add rendered entries at the end, creating the file on a tier that started without one."""
    text = path.read_text() if path.exists() else HEADER
    path.write_text(text.rstrip() + "\n\n" + "\n".join(entries).rstrip() + "\n")
