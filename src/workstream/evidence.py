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
    ## Text to apply
    ### `<path from the repo root>`
    <the exact text, for a file this worker can't edit>

Text to apply comes last and runs to the end of the file, so it may hold any heading at all and
nothing else here reads it as structure. A blocked task writes `- **Status:** blocked (<reason>)` and may stop there. Nothing here reads
the worker's prose for meaning: it checks the shape, so an item with nothing quoted is caught
without anyone reading it.
"""

from __future__ import annotations

import re
from pathlib import Path

from workstream import decisions, gitutil, tasks
from workstream.project import Project

DONE, BLOCKED = "done", "blocked"
STATUS_RE = re.compile(r"^[-*\s]*\*\*Status:\*\*\s*(.*?)\s*$", re.MULTILINE)
SECTION_RE = re.compile(r"^## +(.+?)\s*$", re.MULTILINE)
ITEM_RE = re.compile(r"^\s*(\d+)[.)]\s+(.*)$")
PROPOSAL_RE = re.compile(r"^### +(P\d+)\s*:\s*(.*?)\s*$", re.MULTILINE)
ARROW_RE = re.compile(r"(?:->|→)\s*(\S.*)$")
REJECTED_RE = re.compile(r"\brejected\b", re.IGNORECASE)
PLACEHOLDER = "{{"
TEXTS_RE = re.compile(r"^## +text to apply[ \t]*$", re.MULTILINE | re.IGNORECASE)
TEXT_FILE_RE = re.compile(r"^### +`([^`\n]+)`[ \t]*$", re.MULTILINE)
TEXTS_NONE = ("None. (Text for a file you can't edit goes here, whole: a line of ### `path`, "
              "relative to the repo root, then the text. Keep this section last.)")


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


def _split_texts(text: str) -> tuple[str, str, str]:
    """(everything before Text to apply, its heading, its body), the last two "" if absent.
    The first such heading counts, because the text under it may quote the heading itself."""
    match = TEXTS_RE.search(text)
    return (text[:match.start()], match[0], text[match.end():]) if match else (text, "", "")


def _texts(body: str) -> list[dict]:
    """[{path, text}] in file order. Text above the first file has the path "", for problems
    to report; only a `### ` line holding nothing but a backticked path starts a file."""
    matches = list(TEXT_FILE_RE.finditer(body))
    above = body[:matches[0].start() if matches else len(body)].strip()
    found = []
    if above and above.lower() not in ("none", "none.", TEXTS_NONE.lower()):
        found.append({"path": "", "text": above})
    for i, match in enumerate(matches):
        end = matches[i + 1].start() if i + 1 < len(matches) else len(body)
        found.append({"path": match[1].strip(), "text": body[match.end():end].strip("\n")})
    return found


def parse(text: str) -> dict:
    """{status, reason, items, proposals, gotchas, texts}. Status is "" when it can't be read."""
    text, _, texts = _split_texts(text)
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
            "gotchas": _named(found, "gotcha"),
            "texts": _texts(texts)}


def _has_proof(item: str) -> bool:
    """Something after the arrow, or lines under the item: `-> ok` shows no more than `ok`
    would, but a missing proof is the mistake worth catching mechanically."""
    first, _, rest = item.partition("\n")
    return ARROW_RE.search(first) is not None or bool(rest.strip())


def proof_of(item: str) -> str:
    """What an item quotes: after the arrow on its first line, then the lines under it."""
    first, _, rest = item.partition("\n")
    match = ARROW_RE.search(first)
    return "\n".join(part for part in (match[1] if match else "", rest.strip()) if part)


def paired_items(parsed: dict | None, task: dict) -> list[dict]:
    """Each acceptance item beside its proof, in the task's order. A proof is "" when the
    evidence quotes nothing for it, which is what a reader most needs to see."""
    items = parsed["items"] if parsed else {}
    return [{"n": n, "item": tasks.acceptance_text(item), "proof": proof_of(items.get(n, ""))}
            for n, item in enumerate(task.get("acceptance", []), 1)]


def text_problem(entry: dict) -> str | None:
    path = entry["path"]
    if not path:
        return "Text to apply has text with no file (start each with a line of ### `path`)"
    parts = re.split(r"[/\\]", path)
    if path[0] in "/\\" or re.match(r"[A-Za-z]:", path):
        return f"Text to apply names an absolute path: {path}"
    if ".." in parts:
        return f"Text to apply names a path with `..`: {path}"
    if not entry["text"].strip():
        return f"Text to apply has no text for {path}"
    return None


def problems(text: str | None, task: dict) -> list[str]:
    """Why this evidence can't settle the task. Empty means it can."""
    if text is None:
        return [f"no evidence/{task['id']}.md (`ws evidence new {task['id']}` starts one)"]
    if PLACEHOLDER in _split_texts(text)[0]:  # text to apply may be a template itself
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
    for proposal in parsed["proposals"]:
        body = proposal["body"]
        if not body:
            found.append(f"{proposal['id']} has no reason under it")
        elif not REJECTED_RE.search(body) and not decisions.is_open(body):
            # The one thing a later session can't work out from the code.
            found.append(f"{proposal['id']} doesn't say what was rejected (`Rejected: ...`)")
    found += [problem for problem in map(text_problem, parsed["texts"]) if problem]
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
              "None. (A reversible call goes here as `### P1: the call`, with the reason, then "
              "`Rejected: the alternative`. `ws settle` numbers it.)", "",
              "## Gotchas and follow-ups", "", "None.", "",
              "## Text to apply", "", TEXTS_NONE, ""]
    return "\n".join(lines)


def rewrite_ids(text: str, mapping: dict[str, str]) -> str:
    """Each proposal id replaced by its decision id, wherever the file mentions it, except in
    text to apply, which has to stay exactly what its author wrote."""
    head, heading, body = _split_texts(text)
    for old, new in mapping.items():
        head = re.sub(rf"\b{re.escape(old)}\b", new, head)
    return head + heading + body
