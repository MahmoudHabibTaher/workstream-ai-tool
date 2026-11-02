"""`ws adapt`: generated files, their drift, and never overwriting what someone wrote."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path
from unittest import mock

from tests.helpers import WsTestCase
from workstream import adapt, protocol

REAL = os.environ.get("WS_REAL_TOOLS") == "1"
CLAUDE, COPILOT = "claude-code", "copilot-cli"
SKILL_DIR = {CLAUDE: ".claude/skills", COPILOT: ".github/skills"}
INSTRUCTIONS = {CLAUDE: "CLAUDE.md", COPILOT: ".github/copilot-instructions.md"}


class AdaptCase(WsTestCase):
    def path(self, rel: str) -> Path:
        return self.root / rel

    def skill(self, agent: str = CLAUDE, name: str = "ws-run") -> Path:
        return self.path(f"{SKILL_DIR[agent]}/{name}/SKILL.md")


class WritingTests(AdaptCase):
    def test_each_agent_gets_every_skill_where_its_docs_say(self) -> None:
        for agent in (CLAUDE, COPILOT):
            self.ok("adapt", agent)
            for name in protocol.skill_names():
                self.assertIn(f"name: {name}\n", self.skill(agent, name).read_text())

    def test_listing(self) -> None:
        self.assertIn(f"agents: {CLAUDE}, {COPILOT}; adapted here: none", self.ok("adapt"))
        self.ok("adapt", CLAUDE)
        self.assertIn(f"adapted here: {CLAUDE}", self.ok("adapt"))

    def test_an_unknown_agent_names_the_real_ones(self) -> None:
        self.assertIn("there is: claude-code", self.fails("adapt", "nope"))

    def test_running_it_again_changes_nothing(self) -> None:
        self.ok("adapt", CLAUDE)
        self.commit_all("adapted")
        self.assertIn("0 written", self.ok("adapt", CLAUDE))
        self.assertEqual(self.git("status", "--porcelain"), "")

    def test_a_manifest_records_each_file(self) -> None:
        self.ok("adapt", CLAUDE)
        manifest = json.loads(self.path(adapt.MANIFEST_REL).read_text())
        self.assertIn(f"{SKILL_DIR[CLAUDE]}/ws-run/SKILL.md", manifest["adapters"][CLAUDE]["files"])

    def test_two_agents_share_a_manifest(self) -> None:
        self.ok("adapt", CLAUDE)
        self.ok("adapt", COPILOT)
        self.assertEqual(adapt.adapted(self.project()), [CLAUDE, COPILOT])


class PointerTests(AdaptCase):
    def test_it_creates_the_file_when_absent(self) -> None:
        self.ok("adapt", COPILOT)
        text = self.path(INSTRUCTIONS[COPILOT]).read_text()
        self.assertIn(protocol.POINTER_FILE.read_text().strip(), text)

    def test_it_keeps_what_was_there(self) -> None:
        self.path("CLAUDE.md").write_text("# Mine\n\nDon't touch this.\n")
        self.ok("adapt", CLAUDE)
        text = self.path("CLAUDE.md").read_text()
        self.assertTrue(text.startswith("# Mine\n\nDon't touch this.\n"))
        self.assertIn(adapt.BLOCK_START, text)

    def test_it_does_not_repeat(self) -> None:
        self.ok("adapt", CLAUDE)
        self.ok("adapt", CLAUDE)
        self.assertEqual(self.path("CLAUDE.md").read_text().count(adapt.BLOCK_START), 1)

    def test_a_changed_block_is_replaced_in_place(self) -> None:
        self.path("CLAUDE.md").write_text(f"before\n\n{adapt.BLOCK_START}\nold\n{adapt.BLOCK_END}\n\nafter\n")
        self.ok("adapt", CLAUDE)
        text = self.path("CLAUDE.md").read_text()
        self.assertNotIn("old", text)
        self.assertLess(text.index("before"), text.index(adapt.BLOCK_START))
        self.assertLess(text.index(adapt.BLOCK_END), text.index("after"))


class DriftTests(AdaptCase):
    def test_check_passes_when_current(self) -> None:
        self.ok("adapt", CLAUDE)
        self.assertEqual(self.ok("adapt", CLAUDE, "--check").strip(), "OK")

    def test_check_finds_a_missing_file(self) -> None:
        self.ok("adapt", CLAUDE)
        self.skill().unlink()
        self.assertIn("ws-run/SKILL.md: missing", self.fails("adapt", CLAUDE, "--check"))

    def test_check_finds_an_edited_file(self) -> None:
        self.ok("adapt", CLAUDE)
        self.skill().write_text("mine\n")
        self.assertIn("ws-run/SKILL.md: edited", self.fails("adapt", CLAUDE, "--check"))

    def test_check_finds_a_removed_pointer(self) -> None:
        self.ok("adapt", CLAUDE)
        self.path("CLAUDE.md").write_text("# gone\n")
        self.assertIn("CLAUDE.md: missing", self.fails("adapt", CLAUDE, "--check"))

    def test_a_newer_ws_makes_files_stale_and_refreshes_them(self) -> None:
        self.ok("adapt", CLAUDE)
        original = protocol.skill_text("ws-run")
        with mock.patch.object(adapt.protocol, "skill_text",
                               lambda name: original + "\nNew rule.\n" if name == "ws-run"
                               else protocol.PROTOCOL_FILE.parent.joinpath(
                                   "skills", name, "SKILL.md").read_text()):
            self.assertIn("ws-run/SKILL.md: stale", self.fails("adapt", CLAUDE, "--check"))
            self.assertIn("1 written", self.ok("adapt", CLAUDE))
            self.assertIn("New rule.", self.skill().read_text())

    def test_doctor_warns_about_drift(self) -> None:
        self.assertNotIn("agent files", self.ok("doctor").replace("ok   the agent files", ""))
        self.ok("adapt", CLAUDE)
        self.skill().unlink()
        out = self.ok("doctor")
        self.assertIn(f"warn the agent files are current: `ws adapt {CLAUDE}`", out)

    def test_a_broken_manifest_is_a_warning_not_a_traceback(self) -> None:
        self.path(adapt.MANIFEST_REL).write_text("{broken")
        self.assertIn("not valid JSON", self.ok("doctor"))


class HandEditTests(AdaptCase):
    def test_an_edited_file_is_refused_and_nothing_is_written(self) -> None:
        self.ok("adapt", CLAUDE)
        self.skill().write_text("mine\n")
        other = self.skill(name="ws-plan")
        other.unlink()
        self.assertIn("edited by hand", self.fails("adapt", CLAUDE))
        self.assertEqual(self.skill().read_text(), "mine\n")
        self.assertFalse(other.exists())

    def test_force_overwrites_it(self) -> None:
        self.ok("adapt", CLAUDE)
        self.skill().write_text("mine\n")
        self.ok("adapt", CLAUDE, "--force")
        self.assertIn("name: ws-run", self.skill().read_text())

    def test_a_file_that_was_there_first_is_not_ours(self) -> None:
        self.skill().parent.mkdir(parents=True)
        self.skill().write_text("someone's own skill\n")
        self.assertIn("edited by hand, or not ours", self.fails("adapt", CLAUDE))
        self.assertEqual(self.skill().read_text(), "someone's own skill\n")


class WorkerTests(AdaptCase):
    def test_each_agent_gets_a_worker_that_can_not_spawn(self) -> None:
        self.ok("adapt", CLAUDE)
        self.ok("adapt", COPILOT)
        claude = self.path(".claude/agents/ws-worker.md").read_text()
        copilot = self.path(".github/agents/ws-worker.agent.md").read_text()
        self.assertIn("tools: Read, Edit, Write, Bash, Grep, Glob\n", claude)
        self.assertNotIn("Agent", claude.split("---")[1])
        self.assertIn('tools: ["read", "grep", "glob", "edit", "execute"]\n', copilot)
        self.assertIn("strict-tools-list: true", copilot)
        self.assertNotIn('"task"', copilot)
        for text in (claude, copilot):
            self.assertIn("`ws brief`", text.split("---")[2])
            self.assertIn("name: ws-worker\n", text)

    def test_a_copilot_worker_keeps_the_projects_rules(self) -> None:
        self.ok("adapt", COPILOT)
        self.assertIn("include-custom-instructions: true",
                      self.path(".github/agents/ws-worker.agent.md").read_text())


class NoteTests(AdaptCase):
    def test_ws_run_says_how_to_start_a_worker_and_not_to_isolate(self) -> None:
        self.ok("adapt", CLAUDE)
        text = self.skill().read_text()
        self.assertIn("## On Claude Code", text)
        self.assertIn('`subagent_type: "ws-worker"`', text)
        self.assertIn("no `isolation` setting", text)

    def test_copilot_passes_its_model_explicitly(self) -> None:
        self.ok("adapt", COPILOT)
        text = self.skill(COPILOT).read_text()
        self.assertIn("`task` tool: agent type `ws-worker`", text)
        self.assertIn("`model` set to the model you are running as", text)

    def test_a_skill_with_no_note_is_left_as_it_is(self) -> None:
        self.ok("adapt", CLAUDE)
        self.assertEqual(self.skill(name="ws-review").read_text(), protocol.skill_text("ws-review"))

    def test_the_shared_skills_stay_free_of_agents(self) -> None:
        self.assertNotIn("subagent_type", protocol.skill_text("ws-run"))


class SettingsTests(AdaptCase):
    settings = ".claude/settings.json"

    def test_it_allows_what_a_background_worker_needs_and_no_push(self) -> None:
        self.ok("adapt", CLAUDE)
        allow = json.loads(self.path(self.settings).read_text())["permissions"]["allow"]
        self.assertIn("Bash(ws *)", allow)
        self.assertIn("Bash(git commit *)", allow)
        self.assertFalse([a for a in allow if "push" in a])

    def test_it_keeps_everything_that_was_there(self) -> None:
        self.path(".claude").mkdir()
        self.path(self.settings).write_text(json.dumps({
            "model": "x", "permissions": {"allow": ["Bash(ls *)"], "deny": ["Bash(rm *)"]},
            "hooks": {"Stop": []}}))
        self.ok("adapt", CLAUDE)
        data = json.loads(self.path(self.settings).read_text())
        self.assertEqual((data["model"], data["hooks"]), ("x", {"Stop": []}))
        self.assertEqual(data["permissions"]["deny"], ["Bash(rm *)"])
        self.assertEqual(data["permissions"]["allow"][0], "Bash(ls *)")
        self.assertIn("Bash(ws *)", data["permissions"]["allow"])

    def test_running_it_twice_adds_nothing(self) -> None:
        self.ok("adapt", CLAUDE)
        first = self.path(self.settings).read_text()
        self.ok("adapt", CLAUDE)
        self.assertEqual(self.path(self.settings).read_text(), first)

    def test_broken_settings_are_refused_and_left_alone(self) -> None:
        self.path(".claude").mkdir()
        self.path(self.settings).write_text("{broken")
        self.assertIn("isn't valid JSON", self.fails("adapt", CLAUDE))
        self.assertEqual(self.path(self.settings).read_text(), "{broken")
        self.assertFalse(self.skill().exists())

    def test_a_removed_rule_is_drift(self) -> None:
        self.ok("adapt", CLAUDE)
        self.path(self.settings).write_text("{}")
        self.assertIn(f"{self.settings}: missing", self.fails("adapt", CLAUDE, "--check"))

    def test_an_agent_without_settings_writes_none(self) -> None:
        self.ok("adapt", COPILOT)
        self.assertFalse(self.path(".github/copilot/settings.json").exists())


class PluginTests(AdaptCase):
    def test_it_writes_a_plugin_with_names_as_a_plugin_has_them(self) -> None:
        out = self.root.parent / "plugin"
        self.ok("adapt", CLAUDE, "--plugin", str(out))
        manifest = json.loads((out / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["name"], "workstream")
        self.assertIn('`subagent_type: "workstream:ws-worker"`',
                      (out / "skills" / "ws-run" / "SKILL.md").read_text())
        self.assertIn("name: ws-worker\n", (out / "agents" / "ws-worker.md").read_text())
        self.assertFalse(self.skill().exists(), "a plugin doesn't touch the project")

    def test_an_agent_with_no_plugin_form_says_so(self) -> None:
        self.assertIn("no plugin form", self.fails("adapt", COPILOT, "--plugin", "x"))

    @unittest.skipUnless(REAL and shutil.which("claude"), "needs WS_REAL_TOOLS=1 and the CLI")
    def test_the_real_validator_accepts_it(self) -> None:
        out = self.root.parent / "plugin"
        self.ok("adapt", CLAUDE, "--plugin", str(out))
        proc = subprocess.run(["claude", "plugin", "validate", str(out)], capture_output=True,
                              text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)


class LiteralTests(AdaptCase):
    def test_no_agent_is_named_in_the_engine_or_the_skills(self) -> None:
        engine = Path(adapt.__file__).read_text()
        for name in (CLAUDE, COPILOT, "CLAUDE.md", ".github"):
            self.assertIsNone(re.search(re.escape(name), engine), name)
