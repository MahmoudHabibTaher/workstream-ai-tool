"""session_handoff.md and the progress log's order: written from state, never by an agent.

The handoff is overwritten each time, because it says only where things stand now. Anything
worth keeping belongs in the evidence, which stays.
"""

from __future__ import annotations

from workstream import decisions, evidence, gitutil, graph, tasks
from workstream.fsutil import today
from workstream.project import Project

FILE_NAME = "session_handoff.md"
SEPARATOR = "---"


def insert_newest_first(text: str, entries: list[str]) -> str:
    """Put entries under the file's `---` line, ahead of what is there; at the end without one."""
    block = "\n".join(entries)
    lines = text.splitlines()
    if SEPARATOR not in lines:
        return text.rstrip() + "\n\n" + block
    at = lines.index(SEPARATOR) + 1
    before = "\n".join(lines[:at]).rstrip()
    after = "\n".join(lines[at:]).strip()
    return f"{before}\n\n{block}" + (f"\n{after}\n" if after else "")


def next_lines(rows: list[dict]) -> list[str]:
    """What the next session does, from the graph."""
    wave = graph.compute_wave(sorted(rows, key=lambda t: t["priority"]))
    if wave["state"] == "finished":
        return ["The queue is finished; `ws close` closes the workstream."]
    if wave["state"] == "ready":
        return [f"`ws claim --commit {' '.join(wave['ids'])}` (phase {wave['phase']})."]
    return ["Nothing is ready: see the blocked tasks below, or anything still in progress."]


def open_decisions(project: Project, ws: dict, rows: list[dict]) -> list[dict]:
    """Every open decision as {id, line}; the line names the unfinished tasks waiting on the task
    that recorded it, directly or not."""
    path = project.folder(ws) / "DECISIONS.md"
    entries = decisions.parse(path.read_text()) if path.exists() else []
    unfinished = {t["id"] for t in rows if t["status"] in tasks.OPEN_STATUSES}
    found = []
    for entry in decisions.open_entries(entries):
        waiting = [i for i in graph.dependents(rows, entry["who"]) if i in unfinished]
        says = f"waiting: {', '.join(waiting)}" if waiting else "no task waiting"
        found.append({"id": entry["id"], "line": f"{entry['id']}: {entry['title']} ({says})"})
    return found


def _collapsed(text: str) -> str:
    return " ".join(text.split())


def _is_applied(project: Project, entry: dict) -> bool:
    """Whether the file under the root holds the text, whatever its line breaks: a coordinator
    may reflow it. Rewording more than that reads as not applied, which only ever warns."""
    target = project.root / entry["path"]
    try:
        held = target.read_text(errors="replace") if target.is_file() else ""
    except OSError:
        return False
    return _collapsed(entry["text"]) in _collapsed(held)


def texts_to_apply(project: Project, ws: dict, rows: list[dict]) -> list[dict]:
    """Each done task's text not yet in its file, as {id, path, line}. A blocked task hasn't
    landed, so its text isn't due. A path the evidence check rejects is never read, since a
    worker's evidence can point anywhere."""
    found = []
    for row in rows:
        text = evidence.read_at(project, ws, row["id"], None) if row["status"] == "done" else None
        for entry in evidence.parse(text)["texts"] if text else []:
            if evidence.text_problem(entry) or _is_applied(project, entry):
                continue
            line = f"{row['id']}: {entry['path']} (evidence/{row['id']}.md)"
            found.append({"id": row["id"], "path": entry["path"], "line": line})
    return found


def render(project: Project, ws: dict, rows: list[dict], outcomes: list[dict],
           note: str | None) -> str:
    head = gitutil.rev_parse(project.root, "HEAD", short=True)
    done = sum(t["status"] == "done" for t in rows)
    lines = ["# Session handoff", "",
             f"**State:** {done}/{len(rows)} done on `{project.config.integration}` at "
             f"`{head}`, as of {today()}.", ""]
    landed = [o for o in outcomes if o["state"] == "merged"]
    if landed:
        lines += ["**Just landed:** " + ", ".join(f"{o['id']} (`{o['commit'][:10]}`)"
                                                  for o in landed), ""]
    blocked = [t for t in rows if t["status"] == "blocked"]
    if blocked:
        lines.append("**Blocked:**")
        lines += [f"- {t['id']}: {t.get('blockedReason') or t.get('notes') or t['title']}"
                  for t in blocked]
        lines.append("")
    running = [t for t in rows if t["status"] == "in-progress"]
    if running:
        lines += ["**Still in progress:** " + ", ".join(
            f"{t['id']} ({t.get('claimedBy') or 'unclaimed'})" for t in running), ""]
    still_open = open_decisions(project, ws, rows)
    if still_open:
        lines += ["**Open decisions:**", *[f"- {d['line']}" for d in still_open], ""]
    to_apply = texts_to_apply(project, ws, rows)
    if to_apply:
        lines += ["**Text to apply:**", *[f"- {t['line']}" for t in to_apply], ""]
    lines += ["**Next:** " + " ".join(next_lines(rows)), ""]
    gotchas = []
    for out in outcomes:
        found = (out.get("parsed") or {}).get("gotchas") or out.get("gotchas") or ""
        if found and found.lower().rstrip(".") != "none":
            gotchas.append(f"- {out['id']}: {found}")
    if gotchas:
        lines += ["**Gotchas:**", *gotchas, ""]
    if note:
        lines += [f"**Note:** {note}", ""]
    return "\n".join(lines)


def write(project: Project, ws: dict, outcomes: list[dict], note: str | None) -> bool:
    """Overwrite the handoff, on a tier that keeps one. False when this one doesn't."""
    path = project.folder(ws) / FILE_NAME
    if not path.exists():
        return False
    rows = tasks.load(project.tasks_path(ws), project.config)["tasks"]
    path.write_text(render(project, ws, rows, outcomes, note))
    return True
