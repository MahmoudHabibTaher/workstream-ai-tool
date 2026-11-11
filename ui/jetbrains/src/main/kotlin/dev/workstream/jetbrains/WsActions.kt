// The Registry's writes, launches and documents (D-ACTIONS, D-MENUS), grouped as Run, Workstream,
// Task and Open on the toolbar, under Tools > Workstreams, in the list's, table's and Health tree's
// popup menus and in Find Action; a group with nothing offered hides.
// Pause, Resume, Sync and Unclaim are enabled only where the node's row or finding offers them,
// in the Registry or the Health tab, ask first, then write through `ws act` against the revisions
// the node was drawn with (plan T8).
// Run, Coordinate, Close and Abandon come only from the row's `launches`, open the launch dialog
// (D-DIALOG) and go to Launcher with the target it chose.
package dev.workstream.jetbrains

import com.intellij.notification.NotificationType
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.DataKey
import com.intellij.openapi.actionSystem.DefaultActionGroup
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.fileEditor.OpenFileDescriptor
import com.intellij.openapi.project.DumbAware
import com.intellij.openapi.util.Disposer
import com.intellij.openapi.vfs.LocalFileSystem
import dev.workstream.jetbrains.logic.TaskNode
import dev.workstream.jetbrains.logic.WorkstreamNode
import dev.workstream.jetbrains.logic.WsView
import dev.workstream.jetbrains.logic.taskOffset
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

/** The selected workstream's own snapshot, as the Workstreams tab drew it: what the Open group opens. */
val WS_VIEW: DataKey<WsView> = DataKey.create("dev.workstream.jetbrains.view")

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
        // Run can pin a task of the queue that isn't done; the checks say whether it may start.
        val tasks = if (kind == LaunchDialog.RUN) Workstreams.of(project).cachedView(ws)?.tasks?.filter { it.status != "done" }?.map { it.id } ?: listOf() else listOf()
        val dialog = LaunchDialog(project, LaunchSetup(ws, kind, title, promptOf(offer, answer), root, tasks))
        val choice = try {
            if (!LaunchDialog.show(dialog)) return
            dialog.accepted() ?: return
        } finally {
            Disposer.dispose(dialog.disposable)
        }
        val started = Launcher.launch(project, choice.request, choice.target)
        Text.notify(project, started.said, NotificationType.INFORMATION)
    }
}

class RunAction : LaunchAction("run")
class CoordinateAction : LaunchAction("coordinate")
class CloseAction : LaunchAction("close")
class AbandonAction : LaunchAction("abandon")

/** The Open group's name for the workstream's tasks file, beside the snapshot's `paths` names. */
const val TASKS_DOC = "tasks"

/** Where a view's document of this name is, as its snapshot named it; null where it named none. */
fun docPath(view: WsView?, doc: String): String? = if (doc == TASKS_DOC) view?.tasksFile else view?.docs?.get(doc)

/**
 * Opens one of the selected workstream's files, enabled only where its snapshot named that file.
 * The tasks file opens at the selected task's id when a task is what the person used last.
 */
abstract class OpenAction(private val doc: String) : AnAction(), DumbAware {
    override fun getActionUpdateThread() = ActionUpdateThread.BGT

    override fun update(e: AnActionEvent) {
        e.presentation.isEnabledAndVisible = e.project != null && docPath(e.getData(WS_VIEW), doc) != null
    }

    override fun actionPerformed(e: AnActionEvent) {
        val project = e.project ?: return
        val path = docPath(e.getData(WS_VIEW), doc) ?: return Text.notify(project, "No $doc file is named here.", NotificationType.ERROR)
        val fs = LocalFileSystem.getInstance()
        val file = fs.findFileByPath(path) ?: fs.refreshAndFindFileByPath(path)
            ?: return Text.notify(project, "$path does not exist.", NotificationType.WARNING)
        val task = (e.getData(WS_NODE) as? TaskNode)?.task?.id
        val offset = if (doc == TASKS_DOC && task != null) {
            taskOffset(FileDocumentManager.getInstance().getDocument(file)?.text ?: "", task) ?: 0
        } else 0
        OpenFileDescriptor(project, file, offset).navigate(true)
    }
}

class OpenPlanAction : OpenAction("plan")
class OpenProgressAction : OpenAction("progress")
class OpenDecisionsAction : OpenAction("decisions")
class OpenHandoffAction : OpenAction("handoff")
class OpenTasksAction : OpenAction(TASKS_DOC)

/** A toolbar and menu group that hides itself when nothing in it is offered here. */
class WsGroup : DefaultActionGroup(), DumbAware {
    override fun getActionUpdateThread() = ActionUpdateThread.BGT
    init {
        templatePresentation.isHideGroupIfEmpty = true
    }
}
