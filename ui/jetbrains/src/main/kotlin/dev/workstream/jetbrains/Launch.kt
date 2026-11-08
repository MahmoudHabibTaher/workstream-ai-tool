// Where a launch goes (D-ACTIONS). Each target says whether it can take the launch now; the first
// that can starts it. Today that is the Terminal, when the agent command is set and the Terminal
// plugin is on, then the clipboard. Callers only call `Launcher.launch` and show what it said, so
// they never know which target ran. Apart from Cli.kt, this is the only file that starts a process:
// the agent, as a Terminal tab's own process (plan T7).
package dev.workstream.jetbrains

import com.intellij.openapi.extensions.ExtensionPointName
import com.intellij.openapi.ide.CopyPasteManager
import com.intellij.openapi.project.Project
import dev.workstream.jetbrains.logic.clipboardLine
import dev.workstream.jetbrains.logic.terminalArgv
import dev.workstream.jetbrains.logic.terminalLine
import org.jetbrains.plugins.terminal.LocalTerminalDirectRunner
import org.jetbrains.plugins.terminal.TerminalTabState
import org.jetbrains.plugins.terminal.TerminalToolWindowManager
import java.awt.datatransfer.StringSelection

/** A launch: the tab's title, the finished prompt and the folder the agent starts in. */
data class LaunchRequest(val title: String, val prompt: String, val root: String)

/** What the target did, in a line the caller shows; `argv` is the process a Terminal tab runs. */
data class Started(val target: String, val said: String, val argv: List<String>? = null)

interface LaunchTarget {
    /** The target's name, the `target` of what it starts. */
    val id: String

    /** Null when this target can't take the request, so the next one is tried. */
    fun start(project: Project, request: LaunchRequest): Started?
}

/** Opens a Terminal tab running `argv` in `cwd`; a test swaps it to see the argv. */
fun interface TerminalOpener {
    fun open(project: Project, cwd: String, tab: String, argv: List<String>)
}

/**
 * The Terminal target, registered in workstreams-terminal.xml, so it exists only when the Terminal
 * plugin does. `createNewSession` runs the argv as the tab's process: no shell parses the prompt.
 */
class TerminalTarget : LaunchTarget {
    override val id: String = TERMINAL

    override fun start(project: Project, request: LaunchRequest): Started? {
        val argv = terminalArgv(WsSettings.getInstance().agentCommand, request.prompt) ?: return null
        opener.open(project, request.root, "Workstreams: ${request.title}", argv)
        return Started(id, terminalLine(argv, request.title), argv)
    }

    companion object {
        // The tab state's shellCommand is the tab process's argv. The five-argument
        // createNewSession(workingDir, tabName, command, ...) does the same but is @ApiStatus.Internal.
        private val OPEN = TerminalOpener { project, cwd, tab, argv ->
            val state = TerminalTabState().apply {
                myTabName = tab
                myIsUserDefinedTabTitle = true
                myShellCommand = argv
                myWorkingDirectory = cwd
            }
            TerminalToolWindowManager.getInstance(project).createNewSession(LocalTerminalDirectRunner.createTerminalRunner(project), state)
        }

        @Volatile
        var opener: TerminalOpener = OPEN

        @org.jetbrains.annotations.TestOnly
        fun reset() {
            opener = OPEN
        }
    }
}

const val TERMINAL = "terminal"

object Launcher {
    val TARGETS: ExtensionPointName<LaunchTarget> = ExtensionPointName.create("dev.workstream.jetbrains.launchTarget")

    /**
     * Starts the request with the first target that takes it, else copies the prompt and says why.
     * Launcher never names a target's class, so it loads without the Terminal plugin. On the EDT.
     */
    fun launch(project: Project, request: LaunchRequest): Started {
        val targets = TARGETS.extensionList
        for (target in targets) {
            target.start(project, request)?.let { return it }
        }
        CopyPasteManager.getInstance().setContents(StringSelection(request.prompt))
        val agentSet = terminalArgv(WsSettings.getInstance().agentCommand, request.prompt) != null
        return Started("clipboard", clipboardLine(request.title, request.prompt, targets.any { it.id == TERMINAL }, agentSet))
    }
}
