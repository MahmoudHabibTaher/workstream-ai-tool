"""End to end, git steps included: the single-writer protocol that lets parallel workers merge.

1. The orchestrator creates a workstream, seeds two tasks and claims both on the integration
   branch.
2. Two workers each branch from the post-claim commit and commit code plus their own
   `evidence/<TASK-ID>.md`, touching no other tracking file.
3. The orchestrator merges both `--no-ff`, marks both done, validates, syncs and closes.

The point is step 3: two parallel branches merge with no conflict because neither writes the
queue, PROGRESS.md or DECISIONS.md. A control test shows that when each branch appends its own
PROGRESS entry, they conflict on exactly that file.
"""

from __future__ import annotations

import unittest

from tests.helpers import WsTestCase, task

WS_ID = "flow"


class ProtocolFlowTests(WsTestCase):
    integration = "trunk"

    def setUp(self) -> None:
        super().setUp()
        (self.root / "src").mkdir()
        (self.root / "src" / "base.txt").write_text("base\n")
        self.folder = self.ws_dir / WS_ID

    def plan_and_claim(self) -> str:
        """The orchestrator's side up to dispatch; returns the post-claim base hash."""
        self.new_ws(WS_ID, "FL")
        self.seed_ok([task(f"FL-0{n}", n * 10, files=[f"src/task{n}.txt"]) for n in (1, 2)], WS_ID)
        pre = self.commit_all(f"{WS_ID}: create workstream")
        self.ok("claim", "-w", WS_ID, "--base", pre, "--by", "flow-test", "FL-01", "FL-02")
        self.ok("sync")
        return self.commit_all(f"{WS_ID}: claim FL-01, FL-02")

    def worker(self, base: str, n: int, *, own_progress: bool = False) -> str:
        """One worker's branch: code plus its evidence file (or, own_progress, a PROGRESS
        entry of its own instead). Returns the branch name."""
        branch = self.by_id(f"FL-0{n}", WS_ID)["branch"]
        self.git("switch", "-q", "-c", branch, base)
        (self.root / "src" / f"task{n}.txt").write_text(f"task {n}\n")
        if own_progress:
            progress = self.folder / "PROGRESS.md"
            progress.write_text(progress.read_text() + f"\n## FL-0{n}\n\nWorker {n} was here.\n")
        else:
            evidence = self.folder / "evidence" / f"FL-0{n}.md"
            evidence.parent.mkdir(exist_ok=True)
            evidence.write_text(f"# FL-0{n} evidence\n- **Status:** done\n")
        self.commit_all(f"FL-0{n}")
        self.git("switch", "-q", "trunk")
        return branch

    def test_two_parallel_workers_merge_without_conflict(self) -> None:
        base = self.plan_and_claim()
        claimed = self.queue(WS_ID)["tasks"]
        self.assertEqual({t["status"] for t in claimed}, {"in-progress"})
        self.assertTrue(all(t["startedAt"] and t["claimedBy"] == "flow-test" for t in claimed))

        branches = [self.worker(base, n) for n in (1, 2)]
        for n, branch in zip((1, 2), branches):
            touched = self.git("diff", "--name-only", base, branch).split()
            self.assertEqual(sorted(touched),
                             sorted([f"src/task{n}.txt", f"workstreams/{WS_ID}/evidence/FL-0{n}.md"]),
                             "a worker wrote outside its code and evidence file")

        merges = []
        for branch in branches:
            self.git("merge", "--no-ff", "-m", f"Merge {branch}", branch)
            merges.append(self.git("rev-parse", "--short", "HEAD").strip())
        self.assertEqual(self.git("status", "--porcelain"), "")

        for n, merge in zip((1, 2), merges):
            self.ok("update", "-w", WS_ID, f"FL-0{n}", "--status", "done", "--commit", merge)
        self.ok("sync")
        self.ok("validate")
        self.assertEqual(self.entry(WS_ID)["progress"]["done"], 2)
        self.ok("close", "-w", WS_ID)
        self.commit_all(f"{WS_ID}: close")
        self.assertEqual(self.entry(WS_ID)["status"], "done")

    def test_control_each_branch_writing_progress_conflicts_there(self) -> None:
        # Without this, a merge helper that silently resolved conflicts would pass the test
        # above for the wrong reason.
        base = self.plan_and_claim()
        first, second = (self.worker(base, n, own_progress=True) for n in (1, 2))
        self.git("merge", "--no-ff", "-m", "first", first)
        merged = self.git("merge", "--no-ff", "-m", "second", second, check=False)
        self.assertNotEqual(self.git("status", "--porcelain"), "", merged)
        conflicted = self.git("diff", "--name-only", "--diff-filter=U").split()
        self.assertEqual(conflicted, [f"workstreams/{WS_ID}/PROGRESS.md"])
        self.git("merge", "--abort")


if __name__ == "__main__":
    unittest.main()
