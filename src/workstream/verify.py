"""`ws verify`: run a task's commands, record the outcome against the tree they ran on.

The agent gets a verdict, new findings and a short tail on failure. The whole log goes to a
file, because a build's output is the cost every agent pays on every run. Pass or fail stops
being the agent's claim: `ws settle` reads this record, not the agent's report.

Records live under <git common dir>/workstream/runs/<workstream>/<task>/, so every worktree
shares them, they can never be committed, and a project's .gitignore needn't know about them.
A person or agent with a shell can still edit that file: this makes an honest mistake
impossible, not fraud.

A record is tied to the *code tree*: the tree with each workstream's tracking folder and the
registry removed. Writing the evidence file and committing therefore doesn't invalidate a
verification, and changing any code does.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from pathlib import Path

from workstream import baseline, gitutil, registry, snapshot, tasks
from workstream.errors import WsError
from workstream.fsutil import now_iso, write_json
from workstream.project import Project

LATEST = "latest"
POST_MERGE = "post-merge"
TAIL_BYTES = 64 * 1024
LINE_WIDTH = 240
MAX_NEW_SHOWN = 20
TERMINATE_GRACE_SECONDS = 5


def runs_dir(project: Project, ws_id: str, task_id: str) -> Path:
    common = gitutil.common_dir(project.root)
    base = common / "workstream" if common else project.root / ".workstream"
    return base / "runs" / ws_id / task_id


def code_tree(project: Project, rev: str | None = None) -> str:
    """The hash of the code at rev, or of the working tree with no rev: what `git commit -a`
    plus every untracked file would give, without the tracking files. "" when git can't say.

    Works on a throwaway index, so nothing here touches the real one. It writes loose objects,
    which git collects like any others.
    """
    root = project.root
    rows = registry.load(project)["workstreams"]
    with tempfile.TemporaryDirectory(prefix="ws-index-") as tmp:
        index = Path(tmp) / "index"
        env = {**os.environ, "GIT_INDEX_FILE": str(index)}
        if rev is not None:
            steps = [("read-tree", rev)]
        else:
            real = gitutil.run(root, "rev-parse", "--git-path", "index").stdout.strip()
            if real and (root / real).exists():
                # Keeps the stat cache, so add -A stays quick, and the index's mtime: a newer copy
                # would stop git's racy check rereading a same-size edit, and hash HEAD's tree.
                shutil.copy2(root / real, index)
            steps = [("add", "-A")]
        # Forced: this index is meant to differ from HEAD, which `git rm` otherwise refuses.
        steps.append(("rm", "-r", "-q", "-f", "--cached", "--ignore-unmatch", "--",
                      *snapshot.tracking_paths(project, rows)))
        try:
            for step in steps:
                if gitutil.run(root, *step, env=env).returncode != 0:
                    return ""
            proc = gitutil.run(root, "write-tree", env=env)
        except OSError:
            return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def run_command(command: str, cwd: Path, log_path: Path, timeout: int) -> tuple[int | None, float]:
    """(exit code, seconds), with None for the code when it ran out of time. Output goes
    straight to the file: nothing buffers in memory however much a build prints, and a command
    that waits for input gets end-of-file rather than hanging."""
    log_path.parent.mkdir(parents=True, exist_ok=True)
    started = time.monotonic()
    with log_path.open("wb") as log:
        proc = subprocess.Popen(command, shell=True, cwd=cwd, stdin=subprocess.DEVNULL,
                                stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        try:
            code: int | None = proc.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            _kill_group(proc)
            code = None
        except BaseException:
            _kill_group(proc)
            raise
    return code, round(time.monotonic() - started, 1)


def _kill_group(proc: subprocess.Popen) -> None:
    """A build's children outlive a killed shell, so the whole process group goes."""
    for sig, wait in ((signal.SIGTERM, TERMINATE_GRACE_SECONDS), (signal.SIGKILL, None)):
        try:
            os.killpg(proc.pid, sig)
        except ProcessLookupError:
            return
        try:
            proc.wait(timeout=wait)
            return
        except subprocess.TimeoutExpired:
            continue


def read_log(path: Path) -> str:
    return path.read_text(errors="replace") if path.exists() else ""


def tail(path: Path, lines: int, width: int = LINE_WIDTH) -> list[str]:
    """The last lines of a log, each cut to width, read from the end of however large a file."""
    if not path.exists():
        return []
    with path.open("rb") as f:
        f.seek(0, os.SEEK_END)
        f.seek(max(0, f.tell() - TAIL_BYTES))
        text = f.read().decode(errors="replace")
    kept = [baseline.strip_ansi(line) for line in text.splitlines()][-lines:]
    return [line if len(line) <= width else line[:width] + "..." for line in kept]


def _log_name(label: str, record: str) -> str:
    """A file name for a key. A raw command also gets a hash, as two can share a prefix."""
    slug = re.sub(r"[^a-z0-9._-]+", "-", label.lower()).strip("-")[:40] or "command"
    if tasks.is_raw_command(label):
        slug += "-" + hashlib.sha256(label.encode()).hexdigest()[:8]
    return f"{record}-{slug}.log"


def run_one(project: Project, label: str, command: str, entry: dict, known: list[str],
            directory: Path, record: str) -> dict:
    """One command, run and judged. An empty command is a key the config doesn't have."""
    if not command:
        return {"key": label, "command": "", "exit": None, "seconds": 0, "verdict": baseline.FAIL,
                "reason": "not in [commands]", "new": [], "gone": 0, "known": 0, "log": ""}
    log_path = directory / _log_name(label, record)
    started = time.time()
    code, seconds = run_command(command, project.root, log_path, project.config.verify_timeout)
    findings, problem = baseline.read_findings(entry, read_log(log_path), project.root, started)
    judged = baseline.judge(code, entry, findings, problem, known)
    return {"key": label, "command": command, "exit": code, "seconds": seconds, **judged,
            "log": str(log_path)}


def load_run(project: Project, ws_id: str, task_id: str, record: str = LATEST) -> dict | None:
    path = runs_dir(project, ws_id, task_id) / f"{record}.json"
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except json.JSONDecodeError:
        return None  # an interrupted run: the same as not having verified
    return data if isinstance(data, dict) and isinstance(data.get("results"), list) else None


def verify_task(project: Project, ws: dict, task: dict, keys: list[str] | None = None,
                record: str = LATEST) -> dict:
    """Run the task's verify commands here and write the record. With keys, run only those and
    keep earlier results for the rest if the code hasn't changed since. Raises WsError if a key
    isn't one this task verifies with, since a result for it would prove nothing."""
    commands = tasks.verify_commands(task, project.config)
    labels = [label for label, _ in commands]
    unknown = [k for k in keys or [] if k not in labels]
    if unknown:
        raise WsError(f"{task['id']} does not verify with {', '.join(unknown)} "
                      f"(it has: {', '.join(labels) or 'nothing'})")
    tree = code_tree(project)
    directory = runs_dir(project, ws["id"], task["id"])
    directory.mkdir(parents=True, exist_ok=True)
    known_record = baseline.load_for(project, project.folder(ws))
    results = []
    for label, command in commands:
        if keys and label not in keys:
            continue
        entry = project.config.baseline_parsers.get(label, {"parser": baseline.EXIT_CODE})
        results.append(run_one(project, label, command, entry,
                               baseline.known_findings(known_record, label), directory, record))
    earlier = load_run(project, ws["id"], task["id"], record) if keys else None
    if earlier and earlier.get("tree") == tree:
        fresh = {r["key"] for r in results}
        results = [r for r in earlier["results"] if r["key"] not in fresh] + results
        results.sort(key=lambda r: labels.index(r["key"]) if r["key"] in labels else len(labels))
    # The tree is read again: a command that rewrites sources must not vouch for what it changed.
    after = code_tree(project)
    run = {"workstream": ws["id"], "task": task["id"], "tree": tree, "at": now_iso(),
           "branch": gitutil.current_branch(project.root), "results": results,
           "changedTree": bool(tree and after and tree != after)}
    run["missingOutput"] = missing_output(task, labels, results)
    run["problems"] = run_problems(run, labels)
    write_json(directory / f"{record}.json", run)
    return run


def missing_output(task: dict, labels: list[str], results: list[dict]) -> list[dict]:
    """Each acceptance item's expected literal that no log of this run holds. Waits until every
    key has a result on this tree, as a --key subset hasn't printed everything yet."""
    wanted = tasks.expected_outputs(task)
    current = [r for r in results if r["key"] in labels]
    if not wanted or {r["key"] for r in current} != set(labels):
        return []
    logs = [baseline.strip_ansi(read_log(Path(r["log"]))) for r in current if r.get("log")]
    return [{"item": n, "expect": literal} for n, literal in wanted
            if not any(literal in log for log in logs)]


def _missing_text(miss: dict) -> str:
    return (f"acceptance {miss['item']}: expected output not in the logs: "
            f"{miss['expect'][:LINE_WIDTH]}")


def run_problems(run: dict, labels: list[str]) -> list[str]:
    """Why this record doesn't show every one of these keys passing on one tree."""
    problems = [f"{r['key']}: {r.get('reason') or 'failed'}" for r in run.get("results", [])
                if r.get("verdict") == baseline.FAIL]
    seen = {r.get("key") for r in run.get("results", [])}
    problems += [f"{label}: not run" for label in labels if label not in seen]
    problems += [_missing_text(miss) for miss in run.get("missingOutput", [])]
    if run.get("changedTree"):
        problems.append("the commands changed the code they checked; commit that and verify again")
    return problems


def summary(run: dict, post_merge: str) -> dict:
    """What a settled task keeps in its queue: the log and the command stay out."""
    results = []
    for r in run.get("results", []):
        entry = {"key": r["key"], "exit": r.get("exit"), "verdict": r.get("verdict")}
        new = r.get("newCount", len(r.get("new", [])))
        if new:
            entry["new"] = new
        if r.get("known"):
            entry["known"] = r["known"]
        results.append(entry)
    return {"tree": run.get("tree", ""), "at": run.get("at", ""), "postMerge": post_merge,
            "results": results}


def format_run(run: dict, tail_lines: int) -> list[str]:
    """The lines an agent reads. Every part has a cap, so a failure can't flood its context."""
    results = run["results"]
    lines = [f"{run['task']}: verified at {run['tree'][:12] or '(no tree)'} on {run['branch'] or '?'}"]
    if not results:
        lines.append("  nothing to run: this task has no verify commands")
    for r in results:
        word = {"pass": "PASS", "known-only": "PASS", "fail": "FAIL"}[r["verdict"]]
        detail = f" ({r['reason']})" if r.get("reason") else ""
        lines.append(f"  {word} {r['key']}  {r.get('seconds', 0)}s{detail}")
        if r["verdict"] != baseline.FAIL:
            continue
        new = r.get("new", [])
        for finding in new[:MAX_NEW_SHOWN]:
            lines.append(f"    new: {finding[:LINE_WIDTH]}")
        total = r.get("newCount", len(new))
        if total > MAX_NEW_SHOWN:
            lines.append(f"    ...and {total - MAX_NEW_SHOWN} more")
        if not new and r.get("log"):
            lines += [f"    | {line}" for line in tail(Path(r["log"]), tail_lines)]
        if r.get("log"):
            lines.append(f"    full log: {r['log']}")
    lines += [f"  FAIL {_missing_text(miss)}" for miss in run.get("missingOutput", [])]
    if run.get("changedTree"):
        lines.append("  warning: the commands changed the code they checked")
    lines.append("OK" if not run["problems"] else f"FAIL: {len(run['problems'])} problem(s)")
    return lines


def record_baseline(project: Project, ws: dict, keys: list[str] | None) -> list[dict]:
    """Run commands on the tree as committed and record what they report.

    Refuses uncommitted code: findings from work in progress would pass as known forever. A
    plan's own files may be uncommitted, since this runs while it is being set up. Returns one
    {key, exit, findings, parser, problem} per command.
    """
    if code_tree(project) != code_tree(project, "HEAD"):
        raise WsError("a baseline is taken on a clean tree; commit or stash code changes first")
    config = project.config
    folder = project.folder(ws)
    queue = tasks.load(project.tasks_path(ws), config)["tasks"]
    chosen = keys or baseline.keys_to_record(config, queue)
    unknown = [k for k in chosen if k not in config.commands]
    if unknown:
        raise WsError(f"not in [commands]: {', '.join(unknown)}")
    directory = runs_dir(project, ws["id"], "_baseline")
    directory.mkdir(parents=True, exist_ok=True)
    report, recorded = [], {}
    for key in chosen:
        entry = config.baseline_parsers.get(key, {"parser": baseline.EXIT_CODE})
        log_path = directory / _log_name(key, "baseline")
        started = time.time()
        code, seconds = run_command(config.commands[key], project.root, log_path,
                                    config.verify_timeout)
        found, problem = baseline.read_findings(entry, read_log(log_path), project.root, started)
        recorded[key] = {"parser": entry["parser"], "command": config.commands[key], "exit": code,
                         "findings": sorted(found or [])}
        report.append({"key": key, "exit": code, "seconds": seconds, "parser": entry["parser"],
                       "findings": len(found or []), "problem": problem, "log": str(log_path)})
    baseline.write(project, folder, recorded)
    return report
