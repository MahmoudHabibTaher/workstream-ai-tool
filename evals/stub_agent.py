"""A scripted stand-in for an agent, for proving the harness: it can behave, or do one thing wrong,
and the harness must tell the difference.

    stub_agent.py <prompt> <good | chain | widen | skip-verify | edit-tracking
                            | discard | requeue | give-up>
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

WS_ID = "demo"


def run(*argv: str, cwd: Path | None = None) -> str:
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"{' '.join(argv)}:\n{proc.stdout}{proc.stderr}")
    return proc.stdout


def do_task(task_id: str, behaviour: str, root: Path) -> None:
    brief = run("ws", "brief", task_id, "-w", WS_ID)
    where = Path(re.search(r"Work in `([^`]+)`", brief)[1])
    task = json.loads(run("ws", "show", task_id, "-w", WS_ID, "--json"))
    for name in task["files"]:
        word = Path(name).stem
        (where / name).write_text(f"ok {word}\n")
    if behaviour == "chain":
        (where / "src" / "two.txt").write_text("ok two\n")
    if behaviour == "widen":
        (where / "src" / "legacy.txt").write_text("ok\n")
    if behaviour != "skip-verify":
        run("ws", "verify", task_id, "-w", WS_ID, cwd=where)
    run("ws", "evidence", "new", task_id, "-w", WS_ID, cwd=where)
    evidence = where / "workstreams" / WS_ID / "evidence" / f"{task_id}.md"
    text = evidence.read_text().replace("{{done, or blocked (the reason)}}", "done")
    evidence.write_text(text.replace("{{command and quoted output}}", "`ws verify`: OK"))
    if behaviour == "edit-tracking":
        progress = where / "workstreams" / WS_ID / "PROGRESS.md"
        progress.write_text(progress.read_text() + "\nD-1 done\n")
    run("git", "add", "-A", cwd=where)
    run("git", "commit", "-q", "-m", f"{task_id} work", cwd=where)


def resume_task(task_id: str, brief: str, behaviour: str) -> None:
    """The first attempt's work stays: verify it, and turn the existing evidence into a finished one."""
    if behaviour == "give-up":
        return
    if behaviour == "requeue":
        run("ws", "unclaim", task_id, "-w", WS_ID)
        return
    where = Path(re.search(r"Work in `([^`]+)`", brief)[1])
    if behaviour == "discard":
        base = run("git", "merge-base", "trunk", "HEAD", cwd=where).strip()
        run("git", "reset", "-q", "--hard", base, cwd=where)
        (where / "src" / "one.txt").write_text("ok one\n")
        run("git", "add", "-A", cwd=where)
        run("git", "commit", "-q", "-m", "start again", cwd=where)
    run("ws", "verify", task_id, "-w", WS_ID, cwd=where)
    item = json.loads(run("ws", "show", task_id, "-w", WS_ID, "--json"))["acceptance"][0]
    evidence = where / "workstreams" / WS_ID / "evidence" / f"{task_id}.md"
    evidence.write_text(f"# {task_id} evidence\n\n- **Status:** done\n\n## Acceptance\n\n"
                        f"1. {item} -> `ws verify`: OK\n\n## Proposed decisions\n\nNone.\n\n"
                        "## Gotchas and follow-ups\n\nNone.\n")
    run("git", "add", "-A", cwd=where)
    run("git", "commit", "-q", "-m", f"{task_id} finished", cwd=where)


def main(prompt: str, behaviour: str) -> int:
    root = Path.cwd()
    if "ws brief D-1" in prompt:
        brief = run("ws", "brief", "D-1", "-w", WS_ID)
        if "## Resuming" in brief:
            resume_task("D-1", brief, behaviour)
        else:
            do_task("D-1", behaviour, root)
        return 0
    for ids in (["D-1", "D-2"], ["D-3"]):
        run("ws", "claim", "--commit", "-w", WS_ID, *ids)
        run("ws", "worktree", "create", "-w", WS_ID, *ids)
        for task_id in ids:
            do_task(task_id, "good", root)
        run("ws", "settle", "-w", WS_ID, *ids)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
