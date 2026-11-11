"""`ws launch check`: each pre-flight check passing and failing, and `ws launch agents`/`argv`:
the presets and the command lines they build, through the CLI a UI calls."""

from __future__ import annotations

import json

from tests.helpers import WsTestCase, task
from workstream import adapt, launch, snapshot

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


# The flags each preset adds, as each CLI's --help gives them: (agent, flag, levels, choices).
EFFORT = {
    "claude-code": ("--effort", ["low", "medium", "high", "xhigh", "max"]),
    "copilot-cli": ("--reasoning-effort",
                    ["none", "minimal", "low", "medium", "high", "xhigh", "max"]),
}
PERMISSIONS = {
    "claude-code": {m: ["--permission-mode", m] for m in
                    ("manual", "acceptEdits", "plan", "auto", "dontAsk", "bypassPermissions")},
    "copilot-cli": {"allow-all-tools": ["--allow-all-tools"], "allow-all": ["--allow-all"]},
}
COMMAND = {"claude-code": "claude", "copilot-cli": "copilot"}
RUN_PROMPT = "Use the ws-run skill to run workstream alpha."


def with_prompt(agent: str, prompt: str) -> list[str]:
    """Where each agent takes its prompt: claude-code's last argument, copilot-cli's -i."""
    return ["-i", prompt] if agent == "copilot-cli" else [prompt]


class LaunchArgvTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws(WS_ID, "AL")
        self.seed_ok([task("AL-01", 10)], WS_ID)
        self.commit_all("seed")

    def argv(self, *extra: str) -> dict:
        data = json.loads(self.ok("launch", "argv", "-w", WS_ID, *extra, "--json"))
        self.assertEqual(list(data), ["argv", "effortLevels", "permissionChoices"])
        return data

    def test_agents_lists_each_preset(self) -> None:
        data = json.loads(self.ok("launch", "agents", "--json"))
        agents = {a["agent"]: a for a in data["agents"]}
        self.assertEqual(sorted(agents), sorted(EFFORT))
        for agent, a in agents.items():
            self.assertEqual(sorted(a), ["agent", "command", "effortLevels", "label",
                                         "permissionChoices"])
            self.assertEqual(a["command"], COMMAND[agent])
            self.assertEqual(a["effortLevels"], EFFORT[agent][1])
            self.assertEqual(a["permissionChoices"], list(PERMISSIONS[agent]))

    def test_no_effort_or_permissions_adds_no_flag(self) -> None:
        for agent in EFFORT:
            with self.subTest(agent=agent):
                data = self.argv("--agent", agent, "--prompt-kind", "run")
                self.assertEqual(data["argv"], [COMMAND[agent], *with_prompt(agent, RUN_PROMPT)])
                self.assertEqual(data["effortLevels"], EFFORT[agent][1])
                self.assertEqual(data["permissionChoices"], list(PERMISSIONS[agent]))

    def test_each_effort_level(self) -> None:
        for agent, (flag, levels) in EFFORT.items():
            for level in levels:
                with self.subTest(agent=agent, level=level):
                    data = self.argv("--agent", agent, "--effort", level, "--prompt-kind", "run")
                    self.assertEqual(data["argv"], [COMMAND[agent], flag, level,
                                                    *with_prompt(agent, RUN_PROMPT)])

    def test_each_permission_choice(self) -> None:
        for agent, choices in PERMISSIONS.items():
            for choice, flags in choices.items():
                with self.subTest(agent=agent, choice=choice):
                    data = self.argv("--agent", agent, "--permissions", choice,
                                     "--prompt-kind", "run")
                    self.assertEqual(data["argv"], [COMMAND[agent], *flags,
                                                    *with_prompt(agent, RUN_PROMPT)])

    def test_effort_and_permissions_together(self) -> None:
        data = self.argv("--agent", "claude-code", "--effort", "high",
                         "--permissions", "acceptEdits", "--prompt-kind", "close")
        self.assertEqual(data["argv"], ["claude", "--effort", "high", "--permission-mode",
                                        "acceptEdits",
                                        "Use the ws-coordinate skill to close workstream alpha."])
        data = self.argv("--agent", "copilot-cli", "--effort", "xhigh",
                         "--permissions", "allow-all-tools", "--prompt-kind", "coordinate")
        self.assertEqual(data["argv"], ["copilot", "--reasoning-effort", "xhigh",
                                        "--allow-all-tools", "-i",
                                        "Use the ws-coordinate skill on workstream alpha."])

    def test_each_kind_takes_its_prompt_from_the_snapshot(self) -> None:
        for kind, text in snapshot.LAUNCH_PROMPTS.items():
            with self.subTest(kind=kind):
                extra = ("--task", "AL-01") if kind == launch.TASK_KIND else ()
                data = self.argv("--agent", "claude-code", "--prompt-kind", kind, *extra)
                self.assertEqual(data["argv"][-1], text.format(ws=WS_ID, task="AL-01"))

    def test_run_task_names_the_task(self) -> None:
        data = self.argv("--agent", "claude-code", "--prompt-kind", "run-task", "--task", "AL-01")
        self.assertEqual(data["argv"][-1],
                         "Use the ws-run skill to run only task AL-01 of workstream alpha.")

    def test_prompt_replaces_the_snapshots_text(self) -> None:
        edited = 'Use the ws-coordinate skill to abandon workstream alpha: it\'s "done"; $(rm -rf)'
        for agent in EFFORT:
            with self.subTest(agent=agent):
                data = self.argv("--agent", agent, "--prompt-kind", "abandon", "--prompt", edited)
                self.assertEqual(data["argv"], [COMMAND[agent], *with_prompt(agent, edited)])
                self.assertNotIn(snapshot.LAUNCH_PROMPTS["abandon"].format(ws=WS_ID),
                                 data["argv"])

    def test_text_output_is_one_shell_line(self) -> None:
        out = self.ok("launch", "argv", "-w", WS_ID, "--agent", "copilot-cli",
                      "--prompt-kind", "run")
        self.assertEqual(out.strip(), f"copilot -i '{RUN_PROMPT}'")

    def test_what_the_caller_got_wrong_is_refused(self) -> None:
        base = ("launch", "argv", "-w", WS_ID, "--prompt-kind", "run")
        self.assertIn("unknown effort", self.fails(*base, "--agent", "claude-code",
                                                   "--effort", "none"))
        self.assertIn("unknown permissions", self.fails(*base, "--agent", "copilot-cli",
                                                        "--permissions", "plan"))
        self.assertIn("no adapter", self.fails(*base, "--agent", "nobody"))
        self.assertIn("applies only to run-task", self.fails(*base, "--agent", "claude-code",
                                                             "--task", "AL-01"))
        self.assertIn("needs --task", self.fails("launch", "argv", "-w", WS_ID, "--agent",
                                                 "claude-code", "--prompt-kind", "run-task"))
        self.assertIn("no such task", self.fails("launch", "argv", "-w", WS_ID, "--agent",
                                                 "claude-code", "--prompt-kind", "run-task",
                                                 "--task", "AL-99"))
        code, _, _ = self.ws("launch", "argv", "-w", WS_ID, "--agent", "claude-code",
                             "--prompt-kind", "nope")
        self.assertNotEqual(code, 0)

    def test_an_adapter_without_a_launch_table_has_no_preset(self) -> None:
        bare = adapt.Adapter("bare", "Bare", "X.md", "x/{name}.md", {})
        self.assertIsNone(adapt.launch_preset(bare))


if __name__ == "__main__":
    import unittest

    unittest.main()
