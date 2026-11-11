// What a node offers and what the confirm and launches say, with ui/vscode/test/logic's cases where
// they exist. The prompts here are made-up stand-ins: the real ones are the snapshot's.
package dev.workstream.jetbrains.logic

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class ActionsTest {
    private val pinned = Revisions("r1", mapOf("w" to "t1"))
    private val launches = listOf(LaunchOffer("run", "go w"), LaunchOffer("abandon", "drop w: ", "reason"))

    @Test
    fun rowWritesComeFromTheRowAndFromFindingsForTheWholeRow() {
        val row = Row("w", "active", actions = listOf("sync", "pause", "bogus"))
        val health = listOf(Finding("warning", "w", actions = listOf(Offer("resume", "w"), Offer("unclaim", "w", "T1"))),
                            Finding("warning", "x", actions = listOf(Offer("pause", "x"))))
        assertEquals(listOf("pause", "resume", "sync"), rowWrites(row, health))
        assertEquals(listOf("unclaim"), taskWrites(health, "w", "T1"))
        assertEquals(listOf<String>(), taskWrites(health, "w", "T2"))
    }

    @Test
    fun aNodeOffersOnlyWhatItCarries() {
        val ws = WorkstreamNode("w", Row("w", "active", launches = launches), 0, listOf("pause"), pinned)
        val task = TaskNode("t", "w", Task("T1"), listOf(), listOf("unclaim"), pinned)
        val bare = TaskNode("t2", "w", Task("T2"), listOf())
        assertEquals("w" to Confirm("pause"), targetOf(ws, "pause"))
        assertNull(targetOf(ws, "resume"))
        assertEquals("w" to Confirm("unclaim", "T1"), targetOf(task, "unclaim"))
        assertNull(targetOf(bare, "unclaim"))
        assertNull(targetOf("not a node", "pause"))
        assertNull(pinnedOf("not a node"))
        assertEquals(pinned, pinnedOf(task))
        assertEquals(LaunchOffer("run", "go w"), launchOf(ws, "run"))
        assertNull(launchOf(ws, "close"))
        assertNull(launchOf(task, "run"))
    }

    @Test
    fun theConfirmNamesTheCommitLineAndBranchAndSaysWhenBehind() {
        assertEquals(ConfirmText("Pause w?", listOf("This commits \"w: pause\" on main.")), confirmText("w", "pause", null, "main", false))
        assertEquals(ConfirmText("Unclaim T1?", listOf("This commits \"w: unclaim T1\" on dev.",
                                                       "This has changed since the tree drew it, so the write will be refused.")),
                     confirmText("w", "unclaim", "T1", "dev", true))
        assertFalse(moved(pinned, null, "w"))
        assertFalse(moved(pinned, Revisions("r1", mapOf("w" to "t1", "x" to "other")), "w"))
        assertTrue(moved(pinned, Revisions("r2", mapOf("w" to "t1")), "w"))
        assertTrue(moved(pinned, Revisions("r1", mapOf("w" to "t2")), "w"))
    }

    @Test
    fun theTerminalArgvIsTheAgentThenThePromptAndAbandonAppendsTheReason() {
        assertEquals(listOf("agent", "--flag", "go w"), terminalArgv(listOf("agent", "--flag"), promptOf(launches[0], null)))
        assertEquals("drop w: not needed", promptOf(launches[1], "not needed"))
        assertNull(terminalArgv(listOf(), "go w"))
        assertNull(terminalArgv(listOf(" "), "go w"))
        assertEquals("Run w", launchTitle("run", "w"))
        assertTrue(clipboardLine("Run w", "go w", terminal = true, agentSet = false).contains(AGENT_SETTING))
        assertTrue(clipboardLine("Run w", "go w", terminal = false, agentSet = true).contains("Terminal plugin is not enabled"))
    }
}
