"""M2's definition of done: a scripted agent takes a real workstream from plan to close, one
task at a time and in parallel, using only what the CLI tells it. Every command here is a real
process in a real repository, in the order a coordinator would run them."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import GIT_ENV

REPO = Path(__file__).resolve().parent.parent
WS = [sys.executable, "-B", "-m", "workstream"]
WAVE_READY, WAVE_FINISHED, WAVE_STUCK = 0, 2, 3

# The project's own checks: every file under src/ must start "ok", and TODOs are lint findings.
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


def tasks_json(tasks: list[dict]) -> str:
    return json.dumps(tasks, indent=1)


def plan_text(tasks: list[dict]) -> str:
    return f"""# Sample: plan

## 1. Context

Why.

## 2. Traps

### T1: the obvious fix is wrong
Use the other one.

## 4. Tasks

```json ws-tasks
{tasks_json(tasks)}
```

```text ws-decisions
The user kept it small.
```
"""


class EndToEnd(unittest.TestCase):
    def setUp(self) -> None:
        env = mock.patch.dict(os.environ, {**GIT_ENV, "PYTHONPATH": f"{REPO}/src:{REPO}"})
        env.start()
        self.addCleanup(env.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "a repo"  # real ones have spaces
        self.root.mkdir()
        self.git("init", "-q", "-b", "trunk")
        (self.root / "src").mkdir()
        (self.root / "src" / "legacy.txt").write_text("ok\nTODO old debt\n")
        (self.root / "check.py").write_text(CHECK)
        (self.root / "lint.py").write_text(LINT)
        self.ws("init", "--integration", "trunk")
        config = self.root / ".workstream" / "config.toml"
        text = config.read_text().replace(
            "[commands]\n",
            f'[commands]\ntest = "{sys.executable} check.py"\nlint = "{sys.executable} lint.py"\n')
        text = text.replace("[adequacy]\n", '[adequacy]\nbehaviour = ["test"]\n')
        text += ("\n[baseline.lint]\nparser = \"regex\"\n"
                 "pattern = '^(?P<file>\\S+):\\d+: (?P<text>.*)$'\n")
        config.write_text(text)
        self.commit("project set up")
        self.ws("new", "sample", "--title", "Sample", "--summary", "A sample.", "--prefix", "S")
        self.folder = self.root / "workstreams" / "sample"

    # --- processes ------------------------------------------------------------------------

    def ws(self, *argv: str, code: int | None = 0) -> str:
        proc = subprocess.run([*WS, *argv], cwd=self.root, capture_output=True, text=True)
        if code is not None:
            self.assertEqual(proc.returncode, code, f"ws {' '.join(argv)}:\n{proc.stdout}{proc.stderr}")
        return proc.stdout + proc.stderr

    def git(self, *argv: str) -> str:
        return subprocess.run(["git", *argv], cwd=self.root, capture_output=True, text=True,
                              check=True).stdout

    def commit(self, message: str) -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def agent(self, task_id: str) -> subprocess.Popen:
        return subprocess.Popen([sys.executable, "-B", "-m", "tests.fake_agent", str(self.root),
                                 "sample", task_id], cwd=REPO, stdout=subprocess.PIPE,
                                stderr=subprocess.PIPE, text=True)

    def wait(self, procs: list[subprocess.Popen]) -> list[dict]:
        reports = []
        for proc in procs:
            out, err = proc.communicate(timeout=120)
            self.assertEqual(proc.returncode, 0, err)
            reports.append(json.loads(out))
        return reports

    # --- the coordinator ------------------------------------------------------------------

    def plan(self, tasks: list[dict]) -> None:
        path = self.root.parent / "approved-plan.md"
        path.write_text(plan_text(tasks))
        self.ws("seed", "--from-plan", str(path))
        self.ws("validate")
        self.ws("baseline", "record")
        self.commit("sample: plan")

    def wave(self) -> tuple[int, list[str]]:
        proc = subprocess.run([*WS, "wave"], cwd=self.root, capture_output=True, text=True)
        if proc.returncode != WAVE_READY:
            return proc.returncode, []
        queue = json.loads((self.folder / "tasks_list.json").read_text())["tasks"]
        ids = [t["id"] for t in queue if f"  {t['id']}  " in proc.stdout]
        return proc.returncode, ids

    def run_sequentially(self) -> None:
        for _ in range(20):
            code, ids = self.wave()
            if code == WAVE_FINISHED:
                return
            self.assertEqual(code, WAVE_READY)
            task_id = ids[0]
            self.ws("claim", "--commit", task_id, "--by", "sequential")
            self.wait([self.agent(task_id)])
            self.git("switch", "-q", "trunk")
            self.ws("settle", task_id)
        self.fail("the queue never finished")

    def run_in_parallel(self) -> None:
        for _ in range(20):
            code, ids = self.wave()
            if code == WAVE_FINISHED:
                return
            self.assertEqual(code, WAVE_READY)
            self.ws("claim", "--commit", *ids, "--by", "parallel")
            self.ws("worktree", "create", *ids)
            self.wait([self.agent(i) for i in ids])
            self.ws("settle", *ids)
        self.fail("the queue never finished")

    # --- what must be true afterward ------------------------------------------------------

    def queue(self) -> dict:
        return {t["id"]: t for t in
                json.loads((self.folder / "tasks_list.json").read_text())["tasks"]}

    def assert_finished_cleanly(self, ids: list[str]) -> None:
        queue = self.queue()
        self.assertEqual({i: queue[i]["status"] for i in ids}, {i: "done" for i in ids})
        for i in ids:
            self.git("merge-base", "--is-ancestor", queue[i]["commit"], "HEAD")
            self.assertTrue((self.folder / "evidence" / f"{i}.md").is_file())
            self.assertTrue(queue[i]["verification"]["results"], i)
            self.assertIn(f": {i}: ", (self.folder / "PROGRESS.md").read_text())
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.git("branch", "--list", "task/*"), "")
        self.assertEqual(len(self.git("worktree", "list").splitlines()), 1)
        self.ws("validate")
        self.ws("reconcile")
        self.assertIn("queue is finished", (self.folder / "session_handoff.md").read_text())
        snapshot = json.loads(self.ws("snapshot"))
        kinds = [f["kind"] for f in snapshot["health"]]
        self.assertEqual(kinds, [], snapshot["health"])
        self.ws("close")
        self.commit("sample: close")
        entry = json.loads((self.root / "workstreams" / "workstreams.json").read_text())
        self.assertEqual(entry["workstreams"][0]["status"], "done")

    # --- the runs -------------------------------------------------------------------------

    def sample_tasks(self) -> list[dict]:
        accept = ["the file exists", "test passes"]
        return [
            {"id": "S-01", "phase": 1, "priority": 10, "title": "first", "kind": "behaviour",
             "files": ["src/one.txt"], "acceptance": accept, "verify": ["test", "lint"],
             "findings": ["T1"],
             "notes": json.dumps({"propose": "use one file",
                                  "gotcha": "one.txt is load-bearing"})},
            {"id": "S-02", "phase": 1, "priority": 20, "title": "second", "kind": "behaviour",
             "files": ["src/two.txt"], "acceptance": accept, "verify": ["test", "lint"],
             "notes": json.dumps({"propose": "use a second file"})},
            {"id": "S-03", "phase": 1, "priority": 30, "title": "third", "kind": "behaviour",
             "files": ["src/three.txt"], "acceptance": accept, "verify": ["test"]},
            {"id": "S-04", "phase": 2, "priority": 40, "title": "last", "kind": "behaviour",
             "files": ["src/four.txt"], "acceptance": accept, "verify": ["test", "lint"],
             "blockedBy": ["S-01", "S-02", "S-03"]},
        ]

    def assert_decisions_numbered(self) -> None:
        log = (self.folder / "DECISIONS.md").read_text()
        self.assertIn("kept it small", log)
        self.assertIn("## D002 (", log)
        self.assertIn("S-01): use one file", log)
        self.assertIn("## D003 (", log)
        self.assertIn("S-02): use a second file", log)
        evidence = (self.folder / "evidence" / "S-01.md").read_text()
        self.assertIn("### D002: use one file", evidence)
        self.assertIn("See D002.", evidence)
        self.assertNotIn("P1", evidence)

    def test_sequential(self) -> None:
        self.plan(self.sample_tasks())
        self.run_sequentially()
        self.assert_decisions_numbered()
        self.assert_finished_cleanly(["S-01", "S-02", "S-03", "S-04"])

    def test_parallel(self) -> None:
        self.plan(self.sample_tasks())
        self.run_in_parallel()
        self.assert_decisions_numbered()
        queue = self.queue()
        # S-01 landed first, onto the code it was verified on: nothing to learn from a rerun.
        self.assertEqual(queue["S-01"]["verification"]["postMerge"], "same-tree")
        # S-02 and S-03 met S-01's code for the first time at their merge, so they ran again.
        self.assertEqual(queue["S-02"]["verification"]["postMerge"], "ran")
        self.assertEqual(queue["S-03"]["verification"]["postMerge"], "ran")
        self.assert_finished_cleanly(["S-01", "S-02", "S-03", "S-04"])

    def test_the_next_tasks_brief_carries_what_the_last_one_learned(self) -> None:
        self.plan(self.sample_tasks())
        self.ws("claim", "--commit", "S-01", "S-02", "S-03")
        self.ws("worktree", "create", "S-01", "S-02", "S-03")
        self.wait([self.agent(i) for i in ("S-01", "S-02", "S-03")])
        self.ws("settle", "S-01", "S-02", "S-03")
        brief = self.ws("brief", "S-04")
        self.assertIn("one.txt is load-bearing", brief)
        self.assertIn("use one file", brief)

    def test_the_brief_cites_the_plan_and_stays_small(self) -> None:
        self.plan(self.sample_tasks())
        brief = self.ws("brief", "S-01")
        self.assertIn("### T1: the obvious fix is wrong", brief)
        self.assertIn("Use the other one.", brief)
        self.assertLess(len(brief) / 4, 2500, "over the worker budget")

    def test_verify_and_evidence_follow_a_task_to_its_worktree(self) -> None:
        """A real worker's shell left its worktree: its evidence landed in the main checkout and
        its checks ran against code without its change."""
        self.plan(self.sample_tasks()[:1])
        self.ws("claim", "--commit", "S-01")
        self.ws("worktree", "create", "S-01")
        self.ws("evidence", "new", "S-01")
        wrote = self.root / self.folder.relative_to(self.root) / "evidence" / "S-01.md"
        self.assertFalse(wrote.exists(), "evidence went to the main checkout")
        place = self.root / ".workstream" / "worktrees" / "s-01"
        self.assertTrue((place / wrote.relative_to(self.root)).exists())
        run = json.JSONDecoder().raw_decode(self.ws("verify", "S-01", "--json", code=None))[0]
        self.assertEqual(run["branch"], "task/s-01")
        self.assertIn(str(place), self.ws("brief", "S-01"))
        (place / "src").mkdir(exist_ok=True)
        (place / "src" / "made.txt").write_text("ok\n")
        committed = self.ws("commit", "S-01", "-m", "the work")
        self.assertIn("src/made.txt", committed)
        self.assertEqual(subprocess.run(["git", "log", "-1", "--format=%s", "task/s-01"], cwd=self.root,
                                        capture_output=True, text=True).stdout.strip(), "the work")
        self.assertIn("nothing to commit", self.ws("commit", "S-01", code=1))

    def test_commit_refuses_a_workers_tracking_edit_and_keeps_it_unstaged(self) -> None:
        self.plan(self.sample_tasks()[:1])
        self.ws("claim", "--commit", "S-01")
        self.ws("worktree", "create", "S-01")
        place = self.root / ".workstream" / "worktrees" / "s-01"
        progress = place / self.folder.relative_to(self.root) / "PROGRESS.md"
        progress.write_text(progress.read_text() + "marked done\n")
        self.assertIn("PROGRESS.md", self.ws("commit", "S-01", code=1))
        staged = subprocess.run(["git", "diff", "--cached", "--name-only"], cwd=place,
                                capture_output=True, text=True).stdout
        self.assertEqual(staged, "")

    def test_commit_leaves_out_what_worktree_setup_made(self) -> None:
        config = self.root / ".workstream" / "config.toml"
        config.write_text(config.read_text() + '\n[worktree]\nsetup = ["ln -s {main}/src linked"]\n')
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "setup")
        self.plan(self.sample_tasks()[:1])
        self.ws("claim", "--commit", "S-01")
        self.ws("worktree", "create", "S-01")
        place = self.root / ".workstream" / "worktrees" / "s-01"
        self.assertTrue((place / "linked").is_symlink())
        (place / "made.txt").write_text("ok\n")
        committed = self.ws("commit", "S-01")
        self.assertIn("made.txt", committed)
        self.assertNotIn("linked", committed)

    def test_a_task_can_not_be_marked_done_before_it_has_landed(self) -> None:
        """A real worker, told to mark its own task done, found `ws update` and did."""
        self.plan(self.sample_tasks()[:1])
        self.ws("claim", "--commit", "S-01")
        self.ws("worktree", "create", "S-01")
        place = self.root / ".workstream" / "worktrees" / "s-01"
        (place / "made.txt").write_text("ok\n")
        self.ws("commit", "S-01")
        unlanded = self.git("rev-parse", "task/s-01").strip()
        self.assertIn("`ws settle S-01`", self.ws("update", "S-01", "--status", "done",
                                                  "--commit", unlanded, code=1))
        self.assertEqual(self.queue()["S-01"]["status"], "in-progress")

    def test_evidence_starts_on_the_task_branch_and_not_on_integration(self) -> None:
        self.plan(self.sample_tasks()[:1])
        self.assertIn("goes on S-01's branch", self.ws("evidence", "new", "S-01", code=1))

    def test_a_blocked_worker_leaves_its_branch_for_later(self) -> None:
        tasks = self.sample_tasks()[:1]
        tasks[0]["notes"] = json.dumps({"block": "the API key is missing"})
        self.plan(tasks)
        self.ws("claim", "--commit", "S-01")
        self.ws("worktree", "create", "S-01")
        self.wait([self.agent("S-01")])
        self.assertIn("blocked: the API key is missing", self.ws("settle", "S-01"))
        task = self.queue()["S-01"]
        self.assertEqual(task["status"], "blocked")
        self.assertIn("the API key is missing", task["notes"])
        self.assertIn("task/s-01", self.git("branch", "--list", "task/*"))
        self.assertEqual(len(self.git("worktree", "list").splitlines()), 2)
        self.assertIn("the API key is missing", (self.folder / "session_handoff.md").read_text())

    def test_changes_that_pass_alone_and_fail_together_do_not_land(self) -> None:
        """The reason merged trees run again: each branch is green, the combination isn't."""
        tasks = self.sample_tasks()[:2]
        (self.root / "check.py").write_text("""import pathlib, sys
if pathlib.Path("src/one.txt").exists() and pathlib.Path("src/two.txt").exists():
    print("one and two may not coexist")
    sys.exit(1)
""")
        self.commit("a rule that only the combination breaks")
        self.plan(tasks)
        self.ws("claim", "--commit", "S-01", "S-02")
        self.ws("worktree", "create", "S-01", "S-02")
        self.wait([self.agent("S-01"), self.agent("S-02")])
        before = self.git("rev-parse", "HEAD")
        out = self.ws("settle", "S-01", "S-02", code=1)
        self.assertIn("S-01: done", out)
        self.assertIn("S-02: NOT settled: after merging: test", out)
        queue = self.queue()
        self.assertEqual(queue["S-01"]["status"], "done")
        self.assertEqual(queue["S-02"]["status"], "in-progress")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertFalse((self.root / "src" / "two.txt").exists())
        self.assertNotEqual(self.git("rev-parse", "HEAD"), before)


if __name__ == "__main__":
    unittest.main()
