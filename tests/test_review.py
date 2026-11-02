"""Per-task review data. The pure parts run on plain data, the git parts in a throwaway repo.

What is proven: a `--no-ff` merge yields its first-parent numstat, not git show's empty
combined diff; an in-progress branch yields base...branch, leaving out what landed since;
--file cuts at a hunk boundary and sets truncated; `review` writes nothing.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from tests.helpers import WsTestCase, task
from workstream import review

WS_ID = "flow"


def numbered(n: int, changed: set[int] = frozenset()) -> str:
    """n lines, the ones in `changed` edited: far-apart edits make separate hunks."""
    return "".join(f"line {i}{' edited' if i in changed else ''}\n" for i in range(n))


class ReviewRangeTests(unittest.TestCase):
    def range_of(self, t: dict, parents=None, branches=()) -> dict:
        return review.review_range(t, lambda rev: parents, lambda name: name in branches)

    def test_a_merge_commit_is_reviewed_against_its_first_parent(self) -> None:
        rng = self.range_of({"status": "done", "commit": "abc"}, parents=["p1", "p2"])
        self.assertEqual(rng, {"from": "abc^1", "to": "abc", "kind": "merge"})
        self.assertEqual(review.diff_spec(rng), "abc^1..abc")

    def test_a_single_parent_commit_is_reviewed_against_its_parent(self) -> None:
        rng = self.range_of({"status": "done", "commit": "abc"}, parents=["p1"])
        self.assertEqual(rng, {"from": "abc^", "to": "abc", "kind": "commit"})
        self.assertEqual(review.diff_spec(rng), "abc^..abc")

    def test_an_in_progress_branch_is_reviewed_from_its_base(self) -> None:
        t = {"status": "in-progress", "branch": "task/x", "baseCommit": "b0"}
        rng = self.range_of(t, branches=("task/x",))
        self.assertEqual(rng, {"from": "b0", "to": "task/x", "kind": "branch"})
        self.assertEqual(review.diff_spec(rng), "b0...task/x")

    def test_everything_else_is_none(self) -> None:
        none = {"from": None, "to": None, "kind": "none"}
        claimed = {"status": "in-progress", "branch": "task/x", "baseCommit": "b0"}
        for t, parents, branches in (
            ({"status": "todo", "branch": "task/x"}, None, ("task/x",)),
            (claimed, None, ()),                                    # branch not created yet
            ({**claimed, "baseCommit": None}, None, ("task/x",)),
            ({"status": "done", "commit": "gone"}, None, ()),       # commit not in this repo
            ({"status": "done", "commit": "root"}, [], ()),         # a root commit
        ):
            with self.subTest(task=t):
                self.assertEqual(self.range_of(t, parents, branches), none)
                self.assertIsNone(review.diff_spec(none))


class ParseTests(unittest.TestCase):
    def test_parse_numstat_reads_counts_and_binary_files(self) -> None:
        text = "3\t1\tsrc/a.rs\n-\t-\timg.png\n0\t7\tdocs/with space.md\n"
        self.assertEqual(review.parse_numstat(text), [
            {"path": "src/a.rs", "added": 3, "removed": 1},
            {"path": "img.png", "added": None, "removed": None},
            {"path": "docs/with space.md", "added": 0, "removed": 7},
        ])

    def test_cap_hunks_keeps_whole_hunks_only(self) -> None:
        header = ["diff --git a/f b/f\n", "--- a/f\n", "+++ b/f\n"]
        hunk = lambda n: ["@@ -1 +1 @@\n", *[f"-{n}\n", f"+{n}\n"]]  # noqa: E731
        lines = header + hunk(1) + hunk(2) + hunk(3)                   # 3 + 3*3 = 12 lines
        text = "".join(lines)
        self.assertEqual(review.cap_hunks(text, 12), (text, False))
        self.assertEqual(review.cap_hunks(text, 11), ("".join(lines[:9]), True))
        self.assertEqual(review.cap_hunks(text, 6), ("".join(lines[:6]), True))
        self.assertEqual(review.cap_hunks(text, 5), ("".join(header), True))


class ReviewRepoTests(WsTestCase):
    """One task merged --no-ff, one claimed with its branch alive, one not started."""

    integration = "trunk"

    def setUp(self) -> None:
        super().setUp()
        self.new_ws(WS_ID, "FL")
        self.write("src/merged.txt", numbered(60))
        self.write("src/other.txt", "other\n")
        base = self.commit_all("base")
        # FL-01: a task branch merged --no-ff.
        self.git("switch", "-q", "-c", "task/one")
        self.write("src/merged.txt", numbered(60, {2, 30, 58}))
        self.write("src/added.txt", "new\n")
        self.commit_all("one")
        self.git("switch", "-q", "trunk")
        self.git("merge", "-q", "--no-ff", "-m", "Merge task/one", "task/one")
        self.merge = self.git("rev-parse", "--short", "HEAD").strip()
        # FL-02: claimed at the merge, with a commit on its branch; trunk moves on after.
        self.git("switch", "-q", "-c", "task/two")
        self.write("src/branch.txt", "branch work\n")
        self.commit_all("two")
        self.git("switch", "-q", "trunk")
        self.write("src/other.txt", "trunk moved on\n")
        self.commit_all("later")
        self.write_queue([
            task("FL-01", 10, status="done", branch="task/one", baseCommit=base,
                 commit=self.merge),
            task("FL-02", 20, status="in-progress", branch="task/two", baseCommit=self.merge,
                 startedAt="2026-10-01T00:00:00Z"),
            task("FL-03", 30, status="todo", branch="task/three"),
        ], WS_ID)
        self.write(f"workstreams/{WS_ID}/evidence/FL-01.md", "# FL-01 evidence\n")
        self.commit_all("tracking")

    def write(self, rel: str, text: str) -> None:
        path = self.root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)

    def review(self, *argv: str) -> dict:
        return json.loads(self.ok("review", "-w", WS_ID, *argv))

    def test_a_no_ff_merge_yields_the_first_parent_numstat(self) -> None:
        # The trap: git show prints an empty combined diff for a clean --no-ff merge.
        self.assertEqual(self.git("show", "--format=", self.merge).strip(), "")
        data = self.review("FL-01")
        self.assertEqual(data["range"], {"from": f"{self.merge}^1", "to": self.merge,
                                         "kind": "merge"})
        self.assertEqual(data["files"], [
            {"path": "src/added.txt", "added": 1, "removed": 0},
            {"path": "src/merged.txt", "added": 3, "removed": 3},
        ])
        self.assertEqual(data["evidence"],
                         str(self.root / "workstreams" / WS_ID / "evidence" / "FL-01.md"))
        self.assertNotIn("hunks", data)

    def test_an_in_progress_branch_yields_base_to_branch(self) -> None:
        data = self.review("FL-02")
        self.assertEqual(data["range"], {"from": self.merge, "to": "task/two", "kind": "branch"})
        # Three dots: trunk's later change to src/other.txt is not the branch's work.
        self.assertEqual(data["files"], [{"path": "src/branch.txt", "added": 1, "removed": 0}])
        self.assertIsNone(data["evidence"])

    def test_an_unstarted_task_has_no_range(self) -> None:
        data = self.review("FL-03")
        self.assertEqual(data["range"]["kind"], "none")
        self.assertEqual(data["files"], [])

    def test_file_truncates_at_a_hunk_boundary(self) -> None:
        whole = self.review("FL-01", "--file", "src/merged.txt")
        self.assertFalse(whole["hunks"]["truncated"])
        full = whole["hunks"]["text"].splitlines()
        starts = [i for i, line in enumerate(full) if line.startswith("@@")]
        self.assertEqual(len(starts), 3, whole["hunks"]["text"])
        # A cap one line short of the second hunk's end keeps the first hunk only.
        cap = starts[2] - 1
        cut = self.review("FL-01", "--file", "src/merged.txt", "--max-lines", str(cap))
        self.assertEqual(cut["hunks"]["path"], "src/merged.txt")
        self.assertTrue(cut["hunks"]["truncated"])
        self.assertEqual(cut["hunks"]["text"].splitlines(), full[:starts[1]])
        self.assertLessEqual(len(cut["hunks"]["text"].splitlines()), cap)

    def test_a_git_failure_comes_back_as_data(self) -> None:
        t = {"id": "FL-02", "status": "in-progress", "branch": "task/two", "baseCommit": "f" * 40}
        with mock.patch.object(review.tasks, "find_task", return_value=t):
            data = review.build_review(self.project(), WS_ID, "FL-02")
        self.assertEqual(data["range"]["kind"], "branch")
        self.assertEqual(data["files"], [])
        self.assertTrue(data["error"].startswith("git diff "), data["error"])

    def test_unknown_ids_exit_with_an_error(self) -> None:
        self.assertIn("no workstream with id 'nope'", self.fails("review", "-w", "nope", "FL-01"))
        self.assertIn("no task with id 'FL-99'", self.fails("review", "-w", WS_ID, "FL-99"))

    def test_a_pruned_workstream_says_so(self) -> None:
        self.write_queue([task("FL-01", 10, status="done", commit=self.merge)], WS_ID)
        self.ok("close", "-w", WS_ID, "--prune", "--yes")
        self.assertIn("no queue left", self.fails("review", "-w", WS_ID, "FL-01"))

    def test_a_revision_that_looks_like_an_option_never_reaches_git(self) -> None:
        # `git diff --output=<path>` would write a file named by the queue's contents.
        target = self.root / "written-by-git"
        for field, status in (("commit", "done"), ("baseCommit", "in-progress"),
                              ("branch", "in-progress")):
            with self.subTest(field=field):
                fields = {"commit": None, "baseCommit": self.merge, "branch": "task/two",
                          field: f"--output={target}"}
                self.write_queue([task("FL-09", 90, status=status, **fields)], WS_ID)
                self.assertIn("starts with '-'", self.fails("review", "-w", WS_ID, "FL-09"))
                self.assertFalse(target.exists())

    def test_review_writes_nothing(self) -> None:
        def state() -> tuple[str, str, bytes]:
            index = (self.root / ".git" / "index").read_bytes()
            return self.git("status", "--porcelain"), self.git("rev-parse", "HEAD"), index

        before = state()
        for t in ("FL-01", "FL-02", "FL-03"):
            self.review(t, "--file", "src/merged.txt")
        self.assertEqual(state(), before)


if __name__ == "__main__":
    unittest.main()
