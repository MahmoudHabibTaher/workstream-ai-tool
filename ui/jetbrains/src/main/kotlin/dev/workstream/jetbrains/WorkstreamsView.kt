// The Workstreams tool window's Workstreams tab (D-LAYOUT): a list of workstreams on the left and,
// for the selected one, a Tasks tab with a table above a task pane. It arranges what Workstreams
// holds, which holds only what the CLI printed. Repo text is drawn as text: list and table cells
// through ColoredListCellRenderer and ColoredTableCellRenderer, pane lines in read-only text areas,
// link labels through Text.html, and tooltips through Text.tip (plan T2, T6).
package dev.workstream.jetbrains

import com.intellij.icons.AllIcons
import com.intellij.notification.NotificationType
import com.intellij.openapi.Disposable
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.DataSink
import com.intellij.openapi.actionSystem.DefaultActionGroup
import com.intellij.openapi.actionSystem.ToggleAction
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.fileEditor.FileDocumentManager
import com.intellij.openapi.fileEditor.OpenFileDescriptor
import com.intellij.openapi.project.DumbAware
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.SimpleToolWindowPanel
import com.intellij.openapi.util.Disposer
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.CollectionListModel
import com.intellij.ui.ColoredListCellRenderer
import com.intellij.ui.ColoredTableCellRenderer
import com.intellij.ui.DoubleClickListener
import com.intellij.ui.OnePixelSplitter
import com.intellij.ui.PopupHandler
import com.intellij.ui.ScrollPaneFactory
import com.intellij.ui.SimpleColoredComponent
import com.intellij.ui.SimpleTextAttributes
import com.intellij.ui.components.ActionLink
import com.intellij.ui.components.JBList
import com.intellij.ui.components.JBTabbedPane
import com.intellij.ui.components.JBTextArea
import com.intellij.ui.content.Content
import com.intellij.ui.content.ContentFactory
import com.intellij.ui.content.ContentManagerEvent
import com.intellij.ui.content.ContentManagerListener
import com.intellij.ui.dsl.builder.AlignX
import com.intellij.ui.dsl.builder.panel
import com.intellij.ui.table.TableView
import com.intellij.util.ui.ColumnInfo
import com.intellij.util.ui.JBUI
import com.intellij.util.ui.ListTableModel
import dev.workstream.jetbrains.logic.Loaded
import dev.workstream.jetbrains.logic.PaneItem
import dev.workstream.jetbrains.logic.PaneSection
import dev.workstream.jetbrains.logic.TASK_COLUMNS
import dev.workstream.jetbrains.logic.TaskNode
import dev.workstream.jetbrains.logic.WorkstreamNode
import dev.workstream.jetbrains.logic.WsView
import dev.workstream.jetbrains.logic.documents
import dev.workstream.jetbrains.logic.filePath
import dev.workstream.jetbrains.logic.rowDetails
import dev.workstream.jetbrains.logic.shown
import dev.workstream.jetbrains.logic.taskCells
import dev.workstream.jetbrains.logic.taskOffset
import dev.workstream.jetbrains.logic.taskPane
import dev.workstream.jetbrains.logic.taskRows
import dev.workstream.jetbrains.logic.waveLine
import dev.workstream.jetbrains.logic.workstreams
import java.awt.BorderLayout
import java.awt.Dimension
import java.awt.FlowLayout
import java.awt.Rectangle
import java.awt.event.FocusAdapter
import java.awt.event.FocusEvent
import java.awt.event.KeyAdapter
import java.awt.event.KeyEvent
import java.awt.event.MouseEvent
import java.util.concurrent.atomic.AtomicInteger
import javax.swing.Icon
import javax.swing.JComponent
import javax.swing.JList
import javax.swing.JPanel
import javax.swing.JTable
import javax.swing.ListSelectionModel
import javax.swing.Scrollable
import javax.swing.SwingConstants
import javax.swing.table.TableCellRenderer

const val TOOL_WINDOW = "Workstreams"
const val WORKSTREAMS_TAB = "Workstreams"
const val TASKS_TAB = "Tasks"
const val POPUP_GROUP = "Workstreams.Registry.Popup"

private val STATUS_ICONS: Map<String, Icon> = mapOf(
    "active" to AllIcons.Actions.Execute, "paused" to AllIcons.Actions.Pause, "done" to AllIcons.Actions.Checked,
    "abandoned" to AllIcons.Actions.Cancel, "in-progress" to AllIcons.Actions.Execute, "blocked" to AllIcons.General.Error,
)

fun statusIcon(status: String): Icon? = STATUS_ICONS[status]

/** A list row: its id, then its done/total, status, claims and errors, greyed; its tooltip through Text.tip. */
class WorkstreamsRenderer : ColoredListCellRenderer<WorkstreamNode>() {
    override fun customizeCellRenderer(list: JList<out WorkstreamNode>, value: WorkstreamNode?, index: Int, selected: Boolean, hasFocus: Boolean) {
        val node = value ?: return
        append(node.row.id, SimpleTextAttributes.REGULAR_ATTRIBUTES)
        val details = rowDetails(node)
        if (details.isNotEmpty()) append("  ${details.joinToString(" · ")}", SimpleTextAttributes.GRAYED_ATTRIBUTES)
        icon = statusIcon(node.row.status)
        toolTipText = Text.tip(shown(node).tip)
    }
}

/** A table cell as text; the Status column also draws the status icon. Its tooltip is the task's, through Text.tip. */
class TaskCellRenderer : ColoredTableCellRenderer() {
    override fun customizeCellRenderer(table: JTable, value: Any?, selected: Boolean, hasFocus: Boolean, row: Int, column: Int) {
        append(value as? String ?: "", SimpleTextAttributes.REGULAR_ATTRIBUTES)
        @Suppress("UNCHECKED_CAST")
        val node = (table.model as? ListTableModel<TaskNode>)?.getItem(table.convertRowIndexToModel(row)) ?: return
        if (table.convertColumnIndexToModel(column) == 0) icon = statusIcon(node.task.status)
        toolTipText = Text.tip(shown(node).tip)
    }
}

private val CELL_RENDERER = TaskCellRenderer()

class TaskColumn(private val index: Int) : ColumnInfo<TaskNode, String>(TASK_COLUMNS[index]) {
    override fun valueOf(item: TaskNode): String = taskCells(item)[index]
    override fun getRenderer(item: TaskNode?): TableCellRenderer = CELL_RENDERER
}

/** A panel that takes the viewport's width, so the pane's text areas wrap rather than scroll sideways. */
private class WidthTracking : JPanel(BorderLayout()), Scrollable {
    override fun getPreferredScrollableViewportSize(): Dimension = preferredSize
    override fun getScrollableUnitIncrement(visibleRect: Rectangle, orientation: Int, direction: Int): Int = JBUI.scale(16)
    override fun getScrollableBlockIncrement(visibleRect: Rectangle, orientation: Int, direction: Int): Int =
        if (orientation == SwingConstants.VERTICAL) visibleRect.height else visibleRect.width
    override fun getScrollableTracksViewportWidth(): Boolean = true
    override fun getScrollableTracksViewportHeight(): Boolean = false
}

/**
 * The selected task's pane, built with the UI DSL from taskPane's sections. Headings are the
 * plugin's constants, lines sit in read-only text areas, which never read markup, and links
 * carry their text through Text.html.
 */
class TaskPane(private val onTask: (String) -> Unit, private val onFile: (String) -> Unit) {
    private val holder = WidthTracking()
    val component: JComponent = ScrollPaneFactory.createScrollPane(holder, true)

    /** What the pane shows now: the sections it was built from, and each link it drew. */
    var sections: List<PaneSection> = listOf()
        private set
    var links: Map<PaneItem, ActionLink> = mapOf()
        private set

    fun show(found: List<PaneSection>) {
        sections = found
        val drawn = mutableMapOf<PaneItem, ActionLink>()
        val content = panel {
            for (section in found) {
                section.heading?.let { heading ->
                    row { cell(SimpleColoredComponent().apply { append(heading, SimpleTextAttributes.REGULAR_BOLD_ATTRIBUTES) }) }
                }
                for (item in section.items) {
                    row {
                        when (item) {
                            is PaneItem.Line -> cell(JBTextArea(item.text).apply {
                                isEditable = false
                                lineWrap = true
                                wrapStyleWord = true
                                isOpaque = false
                                border = null
                            }).align(AlignX.FILL)
                            is PaneItem.TaskLink -> cell(ActionLink(Text.html(item.id)) { onTask(item.id) }.also { drawn[item] = it })
                            is PaneItem.FileLink -> cell(ActionLink(Text.html(item.path)) { onFile(item.path) }.also { drawn[item] = it })
                        }
                    }
                }
            }
        }
        links = drawn
        holder.removeAll()
        holder.add(content, BorderLayout.NORTH)
        holder.revalidate()
        holder.repaint()
    }
}

class WorkstreamsPanel(private val project: Project, parent: Disposable, private val now: () -> Long = System::currentTimeMillis) :
    SimpleToolWindowPanel(true, true) {
    val listModel = CollectionListModel<WorkstreamNode>()
    val list = JBList(listModel)
    val tableModel = ListTableModel<TaskNode>(*TASK_COLUMNS.indices.map { TaskColumn(it) }.toTypedArray())
    val table = TableView(tableModel)
    val pane = TaskPane(::selectTask, ::openFile)
    val tabs = JBTabbedPane()

    /** The selected workstream's name and wave line, and its documents as links. */
    val header = SimpleColoredComponent()
    private val docs = JPanel(FlowLayout(FlowLayout.LEFT, JBUI.scale(8), 0))

    /** The view the table was drawn from, or why there is none. */
    var view: Loaded<WsView>? = null
        private set
    private var shownWs: String? = null

    // A load still running, so a test can wait for the view to settle.
    private val loading = AtomicInteger()
    private val generation = AtomicInteger()
    private var rebuilding = false

    // Whether the last of the two the person used was the table: then the writes act on its task.
    private var taskFocus = false

    val idle: Boolean get() = loading.get() == 0

    init {
        list.cellRenderer = WorkstreamsRenderer()
        list.selectionMode = ListSelectionModel.SINGLE_SELECTION
        list.addListSelectionListener { if (!it.valueIsAdjusting && !rebuilding) loadView() }
        table.setSelectionMode(ListSelectionModel.SINGLE_SELECTION)
        table.selectionModel.addListSelectionListener { if (!it.valueIsAdjusting && !rebuilding) drawPane() }
        list.addFocusListener(object : FocusAdapter() {
            override fun focusGained(e: FocusEvent) { taskFocus = false }
        })
        table.addFocusListener(object : FocusAdapter() {
            override fun focusGained(e: FocusEvent) { taskFocus = true }
        })
        object : DoubleClickListener() {
            override fun onDoubleClick(event: MouseEvent): Boolean = selectedTask()?.let { openTask(it); true } ?: false
        }.installOn(table)
        table.addKeyListener(object : KeyAdapter() {
            override fun keyPressed(e: KeyEvent) {
                if (e.keyCode == KeyEvent.VK_ENTER) selectedTask()?.let { openTask(it); e.consume() }
            }
        })
        PopupHandler.installPopupMenu(list, POPUP_GROUP, "WorkstreamsListPopup")
        PopupHandler.installPopupMenu(table, POPUP_GROUP, "WorkstreamsTasksPopup")

        val tasks = OnePixelSplitter(true, "Workstreams.Tasks.Proportion", 0.5f)
        tasks.firstComponent = ScrollPaneFactory.createScrollPane(table, true)
        tasks.secondComponent = pane.component
        tabs.addTab(TASKS_TAB, tasks)
        val detail = JPanel(BorderLayout())
        val top = JPanel(BorderLayout())
        top.add(header, BorderLayout.NORTH)
        top.add(docs, BorderLayout.SOUTH)
        top.border = JBUI.Borders.empty(4)
        detail.add(top, BorderLayout.NORTH)
        detail.add(tabs, BorderLayout.CENTER)
        val split = OnePixelSplitter(false, "Workstreams.List.Proportion", 0.3f)
        split.firstComponent = ScrollPaneFactory.createScrollPane(list, true)
        split.secondComponent = detail

        val actions = DefaultActionGroup(ShowDoneAction(), RefreshAction())
        val toolbar = ActionManager.getInstance().createActionToolbar("WorkstreamsList", actions, true)
        toolbar.targetComponent = this
        setToolbar(toolbar.component)
        setContent(split)
        project.messageBus.connect(parent).subscribe(Workstreams.CHANGED, Workstreams.Changed {
            ApplicationManager.getApplication().invokeLater({ reloadList() }, { project.isDisposed })
        })
        reloadList()
    }

    fun selectedWorkstream(): WorkstreamNode? = list.selectedValue

    fun selectedTask(): TaskNode? = table.selectedObject

    /** What the writes and launches act on: the task when the table was used last, else the workstream. */
    fun selected(): Any? = (if (taskFocus) selectedTask() else null) ?: selectedWorkstream()

    override fun uiDataSnapshot(sink: DataSink) {
        super.uiDataSnapshot(sink)
        selected()?.let { sink[WS_NODE] = it }
    }

    /** Draws the list from the snapshot, keeping the selection by id, then reads the selected one's view again. */
    fun reloadList() {
        val ws = Workstreams.of(project)
        val snap = ws.snapshot
        val rows = if (snap == null) listOf() else workstreams(Snapshots.rows(snap), Snapshots.health(snap), ws.showDone, Snapshots.revisions(snap))
        val keep = selectedWorkstream()?.row?.id
        rebuilding = true
        try {
            listModel.replaceAll(rows)
            val at = rows.indexOfFirst { it.row.id == keep }.takeIf { it >= 0 } ?: if (rows.isNotEmpty()) 0 else -1
            if (at >= 0) list.selectedIndex = at else list.clearSelection()
        } finally {
            rebuilding = false
        }
        ws.error?.let { list.emptyText.setText(it, SimpleTextAttributes.ERROR_ATTRIBUTES) } ?: list.emptyText.setText("No workstreams")
        loadView()
    }

    /** Selects the workstream with this id, which loads its view. */
    fun selectWorkstream(id: String): Boolean {
        val at = listModel.items.indexOfFirst { it.row.id == id }
        if (at < 0) return false
        list.selectedIndex = at
        return true
    }

    /** Reads the selected workstream's snapshot off the EDT, then draws its table on it. */
    private fun loadView() {
        val node = selectedWorkstream()
        val gen = generation.incrementAndGet()
        if (node == null) return drawView(null, null)
        val id = node.row.id
        loading.incrementAndGet()
        ApplicationManager.getApplication().executeOnPooledThread {
            val got = try { Workstreams.of(project).view(id) } catch (e: RuntimeException) { Loaded.Error(e.message ?: e.toString()) }
            ApplicationManager.getApplication().invokeLater({
                try {
                    if (gen == generation.get()) drawView(id, got)
                } finally {
                    loading.decrementAndGet()
                }
            }, { project.isDisposed })
        }
    }

    private fun drawView(id: String?, got: Loaded<WsView>?) {
        val keep = if (id == shownWs) selectedTask()?.task?.id else null
        view = got
        shownWs = id
        val value = (got as? Loaded.Value)?.value
        val rows = if (id != null && value != null) taskRows(id, value, now()) else listOf()
        rebuilding = true
        try {
            tableModel.items = rows
            val at = rows.indexOfFirst { it.task.id == keep }
            if (at >= 0) table.selectionModel.setSelectionInterval(at, at) else table.clearSelection()
        } finally {
            rebuilding = false
        }
        header.clear()
        val node = selectedWorkstream()
        if (node != null) {
            header.append(node.row.title?.let { "${node.row.id}: $it" } ?: node.row.id, SimpleTextAttributes.REGULAR_BOLD_ATTRIBUTES)
            val line = waveLine(value?.wave)
            if (line.isNotEmpty()) header.append("  $line", SimpleTextAttributes.GRAYED_ATTRIBUTES)
            (got as? Loaded.Error)?.let { header.append("  ${it.error}", SimpleTextAttributes.ERROR_ATTRIBUTES) }
        }
        docs.removeAll()
        value?.let(::documents)?.forEach { (label, path) -> docs.add(ActionLink(Text.html(label)) { openPath(path) }) }
        docs.revalidate()
        drawPane()
    }

    private fun drawPane() {
        val task = selectedTask()
        pane.show(if (task == null) listOf() else taskPane(task, tableModel.items.map { it.task.id }.toSet(), now()))
    }

    /** A jump link: selects the task with this id in the table, which redraws the pane on it. */
    fun selectTask(id: String): Boolean {
        val at = tableModel.items.indexOfFirst { it.task.id == id }
        if (at < 0) return false
        taskFocus = true
        table.selectionModel.setSelectionInterval(at, at)
        table.scrollRectToVisible(table.getCellRect(at, 0, true))
        return true
    }

    /** Opens the workstream's tasks file, as the snapshot named it, at the task's id. */
    fun openTask(node: TaskNode): VirtualFile? {
        val path = (view as? Loaded.Value)?.value?.tasksFile ?: return null
        val file = find(path) ?: return null
        val text = FileDocumentManager.getInstance().getDocument(file)?.text ?: ""
        OpenFileDescriptor(project, file, taskOffset(text, node.task.id) ?: 0).navigate(true)
        return file
    }

    /** Opens one of the task's files, under the snapshot's repo root. */
    fun openFile(path: String) {
        val root = (view as? Loaded.Value)?.value?.root
        if (openPath(filePath(root, path)) == null) Text.notify(project, "$path does not exist.", NotificationType.WARNING)
    }

    fun openPath(path: String): VirtualFile? {
        val file = find(path) ?: return null
        OpenFileDescriptor(project, file).navigate(true)
        return file
    }

    private fun find(path: String): VirtualFile? {
        val fs = LocalFileSystem.getInstance()
        return fs.findFileByPath(path) ?: fs.refreshAndFindFileByPath(path)
    }
}

class ShowDoneAction : ToggleAction("Show Done", "Also show the done and abandoned workstreams", AllIcons.Actions.Show), DumbAware {
    override fun getActionUpdateThread() = ActionUpdateThread.BGT
    override fun isSelected(e: AnActionEvent): Boolean = e.project?.let { Workstreams.of(it).showDone } ?: false
    override fun setSelected(e: AnActionEvent, state: Boolean) {
        e.project?.let { Workstreams.of(it).showDone = state }
    }
}

/** Reads the snapshot again, and drops the budget, which the Budget tab then reads again. */
class RefreshAction : AnAction("Refresh", "Read the snapshot again", AllIcons.Actions.Refresh), DumbAware {
    override fun getActionUpdateThread() = ActionUpdateThread.BGT
    override fun update(e: AnActionEvent) {
        e.presentation.isEnabled = e.project?.let { Workstreams.of(it).root } != null
    }
    override fun actionPerformed(e: AnActionEvent) {
        e.project?.let { Workstreams.of(it).refresh() }
    }
}

/** One tool window, Workstreams: its Workstreams, Review, Health and Budget tabs. */
class WorkstreamsToolWindow : ToolWindowFactory, DumbAware {
    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val workstreams = Disposer.newDisposable(toolWindow.disposable, "Workstreams List")
        addTab(toolWindow, WorkstreamsPanel(project, workstreams), WORKSTREAMS_TAB, workstreams)
        val review = Disposer.newDisposable(toolWindow.disposable, "Workstreams Review")
        addTab(toolWindow, ReviewPanel(project, review), "Review", review)
        val health = Disposer.newDisposable(toolWindow.disposable, "Workstreams Health")
        addTab(toolWindow, HealthPanel(project, health), HEALTH_TAB, health)
        val budget = Disposer.newDisposable(toolWindow.disposable, "Workstreams Budget")
        val budgetPanel = BudgetPanel(project, budget)
        val budgetTab = addTab(toolWindow, budgetPanel, BUDGET_TAB, budget)
        // The budget is read when its tab is selected, not before (D-REVIEW-UI).
        val manager = toolWindow.contentManager
        manager.addContentManagerListener(object : ContentManagerListener {
            override fun selectionChanged(event: ContentManagerEvent) {
                budgetPanel.setShowing(manager.isSelected(budgetTab))
            }
        })
        budgetPanel.setShowing(manager.isSelected(budgetTab))
    }

    private fun addTab(toolWindow: ToolWindow, panel: SimpleToolWindowPanel, name: String, disposable: Disposable): Content {
        val content = ContentFactory.getInstance().createContent(panel, name, false)
        content.setDisposer(disposable)
        toolWindow.contentManager.addContent(content)
        return content
    }
}
