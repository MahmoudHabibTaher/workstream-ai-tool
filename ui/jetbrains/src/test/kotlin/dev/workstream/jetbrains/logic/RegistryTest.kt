// The Registry tree as data, with the cases ui/vscode/test/logic/registry.test.ts uses.
package dev.workstream.jetbrains.logic

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class RegistryTest {
    private val rows = listOf(
        Row("old", "done", progress = Progress(2, 2)),
        Row("alpha", "active", title = "Alpha", summary = "the [x](command:evil) <b>sum</b>", progress = Progress(1, 3)),
        Row("gone", "abandoned"),
        Row("beta", "paused", progress = Progress(0, 0)),
    )
    private val health = listOf(Finding("error", "alpha"), Finding("error", "alpha"), Finding("warning", "beta"))
    private fun t(id: String, status: String = "todo", phase: Int = 1, priority: Int = 10, blockedBy: List<String> = listOf(),
                  mode: String? = null, title: String? = null) = Task(id, phase, priority, status, blockedBy, title = title, mode = mode)
    private val view = WsView(
        tasks = listOf(t("A-3", phase = 2, priority = 30, blockedBy = listOf("A-1")), t("A-2", priority = 20, mode = "foreground"),
                       t("A-1", status = "done", title = "First")),
        wave = Wave("ready", 1, listOf("A-2"), leftovers = listOf()),
        docs = mapOf("plan" to "/p/ws/alpha/PLAN.md", "handoff" to "/p/ws/alpha/session_handoff.md"),
    )

    private fun labels(nodes: List<Node>) = nodes.map { shown(it).label }

    @Test
    fun openWorkstreamsInRegistryOrderAndShowDoneAddsTheClosedOnesAfterThem() {
        assertEquals(listOf("alpha", "beta"), labels(workstreams(rows, health, false)))
        assertEquals(listOf("alpha", "beta", "old", "gone"), labels(workstreams(rows, health, true)))
        assertEquals("active · 1/3 · 2 errors", shown(workstreams(rows, health, false)[0]).description)
    }

    @Test
    fun aWorkstreamOpensToItsWaveLineItsPhasesInOrderThenItsDocuments() {
        val children = workstreamChildren("alpha", view)
        assertEquals(listOf("WaveNode", "PhaseNode", "PhaseNode", "DocumentsNode"), children.map { it.javaClass.simpleName })
        assertEquals(listOf("Phase 1: 1 ready", "Phase 1", "Phase 2", "Documents"), labels(children))
        val tasks = phaseChildren(children[1] as PhaseNode, 0)
        assertEquals(listOf("A-1 First", "A-2"), labels(tasks))
        assertEquals(listOf("done", "todo · ★ ready · foreground"), tasks.map { shown(it).description })
        assertEquals(listOf("todo"), phaseChildren(children[2] as PhaseNode, 0).map { shown(it).description })
        val docs = documentChildren(children[3] as DocumentsNode)
        assertEquals(listOf("Plan" to "/p/ws/alpha/PLAN.md", "Handoff" to "/p/ws/alpha/session_handoff.md"),
                     docs.map { shown(it).label to (it as DocumentNode).path })
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
    fun nodeIdsAreStableAndDistinct() {
        val all = workstreams(rows, health, true) + workstreamChildren("alpha", view)
        assertEquals(all.size, all.map { it.id }.toSet().size)
        assertEquals(workstreams(rows, health, true).map { it.id }, workstreams(rows, health, true).map { it.id })
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
