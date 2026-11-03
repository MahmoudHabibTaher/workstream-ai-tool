"""The workstream registry, <workstreams>/workstreams.json: every workstream that exists or
ever existed. It is the one place a workstream's lifecycle status lives, and the only record
left once a folder has been pruned.

    {
      "schemaVersion": 1, "updated": "YYYY-MM-DD",
      "workstreams": [{
        "id": str, "title": str, "summary": str, "status": str,
        "taskPrefix": str | null,   # every task id starts with this, when set
        "path": str,                # the folder, relative to the repo root
        "tier": "lite" | "standard" | "full",
        "created": "YYYY-MM-DD", "startedAt": str | null, "completedAt": str | null,
        "baseCommit": str,          # the commit the plan was written against
        "dependsOn": [str],         # other workstream ids that must be done first
        "progress": {"total": int, "todo": int, "in-progress": int, "blocked": int,
                     "done": int, "deferred": int},   # derived by `sync`, never by hand
        "notes": str,
        "closed": {"commit": str, "pruned": bool} | absent
      }, ...]
    }
"""

from __future__ import annotations

import json
import re
import shutil
from pathlib import Path

from workstream import gitutil, tasks
from workstream.errors import Refused, WsError
from workstream.fsutil import today, write_json
from workstream.project import TASKS_NAME, TEMPLATES_DIR, Project

MISSING_FILES_KEPT = 3

SCHEMA_VERSION = 1
STATUS_VALUES = ("planned", "active", "paused", "done", "abandoned")
OPEN_STATUSES = ("planned", "active", "paused")
# `done` is not here: closing goes through close(), which checks the queue first.
SETTABLE_STATUSES = ("planned", "active", "paused", "abandoned")
ID_RE = re.compile(r"^[a-z][a-z0-9_-]*$")
PREFIX_RE = re.compile(r"^[A-Z][A-Z0-9]*$")
PLACEHOLDER_RE = re.compile(r"\{\{([A-Z0-9_]+)")
# The files a workstream folder must hold, by tier. A lite workstream is a plan and a queue.
REQUIRED_FILES = {
    "lite": ("PLAN.md", TASKS_NAME),
    "standard": ("PLAN.md", TASKS_NAME, "DECISIONS.md", "PROGRESS.md", "session_handoff.md"),
    "full": ("PLAN.md", TASKS_NAME, "DECISIONS.md", "PROGRESS.md", "session_handoff.md"),
}
# A file a tier starts from a different template for.
TEMPLATE_FOR = {("lite", "PLAN.md"): "PLAN.lite.md"}


def new_registry() -> dict:
    return {"schemaVersion": SCHEMA_VERSION, "updated": today(), "workstreams": []}


def load(project: Project) -> dict:
    path = project.registry_path
    if not path.exists():
        raise WsError(f"{project.rel(path)} does not exist (run `ws init`)")
    try:
        with path.open() as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise WsError(f"{project.rel(path)}: not valid JSON: {e}") from None
    if not isinstance(data, dict) or not isinstance(data.get("workstreams"), list):
        raise WsError(f"{project.rel(path)}: not a registry (no `workstreams` list)")
    for n, row in enumerate(data["workstreams"], 1):
        if not isinstance(row, dict) or not isinstance(row.get("id"), str) or not row["id"]:
            raise WsError(f"{project.rel(path)}: row {n} has no id")
    return data


def save(project: Project, data: dict) -> None:
    data["updated"] = today()
    write_json(project.registry_path, data)


def find(data: dict, ws_id: str) -> dict:
    for ws in data["workstreams"]:
        if ws["id"] == ws_id:
            return ws
    raise WsError(f"no workstream with id {ws_id!r} (see `ws list --all`)")


def count_progress(task_list: list[dict]) -> dict:
    progress = {"total": len(task_list), **{s: 0 for s in tasks.STATUS_VALUES}}
    for t in task_list:
        status = t.get("status")
        if isinstance(status, str):  # validate reports a bad one; counting shouldn't crash on it
            progress[status] = progress.get(status, 0) + 1
    return progress


def compute_progress(project: Project, ws: dict) -> dict:
    """Counted from the queue. A pruned workstream has none, so its last count stands."""
    path = project.tasks_path(ws)
    if not path.exists():
        return ws.get("progress") or count_progress([])
    try:
        return count_progress(tasks.read_raw(path)["tasks"])
    except WsError:
        return ws.get("progress") or count_progress([])


def render(text: str, values: dict) -> str:
    for key, value in values.items():
        text = text.replace("{{" + key + "}}", value)
    return text


def create(project: Project, ws_id: str, title: str, summary: str, *,
           prefix: str | None = None, base: str | None = None,
           depends_on: list[str] | None = None, tier: str = "standard",
           under: str | None = None) -> dict:
    """Scaffold a workstream folder from the templates and register it as planned.

    `under` places it at <under>/workstreams/<id>, for work confined to one module.
    """
    data = load(project)
    if not ID_RE.match(ws_id):
        raise WsError("id must be lower-case letters, digits, - or _, starting with a letter")
    if prefix is not None and not PREFIX_RE.match(prefix):
        raise WsError("prefix must be upper-case letters/digits, e.g. SP")
    if tier not in tasks.TIERS:
        raise WsError(f"tier must be one of {', '.join(tasks.TIERS)}")
    if any(w["id"] == ws_id for w in data["workstreams"]):
        raise WsError(f"workstream {ws_id!r} already registered")
    if tier == tasks.RELEASING_TIER and project.config.release_mode == "none":
        raise WsError("a full workstream ships a release, and this project has no runbook: set "
                      "[release] mode and runbook in the config, or use another tier")
    if prefix:
        clash = [w["id"] for w in data["workstreams"]
                 if w.get("taskPrefix") and (w["taskPrefix"].startswith(prefix)
                                             or prefix.startswith(w["taskPrefix"]))]
        if clash:
            raise WsError(f"prefix {prefix!r} overlaps the task prefix of {clash}")
    for dep in depends_on or []:
        find(data, dep)

    if under:
        folder = project.inside(f"{under}/{project.config.workstreams_dir}/{ws_id}")
    else:
        folder = project.workstreams_dir / ws_id
    if folder.exists():
        raise WsError(f"{project.rel(folder)} already exists")
    folder.mkdir(parents=True)

    base = base or gitutil.rev_parse(project.root, project.config.integration, short=True)
    values = {"ID": ws_id, "TITLE": title, "DATE": today(), "BASE": base or "(unknown)",
              "INTEGRATION": project.config.integration, "SUMMARY": summary}
    for name in REQUIRED_FILES[tier]:
        if name != TASKS_NAME:
            template = TEMPLATES_DIR / TEMPLATE_FOR.get((tier, name), name)
            (folder / name).write_text(render(template.read_text(), values))
    source = f"{project.rel(folder)}/PLAN.md"
    tasks.save(folder / TASKS_NAME, tasks.new_envelope(source, tier))

    ws = {
        "id": ws_id, "title": title, "summary": summary, "status": "planned",
        "taskPrefix": prefix, "path": project.rel(folder), "tier": tier, "created": today(),
        "startedAt": None, "completedAt": None, "baseCommit": base,
        "dependsOn": depends_on or [], "progress": count_progress([]), "notes": "",
    }
    data["workstreams"].append(ws)
    save(project, data)
    return ws


def set_status(project: Project, ws_id: str, status: str, notes: str | None = None) -> dict:
    data = load(project)
    ws = find(data, ws_id)
    if status not in SETTABLE_STATUSES:
        raise WsError(f"status must be one of {', '.join(SETTABLE_STATUSES)}; "
                      "`ws close` closes a workstream")
    if status == "abandoned" and not notes:
        raise WsError("abandoning needs --notes saying why")
    ws["status"] = status
    if status == "active" and not ws.get("startedAt"):
        ws["startedAt"] = today()
    if status == "abandoned":
        ws["completedAt"] = ws.get("completedAt") or today()
    elif ws.get("completedAt"):
        ws["completedAt"] = None
    if notes is not None:
        ws["notes"] = notes
    ws["progress"] = compute_progress(project, ws)
    save(project, data)
    return ws


def check_claimable(project: Project, ws: dict) -> None:
    """A claim needs a workstream that is open for work, and whatever it depends on finished."""
    if ws.get("status") not in ("planned", "active"):
        raise Refused(f"{ws['id']} is {ws.get('status')}; `ws set-status active` resumes it")
    rows = load(project)["workstreams"]
    status = {w["id"]: w.get("status") for w in rows}
    waiting = [d for d in ws.get("dependsOn", []) if status.get(d) != "done"]
    if waiting:
        raise Refused(f"{ws['id']} depends on {', '.join(waiting)}, not done yet")


RELEASE_ORDER = ("none", "patch", "minor", "major")


def release_bump(task_list: list[dict]) -> tuple[str, list[str]]:
    """(the highest releaseImpact among done tasks, the done tasks that don't say). A deferred
    task shipped nothing, so it doesn't count."""
    done = [t for t in task_list if t.get("status") == "done"]
    known = [t["releaseImpact"] for t in done if t.get("releaseImpact") in RELEASE_ORDER]
    bump = max(known, key=RELEASE_ORDER.index, default="none")
    return bump, [t["id"] for t in done if t.get("releaseImpact") is None]


def sync(project: Project) -> list[str]:
    """Refresh every row's progress, moving planned to active once a task has started.
    Returns one line per thing worth saying. Never closes anything."""
    data = load(project)
    lines = []
    for ws in data["workstreams"]:
        ws["progress"] = compute_progress(project, ws)
        p = ws["progress"]
        if ws["status"] == "planned" and p["total"] - p["todo"] > 0:
            ws["status"] = "active"
            ws["startedAt"] = ws.get("startedAt") or today()
            lines.append(f"{ws['id']}: planned -> active (a task has started)")
        remaining = p["todo"] + p["in-progress"] + p["blocked"]
        if ws["status"] == "active" and p["total"] and remaining == 0:
            lines.append(f"{ws['id']}: queue is empty; `ws close -w {ws['id']}` closes it")
    save(project, data)
    lines.append(f"synced {len(data['workstreams'])} workstream(s)")
    return lines


def _commits_gone(project: Project, commits: list[str]) -> set[str]:
    """Which commit fields name hashes and none resolve. An older queue may hold a sentence around
    its hashes, or a marker with none, and neither says anything is wrong. One git call for the
    whole queue: a long one has hundreds, and a UI asks each time something changes."""
    named = {commit: re.findall(r"\b[0-9a-f]{7,40}\b", commit) for commit in commits}
    known = gitutil.existing_commits(project.root, [h for hashes in named.values() for h in hashes])
    return {commit for commit, hashes in named.items() if hashes and not known.intersection(hashes)}


def collapse_missing_files(warnings: list[str], keep: int = MISSING_FILES_KEPT) -> list[str]:
    """Files a task will create are normal, so a long list of them hides what else is there."""
    by_ws: dict[str, list[str]] = {}
    for w in warnings:
        if w.endswith(tasks.MISSING_FILES_SUFFIX):
            by_ws.setdefault(w.split(":", 1)[0], []).append(w)
    out = []
    for w in warnings:
        group = by_ws.get(w.split(":", 1)[0], []) if w.endswith(tasks.MISSING_FILES_SUFFIX) else []
        if len(group) <= keep:
            out.append(w)
        elif w is group[0]:
            first = w.split("files path ", 1)[1].removesuffix(tasks.MISSING_FILES_SUFFIX).strip()
            out.append(f"{w.split(':', 1)[0]}: {len(group)} paths in `files` don't exist yet, as with "
                       f"a file a task will create (first: {first})")
    return out


def validate_entry(project: Project, ws: dict, ids: set[str]) -> tuple[list[str], list[str]]:
    """(errors, warnings) for one registry row, its folder and its queue."""
    problems: list[str] = []
    warnings: list[str] = []
    wid = ws.get("id", "?")
    for field in ("id", "title", "status", "created"):
        if not ws.get(field):
            problems.append(f"{wid}: missing {field}")
    if ws.get("status") not in STATUS_VALUES:
        problems.append(f"{wid}: status {ws.get('status')!r} not in {list(STATUS_VALUES)}")
    for dep in ws.get("dependsOn", []):
        if dep not in ids:
            problems.append(f"{wid}: dependsOn unknown workstream {dep!r}")
    pruned = (ws.get("closed") or {}).get("pruned", False)
    folder = project.folder(ws) if ws.get("id") else None
    if folder is None or not folder.is_dir():
        if not pruned:
            problems.append(f"{wid}: folder {ws.get('path') or wid} missing")
        return problems, warnings
    tier = ws.get("tier", "standard")
    required = REQUIRED_FILES.get(tier, REQUIRED_FILES["standard"])
    if not pruned:
        problems += [f"{wid}: {name} missing" for name in required
                     if not (folder / name).exists()]
    path = folder / TASKS_NAME
    if path.exists():
        queue = _queue_problems(project, ws, path, problems, warnings)
        if ws.get("status") != "planned" and queue is not None and not queue:
            problems.append(f"{wid}: status {ws.get('status')!r} but {TASKS_NAME} is empty")
    if ws.get("status") in OPEN_STATUSES:
        for name in required:
            file = folder / name
            if file.exists():
                for slot in sorted(set(PLACEHOLDER_RE.findall(file.read_text()))):
                    problems.append(f"{wid}: {name} still has the {{{{{slot}}}}} placeholder")
    return problems, warnings


def _queue_problems(project: Project, ws: dict, path: Path, problems: list[str],
                    warnings: list[str]) -> list[dict] | None:
    """Adds this queue's problems to the lists; returns its raw tasks, None if unreadable."""
    wid = ws.get("id", "?")
    try:
        queue = tasks.read_raw(path)
    except WsError as e:
        problems.append(f"{wid}: {e}")
        return None
    version = queue.get("schemaVersion")
    if version != tasks.SCHEMA_VERSION:
        problems.append(f"{wid}: {TASKS_NAME} schemaVersion {version!r} is not "
                        f"{tasks.SCHEMA_VERSION}")
    tier = ws.get("tier", "standard")
    errors, task_warnings = tasks.validate_tasks(queue["tasks"], project.root, project.config, tier)
    if tier == tasks.RELEASING_TIER and project.config.release_mode == "none":
        errors.append("a full workstream needs [release] mode and runbook in the config")
    problems += [f"{wid}: {e}" for e in errors]
    warnings += [f"{wid}: {w}" for w in task_warnings]
    planned_with = queue.get("protocolVersion")
    if planned_with and planned_with != tasks.PROTOCOL_VERSION:
        warnings.append(f"{wid}: planned against protocol {planned_with}; "
                        f"this is {tasks.PROTOCOL_VERSION}")
    landed = [t for t in queue["tasks"]
              if t.get("status") == "done" and isinstance(t.get("commit"), str)]
    gone = _commits_gone(project, [t["commit"] for t in landed])
    warnings += [f"{wid}: {t['id']}: commit {t['commit']} isn't in this repository; "
                 "was it rewritten?" for t in landed if t["commit"] in gone]
    prefix = ws.get("taskPrefix")
    if prefix:
        for t in queue["tasks"]:
            tid = t.get("id")
            if isinstance(tid, str) and not tid.startswith(prefix):
                problems.append(f"{wid}: task {tid} lacks prefix {prefix!r}")
    return queue["tasks"]


def validate_all(project: Project) -> tuple[list[str], list[str], int]:
    """(errors, warnings, row count) across the whole registry."""
    data = load(project)
    rows = data["workstreams"]
    ids = [w.get("id") for w in rows]
    problems = [f"duplicate workstream id: {i}" for i in sorted({i for i in ids if ids.count(i) > 1})]
    prefixes = [(w.get("taskPrefix"), w.get("id")) for w in rows if w.get("taskPrefix")]
    for a, aid in prefixes:
        for b, bid in prefixes:
            if aid != bid and b.startswith(a):
                problems.append(f"task prefix {a!r} ({aid}) overlaps {b!r} ({bid})")
    warnings: list[str] = []
    for ws in rows:
        entry_problems, entry_warnings = validate_entry(project, ws, set(ids))
        problems += entry_problems
        warnings += entry_warnings
    registered = {project.folder(w).resolve() for w in rows if w.get("id")}
    for path in discover_queues(project):
        if path.parent.resolve() not in registered:
            problems.append(f"unregistered workstream: {project.rel(path.parent)}")
    return problems, warnings, len(rows)


def discover_queues(project: Project) -> list[Path]:
    """Every queue file in the repository, wherever its workstreams/ folder sits. A file of
    that name anywhere else (a test fixture, say) isn't a workstream."""
    spec = (TASKS_NAME, f"**/{TASKS_NAME}")
    found = gitutil.tracked_and_untracked(project.root, *spec)
    expected = Path(project.config.workstreams_dir).parts
    paths = {project.root / p for p in found
             if (project.root / p).is_file() and Path(p).parent.parent.parts[-len(expected):] == expected}
    # Not a git repo, or nothing tracked yet: fall back to the configured folder.
    if project.workstreams_dir.is_dir():
        paths.update(project.workstreams_dir.glob(f"*/{TASKS_NAME}"))
    return sorted(paths)


def reconcile(project: Project) -> tuple[list[str], list[str]]:
    """Registry against the tree: (added, differences).

    Adding a row for a queue the registry never knew is safe and done here. Everything else
    is only reported: deciding which side is right is a human call, because the usual cause
    of a disagreement is work settled without being committed.
    """
    data = load(project)
    rows = data["workstreams"]
    added = []
    known_folders = {project.folder(w).resolve() for w in rows if w.get("id")}
    known_ids = {w.get("id") for w in rows}
    differences = []
    for path in discover_queues(project):
        folder = path.parent.resolve()
        if folder in known_folders:
            continue
        ws_id = folder.name
        if ws_id in known_ids:
            differences.append(f"{project.rel(folder)}: name {ws_id!r} is already registered "
                               "at another path")
            continue
        progress = compute_progress(project, {"id": ws_id, "path": project.rel(folder)})
        rows.append({
            "id": ws_id, "title": ws_id, "summary": "", "status": "planned", "taskPrefix": None,
            "path": project.rel(folder), "tier": "standard", "created": today(),
            "startedAt": None, "completedAt": None, "baseCommit": "", "dependsOn": [],
            "progress": progress, "notes": "",
        })
        known_ids.add(ws_id)
        added.append(ws_id)

    for ws in rows:
        wid = ws.get("id", "?")
        folder = project.folder(ws)
        pruned = (ws.get("closed") or {}).get("pruned", False)
        if not folder.is_dir():
            if not pruned:
                differences.append(f"{wid}: folder {ws.get('path') or wid} is gone")
            continue
        path = folder / TASKS_NAME
        if not path.exists():
            continue
        progress = compute_progress(project, ws)
        if ws.get("progress") != progress:
            differences.append(f"{wid}: recorded progress differs from the queue; "
                               "`ws sync` refreshes it")
        remaining = progress["todo"] + progress["in-progress"] + progress["blocked"]
        if ws.get("status") == "done" and remaining:
            differences.append(f"{wid}: registry says done but {remaining} task(s) are open")
        if ws.get("status") == "planned" and progress["total"] - progress["todo"] > 0:
            differences.append(f"{wid}: registry says planned but a task has started")
    if added:
        save(project, data)
    return added, differences


def close_plan(project: Project, ws_id: str, *, allow_deferred: bool = False) -> dict:
    """What closing would do, or a WsError if the queue isn't finished. Writes nothing."""
    ws = find(load(project), ws_id)
    if ws.get("status") not in OPEN_STATUSES:
        raise WsError(f"{ws_id} is {ws.get('status')}, not open")
    path = project.tasks_path(ws)
    queue = tasks.load(path, project.config)["tasks"] if path.exists() else []
    open_ids = [t["id"] for t in queue if t["status"] in tasks.OPEN_STATUSES]
    deferred = [t["id"] for t in queue if t["status"] == "deferred"]
    if open_ids:
        raise WsError(f"{ws_id} has open tasks: {', '.join(open_ids)}")
    if deferred and not allow_deferred:
        raise WsError(f"{ws_id} has deferred tasks: {', '.join(deferred)} "
                      "(--allow-deferred closes anyway)")
    return {"id": ws_id, "folder": project.folder(ws), "tasks": len(queue), "deferred": deferred}


def close(project: Project, ws_id: str, *, allow_deferred: bool = False, prune: bool = False,
          purge: bool = False) -> dict:
    """Mark a finished workstream done. The row always survives.

    By default every file stays, so citations into the folder never go stale. `prune` removes
    what only a next session needed (the queue and the handoff); `purge` removes the whole
    folder. Both record the final counts and commit in the row first. Commits nothing.
    """
    plan = close_plan(project, ws_id, allow_deferred=allow_deferred)
    if (prune or purge) and project.registry_path.resolve().is_relative_to(plan["folder"].resolve()):
        raise WsError(f"{ws_id}'s folder holds the registry itself; refusing to remove it")
    data = load(project)
    ws = find(data, ws_id)
    ws["progress"] = compute_progress(project, ws)
    ws["status"] = "done"
    ws["completedAt"] = ws.get("completedAt") or today()
    ws["closed"] = {"commit": gitutil.rev_parse(project.root, "HEAD"),
                    "pruned": prune or purge}
    save(project, data)
    folder = plan["folder"]
    if purge:
        shutil.rmtree(folder, ignore_errors=True)
    elif prune:
        for name in (TASKS_NAME, "session_handoff.md"):
            (folder / name).unlink(missing_ok=True)
    return ws
