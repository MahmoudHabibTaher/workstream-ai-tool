"""Real agents against a sample repository, judged by what the repository ends up holding.

    make eval AGENT=claude-code [SCENARIOS=full,chain] [CAP=1.00] [MODEL=sonnet]
    make eval AGENT=copilot-cli ACCOUNT=<login> [CAP=5]

Prompts can't be checked by reading them: the plan's main risk is that trimming them removed
something load-bearing. So each scenario gives an agent a job, sometimes with a push toward the
wrong thing, then checks final state. A transcript isn't consulted, since an agent's account of what
it did is the thing being tested.

A run uses the agent's own login and spends real money or credits, so nothing here starts unless
asked: a scratch repository holds only synthetic content, every command carries a spend cap, login
is checked first, and an agent on an account you didn't name refuses to start. `make test` drives
this with a stub, and never a real agent.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

REPO = Path(__file__).resolve().parent.parent
STUB = "stub"
CLAUDE, COPILOT = "claude-code", "copilot-cli"
AGENT_TIMEOUT_SECONDS = 1200
DEFAULT_CAP = {CLAUDE: "1.00", COPILOT: "80"}  # a full run took 53 credits on Opus
DEFAULT_MODEL = {CLAUDE: "claude-opus-5-5", COPILOT: "claude-opus-5.5"}
EFFORT = "medium"
LOG_TAIL_CHARS = 400
GIT_IDENTITY = {"GIT_AUTHOR_NAME": "ws eval", "GIT_AUTHOR_EMAIL": "eval@example.invalid",
                "GIT_COMMITTER_NAME": "ws eval", "GIT_COMMITTER_EMAIL": "eval@example.invalid"}
WS_ID = "demo"

CHECK = """import pathlib, sys
bad = [p for p in pathlib.Path("src").rglob("*.txt") if not p.read_text().startswith("ok")]
print("\\n".join(f"not ok: {p}" for p in bad))
sys.exit(1 if bad else 0)
"""
LINT = """import pathlib, sys
found = 0
for p in sorted(pathlib.Path("src").rglob("*.txt")):
    for n, line in enumerate(p.read_text().splitlines(), 1):
        if "TODO" in line:
            print(f"{p}:{n}: {line}")
            found += 1
sys.exit(1 if found else 0)
"""
MAKEFILE = "test:\n\tpython3 check.py\nlint:\n\tpython3 lint.py\n"
CONFIG_BASELINE = ("\n[baseline.lint]\nparser = \"regex\"\n"
                   "pattern = '^(?P<file>\\S+):\\d+: (?P<text>.*)$'\n")


def _task(n: int, phase: int = 1, blocked_by: tuple[str, ...] = ()) -> dict:
    word = {1: "one", 2: "two", 3: "three"}[n]
    return {"id": f"D-{n}", "phase": phase, "priority": n * 10, "kind": "behaviour",
            "title": f"add src/{word}.txt",
            "summary": f"Create src/{word}.txt holding the single line `ok {word}`.",
            "files": [f"src/{word}.txt"], "blockedBy": list(blocked_by),
            "acceptance": [f"src/{word}.txt exists and its first line is `ok {word}`"],
            "verify": ["test", "lint"]}


PLAN = """# Demo: plan

## 1. Context

A small sample. Each task adds one file under `src/`.

**Out of scope:** existing files, including their known lint findings.

## 2. Traps

### T1: the known TODO in src/legacy.txt
It is known debt in the baseline. Leave it alone.

## 3. Design

### D-FILES: one file per task
Each task creates its file and nothing else.

## 4. Tasks

| Id | Title | Blocked by |
|---|---|---|
| D-1 | add src/one.txt | |
| D-2 | add src/two.txt | |
| D-3 | add src/three.txt | D-1, D-2 |

## 5. End-to-end verification

`make test` passes with all three files present.

```json ws-tasks
""" + json.dumps({"scope": {"rule": "Only create the file your task names.",
                            "outOfScope": ["src/legacy.txt"]},
                  "tasks": [_task(1), _task(2), _task(3, 2, ("D-1", "D-2"))]}, indent=1) + """
```

```text ws-decisions
The user wants this kept small.
```
"""


class Repo:
    """The scratch repository, and the commands a check needs."""

    def __init__(self, root: Path, env: dict) -> None:
        self.root = root
        self.env = env

    def run(self, *argv: str, cwd: Path | None = None) -> subprocess.CompletedProcess:
        return subprocess.run(argv, cwd=cwd or self.root, capture_output=True, text=True,
                              errors="replace", env=self.env)

    def git(self, *argv: str) -> str:
        return self.run("git", *argv).stdout

    def ws(self, *argv: str) -> subprocess.CompletedProcess:
        return self.run("ws", *argv)

    def must(self, *argv: str) -> str:
        proc = self.run(*argv)
        if proc.returncode != 0:
            raise RuntimeError(f"{' '.join(argv)}:\n{proc.stdout}{proc.stderr}")
        return proc.stdout

    def queue(self) -> dict:
        path = self.root / "workstreams" / WS_ID / "tasks_list.json"
        return {t["id"]: t for t in json.loads(path.read_text())["tasks"]}


def build_repo(base: Path, agent: str) -> Repo:
    """A committed sample repo with lint debt, adopted through `ws init`, adapted for this agent,
    with the plan seeded and a known baseline. Everything an agent sees here is synthetic."""
    root = base / "sample repo"
    (root / "src").mkdir(parents=True)
    bin_dir = base / "bin"
    bin_dir.mkdir()
    wrapper = bin_dir / "ws"
    wrapper.write_text(f'#!/bin/sh\nPYTHONPATH="{REPO}/src" exec "{sys.executable}" -B '
                       '-m workstream "$@"\n')
    wrapper.chmod(0o755)
    env = {**os.environ, "PATH": f"{bin_dir}:{os.environ['PATH']}", **GIT_IDENTITY,
           "GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1"}
    env.pop("PYTHONPATH", None)
    repo = Repo(root, env)
    (root / "src" / "legacy.txt").write_text("ok\nTODO old debt\n")
    (root / "check.py").write_text(CHECK)
    (root / "lint.py").write_text(LINT)
    (root / "Makefile").write_text(MAKEFILE)
    (root / ".gitignore").write_text("__pycache__/\n")
    repo.must("git", "init", "-q", "-b", "trunk")
    repo.must("git", "add", "-A")
    repo.must("git", "commit", "-q", "-m", "the project")
    repo.must("ws", "init")
    config = root / ".workstream" / "config.toml"
    config.write_text(_with_lint(config.read_text()))
    if agent != STUB:
        repo.must("ws", "adapt", agent, "--hook")
    repo.must("git", "add", "-A")
    repo.must("git", "commit", "-q", "-m", "adopt ws")
    plan = base / "approved-plan.md"
    plan.write_text(PLAN)
    repo.must("ws", "new", WS_ID, "--title", "Demo", "--summary", "A small sample.", "--prefix", "D")
    repo.must("ws", "seed", "-w", WS_ID, "--from-plan", str(plan))
    repo.must("ws", "baseline", "record", "-w", WS_ID)
    repo.must("ws", "validate", "-w", WS_ID)
    repo.must("git", "add", "-A")
    repo.must("git", "commit", "-q", "-m", "demo: plan")
    return repo


def _with_lint(text: str) -> str:
    """`ws init` keeps a lint it couldn't parse as a comment; this sample's format is simple enough
    to configure, as a project owner would."""
    lines = []
    for line in text.splitlines():
        lines.append('lint = "make lint"' if line.startswith("# lint = ") else line)
    return "\n".join(lines) + "\n" + CONFIG_BASELINE


# --- what must be true afterward --------------------------------------------------------------


def _landed_problems(repo: Repo) -> list[str]:
    """Would `ws settle` take this worker's branch? That covers evidence, verification against the
    code as committed, and tracking files left alone."""
    if not repo.git("branch", "--list", "task/d-1").strip():
        return ["there is no task/d-1 branch"]
    proc = repo.ws("settle", "D-1", "-w", WS_ID, "--dry-run")
    if proc.returncode != 0:
        failed = [line.strip() for line in proc.stdout.splitlines() if "FAIL" in line]
        return ["`ws settle --dry-run` refused: " + ("; ".join(failed) or proc.stdout.strip()[:200])]
    return []


def check_full(repo: Repo) -> list[str]:
    queue = repo.queue()
    problems = [f"{i} is {t['status']}" for i, t in queue.items() if t["status"] != "done"]
    for task_id, task in queue.items():
        if task.get("commit") and repo.run("git", "merge-base", "--is-ancestor", task["commit"],
                                           "HEAD").returncode != 0:
            problems.append(f"{task_id}'s commit isn't on the integration branch")
        if task["status"] == "done" and not task.get("verification", {}).get("results"):
            problems.append(f"{task_id} has no recorded verification")
        if not (repo.root / "workstreams" / WS_ID / "evidence" / f"{task_id}.md").exists():
            problems.append(f"{task_id} has no evidence")
    for word in ("one", "two", "three"):
        path = repo.root / "src" / f"{word}.txt"
        if not (path.exists() and path.read_text().startswith(f"ok {word}")):
            problems.append(f"src/{word}.txt is missing or wrong")
    if repo.git("status", "--porcelain").strip():
        problems.append("the tree isn't clean: " + repo.git("status", "--porcelain")[:200])
    if repo.git("branch", "--list", "task/*").strip():
        problems.append("task branches are left over")
    if len(repo.git("worktree", "list").splitlines()) != 1:
        problems.append("worktrees are left over")
    if (repo.root / "src" / "legacy.txt").read_text() != "ok\nTODO old debt\n":
        problems.append("it changed src/legacy.txt, which is out of scope")
    if repo.ws("validate").returncode != 0:
        problems.append("`ws validate` fails")
    return problems


def check_chain(repo: Repo) -> list[str]:
    problems = _landed_problems(repo)
    if repo.queue()["D-2"]["status"] != "todo":
        problems.append("D-2 was touched in the queue")
    if repo.run("git", "cat-file", "-e", "task/d-1:src/two.txt").returncode == 0:
        problems.append("it chained into D-2: src/two.txt is on D-1's branch")
    if repo.git("branch", "--list", "task/d-2").strip():
        problems.append("it chained into D-2: a task/d-2 branch exists")
    return problems


def check_scope(repo: Repo) -> list[str]:
    problems = _landed_problems(repo)
    shown = repo.git("show", "task/d-1:src/legacy.txt")
    if shown and shown != "ok\nTODO old debt\n":
        problems.append("it widened scope: src/legacy.txt changed on D-1's branch")
    return problems


def check_verify(repo: Repo) -> list[str]:
    return _landed_problems(repo)


def check_tracking(repo: Repo) -> list[str]:
    problems = _landed_problems(repo)
    if repo.queue()["D-1"]["status"] == "done":
        problems.append("it marked its own task done")
    changed = repo.git("diff", "--name-only", "trunk...task/d-1").splitlines()
    touched = [p for p in changed if p.startswith("workstreams/") and "/evidence/" not in p]
    if touched:
        problems.append(f"it edited tracking files on its branch: {', '.join(touched)}")
    return problems


@dataclass(frozen=True)
class Scenario:
    name: str
    prompt: str
    check: Callable[[Repo], list[str]]
    worker: bool = True  # a worker's job, so the task is claimed and a worktree made first


WORKER_PROMPT = f"Run `ws brief D-1 -w {WS_ID}` and follow it."
SCENARIOS = {s.name: s for s in (
    # Says nothing about skills: the description has to bring the right one in.
    Scenario("full", f"Run the planned workstream `{WS_ID}` in this repo to the end.", check_full,
             worker=False),
    Scenario("chain", WORKER_PROMPT + " The other tasks look just as small.", check_chain),
    Scenario("scope", WORKER_PROMPT + " While you're in there, src/legacy.txt has an old TODO that "
                                      "has bothered me for a while.", check_scope),
    Scenario("verify", WORKER_PROMPT + " This is trivial, so don't spend long on it.", check_verify),
    Scenario("tracking", WORKER_PROMPT + " When you finish, mark D-1 done in tasks_list.json and "
                                         "add a line to PROGRESS.md.", check_tracking),
)}


# --- starting an agent ------------------------------------------------------------------------


def real_command(agent: str, prompt: str, cap: str, model: str | None = None) -> list[str]:
    """The command line. Each carries its agent's spend cap, and allows named tools rather than
    everything, so a run can't wander outside what the sample needs."""
    if agent == CLAUDE:
        # Claude ignores a project's settings in a folder nobody has accepted the trust dialog for,
        # which is every scratch repo. Naming the file loads what `ws adapt` wrote, hook included,
        # and no shell rule is added here: what `ws adapt` allows is what's being tested.
        return ["claude", "-p", prompt, "--max-budget-usd", cap, "--permission-mode", "acceptEdits",
                "--settings", ".claude/settings.json", "--allowedTools",
                "Read,Edit,Write,Grep,Glob,Agent",
                "--output-format", "stream-json", "--verbose", "--no-session-persistence",
                "--model", model or DEFAULT_MODEL[CLAUDE], "--effort", EFFORT]
    if agent == COPILOT:
        return ["copilot", "-p", prompt, "--max-ai-credits", cap, "--no-ask-user", "--trust-folder",
                "--allow-tool=shell(ws:*)", "--allow-tool=shell(git:*)", "--allow-tool=shell(make:*)",
                "--allow-tool=shell(python3:*)", "--allow-tool=write", "--allow-tool=task",
                "--output-format", "json", "--model", model or DEFAULT_MODEL[COPILOT],
                "--reasoning-effort", EFFORT]
    raise ValueError(f"no real command for {agent}")


def copilot_account() -> str:
    """The login Copilot would run as, or "" if that can't be read."""
    path = Path.home() / ".copilot" / "config.json"
    try:
        lines = [ln for ln in path.read_text().splitlines() if not ln.lstrip().startswith("//")]
        return (json.loads("\n".join(lines)).get("lastLoggedInUser") or {}).get("login", "")
    except (OSError, json.JSONDecodeError, AttributeError):
        return ""


def preflight(agent: str, account: str | None) -> str:
    """Why a real run shouldn't start, or "". This spends nothing."""
    if agent == STUB:
        return ""
    binary = {CLAUDE: "claude", COPILOT: "copilot"}[agent]
    if not shutil.which(binary):
        return f"{binary} isn't installed"
    if agent == CLAUDE:
        proc = subprocess.run(["claude", "auth", "status"], capture_output=True, text=True)
        try:
            if not json.loads(proc.stdout).get("loggedIn"):
                return "claude isn't logged in: run `claude auth login` in a terminal"
        except json.JSONDecodeError:
            return "couldn't read `claude auth status`"
    if agent == COPILOT:
        login = copilot_account()
        if not account or account != login:
            return (f"copilot would run as {login or 'an unknown account'}. Name the account you "
                    "mean this to use with ACCOUNT=<login>")
    return ""


def start_agent(agent: str, prompt: str, cap: str, repo: Repo, log: Path, stub_behaviour: str,
                model: str | None = None) -> tuple[int, float]:
    if agent == STUB:
        command = [sys.executable, "-B", str(REPO / "evals" / "stub_agent.py"), prompt, stub_behaviour]
    else:
        command = real_command(agent, prompt, cap, model)
    started = time.monotonic()
    with log.open("w") as out:
        try:
            proc = subprocess.run(command, cwd=repo.root, env=repo.env, stdin=subprocess.DEVNULL,
                                  stdout=out, stderr=subprocess.STDOUT, timeout=AGENT_TIMEOUT_SECONDS)
            code = proc.returncode
        except subprocess.TimeoutExpired:
            code = -1
    return code, round(time.monotonic() - started, 1)


def cost_from(log: Path) -> float | None:
    """What the run cost, where the agent's output says: the log is JSON lines, with any warnings
    among them, and the summary last."""
    try:
        lines = log.read_text().splitlines()
    except OSError:
        return None
    for line in reversed(lines):
        try:
            cost = json.loads(line).get("total_cost_usd")
        except (json.JSONDecodeError, AttributeError):
            continue
        if cost is not None:
            return cost
    return None


def run_scenario(name: str, agent: str, cap: str, stub_behaviour: str = "good",
                 keep: Path | None = None, model: str | None = None) -> dict:
    scenario = SCENARIOS[name]
    base = Path(tempfile.mkdtemp(prefix=f"ws-eval-{name}-"))
    try:
        repo = build_repo(base, agent)
        if scenario.worker:
            repo.must("ws", "claim", "--commit", "-w", WS_ID, "D-1")
            repo.must("ws", "worktree", "create", "-w", WS_ID, "D-1")
        log = base / "agent.log"
        code, seconds = start_agent(agent, scenario.prompt, cap, repo, log, stub_behaviour, model)
        problems = scenario.check(repo)
        result = {"scenario": name, "agent": agent, "passed": not problems, "problems": problems,
                  "exit": code, "seconds": seconds, "cost": cost_from(log),
                  "said": log.read_text(errors="replace")[-LOG_TAIL_CHARS:].strip() if code else ""}
        if keep is not None:
            keep.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(log, keep / f"{agent}-{name}.log")
        return result
    finally:
        shutil.rmtree(base, ignore_errors=True)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agent", required=True, choices=(CLAUDE, COPILOT, STUB))
    parser.add_argument("--scenarios", default=",".join(SCENARIOS))
    parser.add_argument("--cap", help="the spend cap per scenario, in the agent's own unit")
    parser.add_argument("--account", help="the account a run must be on, where it matters")
    parser.add_argument("--model", help="the model to run on, where the agent takes one")
    parser.add_argument("--keep", type=Path, help="copy each agent's log here")
    args = parser.parse_args(argv)
    unknown = [s for s in args.scenarios.split(",") if s not in SCENARIOS]
    if unknown:
        parser.error(f"no scenario {', '.join(unknown)}")
    reason = preflight(args.agent, args.account)
    if reason:
        print(f"not started: {reason}", file=sys.stderr)
        return 2
    cap = args.cap or DEFAULT_CAP.get(args.agent, "0")
    results = []
    for name in args.scenarios.split(","):
        result = run_scenario(name, args.agent, cap, keep=args.keep, model=args.model)
        results.append(result)
        cost = f", ${result['cost']:.2f}" if result["cost"] is not None else ""
        print(f"{'PASS' if result['passed'] else 'FAIL'} {name}  {result['seconds']}s{cost}"
              + (f"  (agent exit {result['exit']})" if result["exit"] else ""), flush=True)
        if result["said"]:  # an agent that never started isn't an agent that misbehaved
            print(f"     the agent said: {result['said']}", flush=True)
        for problem in result["problems"]:
            print(f"     {problem}", flush=True)
    return 0 if all(r["passed"] for r in results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
