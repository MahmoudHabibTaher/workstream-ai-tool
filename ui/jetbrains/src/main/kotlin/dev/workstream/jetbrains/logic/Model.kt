// Plain Kotlin: the shapes Cli.kt passes around and the lines it says when ws can't answer. Nothing
// under logic/ imports the platform, so its JUnit tests need no IDE.
package dev.workstream.jetbrains.logic

const val SETTING = "Settings | Tools | Workstreams | ws command"
const val TIMEOUT_MS = 60_000L

/** One finished call: `missing` means the command itself didn't start. */
data class Ran(val exitCode: Int, val stdout: String, val stderr: String, val missing: Boolean = false)

/** Runs `argv` (the whole command, wsCommand first) in `cwd`, never through a shell. */
fun interface Run {
    fun run(argv: List<String>, cwd: String): Ran
}

data class Revisions(val registry: String, val tasks: Map<String, String>)

data class Confirm(val action: String, val task: String? = null)

enum class Side(val word: String) { OLD("old"), NEW("new") }

sealed interface Loaded<out T> {
    data class Value<T>(val value: T) : Loaded<T>
    data class Error(val error: String) : Loaded<Nothing>
}

sealed interface Rooted {
    data class Root(val path: String) : Rooted
    data class Problem(val message: String, val missing: Boolean) : Rooted
}

data class Acted(val line: String, val refused: Boolean)

fun noWs(command: List<String>): String =
    "The ws CLI did not start (${command.joinToString(" ")}). Install it, or set $SETTING to the command that runs it."

fun notAProject(folder: String): String =
    "$folder is not a workstream project (`ws init` sets one up); nothing opened."
