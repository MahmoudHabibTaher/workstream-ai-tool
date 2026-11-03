"""`ws settle`, `ws worktree` and `ws claim --commit`: the ways landing a task can go wrong."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import WsTestCase, evidence_text, task
from tests.test_schema import load_schema, problems
import workstream
from workstream import act, settle


class SettleTestCase(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.set_commands(test="true")
        self.commit_all("config")

    def arrange(self, *tasks_: dict) -> None:
        self.seed_ok(list(tasks_))
        self.commit_all("seeded")

    def t(self, task_id: str, priority: int = 10, **fields) -> dict:
        return task(task_id, priority, verify=["test"], acceptance=["works"], **fields)

    def claim(self, *ids: str) -> list[Path]:
        self.ok("claim", "--commit", *ids)
        self.ok("worktree", "create", *ids)
        return [self.root / ".workstream" / "worktrees" / i.lower() for i in ids]

    def finish(self, where: Path, task_id: str, *, files: dict | None = None,
               evidence: str | None = None, run_verify: bool = True) -> None:
        """What a worker does: code, verify, evidence, commit."""
        for name, content in (files or {f"{task_id}.txt": "x\n"}).items():
            path = where / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(content)
        if run_verify:
            code, out, err = self.ws_at(where, "verify", task_id, "-w", "alpha")
            self.assertEqual(code, 0, out + err)
        folder = where / "workstreams" / "alpha" / "evidence"
        folder.mkdir(exist_ok=True)
        (folder / f"{task_id}.md").write_text(evidence or evidence_text(task_id))
        self.git_at(where, "add", "-A")
        self.git_at(where, "commit", "-q", "-m", f"{task_id} work")

    def work(self, task_id: str = "T1", **kwargs) -> Path:
        where = self.claim(task_id)[0]
        self.finish(where, task_id, **kwargs)
        return where


class UnclaimTests(SettleTestCase):
    def test_the_registry_follows_it(self) -> None:
        self.arrange(self.t("T1"))
        self.ok("claim", "--commit", "T1")
        self.ok("unclaim", "T1", "-w", "alpha")
        self.assertIn("no differences", self.ok("reconcile"))


class BriefForRealWorkTests(SettleTestCase):
    """What the first real pilot run got wrong, in a worker's own words."""

    def test_a_worker_is_told_to_wait_for_verify_and_not_to_read_docs_whole(self) -> None:
        (self.root / "guide.md").write_text("long\n")
        self.arrange(self.t("T1", docs=["guide.md"]))
        out = self.ok("brief", "T1", "-w", "alpha")
        self.assertIn("foreground", out)
        self.assertIn("Ending your turn ends you", out)
        self.assertIn("search them", out)
        self.assertNotIn("Read first", out)


class RootTests(SettleTestCase):
    def test_from_the_checkout_itself(self) -> None:
        self.assertEqual(self.ok("root").strip(), str(self.root))

    def test_from_a_tasks_worktree_it_is_the_integration_checkout(self) -> None:
        self.arrange(self.t("T1"))
        where = self.claim("T1")[0]
        code, out, err = self.ws_at(where, "root")
        self.assertEqual((code, out.strip()), (0, str(self.root)), err)

    def test_a_linked_checkout_holding_the_integration_branch_wins(self) -> None:
        linked = self.root.parent / "linked"
        self.git("worktree", "add", "-q", "-b", "pilot", str(linked), "main")
        config = linked / ".workstream" / "config.toml"
        config.write_text(config.read_text().replace('integration = "main"', 'integration = "pilot"'))
        code, out, err = self.ws_at(linked, "root")
        self.assertEqual((code, out.strip()), (0, str(linked)), err)

    def test_with_the_branch_checked_out_nowhere_it_is_this_checkout(self) -> None:
        self.git("switch", "-q", "-c", "elsewhere")
        self.assertEqual(self.ok("root").strip(), str(self.root))


class RootOutsideAProjectTests(unittest.TestCase):
    def test_it_fails_with_one_line(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            done = subprocess.run([sys.executable, "-B", "-m", "workstream", "--root", tmp, "root"],
                                  capture_output=True, text=True,
                                  env={**os.environ, "PYTHONPATH": str(Path(workstream.__file__).parents[1])})
        self.assertNotEqual(done.returncode, 0)
        self.assertEqual(len(done.stderr.strip().splitlines()), 1, done.stderr)
        self.assertEqual(done.stdout, "")


class LandedEvidenceTests(SettleTestCase):
    def test_a_landed_task_says_so(self) -> None:
        self.arrange(self.t("T1"))
        self.work("T1")
        self.ok("settle", "T1", "-w", "alpha")
        out = self.ok("evidence", "check", "T1", "-w", "alpha")
        self.assertIn(f"T1 has landed as {self.by_id('T1')['commit']}", out)
        self.assertNotIn("never run", out)


class ProtectedPathTests(SettleTestCase):
    def setUp(self) -> None:
        super().setUp()
        rules = self.root / ".claude" / "rules"
        rules.mkdir(parents=True)
        (rules / "x.md").write_text("rule\n")

    def adapted(self) -> None:
        self.ok("adapt", "claude-code")
        self.commit_all("adapted")

    def test_a_background_worker_is_told_not_to_try(self) -> None:
        self.adapted()
        self.arrange(self.t("T1", docs=[".claude/rules/x.md"]))
        out = self.ok("brief", "T1", "-w", "alpha")
        self.assertIn("You can't edit these from the background:** `.claude/rules/x.md`", out)
        self.assertIn("under Gotchas", out)

    def test_a_foreground_task_can_ask_so_it_isnt_told(self) -> None:
        self.adapted()
        self.arrange(self.t("T1", docs=[".claude/rules/x.md"], mode="foreground"))
        self.assertNotIn("from the background", self.ok("brief", "T1", "-w", "alpha"))

    def test_a_project_without_that_agent_isnt_told(self) -> None:
        self.arrange(self.t("T1", docs=[".claude/rules/x.md"]))
        self.assertNotIn("from the background", self.ok("brief", "T1", "-w", "alpha"))


class LinkedCheckoutTests(SettleTestCase):
    """A project can run from a linked checkout on its own branch, leaving the main one alone."""

    def setUp(self) -> None:
        super().setUp()
        self.t1 = self.t("T1")
        self.arrange(self.t1)
        self.main_root, self.root = self.root, self.root.parent / "linked"
        self.ws_dir, self.registry = self.root / "workstreams", self.root / "workstreams" / "workstreams.json"
        self.git_at(self.main_root, "worktree", "add", "-q", "-b", "pilot", str(self.root), "main")
        self.edit_config('integration = "main"', 'integration = "pilot"')
        self.commit_all("on the pilot branch")

    def test_a_task_lands_on_its_branch_and_the_main_checkout_stays_put(self) -> None:
        before = self.git_at(self.main_root, "rev-parse", "HEAD")
        self.work("T1")
        self.ok("settle", "T1", "-w", "alpha")
        self.assertEqual(self.git_at(self.main_root, "rev-parse", "HEAD"), before)
        self.assertEqual(self.git_at(self.main_root, "branch", "--show-current").strip(), "main")
        self.assertEqual(self.by_id("T1")["status"], "done")
        self.assertTrue((self.root / "T1.txt").exists())
        self.assertFalse((self.main_root / "T1.txt").exists())

    def test_its_own_checkout_is_not_a_leftover(self) -> None:
        code, out, err = self.ws("doctor")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn(str(self.root), out)


class ClaimCommitTests(SettleTestCase):
    def test_claims_and_commits_both_files(self) -> None:
        self.arrange(self.t("T1"))
        pre = self.git("rev-parse", "HEAD").strip()
        self.ok("claim", "--commit", "T1", "--by", "me")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.by_id("T1")["baseCommit"], pre)
        self.assertEqual(self.entry()["status"], "active")
        self.assertIn("alpha: claim T1", self.git("log", "-1", "--format=%s"))

    def test_refused_off_the_integration_branch(self) -> None:
        self.arrange(self.t("T1"))
        self.git("switch", "-q", "-c", "elsewhere")
        self.assertIn("not main", self.fails("claim", "--commit", "T1"))
        self.assertEqual(self.by_id("T1")["status"], "todo")

    def test_refused_with_uncommitted_tracking_files(self) -> None:
        self.arrange(self.t("T1"))
        (self.ws_dir / "alpha" / "PLAN.md").write_text("edited")
        self.assertIn("dirty tracking", self.fails("claim", "--commit", "T1"))

    def test_a_refused_claim_commits_nothing(self) -> None:
        self.arrange(self.t("T1"), self.t("T2", 20, blockedBy=["T1"]))
        head = self.git("rev-parse", "HEAD")
        self.assertIn("claimed nothing", self.fails("claim", "--commit", "T2"))
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_a_failed_commit_undoes_the_claim(self) -> None:
        self.arrange(self.t("T1"))
        with mock.patch.object(act, "commit", side_effect=act.Refused("hook said no")):
            self.assertIn("hook said no", self.fails("claim", "--commit", "T1"))
        self.assertEqual(self.by_id("T1")["status"], "todo")
        self.assertEqual(self.git("status", "--porcelain"), "")


class WorktreeTests(SettleTestCase):
    def test_creates_on_the_tasks_branch_and_stays_out_of_status(self) -> None:
        self.arrange(self.t("T1"))
        where = self.claim("T1")[0]
        self.assertEqual(self.git_at(where, "rev-parse", "--abbrev-ref", "HEAD").strip(), "task/t1")
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.ok("validate")

    def test_running_it_twice_finds_the_first(self) -> None:
        self.arrange(self.t("T1"))
        self.claim("T1")
        self.assertIn("already there", self.ok("worktree", "create", "T1"))

    def test_needs_a_claim(self) -> None:
        self.arrange(self.t("T1"))
        self.assertIn("claim --commit", self.fails("worktree", "create", "T1"))

    def test_needs_the_claim_committed(self) -> None:
        self.arrange(self.t("T1"))
        self.ok("claim", "T1")
        self.assertIn("dirty tracking", self.fails("worktree", "create", "T1"))

    def test_needs_the_config_committed(self) -> None:
        self.arrange(self.t("T1"))
        self.ok("claim", "--commit", "T1")
        self.git("rm", "-q", "--cached", ".workstream/config.toml")
        self.git("commit", "-q", "-m", "untrack config")
        self.assertIn("isn't committed", self.fails("worktree", "create", "T1"))

    def test_the_worker_limit_holds(self) -> None:
        self.edit_config("max_workers = 3", "max_workers = 1")
        self.commit_all("one worker")
        self.arrange(self.t("T1"), self.t("T2", 20))
        self.ok("claim", "--commit", "T1", "T2")
        self.ok("worktree", "create", "T1")
        self.assertIn("max_workers", self.fails("worktree", "create", "T2"))

    def test_setup_runs_with_paths_expanded(self) -> None:
        self.edit_config("[parallel]", '[worktree]\nsetup = ["ln -s {main}/shared here"]\n[parallel]')
        self.commit_all("setup")
        self.arrange(self.t("T1"))
        where = self.claim("T1")[0]
        self.assertTrue((where / "here").is_symlink())

    def test_a_failed_setup_leaves_nothing_behind(self) -> None:
        self.edit_config("[parallel]", '[worktree]\nsetup = ["exit 9"]\n[parallel]')
        self.commit_all("setup")
        self.arrange(self.t("T1"))
        self.ok("claim", "--commit", "T1")
        self.assertIn("setup failed", self.fails("worktree", "create", "T1"))
        self.assertEqual(len(self.git("worktree", "list").splitlines()), 1)
        self.assertEqual(self.git("branch", "--list", "task/t1"), "")

    def test_remove_refuses_to_lose_work(self) -> None:
        self.arrange(self.t("T1"))
        where = self.claim("T1")[0]
        (where / "unsaved.txt").write_text("x")
        self.assertIn("uncommitted work", self.fails("worktree", "remove", "T1"))
        self.assertTrue(where.exists())
        self.ok("worktree", "remove", "T1", "--force")
        self.assertFalse(where.exists())

    def test_remove_keeps_an_unmerged_branch(self) -> None:
        self.arrange(self.t("T1"))
        where = self.claim("T1")[0]
        self.finish(where, "T1")
        self.assertIn("isn't merged", self.fails("worktree", "remove", "T1", "--delete-branch"))
        self.assertIn("task/t1", self.git("branch", "--list", "task/t1"))

    def test_list(self) -> None:
        self.assertIn("no linked", self.ok("worktree", "list"))
        self.arrange(self.t("T1"))
        self.claim("T1")
        self.assertIn("task/t1", self.ok("worktree", "list"))

    def test_an_unsafe_task_id_never_reaches_a_path(self) -> None:
        code, out, err = self.seed([task("../../evil", 10)])
        self.assertEqual(code, 1)
        self.assertIn("id must be", out + err)


class GateTests(SettleTestCase):
    def refused(self, *argv: str) -> str:
        code, out, err = self.ws("settle", *argv)
        self.assertEqual(code, 1, out + err)
        self.assertEqual(self.by_id(argv[0])["status"], "in-progress")
        self.assertEqual(self.git("status", "--porcelain"), "")
        return out + err

    def test_a_good_task_lands(self) -> None:
        self.arrange(self.t("T1"))
        where = self.work()
        out = self.ok("settle", "T1")
        self.assertIn("T1: done", out)
        task_ = self.by_id("T1")
        self.assertEqual(task_["status"], "done")
        self.assertTrue(task_["completedAt"])
        self.assertEqual(task_["verification"]["results"][0]["verdict"], "pass")
        self.assertTrue((self.root / "T1.txt").exists())
        self.assertFalse(where.exists())
        self.assertEqual(self.git("branch", "--list", "task/t1"), "")
        self.assertIn("alpha: T1 done", self.git("log", "-1", "--format=%s"))

    def test_merge_and_tracking_are_two_commits_and_the_task_names_the_merge(self) -> None:
        self.arrange(self.t("T1"))
        self.work()
        self.ok("settle", "T1")
        merge = self.git("rev-parse", "HEAD^").strip()
        self.assertEqual(self.by_id("T1")["commit"], merge)
        self.assertEqual(len(self.git("rev-list", "--parents", "-n", "1", merge).split()), 3)
        self.assertIn("Ws-Task: T1", self.git("log", "-1", "--format=%B", merge))

    def test_never_verified(self) -> None:
        self.arrange(self.t("T1"))
        self.work(run_verify=False)
        self.assertIn("never run", self.refused("T1"))

    def test_code_changed_after_verify(self) -> None:
        self.arrange(self.t("T1"))
        where = self.work()
        (where / "later.txt").write_text("x")
        self.git_at(where, "add", "-A")
        self.git_at(where, "commit", "-q", "-m", "more")
        self.assertIn("code changed since", self.refused("T1"))

    def test_committing_evidence_after_verify_is_fine(self) -> None:
        self.arrange(self.t("T1"))
        where = self.work()
        file = where / "workstreams" / "alpha" / "evidence" / "T1.md"
        file.write_text(file.read_text() + "\nmore detail\n")
        self.git_at(where, "add", "-A")
        self.git_at(where, "commit", "-q", "-m", "evidence")
        self.ok("settle", "T1")

    def test_a_failing_verify_stops_it(self) -> None:
        self.edit_config('test = "true"', 'test = "test -f pass"')
        self.commit_all("stricter")
        self.arrange(self.t("T1"))
        where = self.claim("T1")[0]
        self.ws_at(where, "verify", "T1", "-w", "alpha")
        self.finish(where, "T1", run_verify=False)
        self.assertIn("verify commands passed", self.refused("T1"))

    def test_no_evidence(self) -> None:
        self.arrange(self.t("T1"))
        where = self.claim("T1")[0]
        (where / "a.txt").write_text("x")
        self.ws_at(where, "verify", "T1", "-w", "alpha")
        self.git_at(where, "add", "-A")
        self.git_at(where, "commit", "-q", "-m", "work")
        self.assertIn("no evidence/T1.md", self.refused("T1"))

    def test_evidence_with_no_proof(self) -> None:
        self.arrange(self.t("T1"))
        self.work(evidence="# T1\n\n- **Status:** done\n\n## Acceptance\n\n1. works\n")
        self.assertIn("nothing quoted", self.refused("T1"))

    def test_a_worker_that_edits_tracking_files(self) -> None:
        self.arrange(self.t("T1"))
        self.work(files={"workstreams/alpha/PROGRESS.md": "mine\n"})
        self.assertIn("workstreams/alpha/PROGRESS.md", self.refused("T1"))

    def test_a_worker_that_edits_the_registry(self) -> None:
        self.arrange(self.t("T1"))
        self.work(files={"workstreams/workstreams.json": "{}\n"}, run_verify=False)
        self.assertIn("workstreams/workstreams.json", self.refused("T1"))

    def test_a_branch_with_no_commits(self) -> None:
        self.arrange(self.t("T1"))
        self.claim("T1")
        self.assertIn("adds nothing", self.refused("T1"))

    def test_touching_other_files_warns_but_lands(self) -> None:
        self.arrange(self.t("T1", files=["a.txt"]))
        self.work(files={"a.txt": "x", "b.txt": "y"})
        out = self.ok("settle", "T1")
        self.assertIn("warning: the diff stays within", out)
        self.assertIn("b.txt", out)

    def test_a_kind_that_needs_more_verification(self) -> None:
        self.arrange(self.t("T1", kind="behaviour"))
        self.work()
        self.edit_config("[adequacy]\n", '[adequacy]\nbehaviour = ["lint"]\n')
        self.set_commands(lint="true")
        self.commit_all("stricter")
        self.assertIn("needs lint", self.refused("T1"))

    def test_dry_run_changes_nothing(self) -> None:
        self.arrange(self.t("T1"))
        self.work()
        head = self.git("rev-parse", "HEAD")
        self.assertIn("ready to settle", self.ok("settle", "T1", "--dry-run"))
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.by_id("T1")["status"], "in-progress")

    def test_an_option_like_branch_is_refused(self) -> None:
        self.arrange(self.t("T1", branch="--upload-pack=evil"))
        self.ok("claim", "--commit", "T1")
        self.assertIn("looks like an option", self.fails("worktree", "create", "T1"))
        self.assertIn("looks like an option", self.fails("settle", "T1"))


class CheckoutTests(SettleTestCase):
    def test_refused_off_the_integration_branch(self) -> None:
        self.arrange(self.t("T1"))
        self.work()
        self.git("switch", "-q", "-c", "elsewhere")
        self.assertIn("settle runs on main", self.fails("settle", "T1"))

    def test_refused_with_uncommitted_changes(self) -> None:
        self.arrange(self.t("T1"))
        self.work()
        (self.ws_dir / "alpha" / "PLAN.md").write_text("half an edit")
        self.assertIn("uncommitted changes", self.fails("settle", "T1"))

    def test_refused_inside_a_merge(self) -> None:
        self.arrange(self.t("T1"))
        self.work()
        with mock.patch.object(settle.gitutil, "run", wraps=settle.gitutil.run) as run:
            original = run.side_effect
            def fake(root, *argv, env=None):
                if argv[:2] == ("rev-parse", "--verify") and "MERGE_HEAD" in argv:
                    return mock.Mock(returncode=0)
                return settle.subprocess.run(["git", *argv], cwd=root, capture_output=True,
                                             text=True, env=env)
            run.side_effect = fake
            self.assertIn("merge is in progress", self.fails("settle", "T1"))
            run.side_effect = original

    def test_a_task_already_done(self) -> None:
        self.arrange(self.t("T1"))
        self.work()
        self.ok("settle", "T1")
        self.assertIn("its status is done", self.fails("settle", "T1"))


class MergeTests(SettleTestCase):
    def test_a_conflict_aborts_cleanly(self) -> None:
        self.arrange(self.t("T1"), self.t("T2", 20))
        one, two = self.claim("T1", "T2")
        self.finish(one, "T1", files={"same.txt": "one\n"})
        self.finish(two, "T2", files={"same.txt": "two\n"})
        out = self.fails("settle", "T1", "T2")
        self.assertIn("T1: done", out)
        self.assertIn("T2: NOT settled: conflicts in same.txt", out)
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual((self.root / "same.txt").read_text(), "one\n")
        self.assertEqual(self.by_id("T2")["status"], "in-progress")
        self.assertTrue(two.exists())

    def test_a_task_can_land_after_bringing_the_integration_branch_in(self) -> None:
        self.arrange(self.t("T1"), self.t("T2", 20))
        one, two = self.claim("T1", "T2")
        self.finish(one, "T1", files={"same.txt": "one\n"})
        self.finish(two, "T2", files={"same.txt": "two\n"})
        self.fails("settle", "T1", "T2")
        self.git_at(two, "merge", "-q", "-X", "theirs", "main")
        self.assertIn("code changed since", self.fails("settle", "T2"))
        code, out, err = self.ws_at(two, "verify", "T2", "-w", "alpha")
        self.assertEqual(code, 0, out + err)
        self.ok("settle", "T2")

    def test_the_batch_settles_in_priority_order(self) -> None:
        self.arrange(self.t("T1"), self.t("T2", 20))
        one, two = self.claim("T1", "T2")
        self.finish(one, "T1")
        self.finish(two, "T2")
        out = self.ok("settle", "T2", "T1")
        self.assertLess(out.index("T1: done"), out.index("T2: done"))

    def test_the_first_failure_stops_the_batch(self) -> None:
        self.arrange(self.t("T1"), self.t("T2", 20), self.t("T3", 30))
        one, two, three = self.claim("T1", "T2", "T3")
        self.finish(one, "T1")
        self.finish(two, "T2", run_verify=False)
        self.finish(three, "T3")
        out = self.fails("settle", "T1", "T2", "T3")
        self.assertIn("T2: NOT settled", out)
        self.assertNotIn("T3:", out)
        self.assertEqual(self.by_id("T1")["status"], "done")
        self.assertEqual(self.by_id("T3")["status"], "in-progress")

    def test_squash(self) -> None:
        self.edit_config('merge = "no-ff"', 'merge = "squash"')
        self.commit_all("squash")
        self.arrange(self.t("T1"))
        self.work()
        self.ok("settle", "T1")
        commit = self.by_id("T1")["commit"]
        self.assertEqual(len(self.git("rev-list", "--parents", "-n", "1", commit).split()), 2)
        self.assertTrue((self.root / "T1.txt").exists())
        self.assertEqual(self.git("branch", "--list", "task/t1"), "")

    def test_pr_mode_waits_for_the_commit(self) -> None:
        self.edit_config('merge = "no-ff"', 'merge = "pr"')
        self.commit_all("pr")
        self.arrange(self.t("T1"))
        self.work()
        self.assertIn("branches.merge is pr", self.fails("settle", "T1"))
        self.git("merge", "-q", "--no-ff", "-m", "the PR", "task/t1")
        merge = self.git("rev-parse", "HEAD").strip()
        self.ok("settle", "T1", "--commit", merge)
        self.assertEqual(self.by_id("T1")["commit"], merge)

    def test_a_commit_not_on_the_integration_branch_is_refused(self) -> None:
        self.arrange(self.t("T1"))
        where = self.work()
        tip = self.git_at(where, "rev-parse", "HEAD").strip()
        self.assertIn("isn't on main", self.fails("settle", "T1", "--commit", tip))

    def test_commit_names_one_task(self) -> None:
        self.arrange(self.t("T1"), self.t("T2", 20))
        self.assertIn("one task", self.fails("settle", "T1", "T2", "--commit", "HEAD"))

    def test_work_committed_straight_to_the_integration_branch(self) -> None:
        self.arrange(self.t("T1"))
        self.ok("claim", "--commit", "T1")
        (self.root / "a.txt").write_text("x")
        self.ok("verify", "T1")
        folder = self.ws_dir / "alpha" / "evidence"
        folder.mkdir()
        (folder / "T1.md").write_text(evidence_text("T1"))
        self.commit_all("T1 on the trunk")
        head = self.git("rev-parse", "HEAD").strip()
        self.ok("settle", "T1", "--commit", head)
        self.assertEqual(self.by_id("T1")["status"], "done")

    def test_post_merge_verify_can_be_skipped_and_says_so(self) -> None:
        self.arrange(self.t("T1"), self.t("T2", 20))
        one, two = self.claim("T1", "T2")
        self.finish(one, "T1")
        self.finish(two, "T2")
        self.ok("settle", "T1", "T2", "--skip-post-merge-verify")
        self.assertEqual(self.by_id("T2")["verification"]["postMerge"], "skipped")

    def test_keep_leaves_the_worktree_and_branch(self) -> None:
        self.arrange(self.t("T1"))
        where = self.work()
        self.ok("settle", "T1", "--keep")
        self.assertTrue(where.exists())
        self.assertIn("task/t1", self.git("branch", "--list", "task/t1"))


class RecoveryTests(SettleTestCase):
    def test_a_crash_after_the_merge_finishes_on_the_next_run(self) -> None:
        self.arrange(self.t("T1"))
        self.work()
        with mock.patch.object(settle, "_record", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.ws("settle", "T1")
        self.assertEqual(self.by_id("T1")["status"], "in-progress")
        merge = self.git("rev-parse", "HEAD").strip()
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.ok("settle", "T1")
        task_ = self.by_id("T1")
        self.assertEqual((task_["status"], task_["commit"]), ("done", merge))
        self.assertEqual(self.git("rev-parse", "HEAD^").strip(), merge)

    def test_a_crash_after_a_squash_merge_finishes_too(self) -> None:
        self.edit_config('merge = "no-ff"', 'merge = "squash"')
        self.commit_all("squash")
        self.arrange(self.t("T1"))
        self.work()
        with mock.patch.object(settle, "_record", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.ws("settle", "T1")
        merge = self.git("rev-parse", "HEAD").strip()
        self.ok("settle", "T1")
        self.assertEqual(self.by_id("T1")["commit"], merge)

    def test_a_crash_after_a_merge_that_reran_verify_finishes_too(self) -> None:
        self.arrange(self.t("T1"), self.t("T2", 20))
        one, two = self.claim("T1", "T2")
        self.finish(one, "T1")
        self.finish(two, "T2")
        self.ok("settle", "T1")
        with mock.patch.object(settle, "_record", side_effect=KeyboardInterrupt):
            with self.assertRaises(KeyboardInterrupt):
                self.ws("settle", "T2")
        self.ok("settle", "T2")
        self.assertEqual(self.by_id("T2")["verification"]["postMerge"], "ran")

    def test_a_failed_tracking_commit_restores_every_file(self) -> None:
        self.arrange(self.t("T1"))
        self.work(evidence=evidence_text("T1", proposals="### P1: a call\nWhy. Rejected: b."))
        with mock.patch.object(act, "commit", side_effect=act.Refused("hook said no")):
            self.assertIn("hook said no", self.fails("settle", "T1"))
        self.assertEqual(self.git("status", "--porcelain"), "")
        self.assertEqual(self.by_id("T1")["status"], "in-progress")
        self.ok("settle", "T1")
        self.assertIn("a call", (self.ws_dir / "alpha" / "DECISIONS.md").read_text())

    def test_a_failing_commit_hook_on_the_merge_leaves_it_clean(self) -> None:
        self.arrange(self.t("T1"))
        self.work()
        head = self.git("rev-parse", "HEAD")
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(exist_ok=True)
        hook.write_text("#!/bin/sh\necho hook said no >&2\nexit 1\n")
        hook.chmod(0o755)
        self.assertIn("the merge commit failed", self.fails("settle", "T1"))
        self.assertEqual(self.git("rev-parse", "HEAD"), head)
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_a_blocked_task_can_finish_later(self) -> None:
        self.arrange(self.t("T1"))
        where = self.work(evidence="# T1\n\n- **Status:** blocked (needs a key)\n", run_verify=False)
        self.ok("settle", "T1")
        self.assertEqual(self.by_id("T1")["status"], "blocked")
        self.assertIn("still blocked", self.fails("settle", "T1"))
        self.finish(where, "T1", files={"more.txt": "x"})
        self.ok("settle", "T1")
        self.assertEqual(self.by_id("T1")["status"], "done")


class BookkeepingTests(SettleTestCase):
    def test_decisions_are_numbered_across_a_batch_in_merge_order(self) -> None:
        self.arrange(self.t("T1"), self.t("T2", 20))
        one, two = self.claim("T1", "T2")
        self.finish(one, "T1", evidence=evidence_text("T1", proposals="### P1: alpha\nWhy. Rejected: x.\n\n"
                                                                      "### P2: beta\nWhy. Rejected: y."))
        self.finish(two, "T2", evidence=evidence_text("T2", proposals="### P1: gamma\nWhy. Rejected: z."))
        out = self.ok("settle", "T1", "T2")
        self.assertIn("numbered D001, D002, D003", out)
        log = (self.ws_dir / "alpha" / "DECISIONS.md").read_text()
        self.assertLess(log.index("D001"), log.index("D003"))
        self.assertIn("T2): gamma", log)
        self.assertIn("### D003: gamma",
                      (self.ws_dir / "alpha" / "evidence" / "T2.md").read_text())

    def test_progress_goes_newest_first_under_the_header(self) -> None:
        self.arrange(self.t("T1"), self.t("T2", 20, blockedBy=["T1"]))
        (self.ws_dir / "alpha" / "PROGRESS.md").write_text("# Progress\n\n---\n")
        self.commit_all("header")
        self.work("T1")
        self.ok("settle", "T1")
        self.work("T2")
        self.ok("settle", "T2")
        text = (self.ws_dir / "alpha" / "PROGRESS.md").read_text()
        self.assertLess(text.index("---"), text.index("T2: title"))
        self.assertLess(text.index("T2: title"), text.index("T1: title"))
        self.assertIn("Verified: test pass", text)
        self.assertIn("evidence/T1.md", text)

    def test_the_handoff_says_where_things_stand(self) -> None:
        self.arrange(self.t("T1"), self.t("T2", 20, blockedBy=["T1"]))
        self.work(evidence=evidence_text("T1", gotchas="Watch the cache."))
        self.ok("settle", "T1", "--note", "Back on Monday.")
        text = (self.ws_dir / "alpha" / "session_handoff.md").read_text()
        self.assertIn("1/2 done", text)
        self.assertIn("ws claim --commit T2", text)
        self.assertIn("Watch the cache.", text)
        self.assertIn("Back on Monday.", text)

    def test_the_registry_is_synced_in_the_same_commit(self) -> None:
        self.arrange(self.t("T1"))
        self.work()
        self.ok("settle", "T1")
        self.assertEqual(self.entry()["progress"]["done"], 1)
        self.assertIn("workstreams.json",
                      self.git("show", "--name-only", "--format=", "HEAD"))
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_a_lite_workstream_settles_without_the_files_it_never_had(self) -> None:
        self.ok("new", "small", "--title", "S", "--summary", "s", "--tier", "lite")
        (self.ws_dir / "small" / "PLAN.md").write_text("# plan\n")
        self.seed_ok([self.t("L1")], "small")
        self.commit_all("seeded")
        self.ok("claim", "--commit", "L1", "-w", "small")
        self.ok("worktree", "create", "L1", "-w", "small")
        where = self.root / ".workstream" / "worktrees" / "l1"
        (where / "a.txt").write_text("x")
        code, out, err = self.ws_at(where, "verify", "L1", "-w", "small")
        self.assertEqual(code, 0, out + err)
        folder = where / "workstreams" / "small" / "evidence"
        folder.mkdir()
        (folder / "L1.md").write_text(evidence_text("L1"))
        self.git_at(where, "add", "-A")
        self.git_at(where, "commit", "-q", "-m", "work")
        self.ok("settle", "L1", "-w", "small")
        self.assertFalse((self.ws_dir / "small" / "PROGRESS.md").exists())
        self.assertFalse((self.ws_dir / "small" / "DECISIONS.md").exists())
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_what_settling_writes_matches_the_published_schemas(self) -> None:
        self.arrange(self.t("T1"), self.t("T2", 20))
        one, two = self.claim("T1", "T2")
        self.finish(one, "T1")
        self.finish(two, "T2")
        self.ok("baseline", "record", "test")
        self.commit_all("baseline")
        self.ok("settle", "T1", "T2")
        self.ok("validate")
        queue = self.queue()
        self.assertEqual(problems(queue, load_schema("tasks"), load_schema("tasks")), [])
        snapshot = json.loads(self.ok("snapshot", "-w", "alpha"))
        self.assertEqual(problems(snapshot, load_schema("snapshot"), load_schema("snapshot")), [])
        record = json.loads((self.ws_dir / "alpha" / "baseline.json").read_text())
        self.assertEqual(problems(record, load_schema("baseline"), load_schema("baseline")), [])

    def test_reset_clears_the_verification(self) -> None:
        self.arrange(self.t("T1"))
        self.work()
        self.ok("settle", "T1")
        self.ok("reset", "T1", "--yes")
        self.assertIsNone(self.by_id("T1")["verification"])


class EvidenceCommandTests(SettleTestCase):
    def test_new_writes_a_skeleton_once(self) -> None:
        self.arrange(self.t("T1"))
        self.git("switch", "-q", "-c", "task/t1")
        self.ok("evidence", "new", "T1")
        self.assertIn("{{", (self.ws_dir / "alpha" / "evidence" / "T1.md").read_text())
        self.assertIn("already exists", self.fails("evidence", "new", "T1"))

    def test_check_from_a_worktree_says_what_is_left(self) -> None:
        self.arrange(self.t("T1"))
        where = self.claim("T1")[0]
        code, out, _ = self.ws_at(where, "evidence", "check", "T1", "-w", "alpha")
        self.assertEqual(code, 1)
        self.assertIn("no evidence/T1.md", out)
        self.assertIn("never run", out)
        self.finish(where, "T1")
        code, out, _ = self.ws_at(where, "evidence", "check", "T1", "-w", "alpha")
        self.assertEqual(code, 0, out)
        (where / "dirty.txt").write_text("x")
        code, out, _ = self.ws_at(where, "evidence", "check", "T1", "-w", "alpha")
        self.assertEqual(code, 1)
        self.assertIn("everything is committed: dirty.txt", out)

    def test_check_catches_tracking_edits_before_the_coordinator_does(self) -> None:
        self.arrange(self.t("T1"))
        where = self.work(files={"workstreams/alpha/DECISIONS.md": "D999\n"})
        code, out, _ = self.ws_at(where, "evidence", "check", "T1", "-w", "alpha")
        self.assertEqual(code, 1)
        self.assertIn("workstreams/alpha/DECISIONS.md", out)


class BriefTests(SettleTestCase):
    def test_a_brief_for_a_worktree_task(self) -> None:
        self.arrange(self.t("T1", files=["a.py"], summary="Do the thing."))
        where = self.claim("T1")[0]
        brief = self.ok("brief", "T1")
        self.assertIn("# T1: title of T1", brief)
        self.assertIn(f"Work in `{where}`", brief)
        self.assertIn("Do the thing.", brief)
        self.assertIn("1. works", brief)
        self.assertIn("- test: `true`", brief)
        self.assertIn("ws verify T1 -w alpha", brief)

    def test_without_a_worktree_it_says_to_branch(self) -> None:
        self.arrange(self.t("T1"))
        self.assertIn("git switch -c task/t1", self.ok("brief", "T1"))

    def test_a_background_worker_reports_and_stops(self) -> None:
        self.arrange(self.t("T1"))
        brief = self.ok("brief", "T1")
        self.assertIn("5. Report: done or blocked", brief)
        self.assertNotIn("ws settle", brief)

    def test_a_foreground_task_says_to_land_it_too(self) -> None:
        self.arrange(self.t("T1", mode="foreground"))
        brief = self.ok("brief", "T1")
        self.assertIn("`git switch main`, then `ws settle T1 -w alpha`", brief)
        self.assertNotIn("5. Report:", brief)

    def test_a_citation_with_no_section_is_flagged(self) -> None:
        self.arrange(self.t("T1", findings=["T9"]))
        self.assertIn("not found in PLAN.md: T9", self.ok("brief", "T1"))

    def test_long_decision_logs_get_trimmed_with_a_pointer(self) -> None:
        self.arrange(self.t("T1"))
        log = self.ws_dir / "alpha" / "DECISIONS.md"
        log.write_text("".join(f"## D{n:03d} (2026-01-01, user): call {n}\n\n{'why ' * 100}\n\n"
                               for n in range(1, 40)))
        brief = self.ok("brief", "T1", "--max-chars", "3000")
        self.assertLess(len(brief), 3200)
        self.assertIn("more: `ws decisions --for T1 -w alpha`", brief)
        self.assertIn("call 39", brief)
        self.assertNotIn("call 1\n", brief)

    def test_trimming_never_cuts_the_task(self) -> None:
        self.arrange(self.t("T1"))
        brief = self.ok("brief", "T1", "--max-chars", "10")
        self.assertIn("1. works", brief)
        self.assertIn("When the work is done", brief)

    def test_decide_takes_the_next_number(self) -> None:
        self.arrange(self.t("T1"))
        (self.ws_dir / "alpha" / "DECISIONS.md").write_text("## D004 (2026-01-01, user): old\n\nA.\n")
        self.assertIn("D005", self.ok("decide", "keep it", "--why", "Because. Rejected: no."))
        text = (self.ws_dir / "alpha" / "DECISIONS.md").read_text()
        self.assertIn("coordinator): keep it", text)
        self.assertIn("Because. Rejected: no. **Closed.**", text)

    def test_decide_works_where_there_is_no_log_yet(self) -> None:
        self.ok("new", "small", "--title", "S", "--summary", "s", "--tier", "lite")
        self.assertIn("D001", self.ok("decide", "x", "--why", "y", "--by", "user", "-w", "small"))

    def test_a_users_decision_reaches_every_brief(self) -> None:
        self.arrange(self.t("T1"))
        self.ok("decide", "no new endpoints", "--why", "Scope.", "--by", "user")
        self.assertIn("no new endpoints", self.ok("brief", "T1"))

    def test_decisions_command(self) -> None:
        self.arrange(self.t("T1"))
        (self.ws_dir / "alpha" / "DECISIONS.md").write_text(
            "## D001 (2026-01-01, user): scope\n\nA.\n\n## D002 (2026-01-01, T9): other\n\nB.\n")
        self.assertIn("D002", self.ok("decisions"))
        filtered = self.ok("decisions", "--for", "T1")
        self.assertIn("D001", filtered)
        self.assertNotIn("D002", filtered)


class ReviewAfterClaimTests(SettleTestCase):
    def test_reviewing_a_branch_leaves_out_the_claim_commit(self) -> None:
        self.arrange(self.t("T1"))
        where = self.claim("T1")[0]
        self.finish(where, "T1")
        data = json.loads(self.ok("review", "T1"))
        paths = [f["path"] for f in data["files"]]
        self.assertIn("T1.txt", paths)
        self.assertNotIn("workstreams/workstreams.json", paths)
        self.assertNotIn("workstreams/alpha/tasks_list.json", paths)
