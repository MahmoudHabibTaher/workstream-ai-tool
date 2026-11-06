"""Per-task review data. The pure parts run on plain data, the git parts in a throwaway repo.

What is proven: a `--no-ff` merge yields its first-parent numstat, not git show's empty
combined diff; an in-progress branch yields base...branch, leaving out what landed since;
--checks reads a branch's evidence from the branch; --queue puts branch work first; --file cuts
at a hunk boundary and sets truncated; `review` writes nothing. --show gives one side of one
file: a branch's old side at the merge base even after trunk moved, null text for an added or
deleted file, binary with no text, and a path outside the diffstat refused.
"""

from __future__ import annotations

import json
import unittest
from unittest import mock

from tests.helpers import WsTestCase, task
from tests.test_schema import load_schema, problems
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


class SideRevTests(unittest.TestCase):
    def test_a_branchs_old_side_is_the_merge_base_not_from(self) -> None:
        rng = {"from": "trunk-tip", "to": "task/x", "kind": "branch"}
        asked = []
        base = lambda a, b: asked.append((a, b)) or "fork"  # noqa: E731
        self.assertEqual(review.side_rev(rng, "old", base), "fork")
        self.assertEqual(asked, [("trunk-tip", "task/x")])
        self.assertEqual(review.side_rev(rng, "new", base), "task/x")

    def test_a_commit_or_merges_old_side_is_from(self) -> None:
        never = lambda a, b: self.fail("no merge base for a commit")  # noqa: E731
        for kind, start in (("merge", "abc^1"), ("commit", "abc^")):
            rng = {"from": start, "to": "abc", "kind": kind}
            self.assertEqual(review.side_rev(rng, "old", never), start)
            self.assertEqual(review.side_rev(rng, "new", never), "abc")

    def test_none_has_no_side(self) -> None:
        rng = {"from": None, "to": None, "kind": "none"}
        self.assertIsNone(review.side_rev(rng, "old", lambda a, b: "x"))

    def test_binary_is_a_nul_or_not_utf8(self) -> None:
        self.assertFalse(review.is_binary("café\n".encode()))
        self.assertTrue(review.is_binary(b"\x89PNG\r\n\x1a\n\0\0"))
        self.assertTrue(review.is_binary(b"\xff\xfe latin junk"))


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
        t = {"id": "FL-02", "status": "in-progress", "branch": "task/gone", "baseCommit": "f" * 40}
        with mock.patch.object(review.tasks, "find_task", return_value=t), \
                mock.patch.object(review, "git_branch_exists", return_value=True):
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

    # --- --checks ---------------------------------------------------------------------------

    def with_branch_evidence(self, text: str, **fields) -> None:
        """FL-02 with acceptance items, and evidence on its branch only."""
        self.write_queue([
            task("FL-01", 10, status="done", branch="task/one", commit=self.merge,
                 completedAt="2026-10-02T00:00:00Z"),
            task("FL-02", 20, status="in-progress", branch="task/two", baseCommit=self.merge,
                 startedAt="2026-10-01T00:00:00Z",
                 acceptance=["it works", "it fails well"], **fields),
        ], WS_ID)
        self.commit_all("tracking again")
        self.git("switch", "-q", "task/two")
        self.write(f"workstreams/{WS_ID}/evidence/FL-02.md", text)
        self.commit_all("evidence")
        self.git("switch", "-q", "trunk")

    def test_checks_read_a_branchs_evidence_from_the_branch(self) -> None:
        self.with_branch_evidence(
            "- **Status:** done\n\n## Acceptance\n\n1. it works -> `run`: ok\n  and more\n\n"
            "## Proposed decisions\n\n### P1: keep it\nBecause. Rejected: not.\n\n"
            "## Gotchas and follow-ups\n\nWatch out.\n")
        evidence_path = self.root / "workstreams" / WS_ID / "evidence" / "FL-02.md"
        self.assertFalse(evidence_path.exists())
        checks = self.review("FL-02", "--checks")["checks"]
        self.assertEqual((checks["state"], checks["evidenceStatus"]), ("branch", "done"))
        self.assertEqual(checks["items"], [
            {"n": 1, "item": "it works", "proof": "`run`: ok\nand more"},
            {"n": 2, "item": "it fails well", "proof": ""},
        ])
        self.assertEqual([p["id"] for p in checks["proposals"]], ["P1"])
        self.assertEqual(checks["gotchas"], "Watch out.")

    def test_checks_report_the_gates_settling_would_run(self) -> None:
        self.with_branch_evidence("- **Status:** done\n\n## Acceptance\n\n1. it works -> ok\n")
        gates = {g["name"]: g for g in self.review("FL-02", "--checks")["checks"]["gates"]}
        missing = gates["the evidence is complete"]
        self.assertFalse(missing["ok"])
        self.assertIn("acceptance item 2 is missing", missing["detail"])
        self.assertTrue(gates["the branch has commits"]["ok"])
        self.assertTrue(gates["the branch leaves tracking files alone"]["ok"])

    def test_checks_on_a_landed_task_name_the_commit_and_run_no_gates(self) -> None:
        checks = self.review("FL-01", "--checks")["checks"]
        self.assertEqual((checks["state"], checks["commit"], checks["gates"]),
                         ("landed", self.merge, []))
        self.assertEqual(checks["evidenceText"], "# FL-01 evidence\n")

    def test_checks_on_a_task_not_started_say_so(self) -> None:
        checks = self.review("FL-03", "--checks")["checks"]
        self.assertEqual((checks["state"], checks["evidenceText"], checks["items"]),
                         ("none", None, []))

    def test_plain_review_has_no_checks(self) -> None:
        self.assertNotIn("checks", self.review("FL-02"))

    # --- --show -----------------------------------------------------------------------------

    def show(self, t: str, path: str, side: str) -> dict:
        data = self.review(t, "--show", path, "--side", side)
        schema = load_schema("review-show")
        self.assertEqual(problems(data, schema, schema), [])
        return data

    def more_branch_work(self) -> None:
        """FL-02's branch edits src/other.txt, which trunk also changed after the claim, deletes
        src/merged.txt and adds a binary file."""
        self.git("switch", "-q", "task/two")
        self.write("src/other.txt", "branch edit\n")
        (self.root / "src/merged.txt").unlink()
        (self.root / "src/img.bin").write_bytes(b"\x89PNG\r\n\x1a\n\0\0\0\rIHDR")
        self.commit_all("more work")
        self.git("switch", "-q", "trunk")

    def test_a_branchs_old_side_is_the_merge_base_not_mains_tip(self) -> None:
        self.more_branch_work()
        self.assertEqual(self.git("show", "trunk:src/other.txt"), "trunk moved on\n")
        old = self.show("FL-02", "src/other.txt", "old")
        fork = self.git("merge-base", "trunk", "task/two").strip()
        self.assertEqual(old, {"path": "src/other.txt", "side": "old", "rev": fork,
                               "text": "other\n", "binary": False})
        new = self.show("FL-02", "src/other.txt", "new")
        self.assertEqual((new["rev"], new["text"]),
                         (self.git("rev-parse", "task/two").strip(), "branch edit\n"))

    def test_an_added_file_has_no_old_text(self) -> None:
        self.assertEqual(self.show("FL-01", "src/added.txt", "old")["text"], None)
        new = self.show("FL-01", "src/added.txt", "new")
        self.assertEqual((new["text"], new["binary"]), ("new\n", False))
        self.assertEqual(new["rev"], self.git("rev-parse", self.merge).strip())

    def test_a_deleted_file_has_no_new_text(self) -> None:
        self.more_branch_work()
        # FL-02 was claimed after FL-01 landed, so the old side holds FL-01's edits.
        self.assertEqual(self.show("FL-02", "src/merged.txt", "old")["text"],
                         numbered(60, {2, 30, 58}))
        new = self.show("FL-02", "src/merged.txt", "new")
        self.assertEqual((new["text"], new["binary"]), (None, False))

    def test_a_modified_file_has_both_sides_of_a_merge(self) -> None:
        old = self.show("FL-01", "src/merged.txt", "old")
        self.assertEqual((old["rev"], old["text"]),
                         (self.git("rev-parse", f"{self.merge}^1").strip(), numbered(60)))
        new = self.show("FL-01", "src/merged.txt", "new")
        self.assertEqual(new["text"], numbered(60, {2, 30, 58}))

    def test_a_binary_file_says_so_and_has_no_text(self) -> None:
        self.more_branch_work()
        new = self.show("FL-02", "src/img.bin", "new")
        self.assertEqual((new["binary"], new["text"]), (True, None))
        old = self.show("FL-02", "src/img.bin", "old")
        self.assertEqual((old["binary"], old["text"]), (False, None))

    def test_a_path_outside_the_diffstat_is_refused(self) -> None:
        for t, path in (("FL-02", "src/other.txt"), ("FL-02", "nope.txt"), ("FL-03", "x")):
            with self.subTest(task=t, path=path):
                self.assertIn("not in", self.fails("review", "-w", WS_ID, t, "--show", path,
                                                   "--side", "old"))

    def test_show_and_side_go_together_and_alone(self) -> None:
        self.assertIn("go together", self.fails("review", "-w", WS_ID, "FL-01", "--show",
                                                "src/added.txt"))
        self.assertIn("go together", self.fails("review", "-w", WS_ID, "FL-01", "--side", "old"))
        self.assertIn("no --file", self.fails("review", "-w", WS_ID, "FL-01", "--show",
                                              "src/added.txt", "--side", "old", "--checks"))
        self.assertIn("takes no task", self.fails("review", "--queue", "--show", "x"))

    def test_show_runs_git_without_optional_locks(self) -> None:
        seen = []
        real = review.subprocess.run

        def spy(argv, **kw):
            seen.append(kw.get("env", {}).get("GIT_OPTIONAL_LOCKS"))
            return real(argv, **kw)

        with mock.patch.object(review.subprocess, "run", side_effect=spy):
            review.build_show(self.project(), WS_ID, "FL-01", "src/merged.txt", "old")
        self.assertTrue(seen)
        self.assertEqual(set(seen), {"0"})

    def test_plain_review_is_unchanged_by_show(self) -> None:
        data = self.review("FL-01")
        self.assertEqual(set(data), {"task", "evidence", "range", "files"})
        schema = load_schema("review")
        self.assertEqual(problems(data, schema, schema), [])

    # --- --queue ----------------------------------------------------------------------------

    def queue(self) -> list[dict]:
        return json.loads(self.ok("review", "--queue"))["tasks"]

    def test_the_queue_puts_branch_work_before_landed_work(self) -> None:
        self.with_branch_evidence("# none\n")
        self.assertEqual([(e["task"], e["state"]) for e in self.queue()],
                         [("FL-02", "branch"), ("FL-01", "landed")])

    def test_the_queue_holds_sizes_and_evidence(self) -> None:
        self.with_branch_evidence("# on the branch\n")
        first, second = self.queue()
        self.assertEqual((first["files"], first["added"], first["removed"]), (2, 2, 0))
        self.assertTrue(first["hasEvidence"])
        self.assertEqual((second["files"], second["added"], second["removed"]), (2, 4, 3))
        self.assertTrue(second["hasEvidence"])
        self.assertEqual(first["when"], "2026-10-01T00:00:00Z")

    def test_a_new_commit_changes_the_revision(self) -> None:
        self.with_branch_evidence("# on the branch\n")
        before = self.queue()[0]["revision"]
        self.git("switch", "-q", "task/two")
        self.write("src/branch.txt", "more\n")
        self.commit_all("more")
        self.git("switch", "-q", "trunk")
        self.assertNotEqual(self.queue()[0]["revision"], before)

    def test_the_queue_leaves_out_closed_workstreams_and_broken_queues(self) -> None:
        self.with_branch_evidence("# none\n")
        self.ok("new", "broken", "--title", "B", "--summary", "S", "--prefix", "BR")
        (self.root / "workstreams" / "broken" / "tasks_list.json").write_text("{not json")
        self.ok("new", "finished", "--title", "F", "--summary", "S", "--prefix", "FI")
        self.write_queue([task("FI-01", 10, status="done", commit=self.merge)], "finished")
        self.ok("close", "-w", "finished", "--yes")
        self.assertEqual({e["workstream"] for e in self.queue()}, {WS_ID})

    def test_queue_and_a_task_are_refused_together(self) -> None:
        self.assertIn("takes no task", self.fails("review", "--queue", "FL-01"))
        self.assertIn("needs a task id", self.fails("review", "-w", WS_ID))

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
