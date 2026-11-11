// The Workstreams tab, the status bar widget and live refresh in a headless IDE, on a sample project.
package dev.workstream.jetbrains

import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.fileEditor.ex.FileEditorManagerEx
import com.intellij.openapi.util.Disposer
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VfsUtil
import com.intellij.openapi.vfs.VirtualFileManager
import com.intellij.openapi.vfs.newvfs.BulkFileListener
import com.intellij.openapi.vfs.newvfs.events.VFileEvent
import com.intellij.ui.SimpleColoredComponent
import com.intellij.ui.components.ActionLink
import com.intellij.ui.components.JBTextArea
import com.intellij.util.ui.UIUtil
import dev.workstream.jetbrains.logic.Loaded
import dev.workstream.jetbrains.logic.PaneItem
import dev.workstream.jetbrains.logic.Watch
import kotlinx.coroutines.runBlocking
import java.awt.Component
import java.awt.Container
import java.io.File

class WorkstreamsViewTest : SampleTestCase() {
    private lateinit var panel: WorkstreamsPanel

    override fun setUp() {
        super.setUp()
        panel = WorkstreamsPanel(project, Disposer.newDisposable(testRootDisposable, "workstreams"))
    }

    override fun tearDown() {
        try {
            FileEditorManagerEx.getInstanceEx(project).closeAllFiles()
        } finally {
            super.tearDown()
        }
    }

    private fun openSample(firstTitle: String = "First", rich: Boolean = false): File {
        val root = sampleProject(firstTitle, closed = true, rich = rich)
        WsSettings.getInstance().wsCommand = branchCli
        open(root)
        settle()
        return root
    }

    private fun settle() {
        assertTrue("the view never settled", waitFor(30_000) { panel.idle && panel.view != null })
    }

    /** Every list row as the renderer draws it, and its tooltip. */
    private fun listRows(): List<Pair<String, String?>> = (0 until panel.listModel.size).map { i ->
        val c = panel.list.cellRenderer.getListCellRendererComponent(panel.list, panel.listModel.getElementAt(i), i, false, false) as WorkstreamsRenderer
        c.getCharSequence(false).toString() to c.toolTipText
    }

    /** Every table row as the renderer draws its cells. */
    private fun tableRows(): List<List<String>> = (0 until panel.table.rowCount).map { r ->
        (0 until panel.table.columnCount).map { c ->
            val cell = panel.table.prepareRenderer(panel.table.getCellRenderer(r, c), r, c) as TaskCellRenderer
            cell.getCharSequence(false).toString()
        }
    }

    /** A pane as drawn, top to bottom: `#` before a heading, `>` before a link. */
    private fun paneText(pane: TaskPane = panel.pane): List<String> {
        val out = mutableListOf<String>()
        fun walk(c: Component) {
            when (c) {
                is SimpleColoredComponent -> out += "# " + c.getCharSequence(false)
                is JBTextArea -> out += c.text
                is ActionLink -> out += "> " + c.text
                is Container -> c.components.forEach(::walk)
            }
        }
        walk(pane.component)
        return out
    }

    /** The Graph tab's tree as drawn, indented by depth. */
    private fun graphText(): List<String> = (0 until panel.graphTree.rowCount).map { i ->
        val path = panel.graphTree.getPathForRow(i)
        val c = panel.graphTree.cellRenderer.getTreeCellRendererComponent(panel.graphTree, path.lastPathComponent, false, true,
                                                                          false, i, false) as GraphRenderer
        "  ".repeat(path.pathCount - 2) + c.getCharSequence(false)
    }

    private fun selectTask(id: String) {
        assertTrue(panel.selectTask(id))
        UIUtil.dispatchAllInvocationEvents()
    }

    fun testSelectingAWorkstreamAndATaskShowsTheTableAndTheTaskPane() {
        openSample(rich = true)
        assertEquals(listOf("alpha"), panel.listModel.items.map { it.row.id })
        assertEquals("alpha", panel.selectedWorkstream()?.row?.id)
        assertEquals("alpha  0/2 · active · 9 errors", listRows().single().first)
        assertEquals(listOf("Status", "ID", "Phase", "Title", "Waiting on"), (0 until panel.table.columnCount).map { panel.table.getColumnName(it) })
        assertEquals(listOf(listOf("todo", "A-1", "1", "First", ""), listOf("todo", "A-2", "1", "Second", "A-1")), tableRows())
        assertEquals(listOf<String>(), paneText())

        selectTask("A-1")
        assertEquals(listOf(
            "A-1: First", "todo · ★ ready",
            "# Summary", "The first task.",
            "# Unblocks", "> <html>A-2</html>",
            "# Files", "> <html>src/a.txt</html>",
            "# Acceptance", "It works",
            "# Notes", "A note",
        ), paneText())
        assertEquals(listOf<String>(), notes.map { it.content })

        Workstreams.of(project).showDone = true
        settle()
        assertEquals(listOf("alpha  0/2 · active · 9 errors", "old  0/0 · abandoned · 1 error"), listRows().map { it.first })
        assertEquals("the selection stays on alpha and A-1", "alpha" to "A-1", panel.selectedWorkstream()?.row?.id to panel.selectedTask()?.task?.id)

        assertTrue(panel.selectWorkstream("old"))
        settle()
        assertEquals(listOf<List<String>>(), tableRows())
        assertEquals(listOf<String>(), paneText())
    }

    fun testTheGraphAndOverviewTabsShowTheSamplesTreeAndSections() {
        val root = openSample(rich = true)
        assertEquals(listOf(TASKS_TAB, GRAPH_TAB, OVERVIEW_TAB), (0 until panel.tabs.tabCount).map { panel.tabs.getTitleAt(it) })
        assertEquals(listOf("A-1  First  todo · ★ ready", "  A-2  Second  todo · waits on A-1"), graphText())

        // Selecting a node selects its task, and selecting a task selects its node.
        panel.graphTree.selectionPath = panel.graphTree.getPathForRow(1)
        UIUtil.dispatchAllInvocationEvents()
        assertEquals("A-2", panel.selectedTask()?.task?.id)
        assertEquals("A-2: Second", paneText()[0])
        selectTask("A-1")
        assertEquals("A-1", panel.selectedGraphNode()?.task?.task?.id)

        val folder = root.resolve("workstreams").resolve("alpha")
        // The row's dates and base are the sample's own, so they are read back from the row the list drew.
        val row = panel.selectedWorkstream()!!.row
        assertEquals(listOf(
            "# Documents", "> <html>Plan</html>", "> <html>Progress</html>", "> <html>Decisions</html>", "> <html>Handoff</html>",
            "# Registry", "alpha: Alpha", "sample", "active · standard tier", "0/2 done",
            "created ${row.created} · started ${row.startedAt}", "Base ${row.baseCommit}",
            "# Open claims", "None",
            "# Baseline", "None recorded",
        ), paneText(panel.overviewPane))
        assertEquals(sh(root, "git", "rev-parse", "--short", "HEAD~1").trim(), row.baseCommit)
        val plan = panel.overviewPane.links.getValue(PaneItem.FileLink(folder.resolve("PLAN.md").path, "Plan"))
        plan.doClick()
        UIUtil.dispatchAllInvocationEvents()
        assertEquals(listOf(folder.resolve("PLAN.md").path), FileEditorManager.getInstance(project).selectedFiles.map { it.path })
    }

    fun testAJumpLinkSelectsTheTaskItNames() {
        openSample()
        selectTask("A-2")
        assertEquals(listOf("A-2: Second", "todo · waits on A-1", "# Depends on", "> <html>A-1</html>"), paneText())
        panel.pane.links.getValue(PaneItem.TaskLink("A-1")).doClick()
        UIUtil.dispatchAllInvocationEvents()
        assertEquals("A-1", panel.selectedTask()?.task?.id)
        assertEquals(listOf("A-1: First", "todo · ★ ready", "# Unblocks", "> <html>A-2</html>"), paneText())
        panel.pane.links.getValue(PaneItem.TaskLink("A-2")).doClick()
        UIUtil.dispatchAllInvocationEvents()
        assertEquals("A-2", panel.selectedTask()?.task?.id)
    }

    fun testTheSelectionIsKeptByIdAcrossAReload() {
        val root = openSample()
        selectTask("A-2")
        val before = panel.selectedTask()!!
        ws(root, "set-status", "-w", "alpha", "paused")
        sh(root, "git", "commit", "-qam", "pause alpha")
        runBlocking { Workstreams.of(project).refresh().join() }
        assertTrue(waitFor(30_000) { panel.idle && panel.selectedWorkstream()?.row?.status == "paused" })
        assertEquals("A-2", panel.selectedTask()?.task?.id)
        assertNotSame(before, panel.selectedTask())
        assertEquals("todo · waits on A-1", paneText()[1])
    }

    fun testADoubleClickedTaskOpensTheTasksFileAtItsIdAndAFileLinkOpensTheFile() {
        val root = openSample(rich = true)
        val tasksFile = (panel.view as Loaded.Value).value.tasksFile!!
        assertTrue(tasksFile, tasksFile.startsWith(root.resolve("workstreams").resolve("alpha").path + File.separator))
        selectTask("A-2")
        val file = panel.openTask(panel.selectedTask()!!)
        assertEquals(tasksFile, file?.path)
        val editor = FileEditorManager.getInstance(project).selectedTextEditor!!
        assertEquals(tasksFile, FileEditorManager.getInstance(project).selectedFiles.single().path)
        assertTrue(editor.document.text.substring(editor.caretModel.offset).replace(" ", "").startsWith("\"id\":\"A-2\""))

        selectTask("A-1")
        panel.pane.links.getValue(PaneItem.FileLink("src/a.txt")).doClick()
        UIUtil.dispatchAllInvocationEvents()
        assertEquals(root.resolve("src").resolve("a.txt").path, FileEditorManager.getInstance(project).selectedFiles.single().path)
    }

    fun testADocumentLinkOpensThePlan() {
        val root = openSample()
        val plan = root.resolve("workstreams").resolve("alpha").resolve("PLAN.md").path
        assertEquals(plan, (panel.view as Loaded.Value).value.docs["plan"])
        val file = panel.openPath(plan)
        assertNotNull(file)
        assertEquals(listOf(plan), FileEditorManager.getInstance(project).selectedFiles.map { it.path })
        assertEquals("alpha: Alpha  Phase 1: 1 ready", panel.header.getCharSequence(false).toString())
    }

    fun testATitleHoldingMarkupIsDrawnAndTooltippedAsText() {
        openSample("<html><b>x</b>")
        assertEquals(listOf("todo", "A-1", "1", "<html><b>x</b>", ""), tableRows()[0])
        val cell = panel.table.prepareRenderer(panel.table.getCellRenderer(0, 3), 0, 3) as TaskCellRenderer
        assertEquals("<html>A-1: &lt;html&gt;&lt;b&gt;x&lt;/b&gt;<br/><br/>todo · ★ ready</html>", cell.toolTipText)
        selectTask("A-1")
        assertEquals("A-1: <html><b>x</b>", paneText()[0])
        val widget = StatusWidget(project)
        try {
            assertEquals("alpha: Phase 1: 1 ready · 9 errors", widget.getText())
            assertEquals("<html>alpha: Alpha<br/><br/>sample<br/><br/>active · 0/2 · 9 errors</html>", widget.getTooltipText())
        } finally {
            Disposer.dispose(widget)
        }
    }

    private fun snapshots(): Int = calls.count { it == branchCli + "snapshot" }

    /**
     * What the native watcher does when it reports a change: mark the tree dirty and refresh it.
     * The platform turns the watcher off in unit-test mode (NativeFileWatcherImpl.isDisabled), so
     * the test stands in for it; the watch requests it would act on are checked first.
     */
    private fun watcherReports(root: File) {
        val dir = LocalFileSystem.getInstance().findFileByPath(root.path)!!
        VfsUtil.markDirtyAndRefresh(false, true, true, dir)
    }

    fun testACommitMadeOutsideTheIdeReloadsTheSnapshotOncePerBurst() {
        val root = openSample()
        val ws = Workstreams.of(project)
        val refresh = Snapshots.refresh(ws.snapshot!!)
        assertTrue(refresh.contains(Watch(root.resolve("workstreams").resolve("workstreams.json").path, false)))
        assertTrue(refresh.contains(Watch(root.resolve(".git/refs/heads").path, true)))
        assertEquals(refresh, ws.watches)
        assertEquals(refresh.map { it.path to it.recursive }.sortedBy { it.first },
                     ws.watchRequests().map { it.rootPath to it.isToWatchRecursively }.sortedBy { it.first })
        val batches = mutableListOf<List<String>>()
        project.messageBus.connect(testRootDisposable).subscribe(VirtualFileManager.VFS_CHANGES, object : BulkFileListener {
            override fun after(events: List<VFileEvent>) {
                batches += events.map { it.path }
            }
        })
        val notes = root.resolve("notes.txt").apply { writeText("a") }
        LocalFileSystem.getInstance().refreshAndFindFileByPath(notes.path)
        waitFor(1_000) { false }
        val before = snapshots()

        // One outside commit, seen by the VFS as two batches of changes 300 ms never separates.
        ws(root, "set-status", "-w", "alpha", "paused")
        sh(root, "git", "add", "-A")
        watcherReports(root)
        sh(root, "git", "commit", "-qm", "pause alpha")
        watcherReports(root)
        assertTrue("two batches: $batches", batches.size >= 2)
        assertTrue(batches.flatten().contains(root.resolve("workstreams").resolve("workstreams.json").path))
        assertTrue(batches.flatten().any { it.startsWith(root.resolve(".git/refs/heads").path + "/") })
        assertTrue("no reload within 10s of an outside commit", waitFor(10_000) { snapshots() > before })
        waitFor(1_000) { false }
        assertEquals("one burst, one snapshot", before + 1, snapshots())
        assertEquals("paused", Snapshots.rows(ws.snapshot!!).single { it.id == "alpha" }.status)
        assertTrue("the list redraws", waitFor(10_000) { panel.selectedWorkstream()?.row?.status == "paused" })

        // A change the VFS sees outside every refresh path reloads nothing.
        batches.clear()
        notes.writeText("b")
        watcherReports(root)
        assertEquals(listOf(listOf(notes.path)), batches)
        waitFor(1_000) { false }
        assertEquals(before + 1, snapshots())
    }
}
