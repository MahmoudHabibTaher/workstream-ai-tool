"""The eval harness, proven with a stub. If it can't tell a good agent from a bad one, a real run
would prove nothing. These never start a real agent."""

from __future__ import annotations

import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from evals import harness
from tests.helpers import GIT_ENV

REPO = Path(__file__).resolve().parent.parent


class ScenarioTests(unittest.TestCase):
    def setUp(self) -> None:
        env = mock.patch.dict(os.environ, GIT_ENV)
        env.start()
        self.addCleanup(env.stop)

    def run_stub(self, scenario: str, behaviour: str = "good") -> dict:
        return harness.run_scenario(scenario, harness.STUB, "0", behaviour)

    def test_a_well_behaved_agent_passes_every_scenario(self) -> None:
        for name in harness.SCENARIOS:
            with self.subTest(scenario=name):
                result = self.run_stub(name)
                self.assertTrue(result["passed"], result)

    def test_chaining_into_the_next_task_is_caught(self) -> None:
        result = self.run_stub("chain", "chain")
        self.assertFalse(result["passed"])
        self.assertIn("src/two.txt is on D-1's branch", " ".join(result["problems"]))

    def test_widening_scope_is_caught(self) -> None:
        result = self.run_stub("scope", "widen")
        self.assertFalse(result["passed"])
        self.assertIn("src/legacy.txt changed", " ".join(result["problems"]))

    def test_skipping_verify_is_caught(self) -> None:
        result = self.run_stub("verify", "skip-verify")
        self.assertFalse(result["passed"])
        self.assertIn("never run", " ".join(result["problems"]))

    def test_editing_tracking_files_is_caught(self) -> None:
        result = self.run_stub("tracking", "edit-tracking")
        self.assertFalse(result["passed"])
        self.assertIn("workstreams/demo/PROGRESS.md", " ".join(result["problems"]))

    def test_discarding_the_first_attempt_is_caught(self) -> None:
        result = self.run_stub("resume", "discard")
        self.assertFalse(result["passed"])
        self.assertIn("threw away the first attempt", " ".join(result["problems"]))

    def test_requeueing_instead_of_resuming_is_caught(self) -> None:
        result = self.run_stub("resume", "requeue")
        self.assertFalse(result["passed"])
        self.assertIn("D-1 is todo", " ".join(result["problems"]))

    def test_a_resume_that_stops_short_is_caught(self) -> None:
        result = self.run_stub("resume", "give-up")
        self.assertFalse(result["passed"])
        self.assertIn("still leave D-1 blocked", " ".join(result["problems"]))

    def private_temp(self) -> Path:
        """Point tempfile at a folder only this test uses, so parallel suites can't show up in it."""
        folder = Path(tempfile.mkdtemp(prefix="ws-test-scratch-"))
        self.addCleanup(shutil.rmtree, folder, True)
        patcher = mock.patch.object(tempfile, "tempdir", str(folder))
        patcher.start()
        self.addCleanup(patcher.stop)
        return folder

    def test_the_scratch_repo_is_cleaned_up(self) -> None:
        folder = self.private_temp()
        self.run_stub("verify")
        self.assertEqual(list(folder.iterdir()), [])

    def test_a_scratch_repo_left_behind_is_seen(self) -> None:
        folder = self.private_temp()
        with mock.patch.object(harness.shutil, "rmtree"):
            self.run_stub("verify")
        self.assertEqual(len(list(folder.glob("ws-eval-verify-*"))), 1)

    def test_the_sample_has_known_debt_and_a_recorded_baseline(self) -> None:
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        repo = harness.build_repo(base, harness.STUB)
        self.assertEqual(repo.ws("doctor").returncode, 0)
        self.assertEqual(repo.ws("reconcile").returncode, 0, "a coordinator's first check fails")
        self.assertIn("1 known, parser regex", repo.ws("baseline", "show", "-w", "demo").stdout)


class RealRunGuardTests(unittest.TestCase):
    def test_every_real_command_carries_a_cap(self) -> None:
        self.assertEqual(harness.real_command(harness.CLAUDE, "p", "0.50")[3:5],
                         ["--max-budget-usd", "0.50"])
        command = harness.real_command(harness.COPILOT, "p", "3")
        self.assertEqual(command[command.index("--max-ai-credits") + 1], "3")

    def test_no_real_command_allows_everything(self) -> None:
        for agent in (harness.CLAUDE, harness.COPILOT):
            text = " ".join(harness.real_command(agent, "p", "1"))
            for flag in ("--dangerously-skip-permissions", "--allow-all", "--yolo"):
                self.assertNotIn(flag, text)
            self.assertNotIn("push", text)

    def test_a_claude_run_tests_the_generated_rules_and_not_its_own(self) -> None:
        command = harness.real_command(harness.CLAUDE, "p", "1")
        self.assertEqual(command[command.index("--settings") + 1], ".claude/settings.json")
        self.assertNotIn("Bash(", command[command.index("--allowedTools") + 1])

    def test_cost_is_found_among_warnings_and_events(self) -> None:
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        log = base / "log"
        log.write_text('a warning\n{"type": "system"}\n{"total_cost_usd": 0.1}\n'
                       '{"total_cost_usd": 0.2}\n{"type": "end"}\n')
        self.assertEqual(harness.cost_from(log), 0.2)

    def test_a_run_refuses_an_account_nobody_named(self) -> None:
        with mock.patch.object(harness, "copilot_account", return_value="someone"), \
                mock.patch.object(harness.shutil, "which", return_value="/bin/x"):
            self.assertIn("would run as someone", harness.preflight(harness.COPILOT, None))
            self.assertIn("would run as someone", harness.preflight(harness.COPILOT, "other"))
            self.assertEqual(harness.preflight(harness.COPILOT, "someone"), "")

    def test_a_missing_login_is_reported_before_spending(self) -> None:
        done = subprocess.CompletedProcess([], 0, stdout='{"loggedIn": false}')
        with mock.patch.object(harness.shutil, "which", return_value="/bin/x"), \
                mock.patch.object(harness.subprocess, "run", return_value=done) as run:
            self.assertIn("isn't logged in", harness.preflight(harness.CLAUDE, None))
        self.assertEqual(run.call_args[0][0], ["claude", "auth", "status"])

    def test_a_refused_preflight_starts_nothing(self) -> None:
        with mock.patch.object(harness, "preflight", return_value="no"), \
                mock.patch.object(harness, "run_scenario") as started, \
                mock.patch("sys.stderr"):
            self.assertEqual(harness.main(["--agent", harness.CLAUDE]), 2)
        started.assert_not_called()

    def test_the_test_suite_never_names_a_real_run(self) -> None:
        makefile = (REPO / "Makefile").read_text()
        test_recipe = makefile.split("test:")[1].split("\n\n")[0]
        self.assertNotIn("evals.harness", test_recipe)


if __name__ == "__main__":
    unittest.main()
