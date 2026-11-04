"""What a brief carries over from a finished blocker's gotchas."""

from __future__ import annotations

import io
import os
from contextlib import redirect_stdout

from tests.helpers import WsTestCase, evidence_text, task
from workstream import protocol, verify
from workstream.brief import MAX_GOTCHA_CHARS
from workstream.cli import main

POINTER_PATH = "workstreams/alpha/evidence/T1.md"


class GotchaTests(WsTestCase):
    def builds_on(self, gotchas: str) -> list[str]:
        """T2's "Builds on" lines under the T1 line, once T1 left these gotchas."""
        self.new_ws()
        self.seed_ok([task("T1", 1), task("T2", 2, blockedBy=["T1"])])
        folder = self.ws_dir / "alpha" / "evidence"
        folder.mkdir(exist_ok=True)
        (folder / "T1.md").write_text(evidence_text("T1", gotchas=gotchas))
        brief = self.ok("brief", "T2", "-w", "alpha")
        section = brief.split("## Builds on\n\n", 1)[1].split("\n\n## ", 1)[0]
        return section.splitlines()[1:]

    def test_gotchas_under_the_limit_appear_whole_with_every_line_indented(self) -> None:
        gotchas = ("- First one, which runs\n  over two lines.\n\n"
                   "  With a second paragraph.\n- Second one.\n1. A numbered third.")
        self.assertEqual(self.builds_on(gotchas), [
            "  - First one, which runs",
            "    over two lines.",
            "",
            "    With a second paragraph.",
            "  - Second one.",
            "  1. A numbered third.",
        ])

    def test_plain_text_is_one_entry_and_needs_no_pointer(self) -> None:
        self.assertEqual(self.builds_on("Watch the cache.\nIt lies."),
                         ["  Watch the cache.", "  It lies."])

    def test_none_leaves_nothing(self) -> None:
        self.assertEqual(self.builds_on("None."), [])

    def test_over_the_limit_keeps_whole_bullets_and_says_what_is_left_out(self) -> None:
        one, two, three = (f"- {name} " + "x" * 500 + " ends." for name in ("one", "two", "three"))
        lines = self.builds_on(f"{one}\n{two}\n{three}")
        self.assertEqual(lines, [f"  {one}", f"  {two}", f"  (1 more in {POINTER_PATH})"])

    def test_an_entry_that_does_not_fit_does_not_hide_a_shorter_one_after_it(self) -> None:
        one, long, short = "- one " + "x" * 700, "- long " + "y" * 700, "- the contact is Sam."
        lines = self.builds_on(f"{one}\n{long}\n{short}")
        self.assertEqual(lines, [f"  {one}", f"  {short}", f"  (1 more in {POINTER_PATH})"])

    def test_a_bullet_exactly_at_the_limit_is_kept_whole(self) -> None:
        entry = "- " + "x" * (MAX_GOTCHA_CHARS - 2)
        self.assertEqual(self.builds_on(entry), [f"  {entry}"])

    def test_one_entry_over_the_limit_is_cut_at_a_sentence_end(self) -> None:
        first = "- Starts here. " + "word " * 100 + "and stops here."
        rest = " Then goes on" + " and on" * 300 + "."
        lines = self.builds_on(first + rest)
        self.assertEqual(lines, [f"  {first}", f"  (1 more in {POINTER_PATH})"])

    def test_a_sentence_ending_right_at_the_limit_is_kept(self) -> None:
        first = "- " + "x" * (MAX_GOTCHA_CHARS - 3) + "."
        lines = self.builds_on(first + " And more after it.")
        self.assertEqual(lines, [f"  {first}", f"  (1 more in {POINTER_PATH})"])

    def test_a_dot_inside_a_file_name_is_not_a_sentence_end(self) -> None:
        first = "- Read this. See src/app.py "
        lines = self.builds_on(first + "and go on " * 200)
        self.assertEqual(lines, ["  - Read this.", f"  (1 more in {POINTER_PATH})"])

    def test_with_no_sentence_end_the_cut_falls_on_a_word(self) -> None:
        lines = self.builds_on("- " + "word " * 400)
        self.assertLessEqual(len(lines[0]), MAX_GOTCHA_CHARS + 2)
        self.assertTrue(lines[0].endswith(" word"), lines[0][-20:])
        self.assertEqual(lines[1], f"  (1 more in {POINTER_PATH})")

    def test_when_nothing_fits_the_first_is_cut_and_the_others_are_counted(self) -> None:
        one = "- One ends. " + "x" * MAX_GOTCHA_CHARS
        two = "- Two ends. " + "y" * MAX_GOTCHA_CHARS
        self.assertEqual(self.builds_on(f"{one}\n{two}"),
                         ["  - One ends.", f"  (2 more in {POINTER_PATH})"])


class SourceTests(WsTestCase):
    """A brief and a task's definition come from the integration checkout, the work from the
    worktree."""

    def setUp(self) -> None:
        super().setUp()
        self.where = self.root.parent / "where"
        self.set_commands(old=f"echo old >> {self.where}",
                          new=f"pwd >> {self.where}; echo new >> {self.where}")
        self.new_ws()
        self.seed_ok([task("T1", 1, verify=["old"], acceptance=["it works"])])
        self.commit_all("seed")
        self.ok("claim", "T1", "-w", "alpha")
        self.commit_all("claim")
        self.ok("worktree", "create", "T1", "-w", "alpha")
        self.tree = self.root / self.project().config.worktree_dir / "t1"
        self.assertTrue(self.tree.is_dir())

    def at_tree(self, *argv: str) -> str:
        code, out, err = self.ws_at(self.tree, *argv)
        self.assertEqual(code, 0, out + err)
        return out

    def test_a_decision_and_a_note_made_after_the_claim_appear(self) -> None:
        self.ok("decide", "Use the new cache", "--why", "the old one lies", "--by", "user")
        self.ok("update", "T1", "--notes", "Watch the cache", "-w", "alpha")
        brief = self.at_tree("brief", "T1", "-w", "alpha")
        self.assertIn("Use the new cache", brief)
        self.assertIn("**Notes:** Watch the cache", brief)
        self.assertNotIn("Watch the cache", (self.tree / "workstreams/alpha/tasks_list.json").read_text())
        self.commit_all("tracking")
        self.assertEqual(self.at_tree("brief", "T1", "-w", "alpha"), brief)

    def test_the_brief_finds_the_workstream_of_the_folder_it_stands_in(self) -> None:
        self.new_ws("beta")
        self.ok("decide", "Use the new cache", "--why", "the old one lies", "--by", "user", "-w", "alpha")
        back = os.getcwd()
        self.addCleanup(os.chdir, back)
        os.chdir(self.tree / "workstreams" / "alpha")
        out = io.StringIO()
        with redirect_stdout(out):
            self.assertEqual(main(["brief", "T1"]), 0)
        self.assertIn("Use the new cache", out.getvalue())

    def test_verify_runs_the_list_the_integration_branch_has_now(self) -> None:
        self.ok("update", "T1", "--verify", "new", "-w", "alpha")
        self.assertIn('"old"', (self.tree / "workstreams/alpha/tasks_list.json").read_text())
        self.at_tree("verify", "T1", "-w", "alpha")
        self.assertEqual(self.where.read_text().splitlines(), [str(self.tree), "new"])
        run = verify.load_run(self.project(), "alpha", "T1")
        self.assertEqual([r["key"] for r in run["results"]], ["new"])

    def test_verify_commit_and_evidence_still_act_on_the_worktree(self) -> None:
        self.ok("update", "T1", "--verify", "new", "-w", "alpha")
        before = self.git("rev-parse", "HEAD")
        (self.tree / "code.txt").write_text("x")
        self.ok("evidence", "new", "T1", "-w", "alpha")  # from the main checkout, on purpose
        file = self.tree / "workstreams/alpha/evidence/T1.md"
        self.assertTrue(file.exists())
        self.assertFalse((self.root / "workstreams/alpha/evidence/T1.md").exists())
        file.write_text(evidence_text("T1"))
        self.ok("verify", "T1", "-w", "alpha")
        self.assertEqual(self.where.read_text().splitlines()[0], str(self.tree))
        self.ok("commit", "T1", "-w", "alpha", "-m", "the work")
        self.assertEqual(self.git("rev-parse", "HEAD"), before)
        self.assertEqual(self.git_at(self.tree, "log", "-1", "--format=%s").strip(), "the work")
        self.assertEqual(self.git_at(self.tree, "status", "--porcelain"), "")
        self.assertIn("OK", self.ok("evidence", "check", "T1", "-w", "alpha"))
        self.assertIn("OK", self.at_tree("evidence", "check", "T1", "-w", "alpha"))

    def test_the_evidence_check_asks_for_the_list_the_integration_branch_has_now(self) -> None:
        self.at_tree("verify", "T1", "-w", "alpha")
        self.ok("update", "T1", "--verify", "new", "-w", "alpha")
        code, out, _ = self.ws_at(self.tree, "evidence", "check", "T1", "-w", "alpha")
        self.assertEqual(code, 1, out)
        self.assertIn("new: not run", out)

    def test_with_no_checkout_on_the_integration_branch_it_reads_this_checkout(self) -> None:
        self.git("switch", "-q", "-c", "elsewhere")
        self.assertEqual(self.ok("root"), f"{self.root}\n")
        self.ok("update", "T1", "--notes", "from the other branch", "-w", "alpha")
        self.at_tree("update", "T1", "--notes", "from this checkout", "-w", "alpha")
        brief = self.at_tree("brief", "T1", "-w", "alpha")
        self.assertIn("**Notes:** from this checkout", brief)
        self.assertNotIn("from the other branch", brief)
        self.at_tree("verify", "T1", "-w", "alpha")
        self.assertEqual(self.where.read_text().splitlines(), ["old"])


class OpenDecisionTests(WsTestCase):
    LOG = ("# Decisions\n\n---\n\n"
           "## D001 (2026-01-01, T1): direct call\n\nPick. **Open.**\n\n"
           "## D002 (2026-01-01, T0): transitive call\n\nPick. **Open.**\n\n"
           "## D003 (2026-01-01, T1): closed call\n\nPick. **Open.**\n\n"
           "## D004 (2026-01-01, T1): closes it\n\nCloses: D003.\n\nPicked. **Closed.**\n\n"
           "## D005 (2026-01-01, T9): unrelated call\n\nPick. **Open.**\n")

    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.seed_ok([task("T0", 1), task("T1", 2, blockedBy=["T0"]),
                      task("T2", 3, blockedBy=["T1"], acceptance=["works"], verify=["test"]),
                      task("T9", 4)])
        self.set_commands(test="true")
        (self.ws_dir / "alpha" / "DECISIONS.md").write_text(self.LOG)

    def test_blockers_open_decisions_come_right_after_acceptance_and_closed_ones_do_not(self) -> None:
        brief = self.ok("brief", "T2", "-w", "alpha")
        after = brief.split("## Acceptance\n\n1. works\n\n", 1)[1]
        self.assertTrue(after.startswith("## Open decisions\n"), after[:80])
        section = after.split("\n\n## ", 1)[0]
        self.assertIn("report blocked if one changes it", section)
        self.assertIn("`ws decisions --open -w alpha`", section)
        self.assertEqual([line for line in section.splitlines() if line.startswith("- ")],
                         ["- D001: direct call", "- D002: transitive call"])

    def test_no_open_decision_from_a_blocker_means_no_section(self) -> None:
        self.assertNotIn("## Open decisions", self.ok("brief", "T0", "-w", "alpha"))

    def test_it_is_there_with_no_acceptance_too(self) -> None:
        self.assertIn("- D002: transitive call", self.ok("brief", "T1", "-w", "alpha"))


class ResumeTests(WsTestCase):
    BLOCKED = "# T1\n\n- **Status:** blocked (needs a key)\n"

    def setUp(self) -> None:
        super().setUp()
        self.set_commands(test="true")
        self.new_ws()
        self.ok("decide", "Old call", "--why", "before the claim", "--by", "user")
        self.seed_ok([task("T1", 1, verify=["test"], acceptance=["works"], summary="Do the thing.")])
        self.commit_all("seed")

    def start(self) -> None:
        self.ok("claim", "--commit", "T1")
        self.ok("worktree", "create", "T1")
        self.tree = self.root / self.project().config.worktree_dir / "t1"

    def commit_at_tree(self, name: str, content: str) -> None:
        path = self.tree / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content)
        self.git_at(self.tree, "add", "-A")
        self.git_at(self.tree, "commit", "-q", "-m", name)

    def block(self) -> None:
        self.start()
        self.commit_at_tree("code.txt", "x")
        self.commit_at_tree("workstreams/alpha/evidence/T1.md", self.BLOCKED)
        self.ok("settle", "T1")
        self.ok("decide", "New call", "--why", "since the block", "--by", "user")

    def section(self, brief: str) -> str:
        return brief.split("## Resuming\n", 1)[1].split("\n## ", 1)[0]

    def finish_steps(self, brief: str) -> str:
        return brief.split("## When the work is done", 1)[1].split("\n## ", 1)[0]

    def test_a_blocked_tasks_brief_opens_with_what_a_resume_needs(self) -> None:
        self.block()
        brief = self.ok("brief", "T1", "-w", "alpha")
        head = brief.split("\n\n", 1)
        self.assertTrue(head[1].startswith("## Resuming\n"), brief[:120])
        section = self.section(brief)
        self.assertIn("Keep the finished work", section)
        self.assertRegex(section, r"\*\*Reason:\*\* needs a key.*task/t1")
        self.assertIn("- **Commits on `task/t1`:** 2 (", section)
        self.assertIn(f"- **Evidence:** `{self.tree / 'workstreams/alpha/evidence/T1.md'}`", section)
        self.assertRegex(section, r"  - D\d+: New call")
        self.assertNotIn("Old call", section)
        self.assertIn(str(self.ws_dir / "alpha" / "DECISIONS.md"), section)
        self.assertIn("## The task\n\nDo the thing.", brief)

    def test_a_branch_with_every_decision_lacks_none(self) -> None:
        self.start()
        self.commit_at_tree("workstreams/alpha/evidence/T1.md", self.BLOCKED)
        self.ok("settle", "T1")
        self.assertIn("`DECISIONS.md` lacks:** none", self.section(self.ok("brief", "T1", "-w", "alpha")))

    def test_its_finish_steps_update_the_evidence_rather_than_make_it_new(self) -> None:
        self.block()
        brief = self.ok("brief", "T1", "-w", "alpha")
        self.assertNotIn("ws evidence new", brief)
        self.assertIn("2. Update the existing evidence, "
                      f"`{self.tree / 'workstreams/alpha/evidence/T1.md'}`",
                      self.finish_steps(brief))

    def test_a_task_blocked_by_hand_with_no_evidence_is_still_told_to_write_it(self) -> None:
        self.ok("update", "T1", "--status", "blocked", "-w", "alpha")
        brief = self.ok("brief", "T1", "-w", "alpha")
        section = self.section(brief)
        self.assertIn("**Reason:** none recorded", section)
        self.assertIn("doesn't exist yet", section)
        self.assertIn("**Evidence:** none yet", section)
        self.assertIn("`DECISIONS.md` lacks:** none", section)
        self.assertIn("2. `ws evidence new T1 -w alpha`", self.finish_steps(brief))

    def test_a_todo_or_in_progress_brief_is_unchanged(self) -> None:
        todo = self.ok("brief", "T1", "-w", "alpha")
        self.start()
        self.commit_at_tree("code.txt", "x")
        self.ok("decide", "New call", "--why", "since the claim", "--by", "user")
        doing = self.ok("brief", "T1", "-w", "alpha")
        for brief in (todo, doing):
            self.assertTrue(brief.startswith("# T1: title of T1\nWorkstream `alpha`, phase 1, background.\n\n"
                                             "Do the thing.\n"), brief[:120])
            self.assertNotIn("## Resuming", brief)
            self.assertNotIn("## The task", brief)
            self.assertIn("2. `ws evidence new T1 -w alpha`, then fill in what it wrote: quote the "
                          "proof for each item.", self.finish_steps(brief))

    def test_ws_run_says_how_to_resume_and_not_to_unclaim(self) -> None:
        skill = protocol.skill_text("ws-run")
        self.assertIn("**Resuming a blocked task:** once the user answers, start a fresh worker "
                      "with the same prompt on the same worktree.", skill)
        self.assertIn("Never `ws unclaim <task> -w <id>` for this", skill)
