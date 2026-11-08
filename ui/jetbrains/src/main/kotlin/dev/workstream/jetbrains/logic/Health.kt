// Health and Budget as plain data, ported from ui/vscode/src/logic/health.ts: the snapshot's
// `health` findings grouped by level, what each one offers, and `ws audit context --json`'s rows.
// Also which error findings are new to this session (plan T12). HealthView.kt turns these into
// tree nodes; nothing here imports the platform, so JUnit covers it. It arranges what the CLI
// printed and decides nothing.
package dev.workstream.jetbrains.logic

import java.util.Locale

val LEVELS = listOf("error" to "Errors", "warning" to "Warnings")

/** A node is the same node across reloads when its id is, as the Registry's are. */
sealed class HealthNode(val id: String) {
    final override fun equals(other: Any?): Boolean = other is HealthNode && other.javaClass == javaClass && other.id == id
    final override fun hashCode(): Int = id.hashCode()
    override fun toString(): String = "${javaClass.simpleName}($id)"
}

class LevelNode(id: String, val level: String, val label: String, val findings: List<FindingNode>) : HealthNode(id)

/** A finding keeps the revisions of the snapshot it came from, which its write pins (plan T8), and the writes it offers. */
class FindingNode(id: String, val finding: Finding, val writes: List<String>, val revisions: Revisions?) : HealthNode(id)
class HealthNote(id: String, val text: String, val error: Boolean) : HealthNode(id)

private fun key(vararg parts: Any?): String = (listOf<Any?>("health") + parts).joinToString("\u001f") { it?.toString() ?: "" }

/** The writes a finding's `actions` list that the plugin knows, in menu order, without repeats. */
fun findingWrites(finding: Finding): List<String> = WRITES.filter { w -> finding.actions.any { it.action == w } }

/** The workstream and task a finding's write is for: the first of its offers with that action. */
fun offerOf(finding: Finding, action: String): Offer? = finding.actions.firstOrNull { it.action == action }

fun findingNodes(findings: List<Finding>, revisions: Revisions?): List<FindingNode> = findings.mapIndexed { i, f ->
    FindingNode(key(i, f.kind, f.workstream, f.task, f.message), f, findingWrites(f), revisions)
}

/**
 * The snapshot's git error first, when it has one, then errors, warnings and any other level in
 * the order it first came, each in the CLI's order. An empty level is left out, and no findings
 * says so.
 */
fun healthNodes(findings: List<Finding>, revisions: Revisions?, gitError: String? = null): List<HealthNode> {
    val found = mutableListOf<HealthNode>()
    if (!gitError.isNullOrEmpty()) found += HealthNote(key("git"), gitError, true)
    val all = findingNodes(findings, revisions)
    val levels = LEVELS.toMutableList()
    for (node in all) if (levels.none { it.first == node.finding.level }) levels += node.finding.level to node.finding.level
    for ((level, label) in levels) {
        val inIt = all.filter { it.finding.level == level }
        if (inIt.isNotEmpty()) found += LevelNode(key("level", level), level, label, inIt)
    }
    if (all.isEmpty()) found += HealthNote(key("none"), "Nothing to report.", false)
    return found
}

fun levelChildren(node: LevelNode): List<HealthNode> = node.findings

fun findingLabel(finding: Finding): String = finding.message?.ifEmpty { null } ?: finding.kind?.ifEmpty { null } ?: finding.level

fun findingDescription(finding: Finding): String {
    val where = listOfNotNull(finding.workstream, finding.task).filter { it.isNotEmpty() }.joinToString(" ")
    return listOfNotNull(finding.kind, where).filter { it.isNotEmpty() }.joinToString(" · ")
}

/** What a health node shows: label, description and tooltip. Every string here is plain text. */
fun healthShown(node: HealthNode): Shown = when (node) {
    is LevelNode -> Shown(node.label, node.findings.size.toString(), collapsible = true)
    is FindingNode -> {
        val f = node.finding
        val description = findingDescription(f)
        Shown(findingLabel(f), description,
              listOf(Section(lines = listOf(findingLabel(f))), Section(lines = listOf(listOf(f.level, description).filter { it.isNotEmpty() }.joinToString(" · ")))))
    }
    is HealthNote -> Shown(node.text)
}

/** What makes an error finding the same one across reloads (plan T12). */
fun noticeKey(finding: Finding): List<String?> = listOf(finding.kind, finding.workstream, finding.task, finding.message)

/** The error findings whose key isn't in `seen`, in the CLI's order, each once. */
fun newErrors(findings: List<Finding>, seen: Set<List<String?>>): List<Finding> =
    findings.filter { it.level == "error" && noticeKey(it) !in seen }.distinctBy(::noticeKey)

/** One notification's body for a reload's new error findings; null when there are none. */
fun noticeLine(found: List<Finding>): String? = when (found.size) {
    0 -> null
    1 -> "Workstreams error: ${findingLabel(found[0])}"
    else -> "${found.size} new workstream errors. The first: ${findingLabel(found[0])}"
}

/** One row of `ws audit context --json`: a role's tokens against its limit. */
data class BudgetRow(val role: String, val tokens: Int, val budget: Int, val ok: Boolean)

sealed class BudgetNode(val id: String) {
    final override fun equals(other: Any?): Boolean = other is BudgetNode && other.javaClass == javaClass && other.id == id
    final override fun hashCode(): Int = id.hashCode()
    override fun toString(): String = "${javaClass.simpleName}($id)"
}

class RowNode(id: String, val row: BudgetRow) : BudgetNode(id)
class BudgetNote(id: String, val text: String, val error: Boolean) : BudgetNode(id)

fun budgetNodes(rows: List<BudgetRow>): List<BudgetNode> =
    if (rows.isEmpty()) listOf(BudgetNote("budget\u001fnone", "No roles measured.", false))
    else rows.map { RowNode("budget\u001f${it.role}", it) }

fun percentOf(row: BudgetRow): Int = if (row.budget > 0) Math.round(row.tokens * 100.0 / row.budget).toInt() else 0

private fun grouped(n: Int): String = String.format(Locale.US, "%,d", n)

fun budgetShown(node: BudgetNode): Shown = when (node) {
    is RowNode -> {
        val row = node.row
        val description = listOf("${grouped(row.tokens)} / ${grouped(row.budget)}", "${percentOf(row)}%", if (row.ok) "" else "over")
            .filter { it.isNotEmpty() }.joinToString(" · ")
        Shown(row.role, description, listOf(Section(lines = listOf(row.role)),
              Section(lines = listOf("${row.tokens} of ${row.budget} tokens, ${if (row.ok) "within its limit" else "over its limit"}"))))
    }
    is BudgetNote -> Shown(node.text)
}
