// The Registry tree as plain data, ported from ui/vscode/src/logic/registry.ts: which nodes sit
// under which, and the text each one shows. RegistryView.kt turns these into tree nodes; nothing
// here imports the platform, so JUnit covers it.
package dev.workstream.jetbrains.logic

/** A workstream's own snapshot (`ws snapshot -w <id>`): its tasks, wave and document paths. */
data class WsView(val tasks: List<Task>, val wave: Wave?, val docs: Map<String, String>)

/** One `refresh` entry of the snapshot: a path whose change means the snapshot may have changed. */
data class Watch(val path: String, val recursive: Boolean)

/** A tooltip as sections: each heading is the plugin's own constant, each line is repo text. */
data class Section(val heading: String? = null, val lines: List<String>)

/**
 * A node is the same node across reloads when its id is: the tree keeps it expanded and redraws
 * it from the newest copy.
 */
sealed class Node(val id: String) {
    final override fun equals(other: Any?): Boolean = other is Node && other.javaClass == javaClass && other.id == id
    final override fun hashCode(): Int = id.hashCode()
    override fun toString(): String = "${javaClass.simpleName}($id)"
}

class WorkstreamNode(id: String, val row: Row, val errors: Int) : Node(id)
class WaveNode(id: String, val text: String) : Node(id)
class PhaseNode(id: String, val ws: String, val phase: Int, val tasks: List<Task>, val all: List<Task>, val wave: Wave?) : Node(id)
class TaskNode(id: String, val ws: String, val task: Task, val badges: List<String>) : Node(id)
class DocumentsNode(id: String, val ws: String, val docs: List<Pair<String, String>>) : Node(id)
class DocumentNode(id: String, val ws: String, val name: String, val path: String) : Node(id)
class MessageNode(id: String, val text: String, val error: Boolean) : Node(id)

val DOC_LABELS = mapOf("plan" to "Plan", "progress" to "Progress", "decisions" to "Decisions", "handoff" to "Handoff")

private fun key(vararg parts: Any): String = parts.joinToString("\u001f")

/** The registry's rows in registry order, open ones first; closed ones only with Show done. */
fun workstreams(rows: List<Row>, health: List<Finding>, showDone: Boolean): List<Node> {
    val (open, closed) = splitRows(rows)
    val shown = if (showDone) open + closed else open
    return shown.map { WorkstreamNode(key(it.id), it, errorCount(health, it.id)) }
}

/** Under a workstream: its wave line, its phases in order, then its documents. */
fun workstreamChildren(ws: String, view: WsView): List<Node> {
    val found = mutableListOf<Node>()
    val line = waveLine(view.wave)
    if (line.isNotEmpty()) found += WaveNode(key(ws, "wave"), line)
    for (lane in lanes(view.tasks)) found += PhaseNode(key(ws, "phase", lane.phase), ws, lane.phase, lane.tasks, view.tasks, view.wave)
    val docs = DOC_NAMES.mapNotNull { name -> view.docs[name]?.let { name to it } }
    if (docs.isNotEmpty()) found += DocumentsNode(key(ws, "documents"), ws, docs)
    return found
}

/** A phase's tasks, already in priority order, each with its badges. */
fun phaseChildren(node: PhaseNode, now: Long): List<Node> = node.tasks.map { task ->
    TaskNode(key(node.ws, "task", task.id), node.ws, task, badgesOf(task, node.all, node.wave?.ids, now).map { it.text })
}

fun documentChildren(node: DocumentsNode): List<Node> =
    node.docs.map { (name, path) -> DocumentNode(key(node.ws, "doc", name), node.ws, name, path) }

data class Shown(val label: String, val description: String = "", val tip: List<Section> = listOf(), val collapsible: Boolean = false)

private fun plural(n: Int, one: String) = "$n $one${if (n == 1) "" else "s"}"

fun rowDescription(row: Row, errors: Int): String {
    val progress = row.progress?.let { "${it.done}/${it.total}" } ?: ""
    return listOf(row.status, progress, if (errors > 0) plural(errors, "error") else "").filter { it.isNotEmpty() }.joinToString(" · ")
}

/** What a node shows: label, description and tooltip. Every string here is plain text. */
fun shown(node: Node): Shown = when (node) {
    is WorkstreamNode -> {
        val row = node.row
        val tip = mutableListOf(Section(lines = listOf(if (row.title != null) "${row.id}: ${row.title}" else row.id)))
        if (!row.summary.isNullOrEmpty()) tip += Section(lines = listOf(row.summary))
        tip += Section(lines = listOf(rowDescription(row, node.errors)))
        if (row.dependsOn.isNotEmpty()) tip += Section("Depends on", listOf(row.dependsOn.joinToString(", ")))
        Shown(row.id, rowDescription(row, node.errors), tip, collapsible = true)
    }
    is WaveNode -> Shown(node.text)
    is PhaseNode -> Shown("Phase ${node.phase}", "${node.tasks.count { it.status == "done" }}/${node.tasks.size}", collapsible = true)
    is TaskNode -> {
        val task = node.task
        val state = (listOf(task.status) + node.badges).joinToString(" · ")
        val tip = mutableListOf(Section(lines = listOf(if (task.title != null) "${task.id}: ${task.title}" else task.id)))
        tip += Section(lines = listOf(state))
        val blocked = blockedLine(task)
        if (blocked.isNotEmpty()) tip += Section(lines = listOf(blocked))
        if (!task.summary.isNullOrEmpty()) tip += Section(lines = listOf(task.summary))
        if (task.acceptanceText.isNotEmpty()) tip += Section("Acceptance", task.acceptanceText)
        if (task.verifyCommands.isNotEmpty()) {
            tip += Section("Verify", task.verifyCommands.map { if (it.label == it.command) it.command else "${it.label}: ${it.command}" })
        }
        Shown(if (task.title != null) "${task.id} ${task.title}" else task.id, state, tip)
    }
    is DocumentsNode -> Shown("Documents", collapsible = true)
    is DocumentNode -> Shown(DOC_LABELS[node.name] ?: node.name, node.path.split('/', '\\').last())
    is MessageNode -> Shown(node.text)
}

/** The status bar's workstream: the first active row, with its error count. */
fun activeWorkstream(rows: List<Row>, health: List<Finding>): Pair<Row, Int>? =
    rows.firstOrNull { it.status == "active" }?.let { it to errorCount(health, it.id) }

fun statusText(id: String, wave: Wave?, errors: Int): String {
    val line = waveLine(wave)
    return listOf(if (line.isNotEmpty()) "$id: $line" else id, if (errors > 0) plural(errors, "error") else "")
        .filter { it.isNotEmpty() }.joinToString(" · ")
}

/** Whether a changed `path` falls under one of the snapshot's refresh entries. */
fun underRefresh(path: String, watches: List<Watch>): Boolean = watches.any { w ->
    val p = w.path.trimEnd('/')
    path == p || if (w.recursive) path.startsWith("$p/") else path.substringBeforeLast('/') == p
}
