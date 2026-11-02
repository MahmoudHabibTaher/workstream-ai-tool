"""The project config, .workstream/config.toml: every fact about a project lives here.

Nothing else in this package names a branch, a build tool or a stack. A missing section
reads as the defaults below, and an unknown section or an ill-typed value is an error, so a
typo can't silently turn a rule off.

Example:

    schema = 1
    [paths]
    workstreams = "workstreams"
    [branches]
    integration = "main"
    production = "main"
    task = "task/{slug}"
    merge = "no-ff"                # no-ff | squash | pr
    [commands]                     # the keys a task's `verify` names
    test = "make test"
    [adequacy]                     # task kind -> the keys it must verify with
    behaviour = ["test"]
    [requires]
    values = ["live-server", "browser", "device", "external-network", "user"]
    foreground = ["live-server", "browser", "device", "user"]
    [worktree]
    dir = ".workstream/worktrees"
    setup = []                     # run in each new worktree; {main} and {worktree} expand
    [verify]
    timeout_seconds = 3600
    tail_lines = 15
    [baseline.lint]                # how `ws verify` tells new findings from known ones
    parser = "regex"               # regex | sarif | junit | exit-code
    pattern = "^(?P<file>\\S+):\\d+: (?P<message>.*)$"   # named groups fingerprint a finding
    [baseline.test]
    parser = "junit"
    report = "build/reports/*.xml" # sarif and junit read this, relative to the project root
    [parallel]
    max_workers = 3
    [release]
    mode = "none"                  # none | runbook
    runbook = ""
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from workstream.errors import WsError

CONFIG_REL = ".workstream/config.toml"
SCHEMA = 1
MERGE_VALUES = ("no-ff", "squash", "pr")
RELEASE_MODES = ("none", "runbook")
BASELINE_PARSERS = ("regex", "sarif", "junit", "exit-code")
DEFAULT_REQUIRES = ("live-server", "browser", "device", "external-network", "user")
# Any of these in `requires` means the task can't run as a background worker.
DEFAULT_FOREGROUND = ("live-server", "browser", "device", "user")
SECTIONS = {"schema", "paths", "branches", "commands", "adequacy", "requires", "worktree",
            "verify", "parallel", "release", "baseline"}
BASELINE_KEYS = {"parser", "pattern", "report"}


@dataclass(frozen=True)
class Config:
    workstreams_dir: str = "workstreams"
    integration: str = "main"
    production: str = "main"
    task_branch: str = "task/{slug}"
    merge: str = "no-ff"
    commands: dict[str, str] = field(default_factory=dict)
    adequacy: dict[str, list[str]] = field(default_factory=dict)
    requires_values: tuple[str, ...] = DEFAULT_REQUIRES
    foreground_requires: tuple[str, ...] = DEFAULT_FOREGROUND
    worktree_setup: tuple[str, ...] = ()
    worktree_dir: str = ".workstream/worktrees"
    verify_timeout: int = 3600
    tail_lines: int = 15
    max_workers: int = 3
    release_mode: str = "none"
    release_runbook: str = ""
    baseline_parsers: dict[str, dict] = field(default_factory=dict)

    def branch_for(self, task_id: str) -> str:
        """The branch a task works on, from the configured pattern."""
        return self.task_branch.replace("{slug}", task_id.lower())

    def task_branch_glob(self) -> str:
        """The pattern as a `git branch --list` glob: every task branch this repo would have."""
        return self.task_branch.replace("{slug}", "*")


def _section(raw: dict, name: str) -> dict:
    section = raw.get(name, {})
    if not isinstance(section, dict):
        raise WsError(f"{CONFIG_REL}: [{name}] must be a table")
    return section


def _str(section: dict, name: str, key: str, default: str) -> str:
    value = section.get(key, default)
    if not isinstance(value, str):
        raise WsError(f"{CONFIG_REL}: {name}.{key} must be a string, got {value!r}")
    return value


def _str_list(section: dict, name: str, key: str, default: tuple[str, ...]) -> tuple[str, ...]:
    value = section.get(key, list(default))
    if not isinstance(value, list) or not all(isinstance(v, str) for v in value):
        raise WsError(f"{CONFIG_REL}: {name}.{key} must be a list of strings, got {value!r}")
    return tuple(value)


def _choice(value: str, name: str, allowed: tuple[str, ...]) -> str:
    if value not in allowed:
        raise WsError(f"{CONFIG_REL}: {name} must be one of {', '.join(allowed)}, got {value!r}")
    return value


def _positive_int(section: dict, name: str, key: str, default: int) -> int:
    value = section.get(key, default)
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise WsError(f"{CONFIG_REL}: {name}.{key} must be a positive integer")
    return value


def _baseline_entry(key: str, entry: object) -> dict:
    """One [baseline.<key>] table, with what its parser needs checked now: a broken regex
    found at the first `ws verify` would read as a failing command."""
    if not isinstance(entry, dict):
        raise WsError(f"{CONFIG_REL}: baseline.{key} must be a table")
    unknown = sorted(set(entry) - BASELINE_KEYS)
    if unknown:
        raise WsError(f"{CONFIG_REL}: baseline.{key}: unknown key(s): {', '.join(unknown)}")
    parser = _choice(_str(entry, f"baseline.{key}", "parser", "exit-code"),
                     f"baseline.{key}.parser", BASELINE_PARSERS)
    if parser == "regex":
        pattern = _str(entry, f"baseline.{key}", "pattern", "")
        if not pattern:
            raise WsError(f"{CONFIG_REL}: baseline.{key}: the regex parser needs a pattern")
        try:
            re.compile(pattern)
        except re.error as e:
            raise WsError(f"{CONFIG_REL}: baseline.{key}.pattern: {e}") from None
    if parser in ("sarif", "junit"):
        report = _str(entry, f"baseline.{key}", "report", "")
        if not report or report.startswith("/"):
            raise WsError(f"{CONFIG_REL}: baseline.{key}: the {parser} parser needs a report "
                          "path relative to the project root")
    return {"parser": parser, **{k: entry[k] for k in ("pattern", "report") if k in entry}}


def parse_config(raw: dict) -> Config:
    """A Config from parsed TOML. Raises WsError naming the first bad key."""
    unknown = sorted(set(raw) - SECTIONS)
    if unknown:
        raise WsError(f"{CONFIG_REL}: unknown key(s): {', '.join(unknown)}")
    schema = raw.get("schema", SCHEMA)
    if schema != SCHEMA:
        raise WsError(f"{CONFIG_REL}: schema {schema!r} is not supported (this ws reads {SCHEMA})")

    branches = _section(raw, "branches")
    integration = _str(branches, "branches", "integration", "main")
    task_branch = _str(branches, "branches", "task", "task/{slug}")
    if "{slug}" not in task_branch:
        raise WsError(f"{CONFIG_REL}: branches.task must contain {{slug}}, got {task_branch!r}")

    commands = _section(raw, "commands")
    for key, value in commands.items():
        if not isinstance(value, str) or not value.strip():
            raise WsError(f"{CONFIG_REL}: commands.{key} must be a non-empty string")

    adequacy = {}
    for kind in _section(raw, "adequacy"):
        adequacy[kind] = list(_str_list(raw["adequacy"], "adequacy", kind, ()))

    requires = _section(raw, "requires")
    values = _str_list(requires, "requires", "values", DEFAULT_REQUIRES)
    foreground = _str_list(requires, "requires", "foreground", DEFAULT_FOREGROUND)
    stray = sorted(set(foreground) - set(values))
    if stray:
        raise WsError(f"{CONFIG_REL}: requires.foreground names unknown value(s): "
                      f"{', '.join(stray)}")

    release = _section(raw, "release")
    baseline = {key: _baseline_entry(key, entry)
                for key, entry in _section(raw, "baseline").items()}
    worktree = _section(raw, "worktree")
    verify = _section(raw, "verify")

    return Config(
        workstreams_dir=_str(_section(raw, "paths"), "paths", "workstreams", "workstreams"),
        integration=integration,
        production=_str(branches, "branches", "production", integration),
        task_branch=task_branch,
        merge=_choice(_str(branches, "branches", "merge", "no-ff"), "branches.merge",
                      MERGE_VALUES),
        commands=dict(commands),
        adequacy=adequacy,
        requires_values=values,
        foreground_requires=foreground,
        worktree_setup=_str_list(worktree, "worktree", "setup", ()),
        worktree_dir=_str(worktree, "worktree", "dir", ".workstream/worktrees"),
        verify_timeout=_positive_int(verify, "verify", "timeout_seconds", 3600),
        tail_lines=_positive_int(verify, "verify", "tail_lines", 15),
        max_workers=_positive_int(_section(raw, "parallel"), "parallel", "max_workers", 3),
        release_mode=_choice(_str(release, "release", "mode", "none"), "release.mode",
                             RELEASE_MODES),
        release_runbook=_str(release, "release", "runbook", ""),
        baseline_parsers=baseline,
    )


def load_config(path: Path) -> Config:
    try:
        with path.open("rb") as f:
            return parse_config(tomllib.load(f))
    except tomllib.TOMLDecodeError as e:
        raise WsError(f"{CONFIG_REL}: {e}") from None


def render_default(integration: str, production: str | None = None) -> str:
    """The file `ws init` writes for a project with nothing configured yet."""
    return f"""# Project facts for the `ws` CLI. Every key is optional.
schema = {SCHEMA}

[branches]
integration = "{integration}"
production = "{production or integration}"
task = "task/{{slug}}"
merge = "no-ff"

# The commands a task's `verify` names. Add your project's own, for example:
#   test = "make test"
#   lint = "make lint"
[commands]

# Task kind -> the command keys it must verify with, enforced by `ws validate`:
#   behaviour = ["test"]
[adequacy]

[parallel]
max_workers = 3

[release]
mode = "none"
"""
