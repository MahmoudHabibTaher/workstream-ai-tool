"""`ws brief <task>`: everything a worker needs, assembled by the CLI.

A coordinator's spawn prompt becomes one line, "run `ws brief T-01` and follow it", instead of
a hand-written page. Plan sections the task cites come in full, because a worker needs them to
do the job. Everything else is capped: a brief that grows with the project is the cost this
tool exists to remove.
"""

from __future__ import annotations

import re
import shlex
from pathlib import Path

from workstream import (adapt, baseline, decisions, evidence, gitutil, graph, plan, protocol, tasks,
                        worktree)
from workstream.project import Project

DEFAULT_MAX_CHARS = 10_000
MAX_PICKUP_FILES = 10  # audit.project_rows renders these briefs, so a big leftover can't swell one
MAX_SECTION_LINES = 80
MAX_GOTCHA_CHARS = 1_200
BULLET_RE = re.compile(r"(?:[-*+]|\d+[.)])\s")
SENTENCE_END_RE = re.compile(r"[.!?][\"')\]`*_]*(?=\s|$)")


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


def _gotcha_entries(gotchas: str) -> list[str]:
    """The top-level bullets, each with its continuation lines. Text before the first bullet is
    an entry of its own, and text with no bullets is one entry."""
    entries: list[list[str]] = []
    for line in gotchas.splitlines():
        if not entries or BULLET_RE.match(line):
            entries.append([])
        entries[-1].append(line)
    return ["\n".join(entry).rstrip() for entry in entries]


def _cut_at_sentence(entry: str, limit: int) -> str:
    """The most of entry that fits and ends a sentence; failing that, one that ends a word."""
    head = entry[:limit]
    # One character past the limit, so a sentence ending right at it can be seen to end.
    ends = [m.end() for m in SENTENCE_END_RE.finditer(entry[:limit + 1]) if m.end() <= limit]
    if ends:
        return head[:ends[-1]]
    return head.rsplit(None, 1)[0] if len(head.split(None, 1)) > 1 else head


def _gotcha_lines(gotchas: str, pointer_path: str) -> list[str]:
    """A blocker's gotchas, indented under it, up to the cap. Whole entries are kept wherever they
    fit; one is cut only when no entry fits whole. A worker is told what it isn't seeing."""
    entries = _gotcha_entries(gotchas)
    kept, used = [], 0
    for entry in entries:
        if used + len(entry) <= MAX_GOTCHA_CHARS:
            kept.append(entry)
            used += len(entry)
    left = len(entries) - len(kept)
    if not kept:  # the cut entry counts as one more: its rest is what the pointer leads to
        kept = [_cut_at_sentence(entries[0], MAX_GOTCHA_CHARS)]
    lines = [f"  {line}" if line.strip() else "" for e in kept for line in e.splitlines()]
    if left:
        lines.append(f"  ({left} more in {pointer_path})")
    return lines


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
            lines += _gotcha_lines(gotchas, project.rel(evidence.path_for(project, ws, blocker)))
    return lines


def _start_lines(project: Project, ws: dict, task: dict) -> list[str]:
    branch = task.get("branch") or project.config.branch_for(task["id"])
    path = worktree.for_branch(project, branch)
    if path:
        return [f"Work in `{path}`, on `{branch}`. It is already set up. Your shell may not stay "
                "there, so give file paths in full. `ws` finds the worktree itself."]
    if task["mode"] == "foreground":
        return [f"Run `ws worktree create {task['id']} -w {ws['id']}`, and work in the path it "
                f"prints, on `{branch}`. Your shell may not stay there, so give file paths in "
                "full. `ws` finds the worktree itself."]
    return [f"Work on `{branch}`: `git switch -c {branch}` "
            f"(or `git switch {branch}` if it exists), from `{project.config.integration}`."]


def _verify_lines(project: Project, ws: dict, task: dict) -> list[str]:
    record = baseline.load_for(project, project.folder(ws))
    lines = []
    for label, command in tasks.verify_commands(task, project.config):
        known = len(baseline.known_findings(record, label))
        note = f" ({known} known finding(s): only new ones fail)" if known else ""
        lines.append(f"- {label}: `{command or '(not in [commands])'}`{note}"
                     if label != command else f"- `{command}`{note}")
    return lines


def _resume_evidence(project: Project, ws: dict, task: dict) -> str | None:
    """Where a picked-up task's evidence already is, or None if it has none, as when it was blocked
    by hand. `ws evidence new` refuses a file that exists, so the finish steps depend on this."""
    branch = task.get("branch") or project.config.branch_for(task["id"])
    rel = project.rel(evidence.path_for(project, ws, task["id"]))
    tree = worktree.for_branch(project, branch)
    if tree and (Path(tree) / rel).exists():
        return str(Path(tree) / rel)
    return rel if evidence.read_at(project, ws, task["id"], branch) is not None else None


def _resume_lines(project: Project, ws: dict, task: dict, evidence_path: str | None) -> list[str]:
    """What a fresh worker needs to pick up a blocked task without checking finished work again."""
    branch = task.get("branch") or project.config.branch_for(task["id"])
    integration = project.config.integration
    if gitutil.branch_exists(project.root, branch):
        count = gitutil.run(project.root, "rev-list", "--count", f"{integration}..{branch}")
        commits = f"{count.stdout.strip()} (`git log {integration}..{branch}`)"
    else:
        commits = "none, as the branch doesn't exist yet"
    lines = ["", "## Resuming", "",
             "This task was blocked and has been started again. Keep the finished work: don't redo "
             "or re-check it, and pick up from the reason below. `ws verify` proves the whole at "
             "the end. If the reason still stands, report blocked again.", "",
             f"- **Reason:** {task.get('blockedReason') or 'none recorded'}",
             f"- **Commits on `{branch}`:** {commits}",
             f"- **Evidence:** {f'`{evidence_path}`' if evidence_path else 'none yet'}"]
    lacking = _decisions_branch_lacks(project, ws, branch)
    if lacking:
        path = project.folder(ws) / "DECISIONS.md"
        lines += [f"- **Decisions your branch's `DECISIONS.md` lacks:** check your work against "
                  f"these. Read them in `{path}`, since `ws decisions` reads your branch's copy.",
                  *[f"  - {e['id']}: {e['title']}" for e in lacking]]
    else:
        lines.append("- **Decisions your branch's `DECISIONS.md` lacks:** none")
    return [*lines, "", "## The task"]


def _pickup_lines(project: Project, task: dict) -> list[str]:
    """What an in-progress task's worktree already holds, for a fresh worker sent to a dead one's
    work. Empty for a fresh claim. Commits count from the integration branch, not baseCommit: a
    new branch starts on `claim --commit`'s commit, which baseCommit is the parent of."""
    branch = task.get("branch") or project.config.branch_for(task["id"])
    tree = worktree.for_branch(project, branch)
    if not tree:
        return []
    files = worktree.uncommitted(Path(tree))
    integration = project.config.integration
    count = gitutil.run(project.root, "rev-list", "--count", f"{integration}..{branch}")
    commits = int(count.stdout.strip()) if count.returncode == 0 else 0
    if not files and not commits:
        return []
    lines = ["", "## Picking up", "",
             "This worktree already holds work. Unless these are your own edits, an earlier worker "
             "stopped here and nobody has checked what it left: check it against the acceptance "
             "items, and keep what is right.", ""]
    if commits:
        lines.append(f"- **Commits on `{branch}`:** {commits} (`git log {integration}..{branch}`)")
    if files:
        lines.append(f"- **Uncommitted files:** {len(files)}")
        lines += [f"  - `{entry}`" for entry in files[:MAX_PICKUP_FILES]]
        if len(files) > MAX_PICKUP_FILES:
            lines.append(f"  - ({len(files) - MAX_PICKUP_FILES} more)")
    return lines


def _decisions_branch_lacks(project: Project, ws: dict, branch: str) -> list[dict]:
    """The entries made since the branch took its copy. A branch that isn't there has no copy to
    be behind: its worker starts from the integration branch, with all of them."""
    path = project.folder(ws) / "DECISIONS.md"
    if not path.exists() or not gitutil.branch_exists(project.root, branch):
        return []
    proc = gitutil.run(project.root, "show", f"{branch}:{project.rel(path)}")
    theirs = {e["id"] for e in decisions.parse(proc.stdout)} if proc.returncode == 0 else set()
    return [e for e in decisions.parse(path.read_text()) if e["id"] not in theirs]


def _finish_lines(project: Project, ws: dict, task: dict,
                  existing_evidence: str | None = None) -> list[str]:
    tid = f"{task['id']} -w {ws['id']}"
    evidence_step = (f"2. Update the existing evidence, `{existing_evidence}`, rather than starting "
                     "a new file: set its Status again and quote the proof for each item."
                     if existing_evidence else
                     f"2. `ws evidence new {tid}`, then fill in what it wrote: quote the proof for "
                     "each item.")
    lines = [
        "## When the work is done", "",
        f"1. `ws verify {tid}` runs the checks above and records the result. Use it rather than "
        "running them by hand: its output stays short, and only its record counts. Run it in the "
        "foreground with the longest timeout your shell allows, and wait for it. If your shell "
        "moves it to the background, wait for it to exit: it enforces its own time limit, and "
        "elapsed time can include the machine sleeping, so don't kill it.",
        evidence_step,
        f"3. `ws commit {tid} -m \"<what changed>\"` commits the code and the evidence together on "
        "your branch.",
        f"4. `ws evidence check {tid}` must say OK. If you changed code, verify again first.",
    ]
    if task["mode"] == "foreground":
        # No separate coordinator is coming to land this. `ws settle` refuses a worktree, and
        # other sessions share the integration checkout, so it is named rather than switched to.
        checkout = shlex.quote(str(worktree.integration_checkout(project)))
        return lines + [f"5. This task runs in the foreground, so you land it too: "
                        f"`ws --root {checkout} settle {tid}`. That removes your worktree, so "
                        "leave it first if your shell is there."]
    return lines + ["5. Report: done or blocked, the branch, and any proposed decisions. "
                    "Nothing more."]


def _cannot_edit_lines(project: Project, task: dict) -> list[str]:
    """An agent may refuse edits to its own folder from the background, whatever the rules say."""
    if task["mode"] == "foreground":
        return []
    folders = [f for name in adapt.load_manifest(project)["adapters"]
               for f in adapt.load(name).raw["worker"].get("cannot_edit", [])]
    named = [p for p in [*task.get("files", []), *task.get("docs", [])]
             if any(p.startswith(f) for f in folders)]
    if not named:
        return []
    return ["", "**You can't edit these from the background:** " + ", ".join(f"`{p}`" for p in named)
            + ". Don't try: if one needs a change, put the exact text under `## Text to apply` in your evidence, for someone who can."]


def _adapter_rule_lines(project: Project) -> list[str]:
    """Worker rules that hold for one agent only, labelled with it. A project may have more than
    one adapter, and the brief can't tell which agent reads it."""
    lines = []
    for name in adapt.load_manifest(project)["adapters"]:
        adapter = adapt.load(name)
        lines += [f"- **On {adapter.label}:** {rule}" for rule in adapter.raw["worker"].get("rules", [])]
    return lines


def _open_decision_lines(project: Project, ws: dict, task: dict, rows: list[dict]) -> list[str]:
    """Open decisions from anything this task waits on, directly or not: one that lands open can
    make this task's acceptance wrong. Never trimmed, since it can change the whole task."""
    path = project.folder(ws) / "DECISIONS.md"
    if not path.exists():
        return []
    waits_on = graph.blockers_closure(graph.blocked_by_graph(rows)).get(task["id"], set())
    found = [e for e in decisions.open_entries(decisions.parse(path.read_text()))
             if e["who"] in waits_on]
    if not found:
        return []
    return ["", "## Open decisions", "",
            "Check your acceptance against these first, and report blocked if one changes it. "
            f"Read them with `ws decisions --open -w {ws['id']}`.", "",
            *[f"- {e['id']}: {e['title']}" for e in found]]


def _changed_lines(project: Project, ws: dict, task: dict) -> list[str]:
    """Settled decisions saying they change this task. A plan can't be rewritten, so what it cites
    can be out of date. Titles only keep this small enough never to trim: the bodies are in the
    decisions that apply, which do get trimmed."""
    path = project.folder(ws) / "DECISIONS.md"
    if not path.exists():
        return []
    entries = decisions.parse(path.read_text())
    still_open = {e["id"] for e in decisions.open_entries(entries)}
    found = [e for e in entries
             if task["id"] in decisions.changed_tasks(e) and e["id"] not in still_open]
    if not found:
        return []
    return ["", "## Changed since the plan", "",
            "These outrank the plan and the summary where they differ. "
            f"Read them with `ws decisions --for {task['id']} -w {ws['id']}`.", "",
            *[f"- {e['id']}: {e['title']}" for e in found]]


def _scope_lines(scope: dict | None) -> list[str]:
    """The workstream's boundary. A worker that can't see it can't stay inside it."""
    if not scope:
        return []
    lines = []
    if scope.get("rule"):
        lines += ["", f"**Scope rule:** {scope['rule']}"]
    if scope.get("outOfScope"):
        lines += ["", "**Out of scope:** " + "; ".join(scope["outOfScope"])]
    return lines


def render(project: Project, ws: dict, task: dict, rows: list[dict],
           max_chars: int = DEFAULT_MAX_CHARS, *, scope: dict | None = None,
           cited: bool = True) -> str:
    """The brief, with the decisions log trimmed first if it goes over max_chars. What the task
    itself asks for is never trimmed. `cited=False` leaves out the plan sections, for measuring
    the part the context limit covers."""
    parts = [f"# {task['id']}: {task['title']}",
             f"Workstream `{ws['id']}`, phase {task['phase']}, {task['mode']}."]
    existing_evidence = None
    if task["status"] == "blocked":
        existing_evidence = _resume_evidence(project, ws, task)
        parts += _resume_lines(project, ws, task, existing_evidence)
    if task.get("summary"):
        parts += ["", task["summary"]]
    parts += ["", *_start_lines(project, ws, task), *_scope_lines(scope)]
    for label, field in (("Files you are expected to touch", "files"), ("Docs that bear on this (search them, as they may be long)", "docs"),
                         ("Needs", "requires")):
        if task.get(field):
            parts += ["", f"**{label}:** " + ", ".join(f"`{v}`" for v in task[field])]
    parts += _cannot_edit_lines(project, task)
    if task.get("notes"):
        parts += ["", f"**Notes:** {task['notes']}"]
    pickup = _pickup_lines(project, task) if task["status"] == "in-progress" else []
    if pickup:
        existing_evidence = _resume_evidence(project, ws, task)
        parts += pickup
    if task.get("acceptance"):
        parts += ["", "## Acceptance", ""]
        parts += [f"{n}. {tasks.acceptance_text(a)}"
                  for n, a in enumerate(task["acceptance"], 1)]
    parts += _open_decision_lines(project, ws, task, rows)
    parts += _changed_lines(project, ws, task)
    commands = _verify_lines(project, ws, task)
    if commands:
        parts += ["", "## Verify", "", *commands]
    earlier = _builds_on(project, ws, task, rows)
    if earlier:
        parts += ["", "## Builds on", "", *earlier]
    sections, missing = _plan_sections(project, ws, task) if cited else ([], [])
    if sections or missing:
        parts += ["", "## From the plan"]
        for section in sections:
            parts += ["", section]
        if missing:
            parts += ["", f"Cited but not found in PLAN.md: {', '.join(missing)}"]
    parts += ["", "## Rules", "", protocol.section("worker"), *_adapter_rule_lines(project), "",
              *_finish_lines(project, ws, task, existing_evidence)]
    text = "\n".join(parts)
    return _with_decisions(project, ws, task, text, max_chars) + "\n"


def _with_decisions(project: Project, ws: dict, task: dict, text: str, max_chars: int) -> str:
    """Add the decisions that apply, those naming the task first and each group newest first,
    skipping any that doesn't fit so it can't hide a shorter one after it."""
    path = project.folder(ws) / "DECISIONS.md"
    entries = decisions.relevant(decisions.parse(path.read_text()), task) if path.exists() else []
    if not entries:
        return text
    newest_first = entries[::-1]
    naming = [e for e in newest_first if decisions.mentions(e["text"], task["id"])]
    others = [e for e in newest_first if not decisions.mentions(e["text"], task["id"])]
    kept: list[str] = []
    used = len(text)
    for entry in naming + others:
        if used + len(entry["text"]) + 2 > max_chars:
            continue
        kept.append(entry["text"])
        used += len(entry["text"]) + 2
    lines = ["", "## Decisions that apply", ""]
    lines += [part for entry in kept for part in (entry, "")]
    left = len(entries) - len(kept)
    if left:
        lines.append(f"{left} more: `ws decisions --for {task['id']} -w {ws['id']}`")
    return text + "\n" + "\n".join(lines).rstrip()
