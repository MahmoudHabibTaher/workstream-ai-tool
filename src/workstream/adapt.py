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
import shlex
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from workstream import __version__, protocol
from workstream.errors import Refused, WsError
from workstream.fsutil import sha256, write_json
from workstream.project import ASSETS_DIR, Project

ADAPTERS_DIR = ASSETS_DIR / "adapters"
WORKER_FILE = ASSETS_DIR / "worker_agent.md"
MAX_RULE_WORDS = 3
NOT_A_RULE = {"cd", "true", "false", "echo", "exit"}
# A rule from a project's commands stays as far from these as the adapter's own list does.
NEVER_ALLOWED = {"push", "publish", "deploy", "release"}
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


def generated(adapter: Adapter, hook: bool = False) -> dict[str, str]:
    """{relative path: content} for every file this adapter owns outright."""
    files = {adapter.skill.format(name=name): skill_text(adapter, name)
             for name in protocol.skill_names()}
    files[adapter.raw["worker"]["path"]] = worker_text(adapter)
    if hook and "file" in adapter.raw.get("hook", {}):
        files[adapter.raw["hook"]["file"]] = adapter.raw["hook"]["file_content"]
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


def _prefixes(part: str) -> list[str]:
    """What identifies one shell command: its tool and subcommand, without their flags. A rule for
    the tool alone would allow everything it does. An environment prefix gives both forms, as an
    agent matches it literally."""
    try:
        words = shlex.split(part)
    except ValueError:
        return []
    env = [w for w in words if re.match(r"\w+=", w)]
    words = words[len(env):] if words[:len(env)] == env else words
    kept: list[str] = []
    for word in words[:MAX_RULE_WORDS]:
        if word.startswith("-") and len(kept) >= 2:
            break
        kept.append(word)
    if not kept or kept[0] in NOT_A_RULE or NEVER_ALLOWED & set(words):
        return []
    plain = " ".join(kept)
    return [plain, " ".join([*env, plain])] if env else [plain]


def command_rules(project: Project, adapter: Adapter) -> list[str]:
    """An allow rule per command the project declares, so a worker can run its own build tools."""
    shape = (adapter.raw.get("settings") or {}).get("command_rule")
    if not shape:
        return []
    rules: list[str] = []
    for command in project.config.commands.values():
        for part in re.split(r"&&|\|\||;|\|", command):
            rules += [shape.format(p) for p in _prefixes(part) if shape.format(p) not in rules]
    return rules


def merged_env(data: dict, env: dict[str, str]) -> dict:
    """These variables added to the settings, in place. A value already there is the user's."""
    return {**data, "env": {**env, **(data.get("env") or {})}} if env else data


def _hook_entry(adapter: Adapter) -> dict:
    hook = adapter.raw["hook"]
    return {"matcher": hook["matcher"],
            "hooks": [{"type": "command", "command": hook["command"]}]}


def _merges_hook(adapter: Adapter) -> bool:
    return "event" in adapter.raw.get("hook", {})


def _has_hook(data: dict, adapter: Adapter) -> bool:
    command = adapter.raw["hook"]["command"]
    entries = (data.get("hooks") or {}).get(adapter.raw["hook"]["event"]) or []
    return any(h.get("command") == command for e in entries for h in e.get("hooks", []))


def merged_hook(data: dict, adapter: Adapter) -> dict:
    """This hook added to the settings, once, beside whatever hooks are already there."""
    if _has_hook(data, adapter):
        return data
    hooks = data.get("hooks")
    if hooks is None:
        hooks = {}
    event = adapter.raw["hook"]["event"]
    if not isinstance(hooks, dict) or not isinstance(hooks.get(event, []), list):
        raise Refused(f"the settings' `hooks.{event}` isn't a list; add this by hand: "
                      + adapter.raw["hook"]["command"])
    return {**data, "hooks": {**hooks, event: hooks.get(event, []) + [_hook_entry(adapter)]}}


def without_hook(data: dict, adapter: Adapter) -> dict:
    """The settings with only our hook taken out."""
    command = adapter.raw["hook"]["command"]
    event = adapter.raw["hook"]["event"]
    hooks = data.get("hooks")
    if not isinstance(hooks, dict) or not isinstance(hooks.get(event), list):
        return data
    kept = []
    for entry in hooks[event]:
        remaining = [h for h in entry.get("hooks", []) if h.get("command") != command]
        if remaining:
            kept.append({**entry, "hooks": remaining})
    rest = {k: v for k, v in hooks.items() if k != event}
    hooks_after = {**rest, event: kept} if kept else rest
    if hooks_after:
        return {**data, "hooks": hooks_after}
    return {k: v for k, v in data.items() if k != "hooks"}


def _settings_current(project: Project, adapter: Adapter, hook: bool) -> bool:
    settings = adapter.raw.get("settings")
    if not settings:
        return True
    data = read_settings(project.root / settings["path"])
    allowed = (data.get("permissions") or {}).get("allow") or []
    if not all(rule in allowed for rule in [*settings.get("allow", []), *command_rules(project, adapter)]):
        return False
    if not all(key in (data.get("env") or {}) for key in settings.get("env", {})):
        return False
    return not (hook and _merges_hook(adapter)) or _has_hook(data, adapter)


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


def file_states(project: Project, adapter: Adapter, hook: bool | None = None
                ) -> dict[str, str]:
    """{path: state} for this adapter's files, and the block: is each what this `ws` would write?
    A file differing from what was recorded was edited by hand; one matching the record but not the
    current text just comes from an older `ws`."""
    entry = load_manifest(project)["adapters"].get(adapter.name, {})
    recorded = entry.get("files", {})
    hook = entry.get("hook", False) if hook is None else hook
    states = {}
    for rel, content in generated(adapter, hook).items():
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
        states[settings["path"]] = CURRENT if _settings_current(project, adapter, hook) else MISSING
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


def adapt(project: Project, name: str, *, force: bool = False, hook: bool | None = None
          ) -> dict[str, list[str]]:
    """Write this agent's files. {"wrote": [...], "same": [...]}. All or nothing on edited files:
    it refuses before writing anything, so a refusal leaves no half-updated set.

    `hook` turns the guard on or off; None keeps it as it was. It is opt-in because it depends on
    `ws` being on PATH wherever the agent runs.
    """
    adapter = load(name)
    if hook and "hook" not in adapter.raw:
        raise WsError(f"{name} has no hook")
    manifest = load_manifest(project)
    was_on = manifest["adapters"].get(name, {}).get("hook", False)
    hook = was_on if hook is None else hook
    states = file_states(project, adapter, hook)
    edited = [rel for rel, state in states.items() if state == EDITED]
    if edited and not force:
        raise Refused("edited by hand, or not ours (--force overwrites):\n"
                      + "\n".join(f"  {rel}" for rel in edited))
    wrote, same = [], []
    hashes = {}
    for rel, content in generated(adapter, hook).items():
        hashes[rel] = _hash(content)
        if states[rel] == CURRENT:
            same.append(rel)
            continue
        path = project.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        wrote.append(rel)
    if was_on and not hook and "file" in adapter.raw.get("hook", {}):
        (project.root / adapter.raw["hook"]["file"]).unlink(missing_ok=True)
        wrote.append(adapter.raw["hook"]["file"])
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
        path = project.root / settings["path"]
        before = read_settings(path)
        allow = [*settings.get("allow", []), *command_rules(project, adapter)]
        after = merged_env(merged_permissions(before, allow), settings.get("env", {}))
        if _merges_hook(adapter):
            after = merged_hook(after, adapter) if hook else without_hook(after, adapter)
        if after == before and path.exists():
            same.append(settings["path"])
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            write_json(path, after)
            wrote.append(settings["path"])
    manifest["adapters"][name] = {"toolVersion": __version__, "hook": hook, "files": hashes}
    path = _manifest_path(project)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_json(path, manifest)
    return {"wrote": wrote, "same": same}


def hook_is_on(project: Project) -> bool:
    return any(a.get("hook") for a in load_manifest(project)["adapters"].values())


def write_plugin(name: str, out: Path, hook: bool = False) -> list[str]:
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
    if hook:
        event = adapter.raw["hook"]["event"]
        files[adapter.raw["hook"]["plugin_file"]] = json.dumps(
            {"hooks": {event: [_hook_entry(adapter)]}}, indent=2) + "\n"
    for rel, content in files.items():
        path = out / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
    return sorted(files)
