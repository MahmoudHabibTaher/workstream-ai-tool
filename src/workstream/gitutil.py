"""Small git helpers that read. A failure comes back as data or None, never an exception."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run(repo_root: Path, *argv: str, env: dict | None = None) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *argv], cwd=repo_root, capture_output=True, text=True,
                          errors="replace", env=env)


def rev_parse(repo_root: Path, rev: str, short: bool = False) -> str:
    """The commit `rev` names, or "" when git fails or it doesn't resolve."""
    argv = ["rev-parse", *(["--short"] if short else []), "--verify", "--quiet", rev]
    try:
        proc = run(repo_root, *argv)
    except OSError:
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


def existing_commits(repo_root: Path, revs: list[str]) -> set[str]:
    """The ones of these that name a commit, in one process rather than one each. Empty when git
    can't be run."""
    if not revs:
        return set()
    wanted = list(dict.fromkeys(revs))
    try:
        proc = subprocess.run(["git", "cat-file", "--batch-check=%(objectname)"], cwd=repo_root,
                              input="".join(f"{rev}^{{commit}}\n" for rev in wanted),
                              capture_output=True, text=True, errors="replace")
    except OSError:
        return set()
    if proc.returncode != 0:
        return set()
    answers = proc.stdout.splitlines()
    # A name git can't settle comes back as "<name> missing" or "<name> ambiguous".
    return {rev for rev, answer in zip(wanted, answers) if " " not in answer}


def common_dir(repo_root: Path) -> Path | None:
    """The .git directory every worktree of this repository shares, or None outside one."""
    try:
        proc = run(repo_root, "rev-parse", "--git-common-dir")
    except OSError:
        return None
    if proc.returncode != 0 or not proc.stdout.strip():
        return None
    return (Path(repo_root) / proc.stdout.strip()).resolve()


def is_ancestor(repo_root: Path, older: str, newer: str) -> bool:
    return run(repo_root, "merge-base", "--is-ancestor", older, newer).returncode == 0


def current_branch(repo_root: Path) -> str:
    """The branch checked out here; "HEAD" when detached, "" when git can't say."""
    proc = run(repo_root, "rev-parse", "--abbrev-ref", "HEAD")
    return proc.stdout.strip() if proc.returncode == 0 else ""


def branch_exists(repo_root: Path, branch: str) -> bool:
    return run(repo_root, "rev-parse", "--verify", "--quiet",
               f"refs/heads/{branch}").returncode == 0


def toplevel(start: Path) -> Path | None:
    try:
        proc = run(start, "rev-parse", "--show-toplevel")
    except OSError:
        return None
    return Path(proc.stdout.strip()) if proc.returncode == 0 else None


def default_branch(repo_root: Path) -> str:
    """The remote's default branch, else the current branch, else main."""
    try:
        proc = run(repo_root, "symbolic-ref", "--short", "refs/remotes/origin/HEAD")
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip().removeprefix("origin/")
        proc = run(repo_root, "symbolic-ref", "--short", "HEAD")
        if proc.returncode == 0 and proc.stdout.strip():
            return proc.stdout.strip()
    except OSError:
        pass
    return "main"


def tracked_and_untracked(repo_root: Path, *pathspecs: str) -> list[str]:
    """Paths git knows or would add (ignored files left out), relative to repo_root."""
    try:
        proc = run(repo_root, "ls-files", "--cached", "--others", "--exclude-standard", "--",
                   *pathspecs)
    except OSError:
        return []
    return proc.stdout.splitlines() if proc.returncode == 0 else []
