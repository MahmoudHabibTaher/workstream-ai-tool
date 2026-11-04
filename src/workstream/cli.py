"""The `ws` command line. Parsing and printing only: every rule lives in the modules it calls.

Output is written for an agent's context as much as a person's eye: short by default, with
`--json` where a tool wants the data.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from pathlib import Path

from workstream import act, adapt, adopt, audit, baseline, brief, decisions, doctor, evidence, gates, graph
from workstream import gitutil, handoff, hook, importer, plan, protocol, registry, review, settle, snapshot, tasks, verify
from workstream import usage, worktree
from workstream import __version__
from workstream.errors import Refused, WsError
from workstream.fsutil import today
from workstream.project import Project, open_project


def _project(args: argparse.Namespace) -> Project:
    root = getattr(args, "root", None)
    return open_project(Path(root) if root else None)


def _resolve_ws(project: Project, args: argparse.Namespace, here: Project | None = None) -> dict:
    """The workstream a command acts on: -w, else the folder we're standing in, else the only
    open one. Refuses and lists them rather than guessing. `here` is the checkout the command ran
    in, when project is another one: that's where a folder we're standing in would be."""
    data = registry.load(project)
    named = getattr(args, "workstream", None)
    if named:
        return registry.find(data, named)
    cwd = Path.cwd().resolve()
    for ws in data["workstreams"]:
        for checkout in (project, here or project):
            folder = checkout.folder(ws).resolve()
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


def _tracking(args: argparse.Namespace) -> tuple[Project, dict, Path]:
    """The project, workstream and queue as the integration checkout has them, uncommitted changes
    included. A worktree's copies stop at its claim, so they miss what was decided since."""
    here = _project(args)
    source = open_project(worktree.integration_checkout(here))
    ws = _resolve_ws(source, args, here)
    return source, ws, source.tasks_path(ws)


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
    has_git = gitutil.toplevel(root) is not None
    if not args.force_no_git and not has_git:
        raise WsError(f"{root} is not a git repository (--no-git to set it up anyway)")
    result = adopt.adopt(root, args.integration, args.production, args.profile,
                         run=has_git and not args.no_run, timeout=args.timeout,
                         say=lambda line: print(line, flush=True))
    if result["profile"]:
        also = f" (also matches {', '.join(result['others'])}; --profile picks another)" \
            if result["others"] else ""
        print(f"profile: {result['profile']}{also}")
    for key, command in result["active"].items():
        known = len(result["known"].get(key, []))
        print(f"  on   {key}: {command}" + (f" ({known} known finding(s) recorded)" if known else ""))
    for key, (command, why) in result["unverified"].items():
        print(f"  off  {key}: {command}: {why}")
    if result["left"]:
        shown = ", ".join(result["left"][:8])
        print(f"the commands left new files: {shown}; commit or ignore them before starting work")
    for path in result["created"]:
        print(f"created {path}")
    if not result["created"]:
        print("already set up")
    print(f"integration branch: {result['project'].config.integration}")
    if result["created"] and has_git:
        print("commit .workstream/ and the registry; `ws doctor` checks the setup")
    return 0


def cmd_adapt(args: argparse.Namespace) -> int:
    project = _project(args)
    if args.agent is None:
        print(f"agents: {', '.join(adapt.names())}; adapted here: "
              f"{', '.join(adapt.adapted(project)) or 'none'}")
        return 0
    if args.plugin:
        for rel in adapt.write_plugin(args.agent, Path(args.plugin), bool(args.hook)):
            print(f"wrote {rel}")
        return 0
    if args.check:
        wrong = [f"{rel}: {state}" for rel, state
                 in adapt.file_states(project, adapt.load(args.agent)).items()
                 if state != adapt.CURRENT]
        for line in wrong:
            print(f"  {line}")
        print(f"FAIL: `ws adapt {args.agent}` refreshes these" if wrong else "OK")
        return 1 if wrong else 0
    result = adapt.adapt(project, args.agent, force=args.force, hook=args.hook)
    for rel in result["wrote"]:
        print(f"wrote {rel}")
    print(f"{args.agent}: {len(result['wrote'])} written, {len(result['same'])} unchanged"
          + ("; commit them" if result["wrote"] else ""))
    return 0


def cmd_hook(args: argparse.Namespace) -> int:
    """Only a real decision may stop an agent: on one of them any failure here would deny."""
    reason = hook.decide(sys.stdin.read())
    if reason is None:
        return 0
    if args.format == hook.EXIT_CODE:
        print(reason, file=sys.stderr)
        return 2
    print(json.dumps({"permissionDecision": "deny", "permissionDecisionReason": reason}))
    return 0


def cmd_doctor(args: argparse.Namespace) -> int:
    root = getattr(args, "root", None)
    found = doctor.doctor(Path(root) if root else Path.cwd(), run=args.run,
                          ws_id=getattr(args, "workstream", None))
    if args.json:
        print(json.dumps(found, indent=2))
    else:
        _print_gates(found)
    if gates.blockers(found):
        if not args.json:
            print("FAIL")
        return 1
    if not args.json:
        print("OK")
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
        return _print_report(errors, registry.collapse_missing_files(warnings),
                             f"OK: {ws['id']}, no integrity problems")
    errors, warnings, count = registry.validate_all(project)
    return _print_report(errors, registry.collapse_missing_files(warnings),
                         f"OK: {count} workstream(s), no integrity problems")


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
    ws = registry.find(registry.load(project), ws_id)
    if ws.get("tier") == tasks.RELEASING_TIER:
        _print_release(project, tasks.load(project.tasks_path(ws), project.config)["tasks"])
    registry.close(project, ws_id, allow_deferred=args.allow_deferred, prune=args.prune,
                   purge=args.purge)
    print(f"{ws_id}: closed; commit the change")
    return 0


# --- the queue ----------------------------------------------------------------------------


def cmd_seed(args: argparse.Namespace) -> int:
    project = _project(args)
    ws, path = _queue(project, args)
    if bool(args.seed_file) == bool(args.from_plan):
        raise WsError("seed takes a JSON file or --from-plan <plan.md>, one of them")
    if args.from_plan:
        try:
            text = Path(args.from_plan).read_text()
        except OSError as e:
            raise WsError(f"cannot read {args.from_plan}: {e}") from None
        added, warnings = plan.seed_from_plan(project, ws, text, force=args.force)
        for w in warnings:
            print(f"warning: {w}")
        print(f"seeded {added} task(s) and PLAN.md into {ws['id']}")
        registry.sync(project)  # or `ws reconcile`, a coordinator's first check, starts out failing
        return 0
    try:
        with open(args.seed_file) as f:
            new_tasks = json.load(f)
    except (OSError, json.JSONDecodeError) as e:
        raise WsError(f"cannot read {args.seed_file}: {e}") from None
    total = tasks.seed(path, new_tasks, project.config)
    print(f"seeded {len(new_tasks)} task(s) into {ws['id']} ({total} total)")
    registry.sync(project)
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
    registry.sync(project)
    print(f"added {task['id']}")
    return 0


def _correct(project: Project, ws: dict, path: Path, args: argparse.Namespace, flag: str,
             what: str, change: Callable[[], object]) -> None:
    """Apply a correction that names its decision: `change` writes it, `what` labels it."""
    others = (args.status, args.notes, args.verify, args.mode, args.requires, args.release_impact)
    both = args.acceptance is not None and args.summary is not None
    if both or any(v is not None for v in others):
        raise Refused(f"{flag} goes alone: run any other change as its own `ws update`")
    if isinstance(args.commit, str):
        raise Refused(f"--commit takes no hash with {flag}: it commits the queue")
    if not args.because:
        raise Refused(f"{flag} needs --because <Dnnn>, the decision that changed it")
    log = project.folder(ws) / "DECISIONS.md"
    known = {e["id"] for e in decisions.parse(log.read_text())} if log.exists() else set()
    if args.because not in known:
        raise Refused(f"no decision {args.because} in {project.rel(log)}")
    if not args.commit:
        change()
        print(f"updated {args.id}: {what}, {args.because}; commit it")
        return
    rows = registry.load(project)["workstreams"]
    act.check_checkout(project, snapshot.git_facts(project, rows), "update", ws["id"], rows)
    before = path.read_bytes()
    try:
        change()
        short = act.commit(project, [path], f"{ws['id']}: {args.id} {what}, {args.because}")
    except BaseException:
        act.restore({path: before})
        raise
    print(f"updated {args.id}: {what}, {args.because}; committed {short}")


def _correct_acceptance(project: Project, ws: dict, path: Path, args: argparse.Namespace) -> None:
    number, text = args.acceptance
    _correct(project, ws, path, args, "--acceptance", f"acceptance {number}",
             lambda: tasks.correct_acceptance(path, args.id, number, text, args.because,
                                              project.config))


def _correct_summary(project: Project, ws: dict, path: Path, args: argparse.Namespace) -> None:
    _correct(project, ws, path, args, "--summary", "summary",
             lambda: tasks.correct_summary(path, args.id, args.summary, args.because,
                                           project.config))


def cmd_update(args: argparse.Namespace) -> int:
    project = _project(args)
    ws, path = _queue(project, args)
    if args.acceptance:
        _correct_acceptance(project, ws, path, args)
        return 0
    if args.summary is not None:  # empty text reaches the refusal, rather than a plain update
        _correct_summary(project, ws, path, args)
        return 0
    if args.because:
        raise Refused("--because goes with --acceptance or --summary")
    if args.commit is True:
        raise Refused("--commit needs a hash, except with --acceptance or --summary")
    requires = _split(args.requires) if args.requires is not None else None
    if args.status == "done":
        landed = args.commit or tasks.find_task(tasks.load(path, project.config), args.id).get("commit")
        if landed and not gitutil.is_ancestor(project.root, landed, project.config.integration):
            raise Refused(f"{args.id} isn't on {project.config.integration} yet: `ws settle {args.id}` "
                          "lands a task and marks it done")
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


def _print_task(task: dict, all_tasks: list[dict], config) -> None:
    """One task for a reader about to work on it. Empty fields are left out."""
    print(f"{task['id']}  {task['status']}  phase {task['phase']}  priority {task['priority']}"
          f"  {task['mode']}")
    print(task["title"])
    if task.get("summary"):
        print(f"\n{task['summary']}")
    print()
    if task.get("blockedReason"):
        print(f"blocked: {task['blockedReason']}")
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
            print(f"  {n}. {tasks.acceptance_text(item)}")
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
    holds = graph.file_holds(candidates, data["tasks"])
    held = {hold["id"] for hold in holds}
    free = [t for t in candidates if t["id"] not in held]
    if holds and not free:
        print("(no actionable task: every candidate is held back)")
        _print_held(holds)
        return 0
    if not free:
        print("(no actionable task: everything is done, blocked, or needs a user decision)")
        return 0
    task = min(free, key=lambda t: t["priority"])
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


def _print_held(holds: list[dict]) -> None:
    """Each task held back by a shared file, with what holds it. Prints nothing when none is."""
    if holds:
        print(f"held back: {len({h['id'] for h in holds})} sharing files with unfinished work")
        for hold in holds:
            print(f"  {hold['id']}  shares {hold['path']} with {hold['by']}")


def _print_held_and_blocked(rows: list[dict], wave: dict) -> None:
    """What the wave can't offer and why: tasks held back by a shared file, and blocked tasks
    with their reason. Prints nothing when there are neither."""
    _print_held(wave["heldBack"])
    blocked =[t for t in rows if t["status"] == "blocked"]
    if blocked:
        print(f"blocked: {len(blocked)}")
        for t in blocked:
            reason = t.get("blockedReason") or t.get("notes") or t["title"]
            print(f"  {t['id']}  phase={t['phase']}  {reason}")


def cmd_wave(args: argparse.Namespace) -> int:
    """Print the wave and exit with its code (0 ready, 2 finished, 3 stuck). Held-back, blocked
    and in-progress tasks are listed after it, each under its own heading."""
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
        _print_held_and_blocked(rows, wave)
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
    _print_held_and_blocked(rows, wave)
    _print_leftovers(rows)
    return graph.WAVE_READY


def _print_release(project: Project, rows: list[dict]) -> None:
    bump, unset = registry.release_bump(rows)
    print(f"release: {bump}, runbook {project.config.release_runbook or '(none named)'}")
    if unset:
        print(f"  done without a releaseImpact: {', '.join(unset)}")


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
    if ws.get("tier") == tasks.RELEASING_TIER:
        _print_release(project, rows)
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
    ws, path = _queue(project, args)
    registry.check_claimable(project, ws)
    if args.commit:
        base, short = act.commit_claim(project, ws, args.ids, args.base, args.by)
        print(f"claimed {', '.join(args.ids)} at {base}; committed {short}")
        return 0
    base = args.base if args.base is not None else gitutil.rev_parse(project.root, "HEAD")
    ids = tasks.claim(path, args.ids, base, args.by, project.config)
    print(f"claimed {', '.join(ids)} at {base}" + (f" for {args.by}" if args.by else ""))
    return 0


def cmd_unclaim(args: argparse.Namespace) -> int:
    project = _project(args)
    _, path = _queue(project, args)
    ids = tasks.unclaim(path, args.ids, project.config)
    registry.sync(project)
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


# --- running a task -----------------------------------------------------------------------


def _at_task(args: argparse.Namespace) -> tuple[Project, dict, dict]:
    """The project and workstream opened where the task's work is, and the task as the integration
    checkout defines it. A worker's shell doesn't always stay in its worktree, and a check of the
    wrong checkout looks just like a real one. The worktree's copy of the task stops at its claim,
    so `ws verify` would run an old list while `ws settle` reads the new one."""
    source, row, path = _tracking(args)
    task = tasks.find_task(tasks.load(path, source.config), args.id)
    project = _project(args)
    where = worktree.for_branch(project, task.get("branch") or project.config.branch_for(task["id"]))
    if where and Path(where).resolve() != project.root.resolve():
        print(f"(in {where})", file=sys.stderr)
        project = open_project(Path(where))
    return project, registry.find(registry.load(project), row["id"]), task


def cmd_verify(args: argparse.Namespace) -> int:
    project, ws, task = _at_task(args)
    run = verify.verify_task(project, ws, task, keys=args.key)
    if args.json:
        print(json.dumps(run, indent=2))
    else:
        print("\n".join(verify.format_run(run, project.config.tail_lines)))
    return 1 if run["problems"] else 0


def cmd_baseline(args: argparse.Namespace) -> int:
    project = _project(args)
    ws, _ = _queue(project, args)
    if args.action == "show":
        record = baseline.load_for(project, project.folder(ws))
        if not record["keys"]:
            print("(no baseline recorded; everything a command reports counts as new)")
            return 0
        print(f"recorded at {record.get('commit', '?')[:10]} on {record.get('recordedAt', '?')}")
        for key, entry in sorted(record["keys"].items()):
            print(f"  {key}: exit {entry.get('exit')}, {len(entry.get('findings', []))} known, "
                  f"parser {entry.get('parser')}")
        return 0
    results = verify.record_baseline(project, ws, args.keys)
    if not results:
        print("nothing to record: no open task verifies with a named command")
        return 0
    for r in results:
        print(f"  {r['key']}: exit {r['exit']}, {r['findings']} finding(s), {r['seconds']}s")
        if r["problem"]:
            print(f"    warning: {r['problem']}")
        elif r["exit"] != 0 and r["parser"] == baseline.EXIT_CODE:
            print(f"    warning: it fails, and the exit-code parser can't tell new failures from "
                  f"old, so a task verifying with {r['key']} can't pass. Fix it, or configure "
                  f"[baseline.{r['key']}]. Log: {r['log']}")
    print(f"wrote {project.rel(baseline.path_for(project.folder(ws)))}; commit it")
    return 0


def cmd_brief(args: argparse.Namespace) -> int:
    project, ws, path = _tracking(args)
    data = tasks.load(path, project.config)
    task = tasks.find_task_by_prefix(data, args.id)
    print(brief.render(project, ws, task, data["tasks"], args.max_chars, scope=data.get("scope")),
          end="")
    return 0


def cmd_decisions(args: argparse.Namespace) -> int:
    project, ws, path = _tracking(args)
    file = project.folder(ws) / "DECISIONS.md"
    entries = decisions.parse(file.read_text()) if file.exists() else []
    if args.open:  # before --for: whether an entry is open takes the whole log
        entries = decisions.open_entries(entries)
    if args.for_task:
        task = tasks.find_task_by_prefix(tasks.load(path, project.config), args.for_task)
        entries = decisions.relevant(entries, task)
    if not entries:
        print("(no matching decisions)")
    for entry in entries:
        print(entry["text"] + "\n")
    return 0


def cmd_decide(args: argparse.Namespace) -> int:
    project = _project(args)
    ws, _ = _queue(project, args)
    path = project.folder(ws) / "DECISIONS.md"
    why = args.why
    if args.closes is not None:
        entries = decisions.parse(path.read_text()) if path.exists() else []
        why = decisions.closing_body(entries, args.closes, why)
    if args.commit:
        number, short = act.commit_decision(project, ws, today(), args.by, args.title, why)
        print(f"{number}; committed {short}")
        return 0
    print(f"{decisions.record(path, today(), args.by, args.title, why)}; commit it")
    return 0


def _print_gates(found: list[dict]) -> None:
    for g in found:
        word = "ok  " if g["ok"] else ("FAIL" if g["blocking"] else "warn")
        print(f"  {word} {g['name']}" + (f": {g['detail']}" if not g["ok"] and g["detail"] else ""))


def cmd_evidence(args: argparse.Namespace) -> int:
    project, ws, task = _at_task(args)
    file = evidence.path_for(project, ws, task["id"])
    if args.action == "new":
        if gitutil.current_branch(project.root) == project.config.integration:
            raise Refused(f"evidence goes on {task['id']}'s branch, not "
                          f"{project.config.integration}: claim it and make its worktree first")
        if file.exists():
            raise Refused(f"{project.rel(file)} already exists")
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_text(evidence.skeleton(task))
        print(f"wrote {project.rel(file)}; fill in each {{{{...}}}}")
        return 0
    if task["status"] == "done":  # its run record went when it landed, and its gates ran then
        print(f"{task['id']} has landed as {task.get('commit')}; its gates ran then")
        return 0
    rows = registry.load(project)["workstreams"]
    found = gates.ready_gates(project, ws, task, list(snapshot.folders_by_id(project, rows).values()))
    _print_gates(found)
    if gates.blockers(found):
        print("FAIL")
        return 1
    print("OK")
    return 0


def cmd_commit(args: argparse.Namespace) -> int:
    """A worker's commit, wherever its shell is. An agent's rules may refuse git aimed at another
    directory, and a shell that left the worktree would otherwise commit on the wrong branch."""
    project, ws, task = _at_task(args)
    branch = task.get("branch") or project.config.branch_for(task["id"])
    current = gitutil.current_branch(project.root)
    if current != branch:
        raise Refused(f"{task['id']} commits on {branch}; this checkout is on {current}")
    gitutil.run(project.root, "add", "-A")
    staged = gitutil.run(project.root, "diff", "--cached", "--name-only", "--no-renames").stdout.splitlines()
    if not staged:
        raise Refused("nothing to commit")
    rows = registry.load(project)["workstreams"]
    bad = gates.tracking_violations(staged, project.rel(project.registry_path),
                                    list(snapshot.folders_by_id(project, rows).values()),
                                    project.rel(evidence.path_for(project, ws, task["id"])))
    if bad:
        gitutil.run(project.root, "reset", "-q")
        raise Refused("committed nothing: these belong to the coordinator: " + ", ".join(bad[:8]))
    done = gitutil.run(project.root, "commit", "-q", "-m", args.message or f"{task['id']}: {task['title']}")
    if done.returncode != 0:
        gitutil.run(project.root, "reset", "-q")
        detail = (done.stderr or done.stdout).strip().splitlines()
        raise Refused(f"commit failed: {detail[-1] if detail else f'exit {done.returncode}'}")
    print(f"committed {gitutil.rev_parse(project.root, 'HEAD', short=True)} on {branch}:")
    for path in staged:
        print(f"  {path}")
    return 0


def cmd_worktree(args: argparse.Namespace) -> int:
    project = _project(args)
    if args.action == "list":
        rows = [w for w in worktree.live(project) if not w.get("main")]
        if not rows:
            print("(no linked worktrees)")
        for w in rows:
            print(f"{w['path']}  {w.get('branch') or 'detached'}")
        return 0
    ws, _ = _queue(project, args)
    for task_id in args.ids:
        if args.action == "create":
            path, created = worktree.create(project, ws, task_id)
            print(f"{task_id}: {path}" + ("" if created else " (already there)"))
        else:
            print(f"{task_id}: " + worktree.remove(project, ws, task_id, force=args.force,
                                                   delete_branch=args.delete_branch))
    return 0


def cmd_settle(args: argparse.Namespace) -> int:
    project = _project(args)
    ws, _ = _queue(project, args)
    result = settle.settle(project, ws["id"], args.ids, commit=args.commit,
                           skip_post_verify=args.skip_post_verify, keep=args.keep,
                           dry_run=args.dry_run, note=args.note)
    stopped = False
    for out in result["outcomes"]:
        if out["gates"] and (out["state"] != settle.MERGED or args.dry_run):
            print(f"{out['id']}:")
            _print_gates(out["gates"])
        warned = [g for g in out["gates"] if not g["ok"] and not g["blocking"]]
        if out["state"] == settle.MERGED:
            for g in warned:
                print(f"{out['id']}: warning: {g['name']}: {g['detail']}")
            print(f"{out['id']}: done, merged as {out['commit'][:10]} "
                  f"(after merge: {out['postMerge']})")
        elif out["state"] == settle.BLOCKED:
            print(f"{out['id']}: blocked: {out['why']}; its branch {out['branch']} stays")
        elif out["state"] == settle.STOPPED:
            stopped = True
            print(f"{out['id']}: NOT settled: {out['why']}")
        else:
            print(f"{out['id']}: ready to settle")
    if result["decisions"]:
        print(f"numbered {', '.join(result['decisions'])}")
    for line in result["open"]:
        print(f"open: {line}")
    for warning in result["warnings"]:
        print(f"warning: {warning}")
    return 1 if stopped else 0


def cmd_handoff(args: argparse.Namespace) -> int:
    project = _project(args)
    ws, _ = _queue(project, args)
    if not handoff.write(project, ws, [], args.note):
        raise WsError(f"{ws['id']} keeps no {handoff.FILE_NAME} at this tier")
    print(f"wrote {handoff.FILE_NAME}; commit it")
    return 0


# --- the protocol and what it costs -------------------------------------------------------


def cmd_protocol(args: argparse.Namespace) -> int:
    if args.section:
        print(protocol.section(args.section))
        return 0
    print(f"protocol version {protocol.version()}; `ws protocol <section>` prints one of:")
    for name, body in protocol.sections().items():
        print(f"  {name:<12} {audit.tokens(body):>5} tokens")
    return 0


def _cmd_audit_usage(args: argparse.Namespace) -> int:
    agents = [args.agent] if args.agent else usage.agents_with_transcripts()
    project = Path(args.project) if args.project else _project(args).root
    results = [usage.report(agent, project, since=args.since, until=args.until,
                            transcripts=Path(args.transcripts) if args.transcripts else None,
                            worker_marker=args.worker_marker) for agent in agents]
    if args.json:
        print(json.dumps(results, indent=2))
    else:
        for result in results:
            print("\n".join(usage.format_report(result)))
    return 0


def cmd_import(args: argparse.Namespace) -> int:
    project = _project(args)
    plan = importer.run(project, write=args.write)
    if not plan.done:
        print("nothing to import: every queue is current")
        return 0
    word = "did" if args.write else "would do"
    print(f"{word}:")
    for line in plan.done:
        print(f"  {line}")
    if plan.todo:
        print("needs a person:")
        for line in plan.todo:
            print(f"  {line}")
    print("next: `ws validate`, `ws baseline record`, then commit" if args.write
          else "nothing changed: `ws import --write` does this")
    return 0


def cmd_audit(args: argparse.Namespace) -> int:
    if args.what == "usage":
        return _cmd_audit_usage(args)
    rows = audit.role_rows()
    try:
        project = _project(args)
    except WsError:  # the tool's own limits don't need a project around them
        project = None
    if project is not None and project.registry_path.exists():
        data = registry.load(project)
        named = getattr(args, "workstream", None)
        chosen = [registry.find(data, named)] if named else [
            w for w in data["workstreams"] if w.get("status") in registry.OPEN_STATUSES]
        for ws in chosen:
            rows += audit.project_rows(project, ws)
    if args.json:
        print(json.dumps(rows, indent=2))
    else:
        print("\n".join(audit.format_rows(rows)))
    over = [r["role"] for r in rows if not r["ok"]]
    if over:
        print(f"FAIL: over budget: {', '.join(over)}", file=sys.stderr)
        return 1
    return 0


# --- the UI contract ----------------------------------------------------------------------


def cmd_root(args: argparse.Namespace) -> int:
    """Where a UI should read from: a session in a task's worktree would see a frozen queue."""
    print(worktree.integration_checkout(_project(args)))
    return 0


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
    if args.queue:
        if args.task or args.file or args.checks:
            raise WsError("--queue lists every task, so it takes no task, --file or --checks")
        print(json.dumps(review.build_queue(project), indent=2))
        return 0
    if not args.task:
        raise WsError("review needs a task id, or --queue")
    if args.max_lines < 1:
        raise WsError("--max-lines must be at least 1")
    ws = _resolve_ws(project, args)
    print(json.dumps(review.build_review(project, ws["id"], args.task, args.file, args.max_lines,
                                         checks=args.checks), indent=2))
    return 0


def cmd_serve(args: argparse.Namespace) -> int:
    from workstream import serve  # an http server is no cost for every other command to pay

    return serve.run(_project(args), args.port, not args.no_open)


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

    p = command("init", cmd_init, "detect the stack, try its commands, write what worked to "
                                  ".workstream/config.toml, and start a registry")
    p.add_argument("--integration", help="the branch task branches merge into")
    p.add_argument("--production", help="the branch releases go to (default: the same one)")
    p.add_argument("--profile", help="a stack's profile, instead of detecting one")
    p.add_argument("--no-run", action="store_true",
                   help="don't run anything; proposed commands stay commented out")
    p.add_argument("--timeout", type=int, help="seconds for each command tried")
    p.add_argument("--no-git", dest="force_no_git", action="store_true",
                   help="set up outside a git repository")

    p = command("adapt", cmd_adapt, "write the skills and pointer an agent reads, from the one "
                                    "source; with no agent, list them")
    p.add_argument("agent", nargs="?")
    p.add_argument("--check", action="store_true", help="exit 1 if its files aren't current")
    p.add_argument("--force", action="store_true", help="overwrite files edited by hand")
    p.add_argument("--plugin", metavar="DIR", help="write its plugin form to DIR instead")
    p.add_argument("--hook", action=argparse.BooleanOptionalAction, default=None,
                   help="turn on, or off, the guard against direct edits to tracking files; "
                        "it needs `ws` on PATH wherever the agent runs")

    p = command("hook", cmd_hook, "for an agent's hook: check a file edit it is about to make")
    p.add_argument("event", choices=("pre-edit",))
    p.add_argument("--format", choices=hook.FORMATS, required=True)

    p = command("import", cmd_import, "bring older workstream files onto this schema (a dry run unless --write)")
    p.add_argument("--write", action="store_true")

    p = command("doctor", cmd_doctor, "what is wrong with this setup; changes nothing")
    p.add_argument("--run", action="store_true", help="also run each command against the baseline")
    p.add_argument("--json", action="store_true")

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

    p = command("seed", cmd_seed, "bulk-load tasks from a JSON file, or split an approved plan "
                                  "into PLAN.md and the queue")
    p.add_argument("seed_file", nargs="?")
    p.add_argument("--from-plan", metavar="PLAN", help="a plan with a ```json ws-tasks``` block")
    p.add_argument("--force", action="store_true", help="overwrite a PLAN.md already written")

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
    p.add_argument("--commit", nargs="?", const=True,
                   help="record this commit; bare, with --acceptance or --summary, commit the queue")
    p.add_argument("--notes")
    p.add_argument("--verify", action="append", help="replaces the list; repeatable")
    p.add_argument("--acceptance", nargs=2, metavar=("N", "TEXT"),
                   help="replace item N, keeping its kind; needs --because")
    p.add_argument("--summary", metavar="TEXT", help="replace the summary; needs --because")
    p.add_argument("--because", metavar="DNNN", help="the decision that changed it")
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
    p.add_argument("--commit", action="store_true",
                   help="also sync the registry and commit: what a worktree needs to branch from")
    p.add_argument("ids", nargs="+", metavar="ID")

    p = command("unclaim", cmd_unclaim, "requeue in-progress or blocked tasks (all-or-nothing)")
    p.add_argument("ids", nargs="+", metavar="ID")

    p = command("reset", cmd_reset, "replay: tasks back to todo, run-time state cleared")
    p.add_argument("ids", nargs="*", metavar="ID", help="default: every task")
    p.add_argument("--cascade", action="store_true", help="and everything that depends on them")
    p.add_argument("--dry-run", action="store_true")
    p.add_argument("-y", "--yes", action="store_true")

    p = command("verify", cmd_verify, "run a task's verify commands, record the result against "
                                      "the code tree, print a bounded report (exit 1 on failure)")
    p.add_argument("id")
    p.add_argument("--key", action="append", help="only this one of its commands; repeatable")
    p.add_argument("--json", action="store_true")

    # Real subcommands, not an action plus a list: before 3.12, argparse fills both at once, so
    # `ws worktree create -w x T1` would be refused.
    p = command("baseline", cmd_baseline, "what the commands report before any work starts")
    actions = p.add_subparsers(dest="action", required=True)
    q = actions.add_parser("record", parents=[common], help="run the commands and record it")
    q.add_argument("keys", nargs="*", metavar="KEY", help="default: what open tasks verify with")
    actions.add_parser("show", parents=[common], help="what was recorded")

    p = command("brief", cmd_brief, "everything a worker needs for one task")
    p.add_argument("id", help="task id, or a unique prefix of one")
    p.add_argument("--role", choices=("worker",), default="worker")
    p.add_argument("--max-chars", type=int, default=brief.DEFAULT_MAX_CHARS,
                   help="trim decisions past this length; the task itself is never trimmed")

    p = command("decisions", cmd_decisions, "the decisions log, or the entries one task needs")
    p.add_argument("--for", dest="for_task", metavar="ID")
    p.add_argument("--open", action="store_true", help="only entries still open")

    p = command("decide", cmd_decide, "record a coordinator's or user's call, with the next number")
    p.add_argument("title", help="the call, in one line")
    p.add_argument("--why", required=True, help="the reason, and what was rejected")
    p.add_argument("--by", default="coordinator", help="`user` makes it apply to every task")
    p.add_argument("--closes", metavar="IDS",
                   help="open decisions this settles, comma-separated; their text stays as it is")
    p.add_argument("--commit", action="store_true",
                   help="commit DECISIONS.md on the integration branch too, and print the hash")

    p = command("evidence", cmd_evidence, "start a task's evidence file, or check it's ready")
    p.add_argument("action", choices=("new", "check"))
    p.add_argument("id")

    p = command("commit", cmd_commit, "commit a task's work on its branch, from anywhere")
    p.add_argument("id")
    p.add_argument("-m", "--message", help="default: the task's id and title")

    p = command("worktree", cmd_worktree, "a worktree per claimed task")
    actions = p.add_subparsers(dest="action", required=True)
    q = actions.add_parser("create", parents=[common], help="on the task's branch, set up")
    q.add_argument("ids", nargs="+", metavar="ID")
    q = actions.add_parser("remove", parents=[common], help="refuses to lose uncommitted work")
    q.add_argument("ids", nargs="+", metavar="ID")
    q.add_argument("--force", action="store_true", help="discard uncommitted work")
    q.add_argument("--delete-branch", action="store_true", help="also a merged branch")
    actions.add_parser("list", parents=[common], help="every linked worktree")

    p = command("settle", cmd_settle, "land finished tasks: gates, merge, numbered decisions, "
                                      "progress, handoff, registry, one commit")
    p.add_argument("ids", nargs="+", metavar="ID")
    p.add_argument("--commit", help="the task landed another way (a PR, say): record this commit")
    p.add_argument("--skip-post-merge-verify", dest="skip_post_verify", action="store_true",
                   help="don't re-run verify when others landed first; recorded as skipped")
    p.add_argument("--keep", action="store_true", help="leave the worktree and branch")
    p.add_argument("--dry-run", action="store_true", help="print the gates, change nothing")
    p.add_argument("--note", help="a line for the handoff")

    p = command("handoff", cmd_handoff, "rewrite session_handoff.md from the current state")
    p.add_argument("--note", help="a line for the next session")

    p = command("protocol", cmd_protocol, "the protocol, one section at a time")
    p.add_argument("section", nargs="?")

    p = command("audit", cmd_audit, "context each role costs against its limit (exit 1 if over), or real usage")
    p.add_argument("what", choices=("context", "usage"), help="usage reads real transcripts: numbers only")
    p.add_argument("--json", action="store_true")
    p.add_argument("--agent", help="usage: one agent's transcripts, rather than every agent's")
    p.add_argument("--project", help="usage: the project to count (default: this one)")
    p.add_argument("--since", help="usage: sessions from this day, YYYY-MM-DD")
    p.add_argument("--until", help="usage: sessions up to this day, YYYY-MM-DD")
    p.add_argument("--transcripts", help="usage: read from this folder, not the agent's own")
    p.add_argument("--worker-marker", default=usage.DEFAULT_WORKER_MARKER,
                   help="usage: a regex: a session opening with a match is a worker's")

    command("root", cmd_root, "the checkout that holds the integration branch, or this one if none does")

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
    p.add_argument("task", nargs="?", help="task id")
    p.add_argument("--file", help="a path from the diffstat to include the hunks of")
    p.add_argument("--checks", action="store_true",
                   help="also the gates settling would run, each acceptance item beside its "
                        "proof, and the evidence, from the task's branch while it has one")
    p.add_argument("--queue", action="store_true",
                   help="instead, what can be reviewed across the open workstreams")
    p.add_argument("--max-lines", type=int, default=review.DEFAULT_MAX_LINES,
                   help="cap on the hunks' lines; whole hunks only, `truncated` when cut")

    p = command("serve", cmd_serve, "the web UI on localhost: one address per launch, live "
                                    "updates, and writes only through `ws act`")
    p.add_argument("--port", type=int, help="default: this project's usual port, or any free one")
    p.add_argument("--no-open", action="store_true", help="print the address, don't open a browser")
    return parser


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv[1:] if argv is None else argv
    if argv[:1] == ["hook"]:
        return _main_for_hook(argv)
    args = build_parser().parse_args(argv)
    try:
        return args.func(args)
    except Refused as e:
        print(f"refused: {e}", file=sys.stderr)
        return 1
    except WsError as e:
        print(f"error: {e}", file=sys.stderr)
        return 1


def _main_for_hook(argv: list[str]) -> int:
    """A hook's arguments are written by `ws adapt`, so a refusal here means a version skew, and a
    version skew mustn't stop an agent's work. Exit 2 is exactly what would, so it's caught."""
    try:
        args = build_parser().parse_args(argv)
        return args.func(args)
    except SystemExit:
        return 0
    except Exception:
        return 0
