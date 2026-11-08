// Pure helpers ported from ui/vscode/src/logic/format.ts, with the same cases in their tests. They
// arrange what the snapshot says and decide nothing: a rule about what may happen belongs to the CLI.
package dev.workstream.jetbrains.logic

import java.time.Instant

val CLOSED_STATUSES = setOf("done", "abandoned")
val DOC_NAMES = listOf("plan", "progress", "decisions", "handoff")

data class Wave(
    val state: String,
    val phase: Int? = null,
    val ids: List<String> = listOf(),
    val open: List<String> = listOf(),
    val leftovers: List<String> = listOf(),
)

data class VerifyCommand(val label: String, val command: String)

data class Task(
    val id: String,
    val phase: Int = 1,
    val priority: Int = 10,
    val status: String = "todo",
    val blockedBy: List<String> = listOf(),
    val title: String? = null,
    val summary: String? = null,
    val mode: String? = null,
    val needsUserDecision: Boolean = false,
    val startedAt: String? = null,
    val blockedReason: String? = null,
    val acceptanceText: List<String> = listOf(),
    val verifyCommands: List<VerifyCommand> = listOf(),
)

data class Progress(val done: Int, val total: Int)

data class Row(
    val id: String,
    val status: String,
    val title: String? = null,
    val summary: String? = null,
    val progress: Progress? = null,
    val dependsOn: List<String> = listOf(),
    /** The status writes `ws act` would accept for this row now, as the snapshot drew them. */
    val actions: List<String> = listOf(),
    /** What the row can launch, in the snapshot's order, each prompt already filled in. */
    val launches: List<LaunchOffer> = listOf(),
)

data class Finding(
    val level: String,
    val workstream: String?,
    val task: String? = null,
    val message: String? = null,
    /** The writes this finding offers, each naming the workstream and task it is for. */
    val actions: List<Offer> = listOf(),
    /** The CLI's name for what was found, such as `stale-claim`. */
    val kind: String? = null,
)

data class Badge(val text: String, val kind: String)

fun waveLine(wave: Wave?): String {
    if (wave == null) return ""
    if (wave.state == "finished") return "Queue finished"
    if (wave.state == "stuck") return "Stuck: ${wave.open.size} open, none actionable"
    val leftovers = if (wave.leftovers.isNotEmpty()) " · ${wave.leftovers.size} left over" else ""
    return "Phase ${wave.phase}: ${wave.ids.size} ready$leftovers"
}

/** How long ago `startedAt` was, at `now` in epoch milliseconds. */
fun ageOf(startedAt: String, now: Long): String {
    val minutes = maxOf(0L, Math.floorDiv(now - Instant.parse(startedAt).toEpochMilli(), 60_000L))
    if (minutes < 60) return "${minutes}m"
    val hours = minutes / 60
    return if (hours < 48) "${hours}h" else "${hours / 24}d"
}

fun badgesOf(task: Task, tasks: List<Task>, waveIds: List<String>?, now: Long): List<Badge> {
    val statusOf = tasks.associate { it.id to it.status }
    val waitsOn = task.blockedBy.filter { statusOf[it] != "done" }
    val badges = mutableListOf<Badge>()
    if (waveIds != null && task.id in waveIds) badges += Badge("★ ready", "good")
    if (task.mode == "foreground") badges += Badge("foreground", "")
    if (task.needsUserDecision) badges += Badge("needs decision", "warn")
    if (task.status == "todo" && waitsOn.isNotEmpty()) badges += Badge("waits on ${waitsOn.joinToString(", ")}", "")
    if (task.status == "in-progress" && task.startedAt != null) badges += Badge("claimed ${ageOf(task.startedAt, now)}", "accent")
    return badges
}

fun blockedLine(task: Task): String = if (task.blockedReason.isNullOrEmpty()) "" else "Blocked: ${task.blockedReason}"

data class Lane(val phase: Int, val tasks: List<Task>)

fun lanes(tasks: List<Task>): List<Lane> =
    tasks.map { it.phase }.distinct().sorted().map { phase ->
        Lane(phase, tasks.filter { it.phase == phase }.sortedBy { it.priority })
    }

data class Split<T>(val open: List<T>, val closed: List<T>)

fun <T> splitRows(registry: List<T>, status: (T) -> String): Split<T> =
    Split(registry.filter { status(it) !in CLOSED_STATUSES }, registry.filter { status(it) in CLOSED_STATUSES })

fun splitRows(registry: List<Row>): Split<Row> = splitRows(registry) { it.status }

fun errorCount(health: List<Finding>, id: String): Int = health.count { it.level == "error" && it.workstream == id }

/** A task's review range, as `ws review` printed it: `none`, `branch`, `commit` or `merge`. */
data class Range(val kind: String, val from: String? = null, val to: String? = null)

/** One gate `ws review --checks` ran: a failing blocking gate would stop the landing. */
data class Gate(val name: String, val ok: Boolean, val blocking: Boolean, val detail: String? = null)

private val FULL_SHA = Regex("^[0-9a-f]{40}")

fun rangeLine(range: Range): String {
    if (range.kind == "none") return "No diff: this task has no commit or branch yet."
    fun short(rev: String?): String {
        val r = rev ?: ""
        return if (FULL_SHA.containsMatchIn(r)) r.take(10) + r.drop(40) else r
    }
    return "${range.kind}: ${short(range.from)}${if (range.kind == "branch") "..." else ".."}${short(range.to)}"
}

fun statLine(added: Int?, removed: Int?): String {
    if (added == null || removed == null) return "binary"
    return "+$added −$removed"
}

/** What the gates add up to, in a line. settle decides; this says what it would say. */
fun gateSummary(gates: List<Gate>): Badge {
    val stopping = gates.count { !it.ok && it.blocking }
    val warnings = gates.count { !it.ok && !it.blocking }
    if (stopping > 0) return Badge("$stopping check${if (stopping == 1) "" else "s"} would stop this landing", "bad")
    if (warnings > 0) return Badge("Would land, with $warnings warning${if (warnings == 1) "" else "s"}", "warn")
    return Badge("Every check passes", "good")
}
