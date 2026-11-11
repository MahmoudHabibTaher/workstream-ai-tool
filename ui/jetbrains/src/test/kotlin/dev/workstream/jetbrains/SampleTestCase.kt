// A headless IDE with a sample project the branch's own CLI builds. The CLI argv comes from the
// build's test task (WS_TEST_COMMAND) and goes in the wsCommand setting, so these tests never run
// the ws on PATH.
package dev.workstream.jetbrains

import com.google.gson.JsonParser
import com.intellij.notification.Notification
import com.intellij.notification.Notifications
import com.intellij.openapi.vfs.newvfs.impl.VfsRootAccess
import com.intellij.testFramework.PlatformTestUtil
import com.intellij.testFramework.fixtures.BasePlatformTestCase
import dev.workstream.jetbrains.logic.Run
import kotlinx.coroutines.runBlocking
import java.io.File
import java.nio.file.Files
import java.nio.file.Path
import java.util.concurrent.CopyOnWriteArrayList
import java.util.concurrent.TimeUnit

abstract class SampleTestCase : BasePlatformTestCase() {
    protected val branchCli: List<String> by lazy {
        val raw = System.getenv("WS_TEST_COMMAND") ?: error("WS_TEST_COMMAND is unset; run these through ./gradlew test")
        JsonParser.parseString(raw).asJsonArray.map { it.asString }
    }
    protected lateinit var tmp: Path
    private lateinit var saved: List<String>
    protected val notes = CopyOnWriteArrayList<Notification>()
    protected val healthNotes = CopyOnWriteArrayList<Notification>()
    protected val calls = CopyOnWriteArrayList<List<String>>()

    override fun setUp() {
        super.setUp()
        tmp = Files.createTempDirectory("ws-open").toRealPath()
        VfsRootAccess.allowRootAccess(testRootDisposable, tmp.toString())
        saved = WsSettings.getInstance().wsCommand
        project.messageBus.connect(testRootDisposable).subscribe(Notifications.TOPIC, object : Notifications {
            override fun notify(notification: Notification) {
                // The sample's template placeholders are error findings, so opening it raises the
                // health notification (plan T12): those are kept apart from what the others say.
                if (notification.displayId == Workstreams.HEALTH_NOTICE) healthNotes += notification else notes += notification
            }
        })
        Workstreams.of(project).forget()
        Workstreams.of(project).run = Run { argv, cwd -> calls += argv; ProcessRun.run(argv, cwd) }
    }

    override fun tearDown() {
        try {
            WsSettings.getInstance().wsCommand = saved
            Workstreams.of(project).run = ProcessRun
            Workstreams.of(project).forget()
            tmp.toFile().deleteRecursively()
        } finally {
            super.tearDown()
        }
    }

    protected fun sh(cwd: File, vararg argv: String): String {
        val proc = ProcessBuilder(*argv).directory(cwd).redirectErrorStream(true).start()
        val out = proc.inputStream.bufferedReader().readText()
        assertTrue("timed out: ${argv.toList()}", proc.waitFor(60, TimeUnit.SECONDS))
        assertEquals("${argv.toList()}: $out", 0, proc.exitValue())
        return out
    }

    protected fun ws(cwd: File, vararg args: String): String = sh(cwd, *(branchCli + args).toTypedArray())

    /**
     * `ws init`, then `alpha`, active with two tasks, all committed; `closed` adds an abandoned `old`,
     * `rich` gives A-1 a summary, a file, acceptance and notes, and `filled` fills alpha's template
     * placeholders, so no check blocks a launch.
     */
    protected fun sampleProject(firstTitle: String = "First", closed: Boolean = false, rich: Boolean = false, filled: Boolean = false): File {
        val root = tmp.resolve("project").toFile().apply { mkdirs() }
        sh(root, "git", "init", "-q", "-b", "main")
        ws(root, "init", "--integration", "main")
        sh(root, "git", "add", "-A")
        sh(root, "git", "commit", "-qm", "init")
        val base = sh(root, "git", "rev-parse", "--short", "HEAD").trim()
        ws(root, "new", "alpha", "--title", "Alpha", "--summary", "sample", "--base", base)
        val seed = tmp.resolve("seed.json").toFile()
        val title = com.google.gson.JsonPrimitive(firstTitle).toString()
        val more = if (!rich) "" else {
            root.resolve("src").mkdirs()
            root.resolve("src").resolve("a.txt").writeText("a\n")
            """, "summary": "The first task.", "files": ["src/a.txt"], "acceptance": ["It works"], "notes": "A note""""
        }
        seed.writeText("""[{"id": "A-1", "phase": 1, "priority": 10, "title": $title$more},
            {"id": "A-2", "phase": 1, "priority": 20, "title": "Second", "blockedBy": ["A-1"]}]""")
        ws(root, "seed", "-w", "alpha", seed.path)
        ws(root, "set-status", "-w", "alpha", "active")
        if (filled) {
            // The template's placeholders are integrity errors, which block every launch.
            root.resolve("workstreams").resolve("alpha").listFiles { f -> f.name.endsWith(".md") }!!.forEach { f ->
                f.writeText(f.readText().replace(Regex("\\{\\{[^}]*\\}\\}"), "filled"))
            }
        }
        if (closed) {
            ws(root, "new", "old", "--title", "Old", "--summary", "dropped", "--base", base)
            ws(root, "set-status", "-w", "old", "abandoned", "--notes", "dropped")
        }
        sh(root, "git", "add", "-A")
        sh(root, "git", "commit", "-qm", "alpha")
        return root
    }

    protected fun open(folder: File) {
        runBlocking { Workstreams.of(project).open(folder.path).join() }
        PlatformTestUtil.dispatchAllEventsInIdeEventQueue()
    }

    /** Pumps the EDT until `done` holds or `ms` pass; returns whether it held. */
    protected fun waitFor(ms: Long, done: () -> Boolean): Boolean {
        val end = System.currentTimeMillis() + ms
        while (System.currentTimeMillis() < end) {
            PlatformTestUtil.dispatchAllEventsInIdeEventQueue()
            if (done()) return true
            Thread.sleep(20)
        }
        PlatformTestUtil.dispatchAllEventsInIdeEventQueue()
        return done()
    }
}
