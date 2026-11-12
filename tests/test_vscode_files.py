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
        """Plan T1: agent names live in chat.ts alone, which holds the chat targets."""
        found = [f"{p.relative_to(PACKAGE)}:{n}: {line.strip()}" for p in sources()
                 for n, line in enumerate(p.read_text().splitlines(), 1) if FORBIDDEN.search(line)]
        self.assertEqual([f for f in found if not f.startswith("src/chat.ts:")], [])
        self.assertTrue(found, "chat.ts names the agent extensions it targets")
        # Nothing but agent names: no project, build tool or skill name in chat.ts either.
        project = re.compile(FORBIDDEN.pattern.replace("|claude|copilot|anthropic|openai|codex", ""), re.IGNORECASE)
        self.assertEqual([line for line in (SRC / "chat.ts").read_text().splitlines() if project.search(line)], [])

    def test_no_markup_sink(self) -> None:
        found = [f"{p.relative_to(PACKAGE)}:{n}: {line.strip()}" for p in sources()
                 for n, line in enumerate(p.read_text().splitlines(), 1) if MARKUP.search(line)]
        self.assertEqual(found, [])

    def test_every_markdown_string_takes_repo_text_as_text(self) -> None:
        """Plan T6: one module builds MarkdownStrings, starts each empty with trust and HTML off,
        and appends markup only as literals; repo text goes in through appendText."""
        markdown = SRC / "markdown.ts"
        built = {p.name for p in sources() if "MarkdownString" in p.read_text()}
        self.assertEqual(built, {"markdown.ts"})
        text = markdown.read_text()
        constructed = re.findall(r"new vscode\.MarkdownString\((.*?)\)", text)
        self.assertEqual(constructed, [""])
        self.assertIn("md.isTrusted = false", text)
        self.assertIn("md.supportHtml = false", text)
        self.assertNotRegex(text, r"\.value\s*=|appendCodeblock")
        calls = re.findall(r"appendMarkdown\(([^)]*)\)", text)
        self.assertTrue(calls)
        for arg in calls:
            self.assertRegex(arg, r"^'[^'`$\\]*(\\n)*'$", "appendMarkdown takes only a literal")
        self.assertIn("md.appendText(section.heading)", text)
        self.assertIn("md.appendText(line)", text)
        for path in sources():
            for n, line in enumerate(path.read_text().splitlines(), 1):
                if path != markdown:
                    self.assertNotIn("appendMarkdown", line, f"{path.name}:{n}")
                if re.search(r"\.tooltip\s*=", line):
                    self.assertRegex(line, r"\.tooltip\s*=\s*(tooltip\(|')", f"{path.name}:{n}")

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

    def test_writes_and_launches_show_only_where_offered(self) -> None:
        """Plan D-ACTIONS: a write's menu entry keys on the `act:<write>` word the tree item's
        contextValue carries from the snapshot's offers, in the Workstreams, Tasks and Health trees;
        a launch keys on `launch`, in the Workstreams view only. None of them
        is in the command palette, where no tree item says what is offered."""
        contributes = json.loads((PACKAGE / "package.json").read_text())["contributes"]
        setting = contributes["configuration"]["properties"]["workstreams.agentCommand"]
        self.assertEqual((setting["type"], setting["default"]), ("array", []))
        commands = {c["command"] for c in contributes["commands"]}
        menu = {m["command"]: m["when"] for m in contributes["menus"]["view/item/context"]}
        hidden = {m["command"] for m in contributes["menus"]["commandPalette"] if m["when"] == "false"}
        for word, names in (("act:{}", ("pause", "resume", "sync", "unclaim")),
                            ("launch", ("run", "coordinate", "close", "abandon"))):
            for name in names:
                command = f"workstreams.{name}"
                self.assertIn(command, commands)
                self.assertIn(command, hidden)
                where = r"view =~ /^workstreams\.(list|tasks|health)$/" if word.startswith("act") else "view == workstreams.list"
                self.assertEqual(menu[command], f"{where} && viewItem =~ "
                                 f"/(^| ){word.format(name)}( |$)/")
        self.assertIn("contextValue(node.kind, node.writes, node.launch)", (SRC / "views" / "workstreams.ts").read_text())
        self.assertIn("contextValue(node.kind, node.writes)", (SRC / "views" / "tasks.ts").read_text())

    def test_one_prompt_table_with_the_web_uis_text(self) -> None:
        logic = (REPO / "src" / "workstream" / "assets" / "web" / "logic.js").read_text()
        body = logic[logic.index("export function promptText"):]
        body = body[:body.index("\n}\n")]
        web = re.findall(r"`([^`]*)`", body)
        self.assertEqual(len(web), 4)
        ours = (SRC / "logic" / "launch.ts").read_text()
        for text in web:
            self.assertIn(f"`{text}`", ours)
        self.assertEqual([p.name for p in sources() if "Use the ws-" in p.read_text()], ["launch.ts"])

    def test_launch_targets_live_in_one_module(self) -> None:
        """Plan D-ACTIONS: launch.ts holds every target; a caller only calls `launch`."""
        for path in sources():
            text = path.read_text()
            for sink in ("createTerminal", "clipboard.writeText", "sendText"):
                if sink in text:
                    self.assertEqual(path.relative_to(SRC).as_posix(), "launch.ts", sink)
        self.assertNotIn("sendText", (SRC / "launch.ts").read_text())
        self.assertIn("export const TARGETS: Target[] = [terminal, ...CHAT_TARGETS, clipboard]", (SRC / "launch.ts").read_text())
        self.assertIn("(await offeredTargets()).filter(", (SRC / "launchFlow.ts").read_text())
        # Plan T3, T4: Copilot Chat's command takes an options object in agent mode, and the Claude
        # Code URI's query comes from URLSearchParams, so the prompt can't break it.
        chat = (SRC / "chat.ts").read_text()
        self.assertIn("chatHost.execute(CHAT_OPEN, { query: request.prompt, mode: CHAT_MODE })", chat)
        self.assertIn("query: new URLSearchParams({ prompt }).toString()", chat)
        self.assertIn("chatHost.openExternal(claudeCodeUri(request.prompt))", chat)
        self.assertEqual([p.name for p in sources() if "openExternal" in p.read_text() or "executeCommand(command" in p.read_text()], ["chat.ts"])
        # Plan D-LAUNCH: the flow asks, then the caller starts the target the person picked.
        self.assertIn("await launchFlow(", (SRC / "commands.ts").read_text())
        self.assertIn("[settled.target])", (SRC / "commands.ts").read_text())
        self.assertIn("await launch({", (SRC / "commands.ts").read_text())

    def test_the_review_view_and_its_hidden_commands(self) -> None:
        """Plan D-REVIEW-UI: a Review view after the linked views (plan D-VIEWS); a file and the evidence open from
        its items only, so neither is in the command palette."""
        contributes = json.loads((PACKAGE / "package.json").read_text())["contributes"]
        self.assertEqual([v["id"] for v in contributes["views"]["workstreams-review"]], ["workstreams.review"])
        hidden = {m["command"] for m in contributes["menus"]["commandPalette"] if m["when"] == "false"}
        self.assertLessEqual({"workstreams.openReviewFile", "workstreams.openEvidence"}, hidden)
        review = (SRC / "views" / "review.ts").read_text()
        self.assertIn("registerTextDocumentContentProvider(SCHEME, docs)", (SRC / "extension.ts").read_text())
        self.assertIn("await vscode.commands.executeCommand('vscode.diff', left, right, title", review)

    def test_four_panel_containers(self) -> None:
        """vscode_followups D-PANELS: four panel containers, matching the JetBrains tool window's tabs, and no
        activity bar entry. The main container keeps the id `workstreams`, which VS Code remembers its place by."""
        contributes = json.loads((PACKAGE / "package.json").read_text())["contributes"]
        self.assertEqual(list(contributes["viewsContainers"]), ["panel"])
        panel = contributes["viewsContainers"]["panel"]
        self.assertEqual([c["id"] for c in panel],
                         ["workstreams", "workstreams-review", "workstreams-health", "workstreams-budget"])
        for container in panel:
            self.assertTrue((PACKAGE / container["icon"]).is_file(), container["icon"])
        self.assertEqual({k: [v["id"] for v in views] for k, views in contributes["views"].items()},
                         {"workstreams": ["workstreams.list", "workstreams.tasks", "workstreams.task",
                                          "workstreams.graph", "workstreams.overview"],
                          "workstreams-review": ["workstreams.review"],
                          "workstreams-health": ["workstreams.health"],
                          "workstreams-budget": ["workstreams.budget"]})

    def test_the_health_and_budget_views(self) -> None:
        """Plan D-REVIEW-UI: Health and Budget follow Review. A finding's quick fix calls the
        write command its menu does, so it goes through the same confirm; Budget is the one view
        that runs `ws audit context`."""
        contributes = json.loads((PACKAGE / "package.json").read_text())["contributes"]
        self.assertEqual([v["id"] for v in contributes["views"]["workstreams-health"]], ["workstreams.health"])
        self.assertEqual([v["id"] for v in contributes["views"]["workstreams-budget"]], ["workstreams.budget"])
        titles = {m["when"] for m in contributes["menus"]["view/title"] if m["command"] == "workstreams.refresh"}
        self.assertLessEqual({"view == workstreams.health", "view == workstreams.budget"}, titles)
        health = (SRC / "views" / "health.ts").read_text()
        self.assertIn("action.command = { command: commandOf(write), title: action.title, arguments: [fix.node] }", health)
        self.assertIn("contextValue(node.kind, node.writes)", health)
        self.assertEqual([p.name for p in sources() if "loadBudget(" in p.read_text()], ["cli.ts", "health.ts"])
        self.assertIn("registerCodeActionsProvider", (SRC / "extension.ts").read_text())

    def test_gate_and_range_lines_keep_the_web_uis_cases(self) -> None:
        """The ported gateSummary, rangeLine and statLine are tested with the web UI's own
        asserts, line for line."""
        web = (REPO / "ui" / "web" / "tests" / "logic.test.mjs").read_text()
        ours = (PACKAGE / "test" / "logic" / "format.test.ts").read_text()
        cases = [line.strip() for line in web.splitlines()
                 if re.match(r"\s*assert\.\w+\((gateSummary|rangeLine|statLine)\(", line)]
        self.assertEqual(len(cases), 8)
        for line in cases:
            self.assertIn(line, ours)

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
                     "['review', task, '-w', wsId, '--show', path, '--side', side]",
                     "['review', '--queue']", "['audit', 'context', '--json']",
                     "['act', confirm.action, '-w', wsId]", "args.push('--task', confirm.task)",
                     "args.push('--expect-registry', revisions.registry)", "args.push('--expect-tasks', tasks)",
                     "['launch', 'check', '-w', wsId, '--kind', kind, ...(agent ? ['--agent', agent] : []), '--json']",
                     "['launch', 'agents', '--json']",
                     "['launch', 'argv', '-w', wsId, '--agent', ask.agent, '--prompt-kind', ask.kind, `--prompt=${ask.prompt}`]",
                     "args.push('--effort', ask.effort)", "args.push('--permissions', ask.permissions)", "args.push('--json')"):
            self.assertIn(line, source)
        self.assertEqual(self.ok("root").strip(), str(self.root))
        self.assertEqual(json.loads(self.ok("snapshot"))["snapshotVersion"], 1)
        snap = json.loads(self.ok("snapshot", "-w", "alpha"))
        self.assertEqual(snap["snapshotVersion"], 1)
        self.assertEqual(json.loads(self.ok("review", "T1", "-w", "alpha"))["task"], "T1")
        self.assertEqual(json.loads(self.ok("review", "T1", "-w", "alpha", "--checks"))["task"], "T1")
        self.accepted("review", "T1", "-w", "alpha", "--file", "a.txt")
        for side in ("old", "new"):
            self.accepted("review", "T1", "-w", "alpha", "--show", "a.txt", "--side", side)
        self.assertIsInstance(json.loads(self.ok("review", "--queue")), (dict, list))
        self.assertIsInstance(json.loads(self.ok("audit", "context", "--json")), list)
        registry, tasks = snap["revisions"]["registry"], snap["revisions"]["tasks"]["alpha"]
        self.accepted("act", "unclaim", "-w", "alpha", "--task", "T1", "--expect-registry", registry,
                      "--expect-tasks", tasks)
        # The launch flow's reads: every kind it launches, with and without an agent, and an
        # agent's argv with its effort and permissions and a prompt that starts with a dash.
        agents = json.loads(self.ok("launch", "agents", "--json"))["agents"]
        self.assertTrue(agents)
        for kind in ("run", "coordinate", "close", "abandon"):
            checks = json.loads(self.ok("launch", "check", "-w", "alpha", "--kind", kind, "--json"))["checks"]
            self.assertTrue(all({"id", "ok", "blocking", "message"} <= set(c) for c in checks), checks)
        with_agent = json.loads(self.ok("launch", "check", "-w", "alpha", "--kind", "coordinate",
                                        "--agent", agents[0]["agent"], "--json"))["checks"]
        self.assertIn("skills", [c["id"] for c in with_agent])
        for a in agents:
            built = json.loads(self.ok("launch", "argv", "-w", "alpha", "--agent", a["agent"], "--prompt-kind", "coordinate",
                                       "--prompt=-x edited", *(["--effort", a["effortLevels"][-1]] if a["effortLevels"] else []),
                                       *(["--permissions", a["permissionChoices"][0]] if a["permissionChoices"] else []), "--json"))
            self.assertEqual(built["argv"][0], a["command"])
            self.assertEqual(built["argv"][-1], "-x edited")
        self.assertIn("alpha: pause", self.ok("act", "pause", "-w", "alpha", "--expect-registry", registry,
                                              "--expect-tasks", tasks))


if __name__ == "__main__":
    unittest.main()
