"""Per-task review data: `ws review <TASK> [--file <path>] [--max-lines 1500] [--checks]` as JSON:

    {task, evidence: <abs path or null>,
     range: {from, to, kind: "merge"|"commit"|"branch"|"none"},
     files: [{path, added, removed}], hunks?: {path, text, truncated}, checks?, error?}

`--checks` adds what a person judging the task needs and a UI can't work out: the gates settling
would run, each acceptance item beside its quoted proof, and the evidence, read from the task's
branch while it's still there. `ws review --queue` lists what can be reviewed across the open
workstreams. `ws review <TASK> --show <path> --side old|new` prints one file of the diffstat as
it stands on one side, `{path, side, rev, text, binary}`, for a diff editor.

- review_range(task, parents_of, branch_exists): pure. A task's `commit` is usually a
  `--no-ff` merge, whose `git show` is an empty combined diff, so a merge is reviewed
  against its first parent (`<commit>^1..<commit>`), a single-parent commit against its
  parent (`<commit>^..<commit>`). An in-progress task with no commit but an existing branch
  is reviewed before merge from where it left the integration branch, which leaves out the
  commit that claimed it. Anything else is `none`.
- side_rev(range, side, merge_base): pure. A branch's old side is the merge base its
  three-dot diff starts at, never the integration branch's tip.
- parse_numstat(text) and cap_hunks(text, max_lines): pure. The hunks are cut at the last
  whole hunk that fits under the cap, since a hunk cut mid-way does not parse as a diff.
- The git calls sit at the edge, in build_review. They only read, and a git failure comes
  back as data (`error`), never raised.
"""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

from workstream import evidence as evidence_file
from workstream import gates, gitutil, registry, snapshot, tasks
from workstream.errors import WsError
from workstream.project import Project

DEFAULT_MAX_LINES = 1500
RANGE_KINDS = ("merge", "commit", "branch", "none")
# Plain paths (no rename notation, so a path from `files` feeds --file as is), and no
# user colour or external-diff config leaking into the text a UI parses.
DIFF_FLAGS = ("--no-renames", "--no-color", "--no-ext-diff")


# --- pure ---------------------------------------------------------------------------------


def review_range(task: dict, parents_of, branch_exists) -> dict:
    """{from, to, kind} for one task. Pure: parents_of(rev) returns the commit's parent
    hashes, or None when the commit can't be read; branch_exists(name) returns a bool.

    The kind is decided by parent count: a project may record a plain commit, not a merge.
    """
    commit = task.get("commit")
    if commit:
        parents = parents_of(commit)
        if parents and len(parents) > 1:
            return {"from": f"{commit}^1", "to": commit, "kind": "merge"}
        if parents:
            return {"from": f"{commit}^", "to": commit, "kind": "commit"}
        return {"from": None, "to": None, "kind": "none"}
    branch, base = task.get("branch"), task.get("baseCommit")
    if task.get("status") == "in-progress" and branch and base and branch_exists(branch):
        return {"from": base, "to": branch, "kind": "branch"}
    return {"from": None, "to": None, "kind": "none"}


def diff_spec(rng: dict) -> str | None:
    """The revision argument `git diff` takes for a range: two dots for a commit, three
    (against the merge base) for a branch under review; None for `none`."""
    if rng["kind"] == "none":
        return None
    dots = "..." if rng["kind"] == "branch" else ".."
    return f"{rng['from']}{dots}{rng['to']}"


def side_rev(rng: dict, side: str, merge_base) -> str | None:
    """The revision one side of a range's diff reads a file at, matching diff_spec: a branch's
    three-dot diff starts at merge_base(from, to), not at `from`, whose tip may hold work landed
    since the claim; a commit or merge's old side is `from`. None for `none`. Pure:
    merge_base(a, b) returns a commit, or None when git can't find one."""
    if rng["kind"] == "none":
        return None
    if side == "new":
        return rng["to"]
    if rng["kind"] == "branch":
        return merge_base(rng["from"], rng["to"])
    return rng["from"]


def is_binary(data: bytes) -> bool:
    """Git's own test, a NUL in the first 8000 bytes, plus anything that isn't UTF-8, since
    JSON text can't carry it."""
    if b"\0" in data[:8000]:
        return True
    try:
        data.decode("utf-8")
    except UnicodeDecodeError:
        return True
    return False


def parse_numstat(text: str) -> list[dict]:
    """`git diff --numstat` lines as [{path, added, removed}]; a binary file's counts are
    None (git prints `-`)."""
    files = []
    for line in text.splitlines():
        parts = line.split("\t", 2)
        if len(parts) != 3:
            continue
        added, removed, path = parts
        files.append({
            "path": path,
            "added": int(added) if added.isdigit() else None,
            "removed": int(removed) if removed.isdigit() else None,
        })
    return files


def cap_hunks(text: str, max_lines: int) -> tuple[str, bool]:
    """(text, truncated): the diff's file header plus every whole hunk that fits within
    max_lines lines. A hunk never gets cut mid-way. When even the first hunk doesn't fit,
    only the header comes back, truncated."""
    lines = text.splitlines(keepends=True)
    if len(lines) <= max_lines:
        return text, False
    starts = [i for i, line in enumerate(lines) if line.startswith("@@")]
    header_end = starts[0] if starts else len(lines)
    keep = header_end
    for start, end in zip(starts, starts[1:] + [len(lines)]):
        if end > max_lines:
            break
        keep = end
    return "".join(lines[:keep]), True


# --- git, at the edge ---------------------------------------------------------------------


def _git(repo_root: Path, *argv: str) -> subprocess.CompletedProcess:
    """git, reading only, with no optional locks: a review is asked for often, from editors and
    the web UI, and a read shouldn't take the index lock under someone's own git."""
    return subprocess.run(["git", *argv], cwd=repo_root, capture_output=True, text=True,
                          env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})


def _git_error(proc: subprocess.CompletedProcess, argv: tuple[str, ...]) -> str:
    detail = proc.stderr.strip().splitlines()
    return f"git {' '.join(argv)}: {detail[-1] if detail else f'exit {proc.returncode}'}"


def git_parents(repo_root: Path, rev: str) -> list[str] | None:
    proc = _git(repo_root, "rev-list", "--parents", "-n", "1", f"{rev}^{{commit}}", "--")
    if proc.returncode != 0:
        return None
    return proc.stdout.split()[1:]


def git_branch_exists(repo_root: Path, branch: str) -> bool:
    proc = _git(repo_root, "rev-parse", "--verify", "--quiet", f"refs/heads/{branch}")
    return proc.returncode == 0


def _is_option_like(task: dict) -> bool:
    """Whether a revision this task names would reach git as an option. These values come
    from a file in the repo, and `git diff --output=<path>` writes a file."""
    return any(isinstance(task.get(f), str) and task[f].startswith("-")
               for f in ("commit", "branch", "baseCommit"))


def _range_of(project: Project, task: dict) -> dict:
    root = project.root
    rng = review_range(task, lambda rev: git_parents(root, rev),
                       lambda name: git_branch_exists(root, name))
    if rng["kind"] == "branch":
        fork = _git(root, "merge-base", project.config.integration, rng["to"]).stdout.strip()
        if fork and not fork.startswith(rng["from"]):
            rng["from"] = fork
    return rng


def build_checks(project: Project, ws: dict, task: dict, rng: dict) -> dict:
    """What the CLI can say about this task for a person judging it. A landed task's gates ran
    when it landed and its run record went with them, so only work still on a branch runs them.
    Reads only."""
    on_branch = rng["kind"] == "branch"
    rev = task["branch"] if on_branch else None
    text = evidence_file.read_at(project, ws, task["id"], rev)
    if text is None and on_branch:
        text = evidence_file.read_at(project, ws, task["id"], None)
    parsed = evidence_file.parse(text) if text else None
    found = []
    if on_branch:
        rows = registry.load(project)["workstreams"]
        found = gates.settle_gates(project, ws, task, rev, text=text, merged=False,
                                   folders=list(snapshot.folders_by_id(project, rows).values()))
    state = "branch" if on_branch else "landed" if task.get("status") == "done" else "none"
    return {
        "state": state,
        "title": task.get("title", ""),
        "status": task.get("status", ""),
        "commit": task.get("commit"),
        "gates": found,
        "evidenceText": text,
        "evidenceStatus": parsed["status"] if parsed else "",
        "reason": parsed["reason"] if parsed else "",
        "items": evidence_file.paired_items(parsed, task),
        "proposals": parsed["proposals"] if parsed else [],
        "gotchas": parsed["gotchas"] if parsed else "",
    }


def build_review(project: Project, ws_id: str, task_id: str, file: str | None = None,
                 max_lines: int = DEFAULT_MAX_LINES, checks: bool = False) -> dict:
    """The review document for one task. Reads only. Raises WsError for an unknown workstream
    or task; a failing git call becomes an `error` key with what it got so far."""
    root = project.root
    ws = registry.find(registry.load(project), ws_id)
    path = project.tasks_path(ws)
    if not path.is_file():
        raise WsError(f"{ws_id} has no queue left to review")
    task = tasks.find_task(tasks.load(path, project.config), task_id)
    if _is_option_like(task):
        raise WsError(f"{task_id} names a revision that starts with '-'")
    evidence = project.folder(ws) / "evidence" / f"{task_id}.md"
    rng = _range_of(project, task)
    out = {"task": task_id, "evidence": str(evidence) if evidence.is_file() else None,
           "range": rng, "files": []}
    if checks:
        out["checks"] = build_checks(project, ws, task, rng)
    spec = diff_spec(rng)
    if spec is None:
        return out
    argv = ("diff", *DIFF_FLAGS, "--numstat", spec, "--")
    proc = _git(root, *argv)
    if proc.returncode != 0:
        return {**out, "error": _git_error(proc, argv)}
    out["files"] = parse_numstat(proc.stdout)
    if file is not None:
        argv = ("diff", *DIFF_FLAGS, spec, "--", file)
        proc = _git(root, *argv)
        if proc.returncode != 0:
            return {**out, "error": _git_error(proc, argv)}
        text, truncated = cap_hunks(proc.stdout, max_lines)
        out["hunks"] = {"path": file, "text": text, "truncated": truncated}
    return out


# --- one side of one file -----------------------------------------------------------------

SIDES = ("old", "new")


def _git_read(repo_root: Path, *argv: str) -> subprocess.CompletedProcess:
    """_git with bytes out, since a file's content may not be text."""
    return subprocess.run(["git", *argv], cwd=repo_root, capture_output=True,
                          env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})


def build_show(project: Project, ws_id: str, task_id: str, path: str, side: str) -> dict:
    """{path, side, rev, text, binary}: one file of a task's diffstat as it stands on one side
    of the review range. `text` is None when the file doesn't exist on that side, and a binary
    file has `binary` true and no text. Reads only. Raises WsError for a path outside the
    diffstat, as there's nothing to compare it in, and for a git failure."""
    if side not in SIDES:
        raise WsError(f"--side is old or new, not {side!r}")
    data = build_review(project, ws_id, task_id)
    if "error" in data:
        raise WsError(data["error"])
    if path not in {f["path"] for f in data["files"]}:
        raise WsError(f"{path} is not in {task_id}'s diffstat")
    root = project.root

    def merge_base(a: str, b: str) -> str | None:
        proc = _git_read(root, "merge-base", a, b)
        if proc.returncode != 0:
            return None
        return proc.stdout.decode().strip() or None

    named = side_rev(data["range"], side, merge_base)
    proc = _git_read(root, "rev-parse", "--verify", "--quiet", f"{named}^{{commit}}") \
        if named else None
    if proc is None or proc.returncode != 0:
        raise WsError(f"{task_id}'s {side} side has no commit git can read")
    rev = proc.stdout.decode().strip()
    out = {"path": path, "side": side, "rev": rev, "text": None, "binary": False}
    if _git_read(root, "cat-file", "-e", f"{rev}:{path}").returncode != 0:
        return out
    argv = ("cat-file", "blob", f"{rev}:{path}")
    proc = _git_read(root, *argv)
    if proc.returncode != 0:
        raise WsError(f"git {' '.join(argv)}: {proc.stderr.decode(errors='replace').strip()}")
    if is_binary(proc.stdout):
        return {**out, "binary": True}
    return {**out, "text": proc.stdout.decode("utf-8")}


# --- the queue ----------------------------------------------------------------------------


def _queue_entry(project: Project, ws: dict, task: dict) -> dict | None:
    """One task's row, or None when it has nothing to review."""
    if _is_option_like(task):
        return None
    rng = _range_of(project, task)
    spec = diff_spec(rng)
    if spec is None:
        return None
    revision = gitutil.rev_parse(project.root, rng["to"])
    proc = _git(project.root, "diff", *DIFF_FLAGS, "--numstat", spec, "--")
    files = parse_numstat(proc.stdout) if proc.returncode == 0 else []
    on_branch = rng["kind"] == "branch"
    rev = task["branch"] if on_branch else None
    return {
        "workstream": ws["id"],
        "task": task["id"],
        "title": task.get("title", ""),
        "status": task.get("status", ""),
        "state": "branch" if on_branch else "landed",
        "revision": revision,
        "when": task.get("startedAt" if on_branch else "completedAt"),
        "files": len(files),
        "added": sum(f["added"] or 0 for f in files),
        "removed": sum(f["removed"] or 0 for f in files),
        "hasEvidence": evidence_file.read_at(project, ws, task["id"], rev) is not None,
    }


def build_queue(project: Project) -> dict:
    """What can be reviewed in the open workstreams: work on a branch, oldest first since it's
    waited longest, then landed work, newest first. A queue that won't load is the health
    screen's business, so it's left out here. Reads only."""
    rows = registry.load(project)["workstreams"]
    found = []
    for ws in rows:
        path = project.tasks_path(ws)
        if ws.get("status") not in registry.OPEN_STATUSES or not path.is_file():
            continue
        try:
            queue = tasks.load(path, project.config)
        except WsError:
            continue
        found += [entry for t in queue["tasks"] if (entry := _queue_entry(project, ws, t))]
    on_branch = sorted((e for e in found if e["state"] == "branch"), key=lambda e: e["when"] or "")
    landed = sorted((e for e in found if e["state"] == "landed"), key=lambda e: e["when"] or "",
                    reverse=True)
    return {"tasks": on_branch + landed}
