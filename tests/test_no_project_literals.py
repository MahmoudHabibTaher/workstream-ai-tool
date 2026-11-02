"""Core names no stack, build tool, branch model or agent (decision 0002). A fact like that in
src/workstream/ is what stopped the source harnesses being reused. config.py alone may hold
the defaults a fresh project starts from."""

from __future__ import annotations

import re
import unittest
from pathlib import Path

import workstream

CORE = Path(workstream.__file__).resolve().parent
FORBIDDEN = re.compile(
    r"\b(develop|cargo|rustc?|gradlew?|detekt|kotlin|swift|npm|pnpm|yarn|pytest|mvn|maven"
    r"|make check|clippy|subsonic|the Kotlin harness|work|claude|copilot|anthropic|openai|codex"
    r"|ghcr|fastlane|media-library)\b", re.IGNORECASE)
# The branch name, not the worktree `"main"` key the snapshot writes.
ALLOWED_ONLY_IN_CONFIG = re.compile(r'(?<!get\()"main"(?!:)|task/\{slug\}|task/\*')


def core_files() -> list[Path]:
    return sorted(p for p in CORE.rglob("*") if p.suffix in (".py", ".md"))


class NoProjectLiteralsTests(unittest.TestCase):
    def test_finds_the_core_files(self) -> None:
        self.assertGreater(len(core_files()), 10)

    def test_core_names_no_project_stack_or_agent(self) -> None:
        hits = [f"{p.relative_to(CORE)}:{n}: {line.strip()}"
                for p in core_files()
                for n, line in enumerate(p.read_text().splitlines(), 1)
                if FORBIDDEN.search(line)]
        self.assertEqual(hits, [])

    def test_branch_defaults_live_only_in_config(self) -> None:
        hits = [f"{p.relative_to(CORE)}:{n}: {line.strip()}"
                for p in core_files() if p.name != "config.py"
                for n, line in enumerate(p.read_text().splitlines(), 1)
                if ALLOWED_ONLY_IN_CONFIG.search(line)]
        # gitutil falls back to a name when a repo has no branch at all yet.
        self.assertEqual([h for h in hits if not h.startswith("gitutil.py")], [])

    def test_the_pattern_catches_what_it_should(self) -> None:
        for line in ('INTEGRATION = "develop"', "./gradlew detekt", "cargo test", "make check"):
            self.assertTrue(FORBIDDEN.search(line), line)
        for line in ("the developer", "a promise made", "makes checks"):
            self.assertFalse(FORBIDDEN.search(line), line)


if __name__ == "__main__":
    unittest.main()
