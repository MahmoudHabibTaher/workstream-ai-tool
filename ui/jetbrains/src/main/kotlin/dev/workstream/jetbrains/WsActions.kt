// The Registry's writes and launches (D-ACTIONS), in the trees' popup menu and in Find Action.
// Pause, Resume, Sync and Unclaim are enabled only where the node's row or finding offers them,
// in the Registry or the Health tab, ask first, then write through `ws act` against the revisions
// the node was drawn with (plan T8).
// Run, Coordinate, Close and Abandon come only from the row's `launches` and go to Launcher.
package dev.workstream.jetbrains

import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.DataKey
import com.intellij.openapi.project.DumbAware
import dev.workstream.jetbrains.logic.WorkstreamNode
import dev.workstream.jetbrains.logic.askLine
import dev.workstream.jetbrains.logic.confirmText
import dev.workstream.jetbrains.logic.launchOf
import dev.workstream.jetbrains.logic.launchTitle
import dev.workstream.jetbrains.logic.moved
import dev.workstream.jetbrains.logic.pinnedOf
import dev.workstream.jetbrains.logic.promptOf
import dev.workstream.jetbrains.logic.targetOf

/** The Registry or Health node an action is for: the tree's selection, as the panel provides it. */
val WS_NODE: DataKey<Any> = DataKey.create("dev.workstream.jetbrains.node")

abstract class NodeAction : AnAction(), DumbAware {
    override fun getActionUpdateThread() = ActionUpdateThread.BGT

    protected abstract fun offered(node: Any?): Boolean

    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = e.project != null && offered(e.getData(WS_NODE))
    }
}

/** One write. The handler checks the node again, so a write the snapshot didn't offer never reaches act. */
abstract class ActAction(private val action: String) : NodeAction() {
    override fun offered(node: Any?): Boolean = targetOf(node, action) != null

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val node = e.getData(WS_NODE)
        val target = targetOf(node, action)
        val pinned = pinnedOf(node)
        if (target == null || pinned == null) return Text.notify(project, "$action isn't offered here.", NotificationType.ERROR)
        val (ws, confirm) = target
        // Pinned now, from the snapshot the node was drawn with: whether the view is behind is
        // judged as the dialog opens, since a modal dialog can't redraw.
        val service = Workstreams.of(project)
        val latest = service.snapshot
        val branch = latest?.let(Snapshots::integrationBranch) ?: "the integration branch"
        val behind = moved(pinned, latest?.let(Snapshots::revisions), ws)
        if (!Text.confirm(project, confirmText(ws, action, confirm.task, branch, behind))) return
        service.act(ws, confirm, pinned)
    }
}

class PauseAction : ActAction("pause")
class ResumeAction : ActAction("resume")
class SyncAction : ActAction("sync")
class UnclaimAction : ActAction("unclaim")

/** One launch, from the row's `launches`; one that asks something asks it first. */
abstract class LaunchAction(private val kind: String) : NodeAction() {
    override fun offered(node: Any?): Boolean = launchOf(node, kind) != null

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val node = e.getData(WS_NODE)
        val offer = launchOf(node, kind)
        val root = Workstreams.of(project).root
        if (offer == null || root == null) return Text.notify(project, "$kind isn't offered here.", NotificationType.ERROR)
        val ws = (node as WorkstreamNode).row.id
        val title = launchTitle(kind, ws)
        val answer = offer.ask?.let { ask -> Text.ask(project, title, askLine(ask, title))?.trim()?.ifEmpty { null } ?: return }
        val started = Launcher.launch(project, LaunchRequest(title, promptOf(offer, answer), root))
        Text.notify(project, started.said, NotificationType.INFORMATION)
    }
}

class RunAction : LaunchAction("run")
class CoordinateAction : LaunchAction("coordinate")
class CloseAction : LaunchAction("close")
class AbandonAction : LaunchAction("abandon")
