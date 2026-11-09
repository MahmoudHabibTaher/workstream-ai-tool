// The Workstreams tool window's Review tab: the queue `ws review --queue` printed, branch work
// first, and under each task its range, gates, acceptance with proof, evidence and files, from
// `ws review --checks`. A file opens in the platform diff viewer with both sides from `ws review
// --show`, so a branch's old side is the merge base the CLI worked out; Kotlin never runs git.
// Labels are appended as text through ColoredTreeCellRenderer, tooltips go through Text.tip and
// what it says through Text.notify (plan T2).
package dev.workstream.jetbrains

import com.intellij.diff.DiffContentFactory
import com.intellij.diff.DiffManager
import com.intellij.diff.requests.DiffRequest
import com.intellij.diff.requests.SimpleDiffRequest
import com.intellij.icons.AllIcons
import com.intellij.ide.projectView.PresentationData
import com.intellij.ide.util.treeView.AbstractTreeStructure
import com.intellij.ide.util.treeView.NodeDescriptor
import com.intellij.ide.util.treeView.PresentableNodeDescriptor
import com.intellij.notification.NotificationType
import com.intellij.openapi.Disposable
import com.intellij.openapi.actionSystem.ActionManager
import com.intellij.openapi.actionSystem.DefaultActionGroup
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.fileEditor.OpenFileDescriptor
import com.intellij.openapi.fileTypes.FileTypeManager
import com.intellij.openapi.project.Project
import com.intellij.openapi.ui.SimpleToolWindowPanel
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VirtualFile
import com.intellij.testFramework.LightVirtualFile
import com.intellij.ui.ColoredTreeCellRenderer
import com.intellij.ui.DoubleClickListener
import com.intellij.ui.ScrollPaneFactory
import com.intellij.ui.SimpleTextAttributes
import com.intellij.ui.tree.AsyncTreeModel
import com.intellij.ui.tree.StructureTreeModel
import com.intellij.ui.treeStructure.Tree
import com.intellij.util.concurrency.Invoker
import com.intellij.util.ui.tree.TreeUtil
import dev.workstream.jetbrains.logic.EntryNode
import dev.workstream.jetbrains.logic.EvidenceNode
import dev.workstream.jetbrains.logic.FileNode
import dev.workstream.jetbrains.logic.FilesNode
import dev.workstream.jetbrains.logic.GateNode
import dev.workstream.jetbrains.logic.GatesNode
import dev.workstream.jetbrains.logic.GroupNode
import dev.workstream.jetbrains.logic.ItemNode
import dev.workstream.jetbrains.logic.ItemsNode
import dev.workstream.jetbrains.logic.Loaded
import dev.workstream.jetbrains.logic.NoteNode
import dev.workstream.jetbrains.logic.Opening
import dev.workstream.jetbrains.logic.ReviewNode
import dev.workstream.jetbrains.logic.ShowSide
import dev.workstream.jetbrains.logic.Side
import dev.workstream.jetbrains.logic.diffTitle
import dev.workstream.jetbrains.logic.entryChildren
import dev.workstream.jetbrains.logic.fileChildren
import dev.workstream.jetbrains.logic.gateChildren
import dev.workstream.jetbrains.logic.gateMark
import dev.workstream.jetbrains.logic.groupChildren
import dev.workstream.jetbrains.logic.itemChildren
import dev.workstream.jetbrains.logic.opening
import dev.workstream.jetbrains.logic.queueNodes
import dev.workstream.jetbrains.logic.reviewShown
import dev.workstream.jetbrains.logic.sideTitle
import java.awt.event.KeyAdapter
import java.awt.event.KeyEvent
import java.awt.event.MouseEvent
import java.util.concurrent.CompletableFuture
import java.util.concurrent.ConcurrentHashMap
import javax.swing.Icon
import javax.swing.JTree

/** The tree's contents, asked for on a background thread, since a task's come from `ws review --checks`. */
class ReviewStructure(private val project: Project) : AbstractTreeStructure() {
    private val root = Any()
    private val latest = ConcurrentHashMap<ReviewNode, ReviewNode>()

    fun latest(node: ReviewNode): ReviewNode = latest[node] ?: node

    override fun getRootElement(): Any = root

    override fun getChildElements(element: Any): Array<Any> {
        val ws = Workstreams.of(project)
        val found: List<ReviewNode> = when (element) {
            root -> if (ws.root == null || ws.snapshot == null) listOf() else when (val got = ws.reviewQueue()) {
                is Loaded.Error -> listOf(NoteNode("review\u001ferror", got.error, true))
                is Loaded.Value -> queueNodes(got.value)
            }
            is GroupNode -> groupChildren(latest(element) as GroupNode)
            is EntryNode -> {
                val entry = (latest(element) as EntryNode).entry
                when (val got = ws.review(entry.workstream, entry.task)) {
                    is Loaded.Error -> listOf(NoteNode("${element.id}\u001ferror", got.error, true))
                    is Loaded.Value -> entryChildren(element, got.value)
                }
            }
            is GatesNode -> gateChildren(latest(element) as GatesNode)
            is ItemsNode -> itemChildren(latest(element) as ItemsNode)
            is FilesNode -> fileChildren(latest(element) as FilesNode)
            else -> listOf()
        }
        for (node in found) latest[node] = node
        return found.toTypedArray()
    }

    override fun getParentElement(element: Any): Any? = null

    override fun isAlwaysLeaf(element: Any): Boolean = element is ReviewNode && !reviewShown(element).collapsible

    override fun createDescriptor(element: Any, parentDescriptor: NodeDescriptor<*>?): NodeDescriptor<*> =
        ReviewDescriptor(project, parentDescriptor, this, element)

    override fun commit() = Unit

    override fun hasSomethingToCommit(): Boolean = false
}

class ReviewDescriptor(project: Project, parent: NodeDescriptor<*>?, private val structure: ReviewStructure, private val element: Any) :
    PresentableNodeDescriptor<Any>(project, parent) {
    val node: ReviewNode? get() = (element as? ReviewNode)?.let(structure::latest)

    override fun getElement(): Any = element

    override fun update(presentation: PresentationData) {
        val node = node ?: return
        presentation.presentableText = reviewShown(node).label
        presentation.setIcon(reviewIconOf(node))
    }
}

private val GATE_ICONS: Map<String, Icon> = mapOf("ok" to AllIcons.General.InspectionsOK, "stop" to AllIcons.General.Error, "warned" to AllIcons.General.Warning)
private val LEVEL_ICONS: Map<String, Icon> = mapOf("good" to AllIcons.General.InspectionsOK, "warn" to AllIcons.General.Warning, "bad" to AllIcons.General.Error)

fun reviewIconOf(node: ReviewNode): Icon? = when (node) {
    is GroupNode -> if (node.state == "branch") AllIcons.Vcs.Branch else AllIcons.Vcs.Merge
    is EntryNode -> AllIcons.Nodes.Folder
    is GatesNode -> LEVEL_ICONS[node.level] ?: AllIcons.General.Information
    is GateNode -> GATE_ICONS[gateMark(node.gate)]
    is ItemsNode -> AllIcons.Nodes.Folder
    is ItemNode -> if (node.item.proof.isNotEmpty()) AllIcons.General.InspectionsOK else AllIcons.General.Warning
    is EvidenceNode -> AllIcons.FileTypes.Text
    is FilesNode -> AllIcons.Nodes.Folder
    is FileNode -> if (node.file.added == null) AllIcons.FileTypes.Any_type else AllIcons.Actions.Diff
    is NoteNode -> if (node.error) AllIcons.General.Error else AllIcons.General.Information
}

/** Draws a node's label and description as text, and its tooltip through Text.tip. */
class ReviewRenderer : ColoredTreeCellRenderer() {
    override fun customizeCellRenderer(tree: JTree, value: Any?, selected: Boolean, expanded: Boolean, leaf: Boolean, row: Int, hasFocus: Boolean) {
        val node = (TreeUtil.getUserObject(value) as? ReviewDescriptor)?.node ?: return
        val s = reviewShown(node)
        append(s.label, if (node is NoteNode && node.error) SimpleTextAttributes.ERROR_ATTRIBUTES else SimpleTextAttributes.REGULAR_ATTRIBUTES)
        if (s.description.isNotEmpty()) append("  ${s.description}", SimpleTextAttributes.GRAYED_ATTRIBUTES)
        icon = reviewIconOf(node)
        toolTipText = Text.tip(s.tip)
    }
}

/** What opening a file or evidence came to: the request shown, a line said, or the file opened. */
sealed interface Opened {
    data class Diff(val request: SimpleDiffRequest) : Opened
    data class Said(val text: String, val error: Boolean) : Opened
    data class Evidence(val file: VirtualFile) : Opened
}

object ReviewOpen {
    /** How a diff request is shown; a headless test swaps it to keep the request. */
    @Volatile
    var showDiff: (Project, DiffRequest) -> Unit = { project, request -> DiffManager.getInstance().showDiff(project, request) }

    /** A diff between `--show`'s two sides, titled with the path, the task and each side's rev. */
    fun request(project: Project, task: String, old: ShowSide, new: ShowSide): SimpleDiffRequest {
        val type = FileTypeManager.getInstance().getFileTypeByFileName(old.path.substringAfterLast('/'))
        val factory = DiffContentFactory.getInstance()
        return SimpleDiffRequest(diffTitle(old.path, task, old.rev, new.rev),
                                 factory.create(project, old.text ?: "", type), factory.create(project, new.text ?: "", type),
                                 sideTitle(old), sideTitle(new))
    }

    /**
     * Reads both sides off the EDT, then on it shows the diff, or says why not: a binary side
     * opens nothing. A side the file isn't on is empty, as an added file's old side is.
     */
    fun openFile(project: Project, node: FileNode): CompletableFuture<Opened> {
        val done = CompletableFuture<Opened>()
        val app = ApplicationManager.getApplication()
        app.executeOnPooledThread {
            try {
                val ws = Workstreams.of(project)
                val path = node.file.path
                val got = opening(path, ws.show(node.ws, node.task, path, Side.OLD), ws.show(node.ws, node.task, path, Side.NEW))
                app.invokeLater({
                    try {
                        done.complete(show(project, node.task, got))
                    } catch (e: Throwable) {
                        done.completeExceptionally(e)
                    }
                }, project.disposed)
            } catch (e: Throwable) {
                done.completeExceptionally(e)
            }
        }
        return done
    }

    private fun show(project: Project, task: String, got: Opening): Opened = when (got) {
        is Opening.Say -> {
            Text.notify(project, got.text, if (got.error) NotificationType.ERROR else NotificationType.INFORMATION)
            Opened.Said(got.text, got.error)
        }
        is Opening.Sides -> {
            val request = request(project, task, got.old, got.new)
            showDiff(project, request)
            Opened.Diff(request)
        }
    }

    /** A landed task's evidence opens as its file; a branch task's opens read-only, as `--checks` read it from the branch. */
    fun openEvidence(project: Project, node: EvidenceNode): Opened {
        val fs = LocalFileSystem.getInstance()
        val landed = if (!node.onBranch && node.path != null) fs.findFileByPath(node.path) ?: fs.refreshAndFindFileByPath(node.path) else null
        val file = landed ?: LightVirtualFile("${node.task}.md", node.text).apply { isWritable = false }
        OpenFileDescriptor(project, file).navigate(true)
        return Opened.Evidence(file)
    }
}

class ReviewPanel(private val project: Project, parent: Disposable) : SimpleToolWindowPanel(true, true) {
    val structure = ReviewStructure(project)
    val model = StructureTreeModel(structure, null, Invoker.forBackgroundPoolWithoutReadAction(parent), parent)
    val tree = Tree(AsyncTreeModel(model, parent))

    init {
        tree.isRootVisible = false
        tree.showsRootHandles = true
        tree.cellRenderer = ReviewRenderer()
        object : DoubleClickListener() {
            override fun onDoubleClick(event: MouseEvent): Boolean = openSelected()
        }.installOn(tree)
        tree.addKeyListener(object : KeyAdapter() {
            override fun keyPressed(e: KeyEvent) {
                if (e.keyCode == KeyEvent.VK_ENTER && openSelected()) e.consume()
            }
        })
        val toolbar = ActionManager.getInstance().createActionToolbar("WorkstreamsReview", DefaultActionGroup(RefreshAction()), true)
        toolbar.targetComponent = this
        setToolbar(toolbar.component)
        setContent(ScrollPaneFactory.createScrollPane(tree))
        project.messageBus.connect(parent).subscribe(Workstreams.CHANGED, Workstreams.Changed { model.invalidateAsync() })
    }

    fun selected(): ReviewNode? = (TreeUtil.getUserObject(tree.selectionPath?.lastPathComponent) as? ReviewDescriptor)?.node

    private fun openSelected(): Boolean = when (val node = selected()) {
        is FileNode -> { ReviewOpen.openFile(project, node); true }
        is EvidenceNode -> { ReviewOpen.openEvidence(project, node); true }
        else -> false
    }
}
