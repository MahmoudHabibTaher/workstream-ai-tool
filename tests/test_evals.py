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

    def test_leftover_starts_with_uncommitted_partial_work_and_no_evidence(self) -> None:
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        scenario = harness.SCENARIOS["leftover"]
        repo = harness.build_repo(base, harness.STUB, scenario.plan)
        repo.must("ws", "claim", "--commit", "-w", "demo", "D-1")
        repo.must("ws", "worktree", "create", "-w", "demo", "D-1")
        scenario.setup(repo)
        where = repo.root / ".workstream" / "worktrees" / "d-1"
        self.assertEqual(repo.queue()["D-1"]["status"], "in-progress")
        self.assertEqual(repo.run("git", "status", "--porcelain", cwd=where).stdout.split(),
                         ["??", "src/one.txt"])
        self.assertFalse((where / "workstreams" / "demo" / "evidence" / "D-1.md").exists())
        self.assertNotEqual(repo.run("ws", "verify", "D-1", "-w", "demo", cwd=where).returncode, 0,
                            "the work isn't partial if it already passes")
        brief = repo.must("ws", "brief", "D-1", "-w", "demo")
        self.assertIn("## Picking up", brief)
        self.assertIn("`?? src/one.txt`", brief)
        self.assertNotIn("## Resuming", brief)

    def test_keeping_and_finishing_the_partial_work_passes(self) -> None:
        result = self.run_stub("leftover")
        self.assertTrue(result["passed"], result)

    def test_discarding_the_partial_work_is_caught(self) -> None:
        result = self.run_stub("leftover", "discard")
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["problems"]), 1, result)
        self.assertIn("the partial work didn't land", result["problems"][0])

    def test_requeueing_the_partial_work_is_caught(self) -> None:
        result = self.run_stub("leftover", "requeue")
        self.assertFalse(result["passed"])
        self.assertIn("D-1 is todo", " ".join(result["problems"]))

    def test_leaving_the_partial_work_uncommitted_is_caught(self) -> None:
        result = self.run_stub("leftover", "give-up")
        self.assertFalse(result["passed"])
        self.assertIn("the partial work didn't land", " ".join(result["problems"]))

    def test_leaving_the_text_to_apply_passes(self) -> None:
        result = self.run_stub("text")
        self.assertTrue(result["passed"], result)

    def test_text_only_under_gotchas_is_caught(self) -> None:
        result = self.run_stub("text", "gotcha-only")
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["problems"]), 1, result)
        self.assertIn("`## Text to apply` doesn't name .claude/notes.md", result["problems"][0])

    def test_editing_the_file_anyway_is_caught(self) -> None:
        result = self.run_stub("text", "edit-anyway")
        self.assertFalse(result["passed"])
        self.assertEqual(len(result["problems"]), 1, result)
        self.assertIn("it changed .claude/notes.md", result["problems"][0])

    def test_the_text_scenarios_file_is_one_a_claude_worker_is_warned_off(self) -> None:
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        repo = harness.build_repo(base, harness.CLAUDE, harness.SCENARIOS["text"].plan)
        repo.must("ws", "claim", "--commit", "-w", "demo", "D-1")
        repo.must("ws", "worktree", "create", "-w", "demo", "D-1")
        brief = repo.must("ws", "brief", "D-1", "-w", "demo")
        self.assertIn(f"**You can't edit these from the background:** `{harness.TEXT_FILE}`", brief)
        self.assertIn(harness.TEXT_LINE, brief)
        self.assertFalse((repo.root / harness.TEXT_FILE).exists())

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
        self.assertEqual(harness.cost_from(log, harness.CLAUDE), (0.2, harness.USD))

    def _copilot_dirs(self) -> tuple[Path, Path]:
        base = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, base, True)
        (base / "sessions").mkdir()
        return base / "log", base / "sessions"

    def test_copilot_credits_are_found_in_its_log(self) -> None:
        # The two shapes a real events.jsonl had: the figure on data, and under accountingSnapshot.
        log, sessions = self._copilot_dirs()
        log.write_text('a warning\n'
                       '{"type":"session.usage_checkpoint","data":{"totalNanoAiu":21495680000}}\n'
                       '{"type":"session.shutdown","data":{"accountingSnapshot":'
                       '{"totalNanoAiu":54200000000.0,"aiCreditsStatus":"complete"}}}\n'
                       '{"type":"end"}\n')
        amount, unit = harness.cost_from(log, harness.COPILOT, sessions=sessions)
        self.assertAlmostEqual(amount, 54.2)
        self.assertEqual(unit, harness.CREDITS)

    def test_copilot_credits_fall_back_to_the_runs_newest_session(self) -> None:
        log, sessions = self._copilot_dirs()
        log.write_text('{"type":"result"}\n')
        for name, nano, mtime in (("old", 9e9, 1000), ("new", 20e9, 3000), ("before", 5e9, 10)):
            events = sessions / name / "events.jsonl"
            events.parent.mkdir()
            events.write_text(f'{{"type":"session.usage_checkpoint","data":{{"totalNanoAiu":{nano}}}}}\n')
            os.utime(events, (mtime, mtime))
        self.assertEqual(harness.cost_from(log, harness.COPILOT, sessions=sessions, since=500),
                         (20.0, harness.CREDITS))

    def test_no_figure_means_no_cost(self) -> None:
        log, sessions = self._copilot_dirs()
        log.write_text('a warning\n{"type": "end"}\n')
        self.assertIsNone(harness.cost_from(log, harness.CLAUDE))
        self.assertIsNone(harness.cost_from(log, harness.COPILOT, sessions=sessions))
        self.assertIsNone(harness.cost_from(log.with_name("missing"), harness.CLAUDE))

    def test_the_report_prints_each_cost_in_its_unit(self) -> None:
        result = {"scenario": "full", "passed": True, "seconds": 12.5, "exit": 0}
        self.assertEqual(harness.report_line({**result, "cost": (54.2, harness.CREDITS)}),
                         "PASS full  12.5s, 54.20 credits")
        self.assertEqual(harness.report_line({**result, "cost": (0.2, harness.USD)}),
                         "PASS full  12.5s, $0.20")
        self.assertEqual(harness.report_line({**result, "cost": None, "passed": False, "exit": 1}),
                         "FAIL full  12.5s  (agent exit 1)")

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
