"""The project config: defaults, and that a typo is an error rather than a silent no-op."""

from __future__ import annotations

import tomllib
import unittest

from tests.helpers import WsTestCase
from workstream.config import Config, parse_config, render_default
from workstream.errors import WsError


class ParseTests(unittest.TestCase):
    def test_an_empty_file_reads_as_the_defaults(self) -> None:
        self.assertEqual(parse_config({}), Config())

    def test_production_defaults_to_the_integration_branch(self) -> None:
        config = parse_config({"branches": {"integration": "trunk"}})
        self.assertEqual((config.integration, config.production), ("trunk", "trunk"))

    def test_reads_every_section(self) -> None:
        config = parse_config({
            "schema": 1,
            "paths": {"workstreams": "plans"},
            "branches": {"integration": "develop", "production": "main",
                         "task": "wip/{slug}", "merge": "squash"},
            "commands": {"test": "make test"},
            "adequacy": {"behaviour": ["test"]},
            "requires": {"values": ["gpu", "user"], "foreground": ["user"]},
            "worktree": {"setup": ["make deps"]},
            "parallel": {"max_workers": 5},
            "release": {"mode": "runbook", "runbook": "docs/release.md"},
            "baseline": {"lint": {"parser": "sarif"}},
        })
        self.assertEqual(config.workstreams_dir, "plans")
        self.assertEqual((config.integration, config.production, config.merge),
                         ("develop", "main", "squash"))
        self.assertEqual(config.commands, {"test": "make test"})
        self.assertEqual(config.adequacy, {"behaviour": ["test"]})
        self.assertEqual(config.requires_values, ("gpu", "user"))
        self.assertEqual(config.worktree_setup, ("make deps",))
        self.assertEqual(config.max_workers, 5)
        self.assertEqual((config.release_mode, config.release_runbook),
                         ("runbook", "docs/release.md"))
        self.assertEqual(config.baseline_parsers, {"lint": {"parser": "sarif"}})

    def test_branch_for_follows_the_pattern(self) -> None:
        config = parse_config({"branches": {"task": "wip/{slug}"}})
        self.assertEqual(config.branch_for("SP-01"), "wip/sp-01")
        self.assertEqual(config.task_branch_glob(), "wip/*")

    def test_refuses_what_would_silently_turn_a_rule_off(self) -> None:
        cases = [
            ({"comands": {}}, "unknown key(s): comands"),
            ({"schema": 2}, "schema 2 is not supported"),
            ({"branches": "main"}, "[branches] must be a table"),
            ({"branches": {"integration": 1}}, "branches.integration must be a string"),
            ({"branches": {"task": "task"}}, "branches.task must contain {slug}"),
            ({"branches": {"merge": "rebase"}}, "branches.merge must be one of"),
            ({"commands": {"test": ""}}, "commands.test must be a non-empty string"),
            ({"commands": {"test": 1}}, "commands.test must be a non-empty string"),
            ({"adequacy": {"behaviour": "test"}}, "adequacy.behaviour must be a list of strings"),
            ({"requires": {"values": ["a"], "foreground": ["b"]}},
             "requires.foreground names unknown value(s): b"),
            ({"parallel": {"max_workers": 0}}, "parallel.max_workers must be a positive integer"),
            ({"parallel": {"max_workers": True}}, "parallel.max_workers must be a positive integer"),
            ({"release": {"mode": "always"}}, "release.mode must be one of"),
            ({"baseline": {"lint": {"parser": "xml"}}}, "baseline.lint.parser must be one of"),
            ({"baseline": {"lint": "regex"}}, "baseline.lint must be a table"),
        ]
        for raw, message in cases:
            with self.subTest(raw=raw):
                with self.assertRaises(WsError) as caught:
                    parse_config(raw)
                self.assertIn(message, str(caught.exception))

    def test_the_default_file_parses(self) -> None:
        config = parse_config(tomllib.loads(render_default("trunk")))
        self.assertEqual((config.integration, config.production), ("trunk", "trunk"))
        self.assertEqual(config.commands, {})


class FileTests(WsTestCase):
    def test_a_syntax_error_is_an_error_not_a_traceback(self) -> None:
        (self.root / ".workstream/config.toml").write_text("not = = toml")
        self.assertIn(".workstream/config.toml", self.fails("list"))


if __name__ == "__main__":
    unittest.main()
