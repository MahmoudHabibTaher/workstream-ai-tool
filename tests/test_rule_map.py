"""M3's definition of done, kept true: every rule from the source harnesses has a home, and each
home really exists. Removing a skill line a rule depends on fails here."""

from __future__ import annotations

import importlib
import re
import unittest
from pathlib import Path

from workstream import protocol

MAP = Path(__file__).resolve().parent.parent / "docs" / "rule-map.md"
ROW_RE = re.compile(r"^\| (subsonic|kotlin|both) \| (.+?) \| (\w+) \| (.+) \|$")
WHERE_RE = re.compile(r'^([\w-]+): "(.*)"$')
KINDS = {"code", "skill", "protocol", "project", "deleted"}


def rows() -> list[tuple[str, str, str, str]]:
    return [m.groups() for line in MAP.read_text().splitlines() if (m := ROW_RE.match(line))]


class RuleMapTests(unittest.TestCase):
    def test_the_map_covers_both_harnesses(self) -> None:
        sources = [r[0] for r in rows()]
        self.assertGreater(len(sources), 120)
        self.assertGreater(sources.count("subsonic"), 30)
        self.assertGreater(sources.count("the Kotlin harness"), 30)

    def test_every_row_has_a_known_kind(self) -> None:
        self.assertEqual([r for r in rows() if r[2] not in KINDS], [])

    def test_every_table_row_parses(self) -> None:
        """A row the pattern misses would never be checked."""
        lines = [line for line in MAP.read_text().splitlines()
                 if re.match(r"^\| (subsonic|kotlin|both) \|", line)]
        self.assertEqual(len(lines), len(rows()))

    def test_code_rows_name_something_that_exists(self) -> None:
        missing = []
        for _, rule, kind, where in rows():
            if kind != "code":
                continue
            module, _, name = where.partition(".")
            if not hasattr(importlib.import_module(f"workstream.{module}"), name):
                missing.append(f"{rule}: {where}")
        self.assertEqual(missing, [])

    def test_skill_rows_quote_text_in_that_skill(self) -> None:
        missing = []
        for _, rule, kind, where in rows():
            if kind != "skill":
                continue
            match = WHERE_RE.match(where)
            if match is None or match[2] not in protocol.skill_text(match[1]):
                missing.append(f"{rule}: {where}")
        self.assertEqual(missing, [])

    def test_protocol_rows_quote_text_in_that_section(self) -> None:
        missing = []
        for _, rule, kind, where in rows():
            if kind != "protocol":
                continue
            match = WHERE_RE.match(where)
            if match is None or match[2] not in protocol.section(match[1]):
                missing.append(f"{rule}: {where}")
        self.assertEqual(missing, [])

    def test_a_deleted_or_handed_off_rule_says_why(self) -> None:
        self.assertEqual([r for r in rows() if r[2] in ("deleted", "project") and len(r[3]) < 10],
                         [])


if __name__ == "__main__":
    unittest.main()
