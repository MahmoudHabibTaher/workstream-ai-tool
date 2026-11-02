"""`ws import` on hand-written fixtures in both older shapes. Every name here is made up."""

from __future__ import annotations

import json
from pathlib import Path

from tests.helpers import WsTestCase


def old_task(task_id: str, priority: int, status: str = "done", **fields) -> dict:
    return {"id": task_id, "phase": 1, "priority": priority, "severity": "low", "title": f"do {task_id}",
            "findings": [], "summary": "", "files": [], "docs": [], "acceptance": ["it works"],
            "verify": "true", "branch": "", "status": status, "completedAt": None,
            "commit": "abc" if status == "done" else None, "blockedBy": [],
            "needsUserDecision": False, "notes": "", **fields}


class ImportCase(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.git("add", "-A")
        self.git("commit", "-q", "-m", "start", check=False)

    def write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data))

    def tree(self) -> dict[str, bytes]:
        skip = (".git",)
        return {str(p.relative_to(self.root)): p.read_bytes() for p in self.root.rglob("*")
                if p.is_file() and not any(part in skip for part in p.relative_to(self.root).parts)}


class FolderRegistryTests(ImportCase):
    def setUp(self) -> None:
        super().setUp()
        for name, status, queue in (("old", "done", [old_task("O-1", 10)]),
                                    ("next", "planned", [old_task("N-1", 10, "todo"),
                                                         old_task("N-2", 20, "todo", verify="unknown-key")])):
            folder = self.ws_dir / name
            self.write_json(folder / "tasks_list.json", {"source": f"workstreams/{name}/PLAN.md", "updated": "2026-01-01",
                                                         "statusValues": ["todo", "done"], "tasks": queue})
            for doc in ("PLAN.md", "DECISIONS.md", "PROGRESS.md", "session_handoff.md", "AGENTS.md"):
                (folder / doc).write_text(f"# {doc}\n")
        self.write_json(self.ws_dir / "workstreams.json", {"updated": "2026-01-01", "statusValues": ["planned"], "workstreams": [
            {"id": "old", "title": "Old", "status": "done", "created": "2026-01-01", "taskPrefix": "O", "dependsOn": []},
            {"id": "next", "title": "Next", "status": "planned", "created": "2026-01-01", "taskPrefix": "N", "dependsOn": []}]})

    def test_a_dry_run_changes_nothing(self) -> None:
        before = self.tree()
        self.assertIn("nothing changed", self.ok("import"))
        self.assertEqual(self.tree(), before)

    def test_it_converts_and_the_result_validates(self) -> None:
        out = self.ok("import", "--write")
        self.assertIn("schema none to 3", out)
        queue = json.loads((self.ws_dir / "next" / "tasks_list.json").read_text())
        self.assertEqual(queue["schemaVersion"], 3)
        self.assertNotIn("statusValues", queue)
        self.assertEqual(queue["tasks"][0]["verify"], ["true"])
        self.assertEqual(queue["tasks"][0]["severity"], "low", "a field the schema doesn't know is kept")
        self.assertIn("next", self.ok("list"))
        self.ok("status", "-w", "next")

    def test_a_frozen_protocol_copy_goes_from_open_work_only(self) -> None:
        self.ok("import", "--write")
        self.assertFalse((self.ws_dir / "next" / "AGENTS.md").exists())
        self.assertTrue((self.ws_dir / "old" / "AGENTS.md").exists())

    def test_a_second_write_changes_nothing(self) -> None:
        self.ok("import", "--write")
        before = self.tree()
        self.assertIn("nothing to import", self.ok("import", "--write"))
        self.assertEqual(self.tree(), before)

    def test_what_only_the_old_harness_knew_comes_back_for_a_person(self) -> None:
        out = self.ok("import")
        self.assertIn("needs a person", out)
        self.assertIn("`unknown-key`, not in [commands]", out)
        self.assertNotIn("`u`", out)

    def test_closed_work_is_not_rejudged(self) -> None:
        self.ok("import", "--write")
        out = self.ok("show", "O-1", "-w", "old")
        self.assertIn("done", out)


class RootRegistryTests(ImportCase):
    def setUp(self) -> None:
        super().setUp()
        folder = self.root / "work" / "shift_work"
        task = {"id": "S-1", "title": "a", "phase": 1, "status": "pending", "dependsOn": [], "kind": "behaviour",
                "description": "what to do", "filesToTouch": ["a.py"], "acceptanceCriteria": ["it works"],
                "validation": ["true"], "notes": ""}
        done = {**task, "id": "S-2", "status": "done", "commit": "abc", "dependsOn": ["S-1"]}
        self.write_json(folder / "tasks_list.json", {
            "schemaVersion": 1, "workstream": "Shift work", "source": "work/shift_work/DESIGN.md",
            "scope": {"inScope": ["a"], "outOfScope": [], "rule": "just a"}, "validation": {"lint": "true"},
            "statusValues": ["pending"], "protocol": ["do it"], "logbook": {}, "baseline": {"lint": {}}, "tasks": [task, done]})
        (folder / "PROGRESS.md").write_text("# Log\n")
        (folder / "SESSION_HANDOFF.md").write_text("# Next\n")
        self.write_json(self.root / "workstreams.json", {"schemaVersion": 1, "workstreams": [
            {"name": "shift_work", "path": "work/shift_work", "status": "open", "createdOn": "2026-01-01",
             "source": "DESIGN.md", "updatedOn": "2026-01-02", "lastCommit": "abc", "closedOn": None,
             "taskCounts": {"total": 2}},
            {"name": "gone", "path": "work/gone", "status": "closed", "createdOn": "2026-01-01", "source": "x",
             "updatedOn": "2026-01-02", "lastCommit": "abc", "closedOn": "2026-01-03", "taskCounts": {"total": 1}}]})

    def test_a_dry_run_changes_nothing(self) -> None:
        before = self.tree()
        self.assertIn("nothing changed", self.ok("import"))
        self.assertEqual(self.tree(), before)

    def test_fields_statuses_and_names_map_across(self) -> None:
        self.ok("import", "--write")
        queue = json.loads((self.root / "work" / "shift_work" / "tasks_list.json").read_text())
        task = queue["tasks"][0]
        self.assertEqual((task["status"], task["summary"], task["files"], task["acceptance"], task["verify"], task["priority"]),
                         ("todo", "what to do", ["a.py"], ["it works"], ["true"], 10))
        self.assertEqual(queue["tasks"][1]["blockedBy"], ["S-1"])
        self.assertEqual(queue["scope"]["rule"], "just a")
        for gone in ("protocol", "logbook", "statusValues", "baseline", "validation"):
            self.assertNotIn(gone, queue)
        folder = self.root / "work" / "shift_work"
        names = {p.name for p in folder.iterdir()}
        self.assertIn("session_handoff.md", names)
        self.assertNotIn("SESSION_HANDOFF.md", names)
        self.assertIn("DESIGN.md", (folder / "PLAN.md").read_text())

    def test_the_registry_moves_and_a_closed_row_with_no_folder_stays_listed(self) -> None:
        self.ok("import", "--write")
        self.assertFalse((self.root / "workstreams.json").exists())
        data = json.loads((self.ws_dir / "workstreams.json").read_text())
        rows = {w["id"]: w for w in data["workstreams"]}
        self.assertEqual(rows["shift_work"]["status"], "active")
        self.assertEqual(rows["shift_work"]["progress"]["total"], 2)
        self.assertEqual((rows["gone"]["status"], rows["gone"]["closed"]["pruned"]), ("done", True))
        self.assertEqual(self.ok("validate", "-w", "gone").strip().splitlines()[-1], "OK: gone, no integrity problems")
        self.ok("status", "-w", "shift_work")

    def test_a_second_write_changes_nothing(self) -> None:
        self.ok("import", "--write")
        before = self.tree()
        self.assertIn("nothing to import", self.ok("import", "--write"))
        self.assertEqual(self.tree(), before)
