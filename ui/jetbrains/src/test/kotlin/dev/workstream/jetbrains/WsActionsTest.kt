// The Registry's writes and launches in a headless IDE, on a sample project: a confirmed pause is
// the ws act commit, a stale one is act's refusal with HEAD unchanged, each action is enabled only
// where the node offers it, and a launch builds the Terminal argv or copies the prompt.
package dev.workstream.jetbrains

import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.actionSystem.impl.SimpleDataContext
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.ide.CopyPasteManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.ui.TestDialog
import com.intellij.openapi.ui.TestDialogManager
import com.intellij.openapi.ui.TestInputDialog
import com.intellij.openapi.util.Disposer
import com.intellij.testFramework.PlatformTestUtil
import com.intellij.testFramework.TestActionEvent
import com.intellij.util.ui.tree.TreeUtil
import dev.workstream.jetbrains.logic.AGENT_SETTING
import dev.workstream.jetbrains.logic.Acted
import dev.workstream.jetbrains.logic.Confirm
import dev.workstream.jetbrains.logic.DocumentNode
import dev.workstream.jetbrains.logic.Node
import dev.workstream.jetbrains.logic.TaskNode
import dev.workstream.jetbrains.logic.WorkstreamNode
import java.awt.datatransfer.DataFlavor
import java.io.File
import java.util.concurrent.CopyOnWriteArrayList

class WsActionsTest : SampleTestCase() {
    private lateinit var panel: RegistryPanel
    private val asked = CopyOnWriteArrayList<String>()
    private val opened = CopyOnWriteArrayList<List<String>>()
    private lateinit var savedAgent: List<String>

    private val writes = listOf("Pause", "Resume", "Sync", "Unclaim")
    private val launches = listOf("Run", "Coordinate", "Close", "Abandon")

    override fun setUp() {
        super.setUp()
        panel = RegistryPanel(project, Disposer.newDisposable(testRootDisposable, "registry"))
        savedAgent = WsSettings.getInstance().agentCommand
        TestDialogManager.setTestDialog(TestDialog { message -> asked += message; Messages.OK }, testRootDisposable)
        TerminalTarget.opener = TerminalOpener { _: Project, cwd, tab, argv -> opened += listOf(cwd, tab) + argv }
    }

    override fun tearDown() {
        try {
            TestDialogManager.setTestInputDialog(TestInputDialog.DEFAULT)
            TerminalTarget.reset()
            WsSettings.getInstance().agentCommand = savedAgent
        } finally {
            super.tearDown()
        }
    }

    private fun openSample(): File {
        val root = sampleProject(closed = true)
        WsSettings.getInstance().wsCommand = branchCli
        open(root)
        Workstreams.of(project).showDone = true
        repeat(2) {
            PlatformTestUtil.waitForFuture(panel.model.invalidateAsync())
            PlatformTestUtil.expandAll(panel.tree)
            PlatformTestUtil.waitWhileBusy(panel.tree)
        }
        return root
    }

    private fun nodes(): List<Node> = (0 until panel.tree.rowCount).mapNotNull {
        (TreeUtil.getUserObject(panel.tree.getPathForRow(it).lastPathComponent) as? RegistryDescriptor)?.node
    }

    private fun row(id: String): WorkstreamNode = nodes().filterIsInstance<WorkstreamNode>().single { it.row.id == id }

    private fun action(name: String): AnAction = ActionManager.getInstance().getAction("Workstreams.$name")!!

    private fun event(name: String, node: Node?) = TestActionEvent.createTestEvent(action(name),
        SimpleDataContext.builder().add(CommonDataKeys.PROJECT, project).apply { if (node != null) add(WS_NODE, node) }.build())

    private fun enabled(node: Node?): List<String> = (writes + launches).filter { name ->
        event(name, node).also { action(name).update(it) }.presentation.let { it.isEnabled && it.isVisible }
    }

    private fun perform(name: String, node: Node) {
        val e = event(name, node)
        action(name).update(e)
        assertTrue("$name is offered", e.presentation.isEnabled)
        action(name).actionPerformed(e)
    }

    private fun head(root: File): String = sh(root, "git", "rev-parse", "HEAD").trim()

    private fun subject(root: File): String = sh(root, "git", "log", "-1", "--format=%s").trim()

    fun testAConfirmedPauseIsTheActCommit() {
        val root = openSample()
        val before = head(root)
        perform("Pause", row("alpha"))
        assertEquals(listOf(Text.lines(listOf("This commits \"alpha: pause\" on main."))), asked.toList())
        assertTrue("no act notification", waitFor(30_000) { notes.isNotEmpty() })
        assertEquals(listOf(NotificationType.INFORMATION), notes.map { it.type })
        assertEquals("alpha: pause (ws act)", subject(root))
        assertTrue(notes.single().content.contains("alpha: pause"))
        assertEquals(before, sh(root, "git", "rev-parse", "HEAD~1").trim())
        assertTrue("the tree reloads", waitFor(10_000) { reloaded("alpha", "paused") })
    }

    private fun reloaded(id: String, status: String): Boolean =
        Workstreams.of(project).snapshot?.let { Snapshots.rows(it).single { r -> r.id == id }.status == status } ?: false

    fun testAPauseAfterAnOutsideRegistryChangeShowsTheRefusalAndLeavesHeadAlone() {
        val root = openSample()
        val drawn = row("alpha")
        // Another hand changes the registry after the tree drew alpha.
        ws(root, "new", "beta", "--title", "Beta", "--summary", "later", "--base", head(root))
        sh(root, "git", "add", "-A")
        sh(root, "git", "commit", "-qm", "beta")
        val before = head(root)
        perform("Pause", drawn)
        assertEquals(1, asked.size)
        assertTrue("no act notification", waitFor(30_000) { notes.isNotEmpty() })
        val note = notes.single()
        assertEquals(NotificationType.ERROR, note.type)
        assertEquals(before, head(root))
        assertEquals("beta", subject(root))
        // The refusal is act's own stderr as given, escaped: the same call again says the same.
        val again = ApplicationManager.getApplication().executeOnPooledThread<Acted> {
            Cli(branchCli).runAct(root.path, "alpha", Confirm("pause"), drawn.revisions!!)
        }.get()
        assertTrue(again.refused)
        assertTrue(again.line, again.line.contains("registry"))
        assertEquals(Text.escaped(again.line), note.content)
        assertEquals(before, head(root))
    }

    fun testActionsAreEnabledOnlyWhereTheRowOrFindingOffersThem() {
        openSample()
        val alpha = row("alpha")
        val old = row("old")
        val task = nodes().filterIsInstance<TaskNode>().firstOrNull { it.task.id == "A-1" }
        assertNotNull(nodes().toString(), task)
        val doc = nodes().filterIsInstance<DocumentNode>().first()
        assertEquals(listOf("pause"), alpha.writes)
        assertEquals(listOf("Pause") + launches, enabled(alpha))
        assertEquals(listOf<String>(), old.writes)
        assertEquals(listOf<String>(), old.row.launches)
        assertEquals(listOf<String>(), enabled(old))
        assertEquals(listOf<String>(), enabled(task))
        assertEquals(listOf<String>(), enabled(doc))
        assertEquals(listOf<String>(), enabled(null))
        // A write the node doesn't offer never reaches act, even when called directly.
        action("Resume").actionPerformed(event("Resume", alpha))
        assertEquals(listOf<String>(), asked.toList())
        assertEquals(listOf(Text.escaped("resume isn't offered here.")), notes.map { it.content })
    }

    fun testRunAndAbandonBuildTheTerminalArgvAndNoAgentCommandCopiesThePrompt() {
        val root = openSample()
        val alpha = row("alpha")
        val prompts = alpha.row.launches.associate { it.kind to it.prompt }
        WsSettings.getInstance().agentCommand = listOf("agent", "--flag")
        perform("Run", alpha)
        assertEquals(listOf(listOf(root.path, "Workstreams: Run alpha", "agent", "--flag", prompts.getValue("run"))), opened.toList())

        val questions = CopyOnWriteArrayList<String>()
        TestDialogManager.setTestInputDialog(TestInputDialog { q -> questions += q; "  no longer needed " })
        perform("Abandon", alpha)
        assertEquals(1, questions.size)
        assertEquals(listOf(root.path, "Workstreams: Abandon alpha", "agent", "--flag", prompts.getValue("abandon") + "no longer needed"),
                     opened.last())
        assertEquals("reason", alpha.row.launches.single { it.kind == "abandon" }.ask)

        WsSettings.getInstance().agentCommand = listOf()
        notes.clear()
        perform("Run", alpha)
        assertEquals(2, opened.size)
        assertEquals(prompts.getValue("run"), CopyPasteManager.getInstance().getContents<String>(DataFlavor.stringFlavor))
        assertTrue(notes.single().content, notes.single().content.contains(AGENT_SETTING))
        assertTrue(notes.single().content.contains("no agent command is set"))
    }
}
