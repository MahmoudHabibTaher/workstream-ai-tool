"""Pre-flight checks before a UI launches an agent on a workstream.

`ws launch check -w <id> --kind <kind> [--task T] [--agent A] --json` prints
`{checks: [{id, ok, blocking, message}]}`. Each check reads what the CLI already knows, through
the module that owns the rule, so a UI decides nothing itself:

- `validate`: the workstream's integrity errors (`registry.validate_entry`). Blocking.
- `wave`: for `run` only, the queue's wave (`graph.compute_wave`) has an actionable task.
  Blocking.
- `claim`: for `run` and `run-task`, no task of the queue is already claimed. Blocking for
  `run` (another session may be running the workstream), a warning for `run-task`.
- `dirty`: the registry and the workstream's folder have no uncommitted changes, the same
  paths `ws act` refuses on (`snapshot.git_facts`). Blocking.
- `baseline`: every key open tasks verify with was recorded (`baseline.keys_to_record`).
  A warning: settling still works, it just can't tell old findings from new.
- `skills`: with `--agent`, `ws adapt` installed that agent's skills (`adapt.adapted`). A
  warning: a prompt naming a skill works only where the skill is.

`ok` is whether the check passed; `blocking` is whether a failure of it should stop the launch,
so a passing check still says how it would count. A check that can't read what it needs fails,
with what it couldn't read as its message, rather than raising: one broken file names itself
and the other checks still run.
"""

from __future__ import annotations

from workstream import adapt, baseline, graph, registry, snapshot, tasks
from workstream.errors import WsError
from workstream.project import Project

# The launch that pins one task. JX-04 adds its prompt to snapshot.LAUNCH_PROMPTS; until then
# the kind is accepted here so a UI can check before it builds the prompt.
TASK_KIND = "run-task"
KINDS = tuple(dict.fromkeys([*snapshot.LAUNCH_PROMPTS, TASK_KIND]))
# The kinds that start a worker on the queue, so another open claim matters.
CLAIM_KINDS = ("run", TASK_KIND)


def check(cid: str, ok: bool, blocking: bool, message: str) -> dict:
    return {"id": cid, "ok": ok, "blocking": blocking, "message": message}


def check_validate(project: Project, ws: dict, ids: set[str]) -> dict:
    errors, _ = registry.validate_entry(project, ws, ids)
    if errors:
        more = (f" (and {len(errors) - 1} more; see `ws validate -w {ws['id']}`)"
                if len(errors) > 1 else "")
        return check("validate", False, True, f"{errors[0]}{more}")
    return check("validate", True, True, "no integrity errors")


def check_wave(rows: list[dict]) -> dict:
    wave = graph.compute_wave(rows)
    if wave["state"] == "ready":
        return check("wave", True, True,
                     f"phase {wave['phase']}: {', '.join(wave['ids'])} actionable")
    if wave["state"] == "finished":
        return check("wave", False, True, "the queue is finished: no task to run")
    return check("wave", False, True, "no task is actionable: open tasks remain but none can start")


def check_claim(rows: list[dict], kind: str, task_id: str | None) -> dict:
    blocking = kind == "run"
    claimed = [t["id"] for t in rows if t.get("status") == "in-progress"]
    if not claimed:
        return check("claim", True, blocking, "no task is claimed")
    if task_id in claimed:
        return check("claim", False, blocking, f"{task_id} is already claimed")
    return check("claim", False, blocking,
                 f"a claim is already open (another session may be running): {', '.join(claimed)}")


def check_dirty(project: Project, ws_id: str, reg_rows: list[dict]) -> dict:
    """The rule `ws act` refuses by: the registry and this workstream's folder are clean."""
    facts = snapshot.git_facts(project, reg_rows)
    if "error" in facts:
        return check("dirty", False, True, f"cannot read the checkout: {facts['error']}")
    registry_rel = project.rel(project.registry_path)
    folders = snapshot.folders_by_id(project, reg_rows)
    dirty = [p for p in facts["dirtyTracking"]
             if snapshot.tracking_owner(p, registry_rel, folders) in ("", ws_id)]
    if dirty:
        return check("dirty", False, True,
                     f"uncommitted tracking paths (an orchestrator may be mid-step): "
                     f"{', '.join(dirty)}")
    return check("dirty", True, True, "tracking paths are committed")


def check_baseline(project: Project, ws: dict, rows: list[dict]) -> dict:
    needed = baseline.keys_to_record(project.config, rows)
    try:
        recorded = baseline.load_for(project, project.folder(ws))["keys"]
    except WsError as e:
        return check("baseline", False, False, str(e))
    missing = [k for k in needed if k not in recorded]
    if missing:
        return check("baseline", False, False,
                     f"no baseline recorded for {', '.join(missing)} "
                     f"(`ws baseline record -w {ws['id']}`)")
    return check("baseline", True, False, "a baseline is recorded for every key open tasks use")


def check_skills(project: Project, agent: str) -> dict:
    try:
        installed = adapt.adapted(project)
    except WsError as e:
        return check("skills", False, False, str(e))
    if agent not in installed:
        return check("skills", False, False,
                     f"skills not installed for {agent} (`ws adapt {agent}`)")
    return check("skills", True, False, f"skills installed for {agent}")


def _queue_failure(cid: str, blocking: bool, error: str) -> dict:
    return check(cid, False, blocking, f"cannot read the queue: {error}")


def run_checks(project: Project, ws_id: str, kind: str, task_id: str | None = None,
               agent: str | None = None) -> dict:
    """Every check that applies to this launch, in a fixed order, as {checks: [...]}.

    Refuses (WsError) only what a caller got wrong: an unknown workstream or kind, `--task`
    missing for `run-task` or given for another kind, or a task id the queue doesn't hold.
    """
    if kind not in KINDS:
        raise WsError(f"unknown launch kind {kind!r}; one of {', '.join(KINDS)}")
    if kind == TASK_KIND and not task_id:
        raise WsError(f"{TASK_KIND} needs --task")
    if task_id and kind != TASK_KIND:
        raise WsError(f"--task applies only to {TASK_KIND}, not {kind}")
    reg = registry.load(project)
    ws = registry.find(reg, ws_id)
    ids = {w.get("id") for w in reg["workstreams"]}
    rows, queue_error = None, None
    try:
        rows = tasks.load(project.tasks_path(ws), project.config)["tasks"]
    except WsError as e:
        queue_error = str(e)
    if rows is not None and task_id and task_id not in {t["id"] for t in rows}:
        raise WsError(f"{task_id}: no such task in {ws['id']}")

    out = [check_validate(project, ws, ids)]
    if kind == "run":
        out.append(check_wave(rows) if rows is not None
                   else _queue_failure("wave", True, queue_error))
    if kind in CLAIM_KINDS:
        out.append(check_claim(rows, kind, task_id) if rows is not None
                   else _queue_failure("claim", kind == "run", queue_error))
    out.append(check_dirty(project, ws["id"], reg["workstreams"]))
    out.append(check_baseline(project, ws, rows) if rows is not None
               else _queue_failure("baseline", False, queue_error))
    if agent:
        out.append(check_skills(project, agent))
    return {"checks": out}


def blocked(result: dict) -> bool:
    """Whether any blocking check failed."""
    return any(c["blocking"] and not c["ok"] for c in result["checks"])
