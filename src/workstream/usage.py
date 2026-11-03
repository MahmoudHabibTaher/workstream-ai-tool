"""`ws audit usage`: what real sessions cost in context, read from an agent's own transcripts.

`ws audit context` counts what this tool ships. This counts what agents really carried, which is
what the budgets were meant to protect. Transcripts hold whole conversations, so nothing here keeps
or prints their text: a session becomes a list of context sizes and a role, and only medians leave.

Each agent's adapter names where its transcripts live and which reader they need. Sizes come from
each agent's own usage figures, and agents count differently, so compare within an agent only.

    worker       a subagent that does a task, or a session opened with a worker's prompt
    coordinator  a session that started workers
    other        everything else, counted but not reported as either
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from statistics import median
from typing import Iterable, Iterator

from workstream import adapt, gitutil

WORKER, COORDINATOR, OTHER = "worker", "coordinator", "other"
ROLES = (WORKER, COORDINATOR, OTHER)
DEFAULT_WORKER_MARKER = r"\bws brief\b"
GROWTH_TURN = 5  # the plan's targets are written against turn 5


@dataclass
class Session:
    role: str
    started: str = ""  # ISO timestamp of its first record, "" if it has none
    sizes: list[int] = field(default_factory=list)  # context size at each model call, in order


def _lines(path: Path) -> Iterator[dict]:
    """Each JSON object in a transcript. Transcripts get cut off mid-line when a session dies."""
    try:
        with path.open(errors="replace") as f:
            for line in f:
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if isinstance(record, dict):
                    yield record
    except OSError:
        return


def _text_of(content: object) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return " ".join(b.get("text", "") for b in content if isinstance(b, dict))
    return ""


# --- one record per message, usage on the assistant's -------------------------------------------


def slug(path: Path) -> str:
    """How a project's path names its transcript folder."""
    return re.sub(r"[^A-Za-z0-9]", "-", str(path))


def _read_message_file(path: Path, marker: re.Pattern, skip_sidechain: bool) -> tuple[list[int], str, bool]:
    """(context sizes, first timestamp, whether its opening prompt is a worker's). A message's usage
    repeats on each of its content blocks, so each message id counts once."""
    sizes, seen = [], set()
    started, is_worker, opened = "", False, False
    for record in _lines(path):
        started = started or record.get("timestamp", "")
        if skip_sidechain and record.get("isSidechain"):
            continue
        message = record.get("message")
        if not isinstance(message, dict):
            continue
        if record.get("type") == "user" and not opened:
            opened = True
            is_worker = bool(marker.search(_text_of(message.get("content"))))
        usage = message.get("usage")
        if isinstance(usage, dict) and message.get("id") not in seen:
            seen.add(message.get("id"))
            sizes.append(usage.get("input_tokens", 0) + usage.get("cache_read_input_tokens", 0)
                         + usage.get("cache_creation_input_tokens", 0))
    return sizes, started, is_worker


def _is_worker_subagent(path: Path, opened_as_worker: bool) -> bool:
    if opened_as_worker:
        return True
    try:
        meta = json.loads(path.with_name(path.name.replace(".jsonl", ".meta.json")).read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return bool(meta.get("spawnedWithWorktree")) or "worker" in str(meta.get("agentType", ""))


def message_lines(root: Path, project: Path, marker: re.Pattern) -> Iterator[Session]:
    if not root.is_dir():
        return
    prefix = slug(project)
    for folder in sorted(root.iterdir()):
        if not (folder.is_dir() and folder.name.startswith(prefix)):
            continue
        for main in sorted(folder.glob("*.jsonl")):
            workers = []
            for sub in sorted((folder / main.stem / "subagents").glob("*.jsonl")):
                sizes, started, opened_as_worker = _read_message_file(sub, marker, False)
                if sizes:
                    role = WORKER if _is_worker_subagent(sub, opened_as_worker) else OTHER
                    workers.append(Session(role, started, sizes))
            sizes, started, opened_as_worker = _read_message_file(main, marker, True)
            yield from workers
            if sizes:
                role = (COORDINATOR if any(w.role == WORKER for w in workers)
                        else WORKER if opened_as_worker else OTHER)
                yield Session(role, started, sizes)


# --- typed events, one usage record per model call ----------------------------------------------


def _remote_name(project: Path) -> str:
    """The project's `owner/name` on its remote, or "". Worktrees can sit anywhere on disk, and
    their sessions still name this."""
    url = gitutil.run(project, "remote", "get-url", "origin").stdout.strip()
    match = re.search(r"[:/]([^/:]+/[^/]+?)(?:\.git)?$", url)
    return match[1] if match else ""


def _in_project(context: dict, project: Path, remote: str) -> bool:
    """Whether a session ran in this project, below it, or in another checkout of it."""
    if remote and context.get("repository") == remote:
        return True
    for key in ("gitRoot", "cwd"):
        value = context.get(key)
        if isinstance(value, str) and value:
            path = Path(value)
            if path == project or project in path.parents:
                return True
    return False


def event_lines(root: Path, project: Path, marker: re.Pattern) -> Iterator[Session]:
    if not root.is_dir():
        return
    remote = _remote_name(project) if project.is_dir() else ""
    for folder in sorted(root.iterdir()):
        path = folder / "events.jsonl"
        if not path.is_file():
            continue
        records = _lines(path)
        first = next(records, None)
        if first is None or first.get("type") != "session.start":
            continue
        if not _in_project(first.get("data", {}).get("context") or {}, project, remote):
            continue
        started = first.get("timestamp", "")
        main: list[int] = []
        agents: dict[str, list[int]] = {}
        opened_as_worker, opened, worker_calls = False, False, 0
        for record in records:
            kind, data = record.get("type"), record.get("data") or {}
            if kind == "user.message" and not opened:
                opened = True
                opened_as_worker = bool(marker.search(str(data.get("content", ""))))
            elif kind == "subagent.started" and "worker" in str(data.get("agentName", "")):
                worker_calls += 1
            elif kind == "session.usage_record":
                size = (data.get("usage") or {}).get("inputTokens")
                if isinstance(size, int):
                    target = agents.setdefault(record["agentId"], []) if record.get("agentId") else main
                    target.append(size)
        for sizes in agents.values():
            yield Session(WORKER if worker_calls else OTHER, started, sizes)
        if main:
            role = COORDINATOR if worker_calls else WORKER if opened_as_worker else OTHER
            yield Session(role, started, main)


READERS = {"message-lines": message_lines, "event-lines": event_lines}


# --- the report ---------------------------------------------------------------------------------


def _median(values: Iterable[int]) -> int | None:
    values = list(values)
    return round(median(values)) if values else None


def summarise(sessions: Iterable[Session]) -> dict[str, dict]:
    """Per role: the sessions counted and the median of each figure. A session too short to reach
    the growth turn isn't in that turn's figures, as a short session would look like no growth."""
    by_role: dict[str, list[Session]] = {role: [] for role in ROLES}
    for session in sessions:
        by_role[session.role].append(session)
    out = {}
    for role, found in by_role.items():
        reached = [s.sizes for s in found if len(s.sizes) >= GROWTH_TURN]
        out[role] = {
            "sessions": len(found),
            "reachedGrowthTurn": len(reached),
            "turns": _median(len(s.sizes) for s in found),
            "first": _median(s.sizes[0] for s in found),
            "firstStep": _median(s.sizes[1] - s.sizes[0] for s in found if len(s.sizes) > 1),
            "atGrowthTurn": _median(sizes[GROWTH_TURN - 1] for sizes in reached),
            "growth": _median(sizes[GROWTH_TURN - 1] - sizes[0] for sizes in reached),
            "peak": _median(max(s.sizes) for s in found),
            "highestPeak": max((max(s.sizes) for s in found), default=None),
            "cumulative": _median(sum(s.sizes) for s in found),
        }
    return out


def in_window(session: Session, since: str | None, until: str | None) -> bool:
    day = session.started[:10]
    if since and (not day or day < since):
        return False
    return not (until and (not day or day > until))


def report(agent: str, project: Path, *, since: str | None = None, until: str | None = None,
           transcripts: Path | None = None, worker_marker: str = DEFAULT_WORKER_MARKER) -> dict:
    """The summary for one agent's transcripts of one project. Numbers only."""
    settings = adapt.load(agent).raw.get("transcripts") or {}
    reader = READERS[settings["reader"]]
    root = transcripts or Path(settings["root"]).expanduser()
    marker = re.compile(worker_marker)
    sessions = [s for s in reader(root, project.resolve(), marker) if in_window(s, since, until)]
    return {"agent": agent, "since": since, "until": until, "roles": summarise(sessions)}


def agents_with_transcripts() -> list[str]:
    return [name for name in adapt.names() if adapt.load(name).raw.get("transcripts")]


def format_report(result: dict) -> list[str]:
    def cell(value: int | None) -> str:
        return "-" if value is None else f"{value:,}"

    lines = [f"{result['agent']}, tokens in context per model call, medians:",
             f"  {'role':<12}{'sessions':>9}{'turns':>7}{'turn 1':>10}{'step 1':>10}{f'turn {GROWTH_TURN}':>10}"
             f"{'growth':>10}{'peak':>10}{'highest':>10}{'cumulative':>12}"]
    for role in ROLES:
        row = result["roles"][role]
        lines.append(f"  {role:<12}{row['sessions']:>9}{cell(row['turns']):>7}{cell(row['first']):>10}"
                     f"{cell(row['firstStep']):>10}{cell(row['atGrowthTurn']):>10}{cell(row['growth']):>10}{cell(row['peak']):>10}"
                     f"{cell(row['highestPeak']):>10}{cell(row['cumulative']):>12}")
    return lines
