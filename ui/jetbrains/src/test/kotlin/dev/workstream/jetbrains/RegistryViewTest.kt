// The Registry tab, the status bar widget and live refresh in a headless IDE, on a sample project.
package dev.workstream.jetbrains

import com.intellij.openapi.fileEditor.FileEditorManager
import com.intellij.openapi.fileEditor.ex.FileEditorManagerEx
import com.intellij.openapi.util.Disposer
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VfsUtil
import com.intellij.openapi.vfs.VirtualFileManager
import com.intellij.openapi.vfs.newvfs.BulkFileListener
import com.intellij.openapi.vfs.newvfs.events.VFileEvent
import com.intellij.testFramework.PlatformTestUtil
import com.intellij.util.ui.tree.TreeUtil
import dev.workstream.jetbrains.logic.DocumentNode
import dev.workstream.jetbrains.logic.Node
import dev.workstream.jetbrains.logic.Watch
import java.io.File

class RegistryViewTest : SampleTestCase() {
    private lateinit var panel: RegistryPanel

    override fun setUp() {
        super.setUp()
        val disposable = Disposer.newDisposable(testRootDisposable, "registry")
        panel = RegistryPanel(project, disposable)
    }

    override fun tearDown() {
        try {
            FileEditorManagerEx.getInstanceEx(project).closeAllFiles()
        } finally {
            super.tearDown()
        }
    }

    private fun openSample(firstTitle: String = "First"): File {
        val root = sampleProject(firstTitle, closed = true)
        WsSettings.getInstance().wsCommand = branchCli
        open(root)
        return root
    }

    private fun settle() {
        PlatformTestUtil.waitForFuture(panel.model.invalidateAsync())
        PlatformTestUtil.expandAll(panel.tree)
        PlatformTestUtil.waitWhileBusy(panel.tree)
    }

    private data class Drawn(val depth: Int, val text: String, val tip: String?, val node: Node)

    /** Every visible row as the renderer draws it: its text and its tooltip. */
    private fun drawn(): List<Drawn> = (0 until panel.tree.rowCount).map { i ->
        val path = panel.tree.getPathForRow(i)
        val value = path.lastPathComponent
        val renderer = panel.tree.cellRenderer.getTreeCellRendererComponent(panel.tree, value, false, true, panel.tree.model.isLeaf(value), i, false) as RegistryRenderer
        val node = (TreeUtil.getUserObject(value) as RegistryDescriptor).node!!
        Drawn(path.pathCount - 2, renderer.getCharSequence(false).toString(), renderer.toolTipText, node)
    }

    private fun outline(): List<String> = drawn().map { "  ".repeat(it.depth) + it.text }

    fun testTheTreeShowsTheSampleAndShowDoneAddsTheClosedWorkstream() {
        openSample()
        settle()
        // The sample's documents still hold their template placeholders: the CLI counts 9 errors.
        assertEquals(listOf(
            "alpha  active · 0/2 · 9 errors",
            "  Phase 1: 1 ready",
            "  Phase 1  0/2",
            "    A-1 First  todo · ★ ready",
            "    A-2 Second  todo · waits on A-1",
            "  Documents",
            "    Plan  PLAN.md",
            "    Progress  PROGRESS.md",
            "    Decisions  DECISIONS.md",
            "    Handoff  session_handoff.md",
        ), outline())
        assertEquals(listOf<String>(), notes.map { it.content })

        Workstreams.of(project).showDone = true
        settle()
        assertEquals(listOf("alpha  active · 0/2 · 9 errors", "old  abandoned · 0/0 · 1 error"), drawn().filter { it.depth == 0 }.map { it.text })
    }

    fun testADocumentsNodeOpensThePlanInTheEditor() {
        val root = openSample()
        settle()
        val plan = drawn().map { it.node }.filterIsInstance<DocumentNode>().single { it.name == "plan" }
        assertEquals(root.resolve("workstreams").resolve("alpha").resolve("PLAN.md").path, plan.path)
        val file = panel.open(plan)
        assertNotNull(file)
        assertEquals(listOf(plan.path), FileEditorManager.getInstance(project).selectedFiles.map { it.path })
    }

    fun testATitleHoldingMarkupIsDrawnAndTooltippedAsText() {
        openSample("<html><b>x</b>")
        settle()
        val task = drawn().single { it.text.startsWith("A-1") }
        assertEquals("A-1 <html><b>x</b>  todo · ★ ready", task.text)
        assertEquals("<html>A-1: &lt;html&gt;&lt;b&gt;x&lt;/b&gt;<br/><br/>todo · ★ ready</html>", task.tip)
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

        // A change the VFS sees outside every refresh path reloads nothing.
        batches.clear()
        notes.writeText("b")
        watcherReports(root)
        assertEquals(listOf(listOf(notes.path)), batches)
        waitFor(1_000) { false }
        assertEquals(before + 1, snapshots())
    }
}
