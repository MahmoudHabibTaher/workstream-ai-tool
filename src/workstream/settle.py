"""`ws settle`: land finished tasks, and do all the bookkeeping in one commit.

This is the coordinator's whole job per task, as code: check the gates, merge, check the merge,
number the proposed decisions, then update the queue, the progress log, the handoff and the
registry. None of it needs a model, so none of it spends a model's context.

Tasks settle in priority order, one merge at a time. The first one that can't land stops the
batch: tasks already merged are still recorded, and the rest stay as they were.

It is safe to run again. A crash between the merge and the tracking commit leaves a merge the
task doesn't know about yet: settling finds it by its `Ws-Task:` trailer, or by the branch
already being on the integration branch, and carries on from there.

A blocked task's branch and worktree are left alone: its evidence lives there.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from workstream import act, decisions, evidence, gates, gitutil, handoff, registry, snapshot
from workstream import tasks, verify, worktree
from workstream.errors import Refused
from workstream.fsutil import today
from workstream.project import Project

TRAILER = "Ws-Task"
MERGED, BLOCKED, STOPPED = "merged", "blocked", "stopped"


def _git(project: Project, *argv: str):
    return gitutil.run(project.root, *argv)


def _detail(proc) -> str:
    """Git's reason, which comes first: its last line is often just `Aborting`."""
    lines = (proc.stderr or proc.stdout).strip().splitlines()
    return " ".join(line.strip() for line in lines[:4]) or f"exit {proc.returncode}"


def check_checkout(project: Project, rows: list[dict]) -> None:
    """On the integration branch, with no uncommitted change to a tracked file: a merge needs
    that, and a coordinator's half-made edit must not land inside one."""
    facts = snapshot.git_facts(project, rows)
    if "error" in facts:
        raise Refused(f"cannot read the checkout: {facts['error']}")
    if facts["branch"] != project.config.integration:
        raise Refused(f"settle runs on {project.config.integration}; this checkout is on "
                      f"{facts['branch']}")
    if _git(project, "rev-parse", "--verify", "--quiet", "MERGE_HEAD").returncode == 0:
        raise Refused("a merge is in progress; finish or abort it first")
    dirty = _git(project, "status", "--porcelain", "--untracked-files=no").stdout.splitlines()
    if dirty:
        raise Refused("uncommitted changes:\n" + "\n".join(dirty[:10]))


def find_landed(project: Project, task: dict, branch: str) -> str | None:
    """The commit that already landed this task on the integration branch, or None."""
    base = gitutil.rev_parse(project.root, task.get("baseCommit") or "HEAD^{commit}")
    span = f"{base}..HEAD" if task.get("baseCommit") and base else "HEAD"
    wanted = task["id"].replace(".", r"\.")
    proc = _git(project, "log", "--first-parent", "--format=%H", "-n", "1",
                f"--grep=^{TRAILER}: {wanted}$", span, "--")
    if proc.returncode == 0 and proc.stdout.strip():
        return proc.stdout.strip()
    if not gitutil.branch_exists(project.root, branch):
        return None
    tip = gitutil.rev_parse(project.root, branch)
    if not gitutil.is_ancestor(project.root, tip, "HEAD"):
        return None
    # A branch nobody committed to is on the integration branch too, and landed nothing.
    if task.get("baseCommit") and verify.code_tree(project, tip) == verify.code_tree(project, base):
        return None
    walk = _git(project, "rev-list", "--first-parent", "--ancestry-path", f"{tip}..HEAD")
    commits = walk.stdout.split()
    return commits[-1] if commits else tip


def merge_message(ws_id: str, task: dict) -> str:
    return f"{ws_id}: merge {task['id']}: {task['title']}\n\n{TRAILER}: {task['id']}\n"


def _abort_merge(project: Project) -> None:
    """Back to exactly the commit we started from. `reset --merge` covers --squash too, which
    leaves no MERGE_HEAD for `merge --abort` to act on."""
    _git(project, "reset", "-q", "--merge")


def start_merge(project: Project, branch: str) -> str | None:
    """Merge into the working tree and index, uncommitted. None on success, else the reason;
    a refused merge leaves nothing behind."""
    how = "--squash" if project.config.merge == "squash" else "--no-ff"
    argv = ["merge", "--no-commit", how, branch] if how == "--no-ff" else ["merge", how, branch]
    proc = _git(project, *argv)
    if proc.returncode == 0:
        return None
    conflicted = _git(project, "diff", "--name-only", "--diff-filter=U").stdout.split()
    _abort_merge(project)
    return (f"conflicts in {', '.join(conflicted[:8])}; bring {project.config.integration} into "
            f"{branch} and verify again") if conflicted else _detail(proc)


def finish_merge(project: Project, message: str) -> tuple[str | None, str | None]:
    """(the new commit, None), or (None, why): a failing commit hook, say."""
    proc = subprocess.run(["git", "commit", "-q", "-F", "-"], cwd=project.root, input=message,
                          capture_output=True, text=True, errors="replace")
    if proc.returncode != 0:
        _abort_merge(project)
        return None, f"the merge commit failed: {_detail(proc)}"
    return gitutil.rev_parse(project.root, "HEAD"), None


def _post_merge(project: Project, ws: dict, task: dict, skip: bool) -> tuple[str, dict | None, str]:
    """Check the merged tree, still uncommitted. (how it went, its record, why it failed).

    If nothing else landed since the branch was verified, the merged code is the verified code
    and there is nothing to learn from running it again. Otherwise this is the first time these
    changes have ever run together, and it is where parallel work breaks."""
    run = verify.load_run(project, ws["id"], task["id"])
    if not tasks.verify_commands(task, project.config):
        return "not-applicable", run, ""
    if run and run.get("tree") == verify.code_tree(project):
        return "same-tree", run, ""
    if skip:
        return "skipped", run, ""
    after = verify.verify_task(project, ws, task, record=verify.POST_MERGE)
    if after["problems"]:
        return "ran", after, "after merging: " + "; ".join(after["problems"])
    return "ran", after, ""


def _land(project: Project, ws: dict, task: dict, branch: str, skip_post: bool
          ) -> tuple[str | None, dict | None, str, str]:
    """(commit, the record that counts, how the merged tree was checked, why it stopped)."""
    why = start_merge(project, branch)
    if why:
        return None, None, "", why
    how, run, why = _post_merge(project, ws, task, skip_post)
    if why:
        _abort_merge(project)
        return None, None, "", why
    commit, why = finish_merge(project, merge_message(ws["id"], task))
    return commit, run, how, why or ""


def _settle_one(project: Project, ws: dict, task: dict, folders: list[str], *, commit: str | None,
                skip_post: bool, dry_run: bool) -> dict:
    """Land or block one task, touching no tracking file. Returns an outcome for record()."""
    tid = task["id"]
    config = project.config
    branch = task.get("branch") or config.branch_for(tid)
    outcome = {"id": tid, "task": task, "branch": branch, "gates": []}
    if task["status"] not in tasks.UNCLAIMABLE_STATUSES:
        return {**outcome, "state": STOPPED, "why": f"its status is {task['status']}"}
    if branch.startswith("-"):
        return {**outcome, "state": STOPPED, "why": f"branch {branch!r} looks like an option"}
    landed = None
    if commit:
        landed = gitutil.rev_parse(project.root, f"{commit}^{{commit}}")
        if not landed or not gitutil.is_ancestor(project.root, landed, "HEAD"):
            return {**outcome, "state": STOPPED,
                    "why": f"{commit} isn't on {config.integration}"}
    else:
        landed = find_landed(project, task, branch)
    rev = landed or branch
    if not landed and not gitutil.branch_exists(project.root, branch):
        return {**outcome, "state": STOPPED, "why": f"no branch {branch}; `--commit <hash>` "
                                                    "names work that landed another way"}
    text = evidence.read_at(project, ws, tid, rev)
    parsed = evidence.parse(text) if text else None
    if parsed and parsed["status"] == evidence.BLOCKED and not evidence.problems(text, task):
        if task["status"] == "blocked":
            return {**outcome, "state": STOPPED, "why": f"still blocked: {parsed['reason']}"}
        return {**outcome, "state": BLOCKED, "why": parsed["reason"], "gotchas": parsed["gotchas"]}
    found = gates.settle_gates(project, ws, task, rev, text=text, merged=bool(landed),
                               folders=folders)
    outcome["gates"] = found
    if gates.blockers(found):
        return {**outcome, "state": STOPPED, "why": "gates failed"}
    if dry_run:
        return {**outcome, "state": "ready", "why": ""}
    if not landed and config.merge == "pr":
        return {**outcome, "state": STOPPED,
                "why": f"branches.merge is pr: open one from {branch}, then "
                       f"`ws settle {tid} --commit <merge hash>`"}
    if landed:
        # Merged by an earlier run that stopped short, or by hand. If that run checked the
        # merged tree, its record is the one that counts.
        checked = verify.load_run(project, ws["id"], tid, verify.POST_MERGE)
        passed = checked is not None and not checked.get("problems")
        run = checked if passed else verify.load_run(project, ws["id"], tid)
        how = "ran" if passed else "not-applicable"
    else:
        landed, run, how, why = _land(project, ws, task, branch, skip_post)
        if why:
            return {**outcome, "state": STOPPED, "why": why}
    return {**outcome, "state": MERGED, "commit": landed, "run": run, "postMerge": how,
            "text": text, "parsed": parsed}


def _number_decisions(project: Project, ws: dict, merged: list[dict]) -> list[str]:
    """Give every proposed decision the next free number, in merge order, and rewrite each
    evidence file to match. Returns the new ids."""
    path = project.folder(ws) / "DECISIONS.md"
    entries = decisions.parse(path.read_text()) if path.exists() else []
    number = decisions.next_number(entries)
    rendered, ids = [], []
    for out in merged:
        mapping = {}
        for proposal in out["parsed"]["proposals"]:
            new_id = f"D{number:03d}"
            rendered.append(decisions.render_entry(number, today(), out["id"], proposal["title"],
                                                   proposal["body"]))
            mapping[proposal["id"]] = new_id
            ids.append(new_id)
            number += 1
        if mapping:
            file = evidence.path_for(project, ws, out["id"])
            file.write_text(evidence.rewrite_ids(file.read_text(), mapping))
            out["parsed"]["gotchas"] = evidence.rewrite_ids(out["parsed"]["gotchas"], mapping)
    if rendered:
        decisions.append(path, rendered)
    return ids


def _verdicts(run: dict | None) -> str:
    results = (run or {}).get("results", [])
    return ", ".join(f"{r['key']} {r['verdict']}" for r in results) or "no verify commands"


def _progress_entries(project: Project, ws: dict, outcomes: list[dict]) -> None:
    path = project.folder(ws) / "PROGRESS.md"
    if not path.exists():
        return
    entries = []
    for out in outcomes:
        title = out["task"]["title"]
        if out["state"] == MERGED:
            entries.append(f"## {today()}: {out['id']}: {title}\n\nMerged as "
                           f"`{out['commit'][:10]}`. Verified: {_verdicts(out.get('run'))}. "
                           f"[Evidence](evidence/{out['id']}.md).\n")
        else:
            entries.append(f"## {today()}: {out['id']} blocked\n\n{out['why']}. "
                           f"Evidence on `{out['branch']}`.\n")
    path.write_text(handoff.insert_newest_first(path.read_text(), entries))


def _record(project: Project, ws: dict, outcomes: list[dict], note: str | None) -> list[str]:
    """Write every tracking file for these outcomes and commit them together. Restores the old
    bytes if anything fails, so a rerun starts clean: the merges are already safe in history."""
    config = project.config
    queue = project.tasks_path(ws)
    merged = [o for o in outcomes if o["state"] == MERGED]
    blocked = [o for o in outcomes if o["state"] == BLOCKED]
    folder = project.folder(ws)
    paths = [queue, project.registry_path, folder / "DECISIONS.md", folder / "PROGRESS.md",
             folder / "session_handoff.md",
             *[evidence.path_for(project, ws, o["id"]) for o in merged]]
    originals = {p: (p.read_bytes() if p.exists() else None) for p in paths}
    try:
        ids = _number_decisions(project, ws, merged)
        for out in merged:
            how = out["postMerge"]
            tasks.update(queue, out["id"], config, status="done", commit=out["commit"],
                         verification=verify.summary(out["run"] or {}, how))
        for out in blocked:
            tasks.update(queue, out["id"], config, status="blocked",
                         notes=f"{out['why']}; evidence on {out['branch']}")
        _progress_entries(project, ws, outcomes)
        registry.sync(project)
        handoff.write(project, ws, outcomes, note)
        changed = act.changed_paths({p: b for p, b in originals.items()
                                     if p.suffix == ".json"})
        changed += [p for p, b in originals.items() if p.suffix != ".json"
                    and (p.read_bytes() if p.exists() else None) != b]
        names = ", ".join(o["id"] for o in outcomes)
        words = " and ".join(w for w, some in (("done", merged), ("blocked", blocked)) if some)
        for path in changed:  # a tier that started without DECISIONS.md, say
            if originals[path] is None:
                _git(project, "add", "--", project.rel(path))
        act.commit(project, changed, f"{ws['id']}: {names} {words}")
    except BaseException:
        act.restore(originals)
        _git(project, "reset", "-q", "--", *[project.rel(p) for p in originals])
        raise
    return ids


def _clean_up(project: Project, ws: dict, out: dict) -> list[str]:
    """Only after the tracking commit. A failure here costs nothing, so it warns and moves on."""
    warnings = []
    branch = out["branch"]
    path = worktree.for_branch(project, branch)
    if path:
        lost = worktree.uncommitted(Path(path))
        if lost:
            warnings.append(f"{path} kept: it has uncommitted work")
            return warnings
        _git(project, "worktree", "remove", "--force", path)
    if gitutil.branch_exists(project.root, branch):
        # A squash leaves the branch unmerged in git's eyes, though the commit recorded it.
        flag = "-D" if project.config.merge == "squash" else "-d"
        if _git(project, "branch", flag, branch).returncode != 0:
            warnings.append(f"{branch} kept: git won't delete it")
    shutil.rmtree(verify.runs_dir(project, ws["id"], out["id"]), ignore_errors=True)
    return warnings


def settle(project: Project, ws_id: str, ids: list[str], *, commit: str | None = None,
           skip_post_verify: bool = False, keep: bool = False, dry_run: bool = False,
           note: str | None = None) -> dict:
    """Settle these tasks. {outcomes, decisions, warnings}; a task that couldn't land is in
    outcomes with state "stopped" and its reason, not raised, so the ones before it still
    count. Raises Refused only when nothing could be tried at all."""
    rows = registry.load(project)["workstreams"]
    ws = registry.find({"workstreams": rows}, ws_id)
    check_checkout(project, rows)
    if commit and len(ids) != 1:
        raise Refused("--commit names one task's commit; settle one task with it")
    data = tasks.load(project.tasks_path(ws), project.config)
    chosen = sorted((tasks.find_task(data, i) for i in dict.fromkeys(ids)),
                    key=lambda t: t["priority"])
    folders = list(snapshot.folders_by_id(project, rows).values())
    outcomes = []
    for task in chosen:
        out = _settle_one(project, ws, task, folders, commit=commit,
                          skip_post=skip_post_verify, dry_run=dry_run)
        outcomes.append(out)
        if out["state"] == STOPPED:
            break
    result = {"outcomes": outcomes, "decisions": [], "warnings": []}
    settled = [o for o in outcomes if o["state"] in (MERGED, BLOCKED)]
    if dry_run or not settled:
        return result
    result["decisions"] = _record(project, ws, settled, note)
    if not keep:
        for out in settled:
            if out["state"] == MERGED:
                result["warnings"] += _clean_up(project, ws, out)
    return result

