// The Review queue as plain data, ported from ui/vscode/src/logic/review.ts: the queue `ws review
// --queue` printed, branch work first, then landed work, and under each task what `ws review
// --checks` said about it. ReviewView.kt turns these into tree nodes; nothing here imports the
// platform, so JUnit covers it. It arranges what the CLI printed and decides nothing.
package dev.workstream.jetbrains.logic

/** One row of `ws review --queue`. */
data class Entry(
    val workstream: String,
    val task: String,
    val state: String,
    val title: String? = null,
    val status: String? = null,
    val revision: String? = null,
    val files: Int = 0,
    val added: Int = 0,
    val removed: Int = 0,
    val hasEvidence: Boolean = false,
)

data class Item(val n: Int, val item: String, val proof: String)

data class Checks(
    val state: String,
    val commit: String? = null,
    val gates: List<Gate> = listOf(),
    /** Null when the task has no evidence file yet. */
    val evidenceText: String? = null,
    val evidenceStatus: String? = null,
    val reason: String? = null,
    val items: List<Item> = listOf(),
)

/** One diffstat entry: `added` and `removed` are null for a binary file. */
data class FileStat(val path: String, val added: Int?, val removed: Int?)

/** `ws review <task> --checks`: `evidence` is the landed evidence file's path, when it exists. */
data class Review(
    val task: String,
    val evidence: String?,
    val range: Range,
    val files: List<FileStat>,
    val checks: Checks? = null,
    val error: String? = null,
)

/**
 * `ws review <task> --show <path> --side <side>`: the file at `rev`. `text` is null when the file
 * isn't on that side, or when `binary` is true. A branch's old side is its merge base, which the
 * CLI works out.
 */
data class ShowSide(val path: String, val side: String, val rev: String, val text: String?, val binary: Boolean)

val GROUPS = listOf("branch" to "On a branch", "landed" to "Landed")

/** A node is the same node across reloads when its id is, as the Registry's are. */
sealed class ReviewNode(val id: String) {
    final override fun equals(other: Any?): Boolean = other is ReviewNode && other.javaClass == javaClass && other.id == id
    final override fun hashCode(): Int = id.hashCode()
    override fun toString(): String = "${javaClass.simpleName}($id)"
}

class GroupNode(id: String, val state: String, val label: String, val entries: List<Entry>) : ReviewNode(id)
class EntryNode(id: String, val entry: Entry) : ReviewNode(id)
class GatesNode(id: String, val text: String, val level: String, val gates: List<Gate>) : ReviewNode(id)
class GateNode(id: String, val gate: Gate) : ReviewNode(id)
class ItemsNode(id: String, val items: List<Item>) : ReviewNode(id)
class ItemNode(id: String, val item: Item) : ReviewNode(id)

/** `text` is the evidence `--checks` read, which a branch task's opens; `path` is a landed one's file. */
class EvidenceNode(id: String, val ws: String, val task: String, val path: String?, val onBranch: Boolean, val text: String) : ReviewNode(id)
class FilesNode(id: String, val ws: String, val task: String, val files: List<FileStat>) : ReviewNode(id)
class FileNode(id: String, val ws: String, val task: String, val file: FileStat) : ReviewNode(id)
class NoteNode(id: String, val text: String, val error: Boolean) : ReviewNode(id)

private fun key(vararg parts: Any): String = (listOf<Any>("review") + parts).joinToString("\u001f")

/** Branch work first, then landed work, each in the CLI's order; an empty group is left out. */
fun queueNodes(entries: List<Entry>): List<ReviewNode> {
    val found = GROUPS.mapNotNull { (state, label) ->
        val inIt = entries.filter { it.state == state }
        if (inIt.isEmpty()) null else GroupNode(key(state), state, label, inIt)
    }
    return found.ifEmpty { listOf(NoteNode(key("empty"), "Nothing to review.", false)) }
}

fun groupChildren(node: GroupNode): List<ReviewNode> = node.entries.map { EntryNode(key(it.workstream, it.task), it) }

/** Under one task, from its `--checks` review: the range, the gates, the acceptance with its proof, the evidence, then the files. */
fun entryChildren(node: EntryNode, review: Review): List<ReviewNode> {
    val ws = node.entry.workstream
    val task = node.entry.task
    fun id(part: String) = key(ws, task, part)
    val found = mutableListOf<ReviewNode>(NoteNode(id("range"), rangeLine(review.range), false))
    if (review.error != null) found += NoteNode(id("error"), review.error, true)
    val checks = review.checks
    if (checks != null) {
        found += when (checks.state) {
            "landed" -> NoteNode(id("gates"), "Landed as ${(checks.commit ?: "").take(10)}. Its gates ran when it landed.", false)
            "none" -> NoteNode(id("gates"), "Not started, so nothing has been checked.", false)
            else -> gateSummary(checks.gates).let { GatesNode(id("gates"), it.text, it.kind, checks.gates) }
        }
        if (checks.evidenceStatus == "blocked") found += NoteNode(id("blocked"), "Blocked: ${checks.reason ?: ""}", true)
        found += if (checks.items.isNotEmpty()) ItemsNode(id("items"), checks.items)
        else NoteNode(id("items"), "This task lists no acceptance items.", false)
        found += if (checks.evidenceText == null) NoteNode(id("evidence"), "No evidence file yet.", false)
        else EvidenceNode(id("evidence"), ws, task, review.evidence, checks.state == "branch", checks.evidenceText)
    }
    if (review.files.isNotEmpty()) found += FilesNode(id("files"), ws, task, review.files)
    return found
}

fun gateChildren(node: GatesNode): List<ReviewNode> = node.gates.mapIndexed { i, gate -> GateNode("${node.id}\u001f$i", gate) }

fun itemChildren(node: ItemsNode): List<ReviewNode> = node.items.map { ItemNode("${node.id}\u001f${it.n}", it) }

fun fileChildren(node: FilesNode): List<ReviewNode> = node.files.map { FileNode("${node.id}\u001f${it.path}", node.ws, node.task, it) }

const val NOTHING_QUOTED = "Nothing quoted."

fun gateMark(gate: Gate): String = if (gate.ok) "ok" else if (gate.blocking) "stop" else "warned"

fun entryDescription(entry: Entry): String {
    val files = "${entry.files} file${if (entry.files == 1) "" else "s"} +${entry.added} −${entry.removed}"
    return (listOf(entry.workstream, files) + (if (entry.hasEvidence) listOf() else listOf("no evidence"))).joinToString(" · ")
}

/** What a review node shows: label, description and tooltip. Every string here is plain text. */
fun reviewShown(node: ReviewNode): Shown = when (node) {
    is GroupNode -> Shown(node.label, node.entries.size.toString(), collapsible = true)
    is EntryNode -> {
        val e = node.entry
        val label = if (!e.title.isNullOrEmpty()) "${e.task} ${e.title}" else e.task
        Shown(label, entryDescription(e), listOf(Section(lines = listOf(label, entryDescription(e)))), collapsible = true)
    }
    is GatesNode -> Shown(node.text, collapsible = true)
    is GateNode -> {
        val detail = if (!node.gate.ok && !node.gate.detail.isNullOrEmpty()) node.gate.detail else ""
        Shown(node.gate.name, detail, if (detail.isEmpty()) listOf() else listOf(Section(lines = listOf(node.gate.name, detail))))
    }
    is ItemsNode -> Shown("Acceptance and proof", "${node.items.count { it.proof.isNotEmpty() }}/${node.items.size} quoted", collapsible = true)
    is ItemNode -> {
        val proof = node.item.proof.ifEmpty { NOTHING_QUOTED }
        Shown("${node.item.n}. ${node.item.item}", proof, listOf(Section("Acceptance", listOf(node.item.item)), Section("Proof", listOf(proof))))
    }
    is EvidenceNode -> Shown("Evidence", if (node.onBranch) "from the branch" else "")
    is FilesNode -> Shown("Files", node.files.size.toString(), collapsible = true)
    is FileNode -> Shown(node.file.path, statLine(node.file.added, node.file.removed))
    is NoteNode -> Shown(node.text)
}

/** What a diff is called: the path and the range it compares. */
fun diffTitle(path: String, task: String, oldRev: String, newRev: String): String =
    "$path ($task: ${oldRev.take(10)} ↔ ${newRev.take(10)})"

/** One side's title in the diff viewer: which side, and the revision `--show` read it at. */
fun sideTitle(side: ShowSide): String = "${side.side} ${side.rev.take(10)}"

fun binaryLine(path: String): String = "$path is binary, so no diff opens."

/** What opening a file comes to, from its two `--show` answers: a line to say, or both sides. */
sealed interface Opening {
    data class Say(val text: String, val error: Boolean) : Opening
    data class Sides(val old: ShowSide, val new: ShowSide) : Opening
}

/** A failure says itself; a binary side opens nothing and says so; otherwise both sides open. */
fun opening(path: String, old: Loaded<ShowSide>, new: Loaded<ShowSide>): Opening {
    if (old is Loaded.Error) return Opening.Say(old.error, true)
    if (new is Loaded.Error) return Opening.Say(new.error, true)
    val o = (old as Loaded.Value).value
    val n = (new as Loaded.Value).value
    if (o.binary || n.binary) return Opening.Say(binaryLine(path), false)
    return Opening.Sides(o, n)
}
