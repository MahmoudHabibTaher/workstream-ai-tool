"""The read model: one JSON document every UI draws from. Everything here reads.

- git_facts(project, rows): the only impure part. Read-only git calls; never raises, a git
  failure comes back as {"error": "..."}.
- health_findings(project, registry, queues, facts, now, stale_hours): pure apart from the
  config it is handed. Every finding carries the `actions` the guarded writer (`ws act`)
  would accept right now, so a UI renders what the snapshot allows and decides nothing.
- build_snapshot(project, ws_id, ...): reads the tree and assembles the rest.
"""

from __future__ import annotations

import subprocess
from datetime import datetime, timedelta, timezone
from pathlib import Path

from workstream import graph, registry, tasks
from workstream.errors import WsError
from workstream.fsutil import sha256
from workstream.project import TASKS_NAME, Project

SNAPSHOT_VERSION = 1
DEFAULT_STALE_HOURS = 24
# The narrative files a workstream folder may carry, by the key the snapshot names them with.
NARRATIVE_FILES = {
    "plan": "PLAN.md",
    "progress": "PROGRESS.md",
    "decisions": "DECISIONS.md",
    "handoff": "session_handoff.md",
}


# --- git ----------------------------------------------------------------------------------


def _git(repo_root: Path, *argv: str) -> str:
    return subprocess.run(
        ["git", *argv], cwd=repo_root, capture_output=True, text=True, check=True
    ).stdout


def parse_worktrees(porcelain: str) -> list[dict]:
    """`git worktree list --porcelain` as [{path, head, branch, main}]; branch is the short
    name, or None when detached. The first entry is the main worktree."""
    worktrees: list[dict] = []
    for block in porcelain.strip().split("\n\n"):
        fields = {}
        for line in block.splitlines():
            key, _, value = line.partition(" ")
            fields[key] = value
        if "worktree" not in fields:
            continue
        branch = fields.get("branch")
        worktrees.append({
            "path": fields["worktree"],
            "head": fields.get("HEAD"),
            "branch": branch.removeprefix("refs/heads/") if branch else None,
            "main": not worktrees,
        })
    return worktrees


def parse_status_paths(porcelain: str) -> list[str]:
    """The paths in `git status --porcelain` output; a rename gives its new path."""
    paths = []
    for line in porcelain.splitlines():
        if len(line) > 3:
            paths.append(line[3:].split(" -> ")[-1].strip('"'))
    return paths


def tracking_paths(project: Project, rows: list[dict]) -> list[str]:
    """What counts as tracking state: the registry, and each workstream's folder."""
    paths = [project.rel(project.registry_path)]
    paths += [project.rel(project.folder(w)) for w in rows if w.get("id")]
    return paths


def git_facts(project: Project, rows: list[dict]) -> dict:
    """{branch, taskBranches, worktrees, dirtyTracking} for the checkout.

    Never raises: a missing git, a path that isn't a repo or a failing command comes back
    as {"error": "<what failed>"}.
    """
    root = project.root
    try:
        branch = _git(root, "rev-parse", "--abbrev-ref", "HEAD").strip()
        branches = _git(root, "branch", "--list", project.config.task_branch_glob(),
                        "--format=%(refname:short)")
        worktrees = _git(root, "worktree", "list", "--porcelain")
        status = _git(root, "status", "--porcelain", "--", *tracking_paths(project, rows))
    except subprocess.CalledProcessError as e:
        detail = (e.stderr or "").strip().splitlines()
        return {"error": f"{' '.join(e.cmd)}: {detail[-1] if detail else f'exit {e.returncode}'}"}
    except (OSError, ValueError) as e:
        return {"error": f"git: {e}"}
    return {
        "branch": branch,
        "taskBranches": [b for b in branches.splitlines() if b],
        "worktrees": parse_worktrees(worktrees),
        "dirtyTracking": parse_status_paths(status),
    }


# --- health -------------------------------------------------------------------------------


def parse_time(value: object) -> datetime | None:
    """An ISO timestamp (`claim` writes ...Z) as an aware datetime; None if unreadable."""
    if not isinstance(value, str) or not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def tracking_owner(path: str, registry_rel: str, folders: dict[str, str]) -> str | None:
    """The workstream a dirty path is a tracking file of: "" for the registry itself, the
    id for a file inside a registered folder, None for anything else."""
    path = path.rstrip("/")
    if path == registry_rel:
        return ""
    for ws_id, folder in folders.items():
        if path == folder or path.startswith(folder + "/"):
            return ws_id
    return None


def folders_by_id(project: Project, rows: list[dict]) -> dict[str, str]:
    return {w["id"]: project.rel(project.folder(w)) for w in rows if w.get("id")}


def finding(kind: str, level: str, ws: str | None, task: str | None, message: str,
            actions: list[dict] | None = None) -> dict:
    return {"kind": kind, "level": level, "workstream": ws, "task": task, "message": message,
            "actions": actions or []}


class _Context:
    """What every finding rule needs, worked out once from the inputs."""

    def __init__(self, project: Project, reg: dict, queues: dict, facts: dict) -> None:
        self.project = project
        self.rows = reg.get("workstreams", [])
        self.status = {w.get("id"): w.get("status") for w in self.rows}
        self.queues = queues
        self.facts = facts
        self.git_ok = "error" not in facts
        registry_rel = project.rel(project.registry_path)
        folders = folders_by_id(project, self.rows)
        self.owner = lambda p: tracking_owner(p, registry_rel, folders)
        dirty = facts.get("dirtyTracking", []) if self.git_ok else []
        self.dirty = [p for p in dirty if self.owner(p) is not None]
        self.dirty_owners = {self.owner(p) for p in self.dirty}
        self.on_integration = facts.get("branch") == project.config.integration
        self.live_branches = {w["branch"] for w in facts.get("worktrees", []) if w.get("branch")}

    def tasks(self, statuses: tuple[str, ...] | None = None):
        """(workstream id, task) over every queue, optionally filtered by status."""
        for ws_id, queue in self.queues.items():
            for t in queue.get("tasks", []):
                if statuses is None or t.get("status") in statuses:
                    yield ws_id, t

    def can_write(self, ws_id: str) -> bool:
        """`ws act`'s shared refusals: on the integration branch, and neither the registry
        nor this workstream's tracking files dirty."""
        return (self.git_ok and self.on_integration
                and "" not in self.dirty_owners and ws_id not in self.dirty_owners)


def _invalid(ctx: _Context) -> list[dict]:
    out = []
    for ws_id, queue in ctx.queues.items():
        out += [finding("invalid", "error", ws_id, None, e) for e in queue.get("errors", [])]
        out += [finding("invalid", "warning", ws_id, None, w) for w in queue.get("warnings", [])]
    return out


def _stale_claims(ctx: _Context, now: datetime, stale_hours: float) -> list[dict]:
    out = []
    for ws_id, t in ctx.tasks(("in-progress",)):
        started = parse_time(t.get("startedAt"))
        if started is None or now - started < timedelta(hours=stale_hours):
            continue
        age = int((now - started).total_seconds() // 3600)
        branch = t.get("branch")
        live = bool(branch) and branch in ctx.live_branches
        actions = []
        if ctx.can_write(ws_id) and not live:
            actions.append({"action": "unclaim", "workstream": ws_id, "task": t["id"]})
        note = f"; a worktree has {branch} checked out" if live else ""
        out.append(finding(
            "stale-claim", "warning", ws_id, t["id"],
            f"{t['id']} in progress for {age}h (claimed by {t.get('claimedBy') or '-'}){note}",
            actions,
        ))
    return out


def _orphan_branches(ctx: _Context) -> list[dict]:
    if not ctx.git_ok:
        return []
    open_named = {t.get("branch") for _, t in ctx.tasks(tasks.OPEN_STATUSES)}
    done_named = {t.get("branch"): (w, t["id"]) for w, t in ctx.tasks(("done",))}
    out = []
    for branch in ctx.facts.get("taskBranches", []):
        if branch in open_named:
            continue
        ws_id, task = done_named.get(branch, (None, None))
        why = f"its task {task} is done" if task else "no open task names it"
        out.append(finding("orphan-branch", "warning", ws_id, task, f"branch {branch}: {why}"))
    return out


def _orphan_worktrees(ctx: _Context) -> list[dict]:
    if not ctx.git_ok:
        return []
    claimed = {t.get("branch") for _, t in ctx.tasks(("in-progress",))}
    out = []
    for wt in ctx.facts.get("worktrees", []):
        if wt.get("main") or (wt.get("branch") and wt["branch"] in claimed):
            continue
        on = wt.get("branch") or "a detached HEAD"
        out.append(finding("orphan-worktree", "warning", None, None,
                           f"worktree {wt['path']} on {on}: no in-progress task's branch"))
    return out


def _missing_evidence(ctx: _Context) -> list[dict]:
    out = []
    for ws_id, t in ctx.tasks(("done",)):
        if ctx.status.get(ws_id) not in registry.OPEN_STATUSES:
            continue
        if t["id"] not in ctx.queues[ws_id].get("evidence", []):
            out.append(finding("missing-evidence", "warning", ws_id, t["id"],
                               f"{t['id']} is done but has no evidence/{t['id']}.md"))
    return out


def _checkout(ctx: _Context) -> list[dict]:
    if not ctx.git_ok:
        return []
    out = []
    if not ctx.on_integration:
        out.append(finding(
            "wrong-branch", "warning", None, None,
            f"the checkout is on {ctx.facts.get('branch')}, not "
            f"{ctx.project.config.integration}; UI writes are disabled",
        ))
    for owner in sorted(ctx.dirty_owners):
        paths = [p for p in ctx.dirty if ctx.owner(p) == owner]
        out.append(finding(
            "dirty-tracking", "warning", owner or None, None,
            f"uncommitted tracking paths (an orchestrator may be mid-step): {', '.join(paths)}",
        ))
    return out


def health_findings(project: Project, reg: dict, queues: dict, facts: dict, now: datetime,
                    stale_hours: float = DEFAULT_STALE_HOURS) -> list[dict]:
    """Every health finding, errors before warnings.

    reg is the parsed registry; queues maps a workstream id to {"tasks": [...], "evidence":
    [task ids with an evidence file], "errors": [...], "warnings": [...]}; facts is
    git_facts' result. Git-based kinds are skipped when facts carries an error. Each finding
    is {kind, level, workstream, task, message, actions}; `unclaim` is offered on a stale
    claim only on the integration branch, with clean tracking paths, and when no worktree
    has the task's branch checked out.
    """
    ctx = _Context(project, reg, queues, facts)
    found = (_invalid(ctx) + _stale_claims(ctx, now, stale_hours) + _orphan_branches(ctx)
             + _orphan_worktrees(ctx) + _missing_evidence(ctx) + _checkout(ctx))
    return sorted(found, key=lambda f: f["level"] != "error")


# --- the read model -----------------------------------------------------------------------


def _read_queue(project: Project, ws: dict, ids: set[str]) -> tuple[dict, str | None]:
    """One workstream's queue entry for health_findings, and its queue file's sha256."""
    errors, warnings = registry.validate_entry(project, ws, ids)
    # A files path a task has yet to create is the normal state of a planned task, not a
    # health problem; `validate` still prints it.
    warnings = [w for w in warnings if not w.endswith(tasks.MISSING_FILES_SUFFIX)]
    folder = project.folder(ws)
    path = folder / TASKS_NAME
    entry = {"tasks": [], "evidence": [], "errors": errors, "warnings": warnings}
    if not path.exists():
        return entry, None
    raw = path.read_bytes()
    try:
        queue = tasks.read_raw(path)
    except WsError:  # validate_entry already reported it
        return entry, sha256(raw)
    # validate_entry reports a malformed task; the read model still draws the others.
    entry["tasks"] = [tasks.normalize_task(t, project.config) for t in queue["tasks"]
                      if tasks.is_queueable(t)]
    evidence = folder / "evidence"
    entry["evidence"] = sorted(p.stem for p in evidence.glob("*.md")) if evidence.is_dir() else []
    return entry, sha256(raw)


def _paths(folder: Path, task_list: list[dict]) -> dict:
    paths = {key: str(folder / name) for key, name in NARRATIVE_FILES.items()
             if (folder / name).exists()}
    paths["evidence"] = {t["id"]: str(folder / "evidence" / f"{t['id']}.md") for t in task_list
                         if (folder / "evidence" / f"{t['id']}.md").exists()}
    return paths


def build_snapshot(project: Project, ws_id: str | None = None,
                   stale_hours: float = DEFAULT_STALE_HOURS,
                   now: datetime | None = None) -> dict:
    """The whole read model. Raises WsError for an unknown ws_id. With ws_id it adds that
    workstream's tasks, wave and narrative paths."""
    reg = registry.load(project)
    registry_raw = project.registry_path.read_bytes()
    rows = reg["workstreams"]
    ids = {w.get("id") for w in rows}
    if ws_id is not None and ws_id not in ids:
        raise WsError(f"no workstream with id {ws_id!r}")

    queues: dict[str, dict] = {}
    task_revisions: dict[str, str] = {}
    for ws in rows:
        entry, revision = _read_queue(project, ws, ids)
        queues[ws["id"]] = entry
        if revision:
            task_revisions[ws["id"]] = revision

    def live_progress(ws: dict) -> dict:
        # A pruned workstream has no queue left, so its recorded count is the record.
        if project.tasks_path(ws).exists():
            return registry.count_progress(queues[ws["id"]]["tasks"])
        return ws.get("progress") or registry.count_progress([])

    facts = git_facts(project, rows)
    snapshot = {
        "snapshotVersion": SNAPSHOT_VERSION,
        "repoRoot": str(project.root),
        "integrationBranch": project.config.integration,
        "registry": [{**ws, "progress": live_progress(ws),
                      "progressStale": ws.get("progress") != live_progress(ws)} for ws in rows],
        "revisions": {"registry": sha256(registry_raw), "tasks": task_revisions},
    }
    if ws_id is not None:
        task_list = sorted(queues[ws_id]["tasks"], key=lambda t: t["priority"])
        folder = project.folder(next(w for w in rows if w["id"] == ws_id))
        snapshot.update(tasks=task_list, wave=graph.compute_wave(task_list),
                        paths=_paths(folder, task_list))
    now = now or datetime.now(timezone.utc)
    snapshot["health"] = health_findings(project, reg, queues, facts, now, stale_hours)
    snapshot["git"] = facts
    return snapshot
