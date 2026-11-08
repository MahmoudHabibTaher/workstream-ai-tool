// The Workstreams tool window's Registry tab: workstreams, then each one's wave line, phases, tasks
// and documents. It arranges what Workstreams holds, which holds only what the CLI printed. Labels
// are appended as text through ColoredTreeCellRenderer, and tooltips go through Text.tip (plan T2).
package dev.workstream.jetbrains

import com.intellij.icons.AllIcons
import com.intellij.ide.util.treeView.AbstractTreeStructure
import com.intellij.ide.util.treeView.NodeDescriptor
import com.intellij.ide.util.treeView.PresentableNodeDescriptor
import com.intellij.ide.projectView.PresentationData
import com.intellij.openapi.Disposable
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.ActionUpdateThread
import com.intellij.openapi.actionSystem.AnAction
import com.intellij.openapi.actionSystem.AnActionEvent
import com.intellij.openapi.actionSystem.DataSink
import com.intellij.openapi.actionSystem.DefaultActionGroup
import com.intellij.openapi.actionSystem.ToggleAction
import com.intellij.openapi.fileEditor.OpenFileDescriptor
import com.intellij.openapi.project.DumbAware
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.SimpleToolWindowPanel
import com.intellij.openapi.util.Disposer
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.openapi.wm.ToolWindow
import com.intellij.openapi.wm.ToolWindowFactory
import com.intellij.ui.ColoredTreeCellRenderer
import com.intellij.ui.DoubleClickListener
import com.intellij.ui.PopupHandler
import com.intellij.ui.ScrollPaneFactory
import com.intellij.ui.SimpleTextAttributes
import com.intellij.ui.content.ContentFactory
import com.intellij.ui.tree.AsyncTreeModel
import com.intellij.ui.tree.StructureTreeModel
import com.intellij.ui.treeStructure.Tree
import com.intellij.util.concurrency.Invoker
import com.intellij.util.ui.tree.TreeUtil
import dev.workstream.jetbrains.logic.DocumentNode
import dev.workstream.jetbrains.logic.DocumentsNode
import dev.workstream.jetbrains.logic.Loaded
import dev.workstream.jetbrains.logic.MessageNode
import dev.workstream.jetbrains.logic.Node
import dev.workstream.jetbrains.logic.PhaseNode
import dev.workstream.jetbrains.logic.TaskNode
import dev.workstream.jetbrains.logic.WaveNode
import dev.workstream.jetbrains.logic.WorkstreamNode
import dev.workstream.jetbrains.logic.documentChildren
import dev.workstream.jetbrains.logic.phaseChildren
import dev.workstream.jetbrains.logic.shown
import dev.workstream.jetbrains.logic.workstreamChildren
import dev.workstream.jetbrains.logic.workstreams
import java.awt.event.KeyAdapter
import java.awt.event.KeyEvent
import java.awt.event.MouseEvent
import java.util.concurrent.ConcurrentHashMap
import javax.swing.Icon
import javax.swing.JTree

const val TOOL_WINDOW = "Workstreams"
const val POPUP_GROUP = "Workstreams.Registry.Popup"

/**
 * The tree's contents. Children are asked for on a background thread without a read action, since
 * a workstream's children come from `ws snapshot -w`.
 */
class RegistryStructure(private val project: Project, private val now: () -> Long = System::currentTimeMillis) : AbstractTreeStructure() {
    private val root = Any()

    // Nodes are equal across reloads when their ids are; this maps each to its newest copy.
    private val latest = ConcurrentHashMap<Node, Node>()

    fun latest(node: Node): Node = latest[node] ?: node

    override fun getRootElement(): Any = root

    override fun getChildElements(element: Any): Array<Any> {
        val ws = Workstreams.of(project)
        val found: List<Node> = when (element) {
            root -> {
                val snap = ws.snapshot
                val error = ws.error
                val rows = if (snap == null) listOf() else workstreams(Snapshots.rows(snap), Snapshots.health(snap), ws.showDone, Snapshots.revisions(snap))
                (if (error != null) listOf(MessageNode("error", error, true)) else listOf()) + rows
            }
            is WorkstreamNode -> when (val got = ws.view(element.row.id)) {
                is Loaded.Error -> listOf(MessageNode("${element.id}\u001ferror", got.error, true))
                is Loaded.Value -> workstreamChildren(element.row.id, got.value)
            }
            is PhaseNode -> phaseChildren(latest(element) as PhaseNode, now())
            is DocumentsNode -> documentChildren(latest(element) as DocumentsNode)
            else -> listOf()
        }
        for (node in found) latest[node] = node
        return found.toTypedArray()
    }

    override fun getParentElement(element: Any): Any? = null

    override fun isAlwaysLeaf(element: Any): Boolean = element is Node && !shown(element).collapsible

    override fun createDescriptor(element: Any, parentDescriptor: NodeDescriptor<*>?): NodeDescriptor<*> =
        RegistryDescriptor(project, parentDescriptor, this, element)

    override fun commit() = Unit

    override fun hasSomethingToCommit(): Boolean = false
}

class RegistryDescriptor(project: Project, parent: NodeDescriptor<*>?, private val structure: RegistryStructure, private val element: Any) :
    PresentableNodeDescriptor<Any>(project, parent) {
    /** The newest copy of this node, which the renderer draws. */
    val node: Node? get() = (element as? Node)?.let(structure::latest)

    override fun getElement(): Any = element

    override fun update(presentation: PresentationData) {
        val node = node ?: return
        presentation.presentableText = shown(node).label
        presentation.setIcon(iconOf(node))
    }
}

private val STATUS_ICONS: Map<String, Icon> = mapOf(
    "active" to AllIcons.Actions.Execute, "paused" to AllIcons.Actions.Pause, "done" to AllIcons.Actions.Checked,
    "abandoned" to AllIcons.Actions.Cancel, "in-progress" to AllIcons.Actions.Execute, "blocked" to AllIcons.General.Error,
)

fun iconOf(node: Node): Icon? = when (node) {
    is WorkstreamNode -> STATUS_ICONS[node.row.status]
    is TaskNode -> STATUS_ICONS[node.task.status]
    is WaveNode -> AllIcons.General.Information
    is PhaseNode -> AllIcons.Nodes.Folder
    is DocumentsNode -> AllIcons.Nodes.Folder
    is DocumentNode -> AllIcons.FileTypes.Text
    is MessageNode -> if (node.error) AllIcons.General.Error else AllIcons.General.Information
}

/** Draws a node's label and description as text, and its tooltip through Text.tip. */
class RegistryRenderer : ColoredTreeCellRenderer() {
    override fun customizeCellRenderer(tree: JTree, value: Any?, selected: Boolean, expanded: Boolean, leaf: Boolean, row: Int, hasFocus: Boolean) {
        val node = (TreeUtil.getUserObject(value) as? RegistryDescriptor)?.node ?: return
        val s = shown(node)
        append(s.label, if (node is MessageNode && node.error) SimpleTextAttributes.ERROR_ATTRIBUTES else SimpleTextAttributes.REGULAR_ATTRIBUTES)
        if (s.description.isNotEmpty()) append("  ${s.description}", SimpleTextAttributes.GRAYED_ATTRIBUTES)
        icon = iconOf(node)
        toolTipText = Text.tip(s.tip)
    }
}

class RegistryPanel(private val project: Project, parent: Disposable) : SimpleToolWindowPanel(true, true) {
    val structure = RegistryStructure(project)
    val model = StructureTreeModel(structure, null, Invoker.forBackgroundPoolWithoutReadAction(parent), parent)
    val tree = Tree(AsyncTreeModel(model, parent))

    init {
        tree.isRootVisible = false
        tree.showsRootHandles = true
        tree.cellRenderer = RegistryRenderer()
        object : DoubleClickListener() {
            override fun onDoubleClick(event: MouseEvent): Boolean = openSelected()
        }.installOn(tree)
        tree.addKeyListener(object : KeyAdapter() {
            override fun keyPressed(e: KeyEvent) {
                if (e.keyCode == KeyEvent.VK_ENTER && openSelected()) e.consume()
            }
        })
        PopupHandler.installPopupMenu(tree, POPUP_GROUP, "WorkstreamsRegistryPopup")
        val actions = DefaultActionGroup(ShowDoneAction(), RefreshAction())
        val toolbar = ActionManager.getInstance().createActionToolbar("WorkstreamsRegistry", actions, true)
        toolbar.targetComponent = this
        setToolbar(toolbar.component)
        setContent(ScrollPaneFactory.createScrollPane(tree))
        project.messageBus.connect(parent).subscribe(Workstreams.CHANGED, Workstreams.Changed { model.invalidateAsync() })
    }

    /** The selected node's newest copy: what the writes and launches act on. */
    fun selected(): Node? = (TreeUtil.getUserObject(tree.selectionPath?.lastPathComponent) as? RegistryDescriptor)?.node

    override fun uiDataSnapshot(sink: DataSink) {
        super.uiDataSnapshot(sink)
        selected()?.let { sink[WS_NODE] = it }
    }

    private fun openSelected(): Boolean {
        val node = selected()
        if (node !is DocumentNode) return false
        open(node)
        return true
    }

    /** Opens a document in the editor, from the path the snapshot gave. */
    fun open(node: DocumentNode): VirtualFile? {
        val fs = LocalFileSystem.getInstance()
        val file = fs.findFileByPath(node.path) ?: fs.refreshAndFindFileByPath(node.path) ?: return null
        OpenFileDescriptor(project, file).navigate(true)
        return file
    }
}

class ShowDoneAction : ToggleAction("Show Done", "Also show the done and abandoned workstreams", AllIcons.Actions.Show), DumbAware {
    override fun getActionUpdateThread() = ActionUpdateThread.BGT
    override fun isSelected(e: AnActionEvent): Boolean = e.project?.let { Workstreams.of(it).showDone } ?: false
    override fun setSelected(e: AnActionEvent, state: Boolean) {
        e.project?.let { Workstreams.of(it).showDone = state }
    }
}

class RefreshAction : AnAction("Refresh", "Read the snapshot again", AllIcons.Actions.Refresh), DumbAware {
    override fun getActionUpdateThread() = ActionUpdateThread.BGT
    override fun update(e: AnActionEvent) {
        e.presentation.isEnabled = e.project?.let { Workstreams.of(it).root } != null
    }
    override fun actionPerformed(e: AnActionEvent) {
        e.project?.let { Workstreams.of(it).refresh() }
    }
}

/** One tool window, Workstreams: its Registry and Review tabs. */
class WorkstreamsToolWindow : ToolWindowFactory, DumbAware {
    override fun createToolWindowContent(project: Project, toolWindow: ToolWindow) {
        val registry = Disposer.newDisposable(toolWindow.disposable, "Workstreams Registry")
        addTab(toolWindow, RegistryPanel(project, registry), "Registry", registry)
        val review = Disposer.newDisposable(toolWindow.disposable, "Workstreams Review")
        addTab(toolWindow, ReviewPanel(project, review), "Review", review)
    }

    private fun addTab(toolWindow: ToolWindow, panel: SimpleToolWindowPanel, name: String, disposable: Disposable) {
        val content = ContentFactory.getInstance().createContent(panel, name, false)
        content.setDisposer(disposable)
        toolWindow.contentManager.addContent(content)
    }
}
