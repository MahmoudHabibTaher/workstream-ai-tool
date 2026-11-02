"""Profiles are data, and rendering must round-trip: a config that doesn't parse back is worse
than none."""

from __future__ import annotations

import re
import tempfile
import tomllib
import unittest
from pathlib import Path

from workstream import profiles
from workstream.baseline import parse_regex
from workstream.config import parse_config, render_default

ALL = ["cargo", "generic", "go", "gradle-kmp", "node", "python"]
# One real line of each tool's output, and the fingerprint it must give: no line numbers, so a
# finding survives unrelated edits.
SAMPLES = {
    "cargo": ("src/main.rs:2:9: warning: unused variable: `x`",
              "src/main.rs | warning |  | unused variable: `x`"),
    "gradle-kmp": ("/repo/src/File.kt:11:1: Unused import. [UnusedImports]",
                   "/repo/src/File.kt | Unused import. [UnusedImports]"),
    "node": ("src/a.js:3:5: 'x' is defined but never used. [Error/no-unused-vars]",
             "src/a.js | 'x' is defined but never used. [Error/no-unused-vars]"),
    "python": ("src/a.py:1:8: F401 `os` imported but unused",
               "src/a.py | F401 | `os` imported but unused"),
    "go": ("./a.go:3:2: fmt.Printf format %d has arg x of wrong type string",
           "a.go | fmt.Printf format %d has arg x of wrong type string"),
}


class RepoCase(unittest.TestCase):
    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)

    def touch(self, *names: str) -> None:
        for name in names:
            (self.root / name).write_text("")


class DetectionTests(RepoCase):
    def detected(self) -> str:
        return profiles.detect(self.root)[0].name

    def test_all_six_exist_and_load(self) -> None:
        self.assertEqual(profiles.names(), ALL)
        for name in ALL:
            self.assertEqual(profiles.load(name).name, name)

    def test_each_marker_finds_its_profile(self) -> None:
        for name in ALL:
            for marker in profiles.load(name).markers:
                with self.subTest(marker=marker):
                    with tempfile.TemporaryDirectory() as tmp:
                        (Path(tmp) / marker).write_text("")
                        self.assertEqual(profiles.detect(Path(tmp))[0].name, name)

    def test_nothing_recognised_is_generic(self) -> None:
        self.assertEqual(self.detected(), "generic")

    def test_a_build_tool_wins_over_its_tooling_and_the_rest_is_mentioned(self) -> None:
        self.touch("Cargo.toml", "package.json")
        profile, others = profiles.detect(self.root)
        self.assertEqual((profile.name, others), ("cargo", ["node"]))

    def test_a_marker_further_down_does_not_count(self) -> None:
        (self.root / "sub").mkdir()
        (self.root / "sub" / "go.mod").write_text("")
        self.assertEqual(self.detected(), "generic")

    def test_an_unknown_profile_names_the_real_ones(self) -> None:
        with self.assertRaisesRegex(Exception, "there is: cargo"):
            profiles.load("nope")


class CandidateTests(RepoCase):
    def candidates(self, name: str) -> dict[str, list[str]]:
        return profiles.candidates(profiles.load(name), self.root)

    def test_cargo_offers_everything(self) -> None:
        self.assertEqual(set(self.candidates("cargo")), {"compile", "test", "lint"})

    def test_node_offers_only_scripts_that_exist(self) -> None:
        (self.root / "package.json").write_text('{"scripts": {"test": "x"}}')
        self.assertEqual(self.candidates("node"), {"test": ["npm test"]})

    def test_node_prefers_the_lockfiles_runner_and_keeps_a_fallback(self) -> None:
        (self.root / "package.json").write_text('{"scripts": {"lint": "x"}}')
        self.touch("pnpm-lock.yaml")
        self.assertEqual(self.candidates("node")["lint"], ["pnpm run lint", "npm run lint"])

    def test_node_compile_prefers_a_typecheck_over_a_build(self) -> None:
        (self.root / "package.json").write_text('{"scripts": {"typecheck": "x", "build": "y"}}')
        self.assertEqual(self.candidates("node")["compile"], ["npm run typecheck", "npm run build"])

    def test_python_falls_back_to_unittest(self) -> None:
        self.assertEqual(self.candidates("python"), {"test": ["python3 -m unittest discover"]})

    def test_python_tries_pytest_when_the_project_mentions_it(self) -> None:
        (self.root / "pyproject.toml").write_text("[tool.pytest.ini_options]\n[tool.ruff]\n")
        found = self.candidates("python")
        self.assertEqual(found["test"], ["python3 -m pytest -q", "python3 -m unittest discover"])
        self.assertEqual(found["lint"], ["ruff check --output-format=concise ."])

    def test_gradle_prefers_the_wrapper(self) -> None:
        self.touch("gradlew")
        self.assertEqual(self.candidates("gradle-kmp")["test"][0],
                         "./gradlew test --console=plain")

    def test_gradle_multiplatform_tries_all_tests_first(self) -> None:
        self.touch("gradlew")
        (self.root / "build.gradle.kts").write_text('kotlin("multiplatform")\n')
        self.assertEqual(self.candidates("gradle-kmp")["test"][:2],
                         ["./gradlew allTests --console=plain", "./gradlew test --console=plain"])

    def test_gradle_lint_only_when_configured(self) -> None:
        self.touch("gradlew")
        self.assertNotIn("lint", self.candidates("gradle-kmp"))
        (self.root / "build.gradle.kts").write_text('id("io.gitlab.arturbosch.detekt")\n')
        self.assertIn("lint", self.candidates("gradle-kmp"))

    def test_generic_reads_the_makefile(self) -> None:
        self.assertEqual(self.candidates("generic"), {})
        (self.root / "Makefile").write_text("test:\n\techo hi\nnot-lint:\n\ttrue\n")
        self.assertEqual(self.candidates("generic"), {"test": ["make test"]})

    def test_a_repeated_command_is_offered_once(self) -> None:
        self.touch("gradlew", "detekt.yml")
        (self.root / "build.gradle.kts").write_text("detekt\n")
        lint = self.candidates("gradle-kmp")["lint"]
        self.assertEqual(len(lint), len(set(lint)))


class BaselinePatternTests(unittest.TestCase):
    def test_each_profiles_pattern_reads_its_tool_and_drops_the_line_number(self) -> None:
        for name, (line, fingerprint) in SAMPLES.items():
            with self.subTest(profile=name):
                pattern = profiles.load(name).baseline["lint"]["pattern"]
                self.assertEqual(parse_regex(line, pattern), [fingerprint])
                moved = re.sub(r":\d+:\d+:", ":99:9:", line)
                self.assertEqual(parse_regex(moved, pattern), [fingerprint])

    def test_every_pattern_ignores_ordinary_output(self) -> None:
        for name in SAMPLES:
            pattern = profiles.load(name).baseline["lint"]["pattern"]
            self.assertEqual(parse_regex("Compiling thing v0.1.0\nBUILD SUCCESSFUL in 3s\n", pattern),
                             [], name)


class RenderTests(unittest.TestCase):
    def parsed(self, text: str):
        return parse_config(tomllib.loads(text))

    def test_the_default_keeps_the_tables_other_code_edits(self) -> None:
        text = render_default("trunk")
        for line in ("[commands]\n", "[adequacy]\n", "max_workers = 3", 'merge = "no-ff"',
                     'mode = "none"', 'integration = "trunk"'):
            self.assertIn(line, text)
        self.assertEqual(self.parsed(text).commands, {})

    def test_every_profile_round_trips(self) -> None:
        for name in ALL:
            with self.subTest(profile=name):
                profile = profiles.load(name)
                commands = {c["key"]: c["run"] for c in profile.commands}
                config = self.parsed(render_default(
                    "trunk", commands=commands, adequacy=profile.adequacy,
                    baseline=profile.baseline, worktree_setup=profile.worktree_setup))
                self.assertEqual(config.commands, commands)
                self.assertEqual(config.worktree_setup, profile.worktree_setup)
                for key in profile.baseline:
                    if key in commands:
                        self.assertEqual(config.baseline_parsers[key]["pattern"],
                                         profile.baseline[key]["pattern"])

    def test_an_unverified_command_is_a_comment_with_its_reason(self) -> None:
        text = render_default("trunk", commands={"test": "ok"},
                              unverified={"lint": ('run "this"', "exit 1 on a clean tree")})
        self.assertIn('# lint = "run \\"this\\""  # exit 1 on a clean tree', text)
        self.assertEqual(self.parsed(text).commands, {"test": "ok"})

    def test_a_baseline_table_needs_an_active_command(self) -> None:
        text = render_default("trunk", commands={"test": "ok"},
                              baseline={"lint": {"parser": "regex", "pattern": "x"}})
        self.assertNotIn("[baseline.lint]", text)
        self.assertEqual(self.parsed(text).baseline_parsers, {})

    def test_regexes_with_backslashes_survive(self) -> None:
        pattern = r"^(?P<f>\S+):\d+: (?P<m>.*)$"
        text = render_default("trunk", commands={"lint": "x"},
                              baseline={"lint": {"parser": "regex", "pattern": pattern}})
        self.assertEqual(self.parsed(text).baseline_parsers["lint"]["pattern"], pattern)


if __name__ == "__main__":
    unittest.main()
