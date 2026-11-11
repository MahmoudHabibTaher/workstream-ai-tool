"""The JetBrains plugin in ui/jetbrains: its code names no project or agent and makes no markup
from repo text, its build targets platform 262, and the real CLI accepts every argv Cli.kt builds.

`make test-jetbrains` runs its Gradle tests, which need a JVM and the 262 platform, so they stay
local. These need neither, and they're what would notice a command the plugin calls changing shape.
"""

from __future__ import annotations

import json
import re
import unittest
from pathlib import Path

from tests.helpers import WsTestCase, task
from workstream.snapshot import LAUNCH_PROMPTS

REPO = Path(__file__).resolve().parent.parent
PACKAGE = REPO / "ui" / "jetbrains"
SRC = PACKAGE / "src"
KOTLIN = SRC / "main" / "kotlin" / "dev" / "workstream" / "jetbrains"
CLI = KOTLIN / "Cli.kt"
TEXT = KOTLIN / "Text.kt"
FORBIDDEN = re.compile(
    r"\b(develop|subsonic|the Kotlin harness|work|cargo|gradle|npm|manage_workstreams|python3"
    r"|dispatch-tasks|coordinate-workstream|claude|copilot|anthropic|openai|codex)\b"
    r"|\bworkstreams/", re.IGNORECASE)
# Swing reads `<html>` as markup and a notification's content is always HTML (plan T2): each of
# these takes text only through Text.kt's escaping helpers.
SINK = re.compile(
    r"<html>|wrapWith\(|HtmlChunk\.raw|HtmlBuilder|XmlStringUtil\.wrapInHtml|createNotification\("
    r"|Messages\.show|toolTipText\s*=|setToolTipText\(|\.comment\(|JEditorPane|HTMLEditorKit|JBCef"
    r"|text/html|getTooltipText\(\)|\.tooltip\s*=|setTooltip\(")
ESCAPED = re.compile(r"Text\.(html|escaped|tip)\(")
# The places that draw repo text: a tree, list or table cell goes through a Colored*CellRenderer's
# append, which never reads markup, and a tooltip through Text.tip.
WORKSTREAMS = KOTLIN / "WorkstreamsView.kt"
REVIEW = KOTLIN / "ReviewView.kt"
HEALTH = KOTLIN / "HealthView.kt"
STATUS = KOTLIN / "StatusWidget.kt"
LAUNCH = KOTLIN / "Launch.kt"
# createNewSession starts the agent as a Terminal tab's process (plan T7).
PROCESS = re.compile(r"GeneralCommandLine|ProcessBuilder|Runtime\.getRuntime|CapturingProcessHandler|OSProcessHandler"
                     r"|createNewSession|ProcessHandler|PtyProcess")


def sources() -> list[Path]:
    return sorted(p for p in SRC.rglob("*") if p.suffix in (".kt", ".xml"))


def lines(paths: list[Path]):
    for path in paths:
        for n, line in enumerate(path.read_text().splitlines(), 1):
            yield path, n, line


class NamesNoProjectTests(unittest.TestCase):
    def test_finds_the_sources(self) -> None:
        found = sources()
        self.assertNotIn(KOTLIN / "RegistryView.kt", found)
        for path in (CLI, TEXT, WORKSTREAMS, STATUS, KOTLIN / "logic" / "Model.kt", KOTLIN / "logic" / "Format.kt",
                     KOTLIN / "logic" / "Registry.kt", KOTLIN / "logic" / "Actions.kt", KOTLIN / "logic" / "Review.kt",
                     KOTLIN / "logic" / "Health.kt", HEALTH,
                     REVIEW, KOTLIN / "Reviews.kt", LAUNCH, KOTLIN / "LaunchDialog.kt", KOTLIN / "WsActions.kt", SRC / "main" / "resources" / "META-INF" / "plugin.xml",
                     SRC / "test" / "kotlin" / "dev" / "workstream" / "jetbrains" / "OpenTest.kt"):
            self.assertIn(path, found)

    def test_the_plugins_code_is_generic(self) -> None:
        found = [f"{p.relative_to(PACKAGE)}:{n}: {line.strip()}" for p, n, line in lines(sources())
                 if FORBIDDEN.search(line)]
        self.assertEqual(found, [])

    def test_no_unescaped_markup_sink(self) -> None:
        """Outside Text.kt, a markup sink in the plugin only ever takes Text.html, Text.escaped or
        Text.tip. The tests' own expected strings hold markup on purpose, so they aren't scanned."""
        main = [p for p in sources() if p.relative_to(SRC).parts[0] == "main"]
        found = [f"{p.relative_to(PACKAGE)}:{n}: {line.strip()}" for p, n, line in lines(main)
                 if p != TEXT and SINK.search(line) and not ESCAPED.search(line)]
        self.assertEqual(found, [])

    def test_the_workstreams_tab_draws_repo_text_as_text(self) -> None:
        """The list and the table draw through Colored*CellRenderer.append; the task pane puts a
        line in a read-only JBTextArea, which never reads markup, a link's text through Text.html,
        and a heading (the plugin's constant) through SimpleColoredComponent.append (plan T6). The
        Graph tab's tree draws through ColoredTreeCellRenderer.append, and the Overview is a pane."""
        view = WORKSTREAMS.read_text()
        self.assertIn("class WorkstreamsRenderer : ColoredListCellRenderer<WorkstreamNode>()", view)
        self.assertIn("class TaskCellRenderer : ColoredTableCellRenderer()", view)
        self.assertIn("class GraphRenderer : ColoredTreeCellRenderer()", view)
        self.assertEqual(view.count("toolTipText = Text.tip(shown(node).tip)"), 2)
        self.assertEqual(view.count("toolTipText = Text.tip(shown(node.task).tip)"), 1)
        self.assertEqual(re.findall(r"\bappend\(([^,]*),", view),
                         ["node.row.id", '"  ${details.joinToString(" · ")}"', 'value as? String ?: ""',
                          "label.id", '"  ${label.title}"', '"  ${label.detail}"', "heading",
                          'node.row.title?.let { "${node.row.id}: $it" } ?: node.row.id', '"  $line"', '"  ${it.error}"'])
        self.assertEqual(re.findall(r"\bActionLink\(([^)]*\)?)", view),
                         ["Text.html(item.label)", "Text.html(item.label)", "Text.html(label)"])
        self.assertIn("val overviewPane = TaskPane(::selectTask, ::openFile)", view)
        self.assertIn("cell(JBTextArea(item.text).apply {", view)
        self.assertIn("isEditable = false", view)
        # StatusText draws through SimpleColoredComponent too, so the list's empty text may be set.
        self.assertEqual(re.findall(r"\bJ(?:B)?Label\(|\blabel\(|(?<!emptyText)\.setText\(|\.text\s*=|JEditorPane|\bcomment\(", view), [])
        # The table's cells all go through the one renderer, never JTable's default JLabel one.
        self.assertIn("override fun getRenderer(item: TaskNode?): TableCellRenderer = CELL_RENDERER", view)
        # A view is read off the EDT; a write keeps the node's own revisions (plan T7).
        self.assertIn("executeOnPooledThread {", view)
        self.assertIn("selected()?.let { sink[WS_NODE] = it }", view)
        status = STATUS.read_text()
        self.assertIn("override fun getTooltipText(): String? = active()?.let { Text.tip(shown(it).tip) }", status)

    def test_the_review_draws_repo_text_as_text_and_diffs_only_what_show_printed(self) -> None:
        review = REVIEW.read_text()
        self.assertIn("class ReviewRenderer : ColoredTreeCellRenderer()", review)
        self.assertIn("toolTipText = Text.tip(s.tip)", review)
        self.assertEqual(re.findall(r"\bappend\(([^,]*),", review), ["s.label", '"  ${s.description}"'])
        self.assertNotRegex(review, r"\bJLabel\(|\.setText\(|\.text\s*=")
        # Both sides come from `ws review --show` (Workstreams.show), never from git or the disk.
        self.assertIn("ws.show(node.ws, node.task, path, Side.OLD), ws.show(node.ws, node.task, path, Side.NEW)", review)
        self.assertIn("factory.create(project, old.text ?: \"\", type), factory.create(project, new.text ?: \"\", type)", review)
        self.assertIn("Text.notify(project, got.text,", review)
        self.assertIn('LightVirtualFile("${node.task}.md", node.text).apply { isWritable = false }', review)
        self.assertNotRegex(review, r"\"git\"|VcsUtil|GitRepository")
        self.assertIn('addTab(toolWindow, ReviewPanel(project, review), "Review", review)', WORKSTREAMS.read_text())

    def test_health_and_budget_draw_repo_text_as_text_and_notify_through_text_kt(self) -> None:
        health = HEALTH.read_text()
        for renderer in ("class HealthRenderer : ColoredTreeCellRenderer()", "class BudgetRenderer : ColoredTreeCellRenderer()"):
            self.assertIn(renderer, health)
        self.assertEqual(health.count("toolTipText = Text.tip(s.tip)"), 2)
        self.assertEqual(re.findall(r"\bappend\(([^,]*),", health), ["s.label", '"  ${s.description}"'] * 2)
        self.assertNotRegex(health, r"\bJLabel\(|\.setText\(|\.text\s*=|Text\.notify")
        # A finding's writes are the Registry's own actions, so the same confirm and ws act.
        self.assertIn('PopupHandler.installPopupMenu(tree, POPUP_GROUP, "WorkstreamsHealthPopup")', health)
        self.assertIn("(selected() as? FindingNode)?.let { sink[WS_NODE] = it }", health)
        # The health notification's body goes through Text.notify, so it is escaped (plan T2, T12).
        service = (KOTLIN / "Workstreams.kt").read_text()
        self.assertIn("Text.notify(project, line, NotificationType.ERROR, HEALTH_NOTICE, listOf(ShowHealthAction()))", service)
        registry = WORKSTREAMS.read_text()
        self.assertIn("addTab(toolWindow, HealthPanel(project, health), HEALTH_TAB, health)", registry)
        self.assertIn("budgetPanel.setShowing(manager.isSelected(budgetTab))", registry)

    def test_text_tip_escapes_every_line(self) -> None:
        text = TEXT.read_text()
        body = text[text.index("fun tip("):text.index("fun lines(")]
        # HtmlBuilder.append(String) escapes; headings are the plugin's constants, escaped too.
        self.assertEqual(body.count("out.append("), 2)
        self.assertIn("section.heading?.let { out.append(HtmlChunk.text(it).bold()).br() }", body)
        self.assertIn("out.append(line)", body)
        self.assertIn('return out.wrapWith("html").toString()', body)
        # A dialog's message is HTML too: each line escaped, and the question through html().
        dialogs = text[text.index("fun lines("):text.index("fun notify(")]
        self.assertEqual(dialogs.count("out.append("), 1)
        self.assertIn("out.append(line)", dialogs)
        self.assertIn("Messages.showOkCancelDialog(project, lines(text.lines), text.title,", dialogs)
        self.assertIn("Messages.showInputDialog(project, html(question), title,", dialogs)

    def test_text_kt_escapes_what_it_is_given(self) -> None:
        text = TEXT.read_text()
        self.assertIn("fun escaped(text: String): String = HtmlChunk.text(text).toString()", text)
        self.assertIn('fun html(text: String): String = HtmlChunk.text(text).wrapWith("html").toString()', text)
        self.assertEqual(re.findall(r"createNotification\(([^,]*),", text), ["escaped(text)"])
        self.assertNotRegex(text, r'HtmlChunk\.raw|"<html>')

    def test_only_cli_kt_and_launch_kt_run_processes_and_logic_never_imports_the_platform(self) -> None:
        main = [p for p in sources() if "main" in p.relative_to(SRC).parts[:1]]
        runs = sorted({p.name for p, _, line in lines(main) if PROCESS.search(line)})
        self.assertEqual(runs, ["Cli.kt", "Launch.kt"])
        launch = LAUNCH.read_text()
        self.assertIn("TerminalToolWindowManager.getInstance(project).createNewSession(LocalTerminalDirectRunner.createTerminalRunner(project), state)", launch)
        self.assertIn("myShellCommand = argv", launch)
        self.assertNotRegex(launch, r"sendText|createShellWidget|createLocalShellWidget")
        for path in (KOTLIN / "logic").rglob("*.kt"):
            self.assertNotIn("com.intellij", path.read_text(), path.name)
        cli = CLI.read_text()
        self.assertIn(".withParentEnvironmentType(GeneralCommandLine.ParentEnvironmentType.CONSOLE)", cli)
        self.assertIn('.withEnvironment("GIT_OPTIONAL_LOCKS", "0")', cli)
        self.assertIn("isDispatchThread != true", cli)
        self.assertIn("const val TIMEOUT_MS = 60_000L", (KOTLIN / "logic" / "Model.kt").read_text())


class NoPromptTextTests(unittest.TestCase):
    """The snapshot owns the launch prompts (D-LAUNCHES): no Kotlin file, shipped or test, holds
    any piece of one, so a launch can only send what a row's `launches` carries."""

    def test_no_kotlin_file_holds_a_prompt_text(self) -> None:
        pieces = {piece.strip() for text in LAUNCH_PROMPTS.values() for piece in text.split("{ws}")}
        pieces = {p for p in pieces if len(p) >= 8}
        self.assertTrue(pieces)
        words = re.compile(r"\bskill\b|ws-run|ws-coordinate", re.IGNORECASE)
        kotlin = [p for p in sources() if p.suffix == ".kt"]
        found = [f"{p.relative_to(PACKAGE)}:{n}: {line.strip()}" for p, n, line in lines(kotlin)
                 if words.search(line) or any(piece in line for piece in pieces)]
        self.assertEqual(found, [])

    def test_launches_come_from_the_row(self) -> None:
        actions = (KOTLIN / "logic" / "Actions.kt").read_text()
        self.assertIn("(node as? WorkstreamNode)?.row?.launches?.firstOrNull { it.kind == kind }", actions)
        self.assertIn('fun promptOf(offer: LaunchOffer, answer: String?): String = if (offer.ask != null) offer.prompt + (answer ?: "") else offer.prompt', actions)
        terminal = (SRC / "main" / "resources" / "META-INF" / "workstreams-terminal.xml").read_text()
        self.assertIn('<launchTarget implementation="dev.workstream.jetbrains.TerminalTarget"/>', terminal)
        self.assertNotIn("org.jetbrains.plugins.terminal", (KOTLIN / "WsActions.kt").read_text())


class PackageTests(unittest.TestCase):
    def test_the_plugin_xml(self) -> None:
        xml = (SRC / "main" / "resources" / "META-INF" / "plugin.xml").read_text()
        depends = re.findall(r"<depends([^>]*)>([^<]+)</depends>", xml)
        self.assertEqual(depends, [("", "com.intellij.modules.platform"),
                                   (' optional="true" config-file="workstreams-terminal.xml"', "org.jetbrains.plugins.terminal")])
        self.assertTrue((SRC / "main" / "resources" / "META-INF" / "workstreams-terminal.xml").is_file())
        self.assertNotIn("com.intellij.modules.java", xml)
        self.assertIn('<applicationConfigurable parentId="tools"', xml)
        self.assertIn('<toolWindow id="Workstreams"', xml)
        self.assertIn('factoryClass="dev.workstream.jetbrains.WorkstreamsToolWindow"', xml)
        self.assertIn('implementation="dev.workstream.jetbrains.StatusWidgetFactory"', xml)
        self.assertIn('<extensionPoint qualifiedName="dev.workstream.jetbrains.launchTarget"', xml)
        self.assertEqual(re.findall(r'<action id="Workstreams\.(\w+)"', xml),
                         ["Run", "Coordinate", "Close", "Abandon", "Pause", "Resume", "Sync", "Unclaim",
                          "OpenPlan", "OpenProgress", "OpenDecisions", "OpenHandoff", "OpenTasks"])
        # The four groups (D-MENUS) hide when empty, and go under Tools > Workstreams.
        self.assertEqual(re.findall(r'<group id="Workstreams\.(\w+)" class="dev\.workstream\.jetbrains\.WsGroup" popup="true"', xml),
                         ["RunGroup", "WorkstreamGroup", "TaskGroup", "OpenGroup"])
        self.assertIn('<add-to-group group-id="ToolsMenu" anchor="last"/>', xml)

    def test_the_build_targets_262(self) -> None:
        build = (PACKAGE / "build.gradle.kts").read_text()
        self.assertRegex(build, r'val platformVersion = "2026\.2(\.\d+)*"')
        self.assertIn("intellijIdea(platformVersion)", build)
        self.assertIn('sinceBuild = "262"', build)
        self.assertIn("untilBuild = provider { null }", build)
        self.assertIn("languageVersion = JavaLanguageVersion.of(25)", build)
        self.assertIn("vendor = JvmVendorSpec.JETBRAINS", build)
        self.assertIn("local(file(localIdea.get()))", build)
        self.assertIn("local(file(localStudio.get()))", build)
        self.assertIn('environment("PYTHONPATH", checkout.resolve("src").path)', build)
        self.assertIn("kotlin.stdlib.default.dependency=false", (PACKAGE / "gradle.properties").read_text())

    def test_the_wrapper_is_committed_and_cached(self) -> None:
        self.assertTrue((PACKAGE / "gradle" / "wrapper" / "gradle-wrapper.jar").is_file())
        self.assertTrue((PACKAGE / "gradlew").is_file())
        props = (PACKAGE / "gradle" / "wrapper" / "gradle-wrapper.properties").read_text()
        self.assertIn("gradle-9.7.1-bin.zip", props)

    def test_build_outputs_are_ignored(self) -> None:
        ignored = (REPO / ".gitignore").read_text().splitlines()
        for path in ("ui/jetbrains/build/", "ui/jetbrains/.gradle/", "ui/jetbrains/.intellijPlatform/",
                     "ui/jetbrains/.kotlin/"):
            self.assertIn(path, ignored)

    def test_the_make_targets(self) -> None:
        make = (REPO / "Makefile").read_text()
        self.assertIn("test-jetbrains:", make)
        self.assertIn("\tcd ui/jetbrains && ./gradlew test\n", make)
        self.assertIn("\tcd ui/jetbrains && ./gradlew buildPlugin\n", make)
        self.assertIn("\tcd ui/jetbrains && ./gradlew verifyPlugin\n", make)


class TheCliAnswersThePluginTests(WsTestCase):
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

    def test_every_argv_cli_kt_builds(self) -> None:
        source = CLI.read_text()
        for line in ('listOf("root")', 'listOf("snapshot") + (if (id != null) listOf("-w", id) else listOf())',
                     'listOf("review", task, "-w", wsId) + (if (checks) listOf("--checks") else listOf()) + (if (file != null) listOf("--file", file) else listOf())',
                     'listOf("review", task, "-w", wsId, "--show", path, "--side", side.word)',
                     'listOf("review", "--queue")', 'listOf("audit", "context", "--json")',
                     'mutableListOf("act", confirm.action, "-w", wsId)', 'args.addAll(listOf("--task", confirm.task))',
                     'args.addAll(listOf("--expect-registry", revisions.registry))',
                     'args.addAll(listOf("--expect-tasks", tasks))',
                     'listOf("launch", "check", "-w", wsId, "--kind", kind, "--json") + (if (task != null) listOf("--task", task) else listOf()) + (if (agent != null) listOf("--agent", agent) else listOf())',
                     'listOf("launch", "agents", "--json")',
                     'mutableListOf("launch", "argv", "-w", wsId, "--agent", agent, "--prompt-kind", kind, "--json")',
                     'args.addAll(listOf("--task", task))', 'args.addAll(listOf("--effort", effort))',
                     'args.addAll(listOf("--permissions", permissions))', 'args.add("--prompt=$prompt")'):
            self.assertIn(line, source)
        # Ten calls, one per line above that starts an argv: none goes around this test.
        self.assertEqual(len(re.findall(r"(?<!fun )\bws\(", source)), 10)
        self.assertIn('OLD("old"), NEW("new")', (KOTLIN / "logic" / "Model.kt").read_text())
        self.assertEqual(self.ok("root").strip(), str(self.root))
        self.assertEqual(json.loads(self.ok("snapshot"))["snapshotVersion"], 1)
        snap = json.loads(self.ok("snapshot", "-w", "alpha"))
        self.assertEqual(snap["snapshotVersion"], 1)
        self.assertEqual(json.loads(self.ok("review", "T1", "-w", "alpha"))["task"], "T1")
        self.assertEqual(json.loads(self.ok("review", "T1", "-w", "alpha", "--checks"))["task"], "T1")
        self.accepted("review", "T1", "-w", "alpha", "--file", "a.txt")
        self.accepted("review", "T1", "-w", "alpha", "--checks", "--file", "a.txt")
        for side in ("old", "new"):
            self.accepted("review", "T1", "-w", "alpha", "--show", "a.txt", "--side", side)
        self.assertIsInstance(json.loads(self.ok("review", "--queue")), (dict, list))
        self.assertIsInstance(json.loads(self.ok("audit", "context", "--json")), list)
        registry, tasks = snap["revisions"]["registry"], snap["revisions"]["tasks"]["alpha"]
        self.accepted("act", "unclaim", "-w", "alpha", "--task", "T1", "--expect-registry", registry,
                      "--expect-tasks", tasks)
        self.assertIn("alpha: pause", self.ok("act", "pause", "-w", "alpha", "--expect-registry", registry,
                                              "--expect-tasks", tasks))

    def test_the_launch_argvs_cli_kt_builds(self) -> None:
        """The launch dialog's three calls (D-DIALOG): the checks, the presets and the argv, with
        every optional part, and an edited prompt given as `--prompt=` even when it starts with `-`."""
        checks = json.loads(self.ok("launch", "check", "-w", "alpha", "--kind", "run", "--json"))["checks"]
        self.assertTrue(all({"id", "ok", "blocking", "message"} <= set(c) for c in checks))
        pinned = json.loads(self.ok("launch", "check", "-w", "alpha", "--kind", "run-task", "--json", "--task", "T1",
                                    "--agent", "claude-code"))["checks"]
        self.assertIn("skills", [c["id"] for c in pinned])
        agents = json.loads(self.ok("launch", "agents", "--json"))["agents"]
        preset = next(a for a in agents if a["agent"] == "claude-code")
        self.assertTrue({"agent", "label", "effortLevels", "permissionChoices"} <= set(preset))
        effort, permissions = preset["effortLevels"][0], preset["permissionChoices"][0]
        built = json.loads(self.ok("launch", "argv", "-w", "alpha", "--agent", "claude-code", "--prompt-kind", "run-task",
                                   "--json", "--task", "T1", "--effort", effort, "--permissions", permissions,
                                   "--prompt=-edited"))
        self.assertEqual(built["argv"][-1], "-edited")
        self.assertIn(effort, built["argv"])
        own = json.loads(self.ok("launch", "argv", "-w", "alpha", "--agent", "claude-code", "--prompt-kind", "run-task",
                                 "--json", "--task", "T1"))
        self.assertEqual(own["argv"][-1], LAUNCH_PROMPTS["run-task"].format(ws="alpha", task="T1"))


if __name__ == "__main__":
    unittest.main()
