// The helpers ported from ui/vscode/src/logic/format.ts, with the cases ui/vscode/test/logic/format.test.ts uses.
package dev.workstream.jetbrains.logic

import org.junit.Assert.assertEquals
import org.junit.Test
import java.time.Instant

class FormatTest {
    private fun task(id: String, status: String = "todo", phase: Int = 1, priority: Int = 10, blockedBy: List<String> = listOf(),
                     mode: String? = "background", needsUserDecision: Boolean = false, startedAt: String? = null,
                     blockedReason: String? = null, title: String? = null) =
        Task(id, phase, priority, status, blockedBy, title = title, mode = mode, needsUserDecision = needsUserDecision,
             startedAt = startedAt, blockedReason = blockedReason)

    private fun at(iso: String) = Instant.parse(iso).toEpochMilli()

    @Test
    fun theTaskScreenSaysWhyATaskIsBlockedAndNothingWhenNoReasonIsRecorded() {
        assertEquals("Blocked: no key", blockedLine(task("a", status = "blocked", blockedReason = "no key")))
        assertEquals("", blockedLine(task("b", status = "blocked", blockedReason = null, title = "The title")))
        assertEquals("", blockedLine(task("c")))
    }

    @Test
    fun theWaveLineSaysWhatStateTheQueueIsIn() {
        assertEquals("Queue finished", waveLine(Wave("finished")))
        assertEquals("Stuck: 2 open, none actionable", waveLine(Wave("stuck", open = listOf("a", "b"))))
        assertEquals("Phase 2: 1 ready", waveLine(Wave("ready", 2, listOf("a"), leftovers = listOf())))
        assertEquals("Phase 2: 1 ready · 1 left over", waveLine(Wave("ready", 2, listOf("a"), leftovers = listOf("z"))))
        assertEquals("", waveLine(null))
    }

    @Test
    fun agesReadInTheLargestSensibleUnit() {
        val now = at("2026-11-03T12:00:00Z")
        assertEquals("30m", ageOf("2026-11-03T11:30:00Z", now))
        assertEquals("10h", ageOf("2026-11-03T02:00:00Z", now))
        assertEquals("4d", ageOf("2026-10-30T12:00:00Z", now))
        assertEquals("0m", ageOf("2026-11-03T13:00:00Z", now))
    }

    @Test
    fun badgesComeFromTheTaskAndTheWave() {
        val tasks = listOf(task("A", status = "done"), task("B", blockedBy = listOf("A", "C")),
                           task("C", status = "in-progress", startedAt = "2026-11-03T11:00:00Z"))
        val now = at("2026-11-03T12:00:00Z")
        fun texts(t: Task) = badgesOf(t, tasks, listOf("C"), now).map { it.text }
        assertEquals(listOf("waits on C"), texts(tasks[1]))
        assertEquals(listOf("★ ready", "claimed 1h"), texts(tasks[2]))
        assertEquals(listOf("foreground", "needs decision"), texts(task("D", mode = "foreground", needsUserDecision = true)))
    }

    @Test
    fun lanesGoByPhaseThenPriority() {
        val found = lanes(listOf(task("B", phase = 2), task("C", priority = 20), task("A", priority = 5)))
        assertEquals(listOf(1 to listOf("A", "C"), 2 to listOf("B")), found.map { l -> l.phase to l.tasks.map { it.id } })
    }

    @Test
    fun closedRowsAreSplitFromOpenOnes() {
        val (open, closed) = splitRows(listOf("active", "done", "paused", "abandoned").mapIndexed { i, s -> Row("r$i", s) })
        assertEquals(listOf(2, 2), listOf(open.size, closed.size))
    }

    @Test
    fun errorsAreCountedPerWorkstreamWarningsLeftOut() {
        val health = listOf(Finding("error", "w"), Finding("warning", "w"), Finding("error", null), Finding("error", "w"))
        assertEquals(2, errorCount(health, "w"))
        assertEquals(0, errorCount(health, "x"))
    }
}
