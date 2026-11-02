"""`ws adapt`: generated files, their drift, and never overwriting what someone wrote."""

from __future__ import annotations

import json
import re
from pathlib import Path
from unittest import mock

from tests.helpers import WsTestCase
from workstream import adapt, protocol

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


class LiteralTests(AdaptCase):
    def test_no_agent_is_named_in_the_engine_or_the_skills(self) -> None:
        engine = Path(adapt.__file__).read_text()
        for name in (CLAUDE, COPILOT, "CLAUDE.md", ".github"):
            self.assertIsNone(re.search(re.escape(name), engine), name)
