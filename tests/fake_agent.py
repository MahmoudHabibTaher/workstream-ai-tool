"""A scripted worker: what an agent does, with no model. It knows only what `ws brief` tells it,
so a brief that leaves something out fails the end-to-end tests.

    python -m tests.fake_agent <repo root> <workstream> <task id>

It writes the task's `files`, runs the checks, fills in the evidence and commits. What it does
with the code comes from the task's `notes`, a JSON object, so a test can script a misbehaving
worker: {"content": "...", "propose": "the call", "gotcha": "...", "block": "the reason"}.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

WS = [sys.executable, "-B", "-m", "workstream"]


def run(argv: list[str], cwd: Path, check: bool = True) -> str:
    proc = subprocess.run(argv, cwd=cwd, capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise SystemExit(f"{' '.join(argv)} failed:\n{proc.stdout}\n{proc.stderr}")
    return proc.stdout


def where_to_work(brief: str, root: Path) -> Path:
    """The brief names a worktree, or a branch to make in this checkout."""
    match = re.search(r"Work in `([^`]+)`", brief)
    if match:
        return Path(match[1])
    branch = re.search(r"`git switch -c ([^`]+)`", brief)[1]
    run(["git", "switch", "-q", "-c", branch], root)
    return root


def main(root_arg: str, ws_id: str, task_id: str) -> int:
    root = Path(root_arg)
    brief = run([*WS, "brief", task_id, "-w", ws_id], root)
    work = where_to_work(brief, root)
    task = json.loads(run([*WS, "show", task_id, "-w", ws_id, "--json"], work))
    script = json.loads(task["notes"] or "{}")

    if "block" in script:
        run([*WS, "evidence", "new", task_id, "-w", ws_id], work)
        path = work / "workstreams" / ws_id / "evidence" / f"{task_id}.md"
        path.write_text(f"# {task_id} evidence\n\n- **Status:** blocked ({script['block']})\n")
        run(["git", "add", "-A"], work)
        run(["git", "commit", "-q", "-m", f"{task_id}: blocked"], work)
        print(json.dumps({"task": task_id, "status": "blocked"}))
        return 0

    for name in task["files"]:
        path = work / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(script.get("content", f"ok from {task_id}\n"))
    run([*WS, "verify", task_id, "-w", ws_id], work)

    run([*WS, "evidence", "new", task_id, "-w", ws_id], work)
    path = work / "workstreams" / ws_id / "evidence" / f"{task_id}.md"
    text = path.read_text().replace("{{done, or blocked (the reason)}}", "done")
    text = text.replace("{{command and quoted output}}", "`ws verify` -> OK")
    if "propose" in script:
        text = re.sub(r"(## Proposed decisions\n\n).*?\n\n(## Gotchas)",
                      lambda m: f"{m[1]}### P1: {script['propose']}\nBecause. Rejected: the "
                                f"other way. See P1.\n\n{m[2]}", text, flags=re.DOTALL)
    if "gotcha" in script:
        text = text.replace("## Gotchas and follow-ups\n\nNone.",
                            f"## Gotchas and follow-ups\n\n{script['gotcha']}")
    path.write_text(text)

    run(["git", "add", "-A"], work)
    run(["git", "commit", "-q", "-m", f"{task_id}: {task['title']}"], work)
    run([*WS, "evidence", "check", task_id, "-w", ws_id], work)
    print(json.dumps({"task": task_id, "status": "done"}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(*sys.argv[1:]))
