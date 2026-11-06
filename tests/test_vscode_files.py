"""The VS Code extension in ui/vscode: its logic passes under node, its code names no project or
agent and makes no markup from repo text, and the real CLI accepts every argv cli.ts builds.

`make test-vscode` runs it inside VS Code, which needs the app installed, so it stays local.
These run everywhere, and they're what would notice a command the extension calls changing shape.
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import unittest
from pathlib import Path

from tests.helpers import WsTestCase, task
from workstream.config import load_config

REPO = Path(__file__).resolve().parent.parent
PACKAGE = REPO / "ui" / "vscode"
SRC = PACKAGE / "src"
NODE = shutil.which("node")
FORBIDDEN = re.compile(
    r"\b(develop|subsonic|the Kotlin harness|work|cargo|gradle|npm|manage_workstreams|python3"
    r"|dispatch-tasks|coordinate-workstream|claude|copilot|anthropic|openai|codex)\b"
    r"|\bworkstreams/", re.IGNORECASE)
# Repo text in a MarkdownString would render as markup (plan T6), so nothing turns either on.
MARKUP = re.compile(r"isTrusted\s*[:=]\s*true|supportHtml\s*[:=]\s*true|innerHTML|\.html\s*=")


def sources() -> list[Path]:
    return sorted(SRC.rglob("*.ts"))


class NamesNoProjectTests(unittest.TestCase):
    def test_finds_the_sources(self) -> None:
        self.assertIn(SRC / "cli.ts", sources())
        self.assertIn(SRC / "extension.ts", sources())

    def test_the_extensions_code_is_generic(self) -> None:
        found = [f"{p.relative_to(PACKAGE)}:{n}: {line.strip()}" for p in sources()
                 for n, line in enumerate(p.read_text().splitlines(), 1) if FORBIDDEN.search(line)]
        self.assertEqual(found, [])

    def test_no_markup_sink(self) -> None:
        found = [f"{p.relative_to(PACKAGE)}:{n}: {line.strip()}" for p in sources()
                 for n, line in enumerate(p.read_text().splitlines(), 1) if MARKUP.search(line)]
        self.assertEqual(found, [])

    def test_only_cli_ts_runs_processes_and_logic_never_imports_vscode(self) -> None:
        for path in sources():
            text = path.read_text()
            if path.name != "cli.ts":
                self.assertNotIn("child_process", text, path.name)
            if path.parent.name == "logic":
                self.assertNotRegex(text, r"from 'vscode'", path.name)
        self.assertNotIn("shell: true", (SRC / "cli.ts").read_text())


class PackageTests(unittest.TestCase):
    def test_the_manifest(self) -> None:
        manifest = json.loads((PACKAGE / "package.json").read_text())
        self.assertEqual(manifest["engines"]["vscode"], "^1.100.0")
        self.assertEqual(manifest["capabilities"]["untrustedWorkspaces"]["supported"], False)
        self.assertEqual(manifest["capabilities"]["virtualWorkspaces"], False)
        self.assertNotIn("dependencies", manifest)
        self.assertTrue(manifest["devDependencies"]["@types/vscode"].startswith("~1.100."))
        setting = manifest["contributes"]["configuration"]["properties"]["workstreams.wsCommand"]
        self.assertEqual((setting["type"], setting["default"]), ("array", ["ws"]))
        self.assertTrue((PACKAGE / "package-lock.json").is_file())

    def test_the_typescript_stays_erasable(self) -> None:
        options = json.loads((PACKAGE / "tsconfig.json").read_text())["compilerOptions"]
        for key in ("erasableSyntaxOnly", "allowImportingTsExtensions", "rewriteRelativeImportExtensions"):
            self.assertIs(options[key], True, key)

    def test_a_worktree_installs_the_locked_dependencies(self) -> None:
        self.assertIn("cd ui/vscode && npm ci", load_config(REPO / ".workstream" / "config.toml").worktree_setup)


@unittest.skipUnless(NODE, "no node here; the extension's logic is checked where there is one")
class LogicTests(unittest.TestCase):
    def test_the_logic_modules(self) -> None:
        tests = sorted(str(p) for p in (PACKAGE / "test" / "logic").glob("*.test.ts"))
        self.assertTrue(tests)
        done = subprocess.run([NODE, "--disable-warning=MODULE_TYPELESS_PACKAGE_JSON", "--test", *tests],
                              cwd=PACKAGE, capture_output=True, text=True)
        self.assertEqual(done.returncode, 0, done.stdout[-3000:] + done.stderr[-1000:])


class TheCliAnswersTheExtensionTests(WsTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.new_ws()
        self.set_commands(test="true")
        self.seed_ok([task("T1", 10, verify=["test"], acceptance=["works"], files=[])])
        self.commit_all("seeded")

    def accepted(self, *argv: str) -> None:
        """argparse took the argv: whatever the CLI then decided, it didn't print usage."""
        code, out, err = self.ws(*argv)
        self.assertNotEqual(code, 2, err)
        self.assertNotIn("usage:", err)

    def test_every_argv_cli_ts_builds(self) -> None:
        source = (SRC / "cli.ts").read_text()
        for line in ("['root']", "['snapshot', ...(id ? ['-w', id] : [])]",
                     "['review', task, '-w', wsId, ...(ask.checks ? ['--checks'] : []), ...(ask.file ? ['--file', ask.file] : [])]",
                     "['review', '--queue']", "['audit', 'context', '--json']",
                     "['act', confirm.action, '-w', wsId]", "args.push('--task', confirm.task)",
                     "args.push('--expect-registry', revisions.registry)", "args.push('--expect-tasks', tasks)"):
            self.assertIn(line, source)
        self.assertEqual(self.ok("root").strip(), str(self.root))
        self.assertEqual(json.loads(self.ok("snapshot"))["snapshotVersion"], 1)
        snap = json.loads(self.ok("snapshot", "-w", "alpha"))
        self.assertEqual(snap["snapshotVersion"], 1)
        self.assertEqual(json.loads(self.ok("review", "T1", "-w", "alpha"))["task"], "T1")
        self.assertEqual(json.loads(self.ok("review", "T1", "-w", "alpha", "--checks"))["task"], "T1")
        self.accepted("review", "T1", "-w", "alpha", "--file", "a.txt")
        self.assertIsInstance(json.loads(self.ok("review", "--queue")), (dict, list))
        self.assertIsInstance(json.loads(self.ok("audit", "context", "--json")), list)
        registry, tasks = snap["revisions"]["registry"], snap["revisions"]["tasks"]["alpha"]
        self.accepted("act", "unclaim", "-w", "alpha", "--task", "T1", "--expect-registry", registry,
                      "--expect-tasks", tasks)
        self.assertIn("alpha: pause", self.ok("act", "pause", "-w", "alpha", "--expect-registry", registry,
                                              "--expect-tasks", tasks))


if __name__ == "__main__":
    unittest.main()
