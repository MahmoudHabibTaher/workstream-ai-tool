// The Workstreams tab as plain data: the list's rows, the Tasks table's rows and cells, and the
// task pane's sections. WorkstreamsView.kt draws these; nothing here imports the platform, so
// JUnit covers it. Every fact is one the snapshot gave: nothing here works out a graph fact (plan T3).
package dev.workstream.jetbrains.logic

/** A workstream's own snapshot (`ws snapshot -w <id>`): its tasks, wave and document paths. */
data class WsView(
    val tasks: List<Task>,
    val wave: Wave?,
    val docs: Map<String, String>,
    /** The revisions and health of this snapshot: what its task nodes pin and offer. */
    val revisions: Revisions? = null,
    val health: List<Finding> = listOf(),
    /** The snapshot's `repoRoot`, which a task's `files` are relative to. */
    val root: String? = null,
    /** The workstream's tasks file, as the snapshot's `watch` named it. */
    val tasksFile: String? = null,
)

/** One `refresh` entry of the snapshot: a path whose change means the snapshot may have changed. */
data class Watch(val path: String, val recursive: Boolean)

/** A tooltip as sections: each heading is the plugin's own constant, each line is repo text. */
data class Section(val heading: String? = null, val lines: List<String>)

/**
 * A node is the same node across reloads when its id is: the views keep it selected and redraw
 * it from the newest copy.
 */
sealed class Node(val id: String) {
    final override fun equals(other: Any?): Boolean = other is Node && other.javaClass == javaClass && other.id == id
    final override fun hashCode(): Int = id.hashCode()
    override fun toString(): String = "${javaClass.simpleName}($id)"
}

/** A row of the workstream list. It pins the revisions of the snapshot it was drawn from, for its writes. */
class WorkstreamNode(id: String, val row: Row, val errors: Int, val writes: List<String> = listOf(), val revisions: Revisions? = null) : Node(id)

/** A row of the Tasks table. It pins the revisions of the workstream's snapshot, for its writes. */
class TaskNode(id: String, val ws: String, val task: Task, val badges: List<String>, val writes: List<String> = listOf(), val revisions: Revisions? = null) : Node(id)

val DOC_LABELS = mapOf("plan" to "Plan", "progress" to "Progress", "decisions" to "Decisions", "handoff" to "Handoff")

private fun key(vararg parts: Any): String = parts.joinToString("\u001f")

/**
 * The registry's rows in registry order, open ones first; closed ones only with Show done. Each
 * pins the `revisions` of the snapshot it came from, for its writes.
 */
fun workstreams(rows: List<Row>, health: List<Finding>, showDone: Boolean, revisions: Revisions? = null): List<WorkstreamNode> {
    val (open, closed) = splitRows(rows)
    val shown = if (showDone) open + closed else open
    return shown.map { WorkstreamNode(key(it.id), it, errorCount(health, it.id), rowWrites(it, health), revisions) }
}

private fun plural(n: Int, one: String) = "$n $one${if (n == 1) "" else "s"}"

/** What a list row shows after its id: done/total, status, claimed tasks and errors, each only when there is one. */
fun rowDetails(node: WorkstreamNode): List<String> {
    val row = node.row
    val progress = row.progress
    return listOfNotNull(
        progress?.let { "${it.done}/${it.total}" },
        row.status.ifEmpty { null },
        progress?.inProgress?.takeIf { it > 0 }?.let { "$it claimed" },
        node.errors.takeIf { it > 0 }?.let { plural(it, "error") },
    )
}

/** The workstream's tasks as the table's rows, phase by phase in priority order, each with its badges and writes. */
fun taskRows(ws: String, view: WsView, now: Long): List<TaskNode> = lanes(view.tasks).flatMap { it.tasks }.map { task ->
    TaskNode(key(ws, "task", task.id), ws, task, badgesOf(task, view.wave?.ids, now).map { it.text },
             taskWrites(view.health, ws, task.id), view.revisions)
}

val TASK_COLUMNS = listOf("Status", "ID", "Phase", "Title", "Waiting on")

/** One table row's cells, in TASK_COLUMNS' order. Every cell is plain text. */
fun taskCells(node: TaskNode): List<String> {
    val t = node.task
    return listOf(t.status, t.id, t.phase.toString(), t.title ?: "", t.waitingOn.joinToString(", "))
}

/** One line of the task pane: text, a jump to a task of this table, or a file that opens. */
sealed interface PaneItem {
    data class Line(val text: String) : PaneItem
    data class TaskLink(val id: String) : PaneItem
    data class FileLink(val path: String) : PaneItem
}

/** A section of the task pane: its heading is the plugin's own constant, its items repo text. */
data class PaneSection(val heading: String?, val items: List<PaneItem>)

/** An id is a link only when it names a task the table holds; else it is shown as text. */
private fun ids(ids: List<String>, known: Set<String>): List<PaneItem> =
    ids.map { if (it in known) PaneItem.TaskLink(it) else PaneItem.Line(it) }

/**
 * The task pane, top to bottom: the task, its state, summary, claim and age, what it depends on
 * and unblocks, its files, acceptance, verify commands and notes. A section with nothing to say is
 * left out. `known` is the ids the table holds.
 */
fun taskPane(node: TaskNode, known: Set<String>, now: Long): List<PaneSection> {
    val t = node.task
    val found = mutableListOf(PaneSection(null, listOf(PaneItem.Line(if (t.title != null) "${t.id}: ${t.title}" else t.id))))
    found += PaneSection(null, listOf(PaneItem.Line((listOf(t.status) + node.badges).joinToString(" · "))))
    val blocked = blockedLine(t)
    if (blocked.isNotEmpty()) found += PaneSection(null, listOf(PaneItem.Line(blocked)))
    if (!t.summary.isNullOrEmpty()) found += PaneSection("Summary", listOf(PaneItem.Line(t.summary)))
    if (t.status == "in-progress" && (t.claimedBy != null || t.startedAt != null)) {
        val age = t.startedAt?.let { runCatching { "${ageOf(it, now)} ago" }.getOrNull() ?: it }
        found += PaneSection("Claim", listOf(PaneItem.Line(listOfNotNull(t.claimedBy, age).joinToString(" · "))))
    }
    if (t.blockedBy.isNotEmpty()) found += PaneSection("Depends on", ids(t.blockedBy, known))
    if (t.unblocks.isNotEmpty()) found += PaneSection("Unblocks", ids(t.unblocks, known))
    if (t.files.isNotEmpty()) found += PaneSection("Files", t.files.map { PaneItem.FileLink(it) })
    if (t.acceptanceText.isNotEmpty()) found += PaneSection("Acceptance", t.acceptanceText.map { PaneItem.Line(it) })
    if (t.verifyCommands.isNotEmpty()) {
        found += PaneSection("Verify", t.verifyCommands.map { PaneItem.Line(if (it.label == it.command) it.command else "${it.label}: ${it.command}") })
    }
    if (!t.notes.isNullOrEmpty()) found += PaneSection("Notes", listOf(PaneItem.Line(t.notes)))
    return found
}

/** The workstream's documents the snapshot named, in DOC_NAMES' order, as (label, path). */
fun documents(view: WsView): List<Pair<String, String>> =
    DOC_NAMES.mapNotNull { name -> view.docs[name]?.let { (DOC_LABELS[name] ?: name) to it } }

/** Where a task's `files` entry sits: under the snapshot's repo root, unless it is already absolute. */
fun filePath(root: String?, path: String): String =
    if (root == null || java.io.File(path).isAbsolute) path else java.io.File(root, path).path

/**
 * Where the task's id is written in its tasks file: the offset of `"id": "<id>"`, so the editor
 * opens at it. Null when the text doesn't hold it.
 */
fun taskOffset(text: String, id: String): Int? =
    Regex("\"id\"\\s*:\\s*\"${Regex.escape(id)}\"").find(text)?.range?.first

/** What a node of a view shows; `collapsible` is for the Review and Health trees, which share it. */
data class Shown(val label: String, val description: String = "", val tip: List<Section> = listOf(), val collapsible: Boolean = false)

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
        Shown(row.id, rowDescription(row, node.errors), tip)
    }
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
