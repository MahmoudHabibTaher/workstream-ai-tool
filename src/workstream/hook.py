"""`ws hook pre-edit`: an agent's file edit, checked before it happens.

The gates in `ws settle` catch a worker that writes a tracking file, but only after the work is
done. This says no at the moment of the edit, and says which command to use.

It can stop all work if it goes wrong: one agent treats any crash or non-zero exit as a denial. So
every failure of its own means "allow", and only a real decision denies. It sees file tools only.
A shell redirect gets past it, and `ws settle` catches that.

    --format exit-code   exit 2 with the reason on stderr
    --format json        exit 0 with {"permissionDecision": "deny", ...} on stdout
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from workstream import registry
from workstream.baseline import FILE_NAME as BASELINE_NAME
from workstream.baseline import PROJECT_DIR
from workstream.config import CONFIG_REL, load_config
from workstream.errors import WsError
from workstream.handoff import FILE_NAME as HANDOFF_NAME
from workstream.project import TASKS_NAME, Project, find_root

EXIT_CODE, JSON = "exit-code", "json"
FORMATS = (EXIT_CODE, JSON)
PLAN_NAME = "PLAN.md"
PLACEHOLDER = "{{"
PATCH_FILE_RE = re.compile(r"^\*\*\* (?:Update|Add|Delete) File: (.+?)\s*$", re.MULTILINE)
PATH_KEYS = ("file_path", "path", "filePath", "notebook_path")
# In a workstream's folder: who writes each file instead. Acceptance naming one of them gets a
# warning too (`tasks.tracking_file_warnings`), so this is the one list of tracking files.
WRITERS = {
    TASKS_NAME: "the queue is written by `ws` (`ws add`, `ws update`, `ws claim`, `ws settle`)",
    BASELINE_NAME: "the baseline is written by `ws baseline record`",
    "DECISIONS.md": "decisions are numbered by `ws`: propose one in your evidence, or `ws decide`",
    "PROGRESS.md": "the progress log is written by `ws settle`",
    HANDOFF_NAME: "the handoff is written by `ws settle` and `ws handoff --note`",
}


def tool_arguments(payload: dict) -> dict | str:
    """The tool's arguments, under whichever name this agent sends them."""
    for key in ("tool_input", "toolArgs"):
        value = payload.get(key)
        if isinstance(value, str):
            try:
                value = json.loads(value)
            except json.JSONDecodeError:
                return value  # a patch can arrive as bare text
        if isinstance(value, dict):
            return value
    return {}


def paths_in(payload: dict) -> list[str]:
    """Every file this call would touch, from a plain path or from inside a patch."""
    arguments = tool_arguments(payload)
    if isinstance(arguments, str):
        return PATCH_FILE_RE.findall(arguments)
    found = [arguments[k] for k in PATH_KEYS if isinstance(arguments.get(k), str)]
    for value in arguments.values():
        if isinstance(value, str):
            found += PATCH_FILE_RE.findall(value)
    return found


def _writer_of(project: Project, rel: str, name: str, resolved: Path) -> str | None:
    """Who writes this file instead, or None if an agent may. A worker's own evidence is fine."""
    if rel == project.rel(project.registry_path):
        return "the registry is written by `ws` (`ws new`, `ws sync`, `ws settle`)"
    if rel == f"{PROJECT_DIR}/{BASELINE_NAME}":
        return WRITERS[BASELINE_NAME]
    for ws in registry.load(project)["workstreams"]:
        folder = project.rel(project.folder(ws))
        if rel != f"{folder}/{name}":
            continue
        if name in WRITERS:
            return WRITERS[name]
        if name == PLAN_NAME and resolved.exists() and PLACEHOLDER not in resolved.read_text():
            return "the plan is immutable once approved: record a change with `ws decide`"
    return None


def denial(path: str, cwd: Path) -> str | None:
    """Why this edit shouldn't happen, or None. Anything it can't work out is not a reason."""
    target = (cwd / path).resolve()
    root = find_root(target.parent)
    if root is None:
        return None
    project = Project(root=root, config=load_config(root / CONFIG_REL))
    try:
        rel = str(target.relative_to(root))
    except ValueError:
        return None
    writer = _writer_of(project, rel, target.name, target)
    return f"{rel}: {writer}" if writer else None


def decide(raw: str) -> str | None:
    """The reason to deny this call, or None. Never raises: a bad payload allows."""
    try:
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            return None
        cwd = Path(payload.get("cwd") or ".")
        for path in paths_in(payload):
            reason = denial(path, cwd)
            if reason:
                return reason
    except (ValueError, OSError, WsError, TypeError, KeyError):
        return None
    return None
