"""Plan sections, `seed --from-plan`, the decisions log and evidence files."""

from __future__ import annotations

import json
import unittest

from tests.helpers import WsTestCase, evidence_text, task
from workstream import decisions, evidence, plan
from workstream.errors import WsError

PLAN = """# Thing: plan

## Traps

### T1: the cache lies
Don't trust it.

### T10: another
Other text.

## Design

```text
## not a heading
```

### D-API: the shape
It is round.

```json ws-tasks
[{"id": "X-01", "phase": 1, "priority": 10, "title": "first", "findings": ["T1"]}]
```

```text ws-decisions
The user ruled out caching.
```
"""


class SectionTests(unittest.TestCase):
    def test_finds_a_section_by_the_id_it_starts_with(self) -> None:
        self.assertIn("Don't trust it", plan.find_section(PLAN, "T1").text)
        self.assertNotIn("Other text", plan.find_section(PLAN, "T1").text)
        self.assertIn("It is round", plan.find_section(PLAN, "D-API").text)

    def test_an_id_must_match_whole(self) -> None:
        self.assertEqual(plan.find_section(PLAN, "T10").title, "T10: another")
        self.assertIsNone(plan.find_section(PLAN, "T"))

    def test_a_section_stops_at_the_next_heading_at_its_level(self) -> None:
        traps = plan.find_section(PLAN, "Traps").text
        self.assertIn("Other text", traps)
        self.assertNotIn("the shape", traps)

    def test_a_heading_inside_a_fence_is_not_one(self) -> None:
        self.assertIsNone(plan.find_section(PLAN, "not"))

    def test_a_table_row_is_found_by_its_first_cell(self) -> None:
        text = "# Plan\n\n| Id | What |\n|---|---|\n| G70 | wrong |\n| G7 | right |\n"
        found = plan.find_section(text, "G7")
        self.assertEqual(found.text, "| G7 | right |")
        self.assertEqual(found.title, "G7")
        self.assertEqual(plan.find_section(text, "G70").text, "| G70 | wrong |")

    def test_a_table_row_can_start_with_the_ref_and_go_on(self) -> None:
        text = "| G7: the cache | high |\n"
        self.assertEqual(plan.find_section(text, "G7").text, "| G7: the cache | high |")

    def test_a_table_row_only_counts_on_its_first_cell_and_as_a_whole_word(self) -> None:
        text = "| G70 | wrong |\n| other | G7 |\n"
        self.assertIsNone(plan.find_section(text, "G7"))
        self.assertIsNone(plan.find_section(text, "G"))

    def test_a_table_row_inside_a_fence_is_not_one(self) -> None:
        self.assertIsNone(plan.find_section("```\n| G7 | fenced |\n```\n", "G7"))

    def test_a_heading_wins_over_a_table_row(self) -> None:
        text = "| G7 | the row comes first |\n\n### G7: the heading\nBody.\n"
        found = plan.find_section(text, "G7")
        self.assertEqual(found.title, "G7: the heading")
        self.assertIn("Body.", found.text)


class SplitTests(unittest.TestCase):
    def test_splits_the_blocks_out(self) -> None:
        body, new_tasks, scope, _ = plan.parse_plan(PLAN)
        self.assertNotIn("ws-tasks", body)
        self.assertNotIn("ws-decisions", body)
        self.assertIn("## not a heading", body)
        self.assertEqual(new_tasks[0]["id"], "X-01")
        self.assertEqual(scope, "The user ruled out caching.")

    def test_refusals(self) -> None:
        cases = {"# no blocks\n": "no ```json ws-tasks",
                 "```json ws-tasks\nnot json\n```\n": "not valid JSON",
                 "```json ws-tasks\n[]\n```\n": "non-empty array",
                 "```json ws-tasks\n[]\n": "never closed",
                 "```json ws-tasks\n[{}]\n```\n```json ws-tasks\n[{}]\n```\n": "two ws-tasks",
                 "```text ws-other\nx\n```\n": "unknown plan block"}
        for text, expected in cases.items():
            with self.assertRaisesRegex(WsError, expected):
                plan.parse_plan(text)

    def test_a_block_named_inside_another_fence_stays_text(self) -> None:
        text = "````md\n```json ws-tasks\n[]\n```\n````\n```json ws-tasks\n[{\"id\": \"A\"}]\n```\n"
        body, new_tasks, _, _ = plan.parse_plan(text)
        self.assertIn("````md", body)
        self.assertEqual(new_tasks, [{"id": "A"}])


class SeedFromPlanTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.ok("new", "alpha", "--title", "A", "--summary", "s", "--prefix", "X")
        self.folder = self.ws_dir / "alpha"
        self.plan_file = self.root.parent / "plan.md"
        self.plan_file.write_text(PLAN)

    def test_writes_every_file_and_leaves_validate_with_nothing_to_say(self) -> None:
        self.ok("seed", "--from-plan", str(self.plan_file))
        self.assertIn("the cache lies", (self.folder / "PLAN.md").read_text())
        self.assertNotIn("ws-tasks", (self.folder / "PLAN.md").read_text())
        self.assertEqual(self.by_id("X-01")["title"], "first")
        self.assertIn("ruled out caching", (self.folder / "DECISIONS.md").read_text())
        self.assertIn("X-01", (self.folder / "session_handoff.md").read_text())
        self.ok("validate")

    def _seed_citing(self, *rows: dict) -> None:
        start = PLAN.index('[{"id"')
        end = PLAN.index("]\n```\n\n```text") + 1
        self.plan_file.write_text(PLAN[:start] + json.dumps(list(rows)) + PLAN[end:])

    def test_validate_warns_once_for_a_workstream_listing_what_open_tasks_cite(self) -> None:
        self._seed_citing(task("X-01", 10, findings=["T1", "G7"]),
                          task("X-02", 20, findings=["G7", "G8"]))
        self.ok("seed", "--from-plan", str(self.plan_file))
        lines = [line for line in self.ok("validate").splitlines() if "PLAN.md" in line]
        self.assertEqual(lines, ["  - alpha: open tasks cite what PLAN.md doesn't have: G7, G8"])

    def test_seed_prints_the_same_warning(self) -> None:
        self._seed_citing(task("X-01", 10, findings=["T1", "G7"]),
                          task("X-02", 20, findings=["G7", "G8"]))
        out = self.ok("seed", "--from-plan", str(self.plan_file))
        lines = [line for line in out.splitlines() if "PLAN.md" in line and line.startswith("warning")]
        self.assertEqual(lines, ["warning: alpha: open tasks cite what PLAN.md doesn't have: G7, G8"])

    def test_a_ref_in_a_table_row_gets_no_warning(self) -> None:
        self._seed_citing(task("X-01", 10, findings=["G7"]))
        self.plan_file.write_text(self.plan_file.read_text() + "\n| G7 | a finding |\n")
        self.assertNotIn("PLAN.md doesn't", self.ok("seed", "--from-plan", str(self.plan_file)))
        self.assertNotIn("PLAN.md doesn't", self.ok("validate"))

    def test_a_done_task_citation_gets_no_warning(self) -> None:
        self._seed_citing(task("X-01", 10, findings=["G7"]), task("X-02", 20, findings=["T1"]))
        self.assertIn("G7", self.ok("seed", "--from-plan", str(self.plan_file)))
        queue = self.queue()
        queue["tasks"][0]["status"] = "done"
        (self.folder / "tasks_list.json").write_text(json.dumps(queue))
        self.assertNotIn("PLAN.md doesn't", self.ws("validate")[1])

    def test_a_workstream_with_no_written_plan_gets_no_warning(self) -> None:
        self.ok("seed", str(self._seed_file()))
        plan_path = self.folder / "PLAN.md"
        self.assertIn("{{", plan_path.read_text())
        self.assertNotIn("PLAN.md doesn't", self.ws("validate")[1])
        plan_path.unlink()
        self.assertNotIn("PLAN.md doesn't", self.ws("validate")[1])

    def _seed_file(self):
        seed = self.root.parent / "seed.json"
        seed.write_text(json.dumps([task("X-01", 10, findings=["G7"])]))
        return seed

    def test_it_does_not_warn_about_files_tasks_will_create(self) -> None:
        self.plan_file.write_text(PLAN.replace('"findings": ["T1"]',
                                               '"findings": ["T1"], "files": ["later.py"]'))
        self.assertNotIn("does not exist", self.ok("seed", "--from-plan", str(self.plan_file)))

    def test_it_still_passes_on_other_warnings(self) -> None:
        two = ('[{"id": "X-01", "phase": 1, "priority": 10, "title": "a", "files": ["README"]},'
               ' {"id": "X-02", "phase": 1, "priority": 20, "title": "b", "files": ["README"]}]')
        start = PLAN.index('[{"id"')
        end = PLAN.index("]\n```\n\n```text") + 1
        self.plan_file.write_text(PLAN[:start] + two + PLAN[end:])
        (self.root / "README").write_text("x")
        self.assertIn("warning:", self.ok("seed", "--from-plan", str(self.plan_file)))

    def test_a_task_with_problems_changes_nothing(self) -> None:
        self.plan_file.write_text(PLAN.replace('"X-01"', '"WRONG-01"'))
        self.assertIn("lacks the prefix", self.fails("seed", "--from-plan", str(self.plan_file)))
        self.assertIn("{{", (self.folder / "PLAN.md").read_text())
        self.assertEqual(self.queue()["tasks"], [])

    def test_an_approved_plan_is_not_overwritten(self) -> None:
        self.ok("seed", "--from-plan", str(self.plan_file))
        self.assertIn("immutable", self.fails("seed", "--from-plan", str(self.plan_file)))

    def test_a_plan_with_a_placeholder_is_refused(self) -> None:
        self.plan_file.write_text(PLAN + "\n{{TODO}}\n")
        self.assertIn("placeholder", self.fails("seed", "--from-plan", str(self.plan_file)))

    def test_lite_tier_only_gets_decisions_when_there_are_some(self) -> None:
        self.ok("new", "lite", "--title", "L", "--summary", "s", "--tier", "lite")
        self.ok("seed", "-w", "lite", "--from-plan", str(self.plan_file))
        self.assertIn("D001", (self.ws_dir / "lite" / "DECISIONS.md").read_text())

    def test_takes_a_file_or_a_plan_not_both(self) -> None:
        self.assertIn("one of them", self.fails("seed"))
        self.assertIn("one of them", self.fails("seed", "x.json", "--from-plan", "y.md"))

    def test_plain_seed_still_works(self) -> None:
        path = self.root.parent / "seed.json"
        path.write_text(json.dumps([task("X-09", 90)]))
        self.ok("seed", str(path))
        self.assertEqual(self.by_id("X-09")["priority"], 90)


LOG = """# Decisions

## D001 (2026-01-01, user): scope
Only the API.

## D002 (2026-01-02, T-01): use a queue
Touches `src/q.py`. **Closed.**

## D003 (2026-01-03, T-02): retries
See T7 for why.

## D004 (2026-01-04, T-09): unrelated
Nothing here.
"""


class DecisionTests(unittest.TestCase):
    def test_parses_entries(self) -> None:
        entries = decisions.parse(LOG)
        self.assertEqual([e["id"] for e in entries], ["D001", "D002", "D003", "D004"])
        self.assertEqual((entries[1]["who"], entries[1]["title"]), ("T-01", "use a queue"))
        self.assertTrue(entries[0]["text"].endswith("Only the API."))

    def test_next_number(self) -> None:
        self.assertEqual(decisions.next_number(decisions.parse(LOG)), 5)
        self.assertEqual(decisions.next_number([]), 1)

    def relevant(self, **fields) -> list[str]:
        t = {"id": "T-50", **fields}
        return [e["id"] for e in decisions.relevant(decisions.parse(LOG), t)]

    def test_the_users_calls_always_apply(self) -> None:
        self.assertEqual(self.relevant(), ["D001"])

    def test_filters_by_blocker_file_and_finding(self) -> None:
        self.assertIn("D002", self.relevant(blockedBy=["T-01"]))
        self.assertIn("D002", self.relevant(files=["src/q.py"]))
        self.assertIn("D003", self.relevant(findings=["T7"]))
        self.assertNotIn("D003", self.relevant(findings=["T70"]))
        self.assertNotIn("D004", self.relevant(files=["src/q.py"], findings=["T7"]))


    def test_an_unfilled_template_entry_is_not_a_decision(self) -> None:
        entries = decisions.parse("## D001 (2026-01-01, user): scope\n\n{{SCOPE_DECISIONS: x}}\n")
        self.assertEqual(decisions.relevant(entries, {"id": "T-50"}), [])


class EvidenceTests(unittest.TestCase):
    TASK = {"id": "T-01", "acceptance": ["one", {"text": "two", "kind": "manual"}]}

    def test_a_good_file_has_no_problems(self) -> None:
        self.assertEqual(evidence.problems(evidence_text("T-01", 2), self.TASK), [])

    def test_the_skeleton_fails_until_filled(self) -> None:
        text = evidence.skeleton(self.TASK)
        self.assertIn("1. one ->", text)
        self.assertIn("2. two (manual) ->", text)
        self.assertIn("placeholder", evidence.problems(text, self.TASK)[0])

    def test_problems(self) -> None:
        self.assertIn("no evidence/T-01.md", evidence.problems(None, self.TASK)[0])
        self.assertIn("Status", evidence.problems("nothing", self.TASK)[0])
        self.assertIn("item 2 is missing", evidence.problems(evidence_text("T-01", 1), self.TASK)[0])

    def test_an_item_with_no_proof_fails(self) -> None:
        text = evidence_text("T-01", 2).replace("item 2 -> ran it: `ok`", "item 2")
        self.assertIn("item 2 has nothing quoted", evidence.problems(text, self.TASK)[0])

    def test_proof_may_be_on_the_lines_below(self) -> None:
        text = evidence_text("T-01", 2).replace("item 2 -> ran it: `ok`", "item 2\n   ```\n   ok\n   ```")
        self.assertEqual(evidence.problems(text, self.TASK), [])

    def test_blocked_needs_a_reason_and_nothing_else(self) -> None:
        self.assertEqual(evidence.problems("- **Status:** blocked (no key)\n", self.TASK), [])
        self.assertIn("without a reason", evidence.problems("- **Status:** blocked\n", self.TASK)[0])
        parsed = evidence.parse("- **Status:** blocked (no key)\n")
        self.assertEqual((parsed["status"], parsed["reason"]), ("blocked", "no key"))

    def test_proposals(self) -> None:
        text = evidence_text("T-01", 2, proposals="### P1: a call\nWhy. Rejected: b.\n\n"
                                                    "### P2: c\nD. Rejected: e.")
        parsed = evidence.parse(text)
        self.assertEqual([p["id"] for p in parsed["proposals"]], ["P1", "P2"])
        self.assertEqual(parsed["proposals"][0]["body"], "Why. Rejected: b.")
        self.assertEqual(evidence.problems(text, self.TASK), [])

    def test_a_proposal_without_a_reason_fails(self) -> None:
        text = evidence_text("T-01", 2, proposals="### P1: a call\n")
        self.assertIn("P1 has no reason", evidence.problems(text, self.TASK)[0])

    def test_rewriting_ids_is_whole_word(self) -> None:
        self.assertEqual(evidence.rewrite_ids("P1 and P10; see P1.", {"P1": "D007"}),
                         "D007 and P10; see D007.")

    def test_the_skeletons_help_text_proposes_nothing(self) -> None:
        self.assertEqual(evidence.parse(evidence.skeleton(self.TASK))["proposals"], [])

    def with_texts(self, body: str) -> str:
        return evidence_text("T-01", 2) + f"\n## Text to apply\n\n{body}\n"

    def test_text_to_apply_comes_back_whole_for_each_file(self) -> None:
        first = "# A rule\n\n## Acceptance\n\n1. not an item\n\n### Not a file\n\n  indented {{x}} P1\n"
        second = "## Gotchas\n\nnot a gotcha"
        text = self.with_texts(f"### `.claude/rules/a.md`\n{first}\n### `b.md`\n{second}")
        parsed = evidence.parse(text)
        self.assertEqual(parsed["texts"], [{"path": ".claude/rules/a.md", "text": first.rstrip("\n")},
                                           {"path": "b.md", "text": second}])
        self.assertEqual(sorted(parsed["items"]), [1, 2])
        self.assertEqual(parsed["gotchas"], "None.")
        self.assertEqual(evidence.problems(text, self.TASK), [])

    def test_the_skeletons_text_to_apply_is_empty_and_comes_last(self) -> None:
        text = evidence.skeleton(self.TASK)
        self.assertEqual(evidence.parse(text)["texts"], [])
        self.assertEqual(text.rsplit("\n## ", 1)[1].splitlines()[0], "Text to apply")
        filled = text.replace("{{done, or blocked (the reason)}}", "done").replace(
            "{{command and quoted output}}", "ran it")
        self.assertEqual(evidence.problems(filled, self.TASK), [])

    def test_evidence_with_no_text_to_apply_still_parses(self) -> None:
        text = evidence_text("T-01", 2)
        self.assertEqual(evidence.parse(text)["texts"], [])
        self.assertEqual(evidence.problems(text, self.TASK), [])

    def test_text_to_apply_shape_problems(self) -> None:
        cases = {"loose text": "no file", "### not a path\ntext": "no file",
                 "### `a.md`\n\n### `b.md`\nx": "no text for a.md",
                 "### `/etc/a.md`\nx": "absolute path: /etc/a.md",
                 "### `C:\\a.md`\nx": "absolute path",
                 "### `../a.md`\nx": "path with `..`: ../a.md",
                 "### `src/../../a.md`\nx": "path with `..`"}
        for body, expected in cases.items():
            with self.subTest(body):
                found = evidence.problems(self.with_texts(body), self.TASK)
                self.assertEqual(len(found), 1, found)
                self.assertIn(expected, found[0])

    def test_a_name_merely_starting_with_two_dots_is_fine(self) -> None:
        self.assertEqual(evidence.problems(self.with_texts("### `a/..b.md`\nx"), self.TASK), [])

    def test_settling_ids_leaves_text_to_apply_alone(self) -> None:
        text = "See P1.\n\n## Text to apply\n\n### `a.md`\nP1 stays.\n"
        self.assertEqual(evidence.rewrite_ids(text, {"P1": "D007"}),
                         "See D007.\n\n## Text to apply\n\n### `a.md`\nP1 stays.\n")


if __name__ == "__main__":
    unittest.main()
