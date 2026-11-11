// Where a launch goes (D-ACTIONS, D-DIALOG). The launch dialog names a target; it starts the
// launch if it can take it now, else the prompt goes to the clipboard. With no target named, the
// first that can take it starts it. Today the targets are the Terminal, when an agent argv is
// given or the agent command is set and the Terminal plugin is on, the chat targets in
// ChatTargets.kt while their plugins are on, then the clipboard. Callers only
// call `Launcher.launch` and show what it said, so they never know which target's class ran. Apart from Cli.kt, this is the only file that starts a process:
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

/**
 * A launch: the tab's title, the finished prompt and the folder the agent starts in. `argv` is the
 * agent's command line as `ws launch argv` built it for the chosen preset; null uses the agent command.
 */
data class LaunchRequest(val title: String, val prompt: String, val root: String, val argv: List<String>? = null)

/** What the target did, in a line the caller shows; `argv` is the process a Terminal tab runs. */
data class Started(val target: String, val said: String, val argv: List<String>? = null)

interface LaunchTarget {
    /** The target's name, the `target` of what it starts. */
    val id: String

    /** What the launch dialog's target picker calls it. */
    val label: String get() = id

    /** False while the target's plugin is missing, so the launch dialog doesn't offer it. */
    val available: Boolean get() = true

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
    override val label: String = "Terminal"

    override fun start(project: Project, request: LaunchRequest): Started? {
        val argv = request.argv ?: terminalArgv(WsSettings.getInstance().agentCommand, request.prompt) ?: return null
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
const val CLIPBOARD = "clipboard"

object Launcher {
    val TARGETS: ExtensionPointName<LaunchTarget> = ExtensionPointName.create("dev.workstream.jetbrains.launchTarget")

    /** The targets a launch can go to now, in picker order: each registered one, then the clipboard. */
    fun choices(): List<Pair<String, String>> = TARGETS.extensionList.filter { it.available }.map { it.id to it.label } + (CLIPBOARD to "Clipboard")

    /**
     * Starts the request with `target`, or with the first target that takes it when none is named;
     * else copies the prompt and says why. Launcher never names a target's class, so it loads
     * without the Terminal plugin. On the EDT.
     */
    fun launch(project: Project, request: LaunchRequest, target: String? = null): Started {
        val targets = TARGETS.extensionList
        if (target == CLIPBOARD) {
            CopyPasteManager.getInstance().setContents(StringSelection(request.prompt))
            return Started(CLIPBOARD, "Copied the ${request.title} prompt to the clipboard. Prompt: ${request.prompt}")
        }
        for (each in targets.filter { if (target == null) it.available else it.id == target }) {
            each.start(project, request)?.let { return it }
        }
        CopyPasteManager.getInstance().setContents(StringSelection(request.prompt))
        val agentSet = request.argv != null || terminalArgv(WsSettings.getInstance().agentCommand, request.prompt) != null
        return Started(CLIPBOARD, clipboardLine(request.title, request.prompt, targets.any { it.id == TERMINAL }, agentSet))
    }
}
