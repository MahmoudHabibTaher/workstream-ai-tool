"""Closing a decision: a new entry says so, and the old one's text never changes."""

from __future__ import annotations

import unittest

from tests.helpers import WsTestCase, evidence_text
from workstream import decisions, evidence, protocol
from workstream.cli import build_parser

LOG = """# Decisions

Settled judgment calls. Append, never rewrite.

---

## D013 (2026-01-01, T1): already settled

Because. **Closed.**

## D014 (2026-01-01, T2): still undecided

Someone must pick. **Open.**

## D015 (2026-01-02, T3): also undecided

Someone else must pick. **Open.**
"""


def ids(entries: list[dict]) -> list[str]:
    return [e["id"] for e in entries]


class OpenEntriesTests(unittest.TestCase):
    def test_a_later_entry_closes_an_open_one(self) -> None:
        text = LOG + "\n## D016 (2026-01-03, user): pick\n\nCloses: D015.\n\nWhy. **Closed.**\n"
        self.assertEqual(ids(decisions.open_entries(decisions.parse(text))), ["D014"])

    def test_an_earlier_entry_closes_nothing_after_it(self) -> None:
        text = ("## D001 (d, user): a\n\nCloses: D002.\n\nWhy. **Closed.**\n\n"
                "## D002 (d, user): b\n\nPick. **Open.**\n")
        self.assertEqual(ids(decisions.open_entries(decisions.parse(text))), ["D002"])

    def test_a_reason_quoting_a_closes_line_closes_nothing(self) -> None:
        text = LOG + "\n## D016 (2026-01-03, user): pick\n\nDon't write\nCloses: D015.\n"
        self.assertEqual(ids(decisions.open_entries(decisions.parse(text))), ["D014", "D015"])

    def test_a_closing_entry_can_itself_stay_open(self) -> None:
        entries = decisions.parse(LOG)
        body = decisions.closing_body(entries, "D015", "Next question. **Open.**")
        text = LOG + "\n" + decisions.render_entry(16, "d", "user", "pick", body)
        self.assertEqual(ids(decisions.open_entries(decisions.parse(text))), ["D014", "D016"])


class RenderEntryTests(unittest.TestCase):
    def render(self, body: str) -> str:
        return decisions.render_entry(16, "d", "user", "pick", body)

    def test_a_body_already_closed_keeps_one_marker(self) -> None:
        for body in ("B won. **Closed.**", "B won. **Closed.**\n\n"):
            with self.subTest(body=body):
                self.assertEqual(self.render(body),
                                 "## D016 (d, user): pick\n\nB won. **Closed.**\n")

    def test_a_body_quoting_the_marker_mid_text_gets_its_own(self) -> None:
        self.assertEqual(self.render("It said **Closed.** twice, wrongly."),
                         "## D016 (d, user): pick\n\n"
                         "It said **Closed.** twice, wrongly. **Closed.**\n")

    def test_an_open_entry_gets_no_closed_marker(self) -> None:
        rendered = self.render("Which one? **Open.**")
        self.assertEqual(rendered, "## D016 (d, user): pick\n\nWhich one? **Open.**\n")
        self.assertNotIn("**Closed.**", rendered)

    def test_a_plain_body_still_gets_the_marker(self) -> None:
        self.assertEqual(self.render("B won."),
                         "## D016 (d, user): pick\n\nB won. **Closed.**\n")

    def test_a_body_quoting_the_open_mark_mid_text_is_closed(self) -> None:
        rendered = self.render("The **Open.** mark is quoted.")
        self.assertEqual(rendered,
                         "## D016 (d, user): pick\n\nThe **Open.** mark is quoted. **Closed.**\n")
        self.assertEqual(decisions.open_entries(decisions.parse(rendered)), [])

    def test_a_body_ending_in_the_open_mark_stays_open(self) -> None:
        for body in ("Which one? **Open.**", "Which one? **Open.**  \n\n"):
            with self.subTest(body=body):
                self.assertTrue(decisions.is_open(body))
                rendered = self.render(body)
                self.assertEqual(rendered, "## D016 (d, user): pick\n\nWhich one? **Open.**\n")
                self.assertEqual(ids(decisions.open_entries(decisions.parse(rendered))), ["D016"])


class OpenMarkInEvidenceTests(unittest.TestCase):
    TASK = {"id": "T", "acceptance": []}

    def test_a_proposal_quoting_the_open_mark_mid_text_must_name_what_it_rejected(self) -> None:
        text = evidence_text("T", 0, proposals="### P1: a call\nThe **Open.** mark is quoted.")
        self.assertEqual(evidence.problems(text, self.TASK),
                         ["P1 doesn't say what was rejected (`Rejected: ...`)"])

    def test_a_proposal_ending_in_the_open_mark_needs_no_rejected_line(self) -> None:
        text = evidence_text("T", 0, proposals="### P1: a call\nWho decides? **Open.**")
        self.assertEqual(evidence.problems(text, self.TASK), [])


class ClosingTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.log = self.ws_dir / "alpha" / "DECISIONS.md"
        self.log.write_text(LOG)

    def close(self, closes: str, *extra: str) -> tuple[int, str, str]:
        return self.ws("decide", "pick B", "--why", "B won. Rejected: A.", "--closes", closes,
                       "-w", "alpha", *extra)

    def test_closing_adds_an_entry_and_leaves_the_old_text_alone(self) -> None:
        before = {e["id"]: e["text"] for e in decisions.parse(LOG)}
        code, out, err = self.close("D015")
        self.assertEqual(code, 0, err)
        self.assertIn("D016", out)
        text = self.log.read_text()
        self.assertTrue(text.startswith(LOG.rstrip()))
        after = decisions.parse(text)
        self.assertEqual({e["id"]: e["text"] for e in after[:-1]}, before)
        self.assertEqual(after[-1]["id"], "D016")
        self.assertIn("\nCloses: D015.\n", after[-1]["text"])
        self.assertIn("B won. Rejected: A. **Closed.**", after[-1]["text"])

    def test_several_ids_share_one_line(self) -> None:
        self.assertEqual(self.close("D015, D014,D015")[0], 0)
        self.assertIn("\nCloses: D015, D014.\n", self.log.read_text())
        self.assertEqual(self.ok("decisions", "--open", "-w", "alpha").strip(),
                         "(no matching decisions)")

    def test_open_lists_what_is_left(self) -> None:
        self.assertEqual(self.close("D015")[0], 0)
        listed = self.ok("decisions", "--open", "-w", "alpha")
        self.assertIn("## D014", listed)
        self.assertNotIn("## D015", listed)
        self.assertNotIn("## D013", listed)
        self.assertNotIn("## D016", listed)
        self.assertIn("## D015", self.ok("decisions", "-w", "alpha"))

    def test_open_narrows_for_too(self) -> None:
        self.write_queue([{"id": "T9", "phase": 1, "priority": 1, "title": "t", "status": "todo",
                           "findings": ["still undecided"]}])
        listed = self.ok("decisions", "--open", "--for", "T9", "-w", "alpha")
        self.assertIn("## D014", listed)
        self.assertNotIn("## D015", listed)

    def test_refusals_write_nothing(self) -> None:
        self.assertEqual(self.close("D015")[0], 0)
        text = self.log.read_text()
        for closes, needle in (("D099", "no decision D099"),
                               ("D015", "D015 is already closed"),
                               ("D013", "D013 is already closed"),
                               ("D016", "D016 is already closed"),
                               ("D014,D099", "no decision D099"),
                               ("D014,", "no decision (empty id)"),
                               ("", "no decision (empty id)")):
            with self.subTest(closes=closes):
                code, _, err = self.close(closes)
                self.assertEqual(code, 1)
                self.assertIn(needle, err)
                self.assertEqual(self.log.read_text(), text)

    def test_a_log_that_does_not_exist_is_not_created_by_a_refusal(self) -> None:
        self.log.unlink()
        self.assertIn("no decision D001", self.close("D001")[2])
        self.assertFalse(self.log.exists())

    def test_commit_carries_the_closes_line_and_a_refusal_commits_nothing(self) -> None:
        self.commit_all("log")
        head = self.git("rev-parse", "HEAD")
        code, _, err = self.close("D099", "--commit")
        self.assertEqual((code, self.git("rev-parse", "HEAD")), (1, head), err)
        self.assertEqual(self.git("status", "--porcelain"), "")
        code, out, err = self.close("D015", "--commit")
        self.assertEqual(code, 0, err)
        self.assertIn("committed", out)
        self.assertIn("Closes: D015.", self.git("show", "HEAD:workstreams/alpha/DECISIONS.md"))


class FromAWorktreeTests(WsTestCase):
    """The worktree's copy of the log stops at the claim; `ws decisions` reads past it."""

    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.seed_ok([{"id": "T1", "phase": 1, "priority": 1, "title": "t", "status": "todo",
                       "findings": ["the cache"]},
                      {"id": "T2", "phase": 1, "priority": 2, "title": "u", "status": "todo"}])
        self.log = self.ws_dir / "alpha" / "DECISIONS.md"
        self.log.write_text(LOG)
        self.commit_all("seed")
        self.ok("claim", "T1", "-w", "alpha")
        self.commit_all("claim")
        self.ok("worktree", "create", "T1", "-w", "alpha")
        self.tree = self.root / self.project().config.worktree_dir / "t1"
        self.frozen = self.tree / "workstreams" / "alpha" / "DECISIONS.md"

    def at_tree(self, *argv: str) -> str:
        code, out, err = self.ws_at(self.tree, *argv)
        self.assertEqual(code, 0, out + err)
        return out

    def after_the_claim(self, title: str, why: str) -> None:
        self.ok("decide", title, "--why", why, "--by", "T2", "-w", "alpha", "--commit")
        self.assertNotIn(title, self.frozen.read_text())

    def test_an_entry_recorded_after_the_claim_shows(self) -> None:
        self.after_the_claim("Use the new store", "The old one lies.")
        listed = self.at_tree("decisions", "-w", "alpha")
        self.assertIn("## D016", listed)
        self.assertIn("Use the new store", listed)

    def test_open_sees_an_entry_opened_after_the_claim(self) -> None:
        self.after_the_claim("Which store", "Someone must pick. **Open.**")
        listed = self.at_tree("decisions", "--open", "-w", "alpha")
        self.assertIn("Which store", listed)
        self.assertIn("## D014", listed)

    def test_open_sees_an_entry_closed_after_the_claim(self) -> None:
        self.ok("decide", "pick B", "--why", "B won.", "--closes", "D015", "-w", "alpha", "--commit")
        self.assertIn("## D015", self.at_tree("decisions", "-w", "alpha"))
        listed = self.at_tree("decisions", "--open", "-w", "alpha")
        self.assertIn("## D014", listed)
        self.assertNotIn("## D015", listed)

    def test_for_sees_an_entry_recorded_after_the_claim(self) -> None:
        self.after_the_claim("Drop the old store", "It breaks the cache.")
        self.after_the_claim("Rename the logs", "Nothing to do with it.")
        listed = self.at_tree("decisions", "--for", "T1", "-w", "alpha")
        self.assertIn("Drop the old store", listed)
        self.assertNotIn("Rename the logs", listed)

    def test_open_and_for_together_see_it(self) -> None:
        self.after_the_claim("Which store", "It breaks the cache. **Open.**")
        self.after_the_claim("Rename the logs", "Which name? **Open.**")
        listed = self.at_tree("decisions", "--open", "--for", "T1", "-w", "alpha")
        self.assertIn("Which store", listed)
        self.assertNotIn("Rename the logs", listed)

    def test_for_finds_a_task_added_after_the_claim(self) -> None:
        self.after_the_claim("Which store", "Settled for T3.")
        self.ok("add", "--id", "T3", "--title", "later", "--phase", "1", "--priority", "3",
                "-w", "alpha")
        self.commit_all("add T3")
        self.assertNotIn('"T3"', (self.tree / "workstreams/alpha/tasks_list.json").read_text())
        self.assertIn("Which store", self.at_tree("decisions", "--for", "T3", "-w", "alpha"))


class SkillTests(unittest.TestCase):
    def test_ws_coordinate_names_both_and_they_parse(self) -> None:
        text = protocol.skill_text("ws-coordinate")
        self.assertIn("`ws decisions --open -w <id>`", text)
        self.assertIn('`ws decide "..." --why "..." --closes D015,D014 -w <id>`', text)
        parser = build_parser()
        self.assertTrue(parser.parse_args(["decisions", "--open", "-w", "x"]).open)
        args = parser.parse_args(["decide", "x", "--why", "x", "--closes", "D015,D014", "-w", "x"])
        self.assertEqual(args.closes, "D015,D014")
