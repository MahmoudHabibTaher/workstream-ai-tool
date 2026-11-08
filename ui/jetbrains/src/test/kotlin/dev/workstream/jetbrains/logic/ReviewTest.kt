// The Review queue as data, with the cases ui/vscode/test/logic/review.test.ts uses.
package dev.workstream.jetbrains.logic

import org.junit.Assert.assertEquals
import org.junit.Test

class ReviewTest {
    private fun entry(task: String, state: String, files: Int = 2, hasEvidence: Boolean = true) =
        Entry("alpha", task, state, title = "Title $task", files = files, added = 3, removed = 1, hasEvidence = hasEvidence)

    private val sha = "b".repeat(40)
    private val checks = Checks(
        "branch", null,
        listOf(Gate("evidence", ok = true, blocking = true), Gate("verify", ok = false, blocking = false, detail = "none ran")),
        "# T1 evidence", "done", "",
        listOf(Item(1, "it works", "`ok` printed"), Item(2, "it is fast", "")),
    )
    private fun review(range: Range = Range("branch", sha, "task/t1"), evidence: String? = null,
                       files: List<FileStat> = listOf(FileStat("a.txt", 1, 0), FileStat("img.png", null, null)),
                       checks: Checks? = this.checks, error: String? = null) = Review("T1", evidence, range, files, checks, error)

    private fun rowOf(e: Entry) = EntryNode("x", e)
    private fun labels(nodes: List<ReviewNode>) = nodes.map { reviewShown(it).label }

    @Test
    fun theQueueListsBranchWorkBeforeLandedWorkWhateverOrderItCameIn() {
        val nodes = queueNodes(listOf(entry("L1", "landed"), entry("B1", "branch"), entry("L2", "landed"), entry("B2", "branch")))
        assertEquals(listOf("On a branch", "Landed"), labels(nodes))
        assertEquals(listOf(listOf("B1", "B2"), listOf("L1", "L2")), nodes.map { n -> groupChildren(n as GroupNode).map { (it as EntryNode).entry.task } })
        assertEquals(listOf("2", "2"), nodes.map { reviewShown(it).description })
    }

    @Test
    fun anEmptyGroupIsLeftOutAndAnEmptyQueueSaysSo() {
        assertEquals(listOf("Landed"), labels(queueNodes(listOf(entry("L1", "landed")))))
        assertEquals(listOf("Nothing to review."), labels(queueNodes(listOf())))
    }

    @Test
    fun aQueueRowNamesItsWorkstreamItsDiffstatAndMissingEvidence() {
        val group = queueNodes(listOf(entry("B1", "branch", files = 1, hasEvidence = false))).single() as GroupNode
        assertEquals(Shown("B1 Title B1", "alpha · 1 file +3 −1 · no evidence",
                           listOf(Section(lines = listOf("B1 Title B1", "alpha · 1 file +3 −1 · no evidence"))), collapsible = true),
                     reviewShown(groupChildren(group).single()))
    }

    @Test
    fun underABranchTaskRangeGateSummaryAcceptanceWithProofEvidenceFiles() {
        val nodes = entryChildren(rowOf(entry("T1", "branch")), review())
        assertEquals(listOf(NoteNode::class, GatesNode::class, ItemsNode::class, EvidenceNode::class, FilesNode::class), nodes.map { it::class })
        assertEquals(listOf("branch: ${"b".repeat(10)}...task/t1", "Would land, with 1 warning", "Acceptance and proof", "Evidence", "Files"), labels(nodes))
        assertEquals(listOf("evidence" to "", "verify" to "none ran"), gateChildren(nodes[1] as GatesNode).map { reviewShown(it).label to reviewShown(it).description })
        val items = itemChildren(nodes[2] as ItemsNode)
        assertEquals("1/2 quoted", reviewShown(nodes[2]).description)
        assertEquals(listOf("1. it works" to "`ok` printed", "2. it is fast" to "Nothing quoted."), items.map { reviewShown(it).label to reviewShown(it).description })
        assertEquals(listOf(Section("Acceptance", listOf("it is fast")), Section("Proof", listOf("Nothing quoted."))), reviewShown(items[1]).tip)
        assertEquals(true, (nodes[3] as EvidenceNode).onBranch)
        assertEquals("# T1 evidence", (nodes[3] as EvidenceNode).text)
        assertEquals(listOf("a.txt" to "+1 −0", "img.png" to "binary"), fileChildren(nodes[4] as FilesNode).map { reviewShown(it).label to reviewShown(it).description })
    }

    @Test
    fun aLandedTaskSaysItsGatesRanWhenItLandedABlockedOneSaysWhy() {
        val landed = review(Range("merge", "$sha^1", sha), "/p/ws/evidence/T1.md",
                            checks = checks.copy(state = "landed", commit = sha, gates = listOf(), evidenceStatus = "blocked", reason = "no key"))
        val nodes = entryChildren(rowOf(entry("T1", "landed")), landed)
        assertEquals(listOf("merge: ${"b".repeat(10)}^1..${"b".repeat(10)}", "Landed as ${"b".repeat(10)}. Its gates ran when it landed.", "Blocked: no key"),
                     labels(nodes).take(3))
        val evidence = nodes.filterIsInstance<EvidenceNode>().single()
        assertEquals(false to "/p/ws/evidence/T1.md", evidence.onBranch to evidence.path)
    }

    @Test
    fun noEvidenceNoItemsAndAGitErrorEachSaySo() {
        val bare = review(files = listOf(), error = "git diff: bad revision", checks = checks.copy(evidenceText = null, items = listOf()))
        assertEquals(listOf("branch: ${"b".repeat(10)}...task/t1", "git diff: bad revision", "Would land, with 1 warning",
                            "This task lists no acceptance items.", "No evidence file yet."),
                     labels(entryChildren(rowOf(entry("T1", "branch")), bare)))
    }

    @Test
    fun aDiffIsTitledByItsPathAndBothRevisionsABinaryFileSaysItOpensNothing() {
        assertEquals("a.txt (T1: ${"c".repeat(10)} ↔ ${"d".repeat(10)})", diffTitle("a.txt", "T1", "c".repeat(40), "d".repeat(40)))
        assertEquals("img.png is binary, so no diff opens.", binaryLine("img.png"))
        assertEquals("old ${"c".repeat(10)}", sideTitle(ShowSide("a.txt", "old", "c".repeat(40), "x", false)))
    }

    @Test
    fun openingSaysAFailureOrABinarySideAndOtherwiseGivesBothSides() {
        val text = ShowSide("a.txt", "old", "c".repeat(40), "x\n", false)
        val added = ShowSide("a.txt", "old", "c".repeat(40), null, false)
        val binary = ShowSide("a.txt", "new", "d".repeat(40), null, true)
        assertEquals(Opening.Say("no such task", true), opening("a.txt", Loaded.Error("no such task"), Loaded.Value(text)))
        assertEquals(Opening.Say("a.txt is binary, so no diff opens.", false), opening("a.txt", Loaded.Value(text), Loaded.Value(binary)))
        assertEquals(Opening.Sides(added, text), opening("a.txt", Loaded.Value(added), Loaded.Value(text)))
    }
}
