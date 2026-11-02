"""Reading a plan: sections by the id their heading starts with, and `seed --from-plan`.

A plan is written once, in plan mode, then used three ways: as PLAN.md, as the queue, and in
each worker's brief. Writing it again for each of those is 20-35 KB of model output for
nothing, so an approved plan carries its tasks in a fenced block and the CLI splits it:

    ```json ws-tasks
    [{"id": "T-01", "phase": 1, "priority": 10, "title": "..."}]
    ```

The block may instead be `{"scope": {...}, "tasks": [...]}`, adding the workstream's boundary,
which every brief then shows. An optional ```text ws-decisions``` block holds what the user decided while the plan was
discussed. It becomes the first entry in DECISIONS.md. Neither block stays in PLAN.md.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass

from workstream import decisions, handoff, tasks
from workstream.errors import Refused, WsError
from workstream.fsutil import today
from workstream.project import Project

HEADING_RE = re.compile(r"^(#{1,6})\s+(.*\S)\s*$")
FENCE_RE = re.compile(r"^(`{3,}|~{3,})\s*(.*?)\s*$")
TASKS_BLOCK = "ws-tasks"
DECISIONS_BLOCK = "ws-decisions"
SLOT_RE = r"\{\{%s[^}]*\}\}"
PLACEHOLDER = "{{"
SCOPE_KEYS = {"inScope", "outOfScope", "rule"}
NO_SCOPE_DECISIONS = "No scope decisions were recorded with the plan."


@dataclass(frozen=True)
class Section:
    level: int
    title: str
    text: str  # the heading line and the body, down to the next heading at this level or above


def sections(text: str) -> list[Section]:
    """Every heading's section, in order. A `#` line inside a code fence isn't a heading."""
    lines = text.splitlines()
    heads = []
    fence = ""
    for n, line in enumerate(lines):
        match = FENCE_RE.match(line)
        if match and (not fence or (match[1].startswith(fence) and not match[2])):
            fence = "" if fence else match[1]
            continue
        heading = HEADING_RE.match(line) if not fence else None
        if heading:
            heads.append((n, len(heading[1]), heading[2]))
    found = []
    for i, (start, level, title) in enumerate(heads):
        end = next((h[0] for h in heads[i + 1:] if h[1] <= level), len(lines))
        found.append(Section(level, title, "\n".join(lines[start:end]).rstrip()))
    return found


def find_section(text: str, ref: str) -> Section | None:
    """The section whose heading is ref, or starts with it as a whole word (`T3` finds
    `### T3: the cache lies`, and not `### T30: ...`)."""
    pattern = re.compile(rf"^{re.escape(ref)}(?=$|[\s:.,)-])")
    for section in sections(text):
        if pattern.match(section.title):
            return section
    return None


def split_blocks(text: str) -> tuple[str, dict[str, str]]:
    """(the text without its ws- blocks, {block name: body}). Refuses an unclosed or repeated
    block rather than seed half a plan."""
    kept: list[str] = []
    blocks: dict[str, str] = {}
    lines = text.splitlines()
    n = 0
    fence = ""
    while n < len(lines):
        line = lines[n]
        match = FENCE_RE.match(line)
        if fence:
            if match and match[1].startswith(fence) and not match[2]:
                fence = ""
            kept.append(line)
            n += 1
            continue
        if not match:
            kept.append(line)
            n += 1
            continue
        name = next((word for word in match[2].split() if word.startswith("ws-")), None)
        if name is None:
            fence = match[1]
            kept.append(line)
            n += 1
            continue
        if name not in (TASKS_BLOCK, DECISIONS_BLOCK):
            raise WsError(f"unknown plan block {name!r}")
        if name in blocks:
            raise WsError(f"the plan has two {name} blocks")
        end = next((m for m in range(n + 1, len(lines))
                    if lines[m].strip() == match[1]), None)
        if end is None:
            raise WsError(f"the {name} block is never closed")
        blocks[name] = "\n".join(lines[n + 1:end])
        n = end + 1
    return "\n".join(kept).strip() + "\n", blocks


def parse_plan(text: str) -> tuple[str, list[dict], str, dict | None]:
    """(plan body, task objects, the user's decisions, scope) from an approved plan."""
    body, blocks = split_blocks(text)
    if TASKS_BLOCK not in blocks:
        raise WsError(f"the plan has no ```json {TASKS_BLOCK}``` block")
    try:
        new_tasks = json.loads(blocks[TASKS_BLOCK])
    except json.JSONDecodeError as e:
        raise WsError(f"the {TASKS_BLOCK} block is not valid JSON: {e}") from None
    scope = None
    if isinstance(new_tasks, dict):
        scope = new_tasks.get("scope")
        new_tasks = new_tasks.get("tasks")
    if scope is not None and (not isinstance(scope, dict) or set(scope) - SCOPE_KEYS):
        raise WsError(f"scope may only hold {', '.join(sorted(SCOPE_KEYS))}")
    if not isinstance(new_tasks, list) or not new_tasks \
            or not all(isinstance(t, dict) for t in new_tasks):
        raise WsError(f"the {TASKS_BLOCK} block must be a non-empty array of task objects")
    return body, new_tasks, blocks.get(DECISIONS_BLOCK, "").strip(), scope


def _fill(path, slots: dict[str, str]) -> None:
    if not path.exists():
        return
    text = path.read_text()
    for slot, value in slots.items():
        text = re.sub(SLOT_RE % slot, lambda _: value, text)
    path.write_text(text)


def seed_from_plan(project: Project, ws: dict, text: str, force: bool = False
                   ) -> tuple[int, list[str]]:
    """Split an approved plan into PLAN.md, the queue and the first decision, all or nothing.
    Returns (tasks added, warnings). A plan is immutable once approved, so a PLAN.md already
    written is refused without force."""
    folder = project.folder(ws)
    plan_path = folder / "PLAN.md"
    if plan_path.exists() and PLACEHOLDER not in plan_path.read_text() and not force:
        raise Refused(f"{project.rel(plan_path)} is already written; a plan is immutable once "
                      "approved (a change belongs in DECISIONS.md, --force overrides)")
    body, new_tasks, user_decisions, scope = parse_plan(text)
    if PLACEHOLDER in body:
        raise WsError("the plan still has a {{...}} placeholder")
    queue_path = project.tasks_path(ws)
    existing = tasks.load(queue_path, project.config)["tasks"]
    candidate = existing + [tasks.normalize_task(t, project.config) for t in new_tasks]
    errors, warnings = tasks.validate_tasks(candidate, project.root, project.config)
    prefix = ws.get("taskPrefix")
    errors += [f"{t['id']}: lacks the prefix {prefix!r}" for t in new_tasks
               if prefix and not str(t.get("id", "")).startswith(prefix)]
    if errors:
        raise WsError("the plan's tasks have problems:\n" + "\n".join(f"  - {e}" for e in errors))
    tasks.seed(queue_path, new_tasks, project.config)
    if scope:
        tasks.set_scope(queue_path, scope, project.config)
    plan_path.write_text(body)
    decisions_path = folder / "DECISIONS.md"
    if decisions_path.exists():
        _fill(decisions_path, {"SCOPE_DECISIONS": user_decisions or NO_SCOPE_DECISIONS})
    elif user_decisions:
        decisions.append(decisions_path, [decisions.render_entry(1, today(), decisions.USER,
                                                                 "scope approved", user_decisions)])
    rows = tasks.load(queue_path, project.config)["tasks"]
    _fill(folder / handoff.FILE_NAME, {"NEXT": " ".join(handoff.next_lines(rows)),
                                       "GOTCHAS": "None."})
    return len(new_tasks), warnings
