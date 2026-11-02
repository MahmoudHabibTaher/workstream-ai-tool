"""`ws init` on a real project: find out what works by running it.

A profile only proposes. Each key's candidates run in order on the clean tree until one works,
and only what was seen to work becomes an active key. Findings a parser can read are recorded as
known, since a repo's existing lint debt shouldn't stop adoption. Anything else that fails stays
in the config as a comment with its reason: a broken build should be seen, not dropped, and an
active key that can't pass would block every task naming it.
"""

from __future__ import annotations

import shlex
import shutil
import time
from pathlib import Path

from workstream import baseline, gitutil, profiles, registry, verify
from workstream.config import CONFIG_REL, Config, load_config, render_default
from workstream.errors import Refused
from workstream.project import Project

NOT_RUN = "not run (--no-run): `ws init` verifies a command before making it active"


def tool_problem(command: str, root: Path) -> str:
    """Why this command can't start here, without starting it. "" if it might."""
    try:
        words = shlex.split(command)
    except ValueError:
        return ""
    if not words:
        return "an empty command"
    tool = words[0]
    if "/" in tool:
        return "" if (root / tool).exists() else f"{tool} doesn't exist"
    return "" if shutil.which(tool) else f"{tool} isn't on PATH"


def _tracked_changes(root: Path) -> str:
    """Every edit to a tracked file. A new file isn't one: a first build may well write a lockfile,
    which is no reason to think it rewrites sources."""
    return gitutil.run(root, "diff", "--no-ext-diff").stdout


def _untracked(root: Path) -> set[str]:
    proc = gitutil.run(root, "ls-files", "--others", "--exclude-standard")
    return set(proc.stdout.splitlines())


def _try_one(project: Project, key: str, command: str, entry: dict) -> tuple[str, list[str]]:
    """Run one candidate. ("", its findings) if it works, else (why not, [])."""
    root = project.root
    problem = tool_problem(command, root)
    if problem:
        return problem, []
    before = _tracked_changes(root)
    log_path = verify.runs_dir(project, "_init", key) / "candidate.log"
    started = time.time()
    code, _ = verify.run_command(command, root, log_path, project.config.verify_timeout)
    if code is None:
        return "timed out on a clean tree", []
    if _tracked_changes(root) != before:
        return "it changes tracked files, so it can't check them; review what it left", []
    found, parser_problem = baseline.read_findings(entry, verify.read_log(log_path), root, started)
    if parser_problem:
        return f"exit {code}, and {parser_problem}", []
    if found:  # whatever the exit code: a tool that always exits 0 still reports
        return "", found
    if code != 0:
        return f"exit {code} on a clean tree, with nothing a parser could read", []
    return "", []


def try_commands(project: Project, profile: profiles.Profile, candidates: dict[str, list[str]],
                 say=lambda line: None) -> tuple[dict, dict, dict]:
    """(active {key: command}, unverified {key: (command, why)}, known {key: findings})."""
    active: dict[str, str] = {}
    unverified: dict[str, tuple[str, str]] = {}
    known: dict[str, list[str]] = {}
    for key, commands in candidates.items():
        entry = profile.baseline.get(key, {"parser": baseline.EXIT_CODE})
        failures: list[tuple[str, str]] = []
        for command in commands:
            say(f"  trying {key}: {command}")
            why, found = _try_one(project, key, command, entry)
            if not why:
                active[key] = command
                if found:
                    known[key] = sorted(found)
                break
            failures.append((command, why))
        else:
            # What ran and failed says more than a tool that isn't installed.
            ran = [f for f in failures if not tool_problem(f[0], project.root)]
            unverified[key] = (ran or failures)[0]
    return active, unverified, known


def _left_behind(before: set[str], root: Path) -> list[str]:
    """New files the commands wrote and git would pick up. A later `git add -A` would commit them,
    and `ws verify` would see the code change, so someone should decide."""
    return sorted(_untracked(root) - before)


def _dirty(root: Path) -> list[str]:
    return gitutil.run(root, "status", "--porcelain", "--untracked-files=no").stdout.splitlines()


def adopt(root: Path, integration: str | None, production: str | None, profile_name: str | None,
          *, run: bool = True, timeout: int | None = None, say=lambda line: None) -> dict:
    """Write a config for this repository, and an empty registry. {project, created, profile,
    others, active, unverified, known, left}. An existing config is never touched: to start again,
    delete it. Refuses uncommitted changes before running anything, as findings from work in
    progress would be recorded as known for good."""
    root = Path(root).resolve()
    config_path = root / CONFIG_REL
    branch = integration or gitutil.default_branch(root)
    config = Config(integration=branch, production=production or branch,
                    verify_timeout=timeout or Config.verify_timeout)
    project = Project(root=root, config=config)
    created: list[str] = []
    out = {"created": created, "profile": None, "others": [], "active": {}, "unverified": {},
           "known": {}, "left": []}
    if config_path.exists():
        project = Project(root=root, config=load_config(config_path))
        _ensure_registry(project, created)
        return {**out, "project": project}

    if profile_name:
        profile, others = profiles.load(profile_name), []
    else:
        profile, others = profiles.detect(root)
    candidates = profiles.candidates(profile, root)
    if candidates and run:
        dirty = _dirty(root)
        if dirty:
            raise Refused("`ws init` runs commands on a clean tree; commit or stash first "
                          "(--no-run writes them unverified):\n" + "\n".join(dirty[:10]))
    _ensure_registry(project, created)
    untracked = _untracked(root)
    left: list[str] = []
    if run:
        active, unverified, known = try_commands(project, profile, candidates, say)
        left = _left_behind(untracked, root)
    else:
        active, known = {}, {}
        unverified = {key: (commands[0], NOT_RUN) for key, commands in candidates.items()}

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(render_default(
        branch, production, commands=active, unverified=unverified, adequacy=profile.adequacy,
        baseline=profile.baseline, worktree_setup=profile.worktree_setup))
    created.insert(0, CONFIG_REL)
    project = Project(root=root, config=load_config(config_path))
    if known:
        recorded = {key: {"parser": profile.baseline[key].get("parser"), "command": active[key],
                          "findings": found} for key, found in known.items()}
        created.append(project.rel(baseline.write(project, baseline.project_folder(project),
                                                  recorded)))
    return {**out, "project": project, "profile": profile.name, "others": others, "active": active,
            "unverified": unverified, "known": known, "left": left}


def _ensure_registry(project: Project, created: list[str]) -> None:
    if not project.registry_path.exists():
        project.workstreams_dir.mkdir(parents=True, exist_ok=True)
        registry.save(project, registry.new_registry())
        created.append(project.rel(project.registry_path))
