"""The `ws` command line. Parsing and printing only: every rule lives in the modules it calls.

Output is written for an agent's context as much as a person's eye: short by default, with
`--json` where a tool wants the data.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from workstream import act, graph, gitutil, registry, review, snapshot, tasks
from workstream import __version__
from workstream.errors import Refused, WsError
from workstream.project import Project, init_project, open_project


def _project(args: argparse.Namespace) -> Project:
    root = getattr(args, "root", None)
    return open_project(Path(root) if root else None)


def _resolve_ws(project: Project, args: argparse.Namespace) -> dict:
    """The workstream a command acts on: -w, else the folder we're standing in, else the only
    open one. Refuses and lists them rather than guessing."""
    data = registry.load(project)
    named = getattr(args, "workstream", None)
    if named:
        return registry.find(data, named)
    cwd = Path.cwd().resolve()
    for ws in data["workstreams"]:
        folder = project.folder(ws).resolve()
        if cwd == folder or folder in cwd.parents:
            return ws
    open_rows = [w for w in data["workstreams"] if w.get("status") in registry.OPEN_STATUSES]
    if len(open_rows) == 1:
        return open_rows[0]
    if not open_rows:
        raise WsError("no open workstream (see `ws list --all`; `ws new` makes one)")
    names = ", ".join(w["id"] for w in open_rows)
    raise WsError(f"several open workstreams, name one with -w: {names}")


def _queue(project: Project, args: argparse.Namespace) -> tuple[dict, Path]:
    ws = _resolve_ws(project, args)
    return ws, project.tasks_path(ws)


def _split(value: str | None) -> list[str]:
    if not value:
        return []
    return [v.strip() for v in value.split(",") if v.strip()]


def _print_report(errors: list[str], warnings: list[str], ok_line: str) -> int:
    """Errors exit 1 under FAIL; warnings print either way and never change the exit code."""
    if errors:
        print("FAIL:")
        for p in errors:
            print(f"  - {p}")
    if warnings:
        print("warnings:")
        for w in warnings:
            print(f"  - {w}")
    if errors:
        return 1
    print(ok_line + (f" ({len(warnings)} warning(s))" if warnings else ""))
    return 0


def _confirm(prompt: str, word: str) -> bool:
    """Ask for a typed word. With no terminal to answer, the answer is no."""
    if not sys.stdin.isatty():
        return False
    return input(f"{prompt} Type {word!r} to go ahead: ").strip() == word


# --- setup and the registry ---------------------------------------------------------------


def cmd_init(args: argparse.Namespace) -> int:
    root = Path(getattr(args, "root", None) or Path.cwd())
    if not args.force_no_git and gitutil.toplevel(root) is None:
        raise WsError(f"{root} is not a git repository (--no-git to set it up anyway)")
    project, created = init_project(root, args.integration)
    for path in created:
        print(f"created {path}")
    if not created:
        print("already set up")
    print(f"integration branch: {project.config.integration}")
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    project = _project(args)
    ws = registry.create(project, args.id, args.title, args.summary, prefix=args.prefix,
                         base=args.base, depends_on=args.depends_on, tier=args.tier,
                         under=args.under)
    print(f"created {ws['path']}/ and registered {ws['id']!r} as planned ({ws['tier']})")
    print("next: fill PLAN.md, `ws seed <file>`, then `ws validate`")
    return 0


def cmd_list(args: argparse.Namespace) -> int:
    rows = registry.load(_project(args))["workstreams"]
    if args.status:
        rows = [w for w in rows if w["status"] == args.status]
    elif not args.all:
        rows = [w for w in rows if w["status"] in registry.OPEN_STATUSES]
    if not rows:
        print("(no matching workstreams; `ws list --all` includes closed ones)")
        return 0
    width = max(len(w["id"]) for w in rows)
    for w in rows:
        p = w.get("progress") or {}
        print(f"{w['id']:<{width}}  {w['status']:<9}  {p.get('done', 0):>3}/{p.get('total', 0):<3}"
              f"  {w['title']}")
    return 0


def cmd_set_status(args: argparse.Namespace) -> int:
    project = _project(args)
    ws = registry.set_status(project, _resolve_ws(project, args)["id"], args.status, args.notes)
    print(f"{ws['id']}: status={ws['status']}")
    return 0


def cmd_sync(args: argparse.Namespace) -> int:
    for line in registry.sync(_project(args)):
        print(line)
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    project = _project(args)
    if getattr(args, "workstream", None):
        ws = registry.find(registry.load(project), args.workstream)
        ids = {w.get("id") for w in registry.load(project)["workstreams"]}
        errors, warnings = registry.validate_entry(project, ws, ids)
        return _print_report(errors, warnings, f"OK: {ws['id']}, no integrity problems")
    errors, warnings, count = registry.validate_all(project)
    return _print_report(errors, warnings, f"OK: {count} workstream(s), no integrity problems")


def cmd_reconcile(args: argparse.Namespace) -> int:
    added, differences = registry.reconcile(_project(args))
    for ws_id in added:
        print(f"registered {ws_id} (found in the tree, not in the registry)")
    for line in differences:
        print(f"difference: {line}")
    if not added and not differences:
        print("no differences")
    return 1 if differences else 0


def cmd_close(args: argparse.Namespace) -> int:
    project = _project(args)
    ws_id = _resolve_ws(project, args)["id"]
    plan = registry.close_plan(project, ws_id, allow_deferred=args.allow_deferred)
    destructive = args.prune or args.purge
    removes = ("the whole folder" if args.purge
               else "the queue and handoff" if args.prune else "nothing")
    print(f"{ws_id}: {plan['tasks']} task(s), closing removes {removes}")
    if args.dry_run:
        return 0
    if destructive and not args.yes and not _confirm(
            "This cannot be undone unless it is committed.", "close"):
        raise Refused("not closed (destructive close needs confirmation or --yes)")
    registry.close(project, ws_id, allow_deferred=args.allow_deferred, prune=args.prune,
                   purge=args.purge)
    print(f"{ws_id}: closed; commit the change")
    return 0


# --- the queue ----------------------------------------------------------------------------


def cmd_seed(args: argparse.Namespace) -> int:
    project = _project(args)
    ws, path = _queue(project, args)
    try:
        with open(args.seed_file) as f:
            new_tasks = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise WsError(f"cannot read {args.seed_file}: {e}") from None
    total = tasks.seed(path, new_tasks, project.config)
    print(f"seeded {len(new_tasks)} task(s) into {ws['id']} ({total} total)")
    return 0


def cmd_add(args: argparse.Namespace) -> int:
    project = _project(args)
    _, path = _queue(project, args)
    fields = {
        "id": args.id, "phase": args.phase, "priority": args.priority, "title": args.title,
        "kind": args.kind or "", "findings": _split(args.findings), "summary": args.summary or "",
        "files": _split(args.files), "docs": _split(args.docs),
        "acceptance": args.acceptance or [], "verify": args.verify or [],
        "branch": args.branch or "", "blockedBy": _split(args.blocked_by),
        "needsUserDecision": args.needs_user_decision, "notes": args.notes or "",
        "requires": _split(args.requires), "releaseImpact": args.release_impact,
    }
    if args.mode:
        fields["mode"] = args.mode
    task = tasks.add(path, fields, project.config)
    print(f"added {task['id']}")
    return 0


def cmd_update(args: argparse.Namespace) -> int:
    project = _project(args)
    _, path = _queue(project, args)
    requires = _split(args.requires) if args.requires is not None else None
    task = tasks.update(path, args.id, project.config, status=args.status, commit=args.commit,
                        notes=args.notes, requires=requires, mode=args.mode,
                        release_impact=args.release_impact, verify=args.verify)
    print(f"updated {task['id']}: status={task['status']}")
    return 0


def cmd_tasks(args: argparse.Namespace) -> int:
    project = _project(args)
    _, path = _queue(project, args)
    rows = tasks.load(path, project.config)["tasks"]
    rows = sorted(rows, key=lambda t: t["priority"])
    if args.phase is not None:
        rows = [t for t in rows if t["phase"] == args.phase]
    if args.status is not None:
        rows = [t for t in rows if t["status"] == args.status]
    if not rows:
        print("(no matching tasks)")
        return 0
    id_w = max(len(t["id"]) for t in rows)
    status_w = max(len(t["status"]) for t in rows)
    for t in rows:
        print(f"{t['id']:<{id_w}}  phase={t['phase']}  priority={t['priority']:<4}"
              f"  {t['status']:<{status_w}}  {t['title']}")
    return 0


def _acceptance_text(item: object) -> str:
    if isinstance(item, dict):
        suffix = " (manual)" if item.get("kind") == "manual" else ""
        return f"{item.get('text', '')}{suffix}"
    return str(item)


def _print_task(task: dict, all_tasks: list[dict], config) -> None:
    """One task for a reader about to work on it. Empty fields are left out."""
    print(f"{task['id']}  {task['status']}  phase {task['phase']}  priority {task['priority']}"
          f"  {task['mode']}")
    print(task["title"])
    if task.get("summary"):
        print(f"\n{task['summary']}")
    print()
    if task.get("blockedBy"):
        print(f"waits on: {', '.join(task['blockedBy'])}")
    direct = [t["id"] for t in all_tasks if task["id"] in t.get("blockedBy", [])]
    if direct:
        print(f"unblocks: {', '.join(direct)}")
    for label, field in (("kind", "kind"), ("branch", "branch"), ("needs", "requires"),
                         ("cites", "findings"), ("files", "files"), ("docs", "docs")):
        value = task.get(field)
        if value:
            print(f"{label}: {', '.join(value) if isinstance(value, list) else value}")
    if task.get("needsUserDecision"):
        print("needs a user decision")
    if task.get("acceptance"):
        print("acceptance:")
        for n, item in enumerate(task["acceptance"], 1):
            print(f"  {n}. {_acceptance_text(item)}")
    commands = tasks.verify_commands(task, config)
    if commands:
        print("verify:")
        for label, command in commands:
            print(f"  {command}" if label == command
                  else f"  {label}: {command or '(not in [commands])'}")
    if task.get("notes"):
        print(f"notes: {task['notes']}")
    claim = [f"{k}={task[k]}" for k in ("claimedBy", "baseCommit", "commit") if task.get(k)]
    if claim:
        print(" ".join(claim))


def cmd_show(args: argparse.Namespace) -> int:
    project = _project(args)
    _, path = _queue(project, args)
    data = tasks.load(path, project.config)
    task = tasks.find_task_by_prefix(data, args.id)
    if args.json:
        print(json.dumps(task, indent=2))
    else:
        _print_task(task, data["tasks"], project.config)
    return 0


def cmd_next(args: argparse.Namespace) -> int:
    project = _project(args)
    _, path = _queue(project, args)
    data = tasks.load(path, project.config)
    candidates = graph.actionable(data["tasks"])
    if not candidates:
        print("(no actionable task: everything is done, blocked, or needs a user decision)")
        return 0
    task = min(candidates, key=lambda t: t["priority"])
    if args.json:
        print(json.dumps(task, indent=2))
    else:
        _print_task(task, data["tasks"], project.config)
    return 0


def _print_leftovers(rows: list[dict]) -> None:
    """Every in-progress task, with its claim: finished work to merge, or a stale claim to
    `unclaim`. Prints nothing when no task is in progress."""
    leftovers = [t for t in rows if t["status"] == "in-progress"]
    if not leftovers:
        return
    print(f"leftovers: {len(leftovers)} in progress (merge it, or unclaim it to requeue)")
    for t in leftovers:
        print(f"  {t['id']}  phase={t['phase']}  claimedBy={t.get('claimedBy') or '-'}"
              f"  baseCommit={t.get('baseCommit') or '-'}  {t['title']}")


def cmd_wave(args: argparse.Namespace) -> int:
    """Print the wave and exit with its code (0 ready, 2 finished, 3 stuck). In-progress
    tasks are listed after it under a leftovers heading and never change the code."""
    project = _project(args)
    _, path = _queue(project, args)
    rows = sorted(tasks.load(path, project.config)["tasks"], key=lambda t: t["priority"])
    by_id = {t["id"]: t for t in rows}
    wave = graph.compute_wave(rows)
    if wave["state"] == "finished":
        print("(queue finished: every task is done or deferred)")
        return graph.WAVE_FINISHED
    if wave["state"] == "stuck":
        print("(stuck: open tasks remain but none is actionable)")
        for t in (by_id[i] for i in wave["open"]):
            reason = "needsUserDecision" if t.get("needsUserDecision") else t["status"]
            print(f"  {t['id']}  phase={t['phase']}  {reason}  {t['title']}")
        _print_leftovers(rows)
        return graph.WAVE_STUCK
    print(f"phase {wave['phase']}: {len(wave['ids'])} actionable, {len(wave['open'])} open in total")
    for t in (by_id[i] for i in wave["ids"]):
        print(f"  {t['id']}  priority={t['priority']:<4}  mode={t['mode']:<10}  {t['title']}")
        if t.get("requires"):
            print(f"      requires: {', '.join(t['requires'])}")
        if t.get("files"):
            print(f"      files: {', '.join(t['files'])}")
        if t.get("notes"):
            print(f"      notes: {t['notes']}")
    for a, b, overlap in wave["overlaps"]:
        print(f"  warning: {graph.overlap_warning(a, b, overlap)}")
    _print_leftovers(rows)
    return graph.WAVE_READY


def cmd_status(args: argparse.Namespace) -> int:
    project = _project(args)
    ws, path = _queue(project, args)
    print(f"{ws['id']}  {ws['status']}  {ws['title']}")
    if not path.exists():
        p = ws.get("progress") or {}
        print(f"{p.get('done', 0)}/{p.get('total', 0)} done; the queue was pruned at close")
        return 0
    rows = sorted(tasks.load(path, project.config)["tasks"], key=lambda t: t["priority"])
    p = registry.count_progress(rows)
    counts = "  ".join(f"{s}={p[s]}" for s in tasks.STATUS_VALUES if p.get(s))
    print(f"{p['total']} tasks  {counts}".rstrip())
    wave = graph.compute_wave(rows)
    if wave["state"] == "ready":
        print(f"ready (phase {wave['phase']}): {', '.join(wave['ids'])}")
    elif wave["state"] == "stuck" and wave["leftovers"]:
        print("in progress; nothing else is ready")
    else:
        print(wave["state"])
    _print_leftovers(rows)
    return 0


def cmd_graph(args: argparse.Namespace) -> int:
    project = _project(args)
    _, path = _queue(project, args)
    rows = sorted(tasks.load(path, project.config)["tasks"], key=lambda t: t["priority"])
    by_id = {t["id"]: t for t in rows}
    children: dict[str, list[str]] = {t["id"]: [] for t in rows}
    for t in rows:
        for b in t.get("blockedBy", []):
            if b in children:
                children[b].append(t["id"])
    seen: set[str] = set()

    def draw(task_id: str, depth: int) -> None:
        t = by_id[task_id]
        again = " (see above)" if task_id in seen else ""
        print(f"{'  ' * depth}{task_id} [{t['status']}] {t['title']}{again}")
        if not again:
            seen.add(task_id)
            for child in children[task_id]:
                draw(child, depth + 1)

    for t in rows:
        if not [b for b in t.get("blockedBy", []) if b in children]:
            draw(t["id"], 0)
    for t in rows:  # a cycle has no root to reach it from
        if t["id"] not in seen:
            draw(t["id"], 0)
    return 0


def cmd_claim(args: argparse.Namespace) -> int:
    project = _project(args)
    _, path = _queue(project, args)
    base = args.base if args.base is not None else gitutil.rev_parse(project.root, "HEAD")
    ids = tasks.claim(path, args.ids, base, args.by, project.config)
    print(f"claimed {', '.join(ids)} at {base}" + (f" for {args.by}" if args.by else ""))
    return 0


def cmd_unclaim(args: argparse.Namespace) -> int:
    project = _project(args)
    _, path = _queue(project, args)
    ids = tasks.unclaim(path, args.ids, project.config)
    print(f"unclaimed {', '.join(ids)}: back to todo")
    return 0


def cmd_reset(args: argparse.Namespace) -> int:
    project = _project(args)
    _, path = _queue(project, args)
    data = tasks.load(path, project.config)
    planned = tasks.reset_plan(data, args.ids, args.cascade)
    if not planned:
        print("nothing to reset")
        return 0
    print(f"reset would clear: {', '.join(planned)}")
    if args.dry_run:
        return 0
    if not args.yes and not _confirm("This discards the record of what was done.", "reset"):
        raise Refused("not reset (needs confirmation or --yes)")
    tasks.reset(path, args.ids, args.cascade, project.config)
    print(f"reset {len(planned)} task(s) to todo")
    return 0


# --- the UI contract ----------------------------------------------------------------------


def cmd_snapshot(args: argparse.Namespace) -> int:
    project = _project(args)
    data = snapshot.build_snapshot(project, getattr(args, "workstream", None), args.stale_hours)
    print(json.dumps(data, indent=2))
    return 0


def cmd_act(args: argparse.Namespace) -> int:
    project = _project(args)
    ws_id = getattr(args, "workstream", None)
    if not ws_id:
        raise Refused("act needs -w: a write names its workstream")
    print(act.act(project, args.action, ws_id, task=args.task, notes=args.notes,
                  expect_registry=args.expect_registry, expect_tasks=args.expect_tasks))
    return 0


def cmd_review(args: argparse.Namespace) -> int:
    project = _project(args)
    if args.max_lines < 1:
        raise WsError("--max-lines must be at least 1")
    ws = _resolve_ws(project, args)
    print(json.dumps(review.build_review(project, ws["id"], args.task, args.file, args.max_lines),
                     indent=2))
    return 0


# --- the parser ---------------------------------------------------------------------------


def _add_typed_arguments(p: argparse.ArgumentParser) -> None:
    p.add_argument("--mode", choices=tasks.MODE_VALUES,
                   help="default background; a requirement that forces it makes it foreground")
    p.add_argument("--requires", help="comma-separated; the project's config lists the values")
    p.add_argument("--release-impact", choices=tasks.RELEASE_IMPACT_VALUES)


def build_parser() -> argparse.ArgumentParser:
    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("-w", "--workstream", default=argparse.SUPPRESS,
                        help="workstream id (default: the folder you're in, or the only open one)")
    common.add_argument("--root", default=argparse.SUPPRESS,
                        help="project root (default: found from the working directory)")

    parser = argparse.ArgumentParser(
        prog="ws", parents=[common],
        description="Run large bodies of work with coding agents: a task graph in your repo.")
    parser.add_argument("--version", action="version", version=f"ws {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    def command(name: str, func, help_text: str) -> argparse.ArgumentParser:
        p = sub.add_parser(name, parents=[common], help=help_text)
        p.set_defaults(func=func)
        return p

    p = command("init", cmd_init, "set up .workstream/config.toml and an empty registry")
    p.add_argument("--integration", help="the branch task branches merge into")
    p.add_argument("--no-git", dest="force_no_git", action="store_true",
                   help="set up outside a git repository")

    p = command("new", cmd_new, "scaffold a workstream folder and register it as planned")
    p.add_argument("id", help="lower-case folder name, e.g. smart_playlists")
    p.add_argument("--title", required=True)
    p.add_argument("--summary", required=True, help="one or two sentences: the outcome")
    p.add_argument("--prefix", help="task id prefix, e.g. SP -> SP-01")
    p.add_argument("--base", help="commit the plan was written against "
                                  "(default: the integration branch)")
    p.add_argument("--depends-on", action="append", help="workstream id; repeatable")
    p.add_argument("--tier", choices=tasks.TIERS, default="standard")
    p.add_argument("--under", help="module folder to place it under: <under>/workstreams/<id>")

    p = command("list", cmd_list, "open workstreams with progress")
    p.add_argument("--status", choices=registry.STATUS_VALUES)
    p.add_argument("--all", action="store_true", help="include done and abandoned")

    p = command("set-status", cmd_set_status, "pause, resume or abandon a workstream")
    p.add_argument("status", choices=registry.SETTABLE_STATUSES)
    p.add_argument("--notes")

    command("sync", cmd_sync, "refresh registry progress from every queue")
    command("validate", cmd_validate, "integrity check; -w for one workstream, else everything")
    command("reconcile", cmd_reconcile, "registry against the tree: registers unknown queues, "
                                        "reports every other difference (exit 1 if any)")

    p = command("close", cmd_close, "mark a finished workstream done; its registry row survives")
    p.add_argument("--allow-deferred", action="store_true")
    p.add_argument("--prune", action="store_true", help="also remove the queue and the handoff")
    p.add_argument("--purge", action="store_true", help="also remove the whole folder")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-y", "--yes", action="store_true")

    p = command("seed", cmd_seed, "bulk-load an array of task objects from a JSON file")
    p.add_argument("seed_file")

    p = command("add", cmd_add, "append a single task")
    p.add_argument("--id", required=True)
    p.add_argument("--phase", required=True, type=int)
    p.add_argument("--priority", required=True, type=int)
    p.add_argument("--title", required=True)
    p.add_argument("--kind")
    p.add_argument("--findings", help="comma-separated")
    p.add_argument("--summary")
    p.add_argument("--files", help="comma-separated")
    p.add_argument("--docs", help="comma-separated")
    p.add_argument("--acceptance", action="append", help="repeatable")
    p.add_argument("--verify", action="append", help="command key or raw command; repeatable")
    p.add_argument("--branch")
    p.add_argument("--blocked-by", help="comma-separated task ids")
    p.add_argument("--needs-user-decision", action="store_true")
    p.add_argument("--notes")
    _add_typed_arguments(p)

    p = command("update", cmd_update, "transition or annotate one task")
    p.add_argument("id")
    p.add_argument("--status")
    p.add_argument("--commit")
    p.add_argument("--notes")
    p.add_argument("--verify", action="append", help="replaces the list; repeatable")
    _add_typed_arguments(p)

    p = command("tasks", cmd_tasks, "one line per task, by priority")
    p.add_argument("--phase", type=int)
    p.add_argument("--status")

    p = command("show", cmd_show, "one task: detail, resolved verify commands, what it unblocks")
    p.add_argument("id", help="task id, or a unique prefix of one")
    p.add_argument("--json", action="store_true")

    p = command("next", cmd_next, "the lowest-priority actionable task")
    p.add_argument("--json", action="store_true")

    command("wave", cmd_wave, "every actionable task in the lowest phase that has one "
                              "(exit 0 ready, 2 finished, 3 stuck)")
    command("status", cmd_status, "where one workstream stands")
    command("graph", cmd_graph, "the dependency tree")

    p = command("claim", cmd_claim, "start a batch: every id must be actionable or nothing changes")
    p.add_argument("--base", help="the commit the tasks branch from (default: HEAD)")
    p.add_argument("--by", help="who works the batch, e.g. a session or agent label")
    p.add_argument("ids", nargs="+", metavar="ID")

    p = command("unclaim", cmd_unclaim, "requeue in-progress or blocked tasks (all-or-nothing)")
    p.add_argument("ids", nargs="+", metavar="ID")

    p = command("reset", cmd_reset, "replay: tasks back to todo, run-time state cleared")
    p.add_argument("ids", nargs="*", metavar="ID", help="default: every task")
    p.add_argument("--cascade", action="store_true", help="and everything that depends on them")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-y", "--yes", action="store_true")

    p = command("snapshot", cmd_snapshot, "the read model as JSON; with -w also that workstream's "
                                          "tasks, wave and narrative paths")
    p.add_argument("--stale-hours", type=float, default=snapshot.DEFAULT_STALE_HOURS,
                   help="an in-progress claim older than this is a stale-claim finding")

    p = command("act", cmd_act, "a UI's only write: refuse, run and commit one of "
                                "pause/resume/unclaim/sync")
    p.add_argument("action", choices=act.ACTIONS)
    p.add_argument("--task", help="task id (unclaim only)")
    p.add_argument("--notes", help="registry notes (pause and resume only)")
    p.add_argument("--expect-registry", required=True,
                   help="sha256 of the registry as drawn (snapshot revisions.registry)")
    p.add_argument("--expect-tasks",
                   help="sha256 of the queue as drawn (snapshot revisions.tasks); "
                        "required for unclaim")

    p = command("review", cmd_review, "one task's review data as JSON: evidence path, diff range "
                                      "and diffstat; with --file also that file's hunks")
    p.add_argument("task", help="task id")
    p.add_argument("--file", help="a path from the diffstat to include the hunks of")
    p.add_argument("--max-lines", type=int, default=review.DEFAULT_MAX_LINES,
                   help="cap on the hunks' lines; whole hunks only, `truncated` when cut")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    except WsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1
