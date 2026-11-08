// The Health and Budget tabs and the health notification in a headless IDE, on a sample project:
// a stale claim is listed with Unclaim and its Unclaim is the ws act commit, a new error finding
// notifies once, escaped, and Budget runs `ws audit context --json` only on selection and Refresh.
package dev.workstream.jetbrains

import com.google.gson.JsonArray
import com.google.gson.JsonObject
import com.google.gson.JsonParser
import com.google.gson.GsonBuilder
import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.CommonDataKeys
import com.intellij.openapi.actionSystem.impl.SimpleDataContext
import com.intellij.openapi.ui.Messages
import com.intellij.openapi.ui.TestDialog
import com.intellij.openapi.ui.TestDialogManager
import com.intellij.openapi.util.Disposer
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VfsUtil
import com.intellij.testFramework.PlatformTestUtil
import com.intellij.testFramework.TestActionEvent
import com.intellij.toolWindow.ToolWindowHeadlessManagerImpl
import com.intellij.util.ui.tree.TreeUtil
import dev.workstream.jetbrains.logic.FindingNode
import dev.workstream.jetbrains.logic.HealthNode
import dev.workstream.jetbrains.logic.LevelNode
import dev.workstream.jetbrains.logic.RowNode
import kotlinx.coroutines.runBlocking
import java.io.File
import java.time.Instant
import java.time.temporal.ChronoUnit
import java.util.concurrent.CopyOnWriteArrayList

class HealthViewTest : SampleTestCase() {
    private val asked = CopyOnWriteArrayList<String>()

    override fun setUp() {
        super.setUp()
        TestDialogManager.setTestDialog(TestDialog { message -> asked += message; Messages.OK }, testRootDisposable)
    }

    private fun queueOf(root: File): File = root.resolve("workstreams").resolve("alpha").resolve("tasks_list.json")

    /** Rewrites one task in alpha's queue, then commits it, as another hand would. */
    private fun editTask(root: File, id: String, message: String, edit: (JsonObject) -> Unit) {
        val file = queueOf(root)
        val data = JsonParser.parseString(file.readText()).asJsonObject
        edit(data.getAsJsonArray("tasks").map { it.asJsonObject }.single { it.get("id").asString == id })
        file.writeText(GsonBuilder().setPrettyPrinting().create().toJson(data) + "\n")
        sh(root, "git", "commit", "-qam", message)
    }

    private fun statusOf(root: File, id: String): String = JsonParser.parseString(queueOf(root).readText()).asJsonObject
        .getAsJsonArray("tasks").map { it.asJsonObject }.single { it.get("id").asString == id }.get("status").asString

    private fun head(root: File): String = sh(root, "git", "rev-parse", "HEAD").trim()

    private fun settle(panel: HealthPanel) {
        PlatformTestUtil.waitForFuture(panel.model.invalidateAsync())
        PlatformTestUtil.expandAll(panel.tree)
        PlatformTestUtil.waitWhileBusy(panel.tree)
    }

    private data class Drawn(val depth: Int, val text: String, val node: HealthNode)

    private fun drawn(panel: HealthPanel): List<Drawn> = (0 until panel.tree.rowCount).map { i ->
        val path = panel.tree.getPathForRow(i)
        val value = path.lastPathComponent
        val renderer = panel.tree.cellRenderer.getTreeCellRendererComponent(panel.tree, value, false, true, panel.tree.model.isLeaf(value), i, false) as HealthRenderer
        Drawn(path.pathCount - 2, renderer.getCharSequence(false).toString(), (TreeUtil.getUserObject(value) as HealthDescriptor).node!!)
    }

    private fun action(name: String): AnAction = ActionManager.getInstance().getAction("Workstreams.$name")!!

    private fun event(name: String, node: Any) = TestActionEvent.createTestEvent(action(name),
        SimpleDataContext.builder().add(CommonDataKeys.PROJECT, project).add(WS_NODE, node).build())

    private fun enabled(node: Any): List<String> = listOf("Pause", "Resume", "Sync", "Unclaim", "Run", "Coordinate", "Close", "Abandon").filter { name ->
        event(name, node).also { action(name).update(it) }.presentation.let { it.isEnabled && it.isVisible }
    }

    fun testAStaleClaimIsListedWithUnclaimAndItsUnclaimGoesThroughTheConfirmAndLands() {
        val root = sampleProject()
        ws(root, "claim", "A-1", "-w", "alpha")
        sh(root, "git", "commit", "-qam", "claim A-1")
        editTask(root, "A-1", "an old claim") { it.addProperty("startedAt", Instant.now().minus(48, ChronoUnit.HOURS).truncatedTo(ChronoUnit.SECONDS).toString()) }
        WsSettings.getInstance().wsCommand = branchCli
        open(root)
        val panel = HealthPanel(project, Disposer.newDisposable(testRootDisposable, "health"))
        settle(panel)

        val rows = drawn(panel)
        assertEquals(listOf("Errors  9", "Warnings  1"), rows.filter { it.depth == 0 }.map { it.text })
        val stale = rows.single { (it.node as? FindingNode)?.finding?.kind == "stale-claim" }
        assertEquals(1, stale.depth)
        assertEquals("A-1 in progress for 48h (claimed by -)  stale-claim · alpha A-1", stale.text)
        val finding = stale.node as FindingNode
        assertEquals(listOf("unclaim"), finding.writes)
        assertEquals(listOf("Unclaim"), enabled(finding))
        // The popup's data is the selected finding, as the Registry's is its selected node.
        panel.tree.selectionPath = panel.tree.getPathForRow(rows.indexOf(stale))
        assertEquals(finding, panel.selected())
        assertEquals(listOf<String>(), enabled((rows.first { it.node is LevelNode }).node))

        val before = head(root)
        val e = event("Unclaim", finding)
        action("Unclaim").update(e)
        action("Unclaim").actionPerformed(e)
        assertEquals(listOf(Text.lines(listOf("This commits \"alpha: unclaim A-1\" on main."))), asked.toList())
        assertTrue("no act notification", waitFor(30_000) { notes.isNotEmpty() })
        assertEquals(listOf(NotificationType.INFORMATION), notes.map { it.type })
        assertTrue(notes.single().content, notes.single().content.contains("alpha: unclaim A-1"))
        assertEquals("alpha: unclaim A-1 (ws act)", sh(root, "git", "log", "-1", "--format=%s").trim())
        assertEquals(before, sh(root, "git", "rev-parse", "HEAD~1").trim())
        assertEquals("", sh(root, "git", "status", "--porcelain").trim())
        assertEquals("todo", statusOf(root, "A-1"))
        assertTrue("the finding goes once the snapshot reloads", waitFor(10_000) {
            settle(panel)
            drawn(panel).none { (it.node as? FindingNode)?.finding?.kind == "stale-claim" }
        })
        println("health after the unclaim: ${drawn(panel).map { "  ".repeat(it.depth) + it.text }}")
    }

    fun testANewErrorFindingNotifiesOnceAndAReloadWithTheSameFindingDoesNot() {
        val root = sampleProject()
        WsSettings.getInstance().wsCommand = branchCli
        open(root)
        val ws = Workstreams.of(project)
        // The sample's nine placeholder errors are new to the session: one notification says so.
        assertEquals(listOf(Text.escaped("9 new workstream errors. The first: alpha: PLAN.md still has the {{CONTEXT}} placeholder")),
                     healthNotes.map { it.content })
        assertEquals(NotificationType.ERROR, healthNotes.single().type)
        assertEquals(listOf("Show Health"), healthNotes.single().actions.map { it.templatePresentation.text })
        assertTrue(healthNotes.single().actions.single() is ShowHealthAction)

        // A new error whose message holds markup: one more notification, its body escaped.
        editTask(root, "A-2", "a bad mode") { it.addProperty("mode", "<b>bold</b>") }
        runBlocking { ws.refresh().join() }
        assertTrue("no notification for the new error", waitFor(10_000) { healthNotes.size == 2 })
        val note = healthNotes.last()
        val message = "alpha: A-2: mode '<b>bold</b>' not in ['background', 'foreground']"
        assertTrue(Snapshots.health(ws.snapshot!!).any { it.level == "error" && it.message == message })
        assertEquals(Text.escaped("Workstreams error: $message"), note.content)
        assertTrue(note.content, note.content.contains("&lt;b&gt;bold&lt;/b&gt;"))
        assertFalse(note.content.contains("<b>"))
        assertEquals(NotificationType.ERROR, note.type)

        // Reloads holding the same findings, by Refresh and by a poke, notify nothing more.
        val snapshots = { calls.count { it == branchCli + "snapshot" } }
        val before = snapshots()
        runBlocking { ws.refresh().join() }
        ws.poke()
        assertTrue("the poke reloads", waitFor(10_000) { snapshots() >= before + 2 })
        waitFor(500) { false }
        assertEquals(2, healthNotes.size)
        assertEquals(listOf<String>(), notes.map { it.content })
        println("health notifications: ${healthNotes.map { it.content }} after ${snapshots()} snapshots")
    }

    private fun audits(): Int = calls.count { it.takeLast(3) == listOf("audit", "context", "--json") }

    private fun budgetRows(panel: BudgetPanel): List<Pair<String, String>> {
        PlatformTestUtil.waitWhileBusy(panel.tree)
        return (0 until panel.tree.rowCount).map { i ->
            val value = panel.tree.getPathForRow(i).lastPathComponent
            val renderer = panel.tree.cellRenderer.getTreeCellRendererComponent(panel.tree, value, false, true, true, i, false) as BudgetRenderer
            val node = (TreeUtil.getUserObject(value) as BudgetDescriptor).node!!
            (if (node is RowNode) node.row.role else "") to renderer.getCharSequence(false).toString()
        }
    }

    fun testBudgetRunsAuditOnFirstSelectionAndOnRefreshButNotOnAFileChangeReload() {
        val root = sampleProject()
        WsSettings.getInstance().wsCommand = branchCli
        open(root)
        val ws = Workstreams.of(project)
        val window = ToolWindowHeadlessManagerImpl.MockToolWindow(project)
        Disposer.register(testRootDisposable, window.disposable)
        WorkstreamsToolWindow().createToolWindowContent(project, window)
        val manager = window.contentManager
        assertEquals(listOf("Registry", "Review", "Health", "Budget"), manager.contents.map { it.displayName })
        val tab = manager.findContent(BUDGET_TAB)
        val panel = tab.component as BudgetPanel
        waitFor(1_000) { false }
        assertFalse(manager.isSelected(tab))
        assertEquals("nothing runs audit before the tab is selected", 0, audits())
        runBlocking { ws.refresh().join() }
        waitFor(1_000) { false }
        assertEquals("a Refresh while it is hidden doesn't run it either", 0, audits())

        manager.setSelectedContent(tab)
        assertTrue(panel.showing)
        assertTrue("the budget rows", waitFor(30_000) { ws.cachedBudget() != null && budgetRows(panel).isNotEmpty() })
        assertEquals(1, audits())
        val expected = JsonParser.parseString(ws(root, "audit", "context", "--json")) as JsonArray
        val rows = budgetRows(panel)
        assertEquals(expected.map { it.asJsonObject.get("role").asString }, rows.map { it.first })
        val first = expected[0].asJsonObject
        assertTrue(rows[0].second, rows[0].second.startsWith("${first.get("role").asString}  " +
            String.format(java.util.Locale.US, "%,d / %,d · ", first.get("tokens").asInt, first.get("budget").asInt)))
        println("budget once selected: audit ran ${audits()} time(s); rows $rows")

        // A commit under a refresh path reloads the snapshot, which doesn't run audit.
        val snapshots = { calls.count { it == branchCli + "snapshot" } }
        val before = snapshots()
        ws(root, "set-status", "-w", "alpha", "paused")
        sh(root, "git", "commit", "-qam", "pause alpha")
        VfsUtil.markDirtyAndRefresh(false, true, true, LocalFileSystem.getInstance().findFileByPath(root.path)!!)
        assertTrue("no file-change reload", waitFor(10_000) { snapshots() > before })
        waitFor(1_000) { false }
        PlatformTestUtil.waitForFuture(panel.model.invalidateAsync())
        assertEquals("paused", Snapshots.rows(ws.snapshot!!).single { it.id == "alpha" }.status)
        assertEquals(1, audits())
        assertEquals(rows, budgetRows(panel))

        // Refresh, with the tab showing, runs it again.
        runBlocking { ws.refresh().join() }
        assertTrue("Refresh reruns audit", waitFor(10_000) { audits() == 2 && ws.cachedBudget() != null })
        waitFor(1_000) { false }
        assertEquals(2, audits())

        // Leaving the tab and coming back reads nothing new; Refresh while away drops the rows, so coming back reads them.
        manager.setSelectedContent(manager.findContent("Registry"))
        assertFalse(panel.showing)
        manager.setSelectedContent(tab)
        waitFor(1_000) { false }
        assertEquals(2, audits())
        manager.setSelectedContent(manager.findContent("Registry"))
        assertFalse(panel.showing)
        runBlocking { ws.refresh().join() }
        waitFor(1_000) { false }
        assertEquals(2, audits())
        manager.setSelectedContent(tab)
        assertTrue("coming back after a Refresh reads it", waitFor(10_000) { audits() == 3 })
        println("budget: audit ran ${audits()} time(s) in all")
    }
}
