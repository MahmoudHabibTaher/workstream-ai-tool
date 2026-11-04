"""`ws audit context`: how much of an agent's context this tool takes, per role, against a limit.

Limits cover only what the harness adds, not the agent's own system prompt or the project's
instructions. Prompts regrow one reasonable sentence at a time, so this fails CI rather than
waiting for someone to notice.

Static roles are read from the shipped files, and a skill's load includes every protocol section
it names. What a task costs is measured: a sample workstream runs through the real CLI in a
throwaway repository and its output is counted. Tokens are estimated at four characters each.
That is enough to catch growth; `ws audit usage` reads real transcripts.
"""

from __future__ import annotations

import io
import json
import math
import os
import subprocess
import tempfile
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from workstream import adapt, brief, protocol, tasks
from workstream.errors import WsError
from workstream.project import Project

ALWAYS_ON = "always-on"
WORKER = "worker"
COORDINATOR = "coordinator"
PER_TASK = "coordinator per task"
PLANNER = "planner"
REVIEWER = "reviewer"
BUDGETS = {ALWAYS_ON: 150, WORKER: 2500, COORDINATOR: 3000, PER_TASK: 400, PLANNER: 3000,
           REVIEWER: 1500}
# Briefs have their own limit: a task's "Builds on" section grows as its dependencies land.
BRIEF_BUDGET = 4500
SKILLS_BY_ROLE = {COORDINATOR: ("ws-run", "ws-coordinate"), PLANNER: ("ws-plan",),
                  REVIEWER: ("ws-review",)}
SPAWN_PROMPT = "Run `ws brief {task} -w {ws}` and follow it."
# What the skill asks a worker to send back.
SAMPLE_REPORT = "{task}: done, on its branch. Proposed: P1, keep the old format for now."
BATCH = ("S-01", "S-02", "S-03")
SAMPLE_BRANCH = "sample-trunk"
GIT_IDENTITY = {"GIT_CONFIG_GLOBAL": os.devnull, "GIT_CONFIG_NOSYSTEM": "1",
                "GIT_AUTHOR_NAME": "ws audit", "GIT_AUTHOR_EMAIL": "audit@example.invalid",
                "GIT_COMMITTER_NAME": "ws audit", "GIT_COMMITTER_EMAIL": "audit@example.invalid"}


def tokens(text: str) -> int:
    return math.ceil(len(text) / 4)


def always_on_text() -> str:
    """The pointer and each skill's name and description: what every session carries."""
    lines = [protocol.POINTER_FILE.read_text().strip()]
    for name in protocol.skill_names():
        lines.append(f"{name}: {protocol.description(protocol.skill_text(name))}")
    return "\n".join(lines)


def role_text(skills: tuple[str, ...], adapter: adapt.Adapter | None = None) -> str:
    """These skills in full, plus every protocol section they name, each counted once. With an
    adapter, as that agent gets them, with its notes."""
    texts = [adapt.skill_text(adapter, name) if adapter else protocol.skill_text(name)
             for name in skills]
    named = list(dict.fromkeys(s for text in texts for s in protocol.referenced_sections(text)))
    return "\n".join(texts + [protocol.section(s) for s in named])


def _sample_tasks() -> list[dict]:
    """A realistic batch, fuller than most: the measure shouldn't flatter."""
    acceptance = ["a named test covers the new behaviour and passes",
                  "the command prints the expected line for a valid input",
                  "an invalid input is refused with one line on stderr",
                  "the existing suite still passes"]
    files = ["src/alpha/{n}.py", "src/alpha/shared_{n}.py", "tests/test_{n}.py", "docs/{n}.md"]
    return [{"id": task_id, "phase": 1, "priority": 10 * n, "title": f"build part {n} of the work",
             "summary": "Add the new behaviour behind the existing interface, keeping the "
                        "current format readable, and cover it with tests.",
             "files": [f.format(n=n) for f in files], "acceptance": acceptance,
             "verify": ["test", "lint"], "notes": "Reuse the parser the module already has."}
            for n, task_id in enumerate(BATCH, 1)]


class _Flow:
    """The sample run. Everything printed to the coordinator goes in `seen`."""

    def __init__(self, root: Path) -> None:
        self.root = root
        self.seen: list[str] = []

    def git(self, *argv: str, cwd: Path | None = None) -> None:
        subprocess.run(["git", *argv], cwd=cwd or self.root, check=True, capture_output=True)

    def run(self, argv: tuple[str, ...], root: Path | None = None) -> tuple[int, str]:
        from workstream.cli import main  # the CLI imports this module

        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            try:
                code = main(["--root", str(root or self.root), *argv])
            except SystemExit as e:  # argparse refusing it, which must not end the audit quietly
                code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue()

    def ws(self, *argv: str, root: Path | None = None) -> str:
        code, text = self.run(argv, root)
        if code != 0:
            raise WsError(f"audit sample: `ws {' '.join(argv)}` failed:\n{text}")
        return text

    def seen_ws(self, *argv: str) -> str:
        text = self.ws(*argv)
        self.seen.append(text)
        return text

    def set_up(self) -> None:
        self.git("init", "-q", "-b", SAMPLE_BRANCH)
        self.ws("init", "--integration", SAMPLE_BRANCH)
        config = self.root / ".workstream" / "config.toml"
        config.write_text(config.read_text().replace(
            "[commands]\n", '[commands]\ntest = "true"\nlint = "true"\n'))
        self.ws("new", "sample", "--title", "Sample", "--summary", "A sample.", "--prefix", "S")
        seed = self.root.parent / "seed.json"
        seed.write_text(json.dumps(_sample_tasks()))
        self.ws("seed", "-w", "sample", str(seed))
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "plan")

    def run_batch(self) -> str:
        """One batch start to finish. Returns the first worker's orientation."""
        self.seen.append(self.ws("wave", "-w", "sample"))
        self.seen_ws("claim", "--commit", "-w", "sample", "--by", "audit", *BATCH)
        self.seen_ws("worktree", "create", "-w", "sample", *BATCH)
        orientation = ""
        for task_id in BATCH:
            prompt = SPAWN_PROMPT.format(task=task_id, ws="sample")
            self.seen.append(prompt)
            slug = task_id.lower()
            where = self.root / ".workstream" / "worktrees" / slug
            worker_brief = self.ws("brief", task_id, "-w", "sample")
            orientation = orientation or prompt + "\n" + worker_brief
            self._work(where, task_id)
            self.seen.append(SAMPLE_REPORT.format(task=task_id))
        self.seen_ws("settle", "-w", "sample", *BATCH)
        return orientation

    def _work(self, where: Path, task_id: str) -> None:
        (where / f"{task_id}.txt").write_text("done\n")
        self.ws("verify", task_id, "-w", "sample", root=where)
        self.ws("evidence", "new", task_id, "-w", "sample", root=where)
        path = where / "workstreams" / "sample" / "evidence" / f"{task_id}.md"
        text = path.read_text().replace("{{done, or blocked (the reason)}}", "done")
        path.write_text(text.replace("{{command and quoted output}}", "ran it: ok"))
        self.git("add", "-A", cwd=where)
        self.git("commit", "-q", "-m", f"{task_id} work", cwd=where)


def measure_flow() -> dict[str, str]:
    """{role: text} for the two roles only a real run can measure. Per-task text is the whole
    batch's; the caller divides."""
    with tempfile.TemporaryDirectory(prefix="ws-audit-") as tmp, \
            mock.patch.dict(os.environ, GIT_IDENTITY):
        root = Path(tmp).resolve() / "repo"
        root.mkdir()
        flow = _Flow(root)
        flow.set_up()
        orientation = flow.run_batch()
    return {WORKER: orientation, PER_TASK: "\n".join(flow.seen)}


def role_rows(measured: dict[str, str] | None = None) -> list[dict]:
    """One row per role: {role, tokens, budget, ok}."""
    measured = measure_flow() if measured is None else measured
    used = {ALWAYS_ON: tokens(always_on_text()), WORKER: tokens(measured[WORKER]),
            PER_TASK: math.ceil(tokens(measured[PER_TASK]) / len(BATCH))}
    for role, skills in SKILLS_BY_ROLE.items():
        used[role] = tokens(role_text(skills))
    rows = [{"role": role, "tokens": used[role], "budget": budget, "ok": used[role] <= budget}
            for role, budget in BUDGETS.items()]
    return rows + adapter_rows(measured)


def adapter_rows(measured: dict[str, str]) -> list[dict]:
    """What each role costs as one agent gets it: the pointer block, its notes, its worker file."""
    rows = []
    for name in adapt.names():
        adapter = adapt.load(name)
        used = {ALWAYS_ON: tokens(adapt.always_on_text(adapter)),
                WORKER: tokens(measured[WORKER] + adapt.worker_text(adapter))}
        for role, skills in SKILLS_BY_ROLE.items():
            used[role] = tokens(role_text(skills, adapter))
        rows += [{"role": f"{role} on {name}", "tokens": count, "budget": BUDGETS[role],
                  "ok": count <= BUDGETS[role]} for role, count in used.items()]
    return rows


def project_rows(project: Project, ws: dict) -> list[dict]:
    """Each open task's brief without the plan sections it cites, which a worker needs and the
    limit leaves out. One over the limit is a task that should be split."""
    path = project.tasks_path(ws)
    if not path.exists():
        return []
    data = tasks.load(path, project.config)
    rows = []
    for task in data["tasks"]:
        if task["status"] not in tasks.OPEN_STATUSES:
            continue
        text = brief.render(project, ws, task, data["tasks"], scope=data.get("scope"),
                            cited=False)
        used = tokens(text)
        rows.append({"role": f"brief {task['id']}", "tokens": used, "budget": BRIEF_BUDGET,
                     "ok": used <= BRIEF_BUDGET})
    return rows


def format_rows(rows: list[dict]) -> list[str]:
    width = max(len(r["role"]) for r in rows)
    return [f"{r['role']:<{width}}  {r['tokens']:>6}  of {r['budget']:>5}  "
            f"{'ok' if r['ok'] else 'OVER'}" for r in rows]
