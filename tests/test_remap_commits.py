"""The commit remap, run against a temp repo and a handwritten commit-map."""

import contextlib
import io
import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from scripts import remap_commits
from tests.helpers import GIT_ENV

# Old ids. OLD_A and OLD_B share the prefix "aaaa1111" so it is ambiguous.
OLD_A = "aaaa1111" + "0" * 31 + "1"
OLD_B = "aaaa1111" + "0" * 31 + "2"
OLD_C = "cccc2222" + "3" * 32
OLD_D = "dddd4444" + "5" * 32
OLD_DROPPED = "eeee6666" + "7" * 32
NEW_A = "1" * 40
NEW_B = "2" * 40
NEW_C = "3c" * 20
NEW_D = "4d" * 20
UNKNOWN = "f00dfeed" + "9" * 32

COMMIT_MAP = "\n".join([
    "old                                      new",
    f"{OLD_A} {NEW_A}",
    f"{OLD_B} {NEW_B}",
    f"{OLD_C} {NEW_C}",
    f"{OLD_D} {NEW_D}",
    f"{OLD_DROPPED} {'0' * 40}",
    "",
])


class RemapTest(unittest.TestCase):
    """A temp repo holding the files the remap rewrites, and filter-repo's commit-map."""

    def setUp(self):
        env = mock.patch.dict(os.environ, GIT_ENV)
        env.start()
        self.addCleanup(env.stop)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve() / "repo"
        self.root.mkdir()
        subprocess.run(["git", "init", "-q", "-b", "main"], cwd=self.root, check=True)
        self.commit_map = self.root / ".git" / "filter-repo" / "commit-map"
        self.commit_map.parent.mkdir()
        self.commit_map.write_text(COMMIT_MAP)
        self.tasks = self.root / "workstreams" / "demo" / "tasks_list.json"
        self.registry = self.root / "workstreams" / "workstreams.json"
        self.doc = self.root / "docs" / "decisions" / "0001-demo.md"
        self.write_json(self.tasks, {"tasks": [
            {"id": "D-01", "commit": OLD_C},
            {"id": "D-02", "commit": UNKNOWN},
            {"id": "D-03", "commit": None},
        ]})
        self.write_json(self.registry, {"workstreams": [
            {"id": "demo", "closed": {"commit": OLD_D, "pruned": False}},
            {"id": "open_one"},
        ]})
        self.doc.parent.mkdir(parents=True)
        self.doc.write_text(
            f"Landed in `{OLD_C[:7]}`, then `{OLD_D[:12]}`.\n"
            f"Another repo's `{UNKNOWN[:7]}` stays.\n"
            f"The prefix `{OLD_A[:8]}` matches two commits.\n"
            f"Dropped `{OLD_DROPPED[:7]}`; not an id `{OLD_C[:6]}`; unquoted {OLD_C[:7]}.\n"
        )

    @staticmethod
    def write_json(path, data):
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(data, indent=2) + "\n")

    def run_main(self, *argv):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = remap_commits.main(["--root", str(self.root), *argv])
        return code, out.getvalue()

    def test_a_tasks_list_commit_is_remapped(self):
        self.run_main()
        tasks = json.loads(self.tasks.read_text())["tasks"]
        self.assertEqual(tasks[0]["commit"], NEW_C)

    def test_an_unknown_or_null_tasks_list_commit_is_left_alone(self):
        self.run_main()
        tasks = json.loads(self.tasks.read_text())["tasks"]
        self.assertEqual(tasks[1]["commit"], UNKNOWN)
        self.assertIsNone(tasks[2]["commit"])

    def test_a_registry_closed_commit_is_remapped(self):
        self.run_main()
        rows = json.loads(self.registry.read_text())["workstreams"]
        self.assertEqual(rows[0]["closed"], {"commit": NEW_D, "pruned": False})
        self.assertEqual(rows[1], {"id": "open_one"})

    def test_json_keeps_the_layout_ws_writes(self):
        self.run_main()
        self.assertTrue(self.registry.read_text().startswith('{\n  "workstreams": [\n'))
        self.assertTrue(self.registry.read_text().endswith("}\n"))

    def test_a_backticked_short_id_in_markdown_is_remapped_at_the_same_length(self):
        self.run_main()
        text = self.doc.read_text()
        self.assertIn(f"Landed in `{NEW_C[:7]}`, then `{NEW_D[:12]}`.", text)

    def test_an_unknown_short_id_is_left_alone(self):
        self.run_main()
        self.assertIn(f"Another repo's `{UNKNOWN[:7]}` stays.", self.doc.read_text())

    def test_an_ambiguous_prefix_is_left_alone(self):
        self.run_main()
        self.assertIn(f"The prefix `{OLD_A[:8]}` matches two commits.", self.doc.read_text())

    def test_dropped_too_short_and_unquoted_ids_are_left_alone(self):
        self.run_main()
        self.assertIn(
            f"Dropped `{OLD_DROPPED[:7]}`; not an id `{OLD_C[:6]}`; unquoted {OLD_C[:7]}.",
            self.doc.read_text(),
        )

    def test_markdown_under_workstreams_is_remapped(self):
        note = self.root / "workstreams" / "demo" / "evidence" / "D-01.md"
        note.parent.mkdir()
        note.write_text(f"commit `{OLD_C[:10]}`\n")
        self.run_main()
        self.assertEqual(note.read_text(), f"commit `{NEW_C[:10]}`\n")

    def test_counts_are_reported(self):
        code, out = self.run_main()
        self.assertEqual(code, 0)
        # remapped: tasks OLD_C, registry OLD_D, md OLD_C and OLD_D.
        # unknown: tasks UNKNOWN, md UNKNOWN and the dropped id. ambiguous: OLD_A's prefix.
        self.assertEqual(out.splitlines()[-1], "4 remapped, 3 unknown, 1 ambiguous")
        self.assertIn("rewrote docs/decisions/0001-demo.md", out)

    def test_a_second_run_changes_nothing(self):
        self.run_main()
        before = [p.read_text() for p in (self.tasks, self.registry, self.doc)]
        _code, out = self.run_main()
        self.assertEqual([p.read_text() for p in (self.tasks, self.registry, self.doc)], before)
        self.assertNotIn("rewrote", out)

    def test_an_explicit_commit_map_path_is_read(self):
        other = self.root / "elsewhere-map"
        other.write_text(f"old new\n{OLD_C} {NEW_C}\n")
        self.commit_map.unlink()
        code, out = self.run_main("--commit-map", str(other))
        self.assertEqual(code, 0)
        self.assertEqual(json.loads(self.tasks.read_text())["tasks"][0]["commit"], NEW_C)

    def test_a_missing_commit_map_fails(self):
        self.commit_map.unlink()
        err = io.StringIO()
        with contextlib.redirect_stderr(err):
            code, _out = self.run_main()
        self.assertEqual(code, 1)
        self.assertIn("no commit-map at", err.getvalue())

    def test_help_names_the_commit_map_path(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out), self.assertRaises(SystemExit):
            remap_commits.main(["--help"])
        self.assertIn(".git/filter-repo/commit-map", out.getvalue())


if __name__ == "__main__":
    unittest.main()
