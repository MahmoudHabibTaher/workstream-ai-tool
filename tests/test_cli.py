"""What's specific to the command line: finding the project and the workstream, and output
that stays short."""

from __future__ import annotations

import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path

from tests.helpers import WsTestCase, task
from workstream.cli import main


class WorkstreamSelectionTests(WsTestCase):
    def in_dir(self, path: Path, *argv: str) -> tuple[int, str, str]:
        """Run with no --root, from path: what a person at a shell gets."""
        out, err = StringIO(), StringIO()
        previous = os.getcwd()
        os.chdir(path)
        try:
            with redirect_stdout(out), redirect_stderr(err):
                code = main(list(argv))
        finally:
            os.chdir(previous)
        return code, out.getvalue(), err.getvalue()

    def test_finds_the_project_from_any_folder_inside_it(self) -> None:
        self.new_ws("alpha")
        deep = self.root / "src" / "deep"
        deep.mkdir(parents=True)
        code, out, err = self.in_dir(deep, "list")
        self.assertEqual(code, 0, err)
        self.assertIn("alpha", out)

    def test_outside_a_project_it_says_to_run_init(self) -> None:
        with tempfile.TemporaryDirectory() as outside:
            code, _, err = self.in_dir(Path(outside), "list")
        self.assertEqual(code, 1)
        self.assertIn("run `ws init`", err)

    def test_the_only_open_workstream_needs_no_flag(self) -> None:
        self.new_ws("alpha")
        self.seed_ok([task("X-01", 10)])
        self.assertIn("alpha", self.ok("status"))

    def test_several_open_workstreams_are_refused_and_listed(self) -> None:
        self.new_ws("alpha")
        self.new_ws("beta")
        out = self.fails("status")
        self.assertIn("several open workstreams", out)
        self.assertIn("alpha, beta", out)

    def test_the_folder_you_are_in_wins_over_being_ambiguous(self) -> None:
        self.new_ws("alpha")
        self.new_ws("beta")
        code, out, err = self.in_dir(self.ws_dir / "beta", "status")
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("beta "), out)

    def test_w_wins_over_the_folder_and_works_before_or_after_the_command(self) -> None:
        self.new_ws("alpha")
        self.new_ws("beta")
        code, out, err = self.in_dir(self.ws_dir / "beta", "status", "-w", "alpha")
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("alpha "), out)
        code, out, err = self.in_dir(self.root, "-w", "alpha", "status")
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("alpha "), out)

    def test_no_open_workstream_says_how_to_make_one(self) -> None:
        self.assertIn("`ws new`", self.fails("status"))

    def test_a_workstream_in_a_module_folder_is_found_by_standing_in_it(self) -> None:
        self.ok("new", "alpha", "--title", "t", "--summary", "s", "--under", "lib")
        self.ok("new", "beta", "--title", "t", "--summary", "s")
        code, out, err = self.in_dir(self.root / "lib/workstreams/alpha", "status")
        self.assertEqual(code, 0, err)
        self.assertTrue(out.startswith("alpha "), out)


class InitTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()

    def run_init(self, *argv: str) -> tuple[int, str, str]:
        out, err = StringIO(), StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--root", str(self.root), "init", *argv])
        return code, out.getvalue(), err.getvalue()

    def test_refuses_outside_a_git_repository_unless_told(self) -> None:
        code, _, err = self.run_init()
        self.assertEqual(code, 1)
        self.assertIn("not a git repository", err)
        self.assertFalse((self.root / ".workstream").exists())
        code, out, err = self.run_init("--no-git", "--integration", "trunk")
        self.assertEqual(code, 0, err)
        self.assertIn("integration branch: trunk", out)

    def test_running_it_twice_changes_nothing(self) -> None:
        self.run_init("--no-git")
        config = (self.root / ".workstream/config.toml").read_text()
        code, out, _ = self.run_init("--no-git", "--integration", "other")
        self.assertEqual(code, 0)
        self.assertIn("already set up", out)
        self.assertEqual((self.root / ".workstream/config.toml").read_text(), config)


class OutputTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws("alpha")
        self.set_commands(test="make test")
        self.seed_ok([
            task("X-01", 10, summary="Do the thing.", files=["a.py"], verify=["test", "make it"],
                 acceptance=["works", {"text": "looks right", "kind": "manual"}]),
            task("X-02", 20, blockedBy=["X-01"]),
            task("Y-01", 30, blockedBy=["X-01"]),
        ])

    def test_show_is_short_and_resolves_verify(self) -> None:
        out = self.ok("show", "-w", "alpha", "X-01")
        self.assertIn("Do the thing.", out)
        self.assertIn("unblocks: X-02, Y-01", out)
        self.assertIn("test: make test", out)
        self.assertIn("  make it\n", out)
        self.assertIn("2. looks right (manual)", out)
        # Empty fields and null run-time state stay out of an agent's context.
        for absent in ("notes", "docs", "commit", "null", "baseCommit"):
            self.assertNotIn(absent, out)

    def test_show_is_shorter_than_the_task_as_json(self) -> None:
        text = self.ok("show", "-w", "alpha", "X-02")
        as_json = self.ok("show", "-w", "alpha", "X-02", "--json")
        self.assertEqual(json.loads(as_json)["id"], "X-02")
        self.assertLess(len(text), len(as_json) / 3)

    def test_show_takes_a_unique_prefix_and_refuses_an_ambiguous_one(self) -> None:
        self.assertIn("title of Y-01", self.ok("show", "-w", "alpha", "Y-"))
        self.assertIn("matches X-01, X-02", self.fails("show", "-w", "alpha", "X-"))
        self.assertIn("no task with id 'Z'", self.fails("show", "-w", "alpha", "Z"))

    def test_status_says_what_is_ready(self) -> None:
        out = self.ok("status", "-w", "alpha")
        self.assertIn("3 tasks  todo=3", out)
        self.assertIn("ready (phase 1): X-01", out)

    def test_status_does_not_call_running_work_stuck(self) -> None:
        self.ok("claim", "-w", "alpha", "X-01")
        out = self.ok("status", "-w", "alpha")
        self.assertIn("in progress; nothing else is ready", out)
        self.assertNotIn("stuck", out)

    def test_status_says_stuck_when_only_a_person_can_move_it(self) -> None:
        self.ok("update", "-w", "alpha", "X-01", "--status", "blocked")
        self.assertIn("stuck", self.ok("status", "-w", "alpha"))

    def test_status_after_a_prune_uses_the_recorded_counts(self) -> None:
        self.write_queue([task("X-01", 10, status="done", commit="abc")])
        self.ok("close", "-w", "alpha", "--prune", "--yes")
        self.assertIn("1/1 done; the queue was pruned", self.ok("status", "-w", "alpha"))

    def test_graph_draws_the_tree_and_marks_a_repeat(self) -> None:
        self.ok("add", "-w", "alpha", "--id", "Z-01", "--phase", "1", "--priority", "40",
                "--title", "joins", "--blocked-by", "X-02,Y-01")
        out = self.ok("graph", "-w", "alpha")
        self.assertIn("X-01 [todo]", out)
        self.assertIn("  X-02 [todo]", out)
        self.assertIn("    Z-01 [todo] joins\n", out)
        self.assertIn("    Z-01 [todo] joins (see above)", out)

    def test_graph_still_draws_a_cycle(self) -> None:
        self.write_queue([task("X-01", 10, status="todo", blockedBy=["X-02"]),
                          task("X-02", 20, status="todo", blockedBy=["X-01"])])
        out = self.ok("graph", "-w", "alpha")
        self.assertIn("X-01", out)
        self.assertIn("X-02", out)

    def test_tasks_filters_by_phase_and_status(self) -> None:
        self.ok("update", "-w", "alpha", "X-01", "--status", "blocked")
        self.assertEqual(len(self.ok("tasks", "-w", "alpha").splitlines()), 3)
        self.assertEqual(len(self.ok("tasks", "-w", "alpha", "--status", "todo").splitlines()), 2)
        self.assertIn("no matching", self.ok("tasks", "-w", "alpha", "--phase", "9"))

    def test_list_hides_closed_workstreams_until_asked(self) -> None:
        self.write_queue([task("X-01", 10, status="done", commit="abc")])
        self.ok("close", "-w", "alpha")
        self.assertIn("no matching", self.ok("list"))
        self.assertIn("alpha", self.ok("list", "--all"))
        self.assertIn("alpha", self.ok("list", "--status", "done"))

    def test_seeded_commands_never_appear_as_an_empty_verify(self) -> None:
        self.write_queue([task("X-01", 10, status="done", commit="abc", verify=["gone"])])
        self.assertIn("gone: (not in [commands])", self.ok("show", "-w", "alpha", "X-01"))


if __name__ == "__main__":
    unittest.main()
