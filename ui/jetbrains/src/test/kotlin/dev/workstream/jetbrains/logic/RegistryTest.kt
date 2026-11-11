// The Workstreams tab as data: the list's rows, the table's rows and cells, and the task pane.
package dev.workstream.jetbrains.logic

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test
import java.time.Instant

class RegistryTest {
    private val rows = listOf(
        Row("old", "done", progress = Progress(2, 2)),
        Row("alpha", "active", title = "Alpha", summary = "the [x](command:evil) <b>sum</b>", progress = Progress(1, 3, 1)),
        Row("gone", "abandoned"),
        Row("beta", "paused", progress = Progress(0, 0)),
    )
    private val health = listOf(Finding("error", "alpha"), Finding("error", "alpha"), Finding("warning", "beta"),
                                Finding("warning", "alpha", "A-2", actions = listOf(Offer("unclaim", "alpha", "A-2"))))
    private fun t(id: String, status: String = "todo", phase: Int = 1, priority: Int = 10, blockedBy: List<String> = listOf(),
                  mode: String? = null, title: String? = null, unblocks: List<String> = listOf(), waitingOn: List<String> = listOf()) =
        Task(id, phase, priority, status, blockedBy, title = title, mode = mode, unblocks = unblocks, waitingOn = waitingOn)
    private val pinned = Revisions("r", mapOf("alpha" to "t"))
    private val view = WsView(
        tasks = listOf(t("A-3", phase = 2, priority = 30, blockedBy = listOf("A-1", "Z-9"), waitingOn = listOf("Z-9")),
                       t("A-2", priority = 20, mode = "foreground"),
                       t("A-1", status = "done", title = "First", unblocks = listOf("A-3"))),
        wave = Wave("ready", 1, listOf("A-2"), leftovers = listOf()),
        docs = mapOf("plan" to "/p/ws/alpha/PLAN.md", "handoff" to "/p/ws/alpha/session_handoff.md"),
        revisions = pinned,
        health = health,
    )

    @Test
    fun openWorkstreamsInRegistryOrderAndShowDoneAddsTheClosedOnesAfterThem() {
        assertEquals(listOf("alpha", "beta"), workstreams(rows, health, false).map { it.row.id })
        assertEquals(listOf("alpha", "beta", "old", "gone"), workstreams(rows, health, true).map { it.row.id })
        assertEquals("active · 1/3 · 2 errors", shown(workstreams(rows, health, false)[0]).description)
    }

    @Test
    fun aListRowShowsDoneOverTotalStatusClaimsAndErrors() {
        val all = workstreams(rows, health, true).associateBy { it.row.id }
        assertEquals(listOf("1/3", "active", "1 claimed", "2 errors"), rowDetails(all.getValue("alpha")))
        assertEquals(listOf("0/0", "paused"), rowDetails(all.getValue("beta")))
        assertEquals(listOf("abandoned"), rowDetails(all.getValue("gone")))
    }

    @Test
    fun theTableListsTasksPhaseByPhaseInPriorityOrderWithTheSnapshotsWaitingOn() {
        val found = taskRows("alpha", view, 0)
        assertEquals(listOf("A-1", "A-2", "A-3"), found.map { it.task.id })
        assertEquals(listOf(
            listOf("done", "A-1", "1", "First", ""),
            listOf("todo", "A-2", "1", "", ""),
            listOf("todo", "A-3", "2", "", "Z-9"),
        ), found.map(::taskCells))
        assertEquals(TASK_COLUMNS.size, taskCells(found[0]).size)
        // Each row pins the view's revisions and offers only what a finding offers it.
        assertEquals(listOf(pinned, pinned, pinned), found.map { it.revisions })
        assertEquals(listOf(listOf(), listOf("unclaim"), listOf()), found.map { it.writes })
        assertEquals(listOf("★ ready", "foreground"), found[1].badges)
    }

    @Test
    fun theTaskPaneLinksTheTasksTheTableHoldsAndOpensItsFiles() {
        val now = Instant.parse("2026-11-03T12:00:00Z").toEpochMilli()
        val task = Task("A-3", status = "in-progress", title = "Third", summary = "<img src=x>", blockedBy = listOf("A-1", "Z-9"),
                        unblocks = listOf("A-4"), files = listOf("src/a.kt"), acceptanceText = listOf("[a](command:x)"),
                        verifyCommands = listOf(VerifyCommand("test", "make test"), VerifyCommand("make lint", "make lint")),
                        notes = "a note", claimedBy = "agent-1", startedAt = "2026-11-03T09:00:00Z", blockedReason = null)
        val node = TaskNode("x", "alpha", task, listOf("claimed 3h"))
        assertEquals(listOf(
            PaneSection(null, listOf(PaneItem.Line("A-3: Third"))),
            PaneSection(null, listOf(PaneItem.Line("in-progress · claimed 3h"))),
            PaneSection("Summary", listOf(PaneItem.Line("<img src=x>"))),
            PaneSection("Claim", listOf(PaneItem.Line("agent-1 · 3h ago"))),
            PaneSection("Depends on", listOf(PaneItem.TaskLink("A-1"), PaneItem.Line("Z-9"))),
            PaneSection("Unblocks", listOf(PaneItem.TaskLink("A-4"))),
            PaneSection("Files", listOf(PaneItem.FileLink("src/a.kt"))),
            PaneSection("Acceptance", listOf(PaneItem.Line("[a](command:x)"))),
            PaneSection("Verify", listOf(PaneItem.Line("test: make test"), PaneItem.Line("make lint"))),
            PaneSection("Notes", listOf(PaneItem.Line("a note"))),
        ), taskPane(node, setOf("A-1", "A-3", "A-4"), now))
        // A bare task says only what it is.
        assertEquals(listOf(PaneSection(null, listOf(PaneItem.Line("T"))), PaneSection(null, listOf(PaneItem.Line("todo")))),
                     taskPane(TaskNode("y", "alpha", Task("T"), listOf()), setOf("T"), now))
    }

    @Test
    fun aTaskTooltipCarriesItsSummaryAcceptanceAndVerifyLinesAsPlainLinesUnderFixedHeadings() {
        val task = Task("A-1", title = "First", summary = "<img src=x>", acceptanceText = listOf("[a](command:x)"),
                        verifyCommands = listOf(VerifyCommand("test", "make test"), VerifyCommand("make lint", "make lint")))
        assertEquals(listOf(
            Section(lines = listOf("A-1: First")), Section(lines = listOf("todo")), Section(lines = listOf("<img src=x>")),
            Section("Acceptance", listOf("[a](command:x)")), Section("Verify", listOf("test: make test", "make lint")),
        ), shown(TaskNode("x", "alpha", task, listOf())).tip)
    }

    @Test
    fun documentsFilesAndTheTaskInItsFile() {
        assertEquals(listOf("Plan" to "/p/ws/alpha/PLAN.md", "Handoff" to "/p/ws/alpha/session_handoff.md"), documents(view))
        assertEquals(java.io.File("/p", "src/a.kt").path, filePath("/p", "src/a.kt"))
        assertEquals("src/a.kt", filePath(null, "src/a.kt"))
        val text = "{\"tasks\": [\n  {\"id\": \"A-1\"},\n  {\"id\" : \"A-10\"},\n  {\"id\":  \"A-1.x\"}]}"
        assertEquals(text.indexOf("\"id\": \"A-1\""), taskOffset(text, "A-1"))
        assertEquals(text.indexOf("\"id\" : \"A-10\""), taskOffset(text, "A-10"))
        assertEquals(text.indexOf("\"id\":  \"A-1.x\""), taskOffset(text, "A-1.x"))
        assertNull(taskOffset(text, "A-2"))
    }

    @Test
    fun nodeIdsAreStableAndDistinct() {
        val all = workstreams(rows, health, true) + taskRows("alpha", view, 0)
        assertEquals(all.size, all.map { it.id }.toSet().size)
        assertEquals(workstreams(rows, health, true), workstreams(rows.map { it.copy(title = "changed") }, listOf(), true))
    }

    @Test
    fun theStatusBarNamesTheFirstActiveWorkstreamItsWaveLineAndItsErrors() {
        assertEquals("alpha" to 2, activeWorkstream(rows, health)?.let { (row, errors) -> row.id to errors })
        assertEquals("alpha: Phase 1: 1 ready · 2 errors", statusText("alpha", view.wave, 2))
        assertEquals("alpha", statusText("alpha", null, 0))
        assertNull(activeWorkstream(listOf(Row("b", "paused")), listOf()))
    }

    @Test
    fun aChangeCountsOnlyUnderARefreshPathKeepingItsRecursiveFlag() {
        val watches = listOf(Watch("/p/reg.json", false), Watch("/p/ws/alpha", true), Watch("/p/.git/refs/heads", true), Watch("/p/.git", false))
        assertTrue(underRefresh("/p/reg.json", watches))
        assertTrue(underRefresh("/p/ws/alpha/tasks/x.json", watches))
        assertTrue(underRefresh("/p/.git/refs/heads/task/x", watches))
        assertTrue(underRefresh("/p/.git/HEAD", watches))
        assertFalse(underRefresh("/p/.git/objects/ab/cdef", watches))
        assertFalse(underRefresh("/p/ws/alphabet/PLAN.md", watches))
        assertFalse(underRefresh("/p/src/main.kt", watches))
    }
}
