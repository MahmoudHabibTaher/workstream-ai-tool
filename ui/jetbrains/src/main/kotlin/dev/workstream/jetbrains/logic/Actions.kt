// Which writes and launches a node offers, and what the confirm and the launch say, ported from
// ui/vscode/src/logic/actions.ts and launch.ts. The snapshot decides what is offered: a row's
// `actions`, a finding's `actions` and a row's `launches`. Nothing here holds act's status rule or
// a prompt's text, and `ws act` still decides when a write runs.
package dev.workstream.jetbrains.logic

const val AGENT_SETTING = "Settings | Tools | Workstreams | Agent command"

/** The writes the plugin can ask `ws act` for, in the order a menu shows them. */
val WRITES = listOf("pause", "resume", "sync", "unclaim")

/** One write a finding offers, for a workstream and maybe one of its tasks. */
data class Offer(val action: String, val workstream: String, val task: String? = null)

/** One launch a row offers: its kind, its finished prompt and what it asks the person first. */
data class LaunchOffer(val kind: String, val prompt: String, val ask: String? = null)

private fun offered(found: List<String>): List<String> = WRITES.filter { it in found }

/** A row's writes: its own `actions`, and any a finding offers for the whole row. */
fun rowWrites(row: Row, health: List<Finding>): List<String> =
    offered(row.actions + health.flatMap { it.actions }.filter { it.workstream == row.id && it.task == null }.map { it.action })

/** A task's writes: only what a finding offers for that task, `unclaim` on a stale claim today. */
fun taskWrites(health: List<Finding>, ws: String, task: String): List<String> =
    offered(health.flatMap { it.actions }.filter { it.workstream == ws && it.task == task }.map { it.action })

/** The writes a node offers; only workstream, task and finding nodes offer any. */
fun writesOf(node: Any?): List<String> = when (node) {
    is WorkstreamNode -> node.writes
    is TaskNode -> node.writes
    is FindingNode -> node.writes
    else -> listOf()
}

/** The launch of `kind` a node offers: only a workstream's row offers launches. */
fun launchOf(node: Any?, kind: String): LaunchOffer? = (node as? WorkstreamNode)?.row?.launches?.firstOrNull { it.kind == kind }

/** The workstream a write on this node is for, and the confirm it sends; null where none is offered. */
fun targetOf(node: Any?, action: String): Pair<String, Confirm>? {
    if (action !in writesOf(node)) return null
    return when (node) {
        is WorkstreamNode -> node.row.id to Confirm(action)
        is TaskNode -> node.ws to Confirm(action, node.task.id)
        is FindingNode -> offerOf(node.finding, action)?.let { it.workstream to Confirm(action, it.task) }
        else -> null
    }
}

/** The revisions of the snapshot a node was drawn from: what its write expects. */
fun pinnedOf(node: Any?): Revisions? = when (node) {
    is WorkstreamNode -> node.revisions
    is TaskNode -> node.revisions
    is FindingNode -> node.revisions
    else -> null
}

fun commitLine(ws: String, action: String, task: String?): String = "$ws: $action${if (task != null) " $task" else ""}"

/**
 * Whether what the person saw is behind the latest snapshot the plugin holds: the write will then
 * be refused, and the confirm says so before they answer.
 */
fun moved(pinned: Revisions, latest: Revisions?, ws: String): Boolean {
    if (latest == null) return false
    return latest.registry != pinned.registry || latest.tasks[ws] != pinned.tasks[ws]
}

data class ConfirmText(val title: String, val lines: List<String>)

fun confirmText(ws: String, action: String, task: String?, branch: String, behind: Boolean): ConfirmText {
    val lines = mutableListOf("This commits \"${commitLine(ws, action, task)}\" on $branch.")
    if (behind) lines += "This has changed since the tree drew it, so the write will be refused."
    return ConfirmText("${action.replaceFirstChar { it.uppercase() }} ${task ?: ws}?", lines)
}

fun launchTitle(kind: String, ws: String): String = "${kind.replaceFirstChar { it.uppercase() }} $ws"

/** The question a launch asks first, by the field its offer names. */
fun askLine(ask: String, title: String): String = "Give the $ask for $title. The prompt ends with it."

/** The prompt to send: the offer's own, with the person's answer appended when it asked one. */
fun promptOf(offer: LaunchOffer, answer: String?): String = if (offer.ask != null) offer.prompt + (answer ?: "") else offer.prompt

/**
 * The agent's argv with the prompt as its last argument, started as the Terminal tab's own
 * process, so no shell parses the prompt. Null when no agent command is set.
 */
fun terminalArgv(agent: List<String>, prompt: String): List<String>? {
    if (agent.isEmpty() || agent[0].isBlank()) return null
    return agent + prompt
}

fun terminalLine(argv: List<String>, title: String): String = "Started ${argv[0]} in a Terminal tab: $title"

/** Why a launch went to the clipboard, named so the person knows what to change. */
fun clipboardLine(title: String, prompt: String, terminal: Boolean, agentSet: Boolean): String {
    val why = when {
        !agentSet -> "no agent command is set. Set $AGENT_SETTING to start the agent in a Terminal tab instead."
        !terminal -> "the Terminal plugin is not enabled, so $AGENT_SETTING can't start a tab. Enable it to start the agent instead."
        else -> "the Terminal did not start the agent ($AGENT_SETTING)."
    }
    return "Copied the $title prompt to the clipboard, because $why Prompt: $prompt"
}
