"""`ws adapt <agent>`: write what an agent reads, from the one source.

Each agent is a data file under assets/adapters/, so this module knows none of them. What it writes
are copies, and copies drift: that is how a protocol copied into each workstream ended up out of
date nearly everywhere. So there is one copy per repository, every file's hash goes in
.workstream/adapters.json, `--check` reports anything stale or edited, and `ws doctor` warns.

A file someone edited by hand is never overwritten without --force. Text in a file the agent shares
with its owner goes in a marked block, and everything outside the block stays as it was.
"""

from __future__ import annotations

import json
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from workstream import __version__, protocol
from workstream.errors import Refused, WsError
from workstream.fsutil import sha256, write_json
from workstream.project import ASSETS_DIR, Project

ADAPTERS_DIR = ASSETS_DIR / "adapters"
WORKER_FILE = ASSETS_DIR / "worker_agent.md"
MANIFEST_REL = ".workstream/adapters.json"
# These load into every session, so they stay short. `ws adapt` is what regenerates the block.
BLOCK_START = "<!-- ws:start -->"
BLOCK_END = "<!-- ws:end -->"
BLOCK_RE = re.compile(re.escape(BLOCK_START) + r".*?" + re.escape(BLOCK_END), re.DOTALL)
CURRENT, STALE, EDITED, MISSING = "current", "stale", "edited", "missing"


@dataclass(frozen=True)
class Adapter:
    name: str
    label: str
    instructions: str
    skill: str
    raw: dict = field(default_factory=dict)


def names() -> list[str]:
    return sorted(p.stem for p in ADAPTERS_DIR.glob("*.toml"))


def load(name: str) -> Adapter:
    path = ADAPTERS_DIR / f"{name}.toml"
    if not path.is_file():
        raise WsError(f"no adapter for {name!r} (there is: {', '.join(names())})")
    with path.open("rb") as f:
        raw = tomllib.load(f)
    return Adapter(raw["name"], raw["label"], raw["instructions"], raw["skill"], raw)


def skill_text(adapter: Adapter, name: str, worker_name: str | None = None) -> str:
    """One skill as this agent gets it: the shared text and this agent's notes on it."""
    text = protocol.skill_text(name)
    note = adapter.raw.get("notes", {}).get(name, "").strip()
    if not note:
        return text
    note = note.replace("{worker}", worker_name or adapter.raw["worker"]["name"])
    return text.rstrip() + f"\n\n## On {adapter.label}\n\n{note}\n"


def worker_text(adapter: Adapter, name: str | None = None) -> str:
    """The worker agent's file. Its body stands alone, as a worker may not see the project's
    instructions, and its tools are listed so it can't start workers of its own."""
    worker = adapter.raw["worker"]
    return (f"---\nname: {name or worker['name']}\ndescription: {worker['description']}\n"
            f"{worker['frontmatter']}\n---\n\n{WORKER_FILE.read_text().strip()}\n")


def always_on_text(adapter: Adapter) -> str:
    """What every session carries once this agent is set up: the pointer, and each skill's and the
    worker's name and description."""
    lines = [pointer_block()]
    lines += [f"{name}: {protocol.description(protocol.skill_text(name))}"
              for name in protocol.skill_names()]
    worker = adapter.raw["worker"]
    lines.append(f"{worker['name']}: {worker['description']}")
    return "\n".join(lines)


def pointer_block() -> str:
    return f"{BLOCK_START}\n{protocol.POINTER_FILE.read_text().strip()}\n{BLOCK_END}"


def with_block(existing: str, block: str) -> str:
    """The file with this block in place: replaced where it is, or added at the end."""
    if BLOCK_RE.search(existing):
        return BLOCK_RE.sub(lambda _: block, existing)
    return (existing.rstrip() + "\n\n" if existing.strip() else "") + block + "\n"


def generated(adapter: Adapter) -> dict[str, str]:
    """{relative path: content} for every file this adapter owns outright."""
    files = {adapter.skill.format(name=name): skill_text(adapter, name)
             for name in protocol.skill_names()}
    files[adapter.raw["worker"]["path"]] = worker_text(adapter)
    return files


def read_settings(path: Path) -> dict:
    """A settings file that belongs to its owner. Refuses rather than overwrite one it can't read."""
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise Refused(f"{path.name} isn't valid JSON, and it isn't ours to overwrite: {e}") from None
    if not isinstance(data, dict):
        raise Refused(f"{path.name} isn't a JSON object, and it isn't ours to overwrite")
    return data


def merged_permissions(data: dict, allow: list[str]) -> dict:
    """These rules added to the settings, in place. Everything else stays as it was."""
    permissions = data.get("permissions")
    if permissions is None:
        permissions = {}
    if not isinstance(permissions, dict) or not isinstance(permissions.get("allow", []), list):
        raise Refused("the settings' `permissions.allow` isn't a list; add these by hand: "
                      + ", ".join(allow))
    existing = permissions.get("allow", [])
    return {**data, "permissions": {**permissions,
                                    "allow": existing + [a for a in allow if a not in existing]}}


def _settings_current(project: Project, adapter: Adapter) -> bool:
    settings = adapter.raw.get("settings")
    if not settings:
        return True
    data = read_settings(project.root / settings["path"])
    allowed = (data.get("permissions") or {}).get("allow") or []
    return all(rule in allowed for rule in settings.get("allow", []))


def _manifest_path(project: Project) -> Path:
    return project.root / MANIFEST_REL


def load_manifest(project: Project) -> dict:
    path = _manifest_path(project)
    if not path.exists():
        return {"schemaVersion": 1, "adapters": {}}
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError as e:
        raise WsError(f"{MANIFEST_REL}: not valid JSON: {e}") from None
    if not isinstance(data, dict) or not isinstance(data.get("adapters"), dict):
        raise WsError(f"{MANIFEST_REL}: not a manifest")
    return data


def _hash(text: str) -> str:
    return sha256(text.encode())


def file_states(project: Project, adapter: Adapter) -> dict[str, str]:
    """{path: state} for this adapter's files, and the block: is each what this `ws` would write?
    A file differing from what was recorded was edited by hand; one matching the record but not the
    current text just comes from an older `ws`."""
    recorded = load_manifest(project)["adapters"].get(adapter.name, {}).get("files", {})
    states = {}
    for rel, content in generated(adapter).items():
        path = project.root / rel
        if not path.exists():
            states[rel] = MISSING
            continue
        actual = _hash(path.read_text())
        if actual == _hash(content):
            states[rel] = CURRENT
        elif rel in recorded and actual != recorded[rel]:
            states[rel] = EDITED
        elif rel not in recorded:
            states[rel] = EDITED  # it was there first, and it isn't ours
        else:
            states[rel] = STALE
    instructions = project.root / adapter.instructions
    text = instructions.read_text() if instructions.exists() else ""
    states[adapter.instructions] = (CURRENT if pointer_block() in text
                                    else STALE if BLOCK_RE.search(text) else MISSING)
    settings = adapter.raw.get("settings")
    if settings:
        states[settings["path"]] = CURRENT if _settings_current(project, adapter) else MISSING
    return states


def adapted(project: Project) -> list[str]:
    """The agents this repository has been set up for."""
    return sorted(load_manifest(project)["adapters"])


def drift(project: Project) -> dict[str, list[str]]:
    """{agent: paths not current}, for each adapted agent. An agent this `ws` doesn't know is
    reported rather than crashing, since a manifest can outlive an adapter."""
    out = {}
    for name in adapted(project):
        try:
            states = file_states(project, load(name))
        except WsError:
            out[name] = ["(this ws has no such adapter)"]
            continue
        wrong = [f"{rel} ({state})" for rel, state in states.items() if state != CURRENT]
        if wrong:
            out[name] = wrong
    return out


def adapt(project: Project, name: str, *, force: bool = False) -> dict[str, list[str]]:
    """Write this agent's files. {"wrote": [...], "same": [...]}. All or nothing on edited files:
    it refuses before writing anything, so a refusal leaves no half-updated set."""
    adapter = load(name)
    states = file_states(project, adapter)
    edited = [rel for rel, state in states.items() if state == EDITED]
    if edited and not force:
        raise Refused("edited by hand, or not ours (--force overwrites):\n"
                      + "\n".join(f"  {rel}" for rel in edited))
    wrote, same = [], []
    hashes = {}
    for rel, content in generated(adapter).items():
        hashes[rel] = _hash(content)
        if states[rel] == CURRENT:
            same.append(rel)
            continue
        path = project.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        wrote.append(rel)
    instructions = project.root / adapter.instructions
    if states[adapter.instructions] == CURRENT:
        same.append(adapter.instructions)
    else:
        instructions.parent.mkdir(parents=True, exist_ok=True)
        existing = instructions.read_text() if instructions.exists() else ""
        instructions.write_text(with_block(existing, pointer_block()))
        wrote.append(adapter.instructions)
    settings = adapter.raw.get("settings")
    if settings:
        if states[settings["path"]] == CURRENT:
            same.append(settings["path"])
        else:
            path = project.root / settings["path"]
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json(path, merged_permissions(read_settings(path), settings.get("allow", [])))
            wrote.append(settings["path"])
    manifest = load_manifest(project)
    manifest["adapters"][name] = {"toolVersion": __version__, "files": hashes}
    path = _manifest_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, manifest)
    return {"wrote": wrote, "same": same}


def write_plugin(name: str, out: Path) -> list[str]:
    """This agent's plugin form, for an agent that has one: the same text, with names as a plugin
    namespaces them. Nothing here is tracked: a plugin is rebuilt, not edited."""
    adapter = load(name)
    plugin = adapter.raw.get("plugin")
    if plugin is None:
        raise WsError(f"{name} has no plugin form; `ws adapt {name}` sets up the project")
    worker_name = plugin["worker_name"]
    files = {plugin["skill"].format(name=skill): skill_text(adapter, skill, worker_name)
             for skill in protocol.skill_names()}
    files[plugin["worker"]] = worker_text(adapter, adapter.raw["worker"]["name"])
    files[plugin["manifest"]] = json.dumps(
        {"name": plugin["name"], "version": __version__, "description": plugin["description"]},
        indent=2) + "\n"
    for rel, content in files.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return sorted(files)
