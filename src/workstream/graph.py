"""The task graph as pure functions over task dicts: what's ready, what waits, what collides."""

from __future__ import annotations

WAVE_READY, WAVE_FINISHED, WAVE_STUCK = 0, 2, 3  # `ws wave` exit codes, so scripts can branch.


def _str_list(value: object) -> list[str]:
    if isinstance(value, list) and all(isinstance(v, str) for v in value):
        return value
    return []


def blocked_by_graph(tasks: list[dict]) -> dict[str, list[str]]:
    """id -> its well-typed blockedBy ids, for every task with a string id."""
    return {t["id"]: list(_str_list(t.get("blockedBy", [])))
            for t in tasks if isinstance(t.get("id"), str)}


def find_cycles(graph: dict[str, list[str]]) -> list[list[str]]:
    """One cycle per back edge of a depth-first walk, each rotated to start at its least id.

    Self-references are left out; the validator reports those on their own.
    """
    cycles: set[tuple[str, ...]] = set()
    state: dict[str, int] = {}  # 1 = on the current path, 2 = finished
    for start in sorted(graph):
        if start in state:
            continue
        path = [start]
        state[start] = 1
        stack = [iter(sorted(b for b in graph[start] if b in graph and b != start))]
        while stack:
            nxt = next(stack[-1], None)
            if nxt is None:
                stack.pop()
                state[path.pop()] = 2
            elif state.get(nxt) == 1:
                cycle = path[path.index(nxt):]
                i = cycle.index(min(cycle))
                cycles.add(tuple(cycle[i:] + cycle[:i]))
            elif nxt not in state:
                state[nxt] = 1
                path.append(nxt)
                stack.append(iter(sorted(b for b in graph[nxt] if b in graph and b != nxt)))
    return [list(c) for c in sorted(cycles)]


def blockers_closure(graph: dict[str, list[str]]) -> dict[str, set[str]]:
    """id -> every id it waits on, directly or transitively (cycle-safe)."""
    closure: dict[str, set[str]] = {}
    for start in graph:
        seen: set[str] = set()
        todo = list(graph[start])
        while todo:
            b = todo.pop()
            if b in graph and b not in seen:
                seen.add(b)
                todo.extend(graph[b])
        closure[start] = seen
    return closure


def dependents(tasks: list[dict], task_id: str) -> list[str]:
    """Every id that waits on task_id, directly or transitively, in queue order."""
    closure = blockers_closure(blocked_by_graph(tasks))
    return [t["id"] for t in tasks if task_id in closure.get(t["id"], ())]


def file_overlaps(tasks: list[dict]) -> list[tuple[str, str, str]]:
    """(id, id, path) for every pair of tasks naming the same `files` path."""
    overlaps = []
    for i, a in enumerate(tasks):
        a_files = _str_list(a.get("files", []))
        for b in tasks[i + 1:]:
            for path in sorted(set(a_files) & set(_str_list(b.get("files", [])))):
                overlaps.append((a["id"], b["id"], path))
    return overlaps


def overlap_warning(a: str, b: str, path: str) -> str:
    return f"{a} and {b} both list {path!r} in files; run together they would collide"


def actionable(tasks: list[dict]) -> list[dict]:
    """The selection rule: todo, every blockedBy done, no pending user decision."""
    done_ids = {t["id"] for t in tasks if t["status"] == "done"}
    return [t for t in tasks
            if t["status"] == "todo"
            and not t.get("needsUserDecision", False)
            and all(b in done_ids for b in t.get("blockedBy", []))]


def compute_wave(tasks: list[dict]) -> dict:
    """Every actionable task in the lowest phase that has one, as data.

    `phase` is metadata, but blockedBy can cross phases (a phase-1 task needing a phase-2
    one), so the wave is "lowest phase with an actionable task", not "lowest unfinished
    phase": a phase's blocked leftovers come back in a later wave once their blockers land.

    Returns {state, phase, ids, open, overlaps, leftovers}: state is "ready", "finished"
    (every task done or deferred) or "stuck" (open tasks, none actionable); phase and ids
    are the wave (None and [] unless ready); open and leftovers (the in-progress tasks) are
    ids in priority order; overlaps are [a, b, path] for wave tasks sharing a files path.
    In-progress tasks never change the state: a queue whose only open tasks are in progress
    is stuck.
    """
    tasks = sorted(tasks, key=lambda t: t["priority"])
    open_ids = [t["id"] for t in tasks if t["status"] not in ("done", "deferred")]
    leftovers = [t["id"] for t in tasks if t["status"] == "in-progress"]
    result = {"state": "finished", "phase": None, "ids": [], "open": open_ids,
              "overlaps": [], "leftovers": leftovers}
    if not open_ids:
        return result
    candidates = actionable(tasks)
    if not candidates:
        return {**result, "state": "stuck"}
    phase = min(t["phase"] for t in candidates)
    wave = [t for t in candidates if t["phase"] == phase]
    return {**result, "state": "ready", "phase": phase, "ids": [t["id"] for t in wave],
            "overlaps": [list(o) for o in file_overlaps(wave)]}


def why_not_actionable(tasks: list[dict], task: dict) -> str:
    """The first reason actionable() leaves a task out, in the words a claimer needs."""
    if task["status"] != "todo":
        return f"status is {task['status']}"
    if task.get("needsUserDecision"):
        return "needsUserDecision"
    done_ids = {t["id"] for t in tasks if t["status"] == "done"}
    waiting = [b for b in task.get("blockedBy", []) if b not in done_ids]
    return f"waits on {', '.join(waiting)}"
