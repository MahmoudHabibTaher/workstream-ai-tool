// The Workstreams tool window's Health and Budget tabs. Health lists the snapshot's findings,
// errors first, in the CLI's order; a finding's writes are in its popup, the Registry's own
// actions, so they ask the same confirm and go through `ws act`. Budget shows `ws audit context
// --json`'s rows, read when the tab is first selected and again after Refresh, never on a
// file-change reload. Labels are appended as text through ColoredTreeCellRenderer, and tooltips go
// through Text.tip (plan T2).
package dev.workstream.jetbrains

import com.intellij.icons.AllIcons
import com.intellij.ide.projectView.PresentationData
import com.intellij.ide.util.treeView.AbstractTreeStructure
import com.intellij.ide.util.treeView.NodeDescriptor
import com.intellij.ide.util.treeView.PresentableNodeDescriptor
import com.intellij.openapi.Disposable
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.DataSink
import com.intellij.openapi.actionSystem.DefaultActionGroup
import com.intellij.notification.NotificationAction
import com.intellij.notification.Notification
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.SimpleToolWindowPanel
import com.intellij.openapi.wm.ToolWindowManager
import com.intellij.ui.ColoredTreeCellRenderer
import com.intellij.ui.PopupHandler
import com.intellij.ui.ScrollPaneFactory
import com.intellij.ui.SimpleTextAttributes
import com.intellij.ui.tree.AsyncTreeModel
import com.intellij.ui.tree.StructureTreeModel
import com.intellij.ui.treeStructure.Tree
import com.intellij.util.concurrency.Invoker
import com.intellij.util.ui.tree.TreeUtil
import dev.workstream.jetbrains.logic.BudgetNode
import dev.workstream.jetbrains.logic.BudgetNote
import dev.workstream.jetbrains.logic.FindingNode
import dev.workstream.jetbrains.logic.HealthNode
import dev.workstream.jetbrains.logic.HealthNote
import dev.workstream.jetbrains.logic.LevelNode
import dev.workstream.jetbrains.logic.Loaded
import dev.workstream.jetbrains.logic.RowNode
import dev.workstream.jetbrains.logic.budgetNodes
import dev.workstream.jetbrains.logic.budgetShown
import dev.workstream.jetbrains.logic.healthNodes
import dev.workstream.jetbrains.logic.healthShown
import dev.workstream.jetbrains.logic.levelChildren
import java.util.concurrent.ConcurrentHashMap
import javax.swing.Icon
import javax.swing.JTree

const val HEALTH_TAB = "Health"
const val BUDGET_TAB = "Budget"

/** The findings, from the snapshot Workstreams holds: no `ws` call of its own. */
class HealthStructure(private val project: Project) : AbstractTreeStructure() {
    private val root = Any()
    private val latest = ConcurrentHashMap<HealthNode, HealthNode>()

    fun latest(node: HealthNode): HealthNode = latest[node] ?: node

    override fun getRootElement(): Any = root

    override fun getChildElements(element: Any): Array<Any> {
        val ws = Workstreams.of(project)
        val found: List<HealthNode> = when (element) {
            root -> {
                val snap = ws.snapshot
                val error = ws.error
                (if (error != null) listOf(HealthNote("health\u001ferror", error, true)) else listOf()) +
                    (if (snap == null) listOf() else healthNodes(Snapshots.health(snap), Snapshots.revisions(snap), Snapshots.gitError(snap)))
            }
            is LevelNode -> levelChildren(latest(element) as LevelNode)
            else -> listOf()
        }
        for (node in found) latest[node] = node
        return found.toTypedArray()
    }

    override fun getParentElement(element: Any): Any? = null

    override fun isAlwaysLeaf(element: Any): Boolean = element is HealthNode && !healthShown(element).collapsible

    override fun createDescriptor(element: Any, parentDescriptor: NodeDescriptor<*>?): NodeDescriptor<*> =
        HealthDescriptor(project, parentDescriptor, this, element)

    override fun commit() = Unit

    override fun hasSomethingToCommit(): Boolean = false
}

class HealthDescriptor(project: Project, parent: NodeDescriptor<*>?, private val structure: HealthStructure, private val element: Any) :
    PresentableNodeDescriptor<Any>(project, parent) {
    val node: HealthNode? get() = (element as? HealthNode)?.let(structure::latest)

    override fun getElement(): Any = element

    override fun update(presentation: PresentationData) {
        val node = node ?: return
        presentation.presentableText = healthShown(node).label
        presentation.setIcon(healthIconOf(node))
    }
}

private fun levelIcon(level: String): Icon = when (level) {
    "error" -> AllIcons.General.Error
    "warning" -> AllIcons.General.Warning
    else -> AllIcons.General.Information
}

fun healthIconOf(node: HealthNode): Icon = when (node) {
    is LevelNode -> levelIcon(node.level)
    is FindingNode -> levelIcon(node.finding.level)
    is HealthNote -> if (node.error) AllIcons.General.Error else AllIcons.General.InspectionsOK
}

/** Draws a node's label and description as text, and its tooltip through Text.tip. */
class HealthRenderer : ColoredTreeCellRenderer() {
    override fun customizeCellRenderer(tree: JTree, value: Any?, selected: Boolean, expanded: Boolean, leaf: Boolean, row: Int, hasFocus: Boolean) {
        val node = (TreeUtil.getUserObject(value) as? HealthDescriptor)?.node ?: return
        val s = healthShown(node)
        append(s.label, if (node is HealthNote && node.error) SimpleTextAttributes.ERROR_ATTRIBUTES else SimpleTextAttributes.REGULAR_ATTRIBUTES)
        if (s.description.isNotEmpty()) append("  ${s.description}", SimpleTextAttributes.GRAYED_ATTRIBUTES)
        icon = healthIconOf(node)
        toolTipText = Text.tip(s.tip)
    }
}

class HealthPanel(private val project: Project, parent: Disposable) : SimpleToolWindowPanel(true, true) {
    val structure = HealthStructure(project)
    val model = StructureTreeModel(structure, null, Invoker.forBackgroundPoolWithoutReadAction(parent), parent)
    val tree = Tree(AsyncTreeModel(model, parent))

    init {
        tree.isRootVisible = false
        tree.showsRootHandles = true
        tree.cellRenderer = HealthRenderer()
        PopupHandler.installPopupMenu(tree, POPUP_GROUP, "WorkstreamsHealthPopup")
        val toolbar = ActionManager.getInstance().createActionToolbar("WorkstreamsHealth", DefaultActionGroup(RefreshAction()), true)
        toolbar.targetComponent = this
        setToolbar(toolbar.component)
        setContent(ScrollPaneFactory.createScrollPane(tree))
        project.messageBus.connect(parent).subscribe(Workstreams.CHANGED, Workstreams.Changed { model.invalidateAsync() })
    }

    fun selected(): HealthNode? = (TreeUtil.getUserObject(tree.selectionPath?.lastPathComponent) as? HealthDescriptor)?.node

    /** A finding is what the popup's writes act on, as a Registry node is. */
    override fun uiDataSnapshot(sink: DataSink) {
        super.uiDataSnapshot(sink)
        (selected() as? FindingNode)?.let { sink[WS_NODE] = it }
    }
}

/** The health notification's one action: the Workstreams tool window, on its Health tab. */
class ShowHealthAction : NotificationAction("Show Health") {
    override fun getActionUpdateThread() = ActionUpdateThread.EDT

    override fun actionPerformed(e: AnActionEvent, notification: Notification) {
        e.project?.let(::showHealth)
    }
}

fun showHealth(project: Project) {
    val window = ToolWindowManager.getInstance(project).getToolWindow(TOOL_WINDOW) ?: return
    window.activate {
        window.contentManager.findContent(HEALTH_TAB)?.let { window.contentManager.setSelectedContent(it) }
    }
}

/**
 * The rows, asked for on a background thread. While the tab isn't showing it draws only what was
 * already read, so neither a reload nor a Refresh runs `ws audit context` until it is selected.
 */
class BudgetStructure(private val project: Project, private val showing: () -> Boolean) : AbstractTreeStructure() {
    private val root = Any()

    override fun getRootElement(): Any = root

    override fun getChildElements(element: Any): Array<Any> {
        if (element !== root) return arrayOf()
        val ws = Workstreams.of(project)
        if (ws.root == null || ws.snapshot == null) return arrayOf()
        val found: List<BudgetNode> = when (val got = ws.budget(showing)) {
            null -> listOf()
            is Loaded.Error -> listOf(BudgetNote("budget\u001ferror", got.error, true))
            is Loaded.Value -> budgetNodes(got.value)
        }
        return found.toTypedArray()
    }

    override fun getParentElement(element: Any): Any? = null

    override fun isAlwaysLeaf(element: Any): Boolean = element is BudgetNode

    override fun createDescriptor(element: Any, parentDescriptor: NodeDescriptor<*>?): NodeDescriptor<*> =
        BudgetDescriptor(project, parentDescriptor, element)

    override fun commit() = Unit

    override fun hasSomethingToCommit(): Boolean = false
}

class BudgetDescriptor(project: Project, parent: NodeDescriptor<*>?, private val element: Any) : PresentableNodeDescriptor<Any>(project, parent) {
    val node: BudgetNode? get() = element as? BudgetNode

    override fun getElement(): Any = element

    override fun update(presentation: PresentationData) {
        val node = node ?: return
        presentation.presentableText = budgetShown(node).label
        presentation.setIcon(budgetIconOf(node))
    }
}

fun budgetIconOf(node: BudgetNode): Icon = when (node) {
    is RowNode -> if (node.row.ok) AllIcons.General.InspectionsOK else AllIcons.General.Error
    is BudgetNote -> if (node.error) AllIcons.General.Error else AllIcons.General.Information
}

class BudgetRenderer : ColoredTreeCellRenderer() {
    override fun customizeCellRenderer(tree: JTree, value: Any?, selected: Boolean, expanded: Boolean, leaf: Boolean, row: Int, hasFocus: Boolean) {
        val node = (TreeUtil.getUserObject(value) as? BudgetDescriptor)?.node ?: return
        val s = budgetShown(node)
        val bad = (node is BudgetNote && node.error) || (node is RowNode && !node.row.ok)
        append(s.label, if (bad) SimpleTextAttributes.ERROR_ATTRIBUTES else SimpleTextAttributes.REGULAR_ATTRIBUTES)
        if (s.description.isNotEmpty()) append("  ${s.description}", SimpleTextAttributes.GRAYED_ATTRIBUTES)
        icon = budgetIconOf(node)
        toolTipText = Text.tip(s.tip)
    }
}

class BudgetPanel(project: Project, parent: Disposable) : SimpleToolWindowPanel(true, true) {
    @Volatile
    var showing: Boolean = false
        private set
    val structure = BudgetStructure(project) { showing }
    val model = StructureTreeModel(structure, null, Invoker.forBackgroundPoolWithoutReadAction(parent), parent)
    val tree = Tree(AsyncTreeModel(model, parent))

    init {
        tree.isRootVisible = false
        tree.showsRootHandles = false
        tree.cellRenderer = BudgetRenderer()
        val toolbar = ActionManager.getInstance().createActionToolbar("WorkstreamsBudget", DefaultActionGroup(RefreshAction()), true)
        toolbar.targetComponent = this
        setToolbar(toolbar.component)
        setContent(ScrollPaneFactory.createScrollPane(tree))
        project.messageBus.connect(parent).subscribe(Workstreams.CHANGED, Workstreams.Changed { model.invalidateAsync() })
    }

    /** Told when the tab is selected or left: selecting it reads the rows, if none are held. */
    fun setShowing(now: Boolean) {
        val was = showing
        showing = now
        if (now && !was) model.invalidateAsync()
    }
}
