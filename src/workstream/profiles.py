"""Stack profiles: data that says what a kind of project can probably run.

Each is a file under assets/profiles/. This module knows no stack: it reads markers, checks
generic conditions and lists candidates, so adding a stack means adding a file. A candidate is
only a proposal, because `ws init` runs it before writing it down.

    name = "..."
    priority = 20          # lower wins when a repo matches several: most specific first
    markers = ["file that identifies this stack"]

    [[command]]            # tried in file order for each key; the first that works wins
    key = "test"
    run = "the command"
    if_files = ["every one of these exists"]
    if_regex = ["file", "pattern found in it"]

    [adequacy]             # as in the config
    [baseline.<key>]       # as in the config
    [worktree]             # as in the config
"""

from __future__ import annotations

import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from workstream.errors import WsError
from workstream.project import ASSETS_DIR

PROFILES_DIR = ASSETS_DIR / "profiles"
GENERIC = "generic"


@dataclass(frozen=True)
class Profile:
    name: str
    priority: int = 100
    markers: tuple[str, ...] = ()
    commands: tuple[dict, ...] = ()
    adequacy: dict[str, list[str]] = field(default_factory=dict)
    baseline: dict[str, dict] = field(default_factory=dict)
    worktree_setup: tuple[str, ...] = ()


def names() -> list[str]:
    return sorted(p.stem for p in PROFILES_DIR.glob("*.toml"))


def load(name: str) -> Profile:
    path = PROFILES_DIR / f"{name}.toml"
    if not path.is_file():
        raise WsError(f"no profile {name!r} (there is: {', '.join(names())})")
    with path.open("rb") as f:
        raw = tomllib.load(f)
    return Profile(name=raw["name"], priority=raw.get("priority", 100), markers=tuple(raw.get("markers", ())),
                   commands=tuple(raw.get("command", ())), adequacy=dict(raw.get("adequacy", {})),
                   baseline=dict(raw.get("baseline", {})),
                   worktree_setup=tuple(raw.get("worktree", {}).get("setup", ())))


def detect(root: Path) -> tuple[Profile, list[str]]:
    """The profile this repository matches, and any others it also matches, for the caller to
    mention. Only the repository's top level counts: a marker further down is a sub-project."""
    known = sorted((load(name) for name in names()), key=lambda p: p.priority)
    matches = [p for p in known if any((root / marker).exists() for marker in p.markers)]
    return (matches[0] if matches else load(GENERIC)), [p.name for p in matches[1:]]


def _holds(command: dict, root: Path) -> bool:
    for name in command.get("if_files", ()):
        if not (root / name).exists():
            return False
    condition = command.get("if_regex")
    if condition:
        path = root / condition[0]
        if not path.is_file() or re.search(condition[1], path.read_text(errors="replace")) is None:
            return False
    return True


def candidates(profile: Profile, root: Path) -> dict[str, list[str]]:
    """{key: commands worth trying here, best first}. A key with nothing left isn't listed."""
    found: dict[str, list[str]] = {}
    for command in profile.commands:
        if _holds(command, root) and command["run"] not in found.get(command["key"], []):
            found.setdefault(command["key"], []).append(command["run"])
    return found
