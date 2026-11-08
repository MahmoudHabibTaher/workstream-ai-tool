// Cli.kt against a stub in place of a process: the argv each call builds, and what it makes of
// a missing command, a failure, bad JSON and a snapshot of another version.
package dev.workstream.jetbrains

import dev.workstream.jetbrains.logic.Confirm
import dev.workstream.jetbrains.logic.Loaded
import dev.workstream.jetbrains.logic.Ran
import dev.workstream.jetbrains.logic.Revisions
import dev.workstream.jetbrains.logic.Rooted
import dev.workstream.jetbrains.logic.Run
import dev.workstream.jetbrains.logic.SETTING
import dev.workstream.jetbrains.logic.Side
import dev.workstream.jetbrains.logic.notAProject
import dev.workstream.jetbrains.logic.noWs
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class CliTest {
    private class Stub(val answer: (List<String>) -> Ran = { Ran(0, "{}", "") }) : Run {
        val calls = mutableListOf<Pair<List<String>, String>>()
        override fun run(argv: List<String>, cwd: String): Ran {
            calls += argv to cwd
            return answer(argv)
        }
    }

    private val cmd = listOf("wsx", "--flag")

    @Test
    fun anEmptyCommandIsWs() {
        assertEquals(listOf("ws"), Cli(listOf(), Stub()).command)
    }

    @Test
    fun everyReadBuildsItsArgvAtTheRoot() {
        val stub = Stub { argv -> Ran(0, if (argv.contains("snapshot")) """{"snapshotVersion": 1}""" else "[]", "") }
        val cli = Cli(cmd, stub)
        cli.loadSnapshot("/r")
        cli.loadSnapshot("/r", "alpha")
        cli.loadReview("/r", "alpha", "T1")
        cli.loadReview("/r", "alpha", "T1", checks = true, file = "a.txt")
        cli.loadShow("/r", "alpha", "T1", "a.txt", Side.OLD)
        cli.loadQueue("/r")
        cli.loadBudget("/r")
        assertEquals(
            listOf(
                listOf("snapshot"),
                listOf("snapshot", "-w", "alpha"),
                listOf("review", "T1", "-w", "alpha"),
                listOf("review", "T1", "-w", "alpha", "--checks", "--file", "a.txt"),
                listOf("review", "T1", "-w", "alpha", "--show", "a.txt", "--side", "old"),
                listOf("review", "--queue"),
                listOf("audit", "context", "--json"),
            ).map { cmd + it },
            stub.calls.map { it.first },
        )
        assertTrue(stub.calls.all { it.second == "/r" })
    }

    @Test
    fun resolveRootRunsInTheFolder() {
        val stub = Stub { Ran(0, "/the/root\n", "") }
        assertEquals(Rooted.Root("/the/root"), Cli(cmd, stub).resolveRoot("/the/root/sub"))
        assertEquals(listOf(cmd + "root" to "/the/root/sub"), stub.calls)
    }

    @Test
    fun aFolderThatIsNotAProject() {
        val got = Cli(cmd, Stub { Ran(1, "", "not a project") }).resolveRoot("/tmp/x")
        assertEquals(Rooted.Problem(notAProject("/tmp/x"), missing = false), got)
    }

    @Test
    fun aMissingWsNamesTheSetting() {
        val got = Cli(cmd, Stub { Ran(127, "", "", missing = true) }).resolveRoot("/tmp/x")
        assertEquals(Rooted.Problem(noWs(cmd), missing = true), got)
        assertTrue(noWs(cmd).contains(SETTING))
        assertEquals(Loaded.Error(noWs(cmd)), Cli(cmd, Stub { Ran(127, "", "", missing = true) }).loadQueue("/r"))
    }

    @Test
    fun aSnapshotOfAnotherVersionIsRefused() {
        val got = Cli(cmd, Stub { Ran(0, """{"snapshotVersion": 2}""", "") }).loadSnapshot("/r")
        assertEquals(Loaded.Error("snapshot version 2; the plugin reads 1"), got)
    }

    @Test
    fun failuresAndBadJson() {
        assertEquals(Loaded.Error("boom"), Cli(cmd, Stub { Ran(1, "", " boom\n") }).loadBudget("/r"))
        assertEquals(Loaded.Error("audit exited 3"), Cli(cmd, Stub { Ran(3, "", "") }).loadBudget("/r"))
        assertEquals(Loaded.Error("review queue printed no JSON"), Cli(cmd, Stub { Ran(0, "{nope", "") }).loadQueue("/r"))
    }

    @Test
    fun actPassesTheRevisionsItWasGiven() {
        val stub = Stub { Ran(0, "alpha: pause\n", "") }
        val revisions = Revisions("reg1", mapOf("alpha" to "tasks1"))
        val done = Cli(cmd, stub).runAct("/r", "alpha", Confirm("unclaim", "T1"), revisions)
        assertEquals("alpha: pause", done.line)
        assertEquals(false, done.refused)
        Cli(cmd, stub).runAct("/r", "beta", Confirm("pause"), revisions)
        assertEquals(
            listOf(
                cmd + listOf("act", "unclaim", "-w", "alpha", "--task", "T1", "--expect-registry", "reg1", "--expect-tasks", "tasks1"),
                cmd + listOf("act", "pause", "-w", "beta", "--expect-registry", "reg1"),
            ),
            stub.calls.map { it.first },
        )
    }

    @Test
    fun aRefusalIsShownAsGiven() {
        val done = Cli(cmd, Stub { Ran(1, "", "stale: the registry moved\n") })
            .runAct("/r", "alpha", Confirm("pause"), Revisions("r", mapOf()))
        assertEquals("stale: the registry moved", done.line)
        assertTrue(done.refused)
    }
}
