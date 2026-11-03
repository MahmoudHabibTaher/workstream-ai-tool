"""The pane in ui/mod: it names no project, and the real CLI answers what it asks.

The mod's own tests stub `ws`, and need the agent's CLI to run, so they stay in `make test-mod`.
These run everywhere, and they're what would notice a command the mod calls changing shape.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tests.helpers import WsTestCase, task

MOD = Path(__file__).resolve().parent.parent / "ui" / "mod"
FORBIDDEN = re.compile(r"\b(develop|subsonic|the Kotlin harness|cargo|gradle|manage_workstreams|python3"
                       r"|dispatch-tasks|coordinate-workstream)\b|\bworkstreams/", re.IGNORECASE)


class NamesNoProjectTests(WsTestCase):
    def test_the_mods_code_is_generic(self) -> None:
        found = [f"{p.relative_to(MOD)}:{n}: {line.strip()}"
                 for folder in ("hooks", "types") for p in sorted((MOD / folder).rglob("*.ts*"))
                 for n, line in enumerate(p.read_text().splitlines(), 1) if FORBIDDEN.search(line)]
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
