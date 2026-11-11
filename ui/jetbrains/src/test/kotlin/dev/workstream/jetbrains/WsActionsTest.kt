// The Registry's writes and launches in a headless IDE, on a sample project: a confirmed pause is
// the ws act commit, a stale one is act's refusal with HEAD unchanged, each action is enabled only
// where the node offers it, and a launch builds the Terminal argv or copies the prompt.
package dev.workstream.jetbrains

import com.intellij.notification.NotificationType
import com.google.gson.GsonBuilder
import com.google.gson.JsonParser
import com.intellij.openapi.actionSystem.ActionGroup
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.Separator
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
import com.intellij.testFramework.TestActionEvent
import dev.workstream.jetbrains.logic.AGENT_SETTING
import dev.workstream.jetbrains.logic.Acted
import dev.workstream.jetbrains.logic.Confirm
import dev.workstream.jetbrains.logic.Node
import dev.workstream.jetbrains.logic.TaskNode
import dev.workstream.jetbrains.logic.WorkstreamNode
import dev.workstream.jetbrains.logic.WsView
import kotlinx.coroutines.runBlocking
import java.awt.datatransfer.DataFlavor
import java.io.File
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.concurrent.CopyOnWriteArrayList

class WsActionsTest : SampleTestCase() {
    private lateinit var panel: WorkstreamsPanel
    private val asked = CopyOnWriteArrayList<String>()
    private val opened = CopyOnWriteArrayList<List<String>>()
    private lateinit var savedAgent: List<String>

    private val writes = listOf("Pause", "Resume", "Sync", "Unclaim")
    private val launches = listOf("Run", "Coordinate", "Close", "Abandon")
    private val opens = listOf("OpenPlan", "OpenProgress", "OpenDecisions", "OpenHandoff", "OpenTasks")

    /** Each toolbar group's actions, in menu order (D-MENUS). */
    private val groups = mapOf(
        "Workstreams.RunGroup" to launches,
        "Workstreams.WorkstreamGroup" to listOf("Pause", "Resume", "Sync"),
        "Workstreams.TaskGroup" to listOf("Unclaim"),
        "Workstreams.OpenGroup" to opens,
    )

    override fun setUp() {
        super.setUp()
        panel = WorkstreamsPanel(project, Disposer.newDisposable(testRootDisposable, "workstreams"))
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
        assertTrue(waitFor(30_000) { panel.idle && panel.view != null && panel.listModel.size == 2 })
        return root
    }

    /** The list's rows, then the selected workstream's table rows: what the writes act on. */
    private fun nodes(): List<Node> = panel.listModel.items + panel.tableModel.items

    private fun row(id: String): WorkstreamNode = panel.listModel.items.single { it.row.id == id }

    private fun action(name: String): AnAction = ActionManager.getInstance().getAction("Workstreams.$name")!!

    private fun context(node: Node?, view: WsView? = null) = SimpleDataContext.builder().add(CommonDataKeys.PROJECT, project)
        .apply { if (node != null) add(WS_NODE, node) }.apply { if (view != null) add(WS_VIEW, view) }.build()

    private fun event(name: String, node: Node?, view: WsView? = null) = TestActionEvent.createTestEvent(action(name), context(node, view))

    private fun enabled(node: Node?, view: WsView? = null): List<String> = (writes + launches + opens).filter { name ->
        event(name, node, view).also { action(name).update(it) }.presentation.let { it.isEnabled && it.isVisible }
    }

    /** What the panel hands the actions now: its selected node and the view it drew. */
    private fun enabledInPanel(): List<String> = enabled(panel.selected() as Node?, panel.shownView())

    /** The ids of a group's children, as registered. */
    private fun children(id: String): List<String> = (ActionManager.getInstance().getAction(id) as ActionGroup)
        .getChildren(null).filter { it !is Separator }.map { ActionManager.getInstance().getId(it)!! }

    /** Whether the group shows for this data: it hides when none of its actions is offered. */
    private fun groupShown(id: String, node: Node?, view: WsView? = null): Boolean {
        val group = ActionManager.getInstance().getAction(id) as ActionGroup
        assertTrue(group.templatePresentation.isHideGroupIfEmpty)
        return group.getChildren(null).any { child ->
            TestActionEvent.createTestEvent(child, context(node, view)).also { child.update(it) }.presentation.let { it.isEnabled && it.isVisible }
        }
    }

    private fun queueOf(root: File): File = root.resolve("workstreams").resolve("alpha").resolve("tasks_list.json")

    /** Claims A-1 for agent-1 two days ago, as a stale claim, and commits it. */
    private fun staleClaim(root: File) {
        ws(root, "claim", "A-1", "-w", "alpha", "--by", "agent-1")
        sh(root, "git", "commit", "-qam", "claim A-1")
        val file = queueOf(root)
        val data = JsonParser.parseString(file.readText()).asJsonObject
        data.getAsJsonArray("tasks").map { it.asJsonObject }.single { it.get("id").asString == "A-1" }
            .addProperty("startedAt", Instant.now().minus(48, ChronoUnit.HOURS).truncatedTo(ChronoUnit.SECONDS).toString())
        file.writeText(GsonBuilder().setPrettyPrinting().create().toJson(data) + "\n")
        sh(root, "git", "commit", "-qam", "an old claim")
    }

    private fun perform(name: String, node: Node, view: WsView? = null) {
        val e = event(name, node, view)
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

    /**
     * The panel hands the actions the selected list row, or the task when the table was used last,
     * each pinned to the snapshot it was drawn from: a reload draws new nodes, and a node held from
     * before keeps its revisions, so its write is refused rather than re-pinned (plan T7).
     */
    fun testTheSelectedRowOrTaskIsWhatActsPinnedToTheSnapshotItWasDrawnFrom() {
        val root = openSample()
        val ws = Workstreams.of(project)
        val drawn = panel.selected() as WorkstreamNode
        assertEquals("alpha", drawn.row.id)
        assertEquals(Snapshots.revisions(ws.snapshot!!), drawn.revisions)
        assertTrue(panel.selectTask("A-1"))
        val task = panel.selected() as TaskNode
        assertEquals("A-1", task.task.id)
        assertEquals((panel.view as dev.workstream.jetbrains.logic.Loaded.Value).value.revisions, task.revisions)

        ws(root, "new", "beta", "--title", "Beta", "--summary", "later", "--base", head(root))
        sh(root, "git", "add", "-A")
        sh(root, "git", "commit", "-qm", "beta")
        runBlocking { ws.refresh().join() }
        assertTrue(waitFor(30_000) { panel.idle && panel.listModel.size == 3 })
        val redrawn = row("alpha")
        assertNotSame(drawn, redrawn)
        assertFalse(drawn.revisions == redrawn.revisions)
        assertEquals(Snapshots.revisions(ws.snapshot!!), redrawn.revisions)

        val before = head(root)
        perform("Pause", drawn)
        assertTrue(asked.single(), asked.single().contains(Text.escaped("This has changed since the tree drew it")))
        assertTrue("no act notification", waitFor(30_000) { notes.isNotEmpty() })
        assertEquals(NotificationType.ERROR, notes.single().type)
        assertEquals(before, head(root))
    }

    fun testActionsAreEnabledOnlyWhereTheRowOrFindingOffersThem() {
        openSample()
        val alpha = row("alpha")
        val old = row("old")
        val task = nodes().filterIsInstance<TaskNode>().firstOrNull { it.task.id == "A-1" }
        assertNotNull(nodes().toString(), task)
        assertEquals(listOf("pause"), alpha.writes)
        assertEquals(listOf("Pause") + launches, enabled(alpha))
        assertEquals(listOf<String>(), old.writes)
        assertEquals(listOf<String>(), old.row.launches)
        assertEquals(listOf<String>(), enabled(old))
        assertEquals(listOf<String>(), enabled(task))
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

    fun testTheFourGroupsHoldTheirActionsAndAreOnTheToolbarToolsMenuAndPopups() {
        for ((id, names) in groups) assertEquals(id, names.map { "Workstreams.$it" }, children(id))
        assertEquals(TOOLBAR_GROUPS, groups.keys.toList())
        assertEquals(TOOLBAR_GROUPS, children("Workstreams.Menu"))
        assertEquals(TOOLBAR_GROUPS, children(POPUP_GROUP))
        val tools = ActionManager.getInstance().getAction("ToolsMenu") as ActionGroup
        assertTrue(tools.getChildren(null).any { ActionManager.getInstance().getId(it) == "Workstreams.Menu" })
    }

    /**
     * Each group's actions are enabled only where the snapshot offers them: the row's `actions`
     * and `launches`, a finding's offer on a task, and the documents the workstream's own snapshot
     * names. A group with none of them hides.
     */
    fun testEachGroupIsOfferedOnlyWhereTheSnapshotOffersItsActions() {
        openSample()
        val alpha = row("alpha")
        val view = panel.shownView()
        assertNotNull(view)
        assertEquals(alpha, panel.selected())
        val docs = opens.filter { docPath(view, mapOf("OpenPlan" to "plan", "OpenProgress" to "progress", "OpenDecisions" to "decisions",
                                                     "OpenHandoff" to "handoff", "OpenTasks" to TASKS_DOC).getValue(it)) != null }
        assertTrue(docs.toString(), docs.containsAll(listOf("OpenPlan", "OpenTasks")))
        assertEquals(listOf("Pause") + launches + docs, enabledInPanel())
        assertEquals(mapOf("Workstreams.RunGroup" to true, "Workstreams.WorkstreamGroup" to true, "Workstreams.TaskGroup" to false,
                           "Workstreams.OpenGroup" to true), TOOLBAR_GROUPS.associateWith { groupShown(it, alpha, view) })
        // The closed row offers no write and no launch; with no view drawn, nothing to open either.
        assertEquals(listOf<String>(), enabled(row("old")))
        assertEquals(listOf(false, false, false, false), TOOLBAR_GROUPS.map { groupShown(it, row("old")) })
        // A task with no stale claim offers no write; its workstream's files still open.
        assertTrue(panel.selectTask("A-1"))
        assertEquals(docs, enabledInPanel())
        // The tasks file opens at the selected task's id.
        perform("OpenTasks", panel.selected() as Node, view)
        val opened = com.intellij.openapi.fileEditor.FileEditorManager.getInstance(project).selectedTextEditor
        assertEquals(view!!.tasksFile, opened?.virtualFile?.path)
        assertTrue(opened!!.document.text.substring(opened.caretModel.offset).startsWith("\"id\": \"A-1\""))
        com.intellij.openapi.fileEditor.ex.FileEditorManagerEx.getInstanceEx(project).closeAllFiles()
    }

    /**
     * A stale claim's task offers the Task group's Unclaim from the table, and the status bar names
     * it with its age. An Unclaim on the task as drawn before an outside change is refused, as the
     * drawn revisions say; one on the redrawn task lands (plan T7).
     */
    fun testAStaleClaimOffersUnclaimOnTheTaskNamesItInTheStatusBarAndUnclaimKeepsTheDrawnRevisions() {
        val root = sampleProject(closed = true)
        staleClaim(root)
        WsSettings.getInstance().wsCommand = branchCli
        open(root)
        Workstreams.of(project).showDone = true
        assertTrue(waitFor(30_000) { panel.idle && panel.view != null && panel.listModel.size == 2 })

        val widget = StatusWidget(project)
        try {
            val errors = row("alpha").errors
            assertEquals("● alpha · A-1 · 2d" + (if (errors > 0) " · $errors errors" else ""), widget.getText())
        } finally {
            Disposer.dispose(widget)
        }

        assertTrue(panel.selectTask("A-1"))
        val drawn = panel.selected() as TaskNode
        assertEquals(listOf("unclaim"), drawn.writes)
        assertTrue(enabledInPanel().contains("Unclaim"))
        assertEquals(listOf("Unclaim"), enabled(drawn))
        assertTrue(groupShown("Workstreams.TaskGroup", drawn))
        assertFalse(groupShown("Workstreams.WorkstreamGroup", drawn))
        assertFalse(groupShown("Workstreams.RunGroup", drawn))
        // The workstream row offers no Unclaim: it is the task's.
        assertFalse(enabled(row("alpha")).contains("Unclaim"))

        ws(root, "new", "beta", "--title", "Beta", "--summary", "later", "--base", head(root))
        sh(root, "git", "add", "-A")
        sh(root, "git", "commit", "-qm", "beta")
        runBlocking { Workstreams.of(project).refresh().join() }
        assertTrue(waitFor(30_000) { panel.idle && panel.listModel.size == 3 && panel.view != null })
        val before = head(root)
        perform("Unclaim", drawn)
        assertTrue(asked.single(), asked.single().contains(Text.escaped("This has changed since the tree drew it")))
        assertTrue("no act notification", waitFor(30_000) { notes.isNotEmpty() })
        assertEquals(NotificationType.ERROR, notes.single().type)
        assertEquals(before, head(root))

        assertTrue(waitFor(30_000) { panel.idle && panel.selectTask("A-1") && (panel.selected() as? TaskNode)?.let { it.revisions != drawn.revisions } == true })
        val redrawn = panel.selected() as TaskNode
        assertEquals(Snapshots.revisions(Workstreams.of(project).snapshot!!)?.registry, redrawn.revisions?.registry)
        notes.clear()
        perform("Unclaim", redrawn)
        assertTrue("no act notification", waitFor(30_000) { notes.isNotEmpty() })
        assertEquals(NotificationType.INFORMATION, notes.single().type)
        assertEquals("alpha: unclaim A-1 (ws act)", subject(root))
        assertEquals(before, sh(root, "git", "rev-parse", "HEAD~1").trim())
    }
}
