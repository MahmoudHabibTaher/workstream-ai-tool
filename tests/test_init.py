"""`ws init` on repositories with something in them: stub tools stand in for a stack, so these run
anywhere and can make a command fail in exactly the way a test needs."""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import tempfile
import tomllib
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tests.helpers import GIT_ENV, task
from workstream.cli import main
from workstream.config import CONFIG_REL, parse_config

RUST_WARNING = "src/a.rs:1:1: warning: old debt"


class AdoptCase(unittest.TestCase):
    """A committed repo with stub tools first on PATH, and no `ws init` yet."""

    def setUp(self) -> None:
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name).resolve()
        self.root = base / "repo"
        self.root.mkdir()
        self.bin = base / "bin"
        self.bin.mkdir()
        env = mock.patch.dict(os.environ, {**GIT_ENV, "PATH": f"{self.bin}:{os.environ['PATH']}"})
        env.start()
        self.addCleanup(env.stop)
        self.git("init", "-q", "-b", "main")
        (self.root / "README").write_text("hi\n")

    def git(self, *argv: str) -> str:
        return subprocess.run(["git", *argv], cwd=self.root, capture_output=True, text=True,
                              check=True).stdout

    def commit(self, message: str = "x") -> None:
        self.git("add", "-A")
        self.git("commit", "-q", "-m", message)

    def stub(self, name: str, body: str) -> None:
        path = self.bin / name
        path.write_text(f"#!/bin/sh\n{body}\n")
        path.chmod(0o755)

    def file(self, name: str, text: str = "") -> None:
        (self.root / name).write_text(text)

    def ws(self, *argv: str) -> tuple[int, str]:
        out = io.StringIO()
        with redirect_stdout(out), redirect_stderr(out):
            try:
                code = main(["--root", str(self.root), *argv])
            except SystemExit as e:
                code = e.code if isinstance(e.code, int) else 1
        return code, out.getvalue()

    def init(self, *argv: str) -> str:
        code, out = self.ws("init", *argv)
        self.assertEqual(code, 0, out)
        return out

    def config_text(self) -> str:
        return (self.root / CONFIG_REL).read_text()

    def config(self):
        return parse_config(tomllib.loads(self.config_text()))

    def known(self) -> dict:
        path = self.root / ".workstream" / "baseline.json"
        return json.loads(path.read_text())["keys"] if path.exists() else {}

    def cargo(self, *, check: int = 0, test: int = 0, clippy: str = "exit 0") -> None:
        self.file("Cargo.toml", "[package]\n")
        self.commit()
        self.stub("cargo", f'case "$1" in\ncheck) exit {check};;\ntest) exit {test};;\n'
                           f'clippy) {clippy};;\nesac')


class ActiveKeyTests(AdoptCase):
    def test_a_passing_command_becomes_active(self) -> None:
        self.cargo()
        out = self.init()
        self.assertIn("profile: cargo", out)
        self.assertIn("  on   test: cargo test", out)
        self.assertEqual(self.config().commands["test"], "cargo test")
        self.assertEqual(self.config().adequacy["behaviour"], ["compile", "test"])

    def test_lint_with_parsed_findings_is_active_and_they_are_recorded(self) -> None:
        self.cargo(clippy=f'echo "{RUST_WARNING}"; exit 1')
        out = self.init()
        self.assertIn("(1 known finding(s) recorded)", out)
        self.assertIn("lint", self.config().commands)
        self.assertEqual(self.config().baseline_parsers["lint"]["parser"], "regex")
        self.assertEqual(self.known()["lint"]["findings"], ["src/a.rs | warning |  | old debt"])

    def test_no_baseline_file_when_nothing_is_known(self) -> None:
        self.cargo()
        self.init()
        self.assertEqual(self.known(), {})

    def test_a_tool_that_exits_zero_can_still_report(self) -> None:
        self.cargo(clippy=f'echo "{RUST_WARNING}"; exit 0')
        self.init()
        self.assertEqual(len(self.known()["lint"]["findings"]), 1)


class InactiveKeyTests(AdoptCase):
    def test_a_failing_test_is_a_comment_with_the_reason(self) -> None:
        self.cargo(test=101)
        out = self.init()
        self.assertIn("  off  test: cargo test: exit 101 on a clean tree", out)
        self.assertNotIn("test", self.config().commands)
        self.assertIn('# test = "cargo test"  # exit 101 on a clean tree', self.config_text())

    def test_lint_that_crashes_is_not_a_baseline(self) -> None:
        self.cargo(clippy='echo "toolchain missing"; exit 2')
        self.assertIn("nothing a parser could read", self.init())
        self.assertNotIn("lint", self.config().commands)

    def test_a_missing_tool_is_not_run_and_says_so(self) -> None:
        self.file("go.mod")
        self.commit()
        # Hide go however it was installed: CI runners ship it in /usr/bin.
        real_which = shutil.which
        hide_go = lambda tool, *a, **k: None if tool == "go" else real_which(tool, *a, **k)  # noqa: E731
        with mock.patch("workstream.adopt.shutil.which", side_effect=hide_go):
            out = self.init()
        self.assertIn("go isn't on PATH", out)
        self.assertEqual(self.config().commands, {})

    def test_a_command_that_changes_tracked_files_is_not_a_check(self) -> None:
        self.cargo(clippy="echo changed >> README; exit 0")
        self.assertIn("it changes tracked files", self.init())
        self.assertNotIn("lint", self.config().commands)

    def test_a_new_file_is_not_a_changed_one(self) -> None:
        self.cargo(clippy="echo locked > Cargo.lock; exit 0")
        out = self.init()
        self.assertIn("lint", self.config().commands)
        self.assertIn("the commands left new files: Cargo.lock", out)

    def test_ignored_output_is_not_mentioned(self) -> None:
        self.file(".gitignore", "target/\n")
        self.cargo(clippy="mkdir -p target; echo x > target/out; exit 0")
        self.assertNotIn("left new files", self.init())

    def test_a_timeout_is_reported(self) -> None:
        self.cargo()
        self.stub("cargo", 'case "$1" in\ntest) sleep 5;;\nesac')
        self.assertIn("timed out", self.init("--timeout", "1"))


class FallbackTests(AdoptCase):
    def test_a_later_candidate_is_used_when_the_first_fails(self) -> None:
        self.file("package.json", '{"scripts": {"test": "x"}}')
        self.file("pnpm-lock.yaml")
        self.commit()
        self.stub("pnpm", "exit 1")
        self.stub("npm", "exit 0")
        self.init()
        self.assertEqual(self.config().commands["test"], "npm test")

    def test_with_no_candidate_working_the_comment_is_the_one_that_ran(self) -> None:
        self.file("package.json", '{"scripts": {"test": "x"}}')
        self.file("pnpm-lock.yaml")
        self.commit()
        self.stub("npm", "exit 7")
        with mock.patch.dict(os.environ, {"PATH": f"{self.bin}:/usr/bin:/bin"}):
            out = self.init()
        self.assertIn("npm test: exit 7", out)


class SafetyTests(AdoptCase):
    def test_a_dirty_tree_is_refused_and_nothing_is_written(self) -> None:
        self.cargo()
        self.file("README", "changed\n")
        code, out = self.ws("init")
        self.assertEqual(code, 1, out)
        self.assertIn("clean tree", out)
        self.assertFalse((self.root / CONFIG_REL).exists())
        self.assertFalse((self.root / "workstreams").exists())

    def test_untracked_files_are_not_dirty(self) -> None:
        self.cargo()
        self.file("scratch.txt", "x")
        self.init()

    def test_no_run_runs_nothing_and_writes_only_comments(self) -> None:
        self.cargo()
        marker = self.root.parent / "ran"
        self.stub("cargo", f"touch {marker}")
        self.file("README", "dirty is fine here\n")
        self.assertIn("not run", self.init("--no-run"))
        self.assertFalse(marker.exists())
        self.assertEqual(self.config().commands, {})
        self.assertIn('# test = "cargo test"', self.config_text())

    def test_an_existing_config_is_left_alone(self) -> None:
        self.cargo()
        self.init()
        before = self.config_text()
        self.stub("cargo", "exit 1")
        self.assertIn("already set up", self.init())
        self.assertEqual(self.config_text(), before)

    def test_a_repo_with_no_commits_and_no_markers_needs_nothing_run(self) -> None:
        self.assertNotIn("trying", self.init())

    def test_profile_overrides_detection(self) -> None:
        self.cargo()
        self.stub("go", "exit 0")
        self.assertIn("profile: go", self.init("--profile", "go"))

    def test_an_unknown_profile_is_refused(self) -> None:
        code, out = self.ws("init", "--profile", "nope")
        self.assertEqual(code, 1)
        self.assertIn("no profile 'nope'", out)

    def test_several_matches_are_mentioned(self) -> None:
        self.file("package.json", "{}")
        self.cargo()
        self.assertIn("also matches node", self.init())

    def test_branches_are_recorded(self) -> None:
        self.init("--integration", "dev", "--production", "main")
        self.assertEqual((self.config().integration, self.config().production), ("dev", "main"))

    def test_setup_comes_from_the_profile(self) -> None:
        self.file("package.json", "{}")
        self.commit()
        self.init()
        self.assertIn("node_modules", self.config().worktree_setup[0])


class KnownFindingsReachTasksTests(AdoptCase):
    """The point of recording them: a repo's old debt doesn't stop its first task."""

    def adopt_with_debt(self) -> None:
        findings = self.root.parent / "findings.txt"
        findings.write_text(RUST_WARNING + "\n")
        self.cargo(clippy=f'cat {findings}; exit 1')
        self.init()
        self.commit("adopted")
        code, out = self.ws("new", "w", "--title", "t", "--summary", "s", "--base", "abc")
        self.assertEqual(code, 0, out)
        seed = self.root.parent / "seed.json"
        seed.write_text(json.dumps([task("T1", 10, verify=["lint"])]))
        code, out = self.ws("seed", "-w", "w", str(seed))
        self.assertEqual(code, 0, out)

    def test_a_task_passes_on_known_findings_and_fails_on_new_ones(self) -> None:
        self.adopt_with_debt()
        code, out = self.ws("verify", "T1", "-w", "w")
        self.assertEqual(code, 0, out)
        self.assertIn("1 known", out)
        (self.root.parent / "findings.txt").write_text(
            RUST_WARNING.replace("1:1", "9:9") + "\nsrc/b.rs:2:2: warning: mine\n")
        code, out = self.ws("verify", "T1", "-w", "w")
        self.assertEqual(code, 1, out)
        self.assertIn("new: src/b.rs | warning |  | mine", out)

    def test_a_workstreams_own_baseline_takes_over(self) -> None:
        self.adopt_with_debt()
        (self.root.parent / "findings.txt").write_text("src/c.rs:1:1: warning: later\n")
        self.git("add", "-A")
        self.commit("planned")
        code, out = self.ws("baseline", "record", "lint", "-w", "w")
        self.assertEqual(code, 0, out)
        code, out = self.ws("verify", "T1", "-w", "w")
        self.assertEqual(code, 0, out)

    def test_the_brief_mentions_them(self) -> None:
        self.adopt_with_debt()
        code, out = self.ws("brief", "T1", "-w", "w")
        self.assertIn("1 known finding(s): only new ones fail", out)

    def test_show_includes_the_projects_record(self) -> None:
        self.adopt_with_debt()
        self.assertIn("lint: exit", self.ws("baseline", "show", "-w", "w")[1])


if __name__ == "__main__":
    unittest.main()
