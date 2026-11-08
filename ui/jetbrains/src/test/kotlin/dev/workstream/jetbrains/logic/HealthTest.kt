// Health and Budget as plain data, with ui/vscode/test/logic's cases where they exist, and which
// error findings are new to the session (plan T12).
package dev.workstream.jetbrains.logic

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

class HealthTest {
    private val pinned = Revisions("r1", mapOf("w" to "t1"))
    private val stale = Finding("warning", "w", "T1", "T1 in progress for 48h", listOf(Offer("unclaim", "w", "T1"), Offer("bogus", "w")), "stale-claim")
    private val bad = Finding("error", "w", null, "w: mode '<b>x</b>' is wrong", kind = "invalid")
    private val odd = Finding("info", null, null, "", kind = "note")

    @Test
    fun errorsComeFirstThenWarningsThenOtherLevelsEachInTheClisOrder() {
        val nodes = healthNodes(listOf(stale, odd, bad), pinned, "git failed")
        assertEquals(listOf("git failed", "Errors", "Warnings", "info"), nodes.map { healthShown(it).label })
        assertEquals(listOf("", "1", "1", "1"), nodes.map { healthShown(it).description })
        val warnings = levelChildren(nodes[2] as LevelNode).single() as FindingNode
        assertEquals(stale, warnings.finding)
        assertEquals(listOf("unclaim"), warnings.writes)
        assertEquals(pinned, warnings.revisions)
        assertEquals(Shown("T1 in progress for 48h", "stale-claim · w T1", listOf(Section(lines = listOf("T1 in progress for 48h")),
                                                                                  Section(lines = listOf("warning · stale-claim · w T1")))),
                     healthShown(warnings))
        // A finding with no message is labelled by its kind.
        assertEquals("note", healthShown(levelChildren(nodes[3] as LevelNode).single()).label)
        assertEquals(listOf("Nothing to report."), healthNodes(listOf(), null).map { healthShown(it).label })
    }

    @Test
    fun aFindingsWriteIsForTheWorkstreamAndTaskItsOfferNames() {
        val node = findingNodes(listOf(stale), pinned).single()
        assertEquals("w" to Confirm("unclaim", "T1"), targetOf(node, "unclaim"))
        assertNull(targetOf(node, "pause"))
        assertEquals(pinned, pinnedOf(node))
        assertNull(launchOf(node, "run"))
        assertNull(targetOf(findingNodes(listOf(bad), pinned).single(), "unclaim"))
    }

    @Test
    fun onlyAnErrorNotYetNotifiedIsNew() {
        val seen = mutableSetOf<List<String?>>()
        val first = newErrors(listOf(stale, bad, bad), seen)
        assertEquals(listOf(bad), first)
        assertEquals("Workstreams error: w: mode '<b>x</b>' is wrong", noticeLine(first))
        seen += first.map(::noticeKey)
        assertEquals(listOf<Finding>(), newErrors(listOf(stale, bad), seen))
        assertNull(noticeLine(listOf()))
        // The key is kind, workstream, task and message: another message is another finding.
        val other = bad.copy(message = "w: another")
        assertEquals(listOf(other), newErrors(listOf(bad, other), seen))
        assertEquals("2 new workstream errors. The first: w: another", noticeLine(listOf(other, bad.copy(task = "T9"))))
    }

    @Test
    fun aBudgetRowShowsItsTokensAgainstItsLimitTheShareAndOver() {
        val rows = listOf(BudgetRow("worker", 900, 2500, true), BudgetRow("coordinator", 3200, 3000, false), BudgetRow("none", 5, 0, true))
        val nodes = budgetNodes(rows)
        assertEquals(listOf("worker", "coordinator", "none"), nodes.map { budgetShown(it).label })
        assertEquals(listOf("900 / 2,500 · 36%", "3,200 / 3,000 · 107% · over", "5 / 0 · 0%"), nodes.map { budgetShown(it).description })
        assertEquals(listOf(Section(lines = listOf("coordinator")), Section(lines = listOf("3200 of 3000 tokens, over its limit"))), budgetShown(nodes[1]).tip)
        assertEquals(listOf("No roles measured."), budgetNodes(listOf()).map { budgetShown(it).label })
    }
}
