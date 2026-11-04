"""The task queue through the CLI: seed, add, update, next, wave, validate, claim, unclaim."""

from __future__ import annotations

import json
import os
import re
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import WsTestCase, task
from tests.test_protocol import fill_in
from tests.test_schema import load_schema, problems
from workstream import fsutil, graph, protocol, tasks
from workstream.cli import build_parser
from workstream.config import Config


class SeedTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()

    def test_fills_defaults_and_sorts_by_priority(self) -> None:
        self.seed_ok([task("X-02", 20), task("X-01", 10)])
        data = self.queue()
        self.assertEqual([t["id"] for t in data["tasks"]], ["X-01", "X-02"])
        for field, default in tasks.TASK_FIELD_DEFAULTS.items():
            self.assertEqual(data["tasks"][0][field], default, field)

    def test_stamps_the_schema_version_first_and_writes_fields_in_order(self) -> None:
        self.seed_ok([task("X-01", 10)])
        data = self.queue()
        self.assertEqual(next(iter(data)), "schemaVersion")
        self.assertEqual(data["schemaVersion"], tasks.SCHEMA_VERSION)
        self.assertEqual(list(data["tasks"][0]), tasks.FIELD_ORDER)

    def test_keeps_a_field_the_schema_does_not_know_at_the_end(self) -> None:
        self.seed_ok([task("X-01", 10, team="payments")])
        self.assertEqual(list(self.by_id("X-01"))[-1], "team")

    def test_appends_to_an_existing_queue(self) -> None:
        self.seed_ok([task("X-01", 10)])
        code, out, _ = self.seed([task("X-02", 20)])
        self.assertEqual(code, 0)
        self.assertIn("(2 total)", out)

    def test_rejects_an_id_already_present(self) -> None:
        self.seed_ok([task("X-01", 10)])
        code, _, err = self.seed([task("X-01", 20)])
        self.assertEqual(code, 1)
        self.assertIn("already present", err)
        self.assertEqual(len(self.queue()["tasks"]), 1)

    def test_rejects_a_duplicate_priority_and_writes_nothing(self) -> None:
        code, _, err = self.seed([task("X-01", 10), task("X-02", 10)])
        self.assertEqual(code, 1)
        self.assertIn("duplicate priority: 10", err)
        self.assertEqual(self.queue()["tasks"], [])

    def test_rejects_a_seed_that_is_not_an_array(self) -> None:
        code, _, err = self.seed(task("X-01", 10))  # type: ignore[arg-type]
        self.assertEqual(code, 1)
        self.assertIn("JSON array", err)

    def test_rejects_an_unreadable_seed_file(self) -> None:
        self.assertIn("cannot read", self.fails("seed", "-w", "alpha", "/no/such/seed.json"))


class AddTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()

    def add(self, task_id: str, priority: int, *extra: str) -> tuple[int, str, str]:
        return self.ws("add", "-w", "alpha", "--id", task_id, "--phase", "1",
                       "--priority", str(priority), "--title", "t", *extra)

    def test_appends_a_task_with_split_lists(self) -> None:
        code, out, err = self.add("X-01", 10, "--files", "a.py, b.py", "--blocked-by", "X-00",
                                  "--acceptance", "one", "--acceptance", "two",
                                  "--verify", "test", "--verify", "make it")
        self.assertEqual(code, 0, err)
        t = self.by_id("X-01")
        self.assertEqual(t["files"], ["a.py", "b.py"])
        self.assertEqual(t["blockedBy"], ["X-00"])
        self.assertEqual(t["acceptance"], ["one", "two"])
        self.assertEqual(t["verify"], ["test", "make it"])
        self.assertEqual(t["status"], "todo")

    def test_rejects_a_duplicate_id(self) -> None:
        self.add("X-01", 10)
        code, _, err = self.add("X-01", 20)
        self.assertEqual(code, 1)
        self.assertIn("already exists", err)

    def test_rejects_a_duplicate_priority(self) -> None:
        self.add("X-01", 10)
        code, _, err = self.add("X-02", 10)
        self.assertEqual(code, 1)
        self.assertIn("priority 10 already used", err)


class UpdateTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.seed_ok([task("X-01", 10)])

    def update(self, *extra: str) -> tuple[int, str, str]:
        return self.ws("update", "-w", "alpha", "X-01", *extra)

    def test_in_progress_stamps_started_at_once(self) -> None:
        self.update("--status", "in-progress")
        first = self.by_id("X-01")["startedAt"]
        data = self.queue()
        data["tasks"][0]["startedAt"] = "2026-01-01T00:00:00Z"
        tasks.save(self.ws_dir / "alpha" / "tasks_list.json", data)
        self.update("--status", "blocked")
        self.update("--status", "in-progress")
        self.assertRegex(first, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(self.by_id("X-01")["startedAt"], "2026-01-01T00:00:00Z")

    def test_done_stamps_completed_at_and_records_commit_and_notes(self) -> None:
        head = self.git("rev-parse", "HEAD").strip()
        code, _, err = self.update("--status", "done", "--commit", head, "--notes", "landed")
        self.assertEqual(code, 0, err)
        t = self.by_id("X-01")
        self.assertEqual((t["status"], t["commit"], t["notes"]), ("done", head, "landed"))
        self.assertRegex(t["completedAt"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")

    def test_rejects_a_status_outside_the_status_values(self) -> None:
        code, _, err = self.update("--status", "finished")
        self.assertEqual(code, 1)
        self.assertIn("status must be one of", err)
        self.assertEqual(self.by_id("X-01")["status"], "todo")

    def test_rejects_an_unknown_id(self) -> None:
        self.assertIn("no task with id 'X-99'",
                      self.fails("update", "-w", "alpha", "X-99", "--status", "done"))

    def test_refreshes_the_envelope_updated_date(self) -> None:
        path = self.ws_dir / "alpha" / "tasks_list.json"
        data = self.queue()
        data["updated"] = "2000-01-01"
        path.write_text(json.dumps(data))
        before = fsutil.today()
        self.update("--notes", "touched")
        self.assertIn(self.queue()["updated"], {before, fsutil.today()})

    def test_replaces_verify(self) -> None:
        self.update("--verify", "test", "--verify", "lint")
        self.assertEqual(self.by_id("X-01")["verify"], ["test", "lint"])


class CorrectAcceptanceTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.seed_ok([task("X-01", 10, acceptance=["one", {"text": "two", "kind": "manual"}, "three"]),
                      task("X-02", 20, acceptance=["one"], status="deferred"),
                      task("X-03", 30, acceptance=["one"], status="done", commit="abc1234")])
        self.ok("decide", "Change it", "--why", "the target moved", "--by", "user", "-w", "alpha")
        self.queue_path = self.ws_dir / "alpha" / "tasks_list.json"

    def refused(self, needle: str, *argv: str) -> None:
        before = self.queue_path.read_bytes()
        self.assertIn(needle, self.fails("update", "-w", "alpha", *argv))
        self.assertEqual(self.queue_path.read_bytes(), before)

    def test_it_replaces_the_item_and_appends_the_decision(self) -> None:
        self.ok("update", "-w", "alpha", "X-01", "--acceptance", "3", "new three",
                "--because", "D001")
        self.assertEqual(self.by_id("X-01")["acceptance"],
                         ["one", {"text": "two", "kind": "manual"}, "new three (changed by D001)"])

    def test_a_manual_item_stays_manual(self) -> None:
        self.ok("update", "-w", "alpha", "X-01", "--acceptance", "2", "new two",
                "--because", "D001")
        item = self.by_id("X-01")["acceptance"][1]
        self.assertEqual(item, {"text": "new two (changed by D001)", "kind": "manual"})
        self.assertEqual(tasks.acceptance_text(item), "new two (changed by D001) (manual)")

    def test_a_second_correction_names_only_the_later_decision(self) -> None:
        self.ok("decide", "Again", "--why", "it moved again", "--by", "user", "-w", "alpha")
        for decision in ("D001", "D002"):
            self.ok("update", "-w", "alpha", "X-01", "--acceptance", "1", "new",
                    "--because", decision)
        self.assertEqual(self.by_id("X-01")["acceptance"][0], "new (changed by D002)")

    def test_a_missing_because_is_refused(self) -> None:
        self.refused("needs --because", "X-01", "--acceptance", "1", "new")

    def test_an_unknown_decision_is_refused(self) -> None:
        self.refused("no decision D999", "X-01", "--acceptance", "1", "new", "--because", "D999")

    def test_an_item_that_does_not_exist_is_refused(self) -> None:
        for number in ("0", "4", "two", "-1"):
            with self.subTest(number=number):
                self.refused(f"no acceptance item {number}", "X-01", "--acceptance", number, "new",
                             "--because", "D001")

    def test_a_done_or_deferred_task_is_refused(self) -> None:
        self.refused("X-03 is done", "X-03", "--acceptance", "1", "new", "--because", "D001")
        self.refused("X-02 is deferred", "X-02", "--acceptance", "1", "new", "--because", "D001")

    def test_blank_text_and_a_stray_because_are_refused(self) -> None:
        self.refused("new text", "X-01", "--acceptance", "1", "  ", "--because", "D001")
        self.refused("goes with --acceptance", "X-01", "--because", "D001", "--notes", "n")

    def test_it_goes_alone(self) -> None:
        self.refused("goes alone", "X-01", "--acceptance", "1", "new", "--because", "D001",
                     "--status", "blocked")

    def test_commit_commits_only_the_queue(self) -> None:
        self.commit_all("tracking")
        (self.root / "other.txt").write_text("someone's edit\n")
        head = self.git("rev-parse", "HEAD").strip()
        out = self.ok("update", "-w", "alpha", "X-01", "--acceptance", "1", "new",
                      "--because", "D001", "--commit")
        self.assertIn(f"committed {self.git('rev-parse', '--short', 'HEAD').strip()}", out)
        self.assertEqual(self.git("rev-parse", "HEAD~1").strip(), head)
        self.assertEqual(self.git("log", "-1", "--format=%s").strip(),
                         "alpha: X-01 acceptance 1, D001")
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD").split(),
                         ["workstreams/alpha/tasks_list.json"])
        self.assertEqual(self.git("status", "--porcelain").split(), ["??", "other.txt"])
        self.assertEqual(self.by_id("X-01")["acceptance"][0], "new (changed by D001)")

    def test_a_refused_commit_leaves_the_queue_and_history_alone(self) -> None:
        self.commit_all("tracking")
        head = self.git("rev-parse", "HEAD").strip()
        self.refused("no acceptance item 9", "X-01", "--acceptance", "9", "new",
                     "--because", "D001", "--commit")
        self.refused("takes no hash", "X-01", "--acceptance", "1", "new", "--because", "D001",
                     "--commit", head)
        self.queue_path.write_text(self.queue_path.read_text() + "\n")
        self.refused("dirty tracking path", "X-01", "--acceptance", "1", "new",
                     "--because", "D001", "--commit")
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), head)

    def test_a_failed_commit_restores_the_queue(self) -> None:
        self.commit_all("tracking")
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        self.refused("commit failed", "X-01", "--acceptance", "1", "new", "--because", "D001",
                     "--commit")

    def test_a_bare_commit_without_acceptance_is_refused(self) -> None:
        self.refused("needs a hash", "X-01", "--commit")

    def test_a_commit_hash_is_still_recorded(self) -> None:
        self.ok("update", "-w", "alpha", "X-01", "--commit", "abc1234")
        self.assertEqual(self.by_id("X-01")["commit"], "abc1234")

    def test_the_brief_and_skeleton_from_a_worktree_show_the_new_text(self) -> None:
        self.commit_all("seed")
        self.ok("claim", "--commit", "X-01", "-w", "alpha")
        self.ok("worktree", "create", "X-01", "-w", "alpha")
        tree = self.root / self.project().config.worktree_dir / "x-01"
        self.ok("update", "-w", "alpha", "X-01", "--acceptance", "3", "new three",
                "--because", "D001", "--commit")
        self.ok("update", "-w", "alpha", "X-01", "--acceptance", "2", "new two",
                "--because", "D001", "--commit")
        self.assertIn('"three"', (tree / "workstreams/alpha/tasks_list.json").read_text())
        code, brief, err = self.ws_at(tree, "brief", "X-01", "-w", "alpha")
        self.assertEqual(code, 0, err)
        self.assertIn("3. new three (changed by D001)", brief)
        self.assertIn("2. new two (changed by D001) (manual)", brief)
        code, _, err = self.ws_at(tree, "evidence", "new", "X-01", "-w", "alpha")
        self.assertEqual(code, 0, err)
        skeleton = (tree / "workstreams/alpha/evidence/X-01.md").read_text()
        self.assertIn("3. new three (changed by D001) -> ", skeleton)
        self.assertIn("2. new two (changed by D001) (manual) -> ", skeleton)

    def test_the_coordinate_skill_names_it_in_a_form_that_parses(self) -> None:
        commands = [c for c in re.findall(r"`(ws [^`]+)`", protocol.skill_text("ws-coordinate"))
                    if "--acceptance" in c]
        self.assertEqual(len(commands), 1)
        args = build_parser().parse_args(fill_in(commands[0]))
        self.assertEqual((args.acceptance, args.because, args.commit), (["x", "x"], "x", True))


class CorrectSummaryTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.seed_ok([task("X-01", 10, summary="old", acceptance=["one"]),
                      task("X-02", 20, summary="old", status="deferred"),
                      task("X-03", 30, summary="old", status="done", commit="abc1234")])
        self.ok("decide", "Change it", "--why", "the target moved", "--by", "user", "-w", "alpha")
        self.queue_path = self.ws_dir / "alpha" / "tasks_list.json"

    def refused(self, needle: str, *argv: str) -> None:
        before = self.queue_path.read_bytes()
        self.assertIn(needle, self.fails("update", "-w", "alpha", *argv))
        self.assertEqual(self.queue_path.read_bytes(), before)

    def test_it_replaces_the_summary_and_the_brief_shows_it(self) -> None:
        out = self.ok("update", "-w", "alpha", "X-01", "--summary", " new text ",
                      "--because", "D001")
        self.assertIn("updated X-01: summary, D001; commit it", out)
        self.assertEqual(self.by_id("X-01")["summary"], "new text (changed by D001)")
        brief = self.ok("brief", "X-01", "-w", "alpha")
        self.assertIn("new text (changed by D001)", brief)
        self.assertNotIn("\nold\n", brief)

    def test_a_second_correction_names_only_the_later_decision(self) -> None:
        self.ok("decide", "Again", "--why", "it moved again", "--by", "user", "-w", "alpha")
        for decision in ("D001", "D002"):
            self.ok("update", "-w", "alpha", "X-01", "--summary", "new", "--because", decision)
        self.assertEqual(self.by_id("X-01")["summary"], "new (changed by D002)")

    def test_a_missing_because_is_refused(self) -> None:
        self.refused("--summary needs --because", "X-01", "--summary", "new")

    def test_an_unknown_decision_is_refused(self) -> None:
        self.refused("no decision D999", "X-01", "--summary", "new", "--because", "D999")

    def test_empty_text_is_refused(self) -> None:
        for text in ("", "  "):
            with self.subTest(text=text):
                self.refused("--summary needs the new text", "X-01", "--summary", text,
                             "--because", "D001")

    def test_a_done_or_deferred_task_is_refused(self) -> None:
        self.refused("X-03 is done", "X-03", "--summary", "new", "--because", "D001")
        self.refused("X-02 is deferred", "X-02", "--summary", "new", "--because", "D001")
        self.assertEqual(self.by_id("X-03")["summary"], "old")
        self.assertEqual(self.by_id("X-02")["summary"], "old")

    def test_it_goes_alone(self) -> None:
        for extra in (("--status", "blocked"), ("--notes", "n"), ("--verify", "test")):
            with self.subTest(extra=extra):
                self.refused("--summary goes alone", "X-01", "--summary", "new",
                             "--because", "D001", *extra)
        self.refused("goes alone", "X-01", "--summary", "new", "--acceptance", "1", "new",
                     "--because", "D001")

    def test_a_stray_because_or_bare_commit_names_both_flags(self) -> None:
        self.refused("--because goes with --acceptance or --summary", "X-01",
                     "--because", "D001", "--notes", "n")
        self.refused("--commit needs a hash, except with only --acceptance, --summary", "X-01",
                     "--commit")

    def test_commit_commits_only_the_queue_and_prints_the_hash(self) -> None:
        self.commit_all("tracking")
        (self.root / "other.txt").write_text("someone's edit\n")
        head = self.git("rev-parse", "HEAD").strip()
        out = self.ok("update", "-w", "alpha", "X-01", "--summary", "new", "--because", "D001",
                      "--commit")
        self.assertIn(f"committed {self.git('rev-parse', '--short', 'HEAD').strip()}", out)
        self.assertEqual(self.git("rev-parse", "HEAD~1").strip(), head)
        self.assertEqual(self.git("log", "-1", "--format=%s").strip(),
                         "alpha: X-01 summary, D001")
        self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD").split(),
                         ["workstreams/alpha/tasks_list.json"])
        self.assertEqual(self.git("status", "--porcelain").split(), ["??", "other.txt"])
        self.assertEqual(self.by_id("X-01")["summary"], "new (changed by D001)")

    def test_a_refused_commit_leaves_the_queue_and_history_alone(self) -> None:
        self.commit_all("tracking")
        head = self.git("rev-parse", "HEAD").strip()
        self.refused("X-03 is done", "X-03", "--summary", "new", "--because", "D001", "--commit")
        self.refused("takes no hash", "X-01", "--summary", "new", "--because", "D001",
                     "--commit", head)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), head)

    def test_a_failed_commit_restores_the_queue(self) -> None:
        self.commit_all("tracking")
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        self.refused("commit failed", "X-01", "--summary", "new", "--because", "D001", "--commit")


class UpdateCommitsVerifyAndNotesTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.seed_ok([task("X-01", 10)])
        self.queue_path = self.ws_dir / "alpha" / "tasks_list.json"
        self.commit_all("tracking")

    def refused(self, needle: str, *argv: str) -> None:
        before = self.queue_path.read_bytes()
        head = self.git("rev-parse", "HEAD").strip()
        self.assertIn(needle, self.fails("update", "-w", "alpha", "X-01", *argv))
        self.assertEqual(self.queue_path.read_bytes(), before)
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), head)

    def test_it_commits_only_the_queue_on_the_integration_branch_and_prints_the_hash(self) -> None:
        cases = (
            ("verify", ("--verify", "make one"), ["make one"], None),
            ("notes", ("--notes", "first"), None, "first"),
            ("verify and notes", ("--verify", "make two", "--verify", "make three",
                                  "--notes", "second"), ["make two", "make three"], "second"),
        )
        (self.root / "other.txt").write_text("someone's edit\n")
        for what, flags, verify, notes in cases:
            with self.subTest(what=what):
                before = self.by_id("X-01")
                head = self.git("rev-parse", "HEAD").strip()
                out = self.ok("update", "-w", "alpha", "X-01", *flags, "--commit")
                short = self.git("rev-parse", "--short", "HEAD").strip()
                self.assertIn(f"updated X-01: {what}; committed {short}", out)
                self.assertEqual(self.git("rev-parse", "HEAD~1").strip(), head)
                self.assertEqual(self.git("branch", "--show-current").strip(),
                                 self.project().config.integration)
                self.assertEqual(self.git("log", "-1", "--format=%s").strip(),
                                 f"alpha: X-01 {what}")
                self.assertEqual(self.git("show", "--name-only", "--format=", "HEAD").split(),
                                 ["workstreams/alpha/tasks_list.json"])
                self.assertEqual(self.git("status", "--porcelain").split(), ["??", "other.txt"])
                after = self.by_id("X-01")
                self.assertEqual(after["verify"], before["verify"] if verify is None else verify)
                self.assertEqual(after["notes"], before["notes"] if notes is None else notes)
                self.assertIsNone(after.get("commit"))

    def test_a_failed_commit_restores_the_queue(self) -> None:
        hook = self.root / ".git" / "hooks" / "pre-commit"
        hook.write_text("#!/bin/sh\nexit 1\n")
        hook.chmod(0o755)
        for flags in (("--verify", "make new"), ("--notes", "new"),
                      ("--verify", "make new", "--notes", "new")):
            with self.subTest(flags=flags):
                self.refused("commit failed", *flags, "--commit")

    def test_it_is_refused_off_the_integration_branch_or_with_a_dirty_queue(self) -> None:
        self.queue_path.write_text(self.queue_path.read_text() + "\n")
        self.refused("dirty tracking path", "--notes", "new", "--commit")
        self.git("checkout", "--", "workstreams/alpha/tasks_list.json")
        self.git("checkout", "-q", "-b", "elsewhere")
        self.refused("not main", "--verify", "make new", "--commit")

    def test_bare_commit_alone_or_with_the_other_flags_is_still_refused(self) -> None:
        self.refused("--commit needs a hash", "--commit")
        cases = (("--status", "blocked"), ("--mode", "foreground"), ("--requires", "db"),
                 ("--release-impact", "none"))
        for flags in cases:
            for shared in ((), ("--notes", "new"), ("--verify", "make new")):
                with self.subTest(flags=flags, shared=shared):
                    self.refused("--commit needs a hash", *flags, *shared, "--commit")

    def test_a_commit_hash_is_still_recorded_and_commits_nothing(self) -> None:
        head = self.git("rev-parse", "HEAD").strip()
        self.ok("update", "-w", "alpha", "X-01", "--notes", "new", "--verify", "make new",
                "--commit", "abc1234")
        after = self.by_id("X-01")
        self.assertEqual((after["commit"], after["notes"], after["verify"]),
                         ("abc1234", "new", ["make new"]))
        self.assertEqual(self.git("rev-parse", "HEAD").strip(), head)


class UpdateSaysWhatChangedTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.seed_ok([task("X-01", 10)])

    def says(self, *flags: str) -> str:
        return self.ok("update", "-w", "alpha", "X-01", *flags)

    def test_verify_alone_is_named_and_status_is_not(self) -> None:
        out = self.says("--verify", "make one")
        self.assertIn("updated X-01: verify\n", out)
        self.assertNotIn("status", out)

    def test_each_field_given_is_named(self) -> None:
        cases = (
            ("notes", ("--notes", "new")),
            ("mode", ("--mode", "foreground")),
            ("requires", ("--requires", "browser")),
            ("release-impact", ("--release-impact", "minor")),
            ("commit=abc1234", ("--commit", "abc1234")),
        )
        for what, flags in cases:
            with self.subTest(what=what):
                out = self.says(*flags)
                self.assertIn(f"updated X-01: {what}\n", out)
                self.assertNotIn("status", out)

    def test_several_given_together_are_all_named(self) -> None:
        out = self.says("--notes", "new", "--verify", "make one", "--mode", "foreground",
                        "--requires", "browser", "--release-impact", "minor",
                        "--commit", "abc1234", "--status", "in-progress")
        self.assertIn("updated X-01: status=in-progress, commit=abc1234, verify, notes, mode, "
                      "requires, release-impact\n", out)

    def test_an_emptied_field_is_still_named(self) -> None:
        self.assertIn("updated X-01: requires\n", self.says("--requires", ""))

    def test_status_still_prints_its_value(self) -> None:
        self.assertIn("updated X-01: status=blocked\n", self.says("--status", "blocked"))

    def test_no_change_flags_says_nothing_changed_and_writes_nothing(self) -> None:
        path = self.ws_dir / "alpha" / "tasks_list.json"
        before = path.read_bytes()
        out = self.says()
        self.assertIn("X-01: nothing changed\n", out)
        self.assertNotIn("updated", out)
        self.assertEqual(path.read_bytes(), before)

    def test_no_change_flags_on_an_unknown_task_still_fails(self) -> None:
        self.assertIn("X-99", self.fails("update", "-w", "alpha", "X-99"))


class DoneNeedsCommitTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.seed_ok([task("X-01", 10, status="in-progress")])

    def test_done_without_a_commit_is_refused(self) -> None:
        before = (self.ws_dir / "alpha" / "tasks_list.json").read_text()
        self.assertIn("X-01 has no commit",
                      self.fails("update", "-w", "alpha", "X-01", "--status", "done"))
        self.assertEqual((self.ws_dir / "alpha" / "tasks_list.json").read_text(), before)

    def test_done_with_a_commit_succeeds(self) -> None:
        head = self.git("rev-parse", "HEAD").strip()
        self.ok("update", "-w", "alpha", "X-01", "--status", "done", "--commit", head)
        t = self.by_id("X-01")
        self.assertEqual((t["status"], t["commit"]), ("done", head))

    def test_a_task_that_already_has_a_commit_needs_no_flag(self) -> None:
        self.ok("update", "-w", "alpha", "X-01", "--commit", self.git("rev-parse", "HEAD").strip())
        self.ok("update", "-w", "alpha", "X-01", "--status", "done")
        self.assertEqual(self.by_id("X-01")["status"], "done")


class SaveTests(unittest.TestCase):
    def setUp(self) -> None:
        import tempfile

        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = Path(tmp.name)
        self.file = self.dir / "tasks_list.json"

    def test_writes_through_a_temp_file_and_os_replace(self) -> None:
        tasks.save(self.file, {"tasks": [task("X-01", 10)]})
        with mock.patch.object(fsutil.os, "replace", wraps=os.replace) as rep:
            tasks.save(self.file, {"tasks": [task("X-02", 20)]})
        rep.assert_called_once()
        tmp, dest = rep.call_args.args
        self.assertEqual(Path(tmp).parent, self.dir)
        self.assertEqual(Path(dest), self.file)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["tasks_list.json"])

    def test_a_failed_write_leaves_the_old_file_whole_and_no_temp_file(self) -> None:
        tasks.save(self.file, {"tasks": [task("X-01", 10)]})
        original = self.file.read_text()
        with mock.patch.object(fsutil.os, "replace", side_effect=OSError("disk full")):
            with self.assertRaises(OSError):
                tasks.save(self.file, {"tasks": [task("X-02", 20)]})
        self.assertEqual(self.file.read_text(), original)
        self.assertEqual(sorted(p.name for p in self.dir.iterdir()), ["tasks_list.json"])

    def test_keeps_the_file_mode(self) -> None:
        tasks.save(self.file, {"tasks": []})
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o644)
        self.file.chmod(0o664)
        tasks.save(self.file, {"tasks": []})
        self.assertEqual(self.file.stat().st_mode & 0o777, 0o664)


class NextTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()

    def next_id(self) -> str | None:
        out = self.ok("next", "-w", "alpha", "--json")
        return None if out.startswith("(no actionable") else json.loads(out)["id"]

    def test_picks_the_lowest_priority_actionable_task(self) -> None:
        self.seed_ok([
            task("X-01", 10, status="done", commit="abc"),
            task("X-02", 20, needsUserDecision=True),
            task("X-03", 30, blockedBy=["X-04"]),
            task("X-04", 40, status="in-progress"),
            task("X-05", 50, blockedBy=["X-01"]),
            task("X-06", 60),
        ])
        self.assertEqual(self.next_id(), "X-05")

    def test_reports_when_nothing_is_actionable(self) -> None:
        self.seed_ok([task("X-01", 10, status="blocked"), task("X-02", 20, blockedBy=["X-01"])])
        self.assertIsNone(self.next_id())

    def test_skips_a_task_held_back_by_a_shared_file(self) -> None:
        self.seed_ok([task("X-01", 10, status="in-progress", files=["a.py"]),
                      task("X-02", 20, files=["a.py"]),
                      task("X-03", 30, files=["b.py"])])
        self.assertEqual(self.next_id(), "X-03")

    def test_a_held_task_stays_in_the_wave_report_and_the_actionable_list(self) -> None:
        rows = [task("X-01", 10, status="blocked", files=["a.py"]),
                task("X-02", 20, files=["a.py"]),
                task("X-03", 30)]
        self.seed_ok(rows)
        code, out, _ = self.ws("wave", "-w", "alpha")
        self.assertEqual(code, graph.WAVE_READY)
        self.assertIn("held back: 1 sharing files with unfinished work\n"
                      "  X-02  shares a.py with X-01\n", out)
        full = [tasks.normalize_task(row, Config()) for row in rows]
        self.assertEqual(graph.compute_wave(full)["heldBack"],
                         [{"id": "X-02", "by": "X-01", "path": "a.py"}])
        self.assertEqual([t["id"] for t in graph.actionable(full)], ["X-02", "X-03"])

    def test_keeps_the_lowest_priority_across_phases_when_skipping(self) -> None:
        self.seed_ok([task("X-01", 10, status="in-progress", files=["a.py"]),
                      task("X-02", 20, phase=1, files=["a.py"]),
                      task("X-03", 30, phase=2),
                      task("X-04", 40, phase=1)])
        self.assertEqual(self.next_id(), "X-03")

    def test_with_only_held_tasks_left_says_what_holds_each_and_exits_0(self) -> None:
        self.seed_ok([task("X-01", 10, status="in-progress", files=["a.py", "b.py"]),
                      task("X-02", 20, status="blocked", files=["c.py"]),
                      task("X-03", 30, files=["a.py", "b.py"]),
                      task("X-04", 40, files=["c.py"])])
        code, out, _ = self.ws("next", "-w", "alpha")
        self.assertEqual(code, 0)
        self.assertIn("held back: 2 sharing files with unfinished work\n"
                      "  X-03  shares a.py with X-01\n"
                      "  X-03  shares b.py with X-01\n"
                      "  X-04  shares c.py with X-02\n", out)


class WaveTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()

    def wave(self) -> tuple[int, str]:
        code, out, _ = self.ws("wave", "-w", "alpha")
        return code, out

    def test_ready_lists_the_lowest_phase_with_an_actionable_task(self) -> None:
        # X-01 (phase 1) waits on a phase-2 task, so phase 2 is the wave.
        self.seed_ok([
            task("X-01", 10, phase=1, blockedBy=["X-02"]),
            task("X-02", 20, phase=2, files=["a.py"], notes="needs care"),
            task("X-03", 30, phase=2),
            task("X-04", 40, phase=3),
        ])
        code, out = self.wave()
        self.assertEqual(code, graph.WAVE_READY)
        self.assertEqual(code, 0)
        self.assertIn("phase 2: 2 actionable, 4 open in total", out)
        self.assertIn("X-02", out)
        self.assertIn("X-03", out)
        self.assertNotIn("X-04", out)
        self.assertIn("files: a.py", out)
        self.assertIn("notes: needs care", out)

    def test_finished_when_every_task_is_done_or_deferred(self) -> None:
        self.seed_ok([task("X-01", 10, status="done", commit="abc"),
                      task("X-02", 20, status="deferred")])
        code, out = self.wave()
        self.assertEqual(code, graph.WAVE_FINISHED)
        self.assertEqual(code, 2)
        self.assertIn("queue finished", out)

    def test_stuck_when_open_tasks_remain_but_none_is_actionable(self) -> None:
        self.seed_ok([
            task("X-01", 10, status="blocked"),
            task("X-02", 20, needsUserDecision=True),
            task("X-03", 30, blockedBy=["X-01"]),
        ])
        code, out = self.wave()
        self.assertEqual(code, graph.WAVE_STUCK)
        self.assertEqual(code, 3)
        self.assertIn("X-01  phase=1  blocked", out)
        self.assertIn("X-02  phase=1  needsUserDecision", out)
        self.assertIn("X-03  phase=1  todo", out)

    def test_prints_each_task_mode_and_requirements(self) -> None:
        self.seed_ok([task("X-01", 10, requires=["browser"]), task("X-02", 20)])
        code, out = self.wave()
        self.assertEqual(code, 0, out)
        self.assertRegex(out, r"X-01  priority=10\s+mode=foreground")
        self.assertRegex(out, r"X-02  priority=20\s+mode=background")
        self.assertIn("requires: browser", out)

    def test_warns_on_a_files_overlap_and_still_exits_ready(self) -> None:
        self.seed_ok([task("X-01", 10, files=["a.py"]), task("X-02", 20, files=["a.py"])])
        code, out = self.wave()
        self.assertEqual(code, graph.WAVE_READY)
        self.assertIn("warning: X-01 and X-02 both list 'a.py' in files", out)

    def test_ready_wave_lists_in_progress_tasks_as_leftovers(self) -> None:
        self.seed_ok([task("X-01", 10), task("X-02", 20), task("X-03", 30)])
        self.ok("claim", "-w", "alpha", "--base", "cafe123", "--by", "batch-1", "X-01")
        self.ok("update", "-w", "alpha", "X-02", "--status", "in-progress")
        code, out = self.wave()
        self.assertEqual(code, graph.WAVE_READY, out)
        wave, leftovers = out.split("leftovers:")
        self.assertIn("X-03", wave)
        self.assertIn("2 in progress", leftovers)
        self.assertRegex(leftovers, r"X-01  phase=1  claimedBy=batch-1  baseCommit=cafe123  ")
        # Started with `update --status in-progress`: no claim to show.
        self.assertRegex(leftovers, r"X-02  phase=1  claimedBy=-  baseCommit=-  ")

    def test_no_leftovers_heading_when_nothing_is_in_progress(self) -> None:
        self.seed_ok([task("X-01", 10)])
        _, out = self.wave()
        self.assertNotIn("leftovers", out)

    def test_only_in_progress_tasks_open_is_stuck_and_lists_them(self) -> None:
        self.seed_ok([task("X-01", 10), task("X-02", 20, status="done", commit="abc")])
        self.ok("claim", "-w", "alpha", "--base", "cafe123", "--by", "batch-1", "X-01")
        code, out = self.wave()
        self.assertEqual(code, graph.WAVE_STUCK, out)
        self.assertIn("(stuck", out)
        self.assertIn("leftovers: 1 in progress", out)
        self.assertIn("X-01  phase=1  claimedBy=batch-1  baseCommit=cafe123", out)


class WaveHeldAndBlockedOutputTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()

    def wave(self) -> tuple[int, str]:
        code, out, _ = self.ws("wave", "-w", "alpha")
        return code, out

    def test_a_ready_wave_prints_blocked_tasks_and_held_tasks_with_their_causes(self) -> None:
        self.seed_ok([task("X-01", 10, status="blocked", blockedReason="the key is missing",
                           files=["a.py"]),
                      task("X-02", 20, files=["a.py"]),
                      task("X-03", 30)])
        code, out = self.wave()
        self.assertEqual(code, graph.WAVE_READY)
        self.assertIn("phase 1: 1 actionable, 3 open in total", out)
        self.assertIn("held back: 1 sharing files with unfinished work\n"
                      "  X-02  shares a.py with X-01\n", out)
        self.assertIn("blocked: 1\n  X-01  phase=1  the key is missing\n", out)

    def test_a_block_with_no_reason_falls_back_to_its_notes(self) -> None:
        self.seed_ok([task("X-01", 10, status="blocked", notes="old reason"), task("X-02", 20)])
        self.assertIn("  X-01  phase=1  old reason\n", self.wave()[1])

    def test_a_wave_of_held_tasks_exits_stuck_and_says_why(self) -> None:
        self.seed_ok([task("X-01", 10, status="in-progress", files=["a.py"]),
                      task("X-02", 20, files=["a.py"])])
        code, out = self.wave()
        self.assertEqual((code, graph.WAVE_STUCK), (3, 3))
        self.assertIn("stuck", out)
        self.assertIn("  X-02  shares a.py with X-01\n", out)
        self.assertIn("leftovers: 1 in progress", out)

    def test_a_stuck_wave_prints_blocked_reasons(self) -> None:
        self.seed_ok([task("X-01", 10, status="blocked", blockedReason="the key is missing")])
        code, out = self.wave()
        self.assertEqual(code, graph.WAVE_STUCK)
        self.assertIn("blocked: 1\n  X-01  phase=1  the key is missing\n", out)

    def test_nothing_is_printed_when_nothing_is_held_or_blocked(self) -> None:
        self.seed_ok([task("X-01", 10)])
        out = self.wave()[1]
        self.assertNotIn("held back", out)
        self.assertNotIn("blocked", out)


class ShowBlockedReasonTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.seed_ok([task("X-01", 10, status="blocked", blockedReason="the key is missing"),
                      task("X-02", 20, status="blocked", notes="old reason"),
                      task("X-03", 30)])

    def show(self, tid: str) -> str:
        code, out, _ = self.ws("show", "-w", "alpha", tid)
        self.assertEqual(code, 0)
        return out

    def test_a_blocked_task_with_a_reason_prints_it(self) -> None:
        self.assertIn("\nblocked: the key is missing\n", self.show("X-01"))

    def test_a_task_without_a_reason_prints_no_such_line(self) -> None:
        for tid in ("X-02", "X-03"):
            self.assertNotIn("blocked:", self.show(tid))


class ComputeWaveTests(unittest.TestCase):
    def full(self, tid: str, phase: int = 1, priority: int = 10, status: str = "todo",
             **extra) -> dict:
        return tasks.normalize_task({"id": tid, "phase": phase, "priority": priority,
                                     "title": tid, "status": status, **extra}, Config())

    def test_ready_takes_the_lowest_phase_with_overlaps_and_leftovers(self) -> None:
        rows = [
            self.full("X-04", phase=2, priority=40),
            self.full("X-03", phase=1, priority=30, files=["a.py"]),
            self.full("X-02", phase=1, priority=20, files=["a.py"]),
            self.full("X-01", phase=1, priority=10, status="in-progress"),
            self.full("X-05", phase=1, priority=50, blockedBy=["X-04"]),
        ]
        self.assertEqual(graph.compute_wave(rows), {
            "state": "ready", "phase": 1, "ids": ["X-02", "X-03"],
            "open": ["X-01", "X-02", "X-03", "X-04", "X-05"],
            "overlaps": [["X-02", "X-03", "a.py"]], "leftovers": ["X-01"], "heldBack": [],
        })

    def test_a_blocked_low_phase_falls_through_to_the_next_phase(self) -> None:
        rows = [self.full("X-01", phase=1, priority=10, blockedBy=["X-02"]),
                self.full("X-02", phase=2, priority=20)]
        wave = graph.compute_wave(rows)
        self.assertEqual((wave["state"], wave["phase"], wave["ids"]), ("ready", 2, ["X-02"]))

    def test_finished_when_every_task_is_done_or_deferred(self) -> None:
        rows = [self.full("X-01", status="done", commit="abc"),
                self.full("X-02", priority=20, status="deferred")]
        self.assertEqual(graph.compute_wave(rows), {
            "state": "finished", "phase": None, "ids": [], "open": [], "overlaps": [],
            "leftovers": [], "heldBack": [],
        })

    def test_stuck_keeps_its_open_tasks_and_leftovers(self) -> None:
        rows = [self.full("X-01", status="in-progress"),
                self.full("X-02", priority=20, needsUserDecision=True),
                self.full("X-03", priority=30, status="blocked")]
        self.assertEqual(graph.compute_wave(rows), {
            "state": "stuck", "phase": None, "ids": [], "open": ["X-01", "X-02", "X-03"],
            "overlaps": [], "leftovers": ["X-01"], "heldBack": [],
        })

    def test_a_task_sharing_a_file_with_blocked_or_running_work_is_held_back(self) -> None:
        rows = [self.full("X-01", status="blocked", files=["a.py"]),
                self.full("X-02", priority=20, status="in-progress", files=["b.py", "c.py"]),
                self.full("X-03", priority=30, files=["a.py", "b.py", "free.py"]),
                self.full("X-04", priority=40, files=["c.py"]),
                self.full("X-05", priority=50, files=["free.py"])]
        wave = graph.compute_wave(rows)
        self.assertEqual((wave["state"], wave["phase"], wave["ids"]), ("ready", 1, ["X-05"]))
        self.assertEqual(wave["heldBack"], [{"id": "X-03", "by": "X-01", "path": "a.py"},
                                            {"id": "X-03", "by": "X-02", "path": "b.py"},
                                            {"id": "X-04", "by": "X-02", "path": "c.py"}])

    def test_finished_work_and_other_todo_tasks_hold_nothing_back(self) -> None:
        rows = [self.full("X-01", status="done", commit="abc", files=["a.py"]),
                self.full("X-02", priority=20, status="deferred", files=["a.py"]),
                self.full("X-03", priority=30, files=["a.py"]),
                self.full("X-04", priority=40, files=["a.py"])]
        wave = graph.compute_wave(rows)
        self.assertEqual((wave["ids"], wave["heldBack"]), (["X-03", "X-04"], []))
        self.assertEqual(wave["overlaps"], [["X-03", "X-04", "a.py"]])

    def test_a_wave_with_every_candidate_held_back_is_stuck(self) -> None:
        rows = [self.full("X-01", status="in-progress", files=["a.py"]),
                self.full("X-02", priority=20, files=["a.py"])]
        self.assertEqual(graph.compute_wave(rows), {
            "state": "stuck", "phase": None, "ids": [], "open": ["X-01", "X-02"],
            "overlaps": [], "leftovers": ["X-01"],
            "heldBack": [{"id": "X-02", "by": "X-01", "path": "a.py"}],
        })

    def test_an_unrelated_later_phase_task_is_still_offered(self) -> None:
        # A blocked task isn't a barrier: only what shares its files waits.
        rows = [self.full("X-01", phase=1, status="blocked", files=["a.py"]),
                self.full("X-02", phase=1, priority=20, files=["a.py"]),
                self.full("X-03", phase=2, priority=30, files=["b.py"])]
        wave = graph.compute_wave(rows)
        self.assertEqual((wave["state"], wave["phase"], wave["ids"]), ("ready", 2, ["X-03"]))
        self.assertEqual(wave["heldBack"], [{"id": "X-02", "by": "X-01", "path": "a.py"}])

    def test_a_later_phase_task_is_held_by_an_earlier_phases_block(self) -> None:
        # The report this came from: a later task offered while one on its files was unfinished.
        rows = [self.full("X-01", phase=1, status="blocked", files=["a.py"]),
                self.full("X-02", phase=2, priority=20, files=["a.py"])]
        wave = graph.compute_wave(rows)
        self.assertEqual((wave["state"], wave["ids"]), ("stuck", []))
        self.assertEqual(wave["heldBack"], [{"id": "X-02", "by": "X-01", "path": "a.py"}])


class ValidateTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()

    def assert_fails_with(self, rows: list[dict], *messages: str) -> str:
        self.write_queue(rows)
        code, out, err = self.ws("validate", "-w", "alpha")
        self.assertEqual(code, 1, out + err)
        self.assertIn("FAIL:", out)
        for message in messages:
            self.assertIn(message, out)
        return out

    def assert_ok_with_warnings(self, rows: list[dict], *messages: str) -> str:
        self.write_queue(rows)
        code, out, err = self.ws("validate", "-w", "alpha")
        self.assertEqual(code, 0, out + err)
        self.assertNotIn("FAIL", out)
        suffix = f" ({len(messages)} warning(s))" if messages else ""
        self.assertIn(f"no integrity problems{suffix}", out)
        for message in messages:
            self.assertIn(message, out)
        return out

    def open_task(self, task_id: str, priority: int, **fields) -> dict:
        fields.setdefault("status", "todo")
        return task(task_id, priority, **fields)

    def test_ok_on_a_consistent_queue(self) -> None:
        out = self.assert_ok_with_warnings([self.open_task("X-01", 10),
                                            self.open_task("X-02", 20, blockedBy=["X-01"])])
        self.assertNotIn("warning", out)

    def test_fails_on_an_unknown_status(self) -> None:
        self.assert_fails_with([task("X-01", 10, status="finished")],
                               "X-01: status 'finished' not in")

    def test_fails_on_an_unresolved_blocked_by(self) -> None:
        self.assert_fails_with([self.open_task("X-01", 10, blockedBy=["X-09"])],
                               "X-01: blockedBy references unknown id 'X-09'")

    def test_fails_on_duplicate_ids_and_priorities(self) -> None:
        self.assert_fails_with([self.open_task("X-01", 10), self.open_task("X-01", 10)],
                               "duplicate id: X-01", "duplicate priority: 10")

    def test_fails_on_a_blocked_by_cycle(self) -> None:
        self.assert_fails_with(
            [self.open_task("X-01", 10, blockedBy=["X-03"]),
             self.open_task("X-02", 20, blockedBy=["X-01"]),
             self.open_task("X-03", 30, blockedBy=["X-02"]), self.open_task("X-04", 40)],
            "blockedBy cycle: X-01 -> X-03 -> X-02 -> X-01",
        )

    def test_fails_on_a_task_blocked_by_itself(self) -> None:
        out = self.assert_fails_with([self.open_task("X-01", 10, blockedBy=["X-01"])],
                                     "X-01: blockedBy references itself")
        self.assertNotIn("cycle", out)

    def test_fails_on_a_missing_core_field(self) -> None:
        bare = self.open_task("X-02", 20)
        del bare["title"], bare["status"]
        self.assert_fails_with(
            [self.open_task("X-01", 10), bare,
             {"title": "no id", "phase": 1, "priority": 30, "status": "deferred"}],
            "X-02: missing title", "X-02: missing status", "task #3: missing id",
        )

    def test_fails_on_an_ill_typed_field(self) -> None:
        self.assert_fails_with(
            [self.open_task("X-01", 10, phase="1", blockedBy="X-02", needsUserDecision="no",
                            files=[1], startedAt=5, baseCommit=7, claimedBy=["a"], verify="test")],
            "X-01: phase must be an integer, got '1'",
            "X-01: blockedBy must be a list of strings, got 'X-02'",
            "X-01: needsUserDecision must be a boolean, got 'no'",
            "X-01: files must be a list of strings, got [1]",
            "X-01: startedAt must be a string or null, got 5",
            "X-01: baseCommit must be a string or null, got 7",
            "X-01: claimedBy must be a string or null, got ['a']",
            "X-01: verify must be a list of strings, got 'test'",
        )

    def test_fails_on_a_bad_enum_value(self) -> None:
        self.assert_fails_with(
            [self.open_task("X-01", 10, mode="fg", requires=["gpu"], releaseImpact="huge")],
            "X-01: mode 'fg' not in ['background', 'foreground']",
            "X-01: requires 'gpu' not in",
            "X-01: releaseImpact 'huge' not in ['none', 'patch', 'minor', 'major']",
        )

    def test_fails_on_a_done_task_without_a_commit(self) -> None:
        self.assert_fails_with([task("X-01", 10, status="done", commit=None)],
                               "X-01: done without a commit")

    def test_release_impact_is_required_only_on_a_full_workstream(self) -> None:
        for tier in ("lite", "standard"):
            errors, _ = tasks.validate_tasks([self.open_task("X-01", 10, releaseImpact=None)],
                                             self.root, self.project().config, tier)
            self.assertEqual(errors, [], tier)
        for status in tasks.OPEN_STATUSES:
            with self.subTest(status=status):
                errors, _ = tasks.validate_tasks(
                    [self.open_task("X-01", 10, status=status, releaseImpact=None)],
                    self.root, self.project().config, "full")
                self.assertEqual(errors, ["X-01: open task has no releaseImpact"])

    def test_fails_on_an_open_task_with_a_missing_docs_path(self) -> None:
        (self.root / "docs").mkdir()
        (self.root / "docs" / "real.md").write_text("x")
        out = self.assert_fails_with(
            [self.open_task("X-01", 10, docs=["docs/real.md", "docs/gone.md"])],
            "X-01: docs path 'docs/gone.md' does not exist",
        )
        self.assertNotIn("real.md", out)

    def test_fails_on_a_browser_requirement_with_mode_background(self) -> None:
        self.assert_fails_with(
            [self.open_task("X-01", 10, mode="background", requires=["browser", "external-network"])],
            "X-01: requires ['browser'] but mode is 'background'; it must be 'foreground'",
        )
        self.assert_ok_with_warnings(
            [self.open_task("X-01", 10, mode="foreground", requires=["browser"]),
             self.open_task("X-02", 20, mode="background", requires=["external-network"])],
        )

    def test_open_task_rules_skip_done_and_deferred_tasks(self) -> None:
        self.assert_ok_with_warnings([
            task("X-01", 10, status="done", commit="abc1234", docs=["gone.md"], files=["gone.py"],
                 requires=["browser"], mode="background", verify=["nope"]),
            task("X-02", 20, status="deferred", docs=["gone.md"], files=["gone.py"]),
        ])

    def test_warns_but_passes_on_a_missing_files_path(self) -> None:
        (self.root / "here.py").write_text("x")
        self.assert_ok_with_warnings(
            [self.open_task("X-01", 10, files=["here.py", "new.py"])],
            "X-01: files path 'new.py' does not exist (yet)",
        )

    def test_warns_but_passes_on_a_files_overlap_even_across_phases(self) -> None:
        for name in ("shared.py", "other.py"):
            (self.root / name).write_text("x")
        out = self.assert_ok_with_warnings(
            [self.open_task("X-01", 10, phase=2, files=["shared.py"]),
             self.open_task("X-02", 20, phase=2, files=["shared.py", "other.py"]),
             # X-03 waits on X-02, so never runs beside it; a wave can reach X-04 past a phase.
             self.open_task("X-03", 30, phase=2, files=["other.py"], blockedBy=["X-02"]),
             self.open_task("X-04", 40, phase=3, files=["shared.py"])],
            "X-01 and X-02 both list 'shared.py' in files",
            "X-01 and X-04 both list 'shared.py' in files",
            "X-02 and X-04 both list 'shared.py' in files",
        )
        self.assertNotIn("X-03", out)

    def test_validate_tasks_returns_errors_and_warnings(self) -> None:
        errors, warnings = tasks.validate_tasks(
            [self.open_task("X-01", 10, files=["nope.py"]), task("X-02", 20, status="done")],
            self.root, Config(),
        )
        self.assertEqual(errors, ["X-02: done without a commit"])
        self.assertEqual(warnings, ["X-01: files path 'nope.py' does not exist (yet)"])

    # --- verify keys and adequacy ---------------------------------------------------------

    def test_fails_on_an_unknown_verify_key_but_takes_a_raw_command(self) -> None:
        self.set_commands(test="make test")
        self.assert_ok_with_warnings([self.open_task("X-01", 10, verify=["test", "python3 -m x"])])
        self.assert_fails_with([self.open_task("X-01", 10, verify=["lint"])],
                               "X-01: verify key 'lint' is not in [commands]")

    def test_a_kind_must_verify_with_what_the_project_requires(self) -> None:
        self.set_commands(compile="make build", test="make test")
        self.edit_config('[adequacy]\n', '[adequacy]\nbehaviour = ["compile", "test"]\n')
        self.assert_fails_with(
            [self.open_task("X-01", 10, kind="behaviour", verify=["test"])],
            "X-01: kind 'behaviour' must verify with compile",
        )
        self.assert_ok_with_warnings(
            [self.open_task("X-01", 10, kind="behaviour", verify=["compile", "test"]),
             self.open_task("X-02", 20, kind="docs", verify=[])],
        )

    def test_adequacy_cannot_demand_a_command_the_project_lacks(self) -> None:
        config = Config(commands={"test": "make test"},
                        adequacy={"behaviour": ["compile", "test"]})
        errors, _ = tasks.validate_tasks(
            [self.open_task("X-01", 10, kind="behaviour", verify=["test"])], self.root, config)
        self.assertEqual(errors, [])

    # --- a verify prefix that stops short --------------------------------------------------

    def env_warnings(self, *verify: str, **fields) -> list[str]:
        config = Config(commands={"test": "A=1 cargo test && make lint"})
        _, warnings = tasks.validate_tasks(
            [self.open_task("X-01", 10, verify=list(verify), **fields)], self.root, config)
        return warnings

    def test_warns_on_a_raw_verify_whose_prefix_stops_at_the_first_command(self) -> None:
        self.assert_ok_with_warnings(
            [self.open_task("X-01", 10, verify=["A=1 cargo test && make lint"])],
            "X-01: verify 'A=1 cargo test && make lint' sets A for its first command only",
        )

    def test_warns_on_a_commands_key_whose_prefix_stops_at_the_first_command(self) -> None:
        self.set_commands(test="A=1 cargo test && make lint")
        self.assert_ok_with_warnings(
            [self.open_task("X-01", 10, verify=["test"])],
            "X-01: verify 'test' sets A for its first command only",
        )

    def test_the_prefix_warning_covers_each_separator_and_every_name(self) -> None:
        for command in ("A=1 a && b", "A=1 a || b", "A=1 a ; b", "A=1 a; b", "A=1 a | b",
                        'A="x y" a && b', "A= a && b"):
            with self.subTest(command=command):
                self.assertEqual(len(self.env_warnings(command)), 1)
                self.assertIn(" sets A for ", self.env_warnings(command)[0])
        self.assertIn(" sets A, B for ", self.env_warnings("A=1 B=2 a && b")[0])

    def test_no_prefix_warning_where_the_variable_reaches_everything(self) -> None:
        for command in ("A=1 cargo test", "export A=1 && b", "A=1 && b c", "A=1; b c",
                        "A=1 B=2 && c d", "a b && c d", "make A=1 && b",
                        "A=1 sh -c 'a && b'", 'A=1 a "b; c"', r"A=1 find . -exec rm {} \;",
                        "A=1 a 2>&1"):
            with self.subTest(command=command):
                self.assertEqual(self.env_warnings(command), [])

    def test_the_prefix_warning_names_both_fixes_the_entry_and_the_variable(self) -> None:
        warnings = self.env_warnings("A=1 a && b")
        self.assertEqual(len(warnings), 1)
        self.assertIn("verify 'A=1 a && b' sets A for its first command only", warnings[0])
        self.assertIn("export it", warnings[0])
        self.assertIn("separate verify entries that each set it", warnings[0])

    def test_no_prefix_warning_on_the_split_form(self) -> None:
        self.assertEqual(self.env_warnings("A=1 a", "A=1 b"), [])

    def test_no_prefix_warning_on_a_finished_task(self) -> None:
        for status in ("done", "deferred"):
            with self.subTest(status=status):
                self.assertEqual(
                    self.env_warnings("A=1 cargo test && make lint", status=status, commit="abc1234"),
                    [])

    def test_acceptance_takes_strings_and_typed_items(self) -> None:
        self.assert_ok_with_warnings([self.open_task(
            "X-01", 10, acceptance=["plain", {"text": "looks right", "kind": "manual"}])])
        self.assert_fails_with(
            [self.open_task("X-01", 10, acceptance=[{"text": "x", "kind": "vibes"}])],
            "X-01: acceptance must be a list of strings or {text, kind} objects",
        )


class TypedFieldTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()

    def add(self, *extra: str) -> tuple[int, str, str]:
        return self.ws("add", "-w", "alpha", "--phase", "1", "--title", "t", *extra)

    def test_seed_fills_typed_defaults(self) -> None:
        self.seed_ok([task("X-01", 10)])
        t = self.by_id("X-01")
        self.assertEqual((t["mode"], t["requires"], t["releaseImpact"]), ("background", [], None))

    def test_seed_derives_foreground_from_requires(self) -> None:
        self.seed_ok([task("X-01", 10, requires=["live-server"], releaseImpact="minor"),
                      task("X-02", 20, requires=["external-network"])])
        self.assertEqual(self.by_id("X-01")["mode"], "foreground")
        self.assertEqual(self.by_id("X-02")["mode"], "background")

    def test_seed_rejects_bad_enums_and_a_contradicted_mode(self) -> None:
        code, _, err = self.seed([task("X-01", 10, releaseImpact="huge"),
                                  task("X-02", 20, requires=["user"], mode="background")])
        self.assertEqual(code, 1)
        self.assertIn("X-01: releaseImpact 'huge' not in", err)
        self.assertIn("X-02: requires ['user'] needs mode 'foreground'", err)
        self.assertEqual(self.queue()["tasks"], [])

    def test_add_accepts_typed_fields(self) -> None:
        code, _, err = self.add("--id", "X-01", "--priority", "10", "--requires",
                                "browser, external-network", "--release-impact", "patch")
        self.assertEqual(code, 0, err)
        t = self.by_id("X-01")
        self.assertEqual((t["mode"], t["requires"], t["releaseImpact"]),
                         ("foreground", ["browser", "external-network"], "patch"))
        self.assertEqual(list(t), tasks.FIELD_ORDER)

    def test_add_rejects_an_unknown_requirement_and_a_contradicted_mode(self) -> None:
        code, _, err = self.add("--id", "X-01", "--priority", "10", "--requires", "gpu")
        self.assertEqual(code, 1, err)
        self.assertIn("X-01: requires 'gpu' not in", err)
        code, _, err = self.add("--id", "X-02", "--priority", "20", "--requires", "user",
                                "--mode", "background")
        self.assertEqual(code, 1, err)
        self.assertEqual(self.queue()["tasks"], [])

    def test_requires_values_come_from_the_config(self) -> None:
        self.append_config('[requires]\nvalues = ["gpu"]\nforeground = ["gpu"]')
        code, _, err = self.add("--id", "X-01", "--priority", "10", "--requires", "gpu")
        self.assertEqual(code, 0, err)
        self.assertEqual(self.by_id("X-01")["mode"], "foreground")

    def test_update_sets_typed_fields_and_raises_mode_for_requires(self) -> None:
        self.seed_ok([task("X-01", 10)])
        self.ok("update", "-w", "alpha", "X-01", "--release-impact", "minor",
                "--requires", "live-server,browser")
        t = self.by_id("X-01")
        self.assertEqual((t["mode"], t["requires"], t["releaseImpact"]),
                         ("foreground", ["live-server", "browser"], "minor"))
        # Dropping the requirement never lowers the mode: foreground may have other reasons.
        self.ok("update", "-w", "alpha", "X-01", "--requires", "")
        self.assertEqual(self.by_id("X-01")["mode"], "foreground")
        self.fails("update", "-w", "alpha", "X-01", "--requires", "user", "--mode", "background")
        self.assertEqual(self.by_id("X-01")["requires"], [])

    def test_an_older_schema_is_refused_not_guessed_at(self) -> None:
        path = self.ws_dir / "alpha" / "tasks_list.json"
        path.write_text(json.dumps({"schemaVersion": 2, "tasks": []}))
        self.assertIn("schemaVersion 2 is not 3", self.fails("next", "-w", "alpha"))
        self.assertIn("schemaVersion 2 is not 3", self.fails("validate", "-w", "alpha"))

    def test_a_queue_from_before_blocked_reason_still_loads_and_matches_the_schema(self) -> None:
        path = self.ws_dir / "alpha" / "tasks_list.json"
        old = task("X-09", 90, status="blocked", notes="old reason")
        old.pop("blockedReason", None)
        queue = {"schemaVersion": 3, "tasks": [old]}
        path.write_text(json.dumps(queue))
        self.assertNotIn("blockedReason", json.loads(path.read_text())["tasks"][0])
        self.assertEqual(problems(queue, load_schema("tasks"), load_schema("tasks")), [])
        self.ok("validate", "-w", "alpha")
        self.ok("update", "-w", "alpha", "X-09", "--status", "blocked")
        written = self.by_id("X-09")
        self.assertIsNone(written["blockedReason"])
        self.assertEqual(written["notes"], "old reason")
        self.assertEqual(problems(self.queue(), load_schema("tasks"), load_schema("tasks")), [])

    def test_broken_json_is_an_error_not_a_traceback(self) -> None:
        (self.ws_dir / "alpha" / "tasks_list.json").write_text("{broken")
        self.assertIn("not valid JSON", self.fails("next", "-w", "alpha"))
        self.assertIn("not valid JSON", self.fails("validate", "-w", "alpha"))


class MalformedQueueTests(WsTestCase):
    """Read commands refuse a queue the graph can't be trusted on, and point at `validate`."""

    def setUp(self) -> None:
        super().setUp()
        self.new_ws()

    def test_a_malformed_task_is_an_error_not_a_traceback(self) -> None:
        cases = [
            {"title": "no id", "phase": 1, "priority": 10, "status": "todo"},
            task("X-01", 10, status="todo", phase="1"),
            task("X-01", "10", status="todo"),
            task("X-01", 10, status=7),
            # A string here would otherwise be read one character at a time.
            task("X-01", 10, status="todo", blockedBy="X-02"),
        ]
        for bad in cases:
            with self.subTest(bad=bad):
                path = self.ws_dir / "alpha" / "tasks_list.json"
                path.write_text(json.dumps({**self.queue(), "tasks": [bad]}))
                for argv in (["next"], ["wave"], ["status"], ["tasks"], ["graph"]):
                    self.assertIn("`ws validate` says which", self.fails(*argv, "-w", "alpha"))
                self.fails("validate", "-w", "alpha")

    def test_a_task_that_is_not_an_object_is_an_error(self) -> None:
        path = self.ws_dir / "alpha" / "tasks_list.json"
        path.write_text(json.dumps({**self.queue(), "tasks": ["X-01"]}))
        for argv in (["next", "-w", "alpha"], ["validate", "-w", "alpha"], ["sync"]):
            with self.subTest(argv=argv):
                code, out, err = self.ws(*argv)
                self.assertNotIn("Traceback", out + err)


CLAIM_FIELDS = ("status", "startedAt", "baseCommit", "claimedBy")


class ClaimTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.seed_ok([
            task("X-01", 10),
            task("X-02", 20),
            task("X-03", 30, blockedBy=["X-01"]),
            task("X-04", 40, needsUserDecision=True),
            task("X-05", 50, status="done", commit="abc1234"),
        ])
        self.file = self.ws_dir / "alpha" / "tasks_list.json"

    def claim(self, *ids: str, by: str | None = "batch-1") -> tuple[int, str, str]:
        extra = ("--by", by) if by else ()
        return self.ws("claim", "-w", "alpha", "--base", "cafe123", *extra, *ids)

    def claim_state(self, task_id: str) -> tuple:
        t = self.by_id(task_id)
        return tuple(t[f] for f in CLAIM_FIELDS)

    def test_claims_every_actionable_id_and_stamps_all_four_fields(self) -> None:
        code, out, err = self.claim("X-01", "X-02")
        self.assertEqual(code, 0, err)
        self.assertIn("claimed X-01, X-02 at cafe123 for batch-1", out)
        for task_id in ("X-01", "X-02"):
            status, started, base, by = self.claim_state(task_id)
            self.assertEqual((status, base, by), ("in-progress", "cafe123", "batch-1"))
            self.assertRegex(started, r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertEqual(self.by_id("X-01")["startedAt"], self.by_id("X-02")["startedAt"])
        self.assertEqual(list(self.by_id("X-01")), tasks.FIELD_ORDER)

    def test_gives_a_branch_from_the_configured_pattern_and_keeps_a_named_one(self) -> None:
        self.claim("X-01")
        self.assertEqual(self.by_id("X-01")["branch"], "task/x-01")
        self.ok("add", "-w", "alpha", "--id", "X-06", "--phase", "1", "--priority", "60",
                "--title", "t", "--branch", "feature/mine")
        self.claim("X-06")
        self.assertEqual(self.by_id("X-06")["branch"], "feature/mine")

    def test_base_defaults_to_head(self) -> None:
        head = self.git("rev-parse", "HEAD").strip()
        self.ok("claim", "-w", "alpha", "X-01")
        self.assertEqual(self.by_id("X-01")["baseCommit"], head)

    def test_without_by_leaves_claimed_by_null(self) -> None:
        code, _, err = self.claim("X-01", by=None)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.claim_state("X-01")[2:], ("cafe123", None))

    def test_one_non_actionable_id_claims_nothing(self) -> None:
        before = self.file.read_text()
        for bad, reason in [("X-03", "waits on X-01"), ("X-04", "needsUserDecision"),
                            ("X-05", "status is done"), ("X-99", "no such task")]:
            with self.subTest(bad=bad):
                code, out, err = self.claim("X-01", "X-02", bad)
                self.assertNotEqual(code, 0, out)
                self.assertIn("claimed nothing", err)
                self.assertIn(f"{bad}: ", err)
                self.assertIn(reason, err)
                self.assertEqual(self.file.read_text(), before)

    def test_an_already_claimed_task_cannot_be_claimed_again(self) -> None:
        self.claim("X-01")
        code, _, err = self.claim("X-01", by="batch-2")
        self.assertEqual(code, 1, err)
        self.assertIn("X-01: not actionable (status is in-progress)", err)
        self.assertEqual(self.by_id("X-01")["claimedBy"], "batch-1")

    def test_rejects_an_empty_base(self) -> None:
        self.fails("claim", "-w", "alpha", "--base", " ", "X-01")
        self.assertEqual(self.by_id("X-01")["status"], "todo")

    def test_a_claimed_queue_still_validates(self) -> None:
        self.claim("X-01", "X-02")
        self.ok("sync")
        self.ok("validate", "-w", "alpha")

    def test_unclaim_restores_todo_and_clears_the_claim(self) -> None:
        self.claim("X-01", "X-02")
        self.ok("unclaim", "-w", "alpha", "X-01", "X-02")
        for task_id in ("X-01", "X-02"):
            self.assertEqual(self.claim_state(task_id), ("todo", None, None, None))
        # Requeued, so actionable again.
        code, _, err = self.claim("X-01", "X-02", by="batch-2")
        self.assertEqual(code, 0, err)

    def test_unclaim_takes_a_blocked_task_too(self) -> None:
        self.claim("X-01")
        self.ok("update", "-w", "alpha", "X-01", "--status", "blocked")
        self.ok("unclaim", "-w", "alpha", "X-01")
        self.assertEqual(self.claim_state("X-01"), ("todo", None, None, None))

    def test_unclaim_is_all_or_nothing(self) -> None:
        self.claim("X-01")
        before = self.file.read_text()
        for bad in ("X-02", "X-05", "X-99"):
            with self.subTest(bad=bad):
                self.assertIn("unclaimed nothing", self.fails("unclaim", "-w", "alpha", "X-01", bad))
                self.assertEqual(self.file.read_text(), before)


class ResetTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.seed_ok([task("X-01", 10, status="done", commit="abc", notes="kept"),
                      task("X-02", 20, status="done", commit="def", blockedBy=["X-01"]),
                      task("X-03", 30, status="in-progress", blockedBy=["X-02"]),
                      task("X-04", 40)])

    def test_a_dry_run_changes_nothing(self) -> None:
        before = self.queue()
        out = self.ok("reset", "-w", "alpha", "--dry-run")
        self.assertIn("X-01, X-02, X-03", out)
        self.assertNotIn("X-04", out)
        self.assertEqual(self.queue(), before)

    def test_clears_run_time_state_and_keeps_the_definition(self) -> None:
        self.ok("reset", "-w", "alpha", "X-01", "--yes")
        t = self.by_id("X-01")
        self.assertEqual((t["status"], t["commit"], t["completedAt"]), ("todo", None, None))
        self.assertEqual((t["title"], t["notes"]), ("title of X-01", "kept"))
        self.assertEqual(self.by_id("X-02")["status"], "done")

    def test_cascade_takes_every_dependent(self) -> None:
        self.ok("reset", "-w", "alpha", "X-02", "--cascade", "--yes")
        self.assertEqual(self.by_id("X-01")["status"], "done")
        self.assertEqual(self.by_id("X-02")["status"], "todo")
        self.assertEqual(self.by_id("X-03")["status"], "todo")

    def test_without_a_terminal_or_yes_it_refuses(self) -> None:
        before = self.queue()
        self.assertIn("refused", self.fails("reset", "-w", "alpha"))
        self.assertEqual(self.queue(), before)

    def test_says_when_there_is_nothing_to_do(self) -> None:
        self.assertIn("nothing to reset", self.ok("reset", "-w", "alpha", "X-04", "--yes"))


if __name__ == "__main__":
    unittest.main()
