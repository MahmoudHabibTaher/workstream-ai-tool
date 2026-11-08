// Every call the plugin makes outside itself, all to the `ws` CLI, which stays the only source of
// truth: the plugin arranges what it returns and writes only through `ws act`. It follows
// ui/vscode/src/cli.ts. Apart from the launcher, this is the only file that starts a process.
package dev.workstream.jetbrains

import com.google.gson.JsonElement
import com.google.gson.JsonObject
import com.google.gson.JsonParseException
import com.google.gson.JsonParser
import com.intellij.execution.ExecutionException
import com.intellij.execution.configurations.GeneralCommandLine
import com.intellij.execution.process.CapturingProcessHandler
import com.intellij.openapi.application.ApplicationManager
import dev.workstream.jetbrains.logic.Acted
import dev.workstream.jetbrains.logic.Confirm
import dev.workstream.jetbrains.logic.Loaded
import dev.workstream.jetbrains.logic.Ran
import dev.workstream.jetbrains.logic.Revisions
import dev.workstream.jetbrains.logic.Rooted
import dev.workstream.jetbrains.logic.Run
import dev.workstream.jetbrains.logic.Side
import dev.workstream.jetbrains.logic.TIMEOUT_MS
import dev.workstream.jetbrains.logic.notAProject
import dev.workstream.jetbrains.logic.noWs
import java.io.File
import java.nio.charset.StandardCharsets

/**
 * Runs a command the way an IDE started from the Dock must (plan T3): with the login shell's
 * environment, since the IDE's own PATH may not hold `ws`, git's optional locks off, as `ws serve`
 * runs, and a 60-second limit. It refuses the EDT: a snapshot takes about 0.4 s.
 */
object ProcessRun : Run {
    override fun run(argv: List<String>, cwd: String): Ran {
        check(ApplicationManager.getApplication()?.isDispatchThread != true) { "ws runs off the EDT" }
        if (!File(cwd).isDirectory) return Ran(-1, "", "$cwd is not a folder")
        val line = GeneralCommandLine(argv)
            .withWorkDirectory(cwd)
            .withParentEnvironmentType(GeneralCommandLine.ParentEnvironmentType.CONSOLE)
            .withEnvironment("GIT_OPTIONAL_LOCKS", "0")
            .withCharset(StandardCharsets.UTF_8)
        val handler = try {
            CapturingProcessHandler(line)
        } catch (e: ExecutionException) {
            return Ran(127, "", e.message ?: "", missing = true)
        }
        val out = handler.runProcess(TIMEOUT_MS.toInt(), true)
        if (out.isTimeout) return Ran(-1, out.stdout, out.stderr.ifBlank { "timed out after ${TIMEOUT_MS / 1000}s" })
        return Ran(out.exitCode, out.stdout, out.stderr)
    }
}

class Cli(command: List<String>, private val run: Run = ProcessRun) {
    val command: List<String> = command.ifEmpty { listOf("ws") }

    private fun ws(args: List<String>, cwd: String): Ran = run.run(command + args, cwd)

    private fun failed(what: String, ran: Ran): String =
        if (ran.missing) noWs(command) else ran.stderr.trim().ifEmpty { "$what exited ${ran.exitCode}" }

    private fun parsed(what: String, ran: Ran): Loaded<JsonElement> {
        if (ran.exitCode != 0) return Loaded.Error(failed(what, ran))
        return try {
            Loaded.Value(JsonParser.parseString(ran.stdout))
        } catch (_: JsonParseException) {
            Loaded.Error("$what printed no JSON")
        }
    }

    /**
     * `ws root` from the project's folder: a task's worktree still finds the checkout that holds
     * the integration branch. A missing `ws` and a folder that isn't a project are both problems.
     */
    fun resolveRoot(folder: String): Rooted {
        val ran = ws(listOf("root"), folder)
        if (ran.missing) return Rooted.Problem(noWs(command), missing = true)
        val root = ran.stdout.trim()
        if (ran.exitCode != 0 || root.isEmpty()) return Rooted.Problem(notAProject(folder), missing = false)
        return Rooted.Root(root)
    }

    /** Runs at the root, so a worktree's project still reads the integration branch's files. */
    fun loadSnapshot(root: String, id: String? = null): Loaded<JsonObject> {
        val args = listOf("snapshot") + (if (id != null) listOf("-w", id) else listOf())
        return when (val got = parsed("snapshot", ws(args, root))) {
            is Loaded.Error -> got
            is Loaded.Value -> {
                val snap = got.value as? JsonObject ?: return Loaded.Error("snapshot printed no object")
                val version = snap.get("snapshotVersion")
                if (version == null || !version.isJsonPrimitive || version.asString != "1") {
                    Loaded.Error("snapshot version ${version ?: "missing"}; the plugin reads 1")
                } else {
                    Loaded.Value(snap)
                }
            }
        }
    }

    /** One task's review data: `checks` adds the gates, `file` adds that file's capped hunks. */
    fun loadReview(root: String, wsId: String, task: String, checks: Boolean = false, file: String? = null): Loaded<JsonElement> {
        val args = listOf("review", task, "-w", wsId) + (if (checks) listOf("--checks") else listOf()) + (if (file != null) listOf("--file", file) else listOf())
        return parsed("review", ws(args, root))
    }

    /** One file of a task's diffstat on one side; the CLI works out a branch's merge base. */
    fun loadShow(root: String, wsId: String, task: String, path: String, side: Side): Loaded<JsonElement> {
        val args = listOf("review", task, "-w", wsId, "--show", path, "--side", side.word)
        return parsed("review --show", ws(args, root))
    }

    /** What can be reviewed across the open workstreams. */
    fun loadQueue(root: String): Loaded<JsonElement> = parsed("review queue", ws(listOf("review", "--queue"), root))

    fun loadBudget(root: String): Loaded<JsonElement> = parsed("audit", ws(listOf("audit", "context", "--json"), root))

    /**
     * The plugin's only write: `ws act` refuses, writes and commits in one call, against the
     * revisions of the snapshot the person saw. A refusal is its stderr, shown as given.
     */
    fun runAct(root: String, wsId: String, confirm: Confirm, revisions: Revisions): Acted {
        val args = mutableListOf("act", confirm.action, "-w", wsId)
        if (confirm.task != null) args.addAll(listOf("--task", confirm.task))
        args.addAll(listOf("--expect-registry", revisions.registry))
        val tasks = revisions.tasks[wsId]
        if (tasks != null) args.addAll(listOf("--expect-tasks", tasks))
        val ran = ws(args, root)
        if (ran.exitCode == 0) return Acted(ran.stdout.trim(), refused = false)
        return Acted(failed("act", ran), refused = true)
    }

    companion object {
        fun fromSettings(run: Run = ProcessRun): Cli = Cli(WsSettings.getInstance().wsCommand, run)
    }
}
