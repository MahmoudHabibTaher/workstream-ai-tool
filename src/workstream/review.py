"""Per-task review data: `ws review <TASK> [--file <path>] [--max-lines 1500]` as JSON:

    {task, evidence: <abs path or null>,
     range: {from, to, kind: "merge"|"commit"|"branch"|"none"},
     files: [{path, added, removed}], hunks?: {path, text, truncated}, error?}

- review_range(task, parents_of, branch_exists): pure. A task's `commit` is usually a
  `--no-ff` merge, whose `git show` is an empty combined diff, so a merge is reviewed
  against its first parent (`<commit>^1..<commit>`), a single-parent commit against its
  parent (`<commit>^..<commit>`). An in-progress task with no commit but an existing branch
  is reviewed before merge from where it left the integration branch, which leaves out the
  commit that claimed it. Anything else is `none`.
- parse_numstat(text) and cap_hunks(text, max_lines): pure. The hunks are cut at the last
  whole hunk that fits under the cap, since a hunk cut mid-way does not parse as a diff.
- The git calls sit at the edge, in build_review. They only read, and a git failure comes
  back as data (`error`), never raised.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

from workstream import registry, tasks
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
    return subprocess.run(["git", *argv], cwd=repo_root, capture_output=True, text=True)


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


def build_review(project: Project, ws_id: str, task_id: str, file: str | None = None,
                 max_lines: int = DEFAULT_MAX_LINES) -> dict:
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
    rng = review_range(task, lambda rev: git_parents(root, rev),
                       lambda name: git_branch_exists(root, name))
    if rng["kind"] == "branch":
        fork = _git(root, "merge-base", project.config.integration, rng["to"]).stdout.strip()
        if fork and not fork.startswith(rng["from"]):
            rng["from"] = fork
    out = {"task": task_id, "evidence": str(evidence) if evidence.is_file() else None,
           "range": rng, "files": []}
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
