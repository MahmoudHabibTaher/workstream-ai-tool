"""The guarded writer: each action commits exactly the paths it changed; every refusal leaves
every file byte-identical and HEAD where it was; a no-op sync makes no commit; a failing commit
restores the original bytes. Runs on a branch that isn't called main, to prove nothing assumes
one."""

from __future__ import annotations

import json
import os
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import WsTestCase, task
from workstream import act, fsutil, snapshot, tasks
from workstream.config import Config
from workstream.errors import Refused
from workstream.project import Project

WS_ID = "flow"
REGISTRY_REL = "workstreams/workstreams.json"
TASKS_REL = f"workstreams/{WS_ID}/tasks_list.json"


class ActTestCase(WsTestCase):
    integration = "trunk"

    def setUp(self) -> None:
        super().setUp()
        self.new_ws(WS_ID, "FL")
        self.new_ws("other", "OT")
        self.write_queue([
            task("FL-01", 10, status="in-progress", branch="task/flow-1",
                 startedAt="2026-10-01T00:00:00Z", baseCommit="0000000", claimedBy="worker"),
            task("FL-02", 20, status="todo", branch="task/flow-2"),
        ], WS_ID)
        (self.root / "src").mkdir()
        (self.root / "src" / "base.txt").write_text("base\n")
        self.commit_all("seed")
        # The fixture's stored progress is stale on purpose; sync it once so tests start
        # from a registry a no-op sync leaves alone.
        self.act_ok("sync", "--expect-registry", self.rev("registry"))

    # --- helpers --------------------------------------------------------------------------

    def head(self) -> str:
        return self.git("rev-parse", "HEAD").strip()

    def rev(self, which: str) -> str:
        """What a UI would pass: the snapshot's own revisions."""
        revisions = snapshot.build_snapshot(self.project())["revisions"]
        return revisions["registry"] if which == "registry" else revisions["tasks"][WS_ID]

    def tree_bytes(self) -> dict[str, bytes]:
        return {str(p.relative_to(self.root)): p.read_bytes()
                for p in sorted(self.root.rglob("*")) if p.is_file() and ".git" not in p.parts}

    def act(self, action: str, *extra: str) -> tuple[int, str, str]:
        return self.ws("act", action, "-w", WS_ID, *extra)

    def act_ok(self, action: str, *extra: str) -> str:
        code, out, err = self.act(action, *extra)
        self.assertEqual(code, 0, err)
        return out

    def expect_both(self) -> list[str]:
        return ["--expect-registry", self.rev("registry"), "--expect-tasks", self.rev("tasks")]

    def assert_committed(self, message: str, paths: list[str]) -> None:
        self.assertEqual(self.git("log", "-1", "--format=%s").strip(), message)
        shown = self.git("show", "--name-only", "--format=", "HEAD").split()
        self.assertEqual(sorted(shown), sorted(paths))


class ActionTests(ActTestCase):
    def test_pause_then_resume_each_commit_only_the_registry(self) -> None:
        self.assertIn("committed", self.act_ok("pause", "--notes", "parked", *self.expect_both()))
        self.assert_committed("flow: pause (ws act)", [REGISTRY_REL])
        self.assertEqual((self.entry(WS_ID)["status"], self.entry(WS_ID)["notes"]),
                         ("paused", "parked"))
        self.act_ok("resume", "--expect-registry", self.rev("registry"))
        self.assert_committed("flow: resume (ws act)", [REGISTRY_REL])
        self.assertEqual(self.entry(WS_ID)["status"], "active")
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_unclaim_commits_the_queue_and_the_registry(self) -> None:
        self.act_ok("unclaim", "--task", "FL-01", *self.expect_both())
        self.assert_committed("flow: unclaim FL-01 (ws act)", [REGISTRY_REL, TASKS_REL])
        t = self.by_id("FL-01", WS_ID)
        self.assertEqual({k: t[k] for k in ("status", "startedAt", "claimedBy")},
                         {"status": "todo", "startedAt": None, "claimedBy": None})
        self.assertEqual(self.entry(WS_ID)["progress"]["in-progress"], 0)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_sync_commits_a_changed_progress(self) -> None:
        self.write_queue([task("OT-01", 10, status="todo")], "other")
        self.git("commit", "-q", "-am", "other: seed")
        self.act_ok("sync", "--expect-registry", self.rev("registry"))
        self.assert_committed("flow: sync (ws act)", [REGISTRY_REL])
        self.assertEqual(self.entry("other")["progress"]["total"], 1)

    def test_a_no_op_sync_makes_no_commit_and_keeps_the_bytes(self) -> None:
        # setUp's sync already ran; the registry's `updated` date would still move.
        data = json.loads(self.registry.read_text())
        data["updated"] = "2000-01-01"
        fsutil.write_json(self.registry, data)
        self.git("commit", "-q", "-am", "backdate")
        before, head = self.tree_bytes(), self.head()
        self.assertEqual(self.act_ok("sync", "--expect-registry", self.rev("registry")),
                         "no change\n")
        self.assertEqual((self.tree_bytes(), self.head()), (before, head))
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_never_commits_or_unstages_anything_but_its_own_paths(self) -> None:
        (self.root / "src" / "base.txt").write_text("staged edit\n")
        self.git("add", "src/base.txt")
        (self.root / "src" / "loose.txt").write_text("untracked\n")
        (self.ws_dir / "README.md").write_text("not a tracking path\n")
        self.act_ok("pause", "--expect-registry", self.rev("registry"))
        self.assert_committed("flow: pause (ws act)", [REGISTRY_REL])
        status = self.git("status", "--porcelain").splitlines()
        self.assertEqual(sorted(status), ["?? src/loose.txt", "?? workstreams/README.md",
                                          "M  src/base.txt"])

    def test_a_dirty_path_in_another_workstream_blocks_only_sync(self) -> None:
        (self.ws_dir / "other" / "PROGRESS.md").write_text("# mid-step\n")
        self.act_ok("pause", "--expect-registry", self.rev("registry"))
        before, head = self.tree_bytes(), self.head()
        code, _, err = self.act("sync", "--expect-registry", self.rev("registry"))
        self.assertEqual((code, self.tree_bytes(), self.head()), (1, before, head))
        self.assertIn("dirty tracking path", err)


class RefusalTests(ActTestCase):
    def assert_refused(self, action: str, *extra: str, why: str) -> None:
        before, head = self.tree_bytes(), self.head()
        status = self.git("status", "--porcelain")
        code, out, err = self.act(action, *extra)
        self.assertEqual(code, 1, out)
        self.assertTrue(err.startswith("refused: "), err)
        self.assertIn(why, err)
        self.assertEqual(len(err.strip().splitlines()), 1, err)
        self.assertEqual(self.tree_bytes(), before, "a refusal changed a file")
        self.assertEqual(self.head(), head, "a refusal made a commit")
        self.assertEqual(self.git("status", "--porcelain"), status)

    def test_refuses_off_the_integration_branch(self) -> None:
        expect = self.expect_both()
        self.git("switch", "-q", "-c", "elsewhere")
        for action, extra in (("pause", []), ("sync", []), ("unclaim", ["--task", "FL-01"])):
            self.assert_refused(action, *extra, *expect, why="not trunk")

    def test_refuses_on_a_dirty_tracking_path(self) -> None:
        for rel in (f"workstreams/{WS_ID}/PROGRESS.md", REGISTRY_REL,
                    f"workstreams/{WS_ID}/evidence/FL-01.md"):
            with self.subTest(rel=rel):
                path = self.root / rel
                path.parent.mkdir(exist_ok=True)
                original = path.read_bytes() if path.exists() else None
                expect = self.expect_both()
                path.write_text(path.read_text() + " " if original is not None else "new\n")
                self.assert_refused("pause", *expect, why="dirty tracking path")
                self.assert_refused("unclaim", "--task", "FL-01", *expect,
                                    why="dirty tracking path")
                if original is None:
                    path.unlink()
                    path.parent.rmdir() if not any(path.parent.iterdir()) else None
                else:
                    path.write_bytes(original)

    def test_refuses_on_a_stale_expect_hash(self) -> None:
        reg, queue_rev = self.rev("registry"), self.rev("tasks")
        stale = "0" * 64
        self.assert_refused("pause", "--expect-registry", stale, why="the registry changed")
        self.assert_refused("unclaim", "--task", "FL-01", "--expect-registry", reg,
                            "--expect-tasks", stale, why="the queue changed")
        # A change committed behind the UI's back makes its drawn hashes stale too.
        self.act_ok("pause", "--expect-registry", reg)
        self.assert_refused("resume", "--expect-registry", reg, why="the registry changed")
        path = self.ws_dir / WS_ID / "tasks_list.json"
        data = tasks.load(path, Config())
        data["tasks"][1]["title"] = "two, retitled"
        tasks.save(path, data)
        self.git("commit", "-q", "-am", "touch queue")
        self.assert_refused("unclaim", "--task", "FL-01", "--expect-registry",
                            self.rev("registry"), "--expect-tasks", queue_rev,
                            why="the queue changed")

    def test_refuses_a_disallowed_transition(self) -> None:
        self.assert_refused("resume", *self.expect_both(), why="resume needs status paused")
        self.act_ok("pause", "--expect-registry", self.rev("registry"))
        self.assert_refused("pause", *self.expect_both(), why="pause needs status planned")
        self.assert_refused("unclaim", "--task", "FL-02", *self.expect_both(),
                            why="unclaim needs an in-progress task")
        self.assert_refused("unclaim", "--task", "FL-09", *self.expect_both(),
                            why="no task FL-09")

    def test_refuses_unclaim_while_a_worktree_has_the_branch(self) -> None:
        worktree = self.root.parent / "wt-one"
        self.git("worktree", "add", "-q", "-b", "task/flow-1", str(worktree))
        self.assert_refused("unclaim", "--task", "FL-01", *self.expect_both(),
                            why="a worktree has task/flow-1 checked out")
        self.git("worktree", "remove", str(worktree))
        self.act_ok("unclaim", "--task", "FL-01", *self.expect_both())

    def test_refuses_misused_arguments(self) -> None:
        expect = self.expect_both()
        self.assert_refused("unclaim", *expect[:2], "--task", "FL-01",
                            why="unclaim needs --expect-tasks")
        self.assert_refused("unclaim", *expect, why="unclaim needs --task")
        self.assert_refused("pause", "--task", "FL-01", *expect, why="only to unclaim")
        self.assert_refused("sync", "--notes", "x", *expect, why="only to pause and resume")
        code, _, err = self.ws("act", "sync", "-w", "nope", "--expect-registry", expect[1])
        self.assertEqual(code, 1)
        self.assertIn("no workstream with id 'nope'", err)
        code, _, err = self.ws("act", "sync", "--expect-registry", expect[1])
        self.assertEqual(code, 1)
        self.assertIn("act needs -w", err)

    def test_refuses_a_broken_queue_without_writing(self) -> None:
        registry_rev = self.rev("registry")
        (self.ws_dir / WS_ID / "tasks_list.json").write_text("{broken")
        self.git("commit", "-q", "-am", "break it")
        self.assert_refused("pause", "--expect-registry", registry_rev, why="not valid JSON")

    def test_refuses_a_broken_registry_without_writing(self) -> None:
        self.registry.write_text("{broken")
        self.git("commit", "-q", "-am", "break it")
        self.assert_refused("pause", "--expect-registry", "x", why="not valid JSON")

    def test_done_and_abandoned_are_not_actions(self) -> None:
        for action in ("done", "abandoned"):
            code, _, err = self.ws("act", action, "-w", WS_ID, "--expect-registry", "x")
            self.assertEqual(code, 2)
            self.assertIn("invalid choice", err)


class ScriptTests(ActTestCase):
    def test_runs_as_a_separate_process(self) -> None:
        # As a UI runs it.
        src = Path(act.__file__).resolve().parent.parent
        env = {**os.environ, "PYTHONPATH": str(src)}
        argv = ["python3", "-B", "-m", "workstream", "act", "pause", "-w", WS_ID,
                "--expect-registry"]
        stale = subprocess.run([*argv, "0" * 64], cwd=self.root, env=env, capture_output=True,
                               text=True)
        self.assertEqual(stale.returncode, 1)
        self.assertTrue(stale.stderr.startswith("refused: stale view"), stale.stderr)
        done = subprocess.run([*argv, self.rev("registry")], cwd=self.root, env=env,
                              capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertIn("committed", done.stdout)
        self.assert_committed("flow: pause (ws act)", [REGISTRY_REL])


class FailedCommitTests(ActTestCase):
    def test_a_failing_commit_restores_the_original_bytes(self) -> None:
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(exist_ok=True)
        hook.write_text("#!/bin/sh\necho 'hook says no' >&2\nexit 1\n")
        hook.chmod(0o755)
        before, head = self.tree_bytes(), self.head()
        code, _, err = self.act("unclaim", "--task", "FL-01", *self.expect_both())
        self.assertEqual(code, 1)
        self.assertIn("refused: commit failed, tracking files restored: hook says no", err)
        self.assertEqual((self.tree_bytes(), self.head()), (before, head))
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_an_error_mid_write_restores_the_original_bytes(self) -> None:
        before = self.tree_bytes()
        with mock.patch.object(act, "commit", side_effect=RuntimeError("boom")), \
                self.assertRaises(RuntimeError):
            act.act(self.project(), "unclaim", WS_ID, task="FL-01",
                    expect_registry=self.rev("registry"), expect_tasks=self.rev("tasks"))
        self.assertEqual(self.tree_bytes(), before)


class DecideCommitTests(ActTestCase):
    LOG_REL = f"workstreams/{WS_ID}/DECISIONS.md"

    def decide(self, *extra: str) -> tuple[int, str, str]:
        return self.ws("decide", "keep it", "--why", "Because. Rejected: no.", "-w", WS_ID, *extra)

    def fails_cleanly(self, needle: str, *extra: str) -> None:
        before, head = self.tree_bytes(), self.head()
        code, _, err = self.decide("--commit", *extra)
        self.assertEqual(code, 1)
        self.assertIn(needle, err)
        self.assertEqual((self.tree_bytes(), self.head()), (before, head))

    def test_one_commit_holding_only_the_log_and_prints_the_hash(self) -> None:
        (self.root / "src" / "base.txt").write_text("someone's edit\n")
        (self.root / "src" / "staged.txt").write_text("staged\n")
        self.git("add", "src/staged.txt")
        head = self.head()
        out = self.ok("decide", "keep it", "--why", "Because. Rejected: no.", "-w", WS_ID,
                      "--commit")
        self.assert_committed(f"{WS_ID}: D001", [self.LOG_REL])
        self.assertEqual(self.git("rev-parse", "HEAD~1").strip(), head)
        short = self.git("rev-parse", "--short", "HEAD").strip()
        self.assertEqual(out.strip(), f"D001; committed {short}")
        self.assertIn("keep it", self.git("show", f"HEAD:{self.LOG_REL}"))
        self.assertEqual(sorted(self.git("status", "--porcelain").splitlines()),
                         [" M src/base.txt", "A  src/staged.txt"])

    def test_it_works_where_there_is_no_log_yet(self) -> None:
        self.ok("new", "small", "--title", "S", "--summary", "s", "--tier", "lite")
        self.commit_all("lite")
        log = self.ws_dir / "small" / "DECISIONS.md"
        self.assertFalse(log.exists())
        out = self.ok("decide", "x", "--why", "y", "--by", "user", "-w", "small", "--commit")
        self.assertIn("D001; committed ", out)
        self.assert_committed("small: D001", ["workstreams/small/DECISIONS.md"])
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_it_refuses_on_another_branch(self) -> None:
        self.git("checkout", "-q", "-b", "task/flow-1")
        self.fails_cleanly("the checkout is on task/flow-1, not trunk")

    def test_it_refuses_with_dirty_tracking_files(self) -> None:
        for path in (self.ws_dir / WS_ID / "PROGRESS.md", self.root / REGISTRY_REL):
            original = path.read_bytes()
            path.write_bytes(original + b"\n")
            with self.subTest(path=path.name):
                self.fails_cleanly("dirty tracking path")
            path.write_bytes(original)

    def test_a_failing_commit_restores_an_existing_log(self) -> None:
        self.fail_commits()
        self.fails_cleanly("commit failed, tracking files restored: hook says no")
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_a_failing_commit_removes_a_new_log_and_unstages_it(self) -> None:
        log = self.ws_dir / WS_ID / "DECISIONS.md"
        log.unlink()
        self.commit_all("no log")
        self.fail_commits()
        self.fails_cleanly("commit failed, tracking files restored: hook says no")
        self.assertFalse(log.exists())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_without_the_flag_it_writes_and_leaves_the_commit_to_you(self) -> None:
        head = self.head()
        code, out, err = self.decide()
        self.assertEqual((code, err), (0, ""))
        self.assertEqual(out.strip(), "D001; commit it")
        self.assertEqual(self.head(), head)
        self.assertEqual(self.git("status", "--porcelain").strip(), f"M {self.LOG_REL}")

    def test_without_the_flag_it_still_writes_on_another_branch(self) -> None:
        self.git("checkout", "-q", "-b", "task/flow-1")
        self.assertEqual(self.decide()[0], 0)
        self.assertIn("keep it", (self.ws_dir / WS_ID / "DECISIONS.md").read_text())

    def fail_commits(self) -> None:
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(exist_ok=True)
        hook.write_text("#!/bin/sh\necho 'hook says no' >&2\nexit 1\n")
        hook.chmod(0o755)


class PureTests(unittest.TestCase):
    def test_commit_message(self) -> None:
        self.assertEqual(act.commit_message("ws", "unclaim", "WS-01"), "ws: unclaim WS-01 (ws act)")
        self.assertEqual(act.commit_message("ws", "sync", None), "ws: sync (ws act)")

    def test_check_checkout_scopes_dirty_paths_by_action(self) -> None:
        project = Project(root=Path("/repo"), config=Config(integration="trunk"))
        rows = [{"id": "a"}, {"id": "b"}]
        facts = {"branch": "trunk", "worktrees": [],
                 "dirtyTracking": ["workstreams/b/PROGRESS.md", "workstreams/tools/act.py"]}
        act.check_checkout(project, facts, "pause", "a", rows)
        with self.assertRaises(Refused):
            act.check_checkout(project, facts, "sync", "a", rows)
        with self.assertRaises(Refused):
            act.check_checkout(project, {"error": "git: gone"}, "pause", "a", rows)

    def test_actions_are_the_four_guarded_writes(self) -> None:
        self.assertEqual(act.ACTIONS, ("pause", "resume", "unclaim", "sync"))


if __name__ == "__main__":
    unittest.main()
