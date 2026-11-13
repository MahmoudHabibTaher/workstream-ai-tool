"""The pane in ui/mod: it names no project, and the real CLI answers what it asks.

The mod's own tests stub `ws`, and need the agent's CLI to run, so they stay in `make test-mod`.
These run everywhere, and they're what would notice a command the mod calls changing shape.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.helpers import WsTestCase, task
from workstream.snapshot import LAUNCH_PROMPTS

MOD = Path(__file__).resolve().parent.parent / "ui" / "mod"
FORBIDDEN = re.compile(r"\b(develop|subsonic|the Kotlin harness|cargo|gradle|manage_workstreams|python3"
                       r"|dispatch-tasks|coordinate-workstream)\b|\bworkstreams/", re.IGNORECASE)


class NamesNoProjectTests(WsTestCase):
    def test_the_mods_code_is_generic(self) -> None:
        found = [f"{p.relative_to(MOD)}:{n}: {line.strip()}"
                 for folder in ("hooks", "types") for p in sorted((MOD / folder).rglob("*.ts*"))
                 for n, line in enumerate(p.read_text().splitlines(), 1) if FORBIDDEN.search(line)]
        self.assertEqual(found, [])

    def test_no_file_holds_a_launch_prompt(self) -> None:
        # The CLI owns these texts and the pane reads them from each row's launches. Each
        # prompt's words up to its first placeholder must appear nowhere under ui/mod.
        stems = [text.split("{", 1)[0].strip() for text in LAUNCH_PROMPTS.values()]
        self.assertTrue(all(len(stem) > 10 for stem in stems), stems)
        found = [f"{p.relative_to(MOD)}: {stem}" for p in sorted(MOD.rglob("*"))
                 if p.is_file() and "node_modules" not in p.parts
                 for stem in stems if stem in p.read_text(errors="ignore")]
        self.assertEqual(found, [])


class TheCliAnswersThePaneTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.set_commands(test="true")
        self.seed_ok([task("T1", 10, verify=["test"], acceptance=["works"], files=[])])
        self.commit_all("seeded")

    def test_the_commands_data_ts_runs(self) -> None:
        source = (MOD / "hooks" / "data.ts").read_text()
        for line in ("[WS, 'root']", "[WS, 'act', confirm.action, '-w', ws]",
                     "[WS, 'review', task, '-w', ws,", "[WS, 'snapshot', ...(id ? ['-w', id] : [])]"):
            self.assertIn(line, source)
        self.assertEqual(self.ok("root").strip(), str(self.root))
        whole = json.loads(self.ok("snapshot"))
        snap = json.loads(self.ok("snapshot", "-w", "alpha"))
        self.assertEqual(whole["snapshotVersion"], 1)
        self.assertTrue(snap["watch"] and snap["integrationBranch"] and snap["revisions"]["registry"])
        found = snap["tasks"][0]
        self.assertEqual((found["verifyCommands"][0]["command"], found["acceptanceText"]), ("true", ["works"]))
        review = json.loads(self.ok("review", "T1", "-w", "alpha"))
        self.assertEqual((review["task"], review["range"]["kind"]), ("T1", "none"))
        out = self.ok("act", "pause", "-w", "alpha", "--expect-registry", snap["revisions"]["registry"],
                      "--expect-tasks", snap["revisions"]["tasks"]["alpha"])
        self.assertIn("alpha: pause", out)

    def test_launch_check_and_the_task_prompt_answer_the_pane(self) -> None:
        # data.ts's pre-flight and run-task argv, sent as the pane sends them, to the real CLI.
        source = (MOD / "hooks" / "data.ts").read_text()
        for line in ("[WS, 'launch', 'check', '-w', ws, '--kind', kind, ...(task ? ['--task', task] : []), '--json']",
                     "[WS, 'launch', 'argv', '-w', ws, '--agent', PROMPT_AGENT, '--prompt-kind', 'run-task', "
                     "'--task', task, '--json']",
                     "export const PROMPT_AGENT = 'claude-code'"):
            self.assertIn(line, source)
        snap = json.loads(self.ok("snapshot", "-w", "alpha"))
        kinds = [launch["kind"] for launch in snap["registry"][0]["launches"]]
        self.assertEqual(kinds, ["run", "coordinate", "close", "abandon"])
        for kind in kinds:
            checks = json.loads(self.ok("launch", "check", "-w", "alpha", "--kind", kind, "--json"))["checks"]
            self.assertTrue(checks, kind)
            for check in checks:
                self.assertEqual(set(check), {"id", "ok", "blocking", "message"}, kind)
        pinned = json.loads(self.ok("launch", "check", "-w", "alpha", "--kind", "run-task", "--task", "T1", "--json"))
        self.assertIn("validate", [c["id"] for c in pinned["checks"]])
        built = json.loads(self.ok("launch", "argv", "-w", "alpha", "--agent", "claude-code",
                                   "--prompt-kind", "run-task", "--task", "T1", "--json"))["argv"]
        self.assertEqual(built[-1], LAUNCH_PROMPTS["run-task"].format(ws="alpha", task="T1"))
        # A task the queue doesn't hold is a refusal, which the pane draws as its stderr line.
        code, _, err = self.ws("launch", "check", "-w", "alpha", "--kind", "run-task", "--task", "T9", "--json")
        self.assertEqual(code, 1)
        self.assertIn("T9", err)
