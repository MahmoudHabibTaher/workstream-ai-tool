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
    r"|text/html")
ESCAPED = re.compile(r"Text\.(html|escaped)\(")
PROCESS = re.compile(r"GeneralCommandLine|ProcessBuilder|Runtime\.getRuntime|CapturingProcessHandler|OSProcessHandler")


def sources() -> list[Path]:
    return sorted(p for p in SRC.rglob("*") if p.suffix in (".kt", ".xml"))


def lines(paths: list[Path]):
    for path in paths:
        for n, line in enumerate(path.read_text().splitlines(), 1):
            yield path, n, line


class NamesNoProjectTests(unittest.TestCase):
    def test_finds_the_sources(self) -> None:
        found = sources()
        for path in (CLI, TEXT, KOTLIN / "logic" / "Model.kt", SRC / "main" / "resources" / "META-INF" / "plugin.xml",
                     SRC / "test" / "kotlin" / "dev" / "workstream" / "jetbrains" / "OpenTest.kt"):
            self.assertIn(path, found)

    def test_the_plugins_code_is_generic(self) -> None:
        found = [f"{p.relative_to(PACKAGE)}:{n}: {line.strip()}" for p, n, line in lines(sources())
                 if FORBIDDEN.search(line)]
        self.assertEqual(found, [])

    def test_no_unescaped_markup_sink(self) -> None:
        """Outside Text.kt, a markup sink only ever takes Text.html or Text.escaped."""
        found = [f"{p.relative_to(PACKAGE)}:{n}: {line.strip()}" for p, n, line in lines(sources())
                 if p != TEXT and SINK.search(line) and not ESCAPED.search(line)]
        self.assertEqual(found, [])

    def test_text_kt_escapes_what_it_is_given(self) -> None:
        text = TEXT.read_text()
        self.assertIn("fun escaped(text: String): String = HtmlChunk.text(text).toString()", text)
        self.assertIn('fun html(text: String): String = HtmlChunk.text(text).wrapWith("html").toString()', text)
        self.assertEqual(re.findall(r"createNotification\(([^,]*),", text), ["escaped(text)"])
        self.assertNotRegex(text, r'HtmlChunk\.raw|"<html>')

    def test_only_cli_kt_runs_processes_and_logic_never_imports_the_platform(self) -> None:
        main = [p for p in sources() if "main" in p.relative_to(SRC).parts[:1]]
        runs = sorted({p.name for p, _, line in lines(main) if PROCESS.search(line)})
        self.assertEqual(runs, ["Cli.kt"])
        for path in (KOTLIN / "logic").rglob("*.kt"):
            self.assertNotIn("com.intellij", path.read_text(), path.name)
        cli = CLI.read_text()
        self.assertIn(".withParentEnvironmentType(GeneralCommandLine.ParentEnvironmentType.CONSOLE)", cli)
        self.assertIn('.withEnvironment("GIT_OPTIONAL_LOCKS", "0")', cli)
        self.assertIn("isDispatchThread != true", cli)
        self.assertIn("const val TIMEOUT_MS = 60_000L", (KOTLIN / "logic" / "Model.kt").read_text())


class PackageTests(unittest.TestCase):
    def test_the_plugin_xml(self) -> None:
        xml = (SRC / "main" / "resources" / "META-INF" / "plugin.xml").read_text()
        depends = re.findall(r"<depends([^>]*)>([^<]+)</depends>", xml)
        self.assertEqual(depends, [("", "com.intellij.modules.platform"),
                                   (' optional="true" config-file="workstreams-terminal.xml"', "org.jetbrains.plugins.terminal")])
        self.assertTrue((SRC / "main" / "resources" / "META-INF" / "workstreams-terminal.xml").is_file())
        self.assertNotIn("com.intellij.modules.java", xml)
        self.assertIn('<applicationConfigurable parentId="tools"', xml)

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
                     'args.addAll(listOf("--expect-tasks", tasks))'):
            self.assertIn(line, source)
        # Seven calls, one per line above that starts an argv: none goes around this test.
        self.assertEqual(len(re.findall(r"(?<!fun )\bws\(", source)), 7)
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


if __name__ == "__main__":
    unittest.main()
