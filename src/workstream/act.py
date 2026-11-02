"""Guarded, committed tracking writes: the only way a UI writes.

`ws act <action> -w <id> [--task <ID>] [--notes ...] --expect-registry <sha256>
[--expect-tasks <sha256>]`. One call refuses, writes and commits, so the single-writer
invariants live here, in tested Python, and not in any UI:

1. Refuse (one line on stderr, nothing written) when the checkout is not on the integration
   branch, when the registry or a tracking path of the workstream is dirty (any tracking
   path at all for `sync`), when a sha256 differs from `--expect-*` (the UI drew a stale view
   and re-snapshots), or when the transition isn't allowed: `pause` needs planned/active,
   `resume` needs paused, `unclaim` needs an in-progress task whose branch no worktree has
   checked out (the rule `snapshot` offers it by).
2. Run the write in-process, keeping the original bytes.
3. A write that changed nothing but the `updated` date puts the original bytes back and
   returns `no change`, without a commit.
4. `git commit --only -m "<id>: <action> [<task>] (ws act)" -- <changed paths>`. If the
   commit fails, the original bytes go back.

Closing and abandoning are not actions: one is a checked decision, the other needs a reason.
There is no lock around compare-and-write; the hashes and the dirty-path guard leave a window
of milliseconds between two of one user's own sessions, which is accepted.
"""

from __future__ import annotations

import json
import subprocess
from pathlib import Path

from workstream import gitutil, registry, snapshot, tasks
from workstream.errors import Refused, WsError
from workstream.fsutil import sha256
from workstream.project import Project

ACTIONS = ("pause", "resume", "unclaim", "sync")
# The registry status each action may start from; None means any.
FROM_STATUSES = {"pause": ("planned", "active"), "resume": ("paused",), "unclaim": None,
                 "sync": None}


def commit_message(ws_id: str, action: str, task: str | None) -> str:
    return f"{ws_id}: {action}{f' {task}' if task else ''} (ws act)"


def check_arguments(action: str, task: str | None, notes: str | None,
                    expect_tasks: str | None) -> None:
    if action == "unclaim":
        if not task:
            raise Refused("unclaim needs --task")
        if not expect_tasks:
            raise Refused("unclaim needs --expect-tasks")
    elif task:
        raise Refused(f"--task applies only to unclaim, not {action}")
    if notes is not None and action not in ("pause", "resume"):
        raise Refused(f"--notes applies only to pause and resume, not {action}")


def check_checkout(project: Project, facts: dict, action: str, ws_id: str,
                   rows: list[dict]) -> None:
    """The shared refusals: git readable, on the integration branch, and the paths this
    action reads and writes clean. A dirty tracking path means an orchestrator may be
    mid-step."""
    if "error" in facts:
        raise Refused(f"cannot read the checkout: {facts['error']}")
    integration = project.config.integration
    if facts["branch"] != integration:
        raise Refused(f"the checkout is on {facts['branch']}, not {integration}")
    registry_rel = project.rel(project.registry_path)
    folders = snapshot.folders_by_id(project, rows)
    dirty = [p for p in facts["dirtyTracking"]
             if (owner := snapshot.tracking_owner(p, registry_rel, folders)) is not None
             and (action == "sync" or owner in ("", ws_id))]
    if dirty:
        raise Refused(f"dirty tracking path (an orchestrator may be mid-step): "
                      f"{', '.join(dirty)}")


def check_revisions(registry_raw: bytes, tasks_raw: bytes | None, expect_registry: str,
                    expect_tasks: str | None) -> None:
    if sha256(registry_raw) != expect_registry:
        raise Refused("stale view: the registry changed since it was drawn; re-snapshot")
    if expect_tasks is not None and (tasks_raw is None or sha256(tasks_raw) != expect_tasks):
        raise Refused("stale view: the queue changed since it was drawn; re-snapshot")


def check_transition(action: str, ws: dict, tasks_raw: bytes | None, task: str | None,
                     facts: dict) -> None:
    allowed = FROM_STATUSES[action]
    if allowed is not None and ws.get("status") not in allowed:
        raise Refused(f"{action} needs status {' or '.join(allowed)}; "
                      f"{ws['id']} is {ws.get('status')}")
    if action != "unclaim":
        return
    task_list = json.loads(tasks_raw)["tasks"] if tasks_raw is not None else []
    found = next((t for t in task_list if t.get("id") == task), None)
    if found is None:
        raise Refused(f"no task {task} in {ws['id']}")
    if found.get("status") != "in-progress":
        raise Refused(f"unclaim needs an in-progress task; {task} is {found.get('status')}")
    live = {w["branch"] for w in facts.get("worktrees", []) if w.get("branch")}
    if found.get("branch") in live:
        raise Refused(f"a worktree has {found['branch']} checked out; remove it first")


def write_action(project: Project, action: str, ws_id: str, task: str | None,
                 notes: str | None, tasks_path: Path) -> None:
    if action in ("pause", "resume"):
        registry.set_status(project, ws_id, "paused" if action == "pause" else "active", notes)
        return
    if action == "unclaim":
        tasks.unclaim(tasks_path, [task], project.config)
    registry.sync(project)


def _without_updated(raw: bytes) -> object:
    data = json.loads(raw)
    if isinstance(data, dict):
        data.pop("updated", None)
    return data


def changed_paths(originals: dict[Path, bytes | None]) -> list[Path]:
    """The paths whose content changed, beyond the `updated` date every save stamps."""
    changed = []
    for path, before in originals.items():
        after = path.read_bytes() if path.exists() else None
        if after == before:
            continue
        if before is not None and after is not None and \
                _without_updated(before) == _without_updated(after):
            continue
        changed.append(path)
    return changed


def restore(originals: dict[Path, bytes | None]) -> None:
    for path, before in originals.items():
        if before is None:
            path.unlink(missing_ok=True)
        elif not path.exists() or path.read_bytes() != before:
            path.write_bytes(before)


def _git(repo_root: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *argv], cwd=repo_root, capture_output=True, text=True)


def commit(project: Project, paths: list[Path], message: str) -> str:
    """Commit exactly these paths; returns the short hash. Raises Refused on failure."""
    rels = [project.rel(p) for p in paths]
    done = _git(project.root, "commit", "-q", "--only", "-m", message, "--", *rels)
    if done.returncode != 0:
        detail = (done.stderr or done.stdout).strip().splitlines()
        raise Refused(f"commit failed, tracking files restored: "
                      f"{detail[-1] if detail else f'exit {done.returncode}'}")
    return _git(project.root, "rev-parse", "--short", "HEAD").stdout.strip()


def act(project: Project, action: str, ws_id: str, *, task: str | None = None,
        notes: str | None = None, expect_registry: str, expect_tasks: str | None = None) -> str:
    """Refuse, write and commit one action. Returns the line to print on success; raises
    Refused (nothing written, no commit) otherwise."""
    if action not in ACTIONS:
        raise Refused(f"action must be one of {', '.join(ACTIONS)}")
    check_arguments(action, task, notes, expect_tasks)
    registry_path = project.registry_path
    try:
        rows = registry.load(project)["workstreams"]
    except WsError as e:
        raise Refused(str(e)) from None
    registry_raw = registry_path.read_bytes()
    ws = next((w for w in rows if w.get("id") == ws_id), None)
    if ws is None:
        raise Refused(f"no workstream with id {ws_id!r}")
    tasks_path = project.tasks_path(ws)
    tasks_raw = tasks_path.read_bytes() if tasks_path.exists() else None
    if tasks_raw is not None:
        try:
            tasks.load(tasks_path, project.config)
        except WsError as e:
            raise Refused(str(e)) from None

    facts = snapshot.git_facts(project, rows)
    check_checkout(project, facts, action, ws_id, rows)
    check_revisions(registry_raw, tasks_raw, expect_registry, expect_tasks)
    check_transition(action, ws, tasks_raw, task, facts)

    originals = {registry_path: registry_raw, tasks_path: tasks_raw}
    try:
        write_action(project, action, ws_id, task, notes, tasks_path)
        changed = changed_paths(originals)
        if not changed:
            restore(originals)
            return "no change"
        short = commit(project, changed, commit_message(ws_id, action, task))
    except Refused:
        restore(originals)
        raise
    except WsError as e:
        restore(originals)
        raise Refused(str(e)) from None
    except BaseException:
        restore(originals)
        raise
    return f"committed {short}: {commit_message(ws_id, action, task)}"


def commit_claim(project: Project, ws: dict, ids: list[str], base: str | None,
                 by: str | None) -> tuple[str, str]:
    """Claim a batch and commit it on the integration branch, in one step. (base, commit).

    Workers branch from this commit, since their queue and registry come from it. Nothing else
    can be mid-write here: uncommitted tracking files are refused, and a claim that can't be
    committed is undone.
    """
    rows = registry.load(project)["workstreams"]
    check_checkout(project, snapshot.git_facts(project, rows), "claim", ws["id"], rows)
    base = base or gitutil.rev_parse(project.root, "HEAD")
    queue = project.tasks_path(ws)
    problems = tasks.batch_problems(tasks.load(queue, project.config)["tasks"], ids)
    if problems:
        raise Refused("claimed nothing:\n" + "\n".join(f"  - {p}" for p in problems))
    originals = {path: path.read_bytes() for path in (queue, project.registry_path)}
    try:
        tasks.claim(queue, ids, base, by, project.config)
        registry.sync(project)
        short = commit(project, changed_paths(originals),
                       f"{ws['id']}: claim {', '.join(ids)}")
    except BaseException:
        restore(originals)
        raise
    return base, short
