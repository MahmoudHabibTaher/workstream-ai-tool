"""DECISIONS.md: settled judgment calls, each a `## Dnnn (date, who): the call` entry.

Workers propose decisions in their evidence as P1, P2, ...; `ws settle` alone numbers them.
That is what lets parallel workers run without ever fighting over an id. `relevant` is what
keeps a worker from reading the whole log: the entries that name this task, something it
cites, a file it touches or a task it builds on, plus whatever the user decided.
"""

from __future__ import annotations

import re
from pathlib import Path

from workstream import tasks
from workstream.errors import Refused

ENTRY_RE = re.compile(r"^## (D(\d+))\s*(?:\(([^)]*)\))?\s*:?\s*(.*)$", re.MULTILINE)
# Only as an entry's first line, so a reason quoting another entry's Closes line closes nothing.
CLOSES_RE = re.compile(r"\A## .*\n+Closes: (D\d+(?:, D\d+)*)\.")
# Anchored the same way, and after any Closes line, which has to stay first.
_TASK_ID = r"[A-Za-z0-9][A-Za-z0-9._-]*"
CHANGES_RE = re.compile(rf"\A## .*\n+(?:Closes: D\d+(?:, D\d+)*\.\n+)?"
                        rf"Changes: ({_TASK_ID}(?:, {_TASK_ID})*)\.(?=\s|\Z)")
USER = "user"
OPEN_MARK = "**Open.**"
CLOSED_MARK = "**Closed.**"
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


def mentions(text: str, needle: str) -> bool:
    return re.search(rf"(?<![\w/.-]){re.escape(needle)}(?![\w-])", text) is not None


def relevant(entries: list[dict], task: dict) -> list[dict]:
    """The entries this task should know. A user's call applies to everything. A template entry
    nobody filled in isn't a decision."""
    builds_on = set(task.get("blockedBy", []))
    needles = [task["id"], *task.get("findings", []), *task.get("files", [])]
    return [e for e in entries if "{{" not in e["text"]
            and (e["who"] == USER or e["who"] in builds_on
                 or any(mentions(e["text"], n) for n in needles))]


def is_open(text: str) -> bool:
    """Only the ending marks an entry open: a reason quoting the mark mid-text doesn't."""
    return text.rstrip().endswith(OPEN_MARK)


def open_entries(entries: list[dict]) -> list[dict]:
    """Entries with the open mark and no later entry closing them. The log is append-only, so
    an entry's own text can't say this: it takes the whole log, read in order."""
    still_open: dict[str, dict] = {}
    for entry in entries:
        closes = CLOSES_RE.search(entry["text"])
        for closed in closes[1].split(", ") if closes else []:
            still_open.pop(closed, None)
        if is_open(entry["text"]):
            still_open[entry["id"]] = entry
    return list(still_open.values())


def closing_body(entries: list[dict], closes: str, why: str) -> str:
    """`why` with the Closes line for a comma-separated list of ids, each of which must be open
    now. Refusing here is what leaves the log untouched."""
    ids = list(dict.fromkeys(part.strip() for part in closes.split(",")))
    known = {e["id"] for e in entries}
    still_open = {e["id"] for e in open_entries(entries)}
    for wanted in ids:
        if wanted not in known:
            raise Refused(f"no decision {wanted or '(empty id)'} to close")
        if wanted not in still_open:
            raise Refused(f"{wanted} is already closed")
    return f"Closes: {', '.join(ids)}.\n\n{why}"


def changing_body(rows: list[dict], changes: str, why: str) -> str:
    """`why` with the Changes line for a comma-separated list of task ids, each of which `ws update`
    must still be able to correct. Refusing here is what leaves the log untouched."""
    ids = list(dict.fromkeys(part.strip() for part in changes.split(",")))
    status = {t["id"]: t.get("status") for t in rows}
    for wanted in ids:
        if wanted not in status:
            raise Refused(f"no task {wanted or '(empty id)'} to change")
        if status[wanted] not in tasks.OPEN_STATUSES:
            raise Refused(f"{wanted} is {status[wanted]}: `ws update` can't correct it")
    return f"Changes: {', '.join(ids)}.\n\n{why}"


def changed_tasks(entry: dict) -> list[str]:
    """The tasks this entry says it changes."""
    changes = CHANGES_RE.search(entry["text"])
    return changes[1].split(", ") if changes else []


def unmarked(entries: list[dict], task: dict) -> list[str]:
    """Settled decisions that change this task and that its summary and acceptance don't name. An
    open one has settled nothing yet, so it asks for no correction."""
    still_open = {e["id"] for e in open_entries(entries)}
    marks = tasks.marks(task)
    return [e["id"] for e in entries if task["id"] in changed_tasks(e)
            and e["id"] not in still_open and e["id"] not in marks]


def render_entry(number: int, date: str, who: str, title: str, body: str) -> str:
    """One entry. Closed, unless its author marked it open for someone to settle. A body that
    already ends in the closed mark keeps that one: a reason quoting it mid-text still gets its own."""
    body = body.strip()
    ending = "" if is_open(body) or body.endswith(CLOSED_MARK) else f" {CLOSED_MARK}"
    return f"## D{number:03d} ({date}, {who}): {title}\n\n{body}{ending}\n"


def record(path: Path, date: str, who: str, title: str, body: str) -> str:
    """Add one entry with the next free number. Returns its id."""
    number = next_number(parse(path.read_text()) if path.exists() else [])
    append(path, [render_entry(number, date, who, title, body)])
    return f"D{number:03d}"


def append(path: Path, entries: list[str]) -> None:
    """Add rendered entries at the end, creating the file on a tier that started without one."""
    text = path.read_text() if path.exists() else HEADER
    path.write_text(text.rstrip() + "\n\n" + "\n".join(entries).rstrip() + "\n")
