"""What must be true before a task lands. Each gate replaces a line of prose an agent had to
remember: a rule the CLI can check doesn't need to be in anyone's context.

Each is {name, ok, detail, blocking}. A warning shows up but doesn't stop the merge. Reads only.
"""

from __future__ import annotations

from fnmatch import fnmatch

from workstream import evidence, gitutil, tasks, verify
from workstream.config import Config
from workstream.project import Project


def gate(name: str, ok: bool, detail: str = "", blocking: bool = True) -> dict:
    return {"name": name, "ok": ok, "detail": detail, "blocking": blocking}


def blockers(failed: list[dict]) -> list[dict]:
    return [g for g in failed if not g["ok"] and g["blocking"]]


def changed_paths(project: Project, rev: str) -> list[str]:
    """What this revision would bring to the integration branch: everything since they last
    shared a commit. That leaves out the claim commit, which is already there."""
    proc = gitutil.run(project.root, "diff", "--name-only", "--no-renames",
                       f"{project.config.integration}...{rev}", "--")
    return proc.stdout.splitlines() if proc.returncode == 0 else []


def tracking_violations(paths: list[str], registry_rel: str, folders: list[str],
                        own_evidence: str) -> list[str]:
    """Paths a worker may not write: the registry and any workstream's tracking files. Its own
    evidence file is the one exception, and the only way a worker reports anything."""
    bad = []
    for path in paths:
        if path == own_evidence:
            continue
        if path == registry_rel or any(path.startswith(folder + "/") for folder in folders):
            bad.append(path)
    return bad


def out_of_scope(paths: list[str], files: list[str], own_evidence: str) -> list[str]:
    """Changed paths the task never named. `files` entries may be a path, a folder or a glob."""
    if not files:
        return []
    def named(path: str) -> bool:
        return any(path == f or path.startswith(f.rstrip("/") + "/") or fnmatch(path, f)
                   for f in files)
    return [p for p in paths if p != own_evidence and not named(p)]


def _kind_gate(task: dict, config: Config) -> dict:
    """Validation adequacy once more, at the point it matters: `verify` can change after seed."""
    needed = [k for k in config.adequacy.get(task.get("kind") or "", []) if k in config.commands]
    missing = [k for k in needed if k not in task.get("verify", [])]
    return gate("the task verifies with what its kind requires", not missing,
                f"kind {task.get('kind')!r} needs {', '.join(missing)}" if missing else "")


def verification_gates(project: Project, ws: dict, task: dict, trees: set[str]) -> list[dict]:
    """A record exists, every key passed, and it was taken on code this revision holds."""
    labels = [label for label, _ in tasks.verify_commands(task, project.config)]
    if not labels:
        return [gate("verify commands passed", True, "this task has none", blocking=False)]
    run = verify.load_run(project, ws["id"], task["id"])
    if run is None:
        return [gate("verify commands passed", False, f"never run: `ws verify {task['id']}`")]
    problems = verify.run_problems(run, labels)
    out = [gate("verify commands passed", not problems, "; ".join(problems))]
    same = bool(run.get("tree")) and run["tree"] in trees
    out.append(gate("the verified code is what would land", same,
                    "" if same else f"code changed since: `ws verify {task['id']}` on the branch"))
    return out


def settle_gates(project: Project, ws: dict, task: dict, rev: str, *, text: str | None,
                 merged: bool, folders: list[str]) -> list[dict]:
    """The gates for landing this done task from rev. `merged` means rev is already on the
    integration branch, so there is no diff left to inspect."""
    config = project.config
    root = project.root
    out = []
    still_open = [b for b in task.get("blockedBy", [])
                  if _status_of(project, ws, b) not in ("done", "deferred")]
    out.append(gate("what it builds on has landed", not still_open, ", ".join(still_open)))
    evidence_problems = evidence.problems(text, task)
    out.append(gate("the evidence is complete", not evidence_problems,
                    "; ".join(evidence_problems)))
    out.append(_kind_gate(task, config))
    trees = {verify.code_tree(project, rev)}
    if merged:
        # It landed already, so what was verified may be the branch, or this checkout since.
        trees.add(verify.code_tree(project))
        branch = task.get("branch") or config.branch_for(task["id"])
        if gitutil.branch_exists(root, branch):
            trees.add(verify.code_tree(project, branch))
    trees.discard("")
    out += verification_gates(project, ws, task, trees)
    if merged:
        return out
    base = gitutil.run(root, "merge-base", config.integration, rev).stdout.strip()
    ahead = bool(base) and gitutil.rev_parse(root, f"{rev}^{{commit}}") != base
    out.append(gate("the branch has commits", ahead, f"{rev} adds nothing"))
    paths = changed_paths(project, rev)
    own = project.rel(evidence.path_for(project, ws, task["id"]))
    bad = tracking_violations(paths, project.rel(project.registry_path), folders, own)
    out.append(gate("the branch leaves tracking files alone", not bad, ", ".join(bad[:8])))
    extra = out_of_scope(paths, task.get("files", []), own)
    out.append(gate("the diff stays within the task's files", not extra,
                    ", ".join(extra[:8]), blocking=False))
    return out


def _status_of(project: Project, ws: dict, task_id: str) -> str:
    data = tasks.load(project.tasks_path(ws), project.config)
    return next((t["status"] for t in data["tasks"] if t["id"] == task_id), "unknown")


def ready_gates(project: Project, ws: dict, task: dict, folders: list[str]) -> list[dict]:
    """A worker's own check before reporting, from wherever it works: what settling will ask,
    in time to fix it. Reads the working tree rather than a revision."""
    own = project.rel(evidence.path_for(project, ws, task["id"]))
    problems = evidence.problems(evidence.read_at(project, ws, task["id"], None), task)
    out = [gate("the evidence is complete", not problems, "; ".join(problems))]
    tree = verify.code_tree(project)
    out += verification_gates(project, ws, task, {tree} - {""})
    dirty = gitutil.run(project.root, "status", "--porcelain").stdout.splitlines()
    out.append(gate("everything is committed", not dirty, ", ".join(d[3:] for d in dirty[:8])))
    paths = changed_paths(project, "HEAD") + [d[3:] for d in dirty]
    bad = tracking_violations(paths, project.rel(project.registry_path), folders, own)
    out.append(gate("tracking files are untouched", not bad, ", ".join(sorted(set(bad))[:8])))
    extra = out_of_scope(sorted(set(paths)), task.get("files", []), own)
    out.append(gate("the diff stays within the task's files", not extra, ", ".join(extra[:8]),
                    blocking=False))
    return out
