"""evidence/<TASK>.md: what a worker did, in a shape the CLI can check and settle from.

    # T-01 evidence
    - **Status:** done
    ## Acceptance
    1. <the item> -> <the command or test, and its quoted output>
    ## Proposed decisions
    ### P1: <the call>
    <why>. Rejected: <the alternative>.
    ## Gotchas and follow-ups
    <what the next task should know>

A blocked task writes `- **Status:** blocked (<reason>)` and may stop there. Nothing here reads
the worker's prose for meaning: it checks the shape, so an item with nothing quoted is caught
without anyone reading it.
"""

from __future__ import annotations

import re
from pathlib import Path

from workstream import gitutil, tasks
from workstream.project import Project

DONE, BLOCKED = "done", "blocked"
STATUS_RE = re.compile(r"^[-*\s]*\*\*Status:\*\*\s*(.*?)\s*$", re.MULTILINE)
SECTION_RE = re.compile(r"^## +(.+?)\s*$", re.MULTILINE)
ITEM_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
PROPOSAL_RE = re.compile(r"^### +(P\d+)\s*:\s*(.*?)\s*$", re.MULTILINE)
ARROW_RE = re.compile(r"(?:->|→)\s*(\S.*)$")
PLACEHOLDER = "{{"


def path_for(project: Project, ws: dict, task_id: str) -> Path:
    return project.folder(ws) / "evidence" / f"{task_id}.md"


def read_at(project: Project, ws: dict, task_id: str, rev: str | None) -> str | None:
    """The evidence text at a revision, or in the working tree with none; None if absent."""
    path = path_for(project, ws, task_id)
    if rev is None:
        return path.read_text() if path.exists() else None
    proc = gitutil.run(project.root, "show", f"{rev}:{project.rel(path)}")
    return proc.stdout if proc.returncode == 0 else None


def _sections(text: str) -> dict[str, str]:
    matches = list(SECTION_RE.finditer(text))
    out = {}
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        out[match[1].lower()] = text[match.end():end].strip()
    return out


def _named(found: dict[str, str], word: str) -> str:
    """The body of the section whose heading contains word, or ""."""
    return next((body for name, body in found.items() if word in name), "")


def _acceptance_items(body: str) -> dict[int, str]:
    """{item number: its text, continuation lines included}."""
    items: dict[int, list[str]] = {}
    current = None
    for line in body.splitlines():
        match = ITEM_RE.match(line)
        if match:
            current = int(match[1])
            items[current] = [match[2]]
        elif current is not None and line.strip():
            items[current].append(line.strip())
    return {n: "\n".join(lines) for n, lines in items.items()}


def _proposals(body: str) -> list[dict]:
    matches = list(PROPOSAL_RE.finditer(body))
    found = []
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        found.append({"id": match[1], "title": match[2], "body": body[match.end():end].strip()})
    return found


def parse(text: str) -> dict:
    """{status, reason, items, proposals, gotchas}. Status is "" when it can't be read."""
    match = STATUS_RE.search(text)
    raw = match[1] if match else ""
    status, reason = "", ""
    if raw.lower().startswith(BLOCKED):
        status = BLOCKED
        reason = raw[len(BLOCKED):].strip().strip("()").strip()
    elif raw.lower() == DONE:
        status = DONE
    found = _sections(text)
    return {"status": status, "reason": reason,
            "items": _acceptance_items(_named(found, "acceptance")),
            "proposals": _proposals(_named(found, "decision")),
            "gotchas": _named(found, "gotcha")}


def _has_proof(item: str) -> bool:
    """Something after the arrow, or lines under the item: `-> ok` shows no more than `ok`
    would, but a missing proof is the mistake worth catching mechanically."""
    first, _, rest = item.partition("\n")
    return ARROW_RE.search(first) is not None or bool(rest.strip())


def problems(text: str | None, task: dict) -> list[str]:
    """Why this evidence can't settle the task. Empty means it can."""
    if text is None:
        return [f"no evidence/{task['id']}.md (`ws evidence new {task['id']}` starts one)"]
    if PLACEHOLDER in text:
        return ["still has a {{...}} placeholder to fill in"]
    parsed = parse(text)
    if not parsed["status"]:
        return ["no readable **Status:** line (done, or blocked (<reason>))"]
    if parsed["status"] == BLOCKED:
        return [] if parsed["reason"] else ["blocked without a reason"]
    found = []
    items = parsed["items"]
    for n, item in enumerate(task.get("acceptance", []), 1):
        if n not in items:
            found.append(f"acceptance item {n} is missing: {tasks.acceptance_text(item)[:80]}")
        elif not _has_proof(items[n]):
            found.append(f"acceptance item {n} has nothing quoted after `->`")
    ids = [p["id"] for p in parsed["proposals"]]
    found += [f"{i} is proposed twice" for i in sorted({i for i in ids if ids.count(i) > 1})]
    found += [f"{p['id']} has no reason under it" for p in parsed["proposals"] if not p["body"]]
    return found


def skeleton(task: dict) -> str:
    """A file with the acceptance items already in it, so a worker only writes the proof."""
    lines = [f"# {task['id']} evidence", "",
             "- **Status:** {{done, or blocked (the reason)}}", "", "## Acceptance", ""]
    for n, item in enumerate(task.get("acceptance", []), 1):
        lines.append(f"{n}. {tasks.acceptance_text(item)} -> {{{{command and quoted output}}}}")
    if not task.get("acceptance"):
        lines.append("No acceptance items.")
    lines += ["", "## Proposed decisions", "",
              "None. (A reversible call goes here as `### P1: the call`, with the reason and "
              "the rejected alternative. `ws settle` numbers it.)", "",
              "## Gotchas and follow-ups", "", "None.", ""]
    return "\n".join(lines)


def rewrite_ids(text: str, mapping: dict[str, str]) -> str:
    """Each proposal id replaced by its decision id, wherever the file mentions it."""
    for old, new in mapping.items():
        text = re.sub(rf"\b{re.escape(old)}\b", new, text)
    return text
