"""`ws brief <task>`: everything a worker needs, assembled by the CLI.

A coordinator's spawn prompt becomes one line, "run `ws brief T-01` and follow it", instead of
a hand-written page. Plan sections the task cites come in full, because a worker needs them to
do the job. Everything else is capped: a brief that grows with the project is the cost this
tool exists to remove.
"""

from __future__ import annotations

from workstream import baseline, decisions, evidence, plan, tasks, worktree
from workstream.project import TEMPLATES_DIR, Project

DEFAULT_MAX_CHARS = 10_000
MAX_SECTION_LINES = 80
MAX_GOTCHA_CHARS = 400
RULES_FILE = "worker_rules.md"


def _plan_sections(project: Project, ws: dict, task: dict) -> tuple[list[str], list[str]]:
    """(the cited sections' text, the citations PLAN.md has no section for)."""
    path = project.folder(ws) / "PLAN.md"
    text = path.read_text() if path.exists() else ""
    found, missing = [], []
    for ref in task.get("findings", []):
        section = plan.find_section(text, ref)
        if section is None:
            missing.append(ref)
            continue
        lines = section.text.splitlines()
        if len(lines) > MAX_SECTION_LINES:
            lines = lines[:MAX_SECTION_LINES] + [f"(cut at {MAX_SECTION_LINES} lines; "
                                                 f"the rest is in {project.rel(path)})"]
        found.append("\n".join(lines))
    return found, missing


def _builds_on(project: Project, ws: dict, task: dict, rows: list[dict]) -> list[str]:
    """One line per finished blocker, with whatever it left the next task to know."""
    by_id = {t["id"]: t for t in rows}
    lines = []
    for blocker in task.get("blockedBy", []):
        other = by_id.get(blocker)
        if other is None:
            continue
        commit = (other.get("commit") or "")[:10]
        lines.append(f"- {blocker} ({other['status']}{', ' + commit if commit else ''}): "
                     f"{other['title']}")
        text = evidence.read_at(project, ws, blocker, None)
        gotchas = evidence.parse(text)["gotchas"] if text else ""
        if gotchas and gotchas.lower().rstrip(".") != "none":
            lines.append(f"  {gotchas[:MAX_GOTCHA_CHARS]}")
    return lines


def _start_lines(project: Project, task: dict) -> list[str]:
    branch = task.get("branch") or project.config.branch_for(task["id"])
    path = worktree.for_branch(project, branch)
    if path:
        return [f"Work in `{path}`, on `{branch}`. It is already set up."]
    return [f"Work on `{branch}`: `git switch -c {branch}` "
            f"(or `git switch {branch}` if it exists), from `{project.config.integration}`."]


def _verify_lines(project: Project, ws: dict, task: dict) -> list[str]:
    record = baseline.load(project.folder(ws))
    lines = []
    for label, command in tasks.verify_commands(task, project.config):
        known = len(baseline.known_findings(record, label))
        note = f" ({known} known finding(s): only new ones fail)" if known else ""
        lines.append(f"- {label}: `{command or '(not in [commands])'}`{note}"
                     if label != command else f"- `{command}`{note}")
    return lines


def _finish_lines(ws: dict, task: dict) -> list[str]:
    tid = f"{task['id']} -w {ws['id']}"
    return [
        "## When the work is done", "",
        f"1. `ws verify {tid}` runs the checks above and records the result. Use it rather than "
        "running them by hand: its output stays short, and only its record counts.",
        f"2. `ws evidence new {tid}`, then fill in what it wrote: quote the proof for each item.",
        "3. Commit the code and the evidence together on your branch.",
        f"4. `ws evidence check {tid}` must say OK. If you changed code, verify again first.",
        "5. Report: done or blocked, the branch, and any proposed decisions. Nothing more.",
    ]


def render(project: Project, ws: dict, task: dict, rows: list[dict],
           max_chars: int = DEFAULT_MAX_CHARS) -> str:
    """The brief, with the decisions log trimmed first if it goes over max_chars. What the task
    itself asks for is never trimmed."""
    parts = [f"# {task['id']}: {task['title']}",
             f"Workstream `{ws['id']}`, phase {task['phase']}, {task['mode']}."]
    if task.get("summary"):
        parts += ["", task["summary"]]
    parts += ["", *_start_lines(project, task)]
    for label, field in (("Files you are expected to touch", "files"), ("Read first", "docs"),
                         ("Needs", "requires")):
        if task.get(field):
            parts += ["", f"**{label}:** " + ", ".join(f"`{v}`" for v in task[field])]
    if task.get("notes"):
        parts += ["", f"**Notes:** {task['notes']}"]
    if task.get("acceptance"):
        parts += ["", "## Acceptance", ""]
        parts += [f"{n}. {tasks.acceptance_text(a)}"
                  for n, a in enumerate(task["acceptance"], 1)]
    commands = _verify_lines(project, ws, task)
    if commands:
        parts += ["", "## Verify", "", *commands]
    earlier = _builds_on(project, ws, task, rows)
    if earlier:
        parts += ["", "## Builds on", "", *earlier]
    cited, missing = _plan_sections(project, ws, task)
    if cited or missing:
        parts += ["", "## From the plan"]
        for section in cited:
            parts += ["", section]
        if missing:
            parts += ["", f"Cited but not found in PLAN.md: {', '.join(missing)}"]
    parts += ["", (TEMPLATES_DIR / RULES_FILE).read_text().rstrip(), "", *_finish_lines(ws, task)]
    text = "\n".join(parts)
    return _with_decisions(project, ws, task, text, max_chars) + "\n"


def _with_decisions(project: Project, ws: dict, task: dict, text: str, max_chars: int) -> str:
    """Add the decisions that apply, newest first, for as long as they fit."""
    path = project.folder(ws) / "DECISIONS.md"
    entries = decisions.relevant(decisions.parse(path.read_text()), task) if path.exists() else []
    if not entries:
        return text
    kept: list[str] = []
    used = len(text)
    for entry in reversed(entries):
        if used + len(entry["text"]) + 2 > max_chars:
            break
        kept.append(entry["text"])
        used += len(entry["text"]) + 2
    lines = ["", "## Decisions that apply", ""]
    lines += [part for entry in kept for part in (entry, "")]
    left = len(entries) - len(kept)
    if left:
        lines.append(f"{left} more: `ws decisions --for {task['id']} -w {ws['id']}`")
    return text + "\n" + "\n".join(lines).rstrip()
