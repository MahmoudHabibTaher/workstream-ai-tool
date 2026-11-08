// One project's view of its workstreams: the root `ws root` gave and the last snapshot. Every call
// runs on a background coroutine (plan T3); a missing `ws` or a folder that isn't a project gives
// one notification and stops there.
package dev.workstream.jetbrains

import com.google.gson.JsonObject
import com.intellij.openapi.application.ApplicationManager
import com.intellij.openapi.components.Service
import com.intellij.openapi.components.service
import com.intellij.openapi.project.Project
import com.intellij.openapi.project.guessProjectDir
import com.intellij.openapi.startup.ProjectActivity
import dev.workstream.jetbrains.logic.Loaded
import dev.workstream.jetbrains.logic.Rooted
import dev.workstream.jetbrains.logic.Run
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

@Service(Service.Level.PROJECT)
class Workstreams(private val project: Project, private val scope: CoroutineScope) {
    /** How commands run; a test wraps it to count them. */
    @Volatile
    var run: Run = ProcessRun

    @Volatile
    var root: String? = null
        private set

    @Volatile
    var snapshot: JsonObject? = null
        private set

    /** Finds the project's root from `folder`, then loads its snapshot, off the EDT. */
    fun open(folder: String): Job = scope.launch(Dispatchers.IO) { load(folder) }

    private fun load(folder: String) {
        val cli = Cli.fromSettings(run)
        when (val found = cli.resolveRoot(folder)) {
            is Rooted.Problem -> {
                root = null
                snapshot = null
                Text.notify(project, found.message)
            }
            is Rooted.Root -> {
                root = found.path
                when (val got = cli.loadSnapshot(found.path)) {
                    is Loaded.Error -> Text.notify(project, got.error)
                    is Loaded.Value -> snapshot = got.value
                }
            }
        }
    }

    companion object {
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
