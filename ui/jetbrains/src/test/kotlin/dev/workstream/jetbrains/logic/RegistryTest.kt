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
    fun theStatusBarNamesTheClaimedTaskAndItsAgeWhileATaskIsClaimed() {
        assertNull(claimedTask(view))
        assertNull(claimedTask(null))
        val start = "2026-01-01T00:00:00Z"
        val now = Instant.parse(start).toEpochMilli() + 5 * 60 * 60_000L
        val claimed = view.copy(tasks = view.tasks + Task("A-4", status = "in-progress", claimedBy = "agent-1", startedAt = start))
        assertEquals("A-4", claimedTask(claimed)?.id)
        assertEquals("● alpha · A-4 · 5h", statusText("alpha", claimed.wave, 0, claimedTask(claimed), now))
        assertEquals("● alpha · A-4 · 5h · 2 errors", statusText("alpha", claimed.wave, 2, claimedTask(claimed), now))
        // A claim with no start, or one that doesn't parse, shows no age.
        assertEquals("● alpha · A-5", statusText("alpha", null, 0, Task("A-5", status = "in-progress"), now))
        assertEquals("● alpha · A-5", statusText("alpha", null, 0, Task("A-5", status = "in-progress", startedAt = "soon"), now))
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

    @Test
    fun theGraphGrowsFromTheTasksNothingKnownBlocksAndShowsARepeatOnlyOnce() {
        val tasks = listOf(t("B-1", unblocks = listOf("B-2", "B-3")), t("B-2", blockedBy = listOf("B-1"), unblocks = listOf("B-4")),
                           t("B-3", blockedBy = listOf("B-1", "Z-9"), unblocks = listOf("B-4")),
                           t("B-4", status = "blocked", blockedBy = listOf("B-2", "B-3"), title = "Last"),
                           t("C-1", blockedBy = listOf("C-2"), unblocks = listOf("C-2")), t("C-2", blockedBy = listOf("C-1"), unblocks = listOf("C-1")))
        val rows = taskRows("beta", WsView(tasks, null, mapOf()), 0)
        fun lines(nodes: List<GraphNode>, depth: Int = 0): List<String> = nodes.flatMap { n ->
            val l = graphLabel(n)
            listOf("  ".repeat(depth) + listOf(l.id, l.title, l.detail).filter { it.isNotEmpty() }.joinToString(" | ")) + lines(n.children, depth + 1)
        }
        assertEquals(listOf(
            "B-1 | todo",
            "  B-2 | todo",
            "    B-4 | Last | blocked",
            "  B-3 | todo",
            "    B-4 | Last | blocked · shown above",
            "C-1 | todo",
            "  C-2 | todo",
            "    C-1 | todo · shown above",
        ), lines(graph(rows)))
    }

    @Test
    fun theOverviewShowsDocumentsTheRowClaimsScopeVerifyAndBaseline() {
        val now = Instant.parse("2026-01-01T03:00:00Z").toEpochMilli()
        val row = Row("alpha", "active", title = "Alpha", summary = "sum", progress = Progress(1, 3, 1), dependsOn = listOf("base"),
                      tier = "standard", created = "2025-12-30", startedAt = "2025-12-31", baseCommit = "abc1234", notes = "a note")
        val v = view.copy(
            tasks = view.tasks + Task("A-4", status = "in-progress", claimedBy = "agent-1", startedAt = "2026-01-01T00:00:00Z",
                                      verifyCommands = listOf(VerifyCommand("test", "make test"), VerifyCommand("make lint", "make lint"))) +
                Task("A-5", verifyCommands = listOf(VerifyCommand("test", "make test"))),
            scope = Scope(listOf("src"), listOf("docs"), "Stay in src"),
            baseline = Baseline(listOf(BaselineKey("test", "workstream", "make test", 0, 2, "2026-01-01T00:00:00Z", "0123456789abcdef")), listOf("lint: no record")),
        )
        val found = overview(row, v, now)
        assertEquals(listOf("Documents", "Registry", "Open claims", "Scope", "In scope", "Out of scope", "Verify", "Baseline"), found.map { it.heading })
        assertEquals(listOf(PaneItem.FileLink("/p/ws/alpha/PLAN.md", "Plan"), PaneItem.FileLink("/p/ws/alpha/session_handoff.md", "Handoff")), found[0].items)
        assertEquals(listOf("alpha: Alpha", "sum", "active · standard tier", "1/3 done · 1 claimed", "Depends on base",
                            "created 2025-12-30 · started 2025-12-31", "Base abc1234", "a note").map { PaneItem.Line(it) }, found[1].items)
        assertEquals(listOf(PaneItem.TaskLink("A-4", "A-4 · agent-1 · 3h ago")), found[2].items)
        assertEquals(listOf(PaneItem.Line("Stay in src")), found[3].items)
        assertEquals(listOf(PaneItem.Line("test: make test"), PaneItem.Line("make lint")), found[6].items)
        assertEquals(listOf(PaneItem.Line("test: make test · workstream · exit 0 · 2 findings · 2026-01-01T00:00:00Z · 0123456789"),
                            PaneItem.Line("Error: lint: no record")), found[7].items)

        // Nothing to say still says so for claims and the baseline; no row, scope or verify leaves those out.
        val bare = overview(null, WsView(listOf(t("A-1")), null, mapOf()), now)
        assertEquals(listOf("Open claims", "Baseline"), bare.map { it.heading })
        assertEquals(listOf(listOf(PaneItem.Line("None")), listOf(PaneItem.Line("None recorded"))), bare.map { it.items })
    }
}
