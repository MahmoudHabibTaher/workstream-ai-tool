"""Read-only git helpers. A failure comes back as data or None, never an exception."""

from __future__ import annotations

import subprocess
from pathlib import Path


def run(repo_root: Path, *argv: str) -> subprocess.CompletedProcess:
    return subprocess.run(["git", *argv], cwd=repo_root, capture_output=True, text=True)


def rev_parse(repo_root: Path, rev: str, short: bool = False) -> str:
    """The commit `rev` names, or "" when git fails or it doesn't resolve."""
    argv = ["rev-parse", *(["--short"] if short else []), "--verify", "--quiet", rev]
    try:
        proc = run(repo_root, *argv)
    except OSError:
        return ""
    return proc.stdout.strip() if proc.returncode == 0 else ""


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
