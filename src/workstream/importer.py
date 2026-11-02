"""`ws import`: bring a project's older workstream files onto schema v3, in place.

Two older shapes are told apart by what's on disk. `folder-registry` keeps its registry in the
workstreams folder and uses this tool's statuses, with a frozen protocol copy in each workstream.
`root-registry` keeps its registry at the repo root, and tasks with other field names and statuses.

A dry run is the default, since this rewrites every queue a project has. Finished work converts
without being re-judged: `ws validate` only holds open tasks to today's rules. What can't be decided
here, like a command only the old harness knew, comes back as a list for a person.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path

from workstream import registry, tasks
from workstream.fsutil import today, write_json
from workstream.project import REGISTRY_NAME, TASKS_NAME, Project

FOLDER_REGISTRY, ROOT_REGISTRY = "folder-registry", "root-registry"
FROZEN_PROTOCOL = "AGENTS.md"
OLD_HANDOFF = "SESSION_HANDOFF.md"
NO_COMMIT = "imported-without-a-commit"
OLD_STATUSES = {"pending": "todo", "in_progress": "in-progress"}
OLD_FIELDS = {"dependsOn": "blockedBy", "description": "summary", "filesToTouch": "files",
              "acceptanceCriteria": "acceptance", "validation": "verify"}
OLD_TOP_LEVEL = ("statusValues", "protocol", "logbook", "workstream", "baseline", "validation",
                 "sourceRoot", "reuseRule")
OLD_REGISTRY_STATUSES = {"closed": "done", "open": "active"}


@dataclass
class Plan:
    """What an import would do, written as it goes when `write` is set."""
    write: bool
    done: list[str] = field(default_factory=list)
    todo: list[str] = field(default_factory=list)


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9_]+", "_", name.lower()).strip("_")


def detect(project: Project) -> list[str]:
    found = []
    if _old_rows(project.root / REGISTRY_NAME):
        found.append(ROOT_REGISTRY)
    if _needs_folder_import(project):
        found.append(FOLDER_REGISTRY)
    return found


def _old_rows(path: Path) -> list[dict]:
    """The rows of a registry at the repo root, or none if it isn't one."""
    try:
        rows = json.loads(path.read_text()).get("workstreams")
    except (OSError, json.JSONDecodeError, AttributeError):
        return []
    return rows if isinstance(rows, list) and all("name" in r for r in rows) else []


def _needs_folder_import(project: Project) -> bool:
    if not project.registry_path.exists():
        return False
    data = json.loads(project.registry_path.read_text())
    return any(_is_old_queue(project.folder(w) / TASKS_NAME) or "path" not in w
               for w in data.get("workstreams", []))


def _is_old_queue(path: Path) -> bool:
    return path.exists() and tasks.read_raw(path).get("schemaVersion") != tasks.SCHEMA_VERSION


# --- queues -------------------------------------------------------------------------------------


def _convert_task(task: dict, index: int, plan: Plan, label: str) -> dict:
    out = {OLD_FIELDS.get(k, k): v for k, v in task.items()}
    out["status"] = OLD_STATUSES.get(out.get("status"), out.get("status"))
    out.setdefault("priority", (index + 1) * 10)
    if isinstance(out.get("verify"), str):  # an older queue may hold one command, not a list
        out["verify"] = [out["verify"]] if out["verify"] else []
    if out["status"] == "done" and not out.get("commit"):
        out["commit"] = NO_COMMIT
        plan.todo.append(f"{label}: {out.get('id')} is done with no commit on record")
    return out


def _convert_queue(project: Project, path: Path, source: str, plan: Plan) -> None:
    data = tasks.read_raw(path)
    label = project.rel(path)
    converted = {"schemaVersion": tasks.SCHEMA_VERSION, "source": data.get("source") or source,
                 "updated": today(), "protocolVersion": tasks.PROTOCOL_VERSION, "tier": "standard",
                 **{k: v for k, v in data.items() if k not in (*OLD_TOP_LEVEL, "schemaVersion", "source",
                                                               "updated", "tasks")},
                 "tasks": [_convert_task(t, i, plan, label) for i, t in enumerate(data["tasks"])]}
    for task in converted["tasks"]:
        if task["status"] in tasks.OPEN_STATUSES:
            for key in task.get("verify", []):
                if not tasks.is_raw_command(key) and key not in project.config.commands:
                    plan.todo.append(f"{label}: {task['id']} verifies with `{key}`, not in [commands]")
    plan.done.append(f"{label}: schema {data.get('schemaVersion', 'none')} to {tasks.SCHEMA_VERSION}, "
                     f"{len(converted['tasks'])} task(s)")
    if plan.write:
        write_json(path, converted)


def _is_open_queue(path: Path) -> bool:
    return path.exists() and any(
        OLD_STATUSES.get(t.get("status"), t.get("status")) in tasks.OPEN_STATUSES
        for t in tasks.read_raw(path)["tasks"])


# --- folder-registry ----------------------------------------------------------------------------


def _import_folder_registry(project: Project, plan: Plan) -> None:
    data = json.loads(project.registry_path.read_text())
    for row in data["workstreams"]:
        folder = project.workstreams_dir / row["id"]
        path = folder / TASKS_NAME
        row.setdefault("path", project.rel(folder))
        row.setdefault("tier", "standard")
        frozen = folder / FROZEN_PROTOCOL
        if _is_open_queue(path) and frozen.exists():
            plan.done.append(f"{project.rel(frozen)}: removed, as `ws protocol` serves it now")
            if plan.write:
                frozen.unlink()
        if _is_old_queue(path):
            _convert_queue(project, path, f"{project.rel(folder)}/PLAN.md", plan)
    data.pop("statusValues", None)
    plan.done.append(f"{project.rel(project.registry_path)}: {len(data['workstreams'])} row(s)")
    if plan.write:
        write_json(project.registry_path, data)


# --- root-registry ------------------------------------------------------------------------------


def _convert_row(project: Project, row: dict) -> dict:
    status = OLD_REGISTRY_STATUSES.get(row.get("status"), row.get("status"))
    out = {"id": _slug(row["name"]), "title": row["name"], "status": status, "path": row["path"].rstrip("/"),
           "tier": "standard", "created": row.get("createdOn") or today(), "summary": "",
           "taskPrefix": "", "dependsOn": [], "notes": "", "baseCommit": None, "startedAt": None,
           "completedAt": row.get("closedOn")}
    if status == "done":
        out["closed"] = {"commit": row.get("lastCommit") or NO_COMMIT,
                         "pruned": not (project.root / row["path"] / TASKS_NAME).exists()}
    return out


def _fill_required_files(project: Project, folder: Path, source: str, plan: Plan) -> None:
    """The files this tool expects, from what the old shape keeps under other names."""
    # By listing, as on a case-insensitive disk the new name already "exists".
    names = {p.name for p in folder.iterdir()}
    old_handoff, handoff = folder / OLD_HANDOFF, folder / "session_handoff.md"
    if OLD_HANDOFF in names and handoff.name not in names:
        plan.done.append(f"{project.rel(old_handoff)}: renamed to session_handoff.md")
        if plan.write:
            old_handoff.rename(handoff)
    stubs = {"PLAN.md": f"# Plan\n\nThe design is in `{source}`.\n",
             "DECISIONS.md": "# Decisions\n\nNone recorded before this workstream was imported.\n",
             "PROGRESS.md": "# Progress\n",
             "session_handoff.md": "# Session handoff\n"}
    for name, text in stubs.items():
        path = folder / name
        if name not in names and not (name == handoff.name and OLD_HANDOFF in names):
            plan.done.append(f"{project.rel(path)}: created")
            if plan.write:
                path.write_text(text)


def _import_root_registry(project: Project, plan: Plan) -> None:
    old = project.root / REGISTRY_NAME
    rows = _old_rows(old)
    converted = []
    for row in rows:
        out = _convert_row(project, row)
        converted.append(out)
        folder = project.root / out["path"]
        path = folder / TASKS_NAME
        if path.exists():
            source = tasks.read_raw(path).get("source") or row.get("source") or f"{out['path']}/PLAN.md"
            if _is_old_queue(path):
                _convert_queue(project, path, source, plan)
            _fill_required_files(project, folder, source, plan)
        out["progress"] = (registry.compute_progress(project, out) if plan.write and path.exists() else
                           {"total": 0, "todo": 0, "in-progress": 0, "blocked": 0, "done": 0, "deferred": 0})
    existing = (json.loads(project.registry_path.read_text()) if project.registry_path.exists()
                else {"updated": today(), "workstreams": []})
    have = {w["id"] for w in existing["workstreams"]}
    existing["workstreams"] += [w for w in converted if w["id"] not in have]
    plan.done.append(f"{REGISTRY_NAME}: {len(rows)} row(s) moved to {project.rel(project.registry_path)}")
    if plan.write:
        project.registry_path.parent.mkdir(parents=True, exist_ok=True)
        write_json(project.registry_path, existing)
        old.unlink()


def run(project: Project, write: bool = False) -> Plan:
    plan = Plan(write)
    shapes = detect(project)
    if ROOT_REGISTRY in shapes:
        _import_root_registry(project, plan)
    if FOLDER_REGISTRY in shapes:
        _import_folder_registry(project, plan)
    return plan
