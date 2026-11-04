"""The task queue: tasks_list.json's schema, its one validator, and every write to it.

Envelope, schema version 3:

    {
      "schemaVersion": 3, "source": str, "updated": "YYYY-MM-DD",
      "protocolVersion": str,      # the protocol this workstream was planned against
      "tier": "lite" | "standard" | "full",
      "scope": {"inScope": [str], "outOfScope": [str], "rule": str},   # optional
      "tasks": [...]
    }

A task is the fields in FIELD_TYPES; a field this schema doesn't know is kept, at the end.
`verify` holds keys into the config's [commands], or a raw command (anything with a space).
Writes here take a Config, because what `requires` allows and which kinds need which
verification is the project's call.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from workstream import graph
from workstream.config import Config
from workstream.errors import WsError
from workstream.fsutil import now_iso, today, write_json

SCHEMA_VERSION = 3
PROTOCOL_VERSION = "1"
TIERS = ("lite", "standard", "full")
# The tier that ships: only this one must say what each task does to a release.
RELEASING_TIER = "full"
STATUS_VALUES = ("todo", "in-progress", "blocked", "done", "deferred")
# The statuses the open-task rules apply to; done and deferred are history.
OPEN_STATUSES = ("todo", "in-progress", "blocked")
# The statuses `unclaim` takes a task back to todo from: started, not finished.
UNCLAIMABLE_STATUSES = ("in-progress", "blocked")
MODE_VALUES = ("background", "foreground")
RELEASE_IMPACT_VALUES = ("none", "patch", "minor", "major")
ACCEPTANCE_KINDS = ("command", "manual")
# Written by the CLI as a task runs; `reset` clears them.
RUNTIME_FIELDS = ("startedAt", "baseCommit", "claimedBy", "completedAt", "commit", "verification",
                  "blockedReason")

# Every field but id/phase/priority/title, in the order a task is written.
TASK_FIELD_DEFAULTS = {
    "kind": "",
    "findings": [],
    "summary": "",
    "files": [],
    "docs": [],
    "acceptance": [],
    "verify": [],
    "branch": "",
    "blockedBy": [],
    "needsUserDecision": False,
    "notes": "",
    "mode": "background",
    "requires": [],
    "releaseImpact": None,
    "status": "todo",
    "startedAt": None,
    "baseCommit": None,
    "claimedBy": None,
    "completedAt": None,
    "commit": None,
    "verification": None,
    "blockedReason": None,
}
FIELD_ORDER = ["id", "phase", "priority", "title", *TASK_FIELD_DEFAULTS]
# Without one of these a task can't be queued; every other field reads as its default.
REQUIRED_FIELDS = ("id", "phase", "priority", "title", "status")

STR, OPT_STR, OPT_OBJECT, INT, BOOL, STR_LIST, ACCEPTANCE = (
    "str", "str|null", "object|null", "int", "bool", "str_list", "acceptance")
FIELD_TYPES = {
    "id": STR, "phase": INT, "priority": INT, "title": STR, "kind": STR,
    "findings": STR_LIST, "summary": STR, "files": STR_LIST, "docs": STR_LIST,
    "acceptance": ACCEPTANCE, "verify": STR_LIST, "branch": OPT_STR, "blockedBy": STR_LIST,
    "needsUserDecision": BOOL, "notes": STR, "mode": STR, "requires": STR_LIST,
    "releaseImpact": OPT_STR, "status": STR, "startedAt": OPT_STR, "baseCommit": OPT_STR,
    "claimedBy": OPT_STR, "completedAt": OPT_STR, "commit": OPT_STR, "verification": OPT_OBJECT,
    "blockedReason": OPT_STR,
}
TYPE_DESCRIPTIONS = {
    STR: "a string", OPT_STR: "a string or null", OPT_OBJECT: "an object or null", INT: "an integer", BOOL: "a boolean",
    STR_LIST: "a list of strings",
    ACCEPTANCE: "a list of strings or {text, kind} objects",
}
# An id names a file, a worktree folder and a branch, and git may read it as an option.
TASK_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
# Ends the warning for an open task's `files` path that doesn't exist: expected on any task
# that creates the file, so the health findings leave it out.
MISSING_FILES_SUFFIX = "does not exist (yet)"
# What a shell doesn't read as an operator: a quoted string or an escaped character.
SHELL_QUOTED_RE = re.compile(r"""\\.|'[^']*'|"(?:\\.|[^"\\])*\"""", re.DOTALL)
# Leading assignments on a command. An assignment followed by no command (`A=1 && b`) sets
# a shell variable that does last, so a word has to come next.
ENV_PREFIX_RE = re.compile(r"\s*((?:[A-Za-z_]\w*=[^\s;&|]*\s+)+)(?![A-Za-z_]\w*=)[^\s;&|]")
COMMAND_SEPARATOR_RE = re.compile(r"&&|\||;")


# --- reading and writing the file ---------------------------------------------------------


def read_raw(path: Path) -> dict:
    if not path.exists():
        raise WsError(f"{path} does not exist")
    try:
        with path.open() as f:
            data = json.load(f)
    except json.JSONDecodeError as e:
        raise WsError(f"{path}: not valid JSON: {e}") from None
    if not isinstance(data, dict) or not isinstance(data.get("tasks"), list):
        raise WsError(f"{path}: not a task queue (no `tasks` list)")
    if not all(isinstance(t, dict) for t in data["tasks"]):
        raise WsError(f"{path}: every task must be an object")
    return data


def load(path: Path, config: Config) -> dict:
    """Read a queue with every task normalized: runtime fields defaulted, keys in order."""
    data = read_raw(path)
    version = data.get("schemaVersion")
    if version != SCHEMA_VERSION:
        raise WsError(f"{path}: schemaVersion {version!r} is not {SCHEMA_VERSION}")
    if not all(is_queueable(t) for t in data["tasks"]):
        raise WsError(f"{path}: a task is malformed; `ws validate` says which")
    data["tasks"] = [normalize_task(t, config) for t in data["tasks"]]
    return data


def save(path: Path, data: dict) -> None:
    """Write the queue sorted by priority, stamped with the current schemaVersion first."""
    data["tasks"].sort(key=lambda t: t["priority"])
    rest = {k: v for k, v in data.items() if k != "schemaVersion"}
    write_json(path, {"schemaVersion": SCHEMA_VERSION, **rest})


def new_envelope(source: str, tier: str = "standard") -> dict:
    return {"schemaVersion": SCHEMA_VERSION, "source": source, "updated": today(),
            "protocolVersion": PROTOCOL_VERSION, "tier": tier, "tasks": []}


def default_mode(task: dict, config: Config) -> str:
    """`mode` when a task doesn't give one: foreground if `requires` forces it."""
    requires = task.get("requires") or []
    forced = isinstance(requires, list) and any(r in config.foreground_requires for r in requires)
    return "foreground" if forced else "background"


def normalize_task(task: dict, config: Config) -> dict:
    """The task with every absent field defaulted and keys in FIELD_ORDER, any field the
    schema doesn't know at the end, so each CLI write gives every task one shape."""
    task = dict(task)
    if "mode" not in task:
        task["mode"] = default_mode(task, config)
    for field, default in TASK_FIELD_DEFAULTS.items():
        task.setdefault(field, list(default) if isinstance(default, list) else default)
    ordered = {k: task[k] for k in FIELD_ORDER if k in task}
    ordered.update({k: v for k, v in task.items() if k not in ordered})
    return ordered


def find_task(data: dict, task_id: str) -> dict:
    for t in data["tasks"]:
        if t["id"] == task_id:
            return t
    raise WsError(f"no task with id {task_id!r}")


def find_task_by_prefix(data: dict, text: str) -> dict:
    """The task with this id, or the one task whose id starts with it: for commands that
    only read, where a typo can't change anything."""
    exact = [t for t in data["tasks"] if t["id"] == text]
    if exact:
        return exact[0]
    matches = [t for t in data["tasks"] if t["id"].startswith(text)]
    if len(matches) == 1:
        return matches[0]
    if matches:
        raise WsError(f"{text!r} matches {', '.join(t['id'] for t in matches)}")
    raise WsError(f"no task with id {text!r}")


def is_queueable(task: dict) -> bool:
    """Whether a task is sound enough for the graph functions. `validate` names what's wrong
    with one that isn't; everything else refuses it rather than crash or misread it."""
    return (isinstance(task.get("id"), str) and TASK_ID_RE.match(task["id"]) is not None
            and is_type(task.get("phase"), INT)
            and is_type(task.get("priority"), INT)
            and isinstance(task.get("status"), str)
            and is_type(task.get("blockedBy", []), STR_LIST))


def verify_commands(task: dict, config: Config) -> list[tuple[str, str]]:
    """(label, command) for each entry of a task's verify. A raw command labels itself; a
    key with no command in the config reads as an empty command, for the caller to flag."""
    resolved = []
    for entry in task.get("verify", []):
        if is_raw_command(entry):
            resolved.append((entry, entry))
        else:
            resolved.append((entry, config.commands.get(entry, "")))
    return resolved


def is_raw_command(entry: str) -> bool:
    return any(c.isspace() for c in entry)


def acceptance_text(item: object) -> str:
    if isinstance(item, dict):
        suffix = " (manual)" if item.get("kind") == "manual" else ""
        if item.get("expect"):
            suffix += f" (the output must contain `{item['expect']}`)"
        return f"{item.get('text', '')}{suffix}"
    return str(item)


def expected_outputs(task: dict) -> list[tuple[int, str]]:
    """(item number, literal) for each acceptance item naming the output it expects."""
    return [(n, item["expect"]) for n, item in enumerate(task.get("acceptance", []), 1)
            if isinstance(item, dict) and isinstance(item.get("expect"), str) and item["expect"]]


# --- validation ---------------------------------------------------------------------------


def is_type(value: object, kind: str) -> bool:
    if kind == STR:
        return isinstance(value, str)
    if kind == OPT_STR:
        return value is None or isinstance(value, str)
    if kind == OPT_OBJECT:
        return value is None or isinstance(value, dict)
    if kind == INT:
        return isinstance(value, int) and not isinstance(value, bool)
    if kind == BOOL:
        return isinstance(value, bool)
    if kind == ACCEPTANCE:
        return isinstance(value, list) and all(_is_acceptance_item(v) for v in value)
    return isinstance(value, list) and all(isinstance(v, str) for v in value)


def _is_acceptance_item(item: object) -> bool:
    if isinstance(item, str):
        return True
    return (isinstance(item, dict) and isinstance(item.get("text"), str)
            and item.get("kind", "command") in ACCEPTANCE_KINDS)


def _label(task: dict, n: int) -> str:
    return task["id"] if isinstance(task.get("id"), str) and task["id"] else f"task #{n + 1}"


def _expect_errors(task: dict, label: str) -> list[str]:
    """An `expect` must be something `ws verify` can look for, in a log a command wrote."""
    items = task.get("acceptance", [])
    errors = []
    for n, item in enumerate(items if isinstance(items, list) else [], 1):
        if not isinstance(item, dict) or "expect" not in item:
            continue
        where = f"{label}: acceptance {n}"
        if item.get("kind") == "manual":
            errors.append(f"{where}: a manual item has no command output to expect")
        elif not isinstance(item["expect"], str) or not item["expect"].strip():
            errors.append(f"{where}: expect must be a non-empty string")
        elif not task.get("verify"):
            errors.append(f"{where}: expect needs a verify command to read the output of")
    return errors


def _typed_field_errors(task: dict, label: str, config: Config) -> list[str]:
    """Bad enum values in mode/requires/releaseImpact; absent fields read as defaults."""
    errors = []
    mode = task.get("mode", "background")
    if isinstance(mode, str) and mode not in MODE_VALUES:
        errors.append(f"{label}: mode {mode!r} not in {list(MODE_VALUES)}")
    requires = task.get("requires", [])
    if is_type(requires, STR_LIST):
        for r in requires:
            if r not in config.requires_values:
                errors.append(f"{label}: requires {r!r} not in {list(config.requires_values)}")
    impact = task.get("releaseImpact")
    if isinstance(impact, str) and impact not in RELEASE_IMPACT_VALUES:
        errors.append(f"{label}: releaseImpact {impact!r} not in {list(RELEASE_IMPACT_VALUES)}")
    return errors


def _mode_conflict(task: dict, config: Config) -> list[str]:
    """The `requires` entries that force foreground on a task whose mode isn't foreground."""
    requires = task.get("requires", [])
    if not is_type(requires, STR_LIST) or task.get("mode", "background") == "foreground":
        return []
    return [r for r in requires if r in config.foreground_requires]


def _field_errors(task: dict, label: str, config: Config) -> list[str]:
    errors = [f"{label}: missing {f}" for f in REQUIRED_FIELDS if f not in task]
    for field, kind in FIELD_TYPES.items():
        if field in task and not is_type(task[field], kind):
            errors.append(
                f"{label}: {field} must be {TYPE_DESCRIPTIONS[kind]}, got {task[field]!r}")
    errors += _expect_errors(task, label)
    for field in ("id", "title"):
        if task.get(field) == "":
            errors.append(f"{label}: {field} is empty")
    if isinstance(task.get("id"), str) and task["id"] and not TASK_ID_RE.match(task["id"]):
        errors.append(f"{label}: id must be letters, digits, '.', '_' or '-', starting with a "
                      "letter or digit")
    status = task.get("status")
    if isinstance(status, str) and status not in STATUS_VALUES:
        errors.append(f"{label}: status {status!r} not in {list(STATUS_VALUES)}")
    return errors + _typed_field_errors(task, label, config)


def _duplicates(tasks: list[dict]) -> list[str]:
    problems = []
    ids = [t["id"] for t in tasks if isinstance(t.get("id"), str)]
    for dup in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"duplicate id: {dup}")
    priorities = [t["priority"] for t in tasks if is_type(t.get("priority"), INT)]
    for dup in sorted({p for p in priorities if priorities.count(p) > 1}):
        problems.append(f"duplicate priority: {dup}")
    return problems


def _verify_errors(task: dict, label: str, config: Config) -> list[str]:
    """Unknown verify keys, and the keys this task's kind must verify with but doesn't."""
    verify = task.get("verify", [])
    if not is_type(verify, STR_LIST):
        return []
    errors = [f"{label}: verify key {v!r} is not in [commands]" for v in verify
              if not is_raw_command(v) and v not in config.commands]
    kind = task.get("kind")
    if isinstance(kind, str):
        # A key the project has no command for can't be demanded: a project may have no
        # compile step at all.
        needed = [k for k in config.adequacy.get(kind, []) if k in config.commands]
        missing = [k for k in needed if k not in verify]
        if missing:
            errors.append(f"{label}: kind {kind!r} must verify with {', '.join(missing)}")
    return errors


def _short_env_prefix(command: str) -> list[str]:
    """The variables a command sets for its first step only: `A=1 a && b` leaves b without A."""
    unquoted = SHELL_QUOTED_RE.sub("Q", command)
    prefix = ENV_PREFIX_RE.match(unquoted)
    if not prefix or not COMMAND_SEPARATOR_RE.search(unquoted, prefix.end()):
        return []
    return [word.split("=", 1)[0] for word in prefix.group(1).split()]


def _verify_warnings(task: dict, label: str, config: Config) -> list[str]:
    """A warning for each verify command whose leading assignment stops at its first step."""
    if not is_type(task.get("verify", []), STR_LIST):
        return []
    warnings = []
    for entry, command in verify_commands(task, config):
        names = _short_env_prefix(command)
        if names:
            warnings.append(f"{label}: verify {entry!r} sets {', '.join(names)} for its first "
                            f"command only; the rest runs without it (export it instead)")
    return warnings


def validate_tasks(tasks: list[dict], repo_root: Path, config: Config,
                   tier: str = "standard") -> tuple[list[str], list[str]]:
    """Every integrity problem in a queue, as (errors, warnings).

    Errors: a missing or ill-typed field, a bad enum value, duplicate ids or priorities, an
    unknown, self or cyclic blockedBy, a done task without a commit, and, on open tasks
    only, a missing releaseImpact (on a full workstream), a docs path that doesn't
    exist, a mode that requires contradicts, an unknown verify key, or a verify that falls
    short of the task's kind. Warnings: a files path missing on an open task (it may be one
    the task creates), an open task's verify command whose leading VAR=x stops at its first
    step, and two open tasks in the same phase, neither waiting on the other, that name the
    same files path. Open-only rules keep a finished queue valid untouched.
    """
    errors: list[str] = []
    warnings: list[str] = []
    blocked_by = graph.blocked_by_graph(tasks)

    for n, t in enumerate(tasks):
        label = _label(t, n)
        errors += _field_errors(t, label, config)
        for b in blocked_by.get(t["id"], []) if isinstance(t.get("id"), str) else []:
            if b == t["id"]:
                errors.append(f"{label}: blockedBy references itself")
            elif b not in blocked_by:
                errors.append(f"{label}: blockedBy references unknown id {b!r}")
        if t.get("status") == "done" and not t.get("commit"):
            errors.append(f"{label}: done without a commit")
        if t.get("status") not in OPEN_STATUSES:
            continue
        if tier == RELEASING_TIER and t.get("releaseImpact") is None:
            errors.append(f"{label}: open task has no releaseImpact")
        for path in t.get("docs", []) if is_type(t.get("docs", []), STR_LIST) else []:
            if not (repo_root / path).exists():
                errors.append(f"{label}: docs path {path!r} does not exist")
        forcing = _mode_conflict(t, config)
        if forcing:
            errors.append(f"{label}: requires {forcing} but mode is "
                          f"{t.get('mode', 'background')!r}; it must be 'foreground'")
        errors += _verify_errors(t, label, config)
        warnings += _verify_warnings(t, label, config)
        for path in t.get("files", []) if is_type(t.get("files", []), STR_LIST) else []:
            if not (repo_root / path).exists():
                warnings.append(f"{label}: files path {path!r} {MISSING_FILES_SUFFIX}")

    errors += _duplicates(tasks)
    errors += [f"blockedBy cycle: {' -> '.join(c + c[:1])}" for c in graph.find_cycles(blocked_by)]

    closure = graph.blockers_closure(blocked_by)
    open_tasks = [t for t in tasks
                  if t.get("status") in OPEN_STATUSES and isinstance(t.get("id"), str)]
    for a, b, path in graph.file_overlaps(open_tasks):
        if b not in closure.get(a, ()) and a not in closure.get(b, ()):
            warnings.append(graph.overlap_warning(a, b, path))
    return errors, warnings


def _entry_errors(tasks: list[dict], config: Config) -> list[str]:
    """What seed/add/update refuse: ill-typed fields, bad enums, a mode requires forces."""
    errors = []
    for n, t in enumerate(tasks):
        label = _label(t, n)
        errors += _field_errors(t, label, config)
        forcing = _mode_conflict(t, config)
        if forcing:
            errors.append(f"{label}: requires {forcing} needs mode 'foreground', not 'background'")
    return errors


# --- writes -------------------------------------------------------------------------------


def seed(path: Path, new_tasks: object, config: Config) -> int:
    """Bulk-load task objects; all-or-nothing. Returns how many the queue now holds."""
    data = load(path, config)
    if not isinstance(new_tasks, list) or not all(isinstance(t, dict) for t in new_tasks):
        raise WsError("seed must be a JSON array of task objects")
    new_tasks = [normalize_task(t, config) for t in new_tasks]
    problems = _entry_errors(new_tasks, config)
    if problems:
        raise WsError("seed has invalid tasks:\n" + "\n".join(problems))
    existing = {t["id"] for t in data["tasks"]}
    for t in new_tasks:
        if t["id"] in existing:
            raise WsError(f"task id {t['id']!r} already present in {path}")
    data["tasks"].extend(new_tasks)
    problems = _duplicates(data["tasks"])
    if problems:
        raise WsError("seed introduces integrity problems:\n" + "\n".join(problems))
    data["updated"] = today()
    save(path, data)
    return len(data["tasks"])


def add(path: Path, fields: dict, config: Config) -> dict:
    data = load(path, config)
    if any(t["id"] == fields["id"] for t in data["tasks"]):
        raise WsError(f"task id {fields['id']!r} already exists")
    if any(t["priority"] == fields["priority"] for t in data["tasks"]):
        raise WsError(f"priority {fields['priority']} already used by another task")
    task = normalize_task(fields, config)
    problems = _entry_errors([task], config)
    if problems:
        raise WsError("\n".join(problems))
    data["tasks"].append(task)
    data["updated"] = today()
    save(path, data)
    return task


def update(path: Path, task_id: str, config: Config, *, status: str | None = None,
           commit: str | None = None, notes: str | None = None,
           requires: list[str] | None = None, mode: str | None = None,
           release_impact: str | None = None, verify: list[str] | None = None,
           verification: dict | None = None, blocked_reason: str | None = None) -> dict:
    data = load(path, config)
    task = find_task(data, task_id)
    if status is not None:
        if status not in STATUS_VALUES:
            raise WsError(f"status must be one of {list(STATUS_VALUES)}")
        if status == "done" and not (commit or task.get("commit")):
            raise WsError(f"{task_id} has no commit; mark it done with --commit <merge-hash>")
        task["status"] = status
        if status == "in-progress" and not task.get("startedAt"):
            task["startedAt"] = now_iso()
        if status == "done" and not task.get("completedAt"):
            task["completedAt"] = now_iso()
        if status != "blocked":
            task["blockedReason"] = None
    if blocked_reason is not None:
        task["blockedReason"] = blocked_reason
    if commit is not None:
        task["commit"] = commit
    if notes is not None:
        task["notes"] = notes
    if requires is not None:
        task["requires"] = requires
        if mode is None and _mode_conflict(task, config):
            task["mode"] = "foreground"  # raised, never lowered: foreground may have other reasons
    if mode is not None:
        task["mode"] = mode
    if release_impact is not None:
        task["releaseImpact"] = release_impact
    if verify is not None:
        task["verify"] = verify
    if verification is not None:
        task["verification"] = verification
    problems = _entry_errors([task], config)
    if problems:
        raise WsError("\n".join(problems))
    data["updated"] = today()
    save(path, data)
    return task


def correct_acceptance(path: Path, task_id: str, number: str, text: str, because: str,
                       config: Config) -> dict:
    """Replace one acceptance item, naming the decision that changed it. Its position and kind
    stay, since evidence pairs with acceptance by number. Its `expect` goes: that literal belonged
    to the old text, and keeping it could leave the corrected item impossible to pass."""
    data = load(path, config)
    task = find_task(data, task_id)
    if task.get("status") not in OPEN_STATUSES:
        raise WsError(f"{task_id} is {task.get('status')}: its acceptance stays as it was")
    if not text.strip():
        raise WsError("--acceptance needs the item's new text")
    items = task["acceptance"]
    if not number.isdecimal() or not 1 <= int(number) <= len(items):
        raise WsError(f"{task_id} has no acceptance item {number}: it has {len(items)}")
    corrected = f"{text.strip()} (changed by {because})"
    index = int(number) - 1
    if isinstance(items[index], dict):
        items[index]["text"] = corrected
        items[index].pop("expect", None)
    else:
        items[index] = corrected
    data["updated"] = today()
    save(path, data)
    return task


def correct_summary(path: Path, task_id: str, text: str, because: str, config: Config) -> dict:
    """Replace a task's summary, naming the decision that changed it."""
    data = load(path, config)
    task = find_task(data, task_id)
    if task.get("status") not in OPEN_STATUSES:
        raise WsError(f"{task_id} is {task.get('status')}: its summary stays as it was")
    if not text.strip():
        raise WsError("--summary needs the new text")
    task["summary"] = f"{text.strip()} (changed by {because})"
    data["updated"] = today()
    save(path, data)
    return task


def _unique(ids: list[str]) -> list[str]:
    return list(dict.fromkeys(ids))


def claim(path: Path, ids: list[str], base: str, by: str | None, config: Config) -> list[str]:
    """Start a batch: all-or-nothing, so a refused claim leaves the queue untouched."""
    data = load(path, config)
    if not base.strip():
        raise WsError("--base must name the commit the claimed tasks start from")
    tasks = data["tasks"]
    known = {t["id"] for t in tasks}
    ready = {t["id"] for t in graph.actionable(tasks)}
    ids = _unique(ids)
    problems = [f"{i}: no such task" for i in ids if i not in known]
    problems += [f"{i}: not actionable ({graph.why_not_actionable(tasks, find_task(data, i))})"
                 for i in ids if i in known and i not in ready]
    if problems:
        raise WsError("claimed nothing:\n" + "\n".join(f"  - {p}" for p in problems))
    started = now_iso()
    for i in ids:
        task = find_task(data, i)
        task.update(status="in-progress", startedAt=started, baseCommit=base, claimedBy=by)
        task["branch"] = task.get("branch") or config.branch_for(i)
    data["updated"] = today()
    save(path, data)
    return ids


def batch_problems(rows: list[dict], ids: list[str]) -> list[str]:
    """Why these tasks shouldn't run together, or now. Each phase lands and goes green before
    anything builds on it, a foreground task needs the session to itself, and two workers on one
    file only find out at the merge, which goes for a task already in progress or blocked too."""
    chosen = [t for t in rows if t["id"] in set(ids)]
    problems = []
    phases = sorted({t["phase"] for t in chosen})
    if len(phases) > 1:
        problems.append(f"a batch is one phase; these span {phases}")
    foreground = [t["id"] for t in chosen if t["mode"] == "foreground"]
    if foreground and len(chosen) > 1:
        problems.append(f"foreground tasks run alone: {', '.join(foreground)}")
    problems += [f"{a} and {b} both name {path}: claim one now, or chain them with blockedBy"
                 for a, b, path in graph.file_overlaps(chosen)]
    status = {t["id"]: t["status"] for t in rows}
    problems += [f"{h['id']} shares {h['path']} with {h['by']}, which is {status[h['by']]}: "
                 f"land or unclaim {h['by']} first"
                 for h in graph.file_holds(chosen, rows)]
    return problems


def set_scope(path: Path, scope: dict, config: Config) -> None:
    data = load(path, config)
    data["scope"] = scope
    data["updated"] = today()
    save(path, data)


def unclaim(path: Path, ids: list[str], config: Config) -> list[str]:
    """Put started tasks back in the queue: todo, with startedAt, the claim and any block cleared."""
    data = load(path, config)
    known = {t["id"] for t in data["tasks"]}
    ids = _unique(ids)
    problems = [f"{i}: no such task" for i in ids if i not in known]
    problems += [
        f"{i}: status is {find_task(data, i)['status']}, not {' or '.join(UNCLAIMABLE_STATUSES)}"
        for i in ids if i in known and find_task(data, i)["status"] not in UNCLAIMABLE_STATUSES]
    if problems:
        raise WsError("unclaimed nothing:\n" + "\n".join(f"  - {p}" for p in problems))
    for i in ids:
        find_task(data, i).update(status="todo", startedAt=None, baseCommit=None, claimedBy=None,
                                  blockedReason=None)
    data["updated"] = today()
    save(path, data)
    return ids


def reset_plan(data: dict, ids: list[str] | None, cascade: bool) -> list[str]:
    """The ids `reset` would change: all of them, or these and, with cascade, their dependents.
    A task already pristine is left out."""
    tasks = data["tasks"]
    if not ids:
        chosen = [t["id"] for t in tasks]
    else:
        chosen = []
        for i in ids:
            find_task(data, i)
            chosen.append(i)
            if cascade:
                chosen += graph.dependents(tasks, i)
    chosen = _unique(chosen)
    return [i for i in chosen
            if (t := find_task(data, i))["status"] != "todo"
            or any(t.get(f) for f in RUNTIME_FIELDS)]


def reset(path: Path, ids: list[str] | None, cascade: bool, config: Config) -> list[str]:
    """Replay: back to todo with run-time state cleared. Task definitions are never touched."""
    data = load(path, config)
    changed = reset_plan(data, ids, cascade)
    for i in changed:
        find_task(data, i).update(status="todo", **{f: None for f in RUNTIME_FIELDS})
    if changed:
        data["updated"] = today()
        save(path, data)
    return changed
