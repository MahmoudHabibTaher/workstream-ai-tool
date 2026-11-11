// The status bar's Workstreams widget: the first active workstream's claimed task and its age, or
// its wave line when none is claimed, then its error count (D-MENUS). Clicking it opens the tool window.
package dev.workstream.jetbrains

import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.wm.StatusBar
import com.intellij.openapi.wm.StatusBarWidget
import com.intellij.openapi.wm.StatusBarWidgetFactory
import com.intellij.openapi.wm.ToolWindowManager
import com.intellij.util.Consumer
import dev.workstream.jetbrains.logic.WorkstreamNode
import dev.workstream.jetbrains.logic.activeWorkstream
import dev.workstream.jetbrains.logic.claimedTask
import dev.workstream.jetbrains.logic.shown
import dev.workstream.jetbrains.logic.statusText
import java.awt.Component
import java.awt.event.MouseEvent

const val STATUS_WIDGET = "dev.workstream.jetbrains.status"

class StatusWidgetFactory : StatusBarWidgetFactory {
    override fun getId(): String = STATUS_WIDGET
    override fun getDisplayName(): String = "Workstreams"
    override fun isAvailable(project: Project): Boolean = true
    override fun createWidget(project: Project): StatusBarWidget = StatusWidget(project)
}

class StatusWidget(private val project: Project, private val now: () -> Long = System::currentTimeMillis) :
    StatusBarWidget, StatusBarWidget.TextPresentation {
    private var bar: StatusBar? = null

    override fun ID(): String = STATUS_WIDGET

    override fun getPresentation(): StatusBarWidget.WidgetPresentation = this

    override fun install(statusBar: StatusBar) {
        bar = statusBar
        project.messageBus.connect(this).subscribe(Workstreams.CHANGED, Workstreams.Changed {
            ApplicationManager.getApplication().invokeLater({ bar?.updateWidget(STATUS_WIDGET) }, project.disposed)
        })
    }

    private fun active(): WorkstreamNode? {
        val snap = Workstreams.of(project).snapshot ?: return null
        val (row, errors) = activeWorkstream(Snapshots.rows(snap), Snapshots.health(snap)) ?: return null
        return WorkstreamNode(row.id, row, errors)
    }

    /** Plain text: the status bar draws it as a label's text, which this never starts with markup. */
    override fun getText(): String {
        val node = active() ?: return ""
        val view = Workstreams.of(project).cachedView(node.row.id)
        return statusText(node.row.id, view?.wave, node.errors, claimedTask(view), now())
    }

    override fun getAlignment(): Float = Component.CENTER_ALIGNMENT

    override fun getTooltipText(): String? = active()?.let { Text.tip(shown(it).tip) }

    override fun getClickConsumer(): Consumer<MouseEvent> = Consumer {
        ToolWindowManager.getInstance(project).getToolWindow(TOOL_WINDOW)?.activate(null)
    }

    override fun dispose() {
        bar = null
    }
}
