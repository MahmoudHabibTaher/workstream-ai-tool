"""`ws hook`: says no at the moment of an edit, and never stops work because of its own failure."""

from __future__ import annotations

import io
import json
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

from tests.helpers import WsTestCase, task
from workstream import adapt, hook
from workstream.cli import main

CLAUDE, COPILOT = "claude-code", "copilot-cli"


class HookCase(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.seed_ok([task("T1", 10)])
        self.folder = self.ws_dir / "alpha"

    def claude(self, path: str, tool: str = "Edit") -> dict:
        return {"hook_event_name": "PreToolUse", "tool_name": tool, "cwd": str(self.root),
                "tool_input": {"file_path": path}}

    def copilot(self, path: str, tool: str = "edit") -> dict:
        return {"toolName": tool, "cwd": str(self.root), "toolArgs": {"path": path}}

    def run_hook(self, payload: object, fmt: str = hook.EXIT_CODE) -> tuple[int, str, str]:
        raw = payload if isinstance(payload, str) else json.dumps(payload)
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err), mock.patch("sys.stdin", io.StringIO(raw)):
            code = main(["hook", "pre-edit", "--format", fmt])
        return code, out.getvalue(), err.getvalue()

    def denied(self, path: str) -> str | None:
        return hook.decide(json.dumps(self.claude(path)))


class DecisionTests(HookCase):
    def test_every_tracking_file_is_denied_with_its_command(self) -> None:
        cases = {"workstreams/alpha/tasks_list.json": "`ws update`",
                 "workstreams/workstreams.json": "`ws new`",
                 "workstreams/alpha/baseline.json": "`ws baseline record`",
                 ".workstream/baseline.json": "`ws baseline record`",
                 "workstreams/alpha/DECISIONS.md": "`ws decide`",
                 "workstreams/alpha/PROGRESS.md": "`ws settle`",
                 "workstreams/alpha/session_handoff.md": "`ws handoff --note`"}
        for path, command in cases.items():
            with self.subTest(path=path):
                self.assertIn(command, self.denied(path) or "")

    def test_an_absolute_path_counts_the_same(self) -> None:
        self.assertTrue(self.denied(str(self.folder / "PROGRESS.md")))

    def test_ordinary_files_and_a_workers_evidence_are_fine(self) -> None:
        for path in ("src/a.py", "README.md", "workstreams/alpha/evidence/T1.md",
                     "docs/PROGRESS.md", "other/tasks_list.json", ".workstream/config.toml"):
            with self.subTest(path=path):
                self.assertIsNone(self.denied(path))

    def test_a_plan_is_writable_until_it_is_filled_in(self) -> None:
        plan = self.folder / "PLAN.md"
        plan.write_text("{{CONTEXT}}\n")
        self.assertIsNone(self.denied("workstreams/alpha/PLAN.md"))
        plan.write_text("# The plan\n")
        self.assertIn("immutable", self.denied("workstreams/alpha/PLAN.md"))

    def test_a_path_inside_a_worktree_is_judged_the_same(self) -> None:
        self.set_commands(test="true")
        self.commit_all("planned")
        self.ok("claim", "--commit", "T1")
        self.ok("worktree", "create", "T1")
        where = self.root / ".workstream" / "worktrees" / "t1"
        payload = {"tool_input": {"file_path": "workstreams/alpha/PROGRESS.md"}, "cwd": str(where)}
        self.assertIn("`ws settle`", hook.decide(json.dumps(payload)))
        payload["tool_input"]["file_path"] = "workstreams/alpha/evidence/T1.md"
        self.assertIsNone(hook.decide(json.dumps(payload)))

    def test_any_folder_the_registry_knows_is_covered(self) -> None:
        self.ok("new", "mod", "--title", "M", "--summary", "s", "--under", "sub")
        self.assertTrue(self.denied("sub/workstreams/mod/PROGRESS.md"))


class FailingOpenTests(HookCase):
    def test_bad_input_allows(self) -> None:
        for raw in ("", "not json", "[]", "null", '{"tool_input": 3}', '{"toolArgs": null}',
                    '{"cwd": 7, "tool_input": {"file_path": "x"}}'):
            with self.subTest(raw=raw):
                self.assertEqual(self.run_hook(raw), (0, "", ""))

    def test_outside_a_project_allows(self) -> None:
        payload = {"tool_input": {"file_path": "/tmp/tasks_list.json"}, "cwd": "/tmp"}
        self.assertEqual(self.run_hook(payload)[0], 0)

    def test_a_broken_config_allows(self) -> None:
        (self.root / ".workstream" / "config.toml").write_text("not toml =\n")
        self.assertEqual(self.run_hook(self.claude("workstreams/workstreams.json"))[0], 0)

    def test_a_broken_registry_allows(self) -> None:
        self.registry.write_text("{broken")
        self.assertEqual(self.run_hook(self.claude("workstreams/alpha/PROGRESS.md"))[0], 0)

    def test_a_crash_inside_allows(self) -> None:
        with mock.patch.object(hook, "decide", side_effect=RuntimeError("boom")):
            self.assertEqual(self.run_hook(self.claude("x"))[0], 0)

    def test_unknown_arguments_from_a_version_skew_allow(self) -> None:
        err = io.StringIO()
        with redirect_stderr(err):
            self.assertEqual(main(["hook", "pre-edit", "--format", "from-the-future"]), 0)


class FormatTests(HookCase):
    def test_exit_code_format_blocks_with_stderr(self) -> None:
        code, out, err = self.run_hook(self.claude("workstreams/alpha/PROGRESS.md"))
        self.assertEqual((code, out), (2, ""))
        self.assertIn("written by `ws settle`", err)

    def test_json_format_denies_on_stdout_and_exits_zero(self) -> None:
        code, out, err = self.run_hook(self.copilot("workstreams/alpha/PROGRESS.md"), hook.JSON)
        self.assertEqual((code, err), (0, ""))
        decision = json.loads(out)
        self.assertEqual(decision["permissionDecision"], "deny")
        self.assertIn("written by `ws settle`", decision["permissionDecisionReason"])

    def test_allowing_says_nothing_in_either_format(self) -> None:
        self.assertEqual(self.run_hook(self.claude("src/a.py")), (0, "", ""))
        self.assertEqual(self.run_hook(self.copilot("src/a.py"), hook.JSON), (0, "", ""))


class PayloadTests(HookCase):
    PROTECTED = "workstreams/alpha/PROGRESS.md"

    def test_arguments_as_an_object(self) -> None:
        self.assertTrue(hook.decide(json.dumps(self.copilot(self.PROTECTED))))

    def test_arguments_as_a_json_string(self) -> None:
        payload = self.copilot(self.PROTECTED)
        payload["toolArgs"] = json.dumps(payload["toolArgs"])
        self.assertTrue(hook.decide(json.dumps(payload)))

    def test_a_patch_as_bare_text(self) -> None:
        payload = self.copilot("")
        payload["toolArgs"] = f"*** Begin Patch\n*** Update File: {self.PROTECTED}\n@@\n*** End Patch\n"
        self.assertTrue(hook.decide(json.dumps(payload)))

    def test_a_patch_inside_an_argument(self) -> None:
        payload = {"toolName": "apply_patch", "cwd": str(self.root),
                   "toolArgs": {"input": f"*** Add File: src/ok.py\n*** Delete File: {self.PROTECTED}\n"}}
        self.assertTrue(hook.decide(json.dumps(payload)))

    def test_a_patch_touching_only_code_is_fine(self) -> None:
        payload = self.copilot("")
        payload["toolArgs"] = "*** Update File: src/a.py\n"
        self.assertIsNone(hook.decide(json.dumps(payload)))


class SettingsTests(HookCase):
    settings = ".claude/settings.json"

    def data(self) -> dict:
        return json.loads((self.root / self.settings).read_text())

    def test_off_by_default(self) -> None:
        self.ok("adapt", CLAUDE)
        self.ok("adapt", COPILOT)
        self.assertNotIn("hooks", self.data())
        self.assertFalse((self.root / ".github" / "hooks" / "ws.json").exists())

    def test_on_for_one_agent_merges_into_settings(self) -> None:
        self.ok("adapt", CLAUDE, "--hook")
        entry = self.data()["hooks"]["PreToolUse"][0]
        self.assertIn("Edit", entry["matcher"])
        self.assertEqual(entry["hooks"][0]["command"], "ws hook pre-edit --format exit-code")

    def test_on_for_the_other_writes_its_own_file(self) -> None:
        self.ok("adapt", COPILOT, "--hook")
        data = json.loads((self.root / ".github" / "hooks" / "ws.json").read_text())
        self.assertEqual(data["version"], 1)
        entry = data["hooks"]["preToolUse"][0]
        self.assertEqual(entry["bash"], "ws hook pre-edit --format json")
        self.assertIn("apply_patch", entry["matcher"])

    def test_other_hooks_survive_and_running_twice_adds_nothing(self) -> None:
        (self.root / ".claude").mkdir()
        mine = {"matcher": "Bash", "hooks": [{"type": "command", "command": "mine"}]}
        (self.root / self.settings).write_text(json.dumps({"hooks": {"PreToolUse": [mine],
                                                                     "Stop": []}}))
        self.ok("adapt", CLAUDE, "--hook")
        self.ok("adapt", CLAUDE, "--hook")
        hooks = self.data()["hooks"]
        self.assertEqual(hooks["PreToolUse"][0], mine)
        self.assertEqual(len(hooks["PreToolUse"]), 2)
        self.assertEqual(hooks["Stop"], [])

    def test_it_stays_on_when_adapt_runs_again(self) -> None:
        self.ok("adapt", CLAUDE, "--hook")
        self.ok("adapt", CLAUDE)
        self.assertIn("PreToolUse", self.data()["hooks"])

    def test_turning_it_off_takes_out_only_ours(self) -> None:
        (self.root / ".claude").mkdir()
        mine = {"matcher": "Bash", "hooks": [{"type": "command", "command": "mine"}]}
        (self.root / self.settings).write_text(json.dumps({"hooks": {"PreToolUse": [mine]}}))
        self.ok("adapt", CLAUDE, "--hook")
        self.ok("adapt", CLAUDE, "--no-hook")
        self.assertEqual(self.data()["hooks"]["PreToolUse"], [mine])

    def test_turning_it_off_removes_the_other_agents_file(self) -> None:
        self.ok("adapt", COPILOT, "--hook")
        self.ok("adapt", COPILOT, "--no-hook")
        self.assertFalse((self.root / ".github" / "hooks" / "ws.json").exists())
        self.assertEqual(self.ok("adapt", COPILOT, "--check").strip(), "OK")

    def test_a_removed_hook_is_drift(self) -> None:
        self.ok("adapt", CLAUDE, "--hook")
        data = self.data()
        del data["hooks"]
        (self.root / self.settings).write_text(json.dumps(data))
        self.assertIn(f"{self.settings}: missing", self.fails("adapt", CLAUDE, "--check"))

    def test_a_plugin_can_carry_it(self) -> None:
        out = self.root.parent / "plugin"
        self.ok("adapt", CLAUDE, "--plugin", str(out), "--hook")
        data = json.loads((out / "hooks" / "hooks.json").read_text())
        self.assertIn("PreToolUse", data["hooks"])


class DoctorTests(HookCase):
    def gate(self, name: str) -> dict | None:
        data = json.loads(self.ws("doctor", "--json")[1])
        return next((g for g in data if g["name"] == name), None)

    def test_it_only_asks_about_path_once_adapted(self) -> None:
        self.assertIsNone(self.gate("`ws` is on PATH"))
        self.ok("adapt", CLAUDE)
        self.assertIsNotNone(self.gate("`ws` is on PATH"))

    def test_missing_ws_warns_and_explains_the_stakes_with_a_hook(self) -> None:
        self.ok("adapt", COPILOT, "--hook")
        with mock.patch("shutil.which", return_value=None):
            gate = self.gate("`ws` is on PATH")
        self.assertFalse(gate["ok"])
        self.assertIn("denies every edit", gate["detail"])

    def test_the_adapter_data_names_a_real_format(self) -> None:
        for name in adapt.names():
            command = adapt.load(name).raw["hook"]["command"]
            self.assertIn(command.rsplit(" ", 1)[1], hook.FORMATS)

    def test_no_stack_or_agent_in_the_hook(self) -> None:
        self.assertNotIn("Copilot", Path(hook.__file__).read_text())
