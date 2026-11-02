"""`ws doctor`: what is wrong with this setup, without changing anything.

Everything here reads. `--run` also runs the project's commands, whose logs go where `ws verify`
keeps its own, so the only thing that can change is what the commands themselves build.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path

from workstream import adopt, baseline, gitutil, registry, snapshot, verify
from workstream.config import CONFIG_REL, load_config
from workstream.errors import WsError
from workstream.gates import gate
from workstream.project import Project, find_root

MINIMUM_PYTHON = (3, 11)
MAX_HEALTH_SHOWN = 8


def _environment() -> list[dict]:
    python = sys.version_info[:2] >= MINIMUM_PYTHON
    return [gate("Python is new enough", python, f"{sys.version.split()[0]} is too old"),
            gate("git is installed", shutil.which("git") is not None)]


def _repository(root: Path) -> list[dict]:
    if gitutil.toplevel(root) is None:
        return [gate("this is a git repository", False, f"{root} isn't one")]
    email = gitutil.run(root, "config", "user.email").stdout.strip()
    known = bool(email or os.environ.get("GIT_AUTHOR_EMAIL"))
    return [gate("git knows who you are", known, "commits will fail: set user.email",
                 blocking=False)]


def _branches(project: Project) -> list[dict]:
    root, config = project.root, project.config
    out = [gate(f"the integration branch {config.integration} exists",
                gitutil.branch_exists(root, config.integration), "no such branch, or no commit yet")]
    if config.production != config.integration:
        out.append(gate(f"the production branch {config.production} exists",
                        gitutil.branch_exists(root, config.production), "no such branch",
                        blocking=False))
    committed = gitutil.run(root, "cat-file", "-e",
                            f"{config.integration}:{CONFIG_REL}").returncode == 0
    out.append(gate("the config is committed", committed,
                    f"a worktree wouldn't have it: commit {CONFIG_REL}", blocking=False))
    return out


def _commands(project: Project) -> list[dict]:
    config = project.config
    missing = {key: why for key, command in config.commands.items()
               if (why := adopt.tool_problem(command, project.root))}
    out = [gate("there are commands to verify with", bool(config.commands),
                "tasks can't name anything: add them under [commands]", blocking=False),
           gate("each command's tool is here", not missing,
                "; ".join(f"{k}: {w}" for k, w in missing.items()), blocking=False)]
    stray = sorted({k for keys in config.adequacy.values() for k in keys} - set(config.commands))
    out.append(gate("[adequacy] names only real commands", not stray,
                    f"nothing is demanded for: {', '.join(stray)}", blocking=False))
    orphaned = sorted(set(config.baseline_parsers) - set(config.commands))
    out.append(gate("[baseline] names only real commands", not orphaned,
                    f"no command for: {', '.join(orphaned)}", blocking=False))
    return out


def _workstreams(project: Project) -> list[dict]:
    if not project.registry_path.exists():
        return [gate("the registry exists", False, "run `ws init`")]
    try:
        errors, _, count = registry.validate_all(project)
        health = snapshot.build_snapshot(project, None, snapshot.DEFAULT_STALE_HOURS)["health"]
    except WsError as e:
        return [gate("the registry can be read", False, str(e))]
    out = [gate(f"{count} workstream(s) are valid", not errors, "; ".join(errors[:MAX_HEALTH_SHOWN]))]
    # Validate already spoke for these; a file a task will create is expected.
    other = [f["message"] for f in health if f["kind"] != "invalid"]
    out.append(gate("nothing is left over", not other,
                    "; ".join(other[:MAX_HEALTH_SHOWN]), blocking=False))
    return out


def _run_commands(project: Project, ws: dict | None) -> list[dict]:
    """Each command against its baseline: is this tree any good to start from?"""
    folder = project.folder(ws) if ws else baseline.project_folder(project)
    record = baseline.load_for(project, folder)
    directory = verify.runs_dir(project, "_doctor", ws["id"] if ws else "project")
    directory.mkdir(parents=True, exist_ok=True)
    out = []
    for key, command in project.config.commands.items():
        entry = project.config.baseline_parsers.get(key, {"parser": baseline.EXIT_CODE})
        known = baseline.known_findings(record, key)
        result = verify.run_one(project, key, command, entry, known, directory, "doctor")
        ok = result["verdict"] != baseline.FAIL
        detail = result.get("reason", "") + (f"; log: {result['log']}" if result.get("log") else "")
        out.append(gate(f"{key} passes against the baseline", ok, detail))
    return out


def doctor(start: Path, *, run: bool = False, ws_id: str | None = None) -> list[dict]:
    """Every check, in the order they build on each other. It stops where the next one couldn't
    mean anything: with no config, nothing can be said about its commands."""
    found = _environment()
    root = find_root(start)
    if root is None:
        return found + [gate("this project is set up", False, f"no {CONFIG_REL}: run `ws init`")]
    found += _repository(root)
    try:
        config = load_config(root / CONFIG_REL)
    except WsError as e:
        return found + [gate("the config parses", False, str(e))]
    project = Project(root=root, config=config)
    found += [gate("the config parses", True)]
    found += _branches(project) + _commands(project) + _workstreams(project)
    if run:
        ws = registry.find(registry.load(project), ws_id) if ws_id else None
        found += _run_commands(project, ws)
    return found

