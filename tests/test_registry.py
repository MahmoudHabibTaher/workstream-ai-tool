"""The registry through the CLI: new, sync, validate, set-status, reconcile, close."""

from __future__ import annotations

import json
import unittest
from unittest import mock

from tests.helpers import WsTestCase, task
from workstream import fsutil, registry, tasks


class NewTests(WsTestCase):
    def new(self, ws_id: str = "alpha", prefix: str = "AL", *extra: str) -> tuple[int, str, str]:
        return self.ws("new", ws_id, "--title", f"{ws_id} title", "--summary", "s",
                       "--prefix", prefix, "--base", "abc1234", *extra)

    def test_scaffolds_the_folder_and_registers_it_as_planned(self) -> None:
        code, _, err = self.new()
        self.assertEqual(code, 0, err)
        folder = self.ws_dir / "alpha"
        for name in registry.REQUIRED_FILES["standard"]:
            self.assertTrue((folder / name).exists(), name)
        plan = (folder / "PLAN.md").read_text()
        self.assertIn("# alpha title", plan)
        self.assertIn(f"Written {fsutil.today()} against `main` at `abc1234`", plan)
        self.assertNotIn("{{TITLE}}", plan)
        queue = self.queue()
        self.assertEqual((queue["source"], queue["tasks"]), ("workstreams/alpha/PLAN.md", []))
        self.assertEqual((queue["tier"], queue["protocolVersion"]),
                         ("standard", tasks.PROTOCOL_VERSION))
        ws = self.entry()
        self.assertEqual((ws["status"], ws["taskPrefix"], ws["baseCommit"], ws["path"]),
                         ("planned", "AL", "abc1234", "workstreams/alpha"))
        self.assertEqual(ws["progress"]["total"], 0)

    def test_without_base_reads_the_integration_branch(self) -> None:
        expected = self.git("rev-parse", "--short", "main").strip()
        self.ok("new", "alpha", "--title", "t", "--summary", "s")
        self.assertEqual(self.entry()["baseCommit"], expected)

    def test_base_is_empty_when_the_branch_does_not_resolve(self) -> None:
        self.edit_config('integration = "main"', 'integration = "trunk"')
        self.ok("new", "alpha", "--title", "t", "--summary", "s")
        self.assertEqual(self.entry()["baseCommit"], "")

    def test_the_prefix_is_optional(self) -> None:
        self.ok("new", "alpha", "--title", "t", "--summary", "s", "--base", "abc")
        self.assertIsNone(self.entry()["taskPrefix"])

    def test_a_lite_workstream_is_a_plan_and_a_queue(self) -> None:
        self.ok("new", "alpha", "--title", "t", "--summary", "s", "--tier", "lite")
        self.assertEqual(sorted(p.name for p in (self.ws_dir / "alpha").iterdir()),
                         ["PLAN.md", "tasks_list.json"])
        self.assertEqual(self.entry()["tier"], "lite")

    def test_under_places_it_inside_a_module(self) -> None:
        self.ok("new", "alpha", "--title", "t", "--summary", "s", "--under", "lib/core")
        self.assertEqual(self.entry()["path"], "lib/core/workstreams/alpha")
        self.assertTrue((self.root / "lib/core/workstreams/alpha/PLAN.md").exists())

    def test_rejects_bad_ids_prefixes_and_dependencies(self) -> None:
        self.new()
        cases = [
            (("Bad-Id", "BD"), "lower-case"),
            (("beta", "bd"), "upper-case"),
            (("alpha", "BE"), "already registered"),
            (("beta", "A"), "overlaps the task prefix of ['alpha']"),
            (("beta", "ALX"), "overlaps the task prefix of ['alpha']"),
            (("beta", "BE", "--depends-on", "nope"), "no workstream with id 'nope'"),
        ]
        for argv, message in cases:
            with self.subTest(argv=argv):
                code, _, err = self.new(*argv)
                self.assertEqual(code, 1)
                self.assertIn(message, err)
        self.assertFalse((self.ws_dir / "beta").exists())

    def test_rejects_an_existing_folder(self) -> None:
        (self.ws_dir / "beta").mkdir()
        code, _, err = self.new("beta", "BE")
        self.assertEqual(code, 1)
        self.assertIn("workstreams/beta already exists", err)


class SyncTests(WsTestCase):
    def seed_statuses(self, *statuses: str) -> None:
        self.write_queue([
            task(f"AL-{n + 1:02d}", (n + 1) * 10, status=s,
                 **({"commit": "abc"} if s == "done" else {}))
            for n, s in enumerate(statuses)
        ])

    def setUp(self) -> None:
        super().setUp()
        self.new_ws("alpha", "AL")

    def test_a_started_task_moves_planned_to_active_and_counts_progress(self) -> None:
        self.seed_statuses("done", "in-progress", "todo")
        self.assertIn("alpha: planned -> active", self.ok("sync"))
        ws = self.entry()
        self.assertEqual(ws["status"], "active")
        self.assertEqual(ws["startedAt"], fsutil.today())
        self.assertEqual(ws["progress"], {"total": 3, "todo": 1, "in-progress": 1, "blocked": 0,
                                          "done": 1, "deferred": 0})

    def test_a_claim_moves_planned_to_active(self) -> None:
        self.seed_statuses("todo", "todo")
        self.ok("sync")
        self.assertEqual(self.entry()["status"], "planned")
        self.ok("claim", "-w", "alpha", "--base", "abc1234", "--by", "batch-1", "AL-01", "AL-02")
        self.assertIn("alpha: planned -> active", self.ok("sync"))
        self.assertEqual(self.entry()["status"], "active")
        self.assertEqual(self.entry()["progress"]["in-progress"], 2)

    def test_an_empty_queue_suggests_closing_but_never_closes(self) -> None:
        self.seed_statuses("done", "deferred")
        self.assertIn("alpha: queue is empty", self.ok("sync"))
        self.assertEqual(self.entry()["status"], "active")


class ValidateTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws("alpha", "AL")

    def test_ok_on_a_fresh_workstream(self) -> None:
        self.assertIn("OK: 1 workstream(s)", self.ok("validate"))

    def test_a_new_workstream_fails_until_its_templates_are_filled(self) -> None:
        self.ok("new", "beta", "--title", "t", "--summary", "s", "--base", "abc")
        out = self.fails("validate")
        self.assertIn("beta: PLAN.md still has the {{CONTEXT}} placeholder", out)
        self.assertIn("beta: session_handoff.md still has the {{NEXT}} placeholder", out)

    def test_fails_on_an_unregistered_workstream(self) -> None:
        stray = self.ws_dir / "stray"
        stray.mkdir()
        (stray / "tasks_list.json").write_text(json.dumps({"tasks": []}))
        self.assertIn("unregistered workstream: workstreams/stray", self.fails("validate"))

    def test_a_folder_with_no_queue_is_not_a_workstream(self) -> None:
        (self.ws_dir / "tools").mkdir()
        self.ok("validate")

    def test_fails_on_a_missing_required_file(self) -> None:
        (self.ws_dir / "alpha" / "DECISIONS.md").unlink()
        self.assertIn("alpha: DECISIONS.md missing", self.fails("validate"))

    def test_fails_on_a_missing_folder(self) -> None:
        import shutil

        shutil.rmtree(self.ws_dir / "alpha")
        self.assertIn("alpha: folder workstreams/alpha missing", self.fails("validate"))

    def test_fails_on_task_prefix_and_blocked_by_problems(self) -> None:
        self.write_queue([task("ZZ-01", 10, status="todo"),
                          task("AL-02", 20, status="todo", blockedBy=["AL-99"])])
        out = self.fails("validate")
        self.assertIn("alpha: task ZZ-01 lacks prefix 'AL'", out)
        self.assertIn("alpha: AL-02: blockedBy references unknown id 'AL-99'", out)

    def test_fails_on_overlapping_prefixes_and_unknown_dependencies(self) -> None:
        self.new_ws("beta", "BE")
        data = json.loads(self.registry.read_text())
        data["workstreams"][1]["taskPrefix"] = "ALB"
        data["workstreams"][1]["dependsOn"] = ["gamma"]
        self.registry.write_text(json.dumps(data))
        out = self.fails("validate")
        self.assertIn("task prefix 'AL' (alpha) overlaps 'ALB' (beta)", out)
        self.assertIn("beta: dependsOn unknown workstream 'gamma'", out)

    def test_runs_the_shared_task_validator_against_the_repo_root(self) -> None:
        with mock.patch.object(tasks, "validate_tasks", wraps=tasks.validate_tasks) as shared:
            self.ok("validate")
        shared.assert_called_once()
        self.assertEqual(shared.call_args.args[1], self.root)

    def test_fails_on_task_rules_only_the_shared_validator_knows(self) -> None:
        self.write_queue([
            task("AL-01", 10, status="todo", blockedBy=["AL-02"]),
            task("AL-02", 20, status="todo", blockedBy=["AL-01"], docs=["docs/gone.md"]),
            task("AL-03", 30, status="done"),
        ])
        out = self.fails("validate")
        self.assertIn("alpha: blockedBy cycle: AL-01 -> AL-02 -> AL-01", out)
        self.assertIn("alpha: AL-02: docs path 'docs/gone.md' does not exist", out)
        self.assertIn("alpha: AL-03: done without a commit", out)

    def test_docs_paths_resolve_against_the_repo_root(self) -> None:
        (self.root / "docs").mkdir()
        (self.root / "docs" / "here.md").write_text("x")
        self.write_queue([task("AL-01", 10, status="todo", docs=["docs/here.md"])])
        self.ok("validate")

    def test_warnings_print_but_exit_zero(self) -> None:
        self.write_queue([task("AL-01", 10, status="todo", files=["src/new.rs"]),
                          task("AL-02", 20, status="todo", files=["src/new.rs"])])
        out = self.ok("validate")
        self.assertIn("warnings:", out)
        self.assertIn("alpha: AL-01: files path 'src/new.rs' does not exist (yet)", out)
        self.assertIn("alpha: AL-01 and AL-02 both list 'src/new.rs' in files", out)
        self.assertIn("OK: 1 workstream(s), no integrity problems (3 warning(s))", out)

    def test_a_lite_workstream_needs_only_its_plan_and_queue(self) -> None:
        self.ok("new", "beta", "--title", "t", "--summary", "s", "--tier", "lite", "--base", "abc")
        (self.ws_dir / "beta" / "PLAN.md").write_text("# plan\n")
        self.ok("validate")

    def test_a_status_past_planned_needs_tasks(self) -> None:
        self.ok("set-status", "-w", "alpha", "active")
        self.assertIn("alpha: status 'active' but tasks_list.json is empty",
                      self.fails("validate"))


class SetStatusTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws("alpha", "AL")

    def test_abandoning_stamps_completed_at_and_reopening_clears_it(self) -> None:
        self.ok("set-status", "-w", "alpha", "abandoned", "--notes", "dropped")
        ws = self.entry()
        self.assertEqual((ws["status"], ws["completedAt"], ws["notes"]),
                         ("abandoned", fsutil.today(), "dropped"))
        self.ok("set-status", "-w", "alpha", "active")
        ws = self.entry()
        self.assertEqual((ws["status"], ws["completedAt"]), ("active", None))
        self.assertEqual(ws["startedAt"], fsutil.today())

    def test_abandoning_needs_a_reason(self) -> None:
        self.assertIn("needs --notes", self.fails("set-status", "-w", "alpha", "abandoned"))
        self.assertEqual(self.entry()["status"], "planned")

    def test_done_is_not_a_status_you_can_set(self) -> None:
        code, _, err = self.ws("set-status", "-w", "alpha", "done")
        self.assertEqual(code, 2)
        self.assertIn("invalid choice", err)


class ReconcileTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws("alpha", "AL")

    def test_nothing_to_report_on_a_consistent_tree(self) -> None:
        self.assertIn("no differences", self.ok("reconcile"))

    def test_registers_an_unknown_queue_wherever_it_sits(self) -> None:
        folder = self.root / "lib" / "workstreams" / "beta"
        folder.mkdir(parents=True)
        tasks.save(folder / "tasks_list.json", tasks.new_envelope("x"))
        self.assertIn("registered beta", self.ok("reconcile"))
        self.assertEqual(self.entry("beta")["path"], "lib/workstreams/beta")
        self.assertIn("no differences", self.ok("reconcile"))

    def test_reports_but_never_repairs_a_status_that_disagrees(self) -> None:
        self.write_queue([task("AL-01", 10, status="in-progress"),
                          task("AL-02", 20, status="done", commit="abc")])
        before = self.registry.read_text()
        out = self.fails("reconcile")
        self.assertIn("alpha: registry says planned but a task has started", out)
        self.assertIn("alpha: recorded progress differs from the queue", out)
        self.assertEqual(self.registry.read_text(), before)

    def test_reports_done_with_open_tasks_and_a_folder_gone(self) -> None:
        self.write_queue([task("AL-01", 10, status="todo")])
        data = json.loads(self.registry.read_text())
        data["workstreams"][0]["status"] = "done"
        self.registry.write_text(json.dumps(data))
        self.assertIn("registry says done but 1 task(s) are open", self.fails("reconcile"))
        import shutil

        shutil.rmtree(self.ws_dir / "alpha")
        self.assertIn("alpha: folder workstreams/alpha is gone", self.fails("reconcile"))

    def test_a_name_taken_at_another_path_is_reported_not_registered(self) -> None:
        folder = self.root / "lib" / "workstreams" / "alpha"
        folder.mkdir(parents=True)
        tasks.save(folder / "tasks_list.json", tasks.new_envelope("x"))
        self.assertIn("name 'alpha' is already registered", self.fails("reconcile"))
        self.assertEqual(len(json.loads(self.registry.read_text())["workstreams"]), 1)


class UntrustedRegistryTests(WsTestCase):
    """The registry is a file in the repo, so it may have come from someone else's commit."""

    def setUp(self) -> None:
        super().setUp()
        self.new_ws("alpha", "AL")
        self.write_queue([task("AL-01", 10, status="done", commit="abc")])

    def set_path(self, path: str) -> None:
        data = json.loads(self.registry.read_text())
        data["workstreams"][0]["path"] = path
        self.registry.write_text(json.dumps(data))

    def test_purge_refuses_a_path_outside_the_repository(self) -> None:
        victim = self.root.parent / "victim"
        victim.mkdir()
        (victim / "keep.txt").write_text("precious\n")
        for path in ("../victim", str(victim), ".", "workstreams/.."):
            with self.subTest(path=path):
                self.set_path(path)
                self.assertIn("outside the repository",
                              self.fails("close", "-w", "alpha", "--purge", "--yes"))
                self.assertTrue((victim / "keep.txt").exists())
                self.assertTrue((self.root / ".git").exists())

    def test_purge_refuses_a_path_through_a_symlink_out(self) -> None:
        victim = self.root.parent / "victim"
        victim.mkdir()
        (self.root / "link").symlink_to(victim)
        self.set_path("link")
        self.assertIn("outside the repository",
                      self.fails("close", "-w", "alpha", "--purge", "--yes"))
        self.assertTrue(victim.exists())

    def test_purge_and_prune_refuse_the_folder_holding_the_registry(self) -> None:
        self.set_path("workstreams")
        (self.ws_dir / "tasks_list.json").write_text(self.queue_text())
        for flag in ("--purge", "--prune"):
            self.assertIn("holds the registry", self.fails("close", "-w", "alpha", flag, "--yes"))
            self.assertTrue(self.registry.exists())
            self.assertTrue((self.ws_dir / "tasks_list.json").exists())

    def queue_text(self) -> str:
        return (self.ws_dir / "alpha" / "tasks_list.json").read_text()

    def test_under_refuses_to_leave_the_repository(self) -> None:
        self.assertIn("outside the repository",
                      self.fails("new", "beta", "--title", "t", "--summary", "s",
                                 "--under", "../elsewhere"))
        self.assertFalse((self.root.parent / "elsewhere").exists())

    def test_a_row_with_no_id_is_an_error_not_a_traceback(self) -> None:
        data = json.loads(self.registry.read_text())
        data["workstreams"].append({"title": "no id"})
        self.registry.write_text(json.dumps(data))
        for argv in (["list"], ["validate"], ["snapshot"], ["sync"], ["status", "-w", "alpha"]):
            with self.subTest(argv=argv):
                self.assertIn("row 2 has no id", self.fails(*argv))

    def test_a_stray_queue_file_outside_a_workstreams_folder_is_ignored(self) -> None:
        fixtures = self.root / "tests" / "fixtures"
        fixtures.mkdir(parents=True)
        (fixtures / "tasks_list.json").write_text("{}")
        (self.root / "tasks_list.json").write_text("{}")
        self.ok("sync")
        self.ok("validate")
        self.assertIn("no differences", self.ok("reconcile"))


class CloseTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws("alpha", "AL")
        self.write_queue([task("AL-01", 10, status="done", commit="abc")])
        self.folder = self.ws_dir / "alpha"

    def test_refuses_open_tasks(self) -> None:
        self.write_queue([task("AL-01", 10, status="todo")])
        self.assertIn("alpha has open tasks: AL-01", self.fails("close", "-w", "alpha"))
        self.assertEqual(self.entry()["status"], "planned")

    def test_refuses_deferred_tasks_unless_told(self) -> None:
        self.write_queue([task("AL-01", 10, status="deferred")])
        self.assertIn("deferred tasks: AL-01", self.fails("close", "-w", "alpha"))
        self.ok("close", "-w", "alpha", "--allow-deferred")
        self.assertEqual(self.entry()["status"], "done")

    def test_by_default_every_file_stays_so_citations_never_go_stale(self) -> None:
        before = sorted(p.name for p in self.folder.iterdir())
        self.ok("close", "-w", "alpha")
        ws = self.entry()
        self.assertEqual((ws["status"], ws["completedAt"]), ("done", fsutil.today()))
        self.assertEqual(ws["closed"]["pruned"], False)
        self.assertEqual(ws["progress"]["done"], 1)
        self.assertEqual(sorted(p.name for p in self.folder.iterdir()), before)
        self.ok("validate")

    def test_prune_removes_the_queue_and_handoff_and_the_row_keeps_the_record(self) -> None:
        self.ok("close", "-w", "alpha", "--prune", "--yes")
        names = sorted(p.name for p in self.folder.iterdir())
        self.assertEqual(names, ["DECISIONS.md", "PLAN.md", "PROGRESS.md"])
        ws = self.entry()
        self.assertEqual(ws["closed"]["commit"], self.git("rev-parse", "HEAD").strip())
        self.assertEqual(ws["progress"]["done"], 1)
        self.ok("sync")
        self.assertEqual(self.entry()["progress"]["done"], 1)
        self.ok("validate")
        self.assertIn("no differences", self.ok("reconcile"))

    def test_purge_removes_the_folder_and_the_row_survives(self) -> None:
        self.ok("close", "-w", "alpha", "--purge", "--yes")
        self.assertFalse(self.folder.exists())
        self.assertEqual(self.entry()["status"], "done")
        self.ok("validate")
        self.assertIn("no differences", self.ok("reconcile"))
        self.assertIn("1/1", self.ok("list", "--all"))

    def test_a_destructive_close_without_a_terminal_or_yes_refuses(self) -> None:
        self.assertIn("refused", self.fails("close", "-w", "alpha", "--purge"))
        self.assertTrue(self.folder.exists())
        self.assertEqual(self.entry()["status"], "planned")

    def test_a_dry_run_writes_nothing(self) -> None:
        before = self.registry.read_text()
        self.assertIn("the whole folder", self.ok("close", "-w", "alpha", "--purge", "--dry-run"))
        self.assertEqual(self.registry.read_text(), before)
        self.assertTrue(self.folder.exists())

    def test_cannot_close_twice(self) -> None:
        self.ok("close", "-w", "alpha")
        self.assertIn("alpha is done, not open", self.fails("close", "-w", "alpha"))


if __name__ == "__main__":
    unittest.main()
