"""The scope warning, as both `ws settle` and a worker's own check reach it."""

from __future__ import annotations

from pathlib import Path

from tests.test_settle import SettleTestCase
from workstream import evidence, gates, registry, snapshot, tasks
from workstream.project import open_project

SCOPE_GATE = "the diff stays within the task's files"
EDITED = "a different size from the original\n"


class ScopeGateTests(SettleTestCase):
    def worked(self, changes: dict, **fields) -> Path:
        """T1 finished on its branch, with a doc in the tree for `docs` to name."""
        (self.root / "guide.md").write_text("old\n")
        self.commit_all("a doc")
        self.arrange(self.t("T1", **fields))
        return self.work(files=changes)

    def scope_gates(self, where: Path) -> dict:
        """The scope gate from settle_gates, seen from the main checkout, and from ready_gates,
        seen from the worktree: where each one really runs."""
        found = {}
        project = self.project()
        rows = registry.load(project)["workstreams"]
        folders = list(snapshot.folders_by_id(project, rows).values())
        ws = next(w for w in rows if w["id"] == "alpha")
        task = tasks.find_task(tasks.load(project.tasks_path(ws), project.config), "T1")
        rev = project.config.branch_for("T1")
        text = evidence.read_at(project, ws, "T1", rev)
        settled = gates.settle_gates(project, ws, task, rev, text=text, merged=False,
                                     folders=folders)
        found["settle"] = next(g for g in settled if g["name"] == SCOPE_GATE)
        at_tree = open_project(where)
        task = tasks.find_task(tasks.load(at_tree.tasks_path(ws), at_tree.config), "T1")
        ready = gates.ready_gates(at_tree, ws, task, folders)
        found["ready"] = next(g for g in ready if g["name"] == SCOPE_GATE)
        return found

    def test_a_changed_doc_the_task_names_gives_no_warning(self) -> None:
        where = self.worked({"a.txt": "x\n", "guide.md": EDITED},
                            files=["a.txt"], docs=["guide.md"])
        for name, found in self.scope_gates(where).items():
            with self.subTest(name):
                self.assertTrue(found["ok"], found["detail"])

    def test_a_path_in_neither_list_still_warns(self) -> None:
        where = self.worked({"a.txt": "x\n", "guide.md": EDITED, "b.txt": "y\n"},
                            files=["a.txt"], docs=["guide.md"])
        for name, found in self.scope_gates(where).items():
            with self.subTest(name):
                self.assertFalse(found["ok"])
                self.assertFalse(found["blocking"])
                self.assertEqual(found["detail"], "files outside the task's list: b.txt")

    def test_empty_files_with_docs_still_gets_no_check(self) -> None:
        where = self.worked({"b.txt": "y\n"}, docs=["guide.md"])
        for name, found in self.scope_gates(where).items():
            with self.subTest(name):
                self.assertTrue(found["ok"], found["detail"])

    def test_the_settle_output_stays_quiet_about_a_named_doc(self) -> None:
        self.worked({"a.txt": "x\n", "guide.md": EDITED}, files=["a.txt"], docs=["guide.md"])
        self.assertNotIn("the diff stays within", self.ok("settle", "T1"))

    def test_the_shared_printer_keeps_the_name_before_the_detail(self) -> None:
        self.worked({"a.txt": "x\n", "b.txt": "y\n"}, files=["a.txt"])
        self.assertIn("  warn the diff stays within the task's files: "
                      "files outside the task's list: b.txt",
                      self.ok("settle", "T1", "--dry-run"))

    def test_the_doctor_still_prints_warn_name_detail(self) -> None:
        self.edit_config('test = "true"', 'test = "no-such-tool-here"')
        self.assertIn("  warn each command's tool is here: test: ", self.ok("doctor"))


class TaskSchemaTests(SettleTestCase):
    def test_the_protocol_says_docs_may_be_changed(self) -> None:
        out = self.ok("protocol", "task-schema")
        row = next(line for line in out.splitlines() if line.startswith("| `docs` |"))
        self.assertIn("may be changed", row)
        row = next(line for line in out.splitlines() if line.startswith("| `files` |"))
        self.assertIn("not here or in `docs` warns", row)
