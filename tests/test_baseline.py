"""Telling new findings from known ones: the parsers and the judgement, without running anything."""

from __future__ import annotations

import json
import os
import tempfile
import time
import unittest
from pathlib import Path

from workstream import baseline as b

SARIF = json.dumps({"runs": [{"results": [
    {"ruleId": "R1", "message": {"text": "bad"},
     "locations": [{"physicalLocation": {"artifactLocation": {"uri": "file:///repo/src/a.py"}}}]},
    {"ruleId": "R2", "message": {"text": "worse"}},
]}]})
JUNIT = """<testsuites><testsuite>
<testcase classname="pkg.A" name="passes"/>
<testcase classname="pkg.A" name="fails"><failure message="no"/></testcase>
<testcase classname="pkg.B" name="errors"><error/></testcase>
</testsuite></testsuites>"""
REGEX_ENTRY = {"parser": "regex", "pattern": r"^(?P<file>\S+):\d+: (?P<message>.*)$"}


class ParserTests(unittest.TestCase):
    def test_regex_fingerprints_only_the_named_groups(self) -> None:
        found = b.parse_regex("src/a.py:10: unused\nnoise\nsrc/a.py:99: unused\n",
                              REGEX_ENTRY["pattern"])
        self.assertEqual(found, ["src/a.py | unused", "src/a.py | unused"])

    def test_regex_without_named_groups_uses_the_whole_match(self) -> None:
        self.assertEqual(b.parse_regex("x warning: y\n", r"warning: \w+"), ["warning: y"])

    def test_regex_reads_through_colour_codes(self) -> None:
        found = b.parse_regex("\x1b[31msrc/a.py:1: bad\x1b[0m\n", REGEX_ENTRY["pattern"])
        self.assertEqual(found, ["src/a.py | bad"])

    def test_sarif(self) -> None:
        self.assertEqual(b.parse_sarif(SARIF), ["R1 | /repo/src/a.py | bad", "R2 |  | worse"])

    def test_sarif_refuses_what_is_not_sarif(self) -> None:
        for raw in ("[]", "{}", "not json"):
            with self.assertRaises(ValueError):
                b.parse_sarif(raw)

    def test_junit_lists_failures_and_errors_only(self) -> None:
        self.assertEqual(b.parse_junit(JUNIT), ["pkg.A::fails", "pkg.B::errors"])


class ReadFindingsTests(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name).resolve()
        self.entry = {"parser": "junit", "report": "out/*.xml"}

    def test_exit_code_reads_nothing(self) -> None:
        self.assertEqual(b.read_findings({"parser": "exit-code"}, "x", self.root, 0), (None, ""))

    def test_a_report_this_run_did_not_write_is_not_read(self) -> None:
        (self.root / "out").mkdir()
        old = self.root / "out" / "a.xml"
        old.write_text(JUNIT)
        os.utime(old, (1000, 1000))
        found, problem = b.read_findings(self.entry, "", self.root, time.time())
        self.assertIsNone(found)
        self.assertIn("wrote no report", problem)

    def test_several_reports_are_combined(self) -> None:
        (self.root / "out").mkdir()
        (self.root / "out" / "a.xml").write_text(JUNIT)
        (self.root / "out" / "b.xml").write_text(JUNIT)
        found, _ = b.read_findings(self.entry, "", self.root, time.time())
        self.assertEqual(len(found), 4)

    def test_a_broken_report_is_a_problem_not_a_crash(self) -> None:
        (self.root / "out").mkdir()
        (self.root / "out" / "a.xml").write_text("<testsuite")
        found, problem = b.read_findings(self.entry, "", self.root, time.time())
        self.assertIsNone(found)
        self.assertIn("cannot read a.xml", problem)

    def test_a_worktree_path_reads_the_same_as_the_main_checkout(self) -> None:
        log = f"{self.root}/src/a.py:3: bad\n"
        found, _ = b.read_findings(REGEX_ENTRY, log, self.root, 0)
        self.assertEqual(found, ["src/a.py | bad"])


class JudgeTests(unittest.TestCase):
    def judge(self, code, findings, known=(), problem="", entry=None):
        return b.judge(code, entry or REGEX_ENTRY, findings, problem, list(known))

    def test_exit_code_parser(self) -> None:
        exit_code = {"parser": "exit-code"}
        self.assertEqual(self.judge(0, None, entry=exit_code)["verdict"], b.PASS)
        self.assertEqual(self.judge(1, None, entry=exit_code)["verdict"], b.FAIL)

    def test_a_known_red_command_never_passes_under_the_exit_code_parser(self) -> None:
        self.assertEqual(self.judge(1, None, known=["x"], entry={"parser": "exit-code"})["verdict"],
                         b.FAIL)

    def test_timeout_fails(self) -> None:
        self.assertEqual(self.judge(None, None)["reason"], "timed out")

    def test_only_known_findings_pass_despite_the_exit_code(self) -> None:
        result = self.judge(1, ["a", "b"], known=["a", "b", "c"])
        self.assertEqual(result["verdict"], b.KNOWN_ONLY)
        self.assertEqual((result["known"], result["gone"]), (2, 1))

    def test_a_new_finding_fails(self) -> None:
        result = self.judge(1, ["a", "new"], known=["a"])
        self.assertEqual(result["verdict"], b.FAIL)
        self.assertEqual(result["new"], ["new"])

    def test_a_new_finding_fails_even_on_exit_zero(self) -> None:
        self.assertEqual(self.judge(0, ["new"])["verdict"], b.FAIL)

    def test_a_second_copy_of_a_known_finding_is_new(self) -> None:
        self.assertEqual(self.judge(1, ["a", "a"], known=["a"])["new"], ["a"])

    def test_a_failure_with_nothing_parsed_is_a_crash_not_a_pass(self) -> None:
        result = self.judge(2, [], known=["a"])
        self.assertEqual(result["verdict"], b.FAIL)
        self.assertIn("crash", result["reason"])

    def test_a_parser_problem_fails_even_on_exit_zero(self) -> None:
        self.assertEqual(self.judge(0, None, problem="no report")["verdict"], b.FAIL)

    def test_the_new_list_is_capped_but_counted(self) -> None:
        many = [f"f{n}" for n in range(b.MAX_RECORDED_NEW + 5)]
        result = self.judge(1, many)
        self.assertEqual(len(result["new"]), b.MAX_RECORDED_NEW)
        self.assertEqual(result["newCount"], b.MAX_RECORDED_NEW + 5)


if __name__ == "__main__":
    unittest.main()
