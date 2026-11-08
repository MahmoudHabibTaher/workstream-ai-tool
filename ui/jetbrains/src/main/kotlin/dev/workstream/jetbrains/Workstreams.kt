// One project's view of its workstreams: the root `ws root` gave, the last snapshot and each
// workstream's own snapshot once something asked for it. Every call runs on a background coroutine
// (plan T3); a missing `ws` or a folder that isn't a project gives one notification and stops there.
//
// Live refresh (plan T5): every path in the snapshot's `refresh` is watched by the VFS, a change
// under one of them, or the IDE window regaining focus, reloads the snapshot once per 300 ms burst.
package dev.workstream.jetbrains

import com.google.gson.JsonObject
import com.intellij.notification.NotificationType
import com.intellij.openapi.Disposable
import com.intellij.openapi.application.ApplicationActivationListener
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.service
import com.intellij.openapi.project.Project
import com.intellij.openapi.project.guessProjectDir
import com.intellij.openapi.startup.ProjectActivity
import com.intellij.openapi.vfs.LocalFileSystem
import com.intellij.openapi.vfs.VfsUtilCore
import com.intellij.openapi.vfs.VirtualFileManager
import com.intellij.openapi.vfs.VirtualFileVisitor
import com.intellij.openapi.vfs.newvfs.BulkFileListener
import com.intellij.openapi.vfs.newvfs.events.VFileEvent
import com.intellij.openapi.vfs.newvfs.events.VFileMoveEvent
import com.intellij.openapi.vfs.newvfs.events.VFilePropertyChangeEvent
import com.intellij.openapi.wm.IdeFrame
import com.intellij.util.messages.Topic
import dev.workstream.jetbrains.logic.Confirm
import dev.workstream.jetbrains.logic.Entry
import dev.workstream.jetbrains.logic.Loaded
import dev.workstream.jetbrains.logic.Review
import dev.workstream.jetbrains.logic.Revisions
import dev.workstream.jetbrains.logic.Rooted
import dev.workstream.jetbrains.logic.Run
import dev.workstream.jetbrains.logic.ShowSide
import dev.workstream.jetbrains.logic.Side
import dev.workstream.jetbrains.logic.Watch
import dev.workstream.jetbrains.logic.WsView
import dev.workstream.jetbrains.logic.activeWorkstream
import dev.workstream.jetbrains.logic.underRefresh
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.FlowPreview
import kotlinx.coroutines.Job
import kotlinx.coroutines.channels.BufferOverflow
import kotlinx.coroutines.flow.MutableSharedFlow
import kotlinx.coroutines.flow.debounce
import kotlinx.coroutines.launch
import java.util.concurrent.ConcurrentHashMap

const val DEBOUNCE_MS = 300L

@Service(Service.Level.PROJECT)
class Workstreams(private val project: Project, private val scope: CoroutineScope) : Disposable {
    /** Told after every load, from a background thread: the views redraw from here. */
    fun interface Changed {
        fun changed()
    }

    /** How commands run; a test wraps it to count them. */
    @Volatile
    var run: Run = ProcessRun

    @Volatile
    var root: String? = null
        private set

    @Volatile
    var snapshot: JsonObject? = null
        private set

    /** The last reload's failure, shown in the tree in place of the rows; null after a good one. */
    @Volatile
    var error: String? = null
        private set

    @Volatile
    var showDone: Boolean = false
        set(value) {
            field = value
            changed()
        }

    @Volatile
    var watches: List<Watch> = listOf()
        private set
    private var watched: Set<LocalFileSystem.WatchRequest> = setOf()
    private val views = ConcurrentHashMap<String, Loaded<WsView>>()
    private val reviews = ConcurrentHashMap<String, Loaded<Review>>()

    @Volatile
    private var queue: Loaded<List<Entry>>? = null

    // A poke during a reload waits in the buffer, so it makes exactly one more after it.
    private val pokes = MutableSharedFlow<Unit>(extraBufferCapacity = 1, onBufferOverflow = BufferOverflow.DROP_OLDEST)

    init {
        @OptIn(FlowPreview::class)
        scope.launch(Dispatchers.IO) { pokes.debounce(DEBOUNCE_MS).collect { reload() } }
        project.messageBus.connect(this).subscribe(VirtualFileManager.VFS_CHANGES, object : BulkFileListener {
            override fun after(events: List<VFileEvent>) {
                val now = watches
                if (now.isNotEmpty() && events.any { e -> pathsOf(e).any { underRefresh(it, now) } }) poke()
            }
        })
        ApplicationManager.getApplication().messageBus.connect(this)
            .subscribe(ApplicationActivationListener.TOPIC, object : ApplicationActivationListener {
                override fun applicationActivated(ideFrame: IdeFrame) {
                    if (root != null) poke()
                }
            })
    }

    private fun pathsOf(e: VFileEvent): List<String> = listOfNotNull(
        e.path,
        (e as? VFileMoveEvent)?.newPath,
        (e as? VFilePropertyChangeEvent)?.takeIf { it.isRename }?.newPath,
    )

    /** Finds the project's root from `folder`, then loads its snapshot, off the EDT. */
    fun open(folder: String): Job = scope.launch(Dispatchers.IO) { load(folder) }

    /** Asks for a reload: pokes within 300 ms of each other make one. */
    fun poke() {
        pokes.tryEmit(Unit)
    }

    /** Reloads now, off the EDT: the Refresh action. */
    fun refresh(): Job = scope.launch(Dispatchers.IO) { reload() }

    /**
     * The confirmed write, off the EDT: `ws act` against the pinned revisions. Its line, or its
     * refusal as given, is one notification (escaped, plan T2), then the snapshot reloads.
     */
    fun act(ws: String, confirm: Confirm, pinned: Revisions): Job = scope.launch(Dispatchers.IO) {
        val at = root ?: return@launch
        val acted = cli().runAct(at, ws, confirm, pinned)
        Text.notify(project, acted.line, if (acted.refused) NotificationType.ERROR else NotificationType.INFORMATION)
        reload()
    }

    private fun cli() = Cli.fromSettings(run)

    private fun load(folder: String) {
        when (val found = cli().resolveRoot(folder)) {
            is Rooted.Problem -> {
                root = null
                snapshot = null
                Text.notify(project, found.message)
                changed()
            }
            is Rooted.Root -> {
                root = found.path
                reload()?.let { Text.notify(project, it) }
            }
        }
    }

    /** Loads the snapshot again and the active workstream's own; returns the failure, if any. */
    private fun reload(): String? {
        val at = root ?: return null
        val cli = cli()
        when (val got = cli.loadSnapshot(at)) {
            is Loaded.Error -> error = got.error
            is Loaded.Value -> {
                views.clear()
                reviews.clear()
                queue = null
                snapshot = got.value
                error = null
                watch(Snapshots.refresh(got.value))
                activeWorkstream(Snapshots.rows(got.value), Snapshots.health(got.value))?.let { (row, _) -> view(row.id) }
            }
        }
        changed()
        return error
    }

    /** A workstream's own snapshot, read once per reload. It runs `ws`, so never on the EDT. */
    fun view(id: String): Loaded<WsView> {
        views[id]?.let { return it }
        val at = root ?: return Loaded.Error("no project is open")
        val got = when (val loaded = cli().loadSnapshot(at, id)) {
            is Loaded.Error -> loaded
            is Loaded.Value -> Loaded.Value(Snapshots.view(loaded.value))
        }
        views[id] = got
        return got
    }

    /** `ws review --queue`, read once per reload. It runs `ws`, so never on the EDT. */
    fun reviewQueue(): Loaded<List<Entry>> {
        queue?.let { return it }
        val at = root ?: return Loaded.Error("no project is open")
        return Reviews.queue(cli().loadQueue(at)).also { queue = it }
    }

    /** One task's `ws review --checks`, read once per reload. Never on the EDT. */
    fun review(ws: String, task: String): Loaded<Review> {
        val k = "$ws\u001f$task"
        reviews[k]?.let { return it }
        val at = root ?: return Loaded.Error("no project is open")
        return Reviews.review(cli().loadReview(at, ws, task, checks = true)).also { reviews[k] = it }
    }

    /** One side of one file, read each time it opens, since the diff shows it as it is now. Never on the EDT. */
    fun show(ws: String, task: String, path: String, side: Side): Loaded<ShowSide> {
        val at = root ?: return Loaded.Error("no project is open")
        return Reviews.show(cli().loadShow(at, ws, task, path, side))
    }

    /** The cached view, if this reload has read it: what the status bar draws without waiting. */
    fun cachedView(id: String): WsView? = (views[id] as? Loaded.Value)?.value

    /**
     * Watches each refresh path, keeping its recursive flag, and loads it into the VFS: a change
     * reaches VFS_CHANGES only for a file the VFS already knows.
     */
    private fun watch(now: List<Watch>) {
        if (now == watches) return
        val fs = LocalFileSystem.getInstance()
        synchronized(this) {
            watched = fs.replaceWatchedRoots(watched, now.filter { it.recursive }.map { it.path }, now.filter { !it.recursive }.map { it.path })
        }
        for (w in now) {
            val file = fs.refreshAndFindFileByPath(w.path) ?: continue
            if (w.recursive) {
                VfsUtilCore.visitChildrenRecursively(file, object : VirtualFileVisitor<Any>() {})
            } else if (file.isDirectory) {
                file.children
            }
        }
        watches = now
    }

    private fun changed() {
        if (!project.isDisposed) project.messageBus.syncPublisher(CHANGED).changed()
    }

    /** The VFS watch requests held for the refresh paths. */
    fun watchRequests(): Set<LocalFileSystem.WatchRequest> = synchronized(this) { watched }

    /** Back to nothing opened: a light test project, and so this service, outlives each test. */
    @org.jetbrains.annotations.TestOnly
    fun forget() {
        dispose()
        root = null
        snapshot = null
        error = null
        watches = listOf()
        views.clear()
        reviews.clear()
        queue = null
        showDone = false
    }

    override fun dispose() {
        synchronized(this) {
            LocalFileSystem.getInstance().removeWatchedRoots(watched)
            watched = setOf()
        }
    }

    companion object {
        @Topic.ProjectLevel
        val CHANGED: Topic<Changed> = Topic(Changed::class.java, Topic.BroadcastDirection.NONE)

        fun of(project: Project): Workstreams = project.service()
    }
}

/** Opens the project's workstreams once it has loaded. Tests call `open` themselves. */
class OpenWorkstreams : ProjectActivity {
    override suspend fun execute(project: Project) {
        if (ApplicationManager.getApplication().isUnitTestMode) return
        val folder = project.guessProjectDir()?.path ?: project.basePath ?: return
        Workstreams.of(project).open(folder)
    }
}
