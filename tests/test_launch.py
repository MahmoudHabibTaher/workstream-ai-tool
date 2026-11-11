"""`ws launch check`: each pre-flight check passing and failing, through the CLI a UI calls."""

from __future__ import annotations

import json

from tests.helpers import WsTestCase, task
from workstream import adapt, launch

WS_ID = "alpha"


class LaunchCheckTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.set_commands(test="true")
        self.new_ws(WS_ID, "AL")
        self.seed_ok([task("AL-01", 10, verify=["test"]),
                      task("AL-02", 20, blockedBy=["AL-01"])], WS_ID)
        self.commit_all("seed")

    # --- helpers --------------------------------------------------------------------------

    def checks(self, kind: str, *extra: str) -> dict[str, dict]:
        out = self.ok("launch", "check", "-w", WS_ID, "--kind", kind, *extra, "--json")
        data = json.loads(out)
        self.assertEqual(list(data), ["checks"])
        for c in data["checks"]:
            self.assertEqual(sorted(c), ["blocking", "id", "message", "ok"])
        return {c["id"]: c for c in data["checks"]}

    def record_baseline(self) -> None:
        self.ok("baseline", "record", "-w", WS_ID)
        self.commit_all("baseline")

    def set_fields(self, message: str, **by_id: dict) -> None:
        """Change seeded tasks on disk, past the CLI, and commit."""
        rows = self.queue(WS_ID)["tasks"]
        for t in rows:
            t.update(by_id.get(t["id"].replace("-", "_"), {}))
        self.write_queue(rows, WS_ID)
        self.commit_all(message)

    def claim_first(self) -> None:
        self.set_fields("claim", AL_01={"status": "in-progress", "branch": "task/al-01",
                                         "startedAt": "2026-10-01T00:00:00Z",
                                         "baseCommit": "0000000", "claimedBy": "worker"})

    # --- which checks apply ---------------------------------------------------------------

    def test_run_has_every_check_but_skills_without_an_agent(self) -> None:
        self.assertEqual(list(self.checks("run")),
                         ["validate", "wave", "claim", "dirty", "baseline"])

    def test_run_task_has_no_wave_check(self) -> None:
        self.assertEqual(list(self.checks("run-task", "--task", "AL-02")),
                         ["validate", "claim", "dirty", "baseline"])

    def test_other_kinds_have_neither_wave_nor_claim(self) -> None:
        for kind in ("coordinate", "close", "abandon"):
            self.assertEqual(list(self.checks(kind)), ["validate", "dirty", "baseline"], kind)

    def test_kinds_are_the_launch_prompts_and_run_task(self) -> None:
        self.assertIn("run-task", launch.KINDS)
        self.assertEqual(len(launch.KINDS), len(set(launch.KINDS)))

    # --- validate -------------------------------------------------------------------------

    def test_validate_passes_on_a_clean_queue(self) -> None:
        c = self.checks("run")["validate"]
        self.assertEqual((c["ok"], c["blocking"]), (True, True))

    def test_validate_errors_block(self) -> None:
        self.set_fields("self-blocked", AL_01={"blockedBy": ["AL-01"]})
        c = self.checks("coordinate")["validate"]
        self.assertEqual((c["ok"], c["blocking"]), (False, True))
        self.assertIn("AL-01", c["message"])

    # --- wave -----------------------------------------------------------------------------

    def test_wave_passes_with_an_actionable_task(self) -> None:
        c = self.checks("run")["wave"]
        self.assertEqual((c["ok"], c["blocking"]), (True, True))
        self.assertIn("AL-01", c["message"])

    def test_wave_blocks_run_when_nothing_is_actionable(self) -> None:
        self.set_fields("finished", AL_01={"status": "done"}, AL_02={"status": "done"})
        c = self.checks("run")["wave"]
        self.assertEqual((c["ok"], c["blocking"]), (False, True))
        self.assertIn("finished", c["message"])

    def test_wave_blocks_run_when_stuck(self) -> None:
        self.set_fields("stuck", AL_01={"status": "blocked", "blockedReason": "waits"})
        c = self.checks("run")["wave"]
        self.assertEqual((c["ok"], c["blocking"]), (False, True))

    # --- claim ----------------------------------------------------------------------------

    def test_claim_passes_with_nothing_claimed(self) -> None:
        self.assertTrue(self.checks("run")["claim"]["ok"])
        self.assertTrue(self.checks("run-task", "--task", "AL-02")["claim"]["ok"])

    def test_an_open_claim_blocks_run(self) -> None:
        self.claim_first()
        c = self.checks("run")["claim"]
        self.assertEqual((c["ok"], c["blocking"]), (False, True))
        self.assertIn("AL-01", c["message"])

    def test_an_open_claim_only_warns_for_run_task(self) -> None:
        self.claim_first()
        c = self.checks("run-task", "--task", "AL-02")["claim"]
        self.assertEqual((c["ok"], c["blocking"]), (False, False))
        c = self.checks("run-task", "--task", "AL-01")["claim"]
        self.assertEqual((c["ok"], c["blocking"]), (False, False))
        self.assertIn("AL-01 is already claimed", c["message"])

    # --- dirty ----------------------------------------------------------------------------

    def test_dirty_passes_on_a_committed_tree(self) -> None:
        c = self.checks("run")["dirty"]
        self.assertEqual((c["ok"], c["blocking"]), (True, True))

    def test_an_uncommitted_queue_blocks(self) -> None:
        (self.ws_dir / WS_ID / "PLAN.md").write_text("# edited\n")
        c = self.checks("coordinate")["dirty"]
        self.assertEqual((c["ok"], c["blocking"]), (False, True))
        self.assertIn(f"workstreams/{WS_ID}/PLAN.md", c["message"])

    def test_an_uncommitted_registry_blocks(self) -> None:
        self.registry.write_text(self.registry.read_text() + "\n")
        self.assertFalse(self.checks("run")["dirty"]["ok"])

    def test_another_workstreams_folder_and_code_do_not_count(self) -> None:
        self.new_ws("other", "OT")
        self.commit_all("other")
        (self.ws_dir / "other" / "PLAN.md").write_text("# edited\n")
        (self.root / "code.txt").write_text("work in progress\n")
        self.assertTrue(self.checks("run")["dirty"]["ok"])

    # --- baseline -------------------------------------------------------------------------

    def test_a_missing_baseline_warns(self) -> None:
        c = self.checks("run")["baseline"]
        self.assertEqual((c["ok"], c["blocking"]), (False, False))
        self.assertIn("test", c["message"])

    def test_a_recorded_baseline_passes(self) -> None:
        self.record_baseline()
        c = self.checks("run")["baseline"]
        self.assertEqual((c["ok"], c["blocking"]), (True, False))

    def test_a_broken_baseline_file_fails_the_check_not_the_command(self) -> None:
        (self.ws_dir / WS_ID / "baseline.json").write_text("{not json")
        self.commit_all("broken baseline")
        c = self.checks("run")["baseline"]
        self.assertEqual((c["ok"], c["blocking"]), (False, False))
        self.assertIn("not valid JSON", c["message"])

    # --- skills ---------------------------------------------------------------------------

    def test_skills_not_installed_warns(self) -> None:
        agent = adapt.names()[0]
        c = self.checks("run", "--agent", agent)["skills"]
        self.assertEqual((c["ok"], c["blocking"]), (False, False))
        self.assertEqual(c["message"], f"skills not installed for {agent} (`ws adapt {agent}`)")

    def test_skills_installed_passes(self) -> None:
        agent = adapt.names()[0]
        self.ok("adapt", agent)
        self.commit_all("adapt")
        c = self.checks("run", "--agent", agent)["skills"]
        self.assertEqual((c["ok"], c["blocking"]), (True, False))

    def test_an_agent_no_adapter_knows_still_gets_the_warning(self) -> None:
        self.assertFalse(self.checks("run", "--agent", "some-other-agent")["skills"]["ok"])

    # --- the command ----------------------------------------------------------------------

    def test_a_failing_blocking_check_still_exits_zero(self) -> None:
        self.claim_first()
        code, out, err = self.ws("launch", "check", "-w", WS_ID, "--kind", "run", "--json")
        self.assertEqual(code, 0, err)
        self.assertTrue(launch.blocked(json.loads(out)))

    def test_text_output_names_each_check_and_the_outcome(self) -> None:
        self.record_baseline()
        out = self.ok("launch", "check", "-w", WS_ID, "--kind", "run")
        self.assertIn("ready to launch", out)
        self.claim_first()
        out = self.ok("launch", "check", "-w", WS_ID, "--kind", "run")
        self.assertIn("BLOCKS", out)
        self.assertTrue(out.rstrip().endswith("blocked"))

    def test_run_task_needs_a_task_the_queue_holds(self) -> None:
        self.assertIn("needs --task",
                      self.fails("launch", "check", "-w", WS_ID, "--kind", "run-task"))
        self.assertIn("no such task", self.fails("launch", "check", "-w", WS_ID,
                                                 "--kind", "run-task", "--task", "AL-99"))
        self.assertIn("applies only to run-task", self.fails(
            "launch", "check", "-w", WS_ID, "--kind", "run", "--task", "AL-01"))

    def test_an_unknown_kind_is_refused(self) -> None:
        code, _, _ = self.ws("launch", "check", "-w", WS_ID, "--kind", "nope")
        self.assertNotEqual(code, 0)


if __name__ == "__main__":
    import unittest

    unittest.main()
