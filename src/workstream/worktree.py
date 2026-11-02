"""One git worktree per claimed task, so parallel workers can't touch each other's files.

Worktrees sit under the configured dir, inside the repo (where an agent's sandbox allows
writing), and are kept out of `git status` through .git/info/exclude, so the project's
.gitignore never has to know.

A worktree branches from the integration tip, which must already hold the claim: a worker's
queue and registry come from that commit. `create` refuses when the claim isn't committed.
"""

from __future__ import annotations

import shlex
import shutil
import subprocess
from pathlib import Path

from workstream import act, gitutil, registry, snapshot, tasks
from workstream.config import CONFIG_REL
from workstream.errors import Refused, WsError
from workstream.project import Project

SETUP_TIMEOUT_SECONDS = 900


def path_for(project: Project, task_id: str) -> Path:
    return project.root / project.config.worktree_dir / task_id.lower()


def live(project: Project) -> list[dict]:
    """Every linked worktree git knows, as {path, head, branch, main}."""
    proc = gitutil.run(project.root, "worktree", "list", "--porcelain")
    return snapshot.parse_worktrees(proc.stdout) if proc.returncode == 0 else []


def for_branch(project: Project, branch: str) -> str | None:
    """The path of the linked worktree that has this branch checked out, or None."""
    for wt in live(project):
        if wt.get("branch") == branch and not wt.get("main"):
            return wt["path"]
    return None


def _exclude(project: Project) -> None:
    """Keep the worktree dir out of `git status`, without touching a tracked file."""
    common = gitutil.common_dir(project.root)
    root = project.root.resolve()
    target = (project.root / project.config.worktree_dir).resolve()
    if common is None or root not in target.parents:
        return
    line = "/" + str(target.relative_to(root)) + "/"
    path = common / "info" / "exclude"
    existing = path.read_text() if path.exists() else ""
    if line not in existing.splitlines():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(existing + ("" if existing.endswith("\n") or not existing else "\n")
                        + line + "\n")


def _run_setup(project: Project, path: Path) -> None:
    for command in project.config.worktree_setup:
        expanded = (command.replace("{main}", shlex.quote(str(project.root)))
                    .replace("{worktree}", shlex.quote(str(path))))
        try:
            done = subprocess.run(expanded, shell=True, cwd=path, capture_output=True, text=True,
                                  errors="replace", stdin=subprocess.DEVNULL,
                                  timeout=SETUP_TIMEOUT_SECONDS)
        except subprocess.TimeoutExpired:
            raise WsError(f"worktree setup timed out: {expanded}") from None
        if done.returncode != 0:
            last = (done.stderr or done.stdout).strip().splitlines()
            raise WsError(f"worktree setup failed: {expanded}"
                          + (f": {last[-1]}" if last else f" (exit {done.returncode})"))


def create(project: Project, ws: dict, task_id: str) -> tuple[Path, bool]:
    """(path, created): a worktree for a claimed task. Run twice, it finds the first one, so a
    worker that died can be picked up again. A failed setup leaves nothing behind."""
    config = project.config
    data = tasks.load(project.tasks_path(ws), config)
    task = tasks.find_task(data, task_id)
    if task["status"] != "in-progress":
        raise Refused(f"{task_id} is {task['status']}; `ws claim --commit {task_id}` first")
    branch = task.get("branch") or config.branch_for(task_id)
    if branch.startswith("-"):
        raise Refused(f"branch {branch!r} looks like an option")
    existing = for_branch(project, branch)
    if existing:
        return Path(existing), False
    rows = registry.load(project)["workstreams"]
    act.check_checkout(project, snapshot.git_facts(project, rows), "worktree", ws["id"], rows)
    in_use = [w for w in live(project) if not w.get("main")
              and w.get("branch") in _task_branches(project, ws)]
    if len(in_use) >= config.max_workers:
        raise Refused(f"{len(in_use)} worktree(s) in use and parallel.max_workers is "
                      f"{config.max_workers}; settle or remove one first")
    if gitutil.run(project.root, "cat-file", "-e",
                   f"{config.integration}:{CONFIG_REL}").returncode != 0:
        raise Refused(f"{CONFIG_REL} isn't committed on {config.integration}, so a worktree "
                      "wouldn't have it; commit it first")
    path = path_for(project, task_id)
    _exclude(project)
    argv = (["worktree", "add", "-q", str(path), branch]
            if gitutil.branch_exists(project.root, branch)
            else ["worktree", "add", "-q", "-b", branch, str(path), config.integration])
    made_branch = "-b" in argv
    done = gitutil.run(project.root, *argv)
    if done.returncode != 0:
        detail = done.stderr.strip().splitlines()
        raise WsError(f"git worktree add failed: {detail[-1] if detail else done.returncode}")
    try:
        _run_setup(project, path)
    except WsError:
        gitutil.run(project.root, "worktree", "remove", "--force", str(path))
        if made_branch:
            gitutil.run(project.root, "branch", "-D", branch)
        raise
    return path, True


def _task_branches(project: Project, ws: dict) -> set[str]:
    rows = tasks.load(project.tasks_path(ws), project.config)["tasks"]
    return {t.get("branch") or project.config.branch_for(t["id"]) for t in rows}


def uncommitted(path: Path) -> list[str]:
    """What removing this worktree would lose. Ignored files aren't on the list: they are
    build output and setup symlinks."""
    proc = gitutil.run(path, "status", "--porcelain")
    return proc.stdout.splitlines() if proc.returncode == 0 else ["(git status failed)"]


def remove(project: Project, ws: dict, task_id: str, *, force: bool = False,
           delete_branch: bool = False) -> str:
    """Remove a task's worktree, refusing to lose uncommitted work without force. The branch
    stays unless asked, and even then only a merged one goes: `git branch -d` checks that."""
    task = tasks.find_task(tasks.load(project.tasks_path(ws), project.config), task_id)
    branch = task.get("branch") or project.config.branch_for(task_id)
    found = for_branch(project, branch)
    if found is None:
        said = f"no worktree has {branch}"
    else:
        path = Path(found)
        lost = uncommitted(path)
        if lost and not force:
            raise Refused(f"{path} has uncommitted work (--force discards it):\n"
                          + "\n".join(lost[:10]))
        # Forced past git's own check for files in the way: ours above is the one that counts.
        done = gitutil.run(project.root, "worktree", "remove", "--force", str(path))
        if done.returncode != 0:
            shutil.rmtree(path, ignore_errors=True)
            gitutil.run(project.root, "worktree", "prune")
        said = f"removed {path}"
    if delete_branch and gitutil.branch_exists(project.root, branch):
        done = gitutil.run(project.root, "branch", "-d", branch)
        if done.returncode != 0:
            raise Refused(f"{said}; kept {branch}: it isn't merged")
        said += f", deleted {branch}"
    return said
