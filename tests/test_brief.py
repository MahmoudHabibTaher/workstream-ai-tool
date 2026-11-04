"""What a brief carries over from a finished blocker's gotchas."""

from __future__ import annotations

from tests.helpers import WsTestCase, evidence_text, task
from workstream.brief import MAX_GOTCHA_CHARS

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
